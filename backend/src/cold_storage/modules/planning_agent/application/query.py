"""Agent session query port — public read-only interface for agent provenance.

This module defines the architecture boundary between the reports module
and the planning_agent module.  Reports consume agent session data
through this port without touching ORM models, Session objects, or
infrastructure internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AgentSessionQueryPort(ABC):
    """Public read-only port for agent session/tool-call data."""

    @abstractmethod
    def get_sessions_for_project(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        """Return agent sessions for a project version, newest first."""
        ...

    @abstractmethod
    def get_tool_calls_for_session(self, session_id: str) -> list[dict[str, Any]]:
        """Return tool calls for a session."""
        ...

    @abstractmethod
    def get_turns_for_session(self, session_id: str) -> list[dict[str, Any]]:
        """Return turns for a session."""
        ...


class AgentSessionQueryService(AgentSessionQueryPort):
    """Implementation backed by AgentRepository."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def get_sessions_for_project(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        # AgentRepository doesn't have a project-filtered query yet.
        # Use list_sessions and filter in-memory (small N).
        sessions = self._repo.list_sessions(limit=100)
        result = []
        for s in sessions:
            if s.project_id == project_id and s.project_version_id == version_id:
                result.append(
                    {
                        "session_id": s.id,
                        "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                        "title": s.title,
                        "created_by": s.created_by,
                        "created_at": s.created_at.isoformat()
                        if hasattr(s.created_at, "isoformat")
                        else str(s.created_at),
                    }
                )
        return result

    def get_tool_calls_for_session(self, session_id: str) -> list[dict[str, Any]]:
        tool_calls = self._repo.list_tool_calls(session_id)
        results: list[dict[str, Any]] = []
        for tc in tool_calls:
            # Extract knowledge_revision_ids from the tool call's persisted result
            result_data = tc.result
            knowledge_ids: list[str] = []
            if isinstance(result_data, dict):
                knowledge_ids = result_data.get("knowledge_revision_ids", [])
            elif isinstance(result_data, list):
                knowledge_ids = [r for r in result_data if isinstance(r, str)]

            results.append(
                {
                    "id": tc.id,
                    "tool_name": tc.tool_name,
                    "tool_version": tc.tool_version,
                    "result_id": tc.result_reference or "",
                    "persisted_content_hash": getattr(tc, "result_hash", None) or "",
                    "tool_call_status": tc.status.value
                    if hasattr(tc.status, "value")
                    else str(tc.status),
                    "arguments_sha256": tc.arguments_sha256,
                    "completed_at": tc.completed_at.isoformat()
                    if tc.completed_at and hasattr(tc.completed_at, "isoformat")
                    else None,
                    "knowledge_revision_ids": knowledge_ids,
                }
            )
        return results

    def get_turns_for_session(self, session_id: str) -> list[dict[str, Any]]:
        turns = self._repo.list_turns(session_id)
        return [
            {
                "id": t.id,
                "turn_number": t.turn_number,
                "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                "model_provider": t.model_provider,
                "model_name": t.model_name,
                "prompt_version": t.prompt_version,
                "completed_at": t.completed_at.isoformat()
                if t.completed_at and hasattr(t.completed_at, "isoformat")
                else None,
            }
            for t in turns
        ]
