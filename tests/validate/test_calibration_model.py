"""Validation suite: calibration / scenario configuration.

Insurance relevance:
  - Calibration is the risk-bearing assumptions.  Every parameter must be
    validated at the boundary: negative lambdas, negative scales, sigma<=0
    on a lognormal, or xi>=1 on a GPD are all "model is broken" failures
    that must fail loudly, not silently produce nonsense.
  - Revenue scaling is the classic limits/BI proxy; the exponent must apply
    exactly and monotonically, or severity mis-states as a client grows.
  - Benchmark translation must be deterministic, non-mutating, and audited
    (the annotation trail) so the calibrated lambdas trace back to a source.
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from cyberrisk.calibration import (
    FrequencySpec,
    ModelConfig,
    Scenario,
    SeveritySpec,
    apply_benchmarks,
    load_simulation_config,
)


def test_negative_lambda_rejected():
    with pytest.raises(ValidationError):
        FrequencySpec(model="poisson", lambda_annual=-0.5)


def test_zero_lambda_rejected():
    with pytest.raises(ValidationError):
        FrequencySpec(model="poisson", lambda_annual=0.0)


def test_zero_severity_scale_rejected():
    with pytest.raises(ValidationError):
        SeveritySpec(model="lognormal", scale=0.0, mu=0.0, sigma=1.0)


def test_lognormal_requires_sigma():
    with pytest.raises(ValidationError):
        SeveritySpec(model="lognormal", scale=100.0, mu=0.0, sigma=None)


def test_gpd_requires_xi_below_one():
    with pytest.raises(ValidationError):
        SeveritySpec(model="gpd", scale=100.0, xi=1.0, threshold=0.0)


def test_copula_loading_out_of_range_rejected():
    with pytest.raises(ValidationError):
        Scenario(
            key="x",
            name="x",
            frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
            severity=SeveritySpec(model="lognormal", scale=100.0, mu=0.0, sigma=1.0),
            copula_loading=1.5,
        )


def test_duplicate_scenario_keys_rejected():
    def _sc(key):
        return Scenario(
            key=key,
            name=key,
            frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
            severity=SeveritySpec(model="lognormal", scale=100.0, mu=0.0, sigma=1.0),
        )

    with pytest.raises((ValidationError, ValueError)):
        ModelConfig(scenarios=[_sc("a"), _sc("a")])


def test_real_config_fully_valid(config):
    """The production scenario config must satisfy every invariant."""
    keys = config.scenario_keys
    assert len(keys) == len(set(keys))
    for s in config.scenarios:
        assert s.frequency.lambda_annual > 0
        assert s.severity.scale > 0
        assert s.severity.sigma is not None and s.severity.sigma > 0
        assert -1.0 <= s.copula_loading <= 1.0
        assert s.revenue_exponent >= 0.0
        assert "source" in s.annotation  # every scenario is attributable


# ---------------------------------------------------------------- revenue scaling
def test_revenue_scaling_exact_at_reference(config):
    """At the reference revenue the scale factor is exactly 1."""
    for s in config.scenarios:
        base = config.resolve_severity_scale(s)
        assert base == s.severity.scale


def test_revenue_scaling_monotonic_in_revenue(config):
    """Doubling revenue must not shrink severity for any scenario."""
    for s in config.scenarios:
        base = config.resolve_severity_scale(s, revenue=1e9)
        higher = config.resolve_severity_scale(s, revenue=2e9)
        assert higher >= base


def test_revenue_scaling_matches_power_law(config):
    """scale * (R/R_ref)^exp must be exact."""
    s = config.scenarios[0]
    scale = config.resolve_severity_scale(s, revenue=3_000_000_000.0)
    expected = s.severity.scale * (3.0 ** s.revenue_exponent)
    assert scale == pytest.approx(expected, rel=1e-12)


def test_zero_revenue_exponent_is_revenue_neutral(config):
    """exp=0 means severity does not depend on revenue at all."""
    s = config.scenarios[0]
    cfg = config.model_copy(update={"scenarios": [s.model_copy(update={"revenue_exponent": 0.0})]})
    a = cfg.resolve_severity_scale(cfg.scenarios[0], revenue=1e8)
    b = cfg.resolve_severity_scale(cfg.scenarios[0], revenue=1e12)
    assert a == b


# ---------------------------------------------------------------- benchmark translation
def test_apply_benchmarks_deterministic_and_nonmutating(config, benchmark_set):
    before = {s.key: s.frequency.lambda_annual for s in config.scenarios}
    c1 = apply_benchmarks(config, benchmark_set, sector="All")
    c2 = apply_benchmarks(config, benchmark_set, sector="All")
    # pure function: same input -> same output
    assert [s.frequency.lambda_annual for s in c1.scenarios] == [
        s.frequency.lambda_annual for s in c2.scenarios
    ]
    # input config untouched
    assert {s.key: s.frequency.lambda_annual for s in config.scenarios} == before


def test_apply_benchmarks_overrides_known_metrics(config, benchmark_set):
    calibrated = apply_benchmarks(config, benchmark_set, sector="All")
    after = {s.key: s.frequency.lambda_annual for s in calibrated.scenarios}
    assert after["breach"] == pytest.approx(0.75)  # DBIR
    assert after["ransomware"] == pytest.approx(0.40)  # DBIR


def test_apply_benchmarks_leaves_unknown_scenario(config, benchmark_set):
    """A scenario with no benchmark keeps its baseline (no silent drop)."""
    calibrated = apply_benchmarks(config, benchmark_set, sector="All")
    for s in calibrated.scenarios:
        if s.key == "bi":
            assert s.frequency.lambda_annual == pytest.approx(0.30)  # baseline


def test_apply_benchmarks_writes_audit_annotation(config, benchmark_set):
    calibrated = apply_benchmarks(config, benchmark_set, sector="All")
    for s in calibrated.scenarios:
        assert "calibrated_lambda_from" in s.annotation
        assert "calibrated_lambda" in s.annotation


def test_simulation_config_values(config):
    assert config.default_years == 100_000
    assert config.chunk_size == 20_000
    assert config.seed == 20240817
    assert config.tail_quantile == 0.99


def test_load_simulation_config_matches_model(config, repo):
    sim = load_simulation_config(repo / "config" / "simulation_config.yaml")
    assert sim["seed"] == config.seed
    assert sim["default_years"] == config.default_years
