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


def _api_key_is_configured() -> bool:
    return bool(_configured_api_key())


def verify_api_key(authorization: str | None) -> str | None:
    """Return the client identity when the bearer token is valid, else None.

    ``authorization`` is the raw ``Authorization`` header value.  A valid key
    returns a stable identity string (used for rate limiting); an absent or
    mismatched key returns None.  Never echoes the presented secret.
    """
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
        if path == "/api/health":
            await self.app(scope, receive, send)
            return

        # Parse the request (we only need the headers).
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        authorization = headers.get("authorization")

        identity = verify_api_key(authorization)
        if _api_key_is_configured() and identity is None:
            response = _json_response(
                {"detail": "Unauthorized. Provide a valid API key."},
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
                response = _json_response({"detail": exc.detail}, exc.status_code)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


def _client_identity_scope(scope: dict, api_identity: str | None) -> str:
    """Client identity from the ASGI scope (no parsed Request needed)."""
    if api_identity:
        return api_identity
    client = scope.get("client")
    return client[0] if client and client[0] else "unknown"


def _json_response(content: dict, status_code: int):
    from starlette.responses import JSONResponse

    return JSONResponse(content, status_code=status_code)
