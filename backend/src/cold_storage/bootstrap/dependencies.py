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


def init_dependencies(settings: Settings) -> None:
    """Create engine, session_factory, project_service, agent_service and store them."""
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
    """Dispose engine and clear all singletons."""
    if "engine" in _singletons:
        dispose_engine(_singletons["engine"])
    _singletons.clear()


# Backward compatibility
from cold_storage.modules.projects.infrastructure.database import (  # noqa: E402, F401
    create_database_project_service,
)
