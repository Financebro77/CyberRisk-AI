"""Guardrail tests for the demo-company fabrication capability.

Deterministic, no LLM, no network.  These lock in the safety boundary the
user specified: fictional companies only, safe sectors only (critical
national infrastructure excluded in code), no PII, no real-firm names,
chat-only output (never a downloadable report), and standard engine metric
keys so the post-guard can validate the LLM's quoted figures.
"""

from __future__ import annotations

import random
import re

import pytest

from cyberrisk.agent.demo import (
    DEMO_DISCLAIMER,
    EXCLUDED_SECTORS,
    FICTIONAL_NAMES,
    SAFE_SECTORS,
    randomize_demo_brief,
)
from cyberrisk.agent.schemas import CompanyBrief
from cyberrisk.agent.tools import generate_demo_assessment

# A modest blocklist of very well-known real firms: a generated demo name must
# never collide with these.
REAL_FIRM_BLOCKLIST = (
    "google", "microsoft", "amazon", "apple", "jpmorgan", "goldman",
    "walmart", "tesla", "meta", "facebook", "boeing", "lockheed",
    "exxon", "chevron", "shell", "hsbc", "citi", "barclays",
    "nato", "nsa", "cia", "fbi",
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[ -.]?)?\(?\d{3}\)?[ -.]?\d{3}[ -.]?\d{4}")
_ADDR_WORDS = ("street", "avenue", " boulevard", " lane", " road", "drive ", "postcode")


def _sample_briefs(n: int = 60) -> list[CompanyBrief]:
    random.seed(7)
    return [randomize_demo_brief() for _ in range(n)]


# ---------------------------------------------------------------------------
# Generator guardrails
# ---------------------------------------------------------------------------


def test_randomize_demo_brief_is_complete_enough_to_model():
    """Every fabricated brief passes the completeness guard (revenue + controls)."""
    for brief in _sample_briefs():
        assert brief.missing_for_simulation() == []
        assert brief.revenue_usd and brief.revenue_usd > 0
        assert brief.security_controls and brief.security_controls.strip()


def test_demo_sector_is_always_in_safe_allow_list():
    """Critical-national-infrastructure sectors can never be fabricated."""
    for brief in _sample_briefs(200):
        assert brief.industry in SAFE_SECTORS
        assert brief.industry.lower() not in EXCLUDED_SECTORS


def test_demo_firm_name_is_fictional_and_never_a_real_firm():
    """Names come from the curated fictional pool and avoid known real firms.

    Whole-word matching only: a blocklist term must appear as a complete word,
    so 'Caledonia Commercial Trust' (whose 'cia' sits inside 'Commercial') does
    not false-positive, while a real 'Citi Retail' would still be caught.
    """
    for brief in _sample_briefs(200):
        name = brief.firm_name
        assert name in FICTIONAL_NAMES
        low = name.lower()
        assert not any(re.search(rf"\b{re.escape(real)}\b", low) for real in REAL_FIRM_BLOCKLIST), name


def test_demo_brief_contains_no_pii():
    """No emails, phone numbers, or street addresses in any fabricated field."""
    for brief in _sample_briefs():
        for field in brief.model_dump().values():
            if isinstance(field, str):
                assert not _EMAIL_RE.search(field), field
                assert not _PHONE_RE.search(field), field
                assert not any(w in field.lower() for w in _ADDR_WORDS), field


# ---------------------------------------------------------------------------
# generate_demo_assessment (the tool)
# ---------------------------------------------------------------------------


def test_generate_demo_assessment_returns_standard_metrics_and_demo_tag():
    out = generate_demo_assessment(n_years=20_000)
    assert out["status"] == "ok"
    assert out["demo"] is True
    assert out["disclaimer"] == DEMO_DISCLAIMER
    assert out["firm_name"] in FICTIONAL_NAMES
    # Standard metric keys the post-guard validates the LLM's figures against.
    for key in ("eal", "var_95", "var_99", "es_95", "es_99", "aal_by_scenario"):
        assert key in out, key
    assert "client_retained_loss" in out
    assert out["insurance"]["status"] == "ok"
    # Chat-only: the demo path never produces a downloadable report.
    assert "report_path" not in out


def test_generate_demo_assessment_requested_sector_honoured():
    out = generate_demo_assessment(sector="Healthcare", n_years=20_000)
    assert out["status"] == "ok"
    assert out["industry"] == "Healthcare"


def test_generate_demo_assessment_refuses_excluded_sector():
    out = generate_demo_assessment(sector="Power", n_years=20_000)
    assert out["status"] == "error"
    assert "excluded" in out["error"].lower()
    assert "Power" in out["error"]


def test_generate_demo_assessment_unknown_sector_refused():
    out = generate_demo_assessment(sector="Banks", n_years=20_000)
    assert out["status"] == "error"
