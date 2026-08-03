"""Frequency distributions: annual event counts per scenario.

Only the Poisson and negative-binomial count models are used.  Both are
closed under aggregation and have a monotone inverse-CDF (PPF) over the
full integer range -- this is what makes inverse-transform sampling cheap
and exact for the simulation engine.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from scipy import stats

from cyberrisk.calibration import FrequencySpec


class CountDistribution(Protocol):
    """Protocol for the RNG / PPF objects we need from a count distribution."""

    def rvs(self, size: int | tuple[int, ...], random_state: np.random.Generator) -> np.ndarray: ...

    def ppf(self, q: np.ndarray) -> np.ndarray: ...

    def mean(self) -> float: ...


def _rvs_rng(
    dist: stats.rv_discrete | stats.rv_continuous,
    size: int | tuple[int, ...],
    rng: np.random.Generator,
) -> np.ndarray:
    """Distribute `rng` into each scipy generator so seeds flow through."""
    return np.asarray(dist.rvs(size=size, random_state=rng), dtype=np.int64)


def count_distributions(
    specs: list[FrequencySpec],
) -> tuple[list[CountDistribution], np.ndarray, np.ndarray]:
    """Build scipy count distributions, and (mean, variance) per scenario.

    NegBin is parameterised as ``N ~ NegBin(n, p)`` with
    ``n = lambda**2 / (std**2 - lambda)`` and ``p = lambda / std**2``,
    which yields ``E[N] = lambda`` and ``Var[N] = std**2``.
    Returns
        dists  list of PPF/RVS objects aligned with `specs`
        means  array of E[N] per scenario
        vars   array of Var[N] per scenario
    """
    dists: list[CountDistribution] = []
    means = np.zeros(len(specs))
    vars_ = np.zeros(len(specs))

    for i, spec in enumerate(specs):
        lam = spec.lambda_annual
        if spec.model == "poisson":
            dist = stats.poisson(mu=lam)
            var = lam
        elif spec.model == "negbin":
            # Burstiness (dispersion = Var/Mean) maps to the NegBin std dev:
            #   dispersion = var / lam  =>  var = dispersion * lam
            # so the variance we target is (dispersion * lam) and std = sqrt(that).
            if spec.freq_dispersion is not None and spec.freq_dispersion > 1.0:
                var = spec.freq_dispersion * lam
            else:
                sd = max(spec.freq_stddev, np.sqrt(lam) + 1e-6)
                var = sd * sd
            n = lam * lam / (var - lam)
            p = lam / var
            dist = stats.nbinom(n=n, p=p)
        else:  # pragma: no cover - guarded by pydantic Literal
            raise ValueError(f"Unknown frequency model: {spec.model!r}")

        dists.append(dist)
        means[i] = lam
        vars_[i] = var

    return dists, means, vars_


def rvs_counts(
    dists: list[CountDistribution],
    uniforms: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample annual event counts from inverse-transform.

    `uniforms` has shape (n_scenarios, n_years); each column is one year's
    copula-coupled uniforms, each row one scenario's U(0,1) draws.  Counts
    are produced by applying each scenario's PPF to its row, so the
    *within-year* scenario-to-scenario rank dependence from the copula is
    preserved and the marginal count law is exact.
    """
    counts = np.empty_like(uniforms, dtype=np.int64)
    for i, dist in enumerate(dists):
        counts[i] = np.asarray(dist.ppf(uniforms[i]), dtype=np.int64)
    return counts


def poisson_counts(
    lambdas: np.ndarray, n_years: int, rng: np.random.Generator
) -> np.ndarray:
    """Direct (marginal-independent) Poisson draws: shape (n_scenarios, n_years)."""
    return np.asarray(
        stats.poisson(mu=lambdas).rvs(size=(len(lambdas), n_years), random_state=rng),
        dtype=np.int64,
    )
