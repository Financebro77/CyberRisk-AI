"""FastAPI entrypoint for the CyberRisk AI web platform.

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

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cyberrisk import __version__
from cyberrisk.api.chat import router as chat_router
from cyberrisk.api.routes import router

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
    title="CyberRisk AI",
    description="Marsh/Aon-style commercial cyber risk assessment, loss modelling and insurance structuring.",
    version=__version__,
)

# CORS: allow the Vite dev server (localhost:5173) during development and the
# production origin.  In production the frontend is served same-origin by this
# app, so no extra origin is needed there.  A production deployment should
# configure the real deployment origin explicitly rather than leaving the
# localhost allow-list in place.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(chat_router, prefix="/api")


@app.get("/", response_model=None)
def index() -> FileResponse | dict:
    """Serve the built SPA if present, otherwise point to the dev server."""
    if (FRONTEND_DIST / "index.html").exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return {
        "service": "CyberRisk AI",
        "docs": "/docs",
        "note": "Frontend not built yet. Run the Vite dev server in app/frontend, or npm run build first.",
    }


# Serve built static assets (and the SPA fallback for client-side routes).
if (FRONTEND_DIST / "index.html").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.exception_handler(404)
    async def _spa_fallback(request, _exc) -> FileResponse:
        # Any unknown non-/api path serves the SPA shell; the client router
        # takes over from there.  API 404s stay JSON (raised by the router).
        from fastapi.responses import JSONResponse

        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        return FileResponse(FRONTEND_DIST / "index.html")
