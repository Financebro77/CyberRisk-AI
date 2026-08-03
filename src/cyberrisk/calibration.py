"""Calibration configuration: validated dataclasses + YAML loader.

The YAML config (config/scenarios.yaml) is the single source of truth for
scenario baselines.  pydantic validation turns YAML typos into loud errors
at load time rather than silent NaN at runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

FrequencyModel = Literal["poisson", "negbin"]
SeverityModel = Literal["lognormal", "gpd"]


class FrequencySpec(BaseModel):
    """Annual frequency distribution of events for one scenario.

    The plain-English framing for the CFO:

        "A Poisson pattern is perfectly regular: the variation in how many
        events you get per year equals the average.  A 'bursty' pattern is
        more variable than that -- some years quiet, some years a wave of
        attacks.  `freq_dispersion` is the burstiness: the ratio of the
        variance of the annual count to its mean.  dispersion = 1 is a
        perfectly regular Poisson; dispersion = 2 means the count varies
        twice as much as a regular pattern (a negative binomial)."
    """

    model: FrequencyModel = "poisson"
    lambda_annual: float = Field(gt=0.0, description="Expected number of events per year")
    freq_stddev: float = Field(
        default=0.0, ge=0.0, description="Frequency std dev (NegBin over-dispersion)"
    )
    freq_dispersion: float | None = Field(
        default=None,
        ge=1.0,
        description="Burstiness ratio Var/Mean of the annual count "
        "(1 = Poisson; >1 = negative binomial over-dispersion)",
    )

    @model_validator(mode="after")
    def _validate_model_params(self) -> FrequencySpec:
        if self.model == "negbin":
            if self.freq_stddev <= 0.0 and (self.freq_dispersion is None or self.freq_dispersion <= 1.0):
                raise ValueError(
                    "negbin frequency needs freq_stddev > 0 or freq_dispersion > 1"
                )
        return self


class SeveritySpec(BaseModel):
    """Per-event loss severity distribution for one scenario."""

    model: SeverityModel = "lognormal"
    scale: float = Field(gt=0.0, description="Base loss scale ($), already in absolute terms")
    mu: float = 0.0
    sigma: float | None = Field(
        default=0.0, gt=0.0, description="Log-return volatility (tail heaviness); lognormal only"
    )
    threshold: float = Field(
        default=0.0, ge=0.0, description="GPD location: only payouts above this attach"
    )
    xi: float = Field(default=0.0, description="GPD tail index")


    @model_validator(mode="after")
    def _sigma_required_only_for_lognormal(self) -> SeveritySpec:
        if self.model == "lognormal" and (self.sigma is None or self.sigma <= 0.0):
            raise ValueError("sigma > 0 is required for lognormal severity")
        if self.model == "gpd" and self.xi >= 1.0:
            raise ValueError("GPD tail index xi must be < 1 for finite mean")
        return self


class Scenario(BaseModel):
    """One named cyber scenario."""

    name: str
    key: str
    frequency: FrequencySpec
    severity: SeveritySpec
    copula_loading: float = Field(default=0.0, ge=-1.0, le=1.0)
    revenue_exponent: float = Field(default=0.0, ge=0.0, description="Elasticity of severity scale to revenue")
    annotation: dict[str, str] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    """Full validated model configuration."""

    firm_revenue_usd: float = Field(gt=0.0)
    revenue_reference_usd: float = Field(default=1_000_000_000.0, gt=0.0)
    scenarios: list[Scenario]
    default_years: int = Field(default=100_000, ge=1_000)
    chunk_size: int = Field(default=20_000, ge=1_000)
    seed: int = Field(default=20240817)
    tail_quantile: float = Field(default=0.99, gt=0.5, lt=1.0)
    copula_model: Literal["gaussian", "student_t"] = Field(
        default="gaussian",
        description="Dependence model: gaussian (no tail dependence) or student_t (tail dependence)",
    )
    copula_nu: float = Field(
        default=5.0,
        gt=2.0,
        description="Student-t copula degrees of freedom (nu->inf recovers Gaussian)",
    )
    event_clustering_enabled: bool = Field(
        default=False,
        description="Whether to model 'catastrophe years' (Phase 3). "
        "When True, a small fraction of years carry a loss-multiplier to "
        "capture coordinated attacks / campaigns that inflate ALL losses "
        "in the same year.",
    )
    catastrophe_probability: float = Field(
        default=0.05,
        ge=0.0,
        le=0.5,
        description="Probability that any given year is a 'catastrophe year' "
        "(5% = roughly one year in twenty).",
    )
    catastrophe_multiplier_mean: float = Field(
        default=2.0,
        gt=1.0,
        description="Expected loss multiplier in a catastrophe year "
        "(2.0 = everything that happens costs ~2x).",
    )
    catastrophe_multiplier_cv: float = Field(
        default=0.5,
        ge=0.0,
        description="Uncertainty on the catastrophe multiplier (coefficient of "
        "variation).  Higher = wider range of how bad a catastrophe year gets.",
    )

    @model_validator(mode="after")
    def _check_unique_scenario_keys(self) -> ModelConfig:
        keys = [s.key for s in self.scenarios]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate scenario keys: {keys}")
        return self

    @property
    def scenario_keys(self) -> list[str]:
        return [s.key for s in self.scenarios]

    def resolve_severity_scale(self, scenario: Scenario, revenue: float | None = None) -> float:
        """Scale scenario severity to firm revenue via revenue_exponent.

        severity_scale in config is absolute (baseline calibrated at
        revenue_reference_usd); applying the revenue elasticity yields the
        effective per-event severity for this firm.
        """
        revenue = self.firm_revenue_usd if revenue is None else revenue
        factor = (revenue / self.revenue_reference_usd) ** scenario.revenue_exponent
        return scenario.severity.scale * factor


def apply_benchmarks(
    config: ModelConfig,
    benchmarks: "BenchmarkSet",
    sector: str = "All",
) -> ModelConfig:
    """Translate benchmark metrics into scenario lambdas.

    For each scenario, look up a frequency benchmark (metric = the scenario
    key + "_frequency") in the benchmark set, restricted to the given
    `sector` (fall back to "All").  If found, override that scenario's
    lambda_annual.  Severity parameters are left to the scenario config
    (they come from the claims layer / severity benchmarks, applied via
    calibration_benchmarks.csv).

    Returns a NEW ModelConfig (the input config is not mutated), so the
    calibration is reproducible from the benchmark set alone.
    """
    new_scenarios = []
    for s in config.scenarios:
        lam = s.frequency.lambda_annual
        for rec in benchmarks.filter(metric=f"{s.key}_frequency"):
            if rec.sector == sector or (rec.sector == "All" and sector != "All"):
                lam = rec.value
                break
        new_scenarios.append(
            s.model_copy(
                update={
                    "frequency": s.frequency.model_copy(update={"lambda_annual": lam}),
                    "annotation": {
                        **s.annotation,
                        "calibrated_lambda_from": f"{benchmarks.records[0].source if benchmarks.records else 'benchmark'} ({sector})",
                        "calibrated_lambda": str(lam),
                    },
                }
            )
        )
    return config.model_copy(update={"scenarios": new_scenarios})


def load_config(
    path: str | Path | None = None,
    simulation_config_path: str | Path | None = None,
) -> ModelConfig:
    """Load and validate the scenario configuration.

    Parameters
        path                    path to scenarios.yaml (defaults to
                                <repo>/config/scenarios.yaml)
        simulation_config_path  path to simulation_config.yaml (defaults to
                                <repo>/config/simulation_config.yaml).  Simulation
                                knobs are loaded from this separate file when
                                provided; otherwise they fall back to defaults.
    """
    path = _resolve_config("scenarios.yaml", path)
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    sim = {}
    if simulation_config_path is None:
        # Fall back to the legacy inline simulation block if present.
        sim = raw.get("simulation", {})
    else:
        sim_path = _resolve_config("simulation_config.yaml", simulation_config_path)
        sim = yaml.safe_load(Path(sim_path).read_text(encoding="utf-8"))

    scenarios: list[Scenario] = []
    for key, spec in raw["scenarios"].items():
        freq = spec.get("frequency_model", "poisson")
        severity = spec.get("severity_model", "lognormal")
        scenarios.append(
            Scenario(
                key=key,
                name=spec["name"],
                frequency=FrequencySpec(
                    model=freq,
                    lambda_annual=spec["lambda_annual"],
                    freq_stddev=spec.get("freq_stddev", 0.0),
                    freq_dispersion=spec.get("freq_dispersion"),
                ),
                severity=SeveritySpec(
                    model=severity,
                    scale=spec["severity_scale"],
                    mu=spec.get("severity_mu", 0.0),
                    sigma=spec["severity_sigma"],
                    threshold=spec.get("severity_threshold", 0.0),
                    xi=spec.get("severity_xi", 0.0),
                ),
                copula_loading=spec.get("copula_loading", 0.0),
                revenue_exponent=spec.get("revenue_exponent", 0.0),
                annotation=spec.get("annotation", {}),
            )
        )

    return ModelConfig(
        firm_revenue_usd=raw.get("firm_revenue_usd", 1_000_000_000.0),
        revenue_reference_usd=raw.get("revenue_reference_usd", 1_000_000_000.0),
        scenarios=scenarios,
        default_years=sim.get("default_years", 100_000),
        chunk_size=sim.get("chunk_size", 20_000),
        seed=sim.get("seed", 20240817),
        tail_quantile=sim.get("tail_quantile", 0.99),
        copula_model=sim.get("copula_model", "gaussian"),
        copula_nu=sim.get("copula_nu", 5.0),
        event_clustering_enabled=sim.get("event_clustering_enabled", False),
        catastrophe_probability=sim.get("catastrophe_probability", 0.05),
        catastrophe_multiplier_mean=sim.get("catastrophe_multiplier_mean", 2.0),
        catastrophe_multiplier_cv=sim.get("catastrophe_multiplier_cv", 0.5),
    )


def load_simulation_config(path: str | Path | None = None) -> dict[str, int | float]:
    """Load just the simulation knobs from simulation_config.yaml.

    Returns a plain dict with keys default_years / chunk_size / seed /
    tail_quantile, so callers can read engine settings without pulling the
    full scenario calibration.
    """
    sim_path = _resolve_config("simulation_config.yaml", path)
    return yaml.safe_load(Path(sim_path).read_text(encoding="utf-8"))


def _resolve_config(filename: str, path: str | Path | None) -> Path:
    """Default config paths relative to the package repo root."""
    if path is not None:
        return Path(path)
    # package parent is <repo>/src/cyberrisk -> <repo>/config
    return Path(__file__).resolve().parent.parent.parent / "config" / filename
