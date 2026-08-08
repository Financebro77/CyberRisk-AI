"""LLM provider abstraction: pluggable OpenAI / DeepSeek clients.

Public entry points:
    create_llm_client   -> active provider's LLMClient (from LLM_PROVIDER env)
    is_configured       -> True when the active provider's key is present
    get_provider_name   -> "openai" or "deepseek"
    LLMClient           -> the abstract interface
    ChatResponse        -> normalised assistant turn

Imports only base and factory at module scope so importing ``cyberrisk.llm``
never pulls in ``cyberrisk.agent`` (which imports back into this package).
"""

from cyberrisk.llm.base import ChatResponse, LLMClient
from cyberrisk.llm.factory import (
    create_llm_client,
    get_provider_name,
    is_configured,
)

__all__ = [
    "ChatResponse",
    "LLMClient",
    "create_llm_client",
    "get_provider_name",
    "is_configured",
]
