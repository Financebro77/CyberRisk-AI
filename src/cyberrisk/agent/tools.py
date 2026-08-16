"""CyberRisk tool layer for the DeepSeek consultant agent.

Each tool is a thin, read-only wrapper over the existing quantitative
engine.  The engine modules (scoring, calibration, simulation, metrics,
policy_transform, reporting) are imported and CALLED -- never modified.

Two rules keep the numbers honest:

    * Completeness guard -- `run_loss_simulation` and
      `analyse_insurance_structure` refuse to run until the client has given
      revenue and a security-control description.  They return
      ``{"status": "insufficient_info", "needed": [...]}`` instead, which
      the agent turns into a clarifying question.  The engine never runs on
      an invented profile.
    * Deterministic profile mapping -- `build_factor_scores` maps the
      client's free-text brief onto the engine's 18 scoring factors through
      the configured evidence scales (via benchmark._rating_to_score).
      Unstated factors get documented neutral defaults.  The same brief
      always yields the same score, so the numbers the LLM reasons over are
      auditable and reproducible.

Every tool returns a JSON-serialisable dict (floats / lists / strings).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from cyberrisk.agent.schemas import CompanyBrief, PolicyInput
from cyberrisk.benchmark import _rating_to_score
from cyberrisk.calibration import load_config
from cyberrisk.metrics import compute_metrics
from cyberrisk.policy_transform import PolicyStructure, transform_events_to_years
from cyberrisk.scoring import CompanyProfile, compute_score, load_scoring_weights
from cyberrisk.simulation import simulate

# Repo root: src/cyberrisk/agent/tools.py -> src/cyberrisk -> src -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ---------------------------------------------------------------------------
# Deterministic brief -> factor-score mapping
# ---------------------------------------------------------------------------

# Neutral default rating per factor, applied when the client's brief does not
# mention that control.  Chosen to match the model's "medium retail" baseline
# so an unstated control neither inflates nor deflates the score.
DEFAULT_RATINGS: dict[str, str] = {
    "external_attack_surface": "moderate",
    "industry_targeting": "moderate_target",
    "data_sensitivity": "moderate",
    "patch_cadence": "monthly",
    "vuln_scanning": "weekly",
    "open_critical_vulns": "moderate",
    "mfa_coverage": "majority",
    "privileged_access": "basic",
    "iam_governance": "defined",
    "edr_coverage": "majority",
    "backup_frequency": "daily",
    "dr_testing": "annual",
    "vendor_assessment": "annual",
    "contractual_security": "standard",
    "supply_chain_visibility": "partial",
    "incident_response": "documented",
    "risk_oversight": "delegated",
    "cyber_insurance": "partial",
}

# Industry -> evidence-scale rating for the industry_targeting factor.
_INDUSTRY_TARGETING: dict[str, str] = {
    "health": "very_high_target",
    "healthcare": "very_high_target",
    "hospital": "very_high_target",
    "pharma": "very_high_target",
    "financial": "very_high_target",
    "bank": "very_high_target",
    "insurance": "very_high_target",
    "tech": "high_target",
    "software": "high_target",
    "technology": "high_target",
    "telecom": "high_target",
    "energy": "high_target",
    "utilit": "high_target",
    "government": "high_target",
    "public sector": "high_target",
    "retail": "moderate_target",
    "consumer": "moderate_target",
    "professional": "moderate_target",
    "legal": "moderate_target",
    "consulting": "moderate_target",
    "manufactur": "low_target",
    "industrial": "low_target",
    "construction": "low_target",
}

# Customer-record volume -> data_sensitivity rating.
def _data_sensitivity_rating(records: int | None) -> str:
    if records is None:
        return "moderate"
    if records >= 10_000_000:
        return "critical"
    if records >= 1_000_000:
        return "high"
    if records >= 100_000:
        return "moderate"
    return "low"


# Technology dependency -> external_attack_surface rating.
def _attack_surface_rating(dependency: str | None) -> str:
    if not dependency:
        return "moderate"
    d = dependency.strip().lower()
    if d in ("high", "very high", "critical", "extreme"):
        return "high"
    if d in ("low", "minimal", "none"):
        return "low"
    return "moderate"


# Security-controls free text -> factor ratings.
#
# The client says things like "weak MFA and limited network segmentation".
# We scan for control keywords and apply a strength qualifier (weak / none /
# strong) to pick the evidence-scale rating.  Anything not mentioned keeps
# its DEFAULT_RATINGS entry.
#
# IMPORTANT: each control is qualified from the CLAUSE that mentions it, not
# from the whole sentence.  A client may say "MFA is partial, no immutable
# backups, segmentation is weak" -- the qualifier for MFA ("partial"/neutral)
# must come from the text around "MFA", not from the "no" that governs
# backups.  A single absent control must never downgrade unrelated controls.
_WEAK_WORDS = ("weak", "limited", "poor", "minimal", "lacking", "sparse", "irregular", "lagging", "rare", "outdated")
_NONE_WORDS = ("none", "no ", "absent", "missing", "don't have", "do not have", "not implemented", "zero")
_STRONG_WORDS = ("strong", "full", "comprehensive", "enforced", "robust", "mature", "enterprise", "extensive", "continuous")

# Clause separators: the text is split on these so each control is qualified
# only by its own clause.  Commas, semicolons, and "but"/"and" boundary the
# phrases the client uses to describe separate controls.
_CLAUSE_SEPARATORS = (",", ";", " and ", " but ", " while ", " though ", " although ", " yet ")


def _qualifier_for(text: str) -> str:
    """Return 'strong' | 'weak' | 'none' | 'neutral' based on surrounding words.

    Operates on the supplied (clause-local) text so a control is qualified by
    its own phrase, never by words that govern a different control.
    """
    low = text.lower()
    if any(w in low for w in _NONE_WORDS):
        return "none"
    if any(w in low for w in _WEAK_WORDS):
        return "weak"
    if any(w in low for w in _STRONG_WORDS):
        return "strong"
    return "neutral"


def _qualifier_for_control(low_text: str, keywords: tuple[str, ...]) -> str:
    """Qualifier for ONE control, read from the clause that mentions it.

    ``keywords`` is the SAME alias list the trigger used, so a control the
    client described with a synonym ("multi-factor authentication", "network
    isolation", "disaster recovery") is still qualified from its own clause.
    The qualifier is clause-local (split on separators), so "no immutable
    backups" does not downgrade "MFA is partial" in the same sentence.

    When an alias appears in MULTIPLE clauses (e.g. "poor backups, no
    immutable backups"), the strictest (most negative) mention wins -- the
    client said backups are at least partially absent, so "none" is the honest
    reading.
    """
    hits = [k for k in keywords if k in low_text]
    if not hits:
        return "neutral"
    # Score every clause that mentions any alias; "none" > "weak" > "strong"
    # > "neutral" (a single absent control is the strongest signal).
    _RANK = {"none": 3, "weak": 2, "strong": 1, "neutral": 0}
    best = "neutral"
    for keyword in hits:
        idx = -1
        while True:
            idx = low_text.find(keyword, idx + 1)
            if idx < 0:
                break
            qual = _qualifier_for(_clause_containing(low_text, idx))
            if _RANK[qual] > _RANK[best]:
                best = qual
    return best


def _clause_containing(low_text: str, idx: int) -> str:
    """The clause (separator-delimited span) containing character ``idx``."""
    start = 0
    end = len(low_text)
    for sep in _CLAUSE_SEPARATORS:
        sep_low = sep.lower()
        # find all separator occurrences, bracket the one around idx
        pos = -1
        while True:
            pos = low_text.find(sep_low, pos + 1)
            if pos < 0:
                break
            if pos < idx:
                start = max(start, pos + len(sep_low))
            elif pos > idx:
                end = min(end, pos)
                break
    return low_text[start:end]


# Per-control alias sets.  Each trigger AND its qualifier share the SAME list,
# so a client who describes a control with a synonym ("multi-factor
# authentication", "network isolation", "endpoint protection", "disaster
# recovery", "SOC") gets the control scored from that phrasing -- before this,
# the trigger matched the synonym but the qualifier searched for a narrower
# literal keyword, silently rating a stated weakness as "neutral".
_MFA_ALIASES = ("mfa", "multi-factor", "multifactor", "two-factor", "2fa", "2-factor", "2 factor")
_SEGMENT_ALIASES = ("segment", "microsegment", "network isolation", "air-gap", "air gap")
_EDR_ALIASES = ("edr", "endpoint", "antivirus", "anti-virus", "av ")
_DR_ALIASES = ("disaster recovery", "dr testing", "recovery test", "dr plan")
_IR_ALIASES = ("incident response", "ir plan", "security team", "soc", "runbook")
_CISO_ALIASES = ("ciso", "risk oversight", "security leadership", "board")


def _scan_security_controls(brief: CompanyBrief, factors: dict[str, str]) -> None:
    """Populate factor ratings from the client's free-text controls description.

    Each control is qualified from its OWN clause (see ``_qualifier_for_control``),
    so a single absent control never downgrades unrelated controls.
    """
    text = (brief.security_controls or "").strip()
    if not text:
        return
    low = text.lower()

    # MFA ------------------------------------------------------------------
    if any(k in low for k in _MFA_ALIASES):
        factors["mfa_coverage"] = {
            "strong": "comprehensive",
            "weak": "minimal",
            "none": "none",
            "neutral": "partial",
        }[_qualifier_for_control(low, _MFA_ALIASES)]

    # Network segmentation / privileged access -----------------------------
    if any(k in low for k in _SEGMENT_ALIASES):
        factors["privileged_access"] = {
            "strong": "segmented",
            "weak": "weak",
            "none": "none",
            "neutral": "basic",
        }[_qualifier_for_control(low, _SEGMENT_ALIASES)]

    # Patching --------------------------------------------------------------
    if any(k in low for k in ("patch", "patching")):
        factors["patch_cadence"] = {
            "strong": "continuous",
            "weak": "adhoc",
            "none": "none",
            "neutral": "monthly",
        }[_qualifier_for_control(low, ("patch", "patching"))]

    # Vulnerability scanning ------------------------------------------------
    if "vuln" in low and "scan" in low:
        factors["vuln_scanning"] = {
            "strong": "continuous",
            "weak": "quarterly",
            "none": "none",
            "neutral": "weekly",
        }[_qualifier_for_control(low, ("vuln", "scan"))]

    # EDR / endpoint --------------------------------------------------------
    if any(k in low for k in _EDR_ALIASES):
        factors["edr_coverage"] = {
            "strong": "comprehensive",
            "weak": "minimal",
            "none": "none",
            "neutral": "majority",
        }[_qualifier_for_control(low, _EDR_ALIASES)]

    # Backups ---------------------------------------------------------------
    if "backup" in low:
        factors["backup_frequency"] = {
            "strong": "continuous",
            "weak": "monthly",
            "none": "none",
            "neutral": "daily",
        }[_qualifier_for_control(low, ("backup",))]

    # DR / recovery testing -------------------------------------------------
    if any(k in low for k in _DR_ALIASES):
        factors["dr_testing"] = {
            "strong": "quarterly",
            "weak": "occasional",
            "none": "never",
            "neutral": "annual",
        }[_qualifier_for_control(low, _DR_ALIASES)]

    # Incident response -----------------------------------------------------
    if any(k in low for k in _IR_ALIASES):
        factors["incident_response"] = {
            "strong": "tested",
            "weak": "informal",
            "none": "none",
            "neutral": "documented",
        }[_qualifier_for_control(low, _IR_ALIASES)]

    # Governance / CISO -----------------------------------------------------
    if any(k in low for k in _CISO_ALIASES):
        factors["risk_oversight"] = {
            "strong": "dedicated",
            "weak": "delegated",
            "none": "absent",
            "neutral": "delegated",
        }[_qualifier_for_control(low, _CISO_ALIASES)]


def _scan_existing_coverage(brief: CompanyBrief, factors: dict[str, str]) -> None:
    """Map the client's existing cyber insurance text onto the cyber_insurance factor."""
    text = (brief.existing_coverage or "").strip()
    if not text:
        return
    low = text.lower()
    if any(w in low for w in _NONE_WORDS) or low in ("", "none"):
        factors["cyber_insurance"] = "none"
    elif any(w in low for w in _STRONG_WORDS):
        factors["cyber_insurance"] = "comprehensive"
    elif any(w in low for w in ("small", "low", "minimal", "limited", "basic")):
        factors["cyber_insurance"] = "minimal"
    else:
        # A specific limit ("$5M limit") means they have partial coverage.
        factors["cyber_insurance"] = "partial"


def build_factor_scores(brief: CompanyBrief) -> dict[str, float]:
    """Map a client brief onto the 18 scoring-factor ratings, then to scores.

    Deterministic and fully explainable: every factor gets a rating, either
    from the brief or from DEFAULT_RATINGS, mapped through the configured
    evidence scales.  Returns ``{factor_key: 0-100}`` ready for CompanyProfile.
    """
    ratings: dict[str, str] = dict(DEFAULT_RATINGS)

    industry = (brief.industry or "").strip().lower()
    if industry:
        for needle, rating in _INDUSTRY_TARGETING.items():
            if needle in industry:
                ratings["industry_targeting"] = rating
                break
        else:
            ratings["industry_targeting"] = "moderate_target"

    ratings["data_sensitivity"] = _data_sensitivity_rating(brief.customer_records)
    ratings["external_attack_surface"] = _attack_surface_rating(brief.technology_dependency)

    _scan_security_controls(brief, ratings)
    _scan_existing_coverage(brief, ratings)

    weights = load_scoring_weights()
    return {key: _rating_to_score(weights, key, rating) for key, rating in ratings.items()}


def assumed_ratings(brief: CompanyBrief) -> dict[str, str]:
    """Which factors were assumed (neutral default) rather than stated by the client.

    Lets the agent tell the client what it assumed, keeping the assessment
    transparent.
    """
    stated: dict[str, str] = dict(DEFAULT_RATINGS)
    _scan_security_controls(brief, stated)
    _scan_existing_coverage(brief, stated)
    industry = (brief.industry or "").strip().lower()
    if industry:
        for needle, rating in _INDUSTRY_TARGETING.items():
            if needle in industry:
                stated["industry_targeting"] = rating
                break
    stated["data_sensitivity"] = _data_sensitivity_rating(brief.customer_records)
    stated["external_attack_surface"] = _attack_surface_rating(brief.technology_dependency)

    from cyberrisk.scoring import load_scoring_weights
    weights = load_scoring_weights()
    default_scores = {k: _rating_to_score(weights, k, r) for k, r in DEFAULT_RATINGS.items()}
    actual = build_factor_scores(brief)
    return [k for k in default_scores if abs(default_scores[k] - actual[k]) > 1e-9]


# ---------------------------------------------------------------------------
# Engine config / weights (loaded once per process)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _model_config() -> object:
    """Load the calibrated 7-scenario model config once (repo config YAMLs)."""
    return load_config(
        REPO_ROOT / "config" / "scenarios.yaml",
        REPO_ROOT / "config" / "simulation_config.yaml",
    )


class _SimulationCache:
    """Small cache of SimulationResult keyed by (brief fingerprint, n_years).

    Simulate is deterministic (seeded), so re-running is exact; the cache
    just avoids repeating an expensive 100k-year run across tool calls.
    """

    _entries: dict[tuple, object] = {}
    _MAX = 4

    @classmethod
    def get(cls, key: tuple) -> object:
        return cls._entries.get(key)

    @classmethod
    def put(cls, key: tuple, result: object) -> None:
        cls._entries[key] = result
        if len(cls._entries) > cls._MAX:
            oldest = next(iter(cls._entries))
            del cls._entries[oldest]


def _fingerprint(brief: CompanyBrief, n_years: int) -> tuple:
    key = json.dumps(brief.to_tool_input(), sort_keys=True, default=str)
    return key, n_years


def _run_simulation(brief: CompanyBrief, n_years: int, return_events: bool) -> object:
    """Score the brief and run the Monte Carlo engine (cached per fingerprint)."""
    cfg = _model_config()
    factor_scores = build_factor_scores(brief)
    profile = CompanyProfile(
        firm_name=brief.firm_name or "Client",
        revenue_usd=brief.revenue_usd,
        customer_records=brief.customer_records,
        previous_incidents=brief.previous_incidents,
        factor_scores=factor_scores,
    )
    scored = compute_score(profile)
    cfg_adj = cfg.model_copy(update={"firm_revenue_usd": brief.revenue_usd or cfg.firm_revenue_usd})

    cache_key = (_fingerprint(brief, n_years), return_events)
    result = _SimulationCache.get(cache_key)
    if result is None:
        result = simulate(
            cfg_adj,
            n_years=n_years,
            score=scored.composite_score,
            return_events=return_events,
        )
        _SimulationCache.put(cache_key, result)
    return scored, result


def _guarded(brief: CompanyBrief) -> dict | None:
    """Return the insufficient_info payload when the brief cannot be modelled."""
    missing = brief.missing_for_simulation()
    if missing:
        return {
            "status": "insufficient_info",
            "needed": missing,
            "message": "Cannot run the loss model without revenue and a security-controls description. "
            "Ask the client for these before proceeding.",
        }
    return None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def assess_company_risk(brief: CompanyBrief) -> dict:
    """Tool 1: score the client's cyber profile and identify risk drivers.

    Works on partial briefs (unstated factors use documented neutral
    defaults) and always reports what was assumed.
    """
    weights = load_scoring_weights()
    factor_scores = build_factor_scores(brief)
    profile = CompanyProfile(
        firm_name=brief.firm_name or "Client",
        revenue_usd=brief.revenue_usd,
        customer_records=brief.customer_records,
        previous_incidents=brief.previous_incidents,
        factor_scores=factor_scores,
    )
    scored = compute_score(profile, weights)
    return {
        "status": "ok",
        "firm_name": scored.firm_name,
        "risk_score": scored.composite_score,
        "risk_category": scored.risk_category,
        "risk_drivers": scored.risk_drivers,
        "domain_scores": scored.domain_scores,
        "assumed_factors": assumed_ratings(brief),
    }


def run_loss_simulation(brief: CompanyBrief, n_years: int | None = None) -> dict:
    """Tool 2: run the Monte Carlo loss model.

    Returns EAL, VaR, Expected Shortfall, PMLs and a compact loss-
    distribution summary -- all sourced from the engine.
    """
    guard = _guarded(brief)
    if guard:
        return guard
    n_years = n_years or 100_000
    scored, result = _run_simulation(brief, n_years, return_events=True)
    m = compute_metrics(result)
    losses = result.total_losses
    quantiles = {
        "p50": float(np.quantile(losses, 0.50)),
        "p90": float(np.quantile(losses, 0.90)),
        "p95": float(np.quantile(losses, 0.95)),
        "p99": float(np.quantile(losses, 0.99)),
        "p99_9": m.p99_9,
    }
    # Scenario AAL / contribution, ranked descending so the agent sees the
    # biggest drivers first.
    aal = m.aal_by_scenario
    ordered = sorted(aal.items(), key=lambda kv: kv[1], reverse=True)
    contrib = m.scenario_contribution()
    # Scenario contribution analysis with model-linked drivers (frequency /
    # severity drivers, recommended controls) for the agent's explanation.
    from cyberrisk.agent.scenario_contribution import analyze_scenario_contribution

    contrib_analysis = analyze_scenario_contribution(brief, n_years=n_years)
    contrib_with_drivers = contrib_analysis.get("scenarios", []) if contrib_analysis.get("status") == "ok" else []
    # Loss exceedance curve: P(loss >= X) across the simulated sample, sampled
    # at a modest fixed grid so the dashboard's curve uses real engine data
    # without shipping 100k numbers.  Uses the same stable PML quantiles as
    # the rest of the response.
    exceed_grid = [0.0, 0.25e6, 0.5e6, 1.0e6, 2.0e6, 5.0e6, 10.0e6, 20.0e6, 50.0e6]
    exceed_probs = np.clip(
        np.mean(losses[None, :] >= np.asarray(exceed_grid)[:, None], axis=1),
        0.0,
        1.0,
    )
    exceedance = [
        {"loss": float(x), "prob": float(p)}
        for x, p in zip(exceed_grid, exceed_probs)
    ]
    return {
        "status": "ok",
        "firm_name": scored.firm_name,
        "risk_score": scored.composite_score,
        "risk_category": scored.risk_category,
        "risk_drivers": scored.risk_drivers,
        "n_years": n_years,
        "eal": m.eal,
        "var_95": m.var_95,
        "var_99": m.var_99,
        "es_95": m.es_95,
        "es_99": m.es_99,
        "pml_1in200": m.p99_5,
        "pml_1in1000": m.p99_9,
        "prob_zero_loss": m.prob_zero_loss,
        "loss_distribution": quantiles,
        "loss_exceedance": exceedance,
        "aal_by_scenario": dict(ordered),
        "scenario_contribution": {k: contrib[k] for k, _ in ordered},
        "scenario_contribution_detail": contrib_with_drivers,
    }


def analyse_insurance_structure(
    brief: CompanyBrief,
    policy: PolicyInput | None = None,
    n_years: int | None = None,
) -> dict:
    """Tool 3: test a proposed insurance structure against the loss model.

    Applies the policy terms per occurrence, then annually, and reports the
    insurance response and the client's residual retained exposure.  The three
    loss concepts are kept strictly separate:

        Section 1  ground-up loss     (EAL / VaR / ES — before insurance)
        Section 2  insurance response (policy limit, retention, covered loss,
                                      insurer payment)
        Section 3  client retained    (gross loss − insurance recovery)

    The gross 1-in-1000-year PML is NOT an "insurance gap".  The residual
    uncovered exposure is computed as gross loss minus insurance recovery,
    which is always >= 0, and the insurer payment is capped at the policy
    limit, so insurance recovery <= policy limit.
    """
    guard = _guarded(brief)
    if guard:
        return guard
    policy = policy or PolicyInput()
    structure = PolicyStructure(
        per_occurrence_deductible=policy.per_occurrence_deductible,
        per_occurrence_limit=policy.per_occurrence_limit,
        annual_aggregate_deductible=policy.annual_aggregate_deductible,
        annual_aggregate_limit=policy.annual_aggregate_limit,
        coinsurance=policy.coinsurance,
    )
    n_years = n_years or 100_000
    scored, result = _run_simulation(brief, n_years, return_events=True)
    m = compute_metrics(result)

    events = result.events
    pm = transform_events_to_years(
        event_severities=events[:, 2],
        event_scenarios=events[:, 0],
        event_years=events[:, 1],
        n_years=result.years,
        scenario_keys=result.scenario_keys,
        policy=structure,
    )
    retained, transferred = pm["retained"], pm["transferred"]
    from cyberrisk.metrics import expected_shortfall

    retained_eal = float(retained.mean())
    transferred_eal = float(transferred.mean())
    retained_es99 = expected_shortfall(retained, 0.99)
    limit = policy.annual_aggregate_limit
    retention = policy.per_occurrence_deductible
    exhausted = (
        float(np.mean(transferred >= limit - 1e-6))
        if limit is not None
        else 0.0
    )
    # Insurance response for the 1-in-1000-year (P99.9) event, computed
    # analytically from the policy terms.  The insurer pays the part of the
    # event above the retention, capped at the policy limit.  `None` means
    # unlimited; a limit of 0 means the insurer pays nothing.
    p99_9 = m.p99_9
    insured_gross = max(0.0, p99_9 - retention)
    insurer_payment_at_p99_9 = (
        min(insured_gross, limit) if limit is not None else insured_gross
    )
    # Residual uncovered exposure = gross loss − retention − insurance recovery.
    # This is what the policy does NOT cover above the retention (floored at 0).
    residual_at_p99_9 = max(0.0, p99_9 - retention - insurer_payment_at_p99_9)
    # Validation invariants: residual exposure is never negative, and the
    # insurer's payment never exceeds the policy limit.
    assert residual_at_p99_9 >= 0.0
    assert insurer_payment_at_p99_9 <= (limit if limit is not None else float("inf"))

    return {
        "status": "ok",
        "firm_name": scored.firm_name,
        # SECTION 1 — GROUND-UP CYBER LOSS (before insurance recovery).
        "ground_up_loss": {
            "eal": m.eal,
            "var_95": m.var_95,
            "var_99": m.var_99,
            "es_95": m.es_95,
            "es_99": m.es_99,
            "pml_1in1000": p99_9,
        },
        "policy": {
            "per_occurrence_deductible": policy.per_occurrence_deductible,
            "per_occurrence_limit": policy.per_occurrence_limit,
            "annual_aggregate_deductible": policy.annual_aggregate_deductible,
            "annual_aggregate_limit": policy.annual_aggregate_limit,
            "coinsurance": policy.coinsurance,
        },
        # SECTION 2 — INSURANCE RESPONSE (what the policy does).
        "insurance_response": {
            "policy_limit": limit,
            "retention": retention,
            "covered_loss": transferred_eal,
            "insurer_payment": transferred_eal,
            "p_annual_limit_exhausted": exhausted,
        },
        # SECTION 3 — CLIENT RETAINED LOSS (gross loss − insurance recovery).
        "client_retained_loss": {
            "retained_eal": retained_eal,
            "retained_es_99": float(retained_es99),
            "gross_loss_at_p99_9": p99_9,
            "insurance_recovery_at_p99_9": insurer_payment_at_p99_9,
            "residual_exposure_at_p99_9": residual_at_p99_9,
        },
        "pml_1in1000": p99_9,
        "evaluation": _evaluate_structure(
            retained_eal, retained_es99, p99_9, residual_at_p99_9, brief, limit
        ),
    }


def _evaluate_structure(
    retained_eal: float,
    retained_es99: float,
    gross_p99_9: float,
    residual_exposure: float,
    brief: CompanyBrief,
    policy_limit: float | None = None,
) -> dict:
    """Plain-language read on the client's retained exposure at this structure.

    Uses the residual uncovered exposure (gross loss minus insurance recovery),
    not a gross-vs-limit "gap".  The gross 1-in-1000-year PML is presented
    alongside the policy's response so the client sees exactly what is covered
    and what remains theirs.

    ``policy_limit`` distinguishes a real policy (even one exhausted by a tail
    event) from NO insurance in place: with a zero/absent limit the client
    retains the full loss, and the wording says so rather than implying a
    policy "pays up to the limit".
    """
    appetite = brief.risk_appetite
    messages: list[str] = []
    no_insurance = policy_limit is None or policy_limit <= 0.0
    if retained_eal <= 0:
        messages.append("Retained EAL is negligible at this structure.")
    else:
        messages.append(
            f"At this structure the client keeps about ${retained_eal/1e6:,.1f}M of expected annual loss."
        )
    if no_insurance:
        # No policy in place: the entire extreme loss stays with the client.
        messages.append(
            f"With no insurance in place, a ${gross_p99_9/1e6:,.1f}M extreme loss event is "
            "entirely retained by the client."
        )
    elif residual_exposure > 0:
        messages.append(
            f"For a ${gross_p99_9/1e6:,.1f}M extreme loss event, the policy pays up to the "
            f"limit, leaving a residual uncovered exposure of ${residual_exposure/1e6:,.1f}M "
            "the client retains after insurance."
        )
    else:
        messages.append(
            "The policy limit covers the modelled 1-in-1000-year loss: no residual uncovered "
            "exposure remains after insurance."
        )
    return {
        "residual_uncovered": residual_exposure > 0,
        "summary": " ".join(messages),
    }


def search_incidents(
    industry: str | None = None,
    attack_type: str | None = None,
    company: str | None = None,
    limit: int = 3,
) -> dict:
    """Tool 5: search historical cyber incidents by field.

    Queries the IncidentIndex over knowledge/corpus/incidents/curated/ by
    industry / attack type / company and returns structured incident facts
    (company, attack, loss, root cause, lessons learned) each carrying a
    citation marker the consultant can reference.  Returns a JSON-serialisable
    dict; no brief is required (this is a knowledge lookup, not a model run).
    """
    from cyberrisk.knowledge.incidents import load_incident_index

    index = load_incident_index()
    hits = index.search(
        industry=industry, attack_type=attack_type, company=company, limit=limit
    )
    return {
        "status": "ok",
        "query": {
            "industry": industry,
            "attack_type": attack_type,
            "company": company,
            "limit": limit,
        },
        "count": len(hits),
        "incidents": [inc.to_dict() for inc in hits],
    }


def report_filename(name: str) -> str:
    """The on-disk workbook filename for a firm (shared with the download route)."""
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name).strip("_") or "Client"
    return f"{safe_name}_report.xlsx"


def generate_risk_report(
    brief: CompanyBrief,
    firm_name: str | None = None,
    out_dir: str | None = None,
    n_years: int | None = None,
) -> dict:
    """Tool 4: write an Excel workbook of the assessment.

    Runs the full pipeline (score -> simulate -> policy transform -> report)
    and returns the workbook path plus a headline summary.
    """
    guard = _guarded(brief)
    if guard:
        return guard
    name = firm_name or brief.firm_name or "Client"
    n_years = n_years or 100_000
    scored, result = _run_simulation(brief, n_years, return_events=True)

    default_policy = PolicyInput()
    structure = PolicyStructure(
        per_occurrence_deductible=default_policy.per_occurrence_deductible,
        per_occurrence_limit=default_policy.per_occurrence_limit,
        annual_aggregate_deductible=default_policy.annual_aggregate_deductible,
        annual_aggregate_limit=default_policy.annual_aggregate_limit,
        coinsurance=default_policy.coinsurance,
    )
    events = result.events
    pm = transform_events_to_years(
        event_severities=events[:, 2],
        event_scenarios=events[:, 0],
        event_years=events[:, 1],
        n_years=result.years,
        scenario_keys=result.scenario_keys,
        policy=structure,
    )
    out_dir_path = Path(out_dir) if out_dir else REPO_ROOT / "data" / "output"
    out_dir_path.mkdir(parents=True, exist_ok=True)

    from cyberrisk.reporting.excel import write_report

    path = write_report(result, policy_metrics=pm, out_path=out_dir_path / report_filename(name))
    m = compute_metrics(result)
    return {
        "status": "ok",
        "report_path": str(path),
        "firm_name": name,
        "risk_category": scored.risk_category,
        "eal": m.eal,
        "var_99": m.var_99,
        "es_99": m.es_99,
    }


# ---------------------------------------------------------------------------
# Tool registry (JSON-Schema for DeepSeek function calling)
# ---------------------------------------------------------------------------


def _brief_properties() -> dict:
    """JSON-Schema properties for the brief fields a tool can accept."""
    return {
        "industry": {"type": "string", "description": "Client industry, e.g. Healthcare, Manufacturing, Financial services"},
        "revenue_usd": {"type": "number", "description": "Annual revenue in USD"},
        "customer_records": {"type": "integer", "description": "Number of customer / personal records held"},
        "technology_dependency": {"type": "string", "description": "High / Moderate / Low dependence on IT and third-party systems"},
        "security_controls": {"type": "string", "description": "Security posture in plain words, e.g. 'weak MFA and limited network segmentation'"},
        "previous_incidents": {"type": "integer", "description": "Cyber incidents in the last 3-5 years"},
        "existing_coverage": {"type": "string", "description": "Current cyber insurance, e.g. '$5M limit, $500k retention'"},
        "risk_appetite": {"type": "string", "description": "Retention willingness, e.g. 'retain up to $1.5M'"},
    }


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


TOOL_SCHEMAS: list[dict] = [
    _tool(
        "assess_company_risk",
        "Score the client's cyber risk profile (0-100) and identify the main risk drivers. "
        "Useful first step before running the loss model.",
        _brief_properties(),
    ),
    _tool(
        "run_loss_simulation",
        "Run the Monte Carlo loss model and return EAL, VaR 95/99, Expected Shortfall 95/99, "
        "PML and the loss distribution. Requires revenue and a security-controls description.",
        {**_brief_properties(), "n_years": {"type": "integer", "description": "Simulation years (default 100000)"}},
    ),
    _tool(
        "analyse_insurance_structure",
        "Test an insurance structure (retention, limits) against the loss model and report "
        "the insurance response (covered loss, insurer payment) and the client's residual "
        "retained exposure after insurance. Requires revenue and a security-controls description.",
        {
            **_brief_properties(),
            "per_occurrence_deductible": {"type": "number", "description": "Per-occurrence deductible in USD (default 250000)"},
            "per_occurrence_limit": {"type": "number", "description": "Per-occurrence limit in USD (default 5000000)"},
            "annual_aggregate_deductible": {"type": "number", "description": "Annual aggregate deductible in USD (default 1000000)"},
            "annual_aggregate_limit": {"type": "number", "description": "Annual aggregate limit in USD (default 20000000)"},
            "coinsurance": {"type": "number", "description": "Coinsurance fraction 0..1 (default 0)"},
        },
    ),
    _tool(
        "generate_risk_report",
        "Generate an Excel workbook of the full assessment for the client.",
        {"firm_name": {"type": "string", "description": "Client firm name"}, "out_dir": {"type": "string", "description": "Optional output directory"}},
    ),
    _tool(
        "run_control_improvement_scenario",
        "Model the effect of a control improvement on the client's loss: returns "
        "before/after EAL, VaR 99 and ES 99 plus the loss reduction and percentage "
        "improvement. Only claim sensitivity results after this tool runs successfully. "
        "Requires revenue and a security-controls description.",
        {
            **_brief_properties(),
            "control_change": {"type": "string", "description": "Improvement to model, e.g. 'implement MFA', 'improve segmentation', 'reduce privileged access', 'add immutable backups'"},
            "n_years": {"type": "integer", "description": "Simulation years (default 100000)"},
        },
    ),
    _tool(
        "search_incidents",
        "Search historical cyber incidents by industry, attack type, or company. "
        "Returns structured incident facts (company, attack type, financial loss, root cause, "
        "lessons learned), each with a citation marker the consultant can reference. "
        "Use when the client's question relates to a historical breach, attack pattern, "
        "or sector precedent.",
        {
            "industry": {"type": "string", "description": "Industry key (healthcare, finance, retail, manufacturing, energy, government, technology)"},
            "attack_type": {"type": "string", "description": "e.g. 'ransomware', 'BEC', 'breach', 'supply-chain'"},
            "company": {"type": "string", "description": "Company name (substring)"},
            "limit": {"type": "integer", "description": "Max incidents to return (default 3)"},
        },
    ),
]
