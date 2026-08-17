"""Demo-company fabrication for the consultant agent (guardrailed).

When a user explicitly asks for a demo / demonstration / example company,
``generate_demo_assessment`` (in tools.py) fabricates a fictional profile and
runs the REAL engine on it -- fake company, real score math.  This module is
the fabrication layer and the safety boundary:

    * Safe sectors only.  Critical-national-infrastructure sectors (defense,
      intelligence, nuclear, power grid, weapons) are excluded IN CODE, so
      the tool physically cannot produce a fake critical-infrastructure
      profile.  ``SAFE_SECTORS`` is the allow-list; ``EXCLUDED_SECTORS`` is
      the block-list the guardrail tests assert against.
    * Fictional names only.  ``FICTIONAL_NAMES`` is a curated, clearly-made-up
      pool; fabricated profiles never carry a real firm's name.
    * No PII.  The generator emits company-level fields only -- no names,
      emails, phones, or addresses of real people.
    * Complete briefs.  ``randomize_demo_brief`` always returns revenue and a
      security-controls description, so the fabricated profile passes the
      engine's completeness guard.
"""

from __future__ import annotations

import random

from cyberrisk.agent.schemas import CompanyBrief, PolicyInput

# DEMO marker surfaced in every fabricated assessment and echoed verbatim in
# the LLM's reply, so a demo result can never be mistaken for a real one.
DEMO_DISCLAIMER = (
    "DEMO — fictional company data for demonstration only. "
    "No real company or person is described."
)

# Sectors the fabricator may model.  Energy is deliberately a non-grid trading
# firm (see BASE_PROFILES) -- grid / utility operations are critical national
# infrastructure and are excluded.
SAFE_SECTORS: tuple[str, ...] = (
    "Healthcare",
    "Financial Services",
    "Manufacturing",
    "Retail",
    "Energy",
    "Logistics",
)

# Block-list asserted by the guardrail tests: fabricated profiles must never
# touch these.  Keeping it in code means the restriction survives a prompt
# edit.
EXCLUDED_SECTORS: tuple[str, ...] = (
    "defense",
    "intelligence",
    "nuclear",
    "power",
    "grid",
    "weapons",
    "military",
    "government",
)

# Curated, clearly-fictional firm names (non-trademarked).  A demo press picks
# one, so the name never collides with a real company.
FICTIONAL_NAMES: tuple[str, ...] = (
    "Halcyon Health Group",
    "Northwind Systems",
    "Caledonia Commercial Trust",
    "Meridian Market Group",
    "Aurelia Energy Trading",
    "Stonebridge Financial Services",
    "Vantage Manufacturing",
    "Clearwater Logistics",
    "Harborview Retail",
    "Summit Insurance Partners",
)

# Base profiles: one per safe sector, differentiated by industry, revenue,
# data volume, technology dependency, and security posture (mapped through the
# same control-keyword scanner the client brief uses, so posture changes the
# score).
BASE_PROFILES: list[dict] = [
    {
        "industry": "Healthcare",
        "revenue_usd": 850_000_000,
        "customer_records": 2_100_000,
        "technology_dependency": "High",
        "posture": {
            "mfa": "Comprehensive",
            "segmentation": "Segmented",
            "backups": "Daily",
            "vuln": "Monthly",
            "ir": "Documented",
        },
        "existing_coverage": "$25M limit, $1M retention",
        "risk_appetite": "Retain up to $2M",
        "policy_limit": 25_000_000,
        "retention": 1_000_000,
    },
    {
        "industry": "Financial Services",
        "revenue_usd": 1_600_000_000,
        "customer_records": 900_000,
        "technology_dependency": "High",
        "posture": {
            "mfa": "Comprehensive",
            "segmentation": "Segmented",
            "backups": "Continuous",
            "vuln": "Continuous",
            "ir": "Tested",
        },
        "existing_coverage": "$50M limit, $2M retention",
        "risk_appetite": "Retain up to $3M",
        "policy_limit": 50_000_000,
        "retention": 2_000_000,
    },
    {
        "industry": "Manufacturing",
        "revenue_usd": 520_000_000,
        "customer_records": 150_000,
        "technology_dependency": "Moderate",
        "posture": {
            "mfa": "Partial",
            "segmentation": "Basic",
            "backups": "Daily",
            "vuln": "Monthly",
            "ir": "Informal",
        },
        "existing_coverage": "$10M limit, $500k retention",
        "risk_appetite": "Retain up to $1.5M",
        "policy_limit": 10_000_000,
        "retention": 500_000,
    },
    {
        "industry": "Retail",
        "revenue_usd": 1_100_000_000,
        "customer_records": 5_200_000,
        "technology_dependency": "High",
        "posture": {
            "mfa": "Partial",
            "segmentation": "Basic",
            "backups": "Daily",
            "vuln": "Weekly",
            "ir": "Documented",
        },
        "existing_coverage": "$20M limit, $750k retention",
        "risk_appetite": "Retain up to $2M",
        "policy_limit": 20_000_000,
        "retention": 750_000,
    },
    {
        # Energy TRADING, deliberately not a grid/utility operator -- power
        # grid is critical national infrastructure and is excluded.
        "industry": "Energy",
        "revenue_usd": 3_200_000_000,
        "customer_records": 1_400_000,
        "technology_dependency": "High",
        "posture": {
            "mfa": "Comprehensive",
            "segmentation": "Segmented",
            "backups": "Continuous",
            "vuln": "Continuous",
            "ir": "Tested",
        },
        "existing_coverage": "$30M limit, $1.5M retention",
        "risk_appetite": "Retain up to $2.5M",
        "policy_limit": 30_000_000,
        "retention": 1_500_000,
    },
    {
        "industry": "Logistics",
        "revenue_usd": 700_000_000,
        "customer_records": 400_000,
        "technology_dependency": "Moderate",
        "posture": {
            "mfa": "Partial",
            "segmentation": "Basic",
            "backups": "Daily",
            "vuln": "Weekly",
            "ir": "Documented",
        },
        "existing_coverage": "$15M limit, $1M retention",
        "risk_appetite": "Retain up to $1.5M",
        "policy_limit": 15_000_000,
        "retention": 1_000_000,
    },
]

_MFA_LEVELS = ("Comprehensive", "Partial", "None")
_VULN_CADENCES = ("Continuous", "Weekly", "Monthly")
_POLICY_LIMIT_FACTORS = (0.5, 0.75, 1.0, 1.5, 2.0)
_RETENTION_FACTORS = (0.25, 0.5, 0.75, 1.0, 1.5)


def _round_to(n: float, step: float) -> float:
    return max(step, round(n / step) * step)


def _pick_base(sector: str | None = None) -> dict:
    """A base profile, optionally constrained to one safe sector."""
    if sector is None:
        return random.choice(BASE_PROFILES)
    for base in BASE_PROFILES:
        if base["industry"].lower() == sector.strip().lower():
            return base
    raise ValueError(f"Unknown demo sector {sector!r}")


def _controls_text(posture: dict) -> str:
    """Assemble the free-text controls description the score scanner reads.

    Phrasing is chosen so the scanner maps each level to the intended rating:
    'comprehensive'/'continuous'/'tested' read as strong, 'partial'/'basic'/
    'daily' as neutral, 'informal' as weak.
    """
    return (
        f"MFA coverage is {posture['mfa'].lower()}, "
        f"network segmentation is {posture['segmentation'].lower()}, "
        f"backups are {posture['backups'].lower()}, "
        f"vulnerability scanning is {posture['vuln'].lower()}, "
        f"incident response is {posture['ir'].lower()}"
    )


def _brief_from_base(base: dict) -> CompanyBrief:
    """Jitter a base profile into a fresh fictional CompanyBrief.

    Every press produces a different company: revenue / data volumes /
    headcount / incident history / controls all jitter, mirroring the frontend
    demo randomization.
    """
    posture = dict(base["posture"])
    # Vary a control now and then so the risk score can move between presses.
    if random.random() < 0.4:
        posture["mfa"] = random.choice(_MFA_LEVELS)
    if random.random() < 0.3:
        posture["vuln"] = random.choice(_VULN_CADENCES)

    return CompanyBrief(
        firm_name=random.choice(FICTIONAL_NAMES),
        industry=base["industry"],
        revenue_usd=_round_to(base["revenue_usd"] * random.uniform(0.7, 1.5), 1_000_000),
        customer_records=max(1_000, round(base["customer_records"] * random.uniform(0.7, 1.4))),
        technology_dependency=base["technology_dependency"],
        security_controls=_controls_text(posture),
        previous_incidents=random.randint(0, 4),
        existing_coverage=base["existing_coverage"],
        risk_appetite=base["risk_appetite"],
    )


def _policy_from_base(base: dict) -> PolicyInput:
    """The demo insurance structure, jittered from the base profile."""
    limit = _round_to(base["policy_limit"] * random.choice(_POLICY_LIMIT_FACTORS), 1_000_000)
    retention = _round_to(base["retention"] * random.choice(_RETENTION_FACTORS), 50_000)
    return PolicyInput(
        per_occurrence_deductible=retention,
        annual_aggregate_limit=limit,
    )


def demo_company(sector: str | None = None) -> tuple[CompanyBrief, PolicyInput]:
    """Fabricate a fictional demo company + policy from ONE base profile.

    Returns them as a pair so the tool runs the engine on a single coherent
    profile (the brief and the policy always come from the same base).
    """
    base = _pick_base(sector)
    return _brief_from_base(base), _policy_from_base(base)


def randomize_demo_brief(sector: str | None = None) -> CompanyBrief:
    """A complete fictional CompanyBrief (passes the engine's completeness guard).

    Public helper kept separate from the tool so tests can assert the
    generator's guardrails directly.
    """
    return demo_company(sector=sector)[0]
