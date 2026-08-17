"""Benchmark scenario framework for the Armageddon model.

Acts as a Marsh/Aon consultant QA harness: defines synthetic client
profiles spanning the risk spectrum, runs each through the full pipeline
(score -> simulation -> metrics), and checks the output against the
consultant's EXPECTED outcome.

The story: "we ran five representative clients through the model -- a
low-risk manufacturer, a mid-market retailer, a high-exposure hospital,
a data-rich financial firm, and a weakly-controlled small business.  The
model should rank them in a sensible order and the losses should scale
with the risk."

Each profile supplies qualitative security-control RATINGS (e.g. "mature",
"extensive") rather than raw 0-100 numbers, because that is how a client
actually answers.  The ratings are mapped to scores through the configured
evidence scales, keeping the whole thing explainable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from cyberrisk.calibration import ModelConfig, load_config
from cyberrisk.metrics import RiskMetrics, compute_metrics
from cyberrisk.scoring import CompanyProfile, ScoringWeights, compute_score, load_scoring_weights
from cyberrisk.simulation import SimulationResult, simulate

DEFAULT_YAML = Path(__file__).resolve().parent.parent.parent / "config" / "benchmark_profiles.yaml"


class BenchmarkProfile(BaseModel):
    """One synthetic client, defined the way a consultant would describe it."""

    name: str
    industry: str
    revenue_usd: float = Field(gt=0.0)
    data_exposure: str = Field(description="e.g. 'low', 'moderate', 'high', 'critical'")
    controls: dict[str, str] = Field(
        description="factor key -> qualitative rating (mapped through evidence scales)"
    )
    # Consultant's EXPECTED outcomes (used to validate the model).
    expected_category: str = ""
    expected_score_min: float = Field(default=0.0, ge=0.0, le=100.0)
    expected_score_max: float = Field(default=100.0, ge=0.0, le=100.0)
    expected_loss_note: str = ""
    notes: str = ""

    @property
    def key(self) -> str:
        """Stable short key (snake-case of the name) for reporting."""
        return "_".join(self.name.lower().split())


@dataclass
class BenchmarkResult:
    """Full outcome of running one profile through the model."""

    profile: BenchmarkProfile
    scored: object  # ScoredFirm
    metrics: RiskMetrics
    result: SimulationResult

    @property
    def risk_score(self) -> float:
        return self.scored.composite_score

    @property
    def risk_category(self) -> str:
        return self.scored.risk_category

    @property
    def eal(self) -> float:
        return self.metrics.eal

    @property
    def es_99(self) -> float:
        return self.metrics.es_99

    @property
    def p99_9(self) -> float:
        return self.metrics.p99_9

    def score_ok(self) -> bool:
        """Score falls within the consultant's expected range."""
        return self.profile.expected_score_min <= self.risk_score <= self.profile.expected_score_max

    def category_ok(self) -> bool:
        """Category matches the consultant's expectation (if set)."""
        return not self.profile.expected_category or self.risk_category == self.profile.expected_category

    def checks_passed(self) -> bool:
        return self.score_ok() and self.category_ok()


def _rating_to_score(weights: ScoringWeights, factor_key: str, rating: str) -> float:
    """Map a qualitative rating (e.g. 'mature') to a 0-100 score via the evidence scale."""
    for domain in weights.domains:
        for factor in domain.factors:
            if factor.key == factor_key:
                if rating not in factor.evidence_scale:
                    valid = ", ".join(factor.evidence_scale)
                    raise ValueError(
                        f"unknown rating {rating!r} for factor {factor_key!r}; "
                        f"valid: {valid}"
                    )
                return float(factor.evidence_scale[rating])
    raise ValueError(f"unknown factor key {factor_key!r}")


def load_benchmark_profiles(path: str | Path | None = None) -> list[BenchmarkProfile]:
    """Load benchmark profiles from YAML (defaults to config/benchmark_profiles.yaml)."""
    path = Path(path) if path is not None else DEFAULT_YAML
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [BenchmarkProfile(**p) for p in raw["profiles"]]


def run_profile(
    profile: BenchmarkProfile,
    config: ModelConfig,
    weights: ScoringWeights | None = None,
    n_years: int | None = None,
    seed: int | None = None,
) -> BenchmarkResult:
    """Run one profile through scoring -> simulation -> metrics.

    The control ratings are mapped to factor scores, the composite is
    computed, then a score-driven simulation is run and metrics collected.
    """
    if weights is None:
        weights = load_scoring_weights()
    n_years = config.default_years if n_years is None else n_years

    factor_scores = {
        key: _rating_to_score(weights, key, rating)
        for key, rating in profile.controls.items()
    }
    company = CompanyProfile(
        firm_name=profile.name,
        revenue_usd=profile.revenue_usd,
        factor_scores=factor_scores,
    )
    scored = compute_score(company, weights)
    sim = simulate(config, n_years=n_years, score=scored.composite_score, seed=seed)
    metrics = compute_metrics(sim)
    return BenchmarkResult(profile=profile, scored=scored, metrics=metrics, result=sim)


def run_benchmarks(
    profiles: list[BenchmarkProfile] | None = None,
    config: ModelConfig | None = None,
    weights: ScoringWeights | None = None,
    n_years: int | None = None,
    seed: int | None = None,
) -> list[BenchmarkResult]:
    """Run all benchmark profiles and return the results list."""
    if profiles is None:
        profiles = load_benchmark_profiles()
    if config is None:
        repo = Path(__file__).resolve().parent.parent.parent
        config = load_config(
            repo / "config" / "scenarios.yaml",
            repo / "config" / "simulation_config.yaml",
        )
    return [
        run_profile(p, config, weights=weights, n_years=n_years, seed=seed)
        for p in profiles
    ]


def evaluate_results(results: list[BenchmarkResult]) -> list[str]:
    """Run the QA checks and return a list of PASS/FAIL lines."""
    out: list[str] = []
    for r in results:
        score_ok = r.score_ok()
        cat_ok = r.category_ok()
        ok = score_ok and cat_ok
        line = (
            f"{r.profile.name:<34} score={r.risk_score:6.1f} "
            f"[{r.profile.expected_score_min:.0f}-{r.profile.expected_score_max:.0f}] "
            f"cat={r.risk_category:<8} expected={r.profile.expected_category:<8} "
            f"EAL=${r.eal/1e6:6.2f}M -> {'PASS' if ok else 'FAIL'}"
        )
        out.append(line)
        if not score_ok:
            out.append(f"    !! score {r.risk_score:.1f} outside expected range")
        if not cat_ok:
            out.append(f"    !! category {r.risk_category} != expected {r.profile.expected_category}")
    return out
