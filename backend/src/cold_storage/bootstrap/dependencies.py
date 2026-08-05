"""Runtime dependency management — no import-time singletons."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterable
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session as SASession
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.database import create_engine_from_settings, dispose_engine
from cold_storage.bootstrap.settings import Settings
from cold_storage.modules.coefficients.application.resolver import (
    ApprovedCoefficientResolver,
)
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService

# F-PR76-BLOCKER-03: the strict-mode composition contract forbids
# importing the fake model gateway or the process-local coefficient
# service from this module at runtime in staging / production. The
# names below are recorded as evidence tokens in the composition
# manifest (D-S2-06.a) so the defensive audit can prove they were
# never constructed in strict modes without ``runtime_readiness``
# having to import the business types themselves.
_COMPOSITION_TOKEN_FAKE_AGENT_GATEWAY = "FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED"
_COMPOSITION_TOKEN_PROCESS_LOCAL_COEFFICIENT = "PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED"
_COMPOSITION_TOKEN_DATABASE_COEFFICIENT = "DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"
_COMPOSITION_TOKEN_PROVIDER_ERROR = "COMPOSITION_MANIFEST_PROVIDER_ERROR"

_MODEL_BACKED_AGENT_CAPABILITY = "model_backed_agent"
_STRICT_BINDINGS: tuple[tuple[str, str], ...] = (
    ("coefficient_http", "database_backed"),
    (_MODEL_BACKED_AGENT_CAPABILITY, "disabled"),
)
_AGENT_DISABLED_ERROR = {
    "error": {
        "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
        "message": "Model-backed planning agent capability is not included in V0.2 production scope.",
        "details": {"retryable": False},
    }
}
_AGENT_ROUTES: tuple[tuple[str, str], ...] = (
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


if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from cold_storage.modules.coefficients.infrastructure.database import (
        DatabaseCoefficientService,
    )
    from cold_storage.modules.schemes.application.production_service import (
        ProductionSchemeService,
    )

_singletons: dict[str, Any] = {}
_composition_tokens: set[str] = set()


def init_dependencies(settings: Settings, *, app: Any = None) -> None:
    """Create and publish the canonical runtime dependency graph.

    TASK-012 Slice 4 extends the transactional Slice 2 lifecycle with a
    database-backed coefficient HTTP authority, strict disabled-agent routes,
    binding-identity audit evidence, canonical report artifact storage, and a
    shared readiness/metrics capability projection.
    """
    from cold_storage.bootstrap.mode import AppMode, resolve_app_mode  # noqa: PLC0415
    from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
        canonical_settings,
        get_or_init_readiness_state,
        mandatory_startup_probes,
        reset_composition_manifest_provider,
        run_startup_phase,
        set_canonical_settings,
        set_composition_manifest_provider,
    )

    _clear_composition_tokens()
    reset_composition_manifest_provider()
    set_composition_manifest_provider(_composition_manifest_provider)
    set_canonical_settings(settings)

    try:
        engine = create_engine_from_settings(settings)
    except Exception:
        _rollback_bootstrap_state()
        raise

    try:
        mode = resolve_app_mode(settings)
    except Exception:
        mode = None

    _singletons["engine"] = engine
    _singletons["app_mode"] = mode
    try:
        project_service = DatabaseProjectService(engine)
    except Exception:
        shutdown_dependencies()
        raise
    _singletons["project_service"] = project_service

    if mode in (AppMode.STAGING, AppMode.PRODUCTION):
        agent_service: Any = _StrictModeAgentService()
    else:
        from cold_storage.modules.planning_agent.application.agent_service import (  # noqa: PLC0415
            LegacyPlanningAgentService,
        )
        from cold_storage.modules.planning_agent.infrastructure.fake_gateways import (  # noqa: PLC0415
            FakeAgentModelGateway,
        )

        _record_composition_token(_COMPOSITION_TOKEN_FAKE_AGENT_GATEWAY)
        agent_service = LegacyPlanningAgentService(
            model_gateway=FakeAgentModelGateway(),
        )
    _singletons["agent_service"] = agent_service

    # The production coefficient HTTP authority is a singleton bound to the
    # same canonical engine used by startup/readiness. Construction performs
    # no database query; publication and positive composition evidence happen
    # before strict route registration and the final startup audit.
    if mode in (AppMode.STAGING, AppMode.PRODUCTION):
        try:
            from cold_storage.modules.coefficients.infrastructure.database import (  # noqa: PLC0415
                DatabaseCoefficientService,
            )

            production_coefficient_service = DatabaseCoefficientService(engine)
        except Exception:
            shutdown_dependencies()
            raise
        _singletons["production_coefficient_service"] = production_coefficient_service
        _record_composition_token(_COMPOSITION_TOKEN_DATABASE_COEFFICIENT)

    try:
        from cold_storage.bootstrap.production_composition import (  # noqa: PLC0415
            compose_production_scheme_service,
        )

        session_factory_obj: sessionmaker[Any] = sessionmaker(bind=engine, expire_on_commit=False)
        production_service: ProductionSchemeService = compose_production_scheme_service(
            session_factory_obj,
        )
    except Exception:
        shutdown_dependencies()
        raise
    _singletons["production_scheme_service"] = production_service
    _singletons["production_session_factory"] = session_factory_obj

    try:
        from cold_storage.bootstrap.production_composition import (  # noqa: PLC0415
            compose_production_coefficient_resolver,
        )

        _singletons["production_coefficient_resolver"] = compose_production_coefficient_resolver(
            engine=engine,
        )
    except Exception:
        shutdown_dependencies()
        raise

    try:
        from cold_storage.bootstrap.startup_readiness import (  # noqa: PLC0415
            run_startup_readiness_or_raise,
        )

        readiness_outcome = run_startup_readiness_or_raise(settings=settings, engine=engine)
    except Exception:
        shutdown_dependencies()
        raise
    _singletons["startup_readiness_outcome"] = readiness_outcome

    get_or_init_readiness_state(
        settings=settings,
        environment={k: v for k, v in __import__("os").environ.items()},
    )

    try:
        _install_slice4_runtime_audit()
        if app is not None:
            _configure_slice4_application(app=app, settings=settings, mode=mode)
        run_startup_phase(
            settings=settings,
            environment={k: v for k, v in __import__("os").environ.items()},
            startup_probes=mandatory_startup_probes(),
            app=app,
        )
    except Exception:
        shutdown_dependencies()
        raise

    _ = canonical_settings


def _StrictModeAgentService() -> Any:
    """Return an import-free strict-mode placeholder agent service."""

    class _Placeholder:
        def is_strict(self) -> bool:
            return True

    return _Placeholder()


def _record_composition_token(token: str) -> None:
    if not isinstance(token, str) or not token:
        raise ValueError("composition token must be a non-empty string")
    _composition_tokens.add(token)


def _clear_composition_tokens() -> None:
    _composition_tokens.clear()


def _composition_manifest_provider() -> frozenset[str]:
    return frozenset(_composition_tokens)


def _rollback_bootstrap_state() -> None:
    from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
        reset_canonical_settings,
        reset_composition_manifest_provider,
    )

    _clear_composition_tokens()
    reset_composition_manifest_provider()
    reset_canonical_settings()


def get_project_service() -> ProjectService:
    """Return the ProjectService singleton. Raises RuntimeError if not initialized."""
    if "project_service" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["project_service"]  # type: ignore[no-any-return]


def get_agent_service() -> Any:
    """Return the active local/test agent or strict placeholder singleton."""
    if "agent_service" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["agent_service"]


def get_engine() -> Any:
    """Return the canonical engine singleton."""
    if "engine" not in _singletons:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies(settings) first.")
    return _singletons["engine"]


def get_production_coefficient_service() -> DatabaseCoefficientService:
    """Return the strict database-backed coefficient HTTP authority.

    The stable RuntimeError is translated by the coefficient route provider to
    ``PRODUCTION_DEPENDENCIES_NOT_INITIALIZED`` without constructing a
    process-local fallback.
    """
    if "production_coefficient_service" not in _singletons:
        raise RuntimeError("Production dependencies are not initialized.")
    return _singletons["production_coefficient_service"]  # type: ignore[no-any-return]


def get_production_scheme_service() -> ProductionSchemeService:
    """Return the production SchemeRun service singleton."""
    if "production_scheme_service" not in _singletons:
        raise RuntimeError(
            "Dependencies not initialized. Call init_dependencies(settings) first.",
        )
    return _singletons["production_scheme_service"]  # type: ignore[no-any-return]


def get_production_session_factory() -> Callable[[], Any]:
    """Return the production SchemeRun session-factory singleton."""
    if "production_session_factory" not in _singletons:
        raise RuntimeError(
            "Dependencies not initialized. Call init_dependencies(settings) first.",
        )
    return _singletons["production_session_factory"]  # type: ignore[no-any-return]


def get_production_coefficient_resolver() -> ApprovedCoefficientResolver:
    """Return the production ApprovedCoefficientResolver singleton."""
    if "production_coefficient_resolver" not in _singletons:
        raise RuntimeError(
            "Dependencies not initialized. Call init_dependencies(settings) first.",
        )
    return _singletons["production_coefficient_resolver"]  # type: ignore[no-any-return]


def get_startup_readiness_outcome() -> Any:
    """Return the startup readiness outcome from the last initialization."""
    if "startup_readiness_outcome" not in _singletons:
        raise RuntimeError(
            "Dependencies not initialized. Call init_dependencies(settings) first.",
        )
    return _singletons["startup_readiness_outcome"]


def agent_capability_projection() -> tuple[dict[str, object], ...]:
    """Return the canonical bounded capability projection for this app mode."""
    from cold_storage.bootstrap.mode import AppMode

    mode = _singletons.get("app_mode")
    available = mode in (AppMode.LOCAL, AppMode.TEST)
    return (
        {
            "name": _MODEL_BACKED_AGENT_CAPABILITY,
            "status": "available" if available else "disabled",
            "code": None if available else "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
            "blocking": False,
        },
    )


def _configure_slice4_application(*, app: Any, settings: Settings, mode: Any) -> None:
    """Register the finalized Slice 4 HTTP bindings before startup audit."""
    from cold_storage.bootstrap.metrics.registry import get_metrics  # noqa: PLC0415
    from cold_storage.bootstrap.mode import AppMode  # noqa: PLC0415

    metrics = get_metrics()
    metrics.register_capability(_MODEL_BACKED_AGENT_CAPABILITY)
    metrics.record_capability_status(
        _MODEL_BACKED_AGENT_CAPABILITY,
        is_available=mode in (AppMode.LOCAL, AppMode.TEST),
    )

    _install_readiness_capability_projection(app)

    if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
        app.state.strict_capability_bindings = tuple()
        app.openapi_schema = None
        return

    _remove_routes(
        app,
        lambda route: str(getattr(route, "path", "")).startswith("/api/v1/coefficients")
        or str(getattr(route, "path", "")).startswith("/api/v1/agent")
        or str(getattr(route, "path", "")) == "/api/v1/demo/overview",
    )

    from cold_storage.modules.coefficients.api.routes import (  # noqa: PLC0415
        register_coefficient_routes,
    )

    register_coefficient_routes(app, get_production_coefficient_service)
    _mount_disabled_agent_routes(app)
    _install_canonical_report_storage_override(app=app, settings=settings)

    # Immutable, per-app positive declarations. The audit also requires the
    # independently published database-service composition token; route
    # declaration alone is never sufficient.
    app.state.strict_capability_bindings = _STRICT_BINDINGS
    app.openapi_schema = None


def _remove_routes(app: Any, predicate: Callable[[Any], bool]) -> None:
    routes = list(getattr(app.router, "routes", ()))
    app.router.routes[:] = [route for route in routes if not predicate(route)]


def _mount_disabled_agent_routes(app: Any) -> None:
    from fastapi.responses import JSONResponse

    def endpoint_factory(name: str) -> Callable[[], JSONResponse]:
        def disabled_endpoint() -> JSONResponse:
            return JSONResponse(status_code=503, content=_AGENT_DISABLED_ERROR)

        disabled_endpoint.__name__ = name
        return disabled_endpoint

    response_docs = {
        503: {
            "description": "Model-backed planning agent is outside V0.2 production scope.",
            "content": {"application/json": {"example": _AGENT_DISABLED_ERROR}},
        }
    }
    for index, (method, path) in enumerate(_AGENT_ROUTES, start=1):
        app.add_api_route(
            path,
            endpoint_factory(f"disabled_model_backed_agent_{index}"),
            methods=[method],
            status_code=503,
            responses=response_docs,
            tags=["agent"],
            operation_id=f"disabled_model_backed_agent_{index}",
        )


def _install_readiness_capability_projection(app: Any) -> None:
    """Replace the ready route with a schema-compatible capability wrapper."""
    import json

    from fastapi.responses import JSONResponse, Response

    original = getattr(app.state, "slice4_original_ready_endpoint", None)
    if original is None:
        for route in list(getattr(app.router, "routes", ())):
            if getattr(route, "path", None) == "/health/ready" and "GET" in getattr(
                route, "methods", set()
            ):
                original = getattr(route, "endpoint", None)
                break
        if original is None:
            raise RuntimeError("canonical readiness route is missing")
        app.state.slice4_original_ready_endpoint = original

    _remove_routes(app, lambda route: getattr(route, "path", None) == "/health/ready")

    def ready_with_capabilities() -> Any:
        result = original()
        capabilities = [dict(item) for item in agent_capability_projection()]
        if isinstance(result, Response):
            try:
                body = json.loads(bytes(result.body).decode("utf-8"))
            except (TypeError, ValueError, UnicodeDecodeError):
                body = {"status": "not_ready", "state": "ERROR"}
            if not isinstance(body, dict):
                body = {"status": "not_ready", "state": "ERROR"}
            body["capabilities"] = capabilities
            return JSONResponse(status_code=result.status_code, content=body)
        if not isinstance(result, dict):
            result = {"status": "not_ready", "state": "ERROR"}
        body = dict(result)
        body["capabilities"] = capabilities
        return body

    app.add_api_route(
        "/health/ready",
        ready_with_capabilities,
        methods=["GET"],
        name="ready",
        tags=["health"],
    )
    app.openapi_schema = None


def _install_canonical_report_storage_override(*, app: Any, settings: Settings) -> None:
    """Bind active report rendering to the canonical Settings.storage_dir."""
    from fastapi import Depends

    def slice4_report_db_session() -> Generator[SASession, None, None]:
        session = SASession(bind=get_engine(), expire_on_commit=False)
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def slice4_report_render_service(
        db_session: SASession = Depends(slice4_report_db_session),  # noqa: B008
    ) -> Any:
        from cold_storage.modules.reports.application.render_service import (  # noqa: PLC0415
            ReportRenderService,
            ReportRenderUnitOfWork,
        )
        from cold_storage.modules.reports.infrastructure.artifact_storage import (  # noqa: PLC0415
            ReportArtifactStorage,
        )
        from cold_storage.modules.reports.infrastructure.repository import (  # noqa: PLC0415
            SQLReportRepository,
        )

        if not settings.storage_dir:
            raise RuntimeError("canonical artifact storage is not initialized")
        repo = SQLReportRepository(db_session)
        storage = ReportArtifactStorage(base_dir=settings.storage_dir)
        uow = ReportRenderUnitOfWork(
            db_session,
            report_repo=repo,
            artifact_repo=repo,
            session_factory=lambda: SASession(
                bind=db_session.bind,
                expire_on_commit=False,
            ),
        )
        return ReportRenderService(uow=uow, storage=storage, template_repo=repo)

    replaced = False
    for dependency in tuple(app.dependency_overrides):
        if (
            getattr(dependency, "__name__", "") == "_get_render_service"
            and str(getattr(dependency, "__module__", "")).endswith(
                "modules.reports.api.routes"
            )
        ):
            app.dependency_overrides[dependency] = slice4_report_render_service
            replaced = True
    if not replaced:
        raise RuntimeError("report render dependency override authority is missing")


def _install_slice4_runtime_audit() -> None:
    """Install the binding-identity audit into runtime_readiness authority."""
    from cold_storage.bootstrap import runtime_readiness

    runtime_readiness.enumerate_reachable_unsafe_strict_capabilities = (
        _slice4_enumerate_reachable_unsafe_strict_capabilities
    )
    runtime_readiness.assert_no_unsafe_strict_capabilities = (
        _slice4_assert_no_unsafe_strict_capabilities
    )


def _slice4_enumerate_reachable_unsafe_strict_capabilities(
    *, app: Any, routes: Iterable[Any] | None = None
) -> tuple[str, ...]:
    """Cross-check strict routes, immutable binding identity, and composition evidence."""
    from cold_storage.bootstrap.mode import AppMode, resolve_app_mode
    from cold_storage.bootstrap.runtime_readiness import (
        ConfigurationProbeFailed,
        UnsafeStrictCapabilityWiring,
        canonical_settings,
        composition_manifest_tokens,
    )

    _ = routes
    try:
        mode = resolve_app_mode(canonical_settings())
    except ConfigurationProbeFailed:
        mode = None
    if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
        return ()
    if app is None:
        raise UnsafeStrictCapabilityWiring(
            "strict capability audit invoked without a FastAPI app",
            unsafe_capabilities=(),
        )

    unsafe: set[str] = set()
    manifest = getattr(getattr(app, "state", None), "strict_capability_bindings", None)
    if manifest != _STRICT_BINDINGS or not isinstance(manifest, tuple):
        unsafe.update({"coefficient_http", _MODEL_BACKED_AGENT_CAPABILITY})

    tokens = composition_manifest_tokens()
    if _COMPOSITION_TOKEN_PROVIDER_ERROR in tokens:
        unsafe.update({"coefficient_http", _MODEL_BACKED_AGENT_CAPABILITY})
    if _COMPOSITION_TOKEN_DATABASE_COEFFICIENT not in tokens:
        unsafe.add("coefficient_http")
    if _COMPOSITION_TOKEN_PROCESS_LOCAL_COEFFICIENT in tokens:
        unsafe.add("coefficient_http")
    if _COMPOSITION_TOKEN_FAKE_AGENT_GATEWAY in tokens:
        unsafe.add(_MODEL_BACKED_AGENT_CAPABILITY)

    route_paths = {str(getattr(route, "path", "")) for route in getattr(app, "routes", ())}
    if "/api/v1/coefficients" not in route_paths:
        unsafe.add("coefficient_http")
    if "/api/v1/agent/sessions" not in route_paths:
        unsafe.add(_MODEL_BACKED_AGENT_CAPABILITY)
    if "/api/v1/demo/overview" in route_paths:
        unsafe.add(_MODEL_BACKED_AGENT_CAPABILITY)

    return tuple(sorted(unsafe))


def _slice4_assert_no_unsafe_strict_capabilities(*, app: Any = None) -> None:
    from cold_storage.bootstrap.runtime_readiness import UnsafeStrictCapabilityWiring

    unsafe = _slice4_enumerate_reachable_unsafe_strict_capabilities(app=app)
    if unsafe:
        raise UnsafeStrictCapabilityWiring(
            f"unsafe strict capabilities reachable: {list(unsafe)!r}",
            unsafe_capabilities=unsafe,
        )


def shutdown_dependencies() -> None:
    """Drain readiness, dispose the canonical engine once, and clear authorities."""
    from contextlib import suppress

    from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
        get_readiness_state,
        reset_canonical_settings,
        reset_composition_manifest_provider,
        reset_readiness_state,
    )

    state = get_readiness_state()
    with suppress(Exception):
        if state is not None:
            state.transition(to="DRAINING")
    engine = _singletons.get("engine")
    if engine is not None:
        with suppress(Exception):
            dispose_engine(engine)
    _singletons.clear()
    _clear_composition_tokens()
    reset_readiness_state()
    with suppress(Exception):
        reset_composition_manifest_provider()
    with suppress(Exception):
        reset_canonical_settings()


# Backward compatibility
from cold_storage.modules.projects.infrastructure.database import (  # noqa: E402, F401
    create_database_project_service,
)
