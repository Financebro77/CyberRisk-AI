"""LLM provider factory.

Selects a concrete ``LLMClient`` from the environment:

    LLM_PROVIDER=openai      -> OpenAIProvider
    LLM_PROVIDER=deepseek    -> DeepSeekProvider

When ``LLM_PROVIDER`` is unset, the provider is inferred from whichever API
key is present -- an explicit choice is always respected, never overridden.

No API keys are hard-coded here or anywhere in this package; they are read
from the environment (or a ``.env`` file loaded by ``cyberrisk.llm.base``)
at construction time.
"""

from __future__ import annotations

import os

from cyberrisk.llm.base import LLMClient

PROVIDER_ENV = "LLM_PROVIDER"
SUPPORTED_PROVIDERS = ("openai", "deepseek")


def get_provider_name() -> str:
    """Return the active provider name, resolving the fallback rule.

    Returns
        "openai" or "deepseek".
    Raises
        ValueError  when LLM_PROVIDER names an unsupported provider.
        RuntimeError when LLM_PROVIDER is unset and no provider key is set.
    """
    provider = os.getenv(PROVIDER_ENV, "").strip().lower()
    if provider:
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported LLM_PROVIDER {provider!r}. Choose from "
                f"{SUPPORTED_PROVIDERS!r}, e.g. LLM_PROVIDER=openai."
            )
        return provider
    # No explicit choice: infer from whichever key is present.
    from cyberrisk.llm.openai_provider import ENV_API_KEY as OPENAI_KEY
    from cyberrisk.llm.deepseek_provider import ENV_API_KEY as DEEPSEEK_KEY

    if os.getenv(OPENAI_KEY):
        return "openai"
    if os.getenv(DEEPSEEK_KEY):
        return "deepseek"
    raise RuntimeError(
        f"{PROVIDER_ENV} is not set and neither OPENAI_API_KEY nor "
        "DEEPSEEK_API_KEY is present in the environment. Set LLM_PROVIDER=openai "
        "or LLM_PROVIDER=deepseek (and its key in .env / your shell), then restart."
    )


def is_configured() -> bool:
    """True when the active provider's API key is available.  Never raises.

    Returns False for an unset provider or a missing key, so callers can show
    a graceful "LLM not configured" state instead of crashing.
    """
    try:
        name = get_provider_name()
    except (RuntimeError, ValueError):
        return False
    if name == "openai":
        from cyberrisk.llm.openai_provider import OpenAIProvider

        return OpenAIProvider.is_configured()
    from cyberrisk.llm.deepseek_provider import DeepSeekProvider

    return DeepSeekProvider.is_configured()


def create_llm_client(config=None) -> LLMClient:
    """Build the active provider's client.

    Providers are imported lazily so importing this module never pulls in
    ``cyberrisk.agent`` (which imports back into this package) -- no import
    cycle.
    """
    name = get_provider_name()
    if name == "openai":
        from cyberrisk.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(config)
    from cyberrisk.llm.deepseek_provider import DeepSeekProvider

    return DeepSeekProvider(config)


__all__ = [
    "PROVIDER_ENV",
    "SUPPORTED_PROVIDERS",
    "create_llm_client",
    "get_provider_name",
    "is_configured",
]
