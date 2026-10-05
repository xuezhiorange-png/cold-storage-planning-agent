"""Bounded rectangle placement constrained by whole-building composition intent.

This module produces exact rectangle candidates only.  Construction domains are
search organizers, not site/access/Truck engineering authorities.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from math import isqrt
from typing import Any

from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.composition_handoff import (
    StructuralCompositionPlacementHandoffV1,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    normalize_polygon,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
    validate_flexible_candidate,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CompositionFamilyV2,
    ProcessAxisV1,
    ProcessDirectionV1,
)

IDENTITY = "composition-constrained-exact-placement@1.0.0"
SCHEMA_VERSION = "1.0.0"
CONSTRUCTION_DOMAIN_IS_HARD_ENGINEERING_AUTHORITY = False
PLACEMENT_HARD_SCOPE = "SITE_DIMENSIONS_OVERLAP_MUST_ADJACENCY_ONLY"
ACCESS_STATUS = "PENDING_ROUTE_VALIDATION"
FAMILY_ORDER = (
    CompositionFamilyV2.LINEAR_BANDED,
    CompositionFamilyV2.CENTRAL_PROCESS_CORE,
    CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS,
)
DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET = 60_000
MAX_COMPOSITION_PLACEMENT_NODE_BUDGET = DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET
GRID_MM = 1


@dataclass(frozen=True)
class ConstructionDomainV1:
    """Finite event-derived search domain for one band or peripheral domain."""

    domain_id: str
    zone_roles: tuple[str, ...]
    domain_kind: str
    reference_axis: str
    preferred_interval_mm: tuple[int, int] | None
    preferred_face: str
    origin_event_policy: str
    engineering_authority: bool = False


@dataclass(frozen=True)
class CompositionPlacementCandidateV1:
    identity: str
    schema_version: str
    composition_identity: str
    composition_signature: str
    family: CompositionFamilyV2
    process_axis: ProcessAxisV1
    process_direction: ProcessDirectionV1
    zones: tuple[PlacedRectangleV1, ...]
    zone_count: int
    placement_scope: str
    hard_constraints_passed: bool
    site_valid: bool
    dimension_valid: bool
    non_overlap_valid: bool
    must_adjacency_valid: bool
    must_adjacency_satisfied_count: int
    composition_intent_preserved: bool
    construction_domains: tuple[ConstructionDomainV1, ...]
    source_zone_plan_hash: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    search_provenance: tuple[tuple[str, str], ...]
    access_validation_status: str = ACCESS_STATUS
    access_routing_performed: bool = False
    truck_validation_performed: bool = False
    p2d_performed: bool = False
    project_layout_validated_claimed: bool = False
    p2_complete_claimed: bool = False
    legacy_fallback_used: bool = False

    def __post_init__(self) -> None:
        roles = tuple(zone.zone_code for zone in self.zones)
        if self.identity != IDENTITY or self.schema_version != SCHEMA_VERSION:
            raise ValueError("UNSUPPORTED_COMPOSITION_PLACEMENT_CANDIDATE")
        if len(roles) != len(ZONE_CODES) or set(roles) != set(ZONE_CODES):
            raise ValueError("COMPOSITION_PLACEMENT_ROLE_COVERAGE_INVALID")
        if len(set(roles)) != len(roles) or self.zone_count != len(roles):
            raise ValueError("COMPOSITION_PLACEMENT_ROLE_DUPLICATE")
        if self.placement_scope != PLACEMENT_HARD_SCOPE:
            raise ValueError("COMPOSITION_PLACEMENT_SCOPE_INVALID")
        if not all(
            (
                self.hard_constraints_passed,
                self.site_valid,
                self.dimension_valid,
                self.non_overlap_valid,
                self.must_adjacency_valid,
                self.composition_intent_preserved,
            )
        ):
            raise ValueError("COMPOSITION_PLACEMENT_CANDIDATE_NOT_HARD_VALID")
        if self.must_adjacency_satisfied_count != len(process_graph().must_adjacencies):
            raise ValueError("COMPOSITION_PLACEMENT_MUST_ADJACENCY_INVALID")
        if any(domain.engineering_authority for domain in self.construction_domains):
            raise ValueError("CONSTRUCTION_DOMAIN_AUTHORITY_FORBIDDEN")
        if (
            self.access_validation_status != ACCESS_STATUS
            or self.access_routing_performed
            or self.truck_validation_performed
            or self.p2d_performed
            or self.project_layout_validated_claimed
            or self.p2_complete_claimed
            or self.legacy_fallback_used
        ):
            raise ValueError("COMPOSITION_PLACEMENT_SCOPE_VIOLATION")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["zones"] = [zone.to_dict() for zone in self.zones]
        result["family"] = self.family.value
        result["process_axis"] = self.process_axis.value
        result["process_direction"] = self.process_direction.value
        return result

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


@dataclass(frozen=True)
class CompositionPlacementSearchAttemptV1:
    family: CompositionFamilyV2
    composition_identity: str
    composition_signature: str
    process_axis: ProcessAxisV1
    process_direction: ProcessDirectionV1
    peripheral_bank_sign: int
    construction_domains: tuple[ConstructionDomainV1, ...]
    nodes_allocated: int
    nodes_visited: int
    deepest_role_reached: str
    node_budget_exhausted: bool
    complete_layout_found: bool
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "composition_identity": self.composition_identity,
            "composition_signature": self.composition_signature,
            "process_axis": self.process_axis.value,
            "process_direction": self.process_direction.value,
            "peripheral_bank_sign": self.peripheral_bank_sign,
            "construction_domains": [asdict(domain) for domain in self.construction_domains],
            "nodes_allocated": self.nodes_allocated,
            "nodes_visited": self.nodes_visited,
            "deepest_role_reached": self.deepest_role_reached,
            "node_budget_exhausted": self.node_budget_exhausted,
            "complete_layout_found": self.complete_layout_found,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class CompositionPlacementEnumerationV1:
    identity: str
    schema_version: str
    node_budget: int
    nodes_used: int
    node_budget_exhausted: bool
    family_coverage_order: tuple[str, ...]
    family_first_round_complete: bool
    attempt_count_by_family: tuple[tuple[str, int], ...]
    nodes_used_by_family: tuple[tuple[str, int], ...]
    deepest_role_reached_by_family: tuple[tuple[str, str], ...]
    failure_reason_by_family: tuple[tuple[str, str], ...]
    search_attempts: tuple[CompositionPlacementSearchAttemptV1, ...]
    candidates: tuple[CompositionPlacementCandidateV1, ...]
    exact_placement_performed: bool = True
    access_routing_performed: bool = False
    truck_validation_performed: bool = False
    p2d_performed: bool = False
    project_layout_validated_claimed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "schema_version": self.schema_version,
            "node_budget": self.node_budget,
            "nodes_used": self.nodes_used,
            "node_budget_exhausted": self.node_budget_exhausted,
            "family_coverage_order": list(self.family_coverage_order),
            "family_first_round_complete": self.family_first_round_complete,
            "attempt_count_by_family": dict(self.attempt_count_by_family),
            "nodes_used_by_family": dict(self.nodes_used_by_family),
            "deepest_role_reached_by_family": dict(self.deepest_role_reached_by_family),
            "failure_reason_by_family": dict(self.failure_reason_by_family),
            "search_attempts": [attempt.to_dict() for attempt in self.search_attempts],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "exact_placement_performed": self.exact_placement_performed,
            "access_routing_performed": self.access_routing_performed,
            "truck_validation_performed": self.truck_validation_performed,
            "p2d_performed": self.p2d_performed,
            "project_layout_validated_claimed": self.project_layout_validated_claimed,
        }


@dataclass(frozen=True)
class _Shape:
    width_mm: int
    depth_mm: int
    rotation_deg: int

    @property
    def world_width_mm(self) -> int:
        return self.depth_mm if self.rotation_deg == 90 else self.width_mm

    @property
    def world_depth_mm(self) -> int:
        return self.width_mm if self.rotation_deg == 90 else self.depth_mm


def _mm(value: object) -> int:
    number = Decimal(str(value))
    if (
        not number.is_finite()
        or number <= 0
        or number * 1000 != (number * 1000).to_integral_value()
    ):
        raise ValueError("INVALID_AUTHORITATIVE_DIMENSION")
    return int(number * 1000)


def _m(value: int) -> Decimal:
    return Decimal(value) / 1000


def _rectangle(code: str, x: int, y: int, shape: _Shape) -> PlacedRectangleV1:
    return PlacedRectangleV1(
        code,
        _m(x),
        _m(y),
        _m(shape.width_mm),
        _m(shape.depth_mm),
        shape.rotation_deg,
    )


def _authority_shapes(
    authorities: Mapping[str, Mapping[str, Any]],
    boundary: PolygonMM,
    obstacle_polygons: Sequence[PolygonMM],
) -> dict[str, tuple[_Shape, ...]]:
    spans = {
        abs(second[0] - first[0])
        for polygon in (boundary, *obstacle_polygons)
        for first, second in zip(polygon, polygon[1:] + polygon[:1], strict=True)
        if first[0] != second[0]
    }
    spans.update(
        abs(second[1] - first[1])
        for polygon in (boundary, *obstacle_polygons)
        for first, second in zip(polygon, polygon[1:] + polygon[:1], strict=True)
        if first[1] != second[1]
    )
    fixed_shapes: dict[str, tuple[int, int]] = {}
    for code, authority in authorities.items():
        geometry = authority.get("geometry")
        if authority.get("dimension_mode") == "FLEXIBLE_RECTANGLE":
            continue
        if not isinstance(geometry, Mapping):
            raise ValueError(f"DIMENSION_AUTHORITY_MISSING:{code}")
        fixed = (_mm(geometry.get("width_m")), _mm(geometry.get("depth_m")))
        fixed_shapes[code] = fixed
        spans.update(fixed)

    min_x, min_y = min(p[0] for p in boundary), min(p[1] for p in boundary)
    max_x, max_y = max(p[0] for p in boundary), max(p[1] for p in boundary)
    spans.update((max_x - min_x, max_y - min_y))
    shapes: dict[str, tuple[_Shape, ...]] = {}
    for code, authority in authorities.items():
        rotations = authority.get("rotation_allowed")
        if (
            not isinstance(rotations, list)
            or not rotations
            or any(type(rotation) is not int or rotation not in (0, 90) for rotation in rotations)
        ):
            raise ValueError(f"DIMENSION_AUTHORITY_ROTATION_INVALID:{code}")
        if authority.get("dimension_mode") != "FLEXIBLE_RECTANGLE":
            width, depth = fixed_shapes[code]
            shapes[code] = tuple(_Shape(width, depth, rotation) for rotation in rotations)
            continue
        required = Decimal(str(authority.get("required_area_m2")))
        required_mm2 = int(required * 1_000_000)
        near = isqrt(required_mm2)
        if near * near < required_mm2:
            near += 1
        widths = set(spans) | {near, near + 1}
        candidates: set[tuple[int, int]] = set()
        for width in widths:
            if width <= 0:
                continue
            for depth in widths:
                if depth <= 0:
                    continue
                try:
                    validate_flexible_candidate(authority, _m(width), _m(depth))
                except Exception as exc:
                    if (
                        getattr(exc, "code", None) == "INVALID_FLEXIBLE_DIMENSION"
                        or getattr(exc, "code", None) == "FLEXIBLE_DIMENSION_AREA_UNSATISFIED"
                    ):
                        continue
                    raise
                candidates.add((width, depth))
        if not candidates:
            raise ValueError(f"FLEXIBLE_DIMENSION_DOMAIN_EMPTY:{code}")
        ordered = sorted(
            candidates, key=lambda pair: (abs(pair[0] - pair[1]), pair[0] * pair[1], pair)
        )
        shapes[code] = tuple(
            _Shape(width, depth, rotation) for width, depth in ordered for rotation in rotations
        )
    return shapes


def _bounds(rect: PlacedRectangleV1) -> tuple[int, int, int, int]:
    return rect.bounds_mm


def _center(rect: PlacedRectangleV1, axis: str) -> int:
    left, bottom, right, top = _bounds(rect)
    return (left + right) // 2 if axis == "X" else (bottom + top) // 2


def _axis_events(
    *,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    placed: Mapping[str, PlacedRectangleV1],
    width: int,
    depth: int,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    xs = {point[0] for point in boundary}
    ys = {point[1] for point in boundary}
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    xs.update((min_x, max_x - width, (min_x + max_x - width) // 2))
    ys.update((min_y, max_y - depth, (min_y + max_y - depth) // 2))
    for polygon in obstacles:
        for x, y in polygon:
            # No-build predicates treat obstacle boundaries as closed.  The
            # exact legal event is therefore one grid unit beyond the edge;
            # this is a finite obstacle-derived event, not a coordinate sweep.
            xs.update(
                (
                    x - width - GRID_MM,
                    x - width,
                    x - width + GRID_MM,
                    x - GRID_MM,
                    x,
                    x + GRID_MM,
                )
            )
            ys.update(
                (
                    y - depth - GRID_MM,
                    y - depth,
                    y - depth + GRID_MM,
                    y - GRID_MM,
                    y,
                    y + GRID_MM,
                )
            )
        ox = [p[0] for p in polygon]
        oy = [p[1] for p in polygon]
        xs.update((min(ox) - width, max(ox), min(ox), max(ox) - width))
        ys.update((min(oy) - depth, max(oy), min(oy), max(oy) - depth))
    for rectangle in placed.values():
        left, bottom, right, top = _bounds(rectangle)
        xs.update((left - width, right, left, right - width))
        ys.update((bottom - depth, top, bottom, top - depth))
    return tuple(sorted(xs)), tuple(sorted(ys))


def _anchors_at_must_faces(
    code: str,
    shape: _Shape,
    placed: Mapping[str, PlacedRectangleV1],
    must_neighbors: Sequence[str],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> tuple[tuple[int, int], ...]:
    anchors: set[tuple[int, int]] = set()
    width, depth = shape.world_width_mm, shape.world_depth_mm
    x_events, y_events = _axis_events(
        boundary=boundary,
        obstacles=obstacles,
        placed=placed,
        width=width,
        depth=depth,
    )
    for neighbor_code in must_neighbors:
        neighbor = placed[neighbor_code]
        left, bottom, right, top = _bounds(neighbor)
        y_values = {bottom, top - depth, (bottom + top - depth) // 2}
        y_values.update(y for y in y_events if y < top and y + depth > bottom)
        x_values = {left, right - width, (left + right - width) // 2}
        x_values.update(x for x in x_events if x < right and x + width > left)
        for y in y_values:
            anchors.update(((left - width, y), (right, y)))
        for x in x_values:
            anchors.update(((x, bottom - depth), (x, top)))
    return tuple(sorted(anchors))


def _root_anchors(
    shape: _Shape,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> tuple[tuple[int, int], ...]:
    width, depth = shape.world_width_mm, shape.world_depth_mm
    xs, ys = _axis_events(
        boundary=boundary,
        obstacles=obstacles,
        placed=placed,
        width=width,
        depth=depth,
    )
    min_x, max_x = min(point[0] for point in boundary), max(point[0] for point in boundary)
    min_y, max_y = min(point[1] for point in boundary), max(point[1] for point in boundary)
    center_x = (min_x + max_x - width) // 2
    center_y = (min_y + max_y - depth) // 2
    return tuple(
        sorted(
            {(x, y) for x in xs for y in ys},
            key=lambda point: (
                abs((2 * point[0] + width) - (min_x + max_x))
                + abs((2 * point[1] + depth) - (min_y + max_y)),
                abs(point[0] - center_x) + abs(point[1] - center_y),
                point,
            ),
        )
    )


def _domain_faces(
    handoff: StructuralCompositionPlacementHandoffV1, bank_sign: int
) -> dict[str, tuple[str, int]]:
    axis = handoff.process_axis.value
    cross_axis = "Y" if axis == "X" else "X"
    direction_sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1
    result: dict[str, tuple[str, int]] = {}
    if handoff.family == CompositionFamilyV2.CENTRAL_PROCESS_CORE:
        result["packaging_material_storage"] = (axis, direction_sign)
        result["secondary_fruit_buffer"] = (cross_axis, bank_sign)
        result["frozen_fruit_room"] = (cross_axis, -bank_sign)
        result["changing_room"] = (axis, -direction_sign)
        result["office"] = (axis, -direction_sign)
    else:
        for role in (
            "packaging_material_storage",
            "secondary_fruit_buffer",
            "frozen_fruit_room",
        ):
            result[role] = (cross_axis, bank_sign)
        result["changing_room"] = (cross_axis, -bank_sign)
        result["office"] = (cross_axis, -bank_sign)
    return result


def _domain_arrangement(
    handoff: StructuralCompositionPlacementHandoffV1,
    bank_sign: int,
    boundary: PolygonMM,
    authorities: Mapping[str, Mapping[str, Any]],
) -> tuple[ConstructionDomainV1, ...]:
    axis = handoff.process_axis.value
    cross_axis = "Y" if axis == "X" else "X"
    min_x, max_x = min(p[0] for p in boundary), max(p[0] for p in boundary)
    min_y, max_y = min(p[1] for p in boundary), max(p[1] for p in boundary)
    span = (max_x - min_x) if axis == "X" else (max_y - min_y)
    all_bands = tuple(handoff.principal_band_intents)
    ordered_bands = sorted(
        (item for item in all_bands if item.sequence_index is not None),
        key=lambda item: int(item.sequence_index or 0),
    )
    band_areas = []
    for band in ordered_bands:
        area = sum(
            int(Decimal(str(authorities[role].get("required_area_m2", 0))) * 1_000_000)
            for role in band.zone_roles
        )
        band_areas.append((band, max(1, area)))
    total_area = sum(area for _, area in band_areas) or 1
    cursor = min_x if axis == "X" else min_y
    end = max_x if axis == "X" else max_y
    domains: list[ConstructionDomainV1] = []
    cumulative = 0
    for band, area in band_areas:
        low = cursor + (span * cumulative // total_area)
        cumulative += area
        high = cursor + (span * cumulative // total_area)
        if band == band_areas[-1][0]:
            high = end
        domains.append(
            ConstructionDomainV1(
                domain_id=band.band_id,
                zone_roles=band.zone_roles,
                domain_kind="ORDERED_PRINCIPAL_BAND",
                reference_axis=axis,
                preferred_interval_mm=(low, high),
                preferred_face=band.relative_position,
                origin_event_policy=(
                    "AUTHORITATIVE_DIMENSION_AREA_WEIGHTED_SITE_EVENT_INTERVAL;"
                    "PRIORITY_ONLY_WITH_FULL_SITE_EVENT_FALLBACK"
                ),
            )
        )
    for band in all_bands:
        if band.sequence_index is not None:
            continue
        domains.append(
            ConstructionDomainV1(
                domain_id=band.band_id,
                zone_roles=band.zone_roles,
                domain_kind="NONSEQUENTIAL_CORE_OR_PERIPHERAL_FACE_DOMAIN",
                reference_axis=axis,
                preferred_interval_mm=None,
                preferred_face=band.relative_position,
                origin_event_policy="COMPOSITION_FACE_AND_SITE_ROOM_EDGE_EVENTS",
            )
        )
    faces = _domain_faces(handoff, bank_sign)
    for domain in handoff.peripheral_domain_intents:
        preferred = next(
            (
                ("POSITIVE" if sign > 0 else "NEGATIVE") + f"_{ref_axis}"
                for role, (ref_axis, sign) in faces.items()
                if role in domain.zone_roles
            ),
            domain.relative_side,
        )
        domains.append(
            ConstructionDomainV1(
                domain_id=domain.domain_id,
                zone_roles=domain.zone_roles,
                domain_kind="RESERVED_PERIPHERAL_SEARCH_DOMAIN",
                reference_axis=next(
                    (faces[role][0] for role in domain.zone_roles if role in faces), cross_axis
                ),
                preferred_interval_mm=None,
                preferred_face=preferred,
                origin_event_policy=(
                    "COMPOSITION_FACE_RELATION_WITH_SITE_OBSTACLE_ROOM_EDGE_EVENTS"
                ),
            )
        )
    return tuple(domains)


def _side_ok(
    role: str,
    rectangle: PlacedRectangleV1,
    sorting: PlacedRectangleV1,
    faces: Mapping[str, tuple[str, int]],
) -> bool:
    side = faces.get(role)
    if side is None:
        return True
    axis, sign = side
    delta = _center(rectangle, axis) - _center(sorting, axis)
    return delta * sign > 0


def _candidate_is_clear(
    candidate: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> bool:
    if not rectangle_inside_polygon(candidate, boundary):
        return False
    if any(rectangle_intersects_closed_obstacle(candidate, obstacle) for obstacle in obstacles):
        return False
    return not any(rectangles_overlap(candidate, existing) for existing in placed.values())


def _must_neighbors(code: str) -> tuple[str, ...]:
    return tuple(
        second if first == code else first
        for first, second in process_graph().must_adjacencies
        if code in (first, second)
    )


def _axis_coordinate(rectangle: PlacedRectangleV1, axis: str) -> int:
    return _center(rectangle, axis)


def _intent_preserved(
    handoff: StructuralCompositionPlacementHandoffV1,
    placed: Mapping[str, PlacedRectangleV1],
    faces: Mapping[str, tuple[str, int]],
) -> bool:
    axis = handoff.process_axis.value
    sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1
    sorting = placed["sorting_packaging_room"]
    if any(not _side_ok(role, placed[role], sorting, faces) for role in faces):
        return False
    raw_center = (
        sum(
            _axis_coordinate(placed[role], axis)
            for role in ("raw_fruit_buffer", "primary_precooling_room")
        )
        // 2
    )
    finished_center = (
        sum(
            _axis_coordinate(placed[role], axis)
            for role in ("finished_goods_room", "shipping_channel")
        )
        // 2
    )
    core_center = (
        sum(
            _axis_coordinate(placed[role], axis)
            for role in ("sorting_packaging_room", "secondary_precooling_room", "coating_room")
        )
        // 3
    )
    if handoff.family == CompositionFamilyV2.LINEAR_BANDED:
        return (raw_center - core_center) * sign < 0 and (finished_center - core_center) * sign > 0
    if handoff.family == CompositionFamilyV2.CENTRAL_PROCESS_CORE:
        return (raw_center - _center(sorting, axis)) * sign < 0 and (
            finished_center - _center(sorting, axis)
        ) * sign > 0
    flow = (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    projections = [sign * _axis_coordinate(placed[role], axis) for role in flow]
    return all(first <= second for first, second in zip(projections, projections[1:], strict=False))


def _zone_order(handoff: StructuralCompositionPlacementHandoffV1) -> tuple[str, ...]:
    # Start with the composition core, then materialize its reserved support
    # and personnel banks before extending both ends of the product chain.
    # This is deliberately not a main-chain-complete-then-tail lifecycle.
    return (
        "sorting_packaging_room",
        "secondary_precooling_room",
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "changing_room",
        "primary_precooling_room",
        "raw_fruit_buffer",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
        "office",
    )


def _composition_shape_order(
    handoff: StructuralCompositionPlacementHandoffV1,
    shapes: Mapping[str, tuple[_Shape, ...]],
    bank_sign: int,
) -> dict[str, tuple[_Shape, ...]]:
    """Order authoritative variants toward their assigned composition band axis.

    This does not remove or alter an authority-approved dimension/orientation.
    It prevents the first bounded search slice from spending its nodes on a
    footprint whose long axis consumes the scarce process or peripheral span.
    Flexible authority variants keep their existing compact-first order.
    """
    faces = _domain_faces(handoff, bank_sign)
    result: dict[str, tuple[_Shape, ...]] = {}
    for role, variants in shapes.items():
        if len(variants) != 2:
            result[role] = variants
            continue
        axis = faces.get(role, (handoff.process_axis.value, 1))[0]
        result[role] = tuple(
            sorted(
                variants,
                key=lambda shape: (
                    shape.world_width_mm if axis == "X" else shape.world_depth_mm,
                    shape.world_depth_mm if axis == "X" else shape.world_width_mm,
                    shape.rotation_deg,
                ),
            )
        )
    return result


def _domain_interval(
    role: str,
    handoff: StructuralCompositionPlacementHandoffV1,
    domains: Sequence[ConstructionDomainV1],
) -> tuple[str, tuple[int, int] | None]:
    assignment = next(item for item in handoff.zone_role_assignment if item.zone_role == role)
    for domain in domains:
        if domain.domain_id == assignment.composition_band:
            return domain.reference_axis, domain.preferred_interval_mm
    return handoff.process_axis.value, None


def _search_one(
    handoff: StructuralCompositionPlacementHandoffV1,
    authorities: Mapping[str, Mapping[str, Any]],
    shapes: Mapping[str, tuple[_Shape, ...]],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    domains: tuple[ConstructionDomainV1, ...],
    bank_sign: int,
    node_limit: int,
) -> tuple[dict[str, PlacedRectangleV1] | None, int, bool, str]:
    nodes = 0
    budget_hit = False
    deepest_role = "sorting_packaging_room"
    order = _zone_order(handoff)
    faces = _domain_faces(handoff, bank_sign)
    ordered_shapes = _composition_shape_order(handoff, shapes, bank_sign)

    def recurse(
        index: int, placed: dict[str, PlacedRectangleV1]
    ) -> dict[str, PlacedRectangleV1] | None:
        nonlocal nodes, budget_hit, deepest_role
        if index < len(order):
            deepest_role = order[index]
        if index == len(order):
            must_ok = all(
                rectangles_share_positive_edge(placed[first], placed[second])
                for first, second in process_graph().must_adjacencies
            )
            if must_ok and _intent_preserved(handoff, placed, faces):
                return dict(placed)
            return None
        code = order[index]
        neighbors = tuple(name for name in _must_neighbors(code) if name in placed)
        axis, interval = _domain_interval(code, handoff, domains)
        for shape in ordered_shapes[code]:
            if neighbors:
                origins = _anchors_at_must_faces(
                    code, shape, placed, neighbors, boundary, obstacles
                )
            else:
                origins = _root_anchors(shape, placed, boundary, obstacles)
            sorting = placed.get("sorting_packaging_room")
            if sorting is not None and code in faces:
                ref_axis, sign = faces[code]
                sorting_coordinate = _center(sorting, ref_axis)
                origins = tuple(
                    point
                    for point in origins
                    if (
                        (
                            point[0] + shape.world_width_mm // 2
                            if ref_axis == "X"
                            else point[1] + shape.world_depth_mm // 2
                        )
                        - sorting_coordinate
                    )
                    * sign
                    > 0
                )

            def origin_key(
                point: tuple[int, int],
                *,
                shape: _Shape = shape,
                interval: tuple[int, int] | None = interval,
            ) -> tuple[int, int, int]:
                projection = (
                    point[0] + shape.world_width_mm // 2
                    if axis == "X"
                    else point[1] + shape.world_depth_mm // 2
                )
                if interval is None:
                    interval_penalty = 0
                else:
                    left, right = interval
                    interval_penalty = (
                        0
                        if left <= projection <= right
                        else min(abs(projection - left), abs(projection - right))
                    )
                sorting = placed.get("sorting_packaging_room")
                side_penalty = 0
                if sorting is not None and code in faces:
                    ref_axis, sign = faces[code]
                    coordinate = (
                        point[0] + shape.world_width_mm // 2
                        if ref_axis == "X"
                        else point[1] + shape.world_depth_mm // 2
                    )
                    delta = (coordinate - _center(sorting, ref_axis)) * sign
                    side_penalty = 0 if delta > 0 else abs(delta) + 1
                return interval_penalty + side_penalty, point[0], point[1]

            for x, y in sorted(origins, key=origin_key):
                if nodes >= node_limit:
                    budget_hit = True
                    return None
                nodes += 1
                candidate = _rectangle(code, x, y, shape)
                if not _candidate_is_clear(candidate, placed, boundary, obstacles):
                    continue
                if neighbors and any(
                    not rectangles_share_positive_edge(candidate, placed[neighbor])
                    for neighbor in neighbors
                ):
                    continue
                sorting = placed.get("sorting_packaging_room")
                if sorting is not None and not _side_ok(code, candidate, sorting, faces):
                    continue
                placed[code] = candidate
                solution = recurse(index + 1, placed)
                if solution is not None:
                    return solution
                placed.pop(code, None)
                if budget_hit:
                    return None
        return None

    solution = recurse(0, {})
    return solution, nodes, budget_hit, deepest_role


def _candidate(
    handoff: StructuralCompositionPlacementHandoffV1,
    placements: Mapping[str, PlacedRectangleV1],
    domains: tuple[ConstructionDomainV1, ...],
    hashes: tuple[str, str, str],
    node_provenance: tuple[tuple[str, str], ...],
) -> CompositionPlacementCandidateV1:
    ordered_zones = tuple(placements[code] for code in ZONE_CODES)
    must_count = sum(
        rectangles_share_positive_edge(placements[first], placements[second])
        for first, second in process_graph().must_adjacencies
    )
    return CompositionPlacementCandidateV1(
        identity=IDENTITY,
        schema_version=SCHEMA_VERSION,
        composition_identity=handoff.composition_identity,
        composition_signature=handoff.composition_signature,
        family=handoff.family,
        process_axis=handoff.process_axis,
        process_direction=handoff.process_direction,
        zones=ordered_zones,
        zone_count=len(ordered_zones),
        placement_scope=PLACEMENT_HARD_SCOPE,
        hard_constraints_passed=True,
        site_valid=True,
        dimension_valid=True,
        non_overlap_valid=True,
        must_adjacency_valid=must_count == len(process_graph().must_adjacencies),
        must_adjacency_satisfied_count=must_count,
        composition_intent_preserved=True,
        construction_domains=domains,
        source_zone_plan_hash=hashes[0],
        source_p1_handoff_hash=hashes[1],
        source_site_geometry_hash=hashes[2],
        search_provenance=node_provenance,
    )


def enumerate_composition_placements(
    handoffs: Sequence[StructuralCompositionPlacementHandoffV1],
    dimension_authorities: Mapping[str, Mapping[str, Any]],
    site_geometry: Mapping[str, Any],
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    node_budget: int = DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
) -> CompositionPlacementEnumerationV1:
    """Generate bounded, family-first exact candidates from server-bound intents."""
    if (
        type(node_budget) is not int
        or node_budget < len(FAMILY_ORDER)
        or node_budget > MAX_COMPOSITION_PLACEMENT_NODE_BUDGET
    ):
        raise ValueError("INVALID_COMPOSITION_PLACEMENT_NODE_BUDGET")
    if set(dimension_authorities) != set(ZONE_CODES):
        raise ValueError("DIMENSION_AUTHORITY_ROLE_COVERAGE_INVALID")
    if not handoffs or any(
        not isinstance(item, StructuralCompositionPlacementHandoffV1) for item in handoffs
    ):
        raise ValueError("SERVER_BOUND_COMPOSITION_HANDOFFS_REQUIRED")
    boundary_raw = site_geometry.get("site", {}).get("effective_buildable_boundary")
    if not isinstance(boundary_raw, Mapping):
        raise ValueError("VALIDATED_BUILDABLE_BOUNDARY_REQUIRED")
    boundary = normalize_polygon(boundary_raw, allow_numeric_string=True)
    obstacles_raw = site_geometry.get("obstacles", {}).get("no_build_zones", [])
    if not isinstance(obstacles_raw, list):
        raise ValueError("VALIDATED_OBSTACLES_REQUIRED")
    obstacles = tuple(normalize_polygon(item, allow_numeric_string=True) for item in obstacles_raw)
    shapes = _authority_shapes(dimension_authorities, boundary, obstacles)
    by_family: dict[CompositionFamilyV2, list[StructuralCompositionPlacementHandoffV1]] = (
        defaultdict(list)
    )
    for item in handoffs:
        by_family[item.family].append(item)
    if set(by_family) != set(FAMILY_ORDER):
        raise ValueError("COMPOSITION_FAMILY_COVERAGE_INVALID")

    per_attempt_budget = max(1, node_budget // (len(FAMILY_ORDER) * 2 * 2))
    remaining = node_budget
    attempts: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    used: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    deepest: dict[str, str] = {family.value: "NOT_ATTEMPTED" for family in FAMILY_ORDER}
    deepest_rank: dict[str, int] = {family.value: -1 for family in FAMILY_ORDER}
    failures: dict[str, str] = {}
    hashes = (source_zone_plan_hash, source_p1_handoff_hash, source_site_geometry_hash)
    candidate_by_family: dict[CompositionFamilyV2, CompositionPlacementCandidateV1] = {}
    search_attempts: list[CompositionPlacementSearchAttemptV1] = []
    role_rank = {
        role: index for index, role in enumerate(_zone_order(by_family[FAMILY_ORDER[0]][0]))
    }
    tasks = [
        (family, by_family[family][0], bank_sign)
        for family in FAMILY_ORDER
        for bank_sign in (1, -1)
    ]
    tasks.extend(
        (family, by_family[family][1], bank_sign)
        for family in FAMILY_ORDER
        if len(by_family[family]) > 1
        for bank_sign in (1, -1)
    )
    for family, handoff, bank_sign in tasks:
        if remaining <= 0 or family in candidate_by_family:
            continue
        family_key = family.value
        attempts[family_key] += 1
        domains = _domain_arrangement(handoff, bank_sign, boundary, dimension_authorities)
        allocation = min(per_attempt_budget, remaining)
        solution, visited, hit, deepest_role = _search_one(
            handoff,
            dimension_authorities,
            shapes,
            boundary,
            obstacles,
            domains,
            bank_sign,
            allocation,
        )
        used[family_key] += visited
        attempt_failure = (
            None
            if solution is not None
            else (
                "COMPOSITION_VARIANT_NODE_ALLOCATION_EXHAUSTED"
                if hit
                else "NO_COMPLETE_COMPOSITION_CONSTRAINED_LAYOUT"
            )
        )
        search_attempts.append(
            CompositionPlacementSearchAttemptV1(
                family=family,
                composition_identity=handoff.composition_identity,
                composition_signature=handoff.composition_signature,
                process_axis=handoff.process_axis,
                process_direction=handoff.process_direction,
                peripheral_bank_sign=bank_sign,
                construction_domains=domains,
                nodes_allocated=allocation,
                nodes_visited=visited,
                deepest_role_reached=deepest_role,
                node_budget_exhausted=hit,
                complete_layout_found=solution is not None,
                failure_reason=attempt_failure,
            )
        )
        if role_rank[deepest_role] >= deepest_rank[family_key]:
            deepest[family_key] = deepest_role
            deepest_rank[family_key] = role_rank[deepest_role]
        remaining -= visited
        if solution is not None:
            candidate_by_family[family] = _candidate(
                handoff,
                solution,
                domains,
                hashes,
                (
                    (
                        "domain_arrangement",
                        "MIRROR_POSITIVE" if bank_sign > 0 else "MIRROR_NEGATIVE",
                    ),
                    ("nodes_visited", str(used[family_key])),
                    ("event_policy", "SITE_ROOM_EDGE_AND_CLOSED_OBSTACLE_PLUS_MINUS_GRID_MM"),
                    ("per_attempt_node_allocation", str(per_attempt_budget)),
                ),
            )
            failures.pop(family_key, None)
        elif hit:
            failures[family_key] = "COMPOSITION_VARIANT_NODE_ALLOCATION_EXHAUSTED"
        else:
            failures.setdefault(family_key, "NO_COMPLETE_COMPOSITION_CONSTRAINED_LAYOUT")
    candidates = [
        candidate_by_family[family] for family in FAMILY_ORDER if family in candidate_by_family
    ]

    nodes_used = sum(used.values())
    return CompositionPlacementEnumerationV1(
        identity=IDENTITY,
        schema_version=SCHEMA_VERSION,
        node_budget=node_budget,
        nodes_used=nodes_used,
        node_budget_exhausted=nodes_used >= node_budget,
        family_coverage_order=tuple(family.value for family in FAMILY_ORDER),
        family_first_round_complete=all(attempts[family.value] >= 1 for family in FAMILY_ORDER),
        attempt_count_by_family=tuple(
            (family.value, attempts[family.value]) for family in FAMILY_ORDER
        ),
        nodes_used_by_family=tuple((family.value, used[family.value]) for family in FAMILY_ORDER),
        deepest_role_reached_by_family=tuple(
            (family.value, deepest[family.value]) for family in FAMILY_ORDER
        ),
        failure_reason_by_family=tuple((key, failures[key]) for key in sorted(failures)),
        search_attempts=tuple(search_attempts),
        candidates=tuple(candidates),
    )
