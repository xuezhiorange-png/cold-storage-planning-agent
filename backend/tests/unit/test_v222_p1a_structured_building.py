from __future__ import annotations

from decimal import Decimal

import pytest

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, normalize_polygon
from cold_storage.modules.layout.domain.structural_composition import FUNCTIONAL_GROUPS
from cold_storage.modules.layout.domain.structured_building import (
    BASE_LAYOUT_FAMILIES,
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
    BuildingEnvelopeV1,
    construct_structured_building_plan_v1,
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
    assert plan.envelope.site_bounds_mm == (0, 0, 100_000, 80_000)
    assert plan.envelope.bounds_mm != plan.envelope.site_bounds_mm
    x0, y0, x1, y1 = plan.envelope.bounds_mm
    required_program_area_mm2 = sum(
        int(authority["required_area_m2"]) * 1_000_000 for authority in _authorities().values()
    )
    assert (x1 - x0) * (y1 - y0) >= required_program_area_mm2
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
    assert plan.primary_grid.x_axes_mm[0] == x0
    assert plan.primary_grid.x_axes_mm[-1] == x1
    assert plan.primary_grid.y_axes_mm[0] == y0
    assert plan.primary_grid.y_axes_mm[-1] == y1
    assert len(plan.primary_grid.x_axes_mm) < len(plan.primary_grid.event_x_mm)
    assert len(plan.primary_grid.y_axes_mm) < len(plan.primary_grid.event_y_mm)
    assert plan.band_for_zone("packaging_material_storage").bounds_mm != plan.envelope.bounds_mm
    assert plan.band_for_zone("office").bounds_mm != plan.envelope.bounds_mm
    assert plan.band_for_zone("sorting_packaging_room").bounds_mm != plan.envelope.bounds_mm
    support = plan.band_for_zone("packaging_material_storage").bounds_mm
    personnel = plan.band_for_zone("office").bounds_mm
    raw = plan.band_for_zone("raw_fruit_buffer").bounds_mm
    process = plan.band_for_zone("sorting_packaging_room").bounds_mm
    finished = plan.band_for_zone("shipping_channel").bounds_mm
    finished_band = next(band for band in plan.bands if band.band_code == FINISHED_SIDE_BAND)
    envelope = plan.envelope.bounds_mm
    if plan.support_side == "EAST":
        assert support[2] == envelope[2]
    elif plan.support_side == "WEST":
        assert support[0] == envelope[0]
    elif plan.support_side == "NORTH":
        assert support[3] == envelope[3]
    else:
        assert support[1] == envelope[1]
    if plan.personnel_side == "EAST":
        assert personnel[2] == envelope[2]
    elif plan.personnel_side == "WEST":
        assert personnel[0] == envelope[0]
    elif plan.personnel_side == "NORTH":
        assert personnel[3] == envelope[3]
    else:
        assert personnel[1] == envelope[1]
    assert raw[3] == process[1]
    assert process[3] == finished[1]
    assert "coating_room" in finished_band.transition_zone_codes


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
        Decimal(sorting_band.bounds_mm[0]) / 1000,
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
        "coating_room",
        Decimal(plan.band_for_zone("coating_room").bounds_mm[0]) / 1000,
        Decimal(plan.band_for_zone("coating_room").bounds_mm[1]) / 1000,
        Decimal("5.264"),
        Decimal("15.2"),
        90,
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
    for band_code, members in (
        (RAW_SIDE_BAND, FUNCTIONAL_GROUPS["RAW_SIDE_GROUP"]),
        (PROCESS_CORE_BAND, FUNCTIONAL_GROUPS["PROCESSING_CORE_GROUP"]),
        (FINISHED_SIDE_BAND, FUNCTIONAL_GROUPS["FINISHED_SIDE_GROUP"]),
        (SUPPORT_BAND, FUNCTIONAL_GROUPS["SUPPORT_GROUP"]),
        (PERSONNEL_EDGE_BAND, FUNCTIONAL_GROUPS["PERSONNEL_GROUP"]),
    ):
        band = next(row for row in plan.bands if row.band_code == band_code)
        x0, y0, _x1, _y1 = band.bounds_mm
        for code in members:
            placements[code] = PlacedRectangleV1(
                code, Decimal(x0) / 1000, Decimal(y0) / 1000, Decimal("1"), Decimal("1")
            )

    completed = plan.with_placements(placements)
    body = completed.to_dict()
    assert len(body["band_zone_placements"]) == 12
    assert body["primary_grid"]["grid_axis_usage"]
    assert all(
        row["aligned_primary_edge_count"] > 0
        for row in body["band_zone_placements"]
        if row["band_code"] in {RAW_SIDE_BAND, PROCESS_CORE_BAND, FINISHED_SIDE_BAND}
    )
    assert body["primary_grid"]["single_use_primary_axis_count"] == 0


def test_layout_families_are_first_class_and_construct_independently() -> None:
    assert BASE_LAYOUT_FAMILIES == (
        LINEAR_3_BAND,
        CENTRAL_PROCESS_WITH_SIDE_BANKS,
        LONGITUDINAL_PROCESS_SPINE,
    )
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
    family_plans = {
        family: construct_structured_building_plan_v1(
            boundary=_rectangle_boundary(),
            obstacles=(),
            authorities=_authorities(),
            process_axis="Y",
            layout_family=family,
        )
        for family in BASE_LAYOUT_FAMILIES
    }
    assert set(family_plans) == set(BASE_LAYOUT_FAMILIES)
    assert len(
        {
            tuple(
                row.bounds_mm
                for row in plan.bands
                if row.band_code
                in {
                    RAW_SIDE_BAND,
                    PROCESS_CORE_BAND,
                    FINISHED_SIDE_BAND,
                }
            )
            for plan in family_plans.values()
        }
    ) == len(BASE_LAYOUT_FAMILIES)
    assert len({plan.envelope.bounds_mm for plan in family_plans.values()}) >= 2
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
    with pytest.raises(LayoutAuthorityError, match="SIMPLE_L_ENVELOPE_UNAVAILABLE"):
        construct_structured_building_plan_v1(
            boundary=l_boundary,
            obstacles=(),
            authorities=_authorities(),
            process_axis="Y",
            layout_family=LINEAR_3_BAND,
            envelope_family=SIMPLE_L,
        )


def test_simple_l_envelope_uses_exact_buildable_cells_around_site_obstacles() -> None:
    boundary = _rectangle_boundary(100, 80)
    obstacles = (
        normalize_polygon(
            {
                "type": "polygon",
                "points": [
                    {"x": 70, "y": 40},
                    {"x": 100, "y": 40},
                    {"x": 100, "y": 80},
                    {"x": 70, "y": 80},
                ],
            }
        ),
        normalize_polygon(
            {
                "type": "polygon",
                "points": [
                    {"x": 0, "y": 30},
                    {"x": 20, "y": 30},
                    {"x": 20, "y": 50},
                    {"x": 0, "y": 50},
                ],
            }
        ),
    )

    plan = construct_structured_building_plan_v1(
        boundary=boundary,
        obstacles=obstacles,
        authorities=_authorities(),
        process_axis="Y",
        layout_family=CENTRAL_PROCESS_WITH_SIDE_BANKS,
        envelope_family=SIMPLE_L,
        main_entrance=((100_000, 39_000), (100_000, 41_000)),
    )

    assert plan.envelope.family == SIMPLE_L
    assert len(plan.envelope.components_mm) == 2
    assert plan.envelope.site_bounds_mm == (0, 0, 100_000, 80_000)
    assert plan.envelope.bounds_mm != plan.envelope.site_bounds_mm
    for zone_code in ("packaging_material_storage", "office"):
        band = plan.band_for_zone(zone_code)
        assert band.bounds_mm != plan.envelope.bounds_mm
        assert any(
            band.bounds_mm[0] >= x0
            and band.bounds_mm[1] >= y0
            and band.bounds_mm[2] <= x1
            and band.bounds_mm[3] <= y1
            for x0, y0, x1, y1 in plan.envelope.components_mm
        )
    assert (
        sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in plan.envelope.components_mm)
        >= 12 * 100_000_000
    )


def test_simple_l_envelope_contains_rectangles_across_contiguous_components_only() -> None:
    envelope = BuildingEnvelopeV1(
        family=SIMPLE_L,
        bounds_mm=(0, 0, 10_000, 10_000),
        components_mm=((0, 0, 4_000, 10_000), (4_000, 0, 10_000, 4_000)),
        hard_obstacles_mm=(),
        site_bounds_mm=(0, 0, 10_000, 10_000),
    )
    cross_seam = PlacedRectangleV1(
        "finished_goods_room", Decimal("2"), Decimal("1"), Decimal("6"), Decimal("2")
    )
    inside_notch = PlacedRectangleV1(
        "finished_goods_room", Decimal("2"), Decimal("5"), Decimal("6"), Decimal("1")
    )

    assert envelope.contains(cross_seam)
    assert not envelope.contains(inside_notch)


def test_rectangle_envelope_uses_exact_site_and_obstacle_events() -> None:
    obstacle = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 90, "y": 0},
                {"x": 95, "y": 0},
                {"x": 95, "y": 80},
                {"x": 90, "y": 80},
            ],
        }
    )
    plan = construct_structured_building_plan_v1(
        boundary=_rectangle_boundary(),
        obstacles=(obstacle,),
        authorities=_authorities(),
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
    )

    assert plan.envelope.bounds_mm != (0, 0, 100_000, 80_000)
    assert plan.envelope.bounds_mm[2] <= 90_000
    assert plan.envelope.site_bounds_mm == (0, 0, 100_000, 80_000)
