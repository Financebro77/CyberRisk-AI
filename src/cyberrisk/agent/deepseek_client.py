"""DeepSeek API client (OpenAI-compatible SDK).

Backward-compatibility shim: the DeepSeek implementation moved into the
provider-agnostic ``cyberrisk.llm`` package, and this module re-exports it
so existing imports keep working unchanged.

    from cyberrisk.agent.deepseek_client import DeepSeekClient

is now the same object as ``cyberrisk.llm.deepseek_provider.DeepSeekProvider``
with identical configuration behaviour.  New code should import from
``cyberrisk.llm`` (or use ``cyberrisk.llm.factory.create_llm_client`` to let
``LLM_PROVIDER`` pick the provider).

Credentials come EXCLUSIVELY from the environment, never from code:

    DEEPSEEK_API_KEY    (required -- base64-style sk-... token)
    DEEPSEEK_BASE_URL   (optional; default https://api.deepseek.com)
    DEEPSEEK_MODEL      (optional; default deepseek-chat)
"""

from __future__ import annotations

from cyberrisk.llm.base import (
    ChatResponse,
    _normalise_response,
    _parse_arguments,
)
from cyberrisk.llm.deepseek_provider import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_MODEL,
    DeepSeekProvider,
)

# Alias so `DeepSeekClient` remains the name existing callers import.
DeepSeekClient = DeepSeekProvider

__all__ = [
    "ChatResponse",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "ENV_API_KEY",
    "ENV_BASE_URL",
    "ENV_MODEL",
    "DeepSeekClient",
    "DeepSeekProvider",
    "_normalise_response",
    "_parse_arguments",
]
