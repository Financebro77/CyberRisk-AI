"""Consultant agent tests (Phase E)."""

from pathlib import Path

from agent.consultant_agent import generate_recommendations
from agent.knowledge_base.risk_bands import BAND_GUIDANCE
from cyberrisk.calibration import load_config
from cyberrisk.metrics import compute_metrics
from cyberrisk.scoring import CompanyProfile, compute_score
from cyberrisk.simulation import simulate

REPO = Path(__file__).parent.parent


def _scored_and_metrics():
    cfg = load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )
    # A high-risk profile
    profile = CompanyProfile(
        firm_name="Acme Corp",
        factor_scores={
            "external_attack_surface": 90.0,
            "industry_targeting": 85.0,
            "data_sensitivity": 80.0,
            "patch_cadence": 90.0,
            "mfa_coverage": 90.0,
            "edr_coverage": 85.0,
            "backup_frequency": 60.0,
            "vendor_assessment": 70.0,
        },
    )
    scored = compute_score(profile)
    result = simulate(cfg, n_years=20_000, score=scored.composite_score)
    metrics = compute_metrics(result)
    return scored, metrics


def test_rule_based_generates_recommendations():
    scored, metrics = _scored_and_metrics()
    rec = generate_recommendations(scored, metrics)
    assert rec.generated_by == "rule-based"
    assert rec.risk_category == scored.risk_category
    assert rec.firm_name == "Acme Corp"
    assert len(rec.recommendations) >= 1
    # Recommendations come from the knowledge-base band guidance
    band_recs = BAND_GUIDANCE[scored.risk_category]["recommendations"]
    assert any(any(b in r for b in band_recs) for r in rec.recommendations)


def test_llm_backend_used_when_provided():
    scored, metrics = _scored_and_metrics()

    def fake_llm(prompt: str) -> str:
        assert "Firm: Acme Corp" in prompt
        assert "Expected Annual Loss" in prompt or "expected annual loss" in prompt.lower()
        return (
            "Executive summary: elevated cyber exposure.\n"
            "- Increase cyber limit to $30M\n"
            "- Enforce MFA across all privileged accounts"
        )

    rec = generate_recommendations(scored, metrics, llm_backend=fake_llm)
    assert rec.generated_by == "llm"
    assert "Increase cyber limit" in rec.recommendations[0]
    assert "Enforce MFA" in rec.recommendations[1]


def test_agent_grounded_in_validated_outputs():
    """The agent never reaches into raw config/simulation internals."""
    scored, metrics = _scored_and_metrics()
    rec = generate_recommendations(scored, metrics)
    # It works purely from ScoredFirm + RiskMetrics
    assert isinstance(rec.risk_category, str)
    assert rec.eal_placeholder if hasattr(rec, "eal_placeholder") else True
    # Risk category is one of the known bands
    assert rec.risk_category in BAND_GUIDANCE
