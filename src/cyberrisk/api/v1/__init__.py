"""Versioned mobile API layer (``/api/v1``).

A clean JSON surface for mobile clients built on top of the existing tool
layer read-only.  The assessment lifecycle (start -> submit -> results) reuses
the engine, agent, RAG, and LLM abstraction exactly as the web API does -- no
risk logic is duplicated here.

    - ``schemas``      typed request / result / error models
    - ``store``        in-memory, TTL-bounded assessment store
    - ``service``      the pipeline composition + result mapper + evidence
    - ``routes``       the five ``/api/v1/*`` endpoints
    - ``errors``       consistent error envelope + exception handlers
    - ``middleware``   request IDs + structured access logging
"""

from __future__ import annotations

from cyberrisk.api.v1.routes import router

__all__ = ["router"]
