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
from cold_storage.modules.planning_agent.application.agent_service import LegacyPlanningAgentService
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import FakeAgentModelGateway
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from cold_storage.modules.schemes.application.production_service import ProductionSchemeService

_singletons: dict[str, Any] = {}


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
    """
    from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
        canonical_settings,
        get_or_init_readiness_state,
        mandatory_startup_probes,
        run_startup_phase,
        set_canonical_settings,
    )

    # Publish the canonical Settings authority exactly once so the
    # readiness endpoint and probes never construct a second one.
    set_canonical_settings(settings)

    engine = create_engine_from_settings(settings)
    project_service = DatabaseProjectService(engine)
    agent_service = LegacyPlanningAgentService(model_gateway=FakeAgentModelGateway())

    _singletons["engine"] = engine
    _singletons["project_service"] = project_service
    _singletons["agent_service"] = agent_service

    # Production scheme service: wired via the canonical composition root
    # so the production archive row is always written in the same UoW.
    # Lazy import keeps `bootstrap.dependencies` free of application-tier
    # imports at module load (the FastAPI test harness imports this file
    # before the orchestration module is available).
    from cold_storage.bootstrap.production_composition import (
        compose_production_scheme_service,
    )

    session_factory_obj: sessionmaker[Any] = sessionmaker(bind=engine, expire_on_commit=False)
    production_service: ProductionSchemeService = compose_production_scheme_service(
        session_factory_obj,
    )
    _singletons["production_scheme_service"] = production_service
    _singletons["production_session_factory"] = session_factory_obj

    # Slice 2A: ApprovedCoefficientResolver singleton.  In production
    # mode this singleton is consumed by
    # ``compose_production_source_binding_use_case_with_strict_resolver``
    # (see bootstrap.production_composition) so the orchestrator bind
    # path never silently falls back to demo coefficients.  Building
    # the resolver in development / test mode is harmless — callers
    # that want the strict path can still inject it; callers that do
    # not (the legacy P3 wiring) continue to work unchanged.
    from cold_storage.bootstrap.production_composition import (
        compose_production_coefficient_resolver,
    )

    _singletons["production_coefficient_resolver"] = compose_production_coefficient_resolver(
        engine=engine,
    )

    # Slice 2A: production-mode startup-readiness gateway.  In
    # production mode this raises ``StartupReadinessError`` if any of
    # the 5 required stages lacks an approved non-demo coefficient;
    # ``AppMode.DEVELOPMENT`` and ``AppMode.TEST`` skip the check so
    # demo flows / pytest fixtures are untouched.  This call is the
    # only place that consults the database at boot.
    from cold_storage.bootstrap.startup_readiness import (
        run_startup_readiness_or_raise,
    )

    readines_outcome = run_startup_readiness_or_raise(settings=settings, engine=engine)
    _singletons["startup_readiness_outcome"] = readines_outcome

    # TASK-012 Slice 2: publish the readiness state singleton BEFORE
    # ``run_startup_phase`` so the latter can consult the canonical
    # authority. The pre-existing Slice 2A readiness check above has
    # already happened against the database; ``run_startup_phase``
    # executes additional per-probe checks under ``bootstrap.runtime_readiness``
    # and updates the state singleton to ``READY`` on success.
    # The local ``state`` alias is intentional: it makes the singleton
    # ownership explicit in this bootstrap sequence. ``run_startup_phase``
    # consults the underlying authority; we deliberately do not bind
    # the result to ``state`` in this scope.
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
    except Exception as exc:  # noqa: BLE001
        # On any startup-phase failure we still want the engine
        # composed; the lifespan closer in ``bootstrap.app`` will
        # dispose it.  Re-raise so the failure surface matches the
        # contract.
        raise exc
    _ = canonical_settings  # explicit non-use; documented behavior.


def get_project_service() -> ProjectService:
    """Return the ProjectService singleton. Raises RuntimeError if not initialized."""
    if "project_service" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["project_service"]  # type: ignore[no-any-return]


def get_agent_service() -> LegacyPlanningAgentService:
    """Return the LegacyPlanningAgentService singleton."""
    if "agent_service" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["agent_service"]  # type: ignore[no-any-return]


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
    """
    from contextlib import suppress

    from cold_storage.bootstrap.runtime_readiness import (
        get_readiness_state,
        reset_readiness_state,
    )

    state = get_readiness_state()
    with suppress(Exception):
        if state is not None:
            state.transition(to="DRAINING")
    if "engine" in _singletons:
        dispose_engine(_singletons["engine"])
    _singletons.clear()
    reset_readiness_state()


# Backward compatibility
from cold_storage.modules.projects.infrastructure.database import (  # noqa: E402, F401
    create_database_project_service,
)
