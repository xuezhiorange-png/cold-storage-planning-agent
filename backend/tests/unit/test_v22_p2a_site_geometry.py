"""P2A exact geometry predicates and canonical site-input validation."""

from copy import deepcopy
from decimal import Decimal

import pytest

from cold_storage.modules.layout.application.dimension_handoff import build_dimension_handoff
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import (
    ValidatedSiteGeometryV1,
    evaluate_zone_rectangles,
    validate_building_footprint_against_site,
    validate_rectangle_against_site,
    validate_site_geometry,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    building_footprint_polygon,
    normalize_polygon,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
    segment_on_polygon_boundary,
)
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot
from tests.unit.test_v22_p1f_project_truck_input import truck_input

D = Decimal


def project(site: dict[str, object] | None = None, truck: dict[str, object] | None = None):
    site = site or {
        "site_boundary": {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 80},
                {"x": 0, "y": 80},
            ],
        },
        "main_entrance": {"start": {"x": 0, "y": 0}, "end": {"x": 5, "y": 0}},
        "truck_entrance": {"start": {"x": 10, "y": 0}, "end": {"x": 20, "y": 0}},
    }
    return {"site_constraints": site, "truck_access": truck or truck_input()}


def handoff():
    return build_p1_project_handoff(snapshot(), truck_input())


def test_validated_site_geometry_is_canonical_and_deterministic():
    first = validate_site_geometry(project(), handoff())
    second = validate_site_geometry(project(), handoff())

    assert isinstance(first, ValidatedSiteGeometryV1)
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    body = first.to_dict()
    assert body["identity"] == "site-geometry-foundation@1.0.0"
    assert body["schema_version"] == "1.0.0"
    assert body["coordinate_system"] == "LOCAL_CARTESIAN_METERS"
    assert body["geometry_grid_m"] == "0.001"
    assert body["site"]["buildable_source"] == "SITE_BOUNDARY_DEFAULT"
    assert body["entrances"]["shared_entrance"] is False
    assert body["truck_access"]["engineering_geometry_used"] is False
    assert body["truck_access"]["turning_solver_used"] is False
    assert not {"zones", "building", "routes", "portals", "svg"} & body.keys()


def test_explicit_buildable_boundary_and_shared_entrance_are_recorded():
    data = project()
    data["site_constraints"]["buildable_boundary"] = {
        "type": "polygon",
        "points": [
            {"x": 0, "y": 0},
            {"x": 50, "y": 0},
            {"x": 50, "y": 40},
            {"x": 0, "y": 40},
        ],
    }
    data["site_constraints"]["truck_entrance"] = deepcopy(data["site_constraints"]["main_entrance"])
    body = validate_site_geometry(data, handoff()).to_dict()
    assert body["site"]["buildable_source"] == "EXPLICIT_BUILDABLE_BOUNDARY"
    assert body["entrances"]["shared_entrance"] is True


@pytest.mark.parametrize(
    "value",
    [
        {
            "type": "polygon",
            "points": [{"x": 0, "y": 0}, {"x": 5, "y": 5}],
        },
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 10, "y": 10},
                {"x": 0, "y": 10},
                {"x": 10, "y": 0},
            ],
        },
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 10, "y": 0},
                {"x": 10, "y": 10},
                {"x": 0, "y": 0},
            ],
        },
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 10, "y": 0},
                {"x": 10, "y": 0},
                {"x": 0, "y": 10},
            ],
        },
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 10, "y": 0},
                {"x": 10, "y": 10},
                {"x": 0, "y": 10.0001},
            ],
        },
    ],
)
def test_invalid_site_polygon_fails_closed(value):
    with pytest.raises(LayoutAuthorityError):
        normalize_polygon(value)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), float("-inf"), "1.0"])
def test_invalid_site_coordinate_types_fail_closed(value):
    polygon = {
        "type": "polygon",
        "points": [{"x": 0, "y": 0}, {"x": value, "y": 0}, {"x": 0, "y": 1}],
    }
    with pytest.raises(LayoutAuthorityError):
        normalize_polygon(polygon)


def test_concave_container_checks_edges_not_only_vertices():
    site = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 10, "y": 0},
                {"x": 10, "y": 10},
                {"x": 7, "y": 10},
                {"x": 7, "y": 3},
                {"x": 3, "y": 3},
                {"x": 3, "y": 10},
                {"x": 0, "y": 10},
            ],
        }
    )
    candidate = normalize_polygon(
        {
            "type": "polygon",
            "points": [{"x": 1, "y": 8}, {"x": 9, "y": 8}, {"x": 5, "y": 2}],
        }
    )
    from cold_storage.modules.layout.domain.site_geometry import polygon_contains_polygon

    assert not polygon_contains_polygon(site, candidate)


def test_buildable_and_obstacle_boundaries_are_fail_closed_with_exact_sets():
    data = project()
    data["site_constraints"]["no_build_zones"] = [
        {
            "type": "polygon",
            "points": [
                {"x": 20, "y": 20},
                {"x": 30, "y": 20},
                {"x": 30, "y": 30},
                {"x": 20, "y": 30},
            ],
        }
    ]
    geometry = validate_site_geometry(data, handoff())
    touching = PlacedRectangleV1("zone", 10, 20, 10, 10)
    with pytest.raises(LayoutAuthorityError, match="HARD_CONSTRAINT_UNSATISFIABLE"):
        validate_rectangle_against_site(touching, geometry)

    outside = project()
    outside["site_constraints"]["no_build_zones"] = [
        {
            "type": "polygon",
            "points": [
                {"x": 95, "y": 75},
                {"x": 105, "y": 75},
                {"x": 105, "y": 85},
                {"x": 95, "y": 85},
            ],
        }
    ]
    with pytest.raises(LayoutAuthorityError, match="NO_BUILD_ZONE_OUTSIDE_SITE"):
        validate_site_geometry(outside, handoff())


def test_non_retained_building_is_conditional_not_a_hard_obstacle():
    data = project()
    data["site_constraints"]["existing_buildings"] = [
        {
            "id": "old-shed",
            "name": "Old shed",
            "retained": False,
            "footprint": {
                "type": "polygon",
                "points": [
                    {"x": 20, "y": 20},
                    {"x": 30, "y": 20},
                    {"x": 30, "y": 30},
                    {"x": 20, "y": 30},
                ],
            },
        }
    ]
    geometry = validate_site_geometry(data, handoff())
    body = geometry.to_dict()
    assert body["obstacles"]["hard_obstacles"] == []
    assert body["obstacles"]["conditional_removal_footprints"][0]["removal_authorized"] is False
    assert "NON_RETAINED_BUILDING_REMOVAL_CONFIRMATION_REQUIRED" in body["warnings"]
    assert validate_rectangle_against_site(PlacedRectangleV1("zone", 20, 20, 10, 10), geometry)


def test_existing_building_obstacle_accepts_valid_non_orthogonal_polygon():
    data = project()
    data["site_constraints"]["existing_buildings"] = [
        {
            "id": "triangular-annex",
            "name": "Triangular annex",
            "retained": True,
            "footprint": {
                "type": "polygon",
                "points": [
                    {"x": 20, "y": 20},
                    {"x": 30, "y": 20},
                    {"x": 25, "y": 30},
                ],
            },
        }
    ]

    body = validate_site_geometry(data, handoff()).to_dict()
    assert body["obstacles"]["hard_obstacles"][0]["kind"] == "RETAINED_EXISTING_BUILDING"


def test_retained_building_is_hard_and_building_footprint_is_orthogonal_only():
    data = project()
    data["site_constraints"]["existing_buildings"] = [
        {
            "id": "retained",
            "name": "Retained building",
            "retained": True,
            "footprint": {
                "type": "polygon",
                "points": [
                    {"x": 20, "y": 20},
                    {"x": 30, "y": 20},
                    {"x": 30, "y": 30},
                    {"x": 20, "y": 30},
                ],
            },
        }
    ]
    geometry = validate_site_geometry(data, handoff())
    with pytest.raises(LayoutAuthorityError, match="HARD_CONSTRAINT_UNSATISFIABLE"):
        validate_rectangle_against_site(PlacedRectangleV1("zone", 20, 20, 10, 10), geometry)
    with pytest.raises(LayoutAuthorityError, match="INVALID_BUILDING_FOOTPRINT"):
        building_footprint_polygon(
            {
                "type": "polygon",
                "points": [{"x": 0, "y": 0}, {"x": 2, "y": 0}, {"x": 1, "y": 1}],
            }
        )


def test_entrance_requires_whole_boundary_segment_and_allows_collinear_edges():
    site = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 5, "y": 0},
                {"x": 10, "y": 0},
                {"x": 10, "y": 10},
                {"x": 0, "y": 10},
            ],
        }
    )
    assert segment_on_polygon_boundary((2_000, 0), (8_000, 0), site)
    assert not segment_on_polygon_boundary((0, 0), (10_000, 10_000), site)


def test_rectangle_predicates_distinguish_rotation_overlap_shared_edge_and_corner():
    rotated = PlacedRectangleV1("rotated", 0, 0, 2, 5, 90)
    assert rotated.bounds_mm == (0, 0, 5_000, 2_000)
    assert rotated.actual_area_m2 == D("10")
    inside = PlacedRectangleV1("inside", 5, 0, 5, 2)
    corner = PlacedRectangleV1("corner", 5, 2, 1, 1)
    overlap = PlacedRectangleV1("overlap", 4, 0, 2, 2)
    assert rectangles_share_positive_edge(rotated, inside)
    assert not rectangles_overlap(rotated, inside)
    assert not rectangles_share_positive_edge(rotated, corner)
    assert not rectangles_overlap(rotated, corner)
    assert rectangles_overlap(rotated, overlap)
    square = normalize_polygon(
        {
            "type": "polygon",
            "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}, {"x": 0, "y": 10}],
        }
    )
    assert rectangle_inside_polygon(rotated, square)


def test_closed_obstacle_detects_boundary_touch_and_interior_containment():
    obstacle = normalize_polygon(
        {
            "type": "polygon",
            "points": [{"x": 2, "y": 2}, {"x": 4, "y": 2}, {"x": 4, "y": 4}, {"x": 2, "y": 4}],
        }
    )
    assert rectangle_intersects_closed_obstacle(PlacedRectangleV1("touch", 0, 2, 2, 2), obstacle)
    assert rectangle_intersects_closed_obstacle(PlacedRectangleV1("contains", 1, 1, 5, 5), obstacle)
    assert not rectangle_intersects_closed_obstacle(
        PlacedRectangleV1("clear", 5, 5, 1, 1), obstacle
    )


def test_flexible_candidates_are_area_bound_not_ratio_bound():
    body = build_dimension_handoff(snapshot()).to_dict()
    authority = next(row for row in body["authorities"] if row["zone_code"] == "coating_room")
    from cold_storage.modules.layout.domain.site_geometry import validate_flexible_candidate

    result = validate_flexible_candidate(authority, D("1"), D("100"))
    assert result["actual_area_m2"] == D("100")
    with pytest.raises(LayoutAuthorityError, match="FLEXIBLE_DIMENSION_AREA_UNSATISFIED"):
        validate_flexible_candidate(authority, D("1"), D("0.001"))


def test_concrete_p1_geometry_cannot_be_resized_or_have_area_replaced():
    body = build_dimension_handoff(snapshot()).to_dict()
    authority = next(row for row in body["authorities"] if row["status"] == "DIMENSIONED")
    from cold_storage.modules.layout.domain.site_geometry import validate_concrete_candidate

    assert (
        validate_concrete_candidate(authority, {"zone_code": authority["zone_code"]})
        == authority["geometry"]
    )
    with pytest.raises(LayoutAuthorityError, match="FIXED_DIMENSION_RESIZE_FORBIDDEN"):
        validate_concrete_candidate(
            authority, {"zone_code": authority["zone_code"], "width_m": "999"}
        )


def test_building_and_zone_collection_predicates_are_separate():
    geometry = validate_site_geometry(project(), handoff())
    footprint = {
        "type": "polygon",
        "points": [{"x": 1, "y": 1}, {"x": 11, "y": 1}, {"x": 11, "y": 11}, {"x": 1, "y": 11}],
    }
    assert validate_building_footprint_against_site(footprint, geometry)["hard_constraints_passed"]
    first = PlacedRectangleV1("a", 1, 1, 10, 10)
    second = PlacedRectangleV1("b", 11, 1, 10, 10)
    assert evaluate_zone_rectangles((first, second))["hard_constraints_passed"]
    assert (
        evaluate_zone_rectangles((first, PlacedRectangleV1("b", 10, 1, 10, 10)))[
            "hard_constraints_passed"
        ]
        is False
    )
