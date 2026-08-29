"""SSE MCP transport for 豆包工作伙伴 custom tools.

Thin ASGI: no engineering formulas, no chat parsing. Tools call
``invoke_preview_zone_plan_tool``. Optional ``X-Aily-Connector-Key`` is the
same gate as the REST connector. This is not production RBAC.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from mcp.types import CallToolResult, TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from cold_storage.bootstrap.settings import get_settings
from cold_storage.modules.aily.application.connector_auth import (
    CONNECTOR_KEY_HEADER,
    UNAUTHORIZED_CODE,
    verify_connector_key,
)
from cold_storage.modules.aily.application.mcp_zone_plan import (
    PREVIEW_ZONE_PLAN_TOOL_NAME,
    invoke_preview_zone_plan_tool,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

MCP_MOUNT_PATH = "/api/v1/aily/v1/mcp"
MCP_SSE_PATH = f"{MCP_MOUNT_PATH}/sse"
MCP_MESSAGES_PATH = f"{MCP_MOUNT_PATH}/messages/"

_TOOL_DESCRIPTION = (
    "根据五个过程参数生成冷库分区规划表。"
    "吨=每天。调用前把吨/天×1000得到 daily_inbound_mass_kg（kg/day）。"
    "只传五个 KEY，不要传聊天原文，不要自己算面积。"
    "成功时把 markdown_table 原样展示给用户，并说明这是概念设计、需要复核、不是施工图。"
    "失败时按 ask_operator 向用户追问，不要编造数字。"
)

_KEY_DESCRIPTIONS: dict[str, str] = {
    "daily_inbound_mass_kg": "每天进货质量，kg/day。用户说吨时先×1000。",
    "finished_storage_days": "成品储存天数。",
    "frozen_storage_days": "冻果储存天数。",
    "main_packaging_storage_days": "主包材储存天数。",
    "auxiliary_packaging_storage_days": "辅包材储存天数。",
}


def build_zone_plan_mcp_server() -> Server[Any, Any]:
    """Low-level MCP server exposing only ``preview_zone_plan``."""
    server: Server[Any, Any] = Server(
        name="cold-storage-zone-plan",
        version="1.1.0",
        instructions=_TOOL_DESCRIPTION,
    )

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        properties = {
            field_name: {
                "type": "number",
                "description": _KEY_DESCRIPTIONS[field_name],
            }
            for field_name in OPERATOR_V09_FIVE_KEY_FIELDS
        }
        return [
            Tool(
                name=PREVIEW_ZONE_PLAN_TOOL_NAME,
                description=_TOOL_DESCRIPTION,
                inputSchema={
                    "type": "object",
                    "properties": properties,
                    "required": list(OPERATOR_V09_FIVE_KEY_FIELDS),
                    "additionalProperties": False,
                },
            )
        ]

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        # Schema still lists required KEY for tools/list. Validation is the
        # application fail-closed path so 豆包 sees Chinese ask_operator.
        if name != PREVIEW_ZONE_PLAN_TOOL_NAME:
            payload = {
                "ok": False,
                "error": {
                    "code": "UNKNOWN_MCP_TOOL",
                    "message": f"unknown MCP tool: {name}",
                    "missing_keys": [],
                    "ask_operator": "",
                },
            }
            return CallToolResult(
                content=[TextContent(type="text", text=_dumps(payload))],
                structuredContent=payload,
                isError=True,
            )
        payload = invoke_preview_zone_plan_tool(arguments)
        return CallToolResult(
            content=[TextContent(type="text", text=_dumps(payload))],
            structuredContent=payload,
            isError=False,
        )

    return server


def build_aily_mcp_asgi() -> Starlette:
    """Starlette app: GET ``/sse``, POST ``/messages/``."""
    sse = SseServerTransport("/messages/")
    server = build_zone_plan_mcp_server()

    async def handle_sse(request: Request) -> Response:
        denied = _auth_response(request.headers.get(CONNECTOR_KEY_HEADER))
        if denied is not None:
            return denied
        send = request._send
        async with sse.connect_sse(request.scope, request.receive, send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
        return Response()

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Mount("/messages/", app=_ConnectorKeyASGI(sse.handle_post_message)),
        ]
    )


def mount_aily_mcp(app: FastAPI) -> None:
    """Mount the SSE MCP app on unmodified ``create_app``."""
    app.mount(MCP_MOUNT_PATH, build_aily_mcp_asgi())


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _error_body(exc: AilyConnectorError) -> dict[str, Any]:
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "field_path": exc.field_path,
            "missing_keys": list(exc.missing_keys),
            "ask_operator": exc.ask_operator,
            "details": dict(exc.details),
        }
    }


def _auth_response(header_value: str | None) -> JSONResponse | None:
    try:
        verify_connector_key(header_value, get_settings().aily_connector_shared_secret)
    except AilyConnectorError as exc:
        status = 401 if exc.code == UNAUTHORIZED_CODE else 400
        return JSONResponse(status_code=status, content=_error_body(exc))
    return None


def _header_value(scope: Scope, name: str) -> str | None:
    needle = name.lower().encode("latin-1")
    for key, value in scope.get("headers") or []:
        if key == needle:
            decoded: str = bytes(value).decode("latin-1")
            return decoded
    return None


class _ConnectorKeyASGI:
    """Apply the shared-secret header gate to the MCP messages ASGI app."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            denied = _auth_response(_header_value(scope, CONNECTOR_KEY_HEADER))
            if denied is not None:
                await denied(scope, receive, send)
                return
        await self._inner(scope, receive, send)
