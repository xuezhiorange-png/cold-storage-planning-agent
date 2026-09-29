from __future__ import annotations

from typing import Any

from tests.evaluation.envelope_grid_band_zone_generator import (
    MAIN_ZONES,
    _band_signature,
    _changed_zones,
    _is_micro_jitter,
)


def _candidate(*, shipping_y_mm: int = 33_700, move_finished_bank: bool = False) -> dict[str, Any]:
    positions = {
        "raw_fruit_buffer": (0, 0, 15_200, 8_700, 0),
        "primary_precooling_room": (15_200, 0, 14_700, 10_050, 0),
        "sorting_packaging_room": (15_200, 10_050, 45_760, 13_600, 0),
        "secondary_precooling_room": (15_200, 23_650, 9_800, 10_050, 0),
        "coating_room": (9_317, 20_100, 5_883, 13_600, 0),
        "finished_goods_room": (9_317, 33_700, 32_400, 18_600, 0),
        "shipping_channel": (1_624, shipping_y_mm, 6_500, 7_693, 0),
    }
    if move_finished_bank:
        for code in (
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        ):
            x, y, width, depth, rotation = positions[code]
            positions[code] = (x + 40_000, y, width, depth, rotation)
    return {
        "zones": [
            {
                "zone_code": code,
                "x": str(x / 1000),
                "y": str(y / 1000),
                "width_m": str(width / 1000),
                "depth_m": str(depth / 1000),
                "rotation_deg": rotation,
            }
            for code in MAIN_ZONES
            for x, y, width, depth, rotation in [positions[code]]
        ]
    }


def test_single_millimetre_shipping_shift_is_not_a_structured_candidate() -> None:
    baseline = _candidate()
    jitter = _candidate(shipping_y_mm=33_701)
    assert _changed_zones(baseline, jitter) == ("shipping_channel",)
    assert _is_micro_jitter(baseline, jitter)
    assert _band_signature(baseline) == _band_signature(jitter)


def test_changed_room_bank_changes_geometry_and_functional_band_relationships() -> None:
    baseline = _candidate()
    changed = _candidate(move_finished_bank=True)
    assert len(_changed_zones(baseline, changed)) >= 2
    assert _band_signature(baseline) != _band_signature(changed)
    assert not _is_micro_jitter(baseline, changed)
