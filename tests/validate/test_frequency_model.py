"""Validation suite: frequency (count) model.

Insurance relevance:
  - The Poisson is the base frequency law.  A simulated count mean that does
    not converge to lambda is a sampling or parameterisation bug that would
    bias EAL directly.
  - The negative-binomial must reproduce the OVER-DISPERSION the config
    specifies (Var > mean).  Cyber event counts are over-dispersed across a
    portfolio; a NegBin that silently collapsed to Poisson would understate
    tail frequency.
  - Closed-form tail checks pin the discrete CDF: P(N=k) = e^-λ λ^k/k!.
    This is the single most exact statement in the model and a great probe
    for PPF/PMF bugs.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

from cyberrisk.calibration import FrequencySpec
from cyberrisk.frequency import count_distributions, rvs_counts

N = 500_000  # draws per test (cheap, discrete)


def test_poisson_mean_converges_to_lambda():
    lam = 3.0
    dists, means, vars_ = count_distributions([FrequencySpec(model="poisson", lambda_annual=lam)])
    draws = np.asarray(dists[0].rvs(size=N, random_state=np.random.default_rng(1)))
    # E[N] -> lambda, Var[N] -> lambda (Poisson equality)
    assert draws.mean() == pytest.approx(lam, rel=0.02)
    assert draws.var() == pytest.approx(lam, rel=0.04)


def test_poisson_zero_count_matches_analytic():
    lam = 0.8
    dists, _, _ = count_distributions([FrequencySpec(model="poisson", lambda_annual=lam)])
    draws = np.asarray(dists[0].rvs(size=N, random_state=np.random.default_rng(2)))
    p0 = np.exp(-lam)
    emp_p0 = np.mean(draws == 0)
    assert emp_p0 == pytest.approx(p0, abs=0.01)


def test_negbin_has_requested_overdispersion():
    lam, sd = 2.0, 3.0
    dists, means, vars_ = count_distributions(
        [FrequencySpec(model="negbin", lambda_annual=lam, freq_stddev=sd)]
    )
    draws = np.asarray(dists[0].rvs(size=N, random_state=np.random.default_rng(3)))
    # E[N] still = lambda
    assert draws.mean() == pytest.approx(lam, rel=0.05)
    # Var[N] = sd^2 > lambda  (over-dispersion)
    assert draws.var() == pytest.approx(sd * sd, rel=0.1)
    assert draws.var() > lam


def test_negbin_variance_exceeds_mean_by_construction():
    """For cyber counts, over-dispersion must be real (Var > mean)."""
    lam, sd = 1.0, 2.0
    _, _, vars_ = count_distributions(
        [FrequencySpec(model="negbin", lambda_annual=lam, freq_stddev=sd)]
    )
    assert vars_[0] > lam


def test_negbin_reduces_to_poisson_when_stddev_equals_sqrt_lambda():
    """sd = sqrt(lambda) is exactly the Poisson variance -> same law."""
    lam = 2.0
    nb, _, _ = count_distributions(
        [FrequencySpec(model="negbin", lambda_annual=lam, freq_stddev=np.sqrt(lam) + 1e-6)]
    )
    pois = stats.poisson(mu=lam)
    q = np.array([0.1, 0.5, 0.9])
    assert np.array_equal(nb[0].ppf(q), pois.ppf(q))


def test_ppf_is_inverse_cdf():
    """PPF(CDF(k)) == k for all k; PPF(u) >= u for all u."""
    lam = 1.5
    dists, _, _ = count_distributions([FrequencySpec(model="poisson", lambda_annual=lam)])
    dist = dists[0]
    ks = np.arange(0, 12)
    assert np.array_equal(dist.ppf(dist.cdf(ks)), ks)
    u = np.linspace(0.01, 0.99, 50)
    assert np.all(dist.cdf(dist.ppf(u)) >= u - 1e-12)


def test_rvs_counts_via_ppf_preserves_distribution():
    """Inverse-transform sampling from copula uniforms == direct draws."""
    lam = 0.8
    dists, _, _ = count_distributions([FrequencySpec(model="poisson", lambda_annual=lam)])
    uniforms = np.random.default_rng(4).random((1, N))
    counts = rvs_counts(dists, uniforms, np.random.default_rng(4))
    # P(N=k) must match Poisson
    for k in (0, 1, 2, 3):
        theory = np.exp(-lam) * lam**k / math.factorial(k)
        assert np.mean(counts[0] == k) == pytest.approx(theory, abs=0.005)
