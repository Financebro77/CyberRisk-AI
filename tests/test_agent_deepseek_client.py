"""DeepSeek client config/connection tests.

Only configuration behaviour is tested here (no network).  A live round-trip
test runs only when a DEEPSEEK_API_KEY is actually present, so the suite is
green without credentials.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from cyberrisk.agent.deepseek_client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    ENV_API_KEY,
    DeepSeekClient,
    _normalise_response,
    _parse_arguments,
)
from cyberrisk.agent.schemas import AgentConfig


class FakeMessage:
    content = "Hello"


class FakeFunction:
    name = "run_loss_simulation"
    arguments = '{"security_controls": "weak mfa", "revenue_usd": 5e8}'


class FakeToolCall:
    id = "call_1"
    function = FakeFunction()


class FakeAssistantMessage:
    content = "Let me run the model."
    tool_calls = [FakeToolCall()]


class FakeChoice:
    message = FakeAssistantMessage()


class FakeUsage:
    prompt_tokens = 100
    completion_tokens = 40
    total_tokens = 140


class FakeResponse:
    choices = [FakeChoice()]
    usage = FakeUsage()


def test_parse_arguments_valid():
    assert _parse_arguments('{"a": 1, "b": [2]}') == {"a": 1, "b": [2]}


def test_parse_arguments_invalid_returns_empty():
    assert _parse_arguments("not json") == {}
    assert _parse_arguments(None) == {}


def test_normalise_response_extracts_tool_calls_and_usage():
    resp = _normalise_response(FakeResponse())
    assert resp.content == "Let me run the model."
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert tc["name"] == "run_loss_simulation"
    assert tc["id"] == "call_1"
    assert tc["arguments"]["revenue_usd"] == 5e8
    assert resp.usage["total_tokens"] == 140


def test_is_configured_reflects_env(monkeypatch):
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    assert DeepSeekClient.is_configured() is False
    monkeypatch.setenv(ENV_API_KEY, "sk-test")
    assert DeepSeekClient.is_configured() is True


def test_missing_key_raises_actionable_error(monkeypatch):
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        DeepSeekClient()


def test_client_builds_with_env_key(monkeypatch):
    """Constructing a client with a key should succeed without a network call."""
    monkeypatch.setenv(ENV_API_KEY, "sk-test-key")
    client = DeepSeekClient(config=AgentConfig(model="deepseek-chat"))
    assert client.model_name == "deepseek-chat"
    assert client.base_url == DEFAULT_BASE_URL
    # The openai client is constructed lazily on first chat; ensure attributes exist.
    assert client._client is not None


def test_defaults_match_documentation():
    assert DEFAULT_MODEL == "deepseek-chat"
    assert DEFAULT_BASE_URL == "https://api.deepseek.com"


@pytest.mark.skipif(not os.getenv(ENV_API_KEY), reason="DEEPSEEK_API_KEY not set")
def test_live_chat_round_trip():
    """Real API call -- only runs when a key is configured."""
    client = DeepSeekClient()
    response = client.chat(
        [{"role": "user", "content": "Reply with exactly: pong"}],
        max_tokens=10,
    )
    assert "pong" in response.content.lower()
