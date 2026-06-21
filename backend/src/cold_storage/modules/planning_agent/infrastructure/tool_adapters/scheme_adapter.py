"""Tool adapter: scheme.generate_and_compare → SchemeService."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.planning_agent.domain.models import AgentToolResult


class SchemeGenerateCompareAdapter:
    def __init__(self, scheme_service: Any) -> None:
        self._service = scheme_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        project_id = arguments["project_id"]
        version_number = arguments["version_number"]
        result = self._service.generate_scheme_run(project_id, version_number)
        return AgentToolResult(
            tool_name="scheme.generate_and_compare",
            output={"scheme_result": result},
            requires_review=True,
        )
