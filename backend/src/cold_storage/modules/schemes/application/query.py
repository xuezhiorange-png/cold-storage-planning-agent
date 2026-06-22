"""Scheme query port — public read-only interface for scheme data.

This module defines the architecture boundary between the reports module
and the schemes module.  Reports consume scheme data through this port
without touching ORM models, Session objects, or infrastructure internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SchemeQueryPort(ABC):
    """Public read-only port for scheme data — no ORM/Session exposure."""

    @abstractmethod
    def get_completed_runs_for_project(self, project_id: str) -> list[dict[str, Any]]:
        """Return completed scheme runs for a project, newest first."""
        ...

    @abstractmethod
    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """Return candidate records for a given run."""
        ...


class SchemeQueryService(SchemeQueryPort):
    """Implementation backed by SchemeRepository."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def get_completed_runs_for_project(self, project_id: str) -> list[dict[str, Any]]:
        runs = self._repo.get_completed_runs_for_project(project_id)
        return [
            {
                "run_id": run.id,
                "project_id": run.project_id,
                "project_version_id": run.project_version_id,
                "status": run.status,
                "weight_set_id": run.weight_set_id,
                "generator_version": run.generator_version,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "recommended_scheme_code": run.recommended_scheme_code,
                "warning_messages": run.warning_messages,
            }
            for run in runs
        ]

    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        candidate_records = self._repo.get_candidates(run_id)
        return [
            {
                "id": c.id,
                "scheme_code": c.scheme_code,
                "profile_code": c.profile_code,
                "feasible": c.feasible,
                "rank": c.rank,
                "total_score": str(c.total_score) if c.total_score is not None else None,
                "score_breakdown_snapshot": c.score_breakdown_snapshot,
                "constraint_results": c.constraint_results,
                "result_snapshot": c.result_snapshot,
            }
            for c in candidate_records
        ]
