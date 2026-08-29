"""MCP transport for 豆包工作伙伴 custom tools.

Feishu / 豆包工作伙伴 custom MCP is Streamable HTTP: POST JSON-RPC to
``/api/v1/aily/v1/mcp/sse`` (and ``/api/v1/aily/v1/mcp``) and return a complete
JSON body (``json_response=true`` / ``is_json_response_enabled=True``). It is
not a GET event stream.

GET ``/sse`` plus POST ``/messages/`` remain as optional legacy SSE. Do not
document that path as the Feishu 请求地址. trycloudflare buffers GET SSE into
HTTP 200 with an empty body.

Thin ASGI: no engineering formulas, no chat parsing. Tools call
``invoke_preview_zone_plan_tool``. Optional ``X-Aily-Connector-Key`` is the
same gate as the REST connector. This is not production RBAC.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anyio
from anyio.abc import TaskStatus
from fastapi import FastAPI
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import CallToolResult, TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import Message, Receive, Scope, Send

from cold_storage.bootstrap.settings import get_settings
from cold_storage.modules.aily.application.connector_auth import (
    CONNECTOR_KEY_HEADER,
    UNAUTHORIZED_CODE,
    verify_connector_key,
)
from cold_storage.modules.aily.application.mcp_stage_preview import (
    PREVIEW_COOLING_LOAD_TOOL_NAME,
    PREVIEW_EQUIPMENT_TOOL_NAME,
    PREVIEW_INSTALLED_POWER_TOOL_NAME,
    PREVIEW_INVESTMENT_TOOL_NAME,
    invoke_stage_preview_tool,
)
from cold_storage.modules.aily.application.mcp_zone_plan import (
    PREVIEW_ZONE_PLAN_TOOL_NAME,
    invoke_preview_zone_plan_tool,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

logger = logging.getLogger(__name__)

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

_COOLING_TOOL_DESCRIPTION = (
    "根据五个过程参数生成冷负荷预览表。"
    "地板/规划面积来自分区结果；墙、屋面、U 值仍用演示围护系数与演示目录，不是几何自动推导。"
    "吨=每天。只传五个 KEY。成功时原样展示 markdown_table，并说明概念设计、需复核、演示系数。"
    "失败时按 ask_operator 追问，不要编造数字。"
)

_EQUIPMENT_TOOL_DESCRIPTION = (
    "根据五个过程参数生成设备能力预览表。"
    "吨=每天。只传五个 KEY。成功时原样展示 markdown_table，并说明概念设计、需复核、演示系数。"
    "失败时按 ask_operator 追问，不要编造数字。"
)

_POWER_TOOL_DESCRIPTION = (
    "根据五个过程参数生成装机功率预览表。"
    "压缩机电气 kW(e) 来自设备结果；蒸发/冷凝风机可能仍为演示目录，不是 kW(r)/COP 换算。"
    "吨=每天。只传五个 KEY。成功时原样展示 markdown_table，并说明概念设计、需复核。"
    "失败时按 ask_operator 追问，不要编造数字。"
)

_INVESTMENT_TOOL_DESCRIPTION = (
    "根据五个过程参数生成投资估算预览表。"
    "面积与功率来自分区规划与装机功率结果，不是演示目录占位。"
    "吨=每天。只传五个 KEY。成功时原样展示 markdown_table，并说明概念设计、需复核、演示系数。"
    "失败时按 ask_operator 追问，不要编造数字。"
)

_STAGE_TOOL_DESCRIPTIONS: dict[str, str] = {
    PREVIEW_ZONE_PLAN_TOOL_NAME: _TOOL_DESCRIPTION,
    PREVIEW_COOLING_LOAD_TOOL_NAME: _COOLING_TOOL_DESCRIPTION,
    PREVIEW_EQUIPMENT_TOOL_NAME: _EQUIPMENT_TOOL_DESCRIPTION,
    PREVIEW_INSTALLED_POWER_TOOL_NAME: _POWER_TOOL_DESCRIPTION,
    PREVIEW_INVESTMENT_TOOL_NAME: _INVESTMENT_TOOL_DESCRIPTION,
}

_PREVIEW_TOOL_ORDER: tuple[str, ...] = (
    PREVIEW_ZONE_PLAN_TOOL_NAME,
    PREVIEW_COOLING_LOAD_TOOL_NAME,
    PREVIEW_EQUIPMENT_TOOL_NAME,
    PREVIEW_INSTALLED_POWER_TOOL_NAME,
    PREVIEW_INVESTMENT_TOOL_NAME,
)

_KEY_DESCRIPTIONS: dict[str, str] = {
    "daily_inbound_mass_kg": "每天进货质量，kg/day。用户说吨时先×1000。",
    "finished_storage_days": "成品储存天数。",
    "frozen_storage_days": "冻果储存天数。",
    "main_packaging_storage_days": "主包材储存天数。",
    "auxiliary_packaging_storage_days": "辅包材储存天数。",
}


def build_zone_plan_mcp_server() -> Server[Any, Any]:
    """Low-level MCP server exposing five-stage conversation preview tools."""
    server: Server[Any, Any] = Server(
        name="cold-storage-zone-plan",
        version="1.3.0",
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
        input_schema = {
            "type": "object",
            "properties": properties,
            "required": list(OPERATOR_V09_FIVE_KEY_FIELDS),
            "additionalProperties": False,
        }
        return [
            Tool(
                name=tool_name,
                description=_STAGE_TOOL_DESCRIPTIONS[tool_name],
                inputSchema=input_schema,
            )
            for tool_name in _PREVIEW_TOOL_ORDER
        ]

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        # Schema still lists required KEY for tools/list. Validation is the
        # application fail-closed path so 豆包 sees Chinese ask_operator.
        if name == PREVIEW_ZONE_PLAN_TOOL_NAME:
            payload = invoke_preview_zone_plan_tool(arguments)
        elif name in _STAGE_TOOL_DESCRIPTIONS and name != PREVIEW_ZONE_PLAN_TOOL_NAME:
            payload = invoke_stage_preview_tool(name, arguments)
        else:
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
        return CallToolResult(
            content=[TextContent(type="text", text=_dumps(payload))],
            structuredContent=payload,
            isError=False,
        )

    return server


def build_aily_mcp_asgi() -> Starlette:
    """Starlette app: Streamable HTTP POST on ``/sse`` and ``/``; legacy GET SSE."""
    sse = SseServerTransport("/messages/")
    server = build_zone_plan_mcp_server()

    async def handle_legacy_sse_get(request: Request) -> Response:
        denied = _auth_response(request.headers.get(CONNECTOR_KEY_HEADER))
        if denied is not None:
            return denied
        send = request._send
        async with sse.connect_sse(request.scope, request.receive, send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
        return Response()

    async def handle_streamable_http_post(request: Request) -> Response:
        denied = _auth_response(request.headers.get(CONNECTOR_KEY_HEADER))
        if denied is not None:
            return denied
        return await _stateless_json_mcp_response(server, request)

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_streamable_http_post, methods=["POST"]),
            Route("/", endpoint=handle_streamable_http_post, methods=["POST"]),
            Route("/sse", endpoint=handle_legacy_sse_get, methods=["GET"]),
            Mount("/messages/", app=_ConnectorKeyASGI(sse.handle_post_message)),
        ]
    )


def mount_aily_mcp(app: FastAPI) -> None:
    """Mount the Aily MCP app on unmodified ``create_app``."""
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


def _accept_includes_json(accept_header: str) -> bool:
    accept_types = [media_type.strip() for media_type in accept_header.split(",")]
    return any(media_type.startswith("application/json") for media_type in accept_types)


def _scope_with_json_accept(scope: Scope) -> Scope:
    """Feishu and curl send Content-Type only; MCP SDK 406s on missing/``*/*`` Accept."""
    accept = _header_value(scope, "accept") or ""
    if _accept_includes_json(accept):
        return scope
    patched = dict(scope)
    existing = scope.get("headers") or []
    headers = [(key, value) for key, value in existing if key.lower() != b"accept"]
    headers.append((b"accept", b"application/json"))
    patched["headers"] = headers
    return patched


async def _stateless_json_mcp_response(server: Server[Any, Any], request: Request) -> Response:
    scope = _scope_with_json_accept(request.scope)
    status_code = 500
    raw_headers: list[tuple[bytes, bytes]] = []
    body = bytearray()

    async def send(message: Message) -> None:
        nonlocal status_code, raw_headers
        if message["type"] == "http.response.start":
            status_code = int(message["status"])
            raw_headers = list(message.get("headers") or [])
        elif message["type"] == "http.response.body":
            chunk = message.get("body", b"") or b""
            if chunk:
                body.extend(chunk)

    await _run_stateless_json_mcp(server, scope, request.receive, send)
    header_map = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in raw_headers
        if key.lower() != b"content-length"
    }
    return Response(content=bytes(body), status_code=status_code, headers=header_map)


async def _run_stateless_json_mcp(
    server: Server[Any, Any],
    scope: Scope,
    receive: Receive,
    send: Send,
) -> None:
    # json_response=true: one complete JSON object per POST, not a long-lived SSE stream.
    http_transport = StreamableHTTPServerTransport(
        mcp_session_id=None,
        is_json_response_enabled=True,
        event_store=None,
        security_settings=None,
    )

    async def run_stateless_server(
        *,
        task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
    ) -> None:
        async with http_transport.connect() as streams:
            read_stream, write_stream = streams
            task_status.started()
            try:
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                    stateless=True,
                )
            except Exception:
                logger.exception("Aily MCP Streamable HTTP session crashed")

    async with anyio.create_task_group() as tg:
        await tg.start(run_stateless_server)
        try:
            await http_transport.handle_request(scope, receive, send)
        finally:
            await http_transport.terminate()
            tg.cancel_scope.cancel()


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
