"""Unit coverage for the V2.1 factory-power MCP wrapper."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.aily.application.mcp_factory_power import (
    PREVIEW_FACTORY_POWER_INPUT_FIELDS,
    PREVIEW_FACTORY_POWER_TOOL_NAME,
    invoke_preview_factory_power_tool,
)

_FIVE_KEYS: dict[str, Any] = {
    "daily_inbound_mass_kg": 20000,
    "finished_storage_days": 7,
    "frozen_storage_days": 10,
    "main_packaging_storage_days": 4,
    "auxiliary_packaging_storage_days": 12,
}


def test_factory_power_mcp_wrapper_has_the_sixth_tool_identity() -> None:
    assert PREVIEW_FACTORY_POWER_TOOL_NAME == "preview_factory_power"
    assert tuple(PREVIEW_FACTORY_POWER_INPUT_FIELDS) == (
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
    )


def test_factory_power_mcp_wrapper_returns_success_body() -> None:
    body = invoke_preview_factory_power_tool(_FIVE_KEYS)

    assert body["ok"] is True
    assert body["reply_kind"] == "factory_power_estimation_table"
    assert body["calculator_identity"] == "factory_power_estimation@2.0.0-p1"
    assert body["persisted"] is False
    assert body["markdown_table"]


def test_factory_power_mcp_wrapper_returns_structured_schema_error() -> None:
    payload = dict(_FIVE_KEYS)
    payload["factory_area_m2"] = 9999

    body = invoke_preview_factory_power_tool(payload)

    assert body == {
        "ok": False,
        "error": {
            "code": "MCP_INPUT_SCHEMA_REJECTED",
            "message": "preview_factory_power does not accept unknown or area fields",
            "field_path": "arguments",
            "missing_keys": [],
            "ask_operator": "",
            "details": {"unexpected_keys": "factory_area_m2"},
        },
    }


def test_factory_power_mcp_wrapper_asks_only_for_missing_business_key() -> None:
    payload = dict(_FIVE_KEYS)
    payload.pop("auxiliary_packaging_storage_days")

    body = invoke_preview_factory_power_tool(payload)

    assert body["ok"] is False
    assert body["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"
    assert body["error"]["missing_keys"] == ["auxiliary_packaging_storage_days"]
    assert "辅包材存放天数" in body["error"]["ask_operator"]
    assert "factory_area_m2" not in body["error"]["ask_operator"]
