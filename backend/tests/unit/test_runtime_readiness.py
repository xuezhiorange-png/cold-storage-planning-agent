"""Unit tests for bootstrap.runtime_readiness per TASK-012 Slice 2."""

from __future__ import annotations

import os

import pytest

from cold_storage.bootstrap.runtime_readiness import (
    LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS,
    LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS,
    READINESS_PROBE_TIMEOUT_MAX,
    READINESS_PROBE_TIMEOUT_MIN,
    STARTUP_PROBE_TIMEOUT_MAX,
    STARTUP_PROBE_TIMEOUT_MIN,
    ProbeOutcome,
    ReadinessError,
    StartupProbeTimeout,
    assert_no_unsafe_strict_capabilities,
    registered_strict_capabilities,
    reset_readiness_state,
    run_probe_with_timeout,
    run_readiness_phase,
    run_startup_phase,
    validate_probe_timeout_seconds,
)


class _StubSettings:
    def __init__(self, env_id: str = "test") -> None:
        self._env_id = env_id

    @property
    def environment_id(self):  # noqa: D401, ANN001
        from cold_storage.bootstrap.environment_model import EnvironmentId

        return EnvironmentId(self._env_id)


# ---------------------------------------------------------------------------
# validate_probe_timeout_seconds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,lo,hi",
    [
        ("startup", STARTUP_PROBE_TIMEOUT_MIN, STARTUP_PROBE_TIMEOUT_MAX),
        ("readiness", READINESS_PROBE_TIMEOUT_MIN, READINESS_PROBE_TIMEOUT_MAX),
    ],
)
def test_validate_probe_timeout_seconds_accepts_boundaries(kind, lo, hi):
    assert validate_probe_timeout_seconds(value=lo, kind=kind) == lo
    assert validate_probe_timeout_seconds(value=hi, kind=kind) == hi


@pytest.mark.parametrize(
    "kind,lo,hi",
    [
        ("startup", STARTUP_PROBE_TIMEOUT_MIN, STARTUP_PROBE_TIMEOUT_MAX),
        ("readiness", READINESS_PROBE_TIMEOUT_MIN, READINESS_PROBE_TIMEOUT_MAX),
    ],
)
def test_validate_probe_timeout_seconds_rejects_out_of_range(kind, lo, hi):
    with pytest.raises(ReadinessError):
        validate_probe_timeout_seconds(value=lo - 1, kind=kind)
    with pytest.raises(ReadinessError):
        validate_probe_timeout_seconds(value=hi + 1, kind=kind)


@pytest.mark.parametrize(
    "value",
    [0, -1, "abc", "1.5", "nan", "inf", None, ""],
)
def test_validate_probe_timeout_seconds_rejects_illegal_shapes(value):
    with pytest.raises(ReadinessError):
        validate_probe_timeout_seconds(value=value, kind="startup")


def test_validate_probe_timeout_seconds_unknown_kind():
    with pytest.raises(ReadinessError):
        validate_probe_timeout_seconds(value=5, kind="bogus")


# ---------------------------------------------------------------------------
# run_probe_with_timeout
# ---------------------------------------------------------------------------


def _ok_probe(timeout_seconds: int) -> ProbeOutcome:
    return ProbeOutcome(name="ok", status="pass")


def _slow_probe(timeout_seconds: int) -> ProbeOutcome:
    return ProbeOutcome(name="slow", status="pass", duration_seconds=timeout_seconds + 1)


def _fail_probe(timeout_seconds: int) -> ProbeOutcome:
    return ProbeOutcome(name="fail", status="fail", code="FAIL_PROBE_CODE")


def test_run_probe_with_timeout_passing():
    out = run_probe_with_timeout(
        name="ok", fn=_ok_probe, timeout_seconds=5, on_timeout_code="TIMEOUT_CODE"
    )
    assert out.status == "pass"
    assert out.code is None


def test_run_probe_with_timeout_exceeding_budget_marks_failed():
    out = run_probe_with_timeout(
        name="slow",
        fn=_slow_probe,
        timeout_seconds=5,
        on_timeout_code="TIMEOUT_CODE",
    )
    assert out.status == "fail"
    assert out.code == "TIMEOUT_CODE"


def test_run_probe_with_timeout_appends_code_when_missing():
    out = run_probe_with_timeout(
        name="fail",
        fn=_fail_probe,
        timeout_seconds=5,
        on_timeout_code="ON_TIMEOUT",
    )
    assert out.status == "fail"
    # The probe declared ``FAIL_PROBE_CODE``, which we preserve rather
    # than overwrite.
    assert out.code == "FAIL_PROBE_CODE"


def test_run_probe_with_timeout_handles_exception():
    def _boom(timeout_seconds: int) -> ProbeOutcome:
        raise RuntimeError("kaboom")

    out = run_probe_with_timeout(
        name="boom", fn=_boom, timeout_seconds=5, on_timeout_code="TIMEOUT"
    )
    assert out.status == "fail"
    # When the probe raised, we treat the on_timeout_code as the stable
    # failure code so the caller can branch on a single code.
    assert out.code == "TIMEOUT"


# ---------------------------------------------------------------------------
# run_startup_phase + run_readiness_phase
# ---------------------------------------------------------------------------


def test_run_startup_phase_transitions_to_ready_when_all_pass(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.setenv(
        "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS),
    )
    reset_readiness_state()

    def _ok(timeout_seconds: int) -> ProbeOutcome:
        return ProbeOutcome(name="ok", status="pass")

    # Per brief §6 requirement 6: ``app=None`` is NOT a silent success.
    # Pass a real (clean) FastAPI app so the audit executes against
    # an empty reachable subset and the startup phase transitions to
    # READY as documented.
    clean_app = FastAPI()
    outcomes = run_startup_phase(
        settings=_StubSettings("test"),
        environment=dict(os.environ),
        startup_probes=[_ok, _ok],
        app=clean_app,
    )
    assert all(o.status == "pass" for o in outcomes)
    state = __import__(
        "cold_storage.bootstrap.runtime_readiness", fromlist=["*"]
    ).get_readiness_state()
    assert state is not None and state.is_ready()


def test_run_startup_phase_aborts_on_first_failure(monkeypatch):
    monkeypatch.setenv(
        "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS),
    )
    reset_readiness_state()

    def _ok(timeout_seconds: int) -> ProbeOutcome:
        return ProbeOutcome(name="ok", status="pass")

    def _bad(timeout_seconds: int) -> ProbeOutcome:
        return ProbeOutcome(name="bad", status="fail", code="SOMETHING")

    with pytest.raises(StartupProbeTimeout) as exc_info:
        run_startup_phase(
            settings=_StubSettings("test"),
            environment=dict(os.environ),
            startup_probes=[_ok, _bad],
        )
    assert exc_info.value.failure_code == "STARTUP_PROBE_TIMEOUT"


def test_run_readiness_phase_returns_all_outcomes(monkeypatch):
    monkeypatch.setenv(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS),
    )
    reset_readiness_state()

    def _ok(timeout_seconds: int) -> ProbeOutcome:
        return ProbeOutcome(name="ok", status="pass")

    outcomes = run_readiness_phase(settings=_StubSettings("test"), readiness_probes=[_ok, _ok])
    assert len(outcomes) == 2
    assert all(o.status == "pass" for o in outcomes)


# ---------------------------------------------------------------------------
# Strict-capability enumeration
# ---------------------------------------------------------------------------


def test_default_strict_capabilities_are_registered():
    caps = registered_strict_capabilities()
    assert "PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE" in caps
    assert "COEFFICIENT_HTTP_ROUTE_STRICT_MODE" in caps


def test_assert_no_unsafe_strict_capabilities_passes_when_none_reachable():
    from fastapi import FastAPI

    # Real (clean) FastAPI app: reachable subset is empty.
    assert_no_unsafe_strict_capabilities(app=FastAPI())


# ---------------------------------------------------------------------------
# Strict-capability enumeration — mode x app-presence matrix (D-S2-06.c,
# TASK-012 Slice 2 brief §5). The matrix is required to lock the new
# "mode resolution BEFORE app=None check" contract.
# ---------------------------------------------------------------------------


def _strict_settings(env_id: str):
    """Build a strict-environment Settings instance for unit tests.

    The Settings class reads ``COLD_STORAGE_ENVIRONMENT_ID``,
    ``COLD_STORAGE_APP_HOST`` and ``COLD_STORAGE_APP_PORT`` from the
    process environment (Pydantic v2 BaseSettings validation_alias).
    We therefore set the env vars explicitly before construction so
    the matrix stays hermetic and does not depend on the host's
    existing environment.

    Per the contract (D-S2-01 / D-S2-09) staging and production
    environments do NOT receive code-level defaults; explicit
    application binding (``APP_HOST`` + ``APP_PORT``) is mandatory.
    Test mode similarly requires an explicit SQLite path.
    """
    import os

    from cold_storage.bootstrap.settings import Settings

    prev = {
        "COLD_STORAGE_ENVIRONMENT_ID": os.environ.get("COLD_STORAGE_ENVIRONMENT_ID"),
        "COLD_STORAGE_APP_HOST": os.environ.get("COLD_STORAGE_APP_HOST"),
        "COLD_STORAGE_APP_PORT": os.environ.get("COLD_STORAGE_APP_PORT"),
        "COLD_STORAGE_SQLITE_PATH": os.environ.get("COLD_STORAGE_SQLITE_PATH"),
        "COLD_STORAGE_DATABASE_BACKEND": os.environ.get("COLD_STORAGE_DATABASE_BACKEND"),
        "COLD_STORAGE_DATABASE_URL": os.environ.get("COLD_STORAGE_DATABASE_URL"),
        "COLD_STORAGE_BUILD_COMMIT_SHA": os.environ.get("COLD_STORAGE_BUILD_COMMIT_SHA"),
        "COLD_STORAGE_BUILD_VERSION": os.environ.get("COLD_STORAGE_BUILD_VERSION"),
        "COLD_STORAGE_DATABASE_ENVIRONMENT_ID": os.environ.get(
            "COLD_STORAGE_DATABASE_ENVIRONMENT_ID"
        ),
        "COLD_STORAGE_SECRET_ENVIRONMENT_ID": os.environ.get("COLD_STORAGE_SECRET_ENVIRONMENT_ID"),
        "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID": os.environ.get(
            "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID"
        ),
    }
    os.environ["COLD_STORAGE_ENVIRONMENT_ID"] = env_id
    os.environ.setdefault("COLD_STORAGE_APP_HOST", "127.0.0.1")
    os.environ.setdefault("COLD_STORAGE_APP_PORT", "8000")
    if env_id == "test":
        os.environ["COLD_STORAGE_SQLITE_PATH"] = ":memory:"
    if env_id in ("staging", "production"):
        os.environ["COLD_STORAGE_DATABASE_BACKEND"] = "postgresql"
        os.environ["COLD_STORAGE_DATABASE_URL"] = (
            "postgresql+psycopg2://cold_storage:cold_storage@localhost:5432/cold_storage_test"
        )
        os.environ["COLD_STORAGE_BUILD_COMMIT_SHA"] = "0" * 40
        os.environ["COLD_STORAGE_BUILD_VERSION"] = "v0.0.0-ci"
        os.environ["COLD_STORAGE_CONFIG_SCHEMA_VERSION"] = "1"
        os.environ["COLD_STORAGE_DATABASE_ENVIRONMENT_ID"] = "ci-strict"
        os.environ["COLD_STORAGE_SECRET_ENVIRONMENT_ID"] = "ci-strict"
        os.environ["COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID"] = "ci-strict"
    try:
        return Settings()  # type: ignore[call-arg]
    finally:
        for key, prior in prev.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


def _strict_fastapi_app():
    """Build a clean FastAPI app for strict-mode audit tests."""
    from fastapi import FastAPI

    return FastAPI()


def _strict_fastapi_app_with_planning_agent_route():
    """Build a FastAPI app with the fake-agent HTTP route registered.

    The audit (D-S2-06.c) walks ``app.routes`` and looks for the
    canonical planning-agent path prefix ``/api/v1/agent/`` on each
    ``APIRoute`` instance. The route is registered directly on the
    FastAPI app (not via an included ``APIRouter``) so the audit's
    reachability check fires deterministically.
    """
    from fastapi import FastAPI

    app = FastAPI()

    @app.post("/api/v1/agent/run")
    def _run_agent():  # pragma: no cover - never invoked
        return {"ok": True}

    return app


def _strict_fastapi_app_with_coefficient_route():
    """Build a FastAPI app with the in-memory coefficient HTTP route.

    The audit (D-S2-06.c) walks ``app.routes`` and looks for the
    canonical coefficient path prefix ``/api/v1/coefficients`` on
    each ``APIRoute`` instance. The route is registered directly on
    the FastAPI app so the audit's reachability check fires
    deterministically.
    """
    from fastapi import FastAPI

    app = FastAPI()

    @app.post("/api/v1/coefficients/lookup")
    def _lookup():  # pragma: no cover - never invoked
        return {"ok": True}

    return app


def test_local_mode_app_none_passes_audit():
    """local + app=None → audit short-circuits with empty reachable set.

    Per TASK-012 Slice 2 brief §2: in local mode the audit must NOT
    raise even when the caller has not supplied a FastAPI app, because
    the demo / fixture flows legitimately register the fake-agent or
    in-memory coefficient routes and would otherwise poison every
    bootstrap-isolated test.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("local"))
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=None)
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_test_mode_app_none_passes_audit():
    """test + app=None → audit short-circuits with empty reachable set."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("test"))
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=None)
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_app_none_fails_closed():
    """staging + app=None → audit MUST raise UnsafeStrictCapabilityWiring.

    Per TASK-012 Slice 2 brief §2: in strict environments ``app=None``
    is still NOT a silent success; production lifespan must always
    pass ``app=app`` explicitly. The frozen code is
    ``UNSAFE_STRICT_CAPABILITY_WIRING``.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging"))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            enumerate_reachable_unsafe_strict_capabilities(app=None)
        # Stable code, not a free-form RuntimeError / Exception.
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_app_none_fails_closed():
    """production + app=None → audit MUST raise UnsafeStrictCapabilityWiring."""
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production"))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            enumerate_reachable_unsafe_strict_capabilities(app=None)
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_clean_app_passes_audit():
    """staging + clean FastAPI app → audit returns empty reachable set."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging"))
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=_strict_fastapi_app())
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_clean_app_passes_audit():
    """production + clean FastAPI app → audit returns empty reachable set."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production"))
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=_strict_fastapi_app())
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_planning_agent_route_fails_closed():
    """staging + fake-agent route registered → UNSAFE_STRICT_CAPABILITY_WIRING.

    We call :func:`assert_no_unsafe_strict_capabilities` (the public
    assertion wrapper) rather than the lower-level enumerator because
    the enumerator intentionally returns the reachable tuple so callers
    can branch on it; only the assertion wrapper raises.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        assert_no_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging"))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(
                app=_strict_fastapi_app_with_planning_agent_route()
            )
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
        assert "PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE" in (exc_info.value.unsafe_capabilities)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_planning_agent_route_fails_closed():
    """production + fake-agent route registered → UNSAFE_STRICT_CAPABILITY_WIRING."""
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        assert_no_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production"))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(
                app=_strict_fastapi_app_with_planning_agent_route()
            )
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
        assert "PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE" in (exc_info.value.unsafe_capabilities)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_coefficient_route_fails_closed():
    """staging + in-memory coefficient route → UNSAFE_STRICT_CAPABILITY_WIRING."""
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        assert_no_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging"))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(app=_strict_fastapi_app_with_coefficient_route())
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
        assert "COEFFICIENT_HTTP_ROUTE_STRICT_MODE" in (exc_info.value.unsafe_capabilities)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_coefficient_route_fails_closed():
    """production + in-memory coefficient route → UNSAFE_STRICT_CAPABILITY_WIRING."""
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        assert_no_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production"))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(app=_strict_fastapi_app_with_coefficient_route())
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
        assert "COEFFICIENT_HTTP_ROUTE_STRICT_MODE" in (exc_info.value.unsafe_capabilities)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]
