from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from cold_storage.bootstrap.demo_overview import build_demo_overview
from cold_storage.bootstrap.dependencies import get_agent_service, get_project_service
from cold_storage.bootstrap.logging import configure_logging
from cold_storage.modules.calculations.domain.inputs import ThroughputInput
from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)
from cold_storage.modules.calculations.domain.service import CalculationService
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.planning_agent.application.agent_service import PlanningAgentService
from cold_storage.modules.projects.application.service import ProjectService

ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
AgentServiceDep = Annotated[PlanningAgentService, Depends(get_agent_service)]


class ProjectCreateRequest(BaseModel):
    name: str
    location: str
    product_category: str


class VersionCreateRequest(BaseModel):
    change_summary: str


class InputsRequest(BaseModel):
    inputs: dict[str, Any]


class CalculateRequest(BaseModel):
    calculators: list[str] = ["throughput"]


class PlanningRunRequest(BaseModel):
    inputs: dict[str, Any] | None = None
    daily_inbound_mass_kg: float | None = None
    working_time_h_per_day: float | None = None
    utilization_factor: float | None = None
    storage_days: float | None = None
    finished_storage_days: float | None = None
    packaging_storage_days: float | None = None
    reserve_factor: float | None = None
    precooling_required_ratio: float | None = None
    raw_holding_hours: float | None = None
    storage_position_capacity_kg: float | None = None
    secondary_fruit_ratio: float | None = None
    frozen_fruit_ratio: float | None = None
    frozen_storage_days: float | None = None
    precooling_position_daily_capacity_kg: float | None = None
    primary_precooling_pallet_weight_kg: float | None = None
    primary_precooling_hours_per_pallet: float | None = None
    primary_precooling_working_hours_per_day: float | None = None
    secondary_precooling_pallet_weight_kg: float | None = None
    secondary_precooling_hours_per_pallet: float | None = None
    secondary_precooling_working_hours_per_day: float | None = None
    raw_storage_ratio: float | None = None
    raw_fruit_pallet_weight_kg: float | None = None
    finished_goods_pallet_weight_kg: float | None = None
    frozen_goods_pallet_weight_kg: float | None = None
    secondary_fruit_area_ratio: float | None = None
    main_packaging_storage_days: float | None = None
    auxiliary_packaging_storage_days: float | None = None
    packaging_area_factor: float | None = None


class AgentMessageRequest(BaseModel):
    message: str


def create_app(project_service: ProjectService | None = None) -> FastAPI:
    configure_logging()
    app = FastAPI(title="Cold Storage Planning Agent V1")
    calculator = CalculationService()
    zone_planner = ColdRoomZonePlanner()
    investment_estimator = InvestmentEstimator()
    if project_service is not None:
        app.dependency_overrides[get_project_service] = lambda: project_service

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/v1/demo/overview")
    def demo_overview() -> dict[str, Any]:
        return build_demo_overview()

    @app.post("/api/v1/demo/planning-run")
    def demo_planning_run(request: PlanningRunRequest) -> dict[str, Any]:
        inputs = _inputs_from_planning_request(request, _demo_inputs())
        zone_result = _build_zone_plan_from_inputs(inputs, zone_planner)
        total_area = round(
            sum(_zone_number(zone, "required_area_m2") for zone in zone_result.result["zones"]),
            2,
        )
        power_configuration = _build_power_configuration(
            zone_result.result["zones"],
            _as_float(inputs["daily_inbound_mass_kg"]),
            total_area,
        )
        investment_result = _build_investment_from_zone_result(
            zone_result,
            investment_estimator,
            _as_float(power_configuration["total_installed_power_kw"]),
        )
        return _planning_run_response(inputs, zone_result, investment_result)

    @app.post("/api/v1/projects")
    def create_project(
        request: ProjectCreateRequest,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        project = service.create_project(request.name, request.location, request.product_category)
        version = service.create_version(project.id, "初始草稿版本")
        return {
            "id": project.id,
            "code": project.code,
            "current_version_number": version.version_number,
        }

    @app.get("/api/v1/projects")
    def list_projects(service: ProjectServiceDep) -> list[dict[str, Any]]:
        return [
            {
                "id": project.id,
                "code": project.code,
                "name": project.name,
                "location": project.location,
                "product_category": project.product_category,
                "current_version_number": project.current_version_number,
            }
            for project in service.list_projects()
        ]

    @app.get("/api/v1/projects/{project_id}")
    def get_project(project_id: str, service: ProjectServiceDep) -> dict[str, Any]:
        project = service.get_project(project_id)
        return {
            "id": project.id,
            "code": project.code,
            "name": project.name,
            "location": project.location,
            "product_category": project.product_category,
            "status": project.status,
            "current_version_number": project.current_version_number,
        }

    @app.post("/api/v1/projects/{project_id}/versions")
    def create_version(
        project_id: str,
        request: VersionCreateRequest,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        version = service.create_version(project_id, request.change_summary)
        return {
            "id": version.id,
            "version_number": version.version_number,
            "status": version.status,
        }

    @app.get("/api/v1/projects/{project_id}/versions")
    def list_versions(project_id: str, service: ProjectServiceDep) -> list[dict[str, Any]]:
        return [
            {
                "id": version.id,
                "version_number": version.version_number,
                "change_summary": version.change_summary,
                "status": version.status,
                "input_snapshot": version.input_snapshot,
            }
            for version in service.list_versions(project_id)
        ]

    @app.get("/api/v1/projects/{project_id}/versions/{version}")
    def get_version(project_id: str, version: int, service: ProjectServiceDep) -> dict[str, Any]:
        project_version = service.get_version(project_id, version)
        return {
            "id": project_version.id,
            "version_number": project_version.version_number,
            "change_summary": project_version.change_summary,
            "status": project_version.status,
            "input_snapshot": project_version.input_snapshot,
        }

    @app.post("/api/v1/projects/{project_id}/versions/{version}/approve")
    def approve_version(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        project_version = service.approve_version(project_id, version)
        return {"id": project_version.id, "status": project_version.status}

    @app.put("/api/v1/projects/{project_id}/versions/{version}/inputs")
    def save_inputs(
        project_id: str,
        version: int,
        request: InputsRequest,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        result = service.save_inputs(project_id, version, request.inputs, actor="api")
        if not result.success:
            return {
                "error": {
                    "code": result.error_code,
                    "message": "项目版本已锁定",
                    "details": {},
                }
            }
        return {"success": True}

    @app.post("/api/v1/projects/{project_id}/versions/{version}/validate")
    def validate_inputs(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, object]:
        project_version = service.get_version(project_id, version)
        return service.validate_inputs(project_version.input_snapshot)

    @app.post("/api/v1/projects/{project_id}/versions/{version}/calculate")
    def calculate(
        project_id: str,
        version: int,
        request: CalculateRequest,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        if "throughput" not in request.calculators and "all" not in request.calculators:
            return {
                "error": {
                    "code": "UNSUPPORTED_CALCULATOR",
                    "message": "V1.1 API baseline currently supports throughput calculation",
                    "details": {"calculators": request.calculators},
                }
            }
        project_version = service.get_version(project_id, version)
        inputs = project_version.input_snapshot
        result = calculator.run_throughput(
            ThroughputInput(
                daily_inbound_mass_kg=_as_float(inputs["daily_inbound_mass_kg"]),
                working_time_h_per_day=_as_float(inputs["working_time_h_per_day"]),
                utilization_factor=_as_float(inputs["utilization_factor"]),
            )
        )
        service.record_calculation(project_id, version, result, actor="api")

        return asdict(result)

    @app.get("/api/v1/projects/{project_id}/versions/{version}/calculations")
    def list_calculations(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> list[dict[str, Any]]:
        return service.list_calculations(project_id, version)

    @app.post("/api/v1/projects/{project_id}/versions/{version}/zone-plan")
    def plan_cold_room_zones(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        result = _build_zone_plan(project_id, version, service, zone_planner)
        service.record_calculation(project_id, version, result, actor="api")

        return asdict(result)

    @app.post("/api/v1/projects/{project_id}/versions/{version}/investment-estimate")
    def estimate_investment(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        zone_result = _build_zone_plan(project_id, version, service, zone_planner)
        zones = zone_result.result["zones"]
        if not isinstance(zones, list):
            raise ValueError("zone plan result must contain zones")
        total_area = sum(_zone_number(zone, "required_area_m2") for zone in zones)
        project_version = service.get_version(project_id, version)
        power_configuration = _build_power_configuration(
            zones,
            _as_float(project_version.input_snapshot["daily_inbound_mass_kg"]),
            total_area,
        )
        refrigerated_area = sum(
            _zone_number(zone, "required_area_m2")
            for zone in zones
            if isinstance(zone, dict) and zone.get("temperature_band") != "常温"
        )
        frozen_area = sum(
            _zone_number(zone, "required_area_m2")
            for zone in zones
            if isinstance(zone, dict) and zone.get("temperature_band") == "-18℃"
        )
        position_count = sum(int(_zone_number(zone, "position_count")) for zone in zones)
        result = investment_estimator.estimate(
            InvestmentEstimateInput(
                total_area_m2=round(total_area, 2),
                refrigerated_area_m2=round(refrigerated_area, 2),
                frozen_area_m2=round(frozen_area, 2),
                position_count=position_count,
                total_power_kw=_as_float(power_configuration["total_installed_power_kw"]),
            )
        )
        service.record_calculation(project_id, version, result, actor="api")
        return asdict(result)

    @app.post("/api/v1/projects/{project_id}/versions/{version}/planning-run")
    def run_project_planning(
        project_id: str,
        version: int,
        request: PlanningRunRequest,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        project_version = service.get_version(project_id, version)
        inputs = _inputs_from_planning_request(request, project_version.input_snapshot)
        if request.inputs or _flat_planning_input(request):
            save_result = service.save_inputs(project_id, version, inputs, actor="api")
            if not save_result.success:
                return {
                    "error": {
                        "code": save_result.error_code,
                        "message": "项目版本已锁定",
                        "details": {},
                    }
                }
        zone_result = _build_zone_plan_from_inputs(inputs, zone_planner)
        total_area = round(
            sum(_zone_number(zone, "required_area_m2") for zone in zone_result.result["zones"]),
            2,
        )
        power_configuration = _build_power_configuration(
            zone_result.result["zones"],
            _as_float(inputs["daily_inbound_mass_kg"]),
            total_area,
        )
        investment_result = _build_investment_from_zone_result(
            zone_result,
            investment_estimator,
            _as_float(power_configuration["total_installed_power_kw"]),
        )
        service.record_calculation(project_id, version, zone_result, actor="api")
        service.record_calculation(project_id, version, investment_result, actor="api")
        return _planning_run_response(inputs, zone_result, investment_result)

    @app.get("/api/v1/projects/{project_id}/audit-events")
    def list_audit_events(project_id: str, service: ProjectServiceDep) -> list[dict[str, Any]]:
        return service.list_audit_events(project_id)

    @post_agent_message(app)
    def agent_message(
        request: AgentMessageRequest,
        service: AgentServiceDep,
    ) -> dict[str, Any]:
        response = service.handle_message(request.message)
        return response.__dict__

    return app


def post_agent_message(app: FastAPI) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    return app.post("/api/v1/agent/sessions/{session_id}/messages")


def _as_float(value: object) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    raise ValueError("value must be numeric")


def _build_zone_plan(
    project_id: str,
    version: int,
    service: ProjectService,
    zone_planner: ColdRoomZonePlanner,
) -> Any:
    project_version = service.get_version(project_id, version)
    return _build_zone_plan_from_inputs(project_version.input_snapshot, zone_planner)


def _build_zone_plan_from_inputs(
    inputs: dict[str, Any],
    zone_planner: ColdRoomZonePlanner,
) -> Any:
    return zone_planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=_as_float(inputs["daily_inbound_mass_kg"]),
            working_time_h_per_day=_as_float(inputs["working_time_h_per_day"]),
            finished_storage_days=_as_float(
                inputs.get("finished_storage_days", inputs.get("storage_days"))
            ),
            packaging_storage_days=_as_float(inputs.get("packaging_storage_days", 7)),
            precooling_required_ratio=_as_float(inputs.get("precooling_required_ratio", 0.8)),
            raw_holding_hours=_as_float(inputs.get("raw_holding_hours", 6.6666666667)),
            storage_position_capacity_kg=_as_float(inputs.get("storage_position_capacity_kg", 400)),
            secondary_fruit_ratio=_as_float(inputs.get("secondary_fruit_ratio", 0.08)),
            frozen_fruit_ratio=_as_float(inputs.get("frozen_fruit_ratio", 0.10)),
            frozen_storage_days=_as_float(inputs.get("frozen_storage_days", 5)),
            precooling_position_daily_capacity_kg=_as_float(
                inputs.get("precooling_position_daily_capacity_kg", 1250)
            ),
            primary_precooling_pallet_weight_kg=_as_float(
                inputs.get("primary_precooling_pallet_weight_kg", 220)
            ),
            primary_precooling_hours_per_pallet=_as_float(
                inputs.get("primary_precooling_hours_per_pallet", 1)
            ),
            primary_precooling_working_hours_per_day=_as_float(
                inputs.get("primary_precooling_working_hours_per_day", 6)
            ),
            secondary_precooling_pallet_weight_kg=_as_float(
                inputs.get("secondary_precooling_pallet_weight_kg", 400)
            ),
            secondary_precooling_hours_per_pallet=_as_float(
                inputs.get("secondary_precooling_hours_per_pallet", 2)
            ),
            secondary_precooling_working_hours_per_day=_as_float(
                inputs.get("secondary_precooling_working_hours_per_day", 16)
            ),
            raw_storage_ratio=_as_float(inputs.get("raw_storage_ratio", 0.40)),
            raw_fruit_pallet_weight_kg=_as_float(inputs.get("raw_fruit_pallet_weight_kg", 220)),
            finished_goods_pallet_weight_kg=_as_float(
                inputs.get("finished_goods_pallet_weight_kg", 400)
            ),
            frozen_goods_pallet_weight_kg=_as_float(
                inputs.get("frozen_goods_pallet_weight_kg", 600)
            ),
            secondary_fruit_area_ratio=_as_float(inputs.get("secondary_fruit_area_ratio", 0.80)),
            main_packaging_storage_days=_as_float(
                inputs.get(
                    "main_packaging_storage_days",
                    inputs.get("packaging_storage_days", 3),
                )
            ),
            auxiliary_packaging_storage_days=_as_float(
                inputs.get("auxiliary_packaging_storage_days", 30)
            ),
            packaging_area_factor=_as_float(inputs.get("packaging_area_factor", 1.5)),
        )
    )


def _zone_number(zone: object, key: str) -> float:
    if not isinstance(zone, dict):
        raise TypeError("zone must be a mapping")
    value = zone[key]
    if isinstance(value, int | float):
        return float(value)
    raise TypeError(f"zone field {key} must be numeric")


def _build_investment_from_zone_result(
    zone_result: Any,
    investment_estimator: InvestmentEstimator,
    total_power_kw: float,
) -> Any:
    zones = zone_result.result["zones"]
    if not isinstance(zones, list):
        raise ValueError("zone plan result must contain zones")
    total_area = sum(_zone_number(zone, "required_area_m2") for zone in zones)
    refrigerated_area = sum(
        _zone_number(zone, "required_area_m2")
        for zone in zones
        if isinstance(zone, dict) and zone.get("temperature_band") != "常温"
    )
    frozen_area = sum(
        _zone_number(zone, "required_area_m2")
        for zone in zones
        if isinstance(zone, dict) and zone.get("temperature_band") == "-18℃"
    )
    position_count = sum(int(_zone_number(zone, "position_count")) for zone in zones)
    return investment_estimator.estimate(
        InvestmentEstimateInput(
            total_area_m2=round(total_area, 2),
            refrigerated_area_m2=round(refrigerated_area, 2),
            frozen_area_m2=round(frozen_area, 2),
            position_count=position_count,
            total_power_kw=total_power_kw,
        )
    )


def _planning_run_response(
    inputs: dict[str, Any],
    zone_result: Any,
    investment_result: Any,
) -> dict[str, Any]:
    zones = zone_result.result["zones"]
    if not isinstance(zones, list):
        raise ValueError("zone plan result must contain zones")
    total_area = round(sum(_zone_number(zone, "required_area_m2") for zone in zones), 2)
    total_positions = sum(int(_zone_number(zone, "position_count")) for zone in zones)
    power_configuration = _build_power_configuration(
        zones,
        _as_float(inputs["daily_inbound_mass_kg"]),
        total_area,
    )
    return {
        "success": zone_result.success and investment_result.success,
        "input_snapshot": inputs,
        "summary": {
            "total_area_m2": total_area,
            "total_position_count": total_positions,
            "total_investment_cny": investment_result.result["total_investment_cny"],
            "total_power_kw": power_configuration["total_installed_power_kw"],
            "requires_review": zone_result.requires_review or investment_result.requires_review,
        },
        "zone_plan": asdict(zone_result),
        "investment_estimate": asdict(investment_result),
        "power_configuration": power_configuration,
    }


def _build_power_configuration(
    zones: list[object],
    daily_inbound_mass_kg: float,
    total_area_m2: float,
) -> dict[str, Any]:
    scale = daily_inbound_mass_kg / 25_000
    equipment_rows = [_scale_power_row(row, scale) for row in _reference_power_rows()]
    _apply_precooling_axial_fan_rule(equipment_rows, zones)
    defrost_simultaneous_power = round(
        sum(_optional_number(row["defrost_total_power_kw"]) for row in equipment_rows) * 0.30,
        2,
    )
    running_simultaneous_power = round(
        sum(
            _as_float(row["total_power_kw"])
            for row in equipment_rows
            if row["section"] == "refrigeration"
        )
        * 0.90,
        2,
    )
    refrigeration_total = round(defrost_simultaneous_power + running_simultaneous_power, 2)
    production_total = round(
        sum(
            _as_float(row["total_power_kw"])
            for row in equipment_rows
            if row["section"] == "production"
        )
        * 0.90,
        2,
    )
    grand_total = round(refrigeration_total + production_total, 2)
    summary_rows = [
        {
            "name": "化霜总功率",
            "basis": "按30% 同时化霜",
            "total_power_kw": defrost_simultaneous_power,
        },
        {
            "name": "设备运行功率",
            "basis": "按90% 同时使用系数",
            "total_power_kw": running_simultaneous_power,
        },
        {
            "name": "制冷总功率",
            "basis": "化霜同时系数30% + 设备运行同时系数90%",
            "total_power_kw": refrigeration_total,
        },
        {
            "name": "生产设备总功率",
            "basis": "按90% 同时使用系数",
            "total_power_kw": production_total,
        },
        {"name": "合计", "basis": "", "total_power_kw": grand_total},
    ]
    items = [
        _power_item("制冷系统", refrigeration_total, 1),
        _power_item("生产设备", production_total, 1),
    ]
    return {
        "equipment_rows": equipment_rows,
        "summary_rows": summary_rows,
        "items": items,
        "total_installed_power_kw": grand_total,
        "total_estimated_demand_kw": grand_total,
        "assumptions": [
            "用电配置按参考项目设备清单演示，默认25吨/天，其他产能按比例缩放。",
            "未替代正式电气设计、设备铭牌功率统计或供配电校核。",
        ],
        "requires_review": True,
    }


def _power_item(category: str, installed_power_kw: float, demand_factor: float) -> dict[str, Any]:
    return {
        "category": category,
        "installed_power_kw": round(installed_power_kw, 2),
        "demand_factor": demand_factor,
        "estimated_demand_kw": round(installed_power_kw * demand_factor, 2),
    }


def _apply_precooling_axial_fan_rule(
    equipment_rows: list[dict[str, Any]],
    zones: list[object],
) -> None:
    primary_positions = _zone_position_count(zones, "primary_precooling_room")
    secondary_positions = _zone_position_count(zones, "secondary_precooling_room")
    axial_fan_quantity = (primary_positions + secondary_positions) * 4
    for row in equipment_rows:
        if row["name"] == "轴流风机":
            row["quantity"] = axial_fan_quantity
            row["total_power_kw"] = round(
                axial_fan_quantity * _as_float(row["running_power_kw"]), 2
            )
            return


def _zone_position_count(zones: list[object], zone_code: str) -> int:
    for zone in zones:
        if isinstance(zone, dict) and zone.get("zone_code") == zone_code:
            return int(_as_float(zone.get("position_count", 0)))
    return 0


def _reference_power_rows() -> list[dict[str, Any]]:
    return [
        _equipment_row(
            1,
            "制冷压缩机组",
            "一级预冷、原果暂存间、分选间",
            1,
            None,
            None,
            297.6,
            297.6,
            "refrigeration",
        ),
        _equipment_row(
            2,
            "制冷压缩机组",
            "二级预冷间、成品库、出货通道、覆膜间",
            1,
            None,
            None,
            209.6,
            209.6,
            "refrigeration",
        ),
        _equipment_row(3, "制冷压缩机组", "成品双温库", 2, None, None, 27.5, 55.0, "refrigeration"),
        _equipment_row(4, "制冷压缩机组", "次果暂存区", 1, None, None, 4.21, 4.21, "refrigeration"),
        _equipment_row(5, "制冷压缩机组", "冻果间", 1, None, None, 29.4, 29.4, "refrigeration"),
        _equipment_row(6, "冷风机", "原果暂存", 3, 4.9, 14.7, 0.75, 2.25, "refrigeration"),
        _equipment_row(7, "冷风机", "一级预冷间", 12, 16.0, 192.0, 2.68, 32.16, "refrigeration"),
        _equipment_row(8, "冷风机", "分选间", 14, 4.9, 68.6, 0.75, 10.5, "refrigeration"),
        _equipment_row(9, "冷风机", "二级预冷间", 14, 21.6, 302.4, 2.68, 37.52, "refrigeration"),
        _equipment_row(10, "冷风机", "覆膜间", 3, 21.6, 64.8, 1.796, 5.388, "refrigeration"),
        _equipment_row(11, "冷风机", "双温成品库", 4, 25.2, 100.8, 2.68, 10.72, "refrigeration"),
        _equipment_row(12, "冷风机", "成品库", 3, 10.0, 30.0, 1.796, 5.388, "refrigeration"),
        _equipment_row(13, "冷风机", "次果暂存间", 1, 8.5, 8.5, 1.347, 1.347, "refrigeration"),
        _equipment_row(14, "冷风机", "冻果暂存间", 1, 31.5, 31.5, 3.2, 3.2, "refrigeration"),
        _equipment_row(15, "冷风机", "出货通道", 2, 8.5, 17.0, 1.347, 2.694, "refrigeration"),
        _equipment_row(16, "蒸发冷", "", 1, None, None, 28.0, 28.0, "refrigeration"),
        _equipment_row(17, "蒸发冷", "", 1, None, None, 19.0, 19.0, "refrigeration"),
        _equipment_row(18, "轴流风机", "", 360, None, None, 0.55, 198.0, "refrigeration"),
        _equipment_row(19, "升降平台", "", 3, None, None, 2.2, 6.6, "refrigeration"),
        _equipment_row(20, "工业滑升门", "", 3, None, None, 0.4, 1.2, "refrigeration"),
        _equipment_row(21, "充气门封", "", 3, None, None, 0.4, 1.2, "refrigeration"),
        _equipment_row(22, "电动门", "", 29, None, None, 0.38, 11.02, "refrigeration"),
        _equipment_row(23, "快卷门", "", 2, None, None, 0.38, 0.76, "refrigeration"),
        _equipment_row(24, "风幕机", "", 10, None, None, 0.38, 3.8, "refrigeration"),
        _equipment_row(25, "冷库照明", "", 350, None, None, 0.04, 14.0, "refrigeration"),
        _equipment_row(26, "地坪加热丝", "", 1, None, None, 2.0, 2.0, "refrigeration"),
        _equipment_row(27, "紫外线灯", "", 190, None, None, 0.08, 15.2, "refrigeration"),
        _equipment_row(28, "臭氧", "", 1, None, None, 15.0, 15.0, "refrigeration"),
        _equipment_row(29, "加湿", "", 1, None, None, 15.0, 15.0, "refrigeration"),
        _equipment_row(35, "折箱机", "", 2, None, None, 12.0, 24.0, "production"),
        _equipment_row(36, "枕式包装机", "", 2, None, None, 12.5, 25.0, "production"),
        _equipment_row(37, "包装流水线", "", 2, None, None, 7.5, 15.0, "production"),
        _equipment_row(38, "筐桶清洗机", "", 2, None, None, 20.0, 40.0, "production"),
        _equipment_row(39, "贴标机", "", 2, None, None, 5.0, 10.0, "production"),
        _equipment_row(40, "光电分选设备", "", 1, None, None, 65.0, 65.0, "production"),
        _equipment_row(41, "定量包装设备", "", 3, None, None, 15.0, 45.0, "production"),
        _equipment_row(42, "辅助铺联设备", "", 1, None, None, 40.0, 40.0, "production"),
        _equipment_row(43, "空压机", "", 1, None, None, 22.0, 22.0, "production"),
        _equipment_row(44, "熏蒸设备", "", 2, None, None, 15.0, 30.0, "production"),
    ]


def _equipment_row(
    sequence: int,
    name: str,
    area: str,
    quantity: float,
    defrost_power_kw: float | None,
    defrost_total_power_kw: float | None,
    running_power_kw: float,
    total_power_kw: float,
    section: str,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "name": name,
        "area": area,
        "quantity": quantity,
        "defrost_power_kw": defrost_power_kw,
        "defrost_total_power_kw": defrost_total_power_kw,
        "running_power_kw": running_power_kw,
        "total_power_kw": total_power_kw,
        "section": section,
    }


def _scale_power_row(row: dict[str, Any], scale: float) -> dict[str, Any]:
    return {
        **row,
        "quantity": _scale_value(row["quantity"], scale),
        "defrost_total_power_kw": _scale_optional(row["defrost_total_power_kw"], scale),
        "total_power_kw": _scale_value(row["total_power_kw"], scale),
    }


def _scale_optional(value: object, scale: float) -> float | None:
    if value is None:
        return None
    return _scale_value(value, scale)


def _scale_value(value: object, scale: float) -> float:
    scaled = _as_float(value) * scale
    rounded = round(scaled, 2)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _optional_number(value: object) -> float:
    if value is None:
        return 0
    return _as_float(value)


def _inputs_from_planning_request(
    request: PlanningRunRequest,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    inputs = fallback.copy()
    if request.inputs:
        inputs.update(request.inputs)
    inputs.update(_flat_planning_input(request))
    if "finished_storage_days" not in inputs and "storage_days" in inputs:
        inputs["finished_storage_days"] = inputs["storage_days"]
    if "packaging_storage_days" not in inputs:
        inputs["packaging_storage_days"] = inputs.get("main_packaging_storage_days", 3)
    if "main_packaging_storage_days" not in inputs:
        inputs["main_packaging_storage_days"] = inputs["packaging_storage_days"]
    if "auxiliary_packaging_storage_days" not in inputs:
        inputs["auxiliary_packaging_storage_days"] = 30
    return inputs


def _flat_planning_input(request: PlanningRunRequest) -> dict[str, Any]:
    return request.model_dump(
        exclude_none=True,
        exclude={"inputs"},
    )


def _demo_inputs() -> dict[str, Any]:
    return {
        "daily_inbound_mass_kg": 25_000,
        "working_time_h_per_day": 16,
        "utilization_factor": 0.85,
        "finished_storage_days": 2.5,
        "packaging_storage_days": 3,
        "main_packaging_storage_days": 3,
        "auxiliary_packaging_storage_days": 30,
        "reserve_factor": 1.05,
        "precooling_required_ratio": 1,
    }
