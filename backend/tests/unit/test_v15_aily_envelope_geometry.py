"""V1.5 Aily cooling envelope flags, captions, and no-calculations import."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.aily.application.concept_preview import preview_concept
from cold_storage.modules.aily.application.stage_preview import preview_cooling_load

AILY_DIR = Path(__file__).resolve().parents[2] / "src" / "cold_storage" / "modules" / "aily"

_CAPTION_NEEDLE = "地板、墙、屋面来自分区几何（正方形平面 + 演示层高）"
_U_VALUE_NEEDLE = "U 值与设计温度仍为演示目录"


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


def test_v15_cooling_preview_envelope_from_plan_flags() -> None:
    result = preview_cooling_load(_five_keys())
    assert result["persisted"] is False
    assert result["requires_review"] is True
    assert result["floor_area_from_zone_plan"] is True
    assert result["envelope_wall_roof_from_plan"] is True
    assert result["formula_recut_authorized"] is True
    assert result["calculator_version"] == "1.0.0"
    assert _CAPTION_NEEDLE in result["table"]["caption"]
    assert _U_VALUE_NEEDLE in result["table"]["caption"]
    assert _CAPTION_NEEDLE in result["markdown_table"]
    assert float(result["summary"]["total_cooling_load_kw"]) > 0


def test_v15_concept_preview_envelope_flags_and_persisted_false() -> None:
    result = preview_concept(_five_keys())
    assert result["persisted"] is False
    assert result["floor_area_from_zone_plan"] is True
    assert result["envelope_wall_roof_from_plan"] is True
    assert result["formula_recut_authorized"] is True
    cooling = result["stages"]["cooling_load"]
    assert cooling["persisted"] is False
    assert cooling["envelope_wall_roof_from_plan"] is True
    assert _CAPTION_NEEDLE in cooling["markdown_table"]


def test_v15_two_inbound_masses_change_cooling_total() -> None:
    low = preview_cooling_load(_five_keys(daily_inbound_mass_kg=20000))
    high = preview_cooling_load(_five_keys(daily_inbound_mass_kg=40000))
    assert float(high["summary"]["total_cooling_load_kw"]) > float(
        low["summary"]["total_cooling_load_kw"]
    )


def test_v15_aily_does_not_import_calculations() -> None:
    for path in AILY_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
        assert "five_stage_execution" not in text, path.name
        assert "4 × √" not in text, path.name
        assert "room_height * 4" not in text, path.name
