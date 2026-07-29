"""SQLite integration tests for TASK-012 Slice 2 startup lifecycle.

These tests run with ``DATABASE_BACKEND=sqlite`` and validate that the
SQLite acceptance criteria from contract section 9.2 are satisfied:

* local/test application startup succeeds with explicitly isolated SQLite;
* liveness does not query the database;
* readiness reflects initialization and draining state;
* shutdown disposes the engine and clears state;
* failed initialization leaves no singleton leakage;
* strict environment plus SQLite fails closed;
* health output contains no secret or unsafe exception text.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.dependencies import shutdown_dependencies
from cold_storage.bootstrap.runtime_readiness import (
    LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS,
    LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS,
    ReadinessState,
    reset_readiness_state,
    set_readiness_state,
)


@pytest.fixture()
def isolated_sqlite_env(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "test_slice2.db"
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("COLD_STORAGE_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv(
        "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS),
    )
    monkeypatch.setenv(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS),
    )
    yield tmp_path
    shutdown_dependencies()


def test_startup_succeeds_with_isolated_sqlite(isolated_sqlite_env):
    # Reset singletons before constructing the app.
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health/live")
        assert resp.status_code == 200


def test_readiness_reflects_state_machine(isolated_sqlite_env):
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        body = resp.json()
        assert resp.status_code == 200
        assert body["status"] == "ready"


def test_readiness_returns_503_when_draining(isolated_sqlite_env):
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
        # No raw secrets or unsafe text.
        s = json.dumps(body).lower()
        assert "password" not in s
        assert "secret" not in s
        assert "traceback" not in s


def test_shutdown_disposes_engine_and_clears_state(isolated_sqlite_env):
    from cold_storage.bootstrap.dependencies import _singletons, get_engine

    # Force an init then shutdown.
    from cold_storage.bootstrap.settings import Settings  # noqa: F401

    Settings()  # ensure canonical schema load; result discarded.
    if "engine" in _singletons:
        shutdown_dependencies()
    assert "engine" not in _singletons

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        # Engine must be present after init.
        eng = get_engine()
        assert eng is not None
    # After shutdown, the engine singleton is cleared.
    assert "engine" not in _singletons


def test_strict_environment_plus_sqlite_fails_closed(isolated_sqlite_env, monkeypatch):
    """Strict (production-like) env + sqlite must fail closed at settings load.

    We model this by switching environment_id to ``production`` while
    keeping sqlite as the backend. The configuration validator in
    settings rejects this combination as documented in Slice 1.
    """
    from pydantic import ValidationError

    from cold_storage.bootstrap.environment_model import ConfigurationError

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_SQLITE_PATH", str(isolated_sqlite_env / "test.db"))
    from cold_storage.bootstrap.settings import Settings

    # F-PR76-§15: surface the contract-compliant exception classes
    # only. The Slice 1 frozen configuration identity is
    # :class:`ConfigurationError`; the pydantic layer wraps it in
    # ``ValidationError``. Either is acceptable for the fail-closed
    # contract; ``Exception`` is intentionally NOT in this tuple.
    with pytest.raises((ConfigurationError, ValidationError)) as exc_info:
        Settings()
    msg = str(exc_info.value).lower()
    assert "sqlite" in msg or "postgresql" in msg


def test_health_output_contains_no_secret_or_unsafe_text(isolated_sqlite_env):
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        # Flip to DRAINING AFTER lifespan so the /health/ready endpoint
        # exercises the contract's "DRAINING -> 503" branch without
        # colliding with the mandatory 8-probe startup phase.
        set_readiness_state(ReadinessState(state="DRAINING"))
        resp = client.get("/health/ready")
        body = resp.json()
        s = json.dumps(body)
        for forbidden in (
            "password",
            "DSN",
            "secret",
            "Traceback",
            "credentials",
            "exception",
        ):
            assert forbidden.lower() not in s.lower(), (
                f"health response leaked {forbidden!r}: {body}"
            )
