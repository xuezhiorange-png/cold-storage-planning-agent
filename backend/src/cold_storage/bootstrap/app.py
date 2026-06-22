"""FastAPI application factory."""

import logging
from collections.abc import Callable, Generator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as SASession

from cold_storage.bootstrap.demo_overview import build_demo_overview
from cold_storage.bootstrap.dependencies import (
    get_agent_service,
    get_engine,
    get_project_service,
    init_dependencies,
    shutdown_dependencies,
)
from cold_storage.bootstrap.logging import configure_logging
from cold_storage.bootstrap.settings import get_settings
from cold_storage.modules.calculations.application.service import (
    CoreCalculationService,
)
from cold_storage.modules.calculations.domain.inputs import ThroughputInput
from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)
from cold_storage.modules.calculations.domain.service import CalculationService
from cold_storage.modules.calculations.domain.zone_planning import ColdRoomZonePlanner
from cold_storage.modules.coefficients.api.routes import register_coefficient_routes
from cold_storage.modules.coefficients.application.service import CoefficientService
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
from cold_storage.modules.planning_agent.application.agent_service import LegacyPlanningAgentService
from cold_storage.modules.planning_agent.application.orchestrator import AgentOrchestrator
from cold_storage.modules.planning_agent.application.service import PlanningAgentService
from cold_storage.modules.planning_agent.application.tool_registry import build_default_registry
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import FakeAgentModelGateway
from cold_storage.modules.planning_agent.infrastructure.repository import AgentRepository
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.domain.models import (
    InvalidVersionTransitionError,
    VersionImmutabilityError,
)
from cold_storage.modules.schemes.api.routes import register_scheme_routes
from cold_storage.modules.schemes.application.service import SchemeService

ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
AgentServiceDep = Annotated[LegacyPlanningAgentService, Depends(get_agent_service)]


# --------------------------------------------------------------------------- Fix #2: Per-request
# ---------------------------------------------------------------------------


def _get_db_session() -> Generator[SASession, None, None]:
    """FastAPI dependency: yields a per-request SQLAlchemy Session.

    The Application Service owns commit/rollback.  This dependency only
    handles rollback on unhandled exceptions and session close.
    """
    engine = get_engine()
    session = SASession(bind=engine, expire_on_commit=False)
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_planning_agent_service(
    db_session: SASession = Depends(_get_db_session),  # noqa: B008
) -> PlanningAgentService:
    """FastAPI dependency: creates a PlanningAgentService per-request.

    Fix #2: per-request Session, not singleton.
    Fix #7: transaction boundary via _get_db_session commit/rollback.
    Fix #1+#2: Wire real tool adapters into the orchestrator.
    """
    from cold_storage.modules.knowledge.application.service import (
        KnowledgeService as _KnowledgeService,
    )
    from cold_storage.modules.planning_agent.infrastructure.tool_adapters.knowledge_adapter import (
        KnowledgeSearchAdapter,
    )
    from cold_storage.modules.planning_agent.infrastructure.tool_adapters.planning_adapter import (
        CoolingLoadEquipmentAdapter,
        ThroughputInventoryAreaAdapter,
    )
    from cold_storage.modules.planning_agent.infrastructure.tool_adapters.project_adapter import (
        ProjectGetAdapter,
        ProjectVersionGetAdapter,
    )
    from cold_storage.modules.planning_agent.infrastructure.tool_adapters.scheme_adapter import (
        SchemeGenerateCompareAdapter,
    )

    gateway = FakeAgentModelGateway()
    registry = build_default_registry()

    # Build real adapters — stateless calculators are fine per-request
    zone_planner = ColdRoomZonePlanner()
    investment_estimator = InvestmentEstimator()
    cooling_service = CoreCalculationService()
    scheme_service = SchemeService(db_session)
    knowledge_service = _KnowledgeService(db_session)
    project_service = get_project_service()

    from cold_storage.modules.planning_agent.infrastructure.tool_adapters import ToolAdapter as _TA

    adapters: dict[str, _TA] = {
        "planning.calculate_throughput_inventory_area": ThroughputInventoryAreaAdapter(
            zone_planner, investment_estimator
        ),
        "planning.calculate_cooling_load_and_equipment": CoolingLoadEquipmentAdapter(
            cooling_service
        ),
        "scheme.generate_and_compare": SchemeGenerateCompareAdapter(scheme_service),
        "knowledge.search": KnowledgeSearchAdapter(knowledge_service),
        "project.get": ProjectGetAdapter(project_service),
        "project_version.get": ProjectVersionGetAdapter(project_service),
    }

    orchestrator = AgentOrchestrator(tool_adapters=adapters, project_service=project_service)
    repo = AgentRepository(db_session)
    return PlanningAgentService(
        repository=repo,
        gateway=gateway,
        registry=registry,
        orchestrator=orchestrator,
    )


# --------------------------------------------------------------------------- Request models (API
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


# --------------------------------------------------------------------------- Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    init_dependencies(get_settings())
    try:
        yield
    finally:
        shutdown_dependencies()


# --------------------------------------------------------------------------- App factory
# ---------------------------------------------------------------------------


def create_app(project_service: ProjectService | None = None) -> FastAPI:
    configure_logging()
    app = FastAPI(title="Cold Storage Planning Agent V1", lifespan=_lifespan)
    calculator = CalculationService()
    zone_planner = ColdRoomZonePlanner()
    investment_estimator = InvestmentEstimator()
    coefficient_service = CoefficientService()
    core_calculation_service = CoreCalculationService()
    register_coefficient_routes(app, coefficient_service)

    # Scheme routes
    def _scheme_service_factory() -> SchemeService:
        from cold_storage.bootstrap.dependencies import get_engine

        engine = get_engine()
        session = SASession(bind=engine)
        return SchemeService(session)

    register_scheme_routes(app, _scheme_service_factory)

    # Knowledge routes
    def _knowledge_service_factory() -> Any:
        from cold_storage.bootstrap.dependencies import get_engine
        from cold_storage.modules.knowledge.application.service import KnowledgeService

        engine = get_engine()
        session = SASession(bind=engine)
        return KnowledgeService(session)

    from cold_storage.modules.knowledge.api.routes import (
        register_knowledge_routes,
    )

    register_knowledge_routes(app, _knowledge_service_factory)

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
            zone_result.result["zones"], as_float(inputs["daily_inbound_mass_kg"]), total_area
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

    # ----------------------------------------------------------------------- Fix #2: New Plannin
    # -----------------------------------------------------------------------
    # Fix #2: Router uses Depends() so each request gets its own DB Session.
    # Fix #7: _get_db_session handles commit/rollback/close per-request.
    from cold_storage.modules.planning_agent.api.routes import (
        create_agent_router as _create_agent_router,
    )

    app.include_router(_create_agent_router(_get_planning_agent_service))

    # ----------------------------------------------------------------------- Core Calculation En
    # -----------------------------------------------------------------------

    class CoreCalculationPreviewRequest(BaseModel):
        """Request body for the preview endpoint (no persistence)."""

        inputs: dict[str, Any]

    @app.post("/api/v1/projects/{project_id}/versions/{version}/calculations/core")
    def save_core_calculation(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        """Run core calculations and persist the snapshot to the project version."""
        project_version = service.get_version(project_id, version)
        inputs = project_version.input_snapshot
        result = core_calculation_service.orchestrate_from_dict(inputs)
        # Persist the snapshot via the service (handles DB + audit)
        result_dict = result.to_dict()
        service.save_core_calculation_result(project_id, version, result_dict, actor="api")
        return result_dict

    @app.get("/api/v1/projects/{project_id}/versions/{version}/calculations/core")
    def get_core_calculation(
        project_id: str,
        version: int,
        service: ProjectServiceDep,
    ) -> dict[str, Any]:
        """Retrieve the persisted core calculation snapshot."""
        project_version = service.get_version(project_id, version)
        snapshot = project_version.calculation_snapshot
        if not snapshot:
            return {"error": {"code": "NO_CALCULATION", "message": "No core calculation found"}}
        return snapshot

    @app.post("/api/v1/calculations/core/preview")
    def preview_core_calculation(
        request: CoreCalculationPreviewRequest,
    ) -> dict[str, Any]:
        """Run core calculations without saving (preview mode)."""
        result = core_calculation_service.orchestrate_from_dict(request.inputs)
        return result.to_dict()

    # --- Cooling load calculation (Task 5) ---------------------------------

    @app.post("/api/v1/projects/{project_id}/versions/{version}/calculations/cooling-load")
    def calculate_cooling_load_endpoint(
        project_id: str,
        version: int,
        request: CoreCalculationPreviewRequest,
    ) -> dict[str, Any]:
        """Run cooling load calculation for a project version."""
        from cold_storage.modules.calculations.application.cooling_load_api import (
            run_cooling_load_from_dict,
        )
        from cold_storage.modules.projects.application.service import ProjectService

        project_service = ProjectService()
        project_version = project_service.get_version(project_id, version)
        if project_version is None:
            return {
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Project {project_id} version {version} not found",
                }
            }
        if hasattr(project_version, "is_locked") and project_version.is_locked:
            return {
                "error": {
                    "code": "VERSION_LOCKED",
                    "message": "Cannot calculate on a locked project version",
                }
            }

        try:
            result = run_cooling_load_from_dict(request.inputs)

            # Persist to project version snapshot
            snapshot = getattr(project_version, "calculation_snapshot", {}) or {}
            snapshot["cooling_load"] = result.to_dict()
            project_version.calculation_snapshot = snapshot

            return result.to_dict()

        except Exception as exc:
            return {"error": {"code": "CALCULATION_ERROR", "message": str(exc)}}

    @app.get("/api/v1/projects/{project_id}/versions/{version}/calculations/cooling-load")
    def get_cooling_load(
        project_id: str,
        version: int,
    ) -> dict[str, Any]:
        """Retrieve persisted cooling load calculation results."""
        from cold_storage.modules.projects.application.service import ProjectService

        project_service = ProjectService()
        project_version = project_service.get_version(project_id, version)
        if project_version is None:
            return {
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"Project {project_id} version {version} not found",
                }
            }
        snapshot = getattr(project_version, "calculation_snapshot", {}) or {}
        cooling_load = snapshot.get("cooling_load")
        if not cooling_load:
            return {
                "error": {
                    "code": "NO_CALCULATION",
                    "message": "No cooling load calculation found",
                }
            }
        result: dict[str, Any] = cooling_load
        return result

    @app.post("/api/v1/calculations/cooling-load/preview")
    def preview_cooling_load(
        request: CoreCalculationPreviewRequest,
    ) -> dict[str, Any]:
        """Run cooling load calculation without saving (preview mode)."""
        from cold_storage.modules.calculations.application.cooling_load_api import (
            run_cooling_load_from_dict,
        )

        try:
            result = run_cooling_load_from_dict(request.inputs)
            return result.to_dict()

        except Exception as exc:
            return {"error": {"code": "CALCULATION_ERROR", "message": str(exc)}}

    # -----------------------------------------------------------------------
    # Reports module DI wiring (P0-1)
    # -----------------------------------------------------------------------
    from cold_storage.modules.reports.api.routes import reports_router
    from cold_storage.modules.reports.application.render_service import (
        ReportRenderService,
    )
    from cold_storage.modules.reports.application.service import ReportService
    from cold_storage.modules.reports.infrastructure.artifact_storage import (
        ReportArtifactStorage,
    )
    from cold_storage.modules.reports.infrastructure.repository import (
        SQLReportRepository,
    )

    def _get_reports_db_session() -> Generator[SASession, None, None]:
        """Per-request SQLAlchemy session for the reports module."""
        engine = get_engine()
        session = SASession(bind=engine, expire_on_commit=False)
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _get_report_service(
        db_session: SASession = Depends(_get_reports_db_session),  # noqa: B008
    ) -> ReportService:
        from cold_storage.modules.reports.application.assembler import (
            ReportAssembler,
        )
        from cold_storage.modules.reports.infrastructure.real_data_provider import (
            RealReportDataProvider,
        )

        repo = SQLReportRepository(db_session)
        data_provider = RealReportDataProvider()
        assembler = ReportAssembler(data_provider=data_provider)
        return ReportService(repository=repo, assembler=assembler)

    def _get_report_render_service(
        db_session: SASession = Depends(_get_reports_db_session),  # noqa: B008
    ) -> ReportRenderService:
        repo = SQLReportRepository(db_session)
        artifact_storage = ReportArtifactStorage(base_dir="data/report_artifacts")
        return ReportRenderService(
            repository=repo,
            storage=artifact_storage,
            template_repo=repo,  # type: ignore[arg-type]
            artifact_repo=repo,  # type: ignore[arg-type]
        )

    def _get_report_template_repo(
        db_session: SASession = Depends(_get_reports_db_session),  # noqa: B008
    ) -> SQLReportRepository:
        return SQLReportRepository(db_session)

    # Wire DI overrides
    from cold_storage.modules.reports.api.routes import (
        _get_render_service as _reports_render_stub,
    )
    from cold_storage.modules.reports.api.routes import (
        _get_service as _reports_service_stub,
    )
    from cold_storage.modules.reports.api.routes import (
        _get_template_repo as _reports_template_stub,
    )

    app.dependency_overrides[_reports_service_stub] = _get_report_service
    app.dependency_overrides[_reports_render_stub] = _get_report_render_service
    app.dependency_overrides[_reports_template_stub] = _get_report_template_repo

    # Register report routes
    app.include_router(reports_router)

    # Seed default templates (P0-3) — lazy, only if engine is available
    _seeded = False

    @app.on_event("startup")
    def _seed_report_templates() -> None:
        nonlocal _seeded
        if _seeded:
            return
        try:
            engine = get_engine()
        except RuntimeError:
            return  # dependencies not initialized (e.g. in tests)
        from cold_storage.modules.reports.infrastructure.template_seed import (
            seed_default_templates,
        )

        seed_session = SASession(bind=engine, expire_on_commit=False)
        try:
            seed_repo = SQLReportRepository(seed_session)
            seed_default_templates(seed_repo)
            _seeded = True
        except Exception:
            _logger = logging.getLogger(__name__)
            _logger.exception("Failed to seed default report templates")
            seed_session.rollback()
        finally:
            seed_session.close()

    return app


# --------------------------------------------------------------------------- Helpers local to th
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
