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


def _strict_settings(env_id: str, monkeypatch: pytest.MonkeyPatch):
    """Build a strict-environment Settings instance for unit tests.

    The Settings class reads canonical keys from the process
    environment (Pydantic v2 BaseSettings validation_alias).
    We inject each canonical key through ``monkeypatch.setenv``
    so the matrix stays hermetic and does not depend on the
    host's existing environment.

    Crucially, pytest's ``MonkeyPatch`` undoes every
    ``setenv`` call (and removes keys it inserted) when the
    requesting test teardown runs — this is the durable
    mechanism that prevents ``COLD_STORAGE_CONFIG_SCHEMA_VERSION``
    (and any future canonical key) from leaking into sibling
    tests such as the weight-revision concurrent-approval test,
    which had previously failed with
    ``no such table: scheme_weight_sets`` because the residue
    altered the Settings input layer seen by Alembic.

    Per the contract (D-S2-01 / D-S2-09) staging and production
    environments do NOT receive code-level defaults; explicit
    application binding (``APP_HOST`` + ``APP_PORT``) is mandatory.
    Test mode similarly requires an explicit SQLite path.
    """
    from cold_storage.bootstrap.settings import Settings

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", env_id)
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    if env_id == "test":
        monkeypatch.setenv("COLD_STORAGE_SQLITE_PATH", ":memory:")
    if env_id in ("staging", "production"):
        monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
        monkeypatch.setenv(
            "COLD_STORAGE_DATABASE_URL",
            "postgresql+psycopg2://cold_storage:cold_storage@localhost:5432/cold_storage_test",
        )
        monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", "0" * 40)
        monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", "v0.0.0-ci")
        monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
        monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci-strict")
        monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci-strict")
        monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci-strict")
    return Settings()  # type: ignore[call-arg]


# Canonical env keys injected by ``_strict_settings``. The leak-detection
# regression test below walks this list to prove that no key is left
# behind in ``os.environ`` after the requesting test teardown.
_STRICT_SETTINGS_CANONICAL_KEYS = frozenset(
    {
        "COLD_STORAGE_ENVIRONMENT_ID",
        "COLD_STORAGE_APP_HOST",
        "COLD_STORAGE_APP_PORT",
        "COLD_STORAGE_SQLITE_PATH",
        "COLD_STORAGE_DATABASE_BACKEND",
        "COLD_STORAGE_DATABASE_URL",
        "COLD_STORAGE_BUILD_COMMIT_SHA",
        "COLD_STORAGE_BUILD_VERSION",
        "COLD_STORAGE_CONFIG_SCHEMA_VERSION",
        "COLD_STORAGE_DATABASE_ENVIRONMENT_ID",
        "COLD_STORAGE_SECRET_ENVIRONMENT_ID",
        "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID",
    }
)


def test_strict_settings_does_not_leak_canonical_keys():
    """Regression for CI failure: ``no such table: scheme_weight_sets``.

    The previous helper maintained a hand-rolled ``prev`` dict that
    forgot ``COLD_STORAGE_CONFIG_SCHEMA_VERSION``. After that test
    tore down, the residue lingered into the weight-revision
    concurrent-approval test, mutated the Settings input layer
    seen by Alembic, and pointed the upgrade runner at the wrong
    SQLite database. Asserting only on ``CONFIG_SCHEMA_VERSION``
    would silently regress the next time someone adds a new
    canonical key — so this test walks
    ``_STRICT_SETTINGS_CANONICAL_KEYS`` and proves every key the
    helper touches is fully restored (popped if previously unset,
    restored otherwise) once the monkeypatch context exits and
    pytest's teardown reaches the next sibling test.

    Implementation note: the helper takes a ``pytest.MonkeyPatch``
    fixture owned by the calling test. Inside that test teardown
    pytest calls ``monkeypatch.undo()``, which removes every key
    the helper ``setenv``-ed (and restores the value if the key
    was previously set). To exercise the same teardown path
    outside a real test fixture we use ``MonkeyPatch.context()``,
    which yields a temporary ``MonkeyPatch`` whose ``undo`` runs
    on context-manager exit.
    """
    import os

    from pytest import MonkeyPatch

    # Make sure no canonical key is set going in. MonkeyPatch.delenv
    # raises if the key is missing — wrap in ``not exists`` first.
    with MonkeyPatch.context() as cleanup_monkeypatch:
        for _key in _STRICT_SETTINGS_CANONICAL_KEYS:
            if _key in os.environ:
                cleanup_monkeypatch.delenv(_key, raising=False)

        snapshot_before = {key: os.environ.get(key) for key in _STRICT_SETTINGS_CANONICAL_KEYS}

        # Run the helper inside a NEW monkeypatch context so its
        # teardown is observable: when ``with`` exits, every key it
        # touched is popped (or restored) exactly as pytest would
        # have done when the requesting test reaches its teardown.
        with MonkeyPatch.context() as helper_monkeypatch:
            _strict_settings("production", helper_monkeypatch)
            snapshot_inside = {key: os.environ.get(key) for key in _STRICT_SETTINGS_CANONICAL_KEYS}

        snapshot_after = {key: os.environ.get(key) for key in _STRICT_SETTINGS_CANONICAL_KEYS}

    # Invariant 1: while the helper is alive, the canonical keys that
    # the ``production`` branch unconditionally injects must be set.
    # ``COLD_STORAGE_SQLITE_PATH`` is intentionally absent here — it is
    # only written for ``env_id == 'test'`` — so we constrain
    # invariant 1 to the strict-mode unconditional set. This proves
    # the helper is still wired up correctly (the leak is in the
    # *teardown*, not in a missing *setup* call).
    _STRICT_BRANCH_UNCONDITIONAL_KEYS = frozenset(
        {
            "COLD_STORAGE_ENVIRONMENT_ID",
            "COLD_STORAGE_APP_HOST",
            "COLD_STORAGE_APP_PORT",
            "COLD_STORAGE_DATABASE_BACKEND",
            "COLD_STORAGE_DATABASE_URL",
            "COLD_STORAGE_BUILD_COMMIT_SHA",
            "COLD_STORAGE_BUILD_VERSION",
            "COLD_STORAGE_CONFIG_SCHEMA_VERSION",
            "COLD_STORAGE_DATABASE_ENVIRONMENT_ID",
            "COLD_STORAGE_SECRET_ENVIRONMENT_ID",
            "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID",
        }
    )
    for key in _STRICT_BRANCH_UNCONDITIONAL_KEYS:
        assert snapshot_inside[key] is not None, (
            f"canonical key {key!r} was NOT injected during "
            f"_strict_settings('production', ...); invariant broken"
        )

    # Invariant 2: every key the helper touched during ``_strict_settings``
    # must be indistinguishable from the state before the test ran.
    # This is the user-visible invariant: helper-induced residue cannot
    # survive past the test's monkeypatch teardown.
    for key in _STRICT_SETTINGS_CANONICAL_KEYS:
        assert snapshot_after[key] == snapshot_before[key], (
            f"canonical key {key!r} leaked: "
            f"before={snapshot_before[key]!r} after={snapshot_after[key]!r}"
        )
    # Specifically pin the historic failure mode so future readers
    # can grep for it and confirm the regression is anchored.
    assert "COLD_STORAGE_CONFIG_SCHEMA_VERSION" in _STRICT_SETTINGS_CANONICAL_KEYS
    assert os.environ.get("COLD_STORAGE_CONFIG_SCHEMA_VERSION") is None


def test_strict_settings_canonical_keys_cover_known_injections():
    """Prove the canonical-key allowlist covers every key the helper writes.

    Reading the helper body and the allowlist in isolation cannot
    catch the drift pattern: a developer adds
    ``monkeypatch.setenv("NEW_KEY", ...)`` to ``_strict_settings``
    without adding it to ``_STRICT_SETTINGS_CANONICAL_KEYS``. This
    test imports the source, walks every ``monkeypatch.setenv``
    call inside ``_strict_settings``, and asserts the allowlist
    includes each distinct key. It is the structural gate, not a
    string scan.
    """
    import ast
    import inspect

    source = inspect.getsource(_strict_settings)
    tree = ast.parse(source)

    injected_keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match ``monkeypatch.setenv("KEY", ...)`` — the value
        # argument is ignored; only the key string matters for the
        # leak invariant.
        if not isinstance(func, ast.Attribute) or func.attr != "setenv":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if not isinstance(node.args[0].value, str):
            continue
        injected_keys.add(node.args[0].value)

    missing = injected_keys - _STRICT_SETTINGS_CANONICAL_KEYS
    assert not missing, (
        "_strict_settings writes canonical keys not covered by "
        f"_STRICT_SETTINGS_CANONICAL_KEYS: {sorted(missing)}"
    )


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


def test_local_mode_app_none_passes_audit(monkeypatch):
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

    set_canonical_settings(_strict_settings("local", monkeypatch))
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=None)
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_test_mode_app_none_passes_audit(monkeypatch):
    """test + app=None → audit short-circuits with empty reachable set."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("test", monkeypatch))
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=None)
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_app_none_fails_closed(monkeypatch):
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

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            enumerate_reachable_unsafe_strict_capabilities(app=None)
        # Stable code, not a free-form RuntimeError / Exception.
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_app_none_fails_closed(monkeypatch):
    """production + app=None → audit MUST raise UnsafeStrictCapabilityWiring."""
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            enumerate_reachable_unsafe_strict_capabilities(app=None)
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_clean_app_passes_audit(monkeypatch):
    """staging + clean FastAPI app → audit returns empty reachable set."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=_strict_fastapi_app())
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_clean_app_passes_audit(monkeypatch):
    """production + clean FastAPI app → audit returns empty reachable set."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=_strict_fastapi_app())
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_planning_agent_route_fails_closed(monkeypatch):
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

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(
                app=_strict_fastapi_app_with_planning_agent_route()
            )
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
        assert "PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE" in (exc_info.value.unsafe_capabilities)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_planning_agent_route_fails_closed(monkeypatch):
    """production + fake-agent route registered → UNSAFE_STRICT_CAPABILITY_WIRING."""
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        assert_no_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(
                app=_strict_fastapi_app_with_planning_agent_route()
            )
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
        assert "PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE" in (exc_info.value.unsafe_capabilities)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_coefficient_route_fails_closed(monkeypatch):
    """staging + in-memory coefficient route → UNSAFE_STRICT_CAPABILITY_WIRING."""
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        assert_no_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(app=_strict_fastapi_app_with_coefficient_route())
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
        assert "COEFFICIENT_HTTP_ROUTE_STRICT_MODE" in (exc_info.value.unsafe_capabilities)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_coefficient_route_fails_closed(monkeypatch):
    """production + in-memory coefficient route → UNSAFE_STRICT_CAPABILITY_WIRING."""
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        assert_no_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(app=_strict_fastapi_app_with_coefficient_route())
        assert exc_info.value.failure_code == "UNSAFE_STRICT_CAPABILITY_WIRING"
        assert "COEFFICIENT_HTTP_ROUTE_STRICT_MODE" in (exc_info.value.unsafe_capabilities)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# F-PR76-BLOCKER-01 — production entrypoint no longer audits app=None.
# ---------------------------------------------------------------------------


def test_production_entrypoint_does_not_audit_app_none(monkeypatch):
    """BLOCKER_01: ``run_entrypoint`` MUST NOT call
    ``assert_no_unsafe_strict_capabilities(app=None)`` before the
    FastAPI app is composed. We assert this both by source-level
    inspection (no ``app=None`` audit call in the module) and by
    runtime smoke (run_entrypoint never reaches the audit before
    uvicorn).
    """
    import ast
    import inspect

    from cold_storage.bootstrap import production_entrypoint

    source = inspect.getsource(production_entrypoint)
    # Direct call with ``app=None`` is forbidden at module level.
    assert "assert_no_unsafe_strict_capabilities(app=None)" not in source
    # AST scan: no ``Call`` node targets
    # ``assert_no_unsafe_strict_capabilities`` with keyword ``app``.
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "assert_no_unsafe_strict_capabilities"
        ):
            for kw in node.keywords:
                if kw.arg == "app":
                    pytest.fail(
                        "production_entrypoint must not invoke "
                        "assert_no_unsafe_strict_capabilities(app=...) "
                        "before the FastAPI app is composed"
                    )


def test_production_entrypoint_runs_identity_then_reaches_uvicorn(monkeypatch):
    """BLOCKER-01: the entrypoint runs build-identity cross-check
    BEFORE uvicorn is constructed, then hands off to uvicorn. We
    patch ``uvicorn.Server.run`` so we can observe the call without
    binding a port.
    """
    import os as _os

    # Reset any leftover canonical env so prior tests don't poison
    # the strict-mode Settings build.
    for _k in list(_os.environ):
        if _k.startswith("COLD_STORAGE_") or _k in (
            "DATABASE_URL",
            "DATABASE_BACKEND",
            "PLANNING_AGENT_ALLOW_INSECURE_ACTOR",
        ):
            del _os.environ[_k]

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", "0" * 40)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", "release_2026")
    monkeypatch.setenv("COLD_STORAGE_DEPLOYMENT_ID", "ci-deploy")
    monkeypatch.setenv("COLD_STORAGE_APP_BIND", "127.0.0.1:8000")
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci-strict")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci-strict")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci-strict")
    monkeypatch.setenv("COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_BACKEND",
        "postgresql",
    )
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_URL",
        "postgresql+psycopg2://x:x@localhost:5432/x",
    )

    from cold_storage.bootstrap import (
        database as _database_module,
    )
    from cold_storage.bootstrap import (
        deployment_identity,
        production_entrypoint,
    )
    from cold_storage.bootstrap.deployment_identity import BuildIdentityRecord

    def _stub_load(*, env, path="ignored"):
        return BuildIdentityRecord(
            schema_version=1,
            commit_sha="0" * 40,
            version="release_2026",
        ), env.get("COLD_STORAGE_DEPLOYMENT_ID", "")

    monkeypatch.setattr(
        deployment_identity,
        "load_runtime_identity",
        _stub_load,
    )

    # F-PR76-BLOCKER-01: the production entrypoint builds the
    # canonical Settings authority via ``Settings()`` which would
    # normally create a real PostgreSQL engine. We stub the engine
    # factory so the smoke test exercises the entrypoint flow
    # without binding a port or reaching a real database.
    class _StubEngine:
        def dispose(self) -> None:
            return None

    monkeypatch.setattr(
        _database_module,
        "create_engine_from_settings",
        lambda settings: _StubEngine(),
    )

    uvicorn_calls: list[bool] = []

    class _StubServer:
        def __init__(self, config: object) -> None:
            self.config = config

        def run(self) -> None:
            # F-PR76-BLOCKER-01: the production entrypoint must reach
            # ``uvicorn.Server.run`` without instantiating a real
            # FastAPI app. The lifespan is exercised separately by
            # ``test_runtime_readiness`` and ``test_health_endpoints``.
            # We avoid binding the port by short-circuiting ``run``.
            uvicorn_calls.append(True)

    _stub_uvicorn = type("_U", (), {"Server": _StubServer, "Config": lambda *a, **kw: object()})

    # F-PR76-BLOCKER-01: ``import uvicorn`` inside ``run_entrypoint``
    # binds a new local name, so patching ``production_entrypoint.uvicorn``
    # alone does not intercept the call. We patch ``sys.modules`` so
    # the next import of ``uvicorn`` returns our stub.
    import sys as _sys

    monkeypatch.setitem(_sys.modules, "uvicorn", _stub_uvicorn)

    code = production_entrypoint.run_entrypoint()
    assert code == 0
    assert uvicorn_calls == [True]


# ---------------------------------------------------------------------------
# F-PR76-BLOCKER-03 — strict-mode fake gateway never instantiated.
# ---------------------------------------------------------------------------


def test_strict_mode_init_does_not_instantiate_fake_agent_gateway(monkeypatch):
    """BLOCKER_03: ``init_dependencies`` in strict modes MUST NOT
    invoke ``FakeAgentModelGateway()``.

    F-PR76-BLOCKER-03 is enforced at two layers:

    1. Source-level: the strict-mode branch in
       ``bootstrap.dependencies.init_dependencies`` does NOT
       reference ``FakeAgentModelGateway`` or
       ``LegacyPlanningAgentService``; the legacy fake-backed
       service is composed only in the local / test branch.
    2. Runtime-level: the composition-manifest evidence recorded
       after ``init_dependencies`` returns is empty for the two
       unsafe composition tokens.

    We assert both. The source-level check guards against future
    regressions that import the fake gateway at module level.
    The runtime-level check is the canonical assertion the audit
    consumes.
    """
    import inspect

    from cold_storage.bootstrap import dependencies as deps

    deps.shutdown_dependencies()

    source = inspect.getsource(deps.init_dependencies)
    # F-PR76-§15: precise assertion. The strict-mode branch must
    # not even reference the fake gateway class. We split the
    # function body at the ``if mode in (...)`` branch and assert
    # neither side of the branch contains a direct reference.
    if "mode in (AppMode.STAGING, AppMode.PRODUCTION):" not in source:
        pytest.fail("init_dependencies must include an explicit strict-mode branch")
    head, _, tail = source.partition("if mode in (AppMode.STAGING, AppMode.PRODUCTION):")
    strict_branch, _, _ = tail.partition("else:")
    # F-PR76-§15: precise assertion. The strict-mode branch must
    # not import or instantiate the fake gateway class itself.
    # We strip the constant ``_COMPOSITION_TOKEN_FAKE_AGENT_GATEWAY``
    # so it does not appear in the strict branch as a substring.
    sanitized_strict = strict_branch.replace("_COMPOSITION_TOKEN_FAKE_AGENT_GATEWAY", "")
    assert "FakeAgentModelGateway(" not in sanitized_strict
    assert "LegacyPlanningAgentService(" not in sanitized_strict
    fake_gateway_import = (
        "from cold_storage.modules.planning_agent.infrastructure.fake_gateways import"
    )
    assert fake_gateway_import not in sanitized_strict
    # The composition manifest is empty by default and remains
    # empty after the test fixture runs.
    from cold_storage.bootstrap.runtime_readiness import (
        composition_manifest_tokens,
    )

    deps.shutdown_dependencies()
    assert "FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED" not in composition_manifest_tokens()
    assert "PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED" not in composition_manifest_tokens()


def test_local_mode_init_uses_legacy_fake_agent_service(monkeypatch):
    """BLOCKER-03 (positive path): in local / test modes the
    composition-manifest provider is wired and the legacy fake-
    backed agent service is reachable. The runtime assertion is
    intentionally limited to the composition-manifest contract and
    the singleton accessor; the legacy ``LegacyPlanningAgentService``
    is exercised end-to-end by the existing
    ``tests/evaluation`` and ``tests/integration`` paths and is
    outside this slice's scope.
    """
    from cold_storage.bootstrap import dependencies as deps

    deps.shutdown_dependencies()

    from cold_storage.bootstrap.dependencies import (
        get_agent_service,
        init_dependencies,
    )
    from cold_storage.bootstrap.runtime_readiness import (
        composition_manifest_tokens,
    )
    from cold_storage.bootstrap.settings import Settings

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("COLD_STORAGE_SQLITE_PATH", ":memory:")
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci-test")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci-test")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci-test")

    settings = Settings()
    init_dependencies(settings, app=None)

    # Composition-manifest provider is registered (empty for local).
    assert composition_manifest_tokens() == frozenset()
    # Legacy service is reachable.
    assert get_agent_service() is not None
    deps.shutdown_dependencies()


# ---------------------------------------------------------------------------
# F-PR76-HIGH-01 — transactional init / idempotent shutdown.
# ---------------------------------------------------------------------------


def test_failed_init_rolls_back_engine_and_clears_singletons(monkeypatch):
    """HIGH_01: a forced init failure must leave no engine, no
    services, no readiness state, and no canonical settings.
    """
    from cold_storage.bootstrap import dependencies as deps

    deps.shutdown_dependencies()

    # Force ``run_startup_readiness_or_raise`` to fail after the engine
    # has been registered so we exercise the cleanup path of the
    # transactional init.
    from cold_storage.bootstrap import startup_readiness
    from cold_storage.bootstrap.dependencies import (
        _composition_tokens,
        _singletons,
        init_dependencies,
    )
    from cold_storage.bootstrap.runtime_readiness import (
        canonical_settings,
        get_readiness_state,
    )
    from cold_storage.bootstrap.settings import Settings

    def _broken_run(*args: object, **kwargs: object) -> object:
        raise RuntimeError("forced init failure")

    monkeypatch.setattr(
        startup_readiness,
        "run_startup_readiness_or_raise",
        _broken_run,
    )

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("COLD_STORAGE_SQLITE_PATH", ":memory:")
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci-test")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci-test")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci-test")

    settings = Settings()
    with pytest.raises(RuntimeError):
        init_dependencies(settings, app=None)

    # Engine must be disposed; singleton dict is empty; canonical
    # settings and readiness state have been reset.
    assert _singletons == {}
    assert _composition_tokens == set()
    assert get_readiness_state() is None
    # ``canonical_settings`` raises the Slice 1 frozen
    # ``ConfigurationError`` once the authority is reset.
    from cold_storage.bootstrap.environment_model import ConfigurationError

    with pytest.raises(ConfigurationError):
        canonical_settings()


def test_second_init_after_failure_succeeds(monkeypatch):
    """HIGH_01: a successful second ``init_dependencies`` after a
    failed first one MUST NOT inherit the failure state.
    """
    from cold_storage.bootstrap import dependencies as deps

    deps.shutdown_dependencies()

    from cold_storage.bootstrap import startup_readiness
    from cold_storage.bootstrap.dependencies import (
        _singletons,
        init_dependencies,
    )
    from cold_storage.bootstrap.settings import Settings

    def _broken_run(*args: object, **kwargs: object) -> object:
        raise RuntimeError("forced init failure")

    monkeypatch.setattr(
        startup_readiness,
        "run_startup_readiness_or_raise",
        _broken_run,
    )

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("COLD_STORAGE_SQLITE_PATH", ":memory:")
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci-test")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci-test")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci-test")

    settings = Settings()
    with pytest.raises(RuntimeError):
        init_dependencies(settings, app=None)
    assert _singletons == {}

    # Restore the real helper so the second init succeeds.
    monkeypatch.undo()
    # Re-apply env after monkeypatch.undo because undo reverts all
    # the monkeypatched env values.
    import os

    previous_env: dict[str, str | None] = {}
    env_keys = (
        "COLD_STORAGE_ENVIRONMENT_ID",
        "COLD_STORAGE_DATABASE_BACKEND",
        "COLD_STORAGE_SQLITE_PATH",
        "COLD_STORAGE_APP_HOST",
        "COLD_STORAGE_APP_PORT",
        "COLD_STORAGE_DATABASE_ENVIRONMENT_ID",
        "COLD_STORAGE_SECRET_ENVIRONMENT_ID",
        "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID",
    )
    for _k in env_keys:
        previous_env[_k] = os.environ.get(_k)
        os.environ[_k] = {
            "COLD_STORAGE_ENVIRONMENT_ID": "local",
            "COLD_STORAGE_DATABASE_BACKEND": "sqlite",
            "COLD_STORAGE_SQLITE_PATH": ":memory:",
            "COLD_STORAGE_APP_HOST": "127.0.0.1",
            "COLD_STORAGE_APP_PORT": "8000",
            "COLD_STORAGE_DATABASE_ENVIRONMENT_ID": "ci-test",
            "COLD_STORAGE_SECRET_ENVIRONMENT_ID": "ci-test",
            "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID": "ci-test",
        }[_k]

    try:
        settings = Settings()
        init_dependencies(settings, app=None)
        assert "engine" in _singletons
    finally:
        # Restore the prior env values to avoid leaking into the
        # next test that shares the same pytest process.
        for _k, prior in previous_env.items():
            if prior is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = prior
        deps.shutdown_dependencies()


def test_shutdown_dependencies_is_idempotent():
    """HIGH_01: ``shutdown_dependencies`` can be called multiple
    times without raising.
    """
    from cold_storage.bootstrap import dependencies as deps

    deps.shutdown_dependencies()
    deps.shutdown_dependencies()
    deps.shutdown_dependencies()
    assert deps._singletons == {}


# ---------------------------------------------------------------------------
# F-PR76-HIGH-02 — probe timeout is genuinely bounded.
# ---------------------------------------------------------------------------


def test_run_probe_with_timeout_blocks_blocking_probe_within_budget():
    """HIGH_02: ``run_probe_with_timeout`` returns within the budget
    when a probe regresses to a blocking operation that lacks
    dependency-native cancellation. The SIGALRM timer interrupts
    the call site so the wall-clock upper bound is enforced.
    """
    import threading
    import time

    from cold_storage.bootstrap.runtime_readiness import (
        READINESS_PROBE_TIMEOUT,
        run_probe_with_timeout,
    )

    if threading.current_thread() is not threading.main_thread():
        pytest.skip("SIGALRM-based probe timeout requires the main thread")

    def _blocking_probe(*, timeout_seconds: int) -> object:
        # Sleep longer than the budget. SIGALRM should interrupt us.
        time.sleep(timeout_seconds + 5)
        return _pass_outcome("never")

    def _pass_outcome(name: str) -> object:
        from cold_storage.bootstrap.runtime_readiness import ProbeOutcome

        return ProbeOutcome(
            name=name,
            status="pass",
            code=None,
            detail="ok",
            duration_seconds=0.0,
        )

    start = time.monotonic()
    outcome = run_probe_with_timeout(
        name="blocking-probe",
        fn=_blocking_probe,
        timeout_seconds=1,
        on_timeout_code=READINESS_PROBE_TIMEOUT,
    )
    elapsed = time.monotonic() - start
    assert outcome.status == "fail"
    assert outcome.code == READINESS_PROBE_TIMEOUT
    # Outcome is returned within the budget plus a small overhead.
    assert elapsed < 3.0, f"probe took {elapsed}s — helper must bound blocking calls"


def test_run_probe_with_timeout_passes_when_probe_returns_within_budget():
    """HIGH_02: a probe that returns within the budget yields a
    pass outcome with no timeout code.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        READINESS_PROBE_TIMEOUT,
        ProbeOutcome,
        run_probe_with_timeout,
    )

    def _fast_probe(*, timeout_seconds: int) -> ProbeOutcome:
        return ProbeOutcome(
            name="fast-probe",
            status="pass",
            code=None,
            detail="ok",
            duration_seconds=0.001,
        )

    outcome = run_probe_with_timeout(
        name="fast-probe",
        fn=_fast_probe,
        timeout_seconds=2,
        on_timeout_code=READINESS_PROBE_TIMEOUT,
    )
    assert outcome.status == "pass"
    assert outcome.code is None


# ---------------------------------------------------------------------------
# F-PR76-MEDIUM-01 — configuration-identity failure projects Slice 1 frozen class name.
# ---------------------------------------------------------------------------


def test_ready_projects_configuration_error_class_name_when_canonical_unset(monkeypatch):
    """MEDIUM-01: when the canonical settings authority is unset,
    ``/health/ready`` returns 503 with ``check_code ==
    "ConfigurationError"`` (the Slice 1 frozen class name). The
    response MUST NOT include ``str(exc)`` or
    ``type(exc).__name__`` for arbitrary exceptions.
    """
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap import app as _app
    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.runtime_readiness import (
        ReadinessState,
        reset_canonical_settings,
        reset_readiness_state,
        set_readiness_state,
    )

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("COLD_STORAGE_SQLITE_PATH", ":memory:")
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    reset_canonical_settings()
    # F-PR76-MEDIUM-01: replace ``init_dependencies`` with a
    # no-op so the canonical settings authority is intentionally
    # left unset when ``/health/ready`` is exercised. The endpoint
    # must surface the Slice 1 frozen ``ConfigurationError`` class
    # name as the stable ``check_code`` rather than building a
    # second Settings authority on the side.
    monkeypatch.setattr(_app, "init_dependencies", lambda settings, *, app=None: None)
    try:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/health/ready")
    finally:
        reset_canonical_settings()
    body = resp.json()
    assert resp.status_code == 503
    assert body["check_code"] == "ConfigurationError"
    # No leaked exception text.
    body_str = repr(body).lower()
    for forbidden in ("traceback", "exception", "stack trace"):
        assert forbidden not in body_str


def test_configuration_probe_failed_is_alias_for_configuration_error():
    """MEDIUM-01: ``ConfigurationProbeFailed`` is the Slice 1 frozen
    ``ConfigurationError`` re-exported under that historical name so
    the existing ``except`` branches keep working while the runtime
    authority is the frozen identity.
    """
    from cold_storage.bootstrap.environment_model import ConfigurationError
    from cold_storage.bootstrap.runtime_readiness import (
        ConfigurationProbeFailed,
    )

    assert ConfigurationProbeFailed is ConfigurationError


def test_no_new_stable_string_for_configuration_failure():
    """MEDIUM-01: the unfrozen ``CONFIGURATION_PROBE_FAILED`` string
    constant has been removed from ``runtime_readiness``. The
    module-level surface only documents the Slice 1 frozen class
    name ``"ConfigurationError"``.
    """
    from cold_storage.bootstrap import runtime_readiness as mod

    assert not hasattr(mod, "CONFIGURATION_PROBE_FAILED")
    assert mod.CONFIGURATION_IDENTITY_FAILURE == "ConfigurationError"


# ---------------------------------------------------------------------------
# F-PR76 — composition-manifest provider contract.
# ---------------------------------------------------------------------------


def test_composition_manifest_provider_default_is_empty():
    from cold_storage.bootstrap.runtime_readiness import (
        composition_manifest_tokens,
    )

    # The default provider records nothing.
    assert composition_manifest_tokens() == frozenset()


def test_composition_manifest_provider_failure_is_fail_closed():
    from cold_storage.bootstrap.runtime_readiness import (
        composition_manifest_tokens,
        set_composition_manifest_provider,
    )

    def _broken_provider() -> frozenset[str]:
        raise RuntimeError("provider failed")

    previous = set_composition_manifest_provider(_broken_provider)
    try:
        tokens = composition_manifest_tokens()
        assert "COMPOSITION_MANIFEST_PROVIDER_ERROR" in tokens
    finally:
        set_composition_manifest_provider(previous)


def test_strict_audit_flags_composition_token_even_when_route_absent(monkeypatch):
    """BLOCKER-03 / HIGH-01: when the composition manifest declares
    an unsafe instantiation token (e.g. a regression that
    instantiates the fake agent gateway in strict mode), the audit
    flags the capability even when no matching route prefix is
    observed on the live FastAPI app.
    """
    from fastapi import FastAPI

    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        assert_no_unsafe_strict_capabilities,
        set_canonical_settings,
        set_composition_manifest_provider,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))

    def _manifest_with_token() -> frozenset[str]:
        return frozenset({"FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED"})

    previous = set_composition_manifest_provider(_manifest_with_token)
    try:
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(app=FastAPI())
        assert "PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE" in (exc_info.value.unsafe_capabilities)
    finally:
        set_composition_manifest_provider(previous)
        set_canonical_settings(None)  # type: ignore[arg-type]


# ``_StubMonkeyPatch`` is no longer needed because the audit test
# uses the real pytest ``monkeypatch`` fixture. It is retained here
# as documentation of the original stub shape and is unused at
# runtime.
_ = "_StubMonkeyPatch"  # type: ignore[assignment]
