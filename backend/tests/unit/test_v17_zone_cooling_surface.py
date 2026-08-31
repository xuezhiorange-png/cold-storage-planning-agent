"""V1.7 per-zone cooling component surface tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cold_storage.modules.aily.application.stage_preview import preview_cooling_load
from cold_storage.modules.orchestration.application.production_calculation.adapters import (
    CoolingLoadAdapter,
)
from cold_storage.modules.orchestration.application.source_snapshots import (
    CoolingLoadResultSnapshotV1,
    CoolingLoadZoneResultV1,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType
from tests.unit.test_production_calculation_adapters import (
    _cooling_load_inputs,
    _projection,
)

AILY_DIR = Path(__file__).resolve().parents[2] / "src" / "cold_storage" / "modules" / "aily"

_ZONE_COMPONENT_FIELDS = (
    "transmission_load_kw_r",
    "product_load_kw_r",
    "infiltration_load_kw_r",
    "internal_load_kw_r",
    "defrost_load_kw_r",
    "subtotal_load_kw_r",
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


def test_v17_adapter_keeps_kernel_zone_components() -> None:
    adapter = CoolingLoadAdapter()
    result = adapter.execute(_projection(CalculationType.COOLING_LOAD, _cooling_load_inputs()))
    zones = result.payload["zones"]
    assert zones
    first = zones[0]
    assert first["zone_code"] == "Z1"
    assert first.get("zone_name")
    for field_name in _ZONE_COMPONENT_FIELDS:
        assert field_name in first
        assert Decimal(str(first[field_name])) >= 0
    snap = CoolingLoadResultSnapshotV1(**result.payload)
    assert snap.zones is not None
    assert snap.zones[0].transmission_load_kw_r is not None
    assert snap.zones[0].subtotal_load_kw_r == first["subtotal_load_kw_r"]


def test_v17_historical_two_field_zone_snapshot_still_parses() -> None:
    zone = CoolingLoadZoneResultV1(zone_code="Z1", subtotal_load_kw_r="42.5")
    assert zone.transmission_load_kw_r is None
    assert zone.subtotal_load_kw_r == "42.5"


def test_v17_cooling_preview_zone_table_has_five_components() -> None:
    result = preview_cooling_load(_five_keys())
    assert result["calculator_version"] == "1.0.0"
    assert result["envelope_wall_roof_from_plan"] is True
    assert "分区冷量按内核五项加总" in result["table"]["caption"]
    assert "正方形平面 + 演示层高" in result["table"]["caption"]
    assert "U 值与设计温度仍为演示目录" in result["table"]["caption"]
    extras = result["extra_tables"]
    assert extras
    zone_table = extras[0]
    column_keys = [column["key"] for column in zone_table["columns"]]
    assert column_keys == [
        "zone_code",
        "zone_name",
        "temperature_level",
        "room_design_temperature",
        "room_height",
        "transmission_load_kw_r",
        "product_load_kw_r",
        "infiltration_load_kw_r",
        "internal_load_kw_r",
        "defrost_load_kw_r",
        "subtotal_load_kw_r",
    ]
    assert zone_table["rows"]
    first = zone_table["rows"][0]
    assert first["zone_code"]
    assert first["zone_name"]
    assert Decimal(str(first["subtotal_load_kw_r"])) > 0
    assert Decimal(str(first["transmission_load_kw_r"])) >= 0
    assert "传热负荷" in result["markdown_table"]
    assert "小计冷负荷" in result["markdown_table"]
    payload_zones = result.get("zones") or []
    if payload_zones:
        assert "transmission_load_kw_r" in payload_zones[0]


def test_v17_two_inbound_masses_change_zone_subtotals() -> None:
    low = preview_cooling_load(_five_keys(daily_inbound_mass_kg=20000))
    high = preview_cooling_load(_five_keys(daily_inbound_mass_kg=40000))
    low_rows = low["extra_tables"][0]["rows"]
    high_rows = high["extra_tables"][0]["rows"]
    assert len(low_rows) == len(high_rows)
    assert any(
        Decimal(str(high_row["subtotal_load_kw_r"])) > Decimal(str(low_row["subtotal_load_kw_r"]))
        for low_row, high_row in zip(low_rows, high_rows, strict=True)
    )


def test_v17_aily_does_not_import_calculations() -> None:
    for path in AILY_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
        assert "U × A × ΔT" not in text, path.name
