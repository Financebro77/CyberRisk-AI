"""Consultant agent (Phase E).

Consumes the validated outputs of the scoring engine, loss model, and
policy transform, and produces client-facing risk recommendations.

Deliberately implemented LAST, and this scaffold reflects that: the agent
takes ONLY already-computed outputs (ScoredFirm, RiskMetrics, policy
results) as inputs -- it never reaches into raw simulation internals or
config.  This keeps the reasoning grounded in auditable model output.

Backend model:
  - When `llm_backend` is None (default), it uses the deterministic
    rule-based fallback from prompts.py -- always runnable and testable.
  - Set `llm_backend` to a callable that maps a prompt string to a
    response string (e.g. a Claude / LLM client) to get generative
    recommendations.  The interface is intentionally narrow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent.elicitation import ElicitationResult, determine_missing
from agent.prompts import (
    SAFETY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_recommendation_prompt,
    rule_based_fallback,
)
from agent.safety import (
    OutputCheck,
    SafetyVerdict,
    check_llm_output,
    guard_request,
)
from cyberrisk.metrics import RiskMetrics
from cyberrisk.scoring import ScoredFirm

# A callable backend maps a prompt string to a generated response string.
LLMBackend = Callable[[str], str]


@dataclass
class AgentInput:
    """Validated inputs the agent is allowed to reason over."""

    firm_name: str
    risk_category: str
    risk_drivers: list[str]
    eal: float
    var_99: float
    es_99: float
    policy_recommendations: list[str] | None = None


@dataclass
class ConsultantRecommendation:
    """Final client-facing output."""

    firm_name: str
    risk_category: str
    summary: str
    risk_drivers: list[str]
    recommendations: list[str]
    generated_by: str  # "rule-based" or "llm"
    disclosure: str = ""  # mandatory model-limitations block (appended to every report)

    def full_report(self) -> str:
        """The complete advisory report text, ending with the disclosure."""
        lines = [
            f"Firm: {self.firm_name}",
            f"Risk category: {self.risk_category}",
            f"Summary: {self.summary}",
            f"Key risk drivers: {', '.join(self.risk_drivers) if self.risk_drivers else 'none identified'}",
            "",
            "Recommendations:",
        ]
        lines.extend(f"- {r}" for r in self.recommendations)
        report = "\n".join(lines)
        if self.disclosure:
            from cyberrisk.agent.disclosure import append_disclosure

            report = append_disclosure(report)
        return report


def _extract_recommendations(text: str) -> list[str]:
    """Parse bulleted recommendations out of a generated response."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "•", "*", "  -")) and len(stripped) > 2:
            cleaned = stripped.lstrip("- •*").strip()
            if cleaned:
                lines.append(cleaned)
    return lines


def elicit(provided: dict[str, object]) -> ElicitationResult:
    """Information-gathering phase: check what the client has provided.

    Returns an ElicitationResult.  If `complete` is False, the client-facing
    message (`formatted_response()`) asks for the missing dimensions and
    explains why each matters.  The senior-broker rule: do not give advice
    until `complete` is True.
    """
    return determine_missing(provided)


def advise(
    provided: dict[str, object],
    score_and_run,  # callable(provided) -> (ScoredFirm, RiskMetrics)
    llm_backend: LLMBackend | None = None,
    risk_appetite_text: str | None = None,
) -> ConsultantRecommendation | ElicitationResult:
    """Full first-meeting flow: elicit, then advise only if complete.

    This is the guard that prevents the agent from giving advice on
    incomplete data.  If any required dimension is missing, it returns an
    ElicitationResult (questions to ask) and does NOT produce a
    recommendation.  Only when all dimensions are present does it call
    `score_and_run`, run the risk-appetite check, and generate advice.

    Parameters
        provided            dict of client answers keyed by the 8 dimensions
        score_and_run       callable mapping a complete `provided` dict to a
                            (ScoredFirm, RiskMetrics) tuple
        llm_backend         optional LLM backend for recommendations
        risk_appetite_text  client's stated retention in free text, e.g.
                            "$1M retention" or "we want to keep premium low".
                            When parseable, the agent validates it against the
                            modelled EAL/ES99 and appends the verdict.
    """
    result = elicit(provided)
    if not result.complete:
        return result  # refuse premature advice; ask instead
    scored, metrics = score_and_run(provided)

    recommendation = generate_recommendations(scored, metrics, llm_backend=llm_backend)

    # Risk-appetite validation: append the reality-check verdict if we have
    # both a retention figure and a modelled tail.
    if risk_appetite_text:
        from agent.risk_appetite import parse_retention, validate_appetite

        retention = parse_retention(risk_appetite_text)
        verdict = validate_appetite(retention, metrics.eal, metrics.es_99)
        recommendation.recommendations.append(f"Risk appetite: {verdict.message}")

    return recommendation


def safe_advise(
    request_text: str | None,
    provided: dict[str, object] | None = None,
    score_and_run=None,  # callable(provided) -> (ScoredFirm, RiskMetrics)
    llm_backend: LLMBackend | None = None,
    risk_appetite_text: str | None = None,
) -> SafetyVerdict | ConsultantRecommendation | ElicitationResult:
    """Safety-guarded entry point: intercepts hallucination-class requests.

    Runs the five guardrails (nonexistent statistics, confidential data,
    unsupported recommendations, ambiguous info, contradictory info) BEFORE
    the normal elicit/advise flow.  If a request is intercepted, returns a
    SafetyVerdict with a safe response (admits uncertainty, requests info,
    avoids invention, cites assumptions).  Otherwise proceeds to `advise`.

    Returns
        SafetyVerdict if intercepted; otherwise the same as `advise()`.
    """
    # Privacy input guard: secrets are blocked, personal data redacted,
    # before the request text reaches the safety guards / agent.
    try:
        from cyberrisk.privacy import check_input

        pv = check_input(request_text or "")
        if pv.action == "blocked":
            return SafetyVerdict(
                class_name="privacy_block",
                flagged=True,
                response=pv.notice or "That message was not processed.",
                assumptions_cited=[],
            )
        request_text = pv.message or request_text
    except ImportError:  # pragma: no cover - privacy module always present
        pass

    verdict = guard_request(request_text, provided)
    if verdict.flagged:
        return verdict
    return advise(
        provided or {},
        score_and_run=score_and_run,
        llm_backend=llm_backend,
        risk_appetite_text=risk_appetite_text,
    )


def generate_recommendations(
    scored: ScoredFirm,
    metrics: RiskMetrics,
    llm_backend: LLMBackend | None = None,
    firm_name: str | None = None,
) -> ConsultantRecommendation:
    """Generate client-facing recommendations from validated model outputs.

    Parameters
        scored      ScoredFirm from scoring.compute_score
        metrics     RiskMetrics from metrics.compute_metrics
        llm_backend optional callable(prompt)->str for generative output
        firm_name   override display name (defaults to scored.firm_name)

    Returns a ConsultantRecommendation whose `recommendations` are always
    populated (rule-based fallback if no LLM backend supplied).

    NOTE: call `advise()` for the full first-meeting flow (elicit -> advise).
    Calling this directly bypasses the information-completeness guard; the
    caller is responsible for having complete information.
    """
    name = firm_name or scored.firm_name or "Client"
    drivers = scored.risk_drivers

    if llm_backend is not None:
        prompt = build_recommendation_prompt(
            name, scored.risk_category, drivers, metrics.eal, metrics.var_99, metrics.es_99
        )
        # Prepend the LLM-level safety prompt so the model is instructed to
        # avoid hallucination BEFORE generating.  The post-generation check
        # below is the backstop -- this prompt alone is not enough.
        full = f"{SAFETY_SYSTEM_PROMPT}\n\n{SYSTEM_PROMPT}\n\n{prompt}"
        response = llm_backend(full)

        # Post-generation hallucination check: only accept the LLM response if
        # it passes.  Otherwise fall back to the deterministic rule-based
        # recommendation -- never present hallucinated text to a client.
        validated = {
            "EAL": metrics.eal,
            "VaR95": metrics.var_95,
            "VaR99": metrics.var_99,
            "ES95": metrics.es_95,
            "ES99": metrics.es_99,
            "P99.0": metrics.p99_0,
            "P99.5": metrics.p99_5,
            "P99.9": metrics.p99_9,
        }
        check: OutputCheck = check_llm_output(response, validated_metrics=validated)
        if check.ok:
            recs = _extract_recommendations(response)
            summary = response.splitlines()[0] if response.strip() else scored.risk_category
            generated_by = "llm"
        else:
            # Hallucination detected -- fall back to the safe deterministic path.
            fallback = rule_based_fallback(
                name, scored.risk_category, drivers, metrics.eal
            )
            recs = _extract_recommendations(fallback)
            summary = (
                f"{scored.risk_category} (LLM response flagged: {check.reason})"
            )
            generated_by = "rule-based-fallback"
    else:
        fallback = rule_based_fallback(
            name, scored.risk_category, drivers, metrics.eal
        )
        recs = _extract_recommendations(fallback)
        summary = next(
            (ln for ln in fallback.splitlines() if ln.startswith("Summary: ")),
            scored.risk_category,
        ).replace("Summary: ", "")
        generated_by = "rule-based"

    from cyberrisk.agent.disclosure import disclosure_block

    return ConsultantRecommendation(
        firm_name=name,
        risk_category=scored.risk_category,
        summary=summary,
        risk_drivers=drivers,
        recommendations=recs,
        generated_by=generated_by,
        disclosure=disclosure_block(),
    )
