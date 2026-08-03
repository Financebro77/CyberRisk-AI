"""Tests for the actuarial-standard VaR / Expected Shortfall explanations.

The agent must explain every risk measure with the full
(confidence level, time horizon, loss definition) triple, and must never
state "there is a 1% chance you lose exactly this amount" -- VaR is a
threshold the loss stays at or below with the confidence level, not a point
mass.
"""

from __future__ import annotations

import pytest

from cyberrisk.agent.agent_controller import CyberRiskAgent
from cyberrisk.agent.risk_explanation import (
    contains_forbidden_var_wording,
    explain_expected_shortfall,
    explain_risk_measures,
    explain_var,
)

VAR_EXAMPLE = 30_000_000.0  # the $30M example from the spec
ES_EXAMPLE = 47_300_000.0  # the $47.3M example from the spec


# ---------------------------------------------------------------------------
# explain_var: confidence + horizon + loss definition in every output
# ---------------------------------------------------------------------------


def test_var_explanation_includes_all_three_components():
    """Every VaR explanation names confidence level, time horizon, and loss definition."""
    e = explain_var(VAR_EXAMPLE)
    # Confidence level
    assert e.confidence == 0.99
    assert "99%" in e.sentence
    # Time horizon
    assert e.horizon == "1-year"
    assert "annual" in e.sentence
    # Loss definition
    assert e.loss_definition
    assert "loss" in e.loss_definition.lower()
    # The exact example wording from the spec.
    assert (
        "99% annual aggregate total economic loss before insurance recovery "
        "VaR is $30.0M. This means that based on the simulated annual loss "
        "distribution, only 1% of simulated years exceed this amount."
    ) == e.sentence


def test_var_explanation_is_a_threshold_not_a_point_mass():
    """VaR is the loss only a share of simulated years EXCEED -- never 'exactly'."""
    e = explain_var(VAR_EXAMPLE)
    assert "only 1% of simulated years exceed this amount" in e.sentence
    # The forbidden phrasing must be absent.
    assert not contains_forbidden_var_wording(e.sentence)


def test_var_explanation_confidence_variants():
    """95% and 99% VaR both carry the correct exceedance tail."""
    e95 = explain_var(VAR_EXAMPLE, confidence=0.95)
    assert "95%" in e95.sentence
    assert "only 5% of simulated years exceed this amount" in e95.sentence
    e99 = explain_var(VAR_EXAMPLE, confidence=0.99)
    assert "only 1% of simulated years exceed this amount" in e99.sentence


def test_var_explanation_loss_definition_custom():
    """A custom loss definition flows through to the sentence."""
    e = explain_var(
        VAR_EXAMPLE,
        loss_definition="client retained loss after insurance",
    )
    assert "client retained loss after insurance" in e.sentence


def test_var_explanation_rejects_bad_input():
    with pytest.raises(ValueError):
        explain_var(-1.0)
    with pytest.raises(ValueError):
        explain_var(VAR_EXAMPLE, confidence=1.0)


# ---------------------------------------------------------------------------
# explain_expected_shortfall
# ---------------------------------------------------------------------------


def test_es_explanation_is_average_of_worst_tail():
    """ES is the average annual loss in the worst (1 - confidence) tail."""
    e = explain_expected_shortfall(ES_EXAMPLE)
    assert e.confidence == 0.99
    assert e.horizon == "1-year"
    assert (
        "The 99% Expected Shortfall is $47.3M, representing the average annual "
        "loss in the worst 1% of simulated outcomes (total economic loss before "
        "insurance recovery)."
    ) == e.sentence


def test_es_explanation_never_implies_point_mass():
    e = explain_expected_shortfall(ES_EXAMPLE)
    assert not contains_forbidden_var_wording(e.sentence)


def test_es_explanation_custom_definition_and_confidence():
    e = explain_expected_shortfall(ES_EXAMPLE, confidence=0.95)
    assert "95%" in e.sentence
    assert "worst 5% of simulated outcomes" in e.sentence


def test_es_explanation_rejects_bad_input():
    with pytest.raises(ValueError):
        explain_expected_shortfall(-1.0)
    with pytest.raises(ValueError):
        explain_expected_shortfall(ES_EXAMPLE, confidence=0.0)


# ---------------------------------------------------------------------------
# explain_risk_measures bundle
# ---------------------------------------------------------------------------


def test_risk_measures_bundle_returns_var_and_es_sentences():
    r = explain_risk_measures(VAR_EXAMPLE, ES_EXAMPLE, var_95=12_000_000.0, es_95=18_000_000.0)
    assert set(r) == {"var_99", "es_99", "var_95", "es_95"}
    for sentence in r.values():
        assert contains_forbidden_var_wording(sentence) is False


def test_risk_measures_bundle_optional_95s():
    r = explain_risk_measures(VAR_EXAMPLE, ES_EXAMPLE)
    assert set(r) == {"var_99", "es_99"}


# ---------------------------------------------------------------------------
# Forbidden phrasing guard
# ---------------------------------------------------------------------------


def test_forbidden_wording_guard():
    # The classic mis-statement is flagged.
    assert contains_forbidden_var_wording("There is a 1% chance you lose exactly this amount.")
    assert contains_forbidden_var_wording("There is a 5% probability you lose exactly this amount.")
    # Correct actuarial wording is not flagged.
    assert not contains_forbidden_var_wording(
        "99% annual aggregate VaR is $30M: only 1% of simulated years exceed this amount."
    )
    assert not contains_forbidden_var_wording(
        "The 99% Expected Shortfall is $47.3M, the average annual loss in the worst 1%."
    )
    assert not contains_forbidden_var_wording("")


# ---------------------------------------------------------------------------
# Prompt / controller integration
# ---------------------------------------------------------------------------


def test_system_prompt_requires_actuarial_var_standard():
    from cyberrisk.agent.prompts import GROUNDING_REMINDER, SYSTEM_PROMPT

    # The system prompt mandates the triple and the exact sentence pattern.
    assert "99% annual aggregate VaR is $30M" in SYSTEM_PROMPT
    assert "only 1% of simulated years exceed this amount" in SYSTEM_PROMPT
    assert "The 99% Expected Shortfall is $47.3M" in SYSTEM_PROMPT
    assert "NEVER state \"There is a 1% chance you lose exactly this amount.\"" in SYSTEM_PROMPT
    # The grounding reminder enforces the rule at summary time.
    assert "there is a 1% chance you lose exactly this amount" in GROUNDING_REMINDER
    assert "confidence level" in GROUNDING_REMINDER


def test_controller_exposes_risk_explanations():
    r = CyberRiskAgent.explain_risk_measures(VAR_EXAMPLE, ES_EXAMPLE)
    assert set(r) == {"var_99", "es_99"}
    assert "only 1% of simulated years exceed this amount" in r["var_99"]
    assert "worst 1% of simulated outcomes" in r["es_99"]
