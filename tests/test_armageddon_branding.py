"""Armageddon rebrand contract — every user-facing backend surface presents
itself as "Armageddon", never as the legacy "CyberRisk AI" product name.

This pins the runtime-visible brand strings so the rebrand cannot silently
regress.  Internal names (the ``cyberrisk`` package path, ``CyberRiskAgent``
class, ``CYBERRISK_*`` env vars) are deliberately NOT covered: they are
implementation details, not branding.
"""

from __future__ import annotations


def test_api_title_is_armageddon():
    from cyberrisk.api.main import app

    assert app.title == "Armageddon"


def test_v1_api_title_is_armageddon():
    from cyberrisk.api.v1.app import app as v1_app

    assert v1_app.title == "Armageddon API"


def test_web_health_serves_armageddon(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "Armageddon"


def test_v1_health_serves_armageddon(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "Armageddon"


def test_cli_title_is_armageddon():
    from cyberrisk import cli

    assert cli.TITLE == "Armageddon"
    assert cli.SUBTITLE == "Commercial Cyber Risk Advisory Platform"


def test_privacy_notice_names_armageddon():
    from cyberrisk import privacy

    verdict = privacy.check_input("Email j.doe@example.com or phone +1 555 010 0199 now.")
    assert verdict.action == "redacted"
    assert "Armageddon does not store personal information." in verdict.notice
    assert "CyberRisk AI" not in verdict.notice


def test_agent_system_prompt_uses_armageddon_framework():
    from agent import prompts as agent_prompts
    from cyberrisk.agent import prompts as cyberrisk_prompts

    assert "Armageddon framework" in agent_prompts.SYSTEM_PROMPT
    assert "CyberRisk framework" not in agent_prompts.SYSTEM_PROMPT
    # The real (non-shim) prompt module carries the same white-box sentence.
    assert "Armageddon framework" in cyberrisk_prompts.SYSTEM_PROMPT
    assert "CyberRisk framework" not in cyberrisk_prompts.SYSTEM_PROMPT
