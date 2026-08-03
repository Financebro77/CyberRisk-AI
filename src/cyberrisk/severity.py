"""Severity distributions: per-event loss amounts.

Models:
  lognormal  S = scale * exp(mu + sigma * Z),  Z ~ N(0,1)
             E[S] = scale * exp(mu + sigma^2/2)
  gpd        S = threshold + GPD(loc=threshold, scale, xi)
             E[S] = threshold + scale/(1-xi)   (xi < 1)

Severity per scenario is fixed across years (i.i.d. draws); dependence in
the model is carried by the *frequency* copula, not the severity marginals.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from scipy import stats

from cyberrisk.calibration import SeveritySpec


class SeverityDistribution(Protocol):
    """Protocol for severity RNG / CDF objects."""

    def rvs(self, size: int | tuple[int, ...], random_state: np.random.Generator) -> np.ndarray: ...

    def cdf(self, x: np.ndarray) -> np.ndarray: ...

    def mean(self) -> float: ...


def severity_distributions(
    specs: list[SeveritySpec],
) -> list[SeverityDistribution]:
    """Build scipy severity distributions for the given specs (marginal, i.i.d.)."""
    dists: list[SeverityDistribution] = []
    for spec in specs:
        if spec.model == "lognormal":
            if spec.sigma is None or spec.sigma <= 0.0:
                raise ValueError("sigma > 0 required for lognormal severity")
            dist = stats.lognorm(
                s=spec.sigma,
                scale=spec.scale * np.exp(spec.mu),
            )
        elif spec.model == "gpd":
            dist = stats.genpareto(
                c=spec.xi,
                scale=spec.scale,
                loc=spec.threshold,
            )
        else:  # pragma: no cover - guarded by pydantic Literal
            raise ValueError(f"Unknown severity model: {spec.model!r}")
        dists.append(dist)
    return dists


def rvs_severities(
    dists: list[SeverityDistribution],
    counts: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample per-event severities for each scenario.

    `counts` has shape (n_scenarios, n_years); only the *total* number of
    events per scenario matter for sampling (severities are i.i.d.), so we
    draw all of a scenario's events at once.  Returns a single 1-D array of
    all event severities with a parallel index array `event_lookup` mapping
    each event to its (scenario, year).

    Returns
        severities   float64 array, length == counts.sum()
        event_lookup (n_events, 2) int array, columns [scenario, year]
    """
    total_events = int(counts.sum())
    severities = np.empty(total_events, dtype=np.float64)
    event_lookup = np.empty((total_events, 2), dtype=np.int64)
    cursor = 0

    for i, dist in enumerate(dists):
        n = int(counts[i].sum())
        if n == 0:
            continue
        n_events = n
        draw = np.asarray(dist.rvs(size=n_events, random_state=rng), dtype=np.float64)
        severities[cursor : cursor + n_events] = draw
        # Fill lookup from per-year counts via repeat (keeps event->year order).
        year_of_event = np.repeat(np.arange(counts.shape[1]), counts[i])
        event_lookup[cursor : cursor + n_events, 0] = i
        event_lookup[cursor : cursor + n_events, 1] = year_of_event
        cursor += n_events

    return severities, event_lookup


def draw_severities(
    dists: list[SeverityDistribution],
    counts: np.ndarray,
    rng: np.random.Generator,
) -> list[np.ndarray]:
    """Per-scenario severity draws grouped by scenario: list[np.ndarray] aligned with `counts`.

    Convenience for tests / direct use.  Each element is the array of
    per-event severities for that scenario (length == counts[i].sum()).
    """
    severities = []
    for i, dist in enumerate(dists):
        n = int(counts[i].sum())
        severities.append(
            np.asarray(dist.rvs(size=n, random_state=rng), dtype=np.float64)
        )
    return severities
