"""Policy-term pass-through on /api/report/executive.

The web SPA lets the user tweak risk retention and policy limit before running
an assessment.  This module pins the contract: those knobs must actually reach
the insurance engine and shape the insurance_analysis section, rather than being
dropped as unknown fields (the historical behaviour).
"""

from __future__ import annotations

# A full, model-able brief (same shape the SPA submits via /api/report/executive).
BRIEF = {
    "firm_name": "Acme Healthcare",
    "industry": "Healthcare",
    "revenue_usd": 500_000_000,
    "customer_records": 2_000_000,
    "technology_dependency": "High",
    "security_controls": (
        "MFA enforced on all remote access, endpoint detection installed, "
        "offline backups taken nightly, phishing training quarterly, "
        "a dedicated security team with an incident response plan"
    ),
    "previous_incidents": 1,
    "existing_coverage": "Standalone cyber policy with a $10M limit and $1M deductible",
}


def _post_executive(client, **overrides):
    body = dict(BRIEF)
    body.update(overrides)
    resp = client.post("/api/report/executive", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok", data
    return data


def test_executive_policy_terms_flow(client):
    """Retention / policy-limit knobs reach the insurance section."""
    data = _post_executive(
        client,
        per_occurrence_deductible=1_000_000,
        annual_aggregate_limit=10_000_000,
    )
    ins = data["insurance_analysis"]["insurance_response"]
    assert ins["retention"] == 1_000_000
    assert ins["policy_limit"] == 10_000_000


def test_executive_defaults_without_policy(client):
    """Without policy knobs the engine falls back to its PolicyInput defaults."""
    data = _post_executive(client)
    ins = data["insurance_analysis"]["insurance_response"]
    assert ins["retention"] == 250_000
    assert ins["policy_limit"] == 20_000_000


def test_executive_higher_retention_raises_retained_loss(client):
    """A larger retention must shift retained exposure upward (same brief)."""
    low = _post_executive(client, per_occurrence_deductible=250_000)
    high = _post_executive(client, per_occurrence_deductible=5_000_000)
    low_retained = low["insurance_analysis"]["client_retained_loss"]["retained_eal"]
    high_retained = high["insurance_analysis"]["client_retained_loss"]["retained_eal"]
    assert high_retained > low_retained
