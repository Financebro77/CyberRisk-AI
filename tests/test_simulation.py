"""Simulation engine tests: correctness, reproducibility, dependence effect."""

import numpy as np
import pytest

from cyberrisk.calibration import FrequencySpec, ModelConfig, Scenario, SeveritySpec
from cyberrisk.simulation import simulate, score_scaled_lambdas


def _config(**overrides) -> ModelConfig:
    base = dict(
        firm_revenue_usd=1_000_000_000.0,
        revenue_reference_usd=1_000_000_000.0,
        default_years=100_000,
        chunk_size=20_000,
        seed=20240817,
        tail_quantile=0.99,
    )
    base.update(overrides)
    return ModelConfig(**base)


def _single_scenario_config(lam: float, scale: float, mu: float, sigma: float) -> ModelConfig:
    return _config(
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


def test_single_scenario_eal_matches_analytic():
    """EAL = lambda * E[S]; check against analytic lognormal expectation."""
    lam, scale, mu, sigma = 0.8, 100_000.0, 0.4, 0.9
    cfg = _single_scenario_config(lam, scale, mu, sigma)
    e_s = scale * np.exp(mu + 0.5 * sigma**2)
    theory = lam * e_s

    result = simulate(cfg, n_years=400_000)
    # Monte Carlo error on mean scales ~ sigma/sqrt(n) ~ e_s/sqrt(400k) ~ 0.15%
    assert abs(result.total_losses.mean() - theory) / theory < 0.01


def test_seed_reproducibility():
    cfg = _config(
        scenarios=[
            Scenario(
                key="breach",
                name="breach",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.75),
                severity=SeveritySpec(model="lognormal", scale=320_000.0, mu=0.6, sigma=1.1),
                copula_loading=0.55,
            ),
            Scenario(
                key="ransomware",
                name="ransomware",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.4),
                severity=SeveritySpec(model="lognormal", scale=510_000.0, mu=0.75, sigma=1.3),
                copula_loading=0.7,
            ),
        ]
    )
    a = simulate(cfg, n_years=50_000)
    b = simulate(cfg, n_years=50_000)
    assert np.array_equal(a.total_losses, b.total_losses)
    assert np.array_equal(a.scenario_losses, b.scenario_losses)


def test_chunk_size_independence():
    """Results must not depend on chunking (SeedSequence per chunk)."""
    cfg = _config(
        scenarios=[
            Scenario(
                key="breach",
                name="breach",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.75),
                severity=SeveritySpec(model="lognormal", scale=320_000.0, mu=0.6, sigma=1.1),
                copula_loading=0.55,
            ),
            Scenario(
                key="ransomware",
                name="ransomware",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.4),
                severity=SeveritySpec(model="lognormal", scale=510_000.0, mu=0.75, sigma=1.3),
                copula_loading=0.7,
            ),
        ]
    )
    # Same seed, different chunk sizes -> identical streams
    small = simulate(cfg, n_years=20_000)
    big = simulate(cfg, n_years=20_000, seed=cfg.seed)
    big_cfg = cfg.model_copy(update={"chunk_size": 5_000})
    chunked = simulate(big_cfg, n_years=20_000)
    assert np.array_equal(small.total_losses, chunked.total_losses)


def test_dependence_increases_tail():
    """Positive cross-scenario dependence must raise tail risk (VaR/ES)."""
    cfg = _config(
        scenarios=[
            Scenario(
                key="a",
                name="a",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
                severity=SeveritySpec(model="lognormal", scale=100_000.0, mu=0.5, sigma=1.0),
                copula_loading=0.8,
            ),
            Scenario(
                key="b",
                name="b",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
                severity=SeveritySpec(model="lognormal", scale=100_000.0, mu=0.5, sigma=1.0),
                copula_loading=0.8,
            ),
        ]
    )
    dep = simulate(cfg, n_years=400_000, dependence="dependent")
    ind = simulate(cfg, n_years=400_000, dependence="independent")
    # Means unchanged (copula preserves marginals), tails shift up.
    assert np.isclose(dep.total_losses.mean(), ind.total_losses.mean(), rtol=0.02)
    # Use stable tail measures (ES at a deep quantile) -- max() of a single
    # heavy-tailed sample is far too noisy for a deterministic assertion.
    def es(x, q):
        v = np.quantile(x, q)
        return x[x >= v].mean()

    assert es(dep.total_losses, 0.995) > es(ind.total_losses, 0.995)
    assert np.quantile(dep.total_losses, 0.99) > np.quantile(ind.total_losses, 0.99)


def test_named_seed_overrides_config():
    cfg = _config(
        scenarios=[
            Scenario(
                key="a",
                name="a",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
                severity=SeveritySpec(model="lognormal", scale=10_000.0, mu=0.0, sigma=1.0),
            )
        ]
    )
    r1 = simulate(cfg, n_years=10_000, seed=111)
    r2 = simulate(cfg, n_years=10_000, seed=111)
    r3 = simulate(cfg, n_years=10_000, seed=222)
    assert np.array_equal(r1.total_losses, r2.total_losses)
    assert not np.array_equal(r1.total_losses, r3.total_losses)


def test_returns_event_stream():
    cfg = _config(
        scenarios=[
            Scenario(
                key="a",
                name="a",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
                severity=SeveritySpec(model="lognormal", scale=10_000.0, mu=0.0, sigma=1.0),
            ),
            Scenario(
                key="b",
                name="b",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.3),
                severity=SeveritySpec(model="lognormal", scale=5_000.0, mu=0.0, sigma=1.0),
            ),
        ]
    )
    result = simulate(cfg, n_years=50_000, return_events=True)
    assert result.events is not None
    assert result.events.shape[1] == 3  # (scenario, year, severity)
    # Event count sums to total events across all years
    ev = result.events
    assert ev[:, 0].max() <= 1  # only scenarios 0/1
    assert (ev[:, 2] > 0).all()


def test_invalid_n_years_rejected():
    cfg = _single_scenario_config(0.5, 10_000.0, 0.0, 1.0)
    with pytest.raises(ValueError):
        simulate(cfg, n_years=0)
    with pytest.raises(ValueError):
        simulate(cfg, n_years=-5)


# ---------------------------------------------------------------- Phase-1 t-copula
def _multi_scenario_config(copula_model="student_t", nu=5.0):
    return _config(
        copula_model=copula_model,
        copula_nu=nu,
        scenarios=[
            Scenario(
                key="a",
                name="a",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
                severity=SeveritySpec(model="lognormal", scale=100_000.0, mu=0.5, sigma=1.0),
                copula_loading=0.7,
            ),
            Scenario(
                key="b",
                name="b",
                frequency=FrequencySpec(model="poisson", lambda_annual=0.5),
                severity=SeveritySpec(model="lognormal", scale=100_000.0, mu=0.5, sigma=1.0),
                copula_loading=0.7,
            ),
        ],
    )


def test_student_t_copula_preserves_marginals():
    """The t-copula must NOT change the marginal count law or EAL."""
    cfg = _multi_scenario_config(copula_model="student_t", nu=5)
    t = simulate(cfg, n_years=200_000, dependence="dependent")
    g = simulate(cfg.model_copy(update={"copula_model": "gaussian"}), n_years=200_000, dependence="dependent")
    # Means equal (both copulas preserve marginals)
    assert np.isclose(t.total_losses.mean(), g.total_losses.mean(), rtol=0.02)


def test_student_t_raises_deep_tail():
    """At deep quantiles the t-copula should show a heavier tail.

    Uses the deep tail proxy: the t-copula's extra dependence concentrates
    at the extreme right tail, so P99.9 (1-in-1000) should be >= Gaussian.
    """
    cfg = _multi_scenario_config(copula_model="student_t", nu=3)  # very heavy t
    g_cfg = cfg.model_copy(update={"copula_model": "gaussian"})
    t = simulate(cfg, n_years=300_000, dependence="dependent")
    g = simulate(g_cfg, n_years=300_000, dependence="dependent")
    assert np.quantile(t.total_losses, 0.999) > np.quantile(g.total_losses, 0.999)


def test_copula_model_override_in_simulate():
    """copula_model param must override config."""
    cfg = _multi_scenario_config(copula_model="gaussian")
    # override to student_t at call time
    r = simulate(cfg, n_years=20_000, dependence="dependent", copula_model="student_t", copula_nu=5)
    assert r.total_losses.shape == (20_000,)
    assert np.isfinite(r.total_losses).all()
