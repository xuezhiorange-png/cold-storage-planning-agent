"""Tests for cold_storage.modules.planning.application.service orchestration."""

from __future__ import annotations

from pydantic import BaseModel

from cold_storage.modules.calculations.domain.zone_planning import ColdRoomZonePlanner
from cold_storage.modules.planning.application.service import (
    build_power_configuration,
    build_zone_plan_from_inputs,
    demo_inputs,
    inputs_from_planning_request,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


class FakeRequest(BaseModel):
    inputs: dict | None = None
    daily_inbound_mass_kg: float | None = None
    working_time_h_per_day: float | None = None
    utilization_factor: float | None = None
    storage_days: float | None = None
    finished_storage_days: float | None = None
    packaging_storage_days: float | None = None
    reserve_factor: float | None = None
    precooling_required_ratio: float | None = None
    raw_holding_hours: float | None = None
    storage_position_capacity_kg: float | None = None
    secondary_fruit_ratio: float | None = None
    frozen_fruit_ratio: float | None = None
    frozen_storage_days: float | None = None
    precooling_position_daily_capacity_kg: float | None = None
    primary_precooling_pallet_weight_kg: float | None = None
    primary_precooling_hours_per_pallet: float | None = None
    primary_precooling_working_hours_per_day: float | None = None
    secondary_precooling_pallet_weight_kg: float | None = None
    secondary_precooling_hours_per_pallet: float | None = None
    secondary_precooling_working_hours_per_day: float | None = None
    raw_storage_ratio: float | None = None
    raw_fruit_pallet_weight_kg: float | None = None
    finished_goods_pallet_weight_kg: float | None = None
    frozen_goods_pallet_weight_kg: float | None = None
    secondary_fruit_area_ratio: float | None = None
    main_packaging_storage_days: float | None = None
    auxiliary_packaging_storage_days: float | None = None
    packaging_area_factor: float | None = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildZonePlanFromInputs:
    """build_zone_plan_from_inputs should produce a valid zone plan."""

    def test_returns_success_with_zones(self):
        planner = ColdRoomZonePlanner()
        inputs = demo_inputs()
        result = build_zone_plan_from_inputs(inputs, planner)

        assert result.success is True
        assert "zones" in result.result
        assert isinstance(result.result["zones"], list)
        assert len(result.result["zones"]) > 0

    def test_total_area_matches_sum_of_zones(self):
        planner = ColdRoomZonePlanner()
        inputs = demo_inputs()
        result = build_zone_plan_from_inputs(inputs, planner)

        zones = result.result["zones"]
        total = sum(z["required_area_m2"] for z in zones)
        assert round(total, 2) == result.result["total_required_area_m2"]

    def test_zone_plan_requires_review(self):
        planner = ColdRoomZonePlanner()
        inputs = demo_inputs()
        result = build_zone_plan_from_inputs(inputs, planner)
        assert result.requires_review is True


class TestBuildPowerConfiguration:
    """build_power_configuration produces correct totals."""

    def test_total_power_is_positive(self):
        planner = ColdRoomZonePlanner()
        inputs = demo_inputs()
        zone_result = build_zone_plan_from_inputs(inputs, planner)
        zones = zone_result.result["zones"]

        power_config = build_power_configuration(zones, 25_000, 1000)

        assert power_config["total_installed_power_kw"] > 0
        assert power_config["requires_review"] is True

    def test_power_scales_with_throughput(self):
        planner = ColdRoomZonePlanner()
        inputs = demo_inputs()
        zone_result = build_zone_plan_from_inputs(inputs, planner)
        zones = zone_result.result["zones"]

        power_25t = build_power_configuration(zones, 25_000, 1000)
        power_50t = build_power_configuration(zones, 50_000, 2000)

        # At 50t/day the installed power should be higher than at 25t/day
        # because the scale factor is different
        assert power_50t["total_installed_power_kw"] >= power_25t["total_installed_power_kw"]

    def test_summary_rows_present(self):
        planner = ColdRoomZonePlanner()
        inputs = demo_inputs()
        zone_result = build_zone_plan_from_inputs(inputs, planner)
        zones = zone_result.result["zones"]

        power_config = build_power_configuration(zones, 25_000, 1000)

        assert "summary_rows" in power_config
        assert len(power_config["summary_rows"]) > 0
        # Should have a grand total row
        names = [r["name"] for r in power_config["summary_rows"]]
        assert any("total" in n or "total" in n.lower() or "合计" in n for n in names)


class TestInputsFromPlanningRequest:
    """inputs_from_planning_request merges flat fields and nested inputs."""

    def test_merges_flat_fields_into_fallback(self):
        fallback = {"daily_inbound_mass_kg": 10_000, "storage_days": 3}
        request = FakeRequest(daily_inbound_mass_kg=25_000)

        result = inputs_from_planning_request(request, fallback)

        assert result["daily_inbound_mass_kg"] == 25_000
        assert result["storage_days"] == 3

    def test_nested_inputs_override_fallback(self):
        fallback = {"daily_inbound_mass_kg": 10_000}
        request = FakeRequest(inputs={"daily_inbound_mass_kg": 50_000})

        result = inputs_from_planning_request(request, fallback)

        assert result["daily_inbound_mass_kg"] == 50_000

    def test_storage_days_maps_to_finished_storage_days(self):
        fallback = {"storage_days": 5}
        request = FakeRequest()

        result = inputs_from_planning_request(request, fallback)

        assert result["finished_storage_days"] == 5

    def test_packaging_storage_days_defaults_when_missing(self):
        fallback = {"daily_inbound_mass_kg": 10_000}
        request = FakeRequest()

        result = inputs_from_planning_request(request, fallback)

        assert result["packaging_storage_days"] == 3


class TestDemoInputs:
    """demo_inputs returns expected default values."""

    def test_returns_dict_with_required_keys(self):
        inputs = demo_inputs()
        assert "daily_inbound_mass_kg" in inputs
        assert "working_time_h_per_day" in inputs
        assert "utilization_factor" in inputs

    def test_default_throughput_is_25_tons(self):
        inputs = demo_inputs()
        assert inputs["daily_inbound_mass_kg"] == 25_000

    def test_default_working_hours(self):
        inputs = demo_inputs()
        assert inputs["working_time_h_per_day"] == 16

    def test_default_utilization(self):
        inputs = demo_inputs()
        assert inputs["utilization_factor"] == 0.85
