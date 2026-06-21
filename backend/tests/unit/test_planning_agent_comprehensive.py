"""Comprehensive tests for the planning agent module.

Covers:
1. Confirmation flow (approve)
2. Rejection flow
3. Token replay protection
4. Expired confirmation
5. create_app integration
6. Auth enforcement (requires_project)
7. Error propagation (unregistered tool → 422, not 500)
8. Tool schema validation (wrong type)
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.planning_agent.application.orchestrator import AgentOrchestrator
from cold_storage.modules.planning_agent.application.service import (
    PlanningAgentService,
    sha256_json,
)
from cold_storage.modules.planning_agent.application.tool_registry import (
    build_default_registry,
)
from cold_storage.modules.planning_agent.domain.enums import (
    SessionStatus,
    ToolCallStatus,
    TurnStatus,
)
from cold_storage.modules.planning_agent.domain.errors import (
    ConfirmationAlreadyUsedError,
    ConfirmationExpiredError,
    ToolArgumentValidationError,
    UnauthorizedError,
    UnregisteredToolError,
)
from cold_storage.modules.planning_agent.domain.gateways import (
    AgentModelRequest,
    GatewayMetadata,
)
from cold_storage.modules.planning_agent.domain.models import (
    AgentConfirmation,
    AgentDecision,
    AgentToolRequest,
    AgentToolResult,
)
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import (
    FakeAgentModelGateway,
)
from cold_storage.modules.planning_agent.infrastructure.orm import Base
from cold_storage.modules.planning_agent.infrastructure.repository import AgentRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def repo(db_session):
    return AgentRepository(db_session)


@pytest.fixture()
def gateway():
    return FakeAgentModelGateway()


@pytest.fixture()
def registry():
    return build_default_registry()


class _FakeProjectService:
    """Minimal fake for version governance in tests."""

    def list_versions(self, project_id: str):
        from dataclasses import dataclass

        @dataclass
        class _FakeVersion:
            id: str = "ver-1"
            version_number: int = 1
            status: str = "draft"

        return [_FakeVersion()]


@pytest.fixture()
def orchestrator():
    return AgentOrchestrator(project_service=_FakeProjectService())


@pytest.fixture()
def service(repo, gateway, registry, orchestrator):
    return PlanningAgentService(
        repository=repo,
        gateway=gateway,
        registry=registry,
        orchestrator=orchestrator,
    )


# ---------------------------------------------------------------------------
# Helper: gateway that proposes an unregistered tool
# ---------------------------------------------------------------------------


class _UnregisteredToolGateway:
    """Gateway that always returns a tool call for an unregistered tool."""

    def generate_decision(self, request: AgentModelRequest) -> AgentDecision:
        return AgentDecision(
            decision_type="propose_tools",
            assistant_message="Testing unregistered tool",
            tool_requests=[
                AgentToolRequest(
                    tool_name="nonexistent.tool_xyz",
                    arguments={},
                    reason="test",
                ),
            ],
        )

    def get_metadata(self) -> GatewayMetadata:
        return GatewayMetadata(
            provider="fake",
            model_name="test",
            gateway_version="1.0.0",
            production_ready=False,
            requires_review=True,
        )


class _AuthEnforcementGateway:
    """Gateway that proposes a tool requiring project binding."""

    def generate_decision(self, request: AgentModelRequest) -> AgentDecision:
        return AgentDecision(
            decision_type="propose_tools",
            assistant_message="Testing auth enforcement",
            tool_requests=[
                AgentToolRequest(
                    tool_name="project.get",
                    arguments={"project_id": "proj-1"},
                    reason="test",
                ),
            ],
        )

    def get_metadata(self) -> GatewayMetadata:
        return GatewayMetadata(
            provider="fake",
            model_name="test",
            gateway_version="1.0.0",
            production_ready=False,
            requires_review=True,
        )


class _FakeSchemeAdapter:
    """Fake adapter for scheme.generate_and_compare that returns success."""

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        return AgentToolResult(
            tool_name="scheme.generate_and_compare",
            output={"scheme_result": {"schemes": [{"name": "方案A"}, {"name": "方案B"}]}},
            requires_review=True,
        )


# ===================================================================
# 1. Confirmation flow: approve → session transitions back to active
# ===================================================================


class TestConfirmationFlow:
    """Create session → post message triggering scheme.generate_and_compare
    (requires confirmation) → verify pending_confirmations with token
    → confirm with token → verify session is active again."""

    def test_confirm_tool_call_approve(self, db_session, gateway, registry):
        repo = AgentRepository(db_session)
        orch = AgentOrchestrator(project_service=_FakeProjectService())
        orch.register_adapter("scheme.generate_and_compare", _FakeSchemeAdapter())
        service = PlanningAgentService(
            repository=repo,
            gateway=gateway,
            registry=registry,
            orchestrator=orch,
        )

        # Create session WITH project_id (scheme.generate_and_compare requires it)
        session = service.create_session(
            project_id="proj-1",
            project_version_id="ver-1",
            title="Confirm test",
        )

        # Message with '方案' + '项目' triggers scheme.generate_and_compare
        result = service.post_user_message(session.id, "帮我生成项目方案 项目ID是proj-1 版本1")

        # Verify pending_confirmations returned
        pending = result["pending_confirmations"]
        assert len(pending) >= 1, "Expected at least one pending confirmation"
        token_info = pending[0]
        assert "tool_call_id" in token_info
        assert "confirmation_token" in token_info
        assert "expires_at" in token_info
        assert "arguments_sha256" in token_info

        # Verify session is now awaiting_confirmation
        current = service.get_session(session.id)
        assert current.status == SessionStatus.AWAITING_CONFIRMATION

        # Verify turn is awaiting_confirmation
        turn = service.get_turn(result["turn_id"])
        assert turn.status == TurnStatus.AWAITING_CONFIRMATION

        # Confirm the tool call
        confirm_result = service.confirm_tool_call(
            token_info["tool_call_id"],
            confirmation_token=token_info["confirmation_token"],
        )

        # Verify session transitions back to active
        assert confirm_result["session_status"] == SessionStatus.ACTIVE.value
        final_session = service.get_session(session.id)
        assert final_session.status == SessionStatus.ACTIVE

        # Verify tool call succeeded or executed (not awaiting_confirmation)
        tc = service.get_tool_call(token_info["tool_call_id"])
        assert tc.status in (
            ToolCallStatus.SUCCEEDED,
            ToolCallStatus.EXECUTING,
            ToolCallStatus.CONFIRMED,
        )


# ===================================================================
# 2. Rejection flow: reject → session transitions back to active
# ===================================================================


class TestRejectionFlow:
    """Same as confirmation flow but reject → session transitions back."""

    def test_reject_tool_call(self, db_session, gateway, registry, orchestrator):
        repo = AgentRepository(db_session)
        service = PlanningAgentService(
            repository=repo,
            gateway=gateway,
            registry=registry,
            orchestrator=orchestrator,
        )

        session = service.create_session(
            project_id="proj-1",
            project_version_id="ver-1",
            title="Reject test",
        )

        result = service.post_user_message(session.id, "帮我生成项目方案 项目ID是proj-1 版本1")

        pending = result["pending_confirmations"]
        assert len(pending) >= 1
        token_info = pending[0]
        tool_call_id = token_info["tool_call_id"]

        # Verify session is awaiting_confirmation
        current = service.get_session(session.id)
        assert current.status == SessionStatus.AWAITING_CONFIRMATION

        # Reject
        reject_result = service.reject_tool_call(tool_call_id)

        # Verify session transitions back to active
        assert reject_result["session_status"] == SessionStatus.ACTIVE.value
        final_session = service.get_session(session.id)
        assert final_session.status == SessionStatus.ACTIVE

        # Verify tool call was rejected
        tc = service.get_tool_call(tool_call_id)
        assert tc.status == ToolCallStatus.REJECTED


# ===================================================================
# 3. Token replay protection: confirm same token twice → second fails
# ===================================================================


class TestTokenReplayProtection:
    def test_confirm_twice_second_fails(self, db_session, gateway, registry):
        repo = AgentRepository(db_session)
        orch = AgentOrchestrator(project_service=_FakeProjectService())
        orch.register_adapter("scheme.generate_and_compare", _FakeSchemeAdapter())
        service = PlanningAgentService(
            repository=repo,
            gateway=gateway,
            registry=registry,
            orchestrator=orch,
        )

        session = service.create_session(
            project_id="proj-1",
            project_version_id="ver-1",
            title="Replay test",
        )

        result = service.post_user_message(session.id, "帮我生成项目方案 项目ID是proj-1 版本1")

        pending = result["pending_confirmations"]
        assert len(pending) >= 1
        token_info = pending[0]

        # First confirm — should succeed
        first = service.confirm_tool_call(
            token_info["tool_call_id"],
            confirmation_token=token_info["confirmation_token"],
        )
        assert first["session_status"] == SessionStatus.ACTIVE.value

        # Second confirm with same token — should fail
        with pytest.raises(ConfirmationAlreadyUsedError):
            service.confirm_tool_call(
                token_info["tool_call_id"],
                confirmation_token=token_info["confirmation_token"],
            )


# ===================================================================
# 4. Expired confirmation: expires_at in past → confirm fails
# ===================================================================


class TestExpiredConfirmation:
    def test_confirm_expired_token(self, db_session, repo):
        """Manually insert an expired confirmation and try to confirm."""
        service = PlanningAgentService(
            repository=repo,
            gateway=FakeAgentModelGateway(),
            registry=build_default_registry(),
            orchestrator=AgentOrchestrator(project_service=_FakeProjectService()),
        )

        session = service.create_session(
            project_id="proj-1",
            project_version_id="ver-1",
            title="Expired test",
        )

        result = service.post_user_message(session.id, "帮我生成项目方案 项目ID是proj-1 版本1")

        pending = result["pending_confirmations"]
        assert len(pending) >= 1
        token_info = pending[0]

        # Manually expire the confirmation
        token_hash = sha256_json(token_info["confirmation_token"])
        confirmation = repo.get_confirmation_by_token_hash(token_hash)
        assert confirmation is not None

        expired = AgentConfirmation(
            **{
                **asdict(confirmation),
                "expires_at": datetime.now(UTC) - timedelta(hours=1),
            }
        )
        repo.update_confirmation(expired)

        # Try to confirm — should fail with ConfirmationExpiredError
        with pytest.raises(ConfirmationExpiredError):
            service.confirm_tool_call(
                token_info["tool_call_id"],
                confirmation_token=token_info["confirmation_token"],
            )


# ===================================================================
# 5. create_app integration test
# ===================================================================


class TestCreateAppIntegration:
    """Test POST /api/v1/agent/sessions returns 201,
    GET /api/v1/agent/sessions returns 200."""

    def _build_test_app(self):
        """Build a FastAPI app with the agent router registered."""
        from cold_storage.modules.planning_agent.api.routes import (
            create_agent_router,
        )

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
        db_sess = SessionFactory()

        repo = AgentRepository(db_sess)
        gateway = FakeAgentModelGateway()
        registry = build_default_registry()
        orchestrator = AgentOrchestrator()
        svc = PlanningAgentService(
            repository=repo,
            gateway=gateway,
            registry=registry,
            orchestrator=orchestrator,
        )

        app = FastAPI()
        app.include_router(create_agent_router(lambda: svc))
        return app, db_sess

    def test_create_session_returns_201(self):
        app, db_sess = self._build_test_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/agent/sessions",
                json={"title": "Integration test"},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["status"] == "active"
            assert data["title"] == "Integration test"
            assert "id" in data

    def test_list_sessions_returns_200(self):
        app, db_sess = self._build_test_app()
        with TestClient(app) as client:
            # Create a session first
            client.post(
                "/api/v1/agent/sessions",
                json={"title": "List test"},
            )
            resp = client.get("/api/v1/agent/sessions")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) >= 1


# ===================================================================
# 6. Auth enforcement: session without project_id → tool requiring
#    project fails with UnauthorizedError
# ===================================================================


class TestAuthEnforcement:
    def test_tool_requiring_project_without_session_project(
        self, db_session, registry, orchestrator
    ):
        repo = AgentRepository(db_session)
        auth_gateway = _AuthEnforcementGateway()
        service = PlanningAgentService(
            repository=repo,
            gateway=auth_gateway,
            registry=registry,
            orchestrator=orchestrator,
        )

        # Session WITHOUT project_id
        session = service.create_session(title="No project session")

        # project.get has requires_project=True, so should fail
        with pytest.raises(UnauthorizedError, match="requires a bound project"):
            service.post_user_message(session.id, "查询项目信息")


# ===================================================================
# 7. Error propagation: unregistered tool → UnregisteredToolError
#    (which maps to 422 at API level, not 500)
# ===================================================================


class TestErrorPropagation:
    def test_unregistered_tool_raises_correct_error(self, db_session, registry, orchestrator):
        repo = AgentRepository(db_session)
        unreg_gateway = _UnregisteredToolGateway()
        service = PlanningAgentService(
            repository=repo,
            gateway=unreg_gateway,
            registry=registry,
            orchestrator=orchestrator,
        )

        session = service.create_session(title="Unregistered tool test")

        # Should raise UnregisteredToolError, NOT a generic 500 error
        with pytest.raises(UnregisteredToolError) as exc_info:
            service.post_user_message(session.id, "test")

        assert "nonexistent.tool_xyz" in str(exc_info.value)

    def test_unregistered_tool_api_returns_422(self, db_session, registry, orchestrator):
        """At the API layer, UnregisteredToolError maps to 422, not 500."""
        from cold_storage.modules.planning_agent.api.routes import (
            create_agent_router,
        )

        repo = AgentRepository(db_session)
        unreg_gateway = _UnregisteredToolGateway()
        service = PlanningAgentService(
            repository=repo,
            gateway=unreg_gateway,
            registry=registry,
            orchestrator=orchestrator,
        )

        app = FastAPI()
        app.include_router(create_agent_router(lambda: service))

        with TestClient(app, raise_server_exceptions=False) as client:
            create_resp = client.post(
                "/api/v1/agent/sessions",
                json={"title": "Error propagation test"},
            )
            sid = create_resp.json()["id"]

            msg_resp = client.post(
                f"/api/v1/agent/sessions/{sid}/messages",
                json={"content": "trigger unregistered tool"},
            )
            # Should be 422 (Unprocessable Entity), NOT 500
            assert msg_resp.status_code == 422


# ===================================================================
# 8. Tool schema validation: pass string to number field → fails
# ===================================================================


class TestToolSchemaValidation:
    def test_string_to_number_field_fails(self, registry):
        """Passing a string to a number field should fail validation."""
        with pytest.raises(ToolArgumentValidationError):
            registry.validate_arguments(
                "planning.calculate_throughput_inventory_area",
                {
                    "daily_inbound_mass_kg": "not_a_number",
                    "working_time_h_per_day": 8,
                },
            )

    def test_string_to_integer_field_fails(self, registry):
        """Passing a string to an integer field should fail validation."""
        with pytest.raises(ToolArgumentValidationError):
            registry.validate_arguments(
                "scheme.generate_and_compare",
                {
                    "project_id": "proj-1",
                    "version_number": "not_an_int",
                },
            )

    def test_missing_required_field_fails(self, registry):
        """Missing required fields should fail validation."""
        with pytest.raises(ToolArgumentValidationError):
            registry.validate_arguments(
                "planning.calculate_throughput_inventory_area",
                {
                    "daily_inbound_mass": 1000,
                    "mass_unit": "kg",
                    # missing working_time_h_per_day
                },
            )

    def test_correct_types_pass(self, registry):
        """Correct types should pass validation without error."""
        registry.validate_arguments(
            "planning.calculate_throughput_inventory_area",
            {
                "daily_inbound_mass": 1000.0,
                "mass_unit": "kg",
                "working_time_h_per_day": 8,
            },
        )
