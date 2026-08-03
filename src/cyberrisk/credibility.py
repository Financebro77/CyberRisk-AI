"""Credibility weighting of firm-specific experience vs sector baselines.

The consultant-facing story, in plain English:

    "We start from an industry baseline for how often a company like yours
    suffers each type of cyber event.  The more of YOUR OWN incident
    history we have, the more we let it override that industry average --
    but we never throw the industry baseline away entirely, because a few
    years of your history is too little to trust on its own."

This is the classic limited-fluctuation credibility formula:

    Z  =  T / (T + K)

where
    T   is the total firm experience on a consistent scale (e.g. years of
        loss history, or incidents observed),
    K   is a credibility threshold: the amount of firm experience at which
        we would weight the firm's own data half-and-half with the baseline
        (Z = 0.5).

At T = K the firm's own data and the industry baseline each get 50%
weight.  Z approaches 1 (full firm credibility) as T grows, but never
quite reaches it -- we always keep a little of the industry prior, which
is the conservative, defensible choice for a broker.

Applied to a scenario's annual event rate:

    lambda_credible = Z * lambda_firm + (1 - Z) * lambda_baseline

so a firm with a clean record (fewer incidents than the baseline) gets a
LOWER rate than the industry average, and a firm with a troubled record
gets a HIGHER one -- but always pulled toward the baseline.  The result is
a new ModelConfig whose lambdas are annotated with the credibility weight
and the source of each number, so the audit trail is complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field, model_validator

from cyberrisk.calibration import ModelConfig


class FirmExperience(BaseModel):
    """The firm's own cyber incident history, on a per-scenario basis.

    Parameters
        scenario_key       which scenario the experience applies to
        incidents          number of events of this scenario observed in the
                           firm's history (0 is a legitimate clean record)
        years              length of that history, in years

    The per-scenario event rate implied by this experience is
        lambda_firm = incidents / years
    (0 if the firm had no such incidents in the observation window).
    """

    scenario_key: str
    incidents: int = Field(ge=0)
    years: float = Field(gt=0.0)

    @property
    def lambda_firm(self) -> float:
        """Observed annual event rate from the firm's own history."""
        return self.incidents / self.years


def credibility_weight(years: float, k: float) -> float:
    """Limited-fluctuation credibility Z = T/(T+K) for `years` of experience.

    Parameters
        years   total firm experience on the same scale as K
        k       credibility threshold (Z = 0.5 when years == k)
    Returns
        Z in [0, 1).  Z never reaches 1 (the industry baseline always keeps
        a little weight -- conservative by design).
    """
    if years < 0:
        raise ValueError("years must be >= 0")
    if k <= 0:
        raise ValueError("k must be > 0")
    return float(years / (years + k))


def blend_lambda(lambda_firm: float, lambda_baseline: float, z: float) -> float:
    """Credibility-weighted event rate: Z * firm + (1 - Z) * baseline.

    The blend is always a convex combination, so the result lies strictly
    between the firm's own rate and the industry baseline.
    """
    if not 0.0 <= z < 1.0:
        raise ValueError(f"z must be in [0, 1), got {z}")
    return float(z * lambda_firm + (1.0 - z) * lambda_baseline)


@dataclass
class CredibilityResult:
    """Outcome of applying credibility to a config: audited lambdas."""

    config: ModelConfig  # the NEW config with credibility-weighted lambdas
    weights_by_scenario: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def apply_credibility(
    config: ModelConfig,
    experience: list[FirmExperience],
    k: float,
    firm_revenue_usd: float | None = None,
) -> CredibilityResult:
    """Blend firm experience into scenario baselines by credibility weight.

    Parameters
        config            the base ModelConfig (industry-calibrated baselines)
        experience        firm's own incident history, per scenario
        k                 credibility threshold: years of firm experience at
                          which firm data and baseline each get 50% weight
        firm_revenue_usd  optional revenue override (else config revenue)

    Returns
        CredibilityResult with the blended config (annotations added) and the
        per-scenario credibility weights.

    Notes
        - Only scenarios present in `experience` are blended; the rest keep
          their industry baseline (weight implicitly 0).
        - Scenarios with no firm incidents get lambda_firm = 0 -> a LOWER
          rate than baseline (a clean record earns a lower rate, but never
          to zero, because (1-Z) > 0 always).
    """
    exp_by_key = {e.scenario_key: e for e in experience}
    unknown = set(exp_by_key) - set(config.scenario_keys)
    if unknown:
        raise ValueError(f"experience references unknown scenarios: {sorted(unknown)}")

    weights: dict[str, float] = {}
    notes: list[str] = []
    new_scenarios = []
    z = credibility_weight(k, k)  # reference: Z at the threshold, for notes only

    for s in config.scenarios:
        exp = exp_by_key.get(s.key)
        if exp is None:
            new_scenarios.append(s)  # unchanged baseline
            weights[s.key] = 0.0
            continue

        z_scen = credibility_weight(exp.years, k)
        lam_firm = exp.lambda_firm
        lam_base = s.frequency.lambda_annual
        lam_blend = blend_lambda(lam_firm, lam_base, z_scen)

        new_scenarios.append(
            s.model_copy(
                update={
                    "frequency": s.frequency.model_copy(
                        update={"lambda_annual": lam_blend}
                    ),
                    "annotation": {
                        **s.annotation,
                        "credibility_weight": f"{z_scen:.3f}",
                        "lambda_firm_observed": f"{lam_firm:.4f}",
                        "lambda_baseline": f"{lam_base:.4f}",
                        "lambda_credible": f"{lam_blend:.4f}",
                    },
                }
            )
        )
        weights[s.key] = z_scen
        notes.append(
            f"{s.key}: firm rate {lam_firm:.3f}, baseline {lam_base:.3f}, "
            f"Z={z_scen:.2f} -> credible rate {lam_blend:.3f}"
        )

    return CredibilityResult(
        config=config.model_copy(update={"scenarios": new_scenarios}),
        weights_by_scenario=weights,
        notes=notes,
    )
