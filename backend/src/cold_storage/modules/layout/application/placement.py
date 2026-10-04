"""Bind authoritative P1/site inputs to the P2C placement search.

The application boundary validates that the supplied objects are the current
server-owned replay of the canonical zone plan and P1 project handoff.  The
domain search then only places already-approved rectangles and selects sizes
for the three explicitly flexible zones.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.domain.access_authority import (
    COLD_ROOM,
    PACKAGING,
    resolve_access_profile,
)
from cold_storage.modules.layout.domain.access_routing import (
    DEFAULT_ROUTE_NODE_BUDGET,
    DEFAULT_TRUCK_NODE_BUDGET,
    _boundary_interior_point,
    _edge_class,
    _edge_options,
    _portal_center,
    route_access_requirement,
)
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.objective_profile import (
    ObjectiveProfileV1,
    approved_objective_profile,
    validate_objective_profile,
)
from cold_storage.modules.layout.domain.placement import (
    LEGACY_COMPAT_PHASE,
    STRUCTURED_PHASE,
    PlacementCandidateEnumerationV1,
    SitePlacementResultV1,
    search_placement,
)
from cold_storage.modules.layout.domain.placement import (
    enumerate_placement_candidates as enumerate_domain_placement_candidates,
)
from cold_storage.modules.layout.domain.site_geometry import (
    normalize_polygon,
    normalize_segment,
)
from cold_storage.modules.layout.domain.structural_composition import (
    StructuralCompositionFamilyV1,
)
from cold_storage.modules.layout.domain.truck_maneuver import (
    BoundTruckManeuverProjectInputV1,
)

IDENTITY = "site-constrained-placement-application@1.0.0"
P1_HANDOFF_IDENTITY = "p1-project-access-handoff@1.0.0"
P1_HANDOFF_SCHEMA_VERSION = "1.0.0"
DIMENSION_HANDOFF_IDENTITY = "hybrid_zone_dimension_handoff@1.0.0"
ZONE_PLAN_IDENTITY = "cold_room_zone_plan@1.0.0"
FLEXIBLE_ZONES = frozenset({"coating_room", "changing_room", "office"})
P1_ACCESS_REQUIREMENT_COUNT = 12


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("PLACEMENT_AUTHORITY_INVALID", field=field)
    return value


def _main_entrance_route_start_points(
    site_geometry: ValidatedSiteGeometryV1,
    access_requirements: tuple[Mapping[str, Any], ...],
) -> tuple[tuple[int, int], ...]:
    """Derive exact entrance-side corridor start events from routing primitives.

    These points only order finite construction candidates.  The injected
    ``route_access_requirement`` remains the sole route admission authority.
    """
    requirement = next(
        (
            row
            for row in access_requirements
            if row.get("from_ref") == "main_entrance" and row.get("to_ref") == "changing_room"
        ),
        None,
    )
    if requirement is None:
        return ()
    profile_identity = requirement.get("profile_identity")
    if not isinstance(profile_identity, str):
        return ()
    profile = resolve_access_profile(profile_identity)
    body = site_geometry.to_dict()
    site = _mapping(body.get("site"), field="site")
    entrances = _mapping(body.get("entrances"), field="entrances")
    boundary = normalize_polygon(
        site.get("effective_buildable_boundary"), allow_numeric_string=True
    )
    raw_entrance = entrances.get("main_entrance")
    normalized_entrance: object = raw_entrance
    if isinstance(raw_entrance, Mapping):
        normalized_entrance = {
            endpoint: {
                axis: Decimal(str(value)) for axis, value in point.items() if axis in {"x", "y"}
            }
            if isinstance(point, Mapping)
            else point
            for endpoint, point in raw_entrance.items()
        }
    entrance = normalize_segment(normalized_entrance, error_code="INVALID_SITE_GEOMETRY_RESULT")
    portal_width_mm = int(profile.portal_clear_width_m * Decimal(1000))
    corridor_width_mm = int(profile.corridor_clear_width_m * Decimal(1000))
    portal_options = _edge_options(
        None,
        required_class=None,
        clear_width_mm=portal_width_mm,
        boundary_segment=entrance,
    )
    points = {
        _boundary_interior_point(
            _portal_center(option["segment_mm"]),
            entrance,
            boundary,
            corridor_width_mm // 2,
        )
        for option in portal_options
    }
    return tuple(sorted(points))


def _p1_body(handoff: object) -> tuple[dict[str, Any], str]:
    if isinstance(handoff, ZoneDimensioningResultV1):
        body = handoff.to_dict()
        return body, handoff.canonical_result_hash
    if isinstance(handoff, Mapping):
        body = dict(handoff)
        return body, canonical_hash(body)
    raise _error("P1_HANDOFF_AUTHORITY_REQUIRED")


def _validate_p1_authority(
    zone_plan: Mapping[str, Any],
    handoff: object,
    geometry: ValidatedSiteGeometryV1,
) -> tuple[
    dict[str, Any],
    str,
    dict[str, Mapping[str, Any]],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
]:
    if not geometry._is_authoritative():
        raise _error("INVALID_SITE_GEOMETRY_RESULT", reason="UNVERIFIED_GEOMETRY_RESULT")
    body, handoff_hash = _p1_body(handoff)
    if (
        body.get("identity") != P1_HANDOFF_IDENTITY
        or body.get("schema_version") != P1_HANDOFF_SCHEMA_VERSION
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID")
    status = _mapping(body.get("authority_status"), field="authority_status")
    required_status = (
        "dimension_authority_complete",
        "personnel_access_authority_complete",
        "material_access_authority_complete",
        "truck_access_contract_complete",
        "truck_project_input_contract_complete",
        "p1_complete",
    )
    if any(status.get(key) is not True for key in required_status):
        raise _error("P1_HANDOFF_NOT_COMPLETE", fields=list(required_status))
    if body.get("p1_closure_blockers") != [] or body.get("p2_implemented") is not False:
        raise _error("P1_HANDOFF_NOT_COMPLETE")

    geometry_body = geometry.to_dict()
    if geometry_body.get("source_p1_handoff_hash") != handoff_hash:
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH")

    historical = _mapping(body.get("p1e_historical_handoff"), field="p1e_historical_handoff")
    if body.get("p1e_historical_handoff_hash") != canonical_hash(historical):
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH", field="p1e_historical_handoff_hash")
    dimension = _mapping(historical.get("dimension_handoff"), field="dimension_handoff")
    if dimension.get("calculator_identity") != DIMENSION_HANDOFF_IDENTITY:
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="dimension_handoff")
    if dimension.get("source_zone_plan_calculator_identity") != ZONE_PLAN_IDENTITY:
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    if dimension.get("source_zone_plan_result_hash") != canonical_hash(zone_plan):
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH", field="source_zone_plan_result_hash")
    graph = process_graph()
    if canonical_json(dimension.get("adjacency_graph")) != canonical_json(asdict(graph)):
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH", field="adjacency_graph")

    authorities_raw = dimension.get("authorities")
    if not isinstance(authorities_raw, list) or any(
        not isinstance(row, Mapping) for row in authorities_raw
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="authorities")
    authorities = {str(row["zone_code"]): row for row in authorities_raw if "zone_code" in row}
    if set(authorities) != set(ZONE_CODES) or len(authorities) != len(authorities_raw):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="authorities")
    if not all(
        authorities[code].get("dimension_mode") == "FLEXIBLE_RECTANGLE" for code in FLEXIBLE_ZONES
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="flexible_authorities")
    for code in FLEXIBLE_ZONES:
        authority = authorities[code]
        if (
            authority.get("status") != "FLEXIBLE_AUTHORIZED"
            or authority.get("p2_may_select_width_depth") is not True
        ):
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field=code)
        if authority.get("p2_may_change_required_area") is not False:
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field=code)
    concrete = [code for code in authorities if code not in FLEXIBLE_ZONES]
    if any(authorities[code].get("status") != "DIMENSIONED" for code in concrete):
        raise _error("P1_HANDOFF_NOT_COMPLETE", field="concrete_dimensions")
    dimensions = dimension.get("dimensions")
    if not isinstance(dimensions, list) or {
        row.get("zone_code") for row in dimensions if isinstance(row, Mapping)
    } != set(concrete):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="dimensions")
    raw_access_requirements = historical.get("access_requirements")
    if not isinstance(raw_access_requirements, list):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
    if len(raw_access_requirements) != P1_ACCESS_REQUIREMENT_COUNT:
        raise _error(
            "P1_HANDOFF_IDENTITY_INVALID",
            field="access_requirements",
            expected_count=P1_ACCESS_REQUIREMENT_COUNT,
        )
    required_access_fields = {
        "identity",
        "from_ref",
        "to_ref",
        "flow_kind",
        "access_class",
        "profile_identity",
        "portal_required",
        "corridor_allowed",
        "direct_allowed",
        "edge_orientation_requirement",
        "route_shape_constraint",
    }
    access_requirements: list[Mapping[str, Any]] = []
    access_keys: set[tuple[object, object, object]] = set()
    access_identities: set[str] = set()
    for requirement in raw_access_requirements:
        if not isinstance(requirement, Mapping) or not required_access_fields <= set(requirement):
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
        identity = requirement.get("identity")
        from_ref = requirement.get("from_ref")
        to_ref = requirement.get("to_ref")
        flow_kind = requirement.get("flow_kind")
        if (
            not isinstance(identity, str)
            or not isinstance(from_ref, str)
            or not isinstance(to_ref, str)
            or not isinstance(flow_kind, str)
            or identity in access_identities
        ):
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
        key = (from_ref, to_ref, flow_kind)
        if key in access_keys:
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
        access_identities.add(identity)
        access_keys.add(key)
        access_requirements.append(dict(requirement))
    raw_spatial_relationships = historical.get("spatial_relationships")
    if not isinstance(raw_spatial_relationships, list) or any(
        not isinstance(row, Mapping) for row in raw_spatial_relationships
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="spatial_relationships")
    spatial_relationships = tuple(dict(row) for row in raw_spatial_relationships)
    return (
        body,
        handoff_hash,
        {code: authorities[code] for code in ZONE_CODES},
        tuple(access_requirements),
        spatial_relationships,
    )


def _validated_objective_profile(
    source: ObjectiveProfileV1 | Mapping[str, object] | None,
) -> tuple[ObjectiveProfileV1, str]:
    approved = approved_objective_profile()
    if source is None:
        return approved, approved.canonical_result_hash
    if isinstance(source, ObjectiveProfileV1):
        if source.canonical_json() != approved.canonical_json():
            raise _error("OBJECTIVE_PROFILE_IDENTITY_INVALID")
        return approved, approved.canonical_result_hash
    profile = validate_objective_profile(source)
    return profile, profile.canonical_result_hash


def _structured_construction_access_requirements(
    access_requirements: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    """Pass frozen profile widths only to the structured construction ordering.

    The generic access-requirement objects remain byte-for-byte compatible for
    the legacy and GENERAL_FALLBACK phases. These derived fields are private
    search hints; P2D continues to resolve and validate the original profile.
    """
    profile = resolve_access_profile(PACKAGING)
    rows: list[Mapping[str, Any]] = []
    for requirement in access_requirements:
        if (
            requirement.get("from_ref") == "packaging_material_storage"
            and requirement.get("to_ref") == "sorting_packaging_room"
            and requirement.get("profile_identity") == PACKAGING
        ):
            rows.append(
                {
                    **requirement,
                    "construction_portal_clear_width_m": str(profile.portal_clear_width_m),
                    "construction_corridor_clear_width_m": str(profile.corridor_clear_width_m),
                }
            )
        else:
            rows.append(requirement)
    return tuple(rows)


def place_zones(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    objective_profile: ObjectiveProfileV1 | Mapping[str, object] | None = None,
    *,
    node_budget: int = 50_000,
    complete_candidate_limit: int | None = None,
) -> SitePlacementResultV1:
    """Place all canonical zones within a validated site when the finite search finds one."""
    if not isinstance(canonical_zone_plan, Mapping):
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    if (
        canonical_zone_plan.get("success") is not True
        or canonical_zone_plan.get("calculator_name") != "cold_room_zone_plan"
        or canonical_zone_plan.get("calculator_version") != "1.0.0"
    ):
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    _, handoff_hash, authorities, access_requirements, spatial_relationships = (
        _validate_p1_authority(canonical_zone_plan, p1_handoff, site_geometry)
    )
    profile, profile_hash = _validated_objective_profile(objective_profile)
    geometry_body = site_geometry.to_dict()
    return search_placement(
        authorities,
        geometry_body,
        process_graph(),
        source_zone_plan_hash=canonical_hash(canonical_zone_plan),
        source_p1_handoff_hash=handoff_hash,
        source_site_geometry_hash=site_geometry.canonical_result_hash,
        objective_profile_hash=profile_hash,
        access_requirements=access_requirements,
        spatial_relationships=spatial_relationships,
        node_budget=node_budget,
        complete_candidate_limit=complete_candidate_limit,
    )


# The name mirrors the P2C task language and is kept as a small public alias;
# both names execute the same authority-bound application path.
calculate_site_placement = place_zones


def enumerate_placement_candidates(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    objective_profile: ObjectiveProfileV1 | Mapping[str, object] | None = None,
    *,
    node_budget: int = 50_000,
    truck_maneuver_binding: BoundTruckManeuverProjectInputV1 | Mapping[str, Any] | None = None,
    truck_node_budget: int = DEFAULT_TRUCK_NODE_BUDGET,
    truck_maneuver_validator: Callable[..., Mapping[str, Any]] | None = None,
    complete_candidate_limit: int | None = None,
    structural_family: StructuralCompositionFamilyV1 | None = None,
    structural_topology: str | None = None,
    search_phase: str = LEGACY_COMPAT_PHASE,
    direct_synthesis_enabled: bool = True,
    global_main_process_geometry_registry: dict[str, dict[str, Any]] | None = None,
    global_cross_topology_duplicate_trace: list[dict[str, Any]] | None = None,
) -> PlacementCandidateEnumerationV1:
    """Expose complete P2C candidates for downstream P2 validation.

    This verifies the same P1 authority and site inputs as :func:`place_zones`,
    then delegates to the domain's deterministic candidate stream. When a
    bound truck input is supplied, the structured Tool 7 path may use the
    existing truck maneuver validator only as a necessary-condition preflight
    on a frozen main-process skeleton; complete candidates still go through
    the unchanged P2D application validation.
    """
    if not isinstance(canonical_zone_plan, Mapping):
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    if (
        canonical_zone_plan.get("success") is not True
        or canonical_zone_plan.get("calculator_name") != "cold_room_zone_plan"
        or canonical_zone_plan.get("calculator_version") != "1.0.0"
    ):
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    _, handoff_hash, authorities, access_requirements, spatial_relationships = (
        _validate_p1_authority(canonical_zone_plan, p1_handoff, site_geometry)
    )
    _, profile_hash = _validated_objective_profile(objective_profile)
    construction_access_requirements = (
        _structured_construction_access_requirements(access_requirements)
        if search_phase == STRUCTURED_PHASE
        else access_requirements
    )
    entrance_route_start_points = (
        _main_entrance_route_start_points(site_geometry, construction_access_requirements)
        if search_phase == STRUCTURED_PHASE
        else ()
    )

    construction_access_route_validator: (
        Callable[..., tuple[Mapping[str, Any], tuple[Any, ...]]] | None
    ) = None
    construction_access_portal_event_provider: Callable[..., Mapping[str, Any]] | None = None
    if search_phase == STRUCTURED_PHASE:

        def validate_construction_route(
            requirement: Mapping[str, Any],
            *,
            relationships: Mapping[str, Mapping[str, Any]],
            zones: Mapping[str, Any],
            boundary: Any,
            obstacles: Any,
            entrances: Mapping[str, Any],
        ) -> tuple[dict[str, Any], tuple[Any, ...]]:
            return route_access_requirement(
                requirement,
                relationships=relationships,
                zones=zones,
                boundary=boundary,
                obstacles=obstacles,
                entrances=entrances,
                route_node_budget=DEFAULT_ROUTE_NODE_BUDGET,
            )

        construction_access_route_validator = validate_construction_route

        spatial_by_identity = {
            str(row["identity"]): row
            for row in spatial_relationships
            if isinstance(row.get("identity"), str)
        }

        def construction_access_portal_events(
            requirement: Mapping[str, Any],
            endpoint_ref: str,
            rectangle: Any,
        ) -> Mapping[str, Any]:
            """Expose the routing authority's exact portal events to construction.

            These events order construction candidates only. The injected
            ``route_access_requirement`` remains the admission authority.
            """
            profile_identity = requirement.get("profile_identity")
            if not isinstance(profile_identity, str):
                return {"portals": (), "portal_clear_width_mm": 0, "corridor_clear_width_mm": 0}
            profile = resolve_access_profile(profile_identity)
            portal_width_mm = int(profile.portal_clear_width_m * Decimal(1000))
            if endpoint_ref in requirement.get("cold_room_refs", ()):
                cold_identity = requirement.get("cold_room_portal_profile_identity") or COLD_ROOM
                cold_profile = resolve_access_profile(str(cold_identity))
                portal_width_mm = max(
                    portal_width_mm,
                    int(cold_profile.portal_clear_width_m * Decimal(1000)),
                )
            relationship_identity = requirement.get("edge_orientation_requirement")
            relationship = (
                spatial_by_identity.get(str(relationship_identity))
                if relationship_identity is not None
                else None
            )
            expected_edge_class = _edge_class(
                relationship.get(
                    "from_edge_class"
                    if endpoint_ref == requirement.get("from_ref")
                    else "to_edge_class"
                )
                if relationship is not None
                else None
            )
            options = _edge_options(
                rectangle,
                required_class=expected_edge_class,
                clear_width_mm=portal_width_mm,
            )
            left, bottom, right, top = rectangle.bounds_mm
            portals = []
            for option in options:
                (x0, y0), (x1, y1) = option["segment_mm"]
                side = (
                    "WEST"
                    if x0 == x1 == left
                    else "EAST"
                    if x0 == x1 == right
                    else "SOUTH"
                    if y0 == y1 == bottom
                    else "NORTH"
                    if y0 == y1 == top
                    else None
                )
                if side is not None:
                    portals.append(
                        {
                            "side": side,
                            "edge_class": option["edge_class"],
                            "segment_mm": option["segment_mm"],
                            "center_mm": _portal_center(option["segment_mm"]),
                            "clear_width_mm": portal_width_mm,
                        }
                    )
            return {
                "portals": tuple(portals),
                "portal_clear_width_mm": portal_width_mm,
                "corridor_clear_width_mm": int(profile.corridor_clear_width_m * Decimal(1000)),
            }

        construction_access_portal_event_provider = construction_access_portal_events
    return enumerate_domain_placement_candidates(
        authorities,
        site_geometry.to_dict(),
        process_graph(),
        source_zone_plan_hash=canonical_hash(canonical_zone_plan),
        source_p1_handoff_hash=handoff_hash,
        source_site_geometry_hash=site_geometry.canonical_result_hash,
        objective_profile_hash=profile_hash,
        access_requirements=construction_access_requirements,
        spatial_relationships=spatial_relationships,
        node_budget=node_budget,
        truck_maneuver_binding=truck_maneuver_binding,
        truck_node_budget=truck_node_budget,
        truck_maneuver_validator=truck_maneuver_validator,
        access_route_validator=construction_access_route_validator,
        access_portal_event_provider=construction_access_portal_event_provider,
        main_entrance_route_start_points=entrance_route_start_points,
        complete_candidate_limit=complete_candidate_limit,
        structural_family=structural_family,
        structural_topology=structural_topology,
        search_phase=search_phase,
        direct_synthesis_enabled=direct_synthesis_enabled,
        global_main_process_geometry_registry=global_main_process_geometry_registry,
        global_cross_topology_duplicate_trace=global_cross_topology_duplicate_trace,
    )
