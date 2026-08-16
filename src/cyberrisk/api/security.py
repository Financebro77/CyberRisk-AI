"""API authentication and rate limiting for the CyberRisk web layer.

Both features are **opt-in via environment variables**, so the default local
dev experience is unchanged (no key, no limit), while a production deployment
can enable them without code changes:

    CYBERRISK_API_KEY     when set, every /api/* route requires
                          `Authorization: Bearer <key>`.  Read from env only,
                          never hard-coded, never logged.
    CYBERRISK_RATE_LIMIT  requests per minute per client IP when > 0
                          (default 0 = disabled).  In-memory sliding window;
                          suitable for a single process, not a shared cache.

Secrets are never written to logs — an invalid key returns a 401 without
echoing the presented value, and the privacy logger is active.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import HTTPException, status

ENV_API_KEY = "CYBERRISK_API_KEY"
ENV_RATE_LIMIT = "CYBERRISK_RATE_LIMIT"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def _configured_api_key() -> str | None:
    """The API key from the environment (or None when auth is disabled)."""
    key = os.getenv(ENV_API_KEY)
    return key.strip() if key else None


def verify_api_key(authorization: str | None, key: str | None = None) -> str | None:
    """Return the client identity when the bearer token is valid, else None.

    ``authorization`` is the raw ``Authorization`` header value.  A valid key
    returns a stable identity string (used for rate limiting); an absent or
    mismatched key returns None.  Never echoes the presented secret.  ``key``
    may be passed in to avoid a second env read on the request path.
    """
    if key is None:
        key = _configured_api_key()
    if key is None:
        # Auth is disabled — accept, and use the client IP as identity.
        return None
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    # Constant-time compare to avoid timing side channels on the key.
    import secrets as _secrets

    if _secrets.compare_digest(token.strip(), key):
        return "api-key"  # stable identity for rate limiting
    return None


# ---------------------------------------------------------------------------
# Rate limiting (in-memory sliding window, per client identity)
# ---------------------------------------------------------------------------

_requests: defaultdict[str, deque[float]] = defaultdict(deque)
_LOCK = __import__("threading").Lock()
# Soft cap on tracked identities: when exceeded, identities whose whole
# window has lapsed are dropped (see _check_rate_limit) so a long-running
# public deployment cannot accumulate one deque per unique client forever.
_MAX_IDENTITIES = 1024


def _rate_limit_per_minute() -> int:
    raw = os.getenv(ENV_RATE_LIMIT, "0")
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _check_rate_limit(identity: str, limit: int) -> None:
    """Enforce the per-minute sliding window for one client identity."""
    now = time.monotonic()
    window = 60.0
    with _LOCK:
        stamps = _requests[identity]
        # Drop timestamps outside the window.
        while stamps and now - stamps[0] > window:
            stamps.popleft()
        if len(stamps) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again shortly.",
            )
        stamps.append(now)
        # Bound the store: once it grows past the cap, prune identities whose
        # newest request has already fallen out of the window (they cost us a
        # deque each and would otherwise never be removed).
        if len(_requests) > _MAX_IDENTITIES:
            for key in [
                k for k, v in _requests.items()
                if not v or now - v[-1] > window
            ]:
                del _requests[key]


def _reset_rate_limits() -> None:
    """Clear all in-memory rate-limit windows (used by tests)."""
    with _LOCK:
        _requests.clear()


# ---------------------------------------------------------------------------
# ASGI middleware (protects every /api/* route)
# ---------------------------------------------------------------------------


class APIGatewayMiddleware:
    """Enforce auth + rate limiting on /api/* requests.

    Applied as a pure ASGI middleware so it guards every /api route uniformly
    (including the chat session routes) without touching each endpoint.
    Health checks and the static frontend are left open so orchestration and
    the UI can reach them without a key.
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/api"):
            await self.app(scope, receive, send)
            return
        # Health is exempt so load balancers / the Docker healthcheck work.
        if path in ("/api/health", "/api/v1/health"):
            await self.app(scope, receive, send)
            return

        # Parse the request (we only need the Authorization header).
        authorization = _header_value(scope, b"authorization")

        key = _configured_api_key()
        identity = verify_api_key(authorization, key)
        if key is not None and identity is None:
            response = _error_response(
                scope,
                "Unauthorized. Provide a valid API key.",
                status.HTTP_401_UNAUTHORIZED,
            )
            await response(scope, receive, send)
            return

        limit = _rate_limit_per_minute()
        if limit > 0:
            client_id = _client_identity_scope(scope, identity)
            try:
                _check_rate_limit(client_id, limit)
            except HTTPException as exc:
                # In ASGI middleware we cannot raise — send the response.
                response = _error_response(scope, str(exc.detail), exc.status_code)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


def _client_identity_scope(scope: dict, api_identity: str | None) -> str:
    """Client identity from the ASGI scope (no parsed Request needed)."""
    if api_identity:
        return api_identity
    client = scope.get("client")
    return client[0] if client and client[0] else "unknown"


def _header_value(scope: dict, name: bytes) -> str | None:
    """The first header value for ``name`` (lowercase bytes), or None."""
    for k, v in scope.get("headers", []):
        if k.lower() == name:
            return v.decode("latin-1")
    return None


def _error_response(scope: dict, detail: str, status_code: int):
    """A gateway error body.

    ``/api/v1/*`` requests get the versioned ``{"error": {...}}`` envelope so
    auth / rate-limit errors honour the same contract as every other non-2xx
    v1 response; all other paths keep the web API's ``{"detail": ...}`` shape.
    """
    if scope.get("path", "").startswith("/api/v1"):
        from cyberrisk.api.v1.errors import v1_error_envelope

        request_id = (scope.get("state") or {}).get("request_id", "")
        content = v1_error_envelope(status_code, request_id)
    else:
        content = {"detail": detail}
    from starlette.responses import JSONResponse

    return JSONResponse(content, status_code=status_code)
