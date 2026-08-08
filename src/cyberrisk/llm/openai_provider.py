"""OpenAI chat-completion provider.

Uses the official ``openai`` SDK against the native OpenAI API and hides it
behind the ``LLMClient`` interface, so the agent controller and tool loop run
unchanged regardless of provider.

Credentials come EXCLUSIVELY from the environment, never from code:

    OPENAI_API_KEY   (required -- sk-... token)
    OPENAI_BASE_URL  (optional; override for a compatible gateway / proxy)
    OPENAI_MODEL     (optional; default gpt-4o-mini)

The key is loaded from a ``.env`` file by ``cyberrisk.llm.base``.  If the
key is missing the provider raises a clear, actionable error instead of
failing obscurely mid-chat.
"""

from __future__ import annotations

import os
from typing import Any

from cyberrisk.llm.base import (
    ChatResponse,
    LLMClient,
    _build_openai_client,
    _normalise_response,
)

ENV_API_KEY = "OPENAI_API_KEY"
ENV_BASE_URL = "OPENAI_BASE_URL"
ENV_MODEL = "OPENAI_MODEL"

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(LLMClient):
    """Minimal client for the OpenAI chat-completions API."""

    def __init__(self, config=None) -> None:
        # config is accepted for signature parity with DeepSeekProvider, but
        # deliberately ignored for the model: AgentConfig defaults to
        # "deepseek-chat", which must never be sent to OpenAI.  The OpenAI
        # model comes from OPENAI_MODEL / the provider default instead.
        del config
        api_key = os.getenv(ENV_API_KEY)
        if not api_key:
            raise RuntimeError(
                f"{ENV_API_KEY} is not set. Create a .env file in the project "
                "root (see .env.example) containing `OPENAI_API_KEY=sk-...` "
                "or export it in your shell, then restart the app."
            )
        base_url = os.getenv(ENV_BASE_URL)
        model = os.getenv(ENV_MODEL, DEFAULT_MODEL)
        self.model = model
        self._client = _build_openai_client(api_key, base_url)

    @property
    def model_name(self) -> str:
        return self.model

    @property
    def base_url(self) -> str:
        return os.getenv(ENV_BASE_URL, "https://api.openai.com/v1")

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Send a chat-completions request and normalise the response.

        Parameters
            messages         OpenAI-format message list (system/user/assistant/tool)
            tools            optional JSON-Schema tool definitions for function calling
            temperature      override the default (0.2)
            max_tokens       override the default (1024)
            response_format  optional response-format hint (e.g. json_object)
        Returns
            ChatResponse with content and/or tool_calls.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2 if temperature is None else temperature,
            "max_tokens": 1024 if max_tokens is None else max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format

        response = self._client.chat.completions.create(**kwargs)
        return _normalise_response(response)

    def check_connection(self) -> bool:
        """Probe the OpenAI API.  Returns True when it answers.

        Tries the model list first, then falls back to a 1-token chat.
        Never raises.
        """
        try:
            self._client.models.list()
            return True
        except Exception:  # noqa: BLE001 - any failure means "not reachable"
            try:
                self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                )
                return True
            except Exception:  # noqa: BLE001
                return False

    @classmethod
    def is_configured(cls) -> bool:
        """True when an OpenAI key is available in the environment."""
        return bool(os.getenv(ENV_API_KEY))


__all__ = [
    "DEFAULT_MODEL",
    "ENV_API_KEY",
    "ENV_BASE_URL",
    "ENV_MODEL",
    "OpenAIProvider",
]
