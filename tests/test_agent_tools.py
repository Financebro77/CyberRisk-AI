"""Deterministic tests for the agent tool layer (no LLM, no network).

The tools wrap the existing engine; these tests lock in the mapping from a
client brief to factor scores and verify the tool outputs satisfy the
actuarial sanity axioms the engine is designed around.
"""

from __future__ import annotations

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
