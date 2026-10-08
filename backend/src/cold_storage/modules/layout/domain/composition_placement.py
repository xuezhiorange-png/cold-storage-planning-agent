"""Bounded rectangle placement constrained by whole-building composition intent.

This module produces exact rectangle candidates only.  Construction domains are
search organizers, not site/access/Truck engineering authorities.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.authority_shapes import (
    AuthoritativeZoneShapeV1 as _Shape,
)
from cold_storage.modules.layout.domain.authority_shapes import (
    _m,
    _mm,
)
from cold_storage.modules.layout.domain.authority_shapes import (
    authoritative_zone_shapes as _authority_shapes,
)
from cold_storage.modules.layout.domain.authority_shapes import (
    canonical_construction_shapes as _canonical_construction_shapes,
)
from cold_storage.modules.layout.domain.composition_handoff import (
    StructuralCompositionPlacementHandoffV1,
)
from cold_storage.modules.layout.domain.conditional_metric_support import (
    ConditionalMetricSupportQueryV2,
    ConditionalMetricSupportStateV2,
    ConditionalSupportStatusV2,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.joint_metric_capacity import (
    JointMetricCapacityQueryV1,
    JointMetricSupportStateV1,
)
from cold_storage.modules.layout.domain.metric_reservation_consumption import (
    MetricRuntimeContextV1,
    MetricSupportDiagnosticsV1,
    RuntimeMetricReservationDomainV1,
    build_metric_runtime_context,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    normalize_polygon,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CompositionFamilyV2,
    ProcessAxisV1,
    ProcessDirectionV1,
)
from cold_storage.modules.layout.domain.validated_site_obstacles import (
    validated_hard_obstacle_polygons,
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
GENERIC_FALLBACK_ANCHOR_LIMIT_PER_ROLE = 24


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
    deepest_role_attempted: str
    deepest_role_successfully_placed: str
    max_simultaneously_placed_role_count: int
    role_search_funnel: tuple[RoleSearchFunnelV1, ...]
    domain_derived_anchor_count_by_role: tuple[tuple[str, int], ...]
    generic_fallback_anchor_count_by_role: tuple[tuple[str, int], ...]
    generic_fallback_node_count_by_role: tuple[tuple[str, int], ...]
    authority_shape_variant_count_by_role: tuple[tuple[str, int], ...]
    construction_shape_variant_count_by_role: tuple[tuple[str, int], ...]
    shipping_office_interface_preflight_status: str
    band_capacity_preflight_status: str
    peripheral_capacity_preflight_status: str
    best_partial_placement_witness: PartialPlacementWitnessV1
    node_budget_exhausted: bool
    complete_layout_found: bool
    failure_reason: str | None
    metric_reservation_diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family.value,
            "metric_reservation_diagnostics": dict(self.metric_reservation_diagnostics),
            "composition_identity": self.composition_identity,
            "composition_signature": self.composition_signature,
            "process_axis": self.process_axis.value,
            "process_direction": self.process_direction.value,
            "peripheral_bank_sign": self.peripheral_bank_sign,
            "construction_domains": [asdict(domain) for domain in self.construction_domains],
            "nodes_allocated": self.nodes_allocated,
            "nodes_visited": self.nodes_visited,
            "deepest_role_attempted": self.deepest_role_attempted,
            "deepest_role_successfully_placed": self.deepest_role_successfully_placed,
            "max_simultaneously_placed_role_count": self.max_simultaneously_placed_role_count,
            "role_search_funnel": [item.to_dict() for item in self.role_search_funnel],
            "domain_derived_anchor_count_by_role": dict(self.domain_derived_anchor_count_by_role),
            "generic_fallback_anchor_count_by_role": dict(
                self.generic_fallback_anchor_count_by_role
            ),
            "generic_fallback_used_by_role": {
                role: count > 0 for role, count in self.generic_fallback_node_count_by_role
            },
            "generic_fallback_node_count_by_role": dict(self.generic_fallback_node_count_by_role),
            "domain_derived_anchor_path_is_primary_by_role": {
                role: True for role, _ in self.domain_derived_anchor_count_by_role
            },
            "authority_shape_variant_count_by_role": dict(
                self.authority_shape_variant_count_by_role
            ),
            "construction_shape_variant_count_by_role": dict(
                self.construction_shape_variant_count_by_role
            ),
            "shipping_office_interface_preflight_status": (
                self.shipping_office_interface_preflight_status
            ),
            "band_capacity_preflight_status": self.band_capacity_preflight_status,
            "peripheral_capacity_preflight_status": self.peripheral_capacity_preflight_status,
            "best_partial_placement_witness": self.best_partial_placement_witness.to_dict(),
            "node_budget_exhausted": self.node_budget_exhausted,
            "complete_layout_found": self.complete_layout_found,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class RoleSearchFunnelV1:
    zone_role: str
    role_attempt_count: int
    authority_shape_variant_count: int
    authority_rotation_variant_count: int
    construction_shape_variant_count: int
    shape_variant_attempt_count: int
    domain_derived_anchor_count: int
    generic_fallback_anchor_count: int
    candidate_rectangle_attempt_count: int
    site_rejection_count: int
    obstacle_rejection_count: int
    overlap_rejection_count: int
    domain_side_rejection_count: int
    must_edge_rejection_count: int
    coupled_interface_rejection_count: int
    composition_intent_rejection_count: int
    accepted_partial_placement_count: int
    backtrack_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_role": self.zone_role,
            "role_attempt_count": self.role_attempt_count,
            "authority_shape_variant_count": self.authority_shape_variant_count,
            "authority_rotation_variant_count": self.authority_rotation_variant_count,
            "construction_shape_variant_count": self.construction_shape_variant_count,
            "shape_variant_attempt_count": self.shape_variant_attempt_count,
            "domain_derived_anchor_count": self.domain_derived_anchor_count,
            "generic_fallback_anchor_count": self.generic_fallback_anchor_count,
            "candidate_rectangle_attempt_count": self.candidate_rectangle_attempt_count,
            "site_rejection_count": self.site_rejection_count,
            "obstacle_rejection_count": self.obstacle_rejection_count,
            "overlap_rejection_count": self.overlap_rejection_count,
            "domain_side_rejection_count": self.domain_side_rejection_count,
            "must_edge_rejection_count": self.must_edge_rejection_count,
            "coupled_interface_rejection_count": self.coupled_interface_rejection_count,
            "composition_intent_rejection_count": self.composition_intent_rejection_count,
            "accepted_partial_placement_count": self.accepted_partial_placement_count,
            "backtrack_count": self.backtrack_count,
        }


@dataclass(frozen=True)
class PartialPlacementWitnessV1:
    composition_identity: str
    placed_roles: tuple[str, ...]
    zone_bounds_mm: tuple[tuple[str, tuple[int, int, int, int]], ...]
    next_role: str
    failure_taxonomy: str
    hard_subset_rejection_count: int
    bank_sign: int
    nodes_used: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "composition_identity": self.composition_identity,
            "placed_roles": list(self.placed_roles),
            "zone_bounds_mm": {role: list(bounds) for role, bounds in self.zone_bounds_mm},
            "next_role": self.next_role,
            "failure_taxonomy": self.failure_taxonomy,
            "hard_subset_rejection_count": self.hard_subset_rejection_count,
            "bank_sign": self.bank_sign,
            "nodes_used": self.nodes_used,
            "is_complete_candidate": False,
        }


@dataclass
class _SearchDiagnostics:
    node_limit: int = 0
    nodes: int = 0
    budget_hit: bool = False
    deepest_attempted: str = "NOT_ATTEMPTED"
    deepest_successfully_placed: str = "NOT_PLACED"
    max_placed: int = 0
    generic_nodes: int = 0
    failure_taxonomy: str = "SEARCH_STARTED"
    shipping_office_status: str = "PASS_TO_SEARCH"
    band_capacity_status: str = "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"
    peripheral_capacity_status: str = "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"
    best_witness: PartialPlacementWitnessV1 | None = None
    best_witness_key: tuple[int, int, tuple[tuple[str, tuple[int, int, int, int]], ...]] | None = (
        None
    )
    office_seed_by_shipping: dict[tuple[int, int, int, int], tuple[_Shape, tuple[int, int]]] = (
        field(default_factory=dict)
    )
    funnel: dict[str, dict[str, int]] = field(default_factory=dict)
    domain_anchor_count: dict[str, int] = field(default_factory=dict)
    generic_anchor_count: dict[str, int] = field(default_factory=dict)
    generic_nodes_by_role: dict[str, int] = field(default_factory=dict)
    authority_shape_count: dict[str, int] = field(default_factory=dict)
    construction_shape_count: dict[str, int] = field(default_factory=dict)
    metric_support: MetricSupportDiagnosticsV1 = field(default_factory=MetricSupportDiagnosticsV1)
    metric_capacity: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _SearchOutcome:
    solution: dict[str, PlacedRectangleV1] | None
    diagnostics: _SearchDiagnostics
    deepest_attempted: str
    deepest_successfully_placed: str


@dataclass(frozen=True)
class CompositionPlacementEnumerationV1:
    identity: str
    schema_version: str
    node_budget: int
    nodes_used: int
    node_budget_exhausted: bool
    initial_family_budget: int
    continuation_budget: int
    continuation_selection_reason: str
    family_coverage_order: tuple[str, ...]
    family_first_round_complete: bool
    attempt_count_by_family: tuple[tuple[str, int], ...]
    nodes_used_by_family: tuple[tuple[str, int], ...]
    deepest_role_attempted_by_family: tuple[tuple[str, str], ...]
    deepest_role_successfully_placed_by_family: tuple[tuple[str, str], ...]
    max_simultaneously_placed_role_count_by_family: tuple[tuple[str, int], ...]
    best_partial_placement_witness_by_family: tuple[tuple[str, PartialPlacementWitnessV1], ...]
    domain_derived_anchor_count_by_family: tuple[tuple[str, int], ...]
    generic_fallback_anchor_count_by_family: tuple[tuple[str, int], ...]
    generic_fallback_node_count_by_family: tuple[tuple[str, int], ...]
    failure_reason_by_family: tuple[tuple[str, str], ...]
    search_attempts: tuple[CompositionPlacementSearchAttemptV1, ...]
    candidates: tuple[CompositionPlacementCandidateV1, ...]
    metric_runtime_diagnostics: Mapping[str, Any] = field(default_factory=dict)
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
            "metric_runtime_diagnostics": dict(self.metric_runtime_diagnostics),
            "nodes_used": self.nodes_used,
            "node_budget_exhausted": self.node_budget_exhausted,
            "initial_family_budget": self.initial_family_budget,
            "continuation_budget": self.continuation_budget,
            "continuation_selection_reason": self.continuation_selection_reason,
            "family_coverage_order": list(self.family_coverage_order),
            "family_first_round_complete": self.family_first_round_complete,
            "attempt_count_by_family": dict(self.attempt_count_by_family),
            "nodes_used_by_family": dict(self.nodes_used_by_family),
            "deepest_role_attempted_by_family": dict(self.deepest_role_attempted_by_family),
            "deepest_role_successfully_placed_by_family": dict(
                self.deepest_role_successfully_placed_by_family
            ),
            "max_simultaneously_placed_role_count_by_family": dict(
                self.max_simultaneously_placed_role_count_by_family
            ),
            "best_partial_placement_witness_by_family": {
                family: witness.to_dict()
                for family, witness in self.best_partial_placement_witness_by_family
            },
            "domain_derived_anchor_count_by_family": dict(
                self.domain_derived_anchor_count_by_family
            ),
            "generic_fallback_anchor_count_by_family": dict(
                self.generic_fallback_anchor_count_by_family
            ),
            "generic_fallback_node_count_by_family": dict(
                self.generic_fallback_node_count_by_family
            ),
            "failure_reason_by_family": dict(self.failure_reason_by_family),
            "search_attempts": [attempt.to_dict() for attempt in self.search_attempts],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "exact_placement_performed": self.exact_placement_performed,
            "access_routing_performed": self.access_routing_performed,
            "truck_validation_performed": self.truck_validation_performed,
            "p2d_performed": self.p2d_performed,
            "project_layout_validated_claimed": self.project_layout_validated_claimed,
        }


def _polygon_area_mm2(polygon: PolygonMM) -> int:
    return (
        abs(
            sum(
                first[0] * second[1] - second[0] * first[1]
                for first, second in zip(polygon, polygon[1:] + polygon[:1], strict=True)
            )
        )
        // 2
    )


def _authority_area_mm2(authority: Mapping[str, Any]) -> int:
    required = authority.get("required_area_m2")
    if required is not None:
        return int(Decimal(str(required)) * 1_000_000)
    geometry = authority.get("geometry")
    if not isinstance(geometry, Mapping):
        raise ValueError("DIMENSION_AUTHORITY_AREA_MISSING")
    return _mm(geometry.get("width_m")) * _mm(geometry.get("depth_m"))


def _capacity_preflight_status(
    role_groups: Sequence[Sequence[str]],
    authorities: Mapping[str, Mapping[str, Any]],
    authority_shapes: Mapping[str, Sequence[_Shape]],
    boundary: PolygonMM,
) -> str:
    """Apply only gross-area and bounding-box necessary capacity checks."""
    site_area = _polygon_area_mm2(boundary)
    min_x, max_x = min(point[0] for point in boundary), max(point[0] for point in boundary)
    min_y, max_y = min(point[1] for point in boundary), max(point[1] for point in boundary)
    bbox_width, bbox_depth = max_x - min_x, max_y - min_y
    for role_group in role_groups:
        roles = tuple(role_group)
        if not roles:
            continue
        if sum(_authority_area_mm2(authorities[role]) for role in roles) > site_area:
            return "PROVABLY_EXCEEDS_BUILDABLE_SITE_AREA"
        for role in roles:
            authority = authorities[role]
            if authority.get("dimension_mode") == "FLEXIBLE_RECTANGLE":
                # Area is the only lower bound here; flexible aspect semantics
                # stay owned by the authoritative dimension validator.
                continue
            if not any(
                shape.world_width_mm <= bbox_width and shape.world_depth_mm <= bbox_depth
                for shape in authority_shapes[role]
            ):
                return f"PROVABLY_NO_AUTHORIZED_ORIENTATION_FITS_SITE_BOUNDS:{role}"
    return "PASS_TO_SEARCH_GROSS_AREA_AND_SITE_BOUNDS"


def _shipping_office_interface_preflight_status(
    shipping_shapes: Sequence[_Shape],
    office_shapes: Sequence[_Shape],
    boundary: PolygonMM,
) -> str:
    """Check only whether any authorized shipping/office pair can share an edge
    inside the site bounding box.

    A possible pair is not a placement witness: concavity, obstacles, other
    rooms, and composition domains still belong to exact search. Rejection is
    safe only when no pair of allowed footprints can geometrically fit with a
    positive shared edge even in the larger site bounding box.
    """
    min_x, max_x = min(point[0] for point in boundary), max(point[0] for point in boundary)
    min_y, max_y = min(point[1] for point in boundary), max(point[1] for point in boundary)
    site_width, site_depth = max_x - min_x, max_y - min_y
    for shipping in shipping_shapes:
        shipping_width, shipping_depth = shipping.world_width_mm, shipping.world_depth_mm
        if shipping_width > site_width or shipping_depth > site_depth:
            continue
        for office in office_shapes:
            office_width, office_depth = office.world_width_mm, office.world_depth_mm
            if office_width > site_width or office_depth > site_depth:
                continue
            vertical_pair_fits = (
                shipping_width + office_width <= site_width
                and min(shipping_depth, office_depth) > 0
            )
            horizontal_pair_fits = (
                shipping_depth + office_depth <= site_depth
                and min(shipping_width, office_width) > 0
            )
            if vertical_pair_fits or horizontal_pair_fits:
                return "PASS_TO_SEARCH_SITE_BOUNDS_NECESSARY_CONDITION"
    return "PROVABLY_NO_SHARED_EDGE_CAPACITY_IN_SITE_BOUNDS"


def _rectangle(code: str, x: int, y: int, shape: _Shape) -> PlacedRectangleV1:
    return PlacedRectangleV1(
        code,
        _m(x),
        _m(y),
        _m(shape.width_mm),
        _m(shape.depth_mm),
        shape.rotation_deg,
    )


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


def _domain_faces(
    handoff: StructuralCompositionPlacementHandoffV1, bank_sign: int
) -> dict[str, tuple[str, int]]:
    axis = handoff.process_axis.value
    cross_axis = "Y" if axis == "X" else "X"
    direction_sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1
    result: dict[str, tuple[str, int]] = {}
    # Process-band side hints are ordering inputs only; group ordering remains
    # the composition-level predicate rather than a new room-by-room rule.
    result["raw_fruit_buffer"] = (axis, -direction_sign)
    result["primary_precooling_room"] = (axis, -direction_sign)
    result["finished_goods_room"] = (axis, direction_sign)
    result["shipping_channel"] = (axis, direction_sign)
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
    if handoff.process_direction == ProcessDirectionV1.NEGATIVE:
        reflected: list[ConstructionDomainV1] = []
        for domain in domains:
            interval = domain.preferred_interval_mm
            if interval is None:
                reflected.append(domain)
                continue
            low, high = interval
            reflected.append(
                ConstructionDomainV1(
                    domain_id=domain.domain_id,
                    zone_roles=domain.zone_roles,
                    domain_kind=domain.domain_kind,
                    reference_axis=domain.reference_axis,
                    preferred_interval_mm=(min_x + max_x - high, min_x + max_x - low)
                    if axis == "X"
                    else (min_y + max_y - high, min_y + max_y - low),
                    preferred_face=domain.preferred_face,
                    origin_event_policy=domain.origin_event_policy,
                    engineering_authority=domain.engineering_authority,
                )
            )
        domains = reflected
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
    for peripheral_intent in handoff.peripheral_domain_intents:
        preferred = next(
            (
                ("POSITIVE" if sign > 0 else "NEGATIVE") + f"_{ref_axis}"
                for role, (ref_axis, sign) in faces.items()
                if role in peripheral_intent.zone_roles
            ),
            peripheral_intent.relative_side,
        )
        domains.append(
            ConstructionDomainV1(
                domain_id=peripheral_intent.domain_id,
                zone_roles=peripheral_intent.zone_roles,
                domain_kind="RESERVED_PERIPHERAL_SEARCH_DOMAIN",
                reference_axis=next(
                    (faces[role][0] for role in peripheral_intent.zone_roles if role in faces),
                    cross_axis,
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
    if role not in {
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "changing_room",
        "office",
    }:
        return True
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


def _partial_intent_possible(
    handoff: StructuralCompositionPlacementHandoffV1,
    placed: Mapping[str, PlacedRectangleV1],
    faces: Mapping[str, tuple[str, int]],
) -> bool:
    sorting = placed.get("sorting_packaging_room")
    if sorting is None:
        return True
    if any(
        not _side_ok(role, rectangle, sorting, faces)
        for role, rectangle in placed.items()
        if role in faces
    ):
        return False
    axis = handoff.process_axis.value
    sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1

    def group_center(roles: Sequence[str]) -> int:
        return sum(_axis_coordinate(placed[role], axis) for role in roles) // len(roles)

    raw_roles = ("raw_fruit_buffer", "primary_precooling_room")
    core_roles = ("sorting_packaging_room", "secondary_precooling_room", "coating_room")
    finished_roles = ("finished_goods_room", "shipping_channel")
    if handoff.family == CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS:
        flow = (
            "raw_fruit_buffer",
            "primary_precooling_room",
            "sorting_packaging_room",
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        )
        placed_flow = [
            sign * _axis_coordinate(placed[role], axis) for role in flow if role in placed
        ]
        return all(
            first <= second for first, second in zip(placed_flow, placed_flow[1:], strict=False)
        )
    if all(role in placed for role in raw_roles) and all(role in placed for role in core_roles):
        raw_center, core_center = group_center(raw_roles), group_center(core_roles)
        if handoff.family == CompositionFamilyV2.LINEAR_BANDED:
            if (raw_center - core_center) * sign >= 0:
                return False
        elif (raw_center - _center(sorting, axis)) * sign >= 0:
            return False
    if all(role in placed for role in finished_roles) and all(
        role in placed for role in core_roles
    ):
        finished_center, core_center = group_center(finished_roles), group_center(core_roles)
        if handoff.family == CompositionFamilyV2.LINEAR_BANDED:
            return (finished_center - core_center) * sign > 0
        return (finished_center - _center(sorting, axis)) * sign > 0
    return True


def _zone_order(handoff: StructuralCompositionPlacementHandoffV1) -> tuple[str, ...]:
    # Composition-aware constrained-first sequence interleaves the already
    # reserved branches with the process chain. It does not complete the main
    # chain and then append every peripheral role. Shipping/Office stay coupled.
    return (
        "sorting_packaging_room",
        "primary_precooling_room",
        "raw_fruit_buffer",
        "secondary_precooling_room",
        "packaging_material_storage",
        "coating_room",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "changing_room",
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
        if role == "sorting_packaging_room":
            # Family topology determines the useful core footprint: linear and
            # spine families align the long face with the process axis, while a
            # central core keeps the short face on that axis so opposite
            # process-side domains remain available around the organizer.
            central_core = handoff.family == CompositionFamilyV2.CENTRAL_PROCESS_CORE
            result[role] = tuple(
                sorted(
                    variants,
                    key=lambda shape: (
                        (shape.world_width_mm if axis == "X" else shape.world_depth_mm)
                        * (1 if central_core else -1),
                        shape.rotation_deg,
                    ),
                )
            )
            continue
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


def _interval_origin_events(
    interval: tuple[int, int] | None,
    extent: int,
) -> tuple[int, ...]:
    if interval is None:
        return ()
    low, high = interval
    return tuple(sorted({low, low + (high - low - extent) // 2, high - extent}))


def _face_anchors(
    base: PlacedRectangleV1,
    shape: _Shape,
    axis: str,
    sign: int,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    placed: Mapping[str, PlacedRectangleV1],
) -> set[tuple[int, int]]:
    """Finite edge-event origins on a composition-selected face."""
    left, bottom, right, top = _bounds(base)
    width, depth = shape.world_width_mm, shape.world_depth_mm
    xs, ys = _axis_events(
        boundary=boundary,
        obstacles=obstacles,
        placed=placed,
        width=width,
        depth=depth,
    )
    result: set[tuple[int, int]] = set()
    if axis == "X":
        x = right if sign > 0 else left - width
        cross_events = {
            bottom,
            top - depth,
            (bottom + top - depth) // 2,
            *(event for event in ys if event < top and event + depth > bottom),
        }
        for y in cross_events:
            result.add((x, y))
    else:
        y = top if sign > 0 else bottom - depth
        cross_events = {
            left,
            right - width,
            (left + right - width) // 2,
            *(event for event in xs if event < right and event + width > left),
        }
        for x in cross_events:
            result.add((x, y))
    return result


def _domain_derived_anchors(
    role: str,
    shape: _Shape,
    handoff: StructuralCompositionPlacementHandoffV1,
    domains: Sequence[ConstructionDomainV1],
    bank_sign: int,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> tuple[tuple[int, int], ...]:
    """Construct a bounded role domain from composition and physical events.

    MUST neighbors are used as authoritative attachment events where present;
    branch and personnel roles are instead seeded from their assigned domain
    face relative to Sorting and already-placed members of that bank.
    """
    width, depth = shape.world_width_mm, shape.world_depth_mm
    neighbors = tuple(name for name in _must_neighbors(role) if name in placed)
    if neighbors:
        must_face_anchors = set(
            _anchors_at_must_faces(role, shape, placed, neighbors, boundary, obstacles)
        )
        axis, interval = _domain_interval(role, handoff, domains)
        if interval is not None:
            # The primary domain is an actual finite subset, not merely an
            # ordering preference. Out-of-band MUST-face events remain
            # available through the bounded generic physical-event fallback.
            band_low, band_high = interval

            def center_in_band(point: tuple[int, int]) -> bool:
                projection = point[0] + width // 2 if axis == "X" else point[1] + depth // 2
                return band_low <= projection <= band_high

            must_face_anchors = {point for point in must_face_anchors if center_in_band(point)}
        return tuple(sorted(must_face_anchors))

    if role == "sorting_packaging_room":
        axis, interval = _domain_interval(role, handoff, domains)
        min_x, max_x = min(point[0] for point in boundary), max(point[0] for point in boundary)
        min_y, max_y = min(point[1] for point in boundary), max(point[1] for point in boundary)
        x_events, y_events = _axis_events(
            boundary=boundary,
            obstacles=obstacles,
            placed=placed,
            width=width,
            depth=depth,
        )
        longitudinal = _interval_origin_events(interval, width if axis == "X" else depth)
        if not longitudinal:
            physical_axis_events = x_events if axis == "X" else y_events
            axis_low = min_x if axis == "X" else min_y
            axis_high = max_x - width if axis == "X" else max_y - depth
            eligible = tuple(
                event for event in physical_axis_events if axis_low <= event <= axis_high
            )
            midpoint = (axis_low + axis_high) // 2
            ranked = sorted(eligible, key=lambda event: (abs(event - midpoint), event))
            longitudinal = tuple(sorted({axis_low, axis_high, *ranked[:12]}))
        cross = (
            {
                min_y,
                max_y - depth,
                (min_y + max_y - depth) // 2,
                *(y for y in y_events if min_y <= y <= max_y - depth),
            }
            if axis == "X"
            else {
                min_x,
                max_x - width,
                (min_x + max_x - width) // 2,
                *(x for x in x_events if min_x <= x <= max_x - width),
            }
        )
        pairs = (
            {(event, cross_event) for event in longitudinal for cross_event in cross}
            if axis == "X"
            else {(cross_event, event) for event in longitudinal for cross_event in cross}
        )
        return tuple(sorted(pairs))

    face = _domain_faces(handoff, bank_sign).get(role)
    if face is None:
        return ()
    axis, sign = face
    sorting = placed.get("sorting_packaging_room")
    if sorting is None:
        return ()
    bases = [sorting]
    for other_role, rectangle in placed.items():
        if other_role == "sorting_packaging_room":
            continue
        other_face = _domain_faces(handoff, bank_sign).get(other_role)
        if other_face == face:
            bases.append(rectangle)
    face_anchors: set[tuple[int, int]] = set()
    for base in bases:
        face_anchors.update(_face_anchors(base, shape, axis, sign, boundary, obstacles, placed))
    return tuple(sorted(face_anchors))


def _generic_fallback_anchors(
    role: str,
    shape: _Shape,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> tuple[tuple[int, int], ...]:
    neighbors = tuple(name for name in _must_neighbors(role) if name in placed)
    if neighbors:
        anchors = _anchors_at_must_faces(role, shape, placed, neighbors, boundary, obstacles)
    else:
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
        anchors_set = {
            (min_x, min_y),
            (max_x - width, min_y),
            (min_x, max_y - depth),
            (max_x - width, max_y - depth),
            (center_x, center_y),
            *((x, center_y) for x in xs),
            *((center_x, y) for y in ys),
            *((x, y) for x, y in zip(xs, ys, strict=False)),
        }
        anchors = tuple(sorted(anchors_set))
    return anchors[:GENERIC_FALLBACK_ANCHOR_LIMIT_PER_ROLE]


def _candidate_rejection(
    candidate: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> str | None:
    if not rectangle_inside_polygon(candidate, boundary):
        return "SITE"
    if any(rectangle_intersects_closed_obstacle(candidate, obstacle) for obstacle in obstacles):
        return "OBSTACLE"
    if any(rectangles_overlap(candidate, existing) for existing in placed.values()):
        return "OVERLAP"
    return None


def _shipping_office_seed(
    shipping: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    office_shapes: Sequence[_Shape],
    handoff: StructuralCompositionPlacementHandoffV1,
    domains: Sequence[ConstructionDomainV1],
    bank_sign: int,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    diagnostics: _SearchDiagnostics,
) -> tuple[_Shape, tuple[int, int]] | None:
    office_neighbors = tuple(name for name in _must_neighbors("office") if name in placed)
    if "shipping_channel" not in office_neighbors:
        return None
    faces = _domain_faces(handoff, bank_sign)
    domain_origins_by_shape: dict[_Shape, set[tuple[int, int]]] = {}
    for source in ("DOMAIN", "GENERIC"):
        if source == "GENERIC" and diagnostics.generic_nodes >= max(
            1, diagnostics.node_limit // 10
        ):
            break
        for shape in office_shapes:
            if source == "DOMAIN":
                anchors = _domain_derived_anchors(
                    "office", shape, handoff, domains, bank_sign, placed, boundary, obstacles
                )
                diagnostics.domain_anchor_count["office"] = diagnostics.domain_anchor_count.get(
                    "office", 0
                ) + len(anchors)
                diagnostics.funnel["office"]["domain_derived_anchor_count"] += len(anchors)
                domain_origins_by_shape[shape] = set(anchors)
            else:
                anchors = _generic_fallback_anchors("office", shape, placed, boundary, obstacles)
                anchors = tuple(
                    point
                    for point in anchors
                    if point not in domain_origins_by_shape.get(shape, set())
                )
                diagnostics.generic_anchor_count["office"] = diagnostics.generic_anchor_count.get(
                    "office", 0
                ) + len(anchors)
                diagnostics.funnel["office"]["generic_fallback_anchor_count"] += len(anchors)
            for point in anchors:
                if source == "GENERIC" and diagnostics.generic_nodes >= max(
                    1, diagnostics.node_limit // 10
                ):
                    break
                if diagnostics.nodes >= diagnostics.node_limit:
                    diagnostics.budget_hit = True
                    diagnostics.shipping_office_status = "UNRESOLVED_NODE_BUDGET"
                    return None
                diagnostics.nodes += 1
                funnel = diagnostics.funnel["office"]
                funnel["candidate_rectangle_attempt_count"] += 1
                if source == "GENERIC":
                    diagnostics.generic_nodes += 1
                    diagnostics.generic_nodes_by_role["office"] = (
                        diagnostics.generic_nodes_by_role.get("office", 0) + 1
                    )
                candidate = _rectangle("office", point[0], point[1], shape)
                rejected = _candidate_rejection(candidate, placed, boundary, obstacles)
                if rejected is not None:
                    funnel[f"{rejected.lower()}_rejection_count"] += 1
                    diagnostics.failure_taxonomy = f"OFFICE_{rejected}_REJECTION"
                    continue
                sorting = placed.get("sorting_packaging_room")
                if sorting is not None and not _side_ok("office", candidate, sorting, faces):
                    funnel["domain_side_rejection_count"] += 1
                    diagnostics.failure_taxonomy = "OFFICE_DOMAIN_SIDE_REJECTION"
                    continue
                if not rectangles_share_positive_edge(candidate, shipping):
                    funnel["must_edge_rejection_count"] += 1
                    diagnostics.failure_taxonomy = "OFFICE_SHIPPING_MUST_EDGE_REJECTION"
                    continue
                diagnostics.office_seed_by_shipping[shipping.bounds_mm] = (shape, point)
                diagnostics.shipping_office_status = "PASS"
                return shape, point
    diagnostics.shipping_office_status = "NO_AUTHORITY_VALID_OFFICE_ATTACHMENT"
    return None


def _search_one(
    handoff: StructuralCompositionPlacementHandoffV1,
    shapes: Mapping[str, tuple[_Shape, ...]],
    authority_shapes: Mapping[str, tuple[_Shape, ...]],
    dimension_authorities: Mapping[str, Mapping[str, Any]],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    domains: tuple[ConstructionDomainV1, ...],
    bank_sign: int,
    node_limit: int,
    runtime_domains: tuple[RuntimeMetricReservationDomainV1, ...],
) -> _SearchOutcome:
    order = _zone_order(handoff)
    faces = _domain_faces(handoff, bank_sign)
    ordered_shapes = _composition_shape_order(handoff, shapes, bank_sign)
    diagnostics = _SearchDiagnostics(node_limit=node_limit)

    def conditional_origins(
        role: str, shape: _Shape, partial: Mapping[str, PlacedRectangleV1]
    ) -> tuple[tuple[int, int], ...]:
        return tuple(
            dict.fromkeys(
                (
                    *_domain_derived_anchors(
                        role, shape, handoff, domains, bank_sign, partial, boundary, obstacles
                    ),
                    *_generic_fallback_anchors(role, shape, partial, boundary, obstacles),
                )
            )
        )

    support_query = ConditionalMetricSupportQueryV2(
        runtime_domains,
        process_graph().must_adjacencies,
        lambda partial: _partial_intent_possible(handoff, partial, faces),
        shapes=ordered_shapes,
        boundary=boundary,
        obstacles=obstacles,
        origin_provider=conditional_origins,
        provenance={
            "handoff_hash": handoff.canonical_result_hash,
            "dimension_authority_hash": canonical_hash(dimension_authorities),
            "site_geometry_hash": handoff.source_site_geometry_hash,
        },
    )
    diagnostics.metric_support = support_query.diagnostics
    joint_query = JointMetricCapacityQueryV1(support_query, graph_identity=process_graph().identity)
    diagnostics.metric_capacity = {
        "prunes": 0,
        "support_candidate_attempts": 0,
        "support_candidate_accepts": 0,
        "accepted_partial_with_zero_capacity": 0,
        "accepted_partial_with_unknown_capacity": 0,
        "accepted_partial_with_pairwise_unknown": 0,
        "accepted_partial_with_joint_certificate": 0,
        "accepted_partial_with_false_positive_joint_proof": 0,
        "accepted_partial_pairwise_supported": 0,
        "joint_unplaced_role_capacity_proven": False,
        "final_consumed": [],
        "final_joint_certificates": [],
        "legacy_role_specific_seed_calls": 0,
    }
    role_rank = {role: index for index, role in enumerate(order)}
    for role in order:
        diagnostics.funnel[role] = {
            "role_attempt_count": 0,
            "authority_shape_variant_count": len(authority_shapes[role]),
            "authority_rotation_variant_count": len(
                {shape.rotation_deg for shape in authority_shapes[role]}
            ),
            "construction_shape_variant_count": len(ordered_shapes[role]),
            "shape_variant_attempt_count": 0,
            "domain_derived_anchor_count": 0,
            "generic_fallback_anchor_count": 0,
            "candidate_rectangle_attempt_count": 0,
            "site_rejection_count": 0,
            "obstacle_rejection_count": 0,
            "overlap_rejection_count": 0,
            "domain_side_rejection_count": 0,
            "must_edge_rejection_count": 0,
            "coupled_interface_rejection_count": 0,
            "composition_intent_rejection_count": 0,
            "accepted_partial_placement_count": 0,
            "backtrack_count": 0,
        }
        diagnostics.authority_shape_count[role] = len(authority_shapes[role])
        diagnostics.construction_shape_count[role] = len(ordered_shapes[role])
        diagnostics.domain_anchor_count[role] = 0
        diagnostics.generic_anchor_count[role] = 0
        diagnostics.generic_nodes_by_role[role] = 0

    # These are conservative gates only. Construction domains do not become
    # engineering authority, so uncertain capacity always proceeds to search.
    required_roles = {item.zone_role for item in handoff.zone_role_assignment}
    diagnostics.shipping_office_status = (
        _shipping_office_interface_preflight_status(
            ordered_shapes["shipping_channel"], ordered_shapes["office"], boundary
        )
        if {"office", "shipping_channel"} <= required_roles
        else "UNKNOWN_ROLE_COVERAGE"
    )
    site_area = _polygon_area_mm2(boundary)
    total_zone_area = sum(_authority_area_mm2(item) for item in dimension_authorities.values())
    principal_band_groups = tuple(
        tuple(role for role in band.zone_roles if role in required_roles)
        for band in handoff.principal_band_intents
    )
    peripheral_groups = tuple(
        tuple(role for role in domain.zone_roles if role in required_roles)
        for domain in handoff.peripheral_domain_intents
        if domain.zone_roles
    )
    diagnostics_band_status = _capacity_preflight_status(
        principal_band_groups,
        dimension_authorities,
        authority_shapes,
        boundary,
    )
    diagnostics_peripheral_status = _capacity_preflight_status(
        peripheral_groups,
        dimension_authorities,
        authority_shapes,
        boundary,
    )
    diagnostics.band_capacity_status = diagnostics_band_status
    diagnostics.peripheral_capacity_status = diagnostics_peripheral_status

    def rejection_count() -> int:
        return sum(
            value
            for role_funnel in diagnostics.funnel.values()
            for key, value in role_funnel.items()
            if key.endswith("_rejection_count")
        )

    def save_witness(placed: Mapping[str, PlacedRectangleV1], next_role: str) -> None:
        role_bounds = tuple((role, _bounds(placed[role])) for role in ZONE_CODES if role in placed)
        key = (-len(placed), rejection_count(), role_bounds)
        if diagnostics.best_witness_key is not None and key >= diagnostics.best_witness_key:
            return
        diagnostics.best_witness_key = key
        diagnostics.best_witness = PartialPlacementWitnessV1(
            composition_identity=handoff.composition_identity,
            placed_roles=tuple(role for role in ZONE_CODES if role in placed),
            zone_bounds_mm=role_bounds,
            next_role=next_role,
            failure_taxonomy=diagnostics.failure_taxonomy,
            hard_subset_rejection_count=rejection_count(),
            bank_sign=bank_sign,
            nodes_used=diagnostics.nodes,
        )

    def set_attempted(role: str, placed: Mapping[str, PlacedRectangleV1]) -> None:
        if diagnostics.deepest_attempted == "NOT_ATTEMPTED" or role_rank[role] > role_rank.get(
            diagnostics.deepest_attempted, -1
        ):
            diagnostics.deepest_attempted = role
        diagnostics.funnel[role]["role_attempt_count"] += 1
        save_witness(placed, role)

    def count_candidate_failure(role: str, reason: str) -> None:
        diagnostics.funnel[role][f"{reason.lower()}_rejection_count"] += 1
        diagnostics.failure_taxonomy = f"{role.upper()}_{reason}_REJECTION"

    def recurse(
        index: int,
        placed: dict[str, PlacedRectangleV1],
        support_states: tuple[ConditionalMetricSupportStateV2, ...],
        joint_states: tuple[JointMetricSupportStateV1, ...],
    ) -> dict[str, PlacedRectangleV1] | None:
        if index < len(order):
            set_attempted(order[index], placed)
        if index == len(order):
            must_ok = all(
                rectangles_share_positive_edge(placed[first], placed[second])
                for first, second in process_graph().must_adjacencies
            )
            intent_ok = must_ok and _intent_preserved(handoff, placed, faces)
            consumed_ok = intent_ok and support_query.consumed(placed, support_states)
            consumed_ok = consumed_ok and all(
                state.certificate is not None and joint_query.verify(state.certificate, placed)
                for state in joint_states
            )
            if consumed_ok:
                diagnostics.metric_capacity["final_consumed"] = [
                    state.certificate.proof()
                    for state in support_states
                    if state.certificate is not None
                ]
                diagnostics.metric_capacity["final_joint_certificates"] = [
                    state.certificate.proof()
                    for state in joint_states
                    if state.certificate is not None
                ]
                return dict(placed)
            diagnostics.failure_taxonomy = (
                "FINAL_MUST_ADJACENCY_REJECTION"
                if not must_ok
                else "COMPOSITION_INTENT_REJECTION"
                if not intent_ok
                else "FINAL_METRIC_RESERVATION_UNCONSUMED"
            )
            save_witness(placed, "COMPLETE")
            return None
        code = order[index]
        neighbors = tuple(name for name in _must_neighbors(code) if name in placed)
        axis, interval = _domain_interval(code, handoff, domains)

        def ordered_points(
            points: Sequence[tuple[int, int]], shape: _Shape
        ) -> tuple[tuple[int, int], ...]:
            def key(point: tuple[int, int]) -> tuple[int, int, int, int, int, int]:
                projection = (
                    point[0] + shape.world_width_mm // 2
                    if axis == "X"
                    else point[1] + shape.world_depth_mm // 2
                )
                interval_penalty = 0
                if interval is not None:
                    low, high = interval
                    interval_penalty = (
                        0
                        if low <= projection <= high
                        else min(abs(projection - low), abs(projection - high))
                    )
                sorting = placed.get("sorting_packaging_room")
                side_penalty = 0
                cross_penalty = 0
                process_center_penalty = 0
                if code == "sorting_packaging_room":
                    if handoff.process_axis == ProcessAxisV1.X:
                        process_center = (
                            min(item[0] for item in boundary) + max(item[0] for item in boundary)
                        ) // 2
                        process_center_penalty = abs(projection - process_center)
                        cross_center = point[1] + shape.world_depth_mm // 2
                        site_center = (
                            min(item[1] for item in boundary) + max(item[1] for item in boundary)
                        ) // 2
                    else:
                        process_center = (
                            min(item[1] for item in boundary) + max(item[1] for item in boundary)
                        ) // 2
                        process_center_penalty = abs(projection - process_center)
                        cross_center = point[0] + shape.world_width_mm // 2
                        site_center = (
                            min(item[0] for item in boundary) + max(item[0] for item in boundary)
                        ) // 2
                    cross_penalty = abs(cross_center - site_center)
                    if handoff.family != CompositionFamilyV2.CENTRAL_PROCESS_CORE:
                        process_center_penalty = 0
                if sorting is not None and code in faces:
                    ref_axis, sign = faces[code]
                    coordinate = (
                        point[0] + shape.world_width_mm // 2
                        if ref_axis == "X"
                        else point[1] + shape.world_depth_mm // 2
                    )
                    side_penalty = 0 if (coordinate - _center(sorting, ref_axis)) * sign > 0 else 1
                return (
                    interval_penalty,
                    process_center_penalty,
                    cross_penalty,
                    side_penalty,
                    point[0],
                    point[1],
                )

            return tuple(sorted(set(points), key=key))

        # The complete finite domain-derived set is attempted first across all
        # authority shapes. Generic physical-event anchors are a bounded,
        # explicitly secondary continuation.
        domain_origins_by_shape: dict[_Shape, set[tuple[int, int]]] = {}
        support_candidates = support_query.support_candidates(code, placed, support_states)
        attempted: set[tuple[_Shape, int, int]] = set()
        for source in ("METRIC_RESERVATION_SUPPORT", "DOMAIN", "GENERIC"):
            if source == "GENERIC" and diagnostics.generic_nodes >= max(1, node_limit // 10):
                break
            source_shapes = (
                tuple(dict.fromkeys(shape for shape, _ in support_candidates))
                if source == "METRIC_RESERVATION_SUPPORT"
                else ordered_shapes[code]
            )
            for shape in source_shapes:
                if shape not in ordered_shapes[code]:
                    raise ValueError("METRIC_SUPPORT_SHAPE_AUTHORITY_MISMATCH")
                diagnostics.funnel[code]["shape_variant_attempt_count"] += 1
                if source == "METRIC_RESERVATION_SUPPORT":
                    origins = tuple(
                        origin
                        for supplied_shape, origin in support_candidates
                        if supplied_shape == shape
                    )
                elif source == "DOMAIN":
                    origins = _domain_derived_anchors(
                        code, shape, handoff, domains, bank_sign, placed, boundary, obstacles
                    )
                    diagnostics.domain_anchor_count[code] += len(origins)
                    diagnostics.funnel[code]["domain_derived_anchor_count"] += len(origins)
                    domain_origins_by_shape[shape] = set(origins)
                else:
                    if diagnostics.generic_nodes >= max(1, node_limit // 10):
                        break
                    origins = _generic_fallback_anchors(code, shape, placed, boundary, obstacles)
                    origins = tuple(
                        point
                        for point in origins
                        if point not in domain_origins_by_shape.get(shape, set())
                    )
                    diagnostics.generic_anchor_count[code] += len(origins)
                    diagnostics.funnel[code]["generic_fallback_anchor_count"] += len(origins)
                points = (
                    origins
                    if source == "METRIC_RESERVATION_SUPPORT"
                    else ordered_points(origins, shape)
                )
                for x, y in points:
                    candidate_key = (shape, x, y)
                    if candidate_key in attempted:
                        continue
                    if diagnostics.nodes >= node_limit:
                        diagnostics.budget_hit = True
                        diagnostics.failure_taxonomy = "PLACEMENT_NODE_BUDGET_EXHAUSTED"
                        save_witness(placed, code)
                        return None
                    if source == "GENERIC" and diagnostics.generic_nodes >= max(
                        1, node_limit // 10
                    ):
                        break
                    attempted.add(candidate_key)
                    diagnostics.nodes += 1
                    diagnostics.funnel[code]["candidate_rectangle_attempt_count"] += 1
                    if source == "METRIC_RESERVATION_SUPPORT":
                        diagnostics.metric_capacity["support_candidate_attempts"] += 1
                        support_query.candidate_event(
                            "candidate_attempts", code, (shape, (x, y)), placed, support_states
                        )
                    if source == "GENERIC":
                        diagnostics.generic_nodes += 1
                        diagnostics.generic_nodes_by_role[code] += 1
                    candidate = _rectangle(code, x, y, shape)
                    rejected = _candidate_rejection(candidate, placed, boundary, obstacles)
                    if rejected is not None:
                        count_candidate_failure(code, rejected)
                        save_witness(placed, code)
                        continue
                    if neighbors and any(
                        not rectangles_share_positive_edge(candidate, placed[neighbor])
                        for neighbor in neighbors
                    ):
                        diagnostics.funnel[code]["must_edge_rejection_count"] += 1
                        diagnostics.failure_taxonomy = f"{code.upper()}_MUST_EDGE_REJECTION"
                        save_witness(placed, code)
                        continue
                    sorting = placed.get("sorting_packaging_room")
                    if sorting is not None and not _side_ok(code, candidate, sorting, faces):
                        diagnostics.funnel[code]["domain_side_rejection_count"] += 1
                        diagnostics.failure_taxonomy = f"{code.upper()}_DOMAIN_SIDE_REJECTION"
                        save_witness(placed, code)
                        continue
                    placed[code] = candidate
                    if not _partial_intent_possible(handoff, placed, faces):
                        diagnostics.funnel[code]["composition_intent_rejection_count"] += 1
                        diagnostics.failure_taxonomy = (
                            f"{code.upper()}_PARTIAL_COMPOSITION_INTENT_REJECTION"
                        )
                        save_witness(
                            placed,
                            order[index + 1] if index + 1 < len(order) else "COMPLETE",
                        )
                        placed.pop(code, None)
                        continue
                    child_support = support_query.update(placed, support_states)
                    if any(
                        state.status == ConditionalSupportStatusV2.NONE for state in child_support
                    ):
                        diagnostics.metric_capacity["prunes"] += 1
                        diagnostics.failure_taxonomy = "METRIC_RESERVATION_CAPACITY_CLOSED"
                        placed.pop(code, None)
                        save_witness(placed, code)
                        continue
                    pairwise_unknown = any(
                        state.status == ConditionalSupportStatusV2.UNKNOWN
                        for state in child_support
                    )
                    child_joint = joint_query.update(placed, child_support, joint_states)
                    if any(
                        state.status == ConditionalSupportStatusV2.NONE for state in child_joint
                    ):
                        diagnostics.metric_capacity["prunes"] += 1
                        diagnostics.failure_taxonomy = "JOINT_METRIC_CAPACITY_PROVED_ZERO"
                        placed.pop(code, None)
                        save_witness(placed, code)
                        continue
                    if pairwise_unknown:
                        diagnostics.metric_capacity["accepted_partial_with_pairwise_unknown"] += 1
                    else:
                        diagnostics.metric_capacity["accepted_partial_pairwise_supported"] += 1
                    if any(
                        state.status == ConditionalSupportStatusV2.UNKNOWN for state in child_joint
                    ):
                        diagnostics.metric_capacity["accepted_partial_with_unknown_capacity"] += 1
                    else:
                        diagnostics.metric_capacity["accepted_partial_with_joint_certificate"] += 1
                    if source == "METRIC_RESERVATION_SUPPORT":
                        diagnostics.metric_capacity["support_candidate_accepts"] += 1
                        support_query.candidate_event(
                            "candidate_accepts",
                            code,
                            (shape, (x, y)),
                            {r: v for r, v in placed.items() if r != code},
                            support_states,
                        )
                    diagnostics.max_placed = max(diagnostics.max_placed, len(placed))
                    if diagnostics.deepest_successfully_placed == "NOT_PLACED" or role_rank[
                        code
                    ] > role_rank.get(diagnostics.deepest_successfully_placed, -1):
                        diagnostics.deepest_successfully_placed = code
                    diagnostics.funnel[code]["accepted_partial_placement_count"] += 1
                    diagnostics.failure_taxonomy = "PARTIAL_PLACEMENT_ACCEPTED"
                    save_witness(placed, order[index + 1] if index + 1 < len(order) else "COMPLETE")
                    solution = recurse(index + 1, placed, child_support, child_joint)
                    if solution is not None:
                        return solution
                    placed.pop(code, None)
                    diagnostics.funnel[code]["backtrack_count"] += 1
                    if diagnostics.budget_hit:
                        return None
        return None

    if total_zone_area > site_area:
        diagnostics.failure_taxonomy = "AUTHORITATIVE_ZONE_AREA_EXCEEDS_BUILDABLE_SITE_AREA"
        save_witness({}, "PREFLIGHT")
        return _SearchOutcome(
            solution=None,
            diagnostics=diagnostics,
            deepest_attempted="NOT_ATTEMPTED",
            deepest_successfully_placed="NOT_PLACED",
        )
    root_support = support_query.update({})
    diagnostics.metric_capacity["root"] = [asdict(state) for state in root_support]
    root_joint = joint_query.update({}, root_support)
    diagnostics.metric_capacity["root_joint"] = [asdict(state) for state in root_joint]
    if any(state.status == ConditionalSupportStatusV2.NONE for state in root_support) or any(
        state.status == ConditionalSupportStatusV2.NONE for state in root_joint
    ):
        diagnostics.metric_capacity["prunes"] += 1
        diagnostics.failure_taxonomy = "ROOT_METRIC_RESERVATION_CAPACITY_CLOSED"
        save_witness({}, order[0])
        solution = None
    else:
        solution = recurse(0, {}, root_support, root_joint)
    diagnostics.metric_capacity["joint_capacity"] = joint_query.diagnostics()
    diagnostics.metric_capacity["joint_unplaced_role_capacity_proven"] = (
        all(state.status == ConditionalSupportStatusV2.SUPPORTED for state in root_joint)
        and diagnostics.metric_capacity["accepted_partial_with_unknown_capacity"] == 0
    )
    if diagnostics.best_witness is None:
        diagnostics.failure_taxonomy = "NO_PARTIAL_PLACEMENT"
        save_witness({}, order[0])
    return _SearchOutcome(
        solution=solution,
        diagnostics=diagnostics,
        deepest_attempted=diagnostics.deepest_attempted,
        deepest_successfully_placed=diagnostics.deepest_successfully_placed,
    )


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


def validate_composition_placement_node_budget(node_budget: int) -> None:
    """Existing budget contract, also checked before costly runtime construction."""
    if (
        type(node_budget) is not int
        or node_budget < len(FAMILY_ORDER)
        or node_budget > MAX_COMPOSITION_PLACEMENT_NODE_BUDGET
    ):
        raise ValueError("INVALID_COMPOSITION_PLACEMENT_NODE_BUDGET")


def enumerate_composition_placements(
    handoffs: Sequence[StructuralCompositionPlacementHandoffV1],
    dimension_authorities: Mapping[str, Mapping[str, Any]],
    site_geometry: Mapping[str, Any],
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    node_budget: int = DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    runtime_context: MetricRuntimeContextV1 | None = None,
) -> CompositionPlacementEnumerationV1:
    """Generate bounded, family-first exact candidates from server-bound intents."""
    validate_composition_placement_node_budget(node_budget)
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
    obstacles = validated_hard_obstacle_polygons(site_geometry)
    authority_shapes = _authority_shapes(dimension_authorities, boundary, obstacles)
    shapes = {
        role: _canonical_construction_shapes(variants)
        for role, variants in authority_shapes.items()
    }
    if runtime_context is None:
        runtime_context = build_metric_runtime_context(
            handoffs, dimension_authorities, site_geometry, source_site_geometry_hash
        )
    if (
        runtime_context.source_site_geometry_hash != source_site_geometry_hash
        or runtime_context.source_dimension_authorities_hash
        != canonical_hash(dimension_authorities)
        or runtime_context.handoff_hashes != tuple(h.canonical_result_hash for h in handoffs)
    ):
        raise ValueError("METRIC_RUNTIME_CONTEXT_PROVENANCE_MISMATCH")
    expected_edges = tuple(
        r.interface_source_edge_identity for r in handoffs[0].mandatory_interface_reservations
    )
    if tuple(d.source_edge_identity for d in runtime_context.domains) != expected_edges:
        raise ValueError("METRIC_RUNTIME_AUTHORITY_COVERAGE_MISMATCH")
    by_family: dict[CompositionFamilyV2, list[StructuralCompositionPlacementHandoffV1]] = (
        defaultdict(list)
    )
    for item in handoffs:
        by_family[item.family].append(item)
    if set(by_family) != set(FAMILY_ORDER):
        raise ValueError("COMPOSITION_FAMILY_COVERAGE_INVALID")

    per_attempt_budget = max(1, node_budget // (len(FAMILY_ORDER) * 2 * 2))
    initial_family_budget = per_attempt_budget * 2
    continuation_budget = max(0, node_budget - initial_family_budget * len(FAMILY_ORDER))
    remaining = node_budget
    attempts: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    used: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    deepest_attempted_by_family: dict[str, str] = {
        family.value: "NOT_ATTEMPTED" for family in FAMILY_ORDER
    }
    deepest_attempted_rank: dict[str, int] = {family.value: -1 for family in FAMILY_ORDER}
    deepest_successfully_placed: dict[str, str] = {
        family.value: "NOT_PLACED" for family in FAMILY_ORDER
    }
    deepest_success_rank: dict[str, int] = {family.value: -1 for family in FAMILY_ORDER}
    max_placed_by_family: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    domain_anchor_by_family: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    generic_anchor_by_family: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    generic_nodes_by_family: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    failures: dict[str, str] = {}
    hashes = (source_zone_plan_hash, source_p1_handoff_hash, source_site_geometry_hash)
    candidate_by_family: dict[CompositionFamilyV2, CompositionPlacementCandidateV1] = {}
    search_attempts: list[CompositionPlacementSearchAttemptV1] = []
    # True family-first rounds: every family receives its positive-bank probe
    # before any family receives the mirrored probe, then composition variants
    # continue in the same deterministic family order.
    tasks = [(family, by_family[family][0], 1) for family in FAMILY_ORDER]
    tasks.extend((family, by_family[family][0], -1) for family in FAMILY_ORDER)
    tasks.extend(
        (family, by_family[family][1], 1) for family in FAMILY_ORDER if len(by_family[family]) > 1
    )
    tasks.extend(
        (family, by_family[family][1], -1) for family in FAMILY_ORDER if len(by_family[family]) > 1
    )
    for family, handoff, bank_sign in tasks:
        if remaining <= 0 or family in candidate_by_family:
            continue
        family_key = family.value
        attempts[family_key] += 1
        domains = _domain_arrangement(handoff, bank_sign, boundary, dimension_authorities)
        allocation = min(per_attempt_budget, remaining)
        outcome = _search_one(
            handoff,
            shapes,
            authority_shapes,
            dimension_authorities,
            boundary,
            obstacles,
            domains,
            bank_sign,
            allocation,
            runtime_context.domains,
        )
        solution = outcome.solution
        diagnostics = outcome.diagnostics
        visited = diagnostics.nodes
        hit = diagnostics.budget_hit
        deepest_attempted = outcome.deepest_attempted
        used[family_key] += visited
        domain_anchor_by_family[family_key] += sum(diagnostics.domain_anchor_count.values())
        generic_anchor_by_family[family_key] += sum(diagnostics.generic_anchor_count.values())
        generic_nodes_by_family[family_key] += diagnostics.generic_nodes
        max_placed_by_family[family_key] = max(
            max_placed_by_family[family_key], diagnostics.max_placed
        )
        attempt_role_rank = {role: index for index, role in enumerate(_zone_order(handoff))}
        if attempt_role_rank.get(deepest_attempted, -1) >= deepest_attempted_rank[family_key]:
            deepest_attempted_by_family[family_key] = deepest_attempted
            deepest_attempted_rank[family_key] = attempt_role_rank.get(deepest_attempted, -1)
        deepest_placed = outcome.deepest_successfully_placed
        if (
            deepest_placed != "NOT_PLACED"
            and attempt_role_rank[deepest_placed] >= deepest_success_rank[family_key]
        ):
            deepest_successfully_placed[family_key] = deepest_placed
            deepest_success_rank[family_key] = attempt_role_rank[deepest_placed]
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
                deepest_role_attempted=outcome.deepest_attempted,
                deepest_role_successfully_placed=deepest_placed,
                max_simultaneously_placed_role_count=diagnostics.max_placed,
                role_search_funnel=tuple(
                    RoleSearchFunnelV1(
                        zone_role=role,
                        **metrics,
                    )
                    for role, metrics in diagnostics.funnel.items()
                ),
                domain_derived_anchor_count_by_role=tuple(
                    (role, diagnostics.domain_anchor_count[role]) for role in _zone_order(handoff)
                ),
                generic_fallback_anchor_count_by_role=tuple(
                    (role, diagnostics.generic_anchor_count[role]) for role in _zone_order(handoff)
                ),
                generic_fallback_node_count_by_role=tuple(
                    (role, diagnostics.generic_nodes_by_role[role]) for role in _zone_order(handoff)
                ),
                authority_shape_variant_count_by_role=tuple(
                    (role, diagnostics.authority_shape_count[role]) for role in _zone_order(handoff)
                ),
                construction_shape_variant_count_by_role=tuple(
                    (role, diagnostics.construction_shape_count[role])
                    for role in _zone_order(handoff)
                ),
                shipping_office_interface_preflight_status=diagnostics.shipping_office_status,
                band_capacity_preflight_status=diagnostics.band_capacity_status,
                peripheral_capacity_preflight_status=diagnostics.peripheral_capacity_status,
                best_partial_placement_witness=diagnostics.best_witness
                or PartialPlacementWitnessV1(
                    composition_identity=handoff.composition_identity,
                    placed_roles=(),
                    zone_bounds_mm=(),
                    next_role=_zone_order(handoff)[0],
                    failure_taxonomy="NO_PARTIAL_PLACEMENT",
                    hard_subset_rejection_count=0,
                    bank_sign=bank_sign,
                    nodes_used=visited,
                ),
                node_budget_exhausted=hit,
                complete_layout_found=solution is not None,
                failure_reason=attempt_failure,
                metric_reservation_diagnostics={
                    **diagnostics.metric_capacity,
                    **diagnostics.metric_support.to_dict(),
                },
            )
        )
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
                    ("domain_anchor_path", "COMPOSITION_DOMAIN_FIRST_BOUNDED_GENERIC_FALLBACK"),
                    ("shipping_office_preflight", diagnostics.shipping_office_status),
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
    best_partial_by_family: dict[str, PartialPlacementWitnessV1] = {}
    for attempt in search_attempts:
        witness = attempt.best_partial_placement_witness
        family_key = attempt.family.value
        current = best_partial_by_family.get(family_key)
        witness_key = (
            -len(witness.placed_roles),
            witness.hard_subset_rejection_count,
            witness.zone_bounds_mm,
            witness.composition_identity,
            witness.bank_sign,
        )
        if current is None or witness_key < (
            -len(current.placed_roles),
            current.hard_subset_rejection_count,
            current.zone_bounds_mm,
            current.composition_identity,
            current.bank_sign,
        ):
            best_partial_by_family[family_key] = witness

    nodes_used = sum(used.values())
    return CompositionPlacementEnumerationV1(
        identity=IDENTITY,
        schema_version=SCHEMA_VERSION,
        node_budget=node_budget,
        nodes_used=nodes_used,
        node_budget_exhausted=nodes_used >= node_budget,
        initial_family_budget=initial_family_budget,
        continuation_budget=continuation_budget,
        continuation_selection_reason=(
            "ROUND_1: positive-bank probe for each family; ROUND_2: mirrored first-composition "
            "probe for each family; only then deterministic second-composition continuations "
            "in family order, each bounded by the same per-attempt slice"
        ),
        family_coverage_order=tuple(family.value for family in FAMILY_ORDER),
        family_first_round_complete=all(attempts[family.value] >= 1 for family in FAMILY_ORDER),
        attempt_count_by_family=tuple(
            (family.value, attempts[family.value]) for family in FAMILY_ORDER
        ),
        nodes_used_by_family=tuple((family.value, used[family.value]) for family in FAMILY_ORDER),
        deepest_role_attempted_by_family=tuple(
            (family.value, deepest_attempted_by_family[family.value]) for family in FAMILY_ORDER
        ),
        deepest_role_successfully_placed_by_family=tuple(
            (family.value, deepest_successfully_placed[family.value]) for family in FAMILY_ORDER
        ),
        max_simultaneously_placed_role_count_by_family=tuple(
            (family.value, max_placed_by_family[family.value]) for family in FAMILY_ORDER
        ),
        best_partial_placement_witness_by_family=tuple(
            (family.value, best_partial_by_family[family.value])
            for family in FAMILY_ORDER
            if family.value in best_partial_by_family
        ),
        domain_derived_anchor_count_by_family=tuple(
            (family.value, domain_anchor_by_family[family.value]) for family in FAMILY_ORDER
        ),
        generic_fallback_anchor_count_by_family=tuple(
            (family.value, generic_anchor_by_family[family.value]) for family in FAMILY_ORDER
        ),
        generic_fallback_node_count_by_family=tuple(
            (family.value, generic_nodes_by_family[family.value]) for family in FAMILY_ORDER
        ),
        failure_reason_by_family=tuple((key, failures[key]) for key in sorted(failures)),
        search_attempts=tuple(search_attempts),
        candidates=tuple(candidates),
        metric_runtime_diagnostics={
            "unique_domain_build_count": len(runtime_context.domains),
            "reused_across_compositions": True,
            "total_valid_slot_count": sum(len(d.slots) for d in runtime_context.domains),
            "domains": [
                {
                    "source_edge_identity": d.source_edge_identity,
                    "roles": d.summary.roles,
                    "valid_slot_count": len(d.slots),
                    "slot_set_digest": d.summary.slot_set_digest,
                    "finite_domain_identity": d.summary.finite_domain_identity,
                    "finite_domain_complete": d.summary.complete,
                }
                for d in runtime_context.domains
            ],
        },
    )
