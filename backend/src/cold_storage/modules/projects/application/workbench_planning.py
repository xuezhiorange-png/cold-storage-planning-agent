"""Persisted workbench planning — five-stage chain plus equipment/power table."""

from __future__ import annotations

from typing import Any, Protocol

from cold_storage.modules.calculations.domain.investment import InvestmentEstimator
from cold_storage.modules.calculations.domain.zone_planning import ColdRoomZonePlanner
from cold_storage.modules.planning.application.service import (
    build_investment_from_zone_result,
    build_power_configuration,
    build_zone_plan_from_inputs,
    planning_run_response,
    zone_number,
)
from cold_storage.modules.projects.application.workbench_result_mapping import (
    new_calculation_result_to_legacy,
    power_configuration_to_legacy,
)
from cold_storage.modules.projects.application.workbench_stage_bridge import (
    WorkbenchStageBridgeError,
    build_cooling_load_raw_inputs,
    build_equipment_raw_inputs,
    build_power_raw_inputs,
    run_cooling_load_stage,
    run_equipment_stage,
    run_power_stage,
)
from cold_storage.modules.projects.domain.models import SaveInputsResult


class WorkbenchProjectService(Protocol):
    def get_version(self, project_id: str, version_number: int) -> Any: ...

    def save_inputs(
        self, project_id: str, version_number: int, inputs: dict[str, object], actor: str
    ) -> SaveInputsResult: ...

    def record_calculation(
        self,
        project_id: str,
        version_number: int,
        calculation_result: Any,
        actor: str,
    ) -> dict[str, Any]: ...


class WorkbenchPlanningError(Exception):
    """Fail-closed workbench planning error surfaced to the API."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def run_persisted_workbench_planning(
    *,
    project_service: WorkbenchProjectService,
    project_id: str,
    version_number: int,
    inputs: dict[str, Any],
    zone_planner: ColdRoomZonePlanner,
    investment_estimator: InvestmentEstimator,
    actor: str = "api",
) -> dict[str, Any]:
    """Execute and persist the five-stage workbench chain for a project version.

    Persists zone, cooling_load, equipment, installed_power, investment_estimate,
    and the workbench power/equipment table (`power_configuration`). Returns the
    same response envelope as the legacy planning-run API.
    """
    zone_result = build_zone_plan_from_inputs(inputs, zone_planner)
    if not zone_result.success:
        raise WorkbenchPlanningError(
            "WORKBENCH_ZONE_STAGE_FAILED",
            "冷间分区规划计算失败",
            {"calculator_name": zone_result.calculator_name},
        )

    zones = zone_result.result.get("zones", [])
    if not isinstance(zones, list) or not zones:
        raise WorkbenchPlanningError(
            "WORKBENCH_ZONE_RESULTS_MISSING",
            "冷间分区规划结果为空",
        )

    try:
        cooling_raw = build_cooling_load_raw_inputs(zones, inputs)
        cooling_result = run_cooling_load_stage(cooling_raw)
        if not cooling_result.success:
            raise WorkbenchPlanningError(
                "WORKBENCH_COOLING_STAGE_FAILED",
                "制冷负荷计算失败",
            )

        equipment_raw = build_equipment_raw_inputs(cooling_result, zones)
        equipment_result = run_equipment_stage(equipment_raw)
        if not equipment_result.success:
            raise WorkbenchPlanningError(
                "WORKBENCH_EQUIPMENT_STAGE_FAILED",
                "设备选型计算失败",
            )

        power_raw = build_power_raw_inputs(equipment_result, cooling_result)
        power_result = run_power_stage(power_raw)
        if not power_result.success:
            raise WorkbenchPlanningError(
                "WORKBENCH_POWER_STAGE_FAILED",
                "装机功率计算失败",
            )
    except WorkbenchStageBridgeError as exc:
        raise WorkbenchPlanningError(exc.code, exc.message, exc.details) from exc

    total_area = round(sum(zone_number(zone, "required_area_m2") for zone in zones), 2)
    power_configuration = build_power_configuration(
        zones,
        float(inputs["daily_inbound_mass_kg"]),
        total_area,
    )
    investment_result = build_investment_from_zone_result(
        zone_result,
        investment_estimator,
        float(power_configuration["total_installed_power_kw"]),
    )
    if not investment_result.success:
        raise WorkbenchPlanningError(
            "WORKBENCH_INVESTMENT_STAGE_FAILED",
            "投资测算计算失败",
        )

    project_service.record_calculation(project_id, version_number, zone_result, actor=actor)
    project_service.record_calculation(
        project_id,
        version_number,
        new_calculation_result_to_legacy(cooling_result),
        actor=actor,
    )
    project_service.record_calculation(
        project_id,
        version_number,
        new_calculation_result_to_legacy(equipment_result),
        actor=actor,
    )
    project_service.record_calculation(
        project_id,
        version_number,
        new_calculation_result_to_legacy(power_result),
        actor=actor,
    )
    project_service.record_calculation(project_id, version_number, investment_result, actor=actor)
    project_service.record_calculation(
        project_id,
        version_number,
        power_configuration_to_legacy(power_configuration),
        actor=actor,
    )

    return planning_run_response(inputs, zone_result, investment_result)
