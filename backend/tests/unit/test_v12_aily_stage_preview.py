"""Unit tests for V1.2 Aily five-stage conversation preview."""

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
    assert result["envelope_from_zone_area"] is False
    assert result["formula_recut_authorized"] is False
    assert "演示围护" in result["table"]["caption"]
    assert "演示围护" in result["markdown_table"]
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
    assert power["power_from_demo_catalog"] is True
    assert "演示目录" in power["table"]["caption"]
    assert "演示目录" in power["markdown_table"]


def test_v12_cooling_and_zone_area_are_independent() -> None:
    cooling = preview_cooling_load(_five_keys())
    zone = preview_zone_plan(_five_keys())
    cooling_total = float(cooling["summary"]["total_cooling_load_kw"])
    zone_total_area = float(zone["summary"]["total_required_area_m2"])
    assert cooling_total > 0
    assert zone_total_area > 0
    assert cooling["envelope_from_zone_area"] is False
    assert "演示围护" in cooling["table"]["caption"]
    # Demo envelope cooling must not be tied to zone-planner area totals.
    assert abs(cooling_total - zone_total_area) > 1.0


def test_v12_investment_preview() -> None:
    result = preview_investment(_five_keys())
    assert result["reply_kind"] == "investment_table"
    assert result["calculator_name"] == "investment_estimate"
    assert result["requires_review"] is True
    assert result["investment_from_demo_catalog"] is True
    assert result["envelope_from_zone_area"] is False
    assert result["table"]["rows"]
    assert float(result["summary"]["total_investment_cny"]) > 0


def test_v12_concept_preview_five_stages() -> None:
    result = preview_concept(_five_keys())
    assert result["reply_kind"] == "concept_preview"
    assert result["persisted"] is False
    assert result["requires_review"] is True
    assert result["envelope_from_zone_area"] is False
    assert result["formula_recut_authorized"] is False
    stages = result["stages"]
    for key in ("zone", "cooling_load", "equipment", "power", "investment"):
        assert key in stages
        assert stages[key]["persisted"] is False
    assert stages["cooling_load"]["envelope_from_zone_area"] is False
    assert float(stages["equipment"]["summary"]["compressor_operating_capacity_kw"]) > 0
    assert float(stages["power"]["summary"]["total_installed_power_kw_e"]) > 0
    assert stages["power"]["power_from_demo_catalog"] is True
    assert stages["investment"]["investment_from_demo_catalog"] is True


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
