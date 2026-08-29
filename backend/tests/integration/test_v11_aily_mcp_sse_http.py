"""HTTP tests for the Aily MCP SSE mount on unmodified create_app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.aily.api.mcp_sse import MCP_MESSAGES_PATH, MCP_SSE_PATH

_CONNECTOR_SECRET = "connector-test-secret-v11-mcp"


def test_aily_mcp_sse_unauthorized_without_header_when_secret_set(monkeypatch) -> None:
    monkeypatch.setenv("COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET", _CONNECTOR_SECRET)
    client = TestClient(create_app())
    response = client.get(MCP_SSE_PATH)
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "AILY_CONNECTOR_UNAUTHORIZED"


def test_aily_mcp_sse_unauthorized_with_wrong_header_when_secret_set(monkeypatch) -> None:
    monkeypatch.setenv("COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET", _CONNECTOR_SECRET)
    client = TestClient(create_app())
    response = client.get(
        MCP_SSE_PATH,
        headers={"X-Aily-Connector-Key": "wrong-key"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AILY_CONNECTOR_UNAUTHORIZED"


def test_aily_mcp_messages_unauthorized_when_secret_set(monkeypatch) -> None:
    monkeypatch.setenv("COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET", _CONNECTOR_SECRET)
    client = TestClient(create_app())
    response = client.post(MCP_MESSAGES_PATH, json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AILY_CONNECTOR_UNAUTHORIZED"


def test_aily_mcp_messages_without_session_returns_client_error() -> None:
    client = TestClient(create_app())
    response = client.post(
        MCP_MESSAGES_PATH,
        content=b"{}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code in {400, 404}
