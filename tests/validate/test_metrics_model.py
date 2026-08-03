"""Validation suite: risk metrics axioms.

Insurance relevance: these are the mathematical identities a defensible
risk report depends on.  A violation is not a tuning issue -- it means the
metrics cannot be shown to a client or a regulator.

  - ES >= VaR is the defining property of Expected Shortfall; if it ever
    failed the report would show an implausible "tail mean below threshold".
  - Coherent-risk monotonicity: risk measures must be ordered
    VaR_95 <= VaR_99 <= PML_250.  A crossing signals a sampling or
    quantile bug.
  - Subadditivity (VaR of sum <= sum of VaRs) is what makes VaR NOT
    subadditive a known defect; ES IS subadditive, and that property is
    what justifies reporting ES for a portfolio.
  - Scenario contributions must sum to EAL exactly (reconciliation).
"""

from __future__ import annotations

import numpy as np
import pytest

from cyberrisk.metrics import compute_metrics, expected_shortfall, quantile, exceedance_curve


def test_es_greater_than_var(single_config):
    """Expected Shortfall must exceed VaR at the same confidence."""
    from cyberrisk.simulation import simulate

    result = simulate(single_config, n_years=100_000)
    m = compute_metrics(result)
    assert m.es_95 >= m.var_95
    assert m.es_99 >= m.var_99
    assert m.es_99 >= m.es_95


def test_risk_measures_ordered(single_config):
    """VaR_95 <= VaR_99 <= PML_250 and ES_99 >= VaR_99."""
    from cyberrisk.simulation import simulate

    m = compute_metrics(simulate(single_config, n_years=100_000))
    assert m.var_95 <= m.var_99 <= m.pml_250
    assert m.es_99 >= m.var_99
    assert m.eal < m.pml_250  # mean below extreme tail


def test_eal_is_finite_and_positive(single_config):
    from cyberrisk.simulation import simulate

    m = compute_metrics(simulate(single_config, n_years=100_000))
    assert np.isfinite(m.eal)
    assert m.eal > 0


def test_scenario_contributions_sum_to_one(config):
    from cyberrisk.simulation import simulate

    m = compute_metrics(simulate(config, n_years=30_000))
    contrib = m.scenario_contribution()
    assert abs(sum(contrib.values()) - 1.0) < 1e-9
    # each contribution in [0,1]
    assert all(0.0 <= v <= 1.0 for v in contrib.values())


def test_aal_by_scenario_sums_to_eal(config):
    from cyberrisk.simulation import simulate

    m = compute_metrics(simulate(config, n_years=30_000))
    assert sum(m.aal_by_scenario.values()) == pytest.approx(m.eal, rel=1e-9)


def test_expected_shortfall_matches_tail_mean():
    """ES(q) == mean of the losses above VaR(q)."""
    rng = np.random.default_rng(0)
    x = rng.lognormal(1.0, 0.6, size=100_000)
    var = quantile(x, 0.95)
    assert expected_shortfall(x, 0.95) == pytest.approx(x[x >= var].mean(), rel=1e-9)


def test_expected_shortfall_is_subadditive():
    """ES(a + b) <= ES(a) + ES(b) -- the property that justifies ES over VaR."""
    rng = np.random.default_rng(1)
    a = rng.lognormal(1.0, 0.5, size=100_000)
    b = rng.lognormal(0.8, 0.4, size=100_000)
    es_sum = expected_shortfall(a + b, 0.99)
    es_parts = expected_shortfall(a, 0.99) + expected_shortfall(b, 0.99)
    assert es_sum <= es_parts * (1 + 1e-9)


def test_loss_exceedance_curve_monotone(config):
    """LEC: exceedance probability must fall as the loss level rises."""
    from cyberrisk.simulation import simulate

    losses = simulate(config, n_years=30_000).total_losses
    lec = exceedance_curve(losses)
    x, p = lec[0], lec[1]
    assert len(x) == len(losses)
    assert np.all(np.diff(x) >= 0)  # loss levels sorted ascending
    assert np.all(np.diff(p) <= 1e-12)  # exceedance probabilities non-increasing
    assert p[-1] <= p[0]  # tail much rarer than body


def test_zero_loss_frequency_bounded(single_config):
    """P(no loss) in (0,1); for lambda=0.8 ~ e^-0.8."""
    from cyberrisk.simulation import simulate

    m = compute_metrics(simulate(single_config, n_years=100_000))
    assert 0.0 < m.prob_zero_loss < 1.0
    assert m.prob_zero_loss == pytest.approx(np.exp(-0.8), abs=0.02)


def test_metrics_stable_with_more_years(single_config):
    """ES/VaR at 99% should stabilise as n_years grows (low estimator bias)."""
    from cyberrisk.simulation import simulate

    m50 = compute_metrics(simulate(single_config, n_years=50_000))
    m200 = compute_metrics(simulate(single_config, n_years=200_000))
    # Relative difference small (not exact -- different seeds)
    assert abs(m50.es_99 - m200.es_99) / m200.es_99 < 0.15
