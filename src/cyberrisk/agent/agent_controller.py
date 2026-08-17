"""Agent controller: the LLM tool-calling loop.

Owns the conversation memory, the tool registry and the LLM client (chosen
by the LLM_PROVIDER factory -- OpenAI or DeepSeek), and runs the loop:

    1. Append the user's latest message to memory.
    2. Send the full message history + tool schemas to the provider.
    3. If the model requested tools, execute each one (validated args),
       append the results as `role: tool` messages, and go back to 2.
    4. If the model produced text, that is the consultant's answer -- run
       the existing hallucination check against the metrics the tools
       actually returned, then return it.

Bounded by ``max_tool_rounds`` so a misbehaving model cannot loop forever.

Nothing here touches the quantitative engine directly -- the tools in
tools.py are the only code that does, and they never mutate it.
"""

from __future__ import annotations

import json
from typing import Any

from cyberrisk.agent.disclosure import append_disclosure
from cyberrisk.agent.memory import ClientFacts, ConversationMemory
from cyberrisk.agent.model_mechanics import explain_model_mechanics
from cyberrisk.agent.prompts import SENIOR_CONSULTANT_DIRECTIVES, SYSTEM_PROMPT
from agent.safety import OutputCheck  # existing hallucination guard (src/agent)
from cyberrisk.agent.schemas import AgentConfig, CompanyBrief, PolicyInput, ToolResult
from cyberrisk.agent.sensitivity_tools import run_control_improvement_scenario
from cyberrisk.agent.tools import (
    TOOL_SCHEMAS,
    analyse_insurance_structure,
    assess_company_risk,
    generate_demo_assessment,
    generate_risk_report,
    run_loss_simulation,
    search_incidents,
)
from cyberrisk.llm.base import LLMClient
from cyberrisk.llm.factory import create_llm_client

# Tool name -> callable(brief_fields: dict, extra_args: dict) -> dict
_TOOL_IMPLEMENTATIONS = {
    "assess_company_risk": lambda brief, extra: assess_company_risk(brief),
    "run_loss_simulation": lambda brief, extra: run_loss_simulation(
        brief, n_years=extra.get("n_years")
    ),
    "analyse_insurance_structure": lambda brief, extra: analyse_insurance_structure(
        brief,
        policy=PolicyInput(
            per_occurrence_deductible=extra.get("per_occurrence_deductible", 250_000.0),
            per_occurrence_limit=extra.get("per_occurrence_limit"),
            annual_aggregate_deductible=extra.get("annual_aggregate_deductible", 1_000_000.0),
            annual_aggregate_limit=extra.get("annual_aggregate_limit"),
            coinsurance=extra.get("coinsurance", 0.0),
        ),
        n_years=extra.get("n_years"),
    ),
    "generate_risk_report": lambda brief, extra: generate_risk_report(
        brief,
        firm_name=extra.get("firm_name"),
        out_dir=extra.get("out_dir"),
        n_years=extra.get("n_years"),
    ),
    "run_control_improvement_scenario": lambda brief, extra: run_control_improvement_scenario(
        brief,
        control_change=extra.get("control_change"),
        n_years=extra.get("n_years"),
    ),
    "search_incidents": lambda brief, extra: search_incidents(
        industry=extra.get("industry"),
        attack_type=extra.get("attack_type"),
        company=extra.get("company"),
        limit=extra.get("limit"),
    ),
    # Demo fabrication: takes only non-brief knobs (sector / n_years) so it
    # never mutates the running client facts -- a demo run is session-isolated
    # and a follow-up about the real company returns to the real profile.
    "generate_demo_assessment": lambda brief, extra: generate_demo_assessment(
        sector=extra.get("sector"),
        n_years=extra.get("n_years"),
    ),
}

# Tool arguments that are client-facts rather than tool-specific knobs.
_BRIEF_KEYS = {
    "industry",
    "revenue_usd",
    "customer_records",
    "technology_dependency",
    "security_controls",
    "previous_incidents",
    "existing_coverage",
    "risk_appetite",
}


class CyberRiskAgent:
    """The LLM-powered cyber risk consultant (provider-agnostic)."""

    def __init__(
        self,
        client: LLMClient | None = None,
        config: AgentConfig | None = None,
        memory: ConversationMemory | None = None,
        facts: ClientFacts | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        # Provider picked by LLM_PROVIDER (openai | deepseek) via the factory.
        self.client = client or create_llm_client(self.config)
        self.memory = memory or ConversationMemory()
        self.facts = facts or ClientFacts()
        # Tool trace for the current turn: every tool that ran this turn,
        # its arguments, and its data (so the UI can render charts from the
        # figures the model actually used).  Reset at the start of each chat().
        self.tool_trace: list[dict] = []
        # Last privacy notice returned by the input guard (UI surfaces this).
        self.last_privacy_notice: str = ""
        self._init_system()

    def _init_system(self) -> None:
        """Seed memory with the system prompt (idempotent).

        The internal white-box methodology is appended to the system prompt so
        the model can explain how the model produced its figures (scoring ->
        frequency/severity adjustments -> Monte Carlo -> VaR/ES) without
        treating it as a third-party black box.
        """
        if not self.memory.get() or self.memory.get()[0].get("role") != "system":
            methodology = explain_model_mechanics().full_text()
            system_message = {
                "role": "system",
                "content": SYSTEM_PROMPT
                + "\n\n"
                + SENIOR_CONSULTANT_DIRECTIVES
                + "\n\n"
                + methodology,
            }
            # System message belongs FIRST: the tool loop reads
            # ``memory[0]`` as the base system prompt and the per-turn RAG
            # injection is insert(0)/pop(0) around it.  A restored session
            # (memory seeded from persisted user/assistant rows) must get the
            # system prompt at the front, not appended to the tail.
            self.memory.messages.insert(0, system_message)

    # ------------------------------------------------------------------
    # RAG context injection
    # ------------------------------------------------------------------

    def _rag_context(self, query: str) -> str:
        """Retrieve knowledge relevant to ``query`` and render it as context.

        Two retrieval sources:
          1. the vector store — semantic chunk retrieval (documents),
          2. the incident index — structured historical incidents, matched by
             field keywords in the query (industry / attack type).

        Returns an empty string when neither source returns anything, so the
        agent still works without a populated knowledge base (retrieval is
        additive, never required).
        """
        blocks: list[str] = []

        # 1. Semantic chunk retrieval from the vector store.
        try:
            from cyberrisk.knowledge.rag import Retriever
            from cyberrisk.knowledge.config import load_ingest_config

            retriever = Retriever.from_derived(derived_root=load_ingest_config().derived_path)
            results = retriever.retrieve(query)
            if results:
                blocks.append(retriever.format_context(results))
        except FileNotFoundError:
            pass  # no vector store yet — skip
        except Exception:  # noqa: BLE001 — never let retrieval break a consult
            pass

        # 2. Structured incident retrieval by field keywords in the query.
        try:
            from cyberrisk.knowledge.incidents import load_incident_index

            index = load_incident_index()
            incidents = self._incidents_for_query(index, query)
            for inc in incidents[:3]:
                blocks.append(inc.narrative())
        except Exception:  # noqa: BLE001 — incidents are optional context
            pass

        return "\n\n".join(blocks)

    @staticmethod
    def _incidents_for_query(index, query: str) -> list:
        """Match incidents to a query by industry/attack-type keywords."""
        q = query.lower()
        industries = {
            "healthcare": "healthcare", "health": "healthcare", "hospital": "healthcare",
            "pharma": "healthcare",
            "finance": "finance", "bank": "finance", "financial": "finance",
            "insur": "finance", "fintech": "finance",
            "retail": "retail", "store": "retail", "e-commerce": "retail",
            "manufactur": "manufacturing", "industrial": "manufacturing",
            "energy": "energy", "utility": "energy", "grid": "energy", "power": "energy",
            "government": "government", "public sector": "government", "agency": "government",
            "technology": "technology", "software": "technology", "cloud": "technology",
            "saas": "technology", "tech": "technology",
        }
        attack_types = {
            "ransom": "ransomware", "extort": "ransomware",
            "bec": "BEC", "wire fraud": "BEC", "email compromise": "BEC",
            "breach": "breach", "data theft": "breach",
            "supply": "supply-chain", "third-party": "supply-chain",
        }
        industry = next((v for k, v in industries.items() if k in q), None)
        attack_type = next((v for k, v in attack_types.items() if k in q), None)
        if industry is None and attack_type is None:
            return []
        return index.search(industry=industry, attack_type=attack_type, limit=3)

    def _system_prompt_with_rag(self, query: str) -> str:
        """The system prompt, with retrieved-knowledge context appended.

        The base prompt + methodology is seeded once at init; per-query
        retrieved context is appended so the LLM reasons over both engine
        numbers (via tools) and cited knowledge.
        """
        base = self.memory.get()[0]["content"] if self.memory.get() else SYSTEM_PROMPT
        context = self._rag_context(query)
        if not context:
            return base
        from cyberrisk.agent.prompts import RAG_RULES

        return base + "\n\n" + RAG_RULES + "\n\nRETRIEVED KNOWLEDGE (cite by [citation: chunk_id]):\n" + context

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, user_message: str, welcome: bool = False) -> str:
        """Send a user message and return the consultant's final answer.

        Runs the bounded tool-calling loop.  Raises RuntimeError when the
        loop exhausts its rounds without a final answer, or on an API error.

        Every FINAL answer carries the mandatory model-limitations disclosure
        at the end (idempotent -- the memory stores the answer with the
        disclosure so later turns do not duplicate it).

        If the knowledge vector store is populated, the user's message is used
        as a retrieval query; retrieved context is injected into the system
        prompt for this turn so the LLM reasons over cited knowledge AND engine
        tool results.  The per-turn context is removed in ``finally`` so it
        does not leak into subsequent turns (it is per-query).
        """
        self.tool_trace = []
        # Privacy input guard: secrets are blocked outright; personal data
        # (emails, phones, names, local paths) is redacted before the text
        # reaches the model, per config/privacy.yaml.
        try:
            from cyberrisk.privacy import check_input

            verdict = check_input(user_message)
            self.last_privacy_notice = verdict.notice
            if verdict.action == "blocked":
                blocked = append_disclosure(verdict.notice or "That message was not processed.")
                # Record a neutral marker in history — never the secret itself.
                self.memory.append({"role": "user", "content": "[message blocked by privacy guard]"})
                self.memory.append({"role": "assistant", "content": blocked})
                return blocked
            user_message = verdict.message
        except ImportError:  # pragma: no cover - privacy module always present
            self.last_privacy_notice = ""
        base_system = self.memory.get()[0]["content"] if self.memory.get() else SYSTEM_PROMPT
        rag_system = self._system_prompt_with_rag(user_message)
        injected = False
        if rag_system != base_system:
            self.memory.messages.insert(0, {"role": "system", "content": rag_system})
            injected = True
        try:
            self._append_user(user_message, welcome=welcome)
            answer, tool_metrics = self._run_tool_loop()
        finally:
            if injected and self.memory.messages:
                # Pop the per-turn RAG system message, restoring the base.
                self.memory.messages.pop(0)
        # Hallucination backstop: check_llm_output validates every claim-framed
        # dollar figure in the answer against the metrics the tools returned
        # (5% tolerance).  It never blocks -- when the model drifted from the
        # numbers, add a visible caveat so the client is not misled.
        if not self._post_guard(answer, tool_metrics).ok:
            answer += (
                "\n\n(Note: some figures above could not be fully verified "
                "against the model's outputs; treat them as indicative.)"
            )
        answer = append_disclosure(answer)
        self.memory.append({"role": "assistant", "content": answer})
        return answer

    @property
    def brief(self) -> CompanyBrief:
        return self.facts.brief

    @staticmethod
    def explain_model_mechanics() -> dict[str, str]:
        """Return the internally developed model's methodology sections.

        Convenience pass-through for callers / tests: scoring methodology,
        frequency adjustments, severity adjustments, simulation methodology.
        """
        return explain_model_mechanics().sections()

    @staticmethod
    def explain_risk_measures(
        var_99: float,
        es_99: float,
        var_95: float | None = None,
        es_95: float | None = None,
        loss_definition: str = "total economic loss before insurance recovery",
    ) -> dict[str, str]:
        """Return actuarial-standard VaR/ES explanation sentences.

        Each sentence names the confidence level, the 1-year horizon, and the
        loss definition, and frames VaR as a threshold only a share of
        simulated years exceed (never a point-mass probability).
        """
        from cyberrisk.agent.risk_explanation import explain_risk_measures as _explain

        return _explain(var_99, es_99, var_95, es_95, loss_definition)

    @staticmethod
    def scenario_contribution(
        brief: CompanyBrief,
        n_years: int | None = None,
    ) -> dict:
        """Return the per-scenario EAL contribution with model-linked drivers.

        Each scenario carries its contribution share, AAL, frequency drivers,
        severity drivers, and recommended controls -- all derived from model
        outputs (simulated loss shares, the brief's factor scores, and the
        scenario config).  Pass-through for callers / tests.
        """
        from cyberrisk.agent.scenario_contribution import analyze_scenario_contribution

        return analyze_scenario_contribution(brief, n_years)

    # ------------------------------------------------------------------
    # Loop internals
    # ------------------------------------------------------------------

    def _append_user(self, message: str, welcome: bool = False) -> None:
        from cyberrisk.agent.prompts import WELCOME_GUIDANCE

        if welcome:
            message = f"{message}\n\n{WELCOME_GUIDANCE}"
        self.memory.append({"role": "user", "content": message})

    def _run_tool_loop(self) -> tuple[str, dict[str, float]]:
        from cyberrisk.agent.prompts import GROUNDING_REMINDER

        tool_metrics: dict[str, float] = {}
        grounded = False  # the final-answer reminder is injected once per turn
        for _round in range(self.config.max_tool_rounds):
            messages = self.memory.get()
            # Reinforce grounding only once, only after a tool ran this turn,
            # and WITHOUT persisting -- it is per-answer guidance, not part of
            # the conversation history.
            if not grounded and self.tool_trace:
                messages = [*messages, {"role": "user", "content": GROUNDING_REMINDER}]
                grounded = True
            response = self.client.chat(
                messages,
                tools=TOOL_SCHEMAS,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            if response.wants_tools:
                self._execute_tool_calls(response.tool_calls, tool_metrics)
                continue
            if response.content.strip():
                return response.content.strip(), tool_metrics
            # Empty content with no tools: let the model try again, bounded.
        raise RuntimeError(
            f"The agent did not produce a final answer within "
            f"{self.config.max_tool_rounds} tool rounds."
        )

    def _execute_tool_calls(
        self, tool_calls: list[dict[str, Any]], tool_metrics: dict[str, float]
    ) -> None:
        """Execute each requested tool, inject results, and record metrics."""
        # Assistant message must carry the tool_calls so DeepSeek can match
        # the tool results back to the calls.
        assistant = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                }
                for tc in tool_calls
            ],
        }
        self.memory.append(assistant)

        for tc in tool_calls:
            result = self._execute_one(tc["name"], tc.get("arguments", {}))
            self.memory.append(result.as_tool_message(tc["id"]))
            # Record the trace for chart rendering: the UI only ever charts
            # figures that a tool actually returned -- never fabricated ones.
            self.tool_trace.append({
                "name": tc["name"],
                "arguments": tc.get("arguments", {}),
                "ok": result.ok,
                "error": result.error,
                "data": result.data,
            })
            if result.ok and result.data:
                for key in ("eal", "var_99", "es_99"):
                    if key in result.data:
                        tool_metrics[key] = float(result.data[key])
                # Per-scenario facts (aal_by_scenario) let the hallucination
                # check validate figures like "ransomware is your largest driver".
                if "aal_by_scenario" in result.data:
                    tool_metrics.update(
                        {f"aal_{k}": float(v) for k, v in result.data["aal_by_scenario"].items()}
                    )
                # Insurance-response / client-retained figures validate the
                # three-section reporting (residual exposure, recovery).
                if "client_retained_loss" in result.data:
                    crl = result.data["client_retained_loss"]
                    for key in (
                        "retained_eal",
                        "retained_es_99",
                        "gross_loss_at_p99_9",
                        "insurance_recovery_at_p99_9",
                        "residual_exposure_at_p99_9",
                    ):
                        if key in crl:
                            tool_metrics[key] = float(crl[key])
                # Sensitivity figures (before/after) validate claims that a
                # control change reduced the loss -- only present after the
                # scenario tool actually ran.
                if "impact" in result.data and result.data.get("status") == "ok":
                    before = result.data.get("before", {})
                    after = result.data.get("after", {})
                    for key in ("eal", "var_99", "es_99"):
                        if key in before:
                            tool_metrics[f"before_{key}"] = float(before[key])
                        if key in after:
                            tool_metrics[f"after_{key}"] = float(after[key])
                    if "loss_reduction" in result.data.get("impact", {}):
                        tool_metrics["loss_reduction"] = float(
                            result.data["impact"]["loss_reduction"]
                        )

    def _post_guard(self, text: str, tool_metrics: dict[str, float]) -> OutputCheck:
        """Run the existing hallucination backstop on the final answer.

        Validates every claim-framed dollar figure in the answer against the
        metrics the tools actually returned (5% tolerance).  Does not block
        the answer -- it returns the verdict so the caller can warn if the
        model drifted from the numbers.
        """
        try:
            from agent.safety import check_llm_output
        except ImportError:  # pragma: no cover - the existing agent pkg is installed
            return OutputCheck(ok=True, reason="")
        if not tool_metrics:
            return OutputCheck(ok=True, reason="")
        return check_llm_output(text, validated_metrics=tool_metrics)

    def _execute_one(self, name: str, arguments: dict) -> ToolResult:
        """Run a single tool call with validated arguments."""
        try:
            impl = _TOOL_IMPLEMENTATIONS.get(name)
            if impl is None:
                return ToolResult(name=name, arguments=arguments, ok=False, error=f"unknown tool {name!r}")
            brief_fields = {k: v for k, v in arguments.items() if k in _BRIEF_KEYS}
            extra = {k: v for k, v in arguments.items() if k not in _BRIEF_KEYS}
            brief = CompanyBrief(**brief_fields)
            # Only merge genuine new facts into the running client picture.
            self.facts.update(brief)
            data = impl(self.facts.brief, extra)
            return ToolResult(name=name, arguments=arguments, ok=True, data=data)
        except Exception as exc:  # noqa: BLE001 - surface any tool failure to the LLM
            return ToolResult(name=name, arguments=arguments, ok=False, error=f"{type(exc).__name__}: {exc}")
