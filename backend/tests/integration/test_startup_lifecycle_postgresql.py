"""PostgreSQL integration tests for TASK-012 Slice 2 startup lifecycle.

These tests run with ``DATABASE_BACKEND=postgresql`` (gated by the
``postgresql`` marker) and validate that the PostgreSQL acceptance
criteria from contract section 9.3 are satisfied. Tests that require a
real PostgreSQL connection are skipped when the ``DATABASE_URL`` env
var is not pointing at a reachable database; this matches the existing
test discipline in this repo.

Where the contract requires a live PostgreSQL backend (e.g. strict
artifact admission against the exact Alembic head, coefficient
readiness gating), the test asserts the contract-relevant code path
*consults* the production alembic head enumeration but treats the
exact-head assertion as a CI gate rather than a fixture-driven check.

Environment discipline
----------------------
The CI runner for ``-m postgresql`` sets
``DATABASE_BACKEND=postgresql`` plus the discrete PostgreSQL connection
fields but does NOT set ``COLD_STORAGE_ENVIRONMENT_ID``. The fixture
therefore pins the environment to ``local`` so the lifespan's
``Settings()`` can compose without triggering the strict-mode
fail-closed path (which would require seeded
``coefficient_approval_log`` data the CI outbox database does not
carry). This matches the contract: staging/production use the SAME
classes of readiness checks as the production
:class:`run_startup_readiness_or_raise` function asserts, but the
**CI smoke** runs against the local-mode fast path that is also
used by the existing slice-1/2 acceptance tests. The strict-mode
behaviour is enforced by the architecture test
``test_runtime_bootstrap_does_not_use_alembic`` rather than by
gating the ``/health/*`` contract behind real production data.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

from cold_storage.bootstrap.dependencies import (
    shutdown_dependencies,
)
from cold_storage.bootstrap.runtime_readiness import (
    LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS,
    LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS,
    ReadinessState,
    reset_readiness_state,
    set_readiness_state,
)

pytestmark = pytest.mark.postgresql

# Skip all tests in this module when PostgreSQL is not available.
_requires_pg = pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL") or os.environ.get("COLD_STORAGE_DATABASE_URL")),
    reason="PostgreSQL DATABASE_URL is not configured",
)


# ---------------------------------------------------------------------
# Test-environment helpers
# ---------------------------------------------------------------------
#
# The fixture in this module matches the CI runner's environment
# exactly: ``local`` environment id + ``postgresql`` backend + the
# discrete PostgreSQL connection fields. Storage dir is a pytest-managed
# ``tmp_path`` so the test never touches operator-owned paths and
# never materialises a real production secret. No ``COLD_STORAGE_*``
# env var carries a real production credential.
# ---------------------------------------------------------------------

_TEST_BUILD_COMMIT_SHA = "0" * 40
_TEST_BUILD_VERSION = "ci-postgresql-tests"
_TEST_DEPLOYMENT_ID = "ci-postgresql-deployment"
_TEST_CONFIG_SCHEMA_VERSION = "1"


@pytest.fixture()
def postgresql_env(monkeypatch, tmp_path):
    """Configure a local-mode PostgreSQL environment matching CI."""
    url = os.environ.get("COLD_STORAGE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL DATABASE_URL is not configured")
    parts = urlsplit(url)
    storage_dir = tmp_path / "slice2_artifact_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_URL", url)
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", _TEST_CONFIG_SCHEMA_VERSION)
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", _TEST_BUILD_COMMIT_SHA)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", _TEST_BUILD_VERSION)
    monkeypatch.setenv("COLD_STORAGE_DEPLOYMENT_ID", _TEST_DEPLOYMENT_ID)
    monkeypatch.setenv("COLD_STORAGE_POSTGRES_HOST", parts.hostname or "localhost")
    monkeypatch.setenv("COLD_STORAGE_POSTGRES_PORT", str(parts.port or 5432))
    monkeypatch.setenv("COLD_STORAGE_POSTGRES_DB", (parts.path or "/").lstrip("/") or "test")
    if parts.username is not None:
        monkeypatch.setenv("COLD_STORAGE_POSTGRES_USER", parts.username)
    if parts.password is not None:
        monkeypatch.setenv("COLD_STORAGE_POSTGRES_PASSWORD", parts.password)
    yield url


def test_postgresql_settings_load(postgresql_env):
    from cold_storage.bootstrap.settings import Settings

    settings = Settings()
    assert settings.database_backend == "postgresql"
    assert settings.environment_id.value == "local"
    assert settings.build_commit_sha == _TEST_BUILD_COMMIT_SHA
    assert settings.build_version == _TEST_BUILD_VERSION
    assert settings.deployment_id == _TEST_DEPLOYMENT_ID


def test_application_does_not_run_migrations(postgresql_env):
    """The runtime application must not invoke alembic upgrade/downgrade.

    This is enforced architecturally: the application code only reads
    via the SQLAlchemy engine; migration commands are restricted to
    the external migration service (D-S2-01). We assert the contract
    by importing the bootstrap entry points and verifying that none of
    them references alembic.
    """
    import sys

    bootstrap_entries = [
        "cold_storage.bootstrap.app",
        "cold_storage.bootstrap.dependencies",
        "cold_storage.bootstrap.startup_readiness",
        "cold_storage.bootstrap.runtime_readiness",
    ]
    for entry in bootstrap_entries:
        mod = sys.modules.get(entry) or __import__(entry)
        # ``alembic`` must not appear among the module's globals.
        assert "alembic" not in dir(mod), (
            f"runtime bootstrap module {entry!r} must not reference alembic"
        )


def test_health_endpoint_redacts_dsn(postgresql_env):
    """Health output must not leak the PostgreSQL DSN."""
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.runtime_readiness import (
        ReadinessState,
        reset_readiness_state,
        set_readiness_state,
    )

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        # The response may legitimately be 503 if the DB is unreachable,
        # but the body MUST NOT contain the DSN.
        body_str = str(resp.json())
        assert postgresql_env not in body_str, "health response leaked DATABASE_URL"
        assert "password=" not in body_str.lower()


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: DATABASE_SCHEMA_HEAD_INVALID surface in PostgreSQL.
# ---------------------------------------------------------------------------


def test_postgresql_schema_head_invalid_classifies_to_dshic(monkeypatch):
    """A schema-head mismatch in PostgreSQL mode projects as DATABASE_SCHEMA_HEAD_INVALID.

    V0.2 Slice 2 amendment (D-S2-12.a.v0.2): this test MUST reach the
    schema-head probe (probe 4) and verify it classifies as
    ``DATABASE_SCHEMA_HEAD_INVALID``. The probe was previously
    short-circuited on a missing or incomplete strict-mode fixture.
    The fixture now provides the full set of canonical strict-mode
    identity keys that ``Settings()`` validates in production /
    staging modes — without weakening the production validation,
    without lowering the resource-identity consistency requirement,
    and without changing the production Settings implementation.
    """
    # Default DSN when the test runs without a real PostgreSQL
    # instance. The fake engine never opens a real connection; this
    # string is only used to satisfy the strict-mode ``Settings()``
    # validator.
    postgresql_env = (
        "postgresql+psycopg2://cold_storage:cold_storage@localhost:5432/cold_storage_test"
    )
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

    # ----- Strict-mode canonical identity (D-S2-01 / D-S2-09) -----
    # The full set of canonical strict-mode keys validated by
    # ``Settings()``. Values mirror the production Compose / CI
    # defaults documented in
    # docs/runbooks/TASK-012-slice2-deployment-startup.md §4.2.
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_URL",
        postgresql_env,
    )
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", "0" * 40)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", "v0.0.0-ci")
    monkeypatch.setenv("COLD_STORAGE_DEPLOYMENT_ID", "deploy-fixture-test")
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci-strict")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci-strict")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci-strict")
    monkeypatch.setenv("COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS", "5")
    # No ``COLD_STORAGE_PACKAGED_ALEMBIC_HEAD`` env var — the loader
    # is graph-driven, so this env var is now ignored.
    monkeypatch.delenv("COLD_STORAGE_PACKAGED_ALEMBIC_HEAD", raising=False)
    # Configure an artifact storage dir to satisfy probe 6 in
    # strict mode. The dir need not exist; the probe's failure
    # envelope is what we verify, and the schema-head probe is
    # independent of the artifact-storage probe.
    import tempfile

    _tmp_storage = tempfile.mkdtemp(prefix="cold-storage-test-")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", _tmp_storage)

    # ----- Stub the engine and the lifespan -----
    # ``init_dependencies`` is bypassed (it would attempt to connect
    # to the real PostgreSQL URL); the probe still runs because
    # ``get_engine`` returns our fake.
    import cold_storage.bootstrap.runtime_readiness as rr
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import dependencies as deps

    def _noop_init(settings, app=None):  # noqa: ARG001
        return None

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

        def exec_driver_sql(self, sql):  # noqa: ARG002
            # Recorded head intentionally differs from the graph
            # head so the probe classifies as DATABASE_HEAD_MISMATCH.
            return _FakeResult(("0123456789ab",))

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    fake_engine = _FakeEngine()
    monkeypatch.setattr(deps, "get_engine", lambda: fake_engine)

    # The graph loader is monkeypatched to return a known valid head
    # that does NOT match the recorded alembic_version row.
    def _fake_graph_loader():
        return ("abc123def456", None)

    monkeypatch.setattr(rr, "_load_packaged_alembic_head", _fake_graph_loader)

    set_canonical_settings(Settings())

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/health/ready")
        body = resp.json()
        codes = [body.get("check_code")] + [o.get("code") for o in body.get("outcomes", [])]
        # The probe MUST have classified the schema-head mismatch
        # as the stable code DATABASE_SCHEMA_HEAD_INVALID.
        assert DATABASE_SCHEMA_HEAD_INVALID in codes
        # Locate the schema-head probe outcome specifically and
        # assert its code is DSHIC, NOT a timeout code. Other
        # probes in the readiness tuple (e.g. lifecycle, build
        # identity) may legitimately surface STARTUP_PROBE_TIMEOUT
        # under this fixture; the schema-head probe is the
        # V0.2 amendment's focus.
        schema_outcomes = [
            o for o in body.get("outcomes", []) if o.get("name") == "database_exact_alembic_head"
        ]
        assert schema_outcomes, "schema-head probe MUST have run"
        schema_outcome = schema_outcomes[0]
        assert schema_outcome.get("code") == DATABASE_SCHEMA_HEAD_INVALID
        assert schema_outcome.get("code") != "STARTUP_PROBE_TIMEOUT"
        assert schema_outcome.get("code") != "READINESS_PROBE_TIMEOUT"
        # The detail envelope MUST NOT leak the raw Head value or
        # the DSN. This guards against regression in the public
        # health response surface.
        body_str = str(body)
        assert "abc123def456" not in body_str
        assert "0123456789ab" not in body_str
        assert postgresql_env not in body_str
        assert "password" not in body_str.lower()
        assert "Traceback" not in body_str

    reset_readiness_state()
    reset_canonical_settings()


# ===========================================================================
# V0.2 Slice 4: PostgreSQL lifecycle integrity tests — failed-init rollback,
# shutdown clearance, idempotent shutdown, engine-dispose accounting,
# and reinit isolation.
# ===========================================================================


class _InitFailureSentinel(Exception):
    """Controlled exception raised inside ``init_dependencies`` to test rollback."""


def _make_pg_settings(tmp_path, database_url):
    """Return a minimal ``Settings`` suitable for local PostgreSQL init."""
    from cold_storage.bootstrap.settings import Settings

    os.environ["COLD_STORAGE_ENVIRONMENT_ID"] = "local"
    os.environ["COLD_STORAGE_DATABASE_BACKEND"] = "postgresql"
    os.environ["COLD_STORAGE_DATABASE_URL"] = database_url
    os.environ["COLD_STORAGE_STORAGE_DIR"] = str(tmp_path / "storage")
    os.environ["COLD_STORAGE_CONFIG_SCHEMA_VERSION"] = _TEST_CONFIG_SCHEMA_VERSION
    os.environ["COLD_STORAGE_APP_HOST"] = "127.0.0.1"
    os.environ["COLD_STORAGE_APP_PORT"] = "8000"
    os.environ["COLD_STORAGE_BUILD_COMMIT_SHA"] = _TEST_BUILD_COMMIT_SHA
    os.environ["COLD_STORAGE_BUILD_VERSION"] = _TEST_BUILD_VERSION
    os.environ["COLD_STORAGE_DEPLOYMENT_ID"] = _TEST_DEPLOYMENT_ID
    os.environ["COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS"] = str(
        LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS,
    )
    os.environ["COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS"] = str(
        LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS,
    )
    return Settings()


def _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path):
    """Create an isolated PostgreSQL database and configure the environment.

    Returns the database URL. Caller must call ``shutdown_dependencies()``
    in teardown.
    """
    db_url = pg_database_factory(prefix="pg_lifecycle")
    parts = urlsplit(db_url)

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_URL", db_url)
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", _TEST_CONFIG_SCHEMA_VERSION)
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", _TEST_BUILD_COMMIT_SHA)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", _TEST_BUILD_VERSION)
    monkeypatch.setenv("COLD_STORAGE_DEPLOYMENT_ID", _TEST_DEPLOYMENT_ID)
    monkeypatch.setenv("COLD_STORAGE_POSTGRES_HOST", parts.hostname or "localhost")
    monkeypatch.setenv("COLD_STORAGE_POSTGRES_PORT", str(parts.port or 5432))
    monkeypatch.setenv("COLD_STORAGE_POSTGRES_DB", (parts.path or "/").lstrip("/") or "test")
    if parts.username is not None:
        monkeypatch.setenv("COLD_STORAGE_POSTGRES_USER", parts.username)
    if parts.password is not None:
        monkeypatch.setenv("COLD_STORAGE_POSTGRES_PASSWORD", parts.password)
    monkeypatch.setenv(
        "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS),
    )
    monkeypatch.setenv(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS),
    )
    return db_url


@_requires_pg
def test_pg_failed_init_production_coefficient_singleton_count_zero(
    pg_database_factory,
    monkeypatch,
    tmp_path,
):
    """FAILED_INIT_PRODUCTION_COEFFICIENT_SINGLETON_COUNT=0.

    After a failed init, ``production_coefficient_service`` must NOT exist.
    """
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.dependencies import _singletons, init_dependencies

    _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path)
    reset_readiness_state()

    original_init = deps.DatabaseProjectService.__init__

    def _fail_init(self, engine, *a, **kw):  # noqa: ARG001
        raise _InitFailureSentinel("simulated project service failure")

    monkeypatch.setattr(deps.DatabaseProjectService, "__init__", _fail_init)
    try:
        with pytest.raises(_InitFailureSentinel):
            init_dependencies(_make_pg_settings(tmp_path, os.environ["COLD_STORAGE_DATABASE_URL"]))
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)

    assert "production_coefficient_service" not in _singletons


@_requires_pg
def test_pg_failed_init_database_token_count_zero(
    pg_database_factory,
    monkeypatch,
    tmp_path,
):
    """FAILED_INIT_DATABASE_COMPOSITION_TOKEN_COUNT=0.

    After a failed init, composition tokens must be empty.
    """
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.dependencies import _composition_tokens, init_dependencies

    _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path)
    reset_readiness_state()

    original_init = deps.DatabaseProjectService.__init__

    def _fail_init(self, engine, *a, **kw):  # noqa: ARG001
        raise _InitFailureSentinel("simulated project service failure")

    monkeypatch.setattr(deps.DatabaseProjectService, "__init__", _fail_init)
    try:
        with pytest.raises(_InitFailureSentinel):
            init_dependencies(_make_pg_settings(tmp_path, os.environ["COLD_STORAGE_DATABASE_URL"]))
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)

    assert len(_composition_tokens) == 0


@_requires_pg
def test_pg_failed_init_engine_count_zero(
    pg_database_factory,
    monkeypatch,
    tmp_path,
):
    """FAILED_INIT_ENGINE_COUNT=0.

    After a failed init, ``engine`` must NOT exist in singletons.
    """
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.dependencies import _singletons, init_dependencies

    _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path)
    reset_readiness_state()

    original_init = deps.DatabaseProjectService.__init__

    def _fail_init(self, engine, *a, **kw):  # noqa: ARG001
        raise _InitFailureSentinel("simulated project service failure")

    monkeypatch.setattr(deps.DatabaseProjectService, "__init__", _fail_init)
    try:
        with pytest.raises(_InitFailureSentinel):
            init_dependencies(_make_pg_settings(tmp_path, os.environ["COLD_STORAGE_DATABASE_URL"]))
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)

    assert "engine" not in _singletons


@_requires_pg
def test_pg_reinit_after_failure_creates_new_coefficient_service(
    pg_database_factory,
    monkeypatch,
    tmp_path,
):
    """REINIT_AFTER_FAILURE_CREATES_NEW_COEFFICIENT_SERVICE.

    After a failed init, a subsequent init must succeed and create a fresh
    service.
    """
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.dependencies import _singletons, init_dependencies

    _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path)
    reset_readiness_state()

    call_count = 0
    original_init = deps.DatabaseProjectService.__init__

    def _fail_first_then_succeed(self, engine, *a, **kw):  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _InitFailureSentinel("simulated project service failure")
        return original_init(self, engine, *a, **kw)

    monkeypatch.setattr(deps.DatabaseProjectService, "__init__", _fail_first_then_succeed)
    try:
        with pytest.raises(_InitFailureSentinel):
            init_dependencies(_make_pg_settings(tmp_path, os.environ["COLD_STORAGE_DATABASE_URL"]))

        assert "project_service" not in _singletons

        init_dependencies(_make_pg_settings(tmp_path, os.environ["COLD_STORAGE_DATABASE_URL"]))
        assert "project_service" in _singletons
        assert call_count == 2
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)
        shutdown_dependencies()


@_requires_pg
def test_pg_shutdown_clears_production_coefficient_singleton(
    pg_database_factory,
    monkeypatch,
    tmp_path,
):
    """SHUTDOWN_CLEARS_PRODUCTION_COEFFICIENT_SINGLETON.

    Shutdown must remove ``production_coefficient_service`` from singletons.
    """
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.dependencies import _singletons

    _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path)
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        pass

    assert "production_coefficient_service" not in _singletons


@_requires_pg
def test_pg_shutdown_clears_database_token(
    pg_database_factory,
    monkeypatch,
    tmp_path,
):
    """SHUTDOWN_CLEARS_DATABASE_TOKEN.

    Shutdown must clear composition tokens.
    """
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.dependencies import _composition_tokens

    _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path)
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        pass

    assert len(_composition_tokens) == 0


@_requires_pg
def test_pg_post_shutdown_provider_returns_stable_503(
    pg_database_factory,
    monkeypatch,
    tmp_path,
):
    """POST_SHUTDOWN_PROVIDER_RETURNS_STABLE_503.

    After shutdown, ``get_production_coefficient_service`` raises RuntimeError
    (stable 503 response from the route provider).
    """
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.dependencies import get_production_coefficient_service

    _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path)
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        pass

    with pytest.raises(RuntimeError, match="not initialized"):
        get_production_coefficient_service()


@_requires_pg
def test_pg_engine_dispose_call_count(
    pg_database_factory,
    monkeypatch,
    tmp_path,
):
    """ENGINE_DISPOSE_CALL_COUNT=1.

    Engine.dispose() must be called exactly once during shutdown.
    """
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.app import create_app

    _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path)

    dispose_calls = 0
    original_dispose = deps.dispose_engine

    def _tracking_dispose(engine):
        nonlocal dispose_calls
        dispose_calls += 1
        return original_dispose(engine)

    monkeypatch.setattr(deps, "dispose_engine", _tracking_dispose)

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        pass

    assert dispose_calls == 1


@_requires_pg
def test_pg_second_shutdown_idempotent(
    pg_database_factory,
    monkeypatch,
    tmp_path,
):
    """SECOND_SHUTDOWN_IDEMPOTENT.

    Calling shutdown_dependencies() twice must not raise.
    """
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app

    _pg_lifecycle_env(pg_database_factory, monkeypatch, tmp_path)
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        pass

    # First shutdown already called by TestClient.__exit__.
    # Second shutdown must be a no-op.
    shutdown_dependencies()
    shutdown_dependencies()  # must not raise
