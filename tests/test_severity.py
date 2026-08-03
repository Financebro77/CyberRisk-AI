"""Severity distribution tests."""

import numpy as np

from cyberrisk.calibration import SeveritySpec
from cyberrisk.severity import severity_distributions, rvs_severities, draw_severities


def test_lognormal_mean_matches_analytic():
    spec = SeveritySpec(model="lognormal", scale=100.0, mu=0.5, sigma=0.8)
    dists = severity_distributions([spec])
    theory = 100.0 * np.exp(0.5 + 0.5 * 0.8**2)
    rng = np.random.default_rng(11)
    draws = np.asarray(dists[0].rvs(size=500_000, random_state=rng))
    assert np.isclose(draws.mean(), theory, rtol=0.02)
    assert draws.min() > 0.0  # lognormal strictly positive


def test_gpd_mean_and_threshold():
    spec = SeveritySpec(model="gpd", scale=50.0, xi=0.3, threshold=10.0)
    dists = severity_distributions([spec])
    theory = 10.0 + 50.0 / (1.0 - 0.3)
    rng = np.random.default_rng(12)
    draws = np.asarray(dists[0].rvs(size=500_000, random_state=rng))
    assert np.isclose(draws.mean(), theory, rtol=0.03)
    assert draws.min() >= 10.0 - 1e-9


def test_rvs_severities_event_roundtrip():
    spec0 = SeveritySpec(model="lognormal", scale=10.0, mu=0.0, sigma=0.5)
    spec1 = SeveritySpec(model="lognormal", scale=20.0, mu=0.0, sigma=0.5)
    dists = severity_distributions([spec0, spec1])
    counts = np.array([[0, 2, 0, 1], [1, 0, 3, 0]])  # (2 scenarios, 4 years)
    rng = np.random.default_rng(5)
    severities, lookup = rvs_severities(dists, counts, rng)
    assert severities.size == int(counts.sum()) == 7
    # event order matches per-scenario ordering
    assert set(np.unique(lookup[:, 0])) == {0, 1}
    # scenario 0 has 3 events, scenario 1 has 4
    assert (lookup[:, 0] == 0).sum() == 3
    assert (lookup[:, 0] == 1).sum() == 4
    assert severities.min() > 0.0


def test_draw_severities_shape():
    spec0 = SeveritySpec(model="lognormal", scale=5.0, mu=0.2, sigma=0.6)
    spec1 = SeveritySpec(model="lognormal", scale=9.0, mu=0.1, sigma=0.4)
    dists = severity_distributions([spec0, spec1])
    counts = np.array([[2, 0], [1, 3]])
    rng = np.random.default_rng(6)
    severities = draw_severities(dists, counts, rng)
    assert len(severities) == 2
    assert severities[0].size == 2
    assert severities[1].size == 4
