"""API endpoint tests for planning agent routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.planning_agent.api.routes import create_agent_router
from cold_storage.modules.planning_agent.application.orchestrator import AgentOrchestrator
from cold_storage.modules.planning_agent.application.service import PlanningAgentService
from cold_storage.modules.planning_agent.application.tool_registry import build_default_registry
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import FakeAgentModelGateway
from cold_storage.modules.planning_agent.infrastructure.orm import Base
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
