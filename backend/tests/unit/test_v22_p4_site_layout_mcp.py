"""Focused P4 Tool 7 orchestration, input-boundary, and determinism tests."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.aily.api.mcp_sse import MCP_SSE_PATH
from cold_storage.modules.aily.application import site_layout_preview
from cold_storage.modules.aily.application.mcp_site_layout import (
    invoke_preview_site_layout_tool,
)
from cold_storage.modules.aily.application.preview_bundle import (
    assemble_preview_context,
    json_ready,
)
from cold_storage.modules.aily.application.stage_preview import (
    execute_zone_preview_authority,
)
from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.p1_project_handoff import (
    build_p1_project_handoff,
)
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.placement import SitePlacementResultV1
from cold_storage.modules.layout.domain.truck_maneuver import (
    validate_truck_maneuver_project_binding,
)
from tests.unit.test_v22_p2b1_truck_maneuver_templates import p1f_input
from tests.unit.test_v22_p2d_access_routing import (
    _placement,
    _site_input,
    _truck_maneuver_payload,
)

_FIVE_KEYS: dict[str, Any] = {
    "daily_inbound_mass_kg": 20000,
    "finished_storage_days": 7,
    "frozen_storage_days": 10,
    "main_packaging_storage_days": 4,
    "auxiliary_packaging_storage_days": 12,
}


@pytest.fixture(scope="module")
def representative_authorities() -> dict[str, Any]:
    """Build one real P2D full-pass result for application-boundary tests."""
    context = assemble_preview_context(_FIVE_KEYS, correlation_id="p4-fixture")
    zone_plan = site_layout_preview._zone_plan_snapshot(execute_zone_preview_authority(context))
    p1f = p1f_input()
    handoff = build_p1_project_handoff(zone_plan, p1f)
    site = _site_input()
    geometry = validate_site_geometry(
        {"site_constraints": site, "truck_access": p1f},
        zone_plan,
        p1_handoff=handoff,
    )
    placement_base = _placement(zone_plan, handoff, geometry).to_dict()
    placement = SitePlacementResultV1.from_payload(
        {
            **placement_base,
            "placement_available": True,
            "status": "PLACEMENT_FOUND",
        }
    )
    binding = validate_truck_maneuver_project_binding(p1f, _truck_maneuver_payload())
    routed = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    routed_body = routed.to_dict()
    assert routed_body["project_layout_validated"] is True
    assert routed_body["p2_complete"] is True
    assert routed_body["access_pass_count"] == 12
    return {
        "site": site,
        "binding": binding,
        "placement": placement,
        "routed": routed,
    }


def _tool_payload(representative_authorities: dict[str, Any]) -> dict[str, Any]:
    return {
        **_FIVE_KEYS,
        "site_constraints": representative_authorities["site"],
        "truck_access": representative_authorities["binding"].to_dict(),
    }


def _wire_tool_payload(representative_authorities: dict[str, Any]) -> dict[str, Any]:
    payload = _tool_payload(representative_authorities)
    site = dict(payload["site_constraints"])
    site["main_entrance"] = {
        "start": {"x": 34.7, "y": 0},
        "end": {"x": 44.7, "y": 0},
    }
    payload["site_constraints"] = site
    return payload


def _patch_p2_pipeline(monkeypatch: pytest.MonkeyPatch, authorities: dict[str, Any]) -> None:
    monkeypatch.setattr(
        site_layout_preview,
        "place_zones",
        lambda *_args, **_kwargs: authorities["placement"],
    )
    monkeypatch.setattr(
        site_layout_preview,
        "route_site_placement",
        lambda *_args, **_kwargs: authorities["routed"],
    )


def _structured(response: Any) -> dict[str, Any]:
    result = response.json()["result"]
    structured = result.get("structuredContent")
    if structured is None:
        structured = json.loads(result["content"][0]["text"])
    assert isinstance(structured, dict)
    return structured


def _post_jsonrpc(client: TestClient, payload: dict[str, Any]):
    return client.post(
        MCP_SSE_PATH,
        content=json.dumps(json_ready(payload)),
        headers={"content-type": "application/json"},
    )


def test_tools_list_appends_site_layout_as_seventh_tool() -> None:
    client = TestClient(create_app())
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "p4-list-test", "version": "0.1"},
        },
    }
    assert _post_jsonrpc(client, initialize).status_code == 200
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
        "preview_site_layout",
    ]
    first_schema = tools[0]["inputSchema"]
    for tool in tools[:6]:
        assert tool["inputSchema"] == first_schema
    assert tuple(first_schema["required"]) == tuple(_FIVE_KEYS)
    site_schema = tools[6]["inputSchema"]
    assert tuple(site_schema["required"]) == (
        *_FIVE_KEYS,
        "site_constraints",
        "truck_access",
    )
    assert site_schema["additionalProperties"] is False
    assert "估算工厂电功率" not in tools[6]["description"]
    assert "概念平面图" in tools[6]["description"]


def test_tool7_valid_project_uses_p2d_and_p3_authorities(
    representative_authorities: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_p2_pipeline(monkeypatch, representative_authorities)
    body = invoke_preview_site_layout_tool(_tool_payload(representative_authorities))

    assert body["ok"] is True
    assert body["layout_identity"] == "site_validated_layout@1.0.0"
    assert body["drawing_identity"] == "validated-layout-svg-projection@1.0.0"
    assert body["project_layout_validated"] is True
    assert body["p2_complete"] is True
    assert body["layout"]["zone_count"] == 12
    assert body["layout"]["canonical_result_hash"].startswith("sha256:")
    assert body["drawing"]["canonical_result_hash"].startswith("sha256:")
    assert body["drawing"]["svg_sha256"].startswith("sha256:")
    assert body["drawing"]["svg"]
    assert body["requires_review"] is True
    assert body["concept_design"] is True
    assert body["persisted"] is False


def test_tool7_is_deterministic_for_same_structured_input(
    representative_authorities: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_p2_pipeline(monkeypatch, representative_authorities)
    payload = _tool_payload(representative_authorities)
    first = invoke_preview_site_layout_tool(payload)
    second = invoke_preview_site_layout_tool(payload)

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["layout"]["canonical_result_hash"] == second["layout"]["canonical_result_hash"]
    assert first["drawing"]["svg"] == second["drawing"]["svg"]
    assert first["drawing"]["svg_sha256"] == second["drawing"]["svg_sha256"]


def test_tool7_missing_business_key_reuses_existing_chinese_ask_operator() -> None:
    payload = {"daily_inbound_mass_kg": 20000}
    body = invoke_preview_site_layout_tool(payload)

    assert body["ok"] is False
    assert body["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"
    assert body["error"]["missing_keys"] == [
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
    ]
    assert body["error"]["ask_operator"]


def test_tool7_missing_site_constraints_does_not_create_default_site() -> None:
    body = invoke_preview_site_layout_tool(_FIVE_KEYS)

    assert body["ok"] is False
    assert body["error"]["code"] == "PROJECT_INPUT_REQUIRED"
    assert body["error"]["missing_keys"] == ["site_constraints"]
    assert "矩形" in body["error"]["message"] or "边界" in body["error"]["ask_operator"]


def test_tool7_missing_truck_access_does_not_create_default_vehicle() -> None:
    body = invoke_preview_site_layout_tool(
        {
            **_FIVE_KEYS,
            "site_constraints": _site_input(),
        }
    )

    assert body["ok"] is False
    assert body["error"]["code"] == "PROJECT_INPUT_REQUIRED"
    assert body["error"]["missing_keys"] == ["truck_access"]
    assert "默认" in body["error"]["ask_operator"]


@pytest.mark.parametrize(
    "field",
    [
        "factory_area_m2",
        "cold_storage_area_m2",
        "canonical_result_hash",
        "zone_plan",
        "layout",
        "svg",
        "chat_text",
        "fake_area",
    ],
)
def test_tool7_rejects_untrusted_authority_fields(
    field: str,
) -> None:
    payload = dict(_FIVE_KEYS)
    payload[field] = 1
    body = invoke_preview_site_layout_tool(payload)

    assert body["ok"] is False
    assert body["error"]["code"] == "MCP_INPUT_SCHEMA_REJECTED"
    assert body["error"]["missing_keys"] == []
    assert body["error"]["ask_operator"] == ""


def test_tool7_streamable_http_call_uses_existing_transport_and_auth_boundary(
    representative_authorities: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_p2_pipeline(monkeypatch, representative_authorities)
    client = TestClient(create_app())
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "p4-test", "version": "0.1"},
        },
    }
    assert _post_jsonrpc(client, initialize).status_code == 200
    response = _post_jsonrpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "preview_site_layout",
                "arguments": _wire_tool_payload(representative_authorities),
            },
        },
    )

    assert response.status_code == 200
    body = _structured(response)
    assert body["ok"] is True
    assert body["layout_identity"] == "site_validated_layout@1.0.0"
    assert body["drawing"]["svg"]
    layout = dict(body["layout"])
    layout_hash = layout.pop("canonical_result_hash")
    assert canonical_hash(layout) == layout_hash
