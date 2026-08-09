"""In-memory assessment store for the versioned mobile API.

Mirrors the pattern used by the chat session store (``api/chat.py``): entries
live in process memory, are thread-safe, and are bounded so a long-running
process cannot grow without limit.  This is explicitly dev-grade -- a
production deployment should back the store with Redis/Postgres so assessment
ids survive a restart or a multi-worker process.

Lifecycle: ``start`` inserts a pending entry; ``submit`` stores the finished
result under the same id (idempotent -- re-submitting refreshes the entry);
``get`` returns the status view; ``get_result`` returns the full result.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

_MAX_AGE_SECONDS = 3600  # an assessment result is valid for one hour
_MAX_ENTRIES = 64  # bound memory like the chat store's 32-session bound


@dataclass
class AssessmentEntry:
    """One assessment's lifecycle state."""

    assessment_id: str
    status: str  # "pending" | "ok" | "insufficient_info"
    required_fields: list[str] = field(default_factory=list)
    needed: list[str] = field(default_factory=list)
    message: str = ""
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)


class AssessmentStore:
    """Thread-safe, TTL-bounded store keyed by assessment id.

    Eviction is lazy (on access) plus a soft cap on entry count, so memory
    stays bounded even when ids are never touched again.
    """

    def __init__(
        self,
        *,
        max_age_seconds: int = _MAX_AGE_SECONDS,
        max_entries: int = _MAX_ENTRIES,
    ) -> None:
        self._max_age_seconds = max_age_seconds
        self._max_entries = max_entries
        self._entries: dict[str, AssessmentEntry] = {}
        self._lock = threading.Lock()

    # -- lifecycle -------------------------------------------------------

    def create(self, assessment_id: str, status: str, required_fields: list[str]) -> AssessmentEntry:
        entry = AssessmentEntry(
            assessment_id=assessment_id,
            status=status,
            required_fields=required_fields,
        )
        with self._lock:
            self._evict_locked()
            self._entries[assessment_id] = entry
        return entry

    def store_result(
        self,
        assessment_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        needed: list[str] | None = None,
        message: str = "",
    ) -> AssessmentEntry:
        """Record a finished assessment (ok or insufficient_info).

        Upsert: creates the entry when the id is unknown, or refreshes an
        existing one (idempotent re-submit; the timestamp resets so the TTL
        restarts).
        """
        with self._lock:
            self._evict_locked()
            existing = self._entries.get(assessment_id)
            if existing is None:
                existing = AssessmentEntry(
                    assessment_id=assessment_id,
                    status=status,
                    needed=needed or [],
                    message=message,
                    result=result,
                )
                self._entries[assessment_id] = existing
                return existing
            existing.status = status
            existing.result = result
            existing.needed = needed or []
            existing.message = message
            existing.created_at = time.time()  # refresh TTL
            return existing

    # -- reads -----------------------------------------------------------

    def get(self, assessment_id: str) -> AssessmentEntry | None:
        """The status view entry, or None when unknown / expired."""
        with self._lock:
            self._evict_locked()
            entry = self._entries.get(assessment_id)
            if entry is None:
                return None
            return entry

    def get_result(self, assessment_id: str) -> AssessmentEntry | None:
        """The entry only when a finished result exists, else None."""
        entry = self.get(assessment_id)
        if entry is None or entry.result is None:
            return None
        return entry

    # -- internals -------------------------------------------------------

    def _evict_locked(self) -> None:
        """Drop expired entries, then the oldest beyond the size cap.

        Called with ``_lock`` held.  ``time.time()`` is monotone-enough here
        (wall-clock is fine for a TTL).
        """
        now = time.time()
        stale = [
            aid
            for aid, e in self._entries.items()
            if now - e.created_at > self._max_age_seconds
        ]
        for aid in stale:
            self._entries.pop(aid, None)
        # Evict BEFORE the insert: when already at the cap, dropping the oldest
        # makes room so the store never exceeds _max_entries.
        if len(self._entries) >= self._max_entries:
            # Drop the oldest entries (by creation time) until under the cap.
            ordered = sorted(self._entries, key=lambda aid: self._entries[aid].created_at)
            for aid in ordered[: len(self._entries) - self._max_entries + 1]:
                self._entries.pop(aid, None)

    def clear(self) -> None:
        """Drop every entry (used by tests)."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


# Shared process-wide store so the same assessment id is visible across routes.
_store = AssessmentStore()


def get_store() -> AssessmentStore:
    """The process-wide assessment store."""
    return _store
