"""OpenAI provider tests.

No network.  Construction/config behaviour uses env manipulation; chat /
structured-output / connection tests stub the underlying OpenAI SDK client
so the provider logic is exercised without a live API.
"""

from __future__ import annotations

import pytest

from cyberrisk.llm.openai_provider import (
    DEFAULT_MODEL,
    ENV_API_KEY,
    ENV_MODEL,
    OpenAIProvider,
)


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


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self.response


class FakeChat:
    def __init__(self, response):
        self.completions = FakeCompletions(response)


@pytest.fixture(autouse=True)
def _clear_openai_key(monkeypatch):
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    monkeypatch.delenv(ENV_MODEL, raising=False)


def _stub_provider(monkeypatch, response) -> tuple[OpenAIProvider, FakeCompletions]:
    monkeypatch.setenv(ENV_API_KEY, "sk-test")
    provider = OpenAIProvider()
    completions = FakeCompletions(response)
    # The provider calls self._client.chat.completions.create(**kwargs), so the
    # stub's chat.completions must BE the shared completions object the test
    # inspects (last_kwargs).
    stub_client = type(
        "StubClient",
        (),
        {"chat": type("StubChat", (), {"completions": completions})(),
         "models": type("Models", (), {"list": lambda: None})()},
    )()
    provider._client = stub_client
    return provider, completions


def test_missing_key_raises_actionable_error(monkeypatch):
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIProvider()


def test_builds_with_env_key(monkeypatch):
    monkeypatch.setenv(ENV_API_KEY, "sk-test")
    provider = OpenAIProvider()
    assert provider.model_name == DEFAULT_MODEL == "gpt-4o-mini"
    assert provider.base_url == "https://api.openai.com/v1"
    assert provider._client is not None


def test_model_env_override(monkeypatch):
    monkeypatch.setenv(ENV_API_KEY, "sk-test")
    monkeypatch.setenv(ENV_MODEL, "gpt-4o")
    provider = OpenAIProvider()
    assert provider.model_name == "gpt-4o"


def test_is_configured_reflects_env(monkeypatch):
    assert OpenAIProvider.is_configured() is False
    monkeypatch.setenv(ENV_API_KEY, "sk-test")
    assert OpenAIProvider.is_configured() is True


def test_chat_uses_openai_client_and_normalises(monkeypatch):
    provider, completions = _stub_provider(monkeypatch, FakeResponse())
    resp = provider.chat(
        [{"role": "user", "content": "hello"}],
        tools=[{"type": "function", "function": {"name": "f"}}],
        temperature=0.1,
        max_tokens=50,
    )
    assert resp.content == "Let me run the model."
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0]["name"] == "run_loss_simulation"
    assert resp.tool_calls[0]["arguments"]["revenue_usd"] == 5e8
    assert resp.usage["total_tokens"] == 140
    # The tool schema reached the SDK create() call.
    assert "tools" in completions.last_kwargs
    assert completions.last_kwargs["temperature"] == 0.1
    assert completions.last_kwargs["max_tokens"] == 50
    assert completions.last_kwargs["model"] == "gpt-4o-mini"


def test_generate_response_returns_text(monkeypatch):
    resp = FakeResponse()
    resp.choices[0].message.tool_calls = None
    provider, _ = _stub_provider(monkeypatch, resp)
    assert provider.generate_response([{"role": "user", "content": "hi"}]) == "Let me run the model."


def test_generate_structured_output_parses_json(monkeypatch):
    json_resp = FakeResponse()
    json_resp.choices[0].message.content = '{"score": 73.4, "drivers": ["patching"]}'
    json_resp.choices[0].message.tool_calls = None
    provider, completions = _stub_provider(monkeypatch, json_resp)
    out = provider.generate_structured_output([{"role": "user", "content": "score it"}])
    assert out == {"score": 73.4, "drivers": ["patching"]}
    assert completions.last_kwargs["response_format"] == {"type": "json_object"}


def test_generate_structured_output_bad_json_returns_empty(monkeypatch):
    json_resp = FakeResponse()
    json_resp.choices[0].message.content = "not json"
    json_resp.choices[0].message.tool_calls = None
    provider, _ = _stub_provider(monkeypatch, json_resp)
    assert provider.generate_structured_output([{"role": "user", "content": "score it"}]) == {}


def test_check_connection_true_when_models_list_ok(monkeypatch):
    provider, _ = _stub_provider(monkeypatch, FakeResponse())
    assert provider.check_connection() is True


def test_check_connection_false_on_error(monkeypatch):
    provider, _ = _stub_provider(monkeypatch, FakeResponse())

    def boom():
        raise RuntimeError("no network")

    provider._client.models.list = boom
    provider._client.chat.completions.create = boom
    assert provider.check_connection() is False
