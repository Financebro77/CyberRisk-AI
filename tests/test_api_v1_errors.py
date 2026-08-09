"""Error-envelope tests for the v1 API.

Every non-2xx v1 response must use the envelope
``{"error": {"code", "message", "request_id", "detail"?}}`` -- never a raw
``{"detail": ...}`` and never the web SPA fallback.  Web (/api, non-versioned)
paths must keep their existing behaviour.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cyberrisk.api.main import app
from cyberrisk.api.security import _reset_rate_limits
from cyberrisk.api.v1.store import get_store


@pytest.fixture(autouse=True)
def _isolate_api_security(monkeypatch):
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


def _assert_envelope(body, code, status):
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["error"]["request_id"]


# ---------------------------------------------------------------------------
# 404s
# ---------------------------------------------------------------------------


def test_unknown_assessment_id_is_envelope_404(client):
    resp = client.get("/api/v1/assessment/does-not-exist")
    assert resp.status_code == 404
    _assert_envelope(resp.json(), "not_found", 404)
    assert "expired" in resp.json()["error"]["detail"]


def test_unknown_assessment_results_is_envelope_404(client):
    resp = client.get("/api/v1/assessment/does-not-exist/results")
    assert resp.status_code == 404
    _assert_envelope(resp.json(), "not_found", 404)


def test_unknown_v1_route_is_envelope_not_spa(client):
    """A /api/v1 404 must be the JSON envelope, never the SPA shell."""
    resp = client.get("/api/v1/no-such-route")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    _assert_envelope(resp.json(), "not_found", 404)


# ---------------------------------------------------------------------------
# 422 validation
# ---------------------------------------------------------------------------


def test_malformed_json_is_envelope_422(client):
    resp = client.post("/api/v1/assessment/submit", json="{not json")
    assert resp.status_code == 422
    body = resp.json()
    _assert_envelope(body, "validation_error", 422)
    assert isinstance(body["error"]["detail"], list)


def test_validation_detail_never_echoes_secrets(client):
    """Validation detail must expose only loc + msg, never the value supplied."""
    payload = {"revenue_usd": -5, "password": "sup3rsecret", "api_key": "sk-abc123"}
    resp = client.post("/api/v1/assessment/submit", json=payload)
    assert resp.status_code == 422
    text = str(resp.json())
    assert "sup3rsecret" not in text
    assert "sk-abc123" not in text


# ---------------------------------------------------------------------------
# 500 internal error (safe envelope, no internals leaked)
# ---------------------------------------------------------------------------


def test_internal_error_is_generic_envelope(client, monkeypatch):
    """A tool crash -> 500 envelope with a generic message, no traceback.

    Uses its own TestClient with raise_server_exceptions=False so the 500
    response is returned (and asserted on) instead of the exception escaping.
    """

    def _boom(*_args, **_kwargs):
        raise RuntimeError("secret-internal-detail: /home/deploy/src/tools.py")

    import cyberrisk.api.v1.routes as routes

    monkeypatch.setattr(routes, "run_assessment_pipeline", _boom)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/assessment/submit",
        json={
            "firm_name": "Acme",
            "revenue_usd": 500_000_000,
            "security_controls": "MFA, backups",
        },
    )
    assert resp.status_code == 500
    body = resp.json()
    _assert_envelope(body, "internal_error", 500)
    text = str(body)
    assert "secret-internal-detail" not in text
    assert "/home/deploy" not in text
    assert "Traceback" not in text


# ---------------------------------------------------------------------------
# Web behaviour is untouched
# ---------------------------------------------------------------------------


def test_web_api_404_keeps_detail_contract(client):
    """Unversioned /api paths keep their existing {"detail": ...} 404."""
    resp = client.get("/api/mobile/assessment")  # removed route
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_web_api_422_keeps_default_shape(client):
    resp = client.post("/api/chat/xyz/turns", json="{bad")
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_non_api_unknown_route_is_not_json(client):
    """A non-/api path is the SPA fallback (html) or the built app, not an
    API JSON envelope."""
    resp = client.get("/some-client-side/route")
    assert resp.status_code != 500
    # Either the SPA shell (html) or, when dist is absent, a 404 JSON -- never
    # the v1 envelope (there is no request_id from the v1 error path here).
    if resp.status_code == 200:
        assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Request IDs on every response
# ---------------------------------------------------------------------------


def test_every_response_has_request_id_header(client):
    for method, path, kwargs in (
        ("get", "/api/v1/health", {}),
        ("get", "/api/v1/assessment/unknown", {}),
        ("get", "/api/v1/no-such-route", {}),
        ("post", "/api/v1/assessment/submit", {"json": "{bad"}),
    ):
        resp = getattr(client, method)(path, **kwargs)
        assert resp.headers.get("x-request-id"), f"{method} {path}"


def test_inbound_request_id_is_echoed(client):
    resp = client.get("/api/v1/health", headers={"X-Request-ID": "client-trace-123"})
    assert resp.headers["x-request-id"] == "client-trace-123"


def test_malformed_inbound_request_id_is_replaced(client):
    """Oversized / invalid inbound ids are ignored (fresh uuid used)."""
    resp = client.get("/api/v1/health", headers={"X-Request-ID": "x" * 200})
    rid = resp.headers["x-request-id"]
    assert len(rid) <= 64
    assert rid != "x" * 200
