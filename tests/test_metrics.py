"""Risk metrics tests."""

import numpy as np

from cyberrisk.calibration import FrequencySpec, ModelConfig, Scenario, SeveritySpec
from cyberrisk.metrics import (
    BootstrapSE,
    bootstrap_se,
    compute_metrics,
    expected_shortfall,
    quantile,
)
from cyberrisk.simulation import simulate


def _cfg(**kw) -> ModelConfig:
    base = dict(
        firm_revenue_usd=1_000_000_000.0,
        revenue_reference_usd=1_000_000_000.0,
        default_years=50_000,
        chunk_size=20_000,
        seed=20240817,
        tail_quantile=0.99,
    )
    base.update(kw)
    return ModelConfig(**base)


def _single(lam, scale, mu, sigma):
    return _cfg(
        scenarios=[
            Scenario(
                key="breach",
                name="breach",
                frequency=FrequencySpec(model="poisson", lambda_annual=lam),
                severity=SeveritySpec(model="lognormal", scale=scale, mu=mu, sigma=sigma),
            )
        ]
    )


def test_metrics_basic_properties():
    cfg = _single(0.8, 100_000.0, 0.4, 0.9)
    result = simulate(cfg, n_years=100_000)
    m = compute_metrics(result)

    assert m.eal > 0
    assert m.var_95 > 0
    assert m.var_99 >= m.var_95
    assert m.es_95 >= m.var_95
    assert m.es_99 >= m.var_99
    assert m.es_99 >= m.es_95
    assert m.pml_250 >= m.var_99
    assert 0.0 <= m.prob_zero_loss <= 1.0
    # scenario AAL == EAL for single scenario
    assert np.isclose(m.aal_by_scenario["breach"], m.eal, rtol=1e-9)
    # contribution sums to 1
    contrib = m.scenario_contribution()
    assert abs(sum(contrib.values()) - 1.0) < 1e-9


def test_prob_zero_loss_approx_poisson():
    lam = 0.4
    cfg = _single(lam, 100_000.0, 0.0, 1.0)
    result = simulate(cfg, n_years=300_000)
    m = compute_metrics(result)
    theory = np.exp(-lam)
    assert abs(m.prob_zero_loss - theory) < 0.01


def test_quantile_and_es_match():
    rng = np.random.default_rng(0)
    x = rng.lognormal(1.0, 0.5, size=200_000)
    assert np.isclose(quantile(x, 0.5), np.median(x), rtol=0.01)
    var = quantile(x, 0.95)
    assert np.isclose(expected_shortfall(x, 0.95), x[x >= var].mean(), rtol=1e-9)


def test_scenario_aal_breakdown():
    cfg = _cfg(
        scenarios=[
            Scenario(
                key="a",
                name="a",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
                severity=SeveritySpec(model="lognormal", scale=100_000.0, mu=0.0, sigma=1.0),
            ),
            Scenario(
                key="b",
                name="b",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.25),
                severity=SeveritySpec(model="lognormal", scale=200_000.0, mu=0.0, sigma=1.0),
            ),
        ]
    )
    result = simulate(cfg, n_years=100_000)
    m = compute_metrics(result)
    # scenario b has half the freq but double severity -> same AAL as a
    assert np.isclose(m.aal_by_scenario["a"], m.aal_by_scenario["b"], rtol=0.05)
    # total EAL = sum of scenario AALs
    assert np.isclose(sum(m.aal_by_scenario.values()), m.eal, rtol=1e-6)


def test_metrics_are_finite_and_ordered():
    cfg = _single(0.9, 50_000.0, 0.6, 1.2)
    result = simulate(cfg, n_years=80_000)
    m = compute_metrics(result)
    values = [m.eal, m.var_95, m.es_95, m.var_99, m.es_99, m.pml_250, m.max_single_year]
    assert all(np.isfinite(v) for v in values)
    # EAL should be well below the extreme tail measures
    assert m.eal < m.pml_250


# ---------------------------------------------------------------- Phase-1 PML / bootstrap
def test_return_period_pml_present_and_ordered():
    cfg = _single(0.8, 100_000.0, 0.4, 0.9)
    m = compute_metrics(simulate(cfg, n_years=100_000))
    # All return-period PML fields populated and finite
    assert np.isfinite(m.p99_0)
    assert np.isfinite(m.p99_5)
    assert np.isfinite(m.p99_9)
    # Strict ordering of the return-period basis
    assert m.p99_0 < m.p99_5 < m.p99_9
    # PML sits above the 99% VaR (deeper quantile)
    assert m.p99_0 >= m.var_99


def test_return_period_pml_stable_with_sample_size():
    """Return-period PML must be far more stable than the single sample max."""
    cfg = _single(0.8, 100_000.0, 0.4, 0.9)
    m_small = compute_metrics(simulate(cfg, n_years=50_000))
    m_large = compute_metrics(simulate(cfg, n_years=200_000))
    # P99.5 should not swing wildly between runs (rel drift < 25%)
    drift = abs(m_small.p99_5 - m_large.p99_5) / m_large.p99_5
    assert drift < 0.25
    # but max_single_year will (heavy tail) -- no assertion on max itself


def test_bootstrap_se_returns_sensible_errors():
    cfg = _single(0.8, 100_000.0, 0.4, 0.9)
    result = simulate(cfg, n_years=100_000)
    se = bootstrap_se(result.total_losses, n_boot=30, rng=np.random.default_rng(0))
    assert isinstance(se, BootstrapSE)
    # SEs positive and finite
    assert se.eal > 0
    assert se.es_99 > 0
    assert se.p99_9 > 0
    assert all(np.isfinite(v) for v in [se.eal, se.var_95, se.var_99, se.es_95, se.es_99, se.p99_5, se.p99_9])
    # Relative SE on EAL should be small (mean is well-estimated)
    assert se.eal / (result.total_losses.mean()) < 0.05


def test_bootstrap_se_seeded_reproducible():
    """Same seed + same sample -> identical bootstrap SE (audit requirement)."""
    rng = np.random.default_rng(42)
    x = rng.lognormal(10.0, 1.0, size=20_000)
    s1 = bootstrap_se(x, n_boot=20, rng=np.random.default_rng(7))
    s2 = bootstrap_se(x, n_boot=20, rng=np.random.default_rng(7))
    assert s1.eal == s2.eal
    assert s1.es_99 == s2.es_99


def test_bootstrap_se_rejects_bad_input():
    with np.testing.assert_raises(ValueError):
        bootstrap_se(np.zeros((5, 5)))
