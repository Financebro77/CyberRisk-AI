"""Config loading / validation tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from cyberrisk.calibration import (
    FrequencySpec,
    ModelConfig,
    Scenario,
    SeveritySpec,
    load_config,
    load_simulation_config,
)

REPO = Path(__file__).parent.parent


def _breach(key: str = "breach") -> Scenario:
    return Scenario(
        key=key,
        name="breach",
        frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
        severity=SeveritySpec(model="lognormal", scale=100_000.0, mu=0.5, sigma=1.0),
    )


def _load() -> ModelConfig:
    return load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )


def test_load_real_config():
    cfg = _load()
    assert cfg.firm_revenue_usd > 0
    assert len(cfg.scenarios) >= 5
    keys = cfg.scenario_keys
    assert len(keys) == len(set(keys))  # unique
    for s in cfg.scenarios:
        assert s.frequency.lambda_annual > 0
        assert s.severity.scale > 0
        assert s.severity.sigma > 0
        assert -1.0 <= s.copula_loading <= 1.0
        assert s.revenue_exponent >= 0.0
        assert "source" in s.annotation


def test_simulation_config_loaded_from_split_file():
    cfg = _load()
    # Simulation knobs now come from simulation_config.yaml
    assert cfg.default_years == 100_000
    assert cfg.chunk_size == 20_000
    assert cfg.seed == 20240817
    assert cfg.tail_quantile == 0.99
    # Phase-1: copula settings
    assert cfg.copula_model == "student_t"
    assert cfg.copula_nu == 5.0
    # Phase-3: event clustering settings
    assert cfg.event_clustering_enabled is True
    assert cfg.catastrophe_probability == 0.05
    assert cfg.catastrophe_multiplier_mean == 2.0
    assert cfg.catastrophe_multiplier_cv == 0.5


def test_load_simulation_config_direct():
    sim = load_simulation_config(REPO / "config" / "simulation_config.yaml")
    assert sim["default_years"] == 100_000
    assert sim["seed"] == 20240817
    assert sim["copula_model"] == "student_t"
    assert sim["copula_nu"] == 5.0
    assert set(sim) == {
        "default_years", "chunk_size", "seed", "tail_quantile",
        "copula_model", "copula_nu",
        "event_clustering_enabled", "catastrophe_probability",
        "catastrophe_multiplier_mean", "catastrophe_multiplier_cv",
    }


def test_scenarios_yaml_no_simulation_block():
    """After the split, scenarios.yaml must not carry engine knobs."""
    import yaml

    raw = yaml.safe_load((REPO / "config" / "scenarios.yaml").read_text(encoding="utf-8"))
    assert "simulation" not in raw


def test_duplicate_scenario_keys_rejected():
    s = _breach()
    with pytest.raises((ValidationError, ValueError)):
        ModelConfig(scenarios=[s, _breach()])


def test_invalid_lambda_rejected():
    with pytest.raises(ValidationError):
        Scenario(
            key="breach",
            name="breach",
            frequency=FrequencySpec(model="poisson", lambda_annual=-1.0),
        )


def test_revenue_scale_resolution():
    cfg = _load()
    # At reference revenue the factor is exactly 1
    base = cfg.resolve_severity_scale(cfg.scenarios[0])
    assert base == cfg.scenarios[0].severity.scale
    # Double revenue with exponent 0.6 -> 2^0.6
    higher = cfg.resolve_severity_scale(cfg.scenarios[0], revenue=2_000_000_000.0)
    assert higher == base * 2.0**0.6
