from __future__ import annotations

from decimal import Decimal

from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, normalize_polygon
from cold_storage.modules.layout.domain.structural_composition import FUNCTIONAL_GROUPS
from cold_storage.modules.layout.domain.structured_building import (
    CENTRAL_PROCESS_WITH_SIDE_BANKS,
    FINISHED_SIDE_BAND,
    LINEAR_3_BAND,
    LONGITUDINAL_PROCESS_SPINE,
    PERSONNEL_EDGE_BAND,
    PROCESS_CORE_BAND,
    RAW_SIDE_BAND,
    RECTANGLE,
    SIMPLE_L,
    SUPPORT_BAND,
    construct_structured_building_plan_v1,
    structured_layout_family_for_topology,
)


def _rectangle_boundary(width_m: int = 100, depth_m: int = 80) -> tuple[tuple[int, int], ...]:
    return normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": width_m, "y": 0},
                {"x": width_m, "y": depth_m},
                {"x": 0, "y": depth_m},
            ],
        }
    )


def _authorities() -> dict[str, dict[str, object]]:
    return {
        code: {
            "zone_code": code,
            "dimension_mode": "FIXED_RECTANGLE",
            "required_area_m2": 100,
            "geometry": {
                "width_m": 10,
                "depth_m": 10,
                "required_area_m2": 100,
            },
        }
        for members in FUNCTIONAL_GROUPS.values()
        for code in members
    }


def test_rectangle_envelope_and_three_main_bands_are_constructed_before_zones() -> None:
    plan = construct_structured_building_plan_v1(
        boundary=_rectangle_boundary(),
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
        envelope_family=RECTANGLE,
    )

    assert plan.envelope.family == RECTANGLE
    assert plan.envelope.bounds_mm == (0, 0, 100_000, 80_000)
    assert plan.zone_placements == ()
    assert {row.band_code for row in plan.bands} == {
        RAW_SIDE_BAND,
        PROCESS_CORE_BAND,
        FINISHED_SIDE_BAND,
        SUPPORT_BAND,
        PERSONNEL_EDGE_BAND,
    }
    assert plan.band_for_zone("raw_fruit_buffer").band_code == RAW_SIDE_BAND
    assert plan.band_for_zone("sorting_packaging_room").band_code == PROCESS_CORE_BAND
    assert plan.band_for_zone("shipping_channel").band_code == FINISHED_SIDE_BAND
    assert plan.band_for_zone("packaging_material_storage").band_code == SUPPORT_BAND
    assert plan.band_for_zone("office").band_code == PERSONNEL_EDGE_BAND
    assert plan.primary_grid.x_axes_mm == (0, 10_000, 20_000, 100_000)
    assert plan.primary_grid.y_axes_mm == (0, 10_000, 20_000, 30_000, 40_000, 80_000)
    assert plan.band_for_zone("sorting_packaging_room").bounds_mm != plan.envelope.bounds_mm


def test_zones_are_admitted_only_inside_their_planned_band_and_envelope() -> None:
    plan = construct_structured_building_plan_v1(
        boundary=_rectangle_boundary(),
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
    )
    sorting_band = plan.band_for_zone("sorting_packaging_room")
    valid = PlacedRectangleV1(
        "sorting_packaging_room",
        Decimal("1"),
        Decimal(sorting_band.bounds_mm[1]) / 1000,
        Decimal("10"),
        Decimal("10"),
    )
    outside_band = PlacedRectangleV1(
        "sorting_packaging_room", Decimal("1"), Decimal("60"), Decimal("10"), Decimal("10")
    )
    outside_envelope = PlacedRectangleV1(
        "sorting_packaging_room", Decimal("101"), Decimal("1"), Decimal("10"), Decimal("10")
    )

    assert plan.admits("sorting_packaging_room", valid)
    assert not plan.admits("sorting_packaging_room", outside_band)
    assert not plan.admits("sorting_packaging_room", outside_envelope)


def test_linear_process_band_contains_authoritative_rotated_coating_transition() -> None:
    authorities = _authorities()
    for code, width, depth in (
        ("raw_fruit_buffer", "15.2", "8.7"),
        ("primary_precooling_room", "14.7", "10.05"),
        ("sorting_packaging_room", "45.76", "13.6"),
        ("secondary_precooling_room", "9.8", "10.05"),
        ("coating_room", "5.264", "15.2"),
        ("finished_goods_room", "32.4", "18.6"),
        ("shipping_channel", "6.5", "7.693"),
    ):
        geometry = authorities[code]["geometry"]
        assert isinstance(geometry, dict)
        geometry["width_m"] = width
        geometry["depth_m"] = depth

    plan = construct_structured_building_plan_v1(
        boundary=_rectangle_boundary(),
        obstacles=(),
        authorities=authorities,
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
    )
    coating = PlacedRectangleV1(
        "coating_room", Decimal("14.7"), Decimal("28.436"), Decimal("5.264"), Decimal("15.2"), 90
    )

    assert plan.admits("coating_room", coating)


def test_completed_plan_records_band_assignment_and_shared_primary_axes() -> None:
    plan = construct_structured_building_plan_v1(
        boundary=_rectangle_boundary(),
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
    )
    placements: dict[str, PlacedRectangleV1] = {}
    for code in FUNCTIONAL_GROUPS["RAW_SIDE_GROUP"]:
        placements[code] = PlacedRectangleV1(code, Decimal("0"), Decimal("0"), 1, 1)
    for code in FUNCTIONAL_GROUPS["PROCESSING_CORE_GROUP"]:
        placements[code] = PlacedRectangleV1(code, Decimal("0"), Decimal("10"), 1, 1)
    for code in FUNCTIONAL_GROUPS["FINISHED_SIDE_GROUP"]:
        placements[code] = PlacedRectangleV1(code, Decimal("0"), Decimal("20"), 1, 1)
    for code in FUNCTIONAL_GROUPS["SUPPORT_GROUP"]:
        placements[code] = PlacedRectangleV1(code, Decimal("0"), Decimal("30"), 1, 1)
    for code in FUNCTIONAL_GROUPS["PERSONNEL_GROUP"]:
        placements[code] = PlacedRectangleV1(code, Decimal("0"), Decimal("40"), 1, 1)

    completed = plan.with_placements(placements)
    body = completed.to_dict()
    assert len(body["band_zone_placements"]) == 12
    assert body["primary_grid"]["grid_axis_usage"]
    assert all(row["aligned_primary_edge_count"] > 0 for row in body["band_zone_placements"])


def test_topology_lanes_map_to_distinct_band_arrangements_deterministically() -> None:
    assert structured_layout_family_for_topology("STRAIGHT_LINEAR_BAND") == LINEAR_3_BAND
    assert (
        structured_layout_family_for_topology("CENTRAL_PROCESS_HUB")
        == CENTRAL_PROCESS_WITH_SIDE_BANKS
    )
    assert structured_layout_family_for_topology("OFFSET_LINEAR_BAND") == LONGITUDINAL_PROCESS_SPINE
    first = construct_structured_building_plan_v1(
        boundary=_rectangle_boundary(),
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
    )
    second = construct_structured_building_plan_v1(
        boundary=_rectangle_boundary(),
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
    )
    assert first.to_dict() == second.to_dict()
    assert (
        first.band_for_zone("raw_fruit_buffer").bounds_mm[3]
        < (first.band_for_zone("finished_goods_room").bounds_mm[3])
    )


def test_simple_l_envelope_is_derived_from_orthogonal_site_geometry() -> None:
    l_boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 10, "y": 0},
                {"x": 10, "y": 4},
                {"x": 4, "y": 4},
                {"x": 4, "y": 10},
                {"x": 0, "y": 10},
            ],
        }
    )
    plan = construct_structured_building_plan_v1(
        boundary=l_boundary,
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
        envelope_family=SIMPLE_L,
    )

    assert plan.envelope.family == SIMPLE_L
    assert plan.envelope.components_mm == ((0, 0, 4000, 10000), (4000, 0, 10000, 4000))
