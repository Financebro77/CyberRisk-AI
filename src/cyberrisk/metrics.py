"""Risk metrics derived from a simulation run.

For a heavy-tailed annual loss distribution the sample mean and even the
99% quantile are noisy and underestimate the true catastrophe exposure.
Expected Shortfall (mean of the tail above VaR) is the decision-relevant
measure here, and is reported alongside VaR / PML and the full loss
exceedance curve.

All statistics are computed directly from the simulated sample, so they
inherit the sample's seed (see simulation.simulate).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cyberrisk.simulation import SimulationResult


def quantile(losses: np.ndarray, q: float) -> float:
    """Sample quantile of the annual loss distribution (default linear method)."""
    return float(np.quantile(losses, q))


def expected_shortfall(losses: np.ndarray, q: float) -> float:
    """Expected Shortfall (TVaR) at confidence q: mean of losses >= VaR(q)."""
    q = float(q)
    var = quantile(losses, q)
    tail = losses[losses >= var]
    if tail.size == 0:
        return var
    return float(tail.mean())


def exceedance_curve(
    losses: np.ndarray, probabilities: np.ndarray | None = None
) -> np.ndarray:
    """Loss exceedance probabilities P(L >= x) across the sample.

    The x grid defaults to the sorted sample losses.  Returns a (2, len)
    array: row 0 = loss levels, row 1 = exceedance probabilities.
    """
    sorted_losses = np.sort(losses)
    n = losses.size
    exceed = 1.0 - np.arange(1, n + 1) / n
    if probabilities is not None:
        qs = np.asarray(probabilities, dtype=np.float64)
        return np.vstack([quantile(losses, q) for q in qs])
    return np.vstack([sorted_losses, exceed])


@dataclass
class RiskMetrics:
    """Aggregated risk statistics for one simulation run.

    Return-period PML fields (p99_0 / p99_5 / p99_9) are the statistically
    stable PML measures -- a single sample maximum is not a population risk
    measure and must not be reported as a PML (see validation report).
    """

    eal: float  # Expected Annual Loss (mean of total losses)
    var_95: float
    var_99: float
    es_95: float
    es_99: float
    pml_250: float  # 1-in-250-year loss (99.6%)
    p99_0: float  # 1-in-100-year PML (99.0 percentile)
    p99_5: float  # 1-in-200-year PML (99.5 percentile)
    p99_9: float  # 1-in-1000-year PML (99.9 percentile)
    prob_zero_loss: float  # P(no loss year)
    aal_by_scenario: dict[str, float]  # scenario key -> expected annual loss
    max_single_year: float  # sample max (retained for compatibility; NOT a PML)
    scenario_keys: list[str] = field(default_factory=list)

    def scenario_contribution(self) -> dict[str, float]:
        """Fraction of EAL attributable to each scenario (sums to ~1)."""
        total = self.eal
        if total <= 0:
            return {k: 0.0 for k in self.aal_by_scenario}
        return {k: v / total for k, v in self.aal_by_scenario.items()}


@dataclass
class BootstrapSE:
    """Bootstrap standard errors for the headline risk measures.

    Standard errors quantify Monte Carlo noise in the point estimates
    (NOT parameter uncertainty -- that is a separate, Phase 2 concern).
    """

    eal: float
    var_95: float
    var_99: float
    es_95: float
    es_99: float
    p99_5: float  # SE of the 1-in-200 PML
    p99_9: float  # SE of the 1-in-1000 PML


def bootstrap_se(
    losses: np.ndarray,
    n_boot: int = 50,
    rng: np.random.Generator | None = None,
) -> BootstrapSE:
    """Bootstrap standard errors of headline measures from a loss sample.

    Resamples `losses` with replacement `n_boot` times and computes the
    standard deviation of each statistic across resamples.  Heavy-tailed
    annual losses need a sizeable sample to give a stable SE on ES99 / P99.9.
    """
    if losses.ndim != 1 or losses.size < 2:
        raise ValueError("losses must be a 1-D sample")
    rng = np.random.default_rng() if rng is None else rng
    n = losses.size

    eal_s, v95_s, v99_s, es95_s, es99_s, p995_s, p999_s = ([] for _ in range(7))
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        s = losses[idx]
        eal_s.append(s.mean())
        v95_s.append(quantile(s, 0.95))
        v99_s.append(quantile(s, 0.99))
        es95_s.append(expected_shortfall(s, 0.95))
        es99_s.append(expected_shortfall(s, 0.99))
        p995_s.append(quantile(s, 0.995))
        p999_s.append(quantile(s, 0.999))

    return BootstrapSE(
        eal=float(np.std(eal_s)),
        var_95=float(np.std(v95_s)),
        var_99=float(np.std(v99_s)),
        es_95=float(np.std(es95_s)),
        es_99=float(np.std(es99_s)),
        p99_5=float(np.std(p995_s)),
        p99_9=float(np.std(p999_s)),
    )


def compute_metrics(result: SimulationResult) -> RiskMetrics:
    """Compute RiskMetrics from a SimulationResult."""
    losses = result.total_losses
    n = losses.size

    eal = float(losses.mean())
    var_95 = quantile(losses, 0.95)
    var_99 = quantile(losses, 0.99)
    es_95 = expected_shortfall(losses, 0.95)
    es_99 = expected_shortfall(losses, 0.99)
    pml_250 = quantile(losses, 1.0 - 1.0 / 250.0)
    p99_0 = quantile(losses, 0.990)
    p99_5 = quantile(losses, 0.995)
    p99_9 = quantile(losses, 0.999)
    prob_zero = float(np.mean(losses == 0.0))
    max_year = float(losses.max())

    aal_by_scenario = {
        key: float(result.scenario_losses[:, i].mean())
        for i, key in enumerate(result.scenario_keys)
    }

    return RiskMetrics(
        eal=eal,
        var_95=var_95,
        var_99=var_99,
        es_95=es_95,
        es_99=es_99,
        pml_250=pml_250,
        p99_0=p99_0,
        p99_5=p99_5,
        p99_9=p99_9,
        prob_zero_loss=prob_zero,
        aal_by_scenario=aal_by_scenario,
        max_single_year=max_year,
        scenario_keys=list(result.scenario_keys),
    )
