"""Phase-3 validation: event clustering (catastrophe years)."""

from pathlib import Path

import numpy as np
import pytest

from cyberrisk.calibration import (
    FrequencySpec,
    ModelConfig,
    Scenario,
    SeveritySpec,
    load_config,
)
from cyberrisk.metrics import compute_metrics
from cyberrisk.simulation import _catastrophe_factors, simulate

REPO = Path(__file__).resolve().parent.parent.parent  # tests/validate -> repo root


def _cfg(**kw) -> ModelConfig:
    base = dict(
        firm_revenue_usd=1_000_000_000.0,
        revenue_reference_usd=1_000_000_000.0,
        default_years=50_000,
        chunk_size=20_000,
        seed=20240817,
        tail_quantile=0.99,
        copula_model="student_t",
        copula_nu=5.0,
        event_clustering_enabled=True,
        catastrophe_probability=0.05,
        catastrophe_multiplier_mean=2.0,
        catastrophe_multiplier_cv=0.5,
    )
    base.update(kw)
    return ModelConfig(**base)


def _single(lam=0.8, scale=100_000.0, mu=0.4, sigma=0.9, **kw):
    return _cfg(
        **kw,
        scenarios=[
            Scenario(
                key="breach",
                name="breach",
                frequency=FrequencySpec(model="poisson", lambda_annual=lam),
                severity=SeveritySpec(model="lognormal", scale=scale, mu=mu, sigma=sigma),
                copula_loading=0.0,
            )
        ]
    )


def test_catastrophe_factors_deterministic():
    """Same seed -> identical catastrophe factors (chunk independence)."""
    a = _catastrophe_factors(10_000, root_seed=42, prob=0.05, mean=2.0, cv=0.5)
    b = _catastrophe_factors(10_000, root_seed=42, prob=0.05, mean=2.0, cv=0.5)
    assert np.array_equal(a, b)


def test_catastrophe_factors_value_and_rate():
    """Factors are 1.0 in ordinary years and >=1 in ~prob of years.

    The is-catastrophe fraction is exactly `prob`, but some catastrophe draws
    clamp to exactly 1.0 (a small log-normal draw), so the fraction of years
    with factor STRICTLY > 1 is a touch below `prob`.  We assert both:
    nothing ever goes below 1.0, and the multiplier in catastrophe years is
    ~mean.
    """
    factors = _catastrophe_factors(200_000, root_seed=7, prob=0.05, mean=2.0, cv=0.5)
    # never cheaper in a catastrophe year
    assert (factors >= 1.0).all()
    # mean multiplier across years with an actual multiplier ~ mean (2.0)
    lifted = factors[factors > 1.0]
    assert np.mean(lifted) == pytest.approx(2.0, rel=0.15)
    # a meaningful fraction of years ARE catastrophe years (some clamp to 1.0)
    assert np.mean(factors > 1.0) > 0.04  # ~1 in 20, minus clamped


def test_clustering_raises_eal_by_expected_amount():
    """EAL uplift from clustering ~ prob * (mean - 1) (the expected multiplier)."""
    cfg_off = _single()
    cfg_off = cfg_off.model_copy(update={"event_clustering_enabled": False})
    cfg_on = _single()
    m_off = compute_metrics(simulate(cfg_off, n_years=100_000))
    m_on = compute_metrics(simulate(cfg_on, n_years=100_000))
    # theory: EAL_on / EAL_off = 1 + prob*(mean-1) = 1 + 0.05*1 = 1.05
    ratio = m_on.eal / m_off.eal
    assert ratio == pytest.approx(1.05, rel=0.02)


def test_clustering_raises_tail_more_than_eal():
    """Catastrophe years concentrate in the tail: ES99/P99.9 lift > EAL."""
    cfg_off = _single()
    cfg_off = cfg_off.model_copy(update={"event_clustering_enabled": False})
    cfg_on = _single()
    m_off = compute_metrics(simulate(cfg_off, n_years=150_000))
    m_on = compute_metrics(simulate(cfg_on, n_years=150_000))
    assert m_on.eal / m_off.eal == pytest.approx(1.05, rel=0.03)
    assert m_on.es_99 / m_off.es_99 > 1.05  # tail lifts more than EAL
    assert m_on.p99_9 / m_off.p99_9 > 1.05


def test_clustering_preserves_consistency_with_events():
    """With return_events, per-event sums must equal the clustered totals."""
    cfg = _single()
    result = simulate(cfg, n_years=20_000, return_events=True)
    ev = result.events
    assert ev.shape[1] == 3
    # event column 2 = severity already multiplied by the catastrophe factor
    assert (ev[:, 2] > 0).all()
    # aggregate of events equals scenario_losses
    assert np.isclose(ev[:, 2].sum(), result.scenario_losses[:, 0].sum(), rtol=1e-9)


def test_clustering_disabled_by_default_when_not_enabled():
    cfg = _single(event_clustering_enabled=False)
    result = simulate(cfg, n_years=20_000)
    # no clustering -> no multiplier; loss purely from severity
    assert result.total_losses.shape == (20_000,)
    assert (result.total_losses >= 0).all()


def test_clustering_reproducible_and_chunk_stable():
    """Same seed -> identical results regardless of chunking."""
    cfg = _single()
    a = simulate(cfg, n_years=30_000, seed=99)
    b = simulate(cfg, n_years=30_000, seed=99)
    assert np.array_equal(a.total_losses, b.total_losses)
    # chunk-stable
    cfg_chunked = cfg.model_copy(update={"chunk_size": 5_000})
    c = simulate(cfg_chunked, n_years=30_000, seed=99)
    assert np.array_equal(a.total_losses, c.total_losses)


def test_clustering_full_config_runs():
    """The production config (NegBin + Student-t + clustering) must run cleanly."""
    cfg = load_config(
        REPO / "config" / "scenarios.yaml",
        REPO / "config" / "simulation_config.yaml",
    )
    assert cfg.event_clustering_enabled is True
    m = compute_metrics(simulate(cfg, n_years=50_000, dependence="dependent"))
    assert np.isfinite(m.eal)
    assert m.es_99 > m.eal
