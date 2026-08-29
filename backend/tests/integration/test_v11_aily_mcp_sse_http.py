"""HTTP tests for Aily MCP Streamable HTTP (Feishu path) on unmodified create_app."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.aily.api.mcp_sse import MCP_MESSAGES_PATH, MCP_MOUNT_PATH, MCP_SSE_PATH
from cold_storage.modules.aily.application.mcp_zone_plan import PREVIEW_ZONE_PLAN_TOOL_NAME

_CONNECTOR_SECRET = "connector-test-secret-v11-mcp"

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0.1"},
    },
}

_TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

_FIVE_KEYS = {
    "daily_inbound_mass_kg": 20000,
    "finished_storage_days": 7,
    "frozen_storage_days": 10,
    "main_packaging_storage_days": 4,
    "auxiliary_packaging_storage_days": 12,
}

_TOOLS_CALL = {
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {"name": PREVIEW_ZONE_PLAN_TOOL_NAME, "arguments": _FIVE_KEYS},
}


def _post_jsonrpc(
    client: TestClient,
    path: str,
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
):
    """POST JSON-RPC like Feishu/curl: Content-Type only, no Accept header."""
    request_headers = {"content-type": "application/json"}
    if headers:
        request_headers.update(headers)
    return client.post(path, content=json.dumps(payload), headers=request_headers)


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


def test_aily_mcp_streamable_post_unauthorized_when_secret_set(monkeypatch) -> None:
    monkeypatch.setenv("COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET", _CONNECTOR_SECRET)
    client = TestClient(create_app())
    response = _post_jsonrpc(client, MCP_SSE_PATH, _INITIALIZE)
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


def test_aily_mcp_streamable_initialize_returns_complete_json() -> None:
    client = TestClient(create_app())
    response = _post_jsonrpc(client, MCP_SSE_PATH, _INITIALIZE)
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("application/json")
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert "result" in body
    assert "event:" not in response.text
    server_info = body["result"]["serverInfo"]
    assert server_info["name"] == "cold-storage-zone-plan"


def test_aily_mcp_streamable_tools_list_includes_preview_zone_plan() -> None:
    client = TestClient(create_app())
    init = _post_jsonrpc(client, MCP_SSE_PATH, _INITIALIZE)
    assert init.status_code == 200
    response = _post_jsonrpc(client, MCP_SSE_PATH, _TOOLS_LIST)
    assert response.status_code == 200
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    names = [tool["name"] for tool in body["result"]["tools"]]
    assert names == [PREVIEW_ZONE_PLAN_TOOL_NAME]


def test_aily_mcp_streamable_tools_list_on_mount_root() -> None:
    client = TestClient(create_app())
    init = _post_jsonrpc(client, f"{MCP_MOUNT_PATH}/", _INITIALIZE)
    assert init.status_code == 200
    response = _post_jsonrpc(client, f"{MCP_MOUNT_PATH}/", _TOOLS_LIST)
    assert response.status_code == 200
    names = [tool["name"] for tool in response.json()["result"]["tools"]]
    assert PREVIEW_ZONE_PLAN_TOOL_NAME in names


def test_aily_mcp_streamable_tools_call_returns_markdown_table() -> None:
    client = TestClient(create_app())
    assert _post_jsonrpc(client, MCP_SSE_PATH, _INITIALIZE).status_code == 200
    response = _post_jsonrpc(client, MCP_SSE_PATH, _TOOLS_CALL)
    assert response.status_code == 200
    result = response.json()["result"]
    structured = result.get("structuredContent")
    if structured is None:
        structured = json.loads(result["content"][0]["text"])
    assert structured["ok"] is True
    assert structured["calculator_name"] == "cold_room_zone_plan"
    assert structured["calculator_version"] == "1.0.0"
    assert "面积" in structured["markdown_table"]
