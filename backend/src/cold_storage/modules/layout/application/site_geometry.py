"""P2A site-geometry validation and canonical provenance boundary.

The application layer composes the already-approved project input and P1
handoff.  It does not calculate zone areas, dimension zones, place objects, or
search for a feasible layout.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.domain.access_authority import TRUCK
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.project_truck_input import validate_project_truck_input
from cold_storage.modules.layout.domain.site_geometry import (
    COORDINATE_SYSTEM,
    GRID_M,
    IDENTITY,
    SCHEMA_VERSION,
    PlacedRectangleV1,
    PolygonMM,
    SegmentMM,
    _polygon_edges,
    _segments_intersect_closed,
    building_footprint_polygon,
    normalize_polygon,
    normalize_segment,
    point_in_polygon,
    polygon_contains_polygon,
    polygon_to_dict,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    segment_on_polygon_boundary,
    segment_to_dict,
    segments_share_positive_length,
)

P1_HANDOFF_IDENTITY = "p1-project-access-handoff@1.0.0"
SITE_INPUT_KEYS = frozenset(
    {
        "site_boundary",
        "buildable_boundary",
        "main_entrance",
        "truck_entrance",
        "preferred_loading_side",
        "no_build_zones",
        "existing_buildings",
        "north_angle_degrees",
    }
)
LOADING_SIDES = frozenset(
    {
        "NORTH",
        "EAST",
        "SOUTH",
        "WEST",
        "NEAREST_TRUCK_ENTRANCE",
        "UNSPECIFIED",
    }
)


@dataclass(frozen=True)
class ValidatedSiteGeometryV1:
    """Canonical validated input; no zone placement or final layout result."""

    payload_json: str

    def to_dict(self) -> dict[str, Any]:
        import json

        return cast(dict[str, Any], json.loads(self.payload_json))

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _invalid_input(field: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError("INVALID_INPUT", field=field, **details)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid_input(field)
    return value


def _validate_p1_handoff(
    handoff: Mapping[str, Any] | ZoneDimensioningResultV1,
) -> tuple[dict[str, Any], str]:
    if isinstance(handoff, ZoneDimensioningResultV1):
        body = handoff.to_dict()
        source_hash = handoff.canonical_result_hash
    elif isinstance(handoff, Mapping):
        body = dict(handoff)
        source_hash = canonical_hash(body)
    else:
        raise LayoutAuthorityError("ZONE_PLAN_REQUIRED", source="p1_project_handoff")
    if body.get("identity") != P1_HANDOFF_IDENTITY or body.get("schema_version") != "1.0.0":
        raise LayoutAuthorityError(
            "P1_HANDOFF_IDENTITY_INVALID", expected_identity=P1_HANDOFF_IDENTITY
        )
    status = body.get("authority_status")
    if not isinstance(status, Mapping):
        raise LayoutAuthorityError("P1_HANDOFF_IDENTITY_INVALID", field="authority_status")
    required_true = (
        "dimension_authority_complete",
        "personnel_access_authority_complete",
        "material_access_authority_complete",
        "truck_access_contract_complete",
        "truck_project_input_contract_complete",
        "p1_complete",
    )
    if any(status.get(field) is not True for field in required_true):
        raise LayoutAuthorityError("P1_HANDOFF_NOT_COMPLETE", fields=list(required_true))
    if body.get("p1_closure_blockers") != []:
        raise LayoutAuthorityError("P1_HANDOFF_NOT_COMPLETE", field="p1_closure_blockers")
    if body.get("p2_implemented") is not False or body.get("p2_authorized") is not False:
        raise LayoutAuthorityError("P1_HANDOFF_IDENTITY_INVALID", field="p2_status")
    binding = body.get("truck_input_binding")
    if not isinstance(binding, Mapping) or binding.get("access_profile_identity") != TRUCK:
        raise LayoutAuthorityError("P1_HANDOFF_IDENTITY_INVALID", field="truck_input_binding")
    historical = body.get("p1e_historical_handoff")
    if not isinstance(historical, Mapping):
        raise LayoutAuthorityError("P1_HANDOFF_IDENTITY_INVALID", field="p1e_historical_handoff")
    return body, source_hash


def _validate_project_shape(
    project_input: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if set(project_input) != {"site_constraints", "truck_access"}:
        raise _invalid_input("project_input", reason="SITE_LAYOUT_PROJECT_INPUT_KEYS")
    site = project_input.get("site_constraints")
    truck = project_input.get("truck_access")
    if not isinstance(site, Mapping):
        raise _invalid_input("site_constraints")
    if not isinstance(truck, Mapping):
        raise _invalid_input("truck_access")
    if set(site) - SITE_INPUT_KEYS:
        raise _invalid_input("site_constraints", reason="UNKNOWN_SITE_FIELD")
    return site, truck


def _validate_site_inputs(
    site: Mapping[str, Any],
) -> tuple[
    PolygonMM,
    PolygonMM,
    SegmentMM,
    SegmentMM,
    list[PolygonMM],
    list[dict[str, Any]],
    str,
    Decimal,
]:
    required = {"site_boundary", "main_entrance", "truck_entrance"}
    if not required <= set(site):
        raise _invalid_input("site_constraints", reason="MISSING_SITE_FIELD")
    site_boundary = normalize_polygon(site["site_boundary"], error_code="INVALID_SITE_BOUNDARY")
    if "buildable_boundary" in site:
        buildable = normalize_polygon(
            site["buildable_boundary"], error_code="INVALID_BUILDABLE_BOUNDARY"
        )
        if not polygon_contains_polygon(site_boundary, buildable):
            raise LayoutAuthorityError("BUILDABLE_BOUNDARY_OUTSIDE_SITE")
    else:
        buildable = site_boundary

    main = normalize_segment(site["main_entrance"], error_code="INVALID_ENTRANCE")
    truck = normalize_segment(site["truck_entrance"], error_code="INVALID_ENTRANCE")
    if not segment_on_polygon_boundary(main[0], main[1], site_boundary):
        raise LayoutAuthorityError("INVALID_ENTRANCE", entrance="main_entrance")
    if not segment_on_polygon_boundary(truck[0], truck[1], site_boundary):
        raise LayoutAuthorityError("INVALID_ENTRANCE", entrance="truck_entrance")

    raw_no_build = site.get("no_build_zones", [])
    if not isinstance(raw_no_build, (list, tuple)):
        raise _invalid_input("no_build_zones")
    no_build = []
    for index, raw in enumerate(raw_no_build):
        polygon = normalize_polygon(raw, error_code="INVALID_NO_BUILD_ZONE")
        if not polygon_contains_polygon(site_boundary, polygon):
            raise LayoutAuthorityError("NO_BUILD_ZONE_OUTSIDE_SITE", index=index)
        no_build.append(polygon)
    no_build.sort(key=canonical_json)

    raw_buildings = site.get("existing_buildings", [])
    if not isinstance(raw_buildings, (list, tuple)):
        raise _invalid_input("existing_buildings")
    buildings: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw in raw_buildings:
        if not isinstance(raw, Mapping) or set(raw) != {"id", "name", "footprint", "retained"}:
            raise _invalid_input("existing_buildings", reason="INVALID_BUILDING_RECORD")
        building_id = _required_text(raw["id"], "existing_buildings.id")
        if building_id in ids:
            raise LayoutAuthorityError("DUPLICATE_EXISTING_BUILDING_ID", building_id=building_id)
        ids.add(building_id)
        name = _required_text(raw["name"], "existing_buildings.name")
        if type(raw["retained"]) is not bool:
            raise _invalid_input("existing_buildings.retained")
        # Existing-building footprints are supplied obstacles.  They need to
        # be valid simple polygons, but P2A does not impose the future
        # building-footprint primitive's orthogonal-only restriction on them.
        footprint = normalize_polygon(raw["footprint"], error_code="INVALID_EXISTING_BUILDING")
        if not polygon_contains_polygon(site_boundary, footprint):
            raise LayoutAuthorityError("EXISTING_BUILDING_OUTSIDE_SITE", building_id=building_id)
        buildings.append(
            {
                "id": building_id,
                "name": name,
                "footprint": polygon_to_dict(footprint),
                "retained": raw["retained"],
            }
        )
    buildings.sort(key=lambda row: row["id"])

    loading_side = site.get("preferred_loading_side", "UNSPECIFIED")
    if not isinstance(loading_side, str) or loading_side not in LOADING_SIDES:
        raise _invalid_input("preferred_loading_side")
    north_angle = site.get("north_angle_degrees", 0)
    if isinstance(north_angle, bool) or not isinstance(north_angle, (int, float, Decimal)):
        raise _invalid_input("north_angle_degrees")
    try:
        north_angle_decimal = Decimal(str(north_angle))
    except (ValueError, ArithmeticError):
        raise _invalid_input("north_angle_degrees") from None
    if not north_angle_decimal.is_finite() or north_angle_decimal < 0 or north_angle_decimal >= 360:
        raise _invalid_input("north_angle_degrees")
    return (
        site_boundary,
        buildable,
        main,
        truck,
        no_build,
        buildings,
        loading_side,
        north_angle_decimal,
    )


def validate_site_geometry(
    project_input: Mapping[str, Any],
    p1_handoff: Mapping[str, Any] | ZoneDimensioningResultV1,
) -> ValidatedSiteGeometryV1:
    """Validate SiteLayoutProjectInputV1 against the current P1 authority handoff."""
    if not isinstance(project_input, Mapping):
        raise _invalid_input("project_input")
    handoff, handoff_hash = _validate_p1_handoff(p1_handoff)
    site_input, truck_input = _validate_project_shape(project_input)
    (
        site_boundary,
        buildable,
        main,
        truck,
        no_build,
        buildings,
        loading_side,
        north_angle,
    ) = _validate_site_inputs(site_input)

    truck_status = validate_project_truck_input(truck_input)
    if truck_status["status"] == "INVALID_PROJECT_TRUCK_INPUT":
        raise LayoutAuthorityError(
            "INVALID_PROJECT_TRUCK_INPUT", field=truck_status.get("field", "truck_access")
        )
    warnings = ["P2A validates geometry only; it does not generate placement, routes or portals."]
    if truck_status["status"] == "PROJECT_INPUT_REQUIRED":
        warnings.append("PROJECT_TRUCK_INPUT_REQUIRED")

    hard_obstacles: list[dict[str, Any]] = [
        {
            "kind": "NO_BUILD_ZONE",
            "footprint": polygon_to_dict(polygon),
            "hard": True,
        }
        for polygon in no_build
    ]
    conditional_removals: list[dict[str, Any]] = []
    for building in buildings:
        if building["retained"]:
            hard_obstacles.append(
                {
                    "kind": "RETAINED_EXISTING_BUILDING",
                    "id": building["id"],
                    "footprint": building["footprint"],
                    "hard": True,
                }
            )
        else:
            conditional_removals.append(
                {
                    "id": building["id"],
                    "name": building["name"],
                    "footprint": building["footprint"],
                    "removal_authorized": False,
                }
            )
    if conditional_removals:
        warnings.append("NON_RETAINED_BUILDING_REMOVAL_CONFIRMATION_REQUIRED")

    shared_entrance = segments_share_positive_length(main[0], main[1], truck[0], truck[1])
    payload = {
        "identity": IDENTITY,
        "schema_version": SCHEMA_VERSION,
        "source_project_input_hash": canonical_hash(project_input),
        "source_p1_handoff_identity": handoff["identity"],
        "source_p1_handoff_hash": handoff_hash,
        "coordinate_system": COORDINATE_SYSTEM,
        "geometry_grid_m": GRID_M,
        "site": {
            "site_boundary": polygon_to_dict(site_boundary),
            "buildable_boundary": polygon_to_dict(buildable),
            "effective_buildable_boundary": polygon_to_dict(buildable),
            "buildable_source": (
                "EXPLICIT_BUILDABLE_BOUNDARY"
                if site_input.get("buildable_boundary") is not None
                else "SITE_BOUNDARY_DEFAULT"
            ),
            "preferred_loading_side": loading_side,
            "north_angle_degrees": north_angle,
        },
        "entrances": {
            "main_entrance": segment_to_dict(main),
            "truck_entrance": segment_to_dict(truck),
            "shared_entrance": shared_entrance,
        },
        "obstacles": {
            "no_build_zones": [polygon_to_dict(polygon) for polygon in no_build],
            "existing_buildings": buildings,
            "hard_obstacles": hard_obstacles,
            "conditional_removal_footprints": conditional_removals,
        },
        "truck_access": {
            "status": truck_status["status"],
            "project_truck_input_complete": truck_status["project_truck_input_complete"],
            "engineering_geometry_used": False,
            "turning_solver_used": False,
        },
        "validation_status": "VALIDATED_GEOMETRY_FOUNDATION",
        "warnings": warnings,
        "requires_review": True,
        "placement_implemented": False,
        "routes_implemented": False,
        "portals_implemented": False,
    }
    return ValidatedSiteGeometryV1(canonical_json(payload))


def _geometry_payload(
    geometry: ValidatedSiteGeometryV1 | Mapping[str, Any],
) -> Mapping[str, Any]:
    if isinstance(geometry, ValidatedSiteGeometryV1):
        return geometry.to_dict()
    if isinstance(geometry, Mapping):
        return geometry
    raise LayoutAuthorityError("INVALID_SITE_GEOMETRY_RESULT")


def validate_rectangle_against_site(
    rectangle: PlacedRectangleV1 | Mapping[str, Any],
    geometry: ValidatedSiteGeometryV1 | Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate hard site/obstacle predicates for one supplied rectangle only."""
    body = _geometry_payload(geometry)
    site = body.get("site")
    obstacles = body.get("obstacles")
    if not isinstance(site, Mapping) or not isinstance(obstacles, Mapping):
        raise LayoutAuthorityError("INVALID_SITE_GEOMETRY_RESULT")
    boundary = normalize_polygon(
        site.get("effective_buildable_boundary"), allow_numeric_string=True
    )
    rect = rectangle if isinstance(rectangle, PlacedRectangleV1) else rectangle
    if not rectangle_inside_polygon(rect, boundary):
        raise LayoutAuthorityError(
            "HARD_CONSTRAINT_UNSATISFIABLE",
            constraint="INSIDE_BUILDABLE_BOUNDARY",
            zone_code=_rectangle_zone_code(rect),
        )
    hard = obstacles.get("hard_obstacles")
    if not isinstance(hard, list):
        raise LayoutAuthorityError("INVALID_SITE_GEOMETRY_RESULT", field="hard_obstacles")
    for obstacle in hard:
        if not isinstance(obstacle, Mapping):
            raise LayoutAuthorityError("INVALID_SITE_GEOMETRY_RESULT", field="hard_obstacles")
        footprint = normalize_polygon(
            obstacle.get("footprint"),
            error_code="INVALID_SITE_GEOMETRY_RESULT",
            allow_numeric_string=True,
        )
        if rectangle_intersects_closed_obstacle(rect, footprint):
            raise LayoutAuthorityError(
                "HARD_CONSTRAINT_UNSATISFIABLE",
                constraint="OBSTACLE_CLEAR",
                zone_code=_rectangle_zone_code(rect),
                obstacle=obstacle.get("id", obstacle.get("kind")),
            )
    return {
        "hard_constraints_passed": True,
        "inside_effective_buildable_boundary": True,
        "hard_obstacles_clear": True,
        "access_status": "NOT_EVALUATED_NO_ROUTE",
    }


def _rectangle_zone_code(rectangle: PlacedRectangleV1 | Mapping[str, Any]) -> object:
    return (
        rectangle.zone_code
        if isinstance(rectangle, PlacedRectangleV1)
        else rectangle.get("zone_code")
    )


def validate_building_footprint_against_site(
    footprint: object,
    geometry: ValidatedSiteGeometryV1 | Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a supplied orthogonal footprint; never generate one."""
    body = _geometry_payload(geometry)
    site = body.get("site")
    obstacles = body.get("obstacles")
    if not isinstance(site, Mapping) or not isinstance(obstacles, Mapping):
        raise LayoutAuthorityError("INVALID_SITE_GEOMETRY_RESULT")
    polygon = building_footprint_polygon(footprint)
    boundary = normalize_polygon(
        site.get("effective_buildable_boundary"), allow_numeric_string=True
    )
    if not polygon_contains_polygon(boundary, polygon):
        raise LayoutAuthorityError(
            "HARD_CONSTRAINT_UNSATISFIABLE", constraint="BUILDING_INSIDE_BOUNDARY"
        )
    hard = obstacles.get("hard_obstacles", [])
    if not isinstance(hard, list):
        raise LayoutAuthorityError("INVALID_SITE_GEOMETRY_RESULT", field="hard_obstacles")
    for obstacle in hard:
        if isinstance(obstacle, Mapping) and _polygon_intersects_closed(
            polygon,
            normalize_polygon(
                obstacle.get("footprint"),
                error_code="INVALID_SITE_GEOMETRY_RESULT",
                allow_numeric_string=True,
            ),
        ):
            raise LayoutAuthorityError(
                "HARD_CONSTRAINT_UNSATISFIABLE",
                constraint="BUILDING_OBSTACLE_CLEAR",
                obstacle=obstacle.get("id", obstacle.get("kind")),
            )
    return {"hard_constraints_passed": True, "building_footprint_validated": True}


def _polygon_intersects_closed(first: PolygonMM, second: PolygonMM) -> bool:
    if any(
        _segments_intersect_closed(a, b, c, d)
        for a, b in _polygon_edges(first)
        for c, d in _polygon_edges(second)
    ):
        return True
    return point_in_polygon(first[0], second) or point_in_polygon(second[0], first)


def evaluate_zone_rectangles(
    rectangles: Sequence[PlacedRectangleV1 | Mapping[str, Any]],
) -> dict[str, Any]:
    """Check only zone overlap; shared edges and corner touches remain legal."""
    normalized = tuple(row if isinstance(row, PlacedRectangleV1) else row for row in rectangles)
    violations: list[dict[str, Any]] = []
    for index, first in enumerate(normalized):
        for second in normalized[index + 1 :]:
            if rectangles_overlap(first, second):
                violations.append(
                    {
                        "code": "ZONE_OVERLAP",
                        "zones": sorted(
                            (_rectangle_zone_code(first), _rectangle_zone_code(second))
                        ),
                    }
                )
    return {
        "hard_constraints_passed": not violations,
        "violations": violations,
        "adjacency_status": "NOT_EVALUATED",
    }
