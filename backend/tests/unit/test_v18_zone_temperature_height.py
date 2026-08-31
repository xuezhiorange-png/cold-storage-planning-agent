"""V1.8 per-zone cooling temperature and height catalog + surface tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cold_storage.modules.aily.application.stage_preview import preview_cooling_load
from cold_storage.modules.orchestration.application.production_calculation.adapters import (
    CoolingLoadAdapter,
)
from cold_storage.modules.orchestration.application.source_snapshots import (
    CoolingLoadResultSnapshotV1,
    CoolingLoadZoneResultV1,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType
from cold_storage.modules.projects.application.demo_zone_thermal_catalog import (
    BAND_COLD_END_C,
    ROOM_HEIGHT_M,
    room_design_temperature_c_for_band,
)
from cold_storage.modules.projects.application.operator_process_input import (
    REFRIGERATED_ZONE_REGISTRY,
    assemble_engineering_input_bundle,
)
from cold_storage.modules.projects.domain.models import ProjectVersion
from tests.unit.test_production_calculation_adapters import (
    _cooling_load_inputs,
    _projection,
)

AILY_DIR = Path(__file__).resolve().parents[2] / "src" / "cold_storage" / "modules" / "aily"


def _v09_operator_payload() -> dict[str, object]:
    return {
        "schema_id": "OperatorProcessInputV1",
        "schema_version": "1.1.0",
        "zone_planning_inputs": {
            "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
            "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
            "frozen_storage_days": {"value": "10", "unit": "day", "state": "provided"},
            "main_packaging_storage_days": {"value": "4", "unit": "day", "state": "provided"},
            "auxiliary_packaging_storage_days": {"value": "12", "unit": "day", "state": "provided"},
        },
    }


def _version() -> ProjectVersion:
    return ProjectVersion(
        project_id="p-v18",
        version_number=1,
        change_summary="v18-temp-height",
        id="pv-v18",
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


def test_v18_catalog_cold_end_and_height() -> None:
    assert room_design_temperature_c_for_band("8~10℃") == "8.0"
    assert room_design_temperature_c_for_band("1~3℃") == "1.0"
    assert room_design_temperature_c_for_band("-18℃") == "-18.0"
    assert ROOM_HEIGHT_M == "4.0"
    with pytest.raises(ValueError, match="no V18-T1"):
        room_design_temperature_c_for_band("常温")


def test_v18_assembler_stamps_band_cold_end_and_four_meter_height() -> None:
    bundle = assemble_engineering_input_bundle(
        operator_input=_v09_operator_payload(),
        project_id="p-v18",
        version=_version(),
        actor="test-actor",
    )
    by_code = {
        zone["_assembler_expected_zone_code"]: zone
        for zone in bundle["cooling_load_inputs"]["zones"]
    }
    assert len(by_code) == len(REFRIGERATED_ZONE_REGISTRY)
    for zone_code, _name, band in REFRIGERATED_ZONE_REGISTRY:
        zone = by_code[zone_code]
        expected_t = BAND_COLD_END_C[band]
        assert Decimal(str(zone["room_design_temperature"]["value"])) == Decimal(expected_t)
        assert Decimal(str(zone["product_target_temperature"]["value"])) == Decimal(expected_t)
        assert Decimal(str(zone["room_height"]["value"])) == Decimal(ROOM_HEIGHT_M)
        assert zone["room_design_temperature"]["source_type"] == "demo"
        assert zone["room_design_temperature"]["requires_review"] is True
        assert zone["room_height"]["source_path"].endswith("V18-H1")
        assert zone["room_design_temperature"]["source_path"].endswith("V18-T1")
        assert zone["product_mass_per_day"]["value"] in {"20000", "20000.0"}


def test_v18_adapter_echoes_kernel_temperature_and_height() -> None:
    adapter = CoolingLoadAdapter()
    result = adapter.execute(_projection(CalculationType.COOLING_LOAD, _cooling_load_inputs()))
    first = result.payload["zones"][0]
    assert first["room_design_temperature"] in {"-18", "-18.0"}
    assert first["room_height"] in {"5", "5.0"}
    snap = CoolingLoadResultSnapshotV1(**result.payload)
    assert snap.zones is not None
    assert snap.zones[0].room_design_temperature is not None
    assert snap.zones[0].room_height is not None


def test_v18_historical_zone_snapshot_without_temp_height_still_parses() -> None:
    zone = CoolingLoadZoneResultV1(zone_code="Z1", subtotal_load_kw_r="42.5")
    assert zone.room_design_temperature is None
    assert zone.room_height is None


def test_v18_cooling_preview_shows_temperature_and_height_columns() -> None:
    result = preview_cooling_load(_five_keys())
    assert result["calculator_version"] == "1.0.0"
    caption = result["table"]["caption"]
    assert "室内设计温度取分区规划温区低端" in caption
    assert "4.0 m" in caption
    assert "正方形平面 + 演示层高" in caption
    zone_table = result["extra_tables"][0]
    column_keys = [column["key"] for column in zone_table["columns"]]
    assert "room_design_temperature" in column_keys
    assert "room_height" in column_keys
    by_name = {row["zone_name"]: row for row in zone_table["rows"]}
    assert Decimal(str(by_name["一级预冷间"]["room_design_temperature"])) == Decimal("8")
    assert Decimal(str(by_name["成品间"]["room_design_temperature"])) == Decimal("1")
    assert Decimal(str(by_name["冻果间"]["room_design_temperature"])) == Decimal("-18")
    assert Decimal(str(by_name["一级预冷间"]["room_height"])) == Decimal("4")
    assert "室内设计温度" in result["markdown_table"]
    assert "层高" in result["markdown_table"]


def test_v18_unmapped_band_fails_closed() -> None:
    with pytest.raises(ValueError, match="no V18-T1"):
        room_design_temperature_c_for_band("99℃")
    registry_bands = {band for _code, _name, band in REFRIGERATED_ZONE_REGISTRY}
    assert registry_bands <= set(BAND_COLD_END_C)


def test_v18_aily_does_not_import_calculations_or_embed_formulas() -> None:
    for path in AILY_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
        assert "U × A × ΔT" not in text, path.name
        assert "U * A *" not in text, path.name
