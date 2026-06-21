"""Tool adapters: project.get and project_version.get → ProjectService."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.planning_agent.domain.models import AgentToolResult
from cold_storage.modules.projects.application.service import ProjectService


class ProjectGetAdapter:
    def __init__(self, project_service: ProjectService) -> None:
        self._service = project_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        project_id = arguments["project_id"]
        project = self._service.get_project(project_id)
        return AgentToolResult(
            tool_name="project.get",
            output={"project": project.to_dict() if hasattr(project, "to_dict") else str(project)},
        )


class ProjectVersionGetAdapter:
    def __init__(self, project_service: ProjectService) -> None:
        self._service = project_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        project_id = arguments["project_id"]
        version_number = arguments["version_number"]
        version = self._service.get_version(project_id, version_number)
        return AgentToolResult(
            tool_name="project_version.get",
            output={"version": version.to_dict() if hasattr(version, "to_dict") else str(version)},
        )
