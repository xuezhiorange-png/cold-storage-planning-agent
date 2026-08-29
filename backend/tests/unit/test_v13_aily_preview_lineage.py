"""V1.3 Aily preview lineage behavior tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from cold_storage.modules.aily.application.stage_preview import (
    preview_cooling_load,
    preview_equipment,
    preview_installed_power,
    preview_investment,
    preview_zone_plan,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.orchestration.application.production_calculation.electrical_capturing_equipment_adapter import (
    ElectricalCapturingEquipmentAdapter,
)

AILY_DIR = Path(__file__).resolve().parents[2] / "src" / "cold_storage" / "modules" / "aily"


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


def test_v13_cooling_floor_area_from_zone_changes_with_inbound_mass() -> None:
    low = preview_cooling_load(_five_keys(daily_inbound_mass_kg=20000))
    high = preview_cooling_load(_five_keys(daily_inbound_mass_kg=40000))
    assert low["floor_area_from_zone_plan"] is True
    assert low["envelope_wall_roof_from_plan"] is False
    assert float(high["summary"]["total_cooling_load_kw"]) > float(
        low["summary"]["total_cooling_load_kw"]
    )
    assert "演示" in low["table"]["caption"]


def test_v13_two_key_sets_produce_different_cooling_totals() -> None:
    first = preview_cooling_load(_five_keys(daily_inbound_mass_kg=15000))
    second = preview_cooling_load(_five_keys(daily_inbound_mass_kg=35000))
    assert float(first["summary"]["total_cooling_load_kw"]) != float(
        second["summary"]["total_cooling_load_kw"]
    )


def test_v13_power_compressor_from_equipment_not_demo_catalog() -> None:
    equipment = preview_equipment(_five_keys())
    power = preview_installed_power(_five_keys())
    assert float(equipment["summary"]["compressor_operating_capacity_kw"]) > 0
    assert float(power["summary"]["total_installed_power_kw_e"]) > 0
    assert power["power_from_demo_catalog"] is False
    assert float(power["summary"]["total_installed_power_kw_e"]) != 120.0


def test_v13_investment_from_zone_and_power_not_demo_catalog() -> None:
    zone = preview_zone_plan(_five_keys())
    power = preview_installed_power(_five_keys())
    investment = preview_investment(_five_keys())
    assert investment["investment_from_demo_catalog"] is False
    assert float(investment["summary"]["total_investment_cny"]) > 0
    assert float(zone["summary"]["total_required_area_m2"]) > 0
    assert float(power["summary"]["total_installed_power_kw_e"]) > 0


def test_v13_missing_key_fail_closed() -> None:
    payload = _five_keys()
    del payload["main_packaging_storage_days"]
    with pytest.raises(AilyConnectorError) as exc_info:
        preview_investment(payload)
    assert exc_info.value.code == "MISSING_ENGINEERING_PARAMETER"


def test_v13_aily_does_not_import_calculations() -> None:
    for path in AILY_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name


def test_v13_equipment_and_power_totals_non_zero() -> None:
    equipment = preview_equipment(_five_keys())
    power = preview_installed_power(_five_keys())
    assert float(equipment["summary"]["compressor_operating_capacity_kw"]) > 0
    assert float(power["summary"]["total_installed_power_kw_e"]) > 0
    assert isinstance(ElectricalCapturingEquipmentAdapter(), ElectricalCapturingEquipmentAdapter)
