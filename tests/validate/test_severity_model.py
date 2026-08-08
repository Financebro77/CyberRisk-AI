"""Validation suite: severity (loss amount) model.

Insurance relevance:
  - Heavy tails are the heart of cyber risk.  A lognormal severity with the
    config's sigma must exhibit the classic signature: the mean well above
    the median, and the tail driving a small share of events carrying a
    large share of loss (Pareto principle).  If the model were thin-tailed,
    VaR/ES at 99% would be grossly understated and PML would be wrong.
  - The distribution must reproduce its analytic moments (mean, median)
    so EAL = lambda * E[S] has a defensible analytic anchor.
  - GPD is the standard tail model for excess-over-threshold; it must be
    bounded below by its threshold and its mean must match theory when xi<1.
  - Tail weight must increase monotonically with sigma (more volatile
    severity -> heavier tail), which the sensitivity analysis depends on.
"""

from __future__ import annotations

import numpy as np
import pytest

from cyberrisk.calibration import SeveritySpec
from cyberrisk.severity import severity_distributions

N = 500_000


def test_lognormal_mean_matches_analytic():
    spec = SeveritySpec(model="lognormal", scale=100.0, mu=0.5, sigma=0.8)
    dists = severity_distributions([spec])
    theory = 100.0 * np.exp(0.5 + 0.5 * 0.8**2)
    draws = np.asarray(dists[0].rvs(size=N, random_state=np.random.default_rng(1)))
    assert draws.mean() == pytest.approx(theory, rel=0.02)


def test_lognormal_median_matches_analytic():
    """Median = scale * exp(mu); must hold for heavy-tailed data."""
    spec = SeveritySpec(model="lognormal", scale=100.0, mu=0.5, sigma=0.8)
    dists = severity_distributions([spec])
    draws = np.asarray(dists[0].rvs(size=N, random_state=np.random.default_rng(2)))
    theory_median = 100.0 * np.exp(0.5)
    assert np.median(draws) == pytest.approx(theory_median, rel=0.05)


def test_lognormal_is_heavy_tailed():
    """Mean >> median and a thin slice of events carries most of the loss.

    Uses sigma=1.3 (ransomware-scale tail), where the analytic mean/median
    ratio is ~2.3 -- a genuinely heavy tail.  With sigma=0.8 the ratio is
    only ~1.4 (moderate), which would not show the Pareto effect strongly.
    """
    spec = SeveritySpec(model="lognormal", scale=100.0, mu=0.5, sigma=1.3)
    dists = severity_distributions([spec])
    draws = np.asarray(dists[0].rvs(size=N, random_state=np.random.default_rng(3)))
    # Mean / median ratio > 2 signals a heavy right tail
    assert draws.mean() / np.median(draws) > 2.0
    # Pareto concentration: top 5% of events carry a large share of total loss.
    # Analytic value for this lognormal is ~36.5% (vs ~10% for a normal tail).
    top5 = draws[np.argsort(draws)[-int(0.05 * N):]]
    share = top5.sum() / draws.sum()
    assert share > 0.35
    assert share < 0.5  # heavy but not absurdly concentrated


def test_tail_heaviness_grows_with_sigma():
    """Higher sigma -> heavier tail (higher mean/median ratio, higher tail share)."""
    low = severity_distributions([SeveritySpec(model="lognormal", scale=100.0, mu=0.0, sigma=0.5)])
    high = severity_distributions([SeveritySpec(model="lognormal", scale=100.0, mu=0.0, sigma=1.5)])
    d_low = np.asarray(low[0].rvs(size=N, random_state=np.random.default_rng(4)))
    d_high = np.asarray(high[0].rvs(size=N, random_state=np.random.default_rng(4)))
    assert (d_high.mean() / np.median(d_high)) > (d_low.mean() / np.median(d_low))
    # High-sigma 99th percentile far exceeds low-sigma's
    assert np.quantile(d_high, 0.99) > np.quantile(d_low, 0.99) * 5


def test_high_quantile_exceeds_mean_by_wide_margin():
    """For a heavy-tailed cyber loss, VaR99 >> EAL-per-event."""
    spec = SeveritySpec(model="lognormal", scale=510_000.0, mu=0.75, sigma=1.30)  # ransomware
    dists = severity_distributions([spec])
    draws = np.asarray(dists[0].rvs(size=N, random_state=np.random.default_rng(5)))
    q99 = np.quantile(draws, 0.99)
    assert q99 > draws.mean() * 3


def test_gpd_threshold_lower_bound():
    spec = SeveritySpec(model="gpd", scale=50.0, xi=0.3, threshold=10.0)
    dists = severity_distributions([spec])
    draws = np.asarray(dists[0].rvs(size=N, random_state=np.random.default_rng(6)))
    assert draws.min() >= 10.0 - 1e-9


def test_gpd_mean_matches_analytic_when_xi_lt_1():
    spec = SeveritySpec(model="gpd", scale=50.0, xi=0.3, threshold=10.0)
    dists = severity_distributions([spec])
    draws = np.asarray(dists[0].rvs(size=N, random_state=np.random.default_rng(7)))
    theory = 10.0 + 50.0 / (1.0 - 0.3)
    assert draws.mean() == pytest.approx(theory, rel=0.03)


def test_gpd_heavier_xi_heavier_tail():
    """Higher GPD tail index xi -> heavier tail (higher 99th percentile)."""
    xi_low = severity_distributions([SeveritySpec(model="gpd", scale=50.0, xi=0.1, threshold=10.0)])
    xi_high = severity_distributions([SeveritySpec(model="gpd", scale=50.0, xi=0.5, threshold=10.0)])
    d_low = np.asarray(xi_low[0].rvs(size=N, random_state=np.random.default_rng(8)))
    d_high = np.asarray(xi_high[0].rvs(size=N, random_state=np.random.default_rng(8)))
    assert np.quantile(d_high, 0.99) > np.quantile(d_low, 0.99)


def test_lognormal_samples_are_positive():
    spec = SeveritySpec(model="lognormal", scale=100.0, mu=0.0, sigma=1.0)
    dists = severity_distributions([spec])
    draws = np.asarray(dists[0].rvs(size=100_000, random_state=np.random.default_rng(9)))
    assert (draws > 0).all()
