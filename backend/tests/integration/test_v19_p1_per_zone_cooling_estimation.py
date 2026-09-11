"""Integration coverage for V1.9 P1 zone-planner-to-adapter lineage."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.calculations.domain.zone_planning import (
    HISTORICAL_FORMULA_AUTHORITY,
    ColdRoomZonePlanner,
)
from cold_storage.modules.orchestration.application.production_calculation import (
    adapters,
    persistence,
    projection,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    CalculatorInputProjection,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType


def _zone_projection() -> CalculatorInputProjection:
    return projection.project_calculator_input(
        calculation_type=CalculationType.ZONE,
        raw_inputs={
            "daily_inbound_mass_kg": 25_000.0,
            "working_time_h_per_day": 16.0,
            "finished_storage_days": 2.5,
            "packaging_storage_days": 3.0,
            "precooling_required_ratio": 1.0,
            "primary_precooling_working_hours_per_day": 6.0,
            "secondary_precooling_working_hours_per_day": 16.0,
            "packing_working_hours_per_day": 16.0,
        },
        actor="v19-p1-test",
        correlation_id="v19-p1-zone",
        database_backend="sqlite",
    )


def _zone_by_code(zones: list[dict[str, Any]], code: str) -> dict[str, Any]:
    return next(zone for zone in zones if zone.get("zone_code") == code)


def test_zone_planner_adapter_preserves_v19_fields_end_to_end() -> None:
    projection_value = _zone_projection()
    adapter_result = adapters.ZonePlanningAdapter(
        planner=ColdRoomZonePlanner(
            formula_authority=HISTORICAL_FORMULA_AUTHORITY,
            sorting_packaging_area_factor=1.0,
        )
    ).execute(projection_value)

    assert adapter_result.calculation_type is CalculationType.ZONE
    assert adapter_result.calculator_name == "cold_room_zone_plan"
    assert adapter_result.calculator_version == "1.0.0"
    assert adapter_result.calculator_success is True
    assert adapter_result.requires_review is True

    zones_value = adapter_result.payload["zones"]
    assert isinstance(zones_value, (list, tuple))
    zones = list(zones_value)
    refrigerated = {
        "primary_precooling_room",
        "secondary_precooling_room",
        "raw_fruit_buffer",
        "sorting_packaging_room",
        "coating_room",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "shipping_channel",
    }
    assert {
        zone["zone_code"] for zone in zones if zone["zone_code"] in refrigerated
    } == refrigerated
    for zone in zones:
        if zone["zone_code"] in refrigerated:
            assert "minimum_estimated_cooling_load_kw_r" in zone
            assert "cooling_estimation_basis" in zone
        else:
            assert "minimum_estimated_cooling_load_kw_r" not in zone
            assert "cooling_estimation_basis" not in zone

    primary = _zone_by_code(zones, "primary_precooling_room")
    assert primary["position_count"] == 24
    assert primary["minimum_estimated_cooling_load_kw_r"] == 480
    assert primary["cooling_estimation_basis"]["source_field"] == "position_count"

    draft = persistence.map_adapter_result_to_draft(
        adapter_result=adapter_result,
        actor=projection_value.actor,
        correlation_id=projection_value.correlation_id,
        database_backend=projection_value.database_backend,
    )
    draft_zones = draft.payload["zones"]
    assert isinstance(draft_zones, tuple)
    draft_primary = _zone_by_code(list(draft_zones), "primary_precooling_room")
    assert draft_primary["minimum_estimated_cooling_load_kw_r"] == 480
    assert "cooling_estimation_basis" in draft_primary
