"""Tool adapters that bridge agent tool calls to Application Service interfaces."""

from __future__ import annotations

from typing import Any, Protocol

from cold_storage.modules.planning_agent.domain.models import AgentToolResult


class ToolAdapter(Protocol):
    def execute(self, arguments: dict[str, Any]) -> AgentToolResult: ...
