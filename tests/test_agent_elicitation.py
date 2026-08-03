"""Broker-review tests: information elicitation before advice.

The senior-broker standard these tests enforce:

  * The agent must ASK about any of the 8 dimensions that is missing --
    never silently assume a default.
  * The agent must EXPLAIN why each missing piece matters.
  * The agent must NOT produce a premature recommendation while data is
    incomplete.

Scenario suite: each scenario is missing one or more of the 8 dimensions
on purpose, and we assert the agent asks the right questions.
"""

from __future__ import annotations

import pytest

from agent.consultant_agent import advise, elicit
from agent.elicitation import DIMENSIONS, REQUIRED_DIMENSIONS


def _complete_profile() -> dict[str, object]:
    """A client who has answered all 8 dimensions."""
    return {
        "industry": "Manufacturing",
        "revenue": 500_000_000,
        "customer_data_volume": 50_000,
        "technology_dependency": "High",
        "security_controls": "MFA, patching, EDR",
        "previous_incidents": 1,
        "existing_coverage": "$5M limit / $250k retention",
        "risk_appetite": "Retain up to $500k",
    }


# ---------------------------------------------------------------- the 8 dimensions
def test_all_eight_dimensions_are_defined():
    """The agent knows about all 8 information needs, each with a 'why'."""
    assert set(DIMENSIONS) == {
        "industry",
        "revenue",
        "customer_data_volume",
        "technology_dependency",
        "security_controls",
        "previous_incidents",
        "existing_coverage",
        "risk_appetite",
    }
    for d, spec in DIMENSIONS.items():
        assert spec["question"]  # asks a question
        assert spec["why"]  # explains why it matters


# ---------------------------------------------------------------- completeness
def test_complete_profile_is_complete():
    res = elicit(_complete_profile())
    assert res.complete
    assert res.missing == []


def test_missing_each_dimension_flagged():
    """Removing EACH of the 8 dimensions one at a time must be detected."""
    for dim in REQUIRED_DIMENSIONS:
        profile = _complete_profile()
        profile.pop(dim)
        res = elicit(profile)
        assert not res.complete
        assert dim in res.missing
        # the question for that dimension is asked
        assert any(q.dimension == dim for q in res.questions)


def test_empty_profile_missing_all():
    res = elicit({})
    assert not res.complete
    assert set(res.missing) == set(REQUIRED_DIMENSIONS)
    assert len(res.questions) == 8


# ---------------------------------------------------------------- 'unknown' sentinels
def test_unknown_placeholders_count_as_missing():
    """A client saying 'unknown' / 'n/a' must NOT be treated as informed."""
    for sentinel in ("unknown", "n/a", "not sure", "", None):
        profile = _complete_profile()
        profile["revenue"] = sentinel
        res = elicit(profile)
        assert not res.complete
        assert "revenue" in res.missing


def test_legitimate_zero_counts_as_provided():
    """Zero records / zero incidents is a real answer, not a gap."""
    profile = _complete_profile()
    profile["customer_data_volume"] = 0
    profile["previous_incidents"] = 0
    res = elicit(profile)
    assert res.complete  # zeros are legitimate information


# ---------------------------------------------------------------- why-it-matters
def test_questions_explain_why_each_dimension_matters():
    res = elicit({})
    for q in res.questions:
        assert q.why_it_matters  # non-empty
        # the 'why' should connect to the advice outcome
        assert len(q.why_it_matters.split()) >= 5


# ---------------------------------------------------------------- premature advice guard
def test_advise_refuses_when_incomplete():
    """With missing data, advise() must NOT return a recommendation."""

    def should_not_run(provided):
        pytest.fail("score_and_run must not be called with incomplete data")

    profile = _complete_profile()
    profile.pop("industry")
    profile.pop("risk_appetite")

    result = advise(profile, score_and_run=should_not_run)
    # returns an elicitation (questions), not a recommendation
    assert not result.complete
    assert "industry" in result.missing
    assert "risk_appetite" in result.missing
    # the client-facing response asks questions and does not conclude
    text = result.formatted_response().lower()
    assert "before i can advise" in text
    assert "have not drawn any conclusions" in text


def test_advise_runs_when_complete():
    """Only with complete data does advise() proceed to recommendations."""

    def score_and_run(provided):
        assert provided["industry"] == "Manufacturing"  # full profile passed through
        from tests.test_consultant_agent import _scored_and_metrics

        return _scored_and_metrics()

    profile = _complete_profile()
    result = advise(profile, score_and_run=score_and_run)
    # complete -> a recommendation, not questions
    assert hasattr(result, "recommendations")
    assert len(result.recommendations) >= 1


# ---------------------------------------------------------------- scenario suite
SCENARIOS = [
    ("new_business_no_info", {}),
    ("manufacturer_no_controls", {"industry": "Manufacturing", "revenue": 500_000_000}),
    (
        "bank_no_appetite_no_incidents",
        {
            "industry": "Financial Services",
            "revenue": 2_000_000_000,
            "customer_data_volume": 1_000_000,
            "technology_dependency": "Very high",
            "security_controls": "Strong",
            "existing_coverage": "$10M limit",
        },
    ),
    (
        "healthcare_no_revenue_no_coverage",
        {
            "industry": "Healthcare",
            "customer_data_volume": 500_000,
            "technology_dependency": "High",
            "security_controls": "MFA, patching",
            "previous_incidents": 2,
            "risk_appetite": "Low",
        },
    ),
    (
        "retail_only_basics",
        {
            "industry": "Retail",
            "revenue": 750_000_000,
            "customer_data_volume": 100_000,
            "technology_dependency": "Medium",
        },
    ),
]


@pytest.mark.parametrize("name,provided", SCENARIOS)
def test_scenario_asks_for_every_missing_dimension(name, provided):
    """Each missing-info scenario must ask about every gap, and explain why."""
    res = elicit(provided)
    assert not res.complete
    # asks about every dimension that is missing
    missing = set(REQUIRED_DIMENSIONS) - set(provided)
    assert set(res.missing) == missing
    for q in res.questions:
        assert q.why_it_matters  # explains why it matters


@pytest.mark.parametrize("name,provided", SCENARIOS)
def test_scenario_no_premature_conclusions(name, provided):
    """No scenario may produce advice while information is missing."""
    result = advise(
        provided,
        score_and_run=lambda p: pytest.fail("must not score with missing info"),
    )
    assert not result.complete
    text = result.formatted_response().lower()
    assert "i have not drawn any conclusions" in text


# ---------------------------------------------------------------- the 8 dimensions coverage
def test_coverage_of_all_eight_dimensions_across_scenarios():
    """Across the scenario suite, every one of the 8 dimensions is tested as missing."""
    seen_missing = set()
    for _name, provided in SCENARIOS:
        res = elicit(provided)
        seen_missing.update(res.missing)
    assert set(REQUIRED_DIMENSIONS) <= seen_missing
