"""Unit tests for V1.2/V1.3 Aily five-stage conversation preview."""

from __future__ import annotations

import pytest

from cold_storage.modules.aily.application.concept_preview import preview_concept
from cold_storage.modules.aily.application.stage_preview import (
    preview_cooling_load,
    preview_equipment,
    preview_installed_power,
    preview_investment,
    preview_zone_plan,
)
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


def test_v12_preview_zone_table_still_compatible() -> None:
    result = preview_zone_plan(_five_keys())
    assert result["reply_kind"] == "zone_plan_table"
    assert result["calculator_name"] == "cold_room_zone_plan"
    assert result["calculator_version"] == VERSION == "1.0.0"
    assert result["persisted"] is False
    assert result["requires_review"] is True


def test_v12_cooling_preview_demo_envelope_disclaimer() -> None:
    result = preview_cooling_load(_five_keys())
    assert result["reply_kind"] == "cooling_load_table"
    assert result["calculator_name"] == "cooling_load"
    assert result["calculator_version"] == "1.0.0"
    assert result["persisted"] is False
    assert result["requires_review"] is True
    assert result["floor_area_from_zone_plan"] is True
    assert result["envelope_wall_roof_from_plan"] is False
    assert result["formula_recut_authorized"] is False
    assert "演示" in result["table"]["caption"]
    assert "分区结果" in result["markdown_table"]
    assert float(result["summary"]["total_cooling_load_kw"]) > 0


def test_v12_equipment_and_power_previews() -> None:
    equipment = preview_equipment(_five_keys())
    assert equipment["reply_kind"] == "equipment_table"
    assert equipment["calculator_name"] == "equipment"
    assert equipment["persisted"] is False
    assert float(equipment["summary"]["compressor_operating_capacity_kw"]) > 0

    power = preview_installed_power(_five_keys())
    assert power["reply_kind"] == "power_table"
    assert power["calculator_name"] == "installed_power"
    assert float(power["summary"]["total_installed_power_kw_e"]) > 0
    assert power["power_from_demo_catalog"] is False
    assert float(power["summary"]["total_installed_power_kw_e"]) != 120.0


def test_v12_cooling_total_follows_zone_floor_area_lineage() -> None:
    cooling_low = preview_cooling_load(_five_keys(daily_inbound_mass_kg=20000))
    cooling_high = preview_cooling_load(_five_keys(daily_inbound_mass_kg=40000))
    zone_low = preview_zone_plan(_five_keys(daily_inbound_mass_kg=20000))
    zone_high = preview_zone_plan(_five_keys(daily_inbound_mass_kg=40000))
    low_total = float(cooling_low["summary"]["total_cooling_load_kw"])
    high_total = float(cooling_high["summary"]["total_cooling_load_kw"])
    assert low_total > 0
    assert high_total > low_total
    assert float(zone_high["summary"]["total_required_area_m2"]) > float(
        zone_low["summary"]["total_required_area_m2"]
    )
    assert cooling_low["floor_area_from_zone_plan"] is True


def test_v12_investment_preview() -> None:
    result = preview_investment(_five_keys())
    assert result["reply_kind"] == "investment_table"
    assert result["calculator_name"] == "investment_estimate"
    assert result["requires_review"] is True
    assert result["investment_from_demo_catalog"] is False
    assert result["floor_area_from_zone_plan"] is True
    assert result["envelope_wall_roof_from_plan"] is False
    assert result["table"]["rows"]
    assert float(result["summary"]["total_investment_cny"]) > 0


def test_v12_concept_preview_five_stages() -> None:
    result = preview_concept(_five_keys())
    assert result["reply_kind"] == "concept_preview"
    assert result["persisted"] is False
    assert result["requires_review"] is True
    assert result["floor_area_from_zone_plan"] is True
    assert result["envelope_wall_roof_from_plan"] is False
    assert result["formula_recut_authorized"] is False
    stages = result["stages"]
    for key in ("zone", "cooling_load", "equipment", "power", "investment"):
        assert key in stages
        assert stages[key]["persisted"] is False
    assert stages["cooling_load"]["floor_area_from_zone_plan"] is True
    assert float(stages["equipment"]["summary"]["compressor_operating_capacity_kw"]) > 0
    assert float(stages["power"]["summary"]["total_installed_power_kw_e"]) > 0
    assert stages["power"]["power_from_demo_catalog"] is False
    assert stages["investment"]["investment_from_demo_catalog"] is False


def test_v12_missing_key_fail_closed() -> None:
    payload = _five_keys()
    del payload["frozen_storage_days"]
    with pytest.raises(AilyConnectorError) as exc_info:
        preview_cooling_load(payload)
    assert exc_info.value.code == "MISSING_ENGINEERING_PARAMETER"


def test_v12_does_not_parse_chat_utterance() -> None:
    with pytest.raises(AilyConnectorError) as exc_info:
        preview_concept({"message": "要建一个20吨的加工厂"})
    assert exc_info.value.code == "MISSING_ENGINEERING_PARAMETER"
    assert len(exc_info.value.missing_keys) == 5
