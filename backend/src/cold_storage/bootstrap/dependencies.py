from cold_storage.modules.planning_agent.application.agent_service import PlanningAgentService
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import FakeModelGateway
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.infrastructure.database import create_database_project_service

from .settings import get_settings

project_service = create_database_project_service(get_settings().database_url)
agent_service = PlanningAgentService(model_gateway=FakeModelGateway())


def get_project_service() -> ProjectService:
    return project_service


def get_agent_service() -> PlanningAgentService:
    return agent_service
