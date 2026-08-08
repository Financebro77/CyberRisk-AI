"""DeepSeek chat-completion provider.

DeepSeek exposes an OpenAI-compatible API, so the official ``openai`` package
works with a custom ``base_url``.  This provider hides that detail behind the
``LLMClient`` interface and normalises the response so the controller only
ever sees content / tool_calls / usage.

Credentials come EXCLUSIVELY from the environment, never from code:

    DEEPSEEK_API_KEY    (required -- base64-style sk-... token)
    DEEPSEEK_BASE_URL   (optional; default https://api.deepseek.com)
    DEEPSEEK_MODEL      (optional; default deepseek-chat)

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

ENV_API_KEY = "DEEPSEEK_API_KEY"
ENV_BASE_URL = "DEEPSEEK_BASE_URL"
ENV_MODEL = "DEEPSEEK_MODEL"

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider(LLMClient):
    """Minimal OpenAI-compatible client for the DeepSeek chat API."""

    def __init__(self, config=None) -> None:
        # Imported lazily: the agent package imports this provider (via the
        # factory), so importing AgentConfig at module scope would create an
        # import cycle through cyberrisk.agent.
        from cyberrisk.agent.schemas import AgentConfig

        self.config = config or AgentConfig()
        api_key = os.getenv(ENV_API_KEY)
        if not api_key:
            raise RuntimeError(
                f"{ENV_API_KEY} is not set. Create a .env file in the project "
                "root (see .env.example) containing `DEEPSEEK_API_KEY=sk-...` "
                "or export it in your shell, then restart the app."
            )
        base_url = os.getenv(ENV_BASE_URL, DEFAULT_BASE_URL)
        model = os.getenv(ENV_MODEL, self.config.model)
        # Config.model remains the env-provided default unless overridden by env.
        self.model = model
        self._client = _build_openai_client(api_key, base_url)

    @property
    def model_name(self) -> str:
        return self.model

    @property
    def base_url(self) -> str:
        return os.getenv(ENV_BASE_URL, DEFAULT_BASE_URL)

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
            temperature      override the config default
            max_tokens       override the config default
            response_format  optional response-format hint (e.g. json_object)
        Returns
            ChatResponse with content and/or tool_calls.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format

        response = self._client.chat.completions.create(**kwargs)
        return _normalise_response(response)

    def check_connection(self) -> bool:
        """Probe the DeepSeek API.  Returns True when it answers.

        Tries the model list first, then falls back to a 1-token chat --
        some DeepSeek plans restrict ``/models`` while still serving chat.
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
        """True when a DeepSeek key is available in the environment."""
        return bool(os.getenv(ENV_API_KEY))


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "ENV_API_KEY",
    "ENV_BASE_URL",
    "ENV_MODEL",
    "DeepSeekProvider",
]
