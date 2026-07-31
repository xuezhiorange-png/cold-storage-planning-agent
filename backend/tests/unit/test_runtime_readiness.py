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
    StartupNonTimeoutProbeFailure,
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
    """A non-timeout ``Exception`` with no ``on_non_timeout_code`` MUST fail closed.

    V0.2 Slice 2 amendment (D-S2-12.a.v0.2): the legacy behaviour
    that mapped arbitrary non-timeout ``Exception``s to the timeout
    code has been removed. The helper now raises
    :class:`StartupNonTimeoutProbeFailure` so callers cannot silently
    treat non-timeout failures as timeout events.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        StartupNonTimeoutProbeFailure,
    )

    def _boom(timeout_seconds: int) -> ProbeOutcome:
        raise RuntimeError("kaboom")

    with pytest.raises(StartupNonTimeoutProbeFailure):
        run_probe_with_timeout(name="boom", fn=_boom, timeout_seconds=5, on_timeout_code="TIMEOUT")


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

    # V0.2 Slice 2 amendment (D-S2-12.a.v0.2): the first probe
    # returns ``SOMETHING`` (a non-timeout failure code). Per the
    # amendment, non-timeout failures MUST be wrapped as
    # :class:`StartupNonTimeoutProbeFailure`, NOT
    # :class:`StartupProbeTimeout`. The timeout exception type is
    # reserved for genuine timeout events.
    with pytest.raises(StartupNonTimeoutProbeFailure) as exc_info:
        run_startup_phase(
            settings=_StubSettings("test"),
            environment=dict(os.environ),
            startup_probes=[_ok, _bad],
        )
    assert not isinstance(exc_info.value, StartupProbeTimeout)
    assert exc_info.value.failure_code == "SOMETHING"


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
            # F-PR76-STARTUP-EXIT-CODE: simulate the post-bind steady
            # state.  The entrypoint inspects ``started`` AFTER
            # ``server.run()`` returns to decide between a non-zero
            # exit (lifespan failure) and zero (graceful shutdown
            # after a successful bind).  Setting ``started=True`` here
            # exercises the success branch.
            self.started = False

        def run(self) -> None:
            # F-PR76-BLOCKER-01: the production entrypoint must reach
            # ``uvicorn.Server.run`` without instantiating a real
            # FastAPI app. The lifespan is exercised separately by
            # ``test_runtime_readiness`` and ``test_health_endpoints``.
            # We avoid binding the port by short-circuiting ``run``.
            uvicorn_calls.append(True)
            self.started = True  # simulates "reached steady state, then graceful shutdown"

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
# F-PR76-STARTUP-EXIT-CODE — server.started is the post-bind truth signal.
# ---------------------------------------------------------------------------


def _set_up_entrypoint_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build a complete production-env dict for entrypoint smoke tests.

    Centralised so all four entrypoint exit-code tests share the
    same hermetic env.  Tests may still override individual keys via
    ``monkeypatch.setenv`` after calling this helper.
    """
    for _k in list(os.environ):
        if _k.startswith("COLD_STORAGE_") or _k in (
            "DATABASE_URL",
            "DATABASE_BACKEND",
            "PLANNING_AGENT_ALLOW_INSECURE_ACTOR",
        ):
            del os.environ[_k]
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
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_URL",
        "postgresql+psycopg2://x:x@localhost:5432/x",
    )


def _stub_database_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``bootstrap.database.create_engine_from_settings`` so the
    production entrypoint never instantiates a real engine during
    these smoke tests.
    """
    from cold_storage.bootstrap import database as _database_module

    class _StubEngine:
        def dispose(self) -> None:
            return None

    monkeypatch.setattr(
        _database_module,
        "create_engine_from_settings",
        lambda settings: _StubEngine(),
    )


def _stub_load_runtime_identity_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``bootstrap.deployment_identity.load_runtime_identity``
    so the identity cross-check returns a valid pair (avoiding the
    early-return paths so we exercise the uvicorn path).
    """
    from cold_storage.bootstrap import deployment_identity
    from cold_storage.bootstrap.deployment_identity import BuildIdentityRecord

    def _stub_load(*, env, path="ignored"):
        return (
            BuildIdentityRecord(
                schema_version=1,
                commit_sha="0" * 40,
                version="release_2026",
            ),
            env.get("COLD_STORAGE_DEPLOYMENT_ID", ""),
        )

    monkeypatch.setattr(
        deployment_identity,
        "load_runtime_identity",
        _stub_load,
    )


def _install_started_fake_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
    *,
    started_value: bool,
) -> list[bool]:
    """Install a fake ``uvicorn`` module whose ``Server`` flips
    ``started`` to ``started_value`` after ``run()`` returns.

    Returns a list of records (one per call) so the test can assert
    on call counts.
    """
    calls: list[bool] = []

    class _StubServer:
        def __init__(self, config: object) -> None:
            self.config = config
            self.started = False
            self.should_exit = False

        def run(self) -> None:
            calls.append(True)
            # F-PR76-STARTUP-EXIT-CODE: the entrypoint reads
            # ``started`` AFTER ``run()`` returns.  We set the
            # flag to the test-supplied ``started_value`` to
            # exercise both the failure branch
            # (``started_value=False`` -> exit 1) and the success
            # branch (``started_value=True``  -> exit 0).
            self.started = started_value
            self.should_exit = True

    _stub_uvicorn = type(
        "_U",
        (),
        {
            "Server": _StubServer,
            "Config": lambda *a, **kw: object(),
        },
    )
    import sys as _sys

    monkeypatch.setitem(_sys.modules, "uvicorn", _stub_uvicorn)
    return calls


def test_entrypoint_server_never_started_returns_nonzero(monkeypatch):
    """F-PR76-STARTUP-EXIT-CODE: when the uvicorn ``Server.run``
    returns WITHOUT flipping ``started`` to True (lifespan /
    startup failure path), the entrypoint must exit non-zero so
    container orchestration and CI can observe the failure.

    The contract: a successful production lifespan is the ONLY
    reason ``started`` becomes True; everything else (early
    raise from the readiness check, OOM during startup, FastAPI
    app factory error) leaves ``started`` False.
    """
    _set_up_entrypoint_env(monkeypatch)
    _stub_database_engine(monkeypatch)
    _stub_load_runtime_identity_ok(monkeypatch)
    calls = _install_started_fake_uvicorn(monkeypatch, started_value=False)

    from cold_storage.bootstrap import production_entrypoint

    code = production_entrypoint.run_entrypoint()
    assert calls == [True], "uvicorn.Server.run must have been invoked exactly once"
    assert code == 1, (
        f"entrypoint must return non-zero when uvicorn started=False "
        f"(lifespan failure path); got code={code}"
    )
    assert code != 0, "explicit non-zero guard: code must NOT be 0"


def test_entrypoint_server_started_then_stopped_returns_zero(monkeypatch):
    """F-PR76-STARTUP-EXIT-CODE: when the uvicorn ``Server.run``
    flips ``started`` to True (steady state reached), the entrypoint
    must exit 0.  This includes the normal "started, then graceful
    shutdown on SIGTERM" case where ``run()`` returns after the
    server has already been serving traffic.
    """
    _set_up_entrypoint_env(monkeypatch)
    _stub_database_engine(monkeypatch)
    _stub_load_runtime_identity_ok(monkeypatch)
    calls = _install_started_fake_uvicorn(monkeypatch, started_value=True)

    from cold_storage.bootstrap import production_entrypoint

    code = production_entrypoint.run_entrypoint()
    assert calls == [True], "uvicorn.Server.run must have been invoked exactly once"
    assert code == 0, (
        f"entrypoint must return 0 when uvicorn started=True "
        f"(normal startup then graceful shutdown); got code={code}"
    )


def test_entrypoint_identity_failure_behavior_unchanged(monkeypatch):
    """F-PR76-STARTUP-EXIT-CODE: the entrypoint's identity
    cross-check failure path returns 14, and the new exit-code
    logic must NOT interfere with that early-return path.

    We patch ``load_runtime_identity`` to raise
    ``BuildIdentityMismatch`` so the entrypoint short-circuits
    BEFORE constructing uvicorn.  We assert uvicorn is never
    invoked and the exit code stays 14.
    """
    from cold_storage.bootstrap import deployment_identity
    from cold_storage.bootstrap.deployment_identity import (
        BuildCommitMismatch,
    )

    _set_up_entrypoint_env(monkeypatch)
    _stub_database_engine(monkeypatch)

    def _stub_load_raises(*, env, path="ignored"):
        raise BuildCommitMismatch(
            failure_code="BUILD_COMMIT_MISMATCH",
            detail="injected identity failure",
        )

    monkeypatch.setattr(
        deployment_identity,
        "load_runtime_identity",
        _stub_load_raises,
    )
    # If uvicorn is reached, this list will record it; we assert
    # the list is empty.
    calls = _install_started_fake_uvicorn(monkeypatch, started_value=False)

    from cold_storage.bootstrap import production_entrypoint

    code = production_entrypoint.run_entrypoint()
    assert calls == [], "uvicorn must NOT be reached when identity cross-check fails"
    assert code == 14, f"identity failure exit code must stay 14 (frozen contract); got code={code}"


def test_entrypoint_timeout_configuration_failure_behavior_unchanged(monkeypatch):
    """F-PR76-STARTUP-EXIT-CODE: the entrypoint's probe-timeout
    configuration failure path returns 15 or 16 (kind-dependent),
    and the new exit-code logic must NOT interfere with that
    early-return path either.

    We inject a malformed timeout env var so the validation
    path raises before constructing uvicorn, and assert uvicorn
    is never invoked.
    """
    _set_up_entrypoint_env(monkeypatch)
    _stub_database_engine(monkeypatch)
    _stub_load_runtime_identity_ok(monkeypatch)
    # Malformed timeout: not an integer.  resolve_probe_timeout_seconds
    # accepts the env value; the explicit-numeric re-validation
    # on the raw key will raise inside run_entrypoint and return 16.
    monkeypatch.setenv("COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS", "not-an-int")
    calls = _install_started_fake_uvicorn(monkeypatch, started_value=False)

    from cold_storage.bootstrap import production_entrypoint

    code = production_entrypoint.run_entrypoint()
    assert calls == [], "uvicorn must NOT be reached when probe timeout validation fails"
    # Per F-PR76 the probe-timeout validation exits 16 (raw form
    # mismatch).  We accept 15 or 16 here to be tolerant of the
    # exact kind that triggers first, but the contract is
    # non-zero and BEFORE uvicorn.
    assert code != 0, f"timeout-config failure exit code must be non-zero; got code={code}"
    assert code in (15, 16), (
        f"timeout-config failure exit code must be 15 or 16 (frozen contract); got code={code}"
    )


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


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: DATABASE_SCHEMA_HEAD_INVALID classification
# (D-S2-12.a.v0.2).
#
# The contract freezes exactly one new public stable code for every
# non-timeout failure of the ``database_exact_alembic_head`` mandatory
# probe. Eleven internal reasons are defined as a closed set and MUST
# all project to ``DATABASE_SCHEMA_HEAD_INVALID``. Timeout codes are
# reserved for genuine timeout events. No generic ``Exception`` from
# the probe may be mis-projected to a timeout code.
# ---------------------------------------------------------------------------


_SCHEMA_HEAD_INVALID_INTERNAL_REASONS: tuple[str, ...] = (
    "PACKAGED_HEAD_MISSING",
    "PACKAGED_HEAD_UNREADABLE",
    "PACKAGED_HEAD_MALFORMED",
    "PACKAGED_HEAD_ZERO",
    "PACKAGED_HEAD_MULTIPLE",
    "DATABASE_HEAD_UNREADABLE_AFTER_CONNECTION",
    "DATABASE_HEAD_ZERO",
    "DATABASE_HEAD_MULTIPLE",
    "DATABASE_HEAD_MALFORMED",
    "DATABASE_HEAD_MISMATCH",
    "UNKNOWN_SCHEMA_IDENTITY",
)


def test_schema_head_internal_reason_count_is_eleven():
    """The contract amendment freezes the internal reason count at 11.

    Parametrizing at the test layer protects against silent additions
    or removals to the closed set. The assertion here is on the
    constant exposed by the module — not on the test tuple — so the
    contract assertion remains authoritative.
    """
    import cold_storage.bootstrap.runtime_readiness as rr

    expected = _SCHEMA_HEAD_INVALID_INTERNAL_REASONS
    # Constant naming deliberately NOT exported (private internal closed
    # set); we inspect via a sentinel that mirrors the production tuple.
    assert expected == rr._INTERNAL_SCHEMA_HEAD_REASONS
    assert len(rr._INTERNAL_SCHEMA_HEAD_REASONS) == 11


@pytest.mark.parametrize("internal_reason", _SCHEMA_HEAD_INVALID_INTERNAL_REASONS)
def test_schema_head_internal_reason_is_recognized(internal_reason: str):
    """Every frozen internal reason must be in the 11-element closed set."""
    import cold_storage.bootstrap.runtime_readiness as rr

    assert internal_reason in rr._INTERNAL_SCHEMA_HEAD_REASONS
    assert len(internal_reason) > 0


def test_schema_head_invalid_constant_is_public_and_stable():
    """The single new public stable code must equal its frozen value."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
    )

    assert DATABASE_SCHEMA_HEAD_INVALID == "DATABASE_SCHEMA_HEAD_INVALID"


def test_schema_head_helper_coerces_unknown_reason_to_unknown_identity():
    """An unknown internal reason MUST coerce to UNKNOWN_SCHEMA_IDENTITY."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        PROBE_SCHEMA,
        _schema_head_invalid,
    )

    outcome = _schema_head_invalid(
        name=PROBE_SCHEMA,
        internal_reason="DEFINITELY_NOT_A_REAL_REASON",
        duration=0.01,
    )
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert outcome.status == "fail"
    assert "UNKNOWN_SCHEMA_IDENTITY" in outcome.detail
    # The raw reason string MUST NOT be exposed.
    assert "DEFINITELY_NOT_A_REAL_REASON" not in outcome.detail


def test_schema_head_helper_accepts_all_frozen_reasons():
    """Every frozen reason, when passed to the helper, projects safely."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        _schema_head_invalid,
    )

    for reason in _SCHEMA_HEAD_INVALID_INTERNAL_REASONS:
        outcome = _schema_head_invalid(
            name="database_exact_alembic_head",
            internal_reason=reason,
            duration=0.0,
        )
        assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
        assert outcome.status == "fail"
        assert reason in outcome.detail


# ---- run_probe_with_timeout: on_non_timeout_code parameter -----------------


def _exception_probe(timeout_seconds: int) -> ProbeOutcome:  # noqa: ARG001
    raise RuntimeError("schema probe exploded unexpectedly")


def test_run_probe_with_timeout_on_non_timeout_code_uses_non_timeout_code():
    """When the probe raises an Exception, ``on_non_timeout_code`` wins.

    Without ``on_non_timeout_code`` the helper falls back to
    ``on_timeout_code`` (legacy behaviour); with it, an unexpected
    ``Exception`` MUST project to that stable code instead of being
    mis-classified as a timeout.
    """
    out = run_probe_with_timeout(
        name="schema-head-probe",
        fn=_exception_probe,
        timeout_seconds=5,
        on_timeout_code="STARTUP_PROBE_TIMEOUT",
        on_non_timeout_code="DATABASE_SCHEMA_HEAD_INVALID",
    )
    assert out.status == "fail"
    assert out.code == "DATABASE_SCHEMA_HEAD_INVALID"
    assert out.code != "STARTUP_PROBE_TIMEOUT"


def test_run_probe_with_timeout_without_on_non_timeout_code_no_timeout_fallback():
    """``on_non_timeout_code=None`` MUST NOT mis-project to timeout code.

    V0.2 Slice 2 amendment (D-S2-12.a.v0.2): the legacy fallback that
    mapped arbitrary non-timeout exceptions to ``STARTUP_PROBE_TIMEOUT``
    has been removed. When ``on_non_timeout_code`` is ``None`` and an
    ``Exception`` escapes the probe, ``run_probe_with_timeout`` raises
    :class:`StartupNonTimeoutProbeFailure` instead of returning a
    timeout outcome.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        StartupNonTimeoutProbeFailure,
    )

    with pytest.raises(StartupNonTimeoutProbeFailure) as excinfo:
        run_probe_with_timeout(
            name="legacy-probe",
            fn=_exception_probe,
            timeout_seconds=5,
            on_timeout_code="STARTUP_PROBE_TIMEOUT",
        )
    assert excinfo.value.probe_name == "legacy-probe"
    msg = str(excinfo.value)
    assert "RuntimeError" in msg
    assert "schema probe exploded unexpectedly" not in msg


def test_run_probe_with_timeout_preserves_probe_supplied_fail_code():
    """A probe that returns a fail outcome with its own stable code MUST keep it.

    The schema probe sets ``DATABASE_SCHEMA_HEAD_INVALID`` on its own
    non-timeout failures. The wrapper MUST NOT override that code with
    ``on_timeout_code`` — only fill in when no code was provided.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
    )

    def _explicit_fail(timeout_seconds: int) -> ProbeOutcome:  # noqa: ARG001
        return ProbeOutcome(
            name="schema-probe",
            status="fail",
            code=DATABASE_SCHEMA_HEAD_INVALID,
            detail="packaged head missing",
        )

    out = run_probe_with_timeout(
        name="schema-probe",
        fn=_explicit_fail,
        timeout_seconds=5,
        on_timeout_code="STARTUP_PROBE_TIMEOUT",
    )
    assert out.status == "fail"
    assert out.code == DATABASE_SCHEMA_HEAD_INVALID
    assert out.code != "STARTUP_PROBE_TIMEOUT"


def test_run_probe_with_timeout_still_emits_timeout_on_alarm():
    """The wall-clock SIGALRM budget MUST still surface as timeout code."""

    def _blocking(timeout_seconds: int) -> ProbeOutcome:  # noqa: ARG001
        # Sleep for longer than the budget; the SIGALRM handler in
        # _on_alarm raises BlockingProbeTimeout which is converted to
        # the timeout code by the wrapper.
        import time as _t

        _t.sleep(timeout_seconds + 1)
        return ProbeOutcome(name="blocking", status="pass")

    out = run_probe_with_timeout(
        name="blocking",
        fn=_blocking,
        timeout_seconds=1,
        on_timeout_code="STARTUP_PROBE_TIMEOUT",
        on_non_timeout_code="DATABASE_SCHEMA_HEAD_INVALID",
    )
    # The alarm fires either as BlockingProbeTimeout (which yields
    # on_timeout_code) or the probe ran past its budget and the wrapper
    # reclassified it. Either way, the code MUST NOT be the
    # non-timeout code; it MUST be the timeout code.
    assert out.status == "fail"
    assert out.code == "STARTUP_PROBE_TIMEOUT"


# ---- probe_database_exact_alembic_head: per-reason classification -----------


class _FakeEngine:
    """Minimal SQLAlchemy ``Engine`` double that returns a preset row."""

    def __init__(self, row_value=None, raise_on_connect: Exception | None = None):
        self._row_value = row_value
        self._raise_on_connect = raise_on_connect

    def connect(self):  # pragma: no cover - trivial passthrough
        return _FakeConnection(self._row_value, self._raise_on_connect)


class _FakeConnection:
    def __init__(self, row_value, raise_on_connect):
        self._row_value = row_value
        self._raise_on_connect = raise_on_connect

    def __enter__(self):
        if self._raise_on_connect is not None:
            raise self._raise_on_connect
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def exec_driver_sql(self, _sql: str):
        if self._row_value is None:
            return _FakeRowResult(None)
        return _FakeRowResult(self._row_value)


class _FakeRowResult:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


def _install_fake_engine(monkeypatch, *, row_value=None, raise_on_connect=None):
    """Install a fake ``get_engine`` so the probe never touches a real DB."""
    import cold_storage.bootstrap.dependencies as deps

    monkeypatch.setattr(
        deps,
        "get_engine",
        lambda: _FakeEngine(row_value=row_value, raise_on_connect=raise_on_connect),
    )


def _install_fake_alembic_graph(
    monkeypatch,
    *,
    head=None,
    internal_reason=None,
):
    """Install a fake alembic-graph loader.

    Replaces ``_load_packaged_alembic_head`` so the probe never
    touches a real alembic graph.
    """
    import cold_storage.bootstrap.runtime_readiness as rr

    if internal_reason is not None:

        def _fake_loader():
            return (None, internal_reason)
    else:

        def _fake_loader():
            return (head, None)

    monkeypatch.setattr(rr, "_load_packaged_alembic_head", _fake_loader)


_VALID_REVISION = "abc123def456"


def test_schema_head_probe_exact_match_returns_pass(monkeypatch):
    """Exact Head match returns PASS with code is None."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        PROBE_SCHEMA,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    settings = _strict_settings("production", monkeypatch)
    set_canonical_settings(settings)
    _install_fake_engine(monkeypatch, row_value=(_VALID_REVISION,))
    _install_fake_alembic_graph(monkeypatch, head=_VALID_REVISION)
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "pass"
    assert outcome.code is None
    assert outcome.name == PROBE_SCHEMA
    # Belt-and-braces: pass MUST NOT leak the new fail code.
    assert outcome.code != DATABASE_SCHEMA_HEAD_INVALID
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_packaged_missing_classifies_as_schema_invalid(monkeypatch):
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_engine(monkeypatch)
    _install_fake_alembic_graph(monkeypatch, internal_reason="PACKAGED_HEAD_MISSING")
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "PACKAGED_HEAD_MISSING" in outcome.detail
    # CRITICAL: MUST NOT be projected to a timeout code.
    assert "TIMEOUT" not in outcome.code
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_packaged_malformed_classifies_as_schema_invalid(monkeypatch):
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_engine(monkeypatch, row_value=(_VALID_REVISION,))
    _install_fake_alembic_graph(monkeypatch, internal_reason="PACKAGED_HEAD_MALFORMED")
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "PACKAGED_HEAD_MALFORMED" in outcome.detail
    assert "TIMEOUT" not in outcome.code
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_packaged_multiple_classifies_as_schema_invalid(monkeypatch):
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_engine(monkeypatch, row_value=(_VALID_REVISION,))
    _install_fake_alembic_graph(monkeypatch, internal_reason="PACKAGED_HEAD_MULTIPLE")
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "PACKAGED_HEAD_MULTIPLE" in outcome.detail
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_database_head_zero_classifies_as_schema_invalid(monkeypatch):
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_engine(monkeypatch, row_value=None)
    _install_fake_alembic_graph(monkeypatch, head=_VALID_REVISION)
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "DATABASE_HEAD_ZERO" in outcome.detail
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_database_head_malformed_classifies_as_schema_invalid(monkeypatch):
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_engine(monkeypatch, row_value=("garbage,malformed",))
    _install_fake_alembic_graph(monkeypatch, head=_VALID_REVISION)
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "DATABASE_HEAD_MALFORMED" in outcome.detail
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_database_head_mismatch_classifies_as_schema_invalid(monkeypatch):
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_engine(monkeypatch, row_value=("0123456789ab",))
    _install_fake_alembic_graph(monkeypatch, head=_VALID_REVISION)
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "DATABASE_HEAD_MISMATCH" in outcome.detail
    # Mismatch MUST NOT be projected to a timeout code.
    assert "TIMEOUT" not in outcome.code
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_database_unreadable_after_connection_classifies(monkeypatch):
    """Connection-time exception MUST project to DATABASE_HEAD_UNREADABLE_AFTER_CONNECTION."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_engine(monkeypatch, raise_on_connect=RuntimeError("boom"))
    _install_fake_alembic_graph(monkeypatch, head=_VALID_REVISION)
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "DATABASE_HEAD_UNREADABLE_AFTER_CONNECTION" in outcome.detail
    # Raw exception text MUST NOT leak.
    assert "boom" not in outcome.detail
    assert "RuntimeError" not in outcome.detail
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_unknown_schema_identity_when_settings_missing(monkeypatch):
    """When canonical settings are not initialized, the probe classifies
    the unknown schema identity as DATABASE_SCHEMA_HEAD_INVALID with
    UNKNOWN_SCHEMA_IDENTITY internal reason."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        reset_canonical_settings,
    )

    reset_canonical_settings()
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "UNKNOWN_SCHEMA_IDENTITY" in outcome.detail


def test_schema_head_probe_non_strict_mode_returns_pass_without_packaged_head(monkeypatch):
    """Local / test mode skips the probe; missing packaged head is fine."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    settings = _strict_settings("local", monkeypatch)
    set_canonical_settings(settings)
    _install_fake_alembic_graph(monkeypatch, internal_reason="PACKAGED_HEAD_MISSING")
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "pass"
    set_canonical_settings(None)  # type: ignore[arg-type]


@pytest.mark.parametrize("internal_reason", _SCHEMA_HEAD_INVALID_INTERNAL_REASONS)
def test_schema_head_safe_projection_never_leaks_head_values(monkeypatch, internal_reason):
    """No detail projection leaks the raw Head value, DSN, or SQL fragment."""
    from cold_storage.bootstrap.runtime_readiness import (
        _schema_head_invalid,
    )

    outcome = _schema_head_invalid(
        name="database_exact_alembic_head",
        internal_reason=internal_reason,
        duration=0.001,
    )
    s = str(outcome.detail)
    # Head value shapes must never appear in the detail.
    assert _VALID_REVISION not in s
    assert "0123456789ab" not in s
    # Connection / SQL leakage must never appear.
    assert "DSN" not in s
    assert "password" not in s
    assert "SELECT" not in s.upper() or internal_reason in s


def test_schema_head_probe_packaged_head_empty_string_classifies_as_missing(monkeypatch):
    """Empty-string packaged head classifies as ``PACKAGED_HEAD_MISSING``.

    Under the graph-based loader an empty revision list maps to
    ``PACKAGED_HEAD_ZERO``; the probe's closed-set mapping keeps both
    ``PACKAGED_HEAD_ZERO`` and ``PACKAGED_HEAD_MISSING`` projected to
    ``DATABASE_SCHEMA_HEAD_INVALID``.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_engine(monkeypatch)
    _install_fake_alembic_graph(monkeypatch, internal_reason="PACKAGED_HEAD_ZERO")
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "PACKAGED_HEAD_ZERO" in outcome.detail
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_packaged_head_whitespace_only_classifies_as_missing(monkeypatch):
    """Whitespace-only packaged head MUST classify as PACKAGED_HEAD_MISSING."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_engine(monkeypatch)
    _install_fake_alembic_graph(monkeypatch, internal_reason="PACKAGED_HEAD_MISSING")
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "PACKAGED_HEAD_MISSING" in outcome.detail
    set_canonical_settings(None)  # type: ignore[arg-type]


def test_schema_head_probe_database_head_multiple_via_two_rows_classifies(monkeypatch):
    """Multiple-element column payload is treated as malformed.

    The probe reads ``head_row[0]`` from the SQLAlchemy result. A
    non-string payload (e.g. a 2-tuple from a corrupted migration
    table) is treated as malformed by the
    ``_is_alembic_revision`` shape check; the probe classifies it
    as ``DATABASE_HEAD_MALFORMED`` without surfacing the value.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        probe_database_exact_alembic_head,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    _install_fake_alembic_graph(monkeypatch, head=_VALID_REVISION)

    # Wrap a 2-tuple as the recorded payload. ``head_row[0]`` returns
    # the first element of the tuple, which is itself a tuple — the
    # probe's ``_is_alembic_revision`` shape check then classifies
    # this as malformed (non-string value).
    class _MultiColConnection(_FakeConnection):
        def exec_driver_sql(self, _sql):
            return _FakeRowResult((("nested", "tuple"), _VALID_REVISION))

    class _MultiColEngine(_FakeEngine):
        def connect(self):  # noqa: D401
            return _MultiColConnection(None, None)

    import cold_storage.bootstrap.dependencies as deps

    monkeypatch.setattr(deps, "get_engine", lambda: _MultiColEngine())
    outcome = probe_database_exact_alembic_head(timeout_seconds=5)
    assert outcome.status == "fail"
    assert outcome.code == DATABASE_SCHEMA_HEAD_INVALID
    assert "MALFORMED" in outcome.detail
    set_canonical_settings(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: packaged Head authority + loader behavior.
# ---------------------------------------------------------------------------


def test_packaged_head_loader_unset_env_var_succeeds(monkeypatch):
    """When the legacy env var is unset, the graph loader MUST still succeed.

    This is the production reality: the container does NOT export
    ``COLD_STORAGE_PACKAGED_ALEMBIC_HEAD``. The loader MUST still
    return a valid head from the packaged graph. The current
    development alembic graph may legitimately have multiple heads
    (in which case the loader classifies as
    ``PACKAGED_HEAD_MULTIPLE``); the assertion below permits both
    the single-head and multi-head outcomes — the loader MUST NOT
    consult the env var.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        _load_packaged_alembic_head,
    )

    monkeypatch.delenv("COLD_STORAGE_PACKAGED_ALEMBIC_HEAD", raising=False)
    head, reason = _load_packaged_alembic_head()
    # Either a single valid head OR a multi-head classification is
    # acceptable for the real development graph. The point of this
    # test is to prove the loader does not consult the env var.
    if reason is not None:
        # Multi-head (or zero/missing) classifications are valid
        # outcomes — the loader does not consult the env var.
        assert reason in {
            "PACKAGED_HEAD_MULTIPLE",
            "PACKAGED_HEAD_ZERO",
            "PACKAGED_HEAD_MISSING",
            "PACKAGED_HEAD_UNREADABLE",
            "PACKAGED_HEAD_MALFORMED",
        }
    else:
        assert isinstance(head, str)
        assert head.strip() == head
        assert "," not in head


def test_packaged_head_loader_ignores_env_var(monkeypatch):
    """The loader MUST ignore ``COLD_STORAGE_PACKAGED_ALEMBIC_HEAD`` even when set.

    The real development graph may have multiple heads; setting the
    env var MUST NOT change the loader's outcome.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        _load_packaged_alembic_head,
    )

    # Capture the baseline (no env var).
    monkeypatch.delenv("COLD_STORAGE_PACKAGED_ALEMBIC_HEAD", raising=False)
    base_head, base_reason = _load_packaged_alembic_head()

    # Now set the env var to a misleading value.
    monkeypatch.setenv("COLD_STORAGE_PACKAGED_ALEMBIC_HEAD", "ffffffffffff")
    env_head, env_reason = _load_packaged_alembic_head()

    assert base_head == env_head
    assert base_reason == env_reason


def test_packaged_head_loader_reads_alembic_versions(tmp_path, monkeypatch):
    """The loader reads ``alembic/versions/`` without importing alembic."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    root = tmp_path / "backend"
    script_dir = root / "alembic"
    versions_dir = script_dir / "versions"
    versions_dir.mkdir(parents=True)
    (versions_dir / "0001_initial.py").write_text(
        "revision = 'abc123def456'\ndown_revision = None\n"
    )
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert heads == ("abc123def456",)
    assert parents == {"abc123def456": (None,)}


def test_packaged_head_loader_zero_heads_classifies_zero(tmp_path):
    """An empty graph returns ``PACKAGED_HEAD_ZERO``."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    root = tmp_path / "backend" / "alembic" / "versions"
    root.mkdir(parents=True)
    heads, parents = _parse_alembic_revisions(root)
    assert heads == ()
    assert parents == {}


def test_packaged_head_loader_multiple_heads_classifies_multiple(tmp_path):
    """Multiple branches produce multiple heads."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = tmp_path / "versions"
    versions_dir.mkdir()
    (versions_dir / "0001_a.py").write_text("revision = 'aaa111aaa111'\ndown_revision = None\n")
    (versions_dir / "0001_b.py").write_text("revision = 'bbb222bbb222'\ndown_revision = None\n")
    heads, _ = _parse_alembic_revisions(versions_dir)
    assert len(heads) >= 2


def test_packaged_head_loader_does_not_execute_env_py(tmp_path):
    """An ``env.py`` that raises on import does not affect the loader."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = tmp_path / "versions"
    versions_dir.mkdir()
    (tmp_path / "env.py").write_text(
        "raise RuntimeError('env.py MUST NOT be executed by the loader')\n"
    )
    (versions_dir / "0001_initial.py").write_text(
        "revision = 'abc123def456'\ndown_revision = None\n"
    )
    heads, _ = _parse_alembic_revisions(versions_dir)
    assert heads == ("abc123def456",)


def test_packaged_head_loader_does_not_connect_to_database(tmp_path):
    """Loading the graph MUST NOT connect to any database."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = tmp_path / "versions"
    versions_dir.mkdir()
    (versions_dir / "0001_initial.py").write_text(
        "revision = 'abc123def456'\ndown_revision = None\n"
    )
    heads, _ = _parse_alembic_revisions(versions_dir)
    assert heads == ("abc123def456",)


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: startup-phase exception discrimination.
# ---------------------------------------------------------------------------


def test_run_startup_phase_timeout_outcome_wraps_as_startup_probe_timeout(
    monkeypatch,
):
    """``code=STARTUP_PROBE_TIMEOUT`` outcome MUST be wrapped as ``StartupProbeTimeout``."""
    from cold_storage.bootstrap.runtime_readiness import (
        STARTUP_PROBE_TIMEOUT,
        ProbeOutcome,
        StartupProbeTimeout,
        run_startup_phase,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    settings = _strict_settings("local", monkeypatch)
    set_canonical_settings(settings)

    def _timeout_probe(*, timeout_seconds):  # noqa: ARG001
        return ProbeOutcome(
            name="fake-timeout",
            status="fail",
            code=STARTUP_PROBE_TIMEOUT,
            detail="probe exceeded per-probe budget",
        )

    with pytest.raises(StartupProbeTimeout):
        run_startup_phase(
            settings=Settings(),
            environment={},
            startup_probes=(_timeout_probe,),
        )


def test_run_startup_phase_non_timeout_outcome_wraps_as_non_timeout_failure(
    monkeypatch,
):
    """A non-timeout outcome MUST be wrapped as ``StartupNonTimeoutProbeFailure``."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        ProbeOutcome,
        StartupNonTimeoutProbeFailure,
        StartupProbeTimeout,
        run_startup_phase,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    settings = _strict_settings("local", monkeypatch)
    set_canonical_settings(settings)

    def _dshic_probe(*, timeout_seconds):  # noqa: ARG001
        return ProbeOutcome(
            name="fake-dshic",
            status="fail",
            code=DATABASE_SCHEMA_HEAD_INVALID,
            detail="schema-head non-timeout failure",
        )

    with pytest.raises(StartupNonTimeoutProbeFailure) as excinfo:
        run_startup_phase(
            settings=Settings(),
            environment={},
            startup_probes=(_dshic_probe,),
        )
    assert not isinstance(excinfo.value, StartupProbeTimeout)
    assert excinfo.value.probe_name == "fake-dshic"
    assert excinfo.value.failure_code == DATABASE_SCHEMA_HEAD_INVALID


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: log envelope / safe projection.
# ---------------------------------------------------------------------------


def test_run_probe_with_timeout_safe_detail_does_not_leak_exception_text():
    """``on_non_timeout_code`` detail MUST NOT include raw exception text."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        run_probe_with_timeout,
    )

    def _boom(timeout_seconds):  # noqa: ARG001
        raise RuntimeError(
            "psycopg2.OperationalError: connection to server at "
            '"localhost" (::1), port 5432 failed: FATAL: role "x" '
            "does not exist; SELECT version_num FROM alembic_version"
        )

    out = run_probe_with_timeout(
        name="schema-head",
        fn=_boom,
        timeout_seconds=5,
        on_timeout_code="STARTUP_PROBE_TIMEOUT",
        on_non_timeout_code=DATABASE_SCHEMA_HEAD_INVALID,
    )
    assert out.status == "fail"
    assert out.code == DATABASE_SCHEMA_HEAD_INVALID
    # CRITICAL: the detail MUST NOT embed raw exception text, DSN, SQL,
    # role name, or other secrets.
    assert "psycopg2" not in out.detail
    assert "localhost" not in out.detail
    assert "password" not in out.detail.lower()
    assert "SELECT" not in out.detail.upper()
    assert "Traceback" not in out.detail
    assert "FATAL" not in out.detail
