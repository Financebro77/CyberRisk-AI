"""Cyber risk scoring engine.

Implements the configurable weighted-factor model:

    domain_score   = weighted mean of its factor scores
    composite      = sum(domain_weight * domain_score)     (weights sum to 1)
    risk_category  = band lookup on the composite score
    risk_drivers   = the factors whose score most exceeds their domain
                     average (i.e. where risk is concentrated)

The whole model is driven by config/scoring_weights.yaml -- changing the
weights, evidence scales, or category bands requires no code change.  A
higher score means HIGHER risk (0 = minimal, 100 = critical).

Phase 2 (scoring) is deliberately independent of Phase 1 (loss engine):
it produces a `ScoredFirm` (composite + category + drivers + factor
breakdown) that the simulation layer can later consume through a log-linear
frequency link (see simulation.py: score_scaled_lambdas).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class FactorSpec(BaseModel):
    key: str
    name: str
    weight: float = Field(gt=0.0)
    evidence_scale: dict[str, float] = Field(description="rating -> 0-100 score")

    @model_validator(mode="after")
    def _validate_evidence(self) -> FactorSpec:
        if not self.evidence_scale:
            raise ValueError(f"factor '{self.key}' needs a non-empty evidence_scale")
        for rating, score in self.evidence_scale.items():
            if not 0.0 <= score <= 100.0:
                raise ValueError(f"evidence score for {rating!r} out of [0,100]")
        return self


class DomainSpec(BaseModel):
    key: str
    name: str
    weight: float = Field(gt=0.0)
    factors: list[FactorSpec]

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> DomainSpec:
        total = sum(f.weight for f in self.factors)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"domain '{self.key}' factor weights sum to {total}, not 1")
        return self

    @model_validator(mode="after")
    def _unique_factor_keys(self) -> DomainSpec:
        keys = [f.key for f in self.factors]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate factor keys in domain '{self.key}': {keys}")
        return self


class ScoringWeights(BaseModel):
    category_bands: list[dict[str, float | str]] = Field(description="max_score -> category")
    domains: list[DomainSpec]

    @model_validator(mode="after")
    def _domain_weights_sum_to_one(self) -> ScoringWeights:
        total = sum(d.weight for d in self.domains)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"domain weights sum to {total}, not 1")
        return self

    @model_validator(mode="after")
    def _category_bands_ordered(self) -> ScoringWeights:
        bands = [b["max_score"] for b in self.category_bands]
        if bands != sorted(bands):
            raise ValueError("category_bands must be sorted ascending by max_score")
        if bands[0] <= 0 or bands[-1] != 100:
            raise ValueError("category_bands must start >0 and end at 100")
        return self

    @property
    def domain_keys(self) -> list[str]:
        return [d.key for d in self.domains]

    def category_for_score(self, score: float) -> str:
        """Map a composite 0-100 score to a risk category (Low/Medium/High/Critical)."""
        for band in self.category_bands:
            if score <= band["max_score"]:
                return band["category"]
        return str(self.category_bands[-1]["category"])


def load_scoring_weights(path: str | Path | None = None) -> ScoringWeights:
    """Load scoring weights from YAML (defaults to config/scoring_weights.yaml)."""
    if path is None:
        path = Path(__file__).resolve().parent.parent.parent / "config" / "scoring_weights.yaml"
    path = Path(path)
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ScoringWeights(**raw)


class CompanyProfile(BaseModel):
    """Input company cyber profile (as supplied by the client / assessment).

    Each field is a 0-100 pre-scored factor keyed by the factor's `key`.
    The scoring engine maps these through the evidence_scale of the
    configured factors.
    """

    firm_name: str = ""
    revenue_usd: float | None = None
    employees: int | None = None
    customer_records: int | None = None
    previous_incidents: int = 0
    # factor key -> 0-100 score (higher = worse)
    factor_scores: dict[str, float] = Field(default_factory=dict)


@dataclass
class ScoredFirm:
    """Output of the scoring engine."""

    firm_name: str
    composite_score: float  # 0-100, higher = higher risk
    risk_category: str  # Low / Medium / High / Critical
    domain_scores: dict[str, float]  # domain key -> 0-100
    factor_scores: dict[str, float]  # factor key -> 0-100 (as input)
    risk_drivers: list[str]  # factor keys where risk concentrates
    weights: ScoringWeights  # provenance / reproducibility

    def to_dict(self) -> dict:
        """Serialisable view for reporting / agent input."""
        return {
            "firm_name": self.firm_name,
            "risk_score": self.composite_score,
            "risk_category": self.risk_category,
            "risk_drivers": self.risk_drivers,
            "domain_scores": self.domain_scores,
            "factor_scores": self.factor_scores,
        }


def _domain_score(
    domain: DomainSpec, factor_scores: dict[str, float]
) -> tuple[float, list[str], list[str]]:
    """Weighted mean of a domain's factor scores + the driving factors.

    Returns (domain_score, factor_keys_used, risk_drivers_in_domain).
    """
    weighted_sum = 0.0
    used_keys: list[str] = []
    drivers: list[str] = []
    for factor in domain.factors:
        score = factor_scores.get(factor.key)
        if score is None:
            # Skip factors the profile didn't provide; renormalise the
            # remaining weights to keep the domain score on 0-100.
            continue
        weighted_sum += factor.weight * float(score)
        used_keys.append(factor.key)
        drivers.append(factor.key)

    if not used_keys:
        return 50.0, [], []  # neutral default when nothing provided

    # Renormalise weights over the used factors.
    w_sum = sum(f.weight for f in domain.factors if f.key in used_keys)
    domain_score = weighted_sum / w_sum

    # Risk drivers: factors whose score exceeds the domain average.
    avg = domain_score
    driver_keys = [k for k in drivers if float(factor_scores[k]) > avg + 1e-9]
    return domain_score, used_keys, driver_keys


def compute_score(
    profile: CompanyProfile,
    weights: ScoringWeights | None = None,
) -> ScoredFirm:
    """Compute the composite cyber risk score for a company profile.

    Parameters
        profile   validated company cyber profile
        weights   scoring weights (defaults to config/scoring_weights.yaml)

    Returns
        ScoredFirm with composite score, category, domain breakdown and
        risk drivers.  All numbers are exact arithmetic over the configured
        weights and input factor scores -- no fitting, fully explainable.
    """
    if weights is None:
        weights = load_scoring_weights()

    domain_scores: dict[str, float] = {}
    all_drivers: list[str] = []
    for domain in weights.domains:
        d_score, _used, drivers = _domain_score(domain, profile.factor_scores)
        domain_scores[domain.key] = d_score
        all_drivers.extend(drivers)

    # Composite = weighted mean of domain scores, renormalised over domains
    # that have at least one scored factor.
    present_domains = [
        d for d in weights.domains
        if any(f.key in profile.factor_scores for f in d.factors)
    ]
    if not present_domains:
        composite = 50.0
    else:
        w_sum = sum(d.weight for d in present_domains)
        composite = sum(d.weight * domain_scores[d.key] for d in present_domains) / w_sum

    category = weights.category_for_score(composite)

    return ScoredFirm(
        firm_name=profile.firm_name,
        composite_score=round(float(composite), 4),
        risk_category=category,
        domain_scores={k: round(v, 4) for k, v in domain_scores.items()},
        factor_scores=dict(profile.factor_scores),
        risk_drivers=list(all_drivers),
        weights=weights,
    )
