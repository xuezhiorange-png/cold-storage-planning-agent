"""API endpoint tests for planning agent routes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.runtime_readiness import (
    LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS,
    LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS,
    AgentProviderProbeEvidence,
)
from cold_storage.bootstrap.settings import Settings
from cold_storage.modules.planning_agent.api.routes import create_agent_router
from cold_storage.modules.planning_agent.application.orchestrator import AgentOrchestrator
from cold_storage.modules.planning_agent.application.service import PlanningAgentService
from cold_storage.modules.planning_agent.application.tool_registry import build_default_registry
from cold_storage.modules.planning_agent.domain.errors import (
    AgentProviderFailureCode,
    ModelGatewayError,
    provider_failure_metadata,
)
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import FakeAgentModelGateway
from cold_storage.modules.planning_agent.infrastructure.orm import Base
from cold_storage.modules.planning_agent.infrastructure.real_gateways import (
    OPENAI_OFFICIAL_BASE_URL,
)
from cold_storage.modules.planning_agent.infrastructure.repository import AgentRepository


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionFactory() as session:
        yield session


@pytest.fixture()
def app(db_session):
    repo = AgentRepository(db_session)
    gateway = FakeAgentModelGateway()
    registry = build_default_registry()
    orchestrator = AgentOrchestrator()
    service = PlanningAgentService(
        repository=repo,
        gateway=gateway,
        registry=registry,
        orchestrator=orchestrator,
    )
    fastapi_app = FastAPI()
    fastapi_app.include_router(create_agent_router(lambda: service))
    return fastapi_app


@pytest.fixture()
def client(app):
    with TestClient(app, headers={"X-Actor": "test-user"}) as c:
        yield c


class TestCreateSession:
    def test_create_session_201(self, client):
        resp = client.post("/api/v1/agent/sessions", json={"title": "Test"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "active"
        assert data["title"] == "Test"

    def test_create_session_with_project(self, client):
        resp = client.post(
            "/api/v1/agent/sessions",
            json={
                "title": "With project",
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["project_id"] == "proj-1"


class TestListSessions:
    def test_list_empty(self, client):
        resp = client.get("/api/v1/agent/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_sessions(self, client):
        client.post("/api/v1/agent/sessions", json={"title": "A"})
        client.post("/api/v1/agent/sessions", json={"title": "B"})
        resp = client.get("/api/v1/agent/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestGetSession:
    def test_get_existing(self, client):
        create = client.post("/api/v1/agent/sessions", json={"title": "X"})
        sid = create.json()["id"]
        resp = client.get(f"/api/v1/agent/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == sid

    def test_get_nonexistent(self, client):
        resp = client.get("/api/v1/agent/sessions/nonexistent")
        assert resp.status_code == 404


class TestPostMessage:
    def test_post_message_201(self, client):
        create = client.post("/api/v1/agent/sessions", json={"title": "Msg test"})
        sid = create.json()["id"]
        resp = client.post(f"/api/v1/agent/sessions/{sid}/messages", json={"content": "25吨蓝莓"})
        assert resp.status_code == 201
        data = resp.json()
        assert "assistant_message" in data
        assert "turn_id" in data
        assert data["prompt_version"] == "planning-agent-system-v1"

    def test_post_message_missing_params(self, client):
        create = client.post("/api/v1/agent/sessions", json={"title": "Missing"})
        sid = create.json()["id"]
        resp = client.post(
            f"/api/v1/agent/sessions/{sid}/messages", json={"content": "我想做蓝莓加工厂规划"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["decision_type"] == "ask_clarification"
        assert len(data["missing_parameters"]) >= 1

    def test_post_message_to_nonexistent_session(self, client):
        resp = client.post("/api/v1/agent/sessions/bad-id/messages", json={"content": "hi"})
        assert resp.status_code == 404

    def test_post_message_to_cancelled_session(self, client):
        create = client.post("/api/v1/agent/sessions", json={"title": "C"})
        sid = create.json()["id"]
        client.post(f"/api/v1/agent/sessions/{sid}/cancel")
        resp = client.post(f"/api/v1/agent/sessions/{sid}/messages", json={"content": "hi"})
        assert resp.status_code == 400


class TestGetMessages:
    def test_get_messages(self, client):
        create = client.post("/api/v1/agent/sessions", json={"title": "M"})
        sid = create.json()["id"]
        client.post(f"/api/v1/agent/sessions/{sid}/messages", json={"content": "hello"})
        resp = client.get(f"/api/v1/agent/sessions/{sid}/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) >= 2  # user + assistant

    def test_get_messages_nonexistent(self, client):
        resp = client.get("/api/v1/agent/sessions/bad/messages")
        assert resp.status_code == 404


class TestGetTurn:
    def test_get_turn(self, client):
        create = client.post("/api/v1/agent/sessions", json={"title": "T"})
        sid = create.json()["id"]
        msg_resp = client.post(f"/api/v1/agent/sessions/{sid}/messages", json={"content": "hi"})
        turn_id = msg_resp.json()["turn_id"]
        resp = client.get(f"/api/v1/agent/sessions/{sid}/turns/{turn_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("completed", "awaiting_confirmation")

    def test_get_turn_nonexistent(self, client):
        create = client.post("/api/v1/agent/sessions", json={"title": "T2"})
        sid = create.json()["id"]
        resp = client.get(f"/api/v1/agent/sessions/{sid}/turns/bad-turn")
        assert resp.status_code == 404


class TestListToolCalls:
    def test_list_tool_calls(self, client):
        create = client.post("/api/v1/agent/sessions", json={"title": "TC"})
        sid = create.json()["id"]
        client.post(f"/api/v1/agent/sessions/{sid}/messages", json={"content": "25吨蓝莓"})
        resp = client.get(f"/api/v1/agent/sessions/{sid}/tool-calls")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_tool_calls_nonexistent(self, client):
        resp = client.get("/api/v1/agent/sessions/bad/tool-calls")
        assert resp.status_code == 404


class TestCancelSession:
    def test_cancel(self, client):
        create = client.post("/api/v1/agent/sessions", json={"title": "To Cancel"})
        sid = create.json()["id"]
        resp = client.post(f"/api/v1/agent/sessions/{sid}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_nonexistent(self, client):
        resp = client.post("/api/v1/agent/sessions/bad/cancel")
        assert resp.status_code == 404


class TestConfirmRejectToolCall:
    def test_confirm_nonexistent(self, client):
        resp = client.post("/api/v1/agent/tool-calls/bad/confirm", json={"confirmation_token": "x"})
        assert resp.status_code == 404

    def test_reject_nonexistent(self, client):
        resp = client.post("/api/v1/agent/tool-calls/bad/reject", json={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# D-S4-02: Strict-mode disabled agent HTTP behavior tests.
# These verify that staging/production disabled endpoints return proper 503.
# ---------------------------------------------------------------------------

# Frozen error envelope for disabled agent endpoints
_DISABLED_ERROR = {
    "error": {
        "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
        "message": "Model-backed agent not in V0.2 production scope.",
        "details": {"retryable": False},
    }
}

_FROZEN_AGENT_ROUTES = (
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


@pytest.fixture()
def strict_app(tmp_path, monkeypatch):
    """Create a strict-mode app with disabled agent routes."""
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.runtime_readiness import (
        ReadinessState,
        reset_readiness_state,
        set_readiness_state,
    )

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_URL",
        "postgresql+psycopg2://x:y@localhost:5432/test",
    )
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", "0" * 40)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", "v0.0.0-ci")
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(artifact_dir))
    monkeypatch.setenv(
        "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS),
    )
    monkeypatch.setenv(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS),
    )

    # Stub init_dependencies to avoid PostgreSQL connection
    def _noop_init(settings, app=None, strict_runtime_authority=None):  # noqa: ARG001
        return None

    monkeypatch.setattr(bootstrap_app, "init_dependencies", _noop_init)
    monkeypatch.setattr(deps, "init_dependencies", _noop_init)

    from cold_storage.bootstrap.app import create_app

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    return app


@pytest.fixture()
def strict_client(strict_app):
    with TestClient(strict_app, headers={"X-Actor": "test-user"}) as c:
        yield c


class TestStrictAgentDisabledEndpoints:
    """DECLARED_METHOD_RETURNS_503: all frozen agent endpoints return 503."""

    def test_post_sessions_returns_503(self, strict_client):
        resp = strict_client.post("/api/v1/agent/sessions", json={"title": "Test"})
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR

    def test_get_sessions_returns_503(self, strict_client):
        resp = strict_client.get("/api/v1/agent/sessions")
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR

    def test_get_session_by_id_returns_503(self, strict_client):
        resp = strict_client.get("/api/v1/agent/sessions/some-id")
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR

    def test_get_messages_returns_503(self, strict_client):
        resp = strict_client.get("/api/v1/agent/sessions/some-id/messages")
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR

    def test_post_messages_returns_503(self, strict_client):
        resp = strict_client.post(
            "/api/v1/agent/sessions/some-id/messages",
            json={"content": "hello"},
        )
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR

    def test_get_turns_returns_503(self, strict_client):
        resp = strict_client.get("/api/v1/agent/sessions/some-id/turns/turn-1")
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR

    def test_get_tool_calls_returns_503(self, strict_client):
        resp = strict_client.get("/api/v1/agent/sessions/some-id/tool-calls")
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR

    def test_confirm_tool_call_returns_503(self, strict_client):
        resp = strict_client.post(
            "/api/v1/agent/tool-calls/tc-1/confirm",
            json={"confirmation_token": "x"},
        )
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR

    def test_reject_tool_call_returns_503(self, strict_client):
        resp = strict_client.post("/api/v1/agent/tool-calls/tc-1/reject", json={})
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR

    def test_cancel_session_returns_503(self, strict_client):
        resp = strict_client.post("/api/v1/agent/sessions/some-id/cancel")
        assert resp.status_code == 503
        assert resp.json() == _DISABLED_ERROR


class TestStrictAgentErrorEnvelope:
    """EXACT_ERROR_ENVELOPE: disabled endpoints return the exact error shape."""

    def test_error_envelope_structure(self, strict_client):
        resp = strict_client.post("/api/v1/agent/sessions", json={"title": "X"})
        body = resp.json()
        assert "error" in body
        error = body["error"]
        assert error["code"] == "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE"
        assert "not in V0.2 production scope" in error["message"]
        assert error["details"]["retryable"] is False

    def test_no_auth_returns_503(self, strict_client):
        """NO_AUTH_RETURNS_503: disabled endpoint returns 503 without auth."""
        resp = strict_client.post(
            "/api/v1/agent/sessions",
            json={"title": "NoAuth"},
            headers={},
        )
        assert resp.status_code == 503

    def test_invalid_auth_returns_503(self, strict_client):
        """INVALID_AUTH_RETURNS_503: disabled endpoint returns 503 with bad auth."""
        resp = strict_client.post(
            "/api/v1/agent/sessions",
            json={"title": "BadAuth"},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 503

    def test_missing_body_returns_503(self, strict_client):
        """MISSING_BODY_RETURNS_503: disabled endpoint returns 503 without body."""
        resp = strict_client.post("/api/v1/agent/sessions")
        assert resp.status_code == 503

    def test_invalid_body_returns_503(self, strict_client):
        """INVALID_BODY_RETURNS_503: disabled endpoint returns 503 with bad body."""
        resp = strict_client.post(
            "/api/v1/agent/sessions",
            json={"invalid_field": True},
        )
        assert resp.status_code == 503

    def test_unknown_resource_id_returns_503(self, strict_client):
        """UNKNOWN_RESOURCE_ID_RETURNS_503: disabled endpoint returns 503."""
        resp = strict_client.get("/api/v1/agent/sessions/nonexistent-uuid")
        assert resp.status_code == 503


class TestStrictAgentMethodNotAllowed:
    """UNDECLARED_METHOD_RETURNS_405: wrong HTTP method returns 405."""

    def test_put_sessions_returns_405(self, strict_client):
        resp = strict_client.put("/api/v1/agent/sessions", json={})
        assert resp.status_code == 405

    def test_delete_sessions_returns_405(self, strict_client):
        resp = strict_client.delete("/api/v1/agent/sessions")
        assert resp.status_code == 405


class TestStrictAgentPathNotFound:
    """UNKNOWN_PATH_RETURNS_404 + TRAILING_SLASH_RETURNS_307."""

    def test_unknown_path_returns_404(self, strict_client):
        resp = strict_client.get("/api/v1/agent/unknown-path")
        assert resp.status_code == 404

    def test_trailing_slash_returns_307(self, strict_client):
        resp = strict_client.get("/api/v1/agent/sessions/", follow_redirects=False)
        assert resp.status_code == 307


class TestStrictAgentSpyProvesNoConstruction:
    """Spy证明：disabled endpoint不构造fake gateway / active service / db session."""

    def test_fake_gateway_constructor_not_called(self, strict_client):
        """FAKE_GATEWAY_CONSTRUCTOR_CALL_COUNT=0."""
        call_count = 0
        original_init = FakeAgentModelGateway.__init__

        def _counting_init(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            original_init(self, *args, **kwargs)

        FakeAgentModelGateway.__init__ = _counting_init  # type: ignore[method-assign]
        try:
            strict_client.post("/api/v1/agent/sessions", json={"title": "Spy"})
        finally:
            FakeAgentModelGateway.__init__ = original_init  # type: ignore[method-assign]
        assert call_count == 0, f"FakeAgentModelGateway.__init__ called {call_count} times"


# ---------------------------------------------------------------------------
# D-S4-02-S5: Strict-mode zero-construction spy tests.
# Proves that disabled endpoints do NOT construct FakeAgentModelGateway,
# PlanningAgentService, invoke _get_planning_agent_service, _get_db_session,
# or ReportArtifactStorage.  Spies are installed BEFORE create_app() and
# TestClient startup so the entire request lifecycle is instrumented.
# ---------------------------------------------------------------------------

# Call counters shared across spy fixtures and test assertions.
_fake_gateway_init_count: int = 0
_planning_agent_service_init_count: int = 0
_get_planning_agent_service_count: int = 0
_get_db_session_count: int = 0
_report_artifact_storage_init_count: int = 0


@pytest.fixture()
def strict_app_with_spies(tmp_path, monkeypatch):
    """Create a strict-mode app with spies installed BEFORE create_app().

    Every spy is a monkeypatch-wrapped __init__ (or function) that increments
    a module-level counter.  The counters are verified in the test body.
    """
    global _fake_gateway_init_count  # noqa: PLW0603
    global _planning_agent_service_init_count  # noqa: PLW0603
    global _get_planning_agent_service_count  # noqa: PLW0603
    global _get_db_session_count  # noqa: PLW0603
    global _report_artifact_storage_init_count  # noqa: PLW0603

    _fake_gateway_init_count = 0
    _planning_agent_service_init_count = 0
    _get_planning_agent_service_count = 0
    _get_db_session_count = 0
    _report_artifact_storage_init_count = 0

    # --- environment setup (identical to strict_app) ---
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap.runtime_readiness import (
        ReadinessState,
        reset_readiness_state,
        set_readiness_state,
    )

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_URL",
        "postgresql+psycopg2://x:y@localhost:5432/test",
    )
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", "0" * 40)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", "v0.0.0-ci")
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(artifact_dir))
    monkeypatch.setenv(
        "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS),
    )
    monkeypatch.setenv(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS),
    )

    # Stub init_dependencies to avoid PostgreSQL connection
    def _noop_init(settings, app=None, strict_runtime_authority=None):  # noqa: ARG001
        return None

    monkeypatch.setattr(bootstrap_app, "init_dependencies", _noop_init)
    monkeypatch.setattr(deps, "init_dependencies", _noop_init)

    # --- SPY INSTALLATION: before create_app() ---

    # Spy 1: FakeAgentModelGateway.__init__
    _orig_fg_init = FakeAgentModelGateway.__init__

    def _spy_fg_init(self, *args, **kwargs):
        global _fake_gateway_init_count  # noqa: PLW0603
        _fake_gateway_init_count += 1
        _orig_fg_init(self, *args, **kwargs)

    monkeypatch.setattr(FakeAgentModelGateway, "__init__", _spy_fg_init)

    # Spy 2: PlanningAgentService.__init__
    _orig_pas_init = PlanningAgentService.__init__

    def _spy_pas_init(self, *args, **kwargs):
        global _planning_agent_service_init_count  # noqa: PLW0603
        _planning_agent_service_init_count += 1
        _orig_pas_init(self, *args, **kwargs)

    monkeypatch.setattr(PlanningAgentService, "__init__", _spy_pas_init)

    # Spy 3 & 4: _get_planning_agent_service and _get_db_session (app module)
    from cold_storage.bootstrap import app as _app_module

    _orig_get_planning = _app_module._get_planning_agent_service

    def _spy_get_planning(*args, **kwargs):
        global _get_planning_agent_service_count  # noqa: PLW0603
        _get_planning_agent_service_count += 1
        return _orig_get_planning(*args, **kwargs)

    monkeypatch.setattr(_app_module, "_get_planning_agent_service", _spy_get_planning)

    _orig_get_db = _app_module._get_db_session

    def _spy_get_db(*args, **kwargs):
        global _get_db_session_count  # noqa: PLW0603
        _get_db_session_count += 1
        return _orig_get_db(*args, **kwargs)

    monkeypatch.setattr(_app_module, "_get_db_session", _spy_get_db)

    # Spy 5: ReportArtifactStorage.__init__
    from cold_storage.modules.reports.infrastructure.artifact_storage import (
        ReportArtifactStorage as _RAS,
    )

    _orig_ras_init = _RAS.__init__

    def _spy_ras_init(self, *args, **kwargs):
        global _report_artifact_storage_init_count  # noqa: PLW0603
        _report_artifact_storage_init_count += 1
        _orig_ras_init(self, *args, **kwargs)

    monkeypatch.setattr(_RAS, "__init__", _spy_ras_init)

    # --- create_app() AFTER spies installed ---
    from cold_storage.bootstrap.app import create_app

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    return app


@pytest.fixture()
def strict_client_with_spies(strict_app_with_spies):
    with TestClient(strict_app_with_spies, headers={"X-Actor": "test-user"}) as c:
        yield c


class TestStrictAgentZeroConstructionProvedBySpies:
    """Spy证明：spies installed BEFORE create_app() prove zero construction.

    All five spy targets must have call count == 0 after every disabled
    endpoint request.  The spies are installed via monkeypatch before
    create_app() and TestClient startup, so the entire request lifecycle
    is instrumented.
    """

    def test_zero_construction_on_post_sessions(self, strict_client_with_spies):
        """POST /api/v1/agent/sessions → 503, zero construction."""
        resp = strict_client_with_spies.post("/api/v1/agent/sessions", json={"title": "Spy-Zero"})
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE"
        assert _fake_gateway_init_count == 0, (
            f"FakeAgentModelGateway.__init__ called {_fake_gateway_init_count} times"
        )
        assert _planning_agent_service_init_count == 0, (
            f"PlanningAgentService.__init__ called {_planning_agent_service_init_count} times"
        )
        assert _get_planning_agent_service_count == 0, (
            f"_get_planning_agent_service called {_get_planning_agent_service_count} times"
        )
        assert _get_db_session_count == 0, f"_get_db_session called {_get_db_session_count} times"
        assert _report_artifact_storage_init_count == 0, (
            f"ReportArtifactStorage.__init__ called {_report_artifact_storage_init_count} times"
        )


@pytest.mark.parametrize("failure_code", tuple(AgentProviderFailureCode))
def test_provider_failure_projection_uses_only_frozen_safe_metadata(
    monkeypatch,
    failure_code: AgentProviderFailureCode,
):
    """All provider failures use the same redacted, machine-readable envelope."""

    class _FailingService:
        def post_user_message(self, *_args, **_kwargs):
            raise ModelGatewayError("raw provider body and api-key-secret", code=failure_code)

    monkeypatch.setenv("PLANNING_AGENT_ALLOW_INSECURE_ACTOR", "true")
    fastapi_app = FastAPI()
    fastapi_app.include_router(create_agent_router(lambda: _FailingService()))
    with TestClient(fastapi_app, headers={"X-Actor": "test-user"}) as client:
        response = client.post(
            "/api/v1/agent/sessions/session-1/messages",
            json={"content": "hello"},
        )

    metadata = provider_failure_metadata(failure_code)
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": failure_code.value,
            "message": metadata.safe_message,
            "details": {"retryable": metadata.retryable},
        }
    }
    response_text = response.text
    assert "raw provider body" not in response_text
    assert "api-key-secret" not in response_text


def _configure_strict_agent_environment(monkeypatch, tmp_path, *, enabled: bool) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_URL", "postgresql+psycopg2://x:y@localhost:5432/test")
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(artifact_dir))
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", "0" * 40)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", "v0.0.0-ci")
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci")
    if enabled:
        monkeypatch.setenv("COLD_STORAGE_AGENT_PROVIDER", "openai")
        monkeypatch.setenv("COLD_STORAGE_AGENT_MODEL", "gpt-test")
        monkeypatch.setenv("COLD_STORAGE_AGENT_TIMEOUT_SECONDS", "10")
        monkeypatch.setenv("COLD_STORAGE_AGENT_MAX_RETRIES", "0")
        monkeypatch.setenv("COLD_STORAGE_OPENAI_API_KEY", "test-only-key")


def _passed_provider_probe(settings):
    return AgentProviderProbeEvidence(
        passed=True,
        provider=settings.agent_provider,
        model=settings.agent_model,
        schema_verified=True,
        schema_identity="AgentDecision",
    )


def _probe_response() -> SimpleNamespace:
    return SimpleNamespace(
        output_parsed={
            "decision_type": "answer",
            "assistant_message": "ready",
            "missing_parameters": [],
            "tool_requests": [],
            "citations": [],
            "requires_review": False,
            "warnings": [],
        },
        output_text=None,
        status="completed",
        incomplete_details=None,
        error=None,
    )


class _ProbeResponses:
    def __init__(self, outcome):
        self._outcome = outcome
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


class _ProbeClient:
    def __init__(self, outcome):
        self.responses = _ProbeResponses(outcome)


def _probe_factory(outcome, calls):
    def _factory(**kwargs):
        calls.append(kwargs)
        return _ProbeClient(outcome)

    return _factory


def _stub_strict_dependency_startup(monkeypatch):
    from cold_storage.bootstrap import app as bootstrap_app

    monkeypatch.setattr(
        bootstrap_app,
        "init_dependencies",
        lambda settings, app=None, strict_runtime_authority=None: None,
    )


def test_strict_disabled_state_does_not_probe_or_construct_real_gateway(monkeypatch, tmp_path):
    from cold_storage.bootstrap.app import create_app

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=False)
    calls = 0

    def _probe(_settings):
        nonlocal calls
        calls += 1
        return True

    app = create_app(agent_provider_probe=_probe)
    evidence = app._agent_capability_evidence  # noqa: SLF001
    assert evidence.state.value == "AGENT_CAPABILITY_DISABLED"
    assert calls == 0
    assert app.state.strict_capability_bindings[-1] == ("model_backed_agent", "disabled")
    assert len(app.state.frozen_agent_endpoint_authority) == 10
    assert all(
        endpoint.__name__.startswith("disabled_agent_")
        for _, _, endpoint in app.state.frozen_agent_endpoint_authority
    )


def test_strict_enabled_not_ready_keeps_disabled_routes_and_fails_closed(
    monkeypatch,
    tmp_path,
):
    from cold_storage.bootstrap import runtime_readiness as readiness
    from cold_storage.bootstrap.app import create_app

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=True)
    _stub_strict_dependency_startup(monkeypatch)
    monkeypatch.setattr(
        readiness,
        "assert_no_unsafe_strict_capabilities",
        lambda **_kwargs: readiness.StrictCapabilityAuditEvidence(
            composition_passed=True,
            route_audit_passed=True,
        ),
    )
    app = create_app(agent_provider_probe=lambda _settings: False)
    evidence = app._agent_capability_evidence  # noqa: SLF001
    assert evidence.state.value == "AGENT_CAPABILITY_ENABLED_NOT_READY"
    assert evidence.global_readiness == "FAIL"
    assert app.state.strict_capability_bindings[-1] == (
        "model_backed_agent",
        "enabled_not_ready",
    )
    assert len(app.state.frozen_agent_endpoint_authority) == 10
    assert all(
        not endpoint.__name__.startswith("disabled_agent_")
        for _, _, endpoint in app.state.frozen_agent_endpoint_authority
    )
    with TestClient(app, headers={"X-Actor": "test-user"}) as client:
        response = client.get("/api/v1/agent/sessions")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_PROVIDER_UNAVAILABLE"


def test_strict_enabled_ready_exposes_only_real_agent_router(monkeypatch, tmp_path):
    from cold_storage.bootstrap.app import create_app

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=True)
    _stub_strict_dependency_startup(monkeypatch)
    app = create_app(
        agent_provider_probe=_passed_provider_probe,
        agent_client_factory=lambda **_kwargs: object(),
    )
    evidence = app._agent_capability_evidence  # noqa: SLF001
    assert evidence.state.value == "AGENT_CAPABILITY_ENABLED_NOT_READY"
    assert evidence.provider_probe_passed is True
    assert evidence.composition_passed is False
    agent_routes = app.state.frozen_agent_endpoint_authority
    assert len(agent_routes) == 10
    assert all(
        not endpoint.__name__.startswith("disabled_agent_") for _, _, endpoint in agent_routes
    )
    authority = app.state._strict_runtime_authority  # noqa: SLF001
    assert authority.agent_capability_state == "AGENT_CAPABILITY_ENABLED_NOT_READY"
    assert authority.agent_candidate is True
    assert callable(authority.agent_service_factory)


class TestStrictAgentZeroConstructionProvedBySpiesContinuation:
    """Keep the original strict spy cases collected after the new cases."""

    def test_zero_construction_on_get_sessions(self, strict_client_with_spies):
        """GET /api/v1/agent/sessions → 503, zero construction."""
        resp = strict_client_with_spies.get("/api/v1/agent/sessions")
        assert resp.status_code == 503
        assert _fake_gateway_init_count == 0
        assert _planning_agent_service_init_count == 0
        assert _get_planning_agent_service_count == 0
        assert _get_db_session_count == 0
        assert _report_artifact_storage_init_count == 0

    def test_zero_construction_on_post_messages(self, strict_client_with_spies):
        """POST /api/v1/agent/sessions/{id}/messages → 503, zero construction."""
        resp = strict_client_with_spies.post(
            "/api/v1/agent/sessions/some-id/messages",
            json={"content": "hello"},
        )
        assert resp.status_code == 503
        assert _fake_gateway_init_count == 0
        assert _planning_agent_service_init_count == 0
        assert _get_planning_agent_service_count == 0
        assert _get_db_session_count == 0
        assert _report_artifact_storage_init_count == 0

    def test_zero_construction_on_all_frozen_routes(self, strict_client_with_spies):
        """All 10 frozen routes → 503, zero construction after exhaustive hit."""
        for method, path in _FROZEN_AGENT_ROUTES:
            path_param = (
                path.replace("{session_id}", "sid")
                .replace("{turn_id}", "tid")
                .replace("{tool_call_id}", "tcid")
            )
            if method == "POST" and "cancel" in path:
                strict_client_with_spies.post(path_param)
            elif method == "POST" and "reject" in path:
                strict_client_with_spies.post(path_param, json={})
            elif method == "POST" and "confirm" in path:
                strict_client_with_spies.post(path_param, json={"confirmation_token": "x"})
            elif method == "POST":
                strict_client_with_spies.post(path_param, json={"title": "T", "content": "C"})
            elif method == "GET":
                strict_client_with_spies.get(path_param)

        assert _fake_gateway_init_count == 0, (
            f"FakeAgentModelGateway.__init__ called {_fake_gateway_init_count} times"
        )
        assert _planning_agent_service_init_count == 0, (
            f"PlanningAgentService.__init__ called {_planning_agent_service_init_count} times"
        )
        assert _get_planning_agent_service_count == 0, (
            f"_get_planning_agent_service called {_get_planning_agent_service_count} times"
        )
        assert _get_db_session_count == 0, f"_get_db_session called {_get_db_session_count} times"
        assert _report_artifact_storage_init_count == 0, (
            f"ReportArtifactStorage.__init__ called {_report_artifact_storage_init_count} times"
        )


def test_strict_default_probe_wiring_uses_canonical_gateway(monkeypatch, tmp_path):
    from cold_storage.bootstrap.app import create_app

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=True)
    calls: list[dict[str, object]] = []
    app = create_app(
        agent_client_factory=_probe_factory(_probe_response(), calls),
    )

    evidence = app._agent_capability_evidence  # noqa: SLF001
    assert evidence.state.value == "AGENT_CAPABILITY_ENABLED_NOT_READY"
    assert evidence.provider_probe_passed is True
    assert evidence.provider_schema_verified is True
    assert evidence.provider_schema_identity == "AgentDecision"
    assert calls[0]["base_url"] == OPENAI_OFFICIAL_BASE_URL
    assert app.state._strict_runtime_authority.agent_candidate is True  # noqa: SLF001
    assert len(app.state.frozen_agent_endpoint_authority) == 10


def test_strict_default_probe_is_not_called_when_agent_is_disabled(monkeypatch, tmp_path):
    from cold_storage.bootstrap.app import create_app

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=False)
    calls: list[dict[str, object]] = []
    app = create_app(
        agent_client_factory=_probe_factory(_probe_response(), calls),
    )

    assert app._agent_capability_evidence.state.value == "AGENT_CAPABILITY_DISABLED"  # noqa: SLF001
    assert calls == []


@pytest.mark.parametrize("failure_code", list(AgentProviderFailureCode))
def test_canonical_probe_preserves_frozen_provider_failure_code(failure_code):
    from cold_storage.bootstrap.dependencies import canonical_agent_provider_probe

    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "openai",
            "COLD_STORAGE_AGENT_MODEL": "gpt-test",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": 10,
            "COLD_STORAGE_AGENT_MAX_RETRIES": 0,
            "COLD_STORAGE_OPENAI_API_KEY": "test-only-key",
        }
    )
    probe = canonical_agent_provider_probe(
        client_factory=_probe_factory(
            ModelGatewayError("raw provider detail", code=failure_code),
            [],
        ),
    )

    evidence = probe(settings)
    assert evidence.passed is False
    assert evidence.failure_code is failure_code
    assert "raw provider detail" not in repr(evidence)


def test_canonical_probe_unknown_exception_fails_closed_without_raw_detail():
    from cold_storage.bootstrap.dependencies import canonical_agent_provider_probe

    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "openai",
            "COLD_STORAGE_AGENT_MODEL": "gpt-test",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": 10,
            "COLD_STORAGE_AGENT_MAX_RETRIES": 0,
            "COLD_STORAGE_OPENAI_API_KEY": "test-only-key",
        }
    )
    probe = canonical_agent_provider_probe(
        client_factory=_probe_factory(RuntimeError("secret raw diagnostic"), []),
    )

    evidence = probe(settings)
    assert evidence.passed is False
    assert evidence.failure_code is AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE
    assert "secret raw diagnostic" not in repr(evidence)


def test_strict_lifespan_finalizes_ready_only_after_real_composition_audit(monkeypatch, tmp_path):
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap import runtime_readiness as readiness
    from cold_storage.bootstrap.app import create_app
    from cold_storage.modules.planning_agent.infrastructure.real_gateways import (
        OpenAIAgentModelGateway,
    )
    from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=True)
    calls: list[dict[str, object]] = []
    audited_manifests: list[object] = []
    app = create_app(
        agent_client_factory=_probe_factory(_probe_response(), calls),
    )

    original_audit = readiness.assert_no_unsafe_strict_capabilities

    def _capture_audit(*args, **kwargs):
        audited_manifests.append(kwargs.get("binding_manifest"))
        return original_audit(*args, **kwargs)

    monkeypatch.setattr(readiness, "assert_no_unsafe_strict_capabilities", _capture_audit)

    def _actual_candidate_init(settings, app=None, strict_runtime_authority=None, **kwargs):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        deps._clear_composition_tokens()  # noqa: SLF001
        deps._singletons["engine"] = engine  # noqa: SLF001
        deps._singletons["project_service"] = DatabaseProjectService(engine)  # noqa: SLF001
        gateway = OpenAIAgentModelGateway(
            api_key=settings.openai_api_key,
            model_name=settings.agent_model,
            timeout_seconds=settings.agent_timeout_seconds,
            max_retries=settings.agent_max_retries,
            provider=settings.agent_provider,
            client_factory=kwargs.get("agent_client_factory"),
        )
        deps._singletons["agent_gateway"] = gateway  # noqa: SLF001
        deps._record_composition_token("OPENAI_AGENT_MODEL_GATEWAY_INSTANTIATED")  # noqa: SLF001
        deps._record_composition_token("DATABASE_COEFFICIENT_SERVICE_INSTANTIATED")  # noqa: SLF001
        session = Session(bind=engine)
        try:
            service = strict_runtime_authority.agent_service_factory(session)
            assert isinstance(service, PlanningAgentService)
        finally:
            session.close()
        deps._record_composition_token("REAL_PLANNING_AGENT_SERVICE_COMPOSED")  # noqa: SLF001
        readiness.set_canonical_settings(settings)
        readiness.set_composition_manifest_provider(deps._composition_manifest_provider)  # noqa: SLF001
        readiness.assert_no_unsafe_strict_capabilities(
            app=app,
            authority=strict_runtime_authority,
        )

    monkeypatch.setattr(bootstrap_app, "init_dependencies", _actual_candidate_init)

    with TestClient(app, headers={"X-Actor": "test-user"}):
        evidence = app._agent_capability_evidence  # noqa: SLF001
        assert evidence.state.value == "AGENT_CAPABILITY_ENABLED_READY"
        assert evidence.provider_probe_passed is True
        assert evidence.composition_passed is True
        assert evidence.route_audit_passed is True
        assert app.state._strict_runtime_authority.agent_candidate is True  # noqa: SLF001
        assert audited_manifests[-1] == (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "enabled_ready"),
        )


def test_strict_composition_failure_cannot_publish_ready(monkeypatch, tmp_path):
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap.app import create_app

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=True)
    app = create_app(
        agent_client_factory=_probe_factory(_probe_response(), []),
    )

    def _composition_failure(*_args, **_kwargs):
        raise RuntimeError("composition failure")

    monkeypatch.setattr(bootstrap_app, "init_dependencies", _composition_failure)
    with pytest.raises(RuntimeError, match="composition failure"), TestClient(app):
        pass
    assert app._agent_capability_evidence.state.value == "AGENT_CAPABILITY_ENABLED_NOT_READY"  # noqa: SLF001


def test_strict_route_audit_failure_cannot_publish_ready(monkeypatch, tmp_path):
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import runtime_readiness as readiness
    from cold_storage.bootstrap.app import create_app

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=True)
    app = create_app(
        agent_client_factory=_probe_factory(_probe_response(), []),
    )

    def _route_audit_failure(*_args, **_kwargs):
        raise readiness.UnsafeStrictCapabilityWiring(
            "route audit failed",
            unsafe_capabilities=("model_backed_agent",),
        )

    monkeypatch.setattr(bootstrap_app, "init_dependencies", lambda *args, **kwargs: None)
    monkeypatch.setattr(readiness, "assert_no_unsafe_strict_capabilities", _route_audit_failure)
    with pytest.raises(readiness.UnsafeStrictCapabilityWiring), TestClient(app):
        pass
    assert app._agent_capability_evidence.state.value == "AGENT_CAPABILITY_ENABLED_NOT_READY"  # noqa: SLF001


def test_final_ready_authority_and_manifest_are_audited_before_publish(monkeypatch, tmp_path):
    """A READY projection cannot be self-attested after the last audit."""
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import runtime_readiness as readiness
    from cold_storage.bootstrap.app import create_app

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=True)
    app = create_app(
        agent_provider_probe=_passed_provider_probe,
        agent_client_factory=lambda **_kwargs: object(),
    )
    audited_manifests: list[object] = []

    def _audit(*, binding_manifest=None, **_kwargs):
        audited_manifests.append(binding_manifest)
        if binding_manifest == (
            ("coefficient_http", "database_backed"),
            ("model_backed_agent", "enabled_ready"),
        ):
            raise readiness.UnsafeStrictCapabilityWiring(
                "final binding audit failed",
                unsafe_capabilities=("model_backed_agent",),
            )
        return readiness.StrictCapabilityAuditEvidence(
            composition_passed=True,
            route_audit_passed=True,
        )

    monkeypatch.setattr(bootstrap_app, "init_dependencies", lambda *args, **kwargs: None)
    monkeypatch.setattr(readiness, "assert_no_unsafe_strict_capabilities", _audit)

    with pytest.raises(readiness.UnsafeStrictCapabilityWiring), TestClient(app):
        pass

    assert audited_manifests[-1] == (
        ("coefficient_http", "database_backed"),
        ("model_backed_agent", "enabled_ready"),
    )
    assert app._agent_capability_evidence.state.value == "AGENT_CAPABILITY_ENABLED_NOT_READY"  # noqa: SLF001


def test_fresh_provider_failure_demotes_and_recovers_guarded_routes(monkeypatch, tmp_path):
    """READY -> NOT_READY -> READY uses one process and one app authority."""
    from cold_storage.bootstrap import app as bootstrap_app
    from cold_storage.bootstrap import dependencies as deps
    from cold_storage.bootstrap import runtime_readiness as readiness
    from cold_storage.bootstrap.app import create_app

    _configure_strict_agent_environment(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setenv("PLANNING_AGENT_ALLOW_INSECURE_ACTOR", "true")

    timeout_evidence = AgentProviderProbeEvidence(
        passed=False,
        failure_code=AgentProviderFailureCode.AGENT_PROVIDER_TIMEOUT,
        provider="openai",
        model="gpt-test",
    )
    probe_results = [_passed_provider_probe, timeout_evidence, _passed_provider_probe]
    probe_calls: list[int] = []

    def _sequenced_probe(settings):
        result = probe_results[len(probe_calls)]
        probe_calls.append(1)
        return result(settings) if callable(result) else result

    class _RequestService:
        def list_sessions_by_actor(self, _actor):
            return []

    service_builds: list[object] = []

    def _record_service_build(_db_session, gateway):
        service_builds.append(gateway)
        return _RequestService()

    monkeypatch.setattr(bootstrap_app, "_build_planning_agent_service", _record_service_build)

    def _candidate_init(settings, app=None, strict_runtime_authority=None):  # noqa: ARG001
        deps._singletons["engine"] = create_engine(  # noqa: SLF001
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        deps._clear_composition_tokens()  # noqa: SLF001
        deps._singletons["agent_gateway"] = object()  # noqa: SLF001
        deps._record_composition_token("OPENAI_AGENT_MODEL_GATEWAY_INSTANTIATED")  # noqa: SLF001
        deps._record_composition_token("REAL_PLANNING_AGENT_SERVICE_COMPOSED")  # noqa: SLF001
        deps._record_composition_token("DATABASE_COEFFICIENT_SERVICE_INSTANTIATED")  # noqa: SLF001
        readiness.set_canonical_settings(settings)
        readiness.set_composition_manifest_provider(  # noqa: SLF001
            deps._composition_manifest_provider,  # noqa: SLF001
        )
        readiness.set_readiness_state(readiness.ReadinessState(state="READY"))

    monkeypatch.setattr(bootstrap_app, "init_dependencies", _candidate_init)

    def _passing_readiness(**kwargs):
        return tuple(
            readiness.ProbeOutcome(
                name=getattr(probe, "__name__", "probe"),
                status="pass",
            )
            for probe in kwargs["readiness_probes"]
        )

    monkeypatch.setattr(readiness, "run_readiness_phase", _passing_readiness)
    app = create_app(agent_provider_probe=_sequenced_probe)

    with TestClient(app, headers={"X-Actor": "test-user"}) as client:
        service_builds.clear()

        demoted = client.get("/health/ready")
        assert demoted.status_code == 503
        assert demoted.json()["check_code"] == "AGENT_PROVIDER_TIMEOUT"
        assert app._agent_capability_evidence.state.value == (  # noqa: SLF001
            "AGENT_CAPABILITY_ENABLED_NOT_READY"
        )

        guarded = client.get("/api/v1/agent/sessions")
        assert guarded.status_code == 503
        assert guarded.json()["error"]["code"] == "AGENT_PROVIDER_TIMEOUT"
        assert service_builds == []

        recovered = client.get("/health/ready")
        assert recovered.status_code == 200
        assert app._agent_capability_evidence.state.value == (  # noqa: SLF001
            "AGENT_CAPABILITY_ENABLED_READY"
        )

        available = client.get("/api/v1/agent/sessions")
        assert available.status_code == 200
        assert available.json() == []
        assert len(service_builds) == 1

    assert len(probe_calls) == 3
