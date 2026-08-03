"""End-to-end healthcare scenario for the AI consultant agent.

The spec's scenario: a healthcare technology company with 10 million patient
records, high operational dependency, weak MFA, limited network segmentation.

The agent's *reasoning* is DeepSeek's job (live, tested by hand).  What this
test locks in deterministically is the set of quantitative facts the model
is given to reason over -- the tool outputs must support the advice the
consultant is expected to give:

    * High ransomware exposure          -> ransomware among the top AAL scenarios
    * High business-interruption risk   -> bi / cloud_outage material
    * Large tail losses                 -> ES99 >> EAL (heavy tail)
    * Need for cyber insurance optimisation -> residual uncovered exposure at a
      modest limit, with residual >= 0 and insurer payment <= policy limit
"""

from __future__ import annotations

from cyberrisk.agent.schemas import CompanyBrief, PolicyInput
from cyberrisk.agent.tools import (
    analyse_insurance_structure,
    assess_company_risk,
    run_loss_simulation,
)

BRIEF = CompanyBrief(
    firm_name="MedTech Health",
    industry="Healthcare",
    revenue_usd=500_000_000,
    customer_records=10_000_000,
    technology_dependency="High",
    security_controls="weak MFA and limited network segmentation",
    previous_incidents=1,
)


def test_healthcare_profile_is_high_or_critical_risk():
    out = assess_company_risk(BRIEF)
    assert out["status"] == "ok"
    assert out["risk_category"] in ("High", "Critical")
    assert out["risk_score"] > 55
    # The consultant must be able to point at MFA and segmentation as drivers.
    assert "mfa_coverage" in out["risk_drivers"]
    assert "privileged_access" in out["risk_drivers"]


def test_healthcare_ransomware_and_bi_are_top_scenarios():
    out = run_loss_simulation(BRIEF, n_years=50_000)
    assert out["status"] == "ok"
    aal = out["aal_by_scenario"]
    keys = list(aal.keys())
    # Ransomware ranks in the top 3 by AAL.
    assert "ransomware" in keys[:3], f"expected ransomware high: {keys}"
    # Business interruption (own ops) is material given high tech dependency.
    assert "bi" in keys[:6]
    # Data breach also material for a 10m-record healthcare firm.
    assert "breach" in keys[:6]


def test_healthcare_tail_is_heavy():
    """ES99 must sit far above EAL -- the consultant should warn about tail risk."""
    out = run_loss_simulation(BRIEF, n_years=50_000)
    assert out["status"] == "ok"
    ratio = out["es_99"] / out["eal"]
    assert ratio > 3.0, f"ES99/EAL ratio {ratio:.2f} too small for a heavy-tail profile"
    assert out["var_99"] > 3 * out["eal"]


def test_healthcare_needs_insurance_optimisation():
    """A modest $10M annual limit must leave residual uncovered exposure."""
    policy = PolicyInput(
        per_occurrence_deductible=250_000.0,
        per_occurrence_limit=5_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=10_000_000.0,
        coinsurance=0.0,
    )
    out = analyse_insurance_structure(BRIEF, policy, n_years=20_000)
    assert out["status"] == "ok"
    cl = out["client_retained_loss"]
    ir = out["insurance_response"]
    assert cl["residual_exposure_at_p99_9"] > 0
    assert out["evaluation"]["residual_uncovered"] is True
    # The tail loss the limit is compared against is large.
    assert out["pml_1in1000"] > out["pml_1in1000"] / 2
    # Invariants: residual never negative; insurer payment within the limit.
    assert cl["residual_exposure_at_p99_9"] >= 0.0
    assert cl["insurance_recovery_at_p99_9"] <= ir["policy_limit"]


def test_healthcare_short_brief_triggers_clarifying_questions():
    """A brief missing revenue/controls must produce questions, not a model run."""
    partial = CompanyBrief(
        firm_name="MedTech Health",
        industry="Healthcare",
        customer_records=10_000_000,
        security_controls="weak MFA",
    )
    out = run_loss_simulation(partial)
    assert out["status"] == "insufficient_info"
    assert "revenue_usd" in out["needed"]
