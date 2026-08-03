"""Risk-appetite validation tests."""

import pytest

from agent.risk_appetite import parse_retention, validate_appetite


# ---------------------------------------------------------------- parsing
def test_parse_dollar_with_unit():
    assert parse_retention("$1M retention") == pytest.approx(1_000_000)
    assert parse_retention("retain 500k") == pytest.approx(500_000)
    assert parse_retention("$2m limit") == pytest.approx(2_000_000)
    assert parse_retention("$250,000") == pytest.approx(250_000)


def test_parse_bare_number():
    assert parse_retention("we retain 750000") == pytest.approx(750_000)


def test_parse_as_little_as_possible_is_zero():
    assert parse_retention("as little as possible") == pytest.approx(0.0)
    assert parse_retention("none") == pytest.approx(0.0)
    assert parse_retention("minimal") == pytest.approx(0.0)


def test_parse_vague_returns_none():
    assert parse_retention("we keep our premium low") is None
    assert parse_retention("") is None
    assert parse_retention("not sure") is None


# ---------------------------------------------------------------- verdicts
def test_sensible_retention_below_twice_eal():
    v = validate_appetite(50_000, eal=5_000_000, es_99=50_000_000)
    assert v.rating == "sensible"
    assert v.is_sane
    assert "ordinary-year losses" in v.message


def test_high_retention_between_eal_and_es():
    v = validate_appetite(20_000_000, eal=5_000_000, es_99=50_000_000)
    assert v.rating == "high"
    assert not v.is_sane
    assert "high side" in v.message


def test_self_insuring_retention_above_es():
    v = validate_appetite(60_000_000, eal=5_000_000, es_99=50_000_000)
    assert v.rating == "self-insuring"
    assert not v.is_sane
    assert "self-insuring" in v.message


def test_unparseable_appetite_asks_for_figure():
    v = validate_appetite(None, eal=5_000_000, es_99=50_000_000)
    assert v.rating == "unparseable"
    assert "dollar figure" in v.message


def test_boundary_exactly_twice_eal_is_sensible():
    v = validate_appetite(10_000_000, eal=5_000_000, es_99=50_000_000)
    assert v.rating == "sensible"


def test_boundary_exactly_es_is_high_not_self_insuring():
    v = validate_appetite(50_000_000, eal=5_000_000, es_99=50_000_000)
    assert v.rating == "high"


# ---------------------------------------------------------------- advise wiring
def test_advise_appends_appetite_verdict():
    from agent.consultant_agent import advise
    from tests.test_consultant_agent import _scored_and_metrics

    profile = {
        "industry": "Manufacturing",
        "revenue": 500_000_000,
        "customer_data_volume": 50_000,
        "technology_dependency": "High",
        "security_controls": "MFA, patching",
        "previous_incidents": 1,
        "existing_coverage": "$5M limit",
        "risk_appetite": "retain $250k",
    }
    rec = advise(
        profile,
        score_and_run=lambda p: _scored_and_metrics(),
        risk_appetite_text="we retain $50k",
    )
    assert hasattr(rec, "recommendations")
    assert any("Risk appetite:" in r for r in rec.recommendations)


def test_advise_vague_appetite_still_returns_recommendation():
    """A vague appetite shouldn't block advice, but should flag the gap."""
    from agent.consultant_agent import advise
    from tests.test_consultant_agent import _scored_and_metrics

    profile = {
        "industry": "Manufacturing",
        "revenue": 500_000_000,
        "customer_data_volume": 50_000,
        "technology_dependency": "High",
        "security_controls": "MFA, patching",
        "previous_incidents": 1,
        "existing_coverage": "$5M limit",
        "risk_appetite": "we keep our premium low",
    }
    rec = advise(
        profile,
        score_and_run=lambda p: _scored_and_metrics(),
        risk_appetite_text="we keep our premium low",
    )
    assert any("Risk appetite:" in r for r in rec.recommendations)
    assert any("dollar figure" in r for r in rec.recommendations)
