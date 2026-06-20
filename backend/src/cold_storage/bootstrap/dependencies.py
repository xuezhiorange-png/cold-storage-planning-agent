"""Runtime dependency management — no import-time singletons."""

from __future__ import annotations

from typing import Any

from cold_storage.bootstrap.database import create_engine_from_settings, dispose_engine
from cold_storage.bootstrap.settings import Settings
from cold_storage.modules.planning_agent.application.agent_service import PlanningAgentService
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import FakeModelGateway
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService

_singletons: dict[str, Any] = {}


def init_dependencies(settings: Settings) -> None:
    """Create engine, session_factory, project_service, agent_service and store them."""
    engine = create_engine_from_settings(settings)
    project_service = DatabaseProjectService(engine)
    agent_service = PlanningAgentService(model_gateway=FakeModelGateway())

    _singletons["engine"] = engine
    _singletons["project_service"] = project_service
    _singletons["agent_service"] = agent_service


def get_project_service() -> ProjectService:
    """Return the ProjectService singleton. Raises RuntimeError if not initialized."""
    if "project_service" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["project_service"]  # type: ignore[no-any-return]


def get_agent_service() -> PlanningAgentService:
    """Return the PlanningAgentService singleton."""
    if "agent_service" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["agent_service"]  # type: ignore[no-any-return]


def get_engine() -> Any:
    """Return the engine from singletons (for alembic/test use)."""
    if "engine" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["engine"]


def shutdown_dependencies() -> None:
    """Dispose engine and clear all singletons."""
    if "engine" in _singletons:
        dispose_engine(_singletons["engine"])
    _singletons.clear()


# Backward compatibility
from cold_storage.modules.projects.infrastructure.database import (  # noqa: E402, F401
    create_database_project_service,
)
