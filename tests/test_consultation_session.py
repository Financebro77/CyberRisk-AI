"""Consultation session (follow-up dialogue) tests."""

import pytest

from agent.elicitation import ConsultationSession, MAX_DIALOGUE_TURNS, DIMENSIONS

ALL = set(DIMENSIONS)


def _full_answers() -> dict:
    return {
        "industry": "Manufacturing",
        "revenue": 500_000_000,
        "customer_data_volume": 50_000,
        "technology_dependency": "High",
        "security_controls": "MFA, patching",
        "previous_incidents": 1,
        "existing_coverage": "$5M limit",
        "risk_appetite": "retain $250k",
    }


def test_session_completes_in_few_turns():
    s = ConsultationSession()
    # answer in two chunks
    half = list(ALL)[:4]
    s.reply({k: _full_answers()[k] for k in half})
    assert not s.complete
    assert set(s.missing) == ALL - set(half)
    s.reply({k: _full_answers()[k] for k in ALL if k not in half})
    assert s.complete
    assert s.missing == []


def test_session_reasks_only_still_missing():
    """After answering some dimensions, only the gaps are re-asked."""
    s = ConsultationSession()
    r = s.reply({"industry": "Bank"})
    assert "industry" not in r.missing
    assert "revenue" in r.missing
    assert len(r.questions) == 7  # only the still-missing get questions


def test_session_merges_across_turns():
    """Answers accumulate; later turns don't clobber earlier ones."""
    s = ConsultationSession()
    s.reply({"industry": "Bank", "revenue": 2_000_000_000})
    s.reply({"customer_data_volume": 1_000_000})
    assert s.answers["industry"] == "Bank"
    assert s.answers["revenue"] == 2_000_000_000
    assert s.answers["customer_data_volume"] == 1_000_000


def test_unknown_pushback_does_not_consume_turn():
    """Saying 'unknown' to a question keeps it missing (and counts a turn)."""
    s = ConsultationSession()
    r = s.reply({"industry": "unknown"})
    assert "industry" in r.missing  # not accepted


def test_vague_appetite_is_pushed_back():
    """"We want to keep our premium low" is NOT a usable appetite -- re-ask."""
    s = ConsultationSession()
    s.reply(_full_answers_without("risk_appetite"))
    r = s.reply({"risk_appetite": "we want to keep our premium low"})
    assert "risk_appetite" in r.missing  # vague -> still missing
    assert not s.complete
    # a real figure completes it
    r2 = s.reply({"risk_appetite": "retain $1.5M"})
    assert r2.complete


def test_vague_appetite_blocks_completion_even_if_else_complete():
    s = ConsultationSession()
    s.reply(_full_answers_without("risk_appetite"))
    s.reply({"risk_appetite": "as little as possible"})  # parseable as 0 -> valid
    assert s.complete  # "as little as possible" IS a usable appetite (retain ~0)


def _full_answers_without(exclude: str) -> dict:
    return {k: v for k, v in _full_answers().items() if k != exclude}


def test_legitimate_zero_accepted_in_session():
    s = ConsultationSession()
    s.reply({"customer_data_volume": 0, "previous_incidents": 0})
    assert "customer_data_volume" not in s.missing
    assert "previous_incidents" not in s.missing


def test_session_blocks_after_max_turns():
    s = ConsultationSession(max_turns=3)
    for _ in range(3):
        s.reply({})  # no real info
    assert s.blocked
    assert not s.complete
    assert "rather not guess" in s.formatted_response()


def test_session_does_not_block_when_complete_before_max():
    s = ConsultationSession(max_turns=3)
    s.reply(_full_answers())  # all at once
    assert s.complete
    assert not s.blocked


def test_default_max_turns_is_sane():
    assert 3 <= MAX_DIALOGUE_TURNS <= 10


def test_formatted_response_complete():
    s = ConsultationSession()
    s.reply(_full_answers())
    text = s.formatted_response()
    assert "I now have what I need" in text


def test_formatted_response_incomplete_asks_only_missing():
    s = ConsultationSession()
    s.reply({"industry": "Retail"})
    text = s.formatted_response()
    # explains what's missing and that no conclusions are drawn
    assert "I have not drawn any conclusions yet" in text
    assert "revenue" in text  # a still-missing dimension is asked about
    assert "7" in text  # "I still need 7 more pieces of information"
