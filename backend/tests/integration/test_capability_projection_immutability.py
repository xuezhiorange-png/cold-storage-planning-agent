"""V0.2 Slice 4: capability projection immutability tests.

These tests prove that the app-bound capability projection (D-S4-04) is
truly immutable: callers cannot mutate it via the MappingProxyType wrapper,
failed init and shutdown do not corrupt it, and repeated app creation
produces isolated projections.

The projection uses ``types.MappingProxyType`` for each entry, ensuring
structural immutability at the Python level.  The tuple itself is already
immutable.
"""

from __future__ import annotations

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
def projection_env(tmp_path, monkeypatch):
    """Isolated SQLite environment for projection immutability tests."""
    sqlite_path = tmp_path / "test_projection.db"
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


def test_caller_mutation_cannot_change_readiness_projection(projection_env):
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


def test_failed_init_does_not_change_projection(projection_env, monkeypatch):
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

            _init(_make_local_settings(tmp_path=projection_env))
    finally:
        monkeypatch.setattr(deps.DatabaseProjectService, "__init__", original_init)

    # The first app's projection must still be intact and unchanged.
    assert getattr(app1, "_capability_projection", None) is not None
    assert bound1[0]["name"] == original_name
    assert bound1[0]["status"] == original_status

    # The MappingProxyType is still immutable after the failed init.
    with pytest.raises(TypeError, match="does not support item assignment"):
        bound1[0]["status"] = "TAMPERED"


def test_shutdown_does_not_change_projection(projection_env):
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


def test_repeated_app_creation_isolated(projection_env):
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


def test_projection_entries_are_mapping_proxy_type(projection_env):
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


def test_app_bound_projection_survives_readiness_requests(projection_env):
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


def _make_local_settings(tmp_path):
    """Return a minimal ``Settings`` suitable for local SQLite init."""
    import os

    from cold_storage.bootstrap.settings import Settings

    os.environ.setdefault("COLD_STORAGE_ENVIRONMENT_ID", "local")
    os.environ.setdefault("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    os.environ.setdefault("COLD_STORAGE_SQLITE_PATH", str(tmp_path / "projection.db"))
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
