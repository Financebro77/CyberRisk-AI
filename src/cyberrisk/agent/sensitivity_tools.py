"""Control-improvement sensitivity analysis for the consultant agent.

The agent can offer to model improvements ("implement MFA", "add immutable
backups") but must NEVER claim a sensitivity result unless this tool actually
ran.  This module is the real engine behind that offer:

    run_control_improvement_scenario(brief, control_change, n_years)

does three things:

    1. MODIFY RISK INPUTS -- takes the client's baseline factor scores and
       applies the control change by moving the target factor's 0-100 score
       to the improved evidence-scale value (e.g. implement MFA moves
       mfa_coverage to the "comprehensive" rating's score).
    2. RUN THE EXISTING ENGINE -- scores both profiles and runs the same
       seeded Monte Carlo simulation for each.
    3. COMPARE BEFORE vs AFTER -- reports EAL / VaR99 / ES99 for each and the
       impact (loss reduction + percentage improvement).

The tool reuses the deterministic factor mapping from tools.py so the same
brief always produces the same before/after figures.  The engine modules are
imported and CALLED -- never modified.

Supported control changes (each maps to one factor + a target rating from
config/scoring_weights.yaml's evidence scales, lower score = lower risk):

    - implement MFA            -> mfa_coverage:      comprehensive
    - improve segmentation     -> privileged_access: segmented
    - reduce privileged access -> privileged_access: least_privilege
    - add immutable backups    -> backup_frequency:  continuous
    - add backups              -> backup_frequency:  daily

An unknown control change is rejected with {"status": "unknown_control_change"}.
A change that would not improve an already-strong control is a no-op and the
report shows the honest "no material impact".
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from cyberrisk.agent.schemas import CompanyBrief
from cyberrisk.agent.tools import _model_config, build_factor_scores
from cyberrisk.metrics import compute_metrics
from cyberrisk.simulation import simulate

# Control change -> (factor key, target rating).  Target ratings are valid
# values from config/scoring_weights.yaml evidence scales.
_CONTROL_CHANGE_FACTORS: dict[str, tuple[str, str]] = {
    "implement mfa": ("mfa_coverage", "comprehensive"),
    "improve segmentation": ("privileged_access", "segmented"),
    "reduce privileged access": ("privileged_access", "least_privilege"),
    "add immutable backups": ("backup_frequency", "continuous"),
    "add backups": ("backup_frequency", "daily"),
}

# Canonical labels for each change, for the client report.
_CANONICAL_LABEL: dict[str, str] = {
    "implement mfa": "Implement MFA",
    "improve segmentation": "Improve network segmentation",
    "reduce privileged access": "Reduce privileged access",
    "add immutable backups": "Add immutable backups",
    "add backups": "Add backups",
}


@dataclass(frozen=True)
class ControlImprovementResult:
    """Before / after metrics plus the impact, ready for the client report."""

    control_change: str
    label: str
    factor_key: str
    target_rating: str
    before_eal: float
    before_var_99: float
    before_es_99: float
    after_eal: float
    after_var_99: float
    after_es_99: float

    @property
    def loss_reduction(self) -> float:
        """EAL reduction in dollars (before - after, floored at 0)."""
        return max(0.0, self.before_eal - self.after_eal)

    @property
    def percentage_improvement(self) -> float:
        """Relative EAL reduction as a fraction (0.0 .. 1.0)."""
        if self.before_eal <= 0:
            return 0.0
        return self.loss_reduction / self.before_eal

    def to_dict(self) -> dict:
        """JSON-serialisable view for the tool result.

        All figures are rounded consistently from the SAME unrounded values so
        the displayed impact matches the displayed before/after (loss_reduction
        == before_eal - after_eal and percentage_improvement == that / before_eal,
        all at the same rounding).
        """
        b_eal = round(self.before_eal, 2)
        a_eal = round(self.after_eal, 2)
        loss_reduction = round(max(0.0, b_eal - a_eal), 2)
        pct = round(loss_reduction / b_eal, 4) if b_eal > 0 else 0.0
        return {
            "status": "ok",
            "control_change": self.control_change,
            "label": self.label,
            "factor_key": self.factor_key,
            "target_rating": self.target_rating,
            "before": {
                "eal": b_eal,
                "var_99": round(self.before_var_99, 2),
                "es_99": round(self.before_es_99, 2),
            },
            "after": {
                "eal": a_eal,
                "var_99": round(self.after_var_99, 2),
                "es_99": round(self.after_es_99, 2),
            },
            "impact": {
                "loss_reduction": loss_reduction,
                "percentage_improvement": pct,
            },
        }


def normalize_control_change(control_change: str) -> str | None:
    """Normalise free-text control change to a canonical key, or None.

    Accepts the aliases above (case-, punctuation- and underscore-insensitive)
    and partial keyword matches ("immutable backups", "2fa", "least
    privilege").  Returns the canonical key or None if unsupported.
    """
    key = (control_change or "").strip().lower().replace("_", " ")
    if key in _CONTROL_CHANGE_FACTORS:
        return key
    if any(alias in key for alias in ("mfa", "multi-factor", "2fa", "2 factor")):
        return "implement mfa"
    if "segment" in key:
        return "improve segmentation"
    if "privilege" in key:
        return "reduce privileged access"
    if "immutable" in key:
        return "add immutable backups"
    if "backup" in key:
        return "add backups"
    return None


@lru_cache(maxsize=1)
def _weights():
    from cyberrisk.scoring import load_scoring_weights

    return load_scoring_weights()


def _score_profile(brief: CompanyBrief, factor_scores: dict[str, float]) -> object:
    """Score a profile from a factor-scores dict (0-100, higher = worse)."""
    from cyberrisk.scoring import CompanyProfile, compute_score

    profile = CompanyProfile(
        firm_name=brief.firm_name or "Client",
        revenue_usd=brief.revenue_usd,
        customer_records=brief.customer_records,
        previous_incidents=brief.previous_incidents,
        factor_scores=factor_scores,
    )
    return compute_score(profile, _weights())


def _metrics_for_composite(brief: CompanyBrief, composite_score: float, n_years: int) -> dict:
    """Run the seeded engine for a composite score and return key metrics."""
    cfg = _model_config()
    cfg_adj = cfg.model_copy(update={"firm_revenue_usd": brief.revenue_usd or cfg.firm_revenue_usd})
    result = simulate(
        cfg_adj,
        n_years=n_years,
        score=composite_score,
        return_events=False,
    )
    m = compute_metrics(result)
    return {
        "eal": float(m.eal),
        "var_99": float(m.var_99),
        "es_99": float(m.es_99),
    }


def run_control_improvement_scenario(
    brief: CompanyBrief,
    control_change: str,
    n_years: int | None = None,
) -> dict:
    """Model the effect of a control improvement on the client's loss.

    Parameters
        brief            the client's baseline profile (revenue + controls)
        control_change   one of the supported improvements, e.g.
                         "implement MFA", "add immutable backups",
                         "improve segmentation", "reduce privileged access"
        n_years          Monte Carlo years (default 100_000)

    Returns
        dict with "before" / "after" metrics (EAL, VaR99, ES99) and "impact"
        (loss_reduction + percentage_improvement), or an error payload:
            {"status": "insufficient_info", "needed": [...]} when the brief
            cannot be modelled, or
            {"status": "unknown_control_change"} when the change is unsupported.

    The tool refuses to fabricate a scenario: it only claims a sensitivity
    result when this function has run the engine for BOTH profiles.
    """
    if n_years is None:
        n_years = 100_000

    # Completeness guard: same rule as the other loss tools -- never model an
    # invented profile.
    from cyberrisk.agent.tools import _guarded

    guard = _guarded(brief)
    if guard:
        return guard

    key = normalize_control_change(control_change)
    if key is None:
        return {
            "status": "unknown_control_change",
            "message": (
                f"Control change {control_change!r} is not supported. "
                "Supported changes: implement MFA, improve segmentation, "
                "reduce privileged access, add immutable backups, add backups."
            ),
        }
    factor_key, target_rating = _CONTROL_CHANGE_FACTORS[key]
    label = _CANONICAL_LABEL.get(key, key.title())

    # 1. Baseline: score the client's current profile and run the engine.
    base_scores = build_factor_scores(brief)
    base_scored = _score_profile(brief, base_scores)
    before = _metrics_for_composite(brief, base_scored.composite_score, n_years)

    # 2. Improved: raise the target factor to the better evidence-scale value.
    #    A lower score means lower risk.  If the client is already at or better
    #    than the improvement, keep their score (honest no-op).
    from cyberrisk.agent.tools import _rating_to_score

    target_score = _rating_to_score(_weights(), factor_key, target_rating)
    improved_scores = dict(base_scores)
    if base_scores[factor_key] > target_score:
        improved_scores[factor_key] = target_score

    improved_scored = _score_profile(brief, improved_scores)
    after = _metrics_for_composite(brief, improved_scored.composite_score, n_years)

    return ControlImprovementResult(
        control_change=key,
        label=label,
        factor_key=factor_key,
        target_rating=target_rating,
        before_eal=before["eal"],
        before_var_99=before["var_99"],
        before_es_99=before["es_99"],
        after_eal=after["eal"],
        after_var_99=after["var_99"],
        after_es_99=after["es_99"],
    ).to_dict()
