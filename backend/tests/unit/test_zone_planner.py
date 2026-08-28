import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    FORMULA_AUTHORITY,
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
    assert result.calculator_version == "1.0.0"
    assert result.requires_review is True
    zones = result.result["zones"]

    assert [zone["zone_code"] for zone in zones] == [
        "office",
        "changing_room",
        "primary_precooling_room",
        "secondary_precooling_room",
        "raw_fruit_buffer",
        "sorting_packaging_room",
        "coating_room",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "packaging_material_storage",
        "shipping_channel",
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
        "1~3℃",
    ]

    primary = zones[2]
    secondary = zones[3]
    assert primary["daily_throughput_kg_day"] == 25_000
    assert secondary["daily_throughput_kg_day"] == 25_000
    assert primary["raw_position_count"] == 19
    assert primary["reporting_scheme_id"] == "6_position"
    assert primary["position_count"] == 24
    assert primary["position_daily_capacity_kg_day"] == 1320
    assert primary["required_area_m2"] == pytest.approx(168, abs=0.01)
    assert len(primary["schemes"]) == 2
    assert primary["schemes"][0]["scheme_id"] == "6_position"
    assert primary["schemes"][0]["required_area_m2"] == pytest.approx(168, abs=0.01)
    assert primary["schemes"][1]["scheme_id"] == "8_position"
    assert primary["schemes"][1]["required_area_m2"] == pytest.approx(168, abs=0.01)

    assert secondary["raw_position_count"] == 8
    assert secondary["position_count"] == 12
    assert secondary["position_daily_capacity_kg_day"] == 3200
    assert secondary["required_area_m2"] == pytest.approx(84, abs=0.01)

    assert zones[0]["required_area_m2"] == pytest.approx(80, abs=0.01)
    assert zones[1]["required_area_m2"] == pytest.approx(80, abs=0.01)

    raw = zones[4]
    assert raw["design_storage_mass_kg"] == 10_000
    assert raw["n_need"] == 46
    assert raw["n_long"] == 10
    assert raw["n_short"] == 5
    assert raw["position_count"] == 50
    assert raw["required_area_m2"] == pytest.approx(142.68, abs=0.01)
    assert "area_basis" not in raw

    sorting = zones[5]
    assert sorting["worker_count"] == 66
    assert sorting["table_count"] == 22
    assert sorting["position_count"] == 28
    assert sorting["required_area_m2"] == pytest.approx(690.56, abs=0.01)

    assert zones[6]["required_area_m2"] == pytest.approx(120, abs=0.01)

    finished = zones[7]
    assert finished["design_storage_mass_kg"] == 56_250
    assert finished["n_need"] == 141
    assert finished["position_count"] == 144
    assert finished["required_area_m2"] == pytest.approx(282.24, abs=0.01)

    secondary_fruit = zones[8]
    assert secondary_fruit["design_storage_mass_kg"] == 5_000
    assert secondary_fruit["secondary_fruit_ratio"] == 0.10
    assert secondary_fruit["secondary_fruit_storage_days"] == 2
    assert secondary_fruit["required_area_m2"] == pytest.approx(68.88, abs=0.01)

    frozen = zones[9]
    assert frozen["temperature_band"] == "-18℃"
    assert frozen["daily_throughput_kg_day"] == 2_500
    assert frozen["design_storage_mass_kg"] == 12_500
    assert frozen["position_count"] == 21
    assert frozen["required_area_m2"] == pytest.approx(57.96, abs=0.01)

    packaging = zones[10]
    assert packaging["position_count"] == 90
    assert packaging["required_area_m2"] == pytest.approx(322.92, abs=0.01)

    shipping = zones[11]
    assert shipping["pallet_count"] == 63
    assert shipping["truck_count"] == 4
    assert shipping["platform_count"] == 1
    assert shipping["position_count"] == 1
    assert shipping["required_area_m2"] == pytest.approx(50, abs=0.01)

    assert result.result["total_area_m2"] == pytest.approx(2147.24, abs=0.01)
    assert result.result["total_area_m2_8_position_scheme"] == pytest.approx(2119.24, abs=0.01)
    assert result.result["planning_parameters"]["main_packaging_storage_days"] == 3
    assert result.result["planning_parameters"]["auxiliary_packaging_storage_days"] == 30
    assert result.result["planning_parameters"]["formula_authority"] == FORMULA_AUTHORITY
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


def test_zone_planner_accepts_explicit_planning_assumption_overrides() -> None:
    """Non-default dataclass fields override §4 written-dead parameters when supplied."""

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
    assert zones[4]["n_need"] == 50
    assert zones[4]["position_count"] == 50
    assert zones[7]["position_count"] == 136
    assert zones[8]["design_storage_mass_kg"] == 5_000
    assert zones[9]["design_storage_mass_kg"] == 25_000
    assert zones[9]["position_count"] == 50
    assert zones[10]["position_count"] == 137
    assert result.result["planning_parameters"]["raw_storage_ratio"] == 0.5
    assert result.result["planning_parameters"]["main_packaging_storage_days"] == 7
    assert result.result["planning_parameters"]["secondary_fruit_ratio_hardcoded"] == 0.10
