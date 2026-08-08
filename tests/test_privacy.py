"""Tests for the privacy & data-protection layer (src/cyberrisk/privacy.py).

Covers:
    * config loading (safe defaults when the file is missing/malformed)
    * PII detection (emails, phones, names, paths, secrets)
    * PII redaction
    * sanitised logging (secrets always scrubbed; PII scrubbed when the
      policy disables sensitive logging)
    * the input-boundary guard (block secrets, redact personal data)
"""

from __future__ import annotations

import logging

import pytest

from cyberrisk import privacy


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def test_privacy_config_defaults_are_safe():
    """Missing config -> the safest defaults (privacy ON)."""
    policy = privacy.PrivacyPolicy.from_mapping({})
    assert policy.privacy_mode is True
    assert policy.allow_personal_data is False
    assert policy.allow_client_data_storage is False
    assert policy.log_sensitive_information is False


def test_privacy_config_from_yaml():
    policy = privacy.PrivacyPolicy.from_mapping(
        {
            "privacy_mode": "false",
            "allow_personal_data": "false",
            "log_sensitive_information": "false",
        }
    )
    assert policy.privacy_mode is False


# ---------------------------------------------------------------------------
# PII detection
# ---------------------------------------------------------------------------

def test_detect_email():
    det = privacy.detect_pii("Contact john.smith@example.com for details.")
    assert "john.smith@example.com" in det["email"]


def test_detect_phone():
    det = privacy.detect_pii("Call me at +44 20 7946 0958 anytime.")
    assert det["phone"]


def test_detect_personal_name():
    det = privacy.detect_pii("The account manager is Mr. Jonathan Whitfield.")
    assert det["name"]


def test_detect_local_path():
    det = privacy.detect_pii("Run from C:\\Users\\alice\\cyberrisk on Windows.")
    assert det["path"]
    det2 = privacy.detect_pii("Config lives at /home/alice/cyberrisk/config.")
    assert det2["path"]


def test_path_regex_does_not_match_regex_escapes():
    # `W:\n` / `s:\n{recs}` inside a regex literal are NOT local paths.
    assert not privacy.detect_pii(r"replace with 'W:\n' or 's:\n{recs}'")["path"]
    assert not privacy.detect_pii(r"n:\s*([^\]]+)\]")["path"]


def test_detect_secret():
    det = privacy.detect_pii("Key: sk-abcdefghijklmnopqrstuvwxyz0123456789")
    assert det["secret"]


def test_clean_text_has_no_pii():
    det = privacy.detect_pii("A healthcare firm with 10M records and weak MFA.")
    assert not any(det.values())


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redact_email_and_phone():
    out = privacy.redact_pii("Email j.doe@example.com or phone +1 555 010 0199 now.")
    assert "j.doe@example.com" not in out
    assert "+1 555 010 0199" not in out
    assert "[REDACTED]" in out


def test_redact_local_path():
    out = privacy.redact_pii("Workdir is C:\\Users\\bob\\project")
    assert "bob" not in out
    assert "[REDACTED]" in out


def test_redact_does_not_mangle_industry_terms():
    out = privacy.redact_pii("Healthcare Manufacturing is in the Financial Services sector.")
    assert "Healthcare" in out
    assert "Financial Services" in out


# ---------------------------------------------------------------------------
# Sanitised logging
# ---------------------------------------------------------------------------

def test_sanitise_log_scrubs_secret_always():
    line = "call failed: sk-abcdefghijklmnopqrstuvwxyz0123456789"
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in privacy.sanitise_log(line)
    assert "[REDACTED]" in privacy.sanitise_log(line)


def test_sanitise_log_scrubs_pii_when_disabled(capsys, monkeypatch):
    monkeypatch.setattr(
        privacy, "_policy_cache", privacy.PrivacyPolicy(log_sensitive_information=False)
    )
    line = "user email alice@example.com and phone +1 555 010 0199"
    out = privacy.sanitise_log(line)
    assert "alice@example.com" not in out
    assert "[REDACTED]" in out


# ---------------------------------------------------------------------------
# Input boundary guard
# ---------------------------------------------------------------------------

def test_check_input_blocks_secret():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        privacy, "_policy_cache", privacy.PrivacyPolicy(privacy_mode=True)
    )
    try:
        verdict = privacy.check_input("use this key sk-abcdefghijklmnopqrstuvwxyz0123456789")
        assert verdict.action == "blocked"
        assert verdict.message == ""
    finally:
        monkeypatch.undo()


def test_check_input_redacts_personal_data():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        privacy, "_policy_cache", privacy.PrivacyPolicy(privacy_mode=True)
    )
    try:
        verdict = privacy.check_input(
            "My email is alice@example.com, the firm is Acme Manufacturing."
        )
        assert verdict.action == "redacted"
        assert "alice@example.com" not in verdict.message
        assert "Acme Manufacturing" in verdict.message
        assert "Personal data" in verdict.notice
    finally:
        monkeypatch.undo()


def test_check_input_passes_clean_brief():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        privacy, "_policy_cache", privacy.PrivacyPolicy(privacy_mode=True)
    )
    try:
        verdict = privacy.check_input("Assess a $500M manufacturer with weak MFA.")
        assert verdict.action == "ok"
        assert verdict.message == "Assess a $500M manufacturer with weak MFA."
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# Sanitised logger behaviour
# ---------------------------------------------------------------------------

def test_sanitised_logger_scrubs_message(caplog):
    logger = logging.getLogger("test.sanitised")
    logger.setLevel(logging.INFO)
    with caplog.at_level(logging.INFO, logger="test.sanitised"):
        # Simulate the record scrub through the privacy path directly.
        scrubbed = privacy.sanitise_log("token sk-abcdefghijklmnopqrstuvwxyz0123456789 leaked")
        logger.info(scrubbed)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in caplog.text
