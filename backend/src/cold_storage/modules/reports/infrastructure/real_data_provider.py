"""Real ReportDataProvider — reads from actual application services and repositories.

Replaces the abstract ReportDataProvider with one that connects to
Task 5 (calculations), Task 7 (schemes), Task 8 (knowledge), and
Task 3 (projects) services/repositories.

No LLM calls, no recalculation.  Only reads persisted data.
"""

from __future__ import annotations

from typing import Any

from cold_storage.modules.reports.application.assembler import ReportDataProvider
from cold_storage.modules.reports.domain.canonical import content_hash


class RealReportDataProvider(ReportDataProvider):
    """Reads persisted data from actual module services and repositories.

    Constructor accepts any combination of services/repos; missing ones
    are silently skipped (returns empty data for that section).
    """

    def __init__(
        self,
        *,
        project_service: Any | None = None,
        calculation_service: Any | None = None,
        scheme_repository: Any | None = None,
        knowledge_repository: Any | None = None,
    ) -> None:
        self._project_service = project_service
        self._calculation_service = calculation_service
        self._scheme_repo = scheme_repository
        self._knowledge_repo = knowledge_repository

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        """Read project metadata from ProjectService."""
        if self._project_service is None:
            return None
        try:
            project = self._project_service.get_project(project_id)
            return {
                "name": getattr(project, "name", ""),
                "location": getattr(project, "location", ""),
                "description": getattr(project, "description", ""),
                "product_category": getattr(project, "product_category", ""),
                "code": getattr(project, "code", ""),
            }
        except (KeyError, AttributeError):
            return None

    def get_project_version(self, version_id: str) -> dict[str, Any] | None:
        """Read project version data."""
        if self._project_service is None:
            return None
        try:
            # ProjectService stores versions in project.current_version
            # We need to search across all projects for the version
            for project in self._project_service.list_projects():
                ver = getattr(project, "current_version", None)
                if ver is not None and getattr(ver, "id", None) == version_id:
                    return {
                        "id": ver.id,
                        "version_number": getattr(ver, "version_number", 0),
                        "status": getattr(ver, "status", ""),
                    }
        except (AttributeError, TypeError):
            pass
        return None

    def get_calculation_results(
        self, project_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        """Read calculation results from CoreCalculationService.

        Returns a list of section-keyed dicts with source metadata.
        """
        if self._calculation_service is None:
            return []
        try:
            result = self._calculation_service.get_orchestrated_result(
                project_id, version_id
            )
        except (AttributeError, KeyError):
            return []
        if result is None:
            return []

        sections: list[dict[str, Any]] = []

        # Map each calculator result to a section
        calculator_map = [
            ("cooling_load", "cooling_load_result", "cooling_load_calculator"),
            ("equipment_selection", "equipment_result", "equipment_calculator"),
            ("electrical_and_energy", "power_result", "power_calculator"),
            ("throughput_inventory_area", "throughput_result", "throughput_calculator"),
        ]

        for section_key, attr_name, tool_name in calculator_map:
            calc_result = getattr(result, attr_name, None)
            if calc_result is None:
                continue
            # Extract the result dict and source metadata
            result_data = getattr(calc_result, "result", {})
            tool_version = getattr(calc_result, "calculator_version", "1.0.0")
            result_id = getattr(calc_result, "id", None)
            if result_id is None:
                # Generate a deterministic ID from calculator name + version
                result_id = f"{tool_name}-{tool_version}-{content_hash(result_data)}"

            sections.append({
                "section_key": section_key,
                "result_id": result_id,
                "tool_name": tool_name,
                "tool_version": tool_version,
                "data": result_data,
                # Source verification metadata
                "tool_call_status": "completed",
            })

        return sections

    def get_scheme_results(
        self, project_id: str, version_id: str
    ) -> dict[str, Any] | None:
        """Read scheme comparison results from SchemeRepository.

        Returns the latest completed scheme run with its candidates.
        """
        if self._scheme_repo is None:
            return None
        try:
            # Find the latest completed run for this project
            from sqlalchemy import select

            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeCandidateRecord,
                SchemeRunRecord,
            )

            stmt = (
                select(SchemeRunRecord)
                .where(
                    SchemeRunRecord.project_id == project_id,
                    SchemeRunRecord.status == "completed",
                )
                .order_by(SchemeRunRecord.created_at.desc())
                .limit(1)
            )
            run_rec = self._scheme_repo._session.execute(stmt).scalar_one_or_none()
            if run_rec is None:
                return None

            # Get candidates
            cand_stmt = (
                select(SchemeCandidateRecord)
                .where(SchemeCandidateRecord.scheme_run_id == run_rec.id)
                .order_by(SchemeCandidateRecord.rank)
            )
            candidates = self._scheme_repo._session.execute(cand_stmt).scalars().all()

            schemes = []
            for c in candidates:
                schemes.append({
                    "scheme_id": c.id,
                    "name": getattr(c, "name", c.id),
                    "total_score": str(getattr(c, "total_score", "0")),
                    "rank": getattr(c, "rank", 0),
                })

            return {
                "run_id": run_rec.id,
                "status": run_rec.status,
                "schemes": schemes,
                "tool_call_status": "completed",
            }
        except (AttributeError, Exception):
            return None

    def get_agent_sessions(
        self, project_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        """Read agent session/tool-call data for provenance.

        Currently returns empty — agent session tracking is not yet
        implemented as a separate module.
        """
        return []
