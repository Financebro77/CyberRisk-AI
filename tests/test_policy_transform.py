"""Policy transform tests (Phase 4)."""

from pathlib import Path

import numpy as np
import pytest

from cyberrisk.policy_transform import (
    PolicyStructure,
    apply_annual_aggregate,
    apply_occurrence_transfer,
    transform_events_to_years,
)


def test_single_event_below_deductible_fully_retained():
    sev = np.array([100.0])
    scen = np.array([0])
    policy = PolicyStructure(per_occurrence_deductible=250.0)
    retained, transferred = apply_occurrence_transfer(sev, scen, ["a"], policy)
    assert retained[0] == 100.0
    assert transferred[0] == 0.0


def test_single_event_above_deductible():
    sev = np.array([500.0])
    scen = np.array([0])
    policy = PolicyStructure(per_occurrence_deductible=250.0)
    retained, transferred = apply_occurrence_transfer(sev, scen, ["a"], policy)
    assert transferred[0] == 250.0  # insurer pays 500-250
    assert retained[0] == 250.0


def test_occurrence_limit_caps_transferred():
    sev = np.array([1_000.0])
    scen = np.array([0])
    policy = PolicyStructure(
        per_occurrence_deductible=100.0, per_occurrence_limit=500.0
    )
    retained, transferred = apply_occurrence_transfer(sev, scen, ["a"], policy)
    assert transferred[0] == 500.0
    assert retained[0] == 500.0


def test_sub_limit_applies_per_scenario():
    sev = np.array([10_000.0, 10_000.0])
    scen = np.array([0, 1])
    policy = PolicyStructure(sub_limits={"ransomware": 2_000.0})
    retained, transferred = apply_occurrence_transfer(
        sev, scen, ["breach", "ransomware"], policy
    )
    # breach: no sub-limit -> 10k transferred
    assert transferred[0] == 10_000.0
    # ransomware: sub-limited to 2k
    assert transferred[1] == 2_000.0
    assert retained[1] == 8_000.0


def test_coinsurance_keeps_fraction():
    sev = np.array([1_000.0])
    scen = np.array([0])
    policy = PolicyStructure(per_occurrence_deductible=200.0, coinsurance=0.10)
    retained, transferred = apply_occurrence_transfer(sev, scen, ["a"], policy)
    # insurer pays (1000-200)*0.9 = 720
    assert transferred[0] == pytest.approx(720.0)
    assert retained[0] == pytest.approx(280.0)


def test_annual_aggregate_deductible():
    year_retained = np.array([0.0, 0.0, 0.0])
    year_transferred = np.array([300.0, 900.0, 100.0])
    policy = PolicyStructure(annual_aggregate_deductible=1_000.0)
    final_retained, final_transferred = apply_annual_aggregate(
        year_retained, year_transferred, policy
    )
    # Each simulated year is an independent policy period: the aggregate
    # deductible (1000) resets every year, so NO year has transferred > 1000.
    assert final_transferred[0] == pytest.approx(0.0)  # 300 - 1000 < 0
    assert final_transferred[1] == pytest.approx(0.0)  # 900 - 1000 < 0
    assert final_transferred[2] == pytest.approx(0.0)  # 100 - 1000 < 0
    # All shortfall reverts to retained.
    assert final_retained[0] == pytest.approx(300.0)
    assert final_retained[1] == pytest.approx(900.0)
    assert final_retained[2] == pytest.approx(100.0)


def test_annual_aggregate_limit_caps_total():
    year_retained = np.array([0.0])
    year_transferred = np.array([5_000.0])
    policy = PolicyStructure(annual_aggregate_limit=3_000.0)
    final_retained, final_transferred = apply_annual_aggregate(
        year_retained, year_transferred, policy
    )
    assert final_transferred[0] == 3_000.0
    assert final_retained[0] == 2_000.0


def test_invalid_policy_rejected():
    with pytest.raises(ValueError):
        PolicyStructure(per_occurrence_deductible=-1.0)
    with pytest.raises(ValueError):
        PolicyStructure(coinsurance=1.5)


def test_transform_events_to_years_pipeline():
    sev = np.array([100.0, 500.0, 1_000.0])
    scen = np.array([0, 0, 1])
    years = np.array([0, 0, 1])  # years 0,1
    policy = PolicyStructure(per_occurrence_deductible=100.0)
    out = transform_events_to_years(sev, scen, years, n_years=2, scenario_keys=["a", "b"], policy=policy)
    # Year 0: events 100,500 -> retained 100 + 100 (deductible each) = 200; transferred 400
    # Year 1: event 1000 -> retained 100, transferred 900
    assert out["retained"][0] == pytest.approx(200.0)
    assert out["transferred"][0] == pytest.approx(400.0)
    assert out["retained"][1] == pytest.approx(100.0)
    assert out["transferred"][1] == pytest.approx(900.0)


def test_policy_transform_integrated_with_simulation():
    """End-to-end: simulated events through a policy yield sane retained/transferred."""
    from cyberrisk.calibration import load_config
    from cyberrisk.simulation import simulate

    repo = Path(__file__).parent.parent
    cfg = load_config(
        repo / "config" / "scenarios.yaml",
        repo / "config" / "simulation_config.yaml",
    )
    result = simulate(cfg, n_years=10_000, return_events=True)
    events = result.events  # (scenario, year, severity)
    policy = PolicyStructure(
        per_occurrence_deductible=250_000.0,
        per_occurrence_limit=5_000_000.0,
        annual_aggregate_deductible=1_000_000.0,
        annual_aggregate_limit=20_000_000.0,
    )
    out = transform_events_to_years(
        events[:, 2],
        events[:, 0],
        events[:, 1],
        n_years=result.years,
        scenario_keys=result.scenario_keys,
        policy=policy,
    )
    retained, transferred = out["retained"], out["transferred"]
    # Retained + transferred == total loss every year
    total = result.total_losses
    assert np.allclose(retained + transferred, total, atol=1e-6)
    # Transferred is capped by aggregate limit
    assert transferred.max() <= 20_000_000.0 + 1e-6
    # Deductible means transferred is bounded above by total
    assert (transferred <= total + 1e-6).all()
