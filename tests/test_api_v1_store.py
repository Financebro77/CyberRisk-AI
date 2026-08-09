"""Unit tests for the v1 in-memory AssessmentStore (no network, no engine)."""

from __future__ import annotations

import threading
import time


from cyberrisk.api.v1.store import AssessmentStore


def test_create_records_pending_entry():
    store = AssessmentStore()
    entry = store.create("abc", status="pending", required_fields=["revenue_usd"])
    assert entry.assessment_id == "abc"
    assert entry.status == "pending"
    assert entry.required_fields == ["revenue_usd"]
    assert entry.result is None


def test_get_returns_unknown_as_none():
    store = AssessmentStore()
    assert store.get("nope") is None
    assert store.get_result("nope") is None


def test_store_result_upserts_unknown_id():
    """store_result must create the entry when the id was never started."""
    store = AssessmentStore()
    entry = store.store_result("fresh", "ok", result={"risk_score": 50.0})
    assert entry.status == "ok"
    assert store.get_result("fresh").result == {"risk_score": 50.0}


def test_resubmit_refreshes_idempotently():
    """Re-submitting under the same id refreshes the result, not duplicates."""
    store = AssessmentStore()
    store.store_result("a", "ok", result={"risk_score": 10.0})
    store.store_result("a", "ok", result={"risk_score": 20.0})
    assert len(store) == 1
    assert store.get_result("a").result == {"risk_score": 20.0}


def test_get_result_returns_none_when_pending():
    store = AssessmentStore()
    store.create("p", status="pending", required_fields=[])
    assert store.get("p") is not None  # status view exists
    assert store.get_result("p") is None  # but no finished result


def test_ttl_eviction():
    store = AssessmentStore(max_age_seconds=1)
    store.store_result("old", "ok", result={})
    time.sleep(1.1)
    assert store.get("old") is None
    assert store.get_result("old") is None


def test_max_entries_bounds_memory():
    store = AssessmentStore(max_entries=2)
    store.store_result("a", "ok", result={})
    store.store_result("b", "ok", result={})
    store.store_result("c", "ok", result={})
    assert len(store) == 2
    # The oldest entries are evicted; the newest survive.
    assert store.get("c") is not None
    assert store.get("a") is None


def test_clear_empties_store():
    store = AssessmentStore()
    store.store_result("a", "ok", result={})
    store.clear()
    assert len(store) == 0


def test_thread_safety_no_corruption():
    """Concurrent writes must not lose entries or raise (Lock held)."""
    store = AssessmentStore(max_entries=100)
    errors: list[Exception] = []

    def writer(i: int) -> None:
        try:
            for _ in range(50):
                store.store_result(f"id-{i}", "ok", result={"i": i})
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(store) == 8  # one per writer thread


def test_shared_singleton_is_stable():
    """get_store() returns the same process-wide store every call."""
    from cyberrisk.api.v1.store import get_store

    assert get_store() is get_store()
