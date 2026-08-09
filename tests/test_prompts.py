"""System prompt + senior-consultant directives tests.

Verifies the consultant persona is present in the system prompt and that the
senior-commercial-consultant directives (business language, Monte Carlo
interpretation, EAL/VaR/ES, incidents, standards, assumptions, uncertainty,
quant-vs-judgement, tone, no-fabrication) are instructed.  These are prompt
contracts — if a directive is removed, the consultant loses the behaviour.
"""

from __future__ import annotations


from cyberrisk.agent.prompts import (
    RAG_RULES,
    SENIOR_CONSULTANT_DIRECTIVES,
    SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# System prompt baseline
# ---------------------------------------------------------------------------


def test_system_prompt_has_hard_rules():
    """The quantitative grounding rules are still present."""
    assert "NEVER invent a number" in SYSTEM_PROMPT
    assert "Model Limitations" in SYSTEM_PROMPT
    assert "Expected Shortfall" in SYSTEM_PROMPT


def test_system_prompt_has_tool_references():
    for tool in (
        "assess_company_risk",
        "run_loss_simulation",
        "analyse_insurance_structure",
        "run_control_improvement_scenario",
    ):
        assert tool in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Senior consultant directives
# ---------------------------------------------------------------------------


def test_directives_present():
    assert SENIOR_CONSULTANT_DIRECTIVES


def test_directives_business_language():
    assert "BUSINESS LANGUAGE" in SENIOR_CONSULTANT_DIRECTIVES
    assert "CFO" in SENIOR_CONSULTANT_DIRECTIVES


def test_directives_monte_carlo_interpretation():
    assert "MONTE CARLO" in SENIOR_CONSULTANT_DIRECTIVES
    assert "100,000" in SENIOR_CONSULTANT_DIRECTIVES


def test_directives_eal_var_es_business_terms():
    assert "EAL" in SENIOR_CONSULTANT_DIRECTIVES
    assert "average annual cost to expect" in SENIOR_CONSULTANT_DIRECTIVES
    assert "loss you stay under" in SENIOR_CONSULTANT_DIRECTIVES
    assert "tail you should insure" in SENIOR_CONSULTANT_DIRECTIVES


def test_directives_insurance_and_controls():
    assert "INSURANCE STRUCTURES" in SENIOR_CONSULTANT_DIRECTIVES
    assert "security control improvements" in SENIOR_CONSULTANT_DIRECTIVES.lower()
    assert "run_control_improvement_scenario" in SENIOR_CONSULTANT_DIRECTIVES


def test_directives_historical_incidents():
    assert "HISTORICAL INCIDENTS" in SENIOR_CONSULTANT_DIRECTIVES
    assert "search_incidents" in SENIOR_CONSULTANT_DIRECTIVES
    assert "NEVER fabricate an incident" in SENIOR_CONSULTANT_DIRECTIVES


def test_directives_industry_standards():
    assert "INDUSTRY STANDARDS" in SENIOR_CONSULTANT_DIRECTIVES
    assert "NIST CSF" in SENIOR_CONSULTANT_DIRECTIVES
    assert "ISO 27001" in SENIOR_CONSULTANT_DIRECTIVES


def test_directives_assumptions_and_uncertainty():
    assert "MODEL ASSUMPTIONS" in SENIOR_CONSULTANT_DIRECTIVES
    assert "UNCERTAINTY" in SENIOR_CONSULTANT_DIRECTIVES
    assert "assumptions, not facts" in SENIOR_CONSULTANT_DIRECTIVES


def test_directives_quant_vs_judgement():
    assert "PROFESSIONAL JUDGEMENT" in SENIOR_CONSULTANT_DIRECTIVES
    assert "[MODEL OUTPUT]" in SENIOR_CONSULTANT_DIRECTIVES
    assert "[INDUSTRY EVIDENCE]" in SENIOR_CONSULTANT_DIRECTIVES
    assert "Never present a judgement as a measured fact" in SENIOR_CONSULTANT_DIRECTIVES


def test_directives_professional_tone():
    assert "EXECUTIVE-READY" in SENIOR_CONSULTANT_DIRECTIVES
    assert "CONSULTING TONE" in SENIOR_CONSULTANT_DIRECTIVES
    assert "calm" in SENIOR_CONSULTANT_DIRECTIVES


def test_directives_no_fabrication():
    assert "NEVER FABRICATE REGULATORY GUIDANCE" in SENIOR_CONSULTANT_DIRECTIVES
    assert "do not invent it" in SENIOR_CONSULTANT_DIRECTIVES


# ---------------------------------------------------------------------------
# RAG rules still present (consultant still attributes + differentiates)
# ---------------------------------------------------------------------------


def test_rag_rules_present():
    assert "RETRIEVED KNOWLEDGE" in RAG_RULES
    assert "[citation:" in RAG_RULES


# ---------------------------------------------------------------------------
# Controller builds the full persona
# ---------------------------------------------------------------------------


def test_controller_system_prompt_includes_directives():
    from cyberrisk.agent.agent_controller import CyberRiskAgent

    # The constructor builds the LLM client eagerly (`client or factory()`),
    # so pass a stub — no API key needed, and _init_system never calls it.
    class _StubClient:
        def __init__(self) -> None:
            self.name = "stub"

    agent = CyberRiskAgent(client=_StubClient())
    system = agent.memory.get()[0]["content"]
    assert "SENIOR COMMERCIAL CONSULTANT" in system
    assert "BUSINESS LANGUAGE" in system
    assert "NEVER invent a number" in system
