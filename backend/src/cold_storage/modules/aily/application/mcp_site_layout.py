"""MCP boundary for the V2.2 site-layout preview tool."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.aily.application.site_layout_preview import (
    PREVIEW_SITE_LAYOUT_INPUT_FIELDS,
    PREVIEW_SITE_LAYOUT_TOOL_NAME,
    preview_site_layout,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError


def _layout_error_body(exc: LayoutAuthorityError) -> dict[str, Any]:
    details = {key: str(value) for key, value in exc.details.items()}
    raw_missing = exc.details.get("missing_fields", exc.details.get("missing_keys", ()))
    missing = (
        [str(value) for value in raw_missing] if isinstance(raw_missing, (list, tuple)) else []
    )
    return {
        "ok": False,
        "error": {
            "code": exc.code,
            "message": str(exc),
            "field_path": str(exc.details.get("field", "site_layout")),
            "missing_keys": missing,
            "ask_operator": str(exc.details.get("ask_operator", "")),
            "details": details,
        },
    }


def invoke_preview_site_layout_tool(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Invoke Tool 7 with the same JSON-ready error style as existing tools."""
    try:
        body = preview_site_layout(arguments)
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
    except LayoutAuthorityError as exc:
        return _layout_error_body(exc)
    return {"ok": True, **body}


__all__ = [
    "PREVIEW_SITE_LAYOUT_INPUT_FIELDS",
    "PREVIEW_SITE_LAYOUT_TOOL_NAME",
    "invoke_preview_site_layout_tool",
]
