"""FastAPI entrypoint for the Armageddon web platform.

Run (dev):
    cd /path/to/project
    .venv/Scripts/python -m uvicorn cyberrisk.api.main:app --port 8000

The API wraps the existing tool layer read-only -- no engine or agent
module is modified.  In production the built frontend (app/frontend/dist)
is served as static files with an SPA fallback so a single process serves
both the API and the UI on :8000.  During development the Vite dev server
(app/frontend, port 5173) proxies /api -> :8000.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cyberrisk import __version__
from cyberrisk.api.chat import router as chat_router
from cyberrisk.api.routes import router
from cyberrisk.api.v1.app import app as v1_app
from cyberrisk.api.v1.errors import register_web_error_handlers
from cyberrisk.api.v1.middleware import RequestContextMiddleware

# Repo root: src/cyberrisk/api/main.py -> src/cyberrisk -> src -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FRONTEND_DIST = REPO_ROOT / "app" / "frontend" / "dist"

# Install the sanitised root logger so uvicorn/app log lines cannot leak a
# secret or personal data (see cyberrisk.privacy).
try:
    from cyberrisk.privacy import configure_sanitised_logging

    configure_sanitised_logging()
except ImportError:  # pragma: no cover - privacy module always present
    pass

app = FastAPI(
    title="Armageddon",
    description="Marsh/Aon-style commercial cyber risk assessment, loss modelling and insurance structuring.",
    version=__version__,
)

# CORS: allow the Vite dev server (localhost:5173), the mobile Streamlit
# client (localhost:8501) during development, and any production origins in
# CYBERRISK_CORS_ORIGINS (comma-separated).  In production the web frontend is
# served same-origin by this app, so no extra origin is needed there; a
# production deployment should configure the real deployment origins explicitly
# rather than leaving the localhost allow-list in place.
_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8501",
    "http://127.0.0.1:8501",
]
_extra = os.getenv("CYBERRISK_CORS_ORIGINS", "")
if _extra.strip():
    _cors_origins.extend(o.strip() for o in _extra.split(",") if o.strip())
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional API auth + rate limiting (opt-in via env — see api/security.py).
# Protects every /api/* route with a bearer key when CYBERRISK_API_KEY is set
# and rate-limits per client when CYBERRISK_RATE_LIMIT > 0.
from cyberrisk.api.security import APIGatewayMiddleware

app.add_middleware(APIGatewayMiddleware)

app.include_router(router, prefix="/api")
app.include_router(chat_router, prefix="/api")
# The versioned mobile API is its own sub-app: private error envelope, shared
# outer middleware (CORS, auth + rate limiting, request-context).
app.mount("/api/v1", v1_app)

# Request-context middleware: assign + echo X-Request-ID and log one line per
# request.  Registered last so it is the OUTERMOST middleware -- the id header
# is present even on the gateway's raw 401/429 responses.
app.add_middleware(RequestContextMiddleware)

# Web error behaviour: SPA fallback for unknown client-side routes, and the
# {"detail": ...} JSON contract for web API errors.  The v1 sub-app installs
# its own envelope handlers.
register_web_error_handlers(app)


@app.get("/", response_model=None)
def index() -> FileResponse | dict:
    """Serve the built SPA if present, otherwise point to the dev server."""
    if (FRONTEND_DIST / "index.html").exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return {
        "service": "Armageddon",
        "docs": "/docs",
        "note": "Frontend not built yet. Run the Vite dev server in app/frontend, or npm run build first.",
    }


# Serve the built multi-page frontend as static files so EVERY real artifact
# (index.html dashboard, voice.html PWA, manifest.webmanifest, sw.js, icons,
# /assets/*) is served as the actual file rather than falling through to the
# SPA shell.  Unknown client-side routes still fall through to the SPA shell
# via the path-aware error handlers in api/v1/errors.py (unchanged behaviour
# for non-/api paths), and unknown /api/* paths stay JSON.  Registering the
# mount last keeps the /api routers and FastAPI's own /docs ahead of it.
if (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="spa")
