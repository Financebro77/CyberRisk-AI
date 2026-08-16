"""The versioned mobile API as a FastAPI sub-app.

Built as its own app and mounted at ``/api/v1`` on the main app, so v1 gets
private error handling: every non-2xx response uses the envelope, and the web
app's SPA fallback / ``{"detail": ...}`` behaviour is untouched -- no path
sniffing required.  The outer app's middleware (CORS, auth + rate limiting,
request-context) still wraps this sub-app, so ``/api/v1/*`` is guarded exactly
like the web routes.
"""

from __future__ import annotations

from fastapi import FastAPI

from cyberrisk import __version__
from cyberrisk.api.v1.errors import register_v1_error_handlers
from cyberrisk.api.v1.routes import router

app = FastAPI(
    title="CyberRisk AI mobile API",
    description="Versioned assessment surface for mobile clients.",
    version=__version__,
)

app.include_router(router)
register_v1_error_handlers(app)
