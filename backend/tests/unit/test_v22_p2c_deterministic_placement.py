"""P2C deterministic placement, objective and incomplete-route semantics."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest

from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.placement import place_zones
from cold_storage.modules.layout.application.site_geometry import (
    ValidatedSiteGeometryV1,
    validate_site_geometry,
)
from cold_storage.modules.layout.domain.placement import (
    PLACEMENT_RESULT_IDENTITY,
    SEARCH_PROFILE_IDENTITY,
    SitePlacementResultV1,
    segment_distance_squared,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    normalize_polygon,
    normalize_segment,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
)
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot
from tests.unit.test_v22_p1f_project_truck_input import truck_input

D = Decimal


def site_input(
    *,
    width: int = 200,
    depth: int = 160,
    preferred_loading_side: str = "UNSPECIFIED",
    no_build_zones: list[dict[str, Any]] | None = None,
    boundary_points: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    points = boundary_points or [
        {"x": 0, "y": 0},
        {"x": width, "y": 0},
        {"x": width, "y": depth},
        {"x": 0, "y": depth},
    ]
    return {
        "site_boundary": {"type": "polygon", "points": points},
        "main_entrance": {"start": {"x": 0, "y": 0}, "end": {"x": 5, "y": 0}},
        "truck_entrance": {
            "start": {"x": min(10, width - 2), "y": 0},
            "end": {"x": min(20, width - 1), "y": 0},
        },
        "preferred_loading_side": preferred_loading_side,
        "no_build_zones": no_build_zones or [],
    }


@pytest.fixture(scope="module")
def authority_context() -> tuple[dict[str, Any], ZoneDimensioningResultV1, ValidatedSiteGeometryV1]:
    zone_plan = snapshot()
    truck = truck_input()
    handoff = build_p1_project_handoff(zone_plan, truck)
    geometry = validate_site_geometry(
        {"site_constraints": site_input(), "truck_access": truck},
        zone_plan,
        p1_handoff=handoff,
    )
    return zone_plan, handoff, geometry


def run_placement(
    authority_context: tuple[dict[str, Any], ZoneDimensioningResultV1, ValidatedSiteGeometryV1],
    *,
    complete_candidate_limit: int = 1,
) -> SitePlacementResultV1:
    zone_plan, handoff, geometry = authority_context
    return place_zones(
        zone_plan,
        handoff,
        geometry,
        complete_candidate_limit=complete_candidate_limit,
    )


def rectangles_from_result(body: dict[str, Any]) -> dict[str, PlacedRectangleV1]:
    return {
        row["zone_code"]: PlacedRectangleV1(
            row["zone_code"],
            D(str(row["x"])),
            D(str(row["y"])),
            D(str(row["width_m"])),
            D(str(row["depth_m"])),
            row["rotation_deg"],
        )
        for row in body["zones"]
    }


def test_representative_fixture_finds_twelve_non_overlapping_zones(authority_context) -> None:
    result = run_placement(authority_context)
    body = result.to_dict()
    assert body["status"] == "PLACEMENT_FOUND"
    assert body["placement_available"] is True
    assert body["placement_result_identity"] == PLACEMENT_RESULT_IDENTITY
    assert body["placement_engine_identity"] == "site-constrained-deterministic-placement@1.0.0"
    assert body["search_profile_identity"] == SEARCH_PROFILE_IDENTITY
    assert len(body["zones"]) == 12
    assert body["zone_count"] == 12
    assert body["placement_hard_constraints_passed"] is True
    assert len({row["zone_code"] for row in body["zones"]}) == 12
    assert all(row["x"] is not None and row["y"] is not None for row in body["zones"])

    rectangles = rectangles_from_result(body)
    geometry = authority_context[2].to_dict()
    boundary = normalize_polygon(
        geometry["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = [
        normalize_polygon(row["footprint"], allow_numeric_string=True)
        for row in geometry["obstacles"]["hard_obstacles"]
    ]
    assert all(rectangle_inside_polygon(rectangle, boundary) for rectangle in rectangles.values())
    assert all(
        not rectangle_intersects_closed_obstacle(rectangle, obstacle)
        for rectangle in rectangles.values()
        for obstacle in obstacles
    )
    assert all(
        not rectangles_overlap(first, second)
        for index, first in enumerate(rectangles.values())
        for second in list(rectangles.values())[index + 1 :]
    )
    assert body["must_adjacency_evaluation"] == {
        "hard_constraints_passed": True,
        "required_count": 7,
        "satisfied_count": 7,
        "satisfied_pairs": [
            ["raw_fruit_buffer", "primary_precooling_room"],
            ["primary_precooling_room", "sorting_packaging_room"],
            ["sorting_packaging_room", "secondary_precooling_room"],
            ["secondary_precooling_room", "coating_room"],
            ["coating_room", "finished_goods_room"],
            ["finished_goods_room", "shipping_channel"],
            ["office", "shipping_channel"],
        ],
        "violations": [],
    }
    assert body["placement_objective_vector"]["should_adjacency"]["total_count"] == 5
    assert body["placement_access_observations"]
    assert all(
        row["status"] == "PENDING_ROUTE_VALIDATION" for row in body["placement_access_observations"]
    )
    assert body["routing_validated"] is False
    assert body["access_route_validated"] is False
    assert body["truck_route_validated"] is False
    assert body["project_layout_validated"] is False
    assert body["p2_complete"] is False


def test_same_authoritative_input_selects_same_canonical_candidate(authority_context) -> None:
    first = run_placement(authority_context, complete_candidate_limit=2)
    second = run_placement(authority_context, complete_candidate_limit=2)

    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert (
        first.to_dict()["canonical_candidate_hash"] == second.to_dict()["canonical_candidate_hash"]
    )
    assert first.to_dict()["search_provenance"] == second.to_dict()["search_provenance"]


def test_concrete_geometry_is_preserved_and_flexible_area_is_not_underfilled(
    authority_context,
) -> None:
    result = run_placement(authority_context)
    body = result.to_dict()
    zones = {row["zone_code"]: row for row in body["zones"]}
    dimension = authority_context[1].to_dict()["p1e_historical_handoff"]["dimension_handoff"]
    authorities = {row["zone_code"]: row for row in dimension["authorities"]}

    for code in ("raw_fruit_buffer", "primary_precooling_room", "sorting_packaging_room"):
        expected = authorities[code]["geometry"]
        actual = zones[code]
        assert (actual["width_m"], actual["depth_m"], actual["actual_area_m2"]) == (
            expected["width_m"],
            expected["depth_m"],
            expected["actual_area_m2"],
        )

    for code in ("coating_room", "changing_room", "office"):
        actual = zones[code]
        required = D(str(authorities[code]["required_area_m2"]))
        assert D(str(actual["width_m"])) > 0
        assert D(str(actual["depth_m"])) > 0
        assert D(str(actual["actual_area_m2"])) >= required
        assert D(str(actual["actual_area_m2"])) == D(str(actual["width_m"])) * D(
            str(actual["depth_m"])
        )
        assert actual["rotation_deg"] in (0, 90)

    packaging = zones["packaging_material_storage"]
    assert packaging["actual_area_m2"] == "250.85"
    assert packaging["required_area_m2"] == "250.85"


@pytest.mark.parametrize("preferred", ["UNSPECIFIED", "NORTH", "NEAREST_TRUCK_ENTRANCE"])
def test_loading_side_modes_are_explicit_and_do_not_use_proxy_distance(
    authority_context, preferred: str
) -> None:
    zone_plan, handoff, _ = authority_context
    geometry = validate_site_geometry(
        {
            "site_constraints": site_input(preferred_loading_side=preferred),
            "truck_access": truck_input(),
        },
        zone_plan,
        p1_handoff=handoff,
    )
    body = place_zones(zone_plan, handoff, geometry, complete_candidate_limit=1).to_dict()
    loading = body["placement_objective_vector"]["loading_side"]
    assert body["shipping_loading_face_side"] in {
        "BOTTOM_LONG_EDGE",
        "TOP_LONG_EDGE",
        "LEFT_LONG_EDGE",
        "RIGHT_LONG_EDGE",
    }
    assert "shipping_loading_face_segment" in body
    if preferred == "UNSPECIFIED":
        assert loading == {"mode": "DISABLED", "preferred_loading_side": preferred}
    elif preferred == "NORTH":
        assert loading["mode"] == "BINARY_MATCH"
        assert isinstance(loading["match"], bool)
    else:
        assert loading["mode"] == "MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE"
        assert loading["comparator"] == "EXACT_MIN_SEGMENT_TO_SEGMENT_SQUARED_EUCLIDEAN_DISTANCE"
        assert loading["internal_unit"] == "MM2"
        assert not isinstance(loading["distance_squared_mm2"], float)


def test_exact_nearest_comparator_uses_squared_integer_millimetre_distance() -> None:
    first = normalize_segment(
        {"start": {"x": 0, "y": 0}, "end": {"x": 10, "y": 0}},
        error_code="INVALID_ENTRANCE",
    )
    second = normalize_segment(
        {"start": {"x": 0, "y": 5}, "end": {"x": 10, "y": 5}},
        error_code="INVALID_ENTRANCE",
    )
    assert segment_distance_squared(first, second) == Fraction(25_000_000)


def test_obstacle_is_a_hard_placement_constraint(authority_context) -> None:
    zone_plan, handoff, _ = authority_context
    no_build = [
        {
            "type": "polygon",
            "points": [
                {"x": 210, "y": 170},
                {"x": 225, "y": 170},
                {"x": 225, "y": 185},
                {"x": 210, "y": 185},
            ],
        }
    ]
    geometry = validate_site_geometry(
        {
            "site_constraints": site_input(width=240, depth=200, no_build_zones=no_build),
            "truck_access": truck_input(),
        },
        zone_plan,
        p1_handoff=handoff,
    )
    body = place_zones(zone_plan, handoff, geometry, complete_candidate_limit=1).to_dict()
    assert body["status"] == "PLACEMENT_FOUND"
    obstacle = normalize_polygon(no_build[0])
    assert all(
        not rectangle_intersects_closed_obstacle(rectangle, obstacle)
        for rectangle in rectangles_from_result(body).values()
    )


def test_concave_buildable_boundary_is_supported(authority_context) -> None:
    zone_plan, handoff, _ = authority_context
    points = [
        {"x": 0, "y": 0},
        {"x": 240, "y": 0},
        {"x": 240, "y": 160},
        {"x": 180, "y": 160},
        {"x": 180, "y": 200},
        {"x": 0, "y": 200},
    ]
    geometry = validate_site_geometry(
        {"site_constraints": site_input(boundary_points=points), "truck_access": truck_input()},
        zone_plan,
        p1_handoff=handoff,
    )
    body = place_zones(zone_plan, handoff, geometry, complete_candidate_limit=1).to_dict()
    assert body["status"] == "PLACEMENT_FOUND"
    assert len(body["zones"]) == 12


def test_exhaustion_is_not_reported_as_infeasibility(authority_context) -> None:
    zone_plan, handoff, _ = authority_context
    geometry = validate_site_geometry(
        {
            "site_constraints": site_input(width=10, depth=10),
            "truck_access": truck_input(),
        },
        zone_plan,
        p1_handoff=handoff,
    )
    body = place_zones(
        zone_plan,
        handoff,
        geometry,
        node_budget=1_000,
        complete_candidate_limit=1,
    ).to_dict()
    assert body["status"] == "LAYOUT_SEARCH_EXHAUSTED"
    assert body["placement_available"] is False
    assert body["layout_infeasible_proof_implemented"] is False
    assert "infeasibility proof" in body["warnings"][0]
