"""CyberRisk engine module (re-export shim).

Re-exports ``cyberrisk.frequency`` without moving code, so ``engine.frequency`` addresses the
same canonical implementation.
"""

from cyberrisk.frequency import *  # noqa: F401,F403
