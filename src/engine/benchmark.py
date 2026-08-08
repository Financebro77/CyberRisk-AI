"""CyberRisk engine module (re-export shim).

Re-exports ``cyberrisk.benchmark`` without moving code, so ``engine.benchmark`` addresses the
same canonical implementation.
"""

from cyberrisk.benchmark import *  # noqa: F401,F403
