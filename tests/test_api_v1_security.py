"""Security + privacy tests for the v1 API.

* Auth and rate limiting inherited from APIGatewayMiddleware must apply to
  /api/v1/* (except health).
* A privacy scan walks a full assessment lifecycle and asserts no secret,
  PII, env-var name, filesystem path, or internal prompt leaks into any
  response body.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cyberrisk.api.main import app
from cyberrisk.api.security import _reset_rate_limits
from cyberrisk.api.v1.store import get_store


@pytest.fixture(autouse=True)
def _isolate_api_security(monkeypatch):
    """Default: auth and rate limiting are both OFF."""
    monkeypatch.delenv("CYBERRISK_API_KEY", raising=False)
    monkeypatch.delenv("CYBERRISK_RATE_LIMIT", raising=False)
    _reset_rate_limits()
    yield
    _reset_rate_limits()


@pytest.fixture(autouse=True)
def _clean_store():
    get_store().clear()
    yield
    get_store().clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


FULL_BRIEF = {
    "firm_name": "Acme Healthcare",
    "industry": "Healthcare",
    "revenue_usd": 500_000_000,
    "customer_records": 2_000_000,
    "technology_dependency": "Critical - patient records and billing are online",
    "security_controls": (
        "MFA enforced on all remote access, endpoint detection installed, "
        "offline backups taken nightly, phishing training quarterly"
    ),
    "previous_incidents": 1,
    "existing_coverage": "Standalone cyber policy with a $10M limit and $1M deductible",
    "risk_appetite": "Moderate",
}


# ---------------------------------------------------------------------------
# Auth (inherited from the gateway)
# ---------------------------------------------------------------------------


def test_v1_requires_key_when_configured(client, monkeypatch):
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    resp = client.post("/api/v1/assessment/start")
    assert resp.status_code == 401


def test_v1_accepts_valid_key(client, monkeypatch):
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    resp = client.post(
        "/api/v1/assessment/start",
        headers={"Authorization": "Bearer test-secret-key"},
    )
    assert resp.status_code == 201


def test_v1_rejects_wrong_key(client, monkeypatch):
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    resp = client.post(
        "/api/v1/assessment/start",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_v1_health_exempt_from_auth(client, monkeypatch):
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    assert client.get("/api/v1/health").status_code == 200


# ---------------------------------------------------------------------------
# Rate limiting (inherited from the gateway)
# ---------------------------------------------------------------------------


def test_v1_route_is_rate_limited(client, monkeypatch):
    monkeypatch.setenv("CYBERRISK_RATE_LIMIT", "2")
    for _ in range(2):
        assert client.post("/api/v1/assessment/start", json={}).status_code == 201
    assert client.post("/api/v1/assessment/start", json={}).status_code == 429


def test_v1_health_is_never_rate_limited(client, monkeypatch):
    monkeypatch.setenv("CYBERRISK_RATE_LIMIT", "2")
    for _ in range(5):
        assert client.get("/api/v1/health").status_code == 200


def test_auth_401_has_request_id_header(client, monkeypatch):
    """Even the gateway's raw 401 carries X-Request-ID (outermost middleware)."""
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    resp = client.get("/api/v1/assessment/start")
    assert resp.status_code == 401
    assert resp.headers.get("x-request-id")


# ---------------------------------------------------------------------------
# Privacy scan across a full lifecycle
# ---------------------------------------------------------------------------


# Anything that would reveal THIS app's secrets, PII, env layout, or internals.
# Markers are deliberately narrow: the knowledge-base content the API returns
# (evidence citations/incidents) legitimately talks about cyber risk, so common
# words like "password" or "secret" are NOT indicators of leakage here.
_FORBIDDEN_MARKERS = (
    # Env / config internals.
    "CYBERRISK_API_KEY",
    "CYBERRISK_RATE_LIMIT",
    "CYBERRISK_CORS_ORIGINS",
    "ENV_",
    # Auth material (would indicate the header/key was echoed).
    "Authorization",
    "Bearer ",
    "test-secret-key",
    "sk-",
    # Filesystem / repo internals.
    "C:\\",
    "c:\\",
    "/home/",
    "/Users/",
    "/usr/",
    "\\src\\",
    "Traceback",
    "dependencies.py",
    "service.py",
    "routes.py",
    "main.py",
    # Model / provider internals (would indicate internal prompts leaked).
    "deepseek",
    "anthropic",
    "openai",
    "claude",
    "system prompt",
)


def test_privacy_scan_lifecycle(client, monkeypatch):
    """No forbidden marker appears in ANY response across the lifecycle.

    Includes the error paths (404/422/429) and both auth-on and auth-off runs.
    """
    monkeypatch.delenv("CYBERRISK_API_KEY", raising=False)

    calls = []
    # auth-off lifecycle
    calls.append(client.get("/api/v1/health"))
    start = client.post("/api/v1/assessment/start", json={})
    calls.append(start)
    aid = start.json()["assessment_id"]
    calls.append(client.get(f"/api/v1/assessment/{aid}"))
    calls.append(client.post("/api/v1/assessment/submit", json=FULL_BRIEF))
    calls.append(client.get("/api/v1/assessment/nope/results"))
    calls.append(client.post("/api/v1/assessment/submit", json="{bad"))
    calls.append(client.get("/api/v1/no-such-route"))

    # auth-on lifecycle (valid key)
    monkeypatch.setenv("CYBERRISK_API_KEY", "test-secret-key")
    calls.append(
        client.post(
            "/api/v1/assessment/start",
            json={},
            headers={"Authorization": "Bearer test-secret-key"},
        )
    )
    # auth-on rejection (wrong key) -> 401
    calls.append(
        client.get("/api/v1/assessment/start", headers={"Authorization": "Bearer wrong-key"})
    )

    for resp in calls:
        text = f"{resp.status_code} {resp.text}"
        for marker in _FORBIDDEN_MARKERS:
            assert marker.lower() not in text.lower(), (
                f"privacy leak in {resp.status_code} response: {marker!r}\n{resp.text[:400]}"
            )


def test_rate_limited_response_has_no_secrets(client, monkeypatch):
    monkeypatch.delenv("CYBERRISK_API_KEY", raising=False)
    monkeypatch.setenv("CYBERRISK_RATE_LIMIT", "1")
    client.post("/api/v1/assessment/start", json={})
    resp = client.post("/api/v1/assessment/start", json={})
    assert resp.status_code == 429
    assert "Rate limit" in resp.text
    for marker in ("CYBERRISK", "secret", "api_key"):
        assert marker.lower() not in resp.text.lower()
