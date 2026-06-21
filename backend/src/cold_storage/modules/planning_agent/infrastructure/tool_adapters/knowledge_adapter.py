"""Tool adapter: knowledge.search → KnowledgeService.search()."""

from __future__ import annotations

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
        return AgentToolResult(
            tool_name="knowledge.search",
            output={"results": results, "count": len(results)},
            requires_review=True,
        )
