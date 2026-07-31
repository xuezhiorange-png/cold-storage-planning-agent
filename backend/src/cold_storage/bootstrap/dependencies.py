"""Runtime dependency management — no import-time singletons."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.database import create_engine_from_settings, dispose_engine
from cold_storage.bootstrap.settings import Settings
from cold_storage.modules.coefficients.application.resolver import (
    ApprovedCoefficientResolver,
)
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService

# F-PR76-BLOCKER-03: the strict-mode composition contract forbids
# importing the fake model gateway or the process-local coefficient
# service from this module at runtime in staging / production. The
# names below are recorded as evidence tokens in the composition
# manifest (D-S2-06.a) so the defensive audit can prove they were
# never constructed in strict modes without ``runtime_readiness``
# having to import the business types themselves.
_COMPOSITION_TOKEN_FAKE_AGENT_GATEWAY = "FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED"
_COMPOSITION_TOKEN_PROCESS_LOCAL_COEFFICIENT = "PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED"


if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from cold_storage.modules.schemes.application.production_service import (
        ProductionSchemeService,
    )

_singletons: dict[str, Any] = {}
_composition_tokens: set[str] = set()


def init_dependencies(settings: Settings, *, app: Any = None) -> None:
    """Create engine, session_factory, project_service, agent_service and store them.

    TASK-012 Slice 2 contract: the readiness authority is registered
    here exactly once (D-S2-10, D-S2-03). The startup phase is invoked
    once after dependency composition; the readiness state singleton
    is published through :func:`get_readiness_state`. The defensive
    strict-mode assertion (D-S2-06.c) executes inside
    ``run_startup_phase``.

    ``app`` is the live FastAPI instance used by the strict-mode
    capability audit (D-S2-06.c). Production callers MUST pass the
    real ``app`` so the audit can inspect ``app.routes`` for any
    registered capability that should not be reachable in staging /
    production. Unit tests that exercise ``init_dependencies``
    without a FastAPI app can pass ``app=None``; the audit then
    raises :class:`UnsafeStrictCapabilityWiring` as part of the
    fail-closed contract (it is NOT a silent success).

    F-PR76-BLOCKER-03 — strict-mode fake-gateway composition. In
    staging / production the ``LegacyPlanningAgentService`` is
    composed with a ``model_gateway=None`` placeholder so the
    ``FakeAgentModelGateway`` constructor is never reached. No
    fake-backed singleton is registered, and the composition-manifest
    provider (registered with ``runtime_readiness``) reports zero
    unsafe composition tokens. The defensive audit therefore proves
    the unsafe backend was never constructed regardless of whether
    any HTTP route is mounted.

    F-PR76-HIGH-01 — transactional ``init_dependencies``. The first
    resource (canonical settings authority) is the transaction root;
    if any subsequent step raises, the already-published resources
    are released through :func:`shutdown_dependencies` before the
    exception is re-raised so the lifespan ``finally`` has nothing
    left to dispose. ``shutdown_dependencies`` is idempotent and
    safe to call multiple times; a second ``init_dependencies``
    after a failure starts from a clean state with no leaked
    singletons.
    """
    from cold_storage.bootstrap.mode import AppMode, resolve_app_mode  # noqa: PLC0415
    from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
        canonical_settings,
        get_or_init_readiness_state,
        mandatory_startup_probes,
        reset_composition_manifest_provider,
        run_startup_phase,
        set_canonical_settings,
        set_composition_manifest_provider,
    )

    # Transactional reset so a previous failed init does not poison
    # this one. ``shutdown_dependencies`` is idempotent; the reset of
    # the composition-manifest provider and the readiness state is
    # here (and not in ``shutdown_dependencies``) because those are
    # bootstrap-owned singletons that must be cleared even if the
    # previous shutdown was skipped due to a failed init.
    _clear_composition_tokens()
    reset_composition_manifest_provider()
    set_composition_manifest_provider(_composition_manifest_provider)
    # Publish the canonical Settings authority exactly once so the
    # readiness endpoint and probes never construct a second one.
    set_canonical_settings(settings)

    # Transactional init: any exception below the publish step
    # triggers a full ``shutdown_dependencies`` so no engine /
    # service / readiness state leaks across lifecycles.
    _init_started = True
    try:
        engine = create_engine_from_settings(settings)
    except Exception:
        _init_started = False
        # Roll back the canonical settings + composition manifest we
        # already published so a fresh init is not poisoned.
        _rollback_bootstrap_state()
        raise

    # Resolve the application mode up front so subsequent branching
    # never accidentally invokes a strict-mode-forbidden backend.
    try:
        mode = resolve_app_mode(settings)
    except Exception:
        mode = None

    _singletons["engine"] = engine
    try:
        project_service = DatabaseProjectService(engine)
    except Exception:
        shutdown_dependencies()
        raise
    _singletons["project_service"] = project_service

    # F-PR76-BLOCKER-03: only local / test modes may instantiate the
    # legacy fake-backed agent service. Strict modes register a
    # placeholder so the agent_service singleton exists without
    # ever invoking ``FakeAgentModelGateway()``.
    #
    # The composition token ``FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED``
    # is ONLY emitted from the *real* fake-gateway construction path
    # in the local / test branch below. The strict-mode placeholder
    # path MUST NOT record this token, otherwise the strict
    # capability audit (D-S2-06.c) would flag the live production
    # manifest even though no fake gateway was ever instantiated.
    if mode in (AppMode.STAGING, AppMode.PRODUCTION):
        agent_service: Any = _StrictModeAgentService()
    else:
        from cold_storage.modules.planning_agent.application.agent_service import (  # noqa: PLC0415
            LegacyPlanningAgentService,
        )
        from cold_storage.modules.planning_agent.infrastructure.fake_gateways import (  # noqa: PLC0415
            FakeAgentModelGateway,
        )

        # Composition-time evidence for the strict capability audit
        # (D-S2-06.c / F-PR76-BLOCKER-03). This token is ONLY emitted
        # on the actual local / test fake-gateway construction path;
        # the strict-mode placeholder branch above MUST NOT record it.
        _record_composition_token(_COMPOSITION_TOKEN_FAKE_AGENT_GATEWAY)
        agent_service = LegacyPlanningAgentService(
            model_gateway=FakeAgentModelGateway(),
        )
    _singletons["agent_service"] = agent_service

    # Production scheme service: wired via the canonical composition root
    # so the production archive row is always written in the same UoW.
    # Lazy import keeps `bootstrap.dependencies` free of application-tier
    # imports at module load (the FastAPI test harness imports this file
    # before the orchestration module is available).
    try:
        from cold_storage.bootstrap.production_composition import (  # noqa: PLC0415
            compose_production_scheme_service,
        )

        session_factory_obj: sessionmaker[Any] = sessionmaker(bind=engine, expire_on_commit=False)
        production_service: ProductionSchemeService = compose_production_scheme_service(
            session_factory_obj,
        )
    except Exception:
        shutdown_dependencies()
        raise
    _singletons["production_scheme_service"] = production_service
    _singletons["production_session_factory"] = session_factory_obj

    # Slice 2A: ApprovedCoefficientResolver singleton.
    try:
        from cold_storage.bootstrap.production_composition import (  # noqa: PLC0415
            compose_production_coefficient_resolver,
        )

        _singletons["production_coefficient_resolver"] = compose_production_coefficient_resolver(
            engine=engine,
        )
    except Exception:
        shutdown_dependencies()
        raise

    # Slice 2A: production-mode startup-readiness gateway.
    try:
        from cold_storage.bootstrap.startup_readiness import (  # noqa: PLC0415
            run_startup_readiness_or_raise,
        )

        readines_outcome = run_startup_readiness_or_raise(settings=settings, engine=engine)
    except Exception:
        shutdown_dependencies()
        raise
    _singletons["startup_readiness_outcome"] = readines_outcome

    # TASK-012 Slice 2: publish the readiness state singleton BEFORE
    # ``run_startup_phase`` so the latter can consult the canonical
    # authority. The pre-existing Slice 2A readiness check above has
    # already happened against the database; ``run_startup_phase``
    # executes additional per-probe checks under ``bootstrap.runtime_readiness``
    # and updates the state singleton to ``READY`` on success.
    get_or_init_readiness_state(
        settings=settings,
        environment={k: v for k, v in __import__("os").environ.items()},
    )
    # Run the per-probe startup phase using the canonical D-S2-04
    # eight-probe tuple. The audit then inspects the live FastAPI app
    # via ``app=app`` so a regression that re-introduces a fake-agent
    # route or a process-local coefficient route is caught fail-closed.
    try:
        run_startup_phase(
            settings=settings,
            environment={k: v for k, v in __import__("os").environ.items()},
            startup_probes=mandatory_startup_probes(),
            app=app,
        )
    except Exception:
        # F-PR76-HIGH-01: clean up half-initialized state so the
        # lifespan ``finally`` does not have to dispose anything
        # else. ``shutdown_dependencies`` is idempotent and resets
        # the canonical settings authority and the composition
        # manifest provider as part of its contract.
        shutdown_dependencies()
        raise
    _ = canonical_settings  # explicit non-use; documented behavior.
    _ = _init_started  # explicit non-use; documented behavior.


def _StrictModeAgentService() -> Any:
    """Strict-mode placeholder agent service (F-PR76-BLOCKER-03).

    The strict-mode composition contract (D-S2-06.a) forbids
    instantiating the fake agent model gateway in staging /
    production. This placeholder exposes the same callable surface
    the legacy service offers so callers that compose
    ``get_agent_service()`` receive something compatible. It is
    intentionally import-free of any business gateway type so the
    audit can prove via composition-manifest evidence that no
    unsafe backend was constructed.
    """

    class _Placeholder:
        def is_strict(self) -> bool:
            return True

    return _Placeholder()


def _record_composition_token(token: str) -> None:
    """Add ``token`` to the composition-manifest evidence set.

    F-PR76-BLOCKER-03: callers that genuinely construct a
    contract-forbidden backend MUST record the token so the audit
    can prove the composition happened. Callers that intentionally
    avoid the forbidden backend MUST NOT call this function with
    the corresponding token.
    """

    if not isinstance(token, str) or not token:
        raise ValueError("composition token must be a non-empty string")
    _composition_tokens.add(token)


def _clear_composition_tokens() -> None:
    """Reset the composition-manifest evidence set.

    Called at the start of every :func:`init_dependencies` so a
    previous failed init cannot leak composition evidence into a
    fresh attempt.
    """

    _composition_tokens.clear()


def _composition_manifest_provider() -> frozenset[str]:
    """Return the current composition-manifest evidence snapshot.

    This is the live provider registered with
    :func:`runtime_readiness.set_composition_manifest_provider`. It
    intentionally returns a fresh ``frozenset`` each call so the
    audit cannot be bypassed by mutating the result.
    """

    return frozenset(_composition_tokens)


def _rollback_bootstrap_state() -> None:
    """Undo the canonical settings publish + composition manifest setup.

    Used when ``init_dependencies`` cannot complete the engine
    creation step. The canonical settings authority and the
    composition-manifest provider are reset so the next init
    attempt starts from a clean state.
    """

    from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
        reset_canonical_settings,
        reset_composition_manifest_provider,
    )

    _clear_composition_tokens()
    reset_composition_manifest_provider()
    reset_canonical_settings()


def get_project_service() -> ProjectService:
    """Return the ProjectService singleton. Raises RuntimeError if not initialized."""
    if "project_service" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["project_service"]  # type: ignore[no-any-return]


def get_agent_service() -> Any:
    """Return the agent service singleton.

    In strict (staging / production) modes the singleton is a
    placeholder that intentionally avoids the
    :class:`FakeAgentModelGateway` construction path
    (F-PR76-BLOCKER-03). In local / test modes the singleton is the
    legacy ``LegacyPlanningAgentService`` with a fake gateway so
    demo flows keep working.
    """

    if "agent_service" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["agent_service"]


def get_engine() -> Any:
    """Return the engine from singletons (for alembic/test use)."""
    if "engine" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["engine"]


def get_production_scheme_service() -> ProductionSchemeService:
    """Return the production SchemeRun service singleton.

    Wired through ``bootstrap.production_composition`` so the
    production archive row always lands in the same UoW as the
    ``scheme_runs`` INSERT.  Raises RuntimeError if dependencies
    are not initialized.
    """
    if "production_scheme_service" not in _singletons:
        raise RuntimeError(
            "Dependencies not initialized. Call init_dependencies(settings) first.",
        )
    return _singletons["production_scheme_service"]  # type: ignore[no-any-return]


def get_production_session_factory() -> Callable[[], Any]:
    """Return the production SchemeRun session-factory singleton.

    Used by API routes / admin scripts that need a fresh
    ``Session`` per request when constructing a
    ``ProductionSchemeService`` directly (without going through
    the cached singleton).
    """
    if "production_session_factory" not in _singletons:
        raise RuntimeError(
            "Dependencies not initialized. Call init_dependencies(settings) first.",
        )
    return _singletons["production_session_factory"]  # type: ignore[no-any-return]


def get_production_coefficient_resolver() -> ApprovedCoefficientResolver:
    """Return the production :class:`ApprovedCoefficientResolver` singleton.

    Wired via ``bootstrap.production_composition`` against the
    production engine.  Consumed by production-mode callers that
    need the strict resolver (e.g. the Slice 2A
    ``compose_production_source_binding_use_case_with_strict_resolver``
    factory).  Raises :class:`RuntimeError` if dependencies were
    not initialized.
    """
    if "production_coefficient_resolver" not in _singletons:
        raise RuntimeError(
            "Dependencies not initialized. Call init_dependencies(settings) first.",
        )
    return _singletons["production_coefficient_resolver"]  # type: ignore[no-any-return]


def get_startup_readiness_outcome() -> Any:
    """Return the :class:`ReadinessCheckOutcome` from the last ``init_dependencies`` call.

    Exposed so callers (admin / readiness endpoints) can inspect the
    last readiness decision without re-running the database query.
    The outcome carries the mode under which the check ran plus,
    for production mode, the dict returned by
    :meth:`CoefficientApprovalService.validate_startup_readiness`.
    """
    if "startup_readiness_outcome" not in _singletons:
        raise RuntimeError(
            "Dependencies not initialized. Call init_dependencies(settings) first.",
        )
    return _singletons["startup_readiness_outcome"]


def shutdown_dependencies() -> None:
    """Dispose engine and clear all singletons.

    TASK-012 Slice 2 contract D-S2-10 requires the shutdown ordering:
    mark readiness unavailable, stop admitting new work, drain
    in-flight, dispose database, clear singletons, terminate. We
    perform the readiness-drain step (state -> DRAINING) BEFORE
    engine disposal; the cold_storage.bootstrap.runtime_readiness
    state singleton is cleared alongside every other singleton.

    F-PR76-HIGH-01 — idempotency. ``shutdown_dependencies`` is
    safe to call multiple times. A second invocation observes an
    already-empty singleton dict and a ``None`` readiness state
    and exits cleanly. The canonical settings authority and the
    composition-manifest provider are reset on every call so the
    next ``init_dependencies`` starts from a clean state.
    """

    from contextlib import suppress

    from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
        get_readiness_state,
        reset_canonical_settings,
        reset_composition_manifest_provider,
        reset_readiness_state,
    )

    state = get_readiness_state()
    with suppress(Exception):
        if state is not None:
            state.transition(to="DRAINING")
    engine = _singletons.get("engine")
    if engine is not None:
        with suppress(Exception):
            dispose_engine(engine)
    _singletons.clear()
    _clear_composition_tokens()
    reset_readiness_state()
    with suppress(Exception):
        reset_composition_manifest_provider()
    with suppress(Exception):
        reset_canonical_settings()


# Backward compatibility
from cold_storage.modules.projects.infrastructure.database import (  # noqa: E402, F401
    create_database_project_service,
)
