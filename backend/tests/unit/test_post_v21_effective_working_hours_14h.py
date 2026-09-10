"""Current POST-V2.1 regression tests for the 14 h/day zone-planning recut."""

from __future__ import annotations

import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    FORMULA_AUTHORITY,
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)


def _sample_input(**overrides: float) -> ColdRoomZonePlanInput:
    values: dict[str, float] = {
        "daily_inbound_mass_kg": 20_000,
        "working_time_h_per_day": 16,
        "finished_storage_days": 7,
        "packaging_storage_days": 3,
        "precooling_required_ratio": 1,
        "frozen_storage_days": 10,
        "main_packaging_storage_days": 4,
        "auxiliary_packaging_storage_days": 12,
    }
    values.update(overrides)
    return ColdRoomZonePlanInput(**values)


def test_post_v21_14h_defaults_match_current_20_t_day_sample() -> None:
    result = ColdRoomZonePlanner().plan(_sample_input())

    assert result.success is True
    assert result.result["planning_parameters"]["formula_authority"] == FORMULA_AUTHORITY
    assert FORMULA_AUTHORITY == "POST-V0.9-P4-charles-zone-area-recut"

    planning_parameters = result.result["planning_parameters"]
    zones = {zone["zone_code"]: zone for zone in result.result["zones"]}
    secondary = zones["secondary_precooling_room"]
    sorting = zones["sorting_packaging_room"]

    assert secondary["working_hours_per_day"] == 14
    assert secondary["position_daily_capacity_kg_day"] == 2800
    assert planning_parameters["secondary_precooling_q_d_kg_day"] == 2800
    assert secondary["required_area_m2"] == pytest.approx(84.00, abs=0.01)

    assert sorting["person_daily_capacity_kg_day"] == 336
    assert planning_parameters["packing_person_daily_capacity_kg"] == 336
    assert sorting["required_area_m2"] == pytest.approx(565.76, abs=0.01)
    assert result.result["total_area_m2"] == pytest.approx(2138.01, abs=0.01)


def test_post_v21_packing_capacity_uses_custom_packing_parameters() -> None:
    result = ColdRoomZonePlanner().plan(
        _sample_input(
            packing_pieces_per_person_hour=20,
            packing_weight_per_piece_kg=2,
            packing_working_hours_per_day=10,
        )
    )

    assert result.success is True
    sorting = next(
        zone for zone in result.result["zones"] if zone["zone_code"] == "sorting_packaging_room"
    )
    assert sorting["person_daily_capacity_kg_day"] == 400
    assert sorting["worker_count"] == 50
    assert sorting["table_count"] == 17
    assert result.result["planning_parameters"]["packing_person_daily_capacity_kg"] == 400
