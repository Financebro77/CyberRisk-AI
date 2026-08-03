"""Phase-3 validation: negative-binomial (burstiness) frequency model."""

import numpy as np
import pytest
from pydantic import ValidationError
from scipy import stats

from cyberrisk.calibration import FrequencySpec
from cyberrisk.frequency import count_distributions


def test_dispersion_maps_to_variance():
    """Var = dispersion * lambda (the plain-English burstiness ratio)."""
    lam, disp = 0.5, 2.0
    dists, means, vars_ = count_distributions(
        [FrequencySpec(model="negbin", lambda_annual=lam, freq_dispersion=disp)]
    )
    assert means[0] == pytest.approx(lam)  # mean preserved
    assert vars_[0] == pytest.approx(disp * lam)  # variance = disp * mean


def test_dispersion_one_equals_poisson():
    """dispersion = 1 should match a Poisson (Var = Mean)."""
    lam = 2.0
    nb, _, _ = count_distributions(
        [FrequencySpec(model="negbin", lambda_annual=lam, freq_dispersion=1.0 + 1e-9)]
    )
    pois = stats.poisson(mu=lam)
    q = np.array([0.1, 0.5, 0.9])
    assert np.array_equal(nb[0].ppf(q), pois.ppf(q))


def test_dispersion_realized_over_dispersion():
    """Simulated counts must actually show Var/Mean ~ dispersion."""
    lam, disp = 1.0, 2.5
    dists, _, _ = count_distributions(
        [FrequencySpec(model="negbin", lambda_annual=lam, freq_dispersion=disp)]
    )
    draws = np.asarray(dists[0].rvs(size=400_000, random_state=np.random.default_rng(0)))
    emp_disp = draws.var() / draws.mean()
    assert emp_disp == pytest.approx(disp, rel=0.1)
    assert emp_disp > 1.0  # genuinely over-dispersed


def test_dispersion_mean_preserved():
    """Burstiness must not change the mean event rate."""
    lam = 0.75
    dists, means, _ = count_distributions(
        [FrequencySpec(model="negbin", lambda_annual=lam, freq_dispersion=2.0)]
    )
    draws = np.asarray(dists[0].rvs(size=200_000, random_state=np.random.default_rng(1)))
    assert draws.mean() == pytest.approx(lam, rel=0.03)


def test_dispersion_requires_above_one():
    """dispersion must be >= 1 (a negative binomial can't under-disperse)."""
    with pytest.raises(ValidationError):
        FrequencySpec(model="negbin", lambda_annual=0.5, freq_dispersion=0.8)


def test_negbin_requires_dispersion_or_stddev():
    """A negbin with neither dispersion nor stddev is degenerate -> reject."""
    with pytest.raises(ValidationError):
        FrequencySpec(model="negbin", lambda_annual=0.5)


def test_dispersion_higher_means_heavier_frequency_tail():
    """Higher dispersion -> more extreme high-count years (tail of counts)."""
    lam = 1.0
    d1, _, _ = count_distributions(
        [FrequencySpec(model="negbin", lambda_annual=lam, freq_dispersion=1.5)]
    )
    d2, _, _ = count_distributions(
        [FrequencySpec(model="negbin", lambda_annual=lam, freq_dispersion=3.0)]
    )
    a = np.asarray(d1[0].rvs(size=300_000, random_state=np.random.default_rng(2)))
    b = np.asarray(d2[0].rvs(size=300_000, random_state=np.random.default_rng(2)))
    assert b.var() > a.var()
    # both have the same mean
    assert np.isclose(a.mean(), b.mean(), rtol=0.03)
