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


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: DATABASE_SCHEMA_HEAD_INVALID surfacing through
# the ``/health/ready`` endpoint (D-S2-12.a.v0.2).
# ---------------------------------------------------------------------------


def test_health_ready_projects_schema_head_invalid_when_mismatch(monkeypatch):
    """A schema-head mismatch surfaces as 503 with ``check_code=DATABASE_SCHEMA_HEAD_INVALID``."""
    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        ReadinessState,
        reset_canonical_settings,
        reset_readiness_state,
        set_canonical_settings,
        set_readiness_state,
    )
    from cold_storage.bootstrap.settings import Settings

    # Pin the canonical settings to strict (production) so the schema
    # probe is exercised.
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_URL",
        "postgresql+psycopg2://x:y@localhost:5432/test",
    )
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", "0" * 40)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", "v0.0.0-ci")
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_PACKAGED_ALEMBIC_HEAD", "abc123def456")
    monkeypatch.setenv("COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS", "5")

    # Stub out init_dependencies so the FastAPI lifespan doesn't
    # attempt to connect to a real PostgreSQL. The probe still runs
    # because ``get_engine`` returns our fake below.
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import dependencies as deps

    def _noop_init(settings, app=None):  # noqa: ARG001
        return None

    # The lifespan captures ``init_dependencies`` by direct reference
    # (top-level ``from ... import``), so the patch must target the
    # binding inside ``bootstrap.app`` AND the source module for
    # safety.
    monkeypatch.setattr(bootstrap_app, "init_dependencies", _noop_init)
    monkeypatch.setattr(deps, "init_dependencies", _noop_init)

    class _FakeResult:
        def __init__(self, v):
            self.v = v

        def first(self):
            return self.v

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec_driver_sql(self, sql):
            return _FakeResult(("0123456789ab",))

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    fake_engine = _FakeEngine()
    monkeypatch.setattr(deps, "get_engine", lambda: fake_engine)

    set_canonical_settings(Settings())

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["check_code"] == DATABASE_SCHEMA_HEAD_INVALID
        body_str = json.dumps(body)
        assert "abc123def456" not in body_str  # packaged head
        assert "0123456789ab" not in body_str  # recorded head
        assert "postgresql+psycopg2" not in body_str  # DSN
        assert "Traceback" not in body_str
        live = client.get("/health/live")
        assert live.status_code == 200

    reset_readiness_state()
    reset_canonical_settings()


def test_health_ready_projects_schema_head_invalid_when_packaged_missing(monkeypatch):
    """A missing packaged head MUST project as DATABASE_SCHEMA_HEAD_INVALID (not timeout)."""
    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        READINESS_PROBE_TIMEOUT,
        ReadinessState,
        reset_canonical_settings,
        reset_readiness_state,
        set_canonical_settings,
        set_readiness_state,
    )
    from cold_storage.bootstrap.settings import Settings

    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_URL",
        "postgresql+psycopg2://x:y@localhost:5432/test",
    )
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", "0" * 40)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", "v0.0.0-ci")
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci")
    monkeypatch.delenv("COLD_STORAGE_PACKAGED_ALEMBIC_HEAD", raising=False)
    monkeypatch.setenv("COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS", "5")

    # Stub init_dependencies to avoid touching a real PostgreSQL.
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import dependencies as deps

    def _noop_init(settings, app=None):  # noqa: ARG001
        return None

    monkeypatch.setattr(bootstrap_app, "init_dependencies", _noop_init)
    monkeypatch.setattr(deps, "init_dependencies", _noop_init)

    set_canonical_settings(Settings())

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        body = resp.json()
        assert resp.status_code == 503
        assert body["check_code"] == DATABASE_SCHEMA_HEAD_INVALID
        assert body["check_code"] != READINESS_PROBE_TIMEOUT

    reset_readiness_state()
    reset_canonical_settings()


def test_health_ready_still_emits_timeout_code_on_real_readiness_timeout(monkeypatch):
    """A real readiness probe timeout MUST still surface as READINESS_PROBE_TIMEOUT."""
    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.runtime_readiness import (
        READINESS_PROBE_TIMEOUT,
        ReadinessState,
        reset_canonical_settings,
        reset_readiness_state,
        set_canonical_settings,
        set_readiness_state,
    )
    from cold_storage.bootstrap.settings import Settings

    # Local mode so the schema probe is skipped; we only need to
    # provoke a timeout on a different probe via a short budget.
    monkeypatch.setenv("COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS", "1")

    # Stub init_dependencies to avoid touching a real PostgreSQL.
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import dependencies as deps

    def _noop_init(settings, app=None):  # noqa: ARG001
        return None

    monkeypatch.setattr(bootstrap_app, "init_dependencies", _noop_init)
    monkeypatch.setattr(deps, "init_dependencies", _noop_init)

    # Replace get_engine with a slow fake engine that triggers the
    # SIGALRM timeout on the database connectivity probe.
    import time as _t

    class _SlowConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def exec_driver_sql(self, sql):  # noqa: ARG002
            _t.sleep(3)
            return None

    class _SlowEng:
        def connect(self):
            return _SlowConn()

    monkeypatch.setattr(deps, "get_engine", lambda: _SlowEng())

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    set_canonical_settings(Settings())

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        body = resp.json()
        # A real timeout MUST surface as one of the timeout codes,
        # NEVER as DATABASE_SCHEMA_HEAD_INVALID. (Some pre-existing
        # probe-level ``_fail`` calls in the legacy probe bodies still
        # use STARTUP_PROBE_TIMEOUT as the wrapper-level fallback;
        # either is acceptable.)
        codes = [body.get("check_code")] + [o.get("code") for o in body.get("outcomes", [])]
        assert any(c in (READINESS_PROBE_TIMEOUT, "STARTUP_PROBE_TIMEOUT") for c in codes)
        assert "DATABASE_SCHEMA_HEAD_INVALID" not in codes

    reset_readiness_state()
    reset_canonical_settings()
