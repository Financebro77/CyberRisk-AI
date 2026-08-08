"""Deterministic update log for the knowledge auto-update system.

Writes ``derived/update/updates.log`` — a plain-text, timestamped, append-only
record of every event the auto-update performs (file registered, ingested,
embedded, error).  The log is how the user sees what the system did; the
``report.json`` (written by update.py) is the machine-readable summary.

Deterministic and idempotent: a second run with no new files writes no
events.  Timestamps are UTC ISO.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class UpdateLogger:
    """Append-only update logger to derived/update/updates.log."""

    def __init__(self, log_path: str | Path) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        """Append a timestamped line to the log."""
        ts = datetime.now(timezone.utc).isoformat()
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(f"{ts}  {message}\n")

    def clear(self) -> None:
        """Reset the log (used at the start of a full update run)."""
        self.log_path.write_text("", encoding="utf-8")

    def read(self) -> str:
        """Return the current log contents."""
        if not self.log_path.exists():
            return ""
        return self.log_path.read_text(encoding="utf-8")
