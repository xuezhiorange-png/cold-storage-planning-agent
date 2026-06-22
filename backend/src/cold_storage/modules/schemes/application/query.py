"""Scheme query port - public read-only interface for scheme data.

This module defines the architecture boundary between the reports module
and the schemes module.  Reports consume scheme data through this port
without touching ORM models, Session objects, or infrastructure internals.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from typing import Any


def _run_content_hash(run: Any, candidates: list[dict[str, Any]] | None = None) -> str:
    """Stable hash of scheme run content for provenance."""
    payload: dict[str, Any] = {
        "run_id": run.id,
        "recommended_scheme_code": run.recommended_scheme_code or "",
        "generator_version": run.generator_version or "",
    }
    if candidates:
        payload["candidates"] = [
            {
                "id": c.get("id", ""),
                "scheme_code": c.get("scheme_code", ""),
                "total_score": c.get("total_score"),
                "rank": c.get("rank"),
            }
            for c in sorted(candidates, key=lambda x: x.get("id", ""))
        ]
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class SchemeQueryPort(ABC):
    """Public read-only port for scheme data — no ORM/Session exposure."""

    @abstractmethod
    def get_completed_runs_for_project(self, project_id: str) -> list[dict[str, Any]]:
        """Return completed scheme runs for a project, newest first."""
        ...

    @abstractmethod
    def get_completed_runs_for_project_version(
        self, project_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        """Return completed scheme runs for a specific project version, newest first."""
        ...

    @abstractmethod
    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """Return candidate records for a given run."""
        ...


class SchemeQueryService(SchemeQueryPort):
    """Implementation backed by SchemeRepository."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def _serialize_run(
        self, run: Any, candidates: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "project_id": run.project_id,
            "project_version_id": run.project_version_id,
            "status": run.status,
            "weight_set_id": run.weight_set_id,
            "generator_version": run.generator_version,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "recommended_scheme_code": run.recommended_scheme_code,
            "warning_messages": run.warning_messages,
            "persisted_content_hash": run.content_hash or _run_content_hash(run, candidates),
        }

    def get_completed_runs_for_project(self, project_id: str) -> list[dict[str, Any]]:
        runs = self._repo.get_completed_runs_for_project(project_id)
        result: list[dict[str, Any]] = []
        for run in runs:
            # Always load candidates so hash fallback (when content_hash is NULL)
            # uses the same inputs as generation-time computation.
            candidate_records = self._repo.get_candidates(run.id)
            candidate_dicts = [
                {
                    "id": c.scheme_code,
                    "scheme_code": c.scheme_code,
                    "total_score": str(c.total_score) if c.total_score else None,
                    "rank": c.rank,
                }
                for c in candidate_records
            ]
            result.append(self._serialize_run(run, candidate_dicts))
        return result

    def get_completed_runs_for_project_version(
        self, project_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        runs = self._repo.get_completed_runs_for_project(project_id)
        filtered = [r for r in runs if r.project_version_id == version_id]
        result: list[dict[str, Any]] = []
        for run in filtered:
            candidate_records = self._repo.get_candidates(run.id)
            # Use scheme_code as hash id for consistency with service.py
            # (SchemeCandidate domain model has no id, only scheme_code)
            candidate_dicts = [
                {
                    "id": c.scheme_code,
                    "scheme_code": c.scheme_code,
                    "total_score": str(c.total_score) if c.total_score else None,
                    "rank": c.rank,
                }
                for c in candidate_records
            ]
            result.append(self._serialize_run(run, candidate_dicts))
        return result

    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        candidate_records = self._repo.get_candidates(run_id)
        return [
            {
                # Use scheme_code as the candidate ID for hash consistency.
                # Hash computation (compute_scheme_source_hash / _run_content_hash)
                # expects scheme_code, not DB UUIDs.  Using c.id here would cause
                # a permanent mismatch with the stored content_hash.
                "id": c.scheme_code,
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
