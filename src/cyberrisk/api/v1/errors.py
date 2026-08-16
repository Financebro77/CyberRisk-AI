"""Safe, consistent error responses for the versioned mobile API.

Every non-2xx v1 response uses the envelope::

    {"error": {"code": str, "message": str, "request_id": str, "detail"?: ...}}

Guarantees:

    * never leaks internals -- 500s return a generic message (the traceback is
      logged server-side only),
    * validation errors expose only field locations + messages (never echoed
      body content),
    * every error carries the correlation id so an operator can find the log
      line.

The handlers are registered on the v1 SUB-APP (``api/v1/app.py``), which is
mounted at ``/api/v1`` on the main app, so they only ever see versioned
requests -- no path sniffing is needed.  The main app keeps its own handlers
(``register_web_error_handlers``): the SPA fallback for unknown client-side
routes and the ``{"detail": ...}`` JSON contract for web API errors.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from cyberrisk.api.v1.middleware import get_request_id

logger = logging.getLogger("cyberrisk.api.v1")

# Repo root: src/cyberrisk/api/v1/errors.py -> src/cyberrisk -> src -> repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_FRONTEND_DIST = _REPO_ROOT / "app" / "frontend" / "dist"


# HTTP status -> (error code, message).  Codes are stable API surface.
_STATUS_INFO = {
    400: ("bad_request", "Bad request."),
    401: ("unauthorized", "Unauthorized. Provide a valid API key."),
    403: ("forbidden", "Forbidden."),
    404: ("not_found", "Not found."),
    409: ("conflict", "Conflict."),
    422: ("validation_error", "Validation error."),
    429: ("rate_limited", "Rate limit exceeded. Try again shortly."),
    500: ("internal_error", "An internal error occurred."),
    503: ("service_unavailable", "The service is currently unavailable."),
}


def build_error_envelope(
    code: str,
    message: str,
    request_id: str,
    detail: Any = None,
) -> dict[str, Any]:
    """The wire envelope for one error."""
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if detail is not None:
        error["detail"] = detail
    return {"error": error}


def _envelope_for_status(status_code: int, request_id: str) -> dict[str, Any]:
    code, message = _STATUS_INFO.get(status_code, ("error", "Error."))
    return build_error_envelope(code, message, request_id)


def v1_error_envelope(status_code: int, request_id: str) -> dict[str, Any]:
    """The versioned envelope for a status code.

    Shared with the API gateway (``api.security``) so auth / rate-limit errors
    on ``/api/v1/*`` honour the same ``{"error": {...}}`` contract as every
    other non-2xx v1 response.
    """
    return _envelope_for_status(status_code, request_id)


def _spa_fallback(request: Request) -> JSONResponse | FileResponse:
    """The web SPA fallback for unknown routes (unchanged behaviour).

    Unknown non-``/api`` paths serve the built SPA shell (client-side routing);
    unknown ``/api`` paths stay JSON.
    """
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if (_FRONTEND_DIST / "index.html").exists():
        return FileResponse(_FRONTEND_DIST / "index.html")
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


def register_v1_error_handlers(app: FastAPI) -> None:
    """Attach the versioned error envelope to the v1 sub-app.

    Only ever called on the mounted ``/api/v1`` app, so every request seen
    here is versioned -- the envelope applies unconditionally.
    """

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = get_request_id(request.scope)
        envelope = _envelope_for_status(exc.status_code, request_id)
        if (
            exc.status_code < 500
            and exc.detail is not None
            and isinstance(exc.detail, str)
        ):
            envelope["error"]["detail"] = exc.detail
        return JSONResponse(status_code=exc.status_code, content=envelope)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = get_request_id(request.scope)
        detail = [
            {"loc": [str(p) for p in err.get("loc", [])], "msg": err.get("msg", "invalid")}
            for err in exc.errors()
        ]
        envelope = build_error_envelope(
            "validation_error",
            "Validation error.",
            request_id,
            detail=detail,
        )
        return JSONResponse(status_code=422, content=envelope)

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id(request.scope)
        # The full traceback is logged server-side; the client gets only the
        # generic message so internals never leak.
        logger.exception("unhandled error: request_id=%s", request_id, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_envelope_for_status(500, request_id),
        )


def register_web_error_handlers(app: FastAPI) -> None:
    """Attach the web app's existing error behaviour (SPA fallback + detail).

    The unversioned surface keeps exactly what it had before v1 was split out:
    unknown client-side routes serve the built SPA shell, unknown ``/api``
    paths stay JSON, validation keeps the default ``{"detail": ...}`` shape,
    and unhandled errors re-raise so the outer ServerErrorMiddleware returns
    the default plain-text 500.
    """

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse | FileResponse:
        if exc.status_code == 404:
            return _spa_fallback(request)
        # Preserve the web API's existing {"detail": ...} contract.
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Keep FastAPI's default web validation shape untouched.
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        # Re-raise so the outer ServerErrorMiddleware keeps the web app's
        # default 500 behaviour (plain text) exactly as before.
        raise exc
