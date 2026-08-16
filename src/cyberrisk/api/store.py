"""Generic bounded, TTL-capable in-process store.

Dev-grade storage shared by the chat-session store and the v1 assessment
store: entries live in process memory, are thread-safe, and are bounded so a
long-running process cannot grow without limit.  A production deployment
should back these with Redis / Postgres so ids survive a restart or a
multi-worker process.

Eviction is lazy on the read path (an expired entry drops on access) plus a
soft size cap on writes (oldest entries evicted first), so memory stays
bounded even when keys are never touched again.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class BoundedStore(Generic[K, V]):
    """Thread-safe dict with a size cap and an optional TTL.

    ``put`` evicts expired entries, then the oldest beyond ``max_entries``
    (FIFO by insertion sequence, so the eviction order stays deterministic
    even when timestamps tie).  ``get`` performs an O(1) TTL check and drops
    the entry when expired.  Values must not be ``None`` (``None`` means
    "absent").
    """

    def __init__(
        self,
        *,
        max_entries: int,
        max_age_seconds: float | None = None,
        on_evict: Callable[[K], None] | None = None,
    ) -> None:
        self._max_entries = max_entries
        self._max_age_seconds = max_age_seconds
        self._on_evict = on_evict
        self._data: dict[K, tuple[V, int, float]] = {}  # key -> (value, seq, created_at)
        self._seq = 0
        self._lock = threading.Lock()

    def put(self, key: K, value: V) -> V:
        """Store a value, replacing any existing entry (upsert).

        Evicts to stay within bounds.  Restarting the TTL on a replace is
        intentional: a refreshed id is a fresh id.
        """
        with self._lock:
            self._evict_locked()
            self._seq += 1
            self._data[key] = (value, self._seq, time.time())
        return value

    def get(self, key: K) -> V | None:
        """The value, or ``None`` when absent / expired (expired entries drop)."""
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            _value, _seq, created = item
            if self._expired(created):
                self._data.pop(key, None)
                self._notify_evict(key)
                return None
            return _value

    def pop(self, key: K) -> V | None:
        """Remove and return the value (``None`` when absent).

        Explicit removal -- ``on_evict`` is NOT fired; the caller owns any
        bookkeeping (e.g. the per-session lock in the chat store).
        """
        with self._lock:
            item = self._data.pop(key, None)
            return item[0] if item is not None else None

    def clear(self) -> None:
        """Drop every entry (used by tests)."""
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    # -- internals -------------------------------------------------------

    def _expired(self, created_at: float) -> bool:
        return (
            self._max_age_seconds is not None
            and time.time() - created_at > self._max_age_seconds
        )

    def _notify_evict(self, key: K) -> None:
        if self._on_evict is not None:
            self._on_evict(key)

    def _evict_locked(self) -> None:
        """Drop expired entries, then the oldest beyond the size cap.

        Called with ``_lock`` held.  ``time.time()`` is monotone-enough here
        (wall-clock is fine for a TTL).
        """
        if self._max_age_seconds is not None:
            stale = [k for k, item in self._data.items() if self._expired(item[2])]
            for k in stale:
                self._data.pop(k, None)
                self._notify_evict(k)
        # Evict BEFORE the insert: when already at the cap, dropping the oldest
        # makes room so the store never exceeds _max_entries.
        if len(self._data) >= self._max_entries:
            # Drop the oldest entries (by insertion sequence) until one slot is
            # free for the upcoming insert.
            ordered = sorted(self._data, key=lambda k: self._data[k][1])
            to_evict = len(self._data) - self._max_entries + 1
            for k in ordered[:to_evict]:
                self._data.pop(k, None)
                self._notify_evict(k)
