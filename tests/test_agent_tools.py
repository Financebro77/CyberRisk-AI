"""Deterministic tests for the agent tool layer (no LLM, no network).

The tools wrap the existing engine; these tests lock in the mapping from a
client brief to factor scores and verify the tool outputs satisfy the
actuarial sanity axioms the engine is designed around.
"""

from __future__ import annotations

import pytest

from cyberrisk.agent.schemas import CompanyBrief, PolicyInput
from cyberrisk.agent.tools import (
    analyse_insurance_structure,
    assess_company_risk,
    build_factor_scores,
    generate_risk_report,
    run_loss_simulation,
)

# The healthcare scenario from the spec: 10m patient records, high tech
# dependency, weak MFA, limited segmentation.
HEALTHCARE_BRIEF = CompanyBrief(
    firm_name="MedTech Health",
    industry="Healthcare",
    revenue_usd=500_000_000,
    customer_records=10_000_000,
    technology_dependency="High",
    security_controls="weak MFA and limited network segmentation",
)


# ---------------------------------------------------------------------------
# build_factor_scores
# ---------------------------------------------------------------------------


def test_factor_scores_mapping_healthcare():
    scores = build_factor_scores(HEALTHCARE_BRIEF)
    # Weak MFA -> minimal (80); weak segmentation -> basic privileged access (65).
    assert scores["mfa_coverage"] > 50
    assert scores["privileged_access"] > 50
    # Healthcare -> very_high_target (90); 10m records -> critical sensitivity (90).
    assert scores["industry_targeting"] >= 70
    assert scores["data_sensitivity"] >= 75
    # High technology dependency -> high attack surface (75).
    assert scores["external_attack_surface"] >= 60
    # All 18 factors present and within [0, 100].
    assert len(scores) == 18
    assert all(0 <= v <= 100 for v in scores.values())


def test_factor_scores_defaults_for_unstated_brief():
    brief = CompanyBrief(firm_name="Quiet Client", revenue_usd=1e9, security_controls="patch regularly")
    scores = build_factor_scores(brief)
    assert len(scores) == 18
    # Unstated controls take the documented neutral default (majority -> 35).
    assert scores["mfa_coverage"] == 35.0
    # "patch regularly" is not a weak/none/strong keyword -> neutral monthly (40).
    assert scores["patch_cadence"] == 40.0


def test_factor_scores_deterministic():
    a = build_factor_scores(HEALTHCARE_BRIEF)
    b = build_factor_scores(HEALTHCARE_BRIEF)
    assert a == b


def test_factor_scores_per_control_qualifier_independent():
    """Each control is qualified from its OWN clause.

    Regression for the global-qualifier bug: a single "no X" in the sentence
    must not downgrade unrelated controls.  "MFA is partial, no immutable
    backups, network segmentation is weak" must score partial / none / weak
    independently.
    """
    brief = CompanyBrief(
        firm_name="MedHealth SaaS",
        industry="Healthcare",
        revenue_usd=250_000_000,
        customer_records=10_000_000,
        technology_dependency="High",
        security_controls="MFA is partial, no immutable backups, network segmentation is weak, "
        "heavy reliance on third-party SaaS providers",
    )
    scores = build_factor_scores(brief)
    # Partial MFA -> partial (60), not downgraded by "no immutable backups".
    assert scores["mfa_coverage"] == 60.0, scores["mfa_coverage"]
    # No immutable backups -> none (95).
    assert scores["backup_frequency"] == 95.0, scores["backup_frequency"]
    # Weak segmentation -> weak (85), not downgraded to none.
    assert scores["privileged_access"] == 85.0, scores["privileged_access"]


def test_absent_control_does_not_poison_other_controls():
    """Adding one absent control must not change any other stated control.

    Regression for the blast-radius case: 'weak MFA, limited segmentation,
    poor backups' vs the same + 'no immutable backups' must yield identical
    MFA / segmentation ratings.
    """
    base = CompanyBrief(
        firm_name="A", industry="Retail", revenue_usd=100_000_000,
        security_controls="weak MFA, limited segmentation, poor backups",
    )
    plus_none = CompanyBrief(
        firm_name="B", industry="Retail", revenue_usd=100_000_000,
        security_controls="weak MFA, limited segmentation, poor backups, no immutable backups",
    )
    a = build_factor_scores(base)
    b = build_factor_scores(plus_none)
    # weak MFA -> minimal (80) in both; weak segmentation -> weak (85) in both.
    assert a["mfa_coverage"] == b["mfa_coverage"] == 80.0
    assert a["privileged_access"] == b["privileged_access"] == 85.0
    # Only backup_frequency changes (none for the second brief).
    assert b["backup_frequency"] == 95.0
    assert a["backup_frequency"] == 80.0


def test_mixed_strengths_in_one_sentence():
    """A single sentence with different strengths per control parses each one."""
    brief = CompanyBrief(
        firm_name="Mixed", industry="Manufacturing", revenue_usd=300_000_000,
        security_controls="strong MFA but weak patching and no DR testing",
    )
    scores = build_factor_scores(brief)
    # strong MFA -> comprehensive (10).
    assert scores["mfa_coverage"] == 10.0, scores["mfa_coverage"]
    # weak patching -> adhoc (85).
    assert scores["patch_cadence"] == 85.0, scores["patch_cadence"]
    # no DR testing -> never (90).
    assert scores["dr_testing"] == 90.0, scores["dr_testing"]


# ---------------------------------------------------------------------------
# End-to-end production-readiness scenario
# ---------------------------------------------------------------------------

# The reviewed healthcare-SaaS profile: partial MFA, no immutable backups, weak
# segmentation, high third-party dependency.  Locks the whole chain -- control
# parsing -> composite score -> insurance residual -- so a silent regression in
# any step (e.g. the old global-qualifier bug) fails loudly.
SAAS_BRIEF = CompanyBrief(
    firm_name="MedHealth SaaS",
    industry="Healthcare",
    revenue_usd=250_000_000,
    customer_records=10_000_000,
    technology_dependency="High",
    security_controls="MFA is partial, no immutable backups, network segmentation is weak, "
    "heavy reliance on third-party SaaS providers",
)


def test_review_scenario_composite_in_expected_band():
    """The reviewed profile must land in the High band (50-75), not be inflated.

    Regression guard for the global-qualifier bug: with the controls parsed
    correctly (partial/weak/none), the composite is ~59.9 (High).  If control
    parsing regressed, the composite would drift out of this range.
    """
    from cyberrisk.scoring import CompanyProfile, compute_score, load_scoring_weights

    scores = build_factor_scores(SAAS_BRIEF)
    # Control factors match the described strengths exactly.
    assert scores["mfa_coverage"] == 60.0  # partial
    assert scores["backup_frequency"] == 95.0  # no immutable backups
    assert scores["privileged_access"] == 85.0  # weak segmentation
    scored = compute_score(CompanyProfile(firm_name="X", factor_scores=scores), load_scoring_weights())
    assert 50.0 <= scored.composite_score <= 75.0, scored.composite_score
    assert scored.risk_category == "High"


def test_review_scenario_insurance_residual_consistent():
    """For the reviewed profile, the residual identity holds end-to-end."""

    policy = PolicyInput(
        per_occurrence_deductible=1_000_000.0,
        per_occurrence_limit=20_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=20_000_000.0,
    )
    out = analyse_insurance_structure(SAAS_BRIEF, policy, n_years=20_000)
    assert out["status"] == "ok"
    g = out["ground_up_loss"]["pml_1in1000"]
    cl = out["client_retained_loss"]
    ir = out["insurance_response"]
    expected = max(0.0, g - ir["retention"] - cl["insurance_recovery_at_p99_9"])
    assert cl["residual_exposure_at_p99_9"] == expected
    assert cl["residual_exposure_at_p99_9"] >= 0.0
    assert cl["insurance_recovery_at_p99_9"] <= ir["policy_limit"]
    # The gross P99.9 is never labelled a 'gap'.
    assert "insurance_gap" not in out
    assert "gap_detected" not in out["evaluation"]


def test_review_scenario_explains_scenario_contribution():
    """Scenario contribution for the reviewed profile links to model outputs."""
    from cyberrisk.agent.scenario_contribution import analyze_scenario_contribution

    out = analyze_scenario_contribution(SAAS_BRIEF, n_years=20_000)
    assert out["status"] == "ok"
    assert out["total_contribution"] == pytest.approx(1.0, abs=0.05)
    assert all(s["linked_to_model"] for s in out["scenarios"])
    ransomware = next(s for s in out["scenarios"] if s["scenario_key"] == "ransomware")
    assert any("MFA" in d for d in ransomware["frequency_drivers"])
    assert any("backup weakness" in d for d in ransomware["severity_drivers"])


# ---------------------------------------------------------------------------
# assess_company_risk
# ---------------------------------------------------------------------------


def test_assess_healthcare_is_high_risk():
    out = assess_company_risk(HEALTHCARE_BRIEF)
    assert out["status"] == "ok"
    assert out["risk_category"] in ("High", "Critical")
    assert out["risk_score"] > 50
    assert "mfa_coverage" in out["risk_drivers"]
    assert "privileged_access" in out["risk_drivers"]


# ---------------------------------------------------------------------------
# run_loss_simulation
# ---------------------------------------------------------------------------


def test_simulation_guard_asks_for_missing_fields():
    brief = CompanyBrief(firm_name="Incomplete", industry="Retail")  # no revenue, no controls
    out = run_loss_simulation(brief)
    assert out["status"] == "insufficient_info"
    assert "revenue_usd" in out["needed"]
    assert "security_controls" in out["needed"]


def test_simulation_metrics_sanity():
    out = run_loss_simulation(HEALTHCARE_BRIEF, n_years=20_000)
    assert out["status"] == "ok"
    assert 0 < out["eal"] <= out["var_95"] <= out["var_99"] <= out["es_99"]
    assert out["var_99"] <= out["es_99"]
    assert out["es_95"] <= out["es_99"]
    # Loss distribution quantiles are monotone.
    q = out["loss_distribution"]
    assert q["p50"] <= q["p90"] <= q["p95"] <= q["p99"]
    # Scenario contributions sum to ~1.
    contrib = out["scenario_contribution"]
    assert abs(sum(contrib.values()) - 1.0) < 0.05


def test_simulation_ransomware_high_contribution():
    """Ransomware must be a leading loss driver for a weak-MFA healthcare firm."""
    out = run_loss_simulation(HEALTHCARE_BRIEF, n_years=20_000)
    aal = out["aal_by_scenario"]
    keys = list(aal.keys())
    assert "ransomware" in keys[:3], f"ransomware should rank high: {keys}"
    # Business interruption should be material (high tech dependency): BI
    # plus the cloud-outage BI channel together are a substantial share of
    # expected annual loss, even if no single scenario is top-3.
    bi_share = out["scenario_contribution"]["bi"]
    cloud_share = out["scenario_contribution"]["cloud_outage"]
    assert bi_share + cloud_share > 0.15, f"BI exposure too small: bi={bi_share:.2f}, cloud={cloud_share:.2f}"


# ---------------------------------------------------------------------------
# analyse_insurance_structure
# ---------------------------------------------------------------------------


def test_residual_exposure_present_at_modest_limit():
    policy = PolicyInput(
        per_occurrence_deductible=250_000.0,
        per_occurrence_limit=2_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=5_000_000.0,
        coinsurance=0.0,
    )
    out = analyse_insurance_structure(HEALTHCARE_BRIEF, policy, n_years=20_000)
    assert out["status"] == "ok"
    cl = out["client_retained_loss"]
    # A modest $5M limit against a heavy-tail healthcare profile should leave a
    # residual uncovered exposure after insurance.
    assert cl["residual_exposure_at_p99_9"] > 0
    assert out["evaluation"]["residual_uncovered"] is True


def test_residual_exposure_zero_at_very_high_limit():
    policy = PolicyInput(
        per_occurrence_deductible=250_000.0,
        per_occurrence_limit=50_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=1_000_000_000.0,
        coinsurance=0.0,
    )
    out = analyse_insurance_structure(HEALTHCARE_BRIEF, policy, n_years=20_000)
    assert out["status"] == "ok"
    cl = out["client_retained_loss"]
    assert cl["residual_exposure_at_p99_9"] == 0.0
    assert out["evaluation"]["residual_uncovered"] is False


def test_insurance_response_sections_are_consistent():
    """The three reporting sections must satisfy the reporting invariants."""
    policy = PolicyInput(
        per_occurrence_deductible=2_000_000.0,
        per_occurrence_limit=20_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=20_000_000.0,
    )
    out = analyse_insurance_structure(HEALTHCARE_BRIEF, policy, n_years=20_000)
    assert out["status"] == "ok"
    g = out["ground_up_loss"]
    ir = out["insurance_response"]
    cl = out["client_retained_loss"]

    # Section 1: ground-up measures (before insurance).
    assert 0 < g["eal"] <= g["var_95"] <= g["var_99"]
    assert 0 < g["es_95"] <= g["es_99"]
    # Section 2: the policy response.
    assert ir["policy_limit"] == 20_000_000.0
    assert ir["retention"] == 2_000_000.0
    assert ir["covered_loss"] >= 0
    assert ir["insurer_payment"] >= 0
    # Section 3: residual = gross - retention - recovery (floored at 0).
    assert cl["residual_exposure_at_p99_9"] == max(
        0.0,
        cl["gross_loss_at_p99_9"]
        - ir["retention"]
        - cl["insurance_recovery_at_p99_9"],
    )


def test_reporting_invariants_residual_non_negative_and_recovery_within_limit():
    """Residual exposure is always >= 0 and insurer payment <= policy limit.

    These are the two invariants that keep the three loss concepts from
    bleeding into each other in client-facing reporting.
    """
    # Try a range of structures, from low limit to unlimited.
    for limit, per_occurrence_limit in (
        (0.0, 0.0),
        (1_000_000.0, 1_000_000.0),
        (5_000_000.0, 5_000_000.0),
        (50_000_000.0, 50_000_000.0),
        (None, None),  # unlimited
    ):
        policy = PolicyInput(
            per_occurrence_deductible=250_000.0,
            per_occurrence_limit=per_occurrence_limit,
            annual_aggregate_deductible=250_000.0,
            annual_aggregate_limit=limit,
            coinsurance=0.0,
        )
        out = analyse_insurance_structure(HEALTHCARE_BRIEF, policy, n_years=20_000)
        assert out["status"] == "ok"
        cl = out["client_retained_loss"]
        ir = out["insurance_response"]
        assert cl["residual_exposure_at_p99_9"] >= 0.0, "residual exposure must never be negative"
        if ir["policy_limit"] is not None:
            assert cl["insurance_recovery_at_p99_9"] <= ir["policy_limit"], (
                "insurer payment must never exceed the policy limit"
            )


# ---------------------------------------------------------------------------
# generate_risk_report
# ---------------------------------------------------------------------------


def test_generate_report_creates_workbook(tmp_path):
    out = generate_risk_report(HEALTHCARE_BRIEF, firm_name="MedTech Health", out_dir=str(tmp_path), n_years=10_000)
    assert out["status"] == "ok"
    from pathlib import Path

    assert Path(out["report_path"]).exists()
    assert Path(out["report_path"]).suffix == ".xlsx"
    assert out["risk_category"] in ("High", "Critical")
