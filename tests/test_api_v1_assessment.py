"""Integration tests for the v1 assessment lifecycle.

Uses FastAPI's TestClient against the real app.  The security fixture keeps
auth + rate limiting OFF by default so the lifecycle tests focus on the API
contract; auth/rate-limit behaviour is covered in test_api_v1_security.py.
"""

from __future__ import annotations


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
# Health
# ---------------------------------------------------------------------------


def test_health_is_open_and_versioned(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["api_version"] == "v1"
    assert body["service"] == "CyberRisk AI"


def test_health_is_auth_exempt(client, monkeypatch):
    """/api/v1/health is exempt from the gateway, like /api/health."""
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


def test_start_returns_pending_with_required_fields(client):
    resp = client.post("/api/v1/assessment/start")
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["required_fields"] == ["revenue_usd", "security_controls"]
    assert body["assessment_id"]
    # The status view is retrievable.
    view = client.get(f"/api/v1/assessment/{body['assessment_id']}")
    assert view.status_code == 200
    assert view.json()["status"] == "pending"


def test_start_with_complete_brief_is_ready(client):
    resp = client.post("/api/v1/assessment/start", json=FULL_BRIEF)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ready"
    assert body["required_fields"] == []


def test_start_accepts_optional_empty_body(client):
    """The start body is optional; sending null/{} is the same as omitting."""
    for payload in (None, {}, {"firm_name": "Acme"}):
        resp = client.post("/api/v1/assessment/start", json=payload)
        assert resp.status_code == 201, payload


# ---------------------------------------------------------------------------
# Submit -> full lifecycle
# ---------------------------------------------------------------------------


def test_submit_full_brief_returns_complete_result(client):
    resp = client.post("/api/v1/assessment/submit", json=FULL_BRIEF)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ok"
    assert body["assessment_id"]

    result = body["result"]
    _assert_full_result_shape(result)


def test_submit_insufficient_info_guard(client):
    """Without revenue + controls the engine guard fires; no simulation runs."""
    resp = client.post("/api/v1/assessment/submit", json={"firm_name": "Acme"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "insufficient_info"
    assert set(body["needed"]) == {"revenue_usd", "security_controls"}
    assert "Cannot run the loss model" in body["message"]


def test_lifecycle_start_submit_results_replay(client):
    """The full lifecycle: start -> submit -> status -> results."""
    start = client.post("/api/v1/assessment/start", json=FULL_BRIEF)
    assessment_id = start.json()["assessment_id"]

    submit = client.post("/api/v1/assessment/submit", json=FULL_BRIEF)
    submitted_id = submit.json()["assessment_id"]
    assert submit.json()["status"] == "ok"

    status = client.get(f"/api/v1/assessment/{submitted_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "ok"
    # Status view never carries the full result.
    assert "result" not in status.json()

    results = client.get(f"/api/v1/assessment/{submitted_id}/results")
    assert results.status_code == 200
    replay = results.json()
    assert replay["status"] == "ok"
    _assert_full_result_shape(replay["result"])

    # The start and submit calls each mint their own id (uuid4).
    assert submitted_id != assessment_id


def test_results_404_for_unknown_and_pending(client):
    """Unknown id -> 404; a started-but-not-submitted id has no result yet."""
    assert client.get("/api/v1/assessment/unknown-id/results").status_code == 404

    pending_id = client.post("/api/v1/assessment/start", json=FULL_BRIEF).json()["assessment_id"]
    assert client.get(f"/api/v1/assessment/{pending_id}/results").status_code == 404


def test_repeated_submits_are_deterministic(client):
    """Two submits of the same brief produce the same risk score.

    The submit route always mints a fresh assessment id (it does not accept a
    caller-supplied id), but the scoring engine is deterministic, so a repeat
    submit must agree with the first.
    """
    first = client.post("/api/v1/assessment/submit", json=FULL_BRIEF).json()
    second = client.post("/api/v1/assessment/submit", json=FULL_BRIEF).json()
    assert second["status"] == "ok"
    assert second["assessment_id"] != first["assessment_id"]
    assert second["result"]["risk_score"] == first["result"]["risk_score"]


# ---------------------------------------------------------------------------
# Policy terms + knobs
# ---------------------------------------------------------------------------


def test_submit_accepts_policy_terms(client):
    payload = dict(FULL_BRIEF)
    payload.update(
        {
            "per_occurrence_deductible": 1_000_000,
            "per_occurrence_limit": 25_000_000,
            "coinsurance": 0.1,
        }
    )
    resp = client.post("/api/v1/assessment/submit", json=payload)
    assert resp.status_code == 201
    ins = resp.json()["result"]["insurance_analysis"]
    assert ins["policy"]["per_occurrence_deductible"] == 1_000_000
    assert ins["policy"]["per_occurrence_limit"] == 25_000_000
    assert ins["policy"]["coinsurance"] == 0.1


def test_submit_rejects_invalid_n_years(client):
    payload = dict(FULL_BRIEF)
    payload["n_years"] = 50  # below the 1_000 floor
    resp = client.post("/api/v1/assessment/submit", json=payload)
    assert resp.status_code == 422
    envelope = resp.json()["error"]
    assert envelope["code"] == "validation_error"
    assert "n_years" in str(envelope["detail"])


def test_submit_rejects_invalid_policy_bounds(client):
    payload = dict(FULL_BRIEF)
    payload["coinsurance"] = 1.5  # must be < 1.0
    resp = client.post("/api/v1/assessment/submit", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_submit_rejects_negative_revenue(client):
    payload = dict(FULL_BRIEF)
    payload["revenue_usd"] = -5  # must be > 0
    resp = client.post("/api/v1/assessment/submit", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Evidence / RAG
# ---------------------------------------------------------------------------


def test_submit_includes_evidence_citations_and_incidents(client):
    """With the real knowledge store present, evidence has citations + incidents."""
    resp = client.post("/api/v1/assessment/submit", json=FULL_BRIEF)
    assert resp.status_code == 201
    evidence = resp.json()["result"]["evidence"]
    assert set(evidence) == {"citations", "incidents", "note"}
    # Citations come from RAG chunks (doc_id + chunk_id); incidents from the index.
    for citation in evidence["citations"]:
        assert citation["doc_id"]
        assert citation["chunk_id"]
    assert isinstance(evidence["incidents"], list)


def test_submit_degrades_gracefully_without_knowledge_store(client, monkeypatch):
    """Absent vector.db -> 200 with empty citations + note, never an exception."""
    import cyberrisk.api.v1.service as service

    def _raise(*_args, **_kwargs):
        raise FileNotFoundError("no vector store")

    # Drop the process-level retriever cache so the patched constructor is
    # actually exercised (the cache persists across tests in this process).
    monkeypatch.setattr(service, "_retriever", None, raising=False)
    monkeypatch.setattr("cyberrisk.knowledge.rag.Retriever.from_derived", _raise)

    resp = client.post("/api/v1/assessment/submit", json=FULL_BRIEF)
    assert resp.status_code == 201
    evidence = resp.json()["result"]["evidence"]
    assert evidence["citations"] == []
    assert "not available" in evidence["note"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_full_result_shape(result: dict) -> None:
    """The exact result contract the mobile client depends on."""
    assert isinstance(result["risk_score"], float)
    assert isinstance(result["risk_category"], str)
    assert isinstance(result["domain_scores"], dict)
    assert isinstance(result["top_risk_drivers"], list)
    assert isinstance(result["expected_annual_loss"], (int, float))
    for key in ("var_95", "var_99", "es_95", "es_99", "pml_1000"):
        assert key in result, f"missing {key}"
        assert isinstance(result[key], (int, float))
    ins = result["insurance_analysis"]
    for section in ("ground_up_loss", "policy", "insurance_response", "client_retained_loss", "evaluation"):
        assert section in ins
    assert isinstance(result["mitigation_recommendations"], list)
    assert result["mitigation_recommendations"], "expected a mitigation roadmap"
    assert result["mitigation_recommendations"][0]["linked_to_model"] is True
    assert result["model_limitations"]["heading"] == "Model Limitations"
    assert len(result["model_limitations"]["limitations"]) >= 1
    assert set(result["evidence"]) == {"citations", "incidents", "note"}
