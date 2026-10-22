"""Actual mounted MCP HTTP calls; real R13 algorithms, synthetic input only."""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.aily.api.mcp_sse import MCP_MOUNT_PATH, MCP_SSE_PATH
from cold_storage.modules.aily.application.mcp_truck_preview import (
    invoke_preview_truck_tool,
    preview_truck_input_schema,
)
from cold_storage.modules.layout.application.truck_preview import invoke_truck_preview
from tests.integration.test_v11_aily_mcp_sse_http import _FIVE_KEYS, _INITIALIZE, _TOOLS_LIST
from tests.unit.test_v222_r13_truck_parameter_preview import example, rectangle

OLD_NAMES = [
    "preview_zone_plan",
    "preview_cooling_load",
    "preview_equipment",
    "preview_installed_power",
    "preview_investment",
    "preview_factory_power",
    "preview_site_layout",
]


def call(client: TestClient, name: str, arguments: Any) -> dict[str, Any]:
    response = client.post(
        MCP_SSE_PATH,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200
    result: dict[str, Any] = response.json()["result"]
    assert result["structuredContent"] == json.loads(result["content"][0]["text"])
    return result


def payload() -> dict[str, Any]:
    return json.loads(json.dumps(example(), default=str))


def test_actual_initialize_discovery_call_svg_and_r13_equivalence() -> None:
    with TestClient(create_app()) as client:
        initialize = client.post(MCP_SSE_PATH, json=_INITIALIZE)
        assert initialize.status_code == 200
        assert initialize.json()["result"]["serverInfo"]["name"] == "cold-storage-zone-plan"
        tools = client.post(MCP_SSE_PATH, json=_TOOLS_LIST).json()["result"]["tools"]
        assert [t["name"] for t in tools] == [*OLD_NAMES, "preview_truck"]
        schema = tools[7]["inputSchema"]
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload())
        result = call(client, "preview_truck", payload())
        body = result["structuredContent"]
        assert not result["isError"] and body["ok"] and body["status"] == "PASS"
        assert body["synthetic_test_only"] and not body["real_project_approved"]
        assert not body["p2_complete"] and not body["server_replay_accepted"]
        assert len(body["truck"]["maneuver_chain"]) == 3
        assert body["result"] == invoke_truck_preview(payload())
        assert body["calculation_hash"] == body["result"]["canonical_result_hash"]
        assert body["drawing"]["svg"] == body["result"]["svg"]
        assert (
            body["drawing"]["svg_sha256"]
            == "sha256:" + sha256(body["drawing"]["svg"].encode()).hexdigest()
        )
        root_tools = client.post(MCP_MOUNT_PATH + "/", json=_TOOLS_LIST).json()["result"]["tools"]
        assert root_tools == tools


@pytest.mark.parametrize(
    "kind", ["missing_vehicle", "missing_template", "missing_source", "hash", "large", "invalid"]
)
def test_input_errors_chinese_prompt_and_no_base64_echo(kind: str) -> None:
    p = payload()
    if kind == "missing_vehicle":
        del p["truck_access"]["vehicle_width_m"]
    elif kind == "missing_template":
        del p["truck_maneuver"]
    elif kind == "missing_source":
        p["evidence"] = []
    elif kind == "hash":
        p["evidence"][0]["content_base64"] = base64.b64encode(b"SECRET_SYNTHETIC_DOCUMENT").decode()
    elif kind == "large":
        p["evidence"][0]["content_base64"] = "A" * 1_398_108
    else:
        p["unknown"] = True
    with TestClient(create_app()) as client:
        r = call(client, "preview_truck", p)
        body = r["structuredContent"]
        assert r["isError"] and not body["ok"]
        assert body["error"]["code"] and "请" in body["error"]["ask_operator"]
        assert "Traceback" not in json.dumps(body)
        assert p["evidence"][0]["content_base64"] not in json.dumps(body) if p["evidence"] else True


def test_collision_and_personnel_review_are_not_engineering_pass() -> None:
    with TestClient(create_app()) as client:
        p = payload()
        p["site_geometry"]["hard_obstacles"] = [rectangle(0, 8, 8, 12)]
        body = call(client, "preview_truck", p)["structuredContent"]
        assert body["ok"] and not body["engineering_pass"]
        assert body["status"] == "TRUCK_MANEUVER_SEARCH_EXHAUSTED" and body["drawing"] is None
        p = payload()
        p["site_geometry"]["personnel_corridors"] = [rectangle(1, 11, 5, 13)]
        body = call(client, "preview_truck", p)["structuredContent"]
        assert body["ok"] and body["status"] == "REQUIRES_ENGINEERING_REVIEW"
        assert not body["engineering_pass"] and body["drawing"] is None


def test_existing_seven_schemas_and_dispatch_remain_unchanged() -> None:
    with TestClient(create_app()) as client:
        tools = client.post(MCP_SSE_PATH, json=_TOOLS_LIST).json()["result"]["tools"]
        for name in OLD_NAMES[:6]:
            assert call(client, name, _FIVE_KEYS)["structuredContent"]["ok"]
        assert not call(client, OLD_NAMES[6], {})["structuredContent"]["ok"]
        schema = preview_truck_input_schema()
        original = json.loads(
            (
                Path(__file__).parents[3]
                / "docs/tasks/V2_2_2-parameterized-truck-preview-v1.schema.json"
            ).read_text()
        )

        def remove_descriptions(v: Any) -> Any:
            if isinstance(v, dict):
                return {k: remove_descriptions(x) for k, x in v.items() if k != "description"}
            if isinstance(v, list):
                return [remove_descriptions(x) for x in v]
            return v

        assert schema["required"] == original["required"]
        assert schema["additionalProperties"] == original["additionalProperties"] is False
        assert set(schema["properties"]) == set(original["properties"])
        # Existing R13 opaque V1 objects are described explicitly for MCP;
        # geometry/evidence/top-level extension shapes remain unchanged.
        for key in set(schema["properties"]) - {"truck_access", "truck_maneuver"}:
            assert remove_descriptions(schema["properties"][key]) == remove_descriptions(
                original["properties"][key]
            )
        frozen = json.loads(
            (Path(__file__).parents[1] / "fixtures/v22/r14_frozen_seven_mcp_tools.json").read_text()
        )
        for current, old in zip(tools[:7], frozen, strict=True):
            assert {k: current[k] for k in ("name", "description", "inputSchema")} == {
                k: old[k] for k in ("name", "description", "inputSchema")
            }
        assert len(tools) == 8


def test_http_connector_auth_invalid_rpc_and_unknown_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET", "r14-synthetic-test-secret")
    with TestClient(create_app()) as client:
        for headers in ({}, {"X-Aily-Connector-Key": "incorrect"}):
            assert client.post(MCP_SSE_PATH, json=_TOOLS_LIST, headers=headers).status_code == 401
        good = {"X-Aily-Connector-Key": "r14-synthetic-test-secret"}
        assert client.post(MCP_SSE_PATH, json=_INITIALIZE, headers=good).status_code == 200
        unknown = client.post(
            MCP_SSE_PATH,
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "unknown_tool", "arguments": {}},
            },
            headers=good,
        )
        assert unknown.json()["result"]["isError"]
        bad = client.post(
            MCP_SSE_PATH, content=b"{", headers={**good, "content-type": "application/json"}
        )
        assert bad.status_code == 400 or "error" in bad.json()


def test_adapter_non_object_and_total_request_bound() -> None:
    assert not invoke_preview_truck_tool([])["ok"]
    r = invoke_preview_truck_tool({"padding": "A" * 12_000_001})
    assert r["error"]["code"] == "TRUCK_DOCUMENT_RESOURCE_LIMIT"


def test_invalid_rpc_argument_type_does_not_echo_file_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "BASE64_SYNTHETIC_FILE_CONTENT_MUST_NOT_BE_ECHOED"
    with TestClient(create_app()) as client:
        response = client.post(
            MCP_SSE_PATH,
            json={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "preview_truck", "arguments": [sentinel]},
            },
        )
        assert response.status_code >= 400 or "error" in response.json()
        assert sentinel not in response.text
        assert sentinel not in caplog.text
