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

The handlers are PATH-AWARE so the unversioned web application is untouched:
only ``/api/v1/*`` requests get the envelope.  Web requests keep their existing
behaviour -- the SPA fallback for unknown client-side routes, and the
``{"detail": ...}`` JSON contract for web API errors.
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


def _is_v1(path: str) -> bool:
    return path.startswith("/api/v1")


# HTTP status -> error code.  Codes are stable API surface.
_STATUS_TO_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}

_STATUS_MESSAGES = {
    400: "Bad request.",
    401: "Unauthorized. Provide a valid API key.",
    403: "Forbidden.",
    404: "Not found.",
    409: "Conflict.",
    422: "Validation error.",
    429: "Rate limit exceeded. Try again shortly.",
    500: "An internal error occurred.",
    503: "The service is currently unavailable.",
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
    code = _STATUS_TO_CODE.get(status_code, "error")
    return build_error_envelope(
        code,
        _STATUS_MESSAGES.get(status_code, "Error."),
        request_id,
    )


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
    """Attach path-aware error handlers to the FastAPI app.

    ``/api/v1/*`` requests get the versioned envelope; everything else keeps the
    web application's existing behaviour (SPA fallback + ``{"detail": ...}``).
    """

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse | FileResponse:
        if not _is_v1(request.url.path):
            if exc.status_code == 404:
                return _spa_fallback(request)
            # Preserve the web API's existing {"detail": ...} contract.
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

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
        if not _is_v1(request.url.path):
            # Keep FastAPI's default web validation shape untouched.
            return JSONResponse(status_code=422, content={"detail": exc.errors()})

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
        if not _is_v1(request.url.path):
            # Re-raise so the outer ServerErrorMiddleware keeps the web app's
            # default 500 behaviour (plain text) exactly as before.
            raise exc

        request_id = get_request_id(request.scope)
        # The full traceback is logged server-side; the client gets only the
        # generic message so internals never leak.
        logger.exception("unhandled error: request_id=%s", request_id, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_envelope_for_status(500, request_id),
        )
