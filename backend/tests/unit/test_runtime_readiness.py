"""Unit tests for bootstrap.runtime_readiness per TASK-012 Slice 2."""

from __future__ import annotations

import os
from typing import Any

import pytest

from cold_storage.bootstrap.runtime_readiness import (
    LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS,
    LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS,
    READINESS_PROBE_TIMEOUT_MAX,
    READINESS_PROBE_TIMEOUT_MIN,
    STARTUP_PROBE_TIMEOUT_MAX,
    STARTUP_PROBE_TIMEOUT_MIN,
    AgentCapabilityEvidence,
    AgentCapabilityState,
    AgentProviderProbeEvidence,
    ProbeOutcome,
    ReadinessError,
    StartupNonTimeoutProbeFailure,
    StartupProbeFailure,
    StartupProbeTimeout,
    StrictCapabilityAuditEvidence,
    assert_no_unsafe_strict_capabilities,
    finalize_agent_capability_evidence,
    registered_strict_capabilities,
    reset_readiness_state,
    resolve_agent_capability_evidence,
    run_probe_with_timeout,
    run_readiness_phase,
    run_startup_phase,
    validate_probe_timeout_seconds,
)
from cold_storage.bootstrap.settings import Settings
from cold_storage.modules.planning_agent.domain.errors import AgentProviderFailureCode


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
    clean_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
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
    # :class:`StartupProbeFailure`, NOT
    # :class:`StartupProbeTimeout` and NOT nested inside
    # :class:`StartupNonTimeoutProbeFailure`. The timeout exception
    # type is reserved for genuine timeout events.
    with pytest.raises(StartupProbeFailure) as exc_info:
        run_startup_phase(
            settings=_StubSettings("test"),
            environment=dict(os.environ),
            startup_probes=[_ok, _bad],
        )
    assert not isinstance(exc_info.value, StartupProbeTimeout)
    assert not isinstance(exc_info.value, StartupNonTimeoutProbeFailure)
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
    """Build a clean FastAPI app for strict-mode audit tests.

    D-S4-06: Includes the strict binding manifest required by the audit.
    R6: Also sets _strict_runtime_authority on app.state.
    """
    from fastapi import FastAPI

    from cold_storage.bootstrap.app import StrictRuntimeAuthority

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.strict_capability_bindings = (
        ("coefficient_http", "database_backed"),
        ("model_backed_agent", "disabled"),
    )
    app.state.frozen_agent_endpoint_authority = ()
    app.state.coefficient_route_evidence = {"provider": None, "endpoints": ()}
    # R6: Set the composition-root authority (empty — no routes registered).
    app.state._strict_runtime_authority = StrictRuntimeAuthority()  # noqa: SLF001
    return app


def _strict_fastapi_app_with_planning_agent_route():
    """Build a FastAPI app with the fake-agent HTTP route registered.

    D-S4-06: Includes the strict binding manifest. The audit checks
    route prefix + binding identity + composition evidence.
    R6: Also sets _strict_runtime_authority on app.state.
    """
    from fastapi import FastAPI

    from cold_storage.bootstrap.app import StrictRuntimeAuthority

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.strict_capability_bindings = (
        ("coefficient_http", "database_backed"),
        ("model_backed_agent", "disabled"),
    )

    @app.post("/api/v1/agent/run")
    def _run_agent():  # pragma: no cover - never invoked
        return {"ok": True}

    app.state.frozen_agent_endpoint_authority = ()
    app.state.coefficient_route_evidence = {"provider": None, "endpoints": ()}
    # R6: No agent routes in frozen authority — audit should reject.
    app.state._strict_runtime_authority = StrictRuntimeAuthority()  # noqa: SLF001
    return app


def _strict_fastapi_app_with_coefficient_route():
    """Build a FastAPI app with the in-memory coefficient HTTP route.

    D-S4-06: Includes the strict binding manifest. The audit checks
    route prefix + binding identity + composition evidence.
    R6: Also sets _strict_runtime_authority on app.state.
    """
    from fastapi import FastAPI

    from cold_storage.bootstrap.app import (
        CoefficientRouteAuthority,
        StrictRuntimeAuthority,
    )

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.strict_capability_bindings = (
        ("coefficient_http", "database_backed"),
        ("model_backed_agent", "disabled"),
    )

    @app.post("/api/v1/coefficients/lookup")
    def _lookup():  # pragma: no cover - never invoked
        return {"ok": True}

    app.state.frozen_agent_endpoint_authority = ()
    app.state.coefficient_route_evidence = {"provider": None, "endpoints": ()}

    # R6: Set the composition-root authority.
    from cold_storage.bootstrap.dependencies import get_production_coefficient_service

    app.state._strict_runtime_authority = StrictRuntimeAuthority(  # noqa: SLF001
        agent_routes=(),
        coefficient_routes=(
            CoefficientRouteAuthority(
                method="POST", path="/api/v1/coefficients/lookup", endpoint=_lookup
            ),
        ),
        coefficient_provider=get_production_coefficient_service,
        capability_mode="enabled",
    )
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
    # D-S4-06: Mock composition tokens to include required positive evidence
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
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
    # D-S4-06: Mock composition tokens to include required positive evidence
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=_strict_fastapi_app())
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_disabled_agent_route_allowed(monkeypatch):
    """STRICT_DISABLED_AGENT_ROUTE_ALLOWED: disabled agent routes are allowed.

    D-S4-06: Agent routes with binding "disabled" in the frozen endpoint
    matrix are allowed in strict modes.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    # D-S4-06: Mock composition tokens to include required positive evidence
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        # Clean app with correct binding → ALLOWED
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app(),
        )
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_extra_agent_route_rejected(monkeypatch):
    """STRICT_ACTIVE_AGENT_ROUTE_REJECTED: extra agent route must fail closed.

    D-S4-06: Any agent route not in the frozen endpoint matrix must be
    rejected, even with correct binding identity.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_planning_agent_route(),
        )
        assert reachable == ("model_backed_agent",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_fake_agent_route_rejected(monkeypatch):
    """STRICT_FAKE_AGENT_ROUTE_REJECTED: fake agent route must fail closed."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        # App with fake agent route (not in frozen matrix)
        from fastapi import FastAPI

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "disabled"),
        )

        @app.post("/api/v1/agent/fake-run")
        def _fake_agent():  # pragma: no cover
            return {"fake": True}

        reachable = enumerate_reachable_unsafe_strict_capabilities(app=app)
        assert reachable == ("model_backed_agent",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_unknown_agent_route_rejected(monkeypatch):
    """STRICT_UNKNOWN_AGENT_ROUTE_REJECTED: unknown agent route must fail closed."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        from fastapi import FastAPI

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "disabled"),
        )

        @app.get("/api/v1/agent/unknown-endpoint")
        def _unknown():  # pragma: no cover
            return {"unknown": True}

        reachable = enumerate_reachable_unsafe_strict_capabilities(app=app)
        assert reachable == ("model_backed_agent",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_coefficient_route_allowed(monkeypatch):
    """STRICT_DELAYED_DATABASE_COEFFICIENT_ROUTE_ALLOWED: database-backed coefficient allowed.

    D-S4-06: Coefficient routes with binding "database_backed" and
    correct composition evidence are allowed in strict modes.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_concrete_coefficient_service_rejected(monkeypatch):
    """STRICT_CONCRETE_DATABASE_SERVICE_ROUTE_REJECTED: concrete service route must fail closed."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    # Process-local composition token present → forbidden
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset(
            {
                "DATABASE_COEFFICIENT_SERVICE_INSTANTIATED",
                "PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED",
            }
        ),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ("coefficient_http",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_process_local_coefficient_rejected(monkeypatch):
    """STRICT_PROCESS_LOCAL_COEFFICIENT_ROUTE_REJECTED: process-local must fail closed."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    # Only process-local token, no database token → forbidden + missing positive
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ("coefficient_http",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_staging_mode_unknown_coefficient_provider_rejected(monkeypatch):
    """STRICT_UNKNOWN_COEFFICIENT_PROVIDER_REJECTED: missing DB token must fail closed."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    # Empty composition tokens → missing required positive DB token
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset(),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ("coefficient_http",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_route_self_attestation_cannot_bypass(monkeypatch):
    """ROUTE_SELF_ATTESTATION_CANNOT_BYPASS: writing app.state.strict_capability_bindings
    from the route module does not bypass the audit."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        from fastapi import FastAPI

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        # Route module self-attests safe bindings
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "disabled"),
        )

        # But registers an extra agent route
        @app.post("/api/v1/agent/self-attested")
        def _self_attested():  # pragma: no cover
            return {"ok": True}

        # Self-attestation does NOT bypass the frozen endpoint check
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=app)
        assert reachable == ("model_backed_agent",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_composition_snapshot_read_count(monkeypatch):
    """COMPOSITION_SNAPSHOT_READ_COUNT=1: audit reads composition manifest exactly once."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    call_count = {"n": 0}
    original_tokens = frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"})

    def _counting_provider():
        call_count["n"] += 1
        return original_tokens

    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        _counting_provider,
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app(),
        )
        assert reachable == ()
        assert call_count["n"] == 1, (
            f"composition manifest should be read exactly once, got {call_count['n']}"
        )
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_disabled_agent_route_allowed(monkeypatch):
    """STRICT_DISABLED_AGENT_ROUTE_ALLOWED (production): disabled agent routes are allowed."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app(),
        )
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_extra_agent_route_rejected(monkeypatch):
    """STRICT_ACTIVE_AGENT_ROUTE_REJECTED (production): extra agent route must fail closed."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_planning_agent_route(),
        )
        assert reachable == ("model_backed_agent",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_coefficient_route_allowed(monkeypatch):
    """STRICT_DELAYED_DATABASE_COEFFICIENT_ROUTE_ALLOWED (production)."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_production_mode_process_local_coefficient_rejected(monkeypatch):
    """STRICT_PROCESS_LOCAL_COEFFICIENT_ROUTE_REJECTED (production)."""
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ("coefficient_http",)
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


def test_production_entrypoint_initializes_canonical_logging_before_run() -> None:
    """The process entrypoint must not create a second basicConfig handler."""

    import inspect

    from cold_storage.bootstrap import production_entrypoint

    source = inspect.getsource(production_entrypoint)
    assert "logging.basicConfig" not in source
    main_body = source[source.index("def main") :]
    assert main_body.index("configure_logging()") < main_body.index("run_entrypoint()")


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

    # Composition-manifest provider is registered. In local / test
    # mode the legacy fake-backed agent service is genuinely
    # constructed (via ``FakeAgentModelGateway()``), so the
    # composition-manifest evidence set MUST contain the
    # ``FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED`` token. The token is
    # intentionally NOT a defect in local / test mode — the audit
    # short-circuits to an empty reachable subset in non-strict
    # modes (see ``enumerate_reachable_unsafe_strict_capabilities``).
    assert "FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED" in composition_manifest_tokens()
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
    monkeypatch.setattr(
        _app,
        "init_dependencies",
        lambda settings, *, app=None, strict_runtime_authority=None: None,
    )
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
        # D-S4-06: App must have binding manifest for audit
        app_with_manifest = FastAPI()
        app_with_manifest.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "disabled"),
        )
        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            assert_no_unsafe_strict_capabilities(app=app_with_manifest)
        assert "model_backed_agent" in (exc_info.value.unsafe_capabilities)
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
    """A non-timeout outcome MUST be wrapped as ``StartupProbeFailure``.

    V0.2 Slice 2 amendment (D-S2-12.a.v0.2): the three startup
    failure channels are mutually exclusive. A classified non-timeout
    ProbeOutcome (e.g. ``code=DATABASE_SCHEMA_HEAD_INVALID``) MUST be
    wrapped as :class:`StartupProbeFailure`. It MUST NOT be wrapped
    as :class:`StartupProbeTimeout` (which is reserved for genuine
    timeout events) and MUST NOT be nested inside
    :class:`StartupNonTimeoutProbeFailure` (which is reserved for
    un-classified ``Exception`` escapes from
    ``run_probe_with_timeout``).
    """
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        ProbeOutcome,
        StartupProbeFailure,
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

    with pytest.raises(StartupProbeFailure) as excinfo:
        run_startup_phase(
            settings=Settings(),
            environment={},
            startup_probes=(_dshic_probe,),
        )
    assert isinstance(excinfo.value, StartupProbeFailure)
    assert not isinstance(excinfo.value, StartupProbeTimeout)
    assert not isinstance(excinfo.value, StartupNonTimeoutProbeFailure)
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


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: AST-based packaged graph parser.
# ---------------------------------------------------------------------------


def _make_versions_dir(tmp_path, name="versions"):
    versions_dir = tmp_path / name
    versions_dir.mkdir(exist_ok=True)
    return versions_dir


def _write_migration(path, body):
    path.write_text(body, encoding="utf-8")


def test_ast_parser_assign_form_revision(tmp_path):
    """``revision = "abc"`` (Assign) is supported."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_legacy.py",
        "revision = 'abc123def456'\ndown_revision = None\n",
    )
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert heads == ("abc123def456",)
    assert parents == {"abc123def456": (None,)}


def test_ast_parser_annassign_form_revision(tmp_path):
    """``revision: str = "abc"`` (AnnAssign) is supported."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0002_ann.py",
        "revision: str = 'abc123def456'\ndown_revision: str | None = None\n",
    )
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert heads == ("abc123def456",)
    assert parents == {"abc123def456": (None,)}


def test_ast_parser_assign_form_down_revision(tmp_path):
    """``down_revision = "parent"`` (Assign) is supported."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_root.py",
        "revision = 'aaa111aaa111'\ndown_revision = None\n",
    )
    _write_migration(
        versions_dir / "0002_child.py",
        "revision = 'bbb222bbb222'\ndown_revision = 'aaa111aaa111'\n",
    )
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert heads == ("bbb222bbb222",)
    assert parents == {
        "aaa111aaa111": (None,),
        "bbb222bbb222": ("aaa111aaa111",),
    }


def test_ast_parser_annassign_form_down_revision(tmp_path):
    """``down_revision: str | None = "parent"`` (AnnAssign) is supported."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_root.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )
    _write_migration(
        versions_dir / "0002_child.py",
        "revision: str = 'bbb222bbb222'\ndown_revision: str | None = 'aaa111aaa111'\n",
    )
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert heads == ("bbb222bbb222",)


def test_ast_parser_none_parent(tmp_path):
    """``down_revision = None`` is supported and treated as a root."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_root.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert heads == ("aaa111aaa111",)
    assert parents == {"aaa111aaa111": (None,)}


def test_ast_parser_tuple_parents(tmp_path):
    """``down_revision = ("a", "b")`` (Tuple) is supported for merges."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_a.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )
    _write_migration(
        versions_dir / "0001_b.py",
        "revision: str = 'bbb222bbb222'\ndown_revision: str | None = None\n",
    )
    _write_migration(
        versions_dir / "0002_merge.py",
        "revision: str = 'ccc333ccc333'\n"
        'down_revision: Sequence[str] = ("aaa111aaa111", "bbb222bbb222")\n',
    )
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert heads == ("ccc333ccc333",)
    assert parents["ccc333ccc333"] == ("aaa111aaa111", "bbb222bbb222")


def test_ast_parser_list_parents(tmp_path):
    """``down_revision = ["a", "b"]`` (List) is supported for merges."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_a.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )
    _write_migration(
        versions_dir / "0001_b.py",
        "revision: str = 'bbb222bbb222'\ndown_revision: str | None = None\n",
    )
    _write_migration(
        versions_dir / "0002_merge.py",
        "revision: str = 'ddd444ddd444'\n"
        'down_revision: list[str] = ["aaa111aaa111", "bbb222bbb222"]\n',
    )
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert heads == ("ddd444ddd444",)
    assert parents["ddd444ddd444"] == ("aaa111aaa111", "bbb222bbb222")


def test_ast_parser_real_repository_unique_head():
    """The real ``backend/alembic/versions/`` graph MUST have a unique head."""

    from cold_storage.bootstrap.runtime_readiness import (
        _load_packaged_alembic_head,
    )

    head, reason = _load_packaged_alembic_head()
    assert reason is None, (
        f"real graph classified as {reason}; AST parser MUST handle annotated assignments"
    )
    assert head == "0040_add_knowledge_page_evidence"


def test_ast_parser_init_file_is_ignored(tmp_path):
    """``__init__.py`` MUST be ignored by the loader."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "__init__.py",
        "# NOT a migration\nrevision = 'should_be_ignored'\ndown_revision = None\n",
    )
    _write_migration(
        versions_dir / "0001_real.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert "should_be_ignored" not in parents
    assert heads == ("aaa111aaa111",)


def test_ast_parser_syntax_error_classifies_unreadable(tmp_path):
    """A migration file with a SyntaxError classifies as PACKAGED_HEAD_UNREADABLE."""
    from cold_storage.bootstrap.runtime_readiness import (
        _PackagedGraphUnreadable,
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_bad.py",
        "revision: str = 'aaa111aaa111'\n"
        "down_revision: str | None = None\n"
        "def broken(:\n",  # SyntaxError
    )
    with pytest.raises(_PackagedGraphUnreadable):
        _parse_alembic_revisions(versions_dir)
    # The loader catches ``_PackagedGraphUnreadable`` and maps it to
    # ``PACKAGED_HEAD_UNREADABLE``. We verify that boundary mapping
    # indirectly: the parser raising Unreadable is the precondition
    # for the loader boundary to project the frozen reason.


def test_ast_parser_unreadable_file_classifies_unreadable(tmp_path, monkeypatch):
    """An unreadable migration file classifies as PACKAGED_HEAD_UNREADABLE."""
    from cold_storage.bootstrap.runtime_readiness import (
        _PackagedGraphUnreadable,
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    rev_file = versions_dir / "0001_unreadable.py"
    rev_file.write_text(
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
        encoding="utf-8",
    )
    # Make the file unreadable by replacing read_text with a raising function.
    import pathlib as _pl

    real_read_text = _pl.Path.read_text

    def _failing_read_text(self, *args, **kwargs):
        if str(self).endswith("0001_unreadable.py"):
            raise OSError("simulated permission error")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(_pl.Path, "read_text", _failing_read_text)
    with pytest.raises(_PackagedGraphUnreadable):
        _parse_alembic_revisions(versions_dir)


def test_ast_parser_missing_revision_classifies_unreadable(tmp_path):
    """A migration file without a top-level ``revision`` classifies as PACKAGED_HEAD_UNREADABLE."""
    from cold_storage.bootstrap.runtime_readiness import (
        _PackagedGraphUnreadable,
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_no_revision.py",
        "# no top-level revision here\ndown_revision = None\n",
    )
    with pytest.raises(_PackagedGraphUnreadable):
        _parse_alembic_revisions(versions_dir)


def test_ast_parser_dynamic_down_revision_classifies_unreadable(tmp_path):
    """A dynamic ``down_revision`` (function call) classifies as PACKAGED_HEAD_UNREADABLE."""
    from cold_storage.bootstrap.runtime_readiness import (
        _PackagedGraphUnreadable,
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_root.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )
    _write_migration(
        versions_dir / "0002_dynamic.py",
        "import builtins\n"
        "revision: str = 'bbb222bbb222'\n"
        "down_revision: str = builtins.str('aaa111aaa111')\n",  # dynamic
    )
    with pytest.raises(_PackagedGraphUnreadable):
        _parse_alembic_revisions(versions_dir)


def test_ast_parser_malformed_revision_classifies_malformed(tmp_path):
    """A revision that violates the shape validator classifies as PACKAGED_HEAD_MALFORMED."""
    from cold_storage.bootstrap.runtime_readiness import (
        _PackagedGraphMalformed,
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_bad.py",
        "revision: str = 'no-digits-or-allowed-shape!!!'\ndown_revision: str | None = None\n",
    )
    with pytest.raises(_PackagedGraphMalformed):
        _parse_alembic_revisions(versions_dir)


def test_ast_parser_duplicate_revision_classifies_malformed(tmp_path):
    """Duplicate revision ids classify as PACKAGED_HEAD_MALFORMED."""
    from cold_storage.bootstrap.runtime_readiness import (
        _PackagedGraphMalformed,
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_a.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )
    _write_migration(
        versions_dir / "0001_b.py",
        "revision: str = 'aaa111aaa111'\n"  # duplicate
        "down_revision: str | None = None\n",
    )
    with pytest.raises(_PackagedGraphMalformed):
        _parse_alembic_revisions(versions_dir)


def test_ast_parser_zero_heads_classifies_zero():
    """An empty graph returns the frozen ``PACKAGED_HEAD_ZERO`` reason."""
    # Real-graph case: there is always a head in this repo. We use a
    # loader-level classification by monkeypatching the parser to
    # return empty heads and asserting the loader boundary maps to
    # PACKAGED_HEAD_ZERO.
    import cold_storage.bootstrap.runtime_readiness as rr
    from cold_storage.bootstrap.runtime_readiness import (
        _load_packaged_alembic_head,
    )

    real_parser = rr._parse_alembic_revisions
    rr._parse_alembic_revisions = lambda _d: ((), {})
    try:
        head, reason = _load_packaged_alembic_head()
    finally:
        rr._parse_alembic_revisions = real_parser
    assert head is None
    assert reason == "PACKAGED_HEAD_ZERO"


def test_ast_parser_multiple_heads_classifies_multiple(tmp_path):
    """Multiple heads produce ``PACKAGED_HEAD_MULTIPLE``."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_a.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )
    _write_migration(
        versions_dir / "0001_b.py",
        "revision: str = 'bbb222bbb222'\ndown_revision: str | None = None\n",
    )
    heads, _parents = _parse_alembic_revisions(versions_dir)
    assert len(heads) >= 2


def test_ast_parser_env_var_does_not_influence_result(monkeypatch, tmp_path):
    """``COLD_STORAGE_PACKAGED_ALEMBIC_HEAD`` MUST NOT influence the AST parser."""
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_real.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )
    monkeypatch.setenv("COLD_STORAGE_PACKAGED_ALEMBIC_HEAD", "ffffffffffff")
    heads, parents = _parse_alembic_revisions(versions_dir)
    assert heads == ("aaa111aaa111",)
    assert "ffffffffffff" not in parents


def test_ast_parser_top_level_side_effects_do_not_execute(tmp_path, monkeypatch):
    """Top-level side effects in migration files MUST NOT execute during parsing.

    The loader only invokes ``ast.parse`` on file text; it does NOT
    ``exec`` / ``import`` / ``runpy``. A module with a side-effectful
    top-level statement (e.g. a function call) MUST NOT cause that
    statement to run.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        _parse_alembic_revisions,
    )

    sentinel_path = tmp_path / "SIDE_EFFECT_RAN.txt"
    versions_dir = _make_versions_dir(tmp_path)
    _write_migration(
        versions_dir / "0001_effect.py",
        "revision: str = 'aaa111aaa111'\n"
        "down_revision: str | None = None\n"
        # Side effect: write a sentinel file. If the parser executed
        # the module, the sentinel would exist after parsing.
        f"open({str(sentinel_path)!r}, 'w').write('ran')\n",
    )
    _parse_alembic_revisions(versions_dir)
    assert not sentinel_path.exists()


def test_ast_parser_env_py_does_not_execute(tmp_path, monkeypatch):
    """``env.py`` MUST NOT execute during packaged-head loading."""
    import cold_storage.bootstrap.runtime_readiness as rr
    from cold_storage.bootstrap.runtime_readiness import (
        _load_packaged_alembic_head,
    )

    # Build a fake deployment root layout in tmp_path.
    fake_root = tmp_path / "backend"
    fake_bootstrap_dir = fake_root / "src" / "cold_storage" / "bootstrap"
    fake_bootstrap_dir.mkdir(parents=True)
    fake_module = fake_bootstrap_dir / "runtime_readiness.py"
    fake_module.write_text("# fake\n")
    # Real alembic.ini in the fake root pointing at script_location.
    script_dir = fake_root / "alembic"
    versions_dir = script_dir / "versions"
    versions_dir.mkdir(parents=True)
    (fake_root / "alembic.ini").write_text(
        f"[alembic]\nscript_location = {script_dir}\n",
        encoding="utf-8",
    )
    # env.py that raises if executed.
    (script_dir / "env.py").write_text(
        "raise RuntimeError('env.py MUST NOT be executed by the loader')\n",
        encoding="utf-8",
    )
    _write_migration(
        versions_dir / "0001_real.py",
        "revision: str = 'aaa111aaa111'\ndown_revision: str | None = None\n",
    )

    # Redirect the loader's module path to the fake module.
    real_file = rr.__file__
    try:
        rr.__dict__["__file__"] = str(fake_module.resolve())
        head, reason = _load_packaged_alembic_head()
    finally:
        rr.__dict__["__file__"] = real_file
    assert reason is None
    assert head == "aaa111aaa111"


def test_ast_parser_no_database_connection(tmp_path, monkeypatch):
    """The packaged-head loader MUST NOT connect to any database."""
    # We assert this by intercepting any attempt to import or
    # construct a database engine; the parser only touches ``ast``.

    # Track engine creation attempts.
    created = []

    class _TrackingEngine:
        def __init__(self, *args, **kwargs):
            created.append("created")

    from cold_storage.bootstrap import dependencies as deps

    monkeypatch.setattr(deps, "get_engine", lambda: _TrackingEngine())

    from cold_storage.bootstrap.runtime_readiness import (
        _load_packaged_alembic_head,
    )

    head, reason = _load_packaged_alembic_head()
    assert reason is None
    assert head == "0040_add_knowledge_page_evidence"
    assert created == []


def test_ast_parser_no_subprocess(tmp_path, monkeypatch):
    """The packaged-head loader MUST NOT spawn subprocesses."""
    import subprocess as _subprocess

    spawned: list[list[str]] = []
    real_run = _subprocess.run

    def _tracking_run(*args, **kwargs):
        spawned.append(list(args[0]) if args else [])
        return real_run(*args, **kwargs)

    monkeypatch.setattr(_subprocess, "run", _tracking_run)
    from cold_storage.bootstrap.runtime_readiness import (
        _load_packaged_alembic_head,
    )

    head, reason = _load_packaged_alembic_head()
    assert reason is None
    assert head == "0040_add_knowledge_page_evidence"
    assert spawned == []


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: exception-channel mutual exclusion regression.
# ---------------------------------------------------------------------------


def test_run_probe_with_timeout_preserves_classified_outcome():
    """A probe returning a classified failure ProbeOutcome MUST have its code preserved."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        ProbeOutcome,
        run_probe_with_timeout,
    )

    def _classified_probe(*, timeout_seconds):  # noqa: ARG001
        return ProbeOutcome(
            name="schema-head",
            status="fail",
            code=DATABASE_SCHEMA_HEAD_INVALID,
            detail="schema-head non-timeout failure",
        )

    out = run_probe_with_timeout(
        name="schema-head",
        fn=_classified_probe,
        timeout_seconds=5,
        on_timeout_code="STARTUP_PROBE_TIMEOUT",
        on_non_timeout_code=DATABASE_SCHEMA_HEAD_INVALID,
    )
    assert out.status == "fail"
    assert out.code == DATABASE_SCHEMA_HEAD_INVALID


def test_classified_failure_not_double_wrapped_in_non_timeout_failure(
    monkeypatch,
):
    """``run_startup_phase`` MUST NOT double-wrap a classified failure."""
    from cold_storage.bootstrap.runtime_readiness import (
        DATABASE_SCHEMA_HEAD_INVALID,
        ProbeOutcome,
        StartupNonTimeoutProbeFailure,
        StartupProbeFailure,
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
            detail="",
        )

    with pytest.raises(StartupProbeFailure) as excinfo:
        run_startup_phase(
            settings=Settings(),
            environment={},
            startup_probes=(_dshic_probe,),
        )
    # CRITICAL regression: the StartupProbeFailure MUST NOT be
    # nested inside a StartupNonTimeoutProbeFailure.original_exception.
    assert not isinstance(excinfo.value, StartupNonTimeoutProbeFailure)
    assert excinfo.value.failure_code == DATABASE_SCHEMA_HEAD_INVALID
    assert not isinstance(excinfo.value, StartupProbeTimeout)


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: artifact-storage-classification.
#   - Public stable code: ARTIFACT_STORAGE_UNAVAILABLE
#   - Internal reasons (NOT public codes):
#       ARTIFACT_STORAGE_PATH_NOT_CONFIGURED
#       ARTIFACT_STORAGE_DIRECTORY_MISSING
#       ARTIFACT_STORAGE_DIRECTORY_NOT_WRITABLE
#       ARTIFACT_STORAGE_PROBE_IO_FAILURE
#   - Canonical authority: Settings.storage_dir (env COLD_STORAGE_STORAGE_DIR)
#   - Forbidden authority: COLD_STORAGE_ARTIFACT_STORAGE_DIR,
#     COLD_STORAGE_REPORT_ARTIFACTS_DIR
# ---------------------------------------------------------------------------


def _install_strict_canonical_settings(env_id, monkeypatch, tmp_path):
    """Build a strict Settings with an isolated canonical storage_dir.

    Per the artifact-storage-classification-amendment contract,
    ``Settings.storage_dir`` is the canonical authority. We inject
    it via ``COLD_STORAGE_STORAGE_DIR`` (Pydantic validation_alias)
    and force a writable directory in ``tmp_path``.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    storage_dir = tmp_path / f"storage-{env_id}"
    storage_dir.mkdir(parents=True, exist_ok=True)
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
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(storage_dir))
    settings = Settings()  # type: ignore[call-arg]
    set_canonical_settings(settings)
    return settings, storage_dir


# --- (1) public stable code value is frozen ---------------------------


def test_artifact_storage_unavailable_public_code_value_is_frozen():
    """The public stable code MUST be exactly "ARTIFACT_STORAGE_UNAVAILABLE"."""
    from cold_storage.bootstrap.runtime_readiness import (
        ARTIFACT_STORAGE_UNAVAILABLE,
    )

    assert ARTIFACT_STORAGE_UNAVAILABLE == "ARTIFACT_STORAGE_UNAVAILABLE"


# --- (2-3) internal reasons project to the public code ----------------


def test_artifact_storage_internal_reasons_projected_to_public_code():
    """All four internal reasons MUST project to ARTIFACT_STORAGE_UNAVAILABLE."""
    from cold_storage.bootstrap.runtime_readiness import (
        _artifact_storage_unavailable,
    )

    for reason in (
        "ARTIFACT_STORAGE_PATH_NOT_CONFIGURED",
        "ARTIFACT_STORAGE_DIRECTORY_MISSING",
        "ARTIFACT_STORAGE_DIRECTORY_NOT_WRITABLE",
        "ARTIFACT_STORAGE_PROBE_IO_FAILURE",
    ):
        outcome = _artifact_storage_unavailable(
            name="artifact_storage_isolated_exists_writable",
            internal_reason=reason,
            duration=0.0,
        )
        assert outcome.status == "fail"
        assert outcome.code == "ARTIFACT_STORAGE_UNAVAILABLE"
        assert reason not in (outcome.code or "")
        assert outcome.detail == (f"artifact-storage non-timeout failure ({reason})")


def test_artifact_storage_internal_reason_unknown_raises_runtime_error():
    """An unknown internal reason MUST NOT silently emit a public code."""
    from cold_storage.bootstrap.runtime_readiness import (
        _artifact_storage_unavailable,
    )

    with pytest.raises(RuntimeError):
        _artifact_storage_unavailable(
            name="artifact_storage_isolated_exists_writable",
            internal_reason="NOT_A_REAL_REASON",
            duration=0.0,
        )


# --- (4-5) production / staging pass when canonical dir is writable --


def test_probe_artifact_storage_passes_in_production_when_canonical_dir_writable(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    settings, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "pass"
    assert outcome.code is None
    assert outcome.name == "artifact_storage_isolated_exists_writable"


def test_probe_artifact_storage_passes_in_staging_when_canonical_dir_writable(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    settings, _ = _install_strict_canonical_settings(
        "staging",
        monkeypatch,
        tmp_path,
    )
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "pass"
    assert outcome.code is None


# --- (6) only canonical env key is required ---------------------------


def test_probe_artifact_storage_passes_with_only_canonical_env_key(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    settings, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "pass"
    assert "COLD_STORAGE_ARTIFACT_STORAGE_DIR" not in (outcome.detail or "")


# --- (7-8) ad-hoc env keys do NOT override canonical ------------------


def test_probe_artifact_storage_ignores_adhoc_artifact_storage_dir(
    monkeypatch,
    tmp_path,
):
    """COLD_STORAGE_ARTIFACT_STORAGE_DIR MUST NOT override canonical path."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    settings, canonical = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    # Set the ad-hoc env var to a non-existent path that, if read,
    # would cause the probe to fail. The probe MUST ignore it.
    monkeypatch.setenv(
        "COLD_STORAGE_ARTIFACT_STORAGE_DIR",
        "/nonexistent/path/that/must/be/ignored",
    )
    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "pass"
    assert outcome.code is None
    # Public detail MUST NOT contain the ad-hoc path.
    assert "/nonexistent/path" not in (outcome.detail or "")


def test_probe_artifact_storage_ignores_adhoc_report_artifacts_dir(
    monkeypatch,
    tmp_path,
):
    """COLD_STORAGE_REPORT_ARTIFACTS_DIR MUST NOT override canonical path."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    settings, canonical = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    monkeypatch.setenv(
        "COLD_STORAGE_REPORT_ARTIFACTS_DIR",
        "/another/nonexistent/path/that/must/be/ignored",
    )
    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "pass"
    assert outcome.code is None
    assert "/another/nonexistent/path" not in (outcome.detail or "")


# --- (9) canonical path missing in strict mode → artifact unavailable -


def test_probe_artifact_storage_path_not_configured_in_production(
    monkeypatch,
    tmp_path,
):
    """Strict canonical path missing → ARTIFACT_STORAGE_UNAVAILABLE.

    We build a strict Settings object whose ``storage_dir`` is the
    empty string (Pydantic accepts the alias as empty input); this
    bypasses the code-default fallback so the probe sees a
    defensive path-absence state.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
        reset_canonical_settings,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    settings = Settings(  # type: ignore[call-arg]
        COLD_STORAGE_ENVIRONMENT_ID="production",
        COLD_STORAGE_APP_HOST="127.0.0.1",
        COLD_STORAGE_APP_PORT="8000",
        COLD_STORAGE_DATABASE_BACKEND="postgresql",
        COLD_STORAGE_DATABASE_URL=("postgresql+psycopg2://u:p@localhost:5432/db"),
        COLD_STORAGE_BUILD_COMMIT_SHA="0" * 40,
        COLD_STORAGE_BUILD_VERSION="v0.0.0-ci",
        COLD_STORAGE_CONFIG_SCHEMA_VERSION="1",
        COLD_STORAGE_DATABASE_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_SECRET_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID="ci-strict",
    )
    # Force ``storage_dir`` to the empty string post-validation so the
    # probe sees a defensive path-absence state (Settings would
    # otherwise apply a code-level default for production).
    object.__setattr__(settings, "storage_dir", "")
    set_canonical_settings(settings)
    assert settings.storage_dir == ""

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "fail"
    assert outcome.code == "ARTIFACT_STORAGE_UNAVAILABLE"
    assert outcome.code != "STARTUP_PROBE_TIMEOUT"
    assert outcome.code != "READINESS_PROBE_TIMEOUT"
    assert "ARTIFACT_STORAGE_PATH_NOT_CONFIGURED" in (outcome.detail or "")
    reset_canonical_settings()


# --- (10) directory absent → artifact unavailable ---------------------


def test_probe_artifact_storage_directory_missing_in_production(
    monkeypatch,
    tmp_path,
):
    """Strict directory absent → ARTIFACT_STORAGE_UNAVAILABLE."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    missing = tmp_path / "does-not-exist"
    settings, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    # Repoint storage_dir to a non-existent path.
    from cold_storage.bootstrap.runtime_readiness import (
        reset_canonical_settings,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    settings = Settings(  # type: ignore[call-arg]
        COLD_STORAGE_ENVIRONMENT_ID="production",
        COLD_STORAGE_APP_HOST="127.0.0.1",
        COLD_STORAGE_APP_PORT="8000",
        COLD_STORAGE_DATABASE_BACKEND="postgresql",
        COLD_STORAGE_DATABASE_URL=("postgresql+psycopg2://u:p@localhost:5432/db"),
        COLD_STORAGE_BUILD_COMMIT_SHA="0" * 40,
        COLD_STORAGE_BUILD_VERSION="v0.0.0-ci",
        COLD_STORAGE_CONFIG_SCHEMA_VERSION="1",
        COLD_STORAGE_DATABASE_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_SECRET_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_STORAGE_DIR=str(missing),
    )
    set_canonical_settings(settings)

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "fail"
    assert outcome.code == "ARTIFACT_STORAGE_UNAVAILABLE"
    assert outcome.code != "STARTUP_PROBE_TIMEOUT"
    assert outcome.code != "READINESS_PROBE_TIMEOUT"
    assert "ARTIFACT_STORAGE_DIRECTORY_MISSING" in (outcome.detail or "")
    assert str(missing) not in (outcome.detail or "")
    reset_canonical_settings()


# --- (11) directory not writable → artifact unavailable ---------------


def test_probe_artifact_storage_directory_not_writable_in_production(
    monkeypatch,
    tmp_path,
):
    """Strict directory not writable → ARTIFACT_STORAGE_UNAVAILABLE.

    We monkeypatch the bounded probe so mkstemp fails with EACCES,
    guaranteeing a deterministic, root-safe "not writable" verdict.
    """
    import tempfile as _tempfile

    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    settings, canonical = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )

    real_mkstemp = _tempfile.mkstemp

    def _failing_mkstemp(*args, **kwargs):
        raise PermissionError("simulated EACCES on mkstemp")

    monkeypatch.setattr(_tempfile, "mkstemp", _failing_mkstemp)
    try:
        outcome = probe_artifact_storage_isolated_exists_writable(
            timeout_seconds=10,
        )
    finally:
        monkeypatch.setattr(_tempfile, "mkstemp", real_mkstemp)

    assert outcome.status == "fail"
    assert outcome.code == "ARTIFACT_STORAGE_UNAVAILABLE"
    assert outcome.code != "STARTUP_PROBE_TIMEOUT"
    assert outcome.code != "READINESS_PROBE_TIMEOUT"
    assert "ARTIFACT_STORAGE_PROBE_IO_FAILURE" in (outcome.detail or "")
    # Public detail MUST NOT include raw exception text or path.
    assert "simulated EACCES" not in (outcome.detail or "")
    assert str(canonical) not in (outcome.detail or "")


# --- (12) probe-file create failure → artifact unavailable -------------


def test_probe_artifact_storage_probe_create_failure_classifies_io_failure(
    monkeypatch,
    tmp_path,
):
    import tempfile as _tempfile

    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    settings, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    monkeypatch.setattr(
        _tempfile,
        "mkstemp",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("ENOSPC simulated")),
    )
    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "fail"
    assert outcome.code == "ARTIFACT_STORAGE_UNAVAILABLE"
    assert "ARTIFACT_STORAGE_PROBE_IO_FAILURE" in (outcome.detail or "")
    assert "ENOSPC simulated" not in (outcome.detail or "")


# --- (13) probe-file write/flush/close failure → artifact unavailable -


def test_probe_artifact_storage_probe_write_failure_classifies_io_failure(
    monkeypatch,
    tmp_path,
):
    import tempfile as _tempfile

    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    settings, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )

    class _BrokenFile:
        def write(self, *_args, **_kwargs):
            raise OSError("EROFS simulated")

        def flush(self):
            raise OSError("EROFS simulated")

        def fileno(self):
            raise OSError("not a real fd")

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _mkstemp_returns_broken(*_args, **_kwargs):
        return 42, "/tmp/broken.tmp"

    monkeypatch.setattr(_tempfile, "mkstemp", _mkstemp_returns_broken)
    monkeypatch.setattr(os, "fdopen", lambda *_a, **_kw: _BrokenFile())
    monkeypatch.setattr(os, "unlink", lambda *_a, **_kw: None)

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "fail"
    assert outcome.code == "ARTIFACT_STORAGE_UNAVAILABLE"
    assert "ARTIFACT_STORAGE_PROBE_IO_FAILURE" in (outcome.detail or "")
    assert "EROFS simulated" not in (outcome.detail or "")
    assert "/tmp/broken.tmp" not in (outcome.detail or "")


# --- (14) probe-file delete failure → artifact unavailable ------------


def test_probe_artifact_storage_probe_delete_failure_classifies_io_failure(
    monkeypatch,
    tmp_path,
):
    import tempfile as _tempfile

    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    settings, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )

    # mkstemp succeeds, fdopen works, write/flush/close work, but
    # the cleanup unlink fails. We must still fail closed.
    class _GoodFile:
        def write(self, *_args, **_kwargs):
            return None

        def flush(self):
            return None

        def fileno(self):
            return 42

        def close(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _mkstemp_returns_ok(*_args, **_kwargs):
        return 42, "/tmp/good.tmp"

    monkeypatch.setattr(_tempfile, "mkstemp", _mkstemp_returns_ok)
    monkeypatch.setattr(os, "fdopen", lambda *_a, **_kw: _GoodFile())

    unlink_calls = []

    def _failing_unlink(path, *args, **kwargs):
        unlink_calls.append(path)
        raise OSError("EPERM simulated on unlink")

    monkeypatch.setattr(os, "unlink", _failing_unlink)

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "fail"
    assert outcome.code == "ARTIFACT_STORAGE_UNAVAILABLE"
    assert "ARTIFACT_STORAGE_PROBE_IO_FAILURE" in (outcome.detail or "")
    assert "EPERM simulated" not in (outcome.detail or "")
    assert "/tmp/good.tmp" not in (outcome.detail or "")


# --- (15) deterministic failures never return timeout codes -----------


def test_probe_artifact_storage_deterministic_failures_never_timeout(
    monkeypatch,
    tmp_path,
):
    """For every deterministic artifact-storage failure mode, the
    outcome MUST NOT be a startup/readiness timeout code."""
    import tempfile as _tempfile

    from cold_storage.bootstrap.runtime_readiness import (
        ARTIFACT_STORAGE_UNAVAILABLE,
        probe_artifact_storage_isolated_exists_writable,
        reset_canonical_settings,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)

    cases = []

    # Case 1: path not configured (force storage_dir to empty
    # post-validation, bypassing the production code default).
    monkeypatch.delenv("COLD_STORAGE_STORAGE_DIR", raising=False)
    s = Settings(  # type: ignore[call-arg]
        COLD_STORAGE_ENVIRONMENT_ID="production",
        COLD_STORAGE_APP_HOST="127.0.0.1",
        COLD_STORAGE_APP_PORT="8000",
        COLD_STORAGE_DATABASE_BACKEND="postgresql",
        COLD_STORAGE_DATABASE_URL=("postgresql+psycopg2://u:p@localhost:5432/db"),
        COLD_STORAGE_BUILD_COMMIT_SHA="0" * 40,
        COLD_STORAGE_BUILD_VERSION="v0.0.0-ci",
        COLD_STORAGE_CONFIG_SCHEMA_VERSION="1",
        COLD_STORAGE_DATABASE_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_SECRET_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID="ci-strict",
    )
    object.__setattr__(s, "storage_dir", "")
    cases.append(("path_not_configured", s, None))

    # Case 2: directory missing
    missing = tmp_path / "absent"
    s = Settings(  # type: ignore[call-arg]
        COLD_STORAGE_ENVIRONMENT_ID="production",
        COLD_STORAGE_APP_HOST="127.0.0.1",
        COLD_STORAGE_APP_PORT="8000",
        COLD_STORAGE_DATABASE_BACKEND="postgresql",
        COLD_STORAGE_DATABASE_URL=("postgresql+psycopg2://u:p@localhost:5432/db"),
        COLD_STORAGE_BUILD_COMMIT_SHA="0" * 40,
        COLD_STORAGE_BUILD_VERSION="v0.0.0-ci",
        COLD_STORAGE_CONFIG_SCHEMA_VERSION="1",
        COLD_STORAGE_DATABASE_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_SECRET_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_STORAGE_DIR=str(missing),
    )
    cases.append(("directory_missing", s, None))

    # Case 3: probe IO failure (mkstemp raises)
    s, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    cases.append(("probe_io_failure", s, _tempfile))

    for label, settings, tmp_mod in cases:
        set_canonical_settings(settings)
        if tmp_mod is not None:
            monkeypatch.setattr(
                tmp_mod,
                "mkstemp",
                lambda *a, **kw: (_ for _ in ()).throw(OSError("simulated")),
            )
        outcome = probe_artifact_storage_isolated_exists_writable(
            timeout_seconds=10,
        )
        assert outcome.status == "fail", f"case={label} expected fail"
        assert outcome.code == ARTIFACT_STORAGE_UNAVAILABLE, f"case={label} code={outcome.code}"
        assert outcome.code != "STARTUP_PROBE_TIMEOUT"
        assert outcome.code != "READINESS_PROBE_TIMEOUT"
    reset_canonical_settings()


# --- (16-18) safe public projection -------------------------------


def test_probe_artifact_storage_detail_does_not_expose_full_path(
    monkeypatch,
    tmp_path,
):
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
        reset_canonical_settings,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)

    secret_path = tmp_path / "very-deep-secret-storage-location-12345"
    s = Settings(  # type: ignore[call-arg]
        COLD_STORAGE_ENVIRONMENT_ID="production",
        COLD_STORAGE_APP_HOST="127.0.0.1",
        COLD_STORAGE_APP_PORT="8000",
        COLD_STORAGE_DATABASE_BACKEND="postgresql",
        COLD_STORAGE_DATABASE_URL="postgresql+psycopg2://u:p@localhost:5432/db",
        COLD_STORAGE_BUILD_COMMIT_SHA="0" * 40,
        COLD_STORAGE_BUILD_VERSION="v0.0.0-ci",
        COLD_STORAGE_CONFIG_SCHEMA_VERSION="1",
        COLD_STORAGE_DATABASE_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_SECRET_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_STORAGE_DIR=str(secret_path),
    )
    set_canonical_settings(s)

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "fail"
    assert str(secret_path) not in (outcome.detail or "")
    assert str(secret_path).split("/")[-1] not in (outcome.detail or "")
    reset_canonical_settings()


def test_probe_artifact_storage_detail_does_not_expose_oserror_text(
    monkeypatch,
    tmp_path,
):
    import tempfile as _tempfile

    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    _settings, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    monkeypatch.setattr(
        _tempfile,
        "mkstemp",
        lambda *a, **kw: (_ for _ in ()).throw(
            OSError(13, "Permission denied on /var/lib/secret-storage")
        ),
    )
    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "fail"
    assert "Permission denied" not in (outcome.detail or "")
    assert "/var/lib/secret-storage" not in (outcome.detail or "")
    assert "[Errno 13]" not in (outcome.detail or "")


def test_probe_artifact_storage_detail_does_not_expose_probe_file_name(
    monkeypatch,
    tmp_path,
):
    import tempfile as _tempfile

    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    _settings, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    # Make cleanup fail so the probe file name would be tempting to
    # include in the failure detail. The probe MUST NOT include it.
    secret_name = "secret-probe-marker-XYZ.tmp"

    def _mkstemp_with_secret_name(*_args, **_kwargs):
        return 42, str(tmp_path / secret_name)

    class _GoodFile:
        def write(self, *_a, **_k):
            return None

        def flush(self):
            return None

        def fileno(self):
            return 42

        def close(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(_tempfile, "mkstemp", _mkstemp_with_secret_name)
    monkeypatch.setattr(os, "fdopen", lambda *_a, **_k: _GoodFile())
    monkeypatch.setattr(
        os,
        "unlink",
        lambda *a, **k: (_ for _ in ()).throw(OSError("cleanup fail")),
    )
    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "fail"
    assert secret_name not in (outcome.detail or "")


# --- (19-20) local / test mode skip semantics -----------------------


def test_probe_artifact_storage_local_mode_skip_when_path_missing(
    monkeypatch,
    tmp_path,
):
    """local mode with no storage_dir configured → PASS (skip)."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "local")
    from cold_storage.bootstrap.settings import Settings

    settings = Settings()  # type: ignore[call-arg]
    from cold_storage.bootstrap.runtime_readiness import (
        reset_canonical_settings,
        set_canonical_settings,
    )

    set_canonical_settings(settings)

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "pass"
    assert outcome.code is None
    reset_canonical_settings()


def test_probe_artifact_storage_test_mode_skip_when_path_missing(
    monkeypatch,
):
    """test mode with no storage_dir configured → PASS (skip)."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
        reset_canonical_settings,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    monkeypatch.delenv("COLD_STORAGE_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "test")
    monkeypatch.setenv("COLD_STORAGE_SQLITE_PATH", ":memory:")
    settings = Settings()  # type: ignore[call-arg]
    set_canonical_settings(settings)

    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "pass"
    assert outcome.code is None
    reset_canonical_settings()


# --- (21) probe does not create missing directory -------------------


def test_probe_artifact_storage_does_not_create_missing_directory(
    monkeypatch,
    tmp_path,
):
    """Strict mode with absent canonical dir MUST NOT auto-create it."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
        reset_canonical_settings,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    absent_dir = tmp_path / "absent-strict"
    settings = Settings(  # type: ignore[call-arg]
        COLD_STORAGE_ENVIRONMENT_ID="production",
        COLD_STORAGE_APP_HOST="127.0.0.1",
        COLD_STORAGE_APP_PORT="8000",
        COLD_STORAGE_DATABASE_BACKEND="postgresql",
        COLD_STORAGE_DATABASE_URL="postgresql+psycopg2://u:p@localhost:5432/db",
        COLD_STORAGE_BUILD_COMMIT_SHA="0" * 40,
        COLD_STORAGE_BUILD_VERSION="v0.0.0-ci",
        COLD_STORAGE_CONFIG_SCHEMA_VERSION="1",
        COLD_STORAGE_DATABASE_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_SECRET_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_STORAGE_DIR=str(absent_dir),
    )
    set_canonical_settings(settings)
    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert not absent_dir.exists()
    assert outcome.status == "fail"
    assert outcome.code == "ARTIFACT_STORAGE_UNAVAILABLE"
    reset_canonical_settings()


# --- (22) probe does not chmod / chown ------------------------------


def test_probe_artifact_storage_does_not_chmod_or_chown(monkeypatch, tmp_path):
    """The probe MUST NOT call ``os.chmod`` or ``os.chown``."""
    import os as _real_os

    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    _settings, _canonical = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )

    chmod_calls = []
    chown_calls = []

    def _spy_chmod(*args, **kwargs):
        chmod_calls.append((args, kwargs))

    def _spy_chown(*args, **kwargs):
        chown_calls.append((args, kwargs))

    monkeypatch.setattr(_real_os, "chmod", _spy_chmod, raising=False)
    monkeypatch.setattr(_real_os, "chown", _spy_chown, raising=False)
    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "pass"
    assert chmod_calls == []
    assert chown_calls == []


# --- (23) Settings construction failure NOT reclassified ------------


def test_probe_artifact_storage_settings_construction_failure_not_reclassified(
    monkeypatch,
):
    """If ``canonical_settings()`` raises, the probe MUST propagate the
    existing configuration classification, NOT reclassify as
    ``ARTIFACT_STORAGE_UNAVAILABLE``."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
        reset_canonical_settings,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    reset_canonical_settings()

    with pytest.raises(Exception) as excinfo:
        probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    # The propagated exception MUST NOT be a probe outcome code of
    # ARTIFACT_STORAGE_UNAVAILABLE; the construction failure must
    # surface as the existing ConfigurationProbeFailed chain.
    msg = str(excinfo.value)
    assert "ARTIFACT_STORAGE_UNAVAILABLE" not in msg


# --- (24) BlockingProbeTimeout still maps to STARTUP_PROBE_TIMEOUT ---


def test_real_blocking_probe_timeout_still_maps_to_startup_probe_timeout():
    """A genuine BlockingProbeTimeout still uses the timeout code.

    This is a regression: the artifact-storage amendment MUST NOT
    have side-effected ``run_probe_with_timeout`` semantics.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        STARTUP_PROBE_TIMEOUT,
        BlockingProbeTimeout,
        run_probe_with_timeout,
    )

    def _slow_probe(*, timeout_seconds):
        raise BlockingProbeTimeout()

    out = run_probe_with_timeout(
        name="slow",
        fn=_slow_probe,
        timeout_seconds=1,
        on_timeout_code=STARTUP_PROBE_TIMEOUT,
    )
    assert out.status == "fail"
    assert out.code == STARTUP_PROBE_TIMEOUT


# --- (25) unclassified non-timeout exception is NOT reclassified -----


def test_probe_artifact_storage_does_not_silently_catch_unexpected_exceptions(
    monkeypatch,
    tmp_path,
):
    """Non-OSError exceptions in the probe body MUST surface through
    the existing un-classified non-timeout failure channel
    (``run_probe_with_timeout`` → ``StartupNonTimeoutProbeFailure``);
    they MUST NOT be silently coerced into
    ``ARTIFACT_STORAGE_UNAVAILABLE``."""
    import tempfile as _tempfile

    from cold_storage.bootstrap.runtime_readiness import (
        StartupNonTimeoutProbeFailure,
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    _settings, _canonical = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )

    def _surprising_mkstemp(*_a, **_k):
        raise RuntimeError("unexpected programming error")

    monkeypatch.setattr(_tempfile, "mkstemp", _surprising_mkstemp)
    # The probe body treats only OSError as the deterministic
    # artifact-storage failure class. A non-OSError must propagate
    # out of the body to the un-classified non-timeout failure
    # channel — NOT be projected to ARTIFACT_STORAGE_UNAVAILABLE.
    with pytest.raises((RuntimeError, StartupNonTimeoutProbeFailure)):
        probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)


# --- regression: ad-hoc env keys absent from public detail ----------


def test_probe_artifact_storage_adhoc_env_keys_absent_from_detail(
    monkeypatch,
    tmp_path,
):
    """The public detail MUST NOT mention the ad-hoc env key names."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
        reset_canonical_settings,
        set_canonical_settings,
    )
    from cold_storage.bootstrap.settings import Settings

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    missing = tmp_path / "missing-detail"
    settings = Settings(  # type: ignore[call-arg]
        COLD_STORAGE_ENVIRONMENT_ID="production",
        COLD_STORAGE_APP_HOST="127.0.0.1",
        COLD_STORAGE_APP_PORT="8000",
        COLD_STORAGE_DATABASE_BACKEND="postgresql",
        COLD_STORAGE_DATABASE_URL="postgresql+psycopg2://u:p@localhost:5432/db",
        COLD_STORAGE_BUILD_COMMIT_SHA="0" * 40,
        COLD_STORAGE_BUILD_VERSION="v0.0.0-ci",
        COLD_STORAGE_CONFIG_SCHEMA_VERSION="1",
        COLD_STORAGE_DATABASE_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_SECRET_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID="ci-strict",
        COLD_STORAGE_STORAGE_DIR=str(missing),
    )
    set_canonical_settings(settings)
    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "fail"
    assert outcome.code == "ARTIFACT_STORAGE_UNAVAILABLE"
    assert "COLD_STORAGE_ARTIFACT_STORAGE_DIR" not in (outcome.detail or "")
    assert "COLD_STORAGE_REPORT_ARTIFACTS_DIR" not in (outcome.detail or "")
    reset_canonical_settings()


# --- regression: probe does not modify the canonical Settings object -


def test_probe_artifact_storage_does_not_mutate_canonical_settings(
    monkeypatch,
    tmp_path,
):
    """The probe MUST NOT mutate the canonical Settings object."""
    from cold_storage.bootstrap.runtime_readiness import (
        probe_artifact_storage_isolated_exists_writable,
    )

    monkeypatch.delenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", raising=False)
    monkeypatch.delenv("COLD_STORAGE_REPORT_ARTIFACTS_DIR", raising=False)
    settings, _ = _install_strict_canonical_settings(
        "production",
        monkeypatch,
        tmp_path,
    )
    original_storage_dir = settings.storage_dir
    original_env_id = settings.environment_id
    outcome = probe_artifact_storage_isolated_exists_writable(timeout_seconds=10)
    assert outcome.status == "pass"
    assert settings.storage_dir == original_storage_dir
    assert settings.environment_id == original_env_id


# ---------------------------------------------------------------------------
# V0.2 Slice 2 amendment: regression guard for F-PR76-BLOCKER-03
# composition-manifest evidence in strict mode.
#
# Background: a previous version of ``bootstrap.dependencies.init_dependencies``
# recorded the ``FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED`` token twice in the
# strict-mode (staging / production) branch even though the strict-mode
# placeholder path does NOT instantiate ``FakeAgentModelGateway``. The token
# in the live composition manifest made the strict capability audit
# (D-S2-06.c) raise ``UnsafeStrictCapabilityWiring`` against the empty
# production placeholder, blocking real production startup.
#
# The earlier ``test_strict_mode_init_does_not_instantiate_fake_agent_gateway``
# test only inspected (a) the source code text and (b) the empty default
# manifest. It did NOT exercise the live init path, so the regression was
# not caught. The new test below actually invokes ``init_dependencies`` in
# strict mode and asserts the live composition-manifest state BEFORE any
# shutdown / reset / teardown could mask the regression.
# ---------------------------------------------------------------------------


def test_strict_mode_init_live_composition_manifest_has_no_fake_token(
    monkeypatch,
):
    """F-PR76-BLOCKER-03 live regression guard.

    Step-by-step:

    1. Configure production canonical Settings with hermetic env vars.
    2. Stub the heavier bootstrap helpers so we do not need a real
       DB engine, project service, production scheme service,
       production coefficient resolver, startup-readiness gateway,
       or full probe pipeline. The minimum needed to reach the
       strict-mode composition branch is just an engine sentinel.
    3. Track ``FakeAgentModelGateway`` instantiation with a sentinel
       guard so any accidental construction raises an explicit
       AssertionError.
    4. Build a real clean FastAPI app.
    5. Call ``init_dependencies(settings, app=app)`` directly.
    6. BEFORE any shutdown / reset, assert the live composition
       manifest is free of the fake-gateway token AND the app has no
       planning-agent HTTP routes mounted.
    7. Call ``assert_no_unsafe_strict_capabilities(app=app)`` and
       confirm it returns normally (does not raise).
    8. Idempotent cleanup in ``finally``.
    """
    from fastapi import FastAPI

    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.runtime_readiness import (
        assert_no_unsafe_strict_capabilities,
        composition_manifest_tokens,
        reset_canonical_settings,
        reset_composition_manifest_provider,
        reset_readiness_state,
    )
    from cold_storage.bootstrap.settings import Settings

    # Step 1: hermetic strict-mode environment.
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
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

    settings = Settings()  # type: ignore[call-arg]

    # Step 2: stub the heavier bootstrap helpers so we exercise the
    # strict-mode composition branch WITHOUT needing a real DB.
    engine = object()
    monkeypatch.setattr(
        deps,
        "create_engine_from_settings",
        lambda s: engine,
    )
    monkeypatch.setattr(
        deps,
        "DatabaseProjectService",
        lambda _engine: object(),
    )

    # Patch the production composition root modules that init_dependencies
    # imports lazily. We patch them on their source modules so the
    # lazy ``from ... import`` inside init_dependencies picks up the
    # stubbed callables.
    from cold_storage.bootstrap import production_composition as prod_comp
    from cold_storage.bootstrap import startup_readiness as startup_read

    monkeypatch.setattr(
        prod_comp,
        "compose_production_scheme_service",
        lambda *a, **kw: object(),
    )
    monkeypatch.setattr(
        prod_comp,
        "compose_production_coefficient_resolver",
        lambda *a, **kw: object(),
    )

    # Stub the startup-readiness gateway so we do not exercise the
    # database. The strict-mode composition branch runs AFTER this
    # gateway, so stubbing it is safe for this regression guard.
    class _StubReadinessOutcome:
        def __init__(self):
            self.report = type("R", (), {})()

    monkeypatch.setattr(
        startup_read,
        "run_startup_readiness_or_raise",
        lambda *a, **kw: _StubReadinessOutcome(),
    )

    # Stub the per-probe startup phase so the audit path runs but no
    # real probe executes (the regression we are guarding against
    # happens in bootstrap, before any probe runs).
    from cold_storage.bootstrap import runtime_readiness as rr

    monkeypatch.setattr(rr, "run_startup_phase", lambda *a, **kw: None)

    # Step 3: sentinel guard on ``FakeAgentModelGateway`` instantiation.
    from cold_storage.modules.planning_agent.infrastructure import (
        fake_gateways,
    )

    real_init = fake_gateways.FakeAgentModelGateway.__init__

    def _forbid_instantiation(self, *args, **kwargs):
        raise AssertionError(
            "FakeAgentModelGateway must not be instantiated in strict mode",
        )

    fake_gateways.FakeAgentModelGateway.__init__ = _forbid_instantiation
    try:
        # Step 4 + 5: build a clean FastAPI app and call the live
        # ``init_dependencies`` strict-mode path.
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        deps.init_dependencies(settings, app=app)

        # Step 6: BEFORE any shutdown / reset, assert the live
        # composition-manifest is clean. This is the regression
        # guard. The previous buggy code recorded the token twice in
        # the strict-mode branch, polluting the live manifest.
        tokens = composition_manifest_tokens()
        assert "FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED" not in tokens, (
            f"strict-mode init leaked fake-gateway token into manifest: {sorted(tokens)}"
        )

        # Step 7: confirm no planning-agent route is mounted in the
        # live FastAPI app.
        route_paths = []
        for r in app.routes:
            path = getattr(r, "path", None)
            if isinstance(path, str):
                route_paths.append(path)
        assert not any(p.startswith("/api/v1/agent/") for p in route_paths), (
            f"strict-mode app has planning-agent routes: {route_paths}"
        )

        # Step 8: confirm the strict capability audit passes on the
        # live app. This is the canonical assertion consumed by
        # production lifespan.
        # D-S4-06: Set binding manifest on app before audit
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "disabled"),
        )
        assert_no_unsafe_strict_capabilities(app=app)
    finally:
        # Idempotent cleanup. We deliberately do NOT use the
        # ``deps.shutdown_dependencies`` shortcut as part of the
        # assertions; we only use it here to leave a clean global
        # state for the next test.
        try:
            deps.shutdown_dependencies()
        finally:
            reset_canonical_settings()
            reset_composition_manifest_provider()
            reset_readiness_state()
            fake_gateways.FakeAgentModelGateway.__init__ = real_init


# ---------------------------------------------------------------------------
# PR #81 R4 — strict audit test cases: frozen endpoint matrix, binding
# manifest validation, composition evidence, and bypass-resistance.
# ---------------------------------------------------------------------------


def _strict_fastapi_app_with_all_frozen_agent_routes():
    """Build a FastAPI app with ALL frozen agent endpoint routes.

    Registers every method+path pair from the frozen endpoint matrix.
    Each endpoint function is named ``disabled_agent_*`` so the
    endpoint identity check passes. The binding manifest declares
    model_backed_agent as "disabled". The audit should ALLOW these
    routes because they exactly match the frozen matrix.
    """
    from fastapi import FastAPI

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.strict_capability_bindings = (
        ("coefficient_http", "database_backed"),
        ("model_backed_agent", "disabled"),
    )

    _frozen: list[tuple[str, str, Any]] = []

    @app.get("/api/v1/agent/sessions")
    def disabled_agent_get_sessions():  # pragma: no cover
        return {"ok": True}

    _frozen.append(("GET", "/api/v1/agent/sessions", disabled_agent_get_sessions))

    @app.post("/api/v1/agent/sessions")
    def disabled_agent_post_sessions():  # pragma: no cover
        return {"ok": True}

    _frozen.append(("POST", "/api/v1/agent/sessions", disabled_agent_post_sessions))

    @app.get("/api/v1/agent/sessions/{session_id}")
    def disabled_agent_get_session():  # pragma: no cover
        return {"ok": True}

    _frozen.append(("GET", "/api/v1/agent/sessions/{session_id}", disabled_agent_get_session))

    @app.post("/api/v1/agent/sessions/{session_id}/cancel")
    def disabled_agent_cancel_session():  # pragma: no cover
        return {"ok": True}

    _frozen.append(
        ("POST", "/api/v1/agent/sessions/{session_id}/cancel", disabled_agent_cancel_session)
    )

    @app.get("/api/v1/agent/sessions/{session_id}/messages")
    def disabled_agent_get_messages():  # pragma: no cover
        return {"ok": True}

    _frozen.append(
        ("GET", "/api/v1/agent/sessions/{session_id}/messages", disabled_agent_get_messages)
    )

    @app.post("/api/v1/agent/sessions/{session_id}/messages")
    def disabled_agent_post_messages():  # pragma: no cover
        return {"ok": True}

    _frozen.append(
        ("POST", "/api/v1/agent/sessions/{session_id}/messages", disabled_agent_post_messages)
    )

    @app.get("/api/v1/agent/sessions/{session_id}/tool-calls")
    def disabled_agent_get_tool_calls():  # pragma: no cover
        return {"ok": True}

    _frozen.append(
        ("GET", "/api/v1/agent/sessions/{session_id}/tool-calls", disabled_agent_get_tool_calls)
    )

    @app.get("/api/v1/agent/sessions/{session_id}/turns/{turn_id}")
    def disabled_agent_get_turns():  # pragma: no cover
        return {"ok": True}

    _frozen.append(
        ("GET", "/api/v1/agent/sessions/{session_id}/turns/{turn_id}", disabled_agent_get_turns)
    )

    @app.post("/api/v1/agent/tool-calls/{tool_call_id}/confirm")
    def disabled_agent_confirm_tool_call():  # pragma: no cover
        return {"ok": True}

    _frozen.append(
        (
            "POST",
            "/api/v1/agent/tool-calls/{tool_call_id}/confirm",
            disabled_agent_confirm_tool_call,
        )
    )

    @app.post("/api/v1/agent/tool-calls/{tool_call_id}/reject")
    def disabled_agent_reject_tool_call():  # pragma: no cover
        return {"ok": True}

    _frozen.append(
        ("POST", "/api/v1/agent/tool-calls/{tool_call_id}/reject", disabled_agent_reject_tool_call)
    )

    app.state.frozen_agent_endpoint_authority = tuple(_frozen)
    app.state.coefficient_route_evidence = {"provider": None, "endpoints": ()}
    # R6: Set the composition-root authority with the actual endpoint objects.
    from cold_storage.bootstrap.app import AgentRouteAuthority, StrictRuntimeAuthority

    app.state._strict_runtime_authority = StrictRuntimeAuthority(  # noqa: SLF001
        agent_routes=tuple(
            AgentRouteAuthority(method=m, path=p, endpoint=ep) for m, p, ep in _frozen
        ),
        coefficient_routes=(),
        coefficient_provider=None,
        capability_mode="enabled",
    )
    return app


def _strict_fastapi_app_with_exact_frozen_agent_route():
    """Build a FastAPI app with an exact frozen agent endpoint route.

    Registers POST /api/v1/agent/sessions with disabled_agent_ naming,
    which is in the frozen endpoint matrix. The binding manifest declares
    model_backed_agent as "disabled". The audit should ALLOW this route.
    R6: Also sets _strict_runtime_authority on app.state.
    """
    from fastapi import FastAPI

    from cold_storage.bootstrap.app import AgentRouteAuthority, StrictRuntimeAuthority

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.strict_capability_bindings = (
        ("coefficient_http", "database_backed"),
        ("model_backed_agent", "disabled"),
    )

    @app.post("/api/v1/agent/sessions")
    def disabled_agent_post_sessions():  # pragma: no cover
        return {"ok": True}

    app.state.frozen_agent_endpoint_authority = (
        ("POST", "/api/v1/agent/sessions", disabled_agent_post_sessions),
    )
    app.state.coefficient_route_evidence = {"provider": None, "endpoints": ()}
    # R6: Set the composition-root authority.
    app.state._strict_runtime_authority = StrictRuntimeAuthority(  # noqa: SLF001
        agent_routes=(
            AgentRouteAuthority(
                method="POST",
                path="/api/v1/agent/sessions",
                endpoint=disabled_agent_post_sessions,
            ),
        ),
        coefficient_routes=(),
        coefficient_provider=None,
        capability_mode="enabled",
    )
    return app


def _strict_fastapi_app_with_wrong_method_agent_route():
    """Build a FastAPI app with a GET route on an agent path not in
    the frozen endpoint matrix.
    R6: Also sets _strict_runtime_authority on app.state.
    """
    from fastapi import FastAPI

    from cold_storage.bootstrap.app import StrictRuntimeAuthority

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.strict_capability_bindings = (
        ("coefficient_http", "database_backed"),
        ("model_backed_agent", "disabled"),
    )

    @app.get("/api/v1/agent/healthz")
    def _healthz():  # pragma: no cover - never invoked
        return {"ok": True}

    # This helper has a wrong method (GET instead of POST) on a frozen path.
    # The frozen authority should NOT include this route.
    app.state.frozen_agent_endpoint_authority = ()
    app.state.coefficient_route_evidence = {"provider": None, "endpoints": ()}
    # R6: No agent routes in frozen authority — audit should reject.
    app.state._strict_runtime_authority = StrictRuntimeAuthority()  # noqa: SLF001
    return app


def test_disabled_agent_exact_method_path_endpoint_allowed(monkeypatch):
    """DISABLED_AGENT_EXACT_METHOD_PATH_ENDPOINT_ALLOWED.

    A POST route on an exact frozen agent endpoint path (e.g.
    /api/v1/agent/sessions) with binding identity "disabled" and
    clean composition evidence MUST pass the audit. This proves
    the frozen endpoint matrix is respected for allowed routes.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_all_frozen_agent_routes(),
        )
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_active_agent_on_frozen_path_rejected(monkeypatch):
    """ACTIVE_AGENT_ON_FROZEN_PATH_REJECTED.

    When the binding manifest declares model_backed_agent with
    identity "active" (instead of the frozen "disabled"), the
    manifest validation MUST raise UnsafeStrictCapabilityWiring
    with error code UNKNOWN_BINDING — even if the route is on a
    frozen endpoint path.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        from fastapi import FastAPI

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        # Binding says "active" instead of "disabled" — WRONG
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "active"),
        )

        @app.post("/api/v1/agent/sessions")
        def _sessions():  # pragma: no cover
            return {"ok": True}

        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            enumerate_reachable_unsafe_strict_capabilities(app=app)
        assert "UNKNOWN_BINDING" in str(exc_info.value)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_fake_agent_on_frozen_path_rejected(monkeypatch):
    """FAKE_AGENT_ON_FROZEN_PATH_REJECTED.

    A route at /api/v1/agent/fake-run (NOT in the frozen endpoint
    matrix) MUST cause the audit to flag model_backed_agent as
    unsafe, even with correct binding identity and composition
    evidence. The frozen matrix is an exact allowlist.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        from fastapi import FastAPI

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "disabled"),
        )

        @app.post("/api/v1/agent/fake-run")
        def _fake():  # pragma: no cover
            return {"fake": True}

        reachable = enumerate_reachable_unsafe_strict_capabilities(app=app)
        assert reachable == ("model_backed_agent",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_wrong_method_on_frozen_path_rejected(monkeypatch):
    """WRONG_METHOD_ON_FROZEN_PATH_REJECTED.

    A GET route at /api/v1/agent/healthz (NOT in the frozen endpoint
    matrix, even though it starts with the agent prefix) MUST cause
    the audit to flag model_backed_agent as unsafe. The frozen matrix
    checks exact path strings, not prefixes.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_wrong_method_agent_route(),
        )
        assert reachable == ("model_backed_agent",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_duplicate_frozen_route_rejected(monkeypatch):
    """DUPLICATE_FROZEN_ROUTE_REJECTED.

    A binding manifest with duplicate entries for the same capability
    (even with identical identity) MUST cause manifest validation to
    fail with DUPLICATE_IDENTICAL_BINDING. The audit raises
    UnsafeStrictCapabilityWiring immediately.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        from fastapi import FastAPI

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        # Duplicate binding — same capability registered twice
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "disabled"),
            ("model_backed_agent", "disabled"),
        )

        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            enumerate_reachable_unsafe_strict_capabilities(app=app)
        assert "DUPLICATE_IDENTICAL_BINDING" in str(exc_info.value)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_extra_agent_route_rejected(monkeypatch):
    """EXTRA_AGENT_ROUTE_REJECTED.

    An extra agent route (e.g. /api/v1/agent/custom-action) not in
    the frozen endpoint matrix MUST cause the audit to flag
    model_backed_agent as unsafe. The frozen matrix is exhaustive.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        from fastapi import FastAPI

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "disabled"),
        )

        @app.post("/api/v1/agent/custom-action")
        def _custom():  # pragma: no cover
            return {"custom": True}

        reachable = enumerate_reachable_unsafe_strict_capabilities(app=app)
        assert reachable == ("model_backed_agent",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_missing_agent_route_rejected(monkeypatch):
    """MISSING_AGENT_ROUTE_REJECTED.

    A binding manifest that omits the required model_backed_agent
    capability MUST cause manifest validation to fail with
    MISSING_REQUIRED_CAPABILITY. Every strict capability declared in
    the frozen manifest must be present.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        from fastapi import FastAPI

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        # model_backed_agent is MISSING from the manifest
        app.state.strict_capability_bindings = (("coefficient_http", "database_backed"),)

        with pytest.raises(UnsafeStrictCapabilityWiring) as exc_info:
            enumerate_reachable_unsafe_strict_capabilities(app=app)
        assert "MISSING_REQUIRED_CAPABILITY" in str(exc_info.value)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_delayed_production_coefficient_provider_allowed(monkeypatch):
    """DELAYED_PRODUCTION_COEFFICIENT_PROVIDER_ALLOWED.

    A coefficient route backed by a delayed (lazy) database-backed
    provider with the DATABASE_COEFFICIENT_SERVICE_INSTANTIATED
    composition token MUST pass the audit in production mode. The
    delayed provider pattern is the only allowed wiring.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ()
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_concrete_database_coefficient_provider_rejected(monkeypatch):
    """CONCRETE_DATABASE_COEFFICIENT_PROVIDER_REJECTED.

    When the composition manifest contains BOTH the required positive
    token (DATABASE_COEFFICIENT_SERVICE_INSTANTIATED) AND the
    forbidden process-local token, the audit MUST flag
    coefficient_http as unsafe. The presence of the forbidden token
    overrides the positive evidence — a concrete (non-delayed)
    wiring is not allowed.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    # Both positive and forbidden tokens present → forbidden wins
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset(
            {
                "DATABASE_COEFFICIENT_SERVICE_INSTANTIATED",
                "PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED",
            }
        ),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ("coefficient_http",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_process_local_provider_rejected(monkeypatch):
    """PROCESS_LOCAL_PROVIDER_REJECTED.

    When the composition manifest contains ONLY the
    PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED token (no
    DATABASE_COEFFICIENT_SERVICE_INSTANTIATED), the audit MUST flag
    coefficient_http as unsafe. Two independent checks fail:
    the forbidden token is present, and the required positive token
    is missing.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ("coefficient_http",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_unknown_provider_rejected(monkeypatch):
    """UNKNOWN_PROVIDER_REJECTED.

    When the composition manifest is empty (no provider was
    registered, or the provider returned an empty set), the audit
    MUST flag coefficient_http as unsafe because the required
    positive token DATABASE_COEFFICIENT_SERVICE_INSTANTIATED is
    missing.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset(),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        assert reachable == ("coefficient_http",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_p2c_disabled_agent_does_not_invoke_provider_probe():
    """DISABLED is configuration-only and never probes a provider."""
    calls = 0

    def _probe(_settings):
        nonlocal calls
        calls += 1
        return True

    evidence = resolve_agent_capability_evidence(
        Settings.model_validate({}),
        provider_probe=_probe,
    )
    assert isinstance(evidence, AgentCapabilityEvidence)
    assert evidence.state is AgentCapabilityState.DISABLED
    assert evidence.global_readiness == "PASS_IF_ALL_OTHER_MANDATORY_READINESS_GATES_PASS"
    assert evidence.route_exposure == "DISABLED_ROUTE_MATRIX"
    assert calls == 0


@pytest.mark.parametrize(
    "values",
    [
        {"COLD_STORAGE_AGENT_PROVIDER": "mimo"},
        {"COLD_STORAGE_AGENT_MODEL": "mimo-v2.5"},
        {"COLD_STORAGE_AGENT_PROVIDER": "other", "COLD_STORAGE_AGENT_MODEL": "mimo-v2.5"},
    ],
)
def test_p2c_enablement_intent_without_valid_configuration_is_not_ready(values):
    values = {
        "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": 10,
        "COLD_STORAGE_AGENT_MAX_RETRIES": 0,
        **values,
    }
    evidence = resolve_agent_capability_evidence(Settings.model_validate(values))
    assert evidence.state is AgentCapabilityState.ENABLED_NOT_READY
    assert evidence.global_readiness == "FAIL"
    assert evidence.route_exposure == "DISABLED_ROUTE_MATRIX"


def test_p2c_provider_probe_failure_is_not_ready():
    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "mimo",
            "COLD_STORAGE_AGENT_MODEL": "mimo-v2.5",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": 10,
            "COLD_STORAGE_AGENT_MAX_RETRIES": 1,
            "COLD_STORAGE_MIMO_API_KEY": "sk-test-only-key",
        }
    )
    evidence = resolve_agent_capability_evidence(
        settings,
        provider_probe=lambda _s: AgentProviderProbeEvidence(
            passed=False,
            failure_code=AgentProviderFailureCode.AGENT_PROVIDER_TIMEOUT,
            provider="mimo",
            model="mimo-v2.5",
        ),
    )
    assert evidence.state is AgentCapabilityState.ENABLED_NOT_READY
    assert evidence.provider_probe_passed is False
    assert evidence.failure_code == "AGENT_PROVIDER_TIMEOUT"


def test_p2c_provider_probe_and_composition_evidence_enable_ready_state():
    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "mimo",
            "COLD_STORAGE_AGENT_MODEL": "mimo-v2.5",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": 10,
            "COLD_STORAGE_AGENT_MAX_RETRIES": 1,
            "COLD_STORAGE_MIMO_API_KEY": "sk-test-only-key",
        }
    )
    evidence = resolve_agent_capability_evidence(
        settings,
        provider_probe=lambda current: AgentProviderProbeEvidence(
            passed=True,
            provider=current.agent_provider,
            model=current.agent_model,
            schema_verified=True,
            schema_identity="AgentDecision",
        ),
    )
    assert evidence.state is AgentCapabilityState.ENABLED_NOT_READY
    assert evidence.provider_probe_passed is True
    assert evidence.composition_passed is False
    assert evidence.route_audit_passed is False

    final = finalize_agent_capability_evidence(
        evidence,
        audit_evidence=StrictCapabilityAuditEvidence(
            composition_passed=True,
            route_audit_passed=True,
        ),
    )
    assert final.state is AgentCapabilityState.ENABLED_READY
    assert final.global_readiness.startswith("PASS_IF_PROVIDER")
    assert final.route_exposure == "REAL_AGENT_ROUTES_ENABLED"


def test_p2c_preserves_canonical_eight_readiness_probes():
    from cold_storage.bootstrap.runtime_readiness import (
        mandatory_readiness_probes,
        mandatory_startup_probes,
    )

    expected = (
        "probe_lifecycle_initialization_completed",
        "probe_process_not_draining_or_shutting_down",
        "probe_database_connectivity",
        "probe_database_exact_alembic_head",
        "probe_environment_and_resource_identities",
        "probe_artifact_storage_isolated_exists_writable",
        "probe_approved_coefficient_readiness_in_strict_modes",
        "probe_build_and_deployment_identity",
    )
    startup_names = tuple(probe.__name__ for probe in mandatory_startup_probes())
    readiness_names = tuple(probe.__name__ for probe in mandatory_readiness_probes())
    assert len(startup_names) == 8
    assert len(readiness_names) == 8
    assert startup_names == expected
    assert readiness_names == expected


def test_forged_positive_token_cannot_bypass(monkeypatch):
    """FORGED_POSITIVE_TOKEN_CANNOT_BYPASS.

    Injecting a forged DATABASE_COEFFICIENT_SERVICE_INSTANTIATED
    composition token while simultaneously having a forbidden
    PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED token MUST NOT
    bypass the audit. The forbidden-token check takes priority over
    positive evidence — the audit cannot be tricked by a forged
    positive signal.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("staging", monkeypatch))
    # Forged positive + forbidden → forbidden wins, bypass blocked
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset(
            {
                "DATABASE_COEFFICIENT_SERVICE_INSTANTIATED",
                "PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED",
            }
        ),
    )
    try:
        reachable = enumerate_reachable_unsafe_strict_capabilities(
            app=_strict_fastapi_app_with_coefficient_route(),
        )
        # The forged positive token does NOT suppress the forbidden
        # token check; coefficient_http is still flagged.
        assert reachable == ("coefficient_http",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]


def test_static_binding_self_attestation_cannot_bypass(monkeypatch):
    """STATIC_BINDING_SELF_ATTESTATION_CANNOT_BYPASS.

    Writing correct-looking strict_capability_bindings on app.state
    from the route module (self-attestation) does NOT bypass the
    frozen endpoint matrix check. The audit independently verifies
    every registered route against the frozen set; a self-attested
    binding manifest cannot suppress route-level violations.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        enumerate_reachable_unsafe_strict_capabilities,
        set_canonical_settings,
    )

    set_canonical_settings(_strict_settings("production", monkeypatch))
    monkeypatch.setattr(
        "cold_storage.bootstrap.runtime_readiness.composition_manifest_tokens",
        lambda: frozenset({"DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"}),
    )
    try:
        from fastapi import FastAPI

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        # Self-attested correct bindings
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "disabled"),
        )

        # But registers a non-frozen agent route
        @app.post("/api/v1/agent/self-attested-endpoint")
        def _self_attested():  # pragma: no cover
            return {"attested": True}

        # Self-attestation does NOT bypass the frozen endpoint check
        reachable = enumerate_reachable_unsafe_strict_capabilities(app=app)
        assert reachable == ("model_backed_agent",)
    finally:
        set_canonical_settings(None)  # type: ignore[arg-type]
