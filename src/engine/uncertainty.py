"""CyberRisk engine module (re-export shim).

Re-exports ``cyberrisk.uncertainty`` without moving code, so ``engine.uncertainty`` addresses the
same canonical implementation.
"""

from cyberrisk.uncertainty import *  # noqa: F401,F403
