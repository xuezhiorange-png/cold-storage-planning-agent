"""Unit tests for Aily / 豆包 zone-plan preview."""

from __future__ import annotations

import pytest

from cold_storage.modules.aily.application.operator_payload import (
    normalize_aily_operator_payload,
)
from cold_storage.modules.aily.application.zone_plan_preview import preview_zone_plan
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.calculations.domain.zone_planning import VERSION


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


def test_aily_normalizes_flat_five_keys() -> None:
    normalized = normalize_aily_operator_payload(_five_keys())
    assert normalized["schema_id"] == "OperatorProcessInputV1"
    assert normalized["schema_version"] == "1.1.0"
    zone = normalized["zone_planning_inputs"]
    assert zone["daily_inbound_mass_kg"]["unit"] == "kg/day"
    assert float(zone["frozen_storage_days"]["value"]) == 10.0


def test_aily_converts_ton_per_day_unit_explicitly() -> None:
    normalized = normalize_aily_operator_payload(
        _five_keys(daily_inbound_mass_kg={"value": 20, "unit": "t/day"})
    )
    assert float(normalized["zone_planning_inputs"]["daily_inbound_mass_kg"]["value"]) == 20000.0


def test_aily_spoken_tonne_unit_means_per_day() -> None:
    """Charles: 吨 always means per day; 豆包 may send unit 吨 after conversion."""
    normalized = normalize_aily_operator_payload(
        _five_keys(daily_inbound_mass_kg={"value": 20, "unit": "吨"})
    )
    assert float(normalized["zone_planning_inputs"]["daily_inbound_mass_kg"]["value"]) == 20000.0


def test_aily_does_not_parse_chat_utterance() -> None:
    """豆包 owns semantics. A chat example is not five KEY."""
    with pytest.raises(AilyConnectorError) as exc_info:
        normalize_aily_operator_payload({"message": "要建一个20吨的加工厂"})
    err = exc_info.value
    assert err.code == "MISSING_ENGINEERING_PARAMETER"
    assert err.missing_keys == (
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
    )
    assert "每天进货量" in err.ask_operator


def test_aily_missing_key_asks_in_chinese() -> None:
    payload = _five_keys()
    del payload["frozen_storage_days"]
    with pytest.raises(AilyConnectorError) as exc_info:
        normalize_aily_operator_payload(payload)
    err = exc_info.value
    assert err.code == "MISSING_ENGINEERING_PARAMETER"
    assert err.missing_keys == ("frozen_storage_days",)
    assert "冻果存放天数" in err.ask_operator


def test_aily_preview_returns_zone_table_from_kernel() -> None:
    result = preview_zone_plan(_five_keys())
    assert result["reply_kind"] == "zone_plan_table"
    assert result["calculator_name"] == "cold_room_zone_plan"
    assert result["calculator_version"] == VERSION == "1.0.0"
    assert result["persisted"] is False
    assert result["requires_review"] is True
    names = [row["zone_name"] for row in result["table"]["rows"]]
    assert "一级预冷间" in names
    assert "出货通道" in names
    assert "办公室" in names
    total = result["summary"]["total_required_area_m2"]
    assert float(total) > 0
    assert "一级预冷间" in result["markdown_table"]
    assert result["extra_tables"]
    assert "mark_reviewed" not in str(result)


def test_aily_preview_does_not_guess_missing_days() -> None:
    payload = _five_keys()
    del payload["finished_storage_days"]
    with pytest.raises(AilyConnectorError) as exc_info:
        preview_zone_plan(payload)
    assert exc_info.value.code == "MISSING_ENGINEERING_PARAMETER"
