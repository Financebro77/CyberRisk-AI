"""Sensitivity / tornado tests (Phase 4)."""

from pathlib import Path

import pytest

from cyberrisk.calibration import load_config
from cyberrisk.sensitivity import lambda_sensitivity

REPO = Path(__file__).parent.parent


def _config():
    return load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )


def test_lambda_sensitivity_returns_tornado_bars():
    cfg = _config()
    bars = lambda_sensitivity(
        cfg, scenario_keys=["breach", "ransomware"], n_years=20_000, pct=0.5, seed=1
    )
    assert len(bars) == 2
    labels = [b.label for b in bars]
    assert set(labels) == {"breach", "ransomware"}
    for bar in bars:
        assert bar.low < bar.base < bar.high
        assert bar.base > 0


def test_lambda_sensitivity_monotonic_in_frequency():
    """Raising a scenario's lambda must raise EAL (all else equal)."""
    cfg = _config()
    bars = lambda_sensitivity(cfg, scenario_keys=["breach"], n_years=30_000, pct=0.5, seed=3)
    bar = bars[0]
    assert bar.high > bar.base > bar.low


def test_sensitivity_scenario_keys_validated():
    cfg = _config()
    with pytest.raises((ValueError, KeyError)):
        lambda_sensitivity(cfg, scenario_keys=["does_not_exist"], n_years=1_000, seed=1)
