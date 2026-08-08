"""Validation suite: policy transform invariants.

Insurance relevance: these are conservation and no-arbitrage identities.
A violation means the retained/transferred split is not economically
meaningful and cannot be shown to an underwriter or a CFO.

  - Retained <= original loss and retained + transferred == original loss:
    money is conserved; the insured never "retains more than they lost".
  - No arbitrage: the insurer's payout on any occurrence never exceeds the
    occurrence's sub-limit or the occurrence limit, and a policy with a
    LOWER limit or HIGHER deductible can never pay MORE.
  - Conservative terms must reduce transferred loss and raise retained loss
    monotonically -- otherwise quoting a tighter policy would lower the
    premium, which inverts the market.
  - Annual aggregate cap is a hard ceiling on the insurer's total payout.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cyberrisk.policy_transform import (
    PolicyStructure,
    apply_annual_aggregate,
    apply_occurrence_transfer,
    transform_events_to_years,
)


def test_retained_never_exceeds_original_loss():
    """Core invariant: insured cannot retain more than the loss itself."""
    rng = np.random.default_rng(0)
    sev = rng.lognormal(10.0, 1.2, size=5_000)
    scen = rng.integers(0, 3, size=5_000)
    policy = PolicyStructure(
        per_occurrence_deductible=250_000.0,
        per_occurrence_limit=5_000_000.0,
        coinsurance=0.10,
    )
    retained, transferred = apply_occurrence_transfer(sev, scen, ["a", "b", "c"], policy)
    assert np.all(retained <= sev + 1e-9)
    assert np.all(retained >= 0)
    assert np.all(transferred >= 0)


def test_retained_plus_transferred_equals_loss():
    """Conservation: every dollar is either retained or transferred."""
    rng = np.random.default_rng(1)
    sev = rng.lognormal(10.0, 1.2, size=2_000)
    scen = np.zeros(2_000, dtype=int)
    policy = PolicyStructure(per_occurrence_deductible=100.0)
    retained, transferred = apply_occurrence_transfer(sev, scen, ["a"], policy)
    assert np.allclose(retained + transferred, sev, atol=1e-6)


def test_occurrence_limit_caps_transfer():
    """Payout per occurrence cannot exceed the occurrence limit."""
    sev = np.array([1_000.0, 5_000.0, 20_000.0])
    scen = np.zeros(3, dtype=int)
    policy = PolicyStructure(per_occurrence_deductible=100.0, per_occurrence_limit=2_000.0)
    retained, transferred = apply_occurrence_transfer(sev, scen, ["a"], policy)
    assert np.all(transferred <= 2_000.0 + 1e-9)
    assert np.all(retained + transferred == sev)


def test_sub_limit_caps_transfer_per_scenario():
    sev = np.array([10_000.0, 10_000.0])
    scen = np.array([0, 1])
    policy = PolicyStructure(sub_limits={"ransomware": 2_000.0})
    retained, transferred = apply_occurrence_transfer(sev, scen, ["breach", "ransomware"], policy)
    # breach unconstrained, ransomware sub-limited
    assert transferred[0] == 10_000.0
    assert transferred[1] == 2_000.0
    assert retained[1] == 8_000.0


def test_higher_deductible_reduces_transfer():
    """Monotone: bigger deductible -> strictly less transferred, more retained."""
    rng = np.random.default_rng(2)
    sev = rng.lognormal(10.0, 1.0, size=5_000)
    scen = np.zeros(5_000, dtype=int)
    p_low = PolicyStructure(per_occurrence_deductible=100.0)
    p_high = PolicyStructure(per_occurrence_deductible=1_000.0)
    r_low, t_low = apply_occurrence_transfer(sev, scen, ["a"], p_low)
    r_high, t_high = apply_occurrence_transfer(sev, scen, ["a"], p_high)
    assert t_high.sum() < t_low.sum()
    assert r_high.sum() > r_low.sum()


def test_lower_occurrence_limit_reduces_transfer():
    rng = np.random.default_rng(3)
    sev = rng.lognormal(10.0, 1.0, size=5_000)
    scen = np.zeros(5_000, dtype=int)
    p_high = PolicyStructure(per_occurrence_deductible=0.0, per_occurrence_limit=5_000_000.0)
    p_low = PolicyStructure(per_occurrence_deductible=0.0, per_occurrence_limit=500_000.0)
    _, t_high = apply_occurrence_transfer(sev, scen, ["a"], p_high)
    _, t_low = apply_occurrence_transfer(sev, scen, ["a"], p_low)
    assert t_low.sum() < t_high.sum()


def test_annual_aggregate_limit_is_hard_ceiling():
    """Insurer's total annual payout never exceeds the aggregate limit."""
    rng = np.random.default_rng(4)
    year_retained = np.zeros(5_000)
    year_transferred = rng.uniform(0, 50_000_000, size=5_000)
    policy = PolicyStructure(annual_aggregate_limit=20_000_000.0)
    final_retained, final_transferred = apply_annual_aggregate(
        year_retained, year_transferred, policy
    )
    assert np.all(final_transferred <= 20_000_000.0 + 1e-6)
    assert np.all(final_transferred >= 0)
    # excess pushed to retained
    assert np.allclose(final_retained + final_transferred, year_transferred, atol=1e-6)


def test_annual_aggregate_deductible_per_year():
    """Each simulated year is its own policy period (deductible resets)."""
    year_retained = np.zeros(3)
    year_transferred = np.array([300.0, 900.0, 100.0])
    policy = PolicyStructure(annual_aggregate_deductible=1_000.0)
    final_retained, final_transferred = apply_annual_aggregate(
        year_retained, year_transferred, policy
    )
    assert np.allclose(final_transferred, [0.0, 0.0, 0.0])
    assert np.allclose(final_retained, [300.0, 900.0, 100.0])


def test_no_policy_terms_no_transformation():
    """A bare policy (all zeros) must leave loss unchanged (identity)."""
    rng = np.random.default_rng(5)
    sev = rng.lognormal(10.0, 1.0, size=2_000)
    scen = np.zeros(2_000, dtype=int)
    policy = PolicyStructure()
    retained, transferred = apply_occurrence_transfer(sev, scen, ["a"], policy)
    assert np.allclose(retained, 0.0)
    assert np.allclose(transferred, sev, atol=1e-6)


def test_transform_events_to_years_conservation():
    """retained + transferred == total loss for every simulated year."""
    from cyberrisk.calibration import load_config
    from cyberrisk.simulation import simulate

    repo = Path(__file__).resolve().parent.parent.parent  # tests/validate -> repo root
    cfg = load_config(
        repo / "config" / "scenarios.yaml",
        repo / "config" / "simulation_config.yaml",
    )
    result = simulate(cfg, n_years=10_000, return_events=True)
    ev = result.events
    policy = PolicyStructure(
        per_occurrence_deductible=250_000.0,
        per_occurrence_limit=5_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=20_000_000.0,
    )
    out = transform_events_to_years(
        ev[:, 2], ev[:, 0], ev[:, 1],
        n_years=result.years,
        scenario_keys=result.scenario_keys,
        policy=policy,
    )
    retained, transferred = out["retained"], out["transferred"]
    total = result.total_losses
    assert np.allclose(retained + transferred, total, atol=1e-6)
    assert np.all(retained >= 0)
    assert transferred.max() <= 20_000_000.0 + 1e-6
