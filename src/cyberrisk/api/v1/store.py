"""In-memory assessment store for the versioned mobile API.

Built on the generic ``BoundedStore`` (the same dev-grade storage the chat
session store uses): entries live in process memory, are thread-safe, and are
bounded so a long-running process cannot grow without limit.  A production
deployment should back the store with Redis/Postgres so assessment ids
survive a restart or a multi-worker process.

Lifecycle: ``start`` inserts a pending entry; ``submit`` stores the finished
result under the same id (idempotent -- re-submitting refreshes the entry);
``get`` returns the status view; ``get_result`` returns the full result.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from cyberrisk.api.store import BoundedStore

_MAX_AGE_SECONDS = 3600  # an assessment result is valid for one hour
_MAX_ENTRIES = 64  # bound memory like the chat store's 32-session bound


@dataclass
class AssessmentEntry:
    """One assessment's lifecycle state."""

    assessment_id: str
    # "pending" | "ready" | "ok" | "insufficient_info" | "error"
    status: str
    required_fields: list[str] = field(default_factory=list)
    needed: list[str] = field(default_factory=list)
    message: str = ""
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)


class AssessmentStore:
    """Thread-safe, TTL-bounded store keyed by assessment id.

    A thin typed facade over the generic ``BoundedStore``; the bound + TTL
    eviction is owned by the shared store.
    """

    def __init__(
        self,
        *,
        max_age_seconds: int = _MAX_AGE_SECONDS,
        max_entries: int = _MAX_ENTRIES,
    ) -> None:
        self._store: BoundedStore[str, AssessmentEntry] = BoundedStore(
            max_entries=max_entries,
            max_age_seconds=max_age_seconds,
        )

    # -- lifecycle -------------------------------------------------------

    def create(self, assessment_id: str, status: str, required_fields: list[str]) -> AssessmentEntry:
        entry = AssessmentEntry(
            assessment_id=assessment_id,
            status=status,
            required_fields=required_fields,
        )
        self._store.put(assessment_id, entry)
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

        Upsert: replaces any existing entry (idempotent re-submit; the fresh
        timestamp restarts the TTL).
        """
        entry = AssessmentEntry(
            assessment_id=assessment_id,
            status=status,
            needed=needed or [],
            message=message,
            result=result,
        )
        self._store.put(assessment_id, entry)
        return entry

    # -- reads -----------------------------------------------------------

    def get(self, assessment_id: str) -> AssessmentEntry | None:
        """The status view entry, or None when unknown / expired."""
        return self._store.get(assessment_id)

    def get_result(self, assessment_id: str) -> AssessmentEntry | None:
        """The entry only when a finished result exists, else None."""
        entry = self._store.get(assessment_id)
        if entry is None or entry.result is None:
            return None
        return entry

    # -- tests -----------------------------------------------------------

    def clear(self) -> None:
        """Drop every entry (used by tests)."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# Shared process-wide store so the same assessment id is visible across routes.
_store = AssessmentStore()


def get_store() -> AssessmentStore:
    """The process-wide assessment store."""
    return _store
