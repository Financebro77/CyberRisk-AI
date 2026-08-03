"""DeepSeek API client (OpenAI-compatible SDK).

DeepSeek exposes an OpenAI-compatible API, so the official ``openai``
package works with a custom ``base_url``.  This thin wrapper hides that
detail and normalises the response so the controller only ever sees:

    content    -- the assistant's text (may be empty on a tool round)
    tool_calls -- list of {name, arguments(dict), id}

Credentials come EXCLUSIVELY from the environment, never from code:

    DEEPSEEK_API_KEY    (required -- base64-style sk-... token)
    DEEPSEEK_BASE_URL   (optional; default https://api.deepseek.com)
    DEEPSEEK_MODEL      (optional; default deepseek-chat)

The key is loaded from a ``.env`` file in the current working directory,
then the repo root, via python-dotenv.  If neither is present the client
raises a clear, actionable error instead of failing obscurely mid-chat.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cyberrisk.agent.schemas import AgentConfig

# Look for a .env in the working directory and, failing that, the repo root
# (four levels above this package: src/cyberrisk/agent -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _candidate in (Path.cwd() / ".env", _REPO_ROOT / ".env"):
    if _candidate.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(_candidate)
        except ImportError:  # pragma: no cover - dotenv is an optional dep
            pass
        break

ENV_API_KEY = "DEEPSEEK_API_KEY"
ENV_BASE_URL = "DEEPSEEK_BASE_URL"
ENV_MODEL = "DEEPSEEK_MODEL"

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


@dataclass
class ChatResponse:
    """Normalised assistant turn from the DeepSeek API."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class DeepSeekClient:
    """Minimal OpenAI-compatible client for the DeepSeek chat API."""

    def __init__(self, config: AgentConfig | None = None) -> None:
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
    ) -> ChatResponse:
        """Send a chat-completions request and normalise the response.

        Parameters
            messages     OpenAI-format message list (system/user/assistant/tool)
            tools        optional JSON-Schema tool definitions for function calling
            temperature  override the config default
            max_tokens   override the config default
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

        response = self._client.chat.completions.create(**kwargs)
        return _normalise_response(response)

    @staticmethod
    def is_configured() -> bool:
        """True when a DeepSeek key is available in the environment."""
        return bool(os.getenv(ENV_API_KEY))


def _build_openai_client(api_key: str, base_url: str):
    """Import openai lazily (it is an optional extra) and build a client."""
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The 'openai' package is required for DeepSeek integration. "
            "Install it with `pip install -e '.[agent]'`."
        ) from exc
    return OpenAI(api_key=api_key, base_url=base_url)


def _normalise_response(response: Any) -> ChatResponse:
    """Convert an OpenAI SDK chat completion into a ChatResponse."""
    choice = response.choices[0]
    message = choice.message
    tool_calls: list[dict[str, Any]] = []
    for tc in getattr(message, "tool_calls", None) or []:
        tool_calls.append(
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": _parse_arguments(tc.function.arguments),
            }
        )
    usage = {}
    if getattr(response, "usage", None) is not None:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
    return ChatResponse(
        content=message.content or "",
        tool_calls=tool_calls,
        usage=usage,
    )


def _parse_arguments(raw: str | None) -> dict[str, Any]:
    """Parse the tool-call JSON arguments string; never raise on bad JSON."""
    import json

    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
