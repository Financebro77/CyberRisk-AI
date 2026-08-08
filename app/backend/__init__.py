"""CyberRisk AI web backend (FastAPI).

Re-exports the FastAPI application from the canonical ``cyberrisk.api.main``
module so the backend can be launched from the ``app/`` layout:

    python -m uvicorn app.backend:app --host 0.0.0.0 --port 8000

The real implementation lives in ``src/cyberrisk/api/main.py`` — this module
is a thin, import-stable alias that keeps the deployment surface in the
``app/`` directory.
"""

from __future__ import annotations

from cyberrisk.api.main import app  # noqa: F401
