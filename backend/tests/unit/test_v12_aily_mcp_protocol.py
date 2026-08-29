"""In-memory MCP protocol tests for V1.2 five-stage preview tools."""

from __future__ import annotations

import json

import anyio
from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from cold_storage.modules.aily.api.mcp_sse import build_zone_plan_mcp_server
from cold_storage.modules.aily.application.mcp_stage_preview import (
    PREVIEW_COOLING_LOAD_TOOL_NAME,
    PREVIEW_EQUIPMENT_TOOL_NAME,
    PREVIEW_INSTALLED_POWER_TOOL_NAME,
    PREVIEW_INVESTMENT_TOOL_NAME,
)
from cold_storage.modules.aily.application.mcp_zone_plan import PREVIEW_ZONE_PLAN_TOOL_NAME
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

_FIVE_KEYS = {
    "daily_inbound_mass_kg": 20000,
    "finished_storage_days": 7,
    "frozen_storage_days": 10,
    "main_packaging_storage_days": 4,
    "auxiliary_packaging_storage_days": 12,
}

_EXPECTED_TOOL_ORDER = (
    PREVIEW_ZONE_PLAN_TOOL_NAME,
    PREVIEW_COOLING_LOAD_TOOL_NAME,
    "preview_equipment",
    "preview_installed_power",
    PREVIEW_INVESTMENT_TOOL_NAME,
)


def test_mcp_server_lists_five_preview_tools_zone_first() -> None:
    anyio.run(_list_tools)


def test_mcp_server_call_cooling_returns_demo_envelope_table() -> None:
    anyio.run(_call_cooling)


def test_mcp_server_call_equipment_returns_non_zero_capacity() -> None:
    anyio.run(_call_equipment)


def test_mcp_server_call_power_returns_non_zero_total() -> None:
    anyio.run(_call_power)


def test_mcp_server_call_investment_returns_table() -> None:
    anyio.run(_call_investment)


async def _list_tools() -> None:
    result = await _with_session(lambda session: session.list_tools())
    names = [tool.name for tool in result.tools]
    assert names == list(_EXPECTED_TOOL_ORDER)
    tool = result.tools[0]
    assert tool.name == PREVIEW_ZONE_PLAN_TOOL_NAME
    required = tool.inputSchema.get("required")
    assert required == list(OPERATOR_V09_FIVE_KEY_FIELDS)
    assert tool.inputSchema.get("additionalProperties") is False


async def _call_cooling() -> None:
    result = await _with_session(
        lambda session: session.call_tool(PREVIEW_COOLING_LOAD_TOOL_NAME, dict(_FIVE_KEYS))
    )
    assert result.structuredContent is not None
    body = result.structuredContent
    assert body["ok"] is True
    assert body["calculator_name"] == "cooling_load"
    assert body["floor_area_from_zone_plan"] is True
    assert body["envelope_wall_roof_from_plan"] is False
    assert "演示" in body["markdown_table"]


async def _call_equipment() -> None:
    result = await _with_session(
        lambda session: session.call_tool(PREVIEW_EQUIPMENT_TOOL_NAME, dict(_FIVE_KEYS))
    )
    assert result.structuredContent is not None
    body = result.structuredContent
    assert body["ok"] is True
    assert body["calculator_name"] == "equipment"
    assert float(body["summary"]["compressor_operating_capacity_kw"]) > 0


async def _call_power() -> None:
    result = await _with_session(
        lambda session: session.call_tool(PREVIEW_INSTALLED_POWER_TOOL_NAME, dict(_FIVE_KEYS))
    )
    assert result.structuredContent is not None
    body = result.structuredContent
    assert body["ok"] is True
    assert body["calculator_name"] == "installed_power"
    assert float(body["summary"]["total_installed_power_kw_e"]) > 0
    assert body["power_from_demo_catalog"] is False


async def _call_investment() -> None:
    result = await _with_session(
        lambda session: session.call_tool(PREVIEW_INVESTMENT_TOOL_NAME, dict(_FIVE_KEYS))
    )
    assert result.structuredContent is not None
    body = result.structuredContent
    assert body["ok"] is True
    assert body["calculator_name"] == "investment_estimate"
    assert body["requires_review"] is True
    assert float(body["summary"]["total_investment_cny"]) > 0
    parsed = json.loads(result.content[0].text)
    assert parsed["ok"] is True


async def _with_session(operation):  # type: ignore[no-untyped-def]
    server = build_zone_plan_mcp_server()
    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream[
        SessionMessage | Exception
    ](64)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream[
        SessionMessage
    ](64)
    result_box: list[object] = []

    async def _run_server() -> None:
        await server.run(
            client_to_server_recv,
            server_to_client_send,
            server.create_initialization_options(),
        )

    async with anyio.create_task_group() as tg:
        tg.start_soon(_run_server)
        async with ClientSession(server_to_client_recv, client_to_server_send) as session:
            await session.initialize()
            result_box.append(await operation(session))
        tg.cancel_scope.cancel()
    return result_box[0]
