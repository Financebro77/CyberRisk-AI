"""CyberRisk engine module (re-export shim).

Re-exports ``cyberrisk.credibility`` without moving code, so ``engine.credibility`` addresses the
same canonical implementation.
"""

from cyberrisk.credibility import *  # noqa: F401,F403
