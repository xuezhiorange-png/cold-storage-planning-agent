"""HTTP integration coverage for the V2.1 factory-power MCP tool."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.aily.api.mcp_sse import MCP_SSE_PATH

_FIVE_KEYS: dict[str, Any] = {
    "daily_inbound_mass_kg": 20000,
    "finished_storage_days": 7,
    "frozen_storage_days": 10,
    "main_packaging_storage_days": 4,
    "auxiliary_packaging_storage_days": 12,
}
_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "v21-p2-test", "version": "0.1"},
    },
}


def _post_jsonrpc(client: TestClient, payload: dict[str, Any]):
    return client.post(
        MCP_SSE_PATH,
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )


def _initialized_client() -> TestClient:
    client = TestClient(create_app())
    response = _post_jsonrpc(client, _INITIALIZE)
    assert response.status_code == 200
    return client


def _structured(response: Any) -> dict[str, Any]:
    result = response.json()["result"]
    structured = result.get("structuredContent")
    if structured is None:
        structured = json.loads(result["content"][0]["text"])
    assert isinstance(structured, dict)
    return structured


def test_factory_power_mcp_tools_list_appends_sixth_tool_with_five_key_schema() -> None:
    client = _initialized_client()
    response = _post_jsonrpc(
        client,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "preview_zone_plan",
        "preview_cooling_load",
        "preview_equipment",
        "preview_installed_power",
        "preview_investment",
        "preview_factory_power",
    ]
    factory_tool = tools[-1]
    assert "估算工厂电功率" in factory_tool["description"]
    assert "kW" in factory_tool["description"]
    schema = factory_tool["inputSchema"]
    assert schema["type"] == "object"
    assert tuple(schema["properties"]) == tuple(_FIVE_KEYS)
    assert tuple(schema["required"]) == tuple(_FIVE_KEYS)
    assert schema["additionalProperties"] is False
    assert not set(schema["properties"]) & {
        "factory_area_m2",
        "cold_storage_area_m2",
        "refrigerated_area_m2",
        "total_area_m2",
    }


def test_factory_power_mcp_call_returns_shared_success_projection() -> None:
    client = _initialized_client()
    response = _post_jsonrpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "preview_factory_power", "arguments": _FIVE_KEYS},
        },
    )

    assert response.status_code == 200
    body = _structured(response)
    assert body["ok"] is True
    assert body["reply_kind"] == "factory_power_estimation_table"
    assert body["available"] is True
    assert body["calculator_identity"] == "factory_power_estimation@2.0.0-p1"
    assert body["canonical_result_hash"].startswith("sha256:")
    assert body["requires_review"] is True
    assert body["persisted"] is False
    assert body["details"]
    assert body["summary"] is not None
    assert body["markdown_table"]


def test_factory_power_mcp_call_rejects_area_injection_at_runtime() -> None:
    client = _initialized_client()
    arguments = dict(_FIVE_KEYS)
    arguments["factory_area_m2"] = 9999
    response = _post_jsonrpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "preview_factory_power", "arguments": arguments},
        },
    )

    assert response.status_code == 200
    body = _structured(response)
    assert body["ok"] is False
    assert body["error"]["code"] == "MCP_INPUT_SCHEMA_REJECTED"
    assert body["error"]["missing_keys"] == []
    assert body["error"]["ask_operator"] == ""
