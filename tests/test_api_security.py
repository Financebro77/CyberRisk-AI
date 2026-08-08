"""API security tests: opt-in auth + rate limiting.

No network.  Uses FastAPI's TestClient against the real app with env vars
manipulated to enable/disable auth and rate limiting.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cyberrisk.api.main import app
from cyberrisk.api.security import _reset_rate_limits


@pytest.fixture(autouse=True)
def _isolate_api_security(monkeypatch):
    """Default: auth and rate limiting are both OFF."""
    monkeypatch.delenv("CYBERRISK_API_KEY", raising=False)
    monkeypatch.delenv("CYBERRISK_RATE_LIMIT", raising=False)
    _reset_rate_limits()
    yield
    _reset_rate_limits()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_open_api_without_key(client):
    """When no CYBERRISK_API_KEY is set, the API is open (default dev mode)."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_auth_required_when_key_set(client, monkeypatch):
    """When CYBERRISK_API_KEY is set, /api routes require the bearer key."""
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    resp = client.get("/api/scenarios")
    assert resp.status_code == 401
    assert "API key" in resp.json()["detail"]


def test_valid_key_allowed(client, monkeypatch):
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    resp = client.get(
        "/api/scenarios",
        headers={"Authorization": "Bearer test-secret-key"},
    )
    assert resp.status_code == 200
    assert "scenarios" in resp.json()


def test_wrong_key_rejected(client, monkeypatch):
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    resp = client.get(
        "/api/scenarios",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_health_is_exempt_when_auth_enabled(client, monkeypatch):
    """Health stays open even with auth on, so the Docker healthcheck works."""
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_rate_limit_enforces_429(client, monkeypatch):
    """With CYBERRISK_RATE_LIMIT=2, a third request in the window is 429.

    Uses /api/scenarios (a real, non-exempt route).  /api/health is exempt
    by design so the Docker healthcheck is never rate-limited.
    """
    monkeypatch.setenv("CYBERRISK_RATE_LIMIT", "2")
    for _ in range(2):
        assert client.get("/api/scenarios").status_code == 200
    # Third request within the window -> 429.
    resp = client.get("/api/scenarios")
    assert resp.status_code == 429
    assert "Rate limit" in resp.json()["detail"]


def test_rate_limit_resets_between_tests(client, monkeypatch):
    """Each test starts with a clean window (the autouse fixture resets)."""
    monkeypatch.setenv("CYBERRISK_RATE_LIMIT", "2")
    for _ in range(2):
        assert client.get("/api/scenarios").status_code == 200
    # Still limited within this test's window.
    assert client.get("/api/scenarios").status_code == 429


def test_health_is_never_rate_limited(client, monkeypatch):
    """/api/health is exempt so the container healthcheck always passes."""
    monkeypatch.setenv("CYBERRISK_RATE_LIMIT", "2")
    for _ in range(5):  # well over the limit
        assert client.get("/api/health").status_code == 200
