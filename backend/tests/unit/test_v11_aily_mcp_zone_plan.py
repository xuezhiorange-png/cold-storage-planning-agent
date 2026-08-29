"""Unit tests for the Aily MCP zone-plan tool (no MCP SDK in this module)."""

from __future__ import annotations

from cold_storage.modules.aily.application.mcp_zone_plan import (
    PREVIEW_ZONE_PLAN_TOOL_NAME,
    invoke_preview_zone_plan_tool,
)


def _five_keys(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "daily_inbound_mass_kg": 20000,
        "finished_storage_days": 7,
        "frozen_storage_days": 10,
        "main_packaging_storage_days": 4,
        "auxiliary_packaging_storage_days": 12,
    }
    payload.update(overrides)
    return payload


def test_mcp_tool_name_is_preview_zone_plan() -> None:
    assert PREVIEW_ZONE_PLAN_TOOL_NAME == "preview_zone_plan"


def test_mcp_tool_returns_markdown_table_from_kernel() -> None:
    result = invoke_preview_zone_plan_tool(_five_keys())
    assert result["ok"] is True
    assert result["calculator_name"] == "cold_room_zone_plan"
    assert result["calculator_version"] == "1.0.0"
    assert result["persisted"] is False
    assert "面积" in result["markdown_table"]
    assert result["table"]["rows"]


def test_mcp_tool_fail_closed_on_missing_key() -> None:
    payload = _five_keys()
    del payload["frozen_storage_days"]
    result = invoke_preview_zone_plan_tool(payload)
    assert result["ok"] is False
    error = result["error"]
    assert error["code"] == "MISSING_ENGINEERING_PARAMETER"
    assert "frozen_storage_days" in error["missing_keys"]
    assert error["ask_operator"]


def test_mcp_tool_does_not_parse_chat_utterance() -> None:
    result = invoke_preview_zone_plan_tool({"message": "要建一个20吨的加工厂"})
    assert result["ok"] is False
    error = result["error"]
    assert error["code"] == "MISSING_ENGINEERING_PARAMETER"
    assert len(error["missing_keys"]) == 5
