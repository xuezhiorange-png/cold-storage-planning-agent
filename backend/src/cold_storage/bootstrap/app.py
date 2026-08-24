"""FastAPI application factory."""

import json
import logging
import threading
from collections.abc import Callable, Generator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
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
from cold_storage.bootstrap.mode import AppMode, resolve_app_mode
from cold_storage.bootstrap.settings import AgentCapabilityState, get_settings
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
from cold_storage.modules.planning_agent.infrastructure.repository import AgentRepository
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.domain.models import (
    InvalidVersionTransitionError,
    VersionImmutabilityError,
)
from cold_storage.modules.schemes.api.routes import register_scheme_routes
from cold_storage.modules.schemes.application.service import SchemeService

if TYPE_CHECKING:
    from cold_storage.bootstrap.runtime_readiness import AgentProviderProbe

ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
AgentServiceDep = Annotated[LegacyPlanningAgentService, Depends(get_agent_service)]


# ---------------------------------------------------------------------------
# R6: Composition-root strict runtime authority
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentRouteAuthority:
    """Immutable record of one disabled agent endpoint.

    Created by :func:`create_app` after registering the actual APIRoute.
    The audit compares actual runtime routes against these exact objects.
    """

    method: str
    path: str
    endpoint: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class CoefficientRouteAuthority:
    """Immutable record of one coefficient endpoint.

    Created by :func:`create_app` after :func:`register_coefficient_routes`
    returns the registration evidence.
    """

    method: str
    path: str
    endpoint: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class StrictRuntimeAuthority:
    """Per-app, immutable, composition-root authority for strict audit.

    Created exclusively by :func:`create_app` after all routes are
    registered and the coefficient provider is resolved.  Captured by
    the per-app lifespan closure.  The strict audit reads **only**
    from this object — never from writable ``app.state``.

    Design guarantees:
    - CREATED_BY = create_app
    - SCOPE = per FastAPI app instance
    - MUTABLE = NO (frozen dataclass)
    - CAPTURED_BY = per-app lifespan closure
    - ROUTE_MODULE_CAN_REPLACE = NO
    - SERVICE_PROVIDER_CAN_REPLACE = NO
    - GLOBAL_SINGLETON = NO
    """

    agent_routes: tuple[AgentRouteAuthority, ...] = field(default=())
    coefficient_routes: tuple[CoefficientRouteAuthority, ...] = field(default=())
    coefficient_provider: Callable[..., Any] = None  # type: ignore[assignment]
    capability_mode: str = "disabled"
    agent_capability_state: str = AgentCapabilityState.DISABLED.value
    agent_evidence: Any | None = None
    agent_service_factory: Callable[..., Any] | None = None
    agent_candidate: bool = False


def _build_strict_authority(
    *,
    agent_routes: tuple[AgentRouteAuthority, ...],
    coefficient_routes: tuple[CoefficientRouteAuthority, ...],
    coefficient_provider: Callable[..., Any],
    capability_mode: str,
    agent_capability_state: str = AgentCapabilityState.DISABLED.value,
    agent_evidence: Any | None = None,
    agent_service_factory: Callable[..., Any] | None = None,
    agent_candidate: bool = False,
) -> StrictRuntimeAuthority:
    """Build the frozen strict authority.  Called once by create_app."""
    return StrictRuntimeAuthority(
        agent_routes=agent_routes,
        coefficient_routes=coefficient_routes,
        coefficient_provider=coefficient_provider,
        capability_mode=capability_mode,
        agent_capability_state=agent_capability_state,
        agent_evidence=agent_evidence,
        agent_service_factory=agent_service_factory,
        agent_candidate=agent_candidate,
    )


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


def _build_planning_agent_service(
    db_session: SASession,
    gateway: Any,
) -> PlanningAgentService:
    """Build one PlanningAgentService around an already-authorized gateway.

    Fix #2: per-request Session, not singleton.
    Fix #7: transaction boundary via _get_db_session commit/rollback.
    Fix #1+#2: Wire real tool adapters into the orchestrator.  The gateway
    choice is made by the composition root; this function never falls back
    between fake and real providers.
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

    # P0-7: Lazy imports for report tool adapters (avoid circular)
    from cold_storage.modules.reports.application.render_service import (
        ReportRenderService as _ReportRenderService,
    )
    from cold_storage.modules.reports.application.render_service import (
        ReportRenderUnitOfWork as _ReportRenderUnitOfWork,
    )
    from cold_storage.modules.reports.infrastructure.artifact_storage import (
        ReportArtifactStorage as _ReportArtifactStorage,
    )
    from cold_storage.modules.reports.infrastructure.report_tool_adapters import (
        ReportGetExportAdapter,
        ReportListExportsAdapter,
        ReportRenderAdapter,
    )
    from cold_storage.modules.reports.infrastructure.repository import (
        SQLReportRepository as _SQLReportRepository,
    )

    registry = build_default_registry()

    # Build real adapters — stateless calculators are fine per-request
    zone_planner = ColdRoomZonePlanner()
    investment_estimator = InvestmentEstimator()
    cooling_service = CoreCalculationService()
    scheme_service = SchemeService(db_session)
    knowledge_service = _KnowledgeService(db_session)
    project_service = get_project_service()

    # P0-7: Create report render service for tool adapters
    _reports_repo = _SQLReportRepository(db_session)
    _reports_storage = _ReportArtifactStorage(
        base_dir=get_settings().storage_dir or "data/report_artifacts"
    )
    _reports_uow = _ReportRenderUnitOfWork(
        db_session,
        report_repo=_reports_repo,
        artifact_repo=_reports_repo,
        session_factory=lambda: SASession(
            bind=db_session.bind,
            expire_on_commit=False,
        ),
    )
    _reports_render_svc = _ReportRenderService(
        uow=_reports_uow,
        storage=_reports_storage,
        template_repo=_reports_repo,
    )

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
        # Report tool adapters (P0-7)
        "report.render": ReportRenderAdapter(_reports_render_svc),
        "report.list_exports": ReportListExportsAdapter(_reports_render_svc),
        "report.get_export": ReportGetExportAdapter(_reports_render_svc),
    }

    orchestrator = AgentOrchestrator(tool_adapters=adapters, project_service=project_service)
    repo = AgentRepository(db_session)
    return PlanningAgentService(
        repository=repo,
        gateway=gateway,
        registry=registry,
        orchestrator=orchestrator,
    )


def _get_planning_agent_service(
    db_session: SASession = Depends(_get_db_session),  # noqa: B008
) -> PlanningAgentService:
    """FastAPI dependency for local/test composition with the fake gateway."""
    from cold_storage.modules.planning_agent.infrastructure.fake_gateways import (
        FakeAgentModelGateway,
    )

    return _build_planning_agent_service(db_session, FakeAgentModelGateway())


def _get_strict_planning_agent_service(
    db_session: SASession = Depends(_get_db_session),  # noqa: B008
) -> PlanningAgentService:
    """FastAPI dependency for the enabled-ready MiMo composition only."""
    from cold_storage.bootstrap.dependencies import get_agent_gateway

    return _build_planning_agent_service(db_session, get_agent_gateway())


class _AgentCapabilityNotReadyError(RuntimeError):
    """Internal route-guard signal for a non-READY strict Agent."""

    def __init__(self, failure_code: str | None = None) -> None:
        self.failure_code = failure_code or "AGENT_PROVIDER_UNAVAILABLE"
        super().__init__(self.failure_code)


def _agent_capability_not_ready_response(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return the frozen safe provider envelope for a guarded route."""
    from cold_storage.modules.planning_agent.domain.errors import provider_failure_metadata

    failure_code = (
        exc.failure_code
        if isinstance(exc, _AgentCapabilityNotReadyError)
        else "AGENT_PROVIDER_UNAVAILABLE"
    )
    try:
        metadata = provider_failure_metadata(failure_code)
    except (TypeError, ValueError):
        metadata = provider_failure_metadata("AGENT_PROVIDER_UNAVAILABLE")
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": metadata.code.value,
                "message": metadata.safe_message,
                "details": {"retryable": metadata.retryable},
            }
        },
    )


def _make_guarded_strict_planning_agent_service(
    authority_box: list[StrictRuntimeAuthority | None],
    authority_lock: threading.RLock,
) -> Callable[..., PlanningAgentService]:
    """Build the request dependency that gates real Agent behavior.

    Strict mode may retain a real route surface while provider readiness is
    transiently unavailable.  The per-app immutable authority is the only
    source consulted before resolving the real gateway; route presence and
    ordinary ``app.state`` flags are deliberately not used.
    """

    def _ensure_ready() -> None:
        with authority_lock:
            authority = authority_box[0]
            evidence = getattr(authority, "agent_evidence", None)
            state = getattr(authority, "agent_capability_state", None)
            verified_ready = (
                state == AgentCapabilityState.ENABLED_READY.value
                and getattr(getattr(evidence, "state", None), "value", None)
                == AgentCapabilityState.ENABLED_READY.value
                and bool(getattr(evidence, "provider_probe_passed", False))
                and bool(getattr(evidence, "provider_schema_verified", False))
                and bool(getattr(evidence, "composition_passed", False))
                and bool(getattr(evidence, "route_audit_passed", False))
            )
            failure_code = getattr(evidence, "failure_code", None)
        if not verified_ready:
            raise _AgentCapabilityNotReadyError(failure_code)

    def _get_guarded_service(
        _verified: None = Depends(_ensure_ready),  # noqa: B008
        db_session: SASession = Depends(_get_db_session),  # noqa: B008
    ) -> PlanningAgentService:

        from cold_storage.bootstrap.dependencies import get_agent_gateway

        return _build_planning_agent_service(db_session, get_agent_gateway())

    return _get_guarded_service


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

# R8: Per-app strict authority captured by the lifespan closure.
# Each create_app() call creates its own _authority_box list.
# The lifespan closure captures the box reference, not the value.
# The box is filled AFTER all routes are registered.
# This guarantees per-app isolation: multiple create_app() calls
# produce independent authority references.
_authority_box: list[StrictRuntimeAuthority | None] = [None]


def _strict_agent_binding_manifest(state: str) -> tuple[tuple[str, str], ...]:
    """Return the immutable strict binding manifest for ``state``."""
    binding = {
        AgentCapabilityState.DISABLED.value: "disabled",
        AgentCapabilityState.ENABLED_NOT_READY.value: "enabled_not_ready",
        AgentCapabilityState.ENABLED_READY.value: "enabled_ready",
    }.get(state, "disabled")
    return (
        ("coefficient_http", "database_backed"),
        ("model_backed_agent", binding),
    )


def _publish_agent_runtime_state(
    *,
    app: FastAPI,
    authority_box: list[StrictRuntimeAuthority | None],
    authority: StrictRuntimeAuthority,
    evidence: Any,
    app_mode: AppMode,
) -> None:
    """Atomically publish one canonical authority/evidence projection."""
    from cold_storage.bootstrap.dependencies import (
        create_capability_projection,
        publish_agent_capability_evidence,
    )

    authority_box[0] = authority
    app.state._strict_runtime_authority = authority  # noqa: SLF001
    app.state.strict_capability_bindings = _strict_agent_binding_manifest(
        authority.agent_capability_state
    )
    app._agent_capability_evidence = evidence  # type: ignore[attr-defined]
    app._capability_projection = create_capability_projection(  # type: ignore[attr-defined]
        app_mode,
        evidence=evidence,
    )
    publish_agent_capability_evidence(evidence)


def _refresh_agent_capability_readiness(
    *,
    app: FastAPI,
    authority_box: list[StrictRuntimeAuthority | None],
    settings: Any,
) -> Any:
    """Run the conditional provider phase and publish a verified transition.

    The mandatory readiness tuple remains the frozen eight-probe set.  This
    conditional aggregate is executed separately for a strict, valid Agent
    configuration so a transient provider failure can demote and later
    recover the same process without rebuilding the FastAPI app.
    """
    from cold_storage.bootstrap.runtime_readiness import (
        UnsafeStrictCapabilityWiring,
        assert_no_unsafe_strict_capabilities,
        finalize_agent_capability_evidence,
        resolve_agent_capability_evidence,
    )

    authority_lock: threading.RLock = app._agent_authority_lock  # type: ignore[attr-defined]
    with authority_lock:
        current_authority = authority_box[0]
        current_evidence = getattr(app, "_agent_capability_evidence", None)
        resolution = settings.agent_capability_resolution
        if (
            current_authority is None
            or current_evidence is None
            or current_authority.agent_candidate is False
            or not resolution.enablement_intent_present
            or not resolution.configuration_valid
        ):
            return current_evidence

        provider_probe = getattr(app, "_agent_provider_probe", None)
        preflight = resolve_agent_capability_evidence(
            settings,
            provider_probe=provider_probe,
        )
        if not preflight.provider_probe_passed:
            not_ready_authority = replace(
                current_authority,
                agent_capability_state=AgentCapabilityState.ENABLED_NOT_READY.value,
                agent_evidence=preflight,
                agent_candidate=True,
            )
            _publish_agent_runtime_state(
                app=app,
                authority_box=authority_box,
                authority=not_ready_authority,
                evidence=preflight,
                app_mode=app._agent_app_mode,  # type: ignore[attr-defined]
            )
            return preflight

        candidate_authority = replace(
            current_authority,
            agent_capability_state=AgentCapabilityState.ENABLED_NOT_READY.value,
            agent_evidence=preflight,
            agent_candidate=True,
        )
        candidate_manifest = _strict_agent_binding_manifest(
            AgentCapabilityState.ENABLED_NOT_READY.value
        )
        try:
            candidate_audit = assert_no_unsafe_strict_capabilities(
                app=app,
                authority=candidate_authority,
                binding_manifest=candidate_manifest,
            )
            final_evidence = finalize_agent_capability_evidence(
                preflight,
                audit_evidence=candidate_audit,
            )
            if final_evidence.state is not AgentCapabilityState.ENABLED_READY:
                not_ready_authority = replace(
                    candidate_authority,
                    agent_capability_state=final_evidence.state.value,
                    agent_evidence=final_evidence,
                )
                _publish_agent_runtime_state(
                    app=app,
                    authority_box=authority_box,
                    authority=not_ready_authority,
                    evidence=final_evidence,
                    app_mode=app._agent_app_mode,  # type: ignore[attr-defined]
                )
                return final_evidence
            final_authority = replace(
                candidate_authority,
                agent_capability_state=AgentCapabilityState.ENABLED_READY.value,
                agent_evidence=final_evidence,
            )
            final_manifest = _strict_agent_binding_manifest(
                AgentCapabilityState.ENABLED_READY.value
            )
            # Audit the exact final authority and final manifest before either
            # is published.  This is deliberately a second, non-self-attested
            # audit rather than a mutation followed by a readback.
            final_audit = assert_no_unsafe_strict_capabilities(
                app=app,
                authority=final_authority,
                binding_manifest=final_manifest,
            )
            if not (final_audit.composition_passed and final_audit.route_audit_passed):
                raise RuntimeError("strict agent final authority audit did not pass")
        except (UnsafeStrictCapabilityWiring, RuntimeError):
            not_ready = replace(
                preflight,
                state=AgentCapabilityState.ENABLED_NOT_READY,
                composition_passed=False,
                route_audit_passed=False,
                failure_code="AGENT_PROVIDER_UNAVAILABLE",
                global_readiness="FAIL",
                route_exposure="DISABLED_ROUTE_MATRIX",
            )
            not_ready_authority = replace(
                current_authority,
                agent_capability_state=AgentCapabilityState.ENABLED_NOT_READY.value,
                agent_evidence=not_ready,
                agent_candidate=True,
            )
            _publish_agent_runtime_state(
                app=app,
                authority_box=authority_box,
                authority=not_ready_authority,
                evidence=not_ready,
                app_mode=app._agent_app_mode,  # type: ignore[attr-defined]
            )
            return not_ready

        _publish_agent_runtime_state(
            app=app,
            authority_box=authority_box,
            authority=final_authority,
            evidence=final_evidence,
            app_mode=app._agent_app_mode,  # type: ignore[attr-defined]
        )
        return final_evidence


def _make_lifespan(
    authority_box: list[StrictRuntimeAuthority | None],
    agent_client_factory: Callable[..., Any] | None = None,
) -> Any:
    """Create a per-app lifespan closure that captures the authority box.

    R8: The authority_box is a one-element mutable list created per
    create_app() call. The lifespan reads authority_box[0] at startup
    time (not at creation time), which is set after all routes are
    registered. This guarantees per-app isolation.

    The authority is NEVER read from app.state for security decisions.
    app.state retains a diagnostic copy only.
    """

    @asynccontextmanager
    async def _lifespan_inner(app: FastAPI):  # type: ignore[no-untyped-def]
        # R8: Read the authority from the per-app box, NOT from app.state.
        auth = authority_box[0]
        if auth is None:
            raise RuntimeError(
                "strict runtime authority not initialized — "
                "create_app() must fill the authority box before lifespan starts"
            )
        try:
            if agent_client_factory is None:
                init_dependencies(get_settings(), app=app, strict_runtime_authority=auth)
            else:
                init_dependencies(
                    get_settings(),
                    app=app,
                    strict_runtime_authority=auth,
                    agent_client_factory=agent_client_factory,
                )
            if auth.agent_candidate:
                from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
                    assert_no_unsafe_strict_capabilities,
                    finalize_agent_capability_evidence,
                )

                # Re-run the immutable authority audit at the transition
                # boundary.  READY is never inferred from the fact that a
                # router was registered or that dependency initialization
                # returned successfully.
                audit_evidence = assert_no_unsafe_strict_capabilities(
                    app=app,
                    authority=auth,
                    binding_manifest=_strict_agent_binding_manifest(auth.agent_capability_state),
                )
                if auth.agent_evidence is None:
                    raise RuntimeError("strict agent startup is missing preflight evidence")
                final_evidence = finalize_agent_capability_evidence(
                    auth.agent_evidence,
                    audit_evidence=audit_evidence,
                )
                final_authority = replace(
                    auth,
                    agent_capability_state=final_evidence.state.value,
                    agent_evidence=final_evidence,
                )
                if final_evidence.state is AgentCapabilityState.ENABLED_READY:
                    final_manifest = _strict_agent_binding_manifest(
                        AgentCapabilityState.ENABLED_READY.value
                    )
                    # Audit the exact final authority and binding manifest
                    # before either is published or becomes request-visible.
                    final_audit = assert_no_unsafe_strict_capabilities(
                        app=app,
                        authority=final_authority,
                        binding_manifest=final_manifest,
                    )
                    if not (final_audit.composition_passed and final_audit.route_audit_passed):
                        raise RuntimeError("strict agent final authority audit did not pass")
                with app._agent_authority_lock:  # type: ignore[attr-defined]
                    _publish_agent_runtime_state(
                        app=app,
                        authority_box=authority_box,
                        authority=final_authority,
                        evidence=final_evidence,
                        app_mode=app._agent_app_mode,  # type: ignore[attr-defined]
                    )
            yield
        finally:
            shutdown_dependencies()

    return _lifespan_inner


# --------------------------------------------------------------------------- App factory
# ---------------------------------------------------------------------------


def create_app(
    project_service: ProjectService | None = None,
    *,
    agent_provider_probe: "AgentProviderProbe | None" = None,
    agent_client_factory: Callable[..., Any] | None = None,
) -> FastAPI:
    configure_logging()
    # R8: Create a per-app authority box. The lifespan closure captures
    # this specific list instance, guaranteeing per-app isolation.
    _app_authority_box: list[StrictRuntimeAuthority | None] = [None]
    app = FastAPI(
        title="Cold Storage Planning Agent V1",
        lifespan=_make_lifespan(_app_authority_box, agent_client_factory),
    )
    app._agent_authority_lock = threading.RLock()  # type: ignore[attr-defined]
    app.add_exception_handler(_AgentCapabilityNotReadyError, _agent_capability_not_ready_response)

    # --- Observability middleware (must be first to capture all requests) ---
    # --- Metrics endpoint ---
    from cold_storage.bootstrap.metrics.endpoint import (  # noqa: PLC0415
        create_metrics_endpoint,
    )
    from cold_storage.bootstrap.metrics.registry import (  # noqa: PLC0415
        get_metrics,
    )
    from cold_storage.bootstrap.middleware.correlation_id import (  # noqa: PLC0415
        CorrelationIdMiddleware,
    )
    from cold_storage.bootstrap.middleware.structured_logging import (  # noqa: PLC0415
        StructuredLoggingMiddleware,
    )

    # Register default route templates for bounded cardinality
    _metrics = get_metrics()
    _default_routes = [
        "/api/v1/projects/{project_id}",
        "/api/v1/projects/{project_id}/versions/{version_number}",
        "/api/v1/projects/{project_id}/inputs/{version_number}",
        "/api/v1/projects/{project_id}/calculate/{version_number}",
        "/api/v1/planning/run",
        "/api/v1/agent/sessions",
        "/api/v1/agent/sessions/{session_id}",
        "/health/live",
        "/health/ready",
        "/api/v1/demo/overview",
    ]
    for route in _default_routes:
        _metrics.register_route_template(route)

    # Register dependencies
    for dep in [
        "database",
        "redis",
        "artifact_storage",
        "outbox_dispatcher",
        "audit_log_writer",
        "health_endpoint",
    ]:
        _metrics.register_dependency(dep)

    # D-S4-05: Register capability metric. Recorded below after
    # initial_mode is resolved (see lines 650-656).
    _metrics.register_capability("model_backed_agent")

    app.add_api_route("/metrics", create_metrics_endpoint(_metrics))
    # Observability middleware – added after _metrics so we can inject it.
    app.add_middleware(StructuredLoggingMiddleware, metrics=_metrics)
    app.add_middleware(CorrelationIdMiddleware)

    calculator = CalculationService()
    zone_planner = ColdRoomZonePlanner()
    investment_estimator = InvestmentEstimator()
    core_calculation_service = CoreCalculationService()

    # D-S4-01: Coefficient routes are mounted in ALL modes. Local/test
    # use a process-local service; staging/production use a delayed
    # provider that resolves the database-backed service per-request.
    initial_settings = get_settings()
    initial_mode = resolve_app_mode(initial_settings)

    from cold_storage.bootstrap.runtime_readiness import (
        resolve_agent_capability_evidence,
    )

    if (
        agent_provider_probe is None
        and initial_mode in (AppMode.STAGING, AppMode.PRODUCTION)
        and initial_settings.agent_enablement_intent_present
    ):
        from cold_storage.bootstrap.dependencies import (  # noqa: PLC0415
            canonical_agent_provider_probe,
        )

        agent_provider_probe = canonical_agent_provider_probe(
            client_factory=agent_client_factory,
        )

    agent_evidence = resolve_agent_capability_evidence(
        initial_settings,
        provider_probe=agent_provider_probe,
    )
    app._agent_provider_probe = agent_provider_probe  # type: ignore[attr-defined]
    app._agent_app_mode = initial_mode  # type: ignore[attr-defined]

    # D-S4-04: Create immutable capability projection bound to this app.
    from cold_storage.bootstrap.dependencies import create_capability_projection

    app._agent_capability_evidence = agent_evidence  # type: ignore[attr-defined]
    app._capability_projection = create_capability_projection(  # type: ignore[attr-defined]
        initial_mode,
        evidence=agent_evidence,
    )

    _coeff_provider: Any = None
    _frozen_coeff_auth: list[CoefficientRouteAuthority] = []

    if initial_mode in (AppMode.LOCAL, AppMode.TEST):
        coefficient_service = CoefficientService()
        coeff_evidence = register_coefficient_routes(app, coefficient_service)
        _coeff_provider = coefficient_service
    else:
        from cold_storage.bootstrap.dependencies import (  # noqa: PLC0415
            get_production_coefficient_service,
        )

        coeff_evidence = register_coefficient_routes(app, get_production_coefficient_service)
        _coeff_provider = get_production_coefficient_service

    # D-S4-06: Store coefficient route evidence for strict audit.
    # R6: Keep on app.state for backward compatibility, but the
    # authoritative copy is in _strict_runtime_authority below.
    app.state.coefficient_route_evidence = coeff_evidence

    # Build CoefficientRouteAuthority objects from the evidence.
    if coeff_evidence and "endpoints" in coeff_evidence:
        for _cm, _cp, _cep in coeff_evidence["endpoints"]:
            _frozen_coeff_auth.append(
                CoefficientRouteAuthority(method=_cm, path=_cp, endpoint=_cep)
            )

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

    def _workflow_service_factory(request: Any) -> Any:
        from cold_storage.bootstrap.dependencies import get_project_service

        override = request.app.dependency_overrides.get(get_project_service, get_project_service)
        project_service = override()
        from cold_storage.modules.knowledge.infrastructure.repository import KnowledgeRepository
        from cold_storage.modules.reports.application.service import _default_trusted_operator
        from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository
        from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query
        from cold_storage.modules.workflow.application.service import WorkflowAggregateService

        engine = getattr(project_service, "engine", None)
        if engine is None:
            engine = get_engine()
        session = SASession(bind=engine, expire_on_commit=False)
        scheme_query = build_sqlalchemy_scheme_query(session)
        report_repo = SQLReportRepository(session)
        knowledge_repo = KnowledgeRepository(session)

        def _read_revision(revision_id: str) -> dict[str, Any] | None:
            record = knowledge_repo.get_revision(revision_id)
            if record is None:
                return None
            return {
                "id": record.id,
                "document_id": record.document_id,
                "content_sha256": record.content_sha256,
                "requires_review": record.requires_review,
                "requires_ocr": record.requires_ocr,
                "ingestion_status": record.ingestion_status,
                "original_filename": record.original_filename,
                "version_label": record.version_label,
                "revision_number": record.revision_number,
                "review_status": record.review_status,
            }

        def _read_document(document_id: str) -> dict[str, Any] | None:
            record = knowledge_repo.get_document(document_id)
            if record is None:
                return None
            return {
                "id": record.id,
                "code": record.code,
                "title": record.title,
            }

        def _read_page_evidence(revision_id: str) -> list[dict[str, Any]]:
            evidence_records = knowledge_repo.list_page_evidence(revision_id)
            entries: list[dict[str, Any]] = []
            for evidence in evidence_records:
                doc = knowledge_repo.get_document(evidence.document_id)
                entries.append(
                    {
                        "source_page_evidence_id": evidence.source_page_evidence_id,
                        "page_number": evidence.page_number,
                        "extraction_method": evidence.extraction_method,
                        "extraction_status": evidence.extraction_status,
                        "source_authority": evidence.source_authority,
                        "source_content_sha256": evidence.source_content_sha256,
                        "original_filename": evidence.original_filename,
                        "is_complete": evidence.is_complete,
                        "is_ocr_derived": evidence.is_derived_evidence,
                        "requires_review": evidence.requires_review,
                        "review_status": evidence.review_status,
                        "confidence": evidence.ocr_confidence,
                        "confidence_source": evidence.confidence_source,
                        "ocr_engine": evidence.ocr_engine,
                        "ingestion_provenance": dict(evidence.ingestion_provenance or {}),
                        "document_code": doc.code if doc is not None else "",
                        "document_title": doc.title if doc is not None else "",
                    }
                )
            return entries

        capability_projection = getattr(request.app, "_capability_projection", None)
        agent_capabilities = (
            [dict(entry) for entry in capability_projection]
            if capability_projection is not None
            else []
        )

        return WorkflowAggregateService(
            project_service=project_service,
            scheme_query=scheme_query,
            report_repository=report_repo,
            knowledge_revision_reader=_read_revision,
            knowledge_page_evidence_reader=_read_page_evidence,
            knowledge_document_reader=_read_document,
            agent_capability_projection=agent_capabilities,
            trusted_operator=_default_trusted_operator,
        )

    from cold_storage.modules.workflow.api.routes import register_workflow_routes

    register_workflow_routes(app, _workflow_service_factory)

    if project_service is not None:
        app.dependency_overrides[get_project_service] = lambda: project_service

    @app.get("/health/live")
    def live() -> dict[str, str]:
        """Liveness MUST NOT query the database (D-S2-03).

        Liveness reflects only that the application process and
        request loop are alive. No DB, no migration state, no
        artifact storage, no external services. Returns 200 whenever
        the FastAPI worker can answer.
        """
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> Any:
        """Readiness is dynamic and dependency-aware (D-S2-03, D-S2-04).

        Returns:

        * HTTP 200 when the readiness state singleton is
          ``READY`` and all readiness probes pass.
        * HTTP 503 when the state is ``INITIALIZING``,
          ``DRAINING``, ``SHUTDOWN_COMPLETE``, or any probe fails.

        D-S4-04: Response includes a safe capability projection.
        """
        from fastapi import Response

        from cold_storage.bootstrap.environment_model import (  # noqa: PLC0415
            ConfigurationError as _ConfigurationError,
        )
        from cold_storage.bootstrap.runtime_readiness import (
            ReadinessState,
            canonical_settings,
            get_readiness_state,
            mandatory_readiness_probes,
            run_readiness_phase,
        )

        # D-S4-04: Safe capability projection bound to app instance.
        def _capability_projection() -> list[dict[str, object]]:
            # Prefer the app-bound immutable projection (D-S4-04).
            bound = getattr(app, "_capability_projection", None)
            if bound is not None:
                return [dict(c) for c in bound]
            # Fallback to singleton-based projection for tests that
            # create apps without the full factory.
            from cold_storage.bootstrap.dependencies import agent_capability_projection

            return [dict(c) for c in agent_capability_projection()]

        try:
            probe_settings = canonical_settings()
            configuration_failed: tuple[str, str] | None = None
        except _ConfigurationError:
            probe_settings = None
            configuration_failed = (
                _ConfigurationError.__name__,
                "settings unavailable",
            )
        except Exception:
            probe_settings = None
            configuration_failed = (
                _ConfigurationError.__name__,
                "settings unavailable",
            )

        state: ReadinessState | None = get_readiness_state()
        snapshot = state.snapshot() if state is not None else {"state": "INITIALIZING"}
        state_name = snapshot.get("state", "INITIALIZING")

        # DRAINING / SHUTDOWN_COMPLETE: refuse work, return 503.
        if state_name in ("DRAINING", "SHUTDOWN_COMPLETE"):
            return Response(
                status_code=503,
                media_type="application/json",
                content=json.dumps(
                    {
                        "status": "draining" if state_name == "DRAINING" else "shutdown",
                        "state": state_name,
                        "capabilities": _capability_projection(),
                    }
                ),
            )

        if probe_settings is None:
            safe_code, safe_detail = configuration_failed or (
                _ConfigurationError.__name__,
                "settings unavailable",
            )
            return Response(
                status_code=503,
                media_type="application/json",
                content=json.dumps(
                    {
                        "status": "not_ready",
                        "state": state_name,
                        "check_code": safe_code,
                        "capabilities": _capability_projection(),
                    }
                ),
            )

        # The mandatory readiness tuple remains exactly the frozen eight
        # probes.  Strict Agent provider/schema readiness is a separate,
        # conditional phase so a transient provider failure can demote and
        # later recover the same process without rebuilding the app.
        _refresh_agent_capability_readiness(
            app=app,
            authority_box=_app_authority_box,
            settings=probe_settings,
        )

        outcomes = run_readiness_phase(
            settings=probe_settings,
            readiness_probes=mandatory_readiness_probes(),
        )
        agent_evidence = getattr(app, "_agent_capability_evidence", None)
        agent_state = getattr(getattr(agent_evidence, "state", None), "value", None)
        agent_blocked = agent_state == AgentCapabilityState.ENABLED_NOT_READY.value
        ok = all(o.status == "pass" for o in outcomes) and not agent_blocked

        if state_name == "READY" and ok:
            return {
                "status": "ready",
                "state": state_name,
                "capabilities": _capability_projection(),
            }

        failed_codes = sorted({o.code for o in outcomes if o.code})
        if agent_blocked and agent_evidence is not None:
            failure_code = getattr(agent_evidence, "failure_code", None)
            if failure_code:
                failed_codes.append(failure_code)
        primary_code = failed_codes[0] if failed_codes else "READINESS_PROBE_TIMEOUT"
        body = {
            "status": "not_ready",
            "state": state_name,
            "check_code": primary_code,
            "outcomes": [o.to_dict() for o in outcomes],
            "capabilities": _capability_projection(),
        }
        return Response(
            status_code=503,
            media_type="application/json",
            content=json.dumps(body),
        )

    # D-S4-05: Register capability metric. Record status based on
    # the resolved app mode, not deferred to init_dependencies.
    _metrics.register_capability("model_backed_agent")
    _metrics.record_capability_status(
        "model_backed_agent",
        is_available=initial_mode in (AppMode.LOCAL, AppMode.TEST),
    )

    # D-S4-05: Demo routes are local/test only. Staging/production
    # must not mount these routes to avoid FakeAgentModelGateway construction.
    if initial_mode in (AppMode.LOCAL, AppMode.TEST):

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
        from cold_storage.modules.projects.application.workbench_planning import (
            WorkbenchPlanningError,
            run_persisted_workbench_planning,
        )

        try:
            return run_persisted_workbench_planning(
                project_service=service,
                project_id=project_id,
                version_number=version,
                inputs=inputs,
                zone_planner=zone_planner,
                investment_estimator=investment_estimator,
                actor="api",
            )
        except WorkbenchPlanningError as exc:
            return {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            }

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

    # D-S4-02/P2-C: strict modes use a real candidate router only after
    # provider/schema preflight. Local/test and disabled strict paths expose
    # the frozen disabled route matrix (V0.4 P4 fail-closed acceptance).
    _frozen_agent_auth: list[AgentRouteAuthority] = []
    _agent_state = agent_evidence.state.value
    _agent_candidate = initial_mode in (AppMode.STAGING, AppMode.PRODUCTION) and (
        initial_settings.agent_enablement_intent_present
        and initial_settings.agent_capability_resolution.configuration_valid
    )

    if _agent_candidate:
        _guarded_service_factory = _make_guarded_strict_planning_agent_service(
            _app_authority_box,
            app._agent_authority_lock,  # type: ignore[attr-defined]
        )
        _agent_router = _create_agent_router(_guarded_service_factory)
        app.include_router(_agent_router)
        for _registered_route in _agent_router.routes:
            route_path = getattr(_registered_route, "path", "")
            if not isinstance(route_path, str) or not route_path.startswith("/api/v1/agent/"):
                continue
            endpoint = getattr(_registered_route, "endpoint", None)
            methods = getattr(_registered_route, "methods", None)
            if endpoint is None or not methods:
                continue
            for method in methods:
                _frozen_agent_auth.append(
                    AgentRouteAuthority(method=method, path=route_path, endpoint=endpoint)
                )
    else:
        from fastapi.responses import JSONResponse as _JSONResponse  # noqa: PLC0415

        if agent_evidence.state is AgentCapabilityState.DISABLED:
            _agent_error = {
                "error": {
                    "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
                    "message": "Model-backed agent not in V0.2 production scope.",
                    "details": {"retryable": False},
                }
            }
        else:
            from cold_storage.modules.planning_agent.domain.errors import (
                provider_failure_metadata,
            )

            _metadata = provider_failure_metadata(
                agent_evidence.failure_code or "AGENT_PROVIDER_UNAVAILABLE"
            )
            _agent_error = {
                "error": {
                    "code": _metadata.code.value,
                    "message": _metadata.safe_message,
                    "details": {"retryable": _metadata.retryable},
                }
            }
        _agent_routes = (
            ("POST", "/api/v1/agent/sessions"),
            ("GET", "/api/v1/agent/sessions"),
            ("GET", "/api/v1/agent/sessions/{session_id}"),
            ("GET", "/api/v1/agent/sessions/{session_id}/messages"),
            ("POST", "/api/v1/agent/sessions/{session_id}/messages"),
            ("GET", "/api/v1/agent/sessions/{session_id}/turns/{turn_id}"),
            ("GET", "/api/v1/agent/sessions/{session_id}/tool-calls"),
            ("POST", "/api/v1/agent/tool-calls/{tool_call_id}/confirm"),
            ("POST", "/api/v1/agent/tool-calls/{tool_call_id}/reject"),
            ("POST", "/api/v1/agent/sessions/{session_id}/cancel"),
        )

        def _disabled_agent_endpoint(name: str) -> Callable[[], _JSONResponse]:
            def _ep() -> _JSONResponse:
                return _JSONResponse(status_code=503, content=_agent_error)

            _ep.__name__ = name
            return _ep

        for _idx, (_method, _path) in enumerate(_agent_routes, start=1):
            _ep = _disabled_agent_endpoint(f"disabled_agent_{_idx}")
            app.add_api_route(
                _path,
                _ep,
                methods=[_method],
                status_code=503,
                tags=["agent"],
                operation_id=f"disabled_model_backed_agent_{_idx}",
            )
            _frozen_agent_auth.append(AgentRouteAuthority(method=_method, path=_path, endpoint=_ep))

    app.state.frozen_agent_endpoint_authority = tuple(
        (a.method, a.path, a.endpoint) for a in _frozen_agent_auth
    )

    # D-S4-06: Immutable binding manifest. Registered after route wiring,
    # before lifespan startup. The strict audit checks this manifest.
    if initial_mode in (AppMode.STAGING, AppMode.PRODUCTION):
        app.state.strict_capability_bindings = (
            ("coefficient_http", "database_backed"),
            (
                "model_backed_agent",
                {
                    AgentCapabilityState.DISABLED.value: "disabled",
                    AgentCapabilityState.ENABLED_NOT_READY.value: "enabled_not_ready",
                    AgentCapabilityState.ENABLED_READY.value: "enabled_ready",
                }.get(_agent_state, "disabled"),
            ),
        )
    else:
        app.state.strict_capability_bindings = ()

    # R6: Build the composition-root strict runtime authority.
    # This is the single source of truth for the strict audit.
    # The authority is captured by the per-app lifespan closure.
    _agent_auth_tuple = tuple(_frozen_agent_auth) if _frozen_agent_auth else ()
    _coeff_auth_tuple = tuple(_frozen_coeff_auth) if _frozen_coeff_auth else ()
    _strict_authority = _build_strict_authority(
        agent_routes=_agent_auth_tuple,
        coefficient_routes=_coeff_auth_tuple,
        coefficient_provider=_coeff_provider,
        capability_mode=(
            "enabled" if initial_mode in (AppMode.STAGING, AppMode.PRODUCTION) else "disabled"
        ),
        agent_capability_state=_agent_state,
        agent_evidence=agent_evidence,
        agent_service_factory=(_get_strict_planning_agent_service if _agent_candidate else None),
        agent_candidate=_agent_candidate,
    )
    app.state._strict_runtime_authority = _strict_authority  # noqa: SLF001

    # R8: Fill the per-app authority box so the lifespan can read it.
    # This is the ONLY place the authority is set for the lifespan.
    # Each create_app() call has its own _app_authority_box, guaranteeing
    # per-app isolation.
    _app_authority_box[0] = _strict_authority

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
        ReportRenderUnitOfWork,
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
        from cold_storage.modules.reports.application.service import _default_trusted_operator
        from cold_storage.modules.reports.infrastructure.real_data_provider import (
            RealReportDataProvider,
        )
        from cold_storage.modules.schemes.application.query import (
            build_sqlalchemy_scheme_query,
        )

        repo = SQLReportRepository(db_session)
        scheme_query = build_sqlalchemy_scheme_query(db_session)
        data_provider = RealReportDataProvider(scheme_query=scheme_query)
        assembler = ReportAssembler(data_provider=data_provider)
        return ReportService(
            repository=repo,
            assembler=assembler,
            scheme_review_query=scheme_query,
            trusted_operator=_default_trusted_operator,
        )

    def _get_report_render_service(
        db_session: SASession = Depends(_get_reports_db_session),  # noqa: B008
    ) -> ReportRenderService:
        repo = SQLReportRepository(db_session)
        from cold_storage.modules.reports.application.service import _default_trusted_operator
        from cold_storage.modules.schemes.application.query import (
            build_sqlalchemy_scheme_query,
        )

        scheme_query = build_sqlalchemy_scheme_query(db_session)
        # D-S4-11: staging/production use canonical_settings() singleton.
        # local/test fall back to the app-factory-resolved settings so
        # that TestCreateAppE2E (which never initializes canonical_settings)
        # continues to work.
        if initial_mode in (AppMode.STAGING, AppMode.PRODUCTION):
            from cold_storage.bootstrap.runtime_readiness import (
                canonical_settings,
            )

            _settings = canonical_settings()
        else:
            _settings = get_settings()
        _storage_dir = _settings.storage_dir
        if not _storage_dir:
            raise RuntimeError("storage_dir not configured; cannot render reports")
        artifact_storage = ReportArtifactStorage(base_dir=_storage_dir)
        uow = ReportRenderUnitOfWork(
            db_session,
            report_repo=repo,
            artifact_repo=repo,
            session_factory=lambda: SASession(
                bind=db_session.bind,
                expire_on_commit=False,
            ),
        )
        return ReportRenderService(
            uow=uow,
            storage=artifact_storage,
            template_repo=repo,
            scheme_review_query=scheme_query,
            trusted_operator=_default_trusted_operator,
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
