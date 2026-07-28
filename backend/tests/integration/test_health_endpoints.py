"""Integration tests for /health/live and /health/ready per Slice 2."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.runtime_readiness import (
    LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS,
    LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS,
    ReadinessState,
    reset_readiness_state,
    set_readiness_state,
)


@pytest.fixture()
def live_client(monkeypatch):
    monkeypatch.setenv(
        "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS),
    )
    monkeypatch.setenv(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS),
    )
    # Pre-set a READY state so /health/ready returns 200 quickly. The
    # cooperative dependency system keeps the existing convention for
    # local/test fixtures.
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        yield client
    reset_readiness_state()


def test_health_live_returns_200_immediately(live_client):
    resp = live_client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "live"


def test_health_ready_returns_200_when_ready(live_client):
    resp = live_client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"


def test_health_ready_returns_503_when_draining():
    from cold_storage.bootstrap.runtime_readiness import ReadinessState, set_readiness_state

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="DRAINING"))
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "draining"
        # No raw exception text, no DSN, no secret.
        body_str = json.dumps(body).lower()
        assert "password" not in body_str
        assert "secret" not in body_str
        assert "dsn" not in body_str
        assert "exception" not in body_str
    reset_readiness_state()


def test_health_live_does_not_touch_database(monkeypatch, live_client):
    """Liveness MUST NOT probe the database or any dependency.

    We monitor ``get_engine`` calls by monkeypatching the engine
    accessor and asserting it is never invoked from ``/health/live``.
    """
    from cold_storage.bootstrap import dependencies as deps

    called = {"count": 0}
    original_get_engine = deps.get_engine

    def _spy_get_engine():
        called["count"] += 1
        return original_get_engine()

    monkeypatch.setattr(deps, "get_engine", _spy_get_engine)

    live_client.get("/health/live")
    live_client.get("/health/live")
    # Liveness must not query the engine at all (no DB).
    assert called["count"] == 0
