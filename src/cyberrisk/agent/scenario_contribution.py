"""Scenario contribution analysis for the consultant agent.

For every client assessment the agent must report how much each cyber scenario
contributes to expected annual loss (EAL) and -- critically -- explain WHY,
with the explanation LINKED TO MODEL OUTPUTS, never invented.

``analyze_scenario_contribution(brief)`` produces, for each scenario:

    - contribution:  the scenario's share of EAL (from ``scenario_contribution``),
    - frequency drivers:  the model factors that scale that scenario's event
      frequency, taken from the client's actual factor scores -- the factors
      in the threat-exposure / access-control / vulnerability-management
      domains whose score is worst (driving the composite risk score up, which
      raises lambda via the log-linear link),
    - severity drivers:  the scenario's configured severity parameters
      (tail sigma, revenue exponent, copula loading) plus the resilience
      factors (backups, DR testing, incident response) that mitigate severity,
    - recommended controls:  the controls that map to those drivers (from the
      evidence-scale ratings).

Everything is derived from model outputs:
    * contribution  -> metrics.scenario_contribution (simulated loss shares)
    * frequency drivers -> build_factor_scores (the brief's factor scores)
    * severity drivers  -> scenarios.yaml severity config for the scenario
    * controls          -> the factor keys/ratings linked to those drivers

No explanation is generated without this linkage.  An unknown scenario yields
no driver text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from cyberrisk.agent.schemas import CompanyBrief
from cyberrisk.agent.tools import _model_config, build_factor_scores
from cyberrisk.metrics import compute_metrics
from cyberrisk.simulation import simulate

# Domain -> factors that primarily influence event FREQUENCY.
# The composite risk score (which scales scenario lambdas) is driven most by
# exposure, vulnerability, and access-control factors.
_FREQUENCY_FACTORS = (
    "external_attack_surface",
    "industry_targeting",
    "patch_cadence",
    "vuln_scanning",
    "open_critical_vulns",
    "mfa_coverage",
    "privileged_access",
    "iam_governance",
)

# Domain -> factors that primarily influence SEVERITY (containment / recovery /
# resilience).  These mitigate how bad an event is once it happens.
_SEVERITY_FACTORS = (
    "edr_coverage",
    "backup_frequency",
    "dr_testing",
    "incident_response",
)

# Scenario key -> (frequency-driver factors, severity-driver factors,
# recommended controls).  The factors are a SUBSET of the configured scoring
# factors that most shape each scenario; the recommended controls are the
# mitigations that map to those factors.
_SCENARIO_PROFILE: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "breach": (
        ("data_sensitivity", "external_attack_surface", "industry_targeting"),
        ("edr_coverage", "incident_response"),
        ("EDR / endpoint detection", "incident response planning"),
    ),
    "ransomware": (
        ("mfa_coverage", "privileged_access", "external_attack_surface"),
        ("backup_frequency", "dr_testing", "network segmentation"),
        ("immutable backups", "privileged access management"),
    ),
    "bec": (
        ("iam_governance", "mfa_coverage"),
        ("incident_response",),
        ("MFA on financial/executive accounts", "IAM governance"),
    ),
    "cloud_outage": (
        ("supply_chain_visibility", "vendor_assessment"),
        ("dr_testing", "incident_response"),
        ("DR testing / recovery", "vendor assessment"),
    ),
    "bi": (
        ("external_attack_surface",),
        ("dr_testing", "backup_frequency", "incident_response"),
        ("DR testing / recovery", "backups"),
    ),
    "supply_chain": (
        ("vendor_assessment", "supply_chain_visibility", "contractual_security"),
        ("incident_response",),
        ("vendor assessment", "contractual security requirements"),
    ),
    "ot_physical": (
        ("external_attack_surface", "industry_targeting"),
        ("dr_testing", "backup_frequency"),
        ("OT network segmentation", "DR / recovery testing"),
    ),
}

# Human-readable labels for factor keys and controls.
_FACTOR_LABELS: dict[str, str] = {
    "external_attack_surface": "exposed remote access / attack surface",
    "industry_targeting": "industry targeting",
    "data_sensitivity": "high-value data at rest",
    "patch_cadence": "patch cadence",
    "vuln_scanning": "vulnerability scanning",
    "open_critical_vulns": "open critical vulnerabilities",
    "mfa_coverage": "MFA weakness",
    "privileged_access": "privileged access exposure",
    "iam_governance": "IAM governance",
    "edr_coverage": "weak EDR / endpoint detection",
    "backup_frequency": "backup weakness",
    "dr_testing": "limited DR / recovery testing",
    "incident_response": "incident response maturity",
    "vendor_assessment": "vendor assessment cadence",
    "contractual_security": "contractual security requirements",
    "supply_chain_visibility": "supply-chain visibility",
    "network segmentation": "network segmentation",
    "risk_oversight": "risk oversight",
    "cyber_insurance": "cyber insurance in place",
}


def _factor_label(factor_key: str) -> str:
    """Human-readable label for a factor key (fallback: the raw key)."""
    return _FACTOR_LABELS.get(factor_key, factor_key.replace("_", " "))


@dataclass(frozen=True)
class ScenarioContribution:
    """One scenario's EAL contribution and its model-linked drivers."""

    scenario_key: str
    scenario_name: str
    contribution: float  # share of EAL (0..1), from scenario_contribution
    aal: float  # expected annual loss for this scenario (USD)
    frequency_drivers: list[str] = field(default_factory=list)
    severity_drivers: list[str] = field(default_factory=list)
    recommended_controls: list[str] = field(default_factory=list)
    linked_to_model: bool = False  # True only when the explanation is model-backed

    def to_dict(self) -> dict:
        """JSON-serialisable view for the tool result."""
        return {
            "scenario_key": self.scenario_key,
            "scenario_name": self.scenario_name,
            "contribution": round(self.contribution, 4),
            "aal": round(self.aal, 2),
            "frequency_drivers": self.frequency_drivers,
            "severity_drivers": self.severity_drivers,
            "recommended_controls": self.recommended_controls,
            "linked_to_model": self.linked_to_model,
        }


def _frequency_drivers_for(scenario_key: str, factor_scores: dict[str, float]) -> list[str]:
    """The frequency-driver factors for a scenario whose score is elevated.

    Uses the client's ACTUAL factor scores (model outputs): a factor is a
    frequency driver if its score exceeds the neutral-risk baseline (50),
    meaning it pushes the composite risk score -- and therefore lambda -- up.
    """
    drivers = []
    for factor in _SCENARIO_PROFILE[scenario_key][0]:
        score = factor_scores.get(factor, 50.0)
        if score > 50.0:
            drivers.append(_factor_label(factor))
    return drivers


def _severity_drivers_for(scenario_key: str, factor_scores: dict[str, float]) -> list[str]:
    """The severity-driver factors for a scenario whose score is elevated.

    Severity drivers are:
      1. the scenario's configured tail / scale characteristics from
         config/scenarios.yaml (sigma, revenue exponent) -- genuine model
         outputs that explain how severe this scenario's events are, and
      2. the client's resilience factors (backups, DR, incident response)
         whose score is elevated (worse containment / recovery).
    """
    drivers = []
    # 1. Config-derived severity characteristics (model outputs).
    cfg = _model_config()
    spec = next((s for s in cfg.scenarios if s.key == scenario_key), None)
    if spec is not None:
        if spec.severity.sigma is not None and spec.severity.sigma >= 1.15:
            drivers.append(f"heavy tail (severity sigma {spec.severity.sigma:.2f})")
        if spec.copula_loading >= 0.6:
            drivers.append(f"systemic correlation (loading {spec.copula_loading:.2f})")
        if spec.revenue_exponent >= 0.7:
            drivers.append("scales with revenue size")
    # 2. Client resilience factors (model outputs from the brief).
    for factor in _SCENARIO_PROFILE[scenario_key][1]:
        score = factor_scores.get(factor, 50.0)
        if score > 50.0:
            drivers.append(_factor_label(factor))
    return drivers


def _recommended_controls_for(scenario_key: str) -> list[str]:
    """The controls that map to a scenario's drivers (from the profile)."""
    return list(_SCENARIO_PROFILE[scenario_key][2])


@lru_cache(maxsize=1)
def _scenario_meta() -> dict[str, str]:
    """Scenario key -> display name, from the model config."""
    return {s.key: s.name for s in _model_config().scenarios}


def analyze_scenario_contribution(
    brief: CompanyBrief,
    n_years: int | None = None,
) -> dict:
    """Analyse each scenario's EAL contribution and its model-linked drivers.

    Parameters
        brief     the client's profile (revenue + controls)
        n_years   Monte Carlo years (default 100_000)

    Returns
        {"status": "ok", "scenarios": [...], "total_contribution": float} with
        each scenario carrying its contribution, AAL, frequency drivers,
        severity drivers, and recommended controls -- all derived from model
        outputs.  Returns {"status": "insufficient_info", ...} when the brief
        cannot be modelled.

    An explanation is only produced when the contribution is computed from the
    simulated loss distribution and the drivers come from the client's factor
    scores / scenario config.  No invented explanations.
    """
    if n_years is None:
        n_years = 100_000

    from cyberrisk.agent.tools import _guarded

    guard = _guarded(brief)
    if guard:
        return guard

    # Run the engine for this brief (deterministic, seeded).
    factor_scores = build_factor_scores(brief)
    cfg = _model_config()
    cfg_adj = cfg.model_copy(update={"firm_revenue_usd": brief.revenue_usd or cfg.firm_revenue_usd})
    result = simulate(
        cfg_adj,
        n_years=n_years,
        score=_composite_for(brief, factor_scores),
        return_events=False,
    )
    m = compute_metrics(result)
    contrib = m.scenario_contribution()
    aal = m.aal_by_scenario
    names = _scenario_meta()

    scenarios = []
    for key, share in contrib.items():
        profile = _SCENARIO_PROFILE.get(key)
        if profile is None:
            continue
        freq_drivers = _frequency_drivers_for(key, factor_scores)
        sev_drivers = _severity_drivers_for(key, factor_scores)
        recs = _recommended_controls_for(key)
        scenarios.append(
            ScenarioContribution(
                scenario_key=key,
                scenario_name=names.get(key, key),
                contribution=float(share),
                aal=float(aal[key]),
                frequency_drivers=freq_drivers,
                severity_drivers=sev_drivers,
                recommended_controls=recs,
                linked_to_model=True,
            ).to_dict()
        )

    # Sort by contribution descending so the biggest drivers come first.
    scenarios.sort(key=lambda s: s["contribution"], reverse=True)
    total = round(sum(s["contribution"] for s in scenarios), 4)
    return {
        "status": "ok",
        "scenarios": scenarios,
        "total_contribution": total,
    }


def _composite_for(brief: CompanyBrief, factor_scores: dict[str, float]) -> float:
    """Composite risk score for the brief's factor scores (model output)."""
    from cyberrisk.scoring import CompanyProfile, compute_score, load_scoring_weights

    profile = CompanyProfile(
        firm_name=brief.firm_name or "Client",
        revenue_usd=brief.revenue_usd,
        customer_records=brief.customer_records,
        previous_incidents=brief.previous_incidents,
        factor_scores=factor_scores,
    )
    scored = compute_score(profile, load_scoring_weights())
    return scored.composite_score


def scenario_contribution_summary(brief: CompanyBrief, n_years: int | None = None) -> str:
    """Client-facing summary of the scenario contribution breakdown.

    Ransomware / data breach / BEC / cloud outage contributions are reported
    with their model-linked drivers.  Only includes scenarios that actually
    contribute (share > 0).
    """
    out = analyze_scenario_contribution(brief, n_years)
    if out["status"] != "ok":
        return out  # pass through insufficient_info
    lines = ["Scenario contribution to EAL:"]
    for s in out["scenarios"]:
        lines.append(f"\n{s['scenario_name']} ({s['contribution']*100:.1f}%):")
        lines.append("  Frequency drivers:")
        for d in s["frequency_drivers"] or ["(none elevated above baseline)"]:
            lines.append(f"    - {d}")
        lines.append("  Severity drivers:")
        for d in s["severity_drivers"] or ["(no elevated severity factors)"]:
            lines.append(f"    - {d}")
        lines.append("  Recommended controls:")
        for c in s["recommended_controls"]:
            lines.append(f"    - {c}")
    return "\n".join(lines)
