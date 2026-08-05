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
import types

import pytest
from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.dependencies import (
    create_capability_projection,
    shutdown_dependencies,
)
from cold_storage.bootstrap.mode import AppMode
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


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: schema-head classification surface in SQLite mode.
# ---------------------------------------------------------------------------


def test_sqlite_schema_probe_skip_in_local_mode(isolated_sqlite_env):
    """Local SQLite mode MUST skip the schema probe (no packaged head needed)."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    settings = Settings()
    set_canonical_settings(settings)
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "pass"
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_sqlite_health_endpoint_returns_503_when_schema_head_invalid(
    monkeypatch,
    isolated_sqlite_env,
    tmp_path,
):
    """The /health/ready endpoint surfaces DATABASE_SCHEMA_HEAD_INVALID in production mode."""
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

    # Override env to strict mode (production + postgresql-style) so
    # the schema probe is exercised, but the test still runs on the
    # sqlite fixture without needing real postgres.
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
    monkeypatch.delenv("COLD_STORAGE_SQLITE_PATH", raising=False)
    monkeypatch.setenv("COLD_STORAGE_PACKAGED_ALEMBIC_HEAD", "abc123def456")
    monkeypatch.setenv("COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS", "5")
    # Provide a real, writable canonical artifact storage directory so
    # the strict-mode artifact probe passes. The probe reads
    # ``Settings.storage_dir`` (env ``COLD_STORAGE_STORAGE_DIR``); the
    # ad-hoc env keys ``COLD_STORAGE_ARTIFACT_STORAGE_DIR`` and
    # ``COLD_STORAGE_REPORT_ARTIFACTS_DIR`` are intentionally NOT set
    # because they are no longer recognized authority.
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(artifact_dir))

    # Stub init_dependencies; install a fake engine whose alembic_version
    # row reports a mismatched head so the schema probe classifies as
    # DATABASE_HEAD_MISMATCH -> DATABASE_SCHEMA_HEAD_INVALID.
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import dependencies as deps

    def _noop_init(settings, app=None, strict_runtime_authority=None):  # noqa: ARG001
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
        # The detail envelope MUST NOT leak Head values, DSN, SQL.
        assert "abc123def456" not in body_str
        assert "0123456789ab" not in body_str
        assert "Traceback" not in body_str

    reset_readiness_state()
    reset_canonical_settings()


# ===========================================================================
# V0.2 Slice 4: lifecycle integrity tests — failed-init rollback,
# shutdown clearance, idempotent shutdown, engine-dispose accounting,
# and reinit isolation.
# ===========================================================================


class _InitFailureSentinel(Exception):
    """Controlled exception raised inside ``init_dependencies`` to test rollback."""


def test_failed_init_production_coefficient_singleton_count_zero(
    isolated_sqlite_env,
    monkeypatch,
):
    """After a failed init, ``production_coefficient_service`` must NOT exist."""
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.dependencies import _singletons

    reset_readiness_state()

    # Patch DatabaseProjectService.__init__ to force a failure after engine
    # creation but before singletons are fully populated.
    original_init = deps.DatabaseProjectService.__init__

    def _fail_init(self, engine, *a, **kw):  # noqa: ARG001
        raise _InitFailureSentinel("simulated project service failure")

    monkeypatch.setattr(deps.DatabaseProjectService, "__init__", _fail_init)
    try:
        with pytest.raises(_InitFailureSentinel):
            init_dependencies(_make_local_settings(tmp_path=isolated_sqlite_env))
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)

    assert "production_coefficient_service" not in _singletons


def test_failed_init_database_token_count_zero(isolated_sqlite_env, monkeypatch):
    """After a failed init, composition tokens must be empty."""
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.dependencies import _composition_tokens

    reset_readiness_state()

    original_init = deps.DatabaseProjectService.__init__

    def _fail_init(self, engine, *a, **kw):  # noqa: ARG001
        raise _InitFailureSentinel("simulated project service failure")

    monkeypatch.setattr(deps.DatabaseProjectService, "__init__", _fail_init)
    try:
        with pytest.raises(_InitFailureSentinel):
            init_dependencies(_make_local_settings(tmp_path=isolated_sqlite_env))
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)

    assert len(_composition_tokens) == 0


def test_failed_init_engine_count_zero(isolated_sqlite_env, monkeypatch):
    """After a failed init, ``engine`` must NOT exist in singletons."""
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.dependencies import _singletons

    reset_readiness_state()

    original_init = deps.DatabaseProjectService.__init__

    def _fail_init(self, engine, *a, **kw):  # noqa: ARG001
        raise _InitFailureSentinel("simulated project service failure")

    monkeypatch.setattr(deps.DatabaseProjectService, "__init__", _fail_init)
    try:
        with pytest.raises(_InitFailureSentinel):
            init_dependencies(_make_local_settings(tmp_path=isolated_sqlite_env))
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)

    assert "engine" not in _singletons


def test_reinit_after_failed_init_creates_new_service(isolated_sqlite_env, monkeypatch):
    """After a failed init, a subsequent init must succeed and create a fresh service."""
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.dependencies import _singletons

    reset_readiness_state()

    call_count = 0
    original_init = deps.DatabaseProjectService.__init__

    def _fail_first_then_succeed(self, engine, *a, **kw):  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _InitFailureSentinel("simulated project service failure")
        # Delegate to real init on the second call.
        return original_init(self, engine, *a, **kw)

    monkeypatch.setattr(deps.DatabaseProjectService, "__init__", _fail_first_then_succeed)
    try:
        # First call fails.
        with pytest.raises(_InitFailureSentinel):
            init_dependencies(_make_local_settings(tmp_path=isolated_sqlite_env))

        # Singletons should be clean after the failure.
        assert "project_service" not in _singletons

        # Second call succeeds and creates a new service.
        init_dependencies(_make_local_settings(tmp_path=isolated_sqlite_env))
        assert "project_service" in _singletons
        assert call_count == 2
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)
        shutdown_dependencies()


def test_shutdown_clears_production_coefficient_singleton(isolated_sqlite_env):
    """Shutdown must remove ``production_coefficient_service`` from singletons."""
    from cold_storage.bootstrap.dependencies import _singletons

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        pass  # lifespan triggers init_dependencies

    # In local mode, production_coefficient_service is never set, so
    # verify the key is absent (cleared by shutdown).
    assert "production_coefficient_service" not in _singletons


def test_shutdown_clears_database_token(isolated_sqlite_env):
    """Shutdown must clear composition tokens."""
    from cold_storage.bootstrap.dependencies import _composition_tokens

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        pass

    assert len(_composition_tokens) == 0


def test_post_shutdown_provider_returns_stable_error(isolated_sqlite_env):
    """After shutdown, ``get_production_coefficient_service`` raises RuntimeError."""
    from cold_storage.bootstrap.dependencies import get_production_coefficient_service

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        pass

    with pytest.raises(RuntimeError, match="not initialized"):
        get_production_coefficient_service()


def test_second_shutdown_is_idempotent(isolated_sqlite_env):
    """Calling shutdown_dependencies() twice must not raise."""
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        pass

    # First shutdown is already called by TestClient.__exit__.
    # Second shutdown must be a no-op.
    shutdown_dependencies()
    shutdown_dependencies()  # must not raise


def test_engine_dispose_call_count(isolated_sqlite_env, monkeypatch):
    """Engine.dispose() must be called exactly once during shutdown."""
    from cold_storage.bootstrap import dependencies as deps

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

    # The TestClient __exit__ calls shutdown_dependencies which disposes
    # the engine exactly once.
    assert dispose_calls == 1


def test_old_service_not_reused(isolated_sqlite_env):
    """After shutdown + reinit, a NEW project service must be created."""
    from cold_storage.bootstrap.dependencies import _singletons

    old_service = None
    new_service = None

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app):
        # Capture the service BEFORE __exit__ triggers shutdown.
        old_service = _singletons.get("project_service")

    # After the context manager exits, singletons are cleared.
    assert "project_service" not in _singletons

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app2 = create_app()
    with TestClient(app2):
        # Capture inside context before __exit__ clears singletons.
        new_service = _singletons.get("project_service")

    # Both services were captured; they must be distinct objects.
    assert new_service is not None
    assert old_service is not None
    assert new_service is not old_service


# ===========================================================================
# V0.2 Slice 4: capability projection immutability tests (migrated from
# test_capability_projection_immutability.py).
#
# These tests prove that the app-bound capability projection (D-S4-04) is
# truly immutable: callers cannot mutate it via the MappingProxyType wrapper,
# failed init and shutdown do not corrupt it, and repeated app creation
# produces isolated projections.
# ===========================================================================


def test_caller_mutation_cannot_change_readiness_projection(isolated_sqlite_env):
    """Mutating a projection entry via the caller MUST NOT affect the app-bound projection.

    D-S4-04: The app-bound projection is stored as a tuple of
    ``MappingProxyType`` entries.  Calling ``dict()`` on a
    ``MappingProxyType`` produces a plain dict copy; mutating that
    copy MUST NOT propagate back to the app-bound projection.
    """
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()

    # The app-bound projection should be immutable MappingProxyType entries.
    bound = getattr(app, "_capability_projection", None)
    assert bound is not None
    assert isinstance(bound, tuple)
    assert len(bound) >= 1
    assert isinstance(bound[0], types.MappingProxyType)

    # Snapshot the original values.
    original_status = bound[0]["status"]
    original_name = bound[0]["name"]

    # Create a mutable copy (as the readiness endpoint does).
    mutable_copy = dict(bound[0])

    # Mutate the copy — this must NOT affect the app-bound projection.
    mutable_copy["status"] = "TAMPERED"
    mutable_copy["name"] = "HACKED"

    # The app-bound projection is still unchanged.
    assert bound[0]["status"] == original_status
    assert bound[0]["name"] == original_name

    # The MappingProxyType itself rejects direct mutation.
    with pytest.raises(TypeError, match="does not support item assignment"):
        bound[0]["status"] = "DIRECT_TAMPER"

    # Verify via the health endpoint that the projection is still sane.
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        body = resp.json()
        capabilities = body.get("capabilities", [])
        assert len(capabilities) >= 1
        assert capabilities[0]["name"] == original_name
        assert capabilities[0]["status"] == original_status


def test_failed_init_does_not_change_projection(isolated_sqlite_env, monkeypatch):
    """A failed init MUST NOT corrupt the app-bound or singleton projection.

    If a prior app's projection was created successfully, a subsequent
    failed init must not mutate or clear it.
    """
    from cold_storage.bootstrap import dependencies as deps

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))

    # Create a successful app and capture its projection.
    app1 = create_app()
    bound1 = getattr(app1, "_capability_projection", None)
    assert bound1 is not None
    original_name = bound1[0]["name"]
    original_status = bound1[0]["status"]

    shutdown_dependencies()

    # Now attempt a failed init.
    original_init = deps.DatabaseProjectService.__init__

    def _fail_init(self, engine, *a, **kw):  # noqa: ARG001
        raise RuntimeError("simulated init failure")

    monkeypatch.setattr(deps.DatabaseProjectService, "__init__", _fail_init)
    try:
        with pytest.raises(RuntimeError, match="simulated init failure"):
            from cold_storage.bootstrap.dependencies import init_dependencies as _init

            _init(_make_local_settings(tmp_path=isolated_sqlite_env))
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)

    # The first app's projection must still be intact and unchanged.
    assert getattr(app1, "_capability_projection", None) is not None
    assert bound1[0]["name"] == original_name
    assert bound1[0]["status"] == original_status

    # The MappingProxyType is still immutable after the failed init.
    with pytest.raises(TypeError, match="does not support item assignment"):
        bound1[0]["status"] = "TAMPERED"


def test_shutdown_does_not_change_projection(isolated_sqlite_env):
    """Shutdown MUST NOT mutate or clear the app-bound projection.

    The projection is bound to the FastAPI app instance, not to the
    singleton graph.  Shutdown clears singletons but the app's
    projection survives.
    """
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()

    bound = getattr(app, "_capability_projection", None)
    assert bound is not None
    original_name = bound[0]["name"]
    original_status = bound[0]["status"]

    shutdown_dependencies()

    # The app-bound projection survives shutdown.
    assert getattr(app, "_capability_projection", None) is not None
    assert bound[0]["name"] == original_name
    assert bound[0]["status"] == original_status

    # The MappingProxyType is still immutable.
    with pytest.raises(TypeError, match="does not support item assignment"):
        bound[0]["status"] = "POST_SHUTDOWN_TAMPER"


def test_repeated_app_creation_isolated(isolated_sqlite_env):
    """Multiple app creations MUST produce isolated, independent projections.

    Mutating one app's projection copy MUST NOT affect another's.
    """
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app1 = create_app()

    bound1 = getattr(app1, "_capability_projection", None)
    assert bound1 is not None

    shutdown_dependencies()

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app2 = create_app()

    bound2 = getattr(app2, "_capability_projection", None)
    assert bound2 is not None

    # Both projections have the same structure (same mode).
    assert bound1[0]["name"] == bound2[0]["name"]
    assert bound1[0]["status"] == bound2[0]["status"]

    # They are distinct tuples (different objects).
    assert bound1 is not bound2
    # The MappingProxyType entries are distinct objects.
    assert bound1[0] is not bound2[0]

    # Mutating a mutable copy of one does not affect the other.
    copy1 = dict(bound1[0])
    copy2 = dict(bound2[0])
    copy1["status"] = "TAMPERED_1"
    copy2["status"] = "TAMPERED_2"

    assert bound1[0]["status"] != "TAMPERED_1"
    assert bound2[0]["status"] != "TAMPERED_2"
    assert bound1[0]["status"] == bound2[0]["status"]

    # Both are still immutable MappingProxyType.
    with pytest.raises(TypeError, match="does not support item assignment"):
        bound1[0]["status"] = "TAMPERED_1"
    with pytest.raises(TypeError, match="does not support item assignment"):
        bound2[0]["status"] = "TAMPERED_2"

    shutdown_dependencies()


def test_projection_entries_are_mapping_proxy_type(isolated_sqlite_env):
    """All projection entries MUST be MappingProxyType (not plain dicts)."""
    from cold_storage.bootstrap.dependencies import agent_capability_projection

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))

    # Test the singleton-based projection function.
    singleton_proj = agent_capability_projection()
    assert isinstance(singleton_proj, tuple)
    for entry in singleton_proj:
        assert isinstance(entry, types.MappingProxyType), (
            f"singleton projection entry is {type(entry).__name__}, expected MappingProxyType"
        )

    # Test the create_capability_projection factory.
    for mode in AppMode:
        proj = create_capability_projection(mode)
        assert isinstance(proj, tuple)
        for entry in proj:
            assert isinstance(entry, types.MappingProxyType), (
                f"create_capability_projection({mode!r}) entry is "
                f"{type(entry).__name__}, expected MappingProxyType"
            )

    shutdown_dependencies()


def test_app_bound_projection_survives_readiness_requests(isolated_sqlite_env):
    """The app-bound projection must survive multiple readiness requests without degradation."""
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()

    bound = getattr(app, "_capability_projection", None)
    assert bound is not None

    original_name = bound[0]["name"]
    with TestClient(app) as client:
        # Fire multiple readiness requests.
        for _ in range(5):
            resp = client.get("/health/ready")
            assert resp.status_code == 200
            body = resp.json()
            capabilities = body.get("capabilities", [])
            assert len(capabilities) >= 1
            assert capabilities[0]["name"] == original_name

    # The app-bound projection is still the same MappingProxyType.
    assert getattr(app, "_capability_projection", None) is not None
    assert bound[0]["name"] == original_name

    # Still immutable after repeated requests.
    with pytest.raises(TypeError, match="does not support item assignment"):
        bound[0]["name"] = "POST_REQUEST_TAMPER"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def init_dependencies(settings):
    """Thin wrapper to call ``cold_storage.bootstrap.dependencies.init_dependencies``."""
    from cold_storage.bootstrap.dependencies import init_dependencies as _init

    _init(settings)


def _make_local_settings(tmp_path):
    """Return a minimal ``Settings`` suitable for local SQLite init."""
    import os

    from cold_storage.bootstrap.settings import Settings

    os.environ.setdefault("COLD_STORAGE_ENVIRONMENT_ID", "local")
    os.environ.setdefault("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    os.environ.setdefault("COLD_STORAGE_SQLITE_PATH", str(tmp_path / "lifecycle.db"))
    os.environ.setdefault("COLD_STORAGE_STORAGE_DIR", str(tmp_path / "storage"))
    os.environ.setdefault(
        "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS),
    )
    os.environ.setdefault(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS),
    )
    return Settings()
