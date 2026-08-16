"""Request-context middleware for the versioned API: request IDs + logging.

Every request gets a correlation id (inbound ``X-Request-ID`` if it looks
well-formed, else a fresh uuid) that is:

    * set on the response ``X-Request-ID`` header so clients can correlate,
    * stored on ``scope["state"]["request_id"]`` for handlers/errors, and
    * included in one structured log line per request.

The log line carries only operational metadata -- method, path, status,
duration, client IP, identity -- NEVER the Authorization header, request body,
API keys, env-var names/values, or brief details.  The sanitised logger is used
as a final backstop so anything that slips through is redacted.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send

_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def get_request_id(scope: Scope) -> str:
    """The request id for the current scope (populated by the middleware)."""
    state = scope.get("state") or {}
    rid = state.get("request_id")
    return rid if isinstance(rid, str) and rid else ""


class RequestContextMiddleware:
    """ASGI middleware: assign + echo a request id, and log one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._logger = logging.getLogger("cyberrisk.api.v1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        request_id = self._incoming_request_id(scope)
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        status_holder: dict[str, int] = {"status": 0}

        async def send_with_header(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            self._log(scope, status_holder["status"], duration_ms, request_id)

    @staticmethod
    def _incoming_request_id(scope: Scope) -> str:
        """Use a well-formed inbound id, else generate a fresh one."""
        headers = scope.get("headers") or []
        for name, value in headers:
            if name.lower() == b"x-request-id":
                raw = value.decode("latin-1").strip()
                if _ID_RE is not None and _ID_RE.match(raw):
                    return raw
                break
        return uuid.uuid4().hex

    def _log(self, scope: Scope, status: int, duration_ms: float, request_id: str) -> None:
        try:
            client = scope.get("client")
            client_ip = client[0] if client and client[0] else "unknown"
            method = scope.get("method", "-")
            path = scope.get("path", "-")
            self._logger.info(
                "request %s %s -> %s (%dms) ip=%s request_id=%s",
                method,
                path,
                status,
                int(duration_ms),
                client_ip,
                request_id,
            )
        except Exception:  # noqa: BLE001 - logging must never break the response
            pass
