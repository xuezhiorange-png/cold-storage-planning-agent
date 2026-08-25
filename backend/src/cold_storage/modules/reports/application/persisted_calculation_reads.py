"""Read persisted canonical calculation rows for report assembly (V0.5 P3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cold_storage.modules.orchestration.domain.consumer_bindings import (
    CANONICAL_STAGE_ORDER,
    STAGE_TO_CALCULATOR_NAME,
    resolve_canonical_calculator_name,
    stage_for_canonical_calculator,
)
from cold_storage.modules.workflow.application.canonical_calculation_reads import (
    index_canonical_calculation_runs,
)

CANONICAL_STAGE_TO_REPORT_ATTR: dict[str, str] = {
    "zone": "throughput_result",
    "cooling_load": "cooling_load_result",
    "equipment": "equipment_result",
    "power": "power_result",
}


class PersistedCalculationQueryPort(Protocol):
    def get_orchestrated_result(
        self, project_id: str, project_version_id: str
    ) -> OrchestratedCalculationResult | None:
        """Return canonical persisted calculation sections for report assembly."""


@dataclass
class CalculationSectionView:
    id: str
    calculator_name: str
    calculator_version: str
    result: dict[str, Any]
    content_hash: str | None = None
    tool_call_status: str | None = None


@dataclass
class OrchestratedCalculationResult:
    throughput_result: CalculationSectionView | None = None
    cooling_load_result: CalculationSectionView | None = None
    equipment_result: CalculationSectionView | None = None
    power_result: CalculationSectionView | None = None


class ProjectServicePersistedCalculationQuery:
    """Application query port backed by ProjectService list_calculations."""

    def __init__(self, project_service: Any) -> None:
        self._project_service = project_service

    def get_orchestrated_result(
        self, project_id: str, project_version_id: str
    ) -> OrchestratedCalculationResult | None:
        version = self._resolve_version(project_id, project_version_id)
        if version is None:
            return None
        calculations = self._project_service.list_calculations(
            project_id,
            int(version.version_number),
        )
        indexed = index_canonical_calculation_runs(
            calculations,
            project_id=project_id,
            project_version_id=project_version_id,
        )
        if not indexed:
            return None

        sections: dict[str, CalculationSectionView | None] = {
            "throughput_result": None,
            "cooling_load_result": None,
            "equipment_result": None,
            "power_result": None,
        }
        for stage in CANONICAL_STAGE_ORDER:
            if stage == "investment":
                continue
            calculator_name = STAGE_TO_CALCULATOR_NAME[stage]
            record = indexed.get(calculator_name)
            attr_name = CANONICAL_STAGE_TO_REPORT_ATTR[stage]
            if record is None:
                sections[attr_name] = None
                continue
            snapshot = record.get("result_snapshot")
            if not isinstance(snapshot, dict):
                snapshot = {}
            sections[attr_name] = CalculationSectionView(
                id=str(record.get("calculation_id") or record.get("id", "")),
                calculator_name=calculator_name,
                calculator_version=str(record.get("calculator_version", "1.0.0")),
                result=snapshot,
                content_hash=str(record.get("result_hash")) if record.get("result_hash") else None,
                tool_call_status=None,
            )
        return OrchestratedCalculationResult(**sections)

    def _resolve_version(self, project_id: str, project_version_id: str) -> Any | None:
        project = self._project_service.get_project(project_id)
        for version in project.versions:
            if version.id == project_version_id:
                return version
        current = getattr(project, "current_version", None)
        if current is not None and current.id == project_version_id:
            return current
        return None


def resolve_report_stage_for_calculator(calculator_name: str) -> str | None:
    stage = stage_for_canonical_calculator(
        resolve_canonical_calculator_name(calculator_name) or calculator_name
    )
    if stage is None or stage == "investment":
        return None
    return stage
