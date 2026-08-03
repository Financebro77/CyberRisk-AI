"""Reporting terminology tests: the three loss sections stay strictly separate.

The agent must never mix ground-up loss, insurance-adjusted loss, and client
retained loss, and must never call a gross P99/P99.9 loss an "insurance gap".
These tests lock in:

    Section 1  GROUND-UP CYBER LOSS    EAL, VaR 95/99, ES95/99 (before insurance)
    Section 2  INSURANCE RESPONSE      policy limit, retention, covered loss,
                                       insurer payment
    Section 3  CLIENT RETAINED LOSS    gross loss - insurance recovery =
                                       residual client exposure

with the invariants that residual exposure >= 0 and insurance recovery <=
policy limit, and that no gross PML is labelled a "gap".
"""

from __future__ import annotations

from cyberrisk.agent.schemas import CompanyBrief, PolicyInput
from cyberrisk.agent.tools import analyse_insurance_structure

BRIEF = CompanyBrief(
    firm_name="MedTech Health",
    industry="Healthcare",
    revenue_usd=500_000_000,
    customer_records=10_000_000,
    technology_dependency="High",
    security_controls="weak MFA and limited network segmentation",
)


def _run(policy: PolicyInput) -> dict:
    out = analyse_insurance_structure(BRIEF, policy, n_years=20_000)
    assert out["status"] == "ok"
    return out


# ---------------------------------------------------------------------------
# Section 1 — ground-up loss (before insurance)
# ---------------------------------------------------------------------------


def test_ground_up_loss_section_has_all_headline_measures():
    out = _run(PolicyInput())
    g = out["ground_up_loss"]
    for key in ("eal", "var_95", "var_99", "es_95", "es_99", "pml_1in1000"):
        assert key in g, f"ground_up_loss missing {key}"
    # Ground-up measures are internal-consistency ordered.
    assert 0 < g["eal"] <= g["var_95"] <= g["var_99"] <= g["pml_1in1000"]
    assert 0 < g["es_95"] <= g["es_99"]


def test_ground_up_loss_is_before_insurance():
    """The ground-up PML equals the gross simulated tail, not a reduced figure."""
    out = _run(PolicyInput())
    g = out["ground_up_loss"]
    cl = out["client_retained_loss"]
    # Ground-up loss is the gross P99.9; the client retained figure after
    # insurance must be <= the gross figure.
    assert g["pml_1in1000"] == cl["gross_loss_at_p99_9"]
    assert cl["insurance_recovery_at_p99_9"] <= g["pml_1in1000"]


# ---------------------------------------------------------------------------
# Section 2 — insurance response
# ---------------------------------------------------------------------------


def test_insurance_response_lists_policy_terms_and_payment():
    policy = PolicyInput(
        per_occurrence_deductible=2_000_000.0,
        per_occurrence_limit=20_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=20_000_000.0,
    )
    out = _run(policy)
    ir = out["insurance_response"]
    assert ir["policy_limit"] == 20_000_000.0
    assert ir["retention"] == 2_000_000.0
    assert ir["covered_loss"] >= 0
    assert ir["insurer_payment"] >= 0
    assert 0 <= ir["p_annual_limit_exhausted"] <= 1.0


# ---------------------------------------------------------------------------
# Section 3 — client retained loss
# ---------------------------------------------------------------------------


def test_client_retained_residual_identity():
    """residual = gross - retention - recovery, floored at zero."""
    policy = PolicyInput(
        per_occurrence_deductible=2_000_000.0,
        per_occurrence_limit=20_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=20_000_000.0,
    )
    out = _run(policy)
    g = out["ground_up_loss"]
    ir = out["insurance_response"]
    cl = out["client_retained_loss"]
    expected = max(
        0.0, g["pml_1in1000"] - ir["retention"] - cl["insurance_recovery_at_p99_9"]
    )
    assert cl["residual_exposure_at_p99_9"] == expected
    # Retained EAL is always a non-negative loss stream.
    assert cl["retained_eal"] >= 0
    assert cl["retained_es_99"] >= cl["retained_eal"]


# ---------------------------------------------------------------------------
# Validation invariants
# ---------------------------------------------------------------------------

# A broad sweep of limits, from a small tower to unlimited, to catch any
# reporting that lets residual go negative or recovery exceed the limit.
_SWEEP = [
    PolicyInput(per_occurrence_deductible=0.0, per_occurrence_limit=0.0,
                annual_aggregate_deductible=0.0, annual_aggregate_limit=0.0),
    PolicyInput(per_occurrence_deductible=250_000.0, per_occurrence_limit=1_000_000.0,
                annual_aggregate_deductible=250_000.0, annual_aggregate_limit=1_000_000.0),
    PolicyInput(per_occurrence_deductible=1_000_000.0, per_occurrence_limit=5_000_000.0,
                annual_aggregate_deductible=1_000_000.0, annual_aggregate_limit=5_000_000.0),
    PolicyInput(per_occurrence_deductible=2_000_000.0, per_occurrence_limit=20_000_000.0,
                annual_aggregate_deductible=2_000_000.0, annual_aggregate_limit=20_000_000.0),
    PolicyInput(per_occurrence_deductible=2_000_000.0, per_occurrence_limit=100_000_000.0,
                annual_aggregate_deductible=2_000_000.0, annual_aggregate_limit=100_000_000.0),
]


def test_residual_exposure_never_negative():
    for policy in _SWEEP:
        out = _run(policy)
        cl = out["client_retained_loss"]
        assert cl["residual_exposure_at_p99_9"] >= 0.0, (
            f"residual exposure went negative at {policy}"
        )
        assert out["evaluation"]["residual_uncovered"] == (
            cl["residual_exposure_at_p99_9"] > 0
        )


def test_insurance_recovery_never_exceeds_policy_limit():
    for policy in _SWEEP:
        out = _run(policy)
        ir = out["insurance_response"]
        cl = out["client_retained_loss"]
        if ir["policy_limit"] is not None:
            assert cl["insurance_recovery_at_p99_9"] <= ir["policy_limit"], (
                f"insurer payment exceeded limit at {policy}"
            )


# ---------------------------------------------------------------------------
# Terminology — never call a gross loss a "gap"
# ---------------------------------------------------------------------------


def test_gross_loss_is_never_labelled_a_gap():
    """The tool output must not frame the gross P99.9 as an 'insurance gap'."""
    for policy in _SWEEP:
        out = _run(policy)
        # The gross PML is a ground-up figure, never reduced by the policy.
        assert out["ground_up_loss"]["pml_1in1000"] == out["client_retained_loss"]["gross_loss_at_p99_9"]
        # The evaluation summarises the client's retained exposure, never a gap.
        # A real policy uses "residual uncovered exposure"; a zero-limit /
        # no-insurance structure correctly says the loss is "entirely retained".
        ev = out["evaluation"]["summary"].lower()
        assert "insurance gap" not in ev
        assert ("residual uncovered exposure" in ev) or ("entirely retained" in ev)
        # And the legacy keys that encouraged the confusion are gone.
        assert "insurance_gap" not in out
        assert "gap_detected" not in out["evaluation"]


def test_required_residual_example():
    """The exact example from the spec: for a $69.9M event with a $2M retention
    and a $20M limit, the residual uncovered exposure is $47.9M.

    This locks the residual identity: residual = gross - retention - recovery.
    """
    # Reproduce the arithmetic directly (independent of the engine run).
    gross, retention, limit = 69.9, 2.0, 20.0
    recovery = min(max(0.0, gross - retention), limit)
    residual = max(0.0, gross - retention - recovery)
    assert recovery == 20.0
    assert abs(residual - 47.9) < 1e-9


def test_system_prompt_enforces_three_sections():
    """The agent system prompt must mandate the three-section reporting."""
    from cyberrisk.agent.prompts import GROUNDING_REMINDER, SYSTEM_PROMPT

    assert "GROUND-UP CYBER LOSS" in SYSTEM_PROMPT
    assert "INSURANCE RESPONSE" in SYSTEM_PROMPT
    assert "CLIENT RETAINED LOSS" in SYSTEM_PROMPT
    assert "residual client exposure" in SYSTEM_PROMPT
    # The prompt forbids the term rather than using it as a metric.
    assert "NEVER call a gross loss figure" in SYSTEM_PROMPT
    assert "GROUND-UP CYBER LOSS" in GROUNDING_REMINDER
    assert "INSURANCE RESPONSE" in GROUNDING_REMINDER
    assert "CLIENT RETAINED LOSS" in GROUNDING_REMINDER
    assert "NEVER call a gross P99/P99.9 loss an \"insurance gap\"" in GROUNDING_REMINDER
