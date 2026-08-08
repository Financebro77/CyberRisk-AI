"""Parameter uncertainty analysis.

The consultant-facing story, in plain English:

    "Any model is only as good as its assumptions.  We don't know the exact
    breach rate for a company like yours, and we don't know exactly how
    heavy the bad tail is.  So instead of giving you one number, we vary
    each assumption within a plausible range, re-run the model a couple of
    hundred times, and give you a middle estimate and a 90% band.

    Think of it like an engineer's tolerance: the central figure is our best
    estimate, and the band shows how much it could move if the assumptions
    are a bit off."

Implementation: each simulation run draws its scenario lambdas, severity
scales and tail weights, and copula parameters from random perturbations
of the base config, then runs the full loss engine.  Across all runs we
collect each risk measure and report its median and the 5th/95th percentiles
(the 90% band).  The result is a small table a CFO can read at a glance.

This deliberately does NOT use full Bayesian machinery or MCMC -- the goal
is an explainable tolerance band, not a posterior distribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from pydantic import BaseModel, Field, model_validator

from cyberrisk.calibration import ModelConfig
from cyberrisk.metrics import compute_metrics
from cyberrisk.simulation import simulate


class UncertaintySpec(BaseModel):
    """Uncertainty parameters (see config/uncertainty_config.yaml)."""

    iterations: int = Field(default=200, ge=2)
    seed: int = 20250201
    lambda_cv: float = Field(default=0.30, ge=0.0)
    severity_scale_cv: float = Field(default=0.30, ge=0.0)
    severity_sigma_cv: float = Field(default=0.15, ge=0.0)
    loading_sd: float = Field(default=0.10, ge=0.0)
    copula_nu_sd: float = Field(default=1.0, ge=0.0)

    @model_validator(mode="after")
    def _no_extreme_spread(self) -> UncertaintySpec:
        for name in ("lambda_cv", "severity_scale_cv", "severity_sigma_cv"):
            if getattr(self, name) > 0.9:
                raise ValueError(f"{name} > 0.9 is implausibly large")
        return self


def load_uncertainty_spec(path: str | Path | None = None) -> UncertaintySpec:
    """Load the uncertainty spec from YAML (defaults to config/uncertainty_config.yaml)."""
    if path is None:
        path = Path(__file__).resolve().parent.parent.parent / "config" / "uncertainty_config.yaml"
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return UncertaintySpec(**raw)


def _perturb_config(
    config: ModelConfig,
    rng: np.random.Generator,
    spec: UncertaintySpec,
) -> ModelConfig:
    """Draw one perturbed copy of the config.

    Each scenario's lambda is multiplied by log-normal(0, lambda_cv);
    severity scale likewise; sigma by log-normal(0, sigma_cv) clamped to
    stay positive and reasonable; copula loadings get additive normal noise
    clipped to [-0.95, 0.95]; Student-t nu gets additive normal noise
    clipped to >= 3.
    """
    scenarios = []
    for s in config.scenarios:
        lam = s.frequency.lambda_annual * float(np.exp(spec.lambda_cv * rng.standard_normal()))
        scale = s.severity.scale * float(np.exp(spec.severity_scale_cv * rng.standard_normal()))
        sigma = s.severity.sigma
        if sigma is not None:
            sigma = float(sigma * np.exp(spec.severity_sigma_cv * rng.standard_normal()))
            sigma = max(sigma, 0.05)
        loading = float(np.clip(s.copula_loading + spec.loading_sd * rng.standard_normal(), -0.95, 0.95))

        scenarios.append(
            s.model_copy(
                update={
                    "frequency": s.frequency.model_copy(update={"lambda_annual": lam}),
                    "severity": s.severity.model_copy(
                        update={"scale": scale, "sigma": sigma}
                    ),
                    "copula_loading": loading,
                }
            )
        )

    nu = config.copula_nu
    if spec.copula_nu_sd > 0:
        nu = float(np.clip(nu + spec.copula_nu_sd * rng.standard_normal(), 3.0, 30.0))

    return config.model_copy(update={"scenarios": scenarios, "copula_nu": nu})


@dataclass
class UncertaintyBand:
    """90% band for one risk measure across perturbed runs."""

    median: float
    p5: float
    p95: float
    metric: str = ""

    @property
    def width(self) -> float:
        """Absolute band width (p95 - p5)."""
        return self.p95 - self.p5

    def describe(self) -> str:
        """One-line summary: 'median (p5 - p95)'.

        Uses a precision that suits the value: 3 decimals for lambdas (which
        are small rates), integer USD for large loss figures.
        """
        if self.median < 100:
            return f"{self.median:.3f} ({self.p5:.3f} - {self.p95:.3f})"
        return f"{self.median:,.0f} ({self.p5:,.0f} - {self.p95:,.0f})"


@dataclass
class UncertaintyResult:
    """Full output of an uncertainty analysis."""

    spec: UncertaintySpec
    base_config: ModelConfig
    n_runs: int
    # metric name -> UncertaintyBand
    bands: dict[str, UncertaintyBand] = field(default_factory=dict)
    # per-scenario lambda median + 90% band (to show where the spread comes from)
    lambda_bands: dict[str, UncertaintyBand] = field(default_factory=dict)
    # per-scenario sigma band (the tail-weight driver)
    sigma_bands: dict[str, UncertaintyBand] = field(default_factory=dict)


_METRICS = ("eal", "var_95", "var_99", "es_95", "es_99", "p99_0", "p99_5", "p99_9")


def run_uncertainty_analysis(
    config: ModelConfig,
    spec: UncertaintySpec | None = None,
    n_years: int | None = None,
    seed: int | None = None,
    quiet: bool = False,
) -> UncertaintyResult:
    """Run `spec.iterations` perturbed simulations and build 90% bands.

    Parameters
        config    base model config (already credibility-adjusted if desired)
        spec      uncertainty spec (defaults to config/uncertainty_config.yaml)
        n_years   years per simulation run (default config.default_years)
        seed      override the spec seed (reproducibility)
        quiet     suppress per-run progress output

    Returns
        UncertaintyResult with per-metric 90% bands and per-scenario
        lambda/sigma bands.  The median of each band is the "central
        estimate" for reporting; the 5th/95th percentiles are the band.
    """
    if spec is None:
        spec = load_uncertainty_spec()
    if seed is not None:
        spec = spec.model_copy(update={"seed": seed})

    rng = np.random.default_rng(spec.seed)
    n_years = config.default_years if n_years is None else n_years

    # Collect raw values across runs, one list per metric.
    cols: dict[str, list[float]] = {m: [] for m in _METRICS}
    lambda_cols: dict[str, list[float]] = {s.key: [] for s in config.scenarios}
    sigma_cols: dict[str, list[float]] = {s.key: [] for s in config.scenarios}

    for it in range(spec.iterations):
        perturbed = _perturb_config(config, rng, spec)
        result = simulate(perturbed, n_years=n_years, dependence="dependent")
        m = compute_metrics(result)
        for metric in _METRICS:
            cols[metric].append(float(getattr(m, metric)))
        for s in perturbed.scenarios:
            lambda_cols[s.key].append(s.frequency.lambda_annual)
            if s.severity.sigma is not None:
                sigma_cols[s.key].append(float(s.severity.sigma))
        if not quiet and (it + 1) % 50 == 0:
            print(f"  uncertainty run {it+1}/{spec.iterations}")

    def band(metric: str) -> UncertaintyBand:
        arr = np.asarray(cols[metric])
        return UncertaintyBand(
            median=float(np.median(arr)),
            p5=float(np.percentile(arr, 5)),
            p95=float(np.percentile(arr, 95)),
            metric=metric,
        )

    return UncertaintyResult(
        spec=spec,
        base_config=config,
        n_runs=spec.iterations,
        bands={m: band(m) for m in _METRICS},
        lambda_bands={
            key: UncertaintyBand(
                median=float(np.median(np.asarray(v))),
                p5=float(np.percentile(v, 5)),
                p95=float(np.percentile(v, 95)),
                metric=f"lambda_{key}",
            )
            for key, v in lambda_cols.items()
        },
        sigma_bands={
            key: UncertaintyBand(
                median=float(np.median(np.asarray(v))),
                p5=float(np.percentile(v, 5)),
                p95=float(np.percentile(v, 95)),
                metric=f"sigma_{key}",
            )
            for key, v in sigma_cols.items()
        },
    )


def central_estimate(result: UncertaintyResult, metric: str) -> float:
    """The central (median) value of a metric across the uncertainty runs."""
    return float(result.bands[metric].median)
