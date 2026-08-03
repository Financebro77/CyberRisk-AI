"""Validation suite: simulation engine (frequency + severity + copula).

Insurance relevance:
  - The loss distribution must be anchored to its analytic expectation:
    EAL = sum_scenarios lambda * E[S].  If the simulated mean drifts from
    this, the engine has a sampling/aggregation bug that invalidates every
    downstream metric.
  - Increasing risk (score or a scenario lambda) must raise expected loss
    and the tail.  A model that responds wrongly to risk drivers cannot be
    used to price or to size limits.
  - Reproducibility and chunk independence are audit requirements: the same
    seed must give bit-identical results on any machine, any chunking.
  - Dependence must push the tail up (quantified), because ignoring it
    understates PML -- the whole point of the copula.
"""

from __future__ import annotations

import numpy as np
import pytest

from cyberrisk.metrics import compute_metrics, expected_shortfall
from cyberrisk.simulation import score_scaled_lambdas, simulate


def test_single_scenario_eal_matches_analytic(single_config):
    """EAL = lambda * scale * exp(mu + 0.5 sigma^2)."""
    lam, scale, mu, sigma = 0.8, 100_000.0, 0.4, 0.9
    e_s = scale * np.exp(mu + 0.5 * sigma**2)
    theory = lam * e_s
    result = simulate(single_config, n_years=200_000)
    assert result.total_losses.mean() == pytest.approx(theory, rel=0.01)


def test_eal_increases_with_lambda():
    """Doubling event frequency must (approximately) double EAL."""
    from tests.conftest import _single_scenario_config

    cfg = _single_scenario_config(lam=1.0)
    cfg2 = _single_scenario_config(lam=2.0)
    m1 = simulate(cfg, n_years=100_000).total_losses.mean()
    m2 = simulate(cfg2, n_years=100_000).total_losses.mean()
    assert m2 == pytest.approx(m1 * 2.0, rel=0.05)


def test_eal_increases_with_severity_scale():
    """Doubling severity scale must (approximately) double EAL."""
    from tests.conftest import _single_scenario_config

    cfg = _single_scenario_config(lam=0.8, scale=100_000.0)
    cfg2 = _single_scenario_config(lam=0.8, scale=200_000.0)
    m1 = simulate(cfg, n_years=100_000).total_losses.mean()
    m2 = simulate(cfg2, n_years=100_000).total_losses.mean()
    assert m2 == pytest.approx(m1 * 2.0, rel=0.05)


def test_loss_rises_with_risk_score(config):
    """Higher risk score -> higher EAL and heavier tail (log-linear link)."""
    low = simulate(config, n_years=100_000, score=30.0)
    ref = simulate(config, n_years=100_000, score=50.0)
    high = simulate(config, n_years=100_000, score=70.0)
    assert high.total_losses.mean() > ref.total_losses.mean() > low.total_losses.mean()
    m_high = compute_metrics(high)
    m_low = compute_metrics(low)
    assert m_high.es_99 > m_low.es_99
    assert m_high.var_99 > m_low.var_99


def test_score_scaled_lambdas_exact(config):
    """The link factor is exactly exp(k*(score-50)/100)."""
    base = np.array([s.frequency.lambda_annual for s in config.scenarios])
    assert np.allclose(score_scaled_lambdas(config, 50.0), base)
    assert np.allclose(score_scaled_lambdas(config, 70.0), base * np.exp(0.2))
    assert np.allclose(score_scaled_lambdas(config, 30.0), base * np.exp(-0.2))
    # score_k array respected
    ks = np.linspace(0.5, 2.0, len(config.scenarios))
    assert np.allclose(score_scaled_lambdas(config, 70.0, k=ks), base * np.exp(ks * 0.2))


def test_seed_reproducibility(config):
    a = simulate(config, n_years=50_000)
    b = simulate(config, n_years=50_000)
    assert np.array_equal(a.total_losses, b.total_losses)
    assert np.array_equal(a.scenario_losses, b.scenario_losses)


def test_chunk_size_independence(config):
    """Results must be identical regardless of chunking (audit requirement)."""
    base = simulate(config, n_years=30_000)
    cfg_big = config.model_copy(update={"chunk_size": 30_000})
    chunked = simulate(cfg_big, n_years=30_000)
    assert np.array_equal(base.total_losses, chunked.total_losses)


def test_dependence_increases_tail(config):
    """Dependent copula must raise tail risk vs independent (marginals kept)."""
    dep = simulate(config, n_years=100_000, dependence="dependent")
    ind = simulate(config, n_years=100_000, dependence="independent")
    # marginals preserved: means equal
    assert dep.total_losses.mean() == pytest.approx(ind.total_losses.mean(), rel=0.02)
    # tail heavier under dependence
    assert expected_shortfall(dep.total_losses, 0.995) > expected_shortfall(
        ind.total_losses, 0.995
    )


def test_scenario_aal_sums_to_eal(config):
    """Scenario contributions must exactly decompose total EAL."""
    result = simulate(config, n_years=50_000)
    aal = result.scenario_aal()
    assert np.isclose(aal.sum(), result.total_losses.mean(), rtol=1e-9)


def test_return_events_conserves_loss(config):
    """Sum of per-event severities == annual totals (event-stream integrity)."""
    result = simulate(config, n_years=20_000, return_events=True)
    assert result.events is not None
    events = result.events
    # per-scenario aggregate from events == scenario_losses columns
    for i, key in enumerate(config.scenario_keys):
        mask = events[:, 0] == i
        assert np.isclose(
            events[mask, 2].sum(), result.scenario_losses[:, i].sum(), rtol=1e-9
        )
    assert (events[:, 2] > 0).all()


def test_simulation_always_nonnegative_loss(config):
    result = simulate(config, n_years=50_000)
    assert (result.total_losses >= 0).all()
