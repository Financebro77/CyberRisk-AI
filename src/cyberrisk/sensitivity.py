"""Sensitivity / what-if analysis (Phase 4).

Quantifies which drivers most move EAL / VaR / ES by sweeping one input at
a time around a reference, and produces a tornado ranking for client-facing
explainability.  Pure OAT (one-at-a-time) analysis -- no surrogate model, so
every number traces directly to a simulation run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from cyberrisk.calibration import ModelConfig
from cyberrisk.metrics import compute_metrics
from cyberrisk.simulation import simulate


@dataclass
class TornadoBar:
    """One bar of a tornado chart."""

    label: str
    low: float  # metric value at low input
    base: float  # metric value at reference input
    high: float  # metric value at high input


def sweep_metric(
    metric_fn: Callable[[float], float],
    values: np.ndarray,
    labels: list[str],
) -> list[TornadoBar]:
    """Run `metric_fn` at each input value; package as tornado bars.

    `metric_fn(x)` returns the metric (e.g. EAL) for a given input value.
    `labels` and `values` are parallel; each entry becomes a TornadoBar with
    low/base/high = (min, reference, max) of the sampled metric.
    """
    if len(values) != len(labels):
        raise ValueError("values and labels must be parallel")
    bars = []
    for label, v in zip(labels, values):
        m = metric_fn(float(v))
        if len(np.atleast_1d(m)) == 1:
            low = high = base = float(m)
        else:
            raise ValueError("metric_fn must return a scalar")
        bars.append(TornadoBar(label=label, low=low, base=base, high=high))
    return bars


def lambda_sensitivity(
    config: ModelConfig,
    scenario_keys: list[str],
    n_years: int = 100_000,
    pct: float = 0.5,
    metric: str = "eal",
    seed: int | None = None,
) -> list[TornadoBar]:
    """Sweep each scenario's baseline lambda by +/- `pct` and report metric.

    Returns one TornadoBar per scenario, where low/high are the metric at
    lambda*(1-pct) and lambda*(1+pct).
    """
    base_config = config
    base_metrics = _metric_value(simulate(base_config, n_years=n_years, seed=seed), metric)
    bars = []

    known_keys = {s.key for s in config.scenarios}
    unknown = set(scenario_keys) - known_keys
    if unknown:
        raise KeyError(f"unknown scenario keys: {sorted(unknown)}")

    for key in scenario_keys:
        for idx, s in enumerate(config.scenarios):
            if s.key == key:
                lam = s.frequency.lambda_annual
                for pct_factor, tag in [(1 - pct, "low"), (1 + pct, "high")]:
                    cfg = config.model_copy(
                        update={
                            "scenarios": [
                                sc.model_copy(
                                    update={
                                        "frequency": sc.frequency.model_copy(
                                            update={"lambda_annual": lam * pct_factor}
                                        )
                                    }
                                )
                                if sc.key == key
                                else sc
                                for sc in config.scenarios
                            ]
                        }
                    )
                    m = _metric_value(simulate(cfg, n_years=n_years, seed=seed), metric)
                    if tag == "low":
                        low = m
                    else:
                        high = m
                bars.append(TornadoBar(label=key, low=low, base=base_metrics, high=high))
    return bars


def _metric_value(result, metric: str) -> float:
    m = compute_metrics(result)
    return float(getattr(m, metric))
