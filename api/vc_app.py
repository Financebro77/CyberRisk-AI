"""Vercel serverless entrypoint for the CyberRisk AI FastAPI app.

Vercel's Python runtime bundles the repository at the function root but does
not install the ``src/``-layout ``cyberrisk`` package, so ``src/`` is put on
``sys.path`` explicitly before the app module is imported.  The app is the
single ASGI process that serves both the ``/api/*`` routes and the built React
SPA (``app/frontend/dist``, mounted with an SPA fallback in
``cyberrisk.api.main``).  Vercel's FastAPI static-file hook detects that
``StaticFiles`` mount at build time and promotes it to the CDN edge, so real
artifacts (``index.html``, ``/assets/*``, ``voice.html``) are served without
invoking the function and every other path (``/api/*``, ``/docs``, unknown
client-side routes) falls through to this function.
"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cyberrisk.api.main import app  # noqa: E402
