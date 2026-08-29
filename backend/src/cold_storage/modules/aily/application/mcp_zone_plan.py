"""MCP tool arguments for the Aily zone-plan preview.

豆包工作伙伴 custom tools speak MCP. This module maps tool arguments onto the
existing preview kernel. It does not parse chat, does not import the MCP SDK,
and does not compute engineering formulas.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.aily.application.zone_plan_preview import preview_zone_plan
from cold_storage.modules.aily.domain.errors import AilyConnectorError

PREVIEW_ZONE_PLAN_TOOL_NAME = "preview_zone_plan"


def invoke_preview_zone_plan_tool(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Run ``preview_zone_plan`` and return a JSON-ready MCP tool payload.

    Business failures (missing KEY, invalid input) are ``ok=False`` with
    ``ask_operator`` so 豆包 can question the user. Values are never guessed.
    """
    try:
        body = preview_zone_plan(arguments)
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
