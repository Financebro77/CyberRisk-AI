"""LLM provider abstraction for the CyberRisk AI consultant.

Defines the provider-agnostic interface the agent talks to, plus the shared
types and helpers every concrete provider reuses:

    LLMClient       -- abstract interface (chat + convenience methods)
    ChatResponse    -- normalised assistant turn (content / tool_calls / usage)

The concrete providers (openai_provider, deepseek_provider) implement the
interface; the factory (factory.py) picks one from the LLM_PROVIDER env var.
Nothing here knows which provider is in use, and nothing imports from
``cyberrisk.agent`` -- the agent package imports this layer, never the other
way around, so there is no import cycle.

Credentials come EXCLUSIVELY from the environment, never from code:

    LLM_PROVIDER     (optional; "openai" or "deepseek")
    OPENAI_API_KEY   (required for the OpenAI provider)
    DEEPSEEK_API_KEY (required for the DeepSeek provider)

A ``.env`` file in the working directory (or the repo root) is loaded at
import time via python-dotenv, so a missing key fails with a clear,
actionable error instead of failing obscurely mid-chat.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Look for a .env in the working directory and, failing that, the repo root
# (five levels above this package: src/cyberrisk/llm -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for _candidate in (Path.cwd() / ".env", _REPO_ROOT / ".env"):
    if _candidate.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(_candidate)
        except ImportError:  # pragma: no cover - dotenv is an optional dep
            pass
        break


@dataclass
class ChatResponse:
    """Normalised assistant turn from any LLM provider.

    Providers map their raw SDK response onto this shape so the agent
    controller only ever sees:

        content    -- the assistant's text (may be empty on a tool round)
        tool_calls -- list of {name, arguments(dict), id}
        usage      -- token usage when the provider reports it
    """

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMClient(ABC):
    """Provider-agnostic interface for the CyberRisk AI consultant.

    ``chat`` is the primary tool-calling surface the agent loop uses.  The
    three convenience methods wrap it for simpler callers:

        generate_response       -- plain text answer, no tools
        generate_structured_output -- JSON-object answer parsed to a dict
        check_connection        -- probe the provider before real work

    Implementations must read their API key from the environment (never from
    code) and raise a clear RuntimeError when it is missing.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model id this client sends to the provider."""

    @property
    @abstractmethod
    def base_url(self) -> str:
        """The API endpoint (provider default unless overridden)."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Send a chat-completions request and return a normalised response.

        Parameters
            messages     OpenAI-format message list (system/user/assistant/tool)
            tools        optional JSON-Schema tool definitions for function calling
            temperature  override the configured default
            max_tokens   override the configured default
        Returns
            ChatResponse with content and/or tool_calls.
        """

    def generate_response(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Plain-text reply: ``chat`` without tools, return only the content."""
        response = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        return response.content.strip()

    def generate_structured_output(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """JSON-object reply: ask the model for ``{...}`` and parse it.

        The model is asked via ``response_format={"type": "json_object"}``
        (supported by both OpenAI and DeepSeek).  Returns an empty dict when
        the reply is not parseable -- callers treat that as "no structured
        answer" rather than crashing.
        """
        response = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return _parse_json_object(response.content)

    @abstractmethod
    def check_connection(self) -> bool:
        """Return True when the provider is reachable with the configured key.

        A cheap probe (model list or a 1-token chat); never raises.
        """

    @classmethod
    @abstractmethod
    def is_configured(cls) -> bool:
        """True when this provider's API key is present in the environment."""


def _build_openai_client(api_key: str, base_url: str | None = None):
    """Import openai lazily (it is an optional extra) and build a client."""
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The 'openai' package is required for LLM integration. "
            "Install it with `pip install -e '.[agent]'`."
        ) from exc
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


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
    if not raw:
        return {}
    return _parse_json_object(raw)


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON-object string to a dict; never raise on bad JSON."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


__all__ = ["ChatResponse", "LLMClient"]
