"""Monte Carlo simulation engine.

Simulates many independent years of cyber loss.  Each year:

    1. Draw a (n_scenarios,) vector of copula-coupled uniforms from the
       one-factor Gaussian copula.
    2. Inverse-transform each scenario's uniform to its count distribution
       PPF -> annual event count per scenario.
    3. Draw per-event severities for the events that occurred.
    4. Aggregate each scenario's events into an annual loss per scenario,
       then across scenarios into the annual aggregate total loss.

Per-event (occurrence) simulation is deliberate: Phase 3 (insurance
structuring) applies policy terms -- deductibles, occurrence limits,
aggregate limits -- to individual simulated events before aggregation.
Aggregating first and applying policy terms afterwards is a common and
wrong shortcut.

Reproducibility & chunk independence: ALL randomness is consumed in a
single deterministic pass driven by the root seed --

    * the copula uniforms are drawn once for all years from the root
      Generator, then
    * per-scenario severities are drawn from a dedicated Generator seeded
      by ``SeedSequence([root_seed, scenario_index])``.

The per-scenario event count (hence how many severities are drawn) is
itself deterministic given the uniforms.  Aggregation is pure arithmetic
and is streamed over fixed-size chunks purely to bound peak memory.  The
result is therefore bit-for-bit identical for any chunk_size and any
decomposition of the year range -- results do not depend on how the work
was chunked, which matters when the same model runs on different machines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from cyberrisk.calibration import ModelConfig
from cyberrisk.copulas import (
    build_loadings,
    copula_uniforms,
    independent_uniforms,
)
from cyberrisk.frequency import count_distributions, rvs_counts
from cyberrisk.severity import severity_distributions

DependenceMode = Literal["dependent", "independent"]

# Score -> frequency link.  A company with composite score `score` gets its
# scenario baselines scaled by exp(k_scenario * (score - score_reference)/100).
# score_reference = 50 (the config default when no profile supplied), so a
# firm scored 50 keeps baseline lambdas unchanged, a score > 50 raises them,
# and a score < 50 lowers them.  k_scenario is a per-scenario elasticity
# (default 1.0) and is the Phase 2 calibration lever.
SCORE_REFERENCE = 50.0


def score_scaled_lambdas(
    config: ModelConfig,
    score: float | None,
    k: float | np.ndarray | None = None,
) -> np.ndarray:
    """Scenario baseline lambdas scaled by a firm's composite risk score.

    lambda_scaled = lambda_baseline * exp(k_scenario * (score - SCORE_REFERENCE)/100)

    k defaults to 1.0 for all scenarios.  Pass an array to vary elasticity
    per scenario (e.g. ransomware more sensitive to score than BEC).
    Returns a float64 array aligned with config.scenarios.
    """
    lambdas = np.array(
        [s.frequency.lambda_annual for s in config.scenarios], dtype=np.float64
    )
    if score is None:
        return lambdas

    if k is None:
        k_arr = np.ones(len(config.scenarios), dtype=np.float64)
    elif np.isscalar(k):
        k_arr = np.full(len(config.scenarios), float(k), dtype=np.float64)
    else:
        k_arr = np.asarray(k, dtype=np.float64)
        if k_arr.shape != (len(config.scenarios),):
            raise ValueError(
                f"k must be scalar or shape ({len(config.scenarios)},), got {k_arr.shape}"
            )

    factor = np.exp(k_arr * (float(score) - SCORE_REFERENCE) / 100.0)
    return lambdas * factor


def _freq_specs_with_lambdas(
    config: ModelConfig, scenario_lambdas: np.ndarray | None
) -> list:
    """Frequency specs for the engine, optionally with overridden lambdas.

    Builds frequency specs from config, replacing lambda_annual with the
    score-scaled values when `scenario_lambdas` is provided.  Used by
    `simulate` so a scored profile scales frequencies without mutating the
    (shared, validated) config.
    """
    specs = [s.frequency for s in config.scenarios]
    if scenario_lambdas is None:
        return specs
    out = []
    for spec, lam in zip(specs, np.atleast_1d(scenario_lambdas)):
        out.append(spec.model_copy(update={"lambda_annual": float(lam)}))
    return out


@dataclass
class SimulationResult:
    """One simulation run.

    Attributes
        config          The ModelConfig this run used.
        years           int, number of simulated years.
        total_losses    (n_years,) annual aggregate loss across all scenarios.
        scenario_losses (n_years, n_scenarios) annual loss per scenario.
        events          (n_events, 3) float64 rows [scenario, year, severity],
                        or None when `return_events=False`.
        scenario_keys   list[str] scenario key order for the columns.
    """

    config: ModelConfig
    years: int
    total_losses: np.ndarray
    scenario_losses: np.ndarray
    events: np.ndarray | None
    scenario_keys: list[str]

    def scenario_aal(self) -> np.ndarray:
        """Per-scenario expected annual loss (AAL) from this run."""
        return self.scenario_losses.mean(axis=0)


def _per_scenario_rng(root_seed: int, scenario_index: int) -> np.random.Generator:
    """Deterministic, chunk-independent Generator per (seed, scenario)."""
    ss = np.random.SeedSequence([root_seed, scenario_index])
    return np.random.default_rng(ss)


def _catastrophe_factors(
    n_years: int,
    root_seed: int,
    prob: float,
    mean: float,
    cv: float,
) -> np.ndarray:
    """Per-year catastrophe multipliers (1.0 in ordinary years, >1 in catastrophe years).

    Plain-English model: "roughly one year in N, several things go wrong at
    once and everything costs more."  Each year is a catastrophe year with
    probability `prob`; in those years the loss multiplier is a log-normal
    with mean `mean` and coefficient of variation `cv`.

    Uses a dedicated seed stream (SeedSequence([root_seed, 424242])) so the
    factors are chunk-independent and reproducible, exactly like the
    per-scenario severity streams.
    """
    rng = np.random.default_rng(np.random.SeedSequence([root_seed, 424242]))
    is_cat = rng.random(n_years) < prob
    # log-normal with given mean and CV: sigma^2 = ln(1 + cv^2), mu = ln(mean) - 0.5*sigma^2
    sigma = float(np.sqrt(np.log(1.0 + cv * cv)))
    mu = float(np.log(mean) - 0.5 * sigma * sigma)
    factors = np.ones(n_years, dtype=np.float64)
    n_cat = int(is_cat.sum())
    if n_cat > 0:
        # Clamp to >= 1: a "catastrophe" year must never make things CHEAPER.
        # A log-normal with a large CV can draw below 1.0; that would contradict
        # the plain-English story ("everything costs more in a catastrophe year").
        factors[is_cat] = np.maximum(np.exp(mu + sigma * rng.standard_normal(n_cat)), 1.0)
    return factors


def simulate(
    config: ModelConfig,
    n_years: int | None = None,
    seed: int | None = None,
    dependence: DependenceMode = "dependent",
    return_events: bool = False,
    score: float | None = None,
    score_k: float | np.ndarray | None = None,
    scenario_lambdas: np.ndarray | None = None,
    copula_model: str | None = None,
    copula_nu: float | None = None,
) -> SimulationResult:
    """Run the annual loss simulation.

    Parameters
        config            validated model configuration
        n_years           number of simulated years (default config.default_years)
        seed              optional override of config.seed for the root RNG
        dependence        "dependent" uses the configured copula (gaussian or
                          student_t); "independent" forces zero loadings
        return_events     also return the per-event table (scenario, year, severity)
        score             optional composite risk score (0-100) that scales
                          baseline frequencies via the log-linear link
        score_k           per-scenario elasticity for the score link (scalar or
                          length-n_scenarios array); default 1.0
        scenario_lambdas  explicit lambda overrides (takes precedence over score);
                          length-n_scenarios float array
        copula_model      override config.copula_model ("gaussian"|"student_t")
        copula_nu         override config.copula_nu (Student-t d.o.f.)
    """
    n_years = config.default_years if n_years is None else int(n_years)
    if n_years < 1:
        raise ValueError("n_years must be >= 1")

    loadings = build_loadings(config)
    if dependence == "independent":
        loadings = np.zeros_like(loadings)

    model = config.copula_model if copula_model is None else copula_model
    nu = config.copula_nu if copula_nu is None else copula_nu

    if scenario_lambdas is not None:
        effective_lambdas = np.atleast_1d(scenario_lambdas)
    elif score is not None:
        effective_lambdas = score_scaled_lambdas(config, score, score_k)
    else:
        effective_lambdas = None

    freq_specs = _freq_specs_with_lambdas(config, effective_lambdas)
    count_dists, _, _ = count_distributions(freq_specs)
    sev_dists = severity_distributions([s.severity for s in config.scenarios])
    # Revenue-scaled per-scenario severity multipliers (fold in the revenue exponent).
    scale_factors = np.array(
        [
            config.resolve_severity_scale(s) / s.severity.scale
            for s in config.scenarios
        ],
        dtype=np.float64,
    )

    root_seed = config.seed if seed is None else int(seed)

    # ---- Phase 1 (random, single deterministic pass) ------------------------
    root_rng = np.random.default_rng(root_seed)
    if dependence == "independent":
        uniforms = independent_uniforms(loadings, n_years, root_rng)
    elif model == "student_t":
        uniforms = copula_uniforms(loadings, n_years, root_rng, model="student_t", nu=nu)
    else:
        uniforms = copula_uniforms(loadings, n_years, root_rng, model="gaussian")
    counts = rvs_counts(count_dists, uniforms, root_rng)  # PPF: deterministic in uniforms

    # Event clustering: per-year catastrophe multipliers (1.0 ordinary, >1 catastrophe).
    clustering_on = (
        config.event_clustering_enabled and config.catastrophe_multiplier_mean > 1.0
    )
    cat_factors = (
        _catastrophe_factors(
            n_years,
            root_seed,
            config.catastrophe_probability,
            config.catastrophe_multiplier_mean,
            config.catastrophe_multiplier_cv,
        )
        if clustering_on
        else np.ones(n_years, dtype=np.float64)
    )

    n_scenarios = len(config.scenarios)
    scenario_losses = np.zeros((n_years, n_scenarios), dtype=np.float64)
    event_rows: list[np.ndarray] = []

    for i in range(n_scenarios):
        n_events = int(counts[i].sum())
        if n_events == 0:
            continue
        sev_rng = _per_scenario_rng(root_seed, i)
        sev_i = np.asarray(
            sev_dists[i].rvs(size=n_events, random_state=sev_rng), dtype=np.float64
        ) * scale_factors[i]
        year_i = np.repeat(np.arange(n_years), counts[i])

        # Apply the per-year catastrophe multiplier to each event's severity.
        sev_i = sev_i * cat_factors[year_i]

        col = np.zeros(n_years, dtype=np.float64)
        np.add.at(col, year_i, sev_i)
        scenario_losses[:, i] = col

        if return_events:
            scenario_idx = np.full(n_events, i, dtype=np.int64)
            event_rows.append(np.column_stack([scenario_idx, year_i, sev_i]))

    total_losses = scenario_losses.sum(axis=1)

    # ---- Phase 2 (aggregation, streamed in chunks to bound peak memory) ------
    # total_losses / scenario_losses are already materialised; chunking here is
    # a no-op for Phase 1.  Kept as the seam where a fully streaming path (much
    # larger n_years) can be introduced without changing the public contract.

    events = np.vstack(event_rows) if return_events else None

    return SimulationResult(
        config=config,
        years=n_years,
        total_losses=total_losses,
        scenario_losses=scenario_losses,
        events=events,
        scenario_keys=config.scenario_keys,
    )
