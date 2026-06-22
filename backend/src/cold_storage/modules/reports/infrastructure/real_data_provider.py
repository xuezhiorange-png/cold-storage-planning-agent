"""Real ReportDataProvider — reads from actual application services.

Uses public query ports (SchemeQueryPort, KnowledgeQueryPort) instead of
directly accessing ORM models or Session objects of other modules.  This
enforces the architecture boundary: the reports module never touches
infrastructure internals of schemes or knowledge.
"""

from __future__ import annotations

from typing import Any

from cold_storage.modules.reports.application.assembler import ReportDataProvider
from cold_storage.modules.reports.domain.canonical import content_hash


class RealReportDataProvider(ReportDataProvider):
    """Reads persisted data from actual module services and repositories.

    Constructor accepts any combination of services/ports; missing ones
    are silently skipped (returns empty data for that section).
    """

    def __init__(
        self,
        *,
        project_service: Any | None = None,
        calculation_service: Any | None = None,
        scheme_query: Any | None = None,
        knowledge_query: Any | None = None,
    ) -> None:
        self._project_service = project_service
        self._calculation_service = calculation_service
        self._scheme_query = scheme_query
        self._knowledge_query = knowledge_query

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

    def get_calculation_results(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        """Read calculation results from CoreCalculationService.

        Returns a list of section-keyed dicts with source metadata.
        """
        if self._calculation_service is None:
            return []
        try:
            result = self._calculation_service.get_orchestrated_result(project_id, version_id)
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

            sections.append(
                {
                    "section_key": section_key,
                    "result_id": result_id,
                    "tool_name": tool_name,
                    "tool_version": tool_version,
                    "data": result_data,
                    # Source verification metadata
                    "tool_call_status": "completed",
                }
            )

        return sections

    def get_scheme_results(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        """Read scheme comparison results via SchemeQueryPort.

        Returns the latest completed scheme run with its candidates.
        """
        if self._scheme_query is None:
            return None
        try:
            runs = self._scheme_query.get_completed_runs_for_project(project_id)
            if not runs:
                return None

            latest_run = runs[0]  # Already ordered by created_at desc

            candidates = self._scheme_query.get_candidates_for_run(latest_run["run_id"])

            schemes: list[dict[str, Any]] = []
            for c in candidates:
                schemes.append(
                    {
                        "scheme_id": c["id"],
                        "name": c.get("scheme_code", c["id"]),
                        "total_score": c.get("total_score", "0"),
                        "rank": c.get("rank", 0),
                    }
                )

            return {
                "run_id": latest_run["run_id"],
                "status": latest_run["status"],
                "schemes": schemes,
                "tool_call_status": "completed",
            }
        except Exception:  # noqa: BLE001
            return None

    def get_knowledge_documents(self) -> list[dict[str, Any]]:
        """Read approved knowledge documents via KnowledgeQueryPort."""
        if self._knowledge_query is None:
            return []
        try:
            docs: list[dict[str, Any]] = self._knowledge_query.get_approved_documents()
            return docs
        except Exception:  # noqa: BLE001
            return []

    def get_agent_sessions(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        """Read agent session/tool-call data for provenance.

        Currently returns empty — agent session tracking is not yet
        implemented as a separate module.
        """
        return []
