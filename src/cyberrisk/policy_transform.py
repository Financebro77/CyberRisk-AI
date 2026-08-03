"""Insurance policy transforms: occurrence-level retained / transferred loss.

Phase 4 module.  Given the per-event simulated loss table and a policy
structure, computes the loss retained by the insured vs transferred to the
insurer, for every simulated year.

Why per-occurrence: a policy has a per-occurrence deductible, an occurrence
limit, and an annual aggregate deductible.  These attach at the LEVEL OF A
SINGLE OCCURRENCE, so they must be applied to each simulated event before
any annual aggregation.  Applying policy terms to an annual aggregate and
then summing is a common but wrong shortcut -- it systematically
understates retained loss because it lets small events escape the
per-occurrence deductible.

Policy structure (all amounts in USD):
    per_occurrence_deductible   retained on each occurrence before insurer pays
    per_occurrence_limit        insurer pays up to this per occurrence
    annual_aggregate_deductible once annual transferred loss exceeds this,
                                the insurer pays the excess (after occurrence
                                terms are applied)
    annual_aggregate_limit      insurer's maximum annual payout
    coinsurance                 insured fraction of each occurrence loss above
                                the deductible (0.10 = insurer pays 90%)
    sub_limits                  dict {scenario_key: max insurer pays per occurrence}
                                (e.g. ransomware sub-limit)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class PolicyStructure:
    per_occurrence_deductible: float = 0.0
    per_occurrence_limit: float | None = None  # None = unlimited
    annual_aggregate_deductible: float = 0.0
    annual_aggregate_limit: float | None = None  # None = unlimited
    coinsurance: float = 0.0  # 0.10 = insured keeps 10% above deductible
    sub_limits: dict[str, float] = field(default_factory=dict)  # scenario key -> max

    def __post_init__(self) -> None:
        if self.per_occurrence_deductible < 0:
            raise ValueError("per_occurrence_deductible must be >= 0")
        if self.per_occurrence_limit is not None and self.per_occurrence_limit < 0:
            raise ValueError("per_occurrence_limit must be >= 0")
        if self.annual_aggregate_deductible < 0:
            raise ValueError("annual_aggregate_deductible must be >= 0")
        if not 0.0 <= self.coinsurance < 1.0:
            raise ValueError("coinsurance must be in [0, 1)")


def apply_occurrence_transfer(
    event_severities: np.ndarray,
    event_scenarios: np.ndarray,
    scenario_keys: list[str],
    policy: PolicyStructure,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply per-occurrence terms to each event; return (retained, transferred) per event.

    For each event loss `sev` in scenario `s`:
        sub = policy.sub_limits.get(s, inf)
        insurer_pays = min(sev, sub)
        insurer_pays = max(insurer_pays - deductible, 0)
        insurer_pays *= (1 - coinsurance)
        transferred = min(insurer_pays, occurrence_limit)
        retained    = sev - transferred

    Returns parallel arrays aligned with `event_severities`.
    """
    n = len(event_severities)
    transferred = np.zeros(n, dtype=np.float64)
    retained = np.zeros(n, dtype=np.float64)

    for i in range(n):
        sev = float(event_severities[i])
        scenario = int(event_scenarios[i])
        key = scenario_keys[scenario] if scenario < len(scenario_keys) else ""

        # Sub-limit first.
        sub = policy.sub_limits.get(key, np.inf)
        insurer = min(sev, sub)

        # Deductible.
        insurer = max(insurer - policy.per_occurrence_deductible, 0.0)

        # Coinsurance (insurer pays (1 - c) of the amount above deductible).
        insurer *= (1.0 - policy.coinsurance)

        # Occurrence limit.
        if policy.per_occurrence_limit is not None:
            insurer = min(insurer, policy.per_occurrence_limit)

        transferred[i] = insurer
        retained[i] = sev - insurer

    return retained, transferred


def apply_annual_aggregate(
    year_retained: np.ndarray,
    year_transferred: np.ndarray,
    policy: PolicyStructure,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the annual aggregate deductible / limit per policy year.

    Each simulated year is an independent policy period, so the aggregate
    deductible resets every year.  The insurer's payout for a year is:

        after_agg = max(year_transferred - agg_deduct, 0)
        after_agg = min(after_agg, agg_limit)   # if limit set

    Any amount not paid (deductible shortfall or above the aggregate limit)
    is pushed back to retained loss.

    Returns (final_retained, final_transferred) per year.
    """
    agg_deduct = policy.annual_aggregate_deductible
    agg_limit = policy.annual_aggregate_limit

    before_agg = year_transferred.copy()
    after_deduct = np.maximum(before_agg - agg_deduct, 0.0)
    if agg_limit is not None:
        after_deduct = np.minimum(after_deduct, agg_limit)

    final_transferred = after_deduct
    final_retained = year_retained + (before_agg - after_deduct)
    return final_retained, final_transferred


def transform_events_to_years(
    event_severities: np.ndarray,
    event_scenarios: np.ndarray,
    event_years: np.ndarray,
    n_years: int,
    scenario_keys: list[str],
    policy: PolicyStructure,
) -> dict[str, np.ndarray]:
    """Full pipeline: occurrence terms -> annual retained/transferred totals.

    Returns dict with keys 'retained' and 'transferred' (each (n_years,)).
    """
    retained, transferred = apply_occurrence_transfer(
        event_severities, event_scenarios, scenario_keys, policy
    )

    # Event years come from the simulation event stream as float64; index
    # accumulation requires integer indices.
    year_idx = event_years.astype(np.int64)

    year_retained = np.zeros(n_years, dtype=np.float64)
    year_transferred = np.zeros(n_years, dtype=np.float64)
    np.add.at(year_retained, year_idx, retained)
    np.add.at(year_transferred, year_idx, transferred)

    final_retained, final_transferred = apply_annual_aggregate(
        year_retained, year_transferred, policy
    )
    return {"retained": final_retained, "transferred": final_transferred}
