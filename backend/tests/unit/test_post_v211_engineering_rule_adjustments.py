"""Current POST-v2.1.1 engineering-rule adjustment regressions."""

from __future__ import annotations

from decimal import Decimal

from cold_storage.modules.calculations.domain.factory_power_estimation import (
    DEFROST_SIMULTANEOUS_USE_FACTOR,
    POOL_A_SIMULTANEITY_FACTOR,
)
from cold_storage.modules.calculations.domain.zone_planning import (
    FORMULA_AUTHORITY,
    PRIMARY_PRECOOL_BATCHES_PER_DAY,
    SORTING_PACKAGING_AREA_FACTOR,
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.orchestration.application.source_snapshots import (
    ZoneResultSnapshotV1,
)
from cold_storage.modules.planning.application.service import build_power_configuration


def _current_sample_input(**overrides: float) -> ColdRoomZonePlanInput:
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


def test_post_v211_current_rules_are_applied_without_recutting_layout_counts() -> None:
    result = ColdRoomZonePlanner().plan(_current_sample_input())

    assert result.success is True
    assert result.result["planning_parameters"]["formula_authority"] == FORMULA_AUTHORITY
    assert FORMULA_AUTHORITY == "POST-V2.1.1-charles-engineering-rule-adjustments"

    zones = {zone["zone_code"]: zone for zone in result.result["zones"]}
    primary = zones["primary_precooling_room"]
    secondary = zones["secondary_precooling_room"]
    sorting = zones["sorting_packaging_room"]

    assert PRIMARY_PRECOOL_BATCHES_PER_DAY == 7
    assert primary["working_hours_per_day"] == 7
    assert primary["position_daily_capacity_kg_day"] == 1540
    assert primary["raw_position_count"] == 13
    assert primary["required_area_m2"] == 126

    assert secondary["working_hours_per_day"] == 14
    assert secondary["position_daily_capacity_kg_day"] == 2800
    assert secondary["required_area_m2"] == 84

    assert sorting["person_daily_capacity_kg_day"] == 336
    assert sorting["n_need"] == 20
    assert sorting["worker_count"] == 60
    assert sorting["table_count"] == 20
    assert sorting["n_long"] == 7
    assert sorting["n_short"] == 3
    assert sorting["raw_required_area_m2"] == 565.76
    assert sorting["sorting_packaging_area_factor"] == SORTING_PACKAGING_AREA_FACTOR
    assert sorting["required_area_m2"] == 622.34
    assert result.result["total_area_m2"] == 2194.59


def test_post_v211_custom_packing_inputs_still_drive_capacity_and_layout() -> None:
    result = ColdRoomZonePlanner().plan(
        _current_sample_input(
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
    assert sorting["n_need"] == 17
    assert sorting["n_long"] == 6
    assert sorting["n_short"] == 3
    assert sorting["raw_required_area_m2"] == 489.60
    assert sorting["required_area_m2"] == 538.56


def test_post_v211_zone_snapshot_schema_accepts_current_sorting_area_fields() -> None:
    result = ColdRoomZonePlanner().plan(_current_sample_input())

    assert result.success is True
    snapshot = ZoneResultSnapshotV1.model_validate(result.result)
    sorting = next(zone for zone in snapshot.zones if zone.zone_code == "sorting_packaging_room")

    assert sorting.raw_required_area_m2 == "565.76"
    assert sorting.sorting_packaging_area_factor == "1.1"
    assert sorting.required_area_m2 == "622.34"


def test_post_v211_defrost_factor_is_shared_by_legacy_power_projection() -> None:
    power = build_power_configuration([], 25_000, 0)

    defrost_installed = sum(row["defrost_total_power_kw"] or 0 for row in power["equipment_rows"])
    assert defrost_installed == 830.3
    assert Decimal("0.20") == DEFROST_SIMULTANEOUS_USE_FACTOR
    assert POOL_A_SIMULTANEITY_FACTOR == DEFROST_SIMULTANEOUS_USE_FACTOR
    assert power["summary_rows"][0] == {
        "name": "化霜总功率",
        "basis": "按20% 同时化霜",
        "total_power_kw": 166.06,
    }
    assert power["summary_rows"][2]["basis"] == "化霜同时系数20% + 设备运行同时系数90%"
