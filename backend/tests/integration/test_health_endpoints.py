"""Integration tests for /health/live and /health/ready per Slice 2."""

from __future__ import annotations

import json
from pathlib import Path

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
def sqlite_env(monkeypatch, tmp_path: Path) -> None:
    """Configure the test environment to a stable TEST-mode SQLite path.

    The existing settings layer refuses to load when
    ``COLD_STORAGE_ENVIRONMENT_ID=test`` and the default
    ``./cold_storage_dev.db`` is used, so any test that exercises
    the FastAPI lifespan (and therefore ``Settings()``) must
    pre-populate ``COLD_STORAGE_SQLITE_PATH`` with a non-default
    value pointing at a pytest-managed ``tmp_path``. The probe
    timeouts are aligned to the documented ``LOCAL_TEST_*`` values
    so the readiness authority's per-probe budget matches what the
    rest of the test suite assumes.
    """
    sqlite_path = tmp_path / "test_health_endpoints.db"
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("COLD_STORAGE_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv(
        "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS),
    )
    monkeypatch.setenv(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS),
    )


@pytest.fixture()
def live_client(monkeypatch, sqlite_env):
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


def test_health_ready_returns_503_when_draining(sqlite_env):
    from cold_storage.bootstrap.runtime_readiness import ReadinessState, set_readiness_state

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        # Flip to DRAINING AFTER lifespan so the /health/ready endpoint
        # exercises the contract's "DRAINING -> 503" branch without
        # colliding with the mandatory 8-probe startup phase.
        set_readiness_state(ReadinessState(state="DRAINING"))
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

    def _spy_get_engine() -> object:
        called["count"] += 1
        return original_get_engine()

    monkeypatch.setattr(deps, "get_engine", _spy_get_engine)

    live_client.get("/health/live")
    live_client.get("/health/live")
    # Liveness must not query the engine at all (no DB).
    assert called["count"] == 0
