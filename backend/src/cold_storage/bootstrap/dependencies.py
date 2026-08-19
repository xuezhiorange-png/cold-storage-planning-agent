"""Runtime dependency management — no import-time singletons."""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
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
_COMPOSITION_TOKEN_REAL_AGENT_GATEWAY = "MIMO_AGENT_MODEL_GATEWAY_INSTANTIATED"
_COMPOSITION_TOKEN_REAL_AGENT_SERVICE = "REAL_PLANNING_AGENT_SERVICE_COMPOSED"
_COMPOSITION_TOKEN_PROCESS_LOCAL_COEFFICIENT = "PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED"
_COMPOSITION_TOKEN_DATABASE_COEFFICIENT = "DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"
_COMPOSITION_TOKEN_PROVIDER_ERROR = "COMPOSITION_MANIFEST_PROVIDER_ERROR"

_MODEL_BACKED_AGENT_CAPABILITY = "model_backed_agent"
_STRICT_BINDINGS: tuple[tuple[str, str], ...] = (
    ("coefficient_http", "database_backed"),
    (_MODEL_BACKED_AGENT_CAPABILITY, "disabled"),
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


def canonical_agent_provider_probe(
    *,
    client_factory: Callable[..., Any] | None = None,
) -> Callable[[Settings], Any]:
    """Build the production provider/schema probe through the MiMo gateway.

    The returned callable is intentionally injected into the readiness
    resolver.  It constructs the existing MiMo Responses gateway and sends
    one structured, no-tool probe request, so provider reachability and the
    frozen ``AgentDecision`` schema are verified together.  Tests can inject
    a deterministic client factory; the composition root never creates a
    second transport or reads a provider-native response directly.
    """

    def _probe(settings: Settings) -> Any:
        from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
            AgentProviderProbeEvidence,
        )
        from cold_storage.modules.planning_agent.domain.errors import (  # noqa: PLC0415
            AgentProviderFailureCode,
            ModelGatewayError,
        )
        from cold_storage.modules.planning_agent.domain.gateways import (  # noqa: PLC0415
            AgentModelRequest,
        )
        from cold_storage.modules.planning_agent.domain.models import AgentDecision  # noqa: PLC0415
        from cold_storage.modules.planning_agent.infrastructure.real_gateways import (  # noqa: PLC0415
            MiMoAgentModelGateway,
        )

        try:
            gateway = MiMoAgentModelGateway(
                api_key=settings.mimo_api_key,
                model_name=settings.agent_model,
                timeout_seconds=settings.agent_timeout_seconds,
                max_retries=settings.agent_max_retries,
                provider=settings.agent_provider,
                client_factory=client_factory,
            )
            decision = gateway.generate_decision(
                AgentModelRequest(
                    system_prompt="Return a structured readiness decision.",
                    messages=[
                        {
                            "role": "user",
                            "content": "Readiness probe: return a no-op structured decision.",
                        }
                    ],
                    max_tokens=256,
                )
            )
            if not isinstance(decision, AgentDecision):
                return AgentProviderProbeEvidence(
                    passed=False,
                    failure_code=AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED,
                    provider=settings.agent_provider,
                    model=settings.agent_model,
                )
            return AgentProviderProbeEvidence(
                passed=True,
                provider=settings.agent_provider,
                model=settings.agent_model,
                schema_verified=True,
                schema_identity="AgentDecision",
            )
        except ModelGatewayError as error:
            return AgentProviderProbeEvidence(
                passed=False,
                failure_code=(
                    error.provider_failure_code
                    or AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE
                ),
                provider=settings.agent_provider,
                model=settings.agent_model,
            )
        except Exception:  # noqa: BLE001
            return AgentProviderProbeEvidence(
                passed=False,
                failure_code=AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE,
                provider=settings.agent_provider,
                model=settings.agent_model,
            )

    return _probe


def init_dependencies(
    settings: Settings,
    *,
    app: Any = None,
    strict_runtime_authority: Any | None = None,
    agent_client_factory: Callable[..., Any] | None = None,
) -> None:
    """Create and publish the canonical runtime dependency graph.

    TASK-012 Slice 4 extends the transactional Slice 2 lifecycle with a
    database-backed coefficient HTTP authority, strict disabled-agent routes,
    binding-identity audit evidence, canonical report artifact storage, and a
    shared readiness/metrics capability projection.

    R7: Accepts strict_runtime_authority explicitly and passes it through
    to run_startup_phase → assert_no_unsafe_strict_capabilities.
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
    _singletons.pop("agent_gateway", None)
    _singletons["agent_evidence"] = getattr(strict_runtime_authority, "agent_evidence", None)
    try:
        project_service = DatabaseProjectService(engine)
    except Exception:
        shutdown_dependencies()
        raise
    _singletons["project_service"] = project_service

    if mode in (AppMode.STAGING, AppMode.PRODUCTION):
        capability_state = getattr(
            strict_runtime_authority,
            "agent_capability_state",
            "AGENT_CAPABILITY_DISABLED",
        )
        agent_candidate = bool(getattr(strict_runtime_authority, "agent_candidate", False))
        if capability_state == "AGENT_CAPABILITY_ENABLED_READY" or agent_candidate:
            evidence = getattr(strict_runtime_authority, "agent_evidence", None)
            if evidence is None or any(
                (
                    getattr(evidence, "provider", None) != settings.agent_provider,
                    getattr(evidence, "model", None) != settings.agent_model,
                    getattr(evidence, "timeout_seconds", None) != settings.agent_timeout_seconds,
                    getattr(evidence, "max_retries", None) != settings.agent_max_retries,
                )
            ):
                shutdown_dependencies()
                raise RuntimeError("agent capability evidence does not match canonical settings")
            try:
                from cold_storage.modules.planning_agent.infrastructure.real_gateways import (  # noqa: PLC0415
                    MiMoAgentModelGateway,
                )

                gateway = MiMoAgentModelGateway(
                    api_key=settings.mimo_api_key,
                    model_name=settings.agent_model,
                    timeout_seconds=settings.agent_timeout_seconds,
                    max_retries=settings.agent_max_retries,
                    provider=settings.agent_provider,
                    client_factory=agent_client_factory,
                )
            except Exception:
                shutdown_dependencies()
                raise
            _singletons["agent_gateway"] = gateway
            _record_composition_token(_COMPOSITION_TOKEN_REAL_AGENT_GATEWAY)
            service_factory = getattr(strict_runtime_authority, "agent_service_factory", None)
            if not callable(service_factory):
                shutdown_dependencies()
                raise RuntimeError("strict agent composition factory is unavailable")
            composition_session = SASession(bind=engine, expire_on_commit=False)
            try:
                agent_service = service_factory(composition_session)
            except Exception:
                composition_session.close()
                shutdown_dependencies()
                raise
            finally:
                composition_session.close()
            _singletons["agent_service"] = agent_service
            _singletons["agent_service_composition"] = agent_service
            _record_composition_token(_COMPOSITION_TOKEN_REAL_AGENT_SERVICE)
        else:
            agent_service = _StrictModeAgentService(capability_state=capability_state)
            _singletons["agent_service"] = agent_service
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
        run_startup_phase(
            settings=settings,
            environment={k: v for k, v in __import__("os").environ.items()},
            startup_probes=mandatory_startup_probes(),
            app=app,
            strict_runtime_authority=strict_runtime_authority,
        )
    except Exception:
        shutdown_dependencies()
        raise

    _ = canonical_settings


def _StrictModeAgentService(
    *,
    capability_state: str = "AGENT_CAPABILITY_DISABLED",
    gateway: Any | None = None,
) -> Any:
    """Return a strict dependency marker without constructing a fake gateway."""

    class _Placeholder:
        def __init__(self) -> None:
            self.capability_state = capability_state
            self.gateway = gateway

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


def get_agent_gateway() -> Any:
    """Return the real strict gateway only after ready composition."""
    if "agent_gateway" not in _singletons:
        raise RuntimeError("Agent gateway is not available in the current capability state.")
    return _singletons["agent_gateway"]


def publish_agent_capability_evidence(evidence: Any) -> None:
    """Publish final app-bound evidence after strict startup audit passes."""
    _singletons["agent_evidence"] = evidence


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


def _capability_projection_entry(
    *,
    app_mode: Any,
    evidence: Any | None = None,
) -> MappingProxyType[str, object]:
    from cold_storage.bootstrap.mode import AppMode

    if app_mode in (AppMode.LOCAL, AppMode.TEST):
        return MappingProxyType(
            {
                "name": _MODEL_BACKED_AGENT_CAPABILITY,
                "status": "available",
                "code": None,
                "blocking": False,
                "capability_state": "LOCAL_TEST_AVAILABLE",
                "route_exposure": "LOCAL_TEST_ROUTES",
            }
        )

    state = getattr(evidence, "state", None)
    state_value = getattr(state, "value", state) or "AGENT_CAPABILITY_DISABLED"
    if state_value == "AGENT_CAPABILITY_ENABLED_READY":
        return MappingProxyType(
            {
                "name": _MODEL_BACKED_AGENT_CAPABILITY,
                "status": "available",
                "code": None,
                "blocking": False,
                "capability_state": state_value,
                "route_exposure": "REAL_AGENT_ROUTES_ENABLED",
            }
        )
    if state_value == "AGENT_CAPABILITY_ENABLED_NOT_READY":
        return MappingProxyType(
            {
                "name": _MODEL_BACKED_AGENT_CAPABILITY,
                "status": "not_ready",
                "code": getattr(evidence, "failure_code", None) or "AGENT_PROVIDER_UNAVAILABLE",
                "blocking": True,
                "capability_state": state_value,
                "route_exposure": "DISABLED_ROUTE_MATRIX",
            }
        )
    return MappingProxyType(
        {
            "name": _MODEL_BACKED_AGENT_CAPABILITY,
            "status": "disabled",
            "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
            "blocking": False,
            "capability_state": "AGENT_CAPABILITY_DISABLED",
            "route_exposure": "DISABLED_ROUTE_MATRIX",
        }
    )


def agent_capability_projection() -> tuple[MappingProxyType[str, object], ...]:
    """Return the canonical bounded capability projection for this app mode.

    D-S4-04: Each entry is a :class:`types.MappingProxyType` to prevent
    callers from mutating the shared singleton projection.  The tuple
    itself is already immutable.
    """
    mode = _singletons.get("app_mode")
    return (
        _capability_projection_entry(
            app_mode=mode,
            evidence=_singletons.get("agent_evidence"),
        ),
    )


def create_capability_projection(
    app_mode: Any,
    *,
    evidence: Any | None = None,
) -> tuple[MappingProxyType[str, object], ...]:
    """Create an immutable capability projection bound to the given app mode.

    D-S4-04: The projection is created once during app factory and bound
    to the FastAPI app instance, ensuring readiness, metrics, and strict
    audit all use the same canonical capability name and resolved app mode.

    Each entry is a :class:`types.MappingProxyType` so callers cannot
    mutate the app-bound projection after creation.
    """
    return (_capability_projection_entry(app_mode=app_mode, evidence=evidence),)


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
