"""Unit tests for the v1 result mapper (pure mapping, no engine/network).

``build_result_payload`` is the only module that owns the mapping from tool
dicts into the versioned result schema, so it is tested exactly with stubbed
tool outputs.  The critical assertions: the ``pml_1in1000`` -> ``pml_1000``
rename, the mitigation roadmap sourcing, and the mandatory model-limitations
disclosure.
"""

from __future__ import annotations

from cyberrisk.agent.disclosure import DISCLOSURE_HEADING, LIMITATIONS
from cyberrisk.agent.schemas import CompanyBrief
from cyberrisk.api.v1.service import build_result_payload

# Stub tool outputs that mirror the real tool dict shapes (see agent/tools.py).
SCORE_RES = {
    "status": "ok",
    "firm_name": "Acme",
    "risk_score": 72.5,
    "risk_category": "High",
    "risk_drivers": ["ransomware", "phishing", "cloud misconfig"],
    "domain_scores": {"Governance": 80.0, "Operations": 65.0, "Resilience": 70.0},
}

SIM_RES = {
    "status": "ok",
    "eal": 4_200_000.0,
    "var_95": 15_000_000.0,
    "var_99": 40_000_000.0,
    "es_95": 22_000_000.0,
    "es_99": 60_000_000.0,
    "pml_1in200": 55_000_000.0,
    "pml_1in1000": 110_000_000.0,
}

INS_RES = {
    "status": "ok",
    "ground_up_loss": {"eal": 4_200_000.0},
    "policy": {"per_occurrence_deductible": 1_000_000.0},
    "insurance_response": {"policy_limit": 25_000_000.0},
    "client_retained_loss": {"retained_eal": 3_500_000.0},
    "evaluation": {"residual_uncovered": True, "summary": "Partial cover."},
}

CONTRIB = {
    "status": "ok",
    "scenarios": [
        {
            "scenario_key": "ransomware",
            "scenario_name": "Ransomware",
            "contribution": 0.42,
            "recommended_controls": ["Offline backups"],
            "linked_to_model": True,
        },
        {
            "scenario_key": "bce",
            "scenario_name": "Business email compromise",
            "contribution": 0.21,
            "recommended_controls": ["MFA"],
            "linked_to_model": True,
        },
    ],
}

BRIEF = CompanyBrief(firm_name="Acme", revenue_usd=500_000_000, security_controls="MFA, backups")


def _payload(**overrides) -> dict:
    base = {
        "score_res": SCORE_RES,
        "sim_res": SIM_RES,
        "ins_res": INS_RES,
        "contrib": CONTRIB,
        "brief": BRIEF,
    }
    base.update(overrides)
    return base


def test_maps_every_required_field():
    """Every required result key is present and sourced from the tool dicts."""
    result = build_result_payload(**_payload())

    assert result["risk_score"] == 72.5
    assert result["risk_category"] == "High"
    assert result["domain_scores"] == {"Governance": 80.0, "Operations": 65.0, "Resilience": 70.0}
    assert result["top_risk_drivers"] == ["ransomware", "phishing", "cloud misconfig"]
    assert result["expected_annual_loss"] == 4_200_000.0
    assert result["var_95"] == 15_000_000.0
    assert result["var_99"] == 40_000_000.0
    assert result["es_95"] == 22_000_000.0
    assert result["es_99"] == 60_000_000.0


def test_pml_1000_is_the_1_in_1000_year_pml_alias():
    """The engine's ``pml_1in1000`` key is exposed as ``pml_1000``."""
    result = build_result_payload(**_payload())
    assert result["pml_1000"] == 110_000_000.0


def test_insurance_analysis_wraps_the_structure_sections():
    result = build_result_payload(**_payload())
    ins = result["insurance_analysis"]
    assert ins["ground_up_loss"] == {"eal": 4_200_000.0}
    assert ins["policy"] == {"per_occurrence_deductible": 1_000_000.0}
    assert ins["insurance_response"] == {"policy_limit": 25_000_000.0}
    assert ins["client_retained_loss"] == {"retained_eal": 3_500_000.0}
    assert ins["evaluation"] == {"residual_uncovered": True, "summary": "Partial cover."}


def test_mitigation_recommendations_come_from_scenario_contribution():
    """The roadmap is the model-linked scenario contribution list."""
    result = build_result_payload(**_payload())
    assert result["mitigation_recommendations"] == CONTRIB["scenarios"]
    assert result["mitigation_recommendations"][0]["linked_to_model"] is True


def test_mitigations_empty_when_contribution_not_ok():
    result = build_result_payload(**_payload(contrib={"status": "insufficient_info", "needed": ["revenue_usd"]}))
    assert result["mitigation_recommendations"] == []


def test_model_limitations_reuse_the_mandatory_disclosure():
    """model_limitations must be the shared disclosure, never a new list."""
    result = build_result_payload(**_payload())
    assert result["model_limitations"]["heading"] == DISCLOSURE_HEADING
    assert result["model_limitations"]["limitations"] == list(LIMITATIONS)
    assert len(LIMITATIONS) == 5  # guards against accidental truncation


def test_evidence_shape_is_always_present():
    """evidence always has citations/incidents/note keys (content is gathered
    separately, so here it degrades to empty)."""
    result = build_result_payload(**_payload())
    assert set(result["evidence"]) == {"citations", "incidents", "note"}
    assert isinstance(result["evidence"]["citations"], list)
    assert isinstance(result["evidence"]["incidents"], list)


def test_payload_round_trips_through_json():
    """The result must be JSON-serialisable (mobile clients parse JSON)."""
    import json

    result = build_result_payload(**_payload())
    json.dumps(result)  # must not raise
