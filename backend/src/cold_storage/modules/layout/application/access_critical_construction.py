"""Bind access-critical construction hints to existing server-owned authorities."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.application.access_routing import (
    _truck_binding_from_input,
    _verify_truck_binding_matches_handoff,
)
from cold_storage.modules.layout.application.layout_authority_binding import (
    bind_layout_authority,
)
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.application.structural_composition import derive_boundary_side
from cold_storage.modules.layout.domain.access_authority import (
    COLD_ROOM,
    PERSONNEL,
    resolve_access_profile,
)
from cold_storage.modules.layout.domain.access_critical_construction import (
    AccessCriticalConstructionIntentV1,
    AccessCriticalInterfaceV1,
    TruckDockPointEventV1,
)
from cold_storage.modules.layout.domain.access_routing import (
    _pose_mm,
    _segment_lattice_points,
    _translation_for_entry,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import SegmentMM
from cold_storage.modules.layout.domain.truck_maneuver import (
    DOCK_REVERSE,
    BoundTruckManeuverProjectInputV1,
    transform_maneuver_template,
)

_REQUIRED_INTERFACES = (
    ("PERSONNEL_INGRESS_INTERFACE", "main_entrance", "changing_room"),
    (
        "PACKAGING_SORTING_STRAIGHT_INTERFACE",
        "packaging_material_storage",
        "sorting_packaging_room",
    ),
    (
        "SECONDARY_SORTING_ACCESS_INTERFACE",
        "sorting_packaging_room",
        "secondary_fruit_buffer",
    ),
    ("FROZEN_SORTING_ACCESS_INTERFACE", "sorting_packaging_room", "frozen_fruit_room"),
    ("SHIPPING_TRUCK_MANEUVER_INTERFACE", "truck_entrance", "shipping_channel"),
)


def _width_mm(value: object, *, field: str) -> int:
    try:
        millimetres = Decimal(str(value)) * 1000
    except (ArithmeticError, TypeError, ValueError):
        raise LayoutAuthorityError("ACCESS_CRITICAL_AUTHORITY_INVALID", field=field) from None
    if (
        not millimetres.is_finite()
        or millimetres <= 0
        or millimetres != millimetres.to_integral_value()
    ):
        raise LayoutAuthorityError("ACCESS_CRITICAL_AUTHORITY_INVALID", field=field)
    return int(millimetres)


def _coordinate_mm(value: object, *, field: str) -> int:
    try:
        millimetres = Decimal(str(value)) * 1000
    except (ArithmeticError, TypeError, ValueError):
        raise LayoutAuthorityError("ACCESS_CRITICAL_AUTHORITY_INVALID", field=field) from None
    if not millimetres.is_finite() or millimetres != millimetres.to_integral_value():
        raise LayoutAuthorityError("ACCESS_CRITICAL_AUTHORITY_INVALID", field=field)
    return int(millimetres)


def _entrance_segment(value: object, *, field: str) -> SegmentMM:
    if not isinstance(value, Mapping):
        raise LayoutAuthorityError("ACCESS_CRITICAL_SITE_GEOMETRY_INVALID", field=field)
    points: list[tuple[int, int]] = []
    for endpoint in ("start", "end"):
        raw = value.get(endpoint)
        if not isinstance(raw, Mapping):
            raise LayoutAuthorityError("ACCESS_CRITICAL_SITE_GEOMETRY_INVALID", field=field)
        try:
            coordinates = tuple(
                _coordinate_mm(raw[axis], field=f"{field}.{endpoint}.{axis}") for axis in ("x", "y")
            )
        except (KeyError, ArithmeticError, TypeError, ValueError):
            raise LayoutAuthorityError(
                "ACCESS_CRITICAL_SITE_GEOMETRY_INVALID", field=field
            ) from None
        points.append((coordinates[0], coordinates[1]))
    if points[0] == points[1]:
        raise LayoutAuthorityError("ACCESS_CRITICAL_SITE_GEOMETRY_INVALID", field=field)
    return points[0], points[1]


def _interface_rows(
    requirements: tuple[Mapping[str, Any], ...],
    relationships: tuple[Mapping[str, Any], ...],
) -> tuple[AccessCriticalInterfaceV1, ...]:
    relationship_by_id = {
        str(row["identity"]): row for row in relationships if isinstance(row.get("identity"), str)
    }
    output: list[AccessCriticalInterfaceV1] = []
    for kind, source, target in _REQUIRED_INTERFACES:
        matches = [
            row
            for row in requirements
            if row.get("from_ref") == source and row.get("to_ref") == target
        ]
        if len(matches) != 1:
            raise LayoutAuthorityError(
                "ACCESS_CRITICAL_AUTHORITY_INVALID",
                interface=kind,
                match_count=len(matches),
            )
        row = matches[0]
        relation_id = row.get("edge_orientation_requirement")
        relation = relationship_by_id.get(str(relation_id)) if relation_id else None
        is_truck = row.get("flow_kind") == "TRUCK"
        portal_width: int | None = None
        corridor_width: int | None = None
        if not is_truck:
            profile = resolve_access_profile(str(row.get("profile_identity")))
            portal_width = _width_mm(profile.portal_clear_width_m, field="portal_clear_width_m")
            corridor_width = _width_mm(
                profile.corridor_clear_width_m, field="corridor_clear_width_m"
            )
            cold_room_refs = row.get("cold_room_refs", ())
            if cold_room_refs:
                portal_width = max(
                    portal_width,
                    _width_mm(
                        resolve_access_profile(COLD_ROOM).portal_clear_width_m,
                        field="cold_room_portal_clear_width_m",
                    ),
                )
        output.append(
            AccessCriticalInterfaceV1(
                interface_kind=kind,
                requirement_identity=str(row["identity"]),
                from_ref=source,
                to_ref=target,
                flow_kind=str(row["flow_kind"]),
                route_shape_constraint=str(row["route_shape_constraint"]),
                edge_orientation_requirement=(str(relation_id) if relation_id else None),
                from_edge_class=(
                    str(relation["from_edge_class"])
                    if relation and relation.get("from_edge_class") is not None
                    else None
                ),
                to_edge_class=(
                    str(relation["to_edge_class"])
                    if relation and relation.get("to_edge_class") is not None
                    else None
                ),
                portal_clear_width_mm=portal_width,
                corridor_clear_width_mm=corridor_width,
                construction_preference={
                    "PERSONNEL_INGRESS_INTERFACE": "ENTRANCE_FACING_CLEAR_CHANNEL",
                    "PACKAGING_SORTING_STRAIGHT_INTERFACE": (
                        "AUTHORITY_EDGE_CLASS_STRAIGHT_COMPATIBILITY"
                    ),
                    "SECONDARY_SORTING_ACCESS_INTERFACE": (
                        "SORTING_BRANCH_PORTAL_AND_CLEAR_DEPARTURE"
                    ),
                    "FROZEN_SORTING_ACCESS_INTERFACE": (
                        "SORTING_BRANCH_PORTAL_AND_CLEAR_DEPARTURE"
                    ),
                    "SHIPPING_TRUCK_MANEUVER_INTERFACE": "AUTHORITATIVE_DOCK_EVENT_FACE_ALIGNMENT",
                }[kind],
            )
        )
    return tuple(output)


def _dock_events(
    binding: BoundTruckManeuverProjectInputV1,
    entrance: SegmentMM,
) -> tuple[TruckDockPointEventV1, ...]:
    project = binding.maneuver_project_input.require_complete()
    templates = tuple(
        template
        for template in project.template_set.templates
        if template.maneuver_class == DOCK_REVERSE and template.final_dock_pose is not None
    )
    events: dict[tuple[int, int, int, int, str], TruckDockPointEventV1] = {}
    for template in templates:
        for entry in _segment_lattice_points(entrance):
            for rotation in (0, 90, 180, 270):
                transformed = transform_maneuver_template(
                    template,
                    _translation_for_entry(template, entry, rotation),
                    rotation,
                )
                final_pose = transformed.get("final_dock_pose")
                if not isinstance(final_pose, Mapping):
                    continue
                point = _pose_mm(final_pose)[:2]
                event = TruckDockPointEventV1(
                    point_mm=(point[0], point[1]),
                    truck_entrance_event_mm=entry,
                    template_identity=template.identity,
                    template_rotation_deg=rotation,
                )
                events[
                    (point[0], point[1], rotation, entry[0], f"{entry[1]}:{template.identity}")
                ] = event
    return tuple(events[key] for key in sorted(events))


def build_access_critical_construction_intent(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: object,
    site_geometry: ValidatedSiteGeometryV1,
    truck_maneuver_binding: BoundTruckManeuverProjectInputV1 | Mapping[str, Any],
) -> AccessCriticalConstructionIntentV1:
    """Derive construction-only interface intents from validated server authorities."""
    binding = bind_layout_authority(canonical_zone_plan, p1_handoff, site_geometry)
    truck_binding = _truck_binding_from_input(truck_maneuver_binding)
    if truck_binding is None:
        raise LayoutAuthorityError("INVALID_TRUCK_MANEUVER_PROJECT_BINDING")
    _verify_truck_binding_matches_handoff(truck_binding, binding.p1_body)
    body = site_geometry.to_dict()
    site = body.get("site")
    entrances = body.get("entrances")
    if not isinstance(site, Mapping) or not isinstance(entrances, Mapping):
        raise LayoutAuthorityError("ACCESS_CRITICAL_SITE_GEOMETRY_INVALID")
    main_raw = entrances.get("main_entrance")
    truck_raw = entrances.get("truck_entrance")
    if not isinstance(main_raw, Mapping) or not isinstance(truck_raw, Mapping):
        raise LayoutAuthorityError("ACCESS_CRITICAL_SITE_GEOMETRY_INVALID")
    main_segment = _entrance_segment(main_raw, field="main_entrance")
    truck_segment = _entrance_segment(truck_raw, field="truck_entrance")
    boundary = site.get("site_boundary")
    if not isinstance(boundary, Mapping):
        raise LayoutAuthorityError("ACCESS_CRITICAL_SITE_GEOMETRY_INVALID", field="site_boundary")
    main_side = derive_boundary_side(main_raw, boundary).value
    truck_side = derive_boundary_side(truck_raw, boundary).value
    interfaces = _interface_rows(binding.access_requirements, binding.spatial_relationships)
    personnel = resolve_access_profile(PERSONNEL)
    main_half_width = _width_mm(personnel.corridor_clear_width_m, field="personnel_corridor") // 2
    loading_side = site.get("preferred_loading_side")
    if not isinstance(loading_side, str) or not loading_side:
        raise LayoutAuthorityError(
            "ACCESS_CRITICAL_SITE_GEOMETRY_INVALID", field="preferred_loading_side"
        )
    face_order = (
        (
            "changing_room",
            tuple(dict.fromkeys((main_side, "NORTH", "SOUTH", "EAST", "WEST"))),
        ),
        ("packaging_material_storage", ("NORTH", "SOUTH", "EAST", "WEST")),
        ("secondary_fruit_buffer", ("NORTH", "SOUTH", "EAST", "WEST")),
        ("frozen_fruit_room", ("NORTH", "SOUTH", "EAST", "WEST")),
        (
            "shipping_channel",
            tuple(dict.fromkeys((truck_side, loading_side, "NORTH", "SOUTH", "EAST", "WEST"))),
        ),
    )
    return AccessCriticalConstructionIntentV1(
        identity="access-critical-construction-intent@1.0.0",
        schema_version="1.0.0",
        interfaces=interfaces,
        main_entrance_segment_mm=main_segment,
        main_entrance_corridor_half_width_mm=main_half_width,
        truck_entrance_segment_mm=truck_segment,
        truck_dock_point_events=_dock_events(truck_binding, truck_segment),
        preferred_role_face_order=face_order,
        preferred_loading_side=loading_side,
        source_p1_handoff_hash=binding.p1_handoff_hash,
        source_site_geometry_hash=binding.site_geometry_hash,
    )
