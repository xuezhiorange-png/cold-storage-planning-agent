"""In-memory MCP protocol tests for the zone-plan tool (no HTTP)."""

from __future__ import annotations

import json

import anyio
from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from cold_storage.modules.aily.api.mcp_sse import build_zone_plan_mcp_server
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


def test_mcp_server_lists_only_preview_zone_plan() -> None:
    anyio.run(_list_tools)


def test_mcp_server_call_returns_markdown_table() -> None:
    anyio.run(_call_success)


def test_mcp_server_call_fail_closed_on_missing_key() -> None:
    anyio.run(_call_missing_key)


async def _list_tools() -> None:
    result = await _with_session(lambda session: session.list_tools())
    names = [tool.name for tool in result.tools]
    assert names == [PREVIEW_ZONE_PLAN_TOOL_NAME]
    tool = result.tools[0]
    required = tool.inputSchema.get("required")
    assert required == list(OPERATOR_V09_FIVE_KEY_FIELDS)
    assert "message" not in tool.inputSchema.get("properties", {})
    assert tool.inputSchema.get("additionalProperties") is False


async def _call_success() -> None:
    result = await _with_session(
        lambda session: session.call_tool(PREVIEW_ZONE_PLAN_TOOL_NAME, dict(_FIVE_KEYS))
    )
    assert result.structuredContent is not None
    body = result.structuredContent
    assert body["ok"] is True
    assert body["calculator_name"] == "cold_room_zone_plan"
    assert body["calculator_version"] == "1.0.0"
    assert "面积" in body["markdown_table"]
    text = result.content[0].text
    parsed = json.loads(text)
    assert parsed["ok"] is True


async def _call_missing_key() -> None:
    incomplete = dict(_FIVE_KEYS)
    del incomplete["frozen_storage_days"]
    result = await _with_session(
        lambda session: session.call_tool(PREVIEW_ZONE_PLAN_TOOL_NAME, incomplete)
    )
    assert result.structuredContent is not None
    body = result.structuredContent
    assert body["ok"] is False
    assert body["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"
    assert "frozen_storage_days" in body["error"]["missing_keys"]
    assert body["error"]["ask_operator"]


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
