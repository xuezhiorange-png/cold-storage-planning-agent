import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)


def test_zone_planner_converts_known_production_to_room_capacities_and_areas() -> None:
    planner = ColdRoomZonePlanner()

    result = planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=25_000,
            working_time_h_per_day=16,
            finished_storage_days=2.5,
            packaging_storage_days=3,
            precooling_required_ratio=1,
        )
    )

    assert result.success is True
    assert result.calculator_name == "cold_room_zone_plan"
    assert result.requires_review is True
    zones = result.result["zones"]

    assert [zone["zone_name"] for zone in zones] == [
        "办公室",
        "更衣室",
        "一级预冷间",
        "二级预冷间",
        "原果暂存间",
        "分选包装间",
        "覆膜间",
        "成品间",
        "次果暂存间",
        "冻果间",
        "包材库",
    ]
    assert [zone["temperature_band"] for zone in zones] == [
        "常温",
        "常温",
        "8~10℃",
        "1~3℃",
        "8~10℃",
        "8~10℃",
        "1~3℃",
        "1~3℃",
        "8~10℃",
        "-18℃",
        "常温",
    ]
    assert zones[2]["daily_throughput_kg_day"] == 25_000
    assert zones[3]["daily_throughput_kg_day"] == 25_000
    assert zones[2]["raw_position_count"] == 19
    assert zones[2]["position_count"] == 24
    assert zones[2]["position_daily_capacity_kg_day"] == 1320
    assert zones[2]["required_area_m2"] == pytest.approx(134.4, abs=0.01)
    assert zones[3]["raw_position_count"] == 8
    assert zones[3]["position_count"] == 8
    assert zones[3]["position_daily_capacity_kg_day"] == 3200
    assert zones[3]["required_area_m2"] == pytest.approx(44.8, abs=0.01)
    assert zones[4]["design_storage_mass_kg"] == 10_000
    assert zones[4]["position_count"] == 46
    assert zones[4]["required_area_m2"] == pytest.approx(86.11, abs=0.01)
    assert zones[5]["worker_count"] == 70
    assert zones[5]["table_count"] == 24
    assert zones[5]["required_area_m2"] == pytest.approx(693, abs=0.01)
    assert zones[6]["required_area_m2"] == pytest.approx(120, abs=0.01)
    assert zones[7]["design_storage_mass_kg"] == 62_500
    assert zones[7]["position_count"] == 157
    assert zones[7]["required_area_m2"] == pytest.approx(293.9, abs=0.01)
    assert zones[8]["required_area_m2"] == pytest.approx(31.45, abs=0.01)
    assert zones[9]["temperature_band"] == "-18℃"
    assert zones[9]["daily_throughput_kg_day"] == 2500
    assert zones[9]["design_storage_mass_kg"] == 12_500
    assert zones[9]["position_count"] == 21
    assert zones[9]["required_area_m2"] == pytest.approx(39.31, abs=0.01)
    assert zones[10]["position_count"] == 90
    assert zones[10]["required_area_m2"] == pytest.approx(210.6, abs=0.01)
    assert result.result["total_area_m2"] == pytest.approx(1813.57, abs=0.01)
    assert result.result["planning_parameters"]["main_packaging_storage_days"] == 3
    assert result.result["planning_parameters"]["auxiliary_packaging_storage_days"] == 30
    assert result.warnings[0].code == "DEMO_ASSUMPTIONS_REQUIRE_REVIEW"


def test_zone_planner_rejects_zero_production() -> None:
    planner = ColdRoomZonePlanner()

    result = planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=0,
            working_time_h_per_day=16,
            finished_storage_days=3,
            packaging_storage_days=7,
            precooling_required_ratio=0.8,
        )
    )

    assert result.success is False
    assert result.errors[0].details["field"] == "daily_inbound_mass_kg"


def test_zone_planner_accepts_explicit_planning_assumptions() -> None:
    planner = ColdRoomZonePlanner()

    result = planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=25_000,
            working_time_h_per_day=16,
            finished_storage_days=3,
            packaging_storage_days=7,
            precooling_required_ratio=0.8,
            primary_precooling_working_hours_per_day=5,
            secondary_precooling_pallet_weight_kg=500,
            secondary_precooling_hours_per_pallet=2,
            secondary_precooling_working_hours_per_day=10,
            raw_storage_ratio=0.5,
            raw_fruit_pallet_weight_kg=250,
            finished_goods_pallet_weight_kg=500,
            frozen_fruit_ratio=0.06,
            frozen_storage_days=10,
            frozen_goods_pallet_weight_kg=500,
            main_packaging_storage_days=7,
            auxiliary_packaging_storage_days=15,
        )
    )

    zones = result.result["zones"]

    assert zones[2]["raw_position_count"] == 23
    assert zones[2]["position_count"] == 24
    assert zones[3]["raw_position_count"] == 10
    assert zones[3]["position_count"] == 12
    assert zones[4]["design_storage_mass_kg"] == 12_500
    assert zones[4]["position_count"] == 50
    assert zones[7]["position_count"] == 150
    assert zones[9]["design_storage_mass_kg"] == 15_000
    assert zones[9]["position_count"] == 30
    assert zones[10]["position_count"] == 137
    assert result.result["planning_parameters"]["raw_storage_ratio"] == 0.5
    assert result.result["planning_parameters"]["main_packaging_storage_days"] == 7
