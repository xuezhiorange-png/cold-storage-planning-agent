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


def validate(data):
    return validate_site_geometry(data, snapshot(), p1_handoff=handoff())


def test_validated_site_geometry_is_canonical_and_deterministic():
    first = validate(project())
    second = validate(project())

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


def test_p1_handoff_candidate_is_only_accepted_when_server_replay_matches():
    body = validate_site_geometry(project(), snapshot(), p1_handoff=handoff().to_dict()).to_dict()
    assert body["source_p1_handoff_identity"] == "p1-project-access-handoff@1.0.0"


@pytest.mark.parametrize(
    "mutation",
    [
        "concrete_dimension",
        "packaging_geometry",
        "flexible_area",
        "personnel_access_width",
        "material_access_width",
        "access_requirement",
        "adjacency_graph",
        "truck_binding",
    ],
)
def test_p1_handoff_mutations_fail_closed_against_server_replay(mutation):
    candidate = handoff().to_dict()
    historical = candidate["p1e_historical_handoff"]
    if mutation == "concrete_dimension":
        row = next(
            row
            for row in historical["dimension_handoff"]["dimensions"]
            if row["zone_code"] == "finished_goods_room"
        )
        row["width_m"] = "999"
    elif mutation == "packaging_geometry":
        row = next(
            row
            for row in historical["dimension_handoff"]["dimensions"]
            if row["zone_code"] == "packaging_material_storage"
        )
        row["width_m"] = "999"
    elif mutation == "flexible_area":
        row = next(
            row
            for row in historical["dimension_handoff"]["authorities"]
            if row["zone_code"] == "coating_room"
        )
        row["required_area_m2"] = "999"
    elif mutation == "personnel_access_width":
        profile = next(
            profile
            for profile in historical["access_profiles"]
            if profile["access_class"] == "PERSONNEL"
        )
        profile["portal_clear_width_m"] = "9"
    elif mutation == "material_access_width":
        profile = next(
            profile
            for profile in historical["access_profiles"]
            if profile["identity"] == "manual-pallet-jack-clear-envelope@1.0.0"
        )
        profile["portal_clear_width_m"] = "9"
    elif mutation == "access_requirement":
        historical["access_requirements"][0]["portal_required"] = False
    elif mutation == "adjacency_graph":
        historical["dimension_handoff"]["adjacency_graph"]["must_adjacencies"][0] = [
            "office",
            "office",
        ]
    else:
        candidate["truck_input_binding"]["to_ref"] = "office"

    with pytest.raises(LayoutAuthorityError, match="P1_HANDOFF_INTEGRITY_MISMATCH"):
        validate_site_geometry(project(), snapshot(), p1_handoff=candidate)


def test_canonical_zone_plan_is_required_for_p1_authority_replay():
    with pytest.raises(LayoutAuthorityError, match="ZONE_PLAN_IDENTITY_INVALID"):
        validate_site_geometry(project(), handoff())


def test_validated_site_geometry_cannot_be_constructed_without_server_authority():
    geometry = validate(project())
    with pytest.raises(LayoutAuthorityError, match="INVALID_SITE_GEOMETRY_RESULT"):
        ValidatedSiteGeometryV1(geometry.canonical_json())


@pytest.mark.parametrize(
    "mutation",
    [
        "effective_buildable_boundary",
        "remove_hard_obstacle",
        "entrance",
        "retained_building",
        "source_project_input_hash",
        "source_p1_handoff_hash",
    ],
)
def test_forged_geometry_mappings_are_rejected_by_all_foundation_consumers(mutation):
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
    data["site_constraints"]["existing_buildings"] = [
        {
            "id": "retained",
            "name": "Retained building",
            "retained": True,
            "footprint": {
                "type": "polygon",
                "points": [
                    {"x": 40, "y": 40},
                    {"x": 50, "y": 40},
                    {"x": 50, "y": 50},
                    {"x": 40, "y": 50},
                ],
            },
        }
    ]
    forged = validate(data).to_dict()
    if mutation == "effective_buildable_boundary":
        forged["site"]["effective_buildable_boundary"]["points"][1]["x"] = D("999")
    elif mutation == "remove_hard_obstacle":
        forged["obstacles"]["hard_obstacles"] = []
    elif mutation == "entrance":
        forged["entrances"]["main_entrance"]["end"]["x"] = D("999")
    elif mutation == "retained_building":
        forged["obstacles"]["existing_buildings"][0]["footprint"]["points"][0]["x"] = D("0")
    elif mutation == "source_project_input_hash":
        forged["source_project_input_hash"] = "sha256:" + "0" * 64
    else:
        forged["source_p1_handoff_hash"] = "sha256:" + "0" * 64

    with pytest.raises(LayoutAuthorityError, match="INVALID_SITE_GEOMETRY_RESULT"):
        validate_rectangle_against_site(PlacedRectangleV1("zone", 1, 1, 2, 2), forged)
    with pytest.raises(LayoutAuthorityError, match="INVALID_SITE_GEOMETRY_RESULT"):
        validate_building_footprint_against_site(
            {
                "type": "polygon",
                "points": [
                    {"x": 1, "y": 1},
                    {"x": 3, "y": 1},
                    {"x": 3, "y": 3},
                    {"x": 1, "y": 3},
                ],
            },
            forged,
        )


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
    body = validate(data).to_dict()
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


def test_finite_grid_coordinates_have_no_undeclared_magnitude_cap():
    origin = D("1000000000.001")
    polygon = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": origin, "y": origin},
                {"x": origin + 1, "y": origin},
                {"x": origin + 1, "y": origin + 1},
                {"x": origin, "y": origin + 1},
            ],
        }
    )
    assert polygon[0] == (1_000_000_000_001, 1_000_000_000_001)


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
    geometry = validate(data)
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
        validate(outside)


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
    geometry = validate(data)
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

    body = validate(data).to_dict()
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
    geometry = validate(data)
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
    geometry = validate(project())
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
