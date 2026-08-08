"""CyberRisk AI web API layer.

A thin FastAPI layer over the existing tool functions in
``cyberrisk.agent.tools`` and ``cyberrisk.agent.sensitivity_tools``.

The quantitative engine and the DeepSeek agent layer are consumed
read-only -- this package adds no new risk logic.  Every endpoint wraps one
of the existing JSON-serialisable tool functions and returns its dict as
the response body.
"""

from cyberrisk.api.main import app

__all__ = ["app"]
