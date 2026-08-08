"""LLM provider factory tests.

No network.  Environment selection logic only: explicit LLM_PROVIDER choice,
fallback to whichever key is present, and the error paths.  A live provider
build is only attempted with a matching key present (the SDK client is
constructed lazily -- no network on construction).
"""

from __future__ import annotations

import pytest

from cyberrisk.llm import create_llm_client, get_provider_name, is_configured
from cyberrisk.llm.deepseek_provider import (
    DEFAULT_MODEL,
    ENV_API_KEY as DEEPSEEK_KEY,
    DeepSeekProvider,
)
from cyberrisk.llm.factory import PROVIDER_ENV
from cyberrisk.llm.openai_provider import (
    ENV_API_KEY as OPENAI_KEY,
    OpenAIProvider,
)


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    """Isolate every test from the developer's .env keys."""
    monkeypatch.delenv(PROVIDER_ENV, raising=False)
    monkeypatch.delenv(OPENAI_KEY, raising=False)
    monkeypatch.delenv(DEEPSEEK_KEY, raising=False)


def test_explicit_openai_selected(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "openai")
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    assert get_provider_name() == "openai"


def test_explicit_deepseek_selected(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "deepseek")
    monkeypatch.setenv(DEEPSEEK_KEY, "sk-test")
    assert get_provider_name() == "deepseek"


def test_fallback_to_configured_key(monkeypatch):
    # Only DeepSeek key present -> deepseek.
    monkeypatch.setenv(DEEPSEEK_KEY, "sk-test")
    assert get_provider_name() == "deepseek"
    # Only OpenAI key present -> openai.
    monkeypatch.delenv(DEEPSEEK_KEY)
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    assert get_provider_name() == "openai"


def test_explicit_choice_beats_key(monkeypatch):
    """An explicit LLM_PROVIDER always wins over a fallback key."""
    monkeypatch.setenv(PROVIDER_ENV, "deepseek")
    monkeypatch.setenv(OPENAI_KEY, "sk-test")  # misleading fallback
    assert get_provider_name() == "deepseek"


def test_no_provider_no_key_raises(monkeypatch):
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        get_provider_name()


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "claude")
    with pytest.raises(ValueError, match="claude"):
        get_provider_name()


def test_provider_name_case_insensitive(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "OpenAI")
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    assert get_provider_name() == "openai"


def test_is_configured_never_raises(monkeypatch):
    assert is_configured() is False
    monkeypatch.setenv(DEEPSEEK_KEY, "sk-test")
    assert is_configured() is True


def test_create_llm_client_openai(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "openai")
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    client = create_llm_client()
    assert isinstance(client, OpenAIProvider)
    assert client.model_name == "gpt-4o-mini"
    assert client._client is not None  # SDK built, no network


def test_create_llm_client_deepseek(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "deepseek")
    monkeypatch.setenv(DEEPSEEK_KEY, "sk-test")
    client = create_llm_client()
    assert isinstance(client, DeepSeekProvider)
    assert client.model_name == DEFAULT_MODEL
    assert client._client is not None


def test_create_llm_client_missing_key_raises(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "openai")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        create_llm_client()
