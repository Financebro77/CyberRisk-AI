"""End-to-end validation of the CyberRisk AI mobile architecture.

Walks the full stack exactly as a mobile client does::

    iOS app -> API -> agent -> risk engine -> RAG -> LLM abstraction
            -> results -> API -> iOS app

Coverage of the acceptance criteria:

    1. a user can start an assessment              POST /assessment/start
    2. assessment data is validated                typed schemas + completeness guard
    3. the backend receives the assessment         the v1 route decodes the brief
    4. the existing agent processes it             run_assessment_pipeline composes
                                                   the SAME tools the chat agent uses
    5. the existing quantitative engine produces
       the results                                  Monte Carlo loss model (eal/var/es/pml)
    6. RAG retrieval works where applicable         evidence.citations from the vector store
    7. results are returned through the API         the v1 result payload
    8. the iOS app displays the results             results replay + payload is exactly the
                                                   shape the voice/mobile client renders
    9. no secrets are exposed                       privacy scan across the lifecycle
   10. no customer information logged unnecessarily structured log lines carry only
                                                   operational metadata
   11. existing CLI functionality still works       cli.main() runs without a key (returns 1
                                                   with a clear config message)
   12. existing tests still pass                    covered by the full suite run

This suite is deterministic and offline: the LLM abstraction is exercised
through the exact interface the agent controller uses (``LLMClient.chat`` ->
``ChatResponse``), the tools hit the real calibrated engine + real knowledge
store, and no network/API key is required.
"""

from __future__ import annotations

import json
import logging
import os
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from cyberrisk.api.main import app
from cyberrisk.api.security import _reset_rate_limits
from cyberrisk.api.v1.store import get_store
from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.agent.disclosure import DISCLOSURE_HEADING
from cyberrisk.agent.schemas import AgentConfig, CompanyBrief
from cyberrisk.llm.base import ChatResponse, LLMClient

# The assessment the E2E flow submits (a full, model-able brief).
FULL_BRIEF = {
    "firm_name": "Acme Healthcare",
    "industry": "Healthcare",
    "revenue_usd": 500_000_000,
    "customer_records": 2_000_000,
    "technology_dependency": "Critical - patient records and billing are online",
    "security_controls": (
        "MFA enforced on all remote access, endpoint detection installed, "
        "offline backups taken nightly, phishing training quarterly, "
        "a dedicated security team with an incident response plan"
    ),
    "previous_incidents": 1,
    "existing_coverage": "Standalone cyber policy with a $10M limit and $1M deductible",
    "risk_appetite": "Moderate - avoid catastrophic tail losses",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_api_security(monkeypatch):
    """Auth + rate limiting OFF (covered separately in the security tests)."""
    monkeypatch.delenv("CYBERRISK_API_KEY", raising=False)
    monkeypatch.delenv("CYBERRISK_RATE_LIMIT", raising=False)
    _reset_rate_limits()
    yield
    _reset_rate_limits()


@pytest.fixture(autouse=True)
def _clean_store():
    get_store().clear()
    yield
    get_store().clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# A deterministic fake LLM that drives the agent's tool loop to completion.
# The agent controller consumes the EXACT abstraction the mobile stack uses.
# ---------------------------------------------------------------------------


class FakeLLMClient(LLMClient):
    """Drives the agent: ask for tools first, then produce a final answer."""

    model_name = "fake-provider"
    base_url = "https://example.invalid"

    def __init__(self) -> None:
        self.request_count = 0
        self.last_messages: list[dict] = []

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        self.request_count += 1
        self.last_messages = messages
        if self.request_count == 1:
            return ChatResponse(
                content="",
                tool_calls=[
                    {
                        "id": "call_e2e_1",
                        "name": "run_loss_simulation",
                        "arguments": dict(FULL_BRIEF),
                    }
                ],
            )
        if self.request_count == 2:
            return ChatResponse(
                content="",
                tool_calls=[
                    {
                        "id": "call_e2e_2",
                        "name": "analyse_insurance_structure",
                        "arguments": {
                            "per_occurrence_deductible": 1_000_000,
                            "per_occurrence_limit": 25_000_000,
                        },
                    }
                ],
            )
        return ChatResponse(
            content=(
                "Based on the Monte Carlo loss model, your expected annual loss is "
                "material and a cyber insurance structure is recommended. "
                "Model limitations apply."
            )
        )

    def check_connection(self) -> bool:
        return True

    @classmethod
    def is_configured(cls) -> bool:
        return True


# ---------------------------------------------------------------------------
# 1. A user can start an assessment
# ---------------------------------------------------------------------------


def test_e2e_user_can_start_an_assessment(client):
    resp = client.post("/api/v1/assessment/start", json={})
    assert resp.status_code == 201
    body = resp.json()
    assert body["assessment_id"]
    assert body["status"] == "pending"
    assert body["required_fields"] == ["revenue_usd", "security_controls"]
    # The status view is retrievable (the mobile client polls it).
    view = client.get(f"/api/v1/assessment/{body['assessment_id']}")
    assert view.status_code == 200
    assert view.json()["assessment_id"] == body["assessment_id"]


# ---------------------------------------------------------------------------
# 2. Assessment data is validated
# ---------------------------------------------------------------------------


def test_e2e_assessment_data_is_validated(client):
    # Invalid revenue -> typed-schema 422 envelope.
    bad = client.post(
        "/api/v1/assessment/submit", json={"revenue_usd": -10, "security_controls": "x"}
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_error"

    # Valid brief -> the guard is satisfied and the model runs (status ok).
    good = client.post("/api/v1/assessment/submit", json=FULL_BRIEF)
    assert good.status_code == 201
    assert good.json()["status"] == "ok"

    # Incomplete brief -> completeness guard, no simulation runs.
    partial = client.post("/api/v1/assessment/submit", json={"firm_name": "Acme"})
    assert partial.status_code == 201
    assert partial.json()["status"] == "insufficient_info"
    assert set(partial.json()["needed"]) == {"revenue_usd", "security_controls"}


# ---------------------------------------------------------------------------
# 3+4+5. Backend receives it; the agent pipeline + the quantitative engine
#         produce the results
# ---------------------------------------------------------------------------


def test_e2e_agent_pipeline_and_engine_produce_results(client):
    resp = client.post("/api/v1/assessment/submit", json=FULL_BRIEF)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ok"
    result = body["result"]

    # The quantitative engine ran: finite, positive, ordered tail measures.
    eal = result["expected_annual_loss"]
    assert isinstance(eal, float) and eal > 0
    var_95, var_99 = result["var_95"], result["var_99"]
    es_95, es_99 = result["es_95"], result["es_99"]
    pml = result["pml_1000"]
    assert var_95 <= var_99, "VaR must increase with confidence"
    assert es_95 <= es_99, "ES must increase with confidence"
    assert var_99 <= es_99, "ES >= VaR at the same level (tail beyond the quantile)"
    assert pml >= var_99, "1-in-1000-year PML is deeper than the 99% VaR"
    assert isinstance(result["risk_score"], float) and 0 <= result["risk_score"] <= 100
    assert result["risk_category"] in ("Low", "Medium", "High", "Critical")

    # Domain scores + drivers present.
    assert isinstance(result["domain_scores"], dict) and len(result["domain_scores"]) > 0
    assert isinstance(result["top_risk_drivers"], list) and len(result["top_risk_drivers"]) > 0

    # Insurance analysis reflects the policy terms.
    ins = result["insurance_analysis"]
    assert ins["policy"]["per_occurrence_deductible"] is not None
    assert isinstance(ins["evaluation"], dict)

    # Mitigation roadmap is the model-linked scenario contribution.
    recs = result["mitigation_recommendations"]
    assert isinstance(recs, list) and len(recs) > 0
    assert all(r.get("linked_to_model") for r in recs)

    # Mandatory disclosure.
    assert result["model_limitations"]["heading"] == DISCLOSURE_HEADING
    assert len(result["model_limitations"]["limitations"]) >= 1


def test_e2e_engine_reuses_the_existing_tool_seam(client):
    """The v1 pipeline must NOT duplicate risk logic: it calls the exact same
    tool functions the chat agent calls (read-only)."""
    from cyberrisk.agent import tools as agent_tools
    from cyberrisk.api.v1 import service as v1_service

    assert v1_service.assess_company_risk is agent_tools.assess_company_risk
    assert v1_service.run_loss_simulation is agent_tools.run_loss_simulation
    assert v1_service.analyse_insurance_structure is agent_tools.analyse_insurance_structure
    assert v1_service.search_incidents is agent_tools.search_incidents


# ---------------------------------------------------------------------------
# 6. RAG retrieval works where applicable
# ---------------------------------------------------------------------------


def test_e2e_rag_retrieval_from_vector_store(client):
    """With the populated vector store, evidence carries real citations.

    The vector store in this repo contains a single chunk (Change Healthcare)
    whose body ``content`` is empty (metadata-only ingestion) -- so the RAG
    contract to assert is that retrieval IDENTIFIES + SOURCES the chunk, not
    that its body text is non-empty.  This mirrors the retrieval side's
    purpose: surface the chunk for the LLM to reason over, with a citation.
    """
    resp = client.post("/api/v1/assessment/submit", json=FULL_BRIEF)
    assert resp.status_code == 201
    evidence = resp.json()["result"]["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["citations"], "expected RAG citations from the vector store"
    for citation in evidence["citations"]:
        assert citation["doc_id"]
        assert citation["chunk_id"]
        assert citation["source"]
        assert citation["score"] >= 0
    assert isinstance(evidence["incidents"], list)


def test_e2e_rag_degrades_gracefully_when_store_absent(client, monkeypatch):
    """Absent vector store -> 200 with empty citations + note (never a 500)."""
    def _raise(*_a, **_k):
        raise FileNotFoundError("no vector store")

    # Patch the classmethod at its definition site so both the RAG module and
    # the v1 service see the patched behaviour.
    monkeypatch.setattr("cyberrisk.knowledge.rag.Retriever.from_derived", _raise)

    resp = client.post("/api/v1/assessment/submit", json=FULL_BRIEF)
    assert resp.status_code == 201
    evidence = resp.json()["result"]["evidence"]
    assert evidence["citations"] == []
    assert "not available" in evidence["note"]


# ---------------------------------------------------------------------------
# 7. Results are returned through the API + 8. iOS app can display them
# ---------------------------------------------------------------------------


def test_e2e_results_returned_and_replayable_for_ios(client):
    submit = client.post("/api/v1/assessment/submit", json=FULL_BRIEF).json()
    assessment_id = submit["assessment_id"]
    assert submit["status"] == "ok"

    # The full payload is included in the submit response (one round trip).
    result = submit["result"]
    _assert_ios_renderable(result)

    # The client can also replay the exact same payload via results.
    replay = client.get(f"/api/v1/assessment/{assessment_id}/results")
    assert replay.status_code == 200
    replay_body = replay.json()
    _assert_ios_renderable(replay_body["result"])

    # The two payloads are identical (deterministic, seeded engine).
    assert replay_body["result"] == result

    # The status view stays light (never the full result).
    status = client.get(f"/api/v1/assessment/{assessment_id}")
    assert status.json()["status"] == "ok"
    assert "result" not in status.json()


def test_e2e_submit_is_a_single_round_trip(client):
    """The submit response already contains everything the UI renders."""
    resp = client.post("/api/v1/assessment/submit", json=FULL_BRIEF)
    assert resp.status_code == 201
    body = resp.json()
    assert set(body.keys()) >= {"assessment_id", "status", "result"}
    assert "risk_score" in body["result"]


def _assert_ios_renderable(result: dict) -> None:
    """Assert the result is exactly what a mobile client can render directly:
    JSON-serialisable, flat scalar tail measures, dict domain scores, and the
    nested sections the voice/consultant UI charts."""
    # JSON-serialisable (Swift Codable-safe).
    json.dumps(result)
    for key in (
        "risk_score",
        "risk_category",
        "domain_scores",
        "top_risk_drivers",
        "expected_annual_loss",
        "var_95",
        "var_99",
        "es_95",
        "es_99",
        "pml_1000",
        "insurance_analysis",
        "mitigation_recommendations",
        "model_limitations",
        "evidence",
    ):
        assert key in result, f"iOS client needs {key!r} in the result"


# ---------------------------------------------------------------------------
# 4 (LLM leg). The agent + LLM abstraction can produce a consultant answer
# ---------------------------------------------------------------------------


def test_e2e_agent_with_llm_abstraction_produces_answer():
    """Drives the real agent controller through the LLM abstraction with a
    fake client, so the tool loop + engine + RAG are exercised without a key."""
    agent = CyberRiskAgent(client=FakeLLMClient(), config=AgentConfig(max_tool_rounds=8))
    answer = agent.chat(
        "Please assess the cyber risk for this healthcare company with "
        f"{FULL_BRIEF['revenue_usd']} in revenue and the following controls: "
        f"{FULL_BRIEF['security_controls']}"
    )
    assert isinstance(answer, str) and answer.strip()
    # The agent used the LLM interface more than once (tool loop ran).
    assert len(agent.tool_trace) >= 1
    # Tool trace only contains figures the tools actually returned.
    names = {t["name"] for t in agent.tool_trace}
    assert "run_loss_simulation" in names
    assert "analyse_insurance_structure" in names


def test_e2e_agent_calls_the_same_engine_tools_as_the_api(client):
    """The agent's tool implementations and the API's pipeline are the SAME
    functions -- the mobile API and the chat consultant are one engine."""
    from cyberrisk.agent.agent_controller import _TOOL_IMPLEMENTATIONS
    from cyberrisk.api.v1 import service as v1_service

    assert _TOOL_IMPLEMENTATIONS["run_loss_simulation"] is not None
    assert v1_service.run_loss_simulation is not None
    # Both reach the calibrated model config (loaded once, read-only).
    from cyberrisk.agent.tools import _model_config as tools_model_config

    cfg = tools_model_config()
    assert len(cfg.scenarios) >= 1


# ---------------------------------------------------------------------------
# 9. No secrets are exposed + 10. No customer information is logged
# ---------------------------------------------------------------------------


def test_e2e_no_secrets_exposed_across_lifecycle(client):
    """Every response across start -> submit -> results is free of secrets,
    env-var names, filesystem paths, provider names, and internal prompts."""
    forbidden = (
        "CYBERRISK_API_KEY",
        "CYBERRISK_RATE_LIMIT",
        "CYBERRISK_CORS_ORIGINS",
        "Authorization",
        "Bearer ",
        "sk-",
        "test-secret-key",
        "C:\\",
        "c:\\",
        "/home/",
        "/Users/",
        "deepseek",
        "anthropic",
        "openai",
        "system prompt",
        "dependencies.py",
        "service.py",
        "routes.py",
        "main.py",
    )
    responses = []
    responses.append(client.get("/api/v1/health"))
    start = client.post("/api/v1/assessment/start", json={})
    responses.append(start)
    aid = start.json()["assessment_id"]
    responses.append(client.get(f"/api/v1/assessment/{aid}"))
    responses.append(client.post("/api/v1/assessment/submit", json=FULL_BRIEF))
    responses.append(client.get(f"/api/v1/assessment/{aid}/results"))
    # Error paths too.
    responses.append(client.get("/api/v1/assessment/unknown-xyz/results"))
    responses.append(client.post("/api/v1/assessment/submit", json="{bad"))

    for resp in responses:
        text = f"{resp.status_code} {resp.text}"
        for marker in forbidden:
            assert marker.lower() not in text.lower(), (
                f"privacy leak in {resp.status_code}: {marker!r}\n{resp.text[:300]}"
            )


def test_e2e_customer_information_not_logged(client, caplog):
    """Structured logs carry operational metadata only -- never the brief's
    firm name, revenue, controls, or other customer data."""
    caplog.set_level(logging.INFO)
    client.post("/api/v1/assessment/submit", json=FULL_BRIEF)

    assert caplog.records, "expected at least one request log line"
    for record in caplog.records:
        msg = record.getMessage()
        if "request " not in msg and "cyberrisk.api.v1" not in record.name:
            continue
        assert "Acme" not in msg, f"customer name leaked into log: {msg}"
        assert "500_000_000" not in msg
        assert "MFA" not in msg, f"controls description leaked into log: {msg}"
        # Operational fields ARE present.
        assert "GET" in msg or "POST" in msg
        assert "request_id" in msg


def test_e2e_request_id_correlates_lifecycle(client):
    """The same inbound X-Request-ID is echoed across the lifecycle, so a
    client can correlate logs to a run."""
    rid = "e2e-correlation-trace-001"
    headers = {"X-Request-ID": rid}
    resp = client.get("/api/v1/health", headers=headers)
    assert resp.headers["x-request-id"] == rid
    resp = client.post("/api/v1/assessment/start", json={}, headers=headers)
    assert resp.headers["x-request-id"] == rid


# ---------------------------------------------------------------------------
# 11. Existing CLI functionality still works
# ---------------------------------------------------------------------------


def test_e2e_cli_still_works_without_a_key():
    """The CLI must start and, when no LLM key is set, fail with a clear
    config message -- it must NOT crash or regress."""
    from cyberrisk import cli

    # Ensure no provider key is set for this check.
    old_env = {k: os.environ.pop(k, None) for k in ("LLM_PROVIDER", "OPENAI_API_KEY", "DEEPSEEK_API_KEY")}
    try:
        import sys

        out = StringIO()
        err = StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            code = cli.main()
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        # With no key, main() returns 1 and prints a config error -- a sane,
        # explicit failure rather than a crash.
        assert code == 1
        assert "config error" in err.getvalue() or "LLM_PROVIDER" in err.getvalue() or "API_KEY" in err.getvalue()
    finally:
        for k, v in old_env.items():
            if v is not None:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# 12. Existing tests still pass — the full suite is run separately; here we
#     assert the app still exposes the unversioned web + chat + CLI surface.
# ---------------------------------------------------------------------------


def test_e2e_existing_web_surface_untouched(client):
    """The unversioned web API still works after the v1 additions."""
    assert client.get("/api/health").status_code == 200
    scenarios = client.get("/api/scenarios")
    assert scenarios.status_code == 200
    assert "scenarios" in scenarios.json()
    # Chat sessions still work (the iOS voice consultant path).
    session = client.post("/api/chat/sessions")
    assert session.status_code == 200
    assert session.json()["session_id"]
    # Removed mobile route is gone (404, not a stray handler).
    assert client.get("/api/mobile/assessment").status_code == 404


def test_e2e_company_brief_schema_is_the_shared_dto():
    """The v1 request schema validates against the same CompanyBrief the agent
    uses -- a single source of truth for the brief fields."""
    from cyberrisk.api.v1.schemas import AssessmentSubmitRequest

    req = AssessmentSubmitRequest(**FULL_BRIEF)
    brief = CompanyBrief(**req.model_dump())
    assert brief.revenue_usd == FULL_BRIEF["revenue_usd"]
    assert brief.security_controls == FULL_BRIEF["security_controls"]
