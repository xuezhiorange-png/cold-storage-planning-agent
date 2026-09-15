"""P2D application boundary for route and final-layout validation.

This module binds a P2C placement to the already verified P1 handoff and site
geometry.  It delegates geometry predicates to the layout domain and never
recomputes a zone area, a process formula, or a truck envelope.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import Context, Decimal, localcontext
from typing import Any, cast

from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.placement import _validate_p1_authority
from cold_storage.modules.layout.application.site_geometry import (
    ValidatedSiteGeometryV1,
    validate_building_footprint_against_site,
)
from cold_storage.modules.layout.domain.access_routing import (
    RESULT_IDENTITY as DOMAIN_RESULT_IDENTITY,
)
from cold_storage.modules.layout.domain.access_routing import (
    SCHEMA_VERSION as DOMAIN_SCHEMA_VERSION,
)
from cold_storage.modules.layout.domain.access_routing import (
    _edge_segments,
    _segment_from_mapping,
    _segment_length_mm,
    derive_building_footprint,
    evaluate_personnel_truck_interaction,
    route_access_requirement,
    validate_truck_maneuver_chain,
)
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.objective_profile import approved_objective_profile
from cold_storage.modules.layout.domain.placement import SitePlacementResultV1, _long_edges
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    SegmentMM,
    _polygon_edges,
    normalize_polygon,
    polygon_contains_polygon,
    polygon_to_dict,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
)
from cold_storage.modules.layout.domain.truck_maneuver import (
    BoundTruckManeuverProjectInputV1,
)

IDENTITY = "site-access-routing-application@1.0.0"
RESULT_IDENTITY = DOMAIN_RESULT_IDENTITY
SCHEMA_VERSION = DOMAIN_SCHEMA_VERSION
P1_ACCESS_REQUIREMENT_COUNT = 12
ZONE_COUNT = 12


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("P2D_AUTHORITY_INVALID", field=field)
    return value


def _decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _error("P2D_AUTHORITY_INVALID", field=field)
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        raise _error("P2D_AUTHORITY_INVALID", field=field) from None
    if not number.is_finite():
        raise _error("P2D_AUTHORITY_INVALID", field=field)
    return number


def _placement_body(
    placement: SitePlacementResultV1 | Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    if isinstance(placement, SitePlacementResultV1):
        body = placement.to_dict()
        return body, placement.canonical_result_hash
    if not isinstance(placement, Mapping):
        raise _error("PLACEMENT_AUTHORITY_REQUIRED")
    body = dict(placement)
    supplied = body.pop("canonical_result_hash", None)
    expected = canonical_hash(body)
    if supplied != expected:
        raise _error(
            "PLACEMENT_INTEGRITY_MISMATCH",
            expected_hash=expected,
            actual_hash=supplied,
        )
    return body, expected


def _rectangle_from_row(row: Mapping[str, Any]) -> PlacedRectangleV1:
    required = {"zone_code", "x", "y", "width_m", "depth_m", "rotation_deg"}
    if not required <= set(row):
        raise _error("PLACEMENT_AUTHORITY_INVALID", field="zones")
    try:
        return PlacedRectangleV1(
            str(row["zone_code"]),
            _decimal(row["x"], field="zones.x"),
            _decimal(row["y"], field="zones.y"),
            _decimal(row["width_m"], field="zones.width_m"),
            _decimal(row["depth_m"], field="zones.depth_m"),
            row["rotation_deg"],
        )
    except LayoutAuthorityError:
        raise
    except (TypeError, ValueError):
        raise _error("PLACEMENT_AUTHORITY_INVALID", field="zones") from None


def _segment_is_subsegment(segment: SegmentMM, edge: SegmentMM) -> bool:
    if segment[0][0] == segment[1][0] != edge[0][0]:
        return False
    if segment[0][1] == segment[1][1] != edge[0][1]:
        return False
    return (
        min(edge[0][0], edge[1][0]) <= segment[0][0] <= max(edge[0][0], edge[1][0])
        and min(edge[0][1], edge[1][1]) <= segment[0][1] <= max(edge[0][1], edge[1][1])
        and min(edge[0][0], edge[1][0]) <= segment[1][0] <= max(edge[0][0], edge[1][0])
        and min(edge[0][1], edge[1][1]) <= segment[1][1] <= max(edge[0][1], edge[1][1])
        and _segment_length_mm(segment) > 0
    )


def _validate_loading_face(rectangle: PlacedRectangleV1, segment: SegmentMM) -> None:
    if not any(
        edge_class == "LONG_EDGE" and _segment_is_subsegment(segment, edge)
        for _, edge_class, edge in _edge_segments(rectangle)
    ):
        raise _error("PLACEMENT_AUTHORITY_INVALID", field="shipping_loading_face_segment")


def _validate_selected_loading_face(
    rectangle: PlacedRectangleV1, side: object, segment: SegmentMM
) -> None:
    """Bind both P2C loading-face fields; P2D may not switch sides."""
    if not isinstance(side, str):
        raise _error("PLACEMENT_AUTHORITY_INVALID", field="shipping_loading_face_side")
    matches = [
        edge_name
        for edge_name, edge in _long_edges(rectangle)
        if _segment_is_subsegment(segment, edge)
    ]
    expected = matches[0] if len(matches) == 1 else None
    if expected != side:
        raise _error(
            "PLACEMENT_INTEGRITY_MISMATCH",
            field="shipping_loading_face_side",
            expected=expected,
            actual=side,
        )


def _zone_authority_checks(
    rows: Sequence[Mapping[str, Any]],
    authorities: Mapping[str, Mapping[str, Any]],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> dict[str, PlacedRectangleV1]:
    if len(rows) != ZONE_COUNT:
        raise _error("PLACEMENT_AUTHORITY_INVALID", field="zones", expected_count=ZONE_COUNT)
    rectangles: dict[str, PlacedRectangleV1] = {}
    for row in rows:
        rectangle = _rectangle_from_row(row)
        if rectangle.zone_code in rectangles:
            raise _error("PLACEMENT_AUTHORITY_INVALID", field="duplicate_zone_code")
        if rectangle.zone_code not in authorities:
            raise _error("PLACEMENT_AUTHORITY_INVALID", field="unknown_zone_code")
        authority = authorities[rectangle.zone_code]
        required = _decimal(
            authority.get("required_area_m2"), field=f"{rectangle.zone_code}.required_area_m2"
        )
        mode = authority.get("dimension_mode")
        if mode == "FLEXIBLE_RECTANGLE" and rectangle.actual_area_m2 < required:
            raise _error(
                "PLACEMENT_HARD_CONSTRAINT_UNSATISFIED",
                zone_code=rectangle.zone_code,
                constraint="ACTUAL_AREA_AT_LEAST_REQUIRED_AREA",
            )
        if not rectangle_inside_polygon(rectangle, boundary):
            raise _error(
                "PLACEMENT_HARD_CONSTRAINT_UNSATISFIED",
                zone_code=rectangle.zone_code,
                constraint="INSIDE_BUILDABLE_BOUNDARY",
            )
        if any(rectangle_intersects_closed_obstacle(rectangle, obstacle) for obstacle in obstacles):
            raise _error(
                "PLACEMENT_HARD_CONSTRAINT_UNSATISFIED",
                zone_code=rectangle.zone_code,
                constraint="OBSTACLE_CLEAR",
            )
        if mode != "FLEXIBLE_RECTANGLE":
            dimensions = authority.get("geometry")
            if isinstance(dimensions, Mapping):
                expected_width = _decimal(dimensions.get("width_m"), field="width_m")
                expected_depth = _decimal(dimensions.get("depth_m"), field="depth_m")
                if rectangle.width_m != expected_width or rectangle.depth_m != expected_depth:
                    raise _error("FIXED_DIMENSION_RESIZE_FORBIDDEN", zone_code=rectangle.zone_code)
        rectangles[rectangle.zone_code] = rectangle
    if set(rectangles) != set(authorities):
        raise _error("PLACEMENT_AUTHORITY_INVALID", field="zone_set")
    for index, first in enumerate(rectangles.values()):
        for second in tuple(rectangles.values())[index + 1 :]:
            if rectangles_overlap(first, second):
                raise _error(
                    "PLACEMENT_HARD_CONSTRAINT_UNSATISFIED",
                    constraint="NO_ZONE_OVERLAP",
                )
    return rectangles


def _truck_binding_from_input(
    binding: BoundTruckManeuverProjectInputV1 | Mapping[str, Any] | None,
) -> BoundTruckManeuverProjectInputV1 | None:
    if binding is None:
        return None
    try:
        return (
            BoundTruckManeuverProjectInputV1.from_mapping(binding.to_dict())
            if isinstance(binding, BoundTruckManeuverProjectInputV1)
            else BoundTruckManeuverProjectInputV1.from_mapping(binding)
        )
    except (LayoutAuthorityError, TypeError, ValueError) as error:
        raise _error(
            "INVALID_TRUCK_MANEUVER_PROJECT_BINDING",
            reason=getattr(error, "code", "INVALID_TRUCK_MANEUVER_PROJECT_BINDING"),
        ) from None


def _verify_truck_binding_matches_handoff(
    binding: BoundTruckManeuverProjectInputV1 | None,
    handoff_body: Mapping[str, Any],
) -> None:
    if binding is None:
        return
    status = handoff_body.get("project_status")
    if not isinstance(status, Mapping):
        raise _error("P1F_PROJECT_INPUT_INTEGRITY_MISMATCH")
    canonical = status.get("validated_input_canonical_json")
    if not isinstance(canonical, str):
        raise _error("P1F_PROJECT_INPUT_INTEGRITY_MISMATCH")
    try:
        p1f = json.loads(canonical)
    except json.JSONDecodeError:
        raise _error("P1F_PROJECT_INPUT_INTEGRITY_MISMATCH") from None
    if not isinstance(p1f, Mapping):
        raise _error("P1F_PROJECT_INPUT_INTEGRITY_MISMATCH")
    if binding.p1f_input_canonical_hash != canonical_hash(p1f):
        raise _error("P1F_PROJECT_INPUT_INTEGRITY_MISMATCH")
    if binding.project_id != p1f.get("project_id"):
        raise _error("P1F_PROJECT_INPUT_INTEGRITY_MISMATCH")


def _truck_access_result(
    requirement: Mapping[str, Any], truck: Mapping[str, Any]
) -> dict[str, Any]:
    result = {
        "requirement_identity": requirement.get("identity"),
        "from_ref": requirement.get("from_ref"),
        "to_ref": requirement.get("to_ref"),
        "flow_kind": requirement.get("flow_kind"),
        "access_class": requirement.get("access_class"),
        "profile_identity": requirement.get("profile_identity"),
        "portal_required": requirement.get("portal_required"),
        "corridor_allowed": requirement.get("corridor_allowed"),
        "direct_allowed": requirement.get("direct_allowed"),
        "edge_orientation_requirement": requirement.get("edge_orientation_requirement"),
        "route_shape_constraint": requirement.get("route_shape_constraint"),
        "topology": "TRUCK_MANEUVER_CHAIN",
        "portal_from": None,
        "portal_to": None,
        "centerline": [],
        "clear_width_m": None,
        "corridor_envelope": [],
        "route_length_m": None,
        "turn_count": None,
        "route_shape": "MANEUVER_CHAIN",
        "edge_alignment_verified": True,
        "status": "PASS" if truck.get("truck_route_validated") is True else "BLOCKED",
        "codes": list(truck.get("codes", [])),
        "requires_review": True,
        "truck_route_validated": truck.get("truck_route_validated") is True,
    }
    result["canonical_hash"] = canonical_hash(result)
    return result


def _placement_access_observation(
    requirement: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any]:
    """Join one P1 requirement with its P2D observation without re-binding it.

    The requirement fields are copied from the verified P1 handoff.  P2D only
    appends observations; it never creates a second access authority model.
    """
    observation = dict(requirement)
    observation.update(
        {
            "observation_id": requirement.get("identity"),
            "evaluation_status": result.get("status"),
            "evaluation_codes": list(result.get("codes", [])),
            "topology": result.get("topology"),
            "portal_from": result.get("portal_from"),
            "portal_to": result.get("portal_to"),
            "centerline": result.get("centerline", []),
            "corridor_envelope": result.get("corridor_envelope", []),
            "route_length_m": result.get("route_length_m"),
            "turn_count": result.get("turn_count"),
            "route_shape": result.get("route_shape"),
            "edge_alignment_verified": result.get("edge_alignment_verified"),
            "canonical_hash": canonical_hash(
                {
                    **observation,
                    "evaluation_status": result.get("status"),
                    "evaluation_codes": list(result.get("codes", [])),
                    "topology": result.get("topology"),
                    "portal_from": result.get("portal_from"),
                    "portal_to": result.get("portal_to"),
                    "centerline": result.get("centerline", []),
                    "corridor_envelope": result.get("corridor_envelope", []),
                    "route_length_m": result.get("route_length_m"),
                    "turn_count": result.get("turn_count"),
                    "route_shape": result.get("route_shape"),
                    "edge_alignment_verified": result.get("edge_alignment_verified"),
                }
            ),
        }
    )
    return observation


def _building_area_m2(polygon: PolygonMM) -> Decimal:
    double_area = sum(
        first[0] * second[1] - second[0] * first[1] for first, second in _polygon_edges(polygon)
    )
    with localcontext(Context(prec=80)):
        return Decimal(abs(double_area)) / Decimal(2_000_000)


@dataclass(frozen=True, init=False)
class SiteAccessRoutingResultV1:
    """Immutable final P2D result; its hash excludes the hash field itself."""

    payload_json: str
    _content_hash: str = dataclass_field(init=False, repr=False, compare=False)

    def __init__(self, payload: Mapping[str, Any]) -> None:
        content = dict(payload)
        content.pop("canonical_result_hash", None)
        object.__setattr__(self, "payload_json", canonical_json(content))
        object.__setattr__(self, "_content_hash", canonical_hash(content))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SiteAccessRoutingResultV1:
        if not isinstance(payload, Mapping):
            raise _error("INVALID_P2D_RESULT")
        supplied = payload.get("canonical_result_hash")
        result = cls(payload)
        if supplied is not None and supplied != result.canonical_result_hash:
            raise _error("P2D_RESULT_INTEGRITY_MISMATCH")
        return result

    def to_dict(self) -> dict[str, Any]:
        value = cast(dict[str, Any], json.loads(self.payload_json))
        value["canonical_result_hash"] = self._content_hash
        return value

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return self._content_hash


def route_site_placement(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    placement: SitePlacementResultV1 | Mapping[str, Any],
    truck_maneuver_binding: BoundTruckManeuverProjectInputV1 | Mapping[str, Any] | None = None,
    *,
    route_node_budget: int = 20_000,
    truck_node_budget: int = 20_000,
) -> SiteAccessRoutingResultV1:
    """Validate all P1 access requirements against one P2C placement."""
    if not isinstance(canonical_zone_plan, Mapping):
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    if (
        not isinstance(site_geometry, ValidatedSiteGeometryV1)
        or not site_geometry._is_authoritative()
    ):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", reason="UNVERIFIED_GEOMETRY_RESULT")
    placement_body, placement_hash = _placement_body(placement)
    if placement_body.get("placement_result_identity") != "site_constrained_factory_layout@1.0.0":
        raise _error("PLACEMENT_IDENTITY_INVALID")
    if placement_body.get("schema_version") != "1.0.0":
        raise _error("PLACEMENT_IDENTITY_INVALID")
    expected_zone_hash = canonical_hash(canonical_zone_plan)
    _, handoff_hash, authorities, requirements, spatial_relationships = _validate_p1_authority(
        canonical_zone_plan, p1_handoff, site_geometry
    )
    if placement_body.get("source_zone_plan_hash") != expected_zone_hash:
        raise _error("PLACEMENT_INTEGRITY_MISMATCH", field="source_zone_plan_hash")
    if placement_body.get("source_p1_handoff_hash") != handoff_hash:
        raise _error("PLACEMENT_INTEGRITY_MISMATCH", field="source_p1_handoff_hash")
    if placement_body.get("source_site_geometry_hash") != site_geometry.canonical_result_hash:
        raise _error("PLACEMENT_INTEGRITY_MISMATCH", field="source_site_geometry_hash")
    if (
        placement_body.get("source_objective_profile_hash")
        != approved_objective_profile().canonical_result_hash
    ):
        raise _error("PLACEMENT_INTEGRITY_MISMATCH", field="source_objective_profile_hash")
    if placement_body.get("placement_hard_constraints_passed") is not True:
        raise _error("PLACEMENT_HARD_CONSTRAINT_UNSATISFIED")
    geometry_body = site_geometry.to_dict()
    site_body = _mapping(geometry_body.get("site"), field="site")
    boundary = normalize_polygon(
        site_body.get("effective_buildable_boundary"), allow_numeric_string=True
    )
    obstacle_body = _mapping(geometry_body.get("obstacles"), field="obstacles")
    raw_obstacles = obstacle_body.get("hard_obstacles", [])
    if not isinstance(raw_obstacles, list):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="hard_obstacles")
    obstacles = tuple(
        normalize_polygon(
            _mapping(row, field="hard_obstacle").get("footprint"),
            error_code="INVALID_SITE_GEOMETRY_RESULT",
            allow_numeric_string=True,
        )
        for row in raw_obstacles
    )
    raw_zone_rows = placement_body.get("zones")
    if not isinstance(raw_zone_rows, list):
        raise _error("PLACEMENT_AUTHORITY_INVALID", field="zones")
    rectangles = _zone_authority_checks(raw_zone_rows, authorities, boundary, obstacles)
    shipping_face = _segment_from_mapping(
        placement_body.get("shipping_loading_face_segment"),
        field="shipping_loading_face_segment",
    )
    _validate_loading_face(rectangles["shipping_channel"], shipping_face)
    _validate_selected_loading_face(
        rectangles["shipping_channel"],
        placement_body.get("shipping_loading_face_side"),
        shipping_face,
    )
    entrances_body = _mapping(geometry_body.get("entrances"), field="entrances")
    entrances: dict[str, SegmentMM] = {
        "main_entrance": _segment_from_mapping(
            entrances_body.get("main_entrance"), field="main_entrance"
        ),
        "truck_entrance": _segment_from_mapping(
            entrances_body.get("truck_entrance"), field="truck_entrance"
        ),
    }
    relationships = {
        str(row["identity"]): dict(row)
        for row in spatial_relationships
        if isinstance(row, Mapping) and isinstance(row.get("identity"), str)
    }
    bound_truck = _truck_binding_from_input(truck_maneuver_binding)
    handoff_body = _mapping(
        p1_handoff.to_dict() if isinstance(p1_handoff, ZoneDimensioningResultV1) else p1_handoff,
        field="p1_handoff",
    )
    _verify_truck_binding_matches_handoff(bound_truck, handoff_body)

    access_results: list[dict[str, Any]] = []
    corridor_records: list[dict[str, Any]] = []
    portal_records: list[dict[str, Any]] = []
    corridor_polygons: list[PolygonMM] = []
    personnel_corridors: list[PolygonMM] = []
    route_metrics: list[dict[str, Any]] = []
    non_truck_requirements = [row for row in requirements if row.get("flow_kind") != "TRUCK"]
    truck_requirements = [row for row in requirements if row.get("flow_kind") == "TRUCK"]
    for requirement in non_truck_requirements:
        routed, polygons = route_access_requirement(
            requirement,
            relationships=relationships,
            zones=rectangles,
            boundary=boundary,
            obstacles=obstacles,
            entrances=entrances,
            route_node_budget=route_node_budget,
        )
        access_results.append(routed)
        if routed.get("portal_from") is not None:
            portal_records.append(routed["portal_from"])
        if routed.get("portal_to") is not None:
            portal_records.append(routed["portal_to"])
        if polygons:
            corridor_polygons.extend(polygons)
            corridor_records.append(
                {
                    "requirement_identity": routed["requirement_identity"],
                    "clear_width_m": routed["clear_width_m"],
                    "centerline": routed["centerline"],
                    "route_shape": routed["route_shape"],
                    "turn_count": routed["turn_count"],
                    "envelope": routed["corridor_envelope"],
                }
            )
            if routed.get("flow_kind") == "PEOPLE":
                personnel_corridors.extend(polygons)
        if routed.get("status") == "PASS":
            route_metrics.append(
                {
                    "requirement_identity": routed["requirement_identity"],
                    "route_length_m": routed["route_length_m"],
                    "turn_count": routed["turn_count"],
                }
            )
    truck_result = validate_truck_maneuver_chain(
        bound_truck,
        truck_entrance=entrances["truck_entrance"],
        shipping_loading_face=shipping_face,
        boundary=boundary,
        obstacles=obstacles,
        zones=rectangles,
        node_budget=truck_node_budget,
    )
    for requirement in truck_requirements:
        access_results.append(_truck_access_result(requirement, truck_result))
    access_results.sort(key=lambda row: str(row.get("requirement_identity")))
    requirement_ids = {str(row.get("identity")) for row in requirements}
    result_ids = {str(row.get("requirement_identity")) for row in access_results}
    if len(access_results) != len(requirements) or result_ids != requirement_ids:
        raise _error(
            "ACCESS_REQUIREMENT_RESULT_BINDING_MISMATCH",
            expected_count=len(requirements),
            actual_count=len(access_results),
        )
    access_pass_count = sum(row.get("status") == "PASS" for row in access_results)
    truck_envelopes: list[PolygonMM] = []
    for raw in truck_result.get("truck_envelopes", []):
        truck_envelopes.append(
            normalize_polygon(
                raw,
                error_code="INVALID_TRANSFORMED_MANEUVER_ENVELOPE",
                allow_numeric_string=True,
            )
        )
    if truck_result.get("truck_route_validated") is True:
        interaction = evaluate_personnel_truck_interaction(personnel_corridors, truck_envelopes)
    else:
        interaction = {
            "status": "BLOCKED",
            "shared_route": False,
            "crossing": False,
            "crossing_necessary": False,
            "requires_review": True,
            "codes": ["BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED"],
            "warnings": [],
            "warning": None,
        }
    building_payload: dict[str, Any] | None = None
    building_valid = False
    building_code: str | None = None
    all_non_truck_pass = len(non_truck_requirements) == 11 and all(
        row.get("flow_kind") == "TRUCK" or row.get("status") == "PASS" for row in access_results
    )
    if all_non_truck_pass:
        try:
            footprint = derive_building_footprint(rectangles, corridor_polygons)
            validate_building_footprint_against_site(polygon_to_dict(footprint), site_geometry)
            if not all(
                polygon_contains_polygon(footprint, rectangle.polygon_mm)
                for rectangle in rectangles.values()
            ) or not all(
                polygon_contains_polygon(footprint, polygon) for polygon in corridor_polygons
            ):
                raise _error("BUILDING_FOOTPRINT_DERIVATION_EXHAUSTED")
            building_payload = {
                "footprint": polygon_to_dict(footprint),
                "gross_area_m2": _building_area_m2(footprint),
                "source": "EXACT_ZONE_RECTANGLES_PLUS_ACCESS_CORRIDOR_ENVELOPES",
                "optimized": False,
            }
            building_valid = True
        except LayoutAuthorityError as error:
            building_code = error.code
    warnings: list[str] = []
    if truck_result.get("truck_route_validated") is not True:
        warnings.append("TRUCK_ROUTE_VALIDATION_INCOMPLETE")
    if interaction.get("status") != "PASS":
        warnings.extend(str(value) for value in interaction.get("warnings", []))
        if interaction.get("warning"):
            warnings.append(str(interaction["warning"]))
    if building_code:
        warnings.append(building_code)
    if access_pass_count != P1_ACCESS_REQUIREMENT_COUNT:
        warnings.append("ACCESS_REQUIREMENT_VALIDATION_INCOMPLETE")
    total_route_length = sum(
        (_decimal(row["route_length_m"], field="route_length_m") for row in route_metrics),
        Decimal("0"),
    )
    final_access = access_pass_count == P1_ACCESS_REQUIREMENT_COUNT
    truck_valid = truck_result.get("truck_route_validated") is True
    project_valid = (
        placement_body.get("placement_hard_constraints_passed") is True
        and final_access
        and truck_valid
        and interaction.get("status") == "PASS"
        and building_valid
    )
    payload = {
        "identity": IDENTITY,
        "schema_version": SCHEMA_VERSION,
        "result_identity": RESULT_IDENTITY,
        "source_zone_plan_hash": expected_zone_hash,
        "source_p1_handoff_hash": handoff_hash,
        "source_site_geometry_hash": site_geometry.canonical_result_hash,
        "source_objective_profile_hash": placement_body["source_objective_profile_hash"],
        "source_placement_result_hash": placement_hash,
        "source_truck_maneuver_binding_hash": (
            bound_truck.canonical_result_hash if bound_truck is not None else None
        ),
        "zone_count": ZONE_COUNT,
        "zones": [raw for raw in raw_zone_rows],
        "shipping_loading_face_side": placement_body.get("shipping_loading_face_side"),
        "shipping_loading_face_segment": {
            "start": {
                "x": _decimal(shipping_face[0][0], field="x") / 1000,
                "y": _decimal(shipping_face[0][1], field="y") / 1000,
            },
            "end": {
                "x": _decimal(shipping_face[1][0], field="x") / 1000,
                "y": _decimal(shipping_face[1][1], field="y") / 1000,
            },
        },
        "portals": portal_records,
        "corridors": corridor_records,
        "access_requirements": [dict(row) for row in requirements],
        "placement_access_observations": [
            _placement_access_observation(
                next(
                    requirement
                    for requirement in requirements
                    if requirement.get("identity") == result.get("requirement_identity")
                ),
                result,
            )
            for result in access_results
        ],
        "access_results": access_results,
        "access_requirement_count": P1_ACCESS_REQUIREMENT_COUNT,
        "access_result_count": len(access_results),
        "access_pass_count": access_pass_count,
        "truck_maneuver_chain": truck_result.get("maneuver_chain", []),
        "truck_envelopes": truck_result.get("truck_envelopes", []),
        "truck_route_status": truck_result.get("status"),
        "truck_route_codes": truck_result.get("codes", []),
        "truck_search_provenance": truck_result.get("search_provenance", {}),
        "personnel_truck_evaluation": interaction,
        "building_footprint": building_payload,
        "route_metrics": {
            "available": True,
            "route_lengths": route_metrics,
            "total_route_length_m": total_route_length,
            "objective_optimization_active": False,
        },
        "warnings": sorted(set(warnings)),
        "routing_implemented": True,
        "access_route_validated": final_access,
        "truck_route_validated": truck_valid,
        "project_layout_validated": project_valid,
        "p2_complete": project_valid,
        "requires_review": True,
    }
    return SiteAccessRoutingResultV1(payload)


validate_site_access_routing = route_site_placement
route_site_layout = route_site_placement
