"""MCP wrapper for the V2.1 factory-power preview capability."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.aily.application.factory_power_preview import (
    PREVIEW_FACTORY_POWER_INPUT_FIELDS,
    preview_factory_power,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError

PREVIEW_FACTORY_POWER_TOOL_NAME = "preview_factory_power"


def invoke_preview_factory_power_tool(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Run the factory-power preview and return a JSON-ready MCP payload."""
    try:
        body = preview_factory_power(arguments)
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


__all__ = [
    "PREVIEW_FACTORY_POWER_INPUT_FIELDS",
    "PREVIEW_FACTORY_POWER_TOOL_NAME",
    "invoke_preview_factory_power_tool",
]
