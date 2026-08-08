"""CyberRisk engine module (re-export shim).

Re-exports ``cyberrisk.sensitivity`` without moving code, so ``engine.sensitivity`` addresses the
same canonical implementation.
"""

from cyberrisk.sensitivity import *  # noqa: F401,F403
