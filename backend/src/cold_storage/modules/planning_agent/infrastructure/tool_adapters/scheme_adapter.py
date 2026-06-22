"""Tool adapter: scheme.generate_and_compare -> SchemeService.

Fix #12: fail closed — raise on missing service/method, never return empty result.
"""

from __future__ import annotations

import uuid
from typing import Any

from cold_storage.modules.planning_agent.domain.errors import PlanningAgentError
from cold_storage.modules.planning_agent.domain.models import AgentToolResult


class SchemeGenerateCompareAdapter:
    def __init__(self, scheme_service: Any) -> None:
        self._service = scheme_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        if not hasattr(self._service, "generate_scheme_run"):
            raise PlanningAgentError(
                "SchemeService missing generate_scheme_run — cannot execute scheme generation"
            )
        project_id = arguments["project_id"]
        version_number = arguments["version_number"]
        result = self._service.generate_scheme_run(project_id, version_number)
        warnings: list[str] = []
        requires_review: bool = True
        output = {
            "source_tool": "scheme.generate_and_compare",
            "tool_version": "1.0.0",
            "result_id": str(uuid.uuid4()),
            "payload": {"scheme_result": result},
            "warnings": warnings,
            "requires_review": requires_review,
        }
        return AgentToolResult(
            tool_name="scheme.generate_and_compare",
            output=output,
        )
