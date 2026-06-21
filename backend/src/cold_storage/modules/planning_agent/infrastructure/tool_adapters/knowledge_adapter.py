"""Tool adapter: knowledge.search → KnowledgeService.search()."""

from __future__ import annotations

import uuid
from typing import Any

from cold_storage.modules.knowledge.application.service import KnowledgeService
from cold_storage.modules.planning_agent.domain.models import AgentToolResult


class KnowledgeSearchAdapter:
    def __init__(self, knowledge_service: KnowledgeService) -> None:
        self._service = knowledge_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        query = arguments["query"]
        top_k = arguments.get("top_k", 5)
        results = self._service.search(query=query, top_k=top_k)
        warnings: list[str] = []
        requires_review: bool = True
        output = {
            "source_tool": "knowledge.search",
            "tool_version": "1.0.0",
            "result_id": str(uuid.uuid4()),
            "payload": {"results": results, "count": len(results)},
            "warnings": warnings,
            "requires_review": requires_review,
        }
        return AgentToolResult(
            tool_name="knowledge.search",
            output=output,
        )
