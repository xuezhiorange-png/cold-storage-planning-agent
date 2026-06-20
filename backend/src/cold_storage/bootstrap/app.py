"""FastAPI application factory."""

from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from cold_storage.bootstrap.demo_overview import build_demo_overview
from cold_storage.bootstrap.dependencies import (
    get_agent_service,
    get_project_service,
    init_dependencies,
    shutdown_dependencies,
)
from cold_storage.bootstrap.logging import configure_logging
from cold_storage.bootstrap.settings import get_settings
from cold_storage.modules.calculations.domain.inputs import ThroughputInput
from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)
from cold_storage.modules.calculations.domain.service import CalculationService
from cold_storage.modules.calculations.domain.zone_planning import ColdRoomZonePlanner
from cold_storage.modules.planning.application.service import (
    as_float,
    build_investment_from_zone_result,
    build_power_configuration,
    build_zone_plan_from_inputs,
    demo_inputs,
    flat_planning_input,
    inputs_from_planning_request,
    planning_run_response,
    zone_number,
)
from cold_storage.modules.planning_agent.application.agent_service import PlanningAgentService
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.domain.models import (
    InvalidVersionTransitionError,
    VersionImmutabilityError,
)

ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
AgentServiceDep = Annotated[PlanningAgentService, Depends(get_agent_service)]


# ---------------------------------------------------------------------------
# Request models (API-layer concerns)
# ---------------------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    name: str
    location: str
    product_category: str


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    location: str | None = None
    product_category: str | None = None


class VersionCreateRequest(BaseModel):
    change_summary: str


class VersionCreateFromRequest(BaseModel):
    source_version: int
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


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    init_dependencies(get_settings())
    try:
        yield
    finally:
        shutdown_dependencies()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(project_service: ProjectService | None = None) -> FastAPI:
    configure_logging()
    app = FastAPI(title="Cold Storage Planning Agent V1", lifespan=_lifespan)
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
        inputs = inputs_from_planning_request(request, demo_inputs())
        zone_result = build_zone_plan_from_inputs(inputs, zone_planner)
        total_area = round(
            sum(zone_number(zone, "required_area_m2") for zone in zone_result.result["zones"]),
            2,
        )
        power_configuration = build_power_configuration(
            zone_result.result["zones"],
            as_float(inputs["daily_inbound_mass_kg"]),
            total_area,
        )
        investment_result = build_investment_from_zone_result(
            zone_result,
            investment_estimator,
            as_float(power_configuration["total_installed_power_kw"]),
        )
        return planning_run_response(inputs, zone_result, investment_result)

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

    @app.patch("/api/v1/projects/{project_id}")
    def update_project(
        project_id: str,
        request: ProjectUpdateRequest,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        project = service.update_project(
            project_id,
            name=request.name,
            location=request.location,
            product_category=request.product_category,
        )
        return {
            "id": project.id,
            "code": project.code,
            "name": project.name,
            "location": project.location,
            "product_category": project.product_category,
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
                "parent_version_id": version.parent_version_id,
                "submitted_at": version.submitted_at.isoformat() if version.submitted_at else None,
                "approved_at": version.approved_at.isoformat() if version.approved_at else None,
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
            "calculation_snapshot": project_version.calculation_snapshot,
            "assumption_snapshot": project_version.assumption_snapshot,
            "parent_version_id": project_version.parent_version_id,
            "submitted_at": project_version.submitted_at.isoformat()
            if project_version.submitted_at
            else None,
            "reviewed_at": project_version.reviewed_at.isoformat()
            if project_version.reviewed_at
            else None,
            "approved_at": project_version.approved_at.isoformat()
            if project_version.approved_at
            else None,
            "approved_by": project_version.approved_by,
            "archived_at": project_version.archived_at.isoformat()
            if project_version.archived_at
            else None,
        }

    @app.post("/api/v1/projects/{project_id}/versions/{version}/submit")
    def submit_version(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        try:
            project_version = service.submit_version(project_id, version, actor="api")
        except (InvalidVersionTransitionError, VersionImmutabilityError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"id": project_version.id, "status": project_version.status}

    @app.post("/api/v1/projects/{project_id}/versions/{version}/return")
    def return_version(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        try:
            project_version = service.return_version(project_id, version, actor="api")
        except (InvalidVersionTransitionError, VersionImmutabilityError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"id": project_version.id, "status": project_version.status}

    @app.post("/api/v1/projects/{project_id}/versions/{version}/review")
    def review_version(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        try:
            project_version = service.review_version(project_id, version, actor="api")
        except (InvalidVersionTransitionError, VersionImmutabilityError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"id": project_version.id, "status": project_version.status}

    @app.post("/api/v1/projects/{project_id}/versions/{version}/approve")
    def approve_version(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        try:
            project_version = service.approve_version(project_id, version, actor="api")
        except (InvalidVersionTransitionError, VersionImmutabilityError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"id": project_version.id, "status": project_version.status}

    @app.post("/api/v1/projects/{project_id}/versions/{version}/archive")
    def archive_version(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        try:
            project_version = service.archive_version(project_id, version, actor="api")
        except (InvalidVersionTransitionError, VersionImmutabilityError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"id": project_version.id, "status": project_version.status}

    @app.post("/api/v1/projects/{project_id}/versions/{version}/create-from")
    def create_version_from(
        project_id: str,
        version: int,
        request: VersionCreateFromRequest,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        new_version = service.create_version_from(
            project_id,
            request.source_version,
            request.change_summary,
            created_by="api",
        )
        return {
            "id": new_version.id,
            "version_number": new_version.version_number,
            "status": new_version.status,
            "parent_version_id": new_version.parent_version_id,
        }

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
                daily_inbound_mass_kg=as_float(inputs["daily_inbound_mass_kg"]),
                working_time_h_per_day=as_float(inputs["working_time_h_per_day"]),
                utilization_factor=as_float(inputs["utilization_factor"]),
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
        total_area = sum(zone_number(zone, "required_area_m2") for zone in zones)
        project_version = service.get_version(project_id, version)
        power_configuration = build_power_configuration(
            zones,
            as_float(project_version.input_snapshot["daily_inbound_mass_kg"]),
            total_area,
        )
        refrigerated_area = sum(
            zone_number(zone, "required_area_m2")
            for zone in zones
            if isinstance(zone, dict) and zone.get("temperature_band") != "常温"
        )
        frozen_area = sum(
            zone_number(zone, "required_area_m2")
            for zone in zones
            if isinstance(zone, dict) and zone.get("temperature_band") == "-18℃"
        )
        position_count = sum(int(zone_number(zone, "position_count")) for zone in zones)
        result = investment_estimator.estimate(
            InvestmentEstimateInput(
                total_area_m2=round(total_area, 2),
                refrigerated_area_m2=round(refrigerated_area, 2),
                frozen_area_m2=round(frozen_area, 2),
                position_count=position_count,
                total_power_kw=as_float(power_configuration["total_installed_power_kw"]),
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
        inputs = inputs_from_planning_request(request, project_version.input_snapshot)
        if request.inputs or flat_planning_input(request):
            save_result = service.save_inputs(project_id, version, inputs, actor="api")
            if not save_result.success:
                return {
                    "error": {
                        "code": save_result.error_code,
                        "message": "项目版本已锁定",
                        "details": {},
                    }
                }
        zone_result = build_zone_plan_from_inputs(inputs, zone_planner)
        total_area = round(
            sum(zone_number(zone, "required_area_m2") for zone in zone_result.result["zones"]),
            2,
        )
        power_configuration = build_power_configuration(
            zone_result.result["zones"],
            as_float(inputs["daily_inbound_mass_kg"]),
            total_area,
        )
        investment_result = build_investment_from_zone_result(
            zone_result,
            investment_estimator,
            as_float(power_configuration["total_installed_power_kw"]),
        )
        service.record_calculation(project_id, version, zone_result, actor="api")
        service.record_calculation(project_id, version, investment_result, actor="api")
        return planning_run_response(inputs, zone_result, investment_result)

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


# ---------------------------------------------------------------------------
# Helpers local to this module
# ---------------------------------------------------------------------------


def post_agent_message(app: FastAPI) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    return app.post("/api/v1/agent/sessions/{session_id}/messages")


def _build_zone_plan(
    project_id: str,
    version: int,
    service: ProjectService,
    zone_planner: ColdRoomZonePlanner,
) -> Any:
    project_version = service.get_version(project_id, version)
    return build_zone_plan_from_inputs(project_version.input_snapshot, zone_planner)
