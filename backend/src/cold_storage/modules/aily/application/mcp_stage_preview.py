"""MCP tool arguments for the four additional Aily stage previews."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.aily.application.stage_preview import (
    preview_cooling_load,
    preview_equipment,
    preview_installed_power,
    preview_investment,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError

PREVIEW_COOLING_LOAD_TOOL_NAME = "preview_cooling_load"
PREVIEW_EQUIPMENT_TOOL_NAME = "preview_equipment"
PREVIEW_INSTALLED_POWER_TOOL_NAME = "preview_installed_power"
PREVIEW_INVESTMENT_TOOL_NAME = "preview_investment"

_STAGE_TOOL_RUNNERS: dict[str, Any] = {
    PREVIEW_COOLING_LOAD_TOOL_NAME: preview_cooling_load,
    PREVIEW_EQUIPMENT_TOOL_NAME: preview_equipment,
    PREVIEW_INSTALLED_POWER_TOOL_NAME: preview_installed_power,
    PREVIEW_INVESTMENT_TOOL_NAME: preview_investment,
}


def invoke_stage_preview_tool(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Run a stage preview tool and return a JSON-ready MCP payload."""
    runner = _STAGE_TOOL_RUNNERS.get(name)
    if runner is None:
        return {
            "ok": False,
            "error": {
                "code": "UNKNOWN_MCP_TOOL",
                "message": f"unknown MCP tool: {name}",
                "missing_keys": [],
                "ask_operator": "",
            },
        }
    try:
        body = runner(arguments)
    except AilyConnectorError as exc:
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "field_path": exc.field_path,
                "missing_keys": list(exc.missing_keys),
                "ask_operator": exc.ask_operator,
                "details": dict(exc.details),
            },
        }
    return {"ok": True, **body}
