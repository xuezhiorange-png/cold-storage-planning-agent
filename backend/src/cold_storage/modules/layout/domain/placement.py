"""Deterministic placement search for the V2.2 P2C MVP.

This module consumes already-bound zone dimensions and site geometry. It does
not calculate zone areas or generate a building envelope. Structured search
may call application-injected authoritative truck/access validators during
construction; final P2D still independently validates all routes. Geometry is
represented as integer millimetres at the predicate boundary so the bounded
search is repeatable and has no floating-point tolerance.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Context, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from itertools import islice, product
from math import isqrt
from typing import Any, Final, cast

from cold_storage.modules.layout.domain.adjacency import AdjacencyGraphV1
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.main_process_skeleton import (
    MainProcessSkeletonCandidateV1,
    canonicalize_main_process_skeleton_for_evaluation,
)
from cold_storage.modules.layout.domain.main_process_topology import (
    classify_main_process_topology_v1,
    decide_main_process_topology_ownership_v1,
)
from cold_storage.modules.layout.domain.objective_profile import (
    CARDINAL_LOADING_SIDE_METRIC,
    LOADING_SIDE_PREFERENCE,
    NEAREST_TRUCK_ENTRANCE_COMPARATOR,
    NEAREST_TRUCK_ENTRANCE_INTERNAL_UNIT,
    SHOULD_ADJACENT,
    approved_objective_profile,
)
from cold_storage.modules.layout.domain.site_geometry import (
    GRID_M,
    MILLIMETRES_PER_METRE,
    PlacedRectangleV1,
    PolygonMM,
    SegmentMM,
    normalize_polygon,
    normalize_segment,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
    segments_share_positive_length,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    FINISHED_SIDE_GROUP,
    FUNCTIONAL_GROUPS,
    LINEAR_PROCESS_BAND,
    MAIN_PROCESS_SKELETON_ZONE_CODES,
    MAIN_PROCESS_ZONE_CODES,
    OFFSET_LINEAR_BAND,
    PROCESSING_CORE_GROUP,
    RAW_SIDE_GROUP,
    STRAIGHT_LINEAR_BAND,
    SUPPORT_GROUP,
    StructuralCompositionFamilyV1,
    StructuralSkeletonV1,
    functional_group_for_zone,
    select_structural_composition_family,
    structural_anchor_references,
    structural_skeleton_candidates,
)
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
    FunctionalBandV1,
    LocalBuildingCompositionV1,
    LocalZonePlacementV1,
    PrimaryGridV1,
    StructuredBuildingSkeletonV1,
    _must_chain_alignment_sequences,
    _must_chain_side_sequences,
    _zone_dimension_options,
    construct_legacy_compatibility_search_plan_v1,
    construct_structured_building_plan_v1,
    structured_layout_family_for_topology,
    zone_band_assignment,
)
from cold_storage.modules.layout.domain.tail_slot_feasibility import (
    EVENT_COMPLETENESS_UNAVAILABLE,
    EXACT_ORTHOGONAL_EVENT_ENUMERATION,
    enumerate_tail_zone_site_anchors_v1,
    evaluate_tail_zone_slot_feasibility_v1,
)

IDENTITY: Final = "site-constrained-deterministic-placement@1.0.0"
PLACEMENT_RESULT_IDENTITY: Final = "site_constrained_factory_layout@1.0.0"
SCHEMA_VERSION: Final = "1.0.0"
SEARCH_PROFILE_IDENTITY: Final = "deterministic-placement-search@1.0.0"
GRID_MM: Final = 1
LOCAL_COMPOSITION_SHAPE_VARIANT_LIMIT: Final = 128
LOCAL_COMPACT_FRONTIER_LIMIT: Final = 48
LOCAL_COMPACT_RESULT_LIMIT: Final = 32
DEFAULT_NODE_BUDGET: Final = 50_000
MAX_OPTIONS_PER_ZONE: Final = 48
STRUCTURED_MAX_OPTIONS_PER_ZONE: Final = 6
TAIL_ACCESS_ROUTE_REPRESENTATIVE_LIMIT: Final = 12
STRUCTURED_PHASE: Final = "STRUCTURED"
GENERAL_FALLBACK_PHASE: Final = "GENERAL_FALLBACK"
LEGACY_COMPAT_PHASE: Final = "LEGACY_COMPAT"
_DIRECT_STRUCTURAL_VARIANT_ROUNDS: Final = (
    (0, RECTANGLE, "DEFAULT_SUPPORT_SIDE", "POSITIVE", 0, 0),
    (0, RECTANGLE, "DEFAULT_SUPPORT_SIDE", "NEGATIVE", 1, -1),
    (0, RECTANGLE, "PERPENDICULAR_SUPPORT_SIDE_A", "POSITIVE", 0, 0),
    (0, RECTANGLE, "PERPENDICULAR_SUPPORT_SIDE_A", "NEGATIVE", 1, -1),
    (0, RECTANGLE, "PERPENDICULAR_SUPPORT_SIDE_B", "POSITIVE", 0, 0),
    (0, RECTANGLE, "PERPENDICULAR_SUPPORT_SIDE_B", "NEGATIVE", 1, -1),
    (1, RECTANGLE, "DEFAULT_SUPPORT_SIDE", "POSITIVE", 0, -1),
    (1, RECTANGLE, "DEFAULT_SUPPORT_SIDE", "NEGATIVE", 1, -1),
    (1, RECTANGLE, "PERPENDICULAR_SUPPORT_SIDE_A", "POSITIVE", 0, 0),
    (1, RECTANGLE, "PERPENDICULAR_SUPPORT_SIDE_A", "NEGATIVE", 1, -1),
    (1, RECTANGLE, "PERPENDICULAR_SUPPORT_SIDE_B", "POSITIVE", 0, 0),
    (1, RECTANGLE, "PERPENDICULAR_SUPPORT_SIDE_B", "NEGATIVE", 1, -1),
)
DIRECT_SYNTHESIS_ATTEMPT_COUNT: Final = len(_DIRECT_STRUCTURAL_VARIANT_ROUNDS) * len(
    BASE_LAYOUT_FAMILIES
)
# Bound the tail search under one already placed main-process skeleton so the
# deterministic node budget reaches distinct process arrangements before it
# is consumed by office/support permutations. A small fixed sample preserves
# P2D-relevant personnel/support alternatives without treating those
# variations as new process skeletons.
STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON: Final = 2
# Bound the tail search under a core root, but preserve a small set of
# personnel/support variants for P2D to evaluate against its unchanged access,
# truck, and single-building-footprint authorities.
STRUCTURED_COMPLETIONS_PER_CORE_ROOT: Final = 4
MIN_CONSTRUCTIVE_SKELETON_NODE_ALLOWANCE: Final = 15
# At the frozen 120-node global cutoff this permits up to eight geometry
# seeds (120 / 15), rather than stopping each topology after two raw seeds.
# The shared scheduler remains the actual global bound; rejected preflights
# therefore cannot turn this per-lane ceiling into a production quota.
CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT: Final = 8
STRUCTURED_SKELETON_CONSTRUCTION_SHARE_NUMERATOR: Final = 1
STRUCTURED_SKELETON_CONSTRUCTION_SHARE_DENOMINATOR: Final = 2
# Construction-share values are scheduler quantum ceilings, not lifetime
# search termination limits. Each topology keeps its generator continuation.
ALTERNATIVE_TOPOLOGY_CONSTRUCTION_SHARE_NUMERATOR: Final = 3
ALTERNATIVE_TOPOLOGY_CONSTRUCTION_SHARE_DENOMINATOR: Final = 4
CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET: Final = 20
CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET: Final = 16
# A scheduler turn is a bounded fairness quantum. Its generator remains alive
# after yielding, so reaching this limit never declares the search exhausted.
PLACEMENT_SEARCH_QUANTUM_NODES: Final = CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET
_CARDINAL_SIDES: Final = ("WEST", "EAST", "SOUTH", "NORTH")
_OPPOSITE_SIDE: Final = {"WEST": "EAST", "EAST": "WEST", "SOUTH": "NORTH", "NORTH": "SOUTH"}

# Group -> band -> zone order: first the authoritative main process, then the
# peripheral personnel interface whose main-entrance access is frozen, then
# local support branches. The complete process skeleton is constructed and
# frozen before either tail group is searched; this ordering only reserves
# access-critical perimeter geometry before support occupies remaining faces.
PLACEMENT_ZONE_ORDER: Final = (
    "raw_fruit_buffer",
    "primary_precooling_room",
    "sorting_packaging_room",
    "secondary_precooling_room",
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
    "changing_room",
    "office",
    "packaging_material_storage",
    "secondary_fruit_buffer",
    "frozen_fruit_room",
)
STRUCTURED_PLACEMENT_ZONE_ORDER: Final = (
    "sorting_packaging_room",
    "primary_precooling_room",
    "raw_fruit_buffer",
    "secondary_precooling_room",
    # Place the dimensioned transition room first so the flexible coating
    # room can bridge the actual P2C core interfaces instead of guessing a
    # future secondary-precooling rectangle.
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
    # The process skeleton is already immutable. Place personnel/access tails
    # before support so peripheral support cannot consume their feasible access
    # corridor; neither tail can move any main-process rectangle.
    "changing_room",
    "office",
    "packaging_material_storage",
    "frozen_fruit_room",
    "secondary_fruit_buffer",
)
LINEAR_STRUCTURED_PLACEMENT_ZONE_ORDER: Final = (
    # A linear lane starts at the raw-side band and grows toward the core and
    # finished side. This is a different search skeleton from the hub lane,
    # not merely another sort order for the same root-first search.
    "raw_fruit_buffer",
    "primary_precooling_room",
    "sorting_packaging_room",
    "secondary_precooling_room",
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
    "changing_room",
    "office",
    "packaging_material_storage",
    "frozen_fruit_room",
    "secondary_fruit_buffer",
)
FLEXIBLE_ZONE_CODES: Final = ("coating_room", "changing_room", "office")
SUPPORT_ZONE_CODES: Final = FUNCTIONAL_GROUPS[SUPPORT_GROUP]


@dataclass(frozen=True)
class PlacementCandidateV1:
    """Immutable selected-candidate evidence, excluding derived hash input."""

    payload_json: str
    _content_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> PlacementCandidateV1:
        content = dict(payload)
        content.pop("canonical_candidate_hash", None)
        normalized = canonical_json(content)
        return cls(normalized, canonical_hash(content))

    def to_dict(self) -> dict[str, Any]:
        import json

        value = cast(dict[str, Any], json.loads(self.payload_json))
        value["canonical_candidate_hash"] = self._content_hash
        return value

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_candidate_hash(self) -> str:
        return self._content_hash


@dataclass(frozen=True)
class SitePlacementResultV1:
    """Immutable placement result; route validation is deliberately absent."""

    payload_json: str
    _content_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SitePlacementResultV1:
        content = dict(payload)
        content.pop("canonical_result_hash", None)
        normalized = canonical_json(content)
        return cls(normalized, canonical_hash(content))

    def to_dict(self) -> dict[str, Any]:
        import json

        value = cast(dict[str, Any], json.loads(self.payload_json))
        value["canonical_result_hash"] = self._content_hash
        return value

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return self._content_hash


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _decimal(value: object, *, field: str, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _error("INVALID_PLACEMENT_AUTHORITY", field=field)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise _error("INVALID_PLACEMENT_AUTHORITY", field=field) from None
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise _error("INVALID_PLACEMENT_AUTHORITY", field=field)
    return number


def _mm(value: object, *, field: str, positive: bool = False) -> int:
    number = _decimal(value, field=field, positive=positive)
    with localcontext(Context(prec=80)):
        scaled = number * MILLIMETRES_PER_METRE
        if scaled != scaled.to_integral_value() or (positive and scaled <= 0):
            raise _error("INVALID_PLACEMENT_GRID_VALUE", field=field, grid_m=str(GRID_M))
        return int(scaled)


def _m(value: int) -> Decimal:
    with localcontext(Context(prec=80)):
        return Decimal(value) / MILLIMETRES_PER_METRE


def _ceil_fraction(value: Fraction) -> int:
    if value.denominator == 1:
        return value.numerator
    return value.numerator // value.denominator + 1


def _ceil_area_depth(required_area_m2: Decimal, width_mm: int) -> int:
    if width_mm <= 0:
        raise _error("INVALID_FLEXIBLE_DIMENSION", field="width_m")
    # 1 m2 = 1,000,000 mm2.  Fraction preserves every decimal digit from the
    # canonical source and makes the outward grid rounding explicit.
    required_mm2 = Fraction(required_area_m2) * 1_000_000
    return max(1, _ceil_fraction(required_mm2 / width_mm))


def _rectangle_from_mm(
    code: str, x_mm: int, y_mm: int, width_mm: int, depth_mm: int, rotation_deg: int
) -> PlacedRectangleV1:
    return PlacedRectangleV1(code, _m(x_mm), _m(y_mm), _m(width_mm), _m(depth_mm), rotation_deg)


def _bounds(rectangle: PlacedRectangleV1) -> tuple[int, int, int, int]:
    return rectangle.bounds_mm


def _authority_code(authority: Mapping[str, Any]) -> str:
    code = authority.get("zone_code")
    if not isinstance(code, str) or not code:
        raise _error("INVALID_PLACEMENT_AUTHORITY", field="zone_code")
    return code


def _authority_mode(authority: Mapping[str, Any]) -> str:
    mode = authority.get("dimension_mode")
    if not isinstance(mode, str) or mode not in {
        "FIXED_RECTANGLE",
        "DETERMINISTIC_GRID_RECTANGLE",
        "FLEXIBLE_RECTANGLE",
    }:
        raise _error("INVALID_PLACEMENT_AUTHORITY", field="dimension_mode")
    return mode


def _authority_dimensions(authority: Mapping[str, Any]) -> tuple[int, int, Decimal]:
    geometry = authority.get("geometry")
    if not isinstance(geometry, Mapping):
        raise _error("FLEXIBLE_DIMENSION_REQUIRED", zone_code=_authority_code(authority))
    width = _mm(geometry.get("width_m"), field="width_m", positive=True)
    depth = _mm(geometry.get("depth_m"), field="depth_m", positive=True)
    area = _decimal(geometry.get("required_area_m2"), field="required_area_m2")
    return width, depth, area


def _required_area(authority: Mapping[str, Any]) -> Decimal:
    return _decimal(authority.get("required_area_m2"), field="required_area_m2")


def _polygon(value: object) -> PolygonMM:
    if not isinstance(value, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT")
    return normalize_polygon(value, allow_numeric_string=True)


def _boundary_extents(boundary: PolygonMM) -> tuple[int, int, int, int]:
    xs = [point[0] for point in boundary]
    ys = [point[1] for point in boundary]
    return min(xs), min(ys), max(xs), max(ys)


def _unique_dimensions(
    authority: Mapping[str, Any], placed: Mapping[str, PlacedRectangleV1], boundary: PolygonMM
) -> tuple[tuple[int, int], ...]:
    mode = _authority_mode(authority)
    if mode != "FLEXIBLE_RECTANGLE":
        width, depth, _ = _authority_dimensions(authority)
        return ((width, depth),)

    required = _required_area(authority)
    required_mm2 = max(1, _ceil_fraction(Fraction(required) * 1_000_000))
    near = max(1, isqrt(required_mm2))
    if near * near < required_mm2:
        near += 1

    width_candidates: set[int] = {near, near + 1}
    min_x, min_y, max_x, max_y = _boundary_extents(boundary)
    width_candidates.update({max_x - min_x, max_y - min_y})
    for point_a, point_b in zip(boundary, boundary[1:] + boundary[:1], strict=True):
        width_candidates.add(abs(point_b[0] - point_a[0]))
        width_candidates.add(abs(point_b[1] - point_a[1]))
    for rectangle in placed.values():
        left, bottom, right, top = _bounds(rectangle)
        width_candidates.update({right - left, top - bottom})

    dimensions: set[tuple[int, int]] = set()
    for width in sorted(width_candidates):
        if width <= 0:
            continue
        depth = _ceil_area_depth(required, width)
        dimensions.add((width, depth))
        dimensions.add((depth, width))
    if not dimensions:
        raise _error("FLEXIBLE_DIMENSION_CANDIDATES_EMPTY", zone_code=_authority_code(authority))
    return tuple(sorted(dimensions))


def _dimension_variants(
    authority: Mapping[str, Any], placed: Mapping[str, PlacedRectangleV1], boundary: PolygonMM
) -> tuple[tuple[int, int, int], ...]:
    dimensions = _unique_dimensions(authority, placed, boundary)
    rotations = (0, 90)
    variants: list[tuple[int, int, int]] = []
    for width, depth in dimensions:
        for rotation in rotations:
            candidate = (width, depth, rotation)
            if candidate not in variants:
                variants.append(candidate)
    return tuple(variants)


def _edge_anchors(
    neighbor: PlacedRectangleV1, width_mm: int, depth_mm: int
) -> tuple[tuple[int, int], ...]:
    left, bottom, right, top = _bounds(neighbor)
    y_values = (bottom, top - depth_mm, bottom + (top - bottom - depth_mm) // 2)
    x_values = (left, right - width_mm, left + (right - left - width_mm) // 2)
    anchors = (
        {(left - width_mm, y) for y in y_values}
        | {(right, y) for y in y_values}
        | {(x, bottom - depth_mm) for x in x_values}
        | {(x, top) for x in x_values}
    )
    return tuple(sorted(anchors))


def _finished_anchors_for_truck_interface(
    shipping_authority: Mapping[str, Any],
    truck_entrance: SegmentMM,
    boundary: PolygonMM,
    finished_width_mm: int,
    finished_depth_mm: int,
) -> tuple[tuple[int, int], ...]:
    """Derive finished-room anchors that can share the truck-side shipping zone."""
    anchors: set[tuple[int, int]] = set()
    for width_mm, depth_mm, rotation in _dimension_variants(shipping_authority, {}, boundary):
        shipping_width, shipping_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        for x_mm, y_mm in _entrance_anchors(truck_entrance, shipping_width, shipping_depth):
            truck_side_shipping = _rectangle_from_mm(
                "shipping_channel",
                x_mm,
                y_mm,
                width_mm,
                depth_mm,
                rotation,
            )
            anchors.update(_edge_anchors(truck_side_shipping, finished_width_mm, finished_depth_mm))
    return tuple(sorted(anchors))


def _minimum_authoritative_axis_extent(
    context: _PlacementSearchContext, zone_code: str, axis: str
) -> int:
    """Return a deterministic lower extent from existing dimension variants."""
    cache_key = (zone_code, axis)
    cached_extent = context.authoritative_axis_extent_cache.get(cache_key)
    if cached_extent is not None:
        return cached_extent
    variants = _dimension_variants(context.authorities[zone_code], {}, context.boundary)
    extents = [
        (depth if rotation == 90 else width)
        if axis == "X"
        else (width if rotation == 90 else depth)
        for width, depth, rotation in variants
    ]
    minimum_extent = min(extents) if extents else 0
    context.authoritative_axis_extent_cache[cache_key] = minimum_extent
    return minimum_extent


def _topology_root_ordering_penalty(
    context: _PlacementSearchContext, rectangle: PlacedRectangleV1
) -> int:
    """Rank roots by a coarse complete-topology envelope; never prune roots.

    Extents are derived from existing authoritative dimension variants. The
    buildable polygon and obstacle constraints remain checked only by the
    exact placement predicates. This estimate is deliberately ordering-only.
    """
    family = context.structural_composition_family
    bounds = _bounds(rectangle)
    axis = context.structural_skeleton.ordering_axis
    low, high = (0, 2) if axis == "X" else (1, 3)
    site_low, site_high = context.boundary_bounds[low], context.boundary_bounds[high]

    if context.structural_topology in {STRAIGHT_LINEAR_BAND, OFFSET_LINEAR_BAND}:
        upstream = max(
            _minimum_authoritative_axis_extent(context, code, axis)
            for code in ("raw_fruit_buffer", "primary_precooling_room")
        )
        downstream = max(
            _minimum_authoritative_axis_extent(context, code, axis)
            for code in (
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
            )
        )
        if family.dominant_direction == "POSITIVE":
            upstream_available = bounds[low] - site_low
            downstream_available = site_high - bounds[high]
        else:
            upstream_available = site_high - bounds[high]
            downstream_available = bounds[low] - site_low
        return max(0, upstream - upstream_available) + max(0, downstream - downstream_available)

    # For the hub, estimate required reach independently on each selected
    # face-pair. Choose the least-penalty pairing for ordering, without
    # rejecting a root based on this coarse rectangle-only estimate.
    penalty_options: list[int] = []
    for raw_side, finished_side in _family_attachment_sides(family):
        penalty = 0
        for side, codes in (
            (raw_side, ("raw_fruit_buffer", "primary_precooling_room")),
            (
                finished_side,
                (
                    "secondary_precooling_room",
                    "coating_room",
                    "finished_goods_room",
                    "shipping_channel",
                ),
            ),
        ):
            measure_axis = "X" if side in {"WEST", "EAST"} else "Y"
            minimum_extent = max(
                _minimum_authoritative_axis_extent(context, code, measure_axis) for code in codes
            )
            measure_low, measure_high = (0, 2) if measure_axis == "X" else (1, 3)
            if side in {"WEST", "SOUTH"}:
                available = bounds[measure_low] - context.boundary_bounds[measure_low]
            else:
                available = context.boundary_bounds[measure_high] - bounds[measure_high]
            penalty += max(0, minimum_extent - available)
        penalty_options.append(penalty)
    return min(penalty_options, default=0)


def _central_core_bridge_anchors(
    sorting: PlacedRectangleV1,
    secondary_authority: Mapping[str, Any],
    *,
    candidate_width_mm: int,
    candidate_depth_mm: int,
    candidate_rotation: int,
    ordering_axis: str,
    boundary: PolygonMM,
) -> tuple[tuple[int, int], ...]:
    """Align the flexible coating core with a dimensioned secondary interface."""
    sort_left, sort_bottom, sort_right, sort_top = _bounds(sorting)
    candidate_x_extent, candidate_y_extent = (
        (candidate_depth_mm, candidate_width_mm)
        if candidate_rotation == 90
        else (candidate_width_mm, candidate_depth_mm)
    )
    secondary_extents: set[int] = set()
    for width_mm, depth_mm, rotation in _dimension_variants(secondary_authority, {}, boundary):
        actual_x, actual_y = (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        secondary_extents.add(actual_x if ordering_axis == "X" else actual_y)

    anchors: set[tuple[int, int]] = set()
    for secondary_extent in secondary_extents:
        if ordering_axis == "Y":
            candidate_y_positions = (
                sort_top + secondary_extent - candidate_y_extent,
                sort_bottom - secondary_extent,
            )
            anchors.update(
                (x, y)
                for y in candidate_y_positions
                for x in (sort_left - candidate_x_extent, sort_right)
            )
        else:
            candidate_x_positions = (
                sort_right + secondary_extent - candidate_x_extent,
                sort_left - secondary_extent,
            )
            anchors.update(
                (x, y)
                for x in candidate_x_positions
                for y in (sort_bottom - candidate_y_extent, sort_top)
            )
    return tuple(sorted(anchors))


def _free_anchors(
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    width_mm: int,
    depth_mm: int,
) -> tuple[tuple[int, int], ...]:
    min_x, min_y, max_x, max_y = _boundary_extents(boundary)
    xs: set[int] = {min_x, max_x - width_mm}
    ys: set[int] = {min_y, max_y - depth_mm}
    for point in boundary:
        xs.update({point[0], point[0] - width_mm})
        ys.update({point[1], point[1] - depth_mm})
    for polygon in obstacles:
        for point in polygon:
            # Obstacles are closed. Add exact one-grid-unit inboard anchors so
            # a structured band can preserve a deterministic clearance while
            # sharing the next legal site line.
            xs.update({point[0], point[0] - width_mm, point[0] - width_mm - 1, point[0] + 1})
            ys.update({point[1], point[1] - depth_mm, point[1] - depth_mm - 1, point[1] + 1})
    anchors: set[tuple[int, int]] = {(x, y) for x in xs for y in ys}
    for rectangle in placed.values():
        left, bottom, right, top = _bounds(rectangle)
        xs.update({left - width_mm, left, right - width_mm, right})
        ys.update({bottom - depth_mm, bottom, top - depth_mm, top})
        anchors.update(_edge_anchors(rectangle, width_mm, depth_mm))
    anchors.update((x, y) for x in xs for y in ys)
    return tuple(sorted(anchors))


def _structural_event_anchors(
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    width_mm: int,
    depth_mm: int,
) -> tuple[tuple[int, int], ...]:
    """Return bounded geometry-event anchors without a Cartesian free-grid."""
    anchors: set[tuple[int, int]] = set()
    for x, y in boundary:
        anchors.update(
            {
                (x, y),
                (x - width_mm, y),
                (x, y - depth_mm),
                (x - width_mm, y - depth_mm),
            }
        )
    for rectangle in placed.values():
        anchors.update(_edge_anchors(rectangle, width_mm, depth_mm))
    for polygon in obstacles:
        for x, y in polygon:
            anchors.update(
                {
                    (x - width_mm - 1, y),
                    (x + 1, y),
                    (x, y - depth_mm - 1),
                    (x, y + 1),
                    (x - width_mm - 1, y - depth_mm - 1),
                    (x + 1, y + 1),
                }
            )
    return tuple(sorted(anchors))


def _must_neighbors(
    code: str, placed: Mapping[str, PlacedRectangleV1], graph: AdjacencyGraphV1
) -> tuple[PlacedRectangleV1, ...]:
    neighbors = []
    for first, second in graph.must_adjacencies:
        other: str | None = None
        if first == code:
            other = second
        elif second == code:
            other = first
        if other is not None and other in placed:
            neighbors.append(placed[other])
    return tuple(sorted(neighbors, key=lambda rectangle: rectangle.zone_code))


def _should_local_count(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    graph: AdjacencyGraphV1,
) -> int:
    count = 0
    for first, second in graph.should_adjacencies:
        if (
            (first == code and second in placed) or (second == code and first in placed)
        ) and rectangles_share_positive_edge(rectangle, placed[second if first == code else first]):
            count += 1
    return count


def _rectangle_is_usable(
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    boundary_bounds: tuple[int, int, int, int],
    obstacles: Sequence[PolygonMM],
) -> bool:
    left, bottom, right, top = _bounds(rectangle)
    min_x, min_y, max_x, max_y = boundary_bounds
    if left < min_x or bottom < min_y or right > max_x or top > max_y:
        return False
    boundary_rectangle = _axis_aligned_rectangle_polygon_bounds(boundary)
    if boundary_rectangle is None and not rectangle_inside_polygon(rectangle, boundary):
        return False
    for obstacle in obstacles:
        obstacle_rectangle = _axis_aligned_rectangle_polygon_bounds(obstacle)
        if obstacle_rectangle is None:
            if rectangle_intersects_closed_obstacle(rectangle, obstacle):
                return False
            continue
        obstacle_left, obstacle_bottom, obstacle_right, obstacle_top = obstacle_rectangle
        if not (
            right < obstacle_left
            or left > obstacle_right
            or top < obstacle_bottom
            or bottom > obstacle_top
        ):
            return False
    return not any(rectangles_overlap(rectangle, other) for other in placed.values())


def _axis_aligned_rectangle_polygon_bounds(
    polygon: PolygonMM,
) -> tuple[int, int, int, int] | None:
    """Return exact bounds only when the polygon is precisely an axis rectangle."""
    if len(polygon) != 4:
        return None
    left = min(point[0] for point in polygon)
    bottom = min(point[1] for point in polygon)
    right = max(point[0] for point in polygon)
    top = max(point[1] for point in polygon)
    if right <= left or top <= bottom:
        return None
    expected = {
        (left, bottom),
        (left, top),
        (right, bottom),
        (right, top),
    }
    return (left, bottom, right, top) if set(polygon) == expected else None


def _polygon_is_orthogonal(polygon: PolygonMM) -> bool:
    return all(
        first[0] == second[0] or first[1] == second[1]
        for first, second in zip(polygon, (*polygon[1:], polygon[0]), strict=True)
    )


def _segment_for_vertical_edge(x: int, low: int, high: int) -> SegmentMM:
    return ((x, low), (x, high))


def _segment_for_horizontal_edge(y: int, low: int, high: int) -> SegmentMM:
    return ((low, y), (high, y))


def _shared_rectangle_interface(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> SegmentMM | None:
    if first[2] == second[0] or second[2] == first[0]:
        x = first[2] if first[2] == second[0] else first[0]
        low, high = max(first[1], second[1]), min(first[3], second[3])
        return _segment_for_vertical_edge(x, low, high) if low < high else None
    if first[3] == second[1] or second[3] == first[1]:
        y = first[3] if first[3] == second[1] else first[1]
        low, high = max(first[0], second[0]), min(first[2], second[2])
        return _segment_for_horizontal_edge(y, low, high) if low < high else None
    return None


def _orthogonal_site_buildable_bays(
    context: _PlacementSearchContext,
) -> tuple[BuildableBayV1, ...]:
    """Enumerate exact disjoint orthogonal free-space bays for a site.

    Obstacle-adjacent legal origins include the immediately adjacent 1 mm grid
    coordinate because the authoritative obstacle predicate rejects contact.
    Non-orthogonal authority is reported as unavailable; it is never replaced
    by a bounding-box approximation.
    """
    polygons = (context.boundary, *context.obstacles)
    if any(not _polygon_is_orthogonal(polygon) for polygon in polygons):
        return ()
    min_x, min_y, max_x, max_y = context.boundary_bounds
    x_events = {coordinate for x, _y in context.boundary for coordinate in (x,)}
    y_events = {coordinate for _x, y in context.boundary for coordinate in (y,)}
    for obstacle in context.obstacles:
        for x, y in obstacle:
            x_events.update((x - GRID_MM, x, x + GRID_MM))
            y_events.update((y - GRID_MM, y, y + GRID_MM))
    xs = tuple(sorted(value for value in x_events if min_x <= value <= max_x))
    ys = tuple(sorted(value for value in y_events if min_y <= value <= max_y))
    if len(xs) < 2 or len(ys) < 2:
        return ()

    usable: list[list[bool]] = []
    for y0, y1 in zip(ys, ys[1:], strict=False):
        row: list[bool] = []
        for x0, x1 in zip(xs, xs[1:], strict=False):
            cell = _rectangle_from_mm("__buildable_bay_cell__", x0, y0, x1 - x0, y1 - y0, 0)
            row.append(
                _rectangle_is_usable(
                    cell,
                    {},
                    context.boundary,
                    context.boundary_bounds,
                    context.obstacles,
                )
            )
        usable.append(row)

    # Enumerate inclusion-maximal rectangles over the exact free-cell grid.
    # A disjoint strip partition hides useful module anchor faces whenever a
    # usable bay spans more than one strip.  Maximal rectangles may overlap;
    # that is intentional because bays are placement regions, not an
    # ownership partition.  Each candidate is still checked against the exact
    # boundary/obstacle predicates above, and IDs/order remain deterministic.
    bounds_set: set[tuple[int, int, int, int]] = set()
    row_count = len(usable)
    column_count = len(xs) - 1
    for row_start in range(row_count):
        common_free = [True] * column_count
        for row_end in range(row_start + 1, row_count + 1):
            current_row = usable[row_end - 1]
            common_free = [
                is_free and current_row[column] for column, is_free in enumerate(common_free)
            ]
            column = 0
            while column < column_count:
                if not common_free[column]:
                    column += 1
                    continue
                start_column = column
                while column < column_count and common_free[column]:
                    column += 1
                end_column = column
                can_extend_south = row_start > 0 and all(
                    usable[row_start - 1][index] for index in range(start_column, end_column)
                )
                can_extend_north = row_end < row_count and all(
                    usable[row_end][index] for index in range(start_column, end_column)
                )
                if can_extend_south or can_extend_north:
                    continue
                bounds_set.add((xs[start_column], ys[row_start], xs[end_column], ys[row_end]))

    maximal_bounds = tuple(
        sorted(
            bounds_set,
            key=lambda bounds: (
                -((bounds[2] - bounds[0]) * (bounds[3] - bounds[1])),
                bounds,
            ),
        )
    )
    # Preserve a deterministic non-overlapping connectivity partition as
    # interface evidence alongside the overlapping maximal placement regions.
    # The former describes shared bay interfaces; the latter supplies the
    # largest useful module-anchor rectangles.
    partition_bounds: set[tuple[int, int, int, int]] = set()
    active_runs: dict[tuple[int, int], int] = {}
    for row_index, row in enumerate(usable):
        current_runs: set[tuple[int, int]] = set()
        column = 0
        while column < len(row):
            if not row[column]:
                column += 1
                continue
            start_column = column
            while column < len(row) and row[column]:
                column += 1
            current_runs.add((start_column, column))
        for run, start_row in tuple(active_runs.items()):
            if run not in current_runs:
                partition_bounds.add((xs[run[0]], ys[start_row], xs[run[1]], ys[row_index]))
                del active_runs[run]
        for run in current_runs:
            active_runs.setdefault(run, row_index)
    for run, start_row in active_runs.items():
        partition_bounds.add((xs[run[0]], ys[start_row], xs[run[1]], ys[row_count]))
    ordered_regions = tuple(
        ("MAXIMAL_PLACEMENT_REGION", bounds) for bounds in maximal_bounds
    ) + tuple(("CONNECTIVITY_PARTITION_REGION", bounds) for bounds in sorted(partition_bounds))
    boundary_edges: list[tuple[str, SegmentMM]] = []
    for first, second in zip(
        context.boundary, (*context.boundary[1:], context.boundary[0]), strict=True
    ):
        if first[0] == second[0]:
            side = "WEST" if first[0] == min_x else "EAST" if first[0] == max_x else ""
            if side:
                boundary_edges.append(
                    (
                        side,
                        _segment_for_vertical_edge(
                            first[0], min(first[1], second[1]), max(first[1], second[1])
                        ),
                    )
                )
        elif first[1] == second[1]:
            side = "SOUTH" if first[1] == min_y else "NORTH" if first[1] == max_y else ""
            if side:
                boundary_edges.append(
                    (
                        side,
                        _segment_for_horizontal_edge(
                            first[1], min(first[0], second[0]), max(first[0], second[0])
                        ),
                    )
                )

    entrance = context.main_entrance
    truck_entrance = _truck_segment(context.site_body)
    initial: list[BuildableBayV1] = []
    for index, (region_role, bounds) in enumerate(ordered_regions, start=1):
        left, bottom, right, top = bounds
        edges = (
            _segment_for_vertical_edge(left, bottom, top),
            _segment_for_vertical_edge(right, bottom, top),
            _segment_for_horizontal_edge(bottom, left, right),
            _segment_for_horizontal_edge(top, left, right),
        )
        contacts = tuple(
            side
            for side, boundary_edge in boundary_edges
            if any(segments_share_positive_length(*edge, *boundary_edge) for edge in edges)
        )
        initial.append(
            BuildableBayV1(
                bay_id=f"BAY-{index:04d}",
                bounds_mm=bounds,
                area_mm2=(right - left) * (top - bottom),
                boundary_contact_sides=tuple(sorted(set(contacts))),
                entrance_contact=any(
                    segments_share_positive_length(*edge, *entrance) for edge in edges
                ),
                truck_entrance_contact=any(
                    segments_share_positive_length(*edge, *truck_entrance) for edge in edges
                ),
                bay_role=region_role,
            )
        )

    adjacent: dict[str, list[str]] = {bay.bay_id: [] for bay in initial}
    interfaces: dict[str, list[SegmentMM]] = {bay.bay_id: [] for bay in initial}
    for index, first_bay in enumerate(initial):
        for second_bay in initial[index + 1 :]:
            shared = _shared_rectangle_interface(first_bay.bounds_mm, second_bay.bounds_mm)
            if shared is None:
                continue
            adjacent[first_bay.bay_id].append(second_bay.bay_id)
            adjacent[second_bay.bay_id].append(first_bay.bay_id)
            interfaces[first_bay.bay_id].append(shared)
            interfaces[second_bay.bay_id].append(shared)
    return tuple(
        replace(
            bay,
            adjacent_bay_ids=tuple(sorted(adjacent[bay.bay_id])),
            shared_interface_segments=tuple(sorted(set(interfaces[bay.bay_id]))),
        )
        for bay in initial
    )


def _module_signature(
    placements: Mapping[str, PlacedRectangleV1],
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    return tuple(
        (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
        for code, rectangle in sorted(placements.items())
    )


def _module_construction_class_signature(
    module: Mapping[str, PlacedRectangleV1],
    *,
    interface_zone: str,
    chain: Sequence[str] = (),
) -> tuple[object, ...]:
    """Classify a rigid module by geometry facts used for finite source pairing.

    The class deliberately omits the module's absolute local origin.  It keeps
    orientation, packing direction, frame proportions, exposed interface side,
    and (for the finished bank) the actual MUST-chain side sequence.  This
    groups equivalent construction classes before forming source pairs, rather
    than taking the first two geometry rows or expanding every raw × finished
    rectangle combination.
    """
    left, bottom, right, top = _local_bbox_bounds(module)
    span_x, span_y = right - left, top - bottom
    if span_x > span_y:
        frame_class = "WIDE" if span_x >= 2 * span_y else "LANDSCAPE"
        packing_axis = "ROW"
    elif span_y > span_x:
        frame_class = "TALL" if span_y >= 2 * span_x else "PORTRAIT"
        packing_axis = "COLUMN"
    else:
        frame_class = "SQUARE"
        packing_axis = "BALANCED"
    interface = module[interface_zone]
    interface_bounds = _bounds(interface)
    exposed_sides = tuple(
        side
        for side, touches in (
            ("WEST", interface_bounds[0] == left),
            ("EAST", interface_bounds[2] == right),
            ("SOUTH", interface_bounds[1] == bottom),
            ("NORTH", interface_bounds[3] == top),
        )
        if touches
    )
    chain_sides = tuple(
        _adjacent_side(module[first], module[second]) or "NOT_SHARED"
        for first, second in zip(chain, chain[1:], strict=False)
    )
    shipping = module.get("shipping_channel")
    shipping_long_axis = None
    if shipping is not None:
        shipping_bounds = _bounds(shipping)
        shipping_long_axis = (
            "X"
            if shipping_bounds[2] - shipping_bounds[0] >= shipping_bounds[3] - shipping_bounds[1]
            else "Y"
        )
    return (
        tuple(sorted({rectangle.rotation_deg for rectangle in module.values()})),
        packing_axis,
        frame_class,
        exposed_sides,
        chain_sides,
        shipping_long_axis,
    )


def _rigid_module_variants(
    placements: Mapping[str, PlacedRectangleV1],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Return deterministic rigid transforms while freezing module internals."""
    if not placements:
        return ()
    left, bottom, right, top = _local_bbox_bounds(placements)
    width, depth = right - left, top - bottom
    variants: dict[tuple[tuple[str, tuple[int, ...]], ...], dict[str, PlacedRectangleV1]] = {}
    transform_order = (
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (True, True, False),
        (False, False, True),
        (True, False, True),
        (False, True, True),
        (True, True, True),
    )
    for mirror_x, mirror_y, rotate_90 in transform_order:
        transformed: dict[str, PlacedRectangleV1] = {}
        for code, rectangle in sorted(placements.items()):
            zone_left, zone_bottom, zone_right, zone_top = rectangle.bounds_mm
            x0, y0 = zone_left - left, zone_bottom - bottom
            x_span, y_span = zone_right - zone_left, zone_top - zone_bottom
            if mirror_x:
                x0 = width - x0 - x_span
            if mirror_y:
                y0 = depth - y0 - y_span
            if rotate_90:
                x0, y0 = depth - y0 - y_span, x0
            transformed[code] = _rectangle_from_mm(
                code,
                x0,
                y0,
                _mm(rectangle.width_m, field="module.width_m"),
                _mm(rectangle.depth_m, field="module.depth_m"),
                (90 - rectangle.rotation_deg) % 180 if rotate_90 else rectangle.rotation_deg,
            )
        variants.setdefault(_module_signature(transformed), transformed)
    return tuple(variants.values())


def _site_assembly_module_variants(
    placements: Mapping[str, PlacedRectangleV1],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Return every deterministic rigid orientation permitted for a module."""
    return _rigid_module_variants(placements)


def _balanced_site_module_pair_variants(
    raw_module: Mapping[str, PlacedRectangleV1],
    finished_module: Mapping[str, PlacedRectangleV1],
) -> tuple[tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]], ...]:
    """Cover each module's rigid variants without a raw×finished Cartesian product."""
    raw_variants = _site_assembly_module_variants(raw_module)
    finished_variants = _site_assembly_module_variants(finished_module)
    if not raw_variants or not finished_variants:
        return ()
    return tuple(
        (
            raw_variants[index % len(raw_variants)],
            finished_variants[index % len(finished_variants)],
        )
        for index in range(max(len(raw_variants), len(finished_variants)))
    )


def _translate_module(
    module: Mapping[str, PlacedRectangleV1], dx_mm: int, dy_mm: int
) -> dict[str, PlacedRectangleV1]:
    return {
        code: _rectangle_from_mm(
            code,
            rectangle.bounds_mm[0] + dx_mm,
            rectangle.bounds_mm[1] + dy_mm,
            _mm(rectangle.width_m, field="module.width_m"),
            _mm(rectangle.depth_m, field="module.depth_m"),
            rectangle.rotation_deg,
        )
        for code, rectangle in sorted(module.items())
    }


def _dock_backsolved_finished_module(
    module: Mapping[str, PlacedRectangleV1], anchor: ShippingDockAnchorV1
) -> dict[str, PlacedRectangleV1] | None:
    """Rigidly translate a frozen finished module onto an exact dock anchor."""
    shipping = module.get("shipping_channel")
    if shipping is None:
        return None
    source_bounds = shipping.bounds_mm
    target_bounds = anchor.shipping_rectangle.bounds_mm
    source_span = (source_bounds[2] - source_bounds[0], source_bounds[3] - source_bounds[1])
    target_span = (target_bounds[2] - target_bounds[0], target_bounds[3] - target_bounds[1])
    if shipping.rotation_deg != anchor.shipping_rotation_deg or source_span != target_span:
        return None
    translated = _translate_module(
        module,
        target_bounds[0] - source_bounds[0],
        target_bounds[1] - source_bounds[1],
    )
    placed_shipping = translated["shipping_channel"]
    if (
        placed_shipping.bounds_mm != target_bounds
        or placed_shipping.rotation_deg != anchor.shipping_rotation_deg
    ):
        return None
    return translated


def _dock_backsolved_finished_chains(
    context: _PlacementSearchContext,
    anchor: ShippingDockAnchorV1,
    sorting_root: PlacedRectangleV1,
    fixed_zones: Mapping[str, PlacedRectangleV1],
    layout_family: str,
    process_axis: str,
    process_direction: str,
    *,
    reserved_corridor: PlacedRectangleV1 | None = None,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Construct the frozen MUST chain backward from an exact shipping anchor.

    Shipping, sorting, and any already-reserved external-interface geometry
    are fixed inputs.  The finite construction places finished goods against
    shipping, coating against finished goods, and secondary precooling against
    coating; only chains whose secondary room shares an authorized positive
    edge with sorting are returned.  Coordinates come solely from
    authoritative dimension variants and exact edge/alignment events.
    """
    shipping = anchor.shipping_rectangle
    fixed = {
        **fixed_zones,
        "sorting_packaging_room": sorting_root,
        "shipping_channel": shipping,
    }
    permitted_secondary_sides = {
        finished_side
        for _raw_side, finished_side in _family_core_face_pairs(
            layout_family, process_axis, process_direction
        )
    }
    sides = ("WEST", "EAST", "SOUTH", "NORTH")
    alignments = ("LOW", "CENTER", "HIGH")
    finished_shapes = _local_dimension_shapes(context, "finished_goods_room")
    coating_shapes = _local_dimension_shapes(context, "coating_room")
    secondary_shapes = _local_dimension_shapes(context, "secondary_precooling_room")
    if not finished_shapes or not coating_shapes or not secondary_shapes:
        return ()

    chains: dict[tuple[tuple[str, tuple[int, ...]], ...], dict[str, PlacedRectangleV1]] = {}
    for finished_shape in finished_shapes:
        for finished_side in sides:
            for finished_alignment in alignments:
                finished_x, finished_y = _local_adjacent_origin(
                    shipping,
                    finished_shape[3],
                    finished_shape[4],
                    finished_side,
                    finished_alignment,
                )
                finished = _local_rectangle_at(
                    "finished_goods_room", finished_shape, finished_x, finished_y
                )
                if not rectangles_share_positive_edge(finished, shipping):
                    continue
                if not _site_module_is_usable(context, {"finished_goods_room": finished}, fixed):
                    continue
                finished_fixed = {**fixed, "finished_goods_room": finished}

                for coating_shape in coating_shapes:
                    for coating_side in sides:
                        for coating_alignment in alignments:
                            coating_x, coating_y = _local_adjacent_origin(
                                finished,
                                coating_shape[3],
                                coating_shape[4],
                                coating_side,
                                coating_alignment,
                            )
                            coating = _local_rectangle_at(
                                "coating_room", coating_shape, coating_x, coating_y
                            )
                            if not rectangles_share_positive_edge(coating, finished):
                                continue
                            if not _site_module_is_usable(
                                context, {"coating_room": coating}, finished_fixed
                            ):
                                continue

                            for secondary_shape in secondary_shapes:
                                for secondary_side in sides:
                                    for secondary_alignment in alignments:
                                        secondary_x, secondary_y = _local_adjacent_origin(
                                            coating,
                                            secondary_shape[3],
                                            secondary_shape[4],
                                            secondary_side,
                                            secondary_alignment,
                                        )
                                        secondary = _local_rectangle_at(
                                            "secondary_precooling_room",
                                            secondary_shape,
                                            secondary_x,
                                            secondary_y,
                                        )
                                        if not rectangles_share_positive_edge(secondary, coating):
                                            continue
                                        if (
                                            _adjacent_side(sorting_root, secondary)
                                            not in permitted_secondary_sides
                                        ):
                                            continue
                                        chain = {
                                            "secondary_precooling_room": secondary,
                                            "coating_room": coating,
                                            "finished_goods_room": finished,
                                        }
                                        if not _site_module_is_usable(context, chain, fixed):
                                            continue
                                        if reserved_corridor is not None and any(
                                            rectangles_overlap(reserved_corridor, rectangle)
                                            for rectangle in chain.values()
                                        ):
                                            continue
                                        signature = _module_signature(chain)
                                        chains.setdefault(signature, chain)
    return tuple(
        chains[key]
        for key in sorted(
            chains,
            key=lambda signature: (
                _local_compactness_key(chains[signature], context, process_axis),
                signature,
            ),
        )
    )


def _module_attached_to_zone(
    module: Mapping[str, PlacedRectangleV1],
    interface_zone_code: str,
    target: PlacedRectangleV1,
    side: str,
    alignment: str,
) -> dict[str, PlacedRectangleV1] | None:
    interface = module.get(interface_zone_code)
    if interface is None:
        return None
    interface_left, interface_bottom, interface_right, interface_top = interface.bounds_mm
    x_span, y_span = interface_right - interface_left, interface_top - interface_bottom
    target_x, target_y = _local_adjacent_origin(target, x_span, y_span, side, alignment)
    translated = _translate_module(module, target_x - interface_left, target_y - interface_bottom)
    return (
        translated
        if rectangles_share_positive_edge(target, translated[interface_zone_code])
        else None
    )


def _finished_module_site_dock_order(
    module: Mapping[str, PlacedRectangleV1],
    sorting_root: PlacedRectangleV1,
    finished_side: str,
    alignments: Sequence[str],
    dock_rectangles: Sequence[PlacedRectangleV1],
) -> tuple[int, int, int, int, tuple[int, int, int, int]]:
    """Order finished modules by their site-frame shipping/dock fit.

    Module coordinates are local until attached to the sorting root. Compare
    dock events only after that rigid attachment; comparing local module
    origins directly with site coordinates creates a meaningless distance.
    This is construction ordering only. Truck and P2D remain authoritative.
    """
    shipping = module["shipping_channel"]
    fallback = (1, 2**31, shipping.rotation_deg, len(alignments), shipping.bounds_mm)
    scores: list[tuple[int, int, int, int, tuple[int, int, int, int]]] = []
    for alignment_index, alignment in enumerate(alignments):
        attached = _module_attached_to_zone(
            module,
            "secondary_precooling_room",
            sorting_root,
            finished_side,
            alignment,
        )
        if attached is None:
            continue
        site_shipping = attached["shipping_channel"]
        site_bounds = _bounds(site_shipping)
        for dock in dock_rectangles:
            dock_bounds = _bounds(dock)
            if dock.rotation_deg != site_shipping.rotation_deg or (
                dock_bounds[2] - dock_bounds[0],
                dock_bounds[3] - dock_bounds[1],
            ) != (site_bounds[2] - site_bounds[0], site_bounds[3] - site_bounds[1]):
                continue
            distance = abs(site_bounds[0] - dock_bounds[0]) + abs(site_bounds[1] - dock_bounds[1])
            scores.append(
                (
                    int(site_bounds != dock_bounds),
                    distance,
                    site_shipping.rotation_deg,
                    alignment_index,
                    site_shipping.bounds_mm,
                )
            )
    return min(scores) if scores else fallback


def _module_origins_from_bay_edges(
    module: Mapping[str, PlacedRectangleV1], bays: Sequence[BuildableBayV1]
) -> tuple[tuple[int, int], ...]:
    """Generate finite module origins by aligning its frame to exact bay edges."""
    if not module:
        return ()
    frame = _local_bbox_bounds(module)
    origins: set[tuple[int, int]] = set()
    for bay in bays:
        left, bottom, right, top = bay.bounds_mm
        bay_x_edges = (left, right)
        bay_y_edges = (bottom, top)
        frame_x_edges = (frame[0], frame[2])
        frame_y_edges = (frame[1], frame[3])
        for target_x in bay_x_edges:
            for source_x in frame_x_edges:
                for target_y in bay_y_edges:
                    for source_y in frame_y_edges:
                        origins.add((target_x - source_x, target_y - source_y))
    return tuple(
        sorted(origins, key=lambda point: (abs(point[1]) + abs(point[0]), point[1], point[0]))
    )


def _site_translations_from_bay_edges(
    placements: Mapping[str, PlacedRectangleV1],
    bays: Sequence[BuildableBayV1],
    *,
    site_body: Mapping[str, Any] | None = None,
    truck_dock_points: Sequence[tuple[int, int]] = (),
    shipping_dock_placements: Sequence[PlacedRectangleV1] = (),
) -> tuple[tuple[int, int], ...]:
    """Align frozen module interfaces, not the whole composition, to bay events.

    Functional modules may span multiple disjoint bays. Aligning only the
    complete composition's bounding box to one bay wrongly assumes that the
    whole program fits inside a single lobe. Interface-zone origins are finite
    site-derived anchors. Existing truck-template dock events are also usable
    as translation anchors for the shipping face, but remain ordering/placement
    events only; every final rectangle and truck maneuver is still checked by
    its existing authoritative predicate.
    """
    if not placements:
        return ()
    translations: set[tuple[int, int]] = set()
    truck_aligned: set[tuple[int, int]] = set()
    template_aligned: list[tuple[int, int]] = []
    template_aligned_seen: set[tuple[int, int]] = set()
    shipping = placements.get("shipping_channel")
    if shipping is not None and site_body is not None:
        source_bounds = _bounds(shipping)
        source_shape = (
            source_bounds[2] - source_bounds[0],
            source_bounds[3] - source_bounds[1],
            shipping.rotation_deg,
        )
        for dock_placement in shipping_dock_placements:
            target_bounds = _bounds(dock_placement)
            target_shape = (
                target_bounds[2] - target_bounds[0],
                target_bounds[3] - target_bounds[1],
                dock_placement.rotation_deg,
            )
            if source_shape != target_shape:
                continue
            offset = (
                target_bounds[0] - source_bounds[0],
                target_bounds[1] - source_bounds[1],
            )
            if offset not in template_aligned_seen:
                template_aligned_seen.add(offset)
                template_aligned.append(offset)
        translations.update(template_aligned)
        entrance = _truck_segment(site_body)
        loading_face = _loading_face(shipping, site_body)[1]
        face_points = (
            loading_face[0],
            loading_face[1],
            (
                (loading_face[0][0] + loading_face[1][0]) // 2,
                (loading_face[0][1] + loading_face[1][1]) // 2,
            ),
        )
        entrance_points = (
            entrance[0],
            entrance[1],
            ((entrance[0][0] + entrance[1][0]) // 2, (entrance[0][1] + entrance[1][1]) // 2),
        )
        center_alignment = (
            entrance_points[2][0] - face_points[2][0],
            entrance_points[2][1] - face_points[2][1],
        )
        truck_aligned.add(center_alignment)
        truck_aligned.update(
            (target[0] - source[0], target[1] - source[1])
            for source in face_points[:2]
            for target in entrance_points[:2]
        )
        truck_aligned.update(
            (dock_x - source[0], dock_y - source[1])
            for source in face_points
            for dock_x, dock_y in truck_dock_points
        )
        translations.update(truck_aligned)
    for code in (
        "sorting_packaging_room",
        "primary_precooling_room",
        "secondary_precooling_room",
        "shipping_channel",
    ):
        anchor = placements.get(code)
        if anchor is None:
            continue
        anchor_left, anchor_bottom, anchor_right, anchor_top = anchor.bounds_mm
        width, depth = anchor_right - anchor_left, anchor_top - anchor_bottom
        for bay in bays:
            left, bottom, right, top = bay.bounds_mm
            target_xs = (left, right - width, (left + right - width) // 2)
            target_ys = (bottom, top - depth, (bottom + top - depth) // 2)
            translations.update(
                (target_x - anchor_left, target_y - anchor_bottom)
                for target_x in target_xs
                for target_y in target_ys
            )

    def order_key(point: tuple[int, int]) -> tuple[int, int, int]:
        return (abs(point[0]) + abs(point[1]), point[1], point[0])

    preferred = sorted(truck_aligned, key=order_key)
    remainder = sorted(translations - truck_aligned, key=order_key)
    return tuple(dict.fromkeys((*template_aligned, *preferred, *remainder)))


def _site_module_is_usable(
    context: _PlacementSearchContext,
    module: Mapping[str, PlacedRectangleV1],
    fixed: Mapping[str, PlacedRectangleV1],
) -> bool:
    placed = dict(fixed)
    for code, rectangle in sorted(module.items()):
        if code in placed or not _rectangle_is_usable(
            rectangle,
            placed,
            context.boundary,
            context.boundary_bounds,
            context.obstacles,
        ):
            return False
        placed[code] = rectangle
    return True


def _sorting_roots_in_bays(
    context: _PlacementSearchContext, bays: Sequence[BuildableBayV1]
) -> tuple[PlacedRectangleV1, ...]:
    roots: dict[tuple[int, ...], PlacedRectangleV1] = {}
    shapes = _local_dimension_shapes(context, "sorting_packaging_room")
    ordered_bays = sorted(bays, key=lambda bay: (-bay.area_mm2, bay.bounds_mm, bay.bay_id))
    for bay in ordered_bays:
        left, bottom, right, top = bay.bounds_mm
        for shape in shapes:
            x_span, y_span = shape[3], shape[4]
            x_origins = tuple(sorted({left, right - x_span, (left + right - x_span) // 2}))
            y_origins = tuple(sorted({bottom, top - y_span, (bottom + top - y_span) // 2}))
            origins = tuple(product(x_origins, y_origins))
            for x, y in origins:
                root = _local_rectangle_at("sorting_packaging_room", shape, x, y)
                if _rectangle_is_usable(
                    root, {}, context.boundary, context.boundary_bounds, context.obstacles
                ):
                    roots.setdefault(root.bounds_mm + (root.rotation_deg,), root)
    by_rotation = {
        rotation: [roots[key] for key in sorted(roots) if key[-1] == rotation]
        for rotation in (0, 90)
    }
    # Keep both authorized orientations in the front of the deterministic
    # candidate order; a later bounded candidate quota must not starve 90°.
    ordered: list[PlacedRectangleV1] = []
    for index in range(max((len(rows) for rows in by_rotation.values()), default=0)):
        for rotation in (0, 90):
            if index < len(by_rotation[rotation]):
                ordered.append(by_rotation[rotation][index])
    return tuple(ordered)


def _family_core_face_pairs(
    layout_family: str, process_axis: str, process_direction: str
) -> tuple[tuple[str, str], ...]:
    if layout_family == LINEAR_3_BAND:
        preferred = {
            ("X", "POSITIVE"): ("WEST", "EAST"),
            ("X", "NEGATIVE"): ("EAST", "WEST"),
            ("Y", "POSITIVE"): ("SOUTH", "NORTH"),
            ("Y", "NEGATIVE"): ("NORTH", "SOUTH"),
        }[(process_axis, process_direction)]
        opposite_pairs = (
            ("WEST", "EAST"),
            ("EAST", "WEST"),
            ("SOUTH", "NORTH"),
            ("NORTH", "SOUTH"),
        )
        one_bend_pairs = tuple(
            (raw_side, finished_side)
            for raw_side in ("WEST", "EAST", "SOUTH", "NORTH")
            for finished_side in ("WEST", "EAST", "SOUTH", "NORTH")
            if raw_side != finished_side
            and {raw_side, finished_side} not in ({"WEST", "EAST"}, {"SOUTH", "NORTH"})
        )
        cofacial_bank_pairs = tuple((side, side) for side in ("NORTH", "SOUTH", "EAST", "WEST"))
        return tuple(
            dict.fromkeys((preferred, *opposite_pairs, *one_bend_pairs, *cofacial_bank_pairs))
        )
    if layout_family == CENTRAL_PROCESS_WITH_SIDE_BANKS:
        side_order = ("WEST", "EAST", "SOUTH", "NORTH")
        orthogonal = tuple(
            (raw_side, finished_side)
            for raw_side in side_order
            for finished_side in side_order
            if raw_side != finished_side
            and {raw_side, finished_side} not in ({"WEST", "EAST"}, {"SOUTH", "NORTH"})
        )
        return orthogonal
    if layout_family == LONGITUDINAL_PROCESS_SPINE:
        terminal_pairs = (
            (("SOUTH", "NORTH"), ("NORTH", "SOUTH"))
            if process_axis == "X"
            else (
                ("WEST", "EAST"),
                ("EAST", "WEST"),
            )
        )
        spine_side_pairs = tuple((side, side) for side in ("NORTH", "SOUTH", "EAST", "WEST"))
        return (*terminal_pairs, *spine_side_pairs)
    return ()


def _main_module_source_pairs(
    context: _PlacementSearchContext,
    main_compositions: Sequence[LocalBuildingCompositionV1],
    *,
    module_variants: tuple[
        Sequence[dict[str, PlacedRectangleV1]],
        Sequence[dict[str, PlacedRectangleV1]],
    ]
    | None = None,
    stats: _PlacementSearchStats | None = None,
) -> tuple[tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]], ...]:
    """Pair geometry-class representatives without positional ZIP truncation."""
    source_pairs: dict[
        tuple[
            tuple[tuple[str, tuple[int, ...]], ...],
            tuple[tuple[str, tuple[int, ...]], ...],
        ],
        tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]],
    ] = {}

    def add_source_pair(
        raw_source: Mapping[str, PlacedRectangleV1],
        finished_source: Mapping[str, PlacedRectangleV1],
    ) -> None:
        raw_normalized = _normalize_local_placements(raw_source)
        finished_normalized = _normalize_local_placements(finished_source)
        signature = (_module_signature(raw_normalized), _module_signature(finished_normalized))
        source_pairs.setdefault(signature, (raw_normalized, finished_normalized))

    if module_variants is None:
        raw_modules = tuple(
            row[0]
            for row in _local_bank_compositions(
                context,
                ("raw_fruit_buffer", "primary_precooling_room"),
                result_limit=24,
            )
        )
        finished_modules = _local_must_chain_module_compositions(
            context,
            (
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
            ),
            result_limit=24,
        )
    else:
        raw_modules, finished_modules = map(tuple, module_variants)

    raw_representatives: dict[tuple[object, ...], dict[str, PlacedRectangleV1]] = {}
    for module in raw_modules:
        signature = _module_construction_class_signature(
            module,
            interface_zone="primary_precooling_room",
            chain=("raw_fruit_buffer", "primary_precooling_room"),
        )
        raw_representatives.setdefault(signature, module)
    finished_chain = (
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    finished_representatives: dict[tuple[object, ...], dict[str, PlacedRectangleV1]] = {}
    for module in finished_modules:
        signature = _module_construction_class_signature(
            module,
            interface_zone="secondary_precooling_room",
            chain=finished_chain,
        )
        finished_representatives.setdefault(signature, module)

    raw_classes = tuple(sorted(raw_representatives))
    finished_classes = tuple(sorted(finished_representatives))
    class_pair_limit = 32
    class_pair_rows: list[tuple[tuple[object, ...], tuple[object, ...]]] = []
    if raw_classes and finished_classes:
        # The cyclic diagonal visits every distinct RAW and FINISHED class in
        # max(n, m) pairs, rather than materializing their Cartesian product.
        coverage_width = max(len(raw_classes), len(finished_classes))
        for index in range(coverage_width):
            class_pair_rows.append(
                (
                    raw_classes[index % len(raw_classes)],
                    finished_classes[index % len(finished_classes)],
                )
            )
        # Add a bounded offset cover so the construction is not a label-only
        # one-to-one pairing while staying well below n_raw * n_finished.
        for offset in range(1, min(len(finished_classes), class_pair_limit)):
            for index in range(coverage_width):
                pair = (
                    raw_classes[index % len(raw_classes)],
                    finished_classes[(index + offset) % len(finished_classes)],
                )
                if pair not in class_pair_rows:
                    class_pair_rows.append(pair)
                if len(class_pair_rows) >= class_pair_limit:
                    break
            if len(class_pair_rows) >= class_pair_limit:
                break
    class_pairs = tuple(class_pair_rows[:class_pair_limit])
    for raw_class, finished_class in class_pairs:
        add_source_pair(raw_representatives[raw_class], finished_representatives[finished_class])

    # Local family compositions are a small compatibility source, not the
    # primary way module geometry is produced.
    for composition in main_compositions:
        source = composition.placements()
        add_source_pair(
            {code: source[code] for code in ("raw_fruit_buffer", "primary_precooling_room")},
            {
                code: source[code]
                for code in (
                    "secondary_precooling_room",
                    "coating_room",
                    "finished_goods_room",
                    "shipping_channel",
                )
            },
        )
        if len(source_pairs) >= class_pair_limit:
            break
    if stats is not None:
        if stats.site_module_variant_counts is None:
            stats.site_module_variant_counts = {}
        stats.site_module_variant_counts["raw_module_distinct_signature_count"] = len(
            raw_representatives
        )
        stats.site_module_variant_counts["finished_module_distinct_signature_count"] = len(
            finished_representatives
        )
        stats.site_module_variant_counts["raw_module_construction_rep_count"] = len(
            raw_representatives
        )
        stats.site_module_variant_counts["finished_module_construction_rep_count"] = len(
            finished_representatives
        )
        stats.site_module_variant_counts["source_pair_distinct_input_geometry_count"] = len(
            source_pairs
        )
        stats.site_module_variant_counts["source_pair_class_product_count"] = len(
            raw_representatives
        ) * len(finished_representatives)
        stats.site_module_variant_counts["source_pair_class_product_capped"] = (
            len(raw_representatives) * len(finished_representatives) > class_pair_limit
        )
    return tuple(source_pairs.values())


@dataclass(frozen=True)
class PackagingAnchorV1:
    """An exact site-valid placement of the authoritative packaging rectangle."""

    anchor_id: str
    bay_id: str
    rectangle: PlacedRectangleV1

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "bay_id": self.bay_id,
            "rectangle": self.rectangle.to_dict(),
        }


@dataclass(frozen=True)
class ShippingDockAnchorV1:
    """A site-frame shipping rectangle bound to an existing truck dock event.

    This is a construction witness only. The maneuver-chain validator remains
    the authority for whether the complete truck route is feasible.
    """

    dock_point_mm: tuple[int, int]
    shipping_rectangle: PlacedRectangleV1
    loading_face_side: str
    loading_face_segment_mm: SegmentMM
    shipping_rotation_deg: int
    source_entry_point_mm: tuple[int, int]
    source_template_identity: str
    source_template_rotation_deg: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "dock_point_mm": list(self.dock_point_mm),
            "shipping_rectangle": self.shipping_rectangle.to_dict(),
            "loading_face_side": self.loading_face_side,
            "loading_face_segment_mm": [
                list(self.loading_face_segment_mm[0]),
                list(self.loading_face_segment_mm[1]),
            ],
            "shipping_rotation_deg": self.shipping_rotation_deg,
            "source_entry_point_mm": list(self.source_entry_point_mm),
            "source_template_identity": self.source_template_identity,
            "source_template_rotation_deg": self.source_template_rotation_deg,
        }


def _enumerate_packaging_site_anchors(
    context: _PlacementSearchContext,
    bays: Sequence[BuildableBayV1],
    fixed_main_process_rectangles: Sequence[PlacedRectangleV1] = (),
) -> tuple[PackagingAnchorV1, ...]:
    authority = context.authorities["packaging_material_storage"]
    enumeration = enumerate_tail_zone_site_anchors_v1(
        zone_code="packaging_material_storage",
        dimension_variants=_dimension_variants(authority, {}, context.boundary),
        dimension_authority_complete=_authority_mode(authority)
        in {"FIXED_RECTANGLE", "DETERMINISTIC_GRID_RECTANGLE"},
        boundary=context.boundary,
        obstacles=context.obstacles,
        fixed_main_process_rectangles=fixed_main_process_rectangles,
    )
    if enumeration.proof_mode != EXACT_ORTHOGONAL_EVENT_ENUMERATION:
        return ()
    maximal_bays = tuple(
        sorted(
            (bay for bay in bays if bay.bay_role == "MAXIMAL_PLACEMENT_REGION"),
            key=lambda bay: (-bay.area_mm2, bay.bounds_mm, bay.bay_id),
        )
    )
    anchors: list[PackagingAnchorV1] = []
    for rectangle in enumeration.legal_anchors:
        left, bottom, right, top = rectangle.bounds_mm
        containing = next(
            (
                bay
                for bay in maximal_bays
                if bay.bounds_mm[0] <= left
                and bay.bounds_mm[1] <= bottom
                and right <= bay.bounds_mm[2]
                and top <= bay.bounds_mm[3]
            ),
            None,
        )
        bay_id = containing.bay_id if containing is not None else "CROSS_BAY"
        anchors.append(
            PackagingAnchorV1(
                anchor_id=(f"PACKAGING-{rectangle.rotation_deg}-{left}-{bottom}-{right}-{top}"),
                bay_id=bay_id,
                rectangle=rectangle,
            )
        )
    return tuple(
        sorted(
            anchors,
            key=lambda row: (row.bay_id, row.rectangle.rotation_deg, row.rectangle.bounds_mm),
        )
    )


def _packaging_anchor_construction_representatives(
    context: _PlacementSearchContext,
    anchors: Sequence[PackagingAnchorV1],
    bays: Sequence[BuildableBayV1],
    *,
    root_options_by_anchor: dict[
        str,
        tuple[tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]], ...],
    ]
    | None = None,
    stats: _PlacementSearchStats | None = None,
) -> tuple[PackagingAnchorV1, ...]:
    """Keep deterministic bay-edge/corner representatives for joint assembly.

    The complete legal event set remains available for evidence and its count;
    construction visits several spatially distinct representatives per bay
    and orientation instead of taking only the first slot witness or forming
    an anchor-by-root Cartesian sweep.
    """
    bay_by_id = {bay.bay_id: bay for bay in bays}
    groups: dict[tuple[str, int], list[PackagingAnchorV1]] = {}
    for anchor in anchors:
        groups.setdefault((anchor.bay_id, anchor.rectangle.rotation_deg), []).append(anchor)

    def spatial_role(
        anchor: PackagingAnchorV1, frame_bounds: tuple[int, int, int, int]
    ) -> tuple[str, int]:
        left, bottom, right, top = frame_bounds
        x0, y0, x1, y1 = anchor.rectangle.bounds_mm
        width, depth = x1 - x0, y1 - y0
        targets = (
            ("CORNER", left, bottom),
            ("CORNER", right - width, bottom),
            ("CORNER", left, top - depth),
            ("CORNER", right - width, top - depth),
            ("EDGE", (left + right - width) // 2, bottom),
            ("EDGE", (left + right - width) // 2, top - depth),
            ("EDGE", left, (bottom + top - depth) // 2),
            ("EDGE", right - width, (bottom + top - depth) // 2),
            ("CENTER", (left + right - width) // 2, (bottom + top - depth) // 2),
        )
        role, target_x, target_y = min(
            targets,
            key=lambda row: (
                abs(x0 - row[1]) + abs(y0 - row[2]),
                ("CORNER", "EDGE", "CENTER").index(row[0]),
                row[1],
                row[2],
            ),
        )
        return role, abs(x0 - target_x) + abs(y0 - target_y)

    selected: dict[str, PackagingAnchorV1] = {}
    cached_root_options = root_options_by_anchor if root_options_by_anchor is not None else {}
    # Score every exact site-valid packaging witness against the finite
    # package-to-sorting edge events. This is only anchor representative
    # selection; it does not run the 7-zone assembly or alter authority.
    for anchor in anchors:
        options = cached_root_options.get(anchor.anchor_id)
        if options is None:
            options = _packaging_driven_sorting_roots(context, anchor, bays=bays, stats=stats)
            cached_root_options[anchor.anchor_id] = options

    for group_key, rows in sorted(groups.items()):
        bay = bay_by_id.get(group_key[0])
        # Preserve both bay-relative and whole-site boundary-relative events.
        # A bay edge can be an obstacle-derived internal boundary; choosing
        # only that representative can miss an equally authoritative placement
        # flush to the effective site boundary (and vice versa).
        frames = (
            ("BAY", bay.bounds_mm if bay is not None else context.boundary_bounds),
            ("SITE", context.boundary_bounds),
        )
        for _frame_name, frame_bounds in frames:
            role_rows: dict[str, list[tuple[PackagingAnchorV1, int]]] = {
                "CORNER": [],
                "EDGE": [],
                "CENTER": [],
            }
            for anchor in rows:
                role, distance = spatial_role(anchor, frame_bounds)
                role_rows[role].append((anchor, distance))
            # Prefer exact package-to-sorting witnesses when a frame-role has
            # them; keep a deterministic no-root witness only if none exists.
            for role in ("CORNER", "EDGE", "CENTER"):
                candidates = role_rows[role]
                if not candidates:
                    continue
                rootable = [row for row in candidates if cached_root_options[row[0].anchor_id]]
                selected_pool = rootable or candidates
                anchor, _distance = min(
                    selected_pool,
                    key=lambda row: (
                        row[1],
                        -len(cached_root_options[row[0].anchor_id]),
                        row[0].rectangle.bounds_mm,
                        row[0].anchor_id,
                    ),
                )
                selected.setdefault(anchor.anchor_id, anchor)

        # Each distinct feasible sorting orientation and package-facing side
        # receives a representative. This prevents spatial-role sampling from
        # erasing the interface direction needed by the process core.
        interface_rows: dict[tuple[int, str], list[PackagingAnchorV1]] = {}
        for anchor in rows:
            for root, package_side, _corridor, _witness in cached_root_options[anchor.anchor_id]:
                interface_rows.setdefault((root.rotation_deg, package_side), []).append(anchor)
        for _interface_class, candidate_anchors in sorted(interface_rows.items()):
            unique_candidates = {anchor.anchor_id: anchor for anchor in candidate_anchors}
            representative = min(
                unique_candidates.values(),
                key=lambda anchor: (
                    -len(cached_root_options[anchor.anchor_id]),
                    anchor.rectangle.bounds_mm,
                    anchor.anchor_id,
                ),
            )
            selected.setdefault(representative.anchor_id, representative)

    by_group: dict[tuple[str, int], dict[str, PackagingAnchorV1]] = {}
    for anchor in selected.values():
        bay = bay_by_id.get(anchor.bay_id)
        role, _distance = spatial_role(
            anchor,
            bay.bounds_mm if bay is not None else context.boundary_bounds,
        )
        by_group.setdefault((anchor.bay_id, anchor.rectangle.rotation_deg), {})[
            f"{role}:{anchor.anchor_id}"
        ] = anchor
    # Interleave bay/orientation groups and geometric/interface roles so a
    # small downstream construction quota cannot consume one lobe or side.
    balanced: list[PackagingAnchorV1] = []
    groups_sorted = sorted(by_group)
    group_rows = {
        group: sorted(
            by_group[group].values(),
            key=lambda anchor: (
                -len(cached_root_options[anchor.anchor_id]),
                anchor.rectangle.bounds_mm,
                anchor.anchor_id,
            ),
        )
        for group in groups_sorted
    }
    # Construction has a bounded downstream node allowance. Interleave bay ×
    # packaging-orientation groups so a small prefix still covers both anchor
    # rotations and each usable lobe before spending a second attempt in one
    # group. The exact complete anchor set remains unchanged.
    for round_index in range(max((len(rows) for rows in group_rows.values()), default=0)):
        for group in groups_sorted:
            rows = group_rows[group]
            if round_index < len(rows):
                balanced.append(rows[round_index])
    return tuple(balanced)


def _orientation_balanced_sorting_roots(
    context: _PlacementSearchContext,
    bays: Sequence[BuildableBayV1],
    *,
    per_orientation_limit: int = 24,
) -> tuple[PlacedRectangleV1, ...]:
    roots = _sorting_roots_in_bays(context, bays)
    by_rotation = {
        rotation: _bounded_site_event_rectangles(
            tuple(row for row in roots if row.rotation_deg == rotation),
            limit=per_orientation_limit,
        )
        for rotation in (0, 90)
    }
    ordered: list[PlacedRectangleV1] = []
    for index in range(max((len(rows) for rows in by_rotation.values()), default=0)):
        for rotation in (0, 90):
            if index < len(by_rotation[rotation]):
                ordered.append(by_rotation[rotation][index])
    return tuple(ordered)


def _packaging_access_widths_mm(
    context: _PlacementSearchContext,
) -> tuple[int, int] | None:
    """Return frozen portal/corridor widths for packaging-to-sorting ordering."""
    requirement = next(
        (
            row
            for row in getattr(context, "access_requirements", ())
            if row.get("from_ref") == "packaging_material_storage"
            and row.get("to_ref") == "sorting_packaging_room"
        ),
        None,
    )
    if requirement is None:
        return None
    profile_identity = requirement.get("profile_identity")
    if not isinstance(profile_identity, str):
        return None
    if (
        profile_identity != "packaging-sorting-straight-access@1.0.0"
        or requirement.get("route_shape_constraint") != "STRAIGHT_ONLY"
    ):
        return None
    portal_width = requirement.get("construction_portal_clear_width_m")
    corridor_width = requirement.get("construction_corridor_clear_width_m")
    if portal_width is None or corridor_width is None:
        return None
    return (
        _mm(
            portal_width,
            field="packaging.portal_clear_width_m",
            positive=True,
        ),
        _mm(
            requirement.get("construction_corridor_clear_width_m"),
            field="packaging.corridor_clear_width_m",
            positive=True,
        ),
    )


def _segment_is_horizontal(segment: SegmentMM) -> bool:
    return segment[0][1] == segment[1][1]


def _packaging_driven_sorting_roots(
    context: _PlacementSearchContext,
    packaging_anchor: PackagingAnchorV1,
    *,
    bays: Sequence[BuildableBayV1] = (),
    stats: _PlacementSearchStats | None = None,
) -> tuple[tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]], ...]:
    """Derive sorting roots from package and exact site-event geometry.

    The returned construction witness records edge alignment and a corridor
    envelope only; final access remains the responsibility of P2D.  A
    positive-gap envelope is retained as construction clearance so later
    modules cannot consume the straight approach corridor being ordered.
    Site, bay, and obstacle events also permit finite corridor-separated roots;
    no arbitrary coordinate sweep is performed.
    """
    package = packaging_anchor.rectangle
    package_edges = tuple(
        (name, segment)
        for name, edge_class, segment in _named_rectangle_edge_classes(package)
        if edge_class == "LONG_EDGE"
    )
    access_widths = _packaging_access_widths_mm(context)
    portal_width_mm, corridor_width_mm = access_widths or (0, 0)
    minimum_direct_overlap = max(portal_width_mm, 1)
    roots: dict[
        tuple[tuple[int, ...], str, int, str],
        tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]],
    ] = {}
    if stats is not None:
        if stats.packaging_anchor_sorting_rotation_attempts_by_group is None:
            stats.packaging_anchor_sorting_rotation_attempts_by_group = {}
        if stats.packaging_anchor_sorting_alignment_proofs_by_group is None:
            stats.packaging_anchor_sorting_alignment_proofs_by_group = {}
        attempts = stats.packaging_anchor_sorting_rotation_attempts_by_group.setdefault(
            packaging_anchor.anchor_id, set()
        )
        proofs = stats.packaging_anchor_sorting_alignment_proofs_by_group.setdefault(
            packaging_anchor.anchor_id, {}
        )
    else:
        attempts = set()
        proofs = {}

    def gap_events(edge_name: str, edge: SegmentMM) -> tuple[tuple[int, str, int], ...]:
        horizontal = _segment_is_horizontal(edge)
        axis = 1 if horizontal else 0
        edge_coordinate = edge[0][axis]
        positive = edge_name in {"TOP", "RIGHT"}
        source_by_gap: dict[int, set[str]] = {0: {"DIRECT"}}
        if corridor_width_mm > 0:
            source_by_gap.setdefault(corridor_width_mm, set()).add("PROFILE_CLEAR_WIDTH")
        bounds = context.boundary_bounds
        for coordinate in (bounds[axis], bounds[axis + 2]):
            gap = coordinate - edge_coordinate if positive else edge_coordinate - coordinate
            if gap >= 0:
                source_by_gap.setdefault(gap, set()).add("SITE_BOUNDARY_EVENT")
        for bay in bays:
            for coordinate in (bay.bounds_mm[axis], bay.bounds_mm[axis + 2]):
                gap = coordinate - edge_coordinate if positive else edge_coordinate - coordinate
                if gap >= 0:
                    source_by_gap.setdefault(gap, set()).add(f"{bay.bay_id}_EDGE_EVENT")
        for obstacle_index, obstacle in enumerate(context.obstacles):
            for coordinate in sorted({point[axis] for point in obstacle}):
                gap = coordinate - edge_coordinate if positive else edge_coordinate - coordinate
                if gap >= 0:
                    source_by_gap.setdefault(gap, set()).add(
                        f"OBSTACLE_{obstacle_index + 1}_EDGE_EVENT"
                    )
        priority = ("DIRECT", "PROFILE_CLEAR_WIDTH")
        return tuple(
            (
                gap,
                next(
                    (candidate for candidate in priority if candidate in sources),
                    min(sources),
                ),
                edge_coordinate + gap if positive else edge_coordinate - gap,
            )
            for gap, sources in sorted(source_by_gap.items())
        )

    for rotation in (0, 90):
        attempts.add(str(rotation))
        shapes = tuple(
            shape
            for shape in _local_dimension_shapes(context, "sorting_packaging_room")
            if shape[2] == rotation
        )
        compatible_edge_pairs: list[tuple[str, SegmentMM, str, SegmentMM]] = []
        for package_edge_name, package_edge in package_edges:
            package_horizontal = _segment_is_horizontal(package_edge)
            for shape in shapes:
                probe = _local_rectangle_at("sorting_packaging_room", shape, 0, 0)
                for sorting_edge_name, edge_class, sorting_edge in _named_rectangle_edge_classes(
                    probe
                ):
                    if edge_class != "SHORT_EDGE":
                        continue
                    if _segment_is_horizontal(sorting_edge) != package_horizontal:
                        continue
                    facing_sides = {
                        ("TOP", "BOTTOM"): "SOUTH",
                        ("BOTTOM", "TOP"): "NORTH",
                        ("RIGHT", "LEFT"): "WEST",
                        ("LEFT", "RIGHT"): "EAST",
                    }
                    package_side = facing_sides.get((package_edge_name, sorting_edge_name))
                    if package_side is None:
                        continue
                    compatible_edge_pairs.append(
                        (package_edge_name, package_edge, sorting_edge_name, sorting_edge)
                    )
        if not compatible_edge_pairs:
            proofs[str(rotation)] = "EDGE_AXES_OR_FACING_SIDES_PROVE_STRAIGHT_ALIGNMENT_IMPOSSIBLE"
            continue
        proofs[str(rotation)] = "PARALLEL_LONG_TO_SHORT_EDGE_ALIGNMENT_ENUMERATED"

        for shape in shapes:
            probe = _local_rectangle_at("sorting_packaging_room", shape, 0, 0)
            for package_edge_name, package_edge, sorting_edge_name, sorting_edge in (
                pair
                for pair in compatible_edge_pairs
                if pair[3]
                in tuple(
                    edge
                    for name, edge_class, edge in _named_rectangle_edge_classes(probe)
                    if edge_class == "SHORT_EDGE" and name == pair[2]
                )
            ):
                package_side = {
                    ("TOP", "BOTTOM"): "SOUTH",
                    ("BOTTOM", "TOP"): "NORTH",
                    ("RIGHT", "LEFT"): "WEST",
                    ("LEFT", "RIGHT"): "EAST",
                }[(package_edge_name, sorting_edge_name)]
                package_low, package_high = sorted(
                    (package_edge[0][0], package_edge[1][0])
                    if _segment_is_horizontal(package_edge)
                    else (package_edge[0][1], package_edge[1][1])
                )
                package_axis = 0 if _segment_is_horizontal(package_edge) else 1
                sorting_low, sorting_high = sorted(
                    (sorting_edge[0][0], sorting_edge[1][0])
                    if _segment_is_horizontal(sorting_edge)
                    else (sorting_edge[0][1], sorting_edge[1][1])
                )
                alignment_rows: dict[int, tuple[str, str, int, str]] = {
                    package_low - sorting_low: (
                        "LOW",
                        "EDGE_START",
                        package_low - sorting_low,
                        "PACKAGE_EDGE_EVENT",
                    ),
                    (package_low + package_high - sorting_low - sorting_high) // 2: (
                        "CENTER",
                        "CENTER",
                        (package_low + package_high - sorting_low - sorting_high) // 2,
                        "PACKAGE_EDGE_EVENT",
                    ),
                    package_high - sorting_high: (
                        "HIGH",
                        "EDGE_END",
                        package_high - sorting_high,
                        "PACKAGE_EDGE_EVENT",
                    ),
                }
                package_edge_length = package_high - package_low
                for interface_zone in (
                    "primary_precooling_room",
                    "secondary_precooling_room",
                ):
                    for interface_shape in _local_dimension_shapes(context, interface_zone):
                        interface_span = (
                            interface_shape[3] if package_axis == 0 else interface_shape[4]
                        )
                        if not 0 < interface_span < package_edge_length:
                            continue
                        for role, aligned_start in (
                            ("LOW", package_low + interface_span),
                            ("HIGH", package_high - interface_span),
                        ):
                            offset = aligned_start - sorting_low
                            alignment_rows.setdefault(
                                offset,
                                (
                                    f"{interface_zone.upper()}_{role}",
                                    "MODULE_INTERFACE_EVENT",
                                    offset,
                                    f"{interface_zone.upper()}_DIMENSION_EVENT",
                                ),
                            )
                alignments = tuple(
                    sorted(
                        alignment_rows.values(),
                        key=lambda row: (
                            0 if row[3] == "PACKAGE_EDGE_EVENT" else 1,
                            row[0],
                            row[2],
                        ),
                    )
                )
                root_gap_events = gap_events(package_edge_name, package_edge)
                for alignment_name, edge_alignment, cross_offset, alignment_source in alignments:
                    for gap_mm, gap_event, target_event_coordinate in root_gap_events:
                        if gap_mm and corridor_width_mm <= 0:
                            continue
                        if _segment_is_horizontal(package_edge):
                            package_y = package_edge[0][1]
                            if package_edge_name == "TOP":
                                sorting_y = package_y + gap_mm - sorting_edge[0][1]
                            else:
                                sorting_y = package_y - gap_mm - sorting_edge[0][1]
                            sorting_x = cross_offset
                        else:
                            package_x = package_edge[0][0]
                            if package_edge_name == "RIGHT":
                                sorting_x = package_x + gap_mm - sorting_edge[0][0]
                            else:
                                sorting_x = package_x - gap_mm - sorting_edge[0][0]
                            sorting_y = cross_offset
                        root = _local_rectangle_at(
                            "sorting_packaging_room", shape, sorting_x, sorting_y
                        )
                        translated_edge = next(
                            edge
                            for edge_name, edge_class, edge in _named_rectangle_edge_classes(root)
                            if edge_name == sorting_edge_name and edge_class == "SHORT_EDGE"
                        )
                        overlap_low = max(
                            min(package_edge[0][package_axis], package_edge[1][package_axis]),
                            min(translated_edge[0][package_axis], translated_edge[1][package_axis]),
                        )
                        overlap_high = min(
                            max(package_edge[0][package_axis], package_edge[1][package_axis]),
                            max(translated_edge[0][package_axis], translated_edge[1][package_axis]),
                        )
                        required_overlap = corridor_width_mm if gap_mm else minimum_direct_overlap
                        if overlap_high - overlap_low < required_overlap:
                            continue
                        fixed = {"packaging_material_storage": package}
                        if not _site_module_is_usable(
                            context, {"sorting_packaging_room": root}, fixed
                        ):
                            continue
                        corridor: PlacedRectangleV1 | None = None
                        corridor_center = (overlap_low + overlap_high) // 2
                        if gap_mm:
                            if _segment_is_horizontal(package_edge):
                                corridor = _rectangle_from_mm(
                                    "__reserved_packaging_corridor__",
                                    corridor_center - corridor_width_mm // 2,
                                    min(package_edge[0][1], translated_edge[0][1]),
                                    corridor_width_mm,
                                    gap_mm,
                                    0,
                                )
                            else:
                                corridor = _rectangle_from_mm(
                                    "__reserved_packaging_corridor__",
                                    min(package_edge[0][0], translated_edge[0][0]),
                                    corridor_center - corridor_width_mm // 2,
                                    gap_mm,
                                    corridor_width_mm,
                                    0,
                                )
                            if (
                                not rectangle_inside_polygon(corridor, context.boundary)
                                or any(
                                    rectangle_intersects_closed_obstacle(corridor, obstacle)
                                    for obstacle in context.obstacles
                                )
                                or rectangles_overlap(corridor, package)
                                or rectangles_overlap(corridor, root)
                            ):
                                continue
                        witness = {
                            "identity": "packaging-sorting-interface-alignment-witness@1.0.0",
                            "classification": "CONSTRUCTION_ORDERING_ONLY_NOT_ACCESS_VALIDATION",
                            "packaging_anchor_id": packaging_anchor.anchor_id,
                            "sorting_rotation_deg": rotation,
                            "package_long_edge": package_edge_name,
                            "sorting_short_edge": sorting_edge_name,
                            "package_side_of_sorting": package_side,
                            "alignment": alignment_name,
                            "edge_alignment": edge_alignment,
                            "alignment_source": alignment_source,
                            "gap_mm": gap_mm,
                            "gap_event": gap_event,
                            "target_event_coordinate_mm": target_event_coordinate,
                            "overlap_interval_mm": [overlap_low, overlap_high],
                            "reserved_corridor_bounds_mm": (
                                list(corridor.bounds_mm) if corridor is not None else None
                            ),
                            "final_p2d_route_validated": False,
                        }
                        signature = (
                            root.bounds_mm + (root.rotation_deg,),
                            package_side,
                            gap_mm,
                            f"{gap_event}:{alignment_name}:{edge_alignment}",
                        )
                        roots.setdefault(signature, (root, package_side, corridor, witness))

    def root_order(
        row: tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]],
    ) -> tuple[Any, ...]:
        root, package_side, _corridor, witness = row
        gap_event = str(witness.get("gap_event", ""))
        event_rank = (
            0
            if gap_event == "DIRECT"
            else 1
            if gap_event == "PROFILE_CLEAR_WIDTH"
            else 2
            if "BAY-" in gap_event
            else 3
            if "OBSTACLE_" in gap_event
            else 4
        )
        return (
            root.rotation_deg,
            package_side,
            event_rank,
            int(witness.get("gap_mm", 0)),
            str(witness.get("alignment_source", "")),
            str(witness.get("alignment", "")),
            root.bounds_mm,
        )

    ordered_rows = sorted(roots.values(), key=root_order)
    root_limit = 24
    if len(ordered_rows) > root_limit:
        by_interface_event: dict[tuple[int, str, str, str], list[Any]] = {}
        for row in ordered_rows:
            by_interface_event.setdefault(
                (
                    row[0].rotation_deg,
                    row[1],
                    str(row[3].get("gap_event", "")),
                    str(row[3].get("alignment_source", "")),
                ),
                [],
            ).append(row)
        selected_rows: list[Any] = []
        interface_events = sorted(
            by_interface_event,
            key=lambda key: (
                key[0],
                key[1],
                0 if key[2] == "DIRECT" else 1 if key[2] == "PROFILE_CLEAR_WIDTH" else 2,
                key[2],
                key[3],
            ),
        )
        for group_key in interface_events:
            selected_rows.append(by_interface_event[group_key][0])
            if len(selected_rows) >= root_limit:
                break
        if len(selected_rows) < root_limit:
            selected_signatures: set[tuple[tuple[int, int, int, int], int, str, str, str]] = {
                (
                    row[0].bounds_mm,
                    row[0].rotation_deg,
                    row[1],
                    str(row[3].get("gap_event", "")),
                    str(row[3].get("alignment", "")),
                )
                for row in selected_rows
            }
            for row in ordered_rows:
                root_signature = (
                    row[0].bounds_mm,
                    row[0].rotation_deg,
                    row[1],
                    str(row[3].get("gap_event", "")),
                    str(row[3].get("alignment", "")),
                )
                if root_signature in selected_signatures:
                    continue
                selected_rows.append(row)
                selected_signatures.add(root_signature)
                if len(selected_rows) >= root_limit:
                    break
        ordered_rows = selected_rows

    if stats is not None and stats.sorting_rotation_site_attempt_counts is not None:
        for root, _side, _corridor, _witness in ordered_rows:
            key = str(root.rotation_deg)
            stats.sorting_rotation_site_attempt_counts[key] += 1
    return tuple(ordered_rows)


def _module_main_site_assemblies_forward(
    context: _PlacementSearchContext,
    main_compositions: Sequence[LocalBuildingCompositionV1],
    layout_family: str,
    process_axis: str,
    process_direction: str,
    bays: Sequence[BuildableBayV1],
    *,
    limit: int,
    source_pairs: Sequence[tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]]]
    | None = None,
    stats: _PlacementSearchStats | None = None,
) -> Iterator[dict[str, Any] | None]:
    """Build an eight-zone critical assembly from package anchors outward.

    A packaging rectangle is selected first. Its authoritative LONG_EDGE
    events generate the only sorting roots considered for that construction
    attempt; RAW and FINISHED rigid modules are then attached to the sorting
    core. The seven-zone mapping exists only as an internal partial geometry
    for exact graph/preflight checks and is never yielded as an accepted S1.
    """
    if limit <= 0:
        return
    if not bays:
        return
    selected_source_pairs = tuple(
        source_pairs or _main_module_source_pairs(context, main_compositions)
    )
    if not selected_source_pairs:
        yield None
        return
    selected_source_pairs_with_variants = tuple(
        (
            raw_source,
            finished_source,
            _balanced_site_module_pair_variants(raw_source, finished_source),
            _module_signature(raw_source),
            _module_signature(finished_source),
        )
        for raw_source, finished_source in selected_source_pairs
    )
    raw_module_signature_by_identity = {
        id(raw_module): _module_signature(raw_module)
        for (
            _raw_source,
            _finished_source,
            variants,
            _raw_sig,
            _finished_sig,
        ) in selected_source_pairs_with_variants
        for raw_module, _finished_module in variants
    }
    finished_module_signature_by_identity = {
        id(finished_module): _module_signature(finished_module)
        for (
            _raw_source,
            _finished_source,
            variants,
            _raw_sig,
            _finished_sig,
        ) in selected_source_pairs_with_variants
        for _raw_module, finished_module in variants
    }
    finished_dock_order_cache: dict[
        tuple[tuple[int, ...], str, tuple[tuple[str, tuple[int, ...]], ...]],
        tuple[int, int, int, int, tuple[int, int, int, int]],
    ] = {}
    face_pairs = _family_core_face_pairs(layout_family, process_axis, process_direction)
    yielded_critical_geometries: set[str] = set()
    invocation_core_pair_count = 0
    local_packaging_preflight_cache: dict[str, dict[str, Any]] = {}
    family_counts: dict[str, int] | None = None
    family_geometry_keys: set[str] | None = None
    family_tail_capable_geometry_keys: set[str] | None = None
    family_packaging_rejected_keys: set[str] | None = None
    family_packaging_unavailable_keys: set[str] | None = None
    family_core_pair_keys: set[str] | None = None
    raw_site_main_geometry_keys: set[str] = set()
    if stats is not None:
        if stats.site_main_assembly_counts_by_family is None:
            stats.site_main_assembly_counts_by_family = {}
        if stats.site_main_assembly_geometry_keys_by_family is None:
            stats.site_main_assembly_geometry_keys_by_family = {}
        family_geometry_keys = stats.site_main_assembly_geometry_keys_by_family.setdefault(
            layout_family, set()
        )
        if stats.site_main_assembly_tail_capable_geometry_keys_by_family is None:
            stats.site_main_assembly_tail_capable_geometry_keys_by_family = {}
        family_tail_capable_geometry_keys = (
            stats.site_main_assembly_tail_capable_geometry_keys_by_family.setdefault(
                layout_family, set()
            )
        )
        if stats.site_main_assembly_packaging_rejected_geometry_keys_by_family is None:
            stats.site_main_assembly_packaging_rejected_geometry_keys_by_family = {}
        family_packaging_rejected_keys = (
            stats.site_main_assembly_packaging_rejected_geometry_keys_by_family.setdefault(
                layout_family, set()
            )
        )
        if stats.site_main_assembly_packaging_unavailable_geometry_keys_by_family is None:
            stats.site_main_assembly_packaging_unavailable_geometry_keys_by_family = {}
        family_packaging_unavailable_keys = (
            stats.site_main_assembly_packaging_unavailable_geometry_keys_by_family.setdefault(
                layout_family, set()
            )
        )
        if stats.packaging_sorting_core_pair_geometry_keys_by_family is None:
            stats.packaging_sorting_core_pair_geometry_keys_by_family = {}
        family_core_pair_keys = (
            stats.packaging_sorting_core_pair_geometry_keys_by_family.setdefault(
                layout_family, set()
            )
        )
        family_counts = stats.site_main_assembly_counts_by_family.setdefault(
            layout_family,
            {
                "source_pair_count": 0,
                "source_pair_attempt_row_count": 0,
                "source_pair_distinct_input_geometry_count": 0,
                "source_pair_with_site_valid_critical_geometry_count": 0,
                "source_pairs_exhausted": 0,
                "source_pair_tail_capacity_exhausted": 0,
                "raw_site_valid_main_count": 0,
                "packaging_slot_rejected_main_count": 0,
                "packaging_slot_unavailable_main_count": 0,
                "tail_capable_main_count": 0,
                "packaging_sorting_core_pair_count": 0,
                "critical_8_zone_count": 0,
                "raw_attachment_candidate_count": 0,
                "raw_attachment_site_valid_count": 0,
                "finished_attachment_candidate_count": 0,
                "finished_attachment_site_valid_count": 0,
                "main_must_graph_valid_count": 0,
            },
        )
        family_counts["source_pair_count"] += len(selected_source_pairs)
        if stats.early_packaging_preflight_by_geometry is None:
            stats.early_packaging_preflight_by_geometry = {}

    def record_source_pair(row: dict[str, Any]) -> None:
        if stats is not None:
            if stats.site_main_source_pair_rows is None:
                stats.site_main_source_pair_rows = []
            stats.site_main_source_pair_rows.append(row)

    def record_geometry_attempt(row: dict[str, Any]) -> None:
        if stats is not None:
            if stats.site_module_assembly_trace is None:
                stats.site_module_assembly_trace = []
            stats.site_module_assembly_trace.append(row)

    all_anchors = (
        stats.site_packaging_anchors
        if stats is not None and stats.site_packaging_anchors is not None
        else _enumerate_packaging_site_anchors(context, bays)
    )
    package_root_options: dict[
        str,
        tuple[tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]], ...],
    ] = (
        stats.site_packaging_sorting_roots_by_anchor
        if stats is not None and stats.site_packaging_sorting_roots_by_anchor is not None
        else {}
    )
    if stats is not None and stats.site_packaging_sorting_roots_by_anchor is None:
        stats.site_packaging_sorting_roots_by_anchor = package_root_options
    anchors = (
        stats.site_packaging_construction_anchors
        if stats is not None and stats.site_packaging_construction_anchors is not None
        else _packaging_anchor_construction_representatives(
            context,
            all_anchors,
            bays,
            root_options_by_anchor=package_root_options,
            stats=stats,
        )
    )
    if stats is not None:
        if stats.site_module_variant_counts is None:
            stats.site_module_variant_counts = {}
        stats.site_module_variant_counts["packaging_site_anchor_count"] = len(all_anchors)
        stats.site_module_variant_counts["packaging_anchor_construction_representative_count"] = (
            len(anchors)
        )
        stats.site_module_variant_counts["packaging_anchor_count_by_bay"] = {
            bay_id: sum(anchor.bay_id == bay_id for anchor in all_anchors)
            for bay_id in sorted({anchor.bay_id for anchor in all_anchors})
        }
        stats.site_module_variant_counts["packaging_anchor_proof_mode"] = (
            EXACT_ORTHOGONAL_EVENT_ENUMERATION if anchors else EVENT_COMPLETENESS_UNAVAILABLE
        )
        stats.site_packaging_anchors = all_anchors
        stats.site_packaging_construction_anchors = anchors
    if not anchors:
        yield None
        return
    if stats is not None and stats.sorting_rotation_site_attempt_counts is None:
        stats.sorting_rotation_site_attempt_counts = {"0": 0, "90": 0}
    critical_signatures_seen: set[str] = set()
    dock_rectangles = _shipping_rectangles_for_dock_events(context)
    for anchor in anchors:
        options = package_root_options.get(anchor.anchor_id)
        if options is None:
            options = _packaging_driven_sorting_roots(context, anchor, bays=bays, stats=stats)
            package_root_options[anchor.anchor_id] = options
        record_geometry_attempt(
            {
                "layout_family": layout_family,
                "stage": "S0_PACKAGING_ANCHOR_DRIVEN_SORTING_ROOTS",
                "result": "ROOTS_DERIVED_FROM_PACKAGING_LONG_EDGE",
                "packaging_anchor": anchor.to_dict(),
                "sorting_root_count": len(options),
                "sorting_rotation_attempts": [0, 90],
                "sorting_roots": [
                    {
                        "bounds_mm": list(root.bounds_mm),
                        "rotation_deg": root.rotation_deg,
                        "package_side_of_sorting": package_side,
                        "alignment_witness": witness,
                        "reserved_corridor_bounds_mm": (
                            list(corridor.bounds_mm) if corridor is not None else None
                        ),
                    }
                    for root, package_side, corridor, witness in options
                ],
                "sorting_alignment_proofs": dict(
                    (stats.packaging_anchor_sorting_alignment_proofs_by_group or {}).get(
                        anchor.anchor_id, {}
                    )
                )
                if stats is not None
                else {},
                "counts_as_placement_node": False,
            }
        )

    alignments = ("CENTER", "LOW", "HIGH")
    for anchor in anchors:
        package = anchor.rectangle
        root_options = package_root_options[anchor.anchor_id]
        if not root_options:
            continue
        base_core: dict[str, PlacedRectangleV1] = {"packaging_material_storage": package}
        anchor_admitted = False
        for root, package_side, reserved_corridor, alignment_witness in root_options:
            core_pair = {**base_core, "sorting_packaging_room": root}
            if not _site_module_is_usable(context, core_pair, {}):
                continue
            if reserved_corridor is not None and any(
                rectangles_overlap(reserved_corridor, rectangle) for rectangle in core_pair.values()
            ):
                continue
            core_pair_signature = repr(_module_signature(core_pair))
            ordered_module_variants_cache: dict[
                tuple[int, tuple[int, ...], str],
                tuple[tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]], ...],
            ] = {}
            raw_attachment_cache: dict[
                tuple[tuple[tuple[str, tuple[int, ...]], ...], str, str],
                dict[str, PlacedRectangleV1] | None,
            ] = {}
            finished_attachment_cache: dict[
                tuple[tuple[tuple[str, tuple[int, ...]], ...], str, str],
                dict[str, PlacedRectangleV1] | None,
            ] = {}
            raw_attachment_core_site_valid: dict[
                tuple[tuple[tuple[str, tuple[int, ...]], ...], str, str], bool
            ] = {}
            finished_attachment_core_site_valid: dict[
                tuple[tuple[tuple[str, tuple[int, ...]], ...], str, str], bool
            ] = {}
            invocation_core_pair_count += 1
            if family_core_pair_keys is None or core_pair_signature not in family_core_pair_keys:
                if family_core_pair_keys is not None:
                    family_core_pair_keys.add(core_pair_signature)
                if family_counts is not None:
                    family_counts["packaging_sorting_core_pair_count"] += 1

            for source_pair_index, (
                _raw_source,
                _finished_source,
                module_pair_variants,
                raw_source_signature,
                finished_source_signature,
            ) in enumerate(selected_source_pairs_with_variants):
                source_pair_geometry_signature = repr(
                    (raw_source_signature, finished_source_signature)
                )
                pair_admitted_count = 0
                pair_main_geometry_keys: set[str] = set()
                pair_critical_keys: set[str] = set()
                pair_sorting_roots: set[tuple[int, ...]] = set()
                pair_raw_attachment_candidates = 0
                pair_raw_attachment_site_valid = 0
                pair_finished_attachment_candidates = 0
                pair_finished_attachment_site_valid = 0
                pair_main_must_graph_valid = 0

                pair_sorting_roots.add(root.bounds_mm + (root.rotation_deg,))
                for raw_side, finished_side in face_pairs:
                    # Packaging may occupy one core face. The actual site
                    # predicate, rather than a new adjacency requirement,
                    # decides whether the remaining module attachment fits.
                    # Dock ordering is evaluated after attaching each finished
                    # module variant to this site-frame core face.
                    def dock_order(
                        pair: tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]],
                        sorting_root: PlacedRectangleV1 = root,
                        selected_finished_side: str = finished_side,
                    ) -> tuple[int, int, int, int, tuple[int, int, int, int]]:
                        root_key = sorting_root.bounds_mm + (sorting_root.rotation_deg,)
                        finished_signature = finished_module_signature_by_identity[id(pair[1])]
                        cache_key = (root_key, selected_finished_side, finished_signature)
                        cached_order = finished_dock_order_cache.get(cache_key)
                        if cached_order is not None:
                            return cached_order
                        order = _finished_module_site_dock_order(
                            pair[1],
                            sorting_root,
                            selected_finished_side,
                            alignments,
                            dock_rectangles,
                        )
                        finished_dock_order_cache[cache_key] = order
                        return order

                    order_key = (
                        source_pair_index,
                        root.bounds_mm + (root.rotation_deg,),
                        finished_side,
                    )
                    ordered_module_variants = ordered_module_variants_cache.get(order_key)
                    if ordered_module_variants is None:
                        ordered_module_variants = tuple(
                            sorted(module_pair_variants, key=dock_order)
                        )
                        ordered_module_variants_cache[order_key] = ordered_module_variants
                    for raw_module, finished_module in ordered_module_variants:
                        for raw_alignment in alignments:
                            pair_raw_attachment_candidates += 1
                            raw_key = (
                                raw_module_signature_by_identity[id(raw_module)],
                                raw_side,
                                raw_alignment,
                            )
                            if raw_key not in raw_attachment_cache:
                                raw_attachment_cache[raw_key] = _module_attached_to_zone(
                                    raw_module,
                                    "primary_precooling_room",
                                    root,
                                    raw_side,
                                    raw_alignment,
                                )
                            raw_attached = raw_attachment_cache[raw_key]
                            if raw_attached is None:
                                continue
                            if raw_key not in raw_attachment_core_site_valid:
                                raw_attachment_core_site_valid[raw_key] = _site_module_is_usable(
                                    context, raw_attached, core_pair
                                )
                            if not raw_attachment_core_site_valid[raw_key]:
                                continue
                            pair_raw_attachment_site_valid += 1
                            if reserved_corridor is not None and any(
                                rectangles_overlap(reserved_corridor, rectangle)
                                for rectangle in raw_attached.values()
                            ):
                                continue
                            for finished_alignment in alignments:
                                finished_key = (
                                    finished_module_signature_by_identity[id(finished_module)],
                                    finished_side,
                                    finished_alignment,
                                )
                                if finished_key not in finished_attachment_cache:
                                    finished_attachment_cache[finished_key] = (
                                        _module_attached_to_zone(
                                            finished_module,
                                            "secondary_precooling_room",
                                            root,
                                            finished_side,
                                            finished_alignment,
                                        )
                                    )
                                finished_attached = finished_attachment_cache[finished_key]
                                if finished_attached is None:
                                    continue
                                pair_finished_attachment_candidates += 1
                                if stats is not None:
                                    stats.finished_forward_site_attempt_count += 1
                                if finished_key not in finished_attachment_core_site_valid:
                                    finished_attachment_core_site_valid[finished_key] = (
                                        _site_module_is_usable(
                                            context, finished_attached, core_pair
                                        )
                                    )
                                if not finished_attachment_core_site_valid[finished_key]:
                                    continue
                                if any(
                                    rectangles_overlap(finished_rectangle, raw_rectangle)
                                    for finished_rectangle in finished_attached.values()
                                    for raw_rectangle in raw_attached.values()
                                ):
                                    continue
                                pair_finished_attachment_site_valid += 1
                                if reserved_corridor is not None and any(
                                    rectangles_overlap(reserved_corridor, rectangle)
                                    for rectangle in finished_attached.values()
                                ):
                                    continue
                                main_candidate = {
                                    **core_pair,
                                    **raw_attached,
                                    **finished_attached,
                                }
                                try:
                                    _validate_main_process_skeleton_graph(
                                        context.graph,
                                        {
                                            code: main_candidate[code]
                                            for code in MAIN_PROCESS_SKELETON_ZONE_CODES
                                        },
                                    )
                                except LayoutAuthorityError:
                                    continue
                                pair_main_must_graph_valid += 1
                                main_signature = _module_signature(
                                    {
                                        code: main_candidate[code]
                                        for code in MAIN_PROCESS_SKELETON_ZONE_CODES
                                    }
                                )
                                geometry_key = repr(main_signature)
                                pair_main_geometry_keys.add(geometry_key)
                                if geometry_key not in raw_site_main_geometry_keys:
                                    raw_site_main_geometry_keys.add(geometry_key)
                                    is_new_family_geometry = (
                                        family_geometry_keys is None
                                        or geometry_key not in family_geometry_keys
                                    )
                                    if family_geometry_keys is not None:
                                        family_geometry_keys.add(geometry_key)
                                    if family_counts is not None and is_new_family_geometry:
                                        family_counts["raw_site_valid_main_count"] += 1

                                proof_cache = (
                                    stats.early_packaging_preflight_by_geometry
                                    if stats is not None
                                    and stats.early_packaging_preflight_by_geometry is not None
                                    else local_packaging_preflight_cache
                                )
                                proof = proof_cache.get(geometry_key)
                                formal_preflight_reused = proof is not None
                                if proof is None:
                                    proof = _packaging_tail_slot_preflight_for_rectangles(
                                        context,
                                        tuple(
                                            main_candidate[code]
                                            for code in MAIN_PROCESS_SKELETON_ZONE_CODES
                                        ),
                                    )
                                    proof_cache[geometry_key] = proof
                                formal_pass = (
                                    proof.get("legal_slot_exists") is True
                                    and proof.get("proof_mode")
                                    == EXACT_ORTHOGONAL_EVENT_ENUMERATION
                                )
                                witness = alignment_witness
                                record_geometry_attempt(
                                    {
                                        "layout_family": layout_family,
                                        "stage": "S1_PACKAGING_RESERVED_MAIN_PREFLIGHT",
                                        "result": (
                                            "FORMAL_PREFLIGHT_PASS"
                                            if formal_pass
                                            else "FORMAL_PREFLIGHT_REJECT"
                                            if proof.get("legal_slot_exists") is False
                                            else "FORMAL_PREFLIGHT_UNAVAILABLE"
                                        ),
                                        "construction_order": [
                                            "PACKAGING_ANCHOR",
                                            "SORTING_CORE",
                                            "RAW_MODULE",
                                            "FINISHED_MODULE",
                                        ],
                                        "source_pair_index": source_pair_index,
                                        "packaging_anchor": anchor.to_dict(),
                                        "sorting_rotation_deg": root.rotation_deg,
                                        "sorting_root_bounds_mm": list(root.bounds_mm),
                                        "package_side_of_sorting": package_side,
                                        "packaging_sorting_alignment_witness": witness,
                                        "geometry_signature": geometry_key,
                                        "preflight_reused": formal_preflight_reused,
                                        "zones": [
                                            main_candidate[code].to_dict()
                                            for code in MAIN_PROCESS_SKELETON_ZONE_CODES
                                        ],
                                        "formal_preflight": proof,
                                        "counts_as_placement_node": False,
                                    }
                                )
                                if not formal_pass:
                                    if proof.get("legal_slot_exists") is False:
                                        is_new_rejection = (
                                            family_packaging_rejected_keys is None
                                            or geometry_key not in family_packaging_rejected_keys
                                        )
                                        if (
                                            is_new_rejection
                                            and family_packaging_rejected_keys is not None
                                        ):
                                            family_packaging_rejected_keys.add(geometry_key)
                                        if family_counts is not None and is_new_rejection:
                                            family_counts["packaging_slot_rejected_main_count"] += 1
                                    else:
                                        is_new_unavailable = (
                                            family_packaging_unavailable_keys is None
                                            or geometry_key not in family_packaging_unavailable_keys
                                        )
                                        if (
                                            is_new_unavailable
                                            and family_packaging_unavailable_keys is not None
                                        ):
                                            family_packaging_unavailable_keys.add(geometry_key)
                                        if family_counts is not None and is_new_unavailable:
                                            family_counts[
                                                "packaging_slot_unavailable_main_count"
                                            ] += 1
                                    continue

                                # ``anchor`` was enumerated once against the
                                # authoritative site/no-build geometry, and
                                # every core/module attachment above was
                                # checked against it with exact zone overlap
                                # predicates.  Re-enumerating the entire site
                                # anchor event set for this completed skeleton
                                # is redundant; the formal fixed-skeleton R9
                                # preflight above remains the admission gate.
                                critical = dict(main_candidate)
                                critical_signature = repr(_module_signature(critical))
                                if critical_signature in critical_signatures_seen:
                                    continue
                                critical_signatures_seen.add(critical_signature)
                                pair_critical_keys.add(critical_signature)
                                pair_admitted_count += 1
                                if family_counts is not None:
                                    family_counts["critical_8_zone_count"] += 1
                                    family_counts["packaging_reserved_main_count"] = (
                                        family_counts.get("packaging_reserved_main_count", 0) + 1
                                    )
                                is_new_tail_capable = (
                                    family_tail_capable_geometry_keys is None
                                    or geometry_key not in family_tail_capable_geometry_keys
                                )
                                if is_new_tail_capable:
                                    if family_tail_capable_geometry_keys is not None:
                                        family_tail_capable_geometry_keys.add(geometry_key)
                                    if family_counts is not None:
                                        family_counts["tail_capable_main_count"] += 1
                                if reserved_corridor is not None and stats is not None:
                                    stats.reserve_construction_space(
                                        critical_signature, reserved_corridor
                                    )
                                record_geometry_attempt(
                                    {
                                        "layout_family": layout_family,
                                        "process_axis": process_axis,
                                        "process_direction": process_direction,
                                        "stage": "S1_PACKAGING_RESERVED_MAIN_ASSEMBLY",
                                        "result": "PACKAGING_RESERVED_MAIN_ADMITTED",
                                        "source_pair_index": source_pair_index,
                                        "packaging_anchor": anchor.to_dict(),
                                        "sorting_rotation_deg": root.rotation_deg,
                                        "sorting_root_bounds_mm": list(root.bounds_mm),
                                        "packaging_sorting_alignment_witness": witness,
                                        "reserved_construction_space": (
                                            reserved_corridor.to_dict()
                                            if reserved_corridor is not None
                                            else None
                                        ),
                                        "zones": [
                                            critical[code].to_dict()
                                            for code in (
                                                *MAIN_PROCESS_SKELETON_ZONE_CODES,
                                                "packaging_material_storage",
                                            )
                                        ],
                                        "packaging_slot_exists": True,
                                        "packaging_proof_mode": proof["proof_mode"],
                                        "formal_preflight_match_expected": True,
                                        "counts_as_placement_node": False,
                                        "packaging_reserved_main_limit": limit,
                                    }
                                )
                                anchor_admitted = True
                                yielded_critical_geometries.add(critical_signature)
                                if len(yielded_critical_geometries) >= limit:
                                    if family_counts is not None:
                                        family_counts["source_pair_attempt_row_count"] += 1
                                        family_counts[
                                            "source_pair_distinct_input_geometry_count"
                                        ] += len(pair_main_geometry_keys)
                                        family_counts[
                                            "source_pair_with_site_valid_critical_geometry_count"
                                        ] += int(bool(pair_critical_keys))
                                        family_counts["raw_attachment_candidate_count"] += (
                                            pair_raw_attachment_candidates
                                        )
                                        family_counts["raw_attachment_site_valid_count"] += (
                                            pair_raw_attachment_site_valid
                                        )
                                        family_counts["finished_attachment_candidate_count"] += (
                                            pair_finished_attachment_candidates
                                        )
                                        family_counts["finished_attachment_site_valid_count"] += (
                                            pair_finished_attachment_site_valid
                                        )
                                        family_counts["main_must_graph_valid_count"] += (
                                            pair_main_must_graph_valid
                                        )
                                    record_source_pair(
                                        {
                                            "layout_family": layout_family,
                                            "process_axis": process_axis,
                                            "process_direction": process_direction,
                                            "source_pair_index": source_pair_index,
                                            "source_pair_geometry_signature": (
                                                source_pair_geometry_signature
                                            ),
                                            "packaging_anchor_id": anchor.anchor_id,
                                            "result": "PACKAGING_RESERVED_MAIN_LIMIT_REACHED",
                                            "source_pair_exhausted": False,
                                            "tail_capable_limit_reached": True,
                                            "packaging_sorting_core_pair_count": len(
                                                family_core_pair_keys or ()
                                            ),
                                            "distinct_input_geometry_count": len(
                                                pair_main_geometry_keys
                                            ),
                                            "site_valid_critical_geometry_count": int(
                                                bool(pair_critical_keys)
                                            ),
                                            "critical_8_zone_count": len(pair_critical_keys),
                                            "sorting_root_count": len(pair_sorting_roots),
                                            "raw_attachment_candidate_count": (
                                                pair_raw_attachment_candidates
                                            ),
                                            "raw_attachment_site_valid_count": (
                                                pair_raw_attachment_site_valid
                                            ),
                                            "finished_attachment_candidate_count": (
                                                pair_finished_attachment_candidates
                                            ),
                                            "finished_attachment_site_valid_count": (
                                                pair_finished_attachment_site_valid
                                            ),
                                            "main_must_graph_valid_count": (
                                                pair_main_must_graph_valid
                                            ),
                                        }
                                    )
                                    yield critical
                                    return
                                yield critical
                                if anchor_admitted:
                                    break
                            if anchor_admitted:
                                break
                        if anchor_admitted:
                            break
                    if anchor_admitted:
                        break
                if family_counts is not None:
                    family_counts["source_pair_attempt_row_count"] += 1
                    family_counts["source_pair_distinct_input_geometry_count"] += len(
                        pair_main_geometry_keys
                    )
                    family_counts["source_pair_with_site_valid_critical_geometry_count"] += int(
                        bool(pair_critical_keys)
                    )
                    family_counts["raw_attachment_candidate_count"] += (
                        pair_raw_attachment_candidates
                    )
                    family_counts["raw_attachment_site_valid_count"] += (
                        pair_raw_attachment_site_valid
                    )
                    family_counts["finished_attachment_candidate_count"] += (
                        pair_finished_attachment_candidates
                    )
                    family_counts["finished_attachment_site_valid_count"] += (
                        pair_finished_attachment_site_valid
                    )
                    family_counts["main_must_graph_valid_count"] += pair_main_must_graph_valid
                tail_capacity_exhausted = (
                    bool(pair_main_geometry_keys)
                    and not pair_critical_keys
                    and (
                        family_packaging_rejected_keys is not None
                        and pair_main_geometry_keys.issubset(family_packaging_rejected_keys)
                    )
                )
                if tail_capacity_exhausted and family_counts is not None:
                    family_counts["source_pair_tail_capacity_exhausted"] += 1
                record_source_pair(
                    {
                        "layout_family": layout_family,
                        "process_axis": process_axis,
                        "process_direction": process_direction,
                        "source_pair_index": source_pair_index,
                        "source_pair_geometry_signature": source_pair_geometry_signature,
                        "packaging_anchor_id": anchor.anchor_id,
                        "result": (
                            "PACKAGING_RESERVED_MAIN_ADMITTED"
                            if pair_admitted_count
                            else "SOURCE_PAIR_TAIL_CAPACITY_EXHAUSTED"
                            if tail_capacity_exhausted
                            else "SOURCE_PAIR_VARIANTS_EXHAUSTED"
                        ),
                        "source_pair_exhausted": True,
                        "tail_capacity_exhausted": tail_capacity_exhausted,
                        "packaging_sorting_core_pair_count": invocation_core_pair_count,
                        "distinct_input_geometry_count": len(pair_main_geometry_keys),
                        "site_valid_critical_geometry_count": int(bool(pair_critical_keys)),
                        "critical_8_zone_count": len(pair_critical_keys),
                        "sorting_root_count": len(pair_sorting_roots),
                        "raw_attachment_candidate_count": pair_raw_attachment_candidates,
                        "raw_attachment_site_valid_count": pair_raw_attachment_site_valid,
                        "finished_attachment_candidate_count": pair_finished_attachment_candidates,
                        "finished_attachment_site_valid_count": (
                            pair_finished_attachment_site_valid
                        ),
                        "main_must_graph_valid_count": pair_main_must_graph_valid,
                    }
                )
                if anchor_admitted:
                    break
            if anchor_admitted:
                break
    if not yielded_critical_geometries and invocation_core_pair_count == 0:
        yield None


@dataclass(frozen=True)
class AccessDrivenTailCandidateV1:
    """Finite S2 construction seed derived from its actual access endpoints."""

    module_name: str
    placements: tuple[tuple[str, PlacedRectangleV1], ...]
    driving_requirement_ids: tuple[str, ...]
    anchor_source: str
    endpoint_event_class: str
    direct_shared_edge_possible: bool
    route_witness_status: str = "UNVALIDATED"
    construction_order_key: tuple[Any, ...] = ()
    construction_corridor_centerline_mm: tuple[tuple[int, int], ...] = ()
    construction_corridor_envelopes_mm: tuple[PolygonMM, ...] = ()
    construction_portal_pair_mm: tuple[tuple[int, int], tuple[int, int]] | None = None

    def as_placements(self) -> dict[str, PlacedRectangleV1]:
        return dict(self.placements)


def _single_zone_site_module_candidates(
    context: _PlacementSearchContext,
    zone_code: str,
    fixed: Mapping[str, PlacedRectangleV1],
    bays: Sequence[BuildableBayV1],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Enumerate one-zone module origins from exact site/module event edges."""
    polygons = (context.boundary, *context.obstacles)
    if any(not _polygon_is_orthogonal(polygon) for polygon in polygons):
        return ()
    candidates: dict[tuple[tuple[str, tuple[int, ...]], ...], dict[str, PlacedRectangleV1]] = {}
    for shape in _local_dimension_shapes(context, zone_code):
        x_span, y_span = shape[3], shape[4]
        x_events = {
            coordinate - offset
            for polygon in polygons
            for x, _y in polygon
            for coordinate in (x,)
            for offset in (0, x_span)
        }
        y_events = {
            coordinate - offset
            for polygon in polygons
            for _x, y in polygon
            for coordinate in (y,)
            for offset in (0, y_span)
        }
        for obstacle in context.obstacles:
            for x, _y in obstacle:
                x_events.update((x - x_span - GRID_MM, x - x_span, x, x + GRID_MM))
            for _x, y in obstacle:
                y_events.update((y - y_span - GRID_MM, y - y_span, y, y + GRID_MM))
        for bay in bays:
            left, bottom, right, top = bay.bounds_mm
            x_events.update((left, right - x_span))
            y_events.update((bottom, top - y_span))
        for rectangle in fixed.values():
            left, bottom, right, top = rectangle.bounds_mm
            x_events.update((left, right, left - x_span, right - x_span))
            y_events.update((bottom, top, bottom - y_span, top - y_span))
        min_x, min_y, max_x, max_y = context.boundary_bounds
        for x_mm in sorted(value for value in x_events if min_x <= value <= max_x - x_span):
            for y_mm in sorted(value for value in y_events if min_y <= value <= max_y - y_span):
                rectangle = _local_rectangle_at(zone_code, shape, x_mm, y_mm)
                module = {zone_code: rectangle}
                if _site_module_is_usable(context, module, fixed):
                    candidates.setdefault(_module_signature(module), module)
    return tuple(candidates[key] for key in sorted(candidates))


def _office_site_module_candidates(
    context: _PlacementSearchContext,
    fixed: Mapping[str, PlacedRectangleV1],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Place the office independently on its frozen shipping MUST interface."""
    shipping = fixed.get("shipping_channel")
    if shipping is None:
        return ()
    candidates: dict[tuple[tuple[str, tuple[int, ...]], ...], dict[str, PlacedRectangleV1]] = {}
    for shape in _local_dimension_shapes(context, "office"):
        office = _local_rectangle_at("office", shape, 0, 0)
        for side in ("WEST", "EAST", "SOUTH", "NORTH"):
            for alignment in ("LOW", "CENTER", "HIGH"):
                attached = _module_attached_to_zone(
                    {"office": office}, "office", shipping, side, alignment
                )
                if attached is not None and _site_module_is_usable(context, attached, fixed):
                    candidates.setdefault(_module_signature(attached), attached)
    return tuple(candidates[key] for key in sorted(candidates))


def _tail_requirement_ids(
    context: _PlacementSearchContext,
    pairs: frozenset[tuple[str, str]],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(row.get("identity"))
            for row in context.access_requirements
            if (str(row.get("from_ref")), str(row.get("to_ref"))) in pairs
        )
    )


def _access_candidate(
    module_name: str,
    zone_code: str,
    rectangle: PlacedRectangleV1,
    requirement_ids: tuple[str, ...],
    *,
    anchor_source: str,
    endpoint_event_class: str,
    direct_shared_edge_possible: bool,
) -> AccessDrivenTailCandidateV1:
    return AccessDrivenTailCandidateV1(
        module_name=module_name,
        placements=((zone_code, rectangle),),
        driving_requirement_ids=requirement_ids,
        anchor_source=anchor_source,
        endpoint_event_class=endpoint_event_class,
        direct_shared_edge_possible=direct_shared_edge_possible,
    )


def _corridor_rectangles_for_centerline(
    centerline: Sequence[tuple[int, int]], width_mm: int
) -> tuple[PlacedRectangleV1, ...]:
    half_width = width_mm // 2
    rectangles: list[PlacedRectangleV1] = []
    for start, end in zip(centerline, centerline[1:], strict=False):
        if start[0] == end[0]:
            low, high = sorted((start[1], end[1]))
            if low < high:
                rectangles.append(
                    _rectangle_from_mm(
                        "__construction_access_corridor__",
                        start[0] - half_width,
                        low,
                        width_mm,
                        high - low,
                        0,
                    )
                )
        elif start[1] == end[1]:
            low, high = sorted((start[0], end[0]))
            if low < high:
                rectangles.append(
                    _rectangle_from_mm(
                        "__construction_access_corridor__",
                        low,
                        start[1] - half_width,
                        high - low,
                        width_mm,
                        0,
                    )
                )
        else:
            return ()
    for point in centerline[1:-1]:
        rectangles.append(
            _rectangle_from_mm(
                "__construction_access_corridor__",
                point[0] - half_width,
                point[1] - half_width,
                width_mm,
                width_mm,
                0,
            )
        )
    return tuple(rectangles)


def _truck_clear_corridor_path(
    context: _PlacementSearchContext,
    centerline: Sequence[tuple[int, int]],
    width_mm: int,
    fixed: Mapping[str, PlacedRectangleV1],
    truck_envelopes: Sequence[PolygonMM],
    reserved_corridors: Sequence[PolygonMM],
) -> tuple[PlacedRectangleV1, ...]:
    """Return only event-path corridor geometry clear of current keepouts."""
    rectangles = _corridor_rectangles_for_centerline(centerline, width_mm)
    if not rectangles:
        return ()
    endpoint_zones = {"sorting_packaging_room", "frozen_fruit_room"}
    for corridor in rectangles:
        if not _rectangle_is_usable(
            corridor,
            {},
            context.boundary,
            context.boundary_bounds,
            context.obstacles,
        ):
            return ()
        if any(
            _orthogonal_polygons_interiors_overlap(corridor.polygon_mm, zone.polygon_mm)
            for code, zone in fixed.items()
            if code not in endpoint_zones
        ):
            return ()
        if any(
            _orthogonal_polygons_interiors_overlap(corridor.polygon_mm, envelope)
            for envelope in truck_envelopes
        ):
            return ()
        if any(
            _orthogonal_polygons_interiors_overlap(corridor.polygon_mm, reserved)
            for reserved in reserved_corridors
        ):
            return ()
    return rectangles


def _portal_normal_centerlines(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    source_side: str,
    target_side: str,
    corridor_width_mm: int,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Derive straight, one-turn, and offset event paths with normal portals."""
    side_normals = {
        "EAST": (1, 0),
        "WEST": (-1, 0),
        "NORTH": (0, 1),
        "SOUTH": (0, -1),
    }
    source_normal = side_normals[source_side]
    target_normal = side_normals[target_side]
    half_width = corridor_width_mm // 2
    source_outside = (
        start[0] + source_normal[0] * half_width,
        start[1] + source_normal[1] * half_width,
    )
    target_outside = (
        end[0] + target_normal[0] * half_width,
        end[1] + target_normal[1] * half_width,
    )

    connector_paths = (
        ((source_outside, target_outside),)
        if source_outside[0] == target_outside[0] or source_outside[1] == target_outside[1]
        else (
            (source_outside, (target_outside[0], source_outside[1]), target_outside),
            (source_outside, (source_outside[0], target_outside[1]), target_outside),
        )
    )
    event_paths: set[tuple[tuple[int, int], ...]] = set()

    def compact(path: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
        points: list[tuple[int, int]] = []
        for point in path:
            if points and point == points[-1]:
                continue
            if len(points) >= 2 and (
                points[-2][0] == points[-1][0] == point[0]
                or points[-2][1] == points[-1][1] == point[1]
            ):
                points[-1] = point
            else:
                points.append(point)
        return tuple(points)

    for connector in connector_paths:
        path = compact((start, *connector, end))
        if len(path) < 2:
            continue
        first_delta = (
            (path[1][0] > path[0][0]) - (path[1][0] < path[0][0]),
            (path[1][1] > path[0][1]) - (path[1][1] < path[0][1]),
        )
        last_delta = (
            (path[-1][0] > path[-2][0]) - (path[-1][0] < path[-2][0]),
            (path[-1][1] > path[-2][1]) - (path[-1][1] < path[-2][1]),
        )
        inward_target = (-target_normal[0], -target_normal[1])
        if first_delta == source_normal and last_delta == inward_target:
            event_paths.add(path)
    return tuple(
        sorted(
            event_paths,
            key=lambda path: (
                sum(
                    abs(end_point[0] - start_point[0]) + abs(end_point[1] - start_point[1])
                    for start_point, end_point in zip(path, path[1:], strict=False)
                ),
                len(path) - 2,
                path,
            ),
        )
    )


def _frozen_truck_clear_corridor_candidates(
    context: _PlacementSearchContext,
    fixed: Mapping[str, PlacedRectangleV1],
    bays: Sequence[BuildableBayV1],
    truck_envelopes: Sequence[PolygonMM],
    *,
    stats: _PlacementSearchStats | None,
    main_identity: str | None,
    reserved_corridors: Sequence[PolygonMM] = (),
) -> tuple[AccessDrivenTailCandidateV1, ...]:
    """Derive finite Frozen targets from exact sorting/portal/keepout events.

    This is a construction candidate generator, not a route validator. It
    places each Frozen portal one authoritative corridor width from a sorting
    face, derives the tangential room origins from site, obstacle, Truck,
    buildable-bay, fixed-zone and actual sorting-portal events, then asks the
    injected portal primitive and route authority to decide what is usable.
    """
    sorting = fixed.get("sorting_packaging_room")
    provider = getattr(context, "access_portal_event_provider", None)
    requirement = next(
        (
            row
            for row in context.access_requirements
            if (str(row.get("from_ref")), str(row.get("to_ref")))
            == ("sorting_packaging_room", "frozen_fruit_room")
        ),
        None,
    )
    if sorting is None or not truck_envelopes or provider is None or requirement is None:
        return ()

    sorting_geometry = provider(requirement, "sorting_packaging_room", sorting)
    sorting_portals = tuple(sorting_geometry.get("portals", ()))
    corridor_width_mm = int(sorting_geometry.get("corridor_clear_width_mm", 0))
    portal_width_mm = int(sorting_geometry.get("portal_clear_width_mm", 0))
    if not sorting_portals or corridor_width_mm <= 0 or portal_width_mm <= 0:
        if stats is not None and main_identity is not None:
            if stats.frozen_candidate_rejection_taxonomy_by_main is None:
                stats.frozen_candidate_rejection_taxonomy_by_main = {}
            taxonomy = stats.frozen_candidate_rejection_taxonomy_by_main.setdefault(
                main_identity, {}
            )
            taxonomy["NO_SORTING_PORTAL_EVENT"] = taxonomy.get("NO_SORTING_PORTAL_EVENT", 0) + 1
        return ()

    shapes = sorted(
        _local_dimension_shapes(context, "frozen_fruit_room"),
        key=lambda shape: (shape[4], shape[3], shape[2], shape[0], shape[1]),
    )
    if not shapes:
        return ()

    # Preserve the direct-seed rejection evidence independently from the
    # corridor-mediated construction domain. Direct Frozen geometry is not
    # admitted here; it is counted so the Truck-envelope rejection stays
    # explicit and auditable.
    direct_by_signature: dict[tuple[tuple[str, tuple[int, ...]], ...], PlacedRectangleV1] = {}
    for shape in shapes:
        x_span, y_span = shape[3], shape[4]
        for side in ("WEST", "EAST", "SOUTH", "NORTH"):
            for alignment in ("LOW", "CENTER", "HIGH"):
                x_mm, y_mm = _local_adjacent_origin(sorting, x_span, y_span, side, alignment)
                rectangle = _local_rectangle_at("frozen_fruit_room", shape, x_mm, y_mm)
                if _site_module_is_usable(context, {"frozen_fruit_room": rectangle}, fixed):
                    direct_by_signature[_module_signature({"frozen_fruit_room": rectangle})] = (
                        rectangle
                    )
    direct_after_truck = {
        signature: rectangle
        for signature, rectangle in direct_by_signature.items()
        if not any(
            rectangle_intersects_closed_obstacle(rectangle, envelope)
            for envelope in truck_envelopes
        )
    }
    direct_truck_rejection_count = len(direct_by_signature) - len(direct_after_truck)
    if stats is not None and main_identity is not None:
        if stats.tail_direct_seed_counts_before_truck_filter_by_main is None:
            stats.tail_direct_seed_counts_before_truck_filter_by_main = {}
        if stats.tail_direct_seed_counts_after_truck_filter_by_main is None:
            stats.tail_direct_seed_counts_after_truck_filter_by_main = {}
        stats.tail_direct_seed_counts_before_truck_filter_by_main.setdefault(main_identity, {})[
            "FROZEN_SUPPORT_MODULE"
        ] = len(direct_by_signature)
        stats.tail_direct_seed_counts_after_truck_filter_by_main.setdefault(main_identity, {})[
            "FROZEN_SUPPORT_MODULE"
        ] = len(direct_after_truck)
        for signature, rectangle in direct_by_signature.items():
            shared = _sorting_shared_interval_mm(sorting, rectangle)
            for envelope_index, envelope in enumerate(truck_envelopes):
                if not rectangle_intersects_closed_obstacle(rectangle, envelope):
                    continue
                bounds = rectangle.bounds_mm
                envelope_bounds = _boundary_extents(envelope)
                overlap_bounds = (
                    max(bounds[0], envelope_bounds[0]),
                    max(bounds[1], envelope_bounds[1]),
                    min(bounds[2], envelope_bounds[2]),
                    min(bounds[3], envelope_bounds[3]),
                )
                row = {
                    "main_identity": main_identity,
                    "frozen_bounds_mm": list(bounds),
                    "sorting_shared_side": shared[0] if shared else None,
                    "sorting_shared_interval_mm": list(shared[1:]) if shared else None,
                    "truck_envelope_identity": f"TRUCK_ENVELOPE-{envelope_index + 1:02d}",
                    "truck_envelope_index": envelope_index,
                    "closed_geometry_intersection": True,
                    "exact_positive_area_overlap": _rectangle_interiors_overlap_orthogonal_polygon(
                        rectangle, envelope
                    ),
                    "overlap_bounds_mm": list(overlap_bounds)
                    if overlap_bounds[0] < overlap_bounds[2]
                    and overlap_bounds[1] < overlap_bounds[3]
                    else None,
                    "alternative_sorting_side_interval_exists": any(
                        _sorting_shared_interval_mm(sorting, alternative) is not None
                        and _module_signature({"frozen_fruit_room": alternative}) != signature
                        for alternative in direct_after_truck.values()
                    ),
                    "mediated_candidate_remains_unsearched": True,
                }
                if stats.frozen_direct_seed_truck_rejection_rows is None:
                    stats.frozen_direct_seed_truck_rejection_rows = []
                if row not in stats.frozen_direct_seed_truck_rejection_rows:
                    stats.frozen_direct_seed_truck_rejection_rows.append(row)

    feature_events: dict[str, set[tuple[str, str, int]]] = {"X": set(), "Y": set()}

    def add_axis_event(axis: str, kind: str, name: str, coordinate: int) -> None:
        feature_events[axis].add((kind, name, coordinate))

    def add_polygon_events(prefix: str, polygon: PolygonMM, kind: str) -> None:
        for coordinate in sorted({point[0] for point in polygon}):
            add_axis_event("X", kind, f"{prefix}_X_{coordinate}", coordinate)
        for coordinate in sorted({point[1] for point in polygon}):
            add_axis_event("Y", kind, f"{prefix}_Y_{coordinate}", coordinate)

    add_polygon_events("SITE", context.boundary, "SITE_BOUNDARY")
    for index, obstacle in enumerate(context.obstacles, start=1):
        add_polygon_events(f"OBSTACLE-{index:02d}", obstacle, "OBSTACLE")
    for index, envelope in enumerate(truck_envelopes, start=1):
        add_polygon_events(f"TRUCK_ENVELOPE-{index:02d}", envelope, "TRUCK_ENVELOPE")
    for index, corridor in enumerate(reserved_corridors, start=1):
        add_polygon_events(
            f"RESERVED_ACCESS_CORRIDOR-{index:02d}",
            corridor,
            "RESERVED_ACCESS_CORRIDOR",
        )
    for bay in bays:
        left, bottom, right, top = bay.bounds_mm
        for axis, name, coordinate in (
            ("X", f"{bay.bay_id}_X_{left}", left),
            ("X", f"{bay.bay_id}_X_{right}", right),
            ("Y", f"{bay.bay_id}_Y_{bottom}", bottom),
            ("Y", f"{bay.bay_id}_Y_{top}", top),
        ):
            add_axis_event(axis, "BUILDABLE_BAY", name, coordinate)
    for code, rectangle in sorted(fixed.items()):
        left, bottom, right, top = rectangle.bounds_mm
        for axis, name, coordinate in (
            ("X", f"{code}_X_{left}", left),
            ("X", f"{code}_X_{right}", right),
            ("Y", f"{code}_Y_{bottom}", bottom),
            ("Y", f"{code}_Y_{top}", top),
        ):
            add_axis_event(axis, "FIXED_ZONE", name, coordinate)
    for index, portal in enumerate(sorting_portals, start=1):
        center_x, center_y = portal["center_mm"]
        add_axis_event("X", "SORTING_PORTAL", f"SORTING_PORTAL-{index:02d}-X", center_x)
        add_axis_event("Y", "SORTING_PORTAL", f"SORTING_PORTAL-{index:02d}-Y", center_y)

    event_priorities = {
        "TRUCK_ENVELOPE": 0,
        "OBSTACLE": 1,
        "RESERVED_ACCESS_CORRIDOR": 2,
        "FIXED_ZONE": 3,
        "SORTING_PORTAL": 4,
        "BUILDABLE_BAY": 5,
        "SITE_BOUNDARY": 6,
    }
    physical_events: dict[str, dict[int, tuple[str, str, int]]] = {"X": {}, "Y": {}}
    for axis in ("X", "Y"):
        for kind, name, coordinate in sorted(feature_events[axis]):
            event_row = (kind, name, event_priorities.get(kind, 6))
            current = physical_events[axis].get(coordinate)
            if current is None or event_row < current:
                physical_events[axis][coordinate] = event_row
    half_corridor = corridor_width_mm // 2
    # Each candidate origin is an exact edge alignment, a one-grid legal
    # clearance, or a half-corridor event around a Truck keepout.  The finite
    # event sets are crossed only after deduplication; there is no millimetre
    # sweep and no expansion by unrelated room coordinates.
    candidates_by_signature: dict[
        tuple[tuple[str, tuple[int, ...]], ...], AccessDrivenTailCandidateV1
    ] = {}
    candidate_order: dict[tuple[tuple[str, tuple[int, ...]], ...], tuple[Any, ...]] = {}
    target_portal_event_signatures: set[tuple[str, tuple[int, int], str]] = set()
    candidate_before_site_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    candidate_geometry_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    after_truck_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    after_fixed_zone_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    after_reserved_corridor_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    truck_clear_corridor_candidate_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    truck_clear_corridor_event_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    sort_left, sort_bottom, sort_right, sort_top = sorting.bounds_mm
    for shape in shapes:
        _width, _depth, _rotation, x_span, y_span = shape
        base = _local_rectangle_at("frozen_fruit_room", shape, 0, 0)
        base_portals = tuple(provider(requirement, "frozen_fruit_room", base).get("portals", ()))
        if not base_portals:
            continue
        for target_portal_option in base_portals:
            side = str(target_portal_option["side"])
            if side in {"EAST", "WEST"}:
                normal_axis, tangent_axis, tangent_index = "X", "Y", 1
                portal_offset = target_portal_option["center_mm"][tangent_index]
                tangent_span = y_span
            else:
                normal_axis, tangent_axis, tangent_index = "Y", "X", 0
                portal_offset = target_portal_option["center_mm"][tangent_index]
                tangent_span = x_span

            if side == "EAST":
                sorting_normal_origin = sort_left - corridor_width_mm - x_span
            elif side == "WEST":
                sorting_normal_origin = sort_right + corridor_width_mm
            elif side == "NORTH":
                sorting_normal_origin = sort_bottom - corridor_width_mm - y_span
            else:
                sorting_normal_origin = sort_top + corridor_width_mm
            # The target room remains exactly one authoritative corridor
            # width from the relevant sorting face. Other site events shape
            # the tangential placement and route detours; they do not move the
            # Frozen room arbitrarily farther away from its endpoint.
            normal_span = x_span if normal_axis == "X" else y_span
            normal_origins: dict[int, tuple[str, str, int]] = {
                sorting_normal_origin: (
                    "SORTING_EDGE",
                    f"SORTING_{normal_axis}_{side}",
                    event_priorities["SORTING_PORTAL"],
                )
            }
            target_face_is_high = side in {"EAST", "NORTH"}
            for coordinate, (kind, name, priority) in sorted(physical_events[normal_axis].items()):
                offsets = {0}
                if kind in {
                    "TRUCK_ENVELOPE",
                    "OBSTACLE",
                    "RESERVED_ACCESS_CORRIDOR",
                    "FIXED_ZONE",
                }:
                    offsets.update((half_corridor + GRID_MM, -half_corridor - GRID_MM))
                for event_coordinate in (coordinate + offset for offset in offsets):
                    origin = (
                        event_coordinate - normal_span if target_face_is_high else event_coordinate
                    )
                    proposed = (kind, name, priority)
                    current = normal_origins.get(origin)
                    if current is None or proposed < current:
                        normal_origins[origin] = proposed

            tangent_origins: dict[int, tuple[str, str, int]] = {}
            for coordinate, (kind, name, priority) in sorted(physical_events[tangent_axis].items()):
                offsets = {0}
                if kind in {
                    "TRUCK_ENVELOPE",
                    "OBSTACLE",
                    "RESERVED_ACCESS_CORRIDOR",
                    "FIXED_ZONE",
                }:
                    offsets.update(
                        (
                            half_corridor + GRID_MM,
                            -half_corridor - GRID_MM,
                        )
                    )
                for event_coordinate in (coordinate + offset for offset in offsets):
                    # Align the actual target portal or one room edge with
                    # an authoritative event. The exact route authority later
                    # decides whether the resulting channel is usable.
                    for origin in (
                        event_coordinate,
                        event_coordinate - portal_offset,
                        event_coordinate - tangent_span,
                    ):
                        proposed = (kind, name, priority)
                        current = tangent_origins.get(origin)
                        if current is None or proposed < current:
                            tangent_origins[origin] = proposed
            for source_index, source_portal in enumerate(sorting_portals, start=1):
                source_center = source_portal["center_mm"]
                source_tangent = source_center[1 if tangent_axis == "Y" else 0]
                origin = source_tangent - portal_offset
                tangent_origins[origin] = (
                    "SORTING_PORTAL",
                    f"SORTING_PORTAL-{source_index:02d}-{source_portal['side']}",
                    event_priorities["SORTING_PORTAL"],
                )

            for tangent_origin, (tangent_kind, tangent_name, tangent_priority) in sorted(
                tangent_origins.items()
            ):
                for normal_origin, (normal_kind, normal_name, normal_priority) in sorted(
                    normal_origins.items()
                ):
                    if normal_axis == "X":
                        x_mm, y_mm = normal_origin, tangent_origin
                    else:
                        x_mm, y_mm = tangent_origin, normal_origin
                    rectangle = _local_rectangle_at("frozen_fruit_room", shape, x_mm, y_mm)
                    left, bottom, right, top = rectangle.bounds_mm
                    separated_from_sorting = (
                        right <= sort_left - corridor_width_mm
                        if side == "EAST"
                        else left >= sort_right + corridor_width_mm
                        if side == "WEST"
                        else top <= sort_bottom - corridor_width_mm
                        if side == "NORTH"
                        else bottom >= sort_top + corridor_width_mm
                    )
                    if not separated_from_sorting:
                        continue
                    signature = _module_signature({"frozen_fruit_room": rectangle})
                    actual_target_portals = tuple(
                        {
                            **portal,
                            "center_mm": (
                                portal["center_mm"][0] + x_mm,
                                portal["center_mm"][1] + y_mm,
                            ),
                            "segment_mm": tuple(
                                (point[0] + x_mm, point[1] + y_mm) for point in portal["segment_mm"]
                            ),
                        }
                        for portal in base_portals
                        if portal["side"] == side
                    )
                    if not actual_target_portals:
                        continue
                    target_portal_event_signatures.update(
                        (row["side"], row["center_mm"], row["edge_class"])
                        for row in actual_target_portals
                    )
                    candidate_before_site_signatures.add(signature)
                    if not _rectangle_is_usable(
                        rectangle,
                        {},
                        context.boundary,
                        context.boundary_bounds,
                        context.obstacles,
                    ):
                        continue
                    candidate_geometry_signatures.add(signature)
                    overlap_with_truck = any(
                        rectangle_intersects_closed_obstacle(rectangle, envelope)
                        for envelope in truck_envelopes
                    )
                    if overlap_with_truck:
                        continue
                    after_truck_signatures.add(signature)
                    if any(
                        rectangles_overlap(rectangle, other)
                        for other in fixed.values()
                        if other is not sorting
                    ):
                        continue
                    after_fixed_zone_signatures.add(signature)
                    if any(
                        _orthogonal_polygons_interiors_overlap(rectangle.polygon_mm, reserved)
                        for reserved in reserved_corridors
                    ):
                        continue
                    after_reserved_corridor_signatures.add(signature)
                    source_side_toward_target = {
                        "EAST": "WEST",
                        "WEST": "EAST",
                        "NORTH": "SOUTH",
                        "SOUTH": "NORTH",
                    }[side]
                    portal_route_specs: list[tuple[int, int, int, int, int, int]] = []
                    for target_index, candidate_target_portal in enumerate(
                        actual_target_portals, start=1
                    ):
                        target_center = tuple(candidate_target_portal["center_mm"])
                        for source_index, source_portal in enumerate(sorting_portals, start=1):
                            source_center = tuple(source_portal["center_mm"])
                            delta_x = target_center[0] - source_center[0]
                            delta_y = target_center[1] - source_center[1]
                            length_lower_bound = abs(delta_x) + abs(delta_y)
                            facing_mismatch = int(
                                source_portal["side"] != source_side_toward_target
                            )
                            portal_route_specs.append(
                                (
                                    facing_mismatch,
                                    length_lower_bound,
                                    int(delta_x != 0 and delta_y != 0),
                                    source_index,
                                    target_index,
                                    int(delta_x == 0 or delta_y == 0),
                                )
                            )
                    if not portal_route_specs:
                        continue
                    ordered_route_specs = sorted(portal_route_specs)
                    selected_route_order: tuple[int, int, int, int, int, int, int] | None = None
                    clear_centerline: tuple[tuple[int, int], ...] = ()
                    for (
                        facing_mismatch,
                        route_length_lower_bound,
                        _route_turn_lower_bound,
                        source_index,
                        target_index,
                        _aligned,
                    ) in ordered_route_specs:
                        if facing_mismatch:
                            continue
                        source_center = cast(
                            tuple[int, int],
                            tuple(sorting_portals[source_index - 1]["center_mm"]),
                        )
                        target_center = cast(
                            tuple[int, int],
                            tuple(actual_target_portals[target_index - 1]["center_mm"]),
                        )
                        route_paths = _portal_normal_centerlines(
                            source_center,
                            target_center,
                            source_side=str(sorting_portals[source_index - 1]["side"]),
                            target_side=str(actual_target_portals[target_index - 1]["side"]),
                            corridor_width_mm=corridor_width_mm,
                        )
                        clear_path_candidates = [
                            path
                            for path in route_paths
                            if _truck_clear_corridor_path(
                                context,
                                path,
                                corridor_width_mm,
                                fixed,
                                truck_envelopes,
                                reserved_corridors,
                            )
                        ]
                        if clear_path_candidates:
                            clear_centerline = min(
                                clear_path_candidates, key=lambda path: (len(path), path)
                            )
                            selected_route_order = (
                                0,
                                facing_mismatch,
                                route_length_lower_bound,
                                len(clear_centerline) - 2,
                                source_index,
                                target_index,
                                0,
                            )
                            break
                    if selected_route_order is None:
                        (
                            facing_mismatch,
                            route_length_lower_bound,
                            route_turn_lower_bound,
                            source_index,
                            target_index,
                            _aligned,
                        ) = ordered_route_specs[0]
                        selected_route_order = (
                            1,
                            facing_mismatch,
                            route_length_lower_bound,
                            route_turn_lower_bound,
                            source_index,
                            target_index,
                            1,
                        )
                    (
                        clear_path_order,
                        facing_mismatch,
                        route_length_lower_bound,
                        turn_lower_bound,
                        source_index,
                        target_index,
                        _path_tie_break,
                    ) = selected_route_order
                    target_portal = actual_target_portals[target_index - 1]
                    truck_clear_corridor_candidate_signatures.add(signature)
                    source_center = cast(
                        tuple[int, int], tuple(sorting_portals[source_index - 1]["center_mm"])
                    )
                    target_center = cast(tuple[int, int], tuple(target_portal["center_mm"]))
                    corridor_centerline = clear_centerline
                    corridor_envelopes: tuple[PolygonMM, ...] = ()
                    if clear_path_order == 0 and clear_centerline:
                        corridor_rectangles = _corridor_rectangles_for_centerline(
                            clear_centerline, corridor_width_mm
                        )
                        if corridor_rectangles:
                            corridor_envelopes = tuple(
                                rectangle.polygon_mm for rectangle in corridor_rectangles
                            )
                            truck_clear_corridor_event_signatures.add(signature)
                    event_source = (
                        f"SORTING_PORTAL-{source_index:02d}-"
                        f"{sorting_portals[source_index - 1]['side']}"
                        f"|NORMAL:{normal_kind}:{normal_name}"
                        f"|TANGENT:{tangent_kind}:{tangent_name}"
                        f"|TARGET_PORTAL:{side}:{target_portal['edge_class']}"
                        "|CORRIDOR_EVENT:ENDPOINT_PAIR"
                    )
                    metadata = replace(
                        _access_candidate(
                            "FROZEN_SUPPORT_MODULE",
                            "frozen_fruit_room",
                            rectangle,
                            _tail_requirement_ids(
                                context,
                                frozenset({("sorting_packaging_room", "frozen_fruit_room")}),
                            ),
                            anchor_source=event_source,
                            endpoint_event_class="FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED",
                            direct_shared_edge_possible=False,
                        ),
                        construction_corridor_centerline_mm=corridor_centerline,
                        construction_corridor_envelopes_mm=corridor_envelopes,
                        construction_order_key=(
                            clear_path_order,
                            facing_mismatch,
                            route_length_lower_bound,
                            turn_lower_bound,
                            normal_priority,
                            tangent_priority,
                            x_span * y_span,
                            abs(x_span - y_span),
                            x_mm,
                            y_mm,
                            rectangle.rotation_deg,
                        ),
                        construction_portal_pair_mm=(source_center, target_center),
                    )
                    order_key = (*metadata.construction_order_key, side, rectangle.bounds_mm)
                    if signature not in candidate_order or order_key < candidate_order[signature]:
                        candidates_by_signature[signature] = metadata
                        candidate_order[signature] = order_key

    if stats is not None and main_identity is not None:
        if stats.frozen_sorting_portal_event_count_by_main is None:
            stats.frozen_sorting_portal_event_count_by_main = {}
        if stats.frozen_target_portal_event_count_by_main is None:
            stats.frozen_target_portal_event_count_by_main = {}
        stats.frozen_sorting_portal_event_count_by_main[main_identity] = len(sorting_portals)
        stats.frozen_target_portal_event_count_by_main[main_identity] = len(
            target_portal_event_signatures
        )
        if stats.frozen_route_constructive_seed_count_by_main is None:
            stats.frozen_route_constructive_seed_count_by_main = {}
        stats.frozen_route_constructive_seed_count_by_main[main_identity] = len(
            truck_clear_corridor_candidate_signatures
        )
        if stats.frozen_truck_clear_corridor_candidate_event_count_by_main is None:
            stats.frozen_truck_clear_corridor_candidate_event_count_by_main = {}
        stats.frozen_truck_clear_corridor_candidate_event_count_by_main[main_identity] = len(
            truck_clear_corridor_event_signatures
        )
        if stats.frozen_candidate_rejection_taxonomy_by_main is None:
            stats.frozen_candidate_rejection_taxonomy_by_main = {}
        if not truck_clear_corridor_event_signatures:
            taxonomy = stats.frozen_candidate_rejection_taxonomy_by_main.setdefault(
                main_identity, {}
            )
            taxonomy["NO_TRUCK_CLEAR_CORRIDOR_EVENT"] = (
                taxonomy.get("NO_TRUCK_CLEAR_CORRIDOR_EVENT", 0) + 1
            )
        if stats.frozen_candidate_counts_by_main is None:
            stats.frozen_candidate_counts_by_main = {}
        stats.frozen_candidate_counts_by_main[main_identity] = {
            "before_truck_filter": len(candidate_geometry_signatures),
            "after_truck_filter": len(after_truck_signatures),
            "after_fixed_zone_filter": len(after_fixed_zone_signatures),
            "after_reserved_corridor_filter": len(after_reserved_corridor_signatures),
        }
        if stats.frozen_candidate_rejection_taxonomy_by_main is None:
            stats.frozen_candidate_rejection_taxonomy_by_main = {}
        taxonomy = stats.frozen_candidate_rejection_taxonomy_by_main.setdefault(main_identity, {})
        for category, count in (
            (
                "FROZEN_SITE_INVALID",
                len(candidate_before_site_signatures) - len(candidate_geometry_signatures),
            ),
            (
                "FROZEN_OVERLAPS_TRUCK_ENVELOPE",
                direct_truck_rejection_count
                + len(candidate_geometry_signatures)
                - len(after_truck_signatures),
            ),
            (
                "FROZEN_OVERLAPS_FIXED_ZONE",
                len(after_truck_signatures) - len(after_fixed_zone_signatures),
            ),
            (
                "FROZEN_OVERLAPS_RESERVED_ACCESS_CORRIDOR",
                len(after_fixed_zone_signatures) - len(after_reserved_corridor_signatures),
            ),
        ):
            if count > 0:
                taxonomy[category] = taxonomy.get(category, 0) + count
        if not target_portal_event_signatures:
            taxonomy["NO_TARGET_PORTAL_EVENT"] = taxonomy.get("NO_TARGET_PORTAL_EVENT", 0) + 1

    boundary_xs = {point[0] for point in context.boundary}
    boundary_ys = {point[1] for point in context.boundary}
    rectangular_boundary = (
        len(context.boundary) == 4
        and len(boundary_xs) == 2
        and len(boundary_ys) == 2
        and set(context.boundary)
        == {(left, bottom) for left in boundary_xs for bottom in boundary_ys}
    )
    boundary_left, boundary_bottom, boundary_right, boundary_top = context.boundary_bounds
    accepted: dict[tuple[tuple[str, tuple[int, ...]], ...], AccessDrivenTailCandidateV1] = {}
    for signature in sorted(candidates_by_signature, key=lambda key: candidate_order[key]):
        candidate = candidates_by_signature[signature]
        placements = candidate.as_placements()
        rectangle = placements["frozen_fruit_room"]
        left, bottom, right, top = rectangle.bounds_mm
        inside_rectangular_site = (
            boundary_left <= left
            and boundary_bottom <= bottom
            and right <= boundary_right
            and top <= boundary_top
        )
        usable = (
            inside_rectangular_site
            and not any(
                rectangle_intersects_closed_obstacle(rectangle, obstacle)
                for obstacle in context.obstacles
            )
            if rectangular_boundary
            else _rectangle_is_usable(
                rectangle, {}, context.boundary, context.boundary_bounds, context.obstacles
            )
        )
        if not usable:
            if stats is not None and main_identity is not None:
                taxonomy = (stats.frozen_candidate_rejection_taxonomy_by_main or {}).setdefault(
                    main_identity, {}
                )
                taxonomy["FROZEN_SITE_INVALID"] = taxonomy.get("FROZEN_SITE_INVALID", 0) + 1
            continue
        accepted[signature] = candidate

    if stats is not None and main_identity is not None:
        if stats.frozen_route_constructive_seed_count_by_main is None:
            stats.frozen_route_constructive_seed_count_by_main = {}
        stats.frozen_route_constructive_seed_count_by_main[main_identity] = len(accepted)
        if stats.frozen_constructive_candidate_witness_by_main is None:
            stats.frozen_constructive_candidate_witness_by_main = {}
        stats.frozen_constructive_candidate_witness_by_main[main_identity] = [
            {
                "frozen_bounds_mm": list(candidate.as_placements()["frozen_fruit_room"].bounds_mm),
                "endpoint_event_class": candidate.endpoint_event_class,
                "anchor_source": candidate.anchor_source,
                "construction_order_key": list(candidate.construction_order_key),
                "centerline_mm": [
                    list(point) for point in candidate.construction_corridor_centerline_mm
                ],
                "corridor_envelopes_mm": [
                    [list(point) for point in polygon]
                    for polygon in candidate.construction_corridor_envelopes_mm
                ],
                "portal_event_pair_mm": (
                    [list(point) for point in candidate.construction_portal_pair_mm]
                    if candidate.construction_portal_pair_mm is not None
                    else None
                ),
                "status": "CONSTRUCTION_CLEAR_PENDING_OFFICIAL_ROUTE",
            }
            for candidate in sorted(accepted.values(), key=lambda row: row.construction_order_key)[
                :12
            ]
        ]
    return tuple(accepted[key] for key in sorted(accepted, key=lambda key: candidate_order[key]))


def _access_tail_dimension_shapes(
    context: _PlacementSearchContext,
    zone_code: str,
    fixed: Mapping[str, PlacedRectangleV1],
) -> tuple[tuple[int, int, int, int, int], ...]:
    """Use P2C's complete dimension authority for flexible access-tail zones."""
    authority = context.authorities.get(zone_code)
    if authority is None:
        return ()
    if zone_code != "changing_room" or _authority_mode(authority) != "FLEXIBLE_RECTANGLE":
        return _local_dimension_shapes(context, zone_code)

    # `_unique_dimensions` is the P2C flexible-rectangle authority: it derives
    # finite 1 mm-grid candidates from required area, boundary spans, and the
    # already placed geometry.  Do not replace it with the structured
    # generator's near-square-only estimates.
    dimensions = _unique_dimensions(authority, fixed, context.boundary)
    by_world_footprint: dict[tuple[int, int], tuple[int, int, int, int, int]] = {}
    for width_mm, depth_mm in dimensions:
        for rotation in (0, 90):
            x_span, y_span = (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
            representative = (width_mm, depth_mm, rotation, x_span, y_span)
            footprint = (x_span, y_span)
            current = by_world_footprint.get(footprint)
            if current is None or representative[:3] < current[:3]:
                by_world_footprint[footprint] = representative
    return tuple(
        sorted(
            by_world_footprint.values(),
            key=lambda shape: (
                shape[3] * shape[4],
                Fraction(max(shape[3], shape[4]), min(shape[3], shape[4])),
                max(shape[3], shape[4]),
                min(shape[3], shape[4]),
                shape[3],
                shape[4],
                shape[:3],
            ),
        )
    )


def _access_tail_authority_shape_signatures(
    context: _PlacementSearchContext,
    zone_code: str,
    fixed: Mapping[str, PlacedRectangleV1],
) -> tuple[tuple[int, int, int], ...]:
    authority = context.authorities.get(zone_code)
    if authority is None:
        return ()
    if zone_code != "changing_room" or _authority_mode(authority) != "FLEXIBLE_RECTANGLE":
        return tuple(
            (width_mm, depth_mm, rotation)
            for width_mm, depth_mm, rotation in _dimension_variants(
                authority, fixed, context.boundary
            )
        )
    return tuple(
        sorted(
            (width_mm, depth_mm, rotation)
            for width_mm, depth_mm in _unique_dimensions(authority, fixed, context.boundary)
            for rotation in (0, 90)
        )
    )


def _shared_edge_length_mm(left: PlacedRectangleV1, right: PlacedRectangleV1) -> int:
    left_x0, left_y0, left_x1, left_y1 = left.bounds_mm
    right_x0, right_y0, right_x1, right_y1 = right.bounds_mm
    if left_x1 == right_x0 or right_x1 == left_x0:
        return max(0, min(left_y1, right_y1) - max(left_y0, right_y0))
    if left_y1 == right_y0 or right_y1 == left_y0:
        return max(0, min(left_x1, right_x1) - max(left_x0, right_x0))
    return 0


def _sorting_shared_interval_mm(
    sorting: PlacedRectangleV1, candidate: PlacedRectangleV1
) -> tuple[str, int, int] | None:
    sort_left, sort_bottom, sort_right, sort_top = sorting.bounds_mm
    left, bottom, right, top = candidate.bounds_mm
    if right == sort_left:
        side, low, high = "WEST", max(bottom, sort_bottom), min(top, sort_top)
    elif left == sort_right:
        side, low, high = "EAST", max(bottom, sort_bottom), min(top, sort_top)
    elif top == sort_bottom:
        side, low, high = "SOUTH", max(left, sort_left), min(right, sort_right)
    elif bottom == sort_top:
        side, low, high = "NORTH", max(left, sort_left), min(right, sort_right)
    else:
        return None
    return (side, low, high) if low < high else None


def _entrance_shared_length_mm(rectangle: PlacedRectangleV1, entrance: SegmentMM) -> int:
    left, bottom, right, top = rectangle.bounds_mm
    (x0, y0), (x1, y1) = entrance
    if x0 == x1 and (left == x0 or right == x0):
        return max(0, min(top, max(y0, y1)) - max(bottom, min(y0, y1)))
    if y0 == y1 and (bottom == y0 or top == y0):
        return max(0, min(right, max(x0, x1)) - max(left, min(x0, x1)))
    return 0


def _access_driven_tail_candidates(
    context: _PlacementSearchContext,
    module_name: str,
    zone_code: str,
    fixed: Mapping[str, PlacedRectangleV1],
    bays: Sequence[BuildableBayV1],
    *,
    stats: _PlacementSearchStats | None = None,
    main_identity: str | None = None,
    truck_envelopes: Sequence[PolygonMM] = (),
    reserved_corridors: Sequence[PolygonMM] = (),
) -> tuple[AccessDrivenTailCandidateV1, ...]:
    """Build finite S2 seeds from the module's frozen route endpoints.

    Event coordinates come only from authoritative room dimensions, endpoint
    edges, entrance endpoints, buildable-bay boundaries and the 2.0/2.5 m
    clearance offsets. Exact route feasibility remains the injected authority.
    """
    sorting = fixed.get("sorting_packaging_room")
    if sorting is None:
        return ()
    if zone_code == "changing_room":
        pairs = frozenset(
            {
                ("main_entrance", "changing_room"),
                ("changing_room", "sorting_packaging_room"),
            }
        )
        module_clearance_mm = 2_000
        module_name = "CHANGING_MODULE"
    elif zone_code == "secondary_fruit_buffer":
        pairs = frozenset({("sorting_packaging_room", "secondary_fruit_buffer")})
        module_clearance_mm = 2_500
        module_name = "SECONDARY_SUPPORT_MODULE"
    elif zone_code == "frozen_fruit_room":
        pairs = frozenset({("sorting_packaging_room", "frozen_fruit_room")})
        module_clearance_mm = 2_500
        module_name = "FROZEN_SUPPORT_MODULE"
    else:
        return ()
    requirement_ids = _tail_requirement_ids(context, pairs)
    if zone_code == "frozen_fruit_room" and truck_envelopes:
        return _frozen_truck_clear_corridor_candidates(
            context,
            fixed,
            bays,
            truck_envelopes,
            stats=stats,
            main_identity=main_identity,
            reserved_corridors=reserved_corridors,
        )
    seeds: dict[tuple[tuple[str, tuple[int, ...]], ...], AccessDrivenTailCandidateV1] = {}
    shapes = _access_tail_dimension_shapes(context, zone_code, fixed)
    alignments = ("LOW", "CENTER", "HIGH")
    (entrance_start, entrance_end) = context.main_entrance
    entrance_low, entrance_high = sorted(
        (entrance_start[1], entrance_end[1])
        if entrance_start[0] == entrance_end[0]
        else (entrance_start[0], entrance_end[0])
    )
    sort_left, sort_bottom, sort_right, sort_top = sorting.bounds_mm
    sorting_center = ((sort_left + sort_right) // 2, (sort_bottom + sort_top) // 2)

    def add(
        rectangle: PlacedRectangleV1,
        *,
        source: str,
        event_class: str,
    ) -> None:
        module = {zone_code: rectangle}
        if not _site_module_is_usable(context, module, fixed):
            return
        signature = _module_signature(module)
        seeds.setdefault(
            signature,
            _access_candidate(
                module_name,
                zone_code,
                rectangle,
                requirement_ids,
                anchor_source=source,
                endpoint_event_class=event_class,
                direct_shared_edge_possible=(
                    _adjacent_side(sorting, rectangle) is not None
                    or (
                        zone_code == "changing_room"
                        and _rectangle_shares_entrance_boundary(rectangle, context.main_entrance)
                    )
                ),
            ),
        )

    if zone_code == "changing_room":
        # A boundary entrance is not a room endpoint: P2D starts from its
        # corridor-width interior point and routes to a portal on changing.
        # Build only exact, collinear endpoint events with sorting on one side;
        # the injected official router still decides whether that corridor is
        # clear through all current zones, obstacles, and reservations.
        minimum_portal_mm = 1_500
        entrance_is_vertical = entrance_start[0] == entrance_end[0]
        entrance_route_starts = getattr(context, "main_entrance_route_start_points", ())
        x_events = {point[0] for point in context.boundary}
        y_events = {point[1] for point in context.boundary}
        x_events.update((sort_left, sort_right))
        y_events.update((sort_bottom, sort_top))
        for bay in bays:
            bay_left, bay_bottom, bay_right, bay_top = bay.bounds_mm
            x_events.update((bay_left, bay_right))
            y_events.update((bay_bottom, bay_top))
        for obstacle in context.obstacles:
            obstacle_left, obstacle_bottom, obstacle_right, obstacle_top = _boundary_extents(
                obstacle
            )
            x_events.update((obstacle_left, obstacle_right))
            y_events.update((obstacle_bottom, obstacle_top))
        for start_x, start_y in entrance_route_starts:
            x_events.add(start_x)
            y_events.add(start_y)

        def axis_origin_events(events: set[int], span: int) -> tuple[int, ...]:
            return tuple(
                sorted(
                    {
                        origin
                        for event in events
                        for origin in (event, event - span, event - span // 2)
                    }
                )
            )

        for shape in shapes:
            _width, _depth, _rotation, x_span, y_span = shape
            for start_x, start_y in entrance_route_starts:
                for side in ("WEST", "EAST", "SOUTH", "NORTH"):
                    if side in {"WEST", "EAST"}:
                        x_mm, _ = _local_adjacent_origin(sorting, x_span, y_span, side, "CENTER")
                        y_origins = set(axis_origin_events(y_events, y_span))
                        y_origins.update(
                            {
                                sort_bottom,
                                sort_top - y_span,
                                sort_bottom + (sort_top - sort_bottom - y_span) // 2,
                                start_y - y_span // 2,
                                start_y - y_span + minimum_portal_mm,
                                start_y - minimum_portal_mm,
                            }
                        )
                        origins = ((x_mm, y_mm) for y_mm in sorted(y_origins))
                    else:
                        _, y_mm = _local_adjacent_origin(sorting, x_span, y_span, side, "CENTER")
                        x_origins = set(axis_origin_events(x_events, x_span))
                        x_origins.update(
                            {
                                sort_left,
                                sort_right - x_span,
                                sort_left + (sort_right - sort_left - x_span) // 2,
                                start_x - x_span // 2,
                                start_x - x_span + minimum_portal_mm,
                                start_x - minimum_portal_mm,
                            }
                        )
                        origins = ((x_mm, y_mm) for x_mm in sorted(x_origins))
                    for x_mm, y_mm in origins:
                        rectangle = _local_rectangle_at(zone_code, shape, x_mm, y_mm)
                        interval = _sorting_shared_interval_mm(sorting, rectangle)
                        if interval is None or interval[2] - interval[1] < minimum_portal_mm:
                            continue
                        left, bottom, right, top = rectangle.bounds_mm
                        if entrance_is_vertical:
                            portal_aligned = (
                                bottom + minimum_portal_mm // 2
                                <= start_y
                                <= top - minimum_portal_mm // 2
                            ) and (start_x < left or start_x > right)
                        else:
                            portal_aligned = (
                                left + minimum_portal_mm // 2
                                <= start_x
                                <= right - minimum_portal_mm // 2
                            ) and (start_y < bottom or start_y > top)
                        if not portal_aligned:
                            continue
                        add(
                            rectangle,
                            source="MAIN_ENTRANCE_INTERIOR_PORTAL_AND_SORTING_EDGE_EVENTS",
                            event_class="ENTRANCE_CORRIDOR_COMPATIBLE_SORTING_DIRECT",
                        )

        # Exact dual-endpoint construction: one changing-room edge lies on
        # the entrance segment and another shares a portal-capable sorting
        # edge.  Origins are endpoint/edge events only; no interpolated or
        # arbitrary site coordinates are introduced.
        entrance_axis = entrance_start[0] if entrance_is_vertical else entrance_start[1]
        entrance_low, entrance_high = sorted(
            (entrance_start[1], entrance_end[1])
            if entrance_is_vertical
            else (entrance_start[0], entrance_end[0])
        )
        for shape in shapes:
            _width, _depth, _rotation, x_span, y_span = shape
            if entrance_is_vertical:
                fixed_x_origins = (entrance_axis - x_span, entrance_axis)
                sorting_edge_y_origins = {
                    sort_bottom,
                    sort_top - y_span,
                    sort_bottom + (sort_top - sort_bottom - y_span) // 2,
                    sort_bottom - y_span,
                    sort_top,
                    entrance_low,
                    entrance_high - y_span,
                }
                origins = (
                    (x_mm, y_mm)
                    for x_mm in fixed_x_origins
                    for y_mm in sorted(sorting_edge_y_origins)
                )
            else:
                fixed_y_origins = (entrance_axis - y_span, entrance_axis)
                sorting_edge_x_origins = {
                    sort_left,
                    sort_right - x_span,
                    sort_left + (sort_right - sort_left - x_span) // 2,
                    sort_left - x_span,
                    sort_right,
                    entrance_low,
                    entrance_high - x_span,
                }
                origins = (
                    (x_mm, y_mm)
                    for y_mm in fixed_y_origins
                    for x_mm in sorted(sorting_edge_x_origins)
                )
            for x_mm, y_mm in origins:
                rectangle = _local_rectangle_at(zone_code, shape, x_mm, y_mm)
                if (
                    _entrance_shared_length_mm(rectangle, context.main_entrance) < minimum_portal_mm
                    or _shared_edge_length_mm(sorting, rectangle) < minimum_portal_mm
                ):
                    continue
                add(
                    rectangle,
                    source="MAIN_ENTRANCE_AND_SORTING_PORTAL_EDGES",
                    event_class="ENTRANCE_SORTING_DUAL_DIRECT",
                )

    # Direct sorting-edge candidates are authoritative endpoint events, not
    # a new MUST relation. The exact route validator decides admission.
    for shape in shapes:
        x_span, y_span = shape[3], shape[4]
        for side in ("WEST", "EAST", "SOUTH", "NORTH"):
            for alignment in alignments:
                x_mm, y_mm = _local_adjacent_origin(sorting, x_span, y_span, side, alignment)
                add(
                    _local_rectangle_at(zone_code, shape, x_mm, y_mm),
                    source="SORTING_EDGE",
                    event_class="SORTING_DIRECT",
                )
            # Exact start/end alignment is retained as its own construction
            # class even when it coincides geometrically with LOW/HIGH.
            for alignment in ("LOW", "HIGH"):
                x_mm, y_mm = _local_adjacent_origin(sorting, x_span, y_span, side, alignment)
                add(
                    _local_rectangle_at(zone_code, shape, x_mm, y_mm),
                    source="SORTING_EDGE",
                    event_class=(
                        "SORTING_DIRECT_EDGE_START"
                        if alignment == "LOW"
                        else "SORTING_DIRECT_EDGE_END"
                    ),
                )

            # Clearance-width offsets are exact construction seeds. They do
            # not assert a route; route_access_requirement remains decisive.
            for alignment in alignments:
                x_mm, y_mm = _local_adjacent_origin(sorting, x_span, y_span, side, alignment)
                if side == "WEST":
                    x_mm -= module_clearance_mm
                elif side == "EAST":
                    x_mm += module_clearance_mm
                elif side == "SOUTH":
                    y_mm -= module_clearance_mm
                else:
                    y_mm += module_clearance_mm
                add(
                    _local_rectangle_at(zone_code, shape, x_mm, y_mm),
                    source="SORTING_EDGE_PLUS_AUTHORIZED_CLEARANCE_EVENT",
                    event_class="CORRIDOR_MEDIATED",
                )

        # Bay-edge mediated candidates reuse the sorting tangential event and
        # one real bay edge; no arbitrary site-coordinate sweep is introduced.
        for bay in bays:
            left, bottom, right, top = bay.bounds_mm
            for y_mm in sorted({bottom, top - y_span, sort_bottom, sort_top - y_span}):
                for x_mm in (left, right - x_span):
                    add(
                        _local_rectangle_at(zone_code, shape, x_mm, y_mm),
                        source=bay.bay_id,
                        event_class="SORTING_BAY_EDGE_MEDIATED",
                    )
        for obstacle_index, obstacle in enumerate(context.obstacles):
            obs_left = min(point[0] for point in obstacle)
            obs_bottom = min(point[1] for point in obstacle)
            obs_right = max(point[0] for point in obstacle)
            obs_top = max(point[1] for point in obstacle)
            obstacle_x_origins = (obs_left - x_span - GRID_MM, obs_right + GRID_MM)
            obstacle_y_origins = (obs_bottom - y_span - GRID_MM, obs_top + GRID_MM)
            sorting_y_origins = (
                sort_bottom,
                (sort_bottom + sort_top - y_span) // 2,
                sort_top - y_span,
            )
            for x_mm in obstacle_x_origins:
                for y_mm in sorting_y_origins:
                    add(
                        _local_rectangle_at(zone_code, shape, x_mm, y_mm),
                        source=f"OBSTACLE-{obstacle_index + 1}",
                        event_class="SORTING_OBSTACLE_EDGE_MEDIATED",
                    )
            sorting_x_origins = (
                sort_left,
                (sort_left + sort_right - x_span) // 2,
                sort_right - x_span,
            )
            for y_mm in obstacle_y_origins:
                for x_mm in sorting_x_origins:
                    add(
                        _local_rectangle_at(zone_code, shape, x_mm, y_mm),
                        source=f"OBSTACLE-{obstacle_index + 1}",
                        event_class="SORTING_OBSTACLE_EDGE_MEDIATED",
                    )
        for bay in bays:
            left, bottom, right, top = bay.bounds_mm
            for x_mm in sorted({left, right - x_span, sort_left, sort_right - x_span}):
                for y_mm in (bottom, top - y_span):
                    add(
                        _local_rectangle_at(zone_code, shape, x_mm, y_mm),
                        source=bay.bay_id,
                        event_class="SORTING_BAY_EDGE_MEDIATED",
                    )

    if zone_code == "frozen_fruit_room":
        for candidate in _frozen_truck_clear_corridor_candidates(
            context,
            fixed,
            bays,
            truck_envelopes,
            stats=stats,
            main_identity=main_identity,
            reserved_corridors=reserved_corridors,
        ):
            signature = _module_signature(candidate.as_placements())
            current = seeds.get(signature)
            if (
                current is None
                or current.endpoint_event_class != "FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED"
            ):
                seeds[signature] = candidate

    if zone_code == "changing_room":
        # Entrance-direct placements use the actual entrance segment and
        # legal room projection, independently of office geometry.
        entrance_x = entrance_start[0]
        for shape in shapes:
            _width, _depth, _rotation, x_span, y_span = shape
            if entrance_x == entrance_end[0]:
                for x_mm in (entrance_x, entrance_x - x_span):
                    for alignment in alignments:
                        y_mm = (
                            entrance_low
                            if alignment == "LOW"
                            else entrance_high - y_span
                            if alignment == "HIGH"
                            else entrance_low + (entrance_high - entrance_low - y_span) // 2
                        )
                        add(
                            _local_rectangle_at(zone_code, shape, x_mm, y_mm),
                            source="MAIN_ENTRANCE_SEGMENT",
                            event_class="ENTRANCE_DIRECT",
                        )
            else:
                entrance_y = entrance_start[1]
                for y_mm in (entrance_y, entrance_y - y_span):
                    for alignment in alignments:
                        x_mm = (
                            entrance_low
                            if alignment == "LOW"
                            else entrance_high - x_span
                            if alignment == "HIGH"
                            else entrance_low + (entrance_high - entrance_low - x_span) // 2
                        )
                        add(
                            _local_rectangle_at(zone_code, shape, x_mm, y_mm),
                            source="MAIN_ENTRANCE_SEGMENT",
                            event_class="ENTRANCE_DIRECT",
                        )

            # Bridge centers are exact rational interpolants of the two
            # endpoint events, rounded down to the existing integer-mm grid.
            entrance_point = (
                (entrance_start[0] + entrance_end[0]) // 2,
                (entrance_start[1] + entrance_end[1]) // 2,
            )
            for numerator in (1, 2, 3):
                center_x = (
                    entrance_point[0] * (4 - numerator) + sorting_center[0] * numerator
                ) // 4
                center_y = (
                    entrance_point[1] * (4 - numerator) + sorting_center[1] * numerator
                ) // 4
                add(
                    _local_rectangle_at(
                        zone_code,
                        shape,
                        center_x - x_span // 2,
                        center_y - y_span // 2,
                    ),
                    source="MAIN_ENTRANCE_AND_SORTING_ENDPOINTS",
                    event_class="ENTRANCE_SORTING_BRIDGE",
                )

    def candidate_order_key(
        signature: tuple[tuple[str, tuple[int, ...]], ...],
    ) -> tuple[Any, ...]:
        candidate = seeds[signature]
        priority = {
            "FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED": 0,
            "ENTRANCE_CORRIDOR_COMPATIBLE_SORTING_DIRECT": 0,
            "ENTRANCE_DIRECT": 1,
            "SORTING_DIRECT": 2,
            "ENTRANCE_SORTING_DUAL_DIRECT": 3,
            "ENTRANCE_SORTING_BRIDGE": 4,
            "CORRIDOR_MEDIATED": 5,
            "SORTING_BAY_EDGE_MEDIATED": 6,
        }.get(candidate.endpoint_event_class, 7)

        rectangle = dict(candidate.placements)[zone_code]
        if candidate.endpoint_event_class == "FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED":
            return (
                priority,
                *candidate.construction_order_key,
                signature,
            )
        left, bottom, right, top = rectangle.bounds_mm
        x_span, y_span = right - left, top - bottom
        aspect_ratio = Fraction(max(x_span, y_span), min(x_span, y_span))
        area = x_span * y_span
        sorting_span = _shared_edge_length_mm(sorting, rectangle)
        entrance_distance = 0
        entrance_route_starts = getattr(context, "main_entrance_route_start_points", ())
        if entrance_route_starts:
            distances = []
            for start_x, start_y in entrance_route_starts:
                if context.main_entrance[0][0] == context.main_entrance[1][0]:
                    distances.append(min(abs(start_x - left), abs(start_x - right)))
                else:
                    distances.append(min(abs(start_y - bottom), abs(start_y - top)))
            entrance_distance = min(distances)
        portal_edge_span = max(x_span, y_span)
        return (
            priority,
            entrance_distance if priority == 0 else 0,
            -sorting_span,
            -portal_edge_span if priority == 0 else 0,
            area,
            aspect_ratio,
            x_span,
            y_span,
            signature,
        )

    return tuple(seeds[key] for key in sorted(seeds, key=candidate_order_key))


@dataclass(frozen=True)
class _TailModuleOption:
    placements: dict[str, PlacedRectangleV1]
    access_results: tuple[Mapping[str, Any], ...]


_S2_ACCESS_ENDPOINTS: Final = (
    ("main_entrance", "changing_room"),
    ("changing_room", "sorting_packaging_room"),
    ("sorting_packaging_room", "secondary_fruit_buffer"),
    ("sorting_packaging_room", "frozen_fruit_room"),
)
_S2_MODULE_ACCESS_PAIRS: Final = {
    "CHANGING_MODULE": frozenset(
        {
            ("main_entrance", "changing_room"),
            ("changing_room", "sorting_packaging_room"),
        }
    ),
    "SECONDARY_SUPPORT_MODULE": frozenset({("sorting_packaging_room", "secondary_fruit_buffer")}),
    "FROZEN_SUPPORT_MODULE": frozenset({("sorting_packaging_room", "frozen_fruit_room")}),
}

_S2_TAIL_MODULES: Final = (
    "CHANGING_MODULE",
    "SECONDARY_SUPPORT_MODULE",
    "FROZEN_SUPPORT_MODULE",
    "OFFICE_MODULE",
)


def _tail_access_capacity_round_reserve(node_budget: int) -> int:
    """Reserve one finite tail-capacity round without enlarging placement budget."""
    return min(
        max(0, node_budget // 3),
        len(_S2_TAIL_MODULES) * len(BASE_LAYOUT_FAMILIES),
    )


def _tail_access_main_is_s2_admissible(status: str) -> bool:
    """Only a proven tail-capacity witness may enter complete S2 assembly."""
    return status == "TAIL_ACCESS_CAPABLE_MAIN"


def _tail_access_main_identity(
    main_skeleton_hash: str | None,
    main: Mapping[str, PlacedRectangleV1],
) -> str:
    """Identify the full 8-zone critical assembly, not only its 7-zone hash."""
    return canonical_hash(
        {
            "main_process_skeleton_hash": main_skeleton_hash,
            "critical_assembly": _module_signature(main),
        }
    )


def _tail_access_capacity_preflight(
    context: _PlacementSearchContext,
    main_rows: Sequence[tuple[str, Mapping[str, PlacedRectangleV1]]],
    bays: Sequence[BuildableBayV1],
    stats: _PlacementSearchStats,
    *,
    node_limit: int | None = None,
) -> Iterator[dict[str, str] | _SearchQuantumYield]:
    """Give each truck-pass main a round-robin exact access-seed check."""
    domains: dict[tuple[str, str], tuple[dict[str, PlacedRectangleV1], ...]] = {}
    main_by_identity: dict[str, Mapping[str, PlacedRectangleV1]] = {}
    skeleton_hash_by_identity: dict[str, str] = {}
    truck_envelopes_by_identity: dict[str, tuple[PolygonMM, ...]] = {}
    cursors: dict[tuple[str, str], int] = {}
    found: dict[tuple[str, str], bool] = {}
    requirements = _tail_access_requirement_rows(context)
    if requirements is None:
        unresolved = {
            _tail_access_main_identity(skeleton_hash, main): "UNRESOLVED_COVERAGE"
            for skeleton_hash, main in main_rows
        }
        if stats.tail_access_capacity_status_by_main is None:
            stats.tail_access_capacity_status_by_main = {}
        stats.tail_access_capacity_status_by_main.update(unresolved)
        yield unresolved
        return

    for skeleton_hash, main in main_rows:
        main_identity = _tail_access_main_identity(skeleton_hash, main)
        main_by_identity[main_identity] = main
        skeleton_hash_by_identity[main_identity] = skeleton_hash
        fixed = dict(main)
        reserved_spaces = (stats.reserved_construction_space_by_critical_signature or {}).get(
            repr(_module_signature(fixed)), ()
        )
        truck_envelopes = (stats.reserved_truck_envelopes_by_critical_signature or {}).get(
            repr(_module_signature(fixed)), ()
        )
        truck_envelopes_by_identity[main_identity] = truck_envelopes
        changing_candidates = _access_driven_tail_candidates(
            context, "CHANGING_MODULE", "changing_room", fixed, bays
        )
        changing_authority = context.authorities.get("changing_room")
        if (
            changing_authority is not None
            and _authority_mode(changing_authority) == "FLEXIBLE_RECTANGLE"
        ):
            if stats.changing_flexible_shape_signatures is None:
                stats.changing_flexible_shape_signatures = set()
            stats.changing_flexible_shape_signatures.update(
                (min(shape[0], shape[1]), max(shape[0], shape[1]))
                for shape in _access_tail_dimension_shapes(context, "changing_room", fixed)
            )
            if stats.changing_authority_shape_signatures is None:
                stats.changing_authority_shape_signatures = set()
            stats.changing_authority_shape_signatures.update(
                _access_tail_authority_shape_signatures(context, "changing_room", fixed)
            )
            if stats.changing_construction_footprint_signatures is None:
                stats.changing_construction_footprint_signatures = set()
            stats.changing_construction_footprint_signatures.update(
                (shape[3], shape[4])
                for shape in _access_tail_dimension_shapes(context, "changing_room", fixed)
            )
            if stats.changing_extreme_aspect_shape_signatures is None:
                stats.changing_extreme_aspect_shape_signatures = set()
            stats.changing_extreme_aspect_shape_signatures.update(
                (shape[3], shape[4])
                for shape in _access_tail_dimension_shapes(context, "changing_room", fixed)
                if min(shape[3], shape[4]) > 0
                and Fraction(max(shape[3], shape[4]), min(shape[3], shape[4])) >= 10
            )
            if stats.changing_dual_endpoint_seed_signatures is None:
                stats.changing_dual_endpoint_seed_signatures = set()
            stats.changing_dual_endpoint_seed_signatures.update(
                _module_signature(candidate.as_placements())
                for candidate in changing_candidates
                if candidate.endpoint_event_class == "ENTRANCE_SORTING_DUAL_DIRECT"
            )
        secondary_candidates = _access_driven_tail_candidates(
            context,
            "SECONDARY_SUPPORT_MODULE",
            "secondary_fruit_buffer",
            fixed,
            bays,
        )
        cached_changing_corridors = {
            tuple(sorted(polygon)): polygon
            for (cached_main, cached_module, _signature), (_routes, polygons) in (
                stats.tail_access_capacity_route_cache or {}
            ).items()
            if cached_main == main_identity and cached_module == "CHANGING_MODULE"
            for polygon in polygons
        }
        frozen_candidates = _access_driven_tail_candidates(
            context,
            "FROZEN_SUPPORT_MODULE",
            "frozen_fruit_room",
            fixed,
            bays,
            stats=stats,
            main_identity=main_identity,
            truck_envelopes=truck_envelopes,
            reserved_corridors=tuple(
                cached_changing_corridors[key] for key in sorted(cached_changing_corridors)
            ),
        )
        module_options: dict[str, tuple[dict[str, PlacedRectangleV1], ...]] = {
            "CHANGING_MODULE": tuple(row.as_placements() for row in changing_candidates),
            "SECONDARY_SUPPORT_MODULE": tuple(row.as_placements() for row in secondary_candidates),
            "FROZEN_SUPPORT_MODULE": tuple(row.as_placements() for row in frozen_candidates),
            "OFFICE_MODULE": _office_site_module_candidates(context, fixed),
        }
        candidate_metadata_by_signature = {
            _module_signature(row.as_placements()): row
            for row in (*changing_candidates, *secondary_candidates, *frozen_candidates)
        }
        truck_filtered = {
            module_name: tuple(
                candidate
                for candidate in candidates
                if not any(
                    rectangle_intersects_closed_obstacle(rectangle, envelope)
                    for envelope in truck_envelopes
                    for rectangle in candidate.values()
                )
            )
            for module_name, candidates in module_options.items()
        }
        frozen_before_truck = len(module_options["FROZEN_SUPPORT_MODULE"])
        frozen_after_truck = len(truck_filtered["FROZEN_SUPPORT_MODULE"])
        if stats.frozen_candidate_counts_by_main is None:
            stats.frozen_candidate_counts_by_main = {}
        frozen_counts = stats.frozen_candidate_counts_by_main.setdefault(
            main_identity,
            {
                "before_truck_filter": 0,
                "after_truck_filter": 0,
                "after_fixed_zone_filter": 0,
                "after_reserved_corridor_filter": 0,
            },
        )
        frozen_counts.setdefault("before_truck_filter", frozen_before_truck)
        frozen_counts.setdefault("after_truck_filter", frozen_after_truck)
        if stats.frozen_candidate_rejection_taxonomy_by_main is None:
            stats.frozen_candidate_rejection_taxonomy_by_main = {}
        frozen_taxonomy = stats.frozen_candidate_rejection_taxonomy_by_main.setdefault(
            main_identity, {}
        )
        truck_room_rejections = frozen_before_truck - frozen_after_truck
        if truck_room_rejections:
            frozen_taxonomy["FROZEN_OVERLAPS_TRUCK_ENVELOPE"] = (
                frozen_taxonomy.get("FROZEN_OVERLAPS_TRUCK_ENVELOPE", 0) + truck_room_rejections
            )
        fixed_zone_filtered = {
            module_name: tuple(
                candidate
                for candidate in candidates
                if not any(
                    rectangles_overlap(rectangle, fixed_rectangle)
                    for rectangle in candidate.values()
                    for fixed_code, fixed_rectangle in fixed.items()
                    if fixed_code not in candidate
                )
            )
            for module_name, candidates in truck_filtered.items()
        }
        frozen_counts.setdefault(
            "after_fixed_zone_filter",
            len(fixed_zone_filtered["FROZEN_SUPPORT_MODULE"]),
        )
        fixed_zone_rejections = frozen_after_truck - frozen_counts["after_fixed_zone_filter"]
        if fixed_zone_rejections:
            frozen_taxonomy["FROZEN_OVERLAPS_FIXED_ZONE"] = (
                frozen_taxonomy.get("FROZEN_OVERLAPS_FIXED_ZONE", 0) + fixed_zone_rejections
            )

        def direct_seed_count(
            module_name: str,
            candidates: Sequence[dict[str, PlacedRectangleV1]],
            *,
            metadata_by_signature: Mapping[
                tuple[tuple[str, tuple[int, ...]], ...], AccessDrivenTailCandidateV1
            ] = candidate_metadata_by_signature,
        ) -> int:
            return sum(
                (metadata := metadata_by_signature.get(_module_signature(candidate))) is not None
                and metadata.module_name == module_name
                and metadata.endpoint_event_class.startswith("SORTING_DIRECT")
                for candidate in candidates
            )

        if stats.tail_direct_seed_counts_before_truck_filter_by_main is None:
            stats.tail_direct_seed_counts_before_truck_filter_by_main = {}
        if stats.tail_direct_seed_counts_after_truck_filter_by_main is None:
            stats.tail_direct_seed_counts_after_truck_filter_by_main = {}
        computed_direct_before = {
            module_name: direct_seed_count(module_name, module_options[module_name])
            for module_name in ("SECONDARY_SUPPORT_MODULE", "FROZEN_SUPPORT_MODULE")
        }
        computed_direct_after = {
            module_name: direct_seed_count(module_name, truck_filtered[module_name])
            for module_name in ("SECONDARY_SUPPORT_MODULE", "FROZEN_SUPPORT_MODULE")
        }
        prior_direct_before = stats.tail_direct_seed_counts_before_truck_filter_by_main.get(
            main_identity, {}
        )
        prior_direct_after = stats.tail_direct_seed_counts_after_truck_filter_by_main.get(
            main_identity, {}
        )
        computed_direct_before["FROZEN_SUPPORT_MODULE"] = prior_direct_before.get(
            "FROZEN_SUPPORT_MODULE", computed_direct_before["FROZEN_SUPPORT_MODULE"]
        )
        computed_direct_after["FROZEN_SUPPORT_MODULE"] = prior_direct_after.get(
            "FROZEN_SUPPORT_MODULE", computed_direct_after["FROZEN_SUPPORT_MODULE"]
        )
        stats.tail_direct_seed_counts_before_truck_filter_by_main[main_identity] = (
            computed_direct_before
        )
        stats.tail_direct_seed_counts_after_truck_filter_by_main[main_identity] = (
            computed_direct_after
        )
        filtered = {
            module_name: tuple(
                candidate
                for candidate in candidates
                if not any(
                    rectangles_overlap(reserved, rectangle)
                    for reserved in reserved_spaces
                    for rectangle in candidate.values()
                )
            )
            for module_name, candidates in fixed_zone_filtered.items()
        }
        frozen_counts.setdefault(
            "after_reserved_corridor_filter",
            len(filtered["FROZEN_SUPPORT_MODULE"]),
        )
        reserved_corridor_rejections = (
            frozen_counts["after_fixed_zone_filter"]
            - frozen_counts["after_reserved_corridor_filter"]
        )
        if reserved_corridor_rejections:
            frozen_taxonomy["FROZEN_OVERLAPS_RESERVED_ACCESS_CORRIDOR"] = (
                frozen_taxonomy.get("FROZEN_OVERLAPS_RESERVED_ACCESS_CORRIDOR", 0)
                + reserved_corridor_rejections
            )
        entrance_compatible_count = sum(
            (metadata := candidate_metadata_by_signature.get(_module_signature(candidate)))
            is not None
            and metadata.endpoint_event_class == "ENTRANCE_CORRIDOR_COMPATIBLE_SORTING_DIRECT"
            for candidate in filtered["CHANGING_MODULE"]
        )
        if stats.entrance_route_compatible_changing_seed_counts_by_main is None:
            stats.entrance_route_compatible_changing_seed_counts_by_main = {}
        stats.entrance_route_compatible_changing_seed_counts_by_main[main_identity] = (
            entrance_compatible_count
        )
        stats.entrance_route_compatible_changing_seed_count = sum(
            stats.entrance_route_compatible_changing_seed_counts_by_main.values()
        )

        sorting = main_by_identity[main_identity]["sorting_packaging_room"]
        frozen_metadata = {_module_signature(row.as_placements()): row for row in frozen_candidates}
        attempted_frozen_candidates = (
            stats.tail_access_capacity_attempted_candidates_by_main or {}
        ).get(main_identity, set())
        mediated_frozen_remains = any(
            ("FROZEN_SUPPORT_MODULE", (signature := _module_signature(candidate)))
            not in attempted_frozen_candidates
            and (metadata := frozen_metadata.get(signature)) is not None
            and metadata.endpoint_event_class
            in {
                "CORRIDOR_MEDIATED",
                "SORTING_BAY_EDGE_MEDIATED",
                "SORTING_OBSTACLE_EDGE_MEDIATED",
                "FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED",
            }
            for candidate in truck_filtered["FROZEN_SUPPORT_MODULE"]
        )
        rejection_rows = stats.frozen_direct_seed_truck_rejection_rows
        if rejection_rows is None:
            rejection_rows = []
            stats.frozen_direct_seed_truck_rejection_rows = rejection_rows
        for candidate in module_options["FROZEN_SUPPORT_MODULE"]:
            signature = _module_signature(candidate)
            metadata = frozen_metadata.get(signature)
            if metadata is None or not metadata.endpoint_event_class.startswith("SORTING_DIRECT"):
                continue
            rectangle = candidate["frozen_fruit_room"]
            bounds = rectangle.bounds_mm
            shared = _sorting_shared_interval_mm(sorting, rectangle)
            for envelope_index, envelope in enumerate(truck_envelopes):
                if not rectangle_intersects_closed_obstacle(rectangle, envelope):
                    continue
                envelope_bounds = _boundary_extents(envelope)
                overlap_bounds = (
                    max(bounds[0], envelope_bounds[0]),
                    max(bounds[1], envelope_bounds[1]),
                    min(bounds[2], envelope_bounds[2]),
                    min(bounds[3], envelope_bounds[3]),
                )
                rejection = {
                    "main_identity": main_identity,
                    "main_skeleton_hash": skeleton_hash,
                    "frozen_bounds_mm": list(bounds),
                    "sorting_shared_side": shared[0] if shared else None,
                    "sorting_shared_interval_mm": list(shared[1:]) if shared else None,
                    "truck_envelope_identity": f"TRUCK_ENVELOPE-{envelope_index + 1:02d}",
                    "truck_envelope_index": envelope_index,
                    "closed_geometry_intersection": True,
                    "exact_positive_area_overlap": _rectangle_interiors_overlap_orthogonal_polygon(
                        rectangle, envelope
                    ),
                    "overlap_bounds_mm": list(overlap_bounds)
                    if overlap_bounds[0] < overlap_bounds[2]
                    and overlap_bounds[1] < overlap_bounds[3]
                    else None,
                    "alternative_sorting_side_interval_exists": any(
                        _sorting_shared_interval_mm(sorting, alternative["frozen_fruit_room"])
                        is not None
                        and _module_signature(alternative) != signature
                        for alternative in truck_filtered["FROZEN_SUPPORT_MODULE"]
                    ),
                    "mediated_candidate_remains_unsearched": mediated_frozen_remains,
                }
                if rejection not in rejection_rows:
                    rejection_rows.append(rejection)
        side_branch_intervals: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for module_name in ("SECONDARY_SUPPORT_MODULE", "FROZEN_SUPPORT_MODULE"):
            interval_rows = {
                (side, low, high): {
                    "sorting_side": side,
                    "interval_mm": [low, high],
                }
                for candidate in filtered[module_name]
                if (
                    interval := _sorting_shared_interval_mm(
                        sorting,
                        candidate[
                            "secondary_fruit_buffer"
                            if module_name == "SECONDARY_SUPPORT_MODULE"
                            else "frozen_fruit_room"
                        ],
                    )
                )
                is not None
                for side, low, high in (interval,)
            }
            side_branch_intervals[module_name] = {
                "GEOMETRY_AND_TRUCK_CLEAR_SEED_INTERVALS": [
                    interval_rows[key] for key in sorted(interval_rows)
                ],
                "ACCESS_VALID_SEED_INTERVALS": [],
            }
        if stats.sorting_side_branch_free_intervals_by_main is None:
            stats.sorting_side_branch_free_intervals_by_main = {}
        stats.sorting_side_branch_free_intervals_by_main[main_identity] = side_branch_intervals
        if stats.tail_access_capacity_seed_counts_by_main is None:
            stats.tail_access_capacity_seed_counts_by_main = {}
        seed_counts = stats.tail_access_capacity_seed_counts_by_main.setdefault(
            main_identity, {module_name: 0 for module_name in _S2_TAIL_MODULES}
        )
        valid_counts = stats.tail_access_valid_candidate_counts_by_main
        if valid_counts is None:
            valid_counts = {}
            stats.tail_access_valid_candidate_counts_by_main = valid_counts
        valid_counts.setdefault(main_identity, {module_name: 0 for module_name in _S2_TAIL_MODULES})
        attempted_by_main = stats.tail_access_capacity_attempted_candidates_by_main
        if attempted_by_main is None:
            attempted_by_main = {}
            stats.tail_access_capacity_attempted_candidates_by_main = attempted_by_main
        attempted_candidates = attempted_by_main.setdefault(main_identity, set())
        if stats.tail_access_driven_candidate_counts_by_main is None:
            stats.tail_access_driven_candidate_counts_by_main = {}
        stats.tail_access_driven_candidate_counts_by_main[main_identity] = {
            module_name: len(filtered[module_name]) for module_name in _S2_TAIL_MODULES
        }
        if stats.tail_office_geometry_candidate_counts_by_main is None:
            stats.tail_office_geometry_candidate_counts_by_main = {}
        stats.tail_office_geometry_candidate_counts_by_main[main_identity] = len(
            filtered["OFFICE_MODULE"]
        )
        for module_name in _S2_TAIL_MODULES:
            key = (main_identity, module_name)
            domains[key] = tuple(
                candidate
                for candidate in filtered[module_name]
                if (module_name, _module_signature(candidate)) not in attempted_candidates
            )
            cursors[key] = 0
            found[key] = seed_counts.get(module_name, 0) > 0

    if stats.tail_access_capacity_preflight_nodes_by_main is None:
        stats.tail_access_capacity_preflight_nodes_by_main = {}
    if stats.tail_access_capacity_status_by_main is None:
        stats.tail_access_capacity_status_by_main = {}
    if stats.tail_access_capacity_preflight_rows is None:
        stats.tail_access_capacity_preflight_rows = []
    capacity_seed_counts_by_main = stats.tail_access_capacity_seed_counts_by_main
    access_valid_counts_by_main = stats.tail_access_valid_candidate_counts_by_main
    assert capacity_seed_counts_by_main is not None
    assert access_valid_counts_by_main is not None
    if stats.tail_access_capacity_candidate_cursor_by_main is None:
        stats.tail_access_capacity_candidate_cursor_by_main = {}
    if stats.tail_access_capacity_domain_exhausted_by_main is None:
        stats.tail_access_capacity_domain_exhausted_by_main = {}
    if stats.tail_incapable_reason_by_main is None:
        stats.tail_incapable_reason_by_main = {}
    if stats.tail_incapable_proof_scope_by_main is None:
        stats.tail_incapable_proof_scope_by_main = {}
    if any(
        stats.tail_access_capacity_attempted_candidates_by_main
        and stats.tail_access_capacity_attempted_candidates_by_main.get(identity)
        for identity in main_by_identity
    ):
        stats.tail_access_capacity_continuation_count += 1

    empty_required_module_domains: dict[str, tuple[str, ...]] = {}
    for skeleton_hash, main in main_rows:
        main_identity = _tail_access_main_identity(skeleton_hash, main)
        empty_modules = tuple(
            module_name
            for module_name in _S2_TAIL_MODULES
            if not found[(main_identity, module_name)] and not domains[(main_identity, module_name)]
        )
        if empty_modules:
            empty_required_module_domains[main_identity] = empty_modules

    preflight_nodes = 0
    probe_order = tuple(
        (main_identity, module_name)
        for skeleton_hash, main in main_rows
        for main_identity in (_tail_access_main_identity(skeleton_hash, main),)
        if main_identity not in empty_required_module_domains
        for module_name in _S2_TAIL_MODULES
    )
    pending = True
    while (
        pending
        and not stats.node_budget_exhausted
        and (node_limit is None or preflight_nodes < node_limit)
    ):
        pending = False
        # Complete one whole main-by-module round before any main gets a
        # second geometry.  This prevents an early main from consuming the
        # shared S2 allocation before its Truck-pass peers are checked.
        for main_identity, module_name in probe_order:
            if node_limit is not None and preflight_nodes >= node_limit:
                break
            key = (main_identity, module_name)
            if found[key] or cursors[key] >= len(domains[key]):
                continue
            pending = True
            cursor_by_module = stats.tail_access_capacity_candidate_cursor_by_main.setdefault(
                main_identity, {}
            )
            candidate_index = cursor_by_module.get(module_name, 0) + 1
            candidate = domains[key][cursors[key]]
            if not _charge_tail_access_slot_node(
                context,
                stats,
                module_name=module_name,
                candidate_index=candidate_index,
                skeleton_hash=main_identity,
            ):
                break
            cursors[key] += 1
            cursor_by_module[module_name] = candidate_index
            preflight_nodes += 1
            stats.tail_access_capacity_preflight_nodes_by_main[main_identity] = (
                stats.tail_access_capacity_preflight_nodes_by_main.get(main_identity, 0) + 1
            )
            quantum = _quantum_checkpoint(stats)
            if quantum is not None:
                yield quantum
            _record_tail_module_slot(stats, module_name, candidate, access_valid=False)
            extended = {**main_by_identity[main_identity], **candidate}
            candidate_signature = _module_signature(candidate)
            metadata = candidate_metadata_by_signature.get(candidate_signature)
            if module_name != "OFFICE_MODULE" and (
                metadata is None or metadata.module_name != module_name
            ):
                metadata = None
                stats.endpoint_driven_candidate_metadata_miss_count += 1
            if module_name == "CHANGING_MODULE" and main_identity not in (
                stats.entrance_route_compatible_passed_by_main or set()
            ):
                changing = candidate.get("changing_room")
                if changing is not None:
                    left, bottom, right, top = changing.bounds_mm
                    aspect_ratio = Fraction(
                        max(right - left, top - bottom), min(right - left, top - bottom)
                    )
                    if aspect_ratio >= 10:
                        stats.changing_extreme_aspect_probed_before_route_compatible_count += 1
            if module_name == "OFFICE_MODULE":
                valid = True
                route_results: tuple[Mapping[str, Any], ...] = ()
                corridors: tuple[PolygonMM, ...] = ()
            else:
                routed = _tail_access_route_rows(
                    context,
                    extended,
                    requirements,
                    module_name=module_name,
                    stats=stats,
                    requirement_pairs=_S2_MODULE_ACCESS_PAIRS[module_name],
                    require_truck_clear_corridors=module_name == "FROZEN_SUPPORT_MODULE",
                    main_identity=main_identity,
                )
                valid = routed is not None
                route_results, corridors = routed if routed is not None else ((), ())
            if valid:
                found[key] = True
                capacity_seed_counts_by_main[main_identity][module_name] = 1
                access_valid_counts_by_main[main_identity][module_name] += 1
                _record_tail_module_slot(stats, module_name, candidate, access_valid=True)
                if (
                    module_name == "CHANGING_MODULE"
                    and metadata is not None
                    and metadata.endpoint_event_class
                    == "ENTRANCE_CORRIDOR_COMPATIBLE_SORTING_DIRECT"
                ):
                    stats.entrance_route_compatible_changing_access_pass_count += 1
                    if stats.entrance_route_compatible_passed_by_main is None:
                        stats.entrance_route_compatible_passed_by_main = set()
                    stats.entrance_route_compatible_passed_by_main.add(main_identity)
                if module_name != "OFFICE_MODULE":
                    if stats.tail_access_capacity_route_cache is None:
                        stats.tail_access_capacity_route_cache = {}
                    stats.tail_access_capacity_route_cache[
                        (main_identity, module_name, _module_signature(candidate))
                    ] = (route_results, corridors)
                    if module_name in side_branch_intervals:
                        zone_code = (
                            "secondary_fruit_buffer"
                            if module_name == "SECONDARY_SUPPORT_MODULE"
                            else "frozen_fruit_room"
                        )
                        interval = _sorting_shared_interval_mm(
                            main_by_identity[main_identity]["sorting_packaging_room"],
                            candidate[zone_code],
                        )
                        if interval is not None:
                            side_branch_intervals[module_name][
                                "ACCESS_VALID_SEED_INTERVALS"
                            ].append(
                                {
                                    "sorting_side": interval[0],
                                    "interval_mm": [interval[1], interval[2]],
                                }
                            )
            if stats.tail_access_capacity_attempted_candidates_by_main is None:
                stats.tail_access_capacity_attempted_candidates_by_main = {}
            stats.tail_access_capacity_attempted_candidates_by_main.setdefault(
                main_identity, set()
            ).add((module_name, _module_signature(candidate)))
            stats.tail_access_capacity_preflight_rows.append(
                {
                    "main_skeleton_hash": skeleton_hash_by_identity[main_identity],
                    "critical_assembly_id": main_identity,
                    "module_name": module_name,
                    "candidate_index": candidate_index,
                    "result": (
                        "GEOMETRY_SEED_FOUND"
                        if valid and module_name == "OFFICE_MODULE"
                        else "ACCESS_SEED_FOUND"
                        if valid
                        else "CANDIDATE_ROUTE_REJECTED"
                    ),
                    "route_witness_status": (
                        "NOT_REQUIRED"
                        if module_name == "OFFICE_MODULE"
                        else "PASS"
                        if valid
                        else "NOT_PASS"
                    ),
                    "zone_bounds_mm": {
                        code: list(rectangle.bounds_mm)
                        for code, rectangle in sorted(candidate.items())
                    },
                    "main_zone_bounds_mm": {
                        code: list(rectangle.bounds_mm)
                        for code, rectangle in sorted(main_by_identity[main_identity].items())
                    },
                    "main_zone_rotation_degrees": {
                        code: rectangle.rotation_deg
                        for code, rectangle in sorted(main_by_identity[main_identity].items())
                    },
                    "truck_envelopes_mm": [
                        [list(point) for point in polygon]
                        for polygon in truck_envelopes_by_identity[main_identity]
                    ],
                    "candidate_metadata": (
                        {
                            "driving_requirement_ids": list(metadata.driving_requirement_ids),
                            "anchor_source": metadata.anchor_source,
                            "endpoint_event_class": metadata.endpoint_event_class,
                            "direct_shared_edge_possible": metadata.direct_shared_edge_possible,
                            "construction_portal_pair_mm": (
                                [list(point) for point in metadata.construction_portal_pair_mm]
                                if metadata.construction_portal_pair_mm is not None
                                else None
                            ),
                        }
                        if metadata is not None
                        else {
                            "endpoint_event_class": (
                                "OFFICE_SHIPPING_MUST"
                                if module_name == "OFFICE_MODULE"
                                else "ENDPOINT_METADATA_MISSING"
                            )
                        }
                    ),
                    "route_witnesses": [dict(row) for row in route_results],
                    "reserved_corridors_mm": [
                        [list(point) for point in polygon] for polygon in corridors
                    ],
                    "reserved_corridor_count": len(corridors),
                }
            )
            if stats.node_budget_exhausted:
                break

    statuses: dict[str, str] = {}
    for skeleton_hash, main in main_rows:
        main_identity = _tail_access_main_identity(skeleton_hash, main)
        counts = capacity_seed_counts_by_main[main_identity]
        domain_exhausted = {
            module_name: (
                counts[module_name] > 0
                or cursors[(main_identity, module_name)]
                >= len(domains[(main_identity, module_name)])
            )
            for module_name in _S2_TAIL_MODULES
        }
        stats.tail_access_capacity_domain_exhausted_by_main[main_identity] = domain_exhausted
        incapable_reasons = sorted(
            module_name
            for module_name in _S2_TAIL_MODULES
            if counts[module_name] == 0 and domain_exhausted[module_name]
        )
        if incapable_reasons:
            stats.tail_incapable_reason_by_main[main_identity] = incapable_reasons
            stats.tail_incapable_proof_scope_by_main[main_identity] = (
                "CURRENT_FINITE_TAIL_CONSTRUCTION_DOMAIN_ONLY"
            )
        else:
            stats.tail_incapable_reason_by_main.pop(main_identity, None)
            stats.tail_incapable_proof_scope_by_main.pop(main_identity, None)
        if all(counts[module_name] > 0 for module_name in _S2_TAIL_MODULES):
            status = "TAIL_ACCESS_CAPABLE_MAIN"
        elif any(
            counts[module_name] == 0 and domain_exhausted[module_name]
            for module_name in _S2_TAIL_MODULES
        ):
            status = "TAIL_ACCESS_INCAPABLE_MAIN"
        else:
            status = "UNRESOLVED_COVERAGE"
        previous_status = stats.tail_access_capacity_status_by_main.get(main_identity)
        if status == "TAIL_ACCESS_INCAPABLE_MAIN" and previous_status != status:
            stats.truck_pass_main_rejected_for_tail_access_count += 1
        statuses[main_identity] = status
        stats.tail_access_capacity_status_by_main[main_identity] = status
    yield statuses


def _rectangle_interiors_overlap_orthogonal_polygon(
    rectangle: PlacedRectangleV1, polygon: PolygonMM
) -> bool:
    """Exact positive-area overlap for a rectangle and an orthogonal polygon."""
    if not _polygon_is_orthogonal(polygon):
        raise _error("S2_ACCESS_CORRIDOR_GEOMETRY_UNSUPPORTED")
    left, bottom, right, top = rectangle.bounds_mm
    y_events = sorted({bottom, top} | {y for _x, y in polygon if bottom < y < top})
    vertical_edges = tuple(
        (x1, min(y1, y2), max(y1, y2))
        for (x1, y1), (x2, y2) in zip(polygon, (*polygon[1:], polygon[0]), strict=True)
        if x1 == x2 and y1 != y2
    )
    for low_y, high_y in zip(y_events, y_events[1:], strict=False):
        if low_y >= high_y:
            continue
        doubled_mid_y = low_y + high_y
        crossings = sorted(
            x
            for x, edge_low, edge_high in vertical_edges
            if 2 * edge_low < doubled_mid_y < 2 * edge_high
        )
        for left_crossing, right_crossing in zip(crossings[::2], crossings[1::2], strict=True):
            if max(left, left_crossing) < min(right, right_crossing):
                return True
    return False


def _orthogonal_polygons_interiors_overlap(left: PolygonMM, right: PolygonMM) -> bool:
    """Return whether two orthogonal polygons overlap by positive area."""
    if not _polygon_is_orthogonal(left) or not _polygon_is_orthogonal(right):
        raise _error("S2_ACCESS_CORRIDOR_GEOMETRY_UNSUPPORTED")
    y_events = sorted({y for _x, y in (*left, *right)})

    def intervals_at(low_y: int, high_y: int, polygon: PolygonMM) -> tuple[tuple[int, int], ...]:
        doubled_mid_y = low_y + high_y
        crossings = sorted(
            x1
            for (x1, y1), (x2, y2) in zip(polygon, (*polygon[1:], polygon[0]), strict=True)
            if x1 == x2 and y1 != y2 and 2 * min(y1, y2) < doubled_mid_y < 2 * max(y1, y2)
        )
        return tuple(zip(crossings[::2], crossings[1::2], strict=True))

    for low_y, high_y in zip(y_events, y_events[1:], strict=False):
        if low_y >= high_y:
            continue
        left_intervals = intervals_at(low_y, high_y, left)
        right_intervals = intervals_at(low_y, high_y, right)
        if any(
            max(left_start, right_start) < min(left_end, right_end)
            for left_start, left_end in left_intervals
            for right_start, right_end in right_intervals
        ):
            return True
    return False


def _tail_truck_envelopes(
    context: _PlacementSearchContext,
    fixed: Mapping[str, PlacedRectangleV1],
    stats: _PlacementSearchStats | None,
) -> tuple[PolygonMM, ...]:
    if stats is None or stats.reserved_truck_envelopes_by_critical_signature is None:
        return ()
    critical_zones = {
        code: rectangle
        for code, rectangle in fixed.items()
        if code in {*MAIN_PROCESS_ZONE_CODES, "packaging_material_storage"}
    }
    if not set((*MAIN_PROCESS_ZONE_CODES, "packaging_material_storage")).issubset(critical_zones):
        return ()
    return stats.reserved_truck_envelopes_by_critical_signature.get(
        repr(_module_signature(critical_zones)), ()
    )


def _tail_access_requirement_rows(
    context: _PlacementSearchContext,
) -> tuple[Mapping[str, Any], ...] | None:
    by_endpoints = {
        (str(row.get("from_ref")), str(row.get("to_ref"))): row
        for row in context.access_requirements
    }
    if any(pair not in by_endpoints for pair in _S2_ACCESS_ENDPOINTS):
        return None
    return tuple(by_endpoints[pair] for pair in _S2_ACCESS_ENDPOINTS)


def _tail_active_access_requirements(
    requirements: Sequence[Mapping[str, Any]],
    fixed: Mapping[str, PlacedRectangleV1],
) -> tuple[Mapping[str, Any], ...]:
    active: list[Mapping[str, Any]] = []
    for requirement in requirements:
        from_ref = str(requirement.get("from_ref"))
        to_ref = str(requirement.get("to_ref"))
        if to_ref not in fixed:
            continue
        if from_ref != "main_entrance" and from_ref not in fixed:
            continue
        active.append(requirement)
    return tuple(active)


def _record_tail_candidate_sampling(
    stats: _PlacementSearchStats | None,
    module_name: str,
    *,
    raw_count: int,
    sampled_count: int,
) -> None:
    if stats is None:
        return
    if stats.tail_raw_geometry_slot_total_by_module is None:
        stats.tail_raw_geometry_slot_total_by_module = {}
    if stats.tail_access_sampled_slot_count_by_module is None:
        stats.tail_access_sampled_slot_count_by_module = {}
    if stats.tail_access_sample_truncated_by_module is None:
        stats.tail_access_sample_truncated_by_module = {}
    stats.tail_raw_geometry_slot_total_by_module[module_name] = (
        stats.tail_raw_geometry_slot_total_by_module.get(module_name, 0) + raw_count
    )
    stats.tail_access_sampled_slot_count_by_module[module_name] = (
        stats.tail_access_sampled_slot_count_by_module.get(module_name, 0) + sampled_count
    )
    stats.tail_access_sample_truncated_by_module[module_name] = (
        stats.tail_access_sample_truncated_by_module.get(module_name, 0)
        + int(raw_count > sampled_count)
    )


def _record_tail_module_slot(
    stats: _PlacementSearchStats | None,
    module_name: str,
    candidate: Mapping[str, PlacedRectangleV1],
    *,
    access_valid: bool,
) -> None:
    if stats is None:
        return
    geometry_key = repr(_module_signature(candidate))
    if stats.tail_raw_geometry_slot_count_by_module is None:
        stats.tail_raw_geometry_slot_count_by_module = {}
    if stats.tail_access_valid_slot_count_by_module is None:
        stats.tail_access_valid_slot_count_by_module = {}
    stats.tail_raw_geometry_slot_count_by_module.setdefault(module_name, set()).add(geometry_key)
    if access_valid:
        stats.tail_access_valid_slot_count_by_module.setdefault(module_name, set()).add(
            geometry_key
        )
    specific = {
        "CHANGING_MODULE": (
            "personnel_raw_candidate_signatures",
            "personnel_access_valid_signatures",
        ),
        "SECONDARY_SUPPORT_MODULE": (
            "secondary_raw_candidate_signatures",
            "secondary_access_valid_signatures",
        ),
        "FROZEN_SUPPORT_MODULE": (
            "frozen_raw_candidate_signatures",
            "frozen_access_valid_signatures",
        ),
    }.get(module_name)
    if specific is None:
        return
    raw_attribute, valid_attribute = specific
    raw_values = getattr(stats, raw_attribute)
    if raw_values is None:
        raw_values = set()
        setattr(stats, raw_attribute, raw_values)
    raw_values.add(geometry_key)
    if access_valid:
        valid_values = getattr(stats, valid_attribute)
        if valid_values is None:
            valid_values = set()
            setattr(stats, valid_attribute, valid_values)
        valid_values.add(geometry_key)


def _tail_candidate_relation_class(
    candidate: Mapping[str, PlacedRectangleV1], fixed: Mapping[str, PlacedRectangleV1]
) -> tuple[int, str, tuple[tuple[str, int], ...]]:
    sorting = fixed.get("sorting_packaging_room")
    target = candidate.get("changing_room") or next(iter(candidate.values()))
    direct_side = _adjacent_side(sorting, target) if sorting is not None else None
    if direct_side is not None:
        side = direct_side
    elif sorting is not None:
        left, bottom, right, top = sorting.bounds_mm
        target_left, target_bottom, target_right, target_top = target.bounds_mm
        dx = (target_left + target_right) - (left + right)
        dy = (target_bottom + target_top) - (bottom + top)
        side = (
            ("EAST" if dx >= 0 else "WEST")
            if abs(dx) >= abs(dy)
            else ("NORTH" if dy >= 0 else "SOUTH")
        )
    else:
        side = "UNANCHORED"
    return (
        0 if direct_side is not None else 1,
        side,
        tuple((code, rectangle.rotation_deg) for code, rectangle in sorted(candidate.items())),
    )


def _tail_candidate_geometry_order_key(
    context: _PlacementSearchContext,
    module_name: str,
    candidate: Mapping[str, PlacedRectangleV1],
    fixed: Mapping[str, PlacedRectangleV1],
) -> tuple[Any, ...]:
    relation_class = _tail_candidate_relation_class(candidate, fixed)
    sorting = fixed.get("sorting_packaging_room")
    target = candidate.get("changing_room") or next(iter(candidate.values()))
    if sorting is None:
        distance = 0
    else:
        target_left, target_bottom, target_right, target_top = target.bounds_mm
        sort_left, sort_bottom, sort_right, sort_top = sorting.bounds_mm
        dx = max(sort_left - target_right, 0, target_left - sort_right)
        dy = max(sort_bottom - target_top, 0, target_bottom - sort_top)
        distance = dx * dx + dy * dy
    entrance_distance = (
        _rectangle_distance_squared_to_entrance(target, context.main_entrance)
        if module_name == "CHANGING_MODULE"
        else 0
    )
    return (
        relation_class[0],
        entrance_distance if module_name == "CHANGING_MODULE" else distance,
        relation_class[1],
        relation_class[2],
        -_module_axis_reuse_count(candidate, fixed),
        _module_signature(candidate),
    )


def _bounded_tail_candidate_representatives(
    context: _PlacementSearchContext,
    module_name: str,
    candidates: Sequence[dict[str, PlacedRectangleV1]],
    fixed: Mapping[str, PlacedRectangleV1],
    *,
    limit: int = TAIL_ACCESS_ROUTE_REPRESENTATIVE_LIMIT,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Select a finite, deterministic side/orientation-spread route probe set.

    This is construction coverage, not a proof that unselected geometric slots
    are inaccessible.  Exact route authority is applied to every selected
    representative before it can enter tail search.
    """
    if limit <= 0 or not candidates:
        return ()
    ordered = tuple(
        sorted(
            candidates,
            key=lambda candidate: _tail_candidate_geometry_order_key(
                context, module_name, candidate, fixed
            ),
        )
    )
    strata: dict[tuple[int, str, tuple[tuple[str, int], ...]], dict[str, PlacedRectangleV1]] = {}
    for candidate in ordered:
        strata.setdefault(_tail_candidate_relation_class(candidate, fixed), candidate)

    selected: list[dict[str, PlacedRectangleV1]] = []
    selected_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    for _stratum, candidate in sorted(
        strata.items(),
        key=lambda row: (
            row[0][0],
            (0 if 0 in {rotation for _code, rotation in row[0][2]} else 1),
            row[0][1],
            row[0][2],
            _module_signature(row[1]),
        ),
    ):
        signature = _module_signature(candidate)
        if signature not in selected_signatures:
            selected.append(candidate)
            selected_signatures.add(signature)
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        remaining = tuple(
            candidate
            for candidate in ordered
            if _module_signature(candidate) not in selected_signatures
        )
        needed = limit - len(selected)
        if len(remaining) <= needed:
            fill = remaining
        else:
            indices = {
                (index * (len(remaining) - 1)) // max(needed - 1, 1) for index in range(needed)
            }
            fill = tuple(remaining[index] for index in sorted(indices))
        for candidate in fill:
            signature = _module_signature(candidate)
            if signature not in selected_signatures:
                selected.append(candidate)
                selected_signatures.add(signature)
    return tuple(
        sorted(
            selected,
            key=lambda candidate: _tail_candidate_geometry_order_key(
                context, module_name, candidate, fixed
            ),
        )
    )


def _tail_corridor_conflicts(
    candidate: Mapping[str, PlacedRectangleV1],
    reserved_corridors: Sequence[PolygonMM],
) -> bool:
    return any(
        _rectangle_interiors_overlap_orthogonal_polygon(rectangle, corridor)
        for rectangle in candidate.values()
        for corridor in reserved_corridors
    )


def _charge_tail_access_slot_node(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats | None,
    *,
    module_name: str,
    candidate_index: int,
    skeleton_hash: str,
) -> bool:
    """Account one exact tail-slot check against the existing placement budget."""
    if stats is None:
        return True
    if stats.visited_nodes >= context.node_budget:
        stats.node_budget_exhausted = True
        stats.skeleton_search_truncated = True
        stats.tail_access_slot_budget_exhausted = True
        return False
    stats.visited_nodes += 1
    stats.construction_node_count += 1
    stats.tail_access_slot_attempt_count += 1
    if stats.tail_access_slot_nodes_by_main is None:
        stats.tail_access_slot_nodes_by_main = {}
    stats.tail_access_slot_nodes_by_main[skeleton_hash] = (
        stats.tail_access_slot_nodes_by_main.get(skeleton_hash, 0) + 1
    )
    stats.current_work_item = {
        "topology": context.structural_topology,
        "layout_family": (
            context.structured_building_plan.layout_family
            if context.structured_building_plan is not None
            else None
        ),
        "band_family": (
            context.structured_building_plan.layout_family
            if context.structured_building_plan is not None
            else None
        ),
        "skeleton_hash": skeleton_hash,
        "branch": "S2_ACCESS_VALID_TAIL_SLOT",
        "tail_module": module_name,
        "tail_candidate_index": candidate_index,
        "placement_node_charged": True,
    }
    return True


def _tail_access_route_rows(
    context: _PlacementSearchContext,
    fixed: Mapping[str, PlacedRectangleV1],
    requirements: Sequence[Mapping[str, Any]],
    *,
    module_name: str,
    stats: _PlacementSearchStats | None,
    requirement_pairs: frozenset[tuple[str, str]] | None = None,
    require_truck_clear_corridors: bool = False,
    main_identity: str | None = None,
) -> tuple[tuple[Mapping[str, Any], ...], tuple[PolygonMM, ...]] | None:
    validator = getattr(context, "access_route_validator", None)
    if validator is None:
        if stats is not None and stats.site_module_assembly_trace is not None:
            stats.site_module_assembly_trace.append(
                {
                    "stage": "S2_ACCESS_AWARE_TAIL_ADMISSION",
                    "result": "REJECTED",
                    "module": module_name,
                    "reason": "ACCESS_ROUTE_VALIDATOR_NOT_INJECTED",
                }
            )
        return None
    active = tuple(
        requirement
        for requirement in _tail_active_access_requirements(requirements, fixed)
        if requirement_pairs is None
        or (str(requirement.get("from_ref")), str(requirement.get("to_ref"))) in requirement_pairs
    )
    relationships = {
        str(row["identity"]): row
        for row in context.spatial_relationships
        if isinstance(row.get("identity"), str)
    }
    result_rows: list[Mapping[str, Any]] = []
    corridors: dict[tuple[tuple[int, int], ...], PolygonMM] = {}
    truck_envelopes = _tail_truck_envelopes(context, fixed, stats)
    passed_pairs: set[tuple[str, str]] = set()

    def direct_topology_possible(requirement: Mapping[str, Any]) -> int:
        from_ref = str(requirement.get("from_ref"))
        to_ref = str(requirement.get("to_ref"))
        destination = fixed.get(to_ref)
        if destination is None:
            return 1
        if from_ref == "main_entrance":
            return (
                0 if _rectangle_shares_entrance_boundary(destination, context.main_entrance) else 1
            )
        source = fixed.get(from_ref)
        return (
            0 if source is not None and rectangles_share_positive_edge(source, destination) else 1
        )

    for requirement in sorted(
        active,
        key=lambda row: (
            direct_topology_possible(row),
            str(row.get("from_ref")),
            str(row.get("to_ref")),
        ),
    ):
        identity = f"{requirement.get('from_ref')}->{requirement.get('to_ref')}"
        pair = (str(requirement.get("from_ref")), str(requirement.get("to_ref")))
        is_frozen_route = pair == ("sorting_packaging_room", "frozen_fruit_room")
        if stats is not None and is_frozen_route and main_identity:
            if stats.frozen_route_probe_count_by_main is None:
                stats.frozen_route_probe_count_by_main = {}
            stats.frozen_route_probe_count_by_main[main_identity] = (
                stats.frozen_route_probe_count_by_main.get(main_identity, 0) + 1
            )
        result, polygons = validator(
            requirement,
            relationships=relationships,
            zones=fixed,
            boundary=context.boundary,
            obstacles=context.obstacles,
            entrances={"main_entrance": context.main_entrance},
        )
        if stats is not None:
            stats.access_route_revalidation_count += 1
            if stats.construction_access_requirement_pass_counts is None:
                stats.construction_access_requirement_pass_counts = {}
            if stats.construction_access_requirement_failure_counts is None:
                stats.construction_access_requirement_failure_counts = {}
        if result.get("status") != "PASS":
            if stats is not None:
                failures = stats.construction_access_requirement_failure_counts
                assert failures is not None
                failures[identity] = failures.get(identity, 0) + 1
                if stats.construction_access_failure_code_counts is None:
                    stats.construction_access_failure_code_counts = {}
                for code in result.get("codes", []):
                    code_name = str(code)
                    stats.construction_access_failure_code_counts[code_name] = (
                        stats.construction_access_failure_code_counts.get(code_name, 0) + 1
                    )
                    if (
                        identity == "main_entrance->changing_room"
                        and stats.main_entrance_to_changing_failure_code_counts is None
                    ):
                        stats.main_entrance_to_changing_failure_code_counts = {}
                    if identity == "main_entrance->changing_room":
                        assert stats.main_entrance_to_changing_failure_code_counts is not None
                        stats.main_entrance_to_changing_failure_code_counts[code_name] = (
                            stats.main_entrance_to_changing_failure_code_counts.get(code_name, 0)
                            + 1
                        )
                if is_frozen_route and main_identity:
                    if stats.frozen_access_failure_code_counts_by_main is None:
                        stats.frozen_access_failure_code_counts_by_main = {}
                    frozen_codes = stats.frozen_access_failure_code_counts_by_main.setdefault(
                        main_identity, {}
                    )
                    if stats.frozen_candidate_rejection_taxonomy_by_main is None:
                        stats.frozen_candidate_rejection_taxonomy_by_main = {}
                    taxonomy = stats.frozen_candidate_rejection_taxonomy_by_main.setdefault(
                        main_identity, {}
                    )
                    for code in result.get("codes", []):
                        code_name = str(code)
                        frozen_codes[code_name] = frozen_codes.get(code_name, 0) + 1
                        category = (
                            "ROUTE_SEARCH_EXHAUSTED"
                            if code_name == "ROUTE_SEARCH_EXHAUSTED"
                            else "PORTAL_CLEAR_WIDTH_INSUFFICIENT"
                            if code_name == "PORTAL_CLEAR_WIDTH_INSUFFICIENT"
                            else "ACCESS_TOPOLOGY_PROHIBITED"
                            if code_name == "ACCESS_TOPOLOGY_PROHIBITED"
                            else "OTHER_AUTHORITY_FAILURE"
                        )
                        taxonomy[category] = taxonomy.get(category, 0) + 1
                    if stats.frozen_candidate_route_rejection_rows_by_main is None:
                        stats.frozen_candidate_route_rejection_rows_by_main = {}
                    rejection_rows = stats.frozen_candidate_route_rejection_rows_by_main.setdefault(
                        main_identity, []
                    )
                    if len(rejection_rows) < 40:
                        rectangle = fixed.get("frozen_fruit_room")
                        rejection_rows.append(
                            {
                                "main_identity": main_identity,
                                "frozen_bounds_mm": (
                                    list(rectangle.bounds_mm) if rectangle is not None else None
                                ),
                                "route_status": result.get("status"),
                                "route_codes": list(result.get("codes", [])),
                            }
                        )
            # One failed required route is sufficient to reject this candidate.
            # Later routes are re-evaluated on the next candidate; spending more
            # route work on an already-invalid slot cannot admit it.
            return None
        result_row = dict(result)
        if is_frozen_route:
            unrelated_corridor_zones = sorted(
                code
                for code, rectangle in fixed.items()
                if code not in {"sorting_packaging_room", "frozen_fruit_room"}
                and any(
                    _orthogonal_polygons_interiors_overlap(corridor, rectangle.polygon_mm)
                    for corridor in polygons
                )
            )
            if unrelated_corridor_zones:
                if stats is not None and main_identity:
                    if stats.frozen_candidate_rejection_taxonomy_by_main is None:
                        stats.frozen_candidate_rejection_taxonomy_by_main = {}
                    taxonomy = stats.frozen_candidate_rejection_taxonomy_by_main.setdefault(
                        main_identity, {}
                    )
                    taxonomy["FROZEN_CORRIDOR_OVERLAPS_FIXED_ZONE"] = (
                        taxonomy.get("FROZEN_CORRIDOR_OVERLAPS_FIXED_ZONE", 0) + 1
                    )
                    if stats.frozen_access_failure_code_counts_by_main is None:
                        stats.frozen_access_failure_code_counts_by_main = {}
                    failure_codes = stats.frozen_access_failure_code_counts_by_main.setdefault(
                        main_identity, {}
                    )
                    failure_codes["CONSTRUCTION_CORRIDOR_INTERSECTS_FIXED_ZONE"] = (
                        failure_codes.get("CONSTRUCTION_CORRIDOR_INTERSECTS_FIXED_ZONE", 0) + 1
                    )
                return None
        corridor_intersects_truck = any(
            _orthogonal_polygons_interiors_overlap(corridor, envelope)
            for corridor in polygons
            for envelope in truck_envelopes
        )
        result_row["intersects_truck_envelope"] = (
            corridor_intersects_truck
            if is_frozen_route
            else result.get("flow_kind") == "PEOPLE" and corridor_intersects_truck
        )
        if is_frozen_route and corridor_intersects_truck and require_truck_clear_corridors:
            if stats is not None and main_identity:
                if stats.frozen_candidate_rejection_taxonomy_by_main is None:
                    stats.frozen_candidate_rejection_taxonomy_by_main = {}
                taxonomy = stats.frozen_candidate_rejection_taxonomy_by_main.setdefault(
                    main_identity, {}
                )
                taxonomy["FROZEN_OVERLAPS_TRUCK_ENVELOPE"] = (
                    taxonomy.get("FROZEN_OVERLAPS_TRUCK_ENVELOPE", 0) + 1
                )
            return None
        result_rows.append(result_row)
        pair = (str(requirement.get("from_ref")), str(requirement.get("to_ref")))
        passed_pairs.add(pair)
        if stats is not None:
            pass_counts = stats.construction_access_requirement_pass_counts
            assert pass_counts is not None
            pass_counts[identity] = pass_counts.get(identity, 0) + 1
            topology = result.get("topology")
            if topology == "DIRECT_SHARED_EDGE":
                stats.direct_shared_edge_access_witness_count += 1
                if pair == ("changing_room", "sorting_packaging_room"):
                    stats.changing_to_sorting_direct_pass_count += 1
            elif topology == "CORRIDOR_MEDIATED":
                stats.corridor_mediated_access_witness_count += 1
            if pair == ("sorting_packaging_room", "secondary_fruit_buffer"):
                if stats.secondary_access_pass_signatures is None:
                    stats.secondary_access_pass_signatures = set()
                stats.secondary_access_pass_signatures.add(
                    repr(
                        _module_signature(
                            {"secondary_fruit_buffer": fixed["secondary_fruit_buffer"]}
                        )
                    )
                )
            elif pair == ("sorting_packaging_room", "frozen_fruit_room"):
                if stats.frozen_access_pass_signatures is None:
                    stats.frozen_access_pass_signatures = set()
                stats.frozen_access_pass_signatures.add(
                    repr(_module_signature({"frozen_fruit_room": fixed["frozen_fruit_room"]}))
                )
                if main_identity:
                    if stats.frozen_access_valid_count_by_main is None:
                        stats.frozen_access_valid_count_by_main = {}
                    stats.frozen_access_valid_count_by_main[main_identity] = (
                        stats.frozen_access_valid_count_by_main.get(main_identity, 0) + 1
                    )
                    if stats.frozen_access_witness_by_main is None:
                        stats.frozen_access_witness_by_main = {}
                    stats.frozen_access_witness_by_main[main_identity] = {
                        "frozen_bounds_mm": list(fixed["frozen_fruit_room"].bounds_mm),
                        "route_witness": dict(result),
                        "corridor_envelopes_mm": [
                            [list(point) for point in corridor] for corridor in polygons
                        ],
                        "truck_clear": not corridor_intersects_truck,
                    }
                    if not corridor_intersects_truck:
                        if stats.frozen_truck_clear_corridor_event_count_by_main is None:
                            stats.frozen_truck_clear_corridor_event_count_by_main = {}
                        stats.frozen_truck_clear_corridor_event_count_by_main[main_identity] = (
                            stats.frozen_truck_clear_corridor_event_count_by_main.get(
                                main_identity, 0
                            )
                            + 1
                        )
        for polygon in polygons:
            key = tuple(sorted(polygon))
            corridors.setdefault(key, polygon)
            if stats is not None:
                if stats.reserved_access_corridor_geometries is None:
                    stats.reserved_access_corridor_geometries = set()
                stats.reserved_access_corridor_geometries.add(key)
    if (
        stats is not None
        and module_name == "CHANGING_MODULE"
        and {
            ("main_entrance", "changing_room"),
            ("changing_room", "sorting_packaging_room"),
        }.issubset(passed_pairs)
    ):
        if stats.personnel_access_2_of_2_pass_signatures is None:
            stats.personnel_access_2_of_2_pass_signatures = set()
        stats.personnel_access_2_of_2_pass_signatures.add(
            repr(
                _module_signature(
                    {code: fixed[code] for code in ("office", "changing_room") if code in fixed}
                )
            )
        )
    if stats is not None:
        if stats.tail_access_candidate_witnesses is None:
            stats.tail_access_candidate_witnesses = []
        if len(stats.tail_access_candidate_witnesses) < 24:
            stats.tail_access_candidate_witnesses.append(
                {
                    "module": module_name,
                    "zone_bounds_mm": {
                        code: list(rectangle.bounds_mm) for code, rectangle in sorted(fixed.items())
                    },
                    "zone_rotation_degrees": {
                        code: rectangle.rotation_deg for code, rectangle in sorted(fixed.items())
                    },
                    "access_witnesses": [
                        {
                            "requirement_identity": row.get("requirement_identity"),
                            "from_ref": row.get("from_ref"),
                            "to_ref": row.get("to_ref"),
                            "flow_kind": row.get("flow_kind"),
                            "status": row.get("status"),
                            "topology": row.get("topology"),
                            "centerline": row.get("centerline", []),
                            "route_shape": row.get("route_shape"),
                            "turn_count": row.get("turn_count"),
                            "route_length_m": row.get("route_length_m"),
                            "intersects_truck_envelope": row.get(
                                "intersects_truck_envelope", False
                            ),
                        }
                        for row in result_rows
                    ],
                    "reserved_corridors_mm": [
                        [list(point) for point in polygon] for polygon in corridors.values()
                    ],
                    "truck_envelopes_mm": [
                        [list(point) for point in polygon] for polygon in truck_envelopes
                    ],
                }
            )
    return tuple(result_rows), tuple(corridors[key] for key in sorted(corridors))


def _module_axis_reuse_count(
    module: Mapping[str, PlacedRectangleV1], fixed: Mapping[str, PlacedRectangleV1]
) -> int:
    fixed_x = {
        coordinate
        for rectangle in fixed.values()
        for coordinate in (rectangle.bounds_mm[0], rectangle.bounds_mm[2])
    }
    fixed_y = {
        coordinate
        for rectangle in fixed.values()
        for coordinate in (rectangle.bounds_mm[1], rectangle.bounds_mm[3])
    }
    return sum(
        int(x in fixed_x) + int(right in fixed_x) + int(y in fixed_y) + int(top in fixed_y)
        for rectangle in module.values()
        for x, y, right, top in (rectangle.bounds_mm,)
    )


def _route_length_mm(result: Mapping[str, Any]) -> int:
    value = result.get("route_length_m")
    if value is None:
        return 0
    try:
        return int(Decimal(str(value)) * MILLIMETRES_PER_METRE)
    except (InvalidOperation, ValueError):
        return 0


def _tail_module_option_order_key(
    module_name: str,
    candidate: Mapping[str, PlacedRectangleV1],
    route_results: Sequence[Mapping[str, Any]],
    fixed: Mapping[str, PlacedRectangleV1],
) -> tuple[Any, ...]:
    by_pair = {(str(row.get("from_ref")), str(row.get("to_ref"))): row for row in route_results}
    personnel_direct_rank = 1
    entrance_length = 0
    people_turns = 0
    people_truck_intersections = 0
    if module_name == "CHANGING_MODULE":
        changing_sorting = by_pair.get(("changing_room", "sorting_packaging_room"), {})
        personnel_direct_rank = 0 if changing_sorting.get("topology") == "DIRECT_SHARED_EDGE" else 1
        entrance_length = _route_length_mm(by_pair.get(("main_entrance", "changing_room"), {}))
        people_turns = sum(
            int(row.get("turn_count", 0))
            for row in route_results
            if row.get("flow_kind") == "PEOPLE"
        )
        people_truck_intersections = sum(
            bool(row.get("intersects_truck_envelope"))
            for row in route_results
            if row.get("flow_kind") == "PEOPLE"
        )
    return (
        personnel_direct_rank,
        entrance_length if module_name == "CHANGING_MODULE" else 0,
        people_turns,
        people_truck_intersections,
        -_module_axis_reuse_count(candidate, fixed),
        _module_signature(candidate),
    )


def _module_full_site_assemblies(
    context: _PlacementSearchContext,
    main: Mapping[str, PlacedRectangleV1],
    bays: Sequence[BuildableBayV1],
    *,
    limit: int,
    stats: _PlacementSearchStats | None = None,
    main_skeleton_hash: str | None = None,
    node_limit: int | None = None,
) -> Iterator[dict[str, PlacedRectangleV1] | _SearchQuantumYield | None]:
    """Complete four independent tail modules by deterministic fail-first slots.

    Packaging is already part of ``main`` and is never reassembled as support.
    Office and changing are independent modules; branch-storage rooms are
    independent semantic modules. Endpoint-driven domains are evaluated before
    the generic geometric fallback, and the smallest positive access-valid
    domain is selected at every partial state.
    """
    if limit <= 0:
        return
    required_main = {*MAIN_PROCESS_ZONE_CODES, "packaging_material_storage"}
    if not required_main.issubset(main):
        yield None
        return

    critical_signature = repr(_module_signature(main))
    main_identity = _tail_access_main_identity(main_skeleton_hash, main)
    tail_nodes_at_start = stats.tail_access_slot_attempt_count if stats is not None else 0
    reserved_spaces = (
        (stats.reserved_construction_space_by_critical_signature or {}).get(critical_signature, ())
        if stats is not None
        else ()
    )
    reserved_truck_envelopes = (
        (stats.reserved_truck_envelopes_by_critical_signature or {}).get(critical_signature, ())
        if stats is not None
        else ()
    )
    yielded = 0
    tail_codes = {"secondary_fruit_buffer", "frozen_fruit_room", "office", "changing_room"}
    module_codes = {
        "OFFICE_MODULE": {"office"},
        "CHANGING_MODULE": {"changing_room"},
        "SECONDARY_SUPPORT_MODULE": {"secondary_fruit_buffer"},
        "FROZEN_SUPPORT_MODULE": {"frozen_fruit_room"},
    }
    last_raw_option_counts: dict[str, int] = {}
    last_access_probe_counts: dict[str, int] = {}
    last_access_domain_exact: dict[str, bool] = {}

    requirements = _tail_access_requirement_rows(context)
    if requirements is None:
        if stats is not None and stats.site_module_assembly_trace is not None:
            stats.site_module_assembly_trace.append(
                {
                    "stage": "S2_ACCESS_AWARE_TAIL_ADMISSION",
                    "result": "REJECTED",
                    "reason": "REQUIRED_S2_ACCESS_AUTHORITY_INCOMPLETE",
                }
            )
        yield None
        return

    def enumerate_options(
        fixed: Mapping[str, PlacedRectangleV1],
        reserved_corridors: Sequence[PolygonMM],
    ) -> Iterator[dict[str, tuple[_TailModuleOption, ...]] | _SearchQuantumYield]:
        raw_options: dict[str, tuple[dict[str, PlacedRectangleV1], ...]] = {}
        if not module_codes["OFFICE_MODULE"].issubset(fixed):
            raw_options["OFFICE_MODULE"] = _office_site_module_candidates(context, fixed)
        if not module_codes["CHANGING_MODULE"].issubset(fixed):
            raw_options["CHANGING_MODULE"] = tuple(
                candidate.as_placements()
                for candidate in _access_driven_tail_candidates(
                    context, "CHANGING_MODULE", "changing_room", fixed, bays
                )
            )
        if "secondary_fruit_buffer" not in fixed:
            raw_options["SECONDARY_SUPPORT_MODULE"] = tuple(
                candidate.as_placements()
                for candidate in _access_driven_tail_candidates(
                    context,
                    "SECONDARY_SUPPORT_MODULE",
                    "secondary_fruit_buffer",
                    fixed,
                    bays,
                )
            )
        if "frozen_fruit_room" not in fixed:
            raw_options["FROZEN_SUPPORT_MODULE"] = tuple(
                candidate.as_placements()
                for candidate in _access_driven_tail_candidates(
                    context,
                    "FROZEN_SUPPORT_MODULE",
                    "frozen_fruit_room",
                    fixed,
                    bays,
                    stats=stats,
                    main_identity=main_identity,
                    truck_envelopes=reserved_truck_envelopes,
                    reserved_corridors=reserved_corridors,
                )
            )
        if stats is not None and _module_signature(fixed) == _module_signature(main):
            for name, candidates in tuple(raw_options.items()):
                cached_signatures = {
                    cache_key[2]
                    for cache_key in (stats.tail_access_capacity_route_cache or {})
                    if cache_key[0] == main_identity and cache_key[1] == name
                }
                if cached_signatures:
                    raw_options[name] = tuple(
                        sorted(
                            candidates,
                            key=lambda candidate: (
                                _module_signature(candidate) not in cached_signatures,
                                _module_signature(candidate),
                            ),
                        )
                    )
                    stats.tail_capacity_seed_cache_reused_in_s2 = True
        if reserved_spaces:
            raw_options = {
                name: tuple(
                    candidate
                    for candidate in candidates
                    if not any(
                        rectangles_overlap(reserved, rectangle)
                        for reserved in reserved_spaces
                        for rectangle in candidate.values()
                    )
                )
                for name, candidates in raw_options.items()
            }
        if reserved_truck_envelopes:
            raw_options = {
                name: tuple(
                    candidate
                    for candidate in candidates
                    if not any(
                        rectangle_intersects_closed_obstacle(rectangle, envelope)
                        for envelope in reserved_truck_envelopes
                        for rectangle in candidate.values()
                    )
                )
                for name, candidates in raw_options.items()
            }
        raw_option_counts = {name: len(rows) for name, rows in raw_options.items()}
        last_raw_option_counts.clear()
        last_raw_option_counts.update(raw_option_counts)
        last_access_probe_counts.clear()
        last_access_probe_counts.update({name: 0 for name in raw_options})
        last_access_domain_exact.clear()
        last_access_domain_exact.update({name: True for name in raw_options})
        # Endpoint-derived domains are already finite construction families;
        # they must not be sampled a second time. The bounded generic sampler
        # is applied only in the fallback block after these families fail.
        sampled_options = dict(raw_options)
        access_probe_counts: dict[str, int] = {}
        options: dict[str, tuple[_TailModuleOption, ...]] = {name: () for name in raw_options}
        evaluation_order = sorted(
            raw_options,
            key=lambda name: (raw_option_counts[name], name),
        )
        for name in evaluation_order:
            candidates = sampled_options[name]
            valid: list[_TailModuleOption] = []
            attempted = 0
            local_quota_exhausted = False

            def admit_candidate(
                candidate: dict[str, PlacedRectangleV1],
                *,
                generic_fallback: bool,
                selected_module_name: str,
            ) -> _TailModuleOption | None:
                _record_tail_module_slot(stats, selected_module_name, candidate, access_valid=False)
                if _tail_corridor_conflicts(candidate, reserved_corridors):
                    return None
                if selected_module_name == "OFFICE_MODULE":
                    access_results: tuple[Mapping[str, Any], ...] = ()
                else:
                    cache_key = (
                        main_identity,
                        selected_module_name,
                        _module_signature(candidate),
                    )
                    cached = (
                        (stats.tail_access_capacity_route_cache or {}).get(cache_key)
                        if stats is not None and _module_signature(fixed) == _module_signature(main)
                        else None
                    )
                    if cached is not None:
                        access_results, _candidate_corridors = cached
                    else:
                        routed = _tail_access_route_rows(
                            context,
                            {**fixed, **candidate},
                            requirements,
                            module_name=selected_module_name,
                            stats=stats,
                            requirement_pairs=_S2_MODULE_ACCESS_PAIRS[selected_module_name],
                            require_truck_clear_corridors=(
                                selected_module_name == "FROZEN_SUPPORT_MODULE"
                            ),
                            main_identity=main_identity,
                        )
                        if routed is None:
                            return None
                        access_results, _candidate_corridors = routed
                        if generic_fallback and stats is not None:
                            stats.tail_generic_fallback_route_probe_count += 1
                _record_tail_module_slot(stats, selected_module_name, candidate, access_valid=True)
                return _TailModuleOption(candidate, access_results)

            for candidate_index, candidate in enumerate(candidates, start=1):
                candidate_signature = _module_signature(candidate)
                preflight_cached = (
                    name != "OFFICE_MODULE"
                    and stats is not None
                    and _module_signature(fixed) == _module_signature(main)
                    and (
                        main_identity,
                        name,
                        candidate_signature,
                    )
                    in (stats.tail_access_capacity_route_cache or {})
                )
                preflight_rejected = (
                    name != "OFFICE_MODULE"
                    and stats is not None
                    and _module_signature(fixed) == _module_signature(main)
                    and (name, candidate_signature)
                    in (stats.tail_access_capacity_attempted_candidates_by_main or {}).get(
                        main_identity, set()
                    )
                    and not preflight_cached
                )
                if preflight_rejected:
                    # This exact endpoint-driven candidate already failed with
                    # the same critical assembly as its fixed geometry. Do not
                    # spend another placement node on the identical route probe.
                    continue
                if (
                    name != "OFFICE_MODULE"
                    and not preflight_cached
                    and node_limit is not None
                    and stats is not None
                    and stats.tail_access_slot_attempt_count - tail_nodes_at_start >= node_limit
                ):
                    local_quota_exhausted = True
                    last_access_domain_exact[name] = False
                    if stats.tail_access_s2_node_quota_exhausted_by_main is None:
                        stats.tail_access_s2_node_quota_exhausted_by_main = set()
                    stats.tail_access_s2_node_quota_exhausted_by_main.add(main_identity)
                    break
                if (
                    name != "OFFICE_MODULE"
                    and not preflight_cached
                    and not _charge_tail_access_slot_node(
                        context,
                        stats,
                        module_name=name,
                        candidate_index=candidate_index,
                        skeleton_hash=main_identity,
                    )
                ):
                    if stats is not None and stats.site_module_assembly_trace is not None:
                        stats.site_module_assembly_trace.append(
                            {
                                "stage": "S2_ACCESS_AWARE_TAIL_ADMISSION",
                                "result": "PLACEMENT_BUDGET_EXHAUSTED",
                                "module": name,
                                "candidate_index": candidate_index,
                                "visited_nodes": stats.visited_nodes,
                                "node_budget": context.node_budget,
                            }
                        )
                    _record_tail_candidate_sampling(
                        stats,
                        name,
                        raw_count=raw_option_counts[name],
                        sampled_count=attempted,
                    )
                    access_probe_counts[name] = attempted
                    last_access_probe_counts[name] = attempted
                    return
                attempted += 1
                last_access_probe_counts[name] = attempted
                if stats is not None and name != "OFFICE_MODULE" and not preflight_cached:
                    quantum = _quantum_checkpoint(stats)
                    if quantum is not None:
                        yield quantum
                option = admit_candidate(
                    candidate,
                    generic_fallback=False,
                    selected_module_name=name,
                )
                if option is not None:
                    valid.append(option)

            fallback_raw_count = 0
            fallback_count = 0
            fallback_truncated = False
            fallback_deferred = False
            if not valid and name != "OFFICE_MODULE" and not local_quota_exhausted:
                local_nodes_used = (
                    stats.tail_access_slot_attempt_count - tail_nodes_at_start
                    if stats is not None
                    else 0
                )
                remaining_local_nodes = (
                    None if node_limit is None else max(0, node_limit - local_nodes_used)
                )
                if remaining_local_nodes == 0:
                    fallback_deferred = True
                    last_access_domain_exact[name] = False
                    if stats is not None:
                        stats.tail_generic_fallback_deferred_count += 1
                else:
                    zone_code = next(iter(module_codes[name]))
                    generic = _single_zone_site_module_candidates(context, zone_code, fixed, bays)
                    primary_signatures = {_module_signature(row) for row in candidates}
                    generic = tuple(
                        row for row in generic if _module_signature(row) not in primary_signatures
                    )
                    fallback_raw_count = len(generic)
                    representatives = _bounded_tail_candidate_representatives(
                        context, name, generic, fixed
                    )
                    if remaining_local_nodes is not None:
                        representatives = representatives[:remaining_local_nodes]
                    fallback_count = len(representatives)
                    fallback_truncated = fallback_raw_count > fallback_count
                    last_access_domain_exact[name] = not fallback_truncated
                    if fallback_truncated and stats is not None:
                        stats.tail_generic_fallback_truncated_count += 1
                for candidate_index, candidate in (
                    enumerate(representatives, start=len(candidates) + 1)
                    if not fallback_deferred
                    else ()
                ):
                    if (
                        node_limit is not None
                        and stats is not None
                        and stats.tail_access_slot_attempt_count - tail_nodes_at_start >= node_limit
                    ):
                        local_quota_exhausted = True
                        last_access_domain_exact[name] = False
                        if stats.tail_access_s2_node_quota_exhausted_by_main is None:
                            stats.tail_access_s2_node_quota_exhausted_by_main = set()
                        stats.tail_access_s2_node_quota_exhausted_by_main.add(main_identity)
                        break
                    if not _charge_tail_access_slot_node(
                        context,
                        stats,
                        module_name=name,
                        candidate_index=candidate_index,
                        skeleton_hash=main_identity,
                    ):
                        if stats is not None:
                            stats.tail_candidate_space_truncated = True
                        break
                    attempted += 1
                    if stats is not None:
                        quantum = _quantum_checkpoint(stats)
                        if quantum is not None:
                            yield quantum
                    option = admit_candidate(
                        candidate,
                        generic_fallback=True,
                        selected_module_name=name,
                    )
                    if option is not None:
                        valid.append(option)

            access_probe_counts[name] = attempted
            last_access_probe_counts[name] = attempted
            _record_tail_candidate_sampling(
                stats,
                name,
                raw_count=raw_option_counts[name] + fallback_raw_count,
                sampled_count=attempted,
            )
            last_raw_option_counts[name] = raw_option_counts[name] + fallback_raw_count
            options[name] = tuple(
                sorted(
                    valid,
                    key=lambda option: _tail_module_option_order_key(
                        name, option.placements, option.access_results, fixed
                    ),
                )
            )
            if local_quota_exhausted:
                for later_name in evaluation_order[evaluation_order.index(name) + 1 :]:
                    last_access_domain_exact[later_name] = False
                break
            if (
                not options[name]
                and attempted >= raw_option_counts[name]
                and not fallback_truncated
            ):
                if stats is not None and stats.site_module_assembly_trace is not None:
                    stats.site_module_assembly_trace.append(
                        {
                            "stage": "S2_ACCESS_AWARE_FAIL_FIRST_TAIL_MODULE_PLACEMENT",
                            "result": "GENERATED_ACCESS_SEED_SET_EXHAUSTED",
                            "module": name,
                            "raw_geometry_slot_count": raw_option_counts[name],
                            "access_valid_slot_count": 0,
                            "access_route_probe_count": attempted,
                            "generic_fallback_candidate_count": fallback_raw_count,
                            "generic_fallback_sampled_count": fallback_count,
                            "remaining_zone_codes": sorted(tail_codes - fixed.keys()),
                        }
                    )
                yield options
                return
            if not options[name] and fallback_truncated and stats is not None:
                stats.tail_candidate_space_truncated = True
                stats.normal_stop_reason = "UNRESOLVED_COVERAGE"
        if stats is not None and stats.site_module_assembly_trace is not None:
            stats.site_module_assembly_trace.append(
                {
                    "stage": "S2_ACCESS_AWARE_FAIL_FIRST_TAIL_MODULE_PLACEMENT",
                    "result": "SLOT_COUNTS_COMPUTED",
                    "remaining_zone_codes": sorted(tail_codes - fixed.keys()),
                    "raw_geometry_slot_count_by_module": {
                        name: raw_option_counts[name] for name in sorted(raw_options)
                    },
                    "access_route_probe_count_by_module": {
                        name: access_probe_counts.get(name, 0) for name in sorted(raw_options)
                    },
                    "generic_fallback_route_probe_limit": TAIL_ACCESS_ROUTE_REPRESENTATIVE_LIMIT,
                    "candidate_sampling_truncated_by_module": {
                        name: raw_option_counts[name] > access_probe_counts.get(name, 0)
                        for name in sorted(raw_options)
                    },
                    "access_valid_slot_count_by_module": {
                        name: len(rows) for name, rows in sorted(options.items())
                    },
                    "reserved_access_corridor_count": len(reserved_corridors),
                    "reserved_construction_space_count": len(reserved_spaces),
                    "reserved_truck_envelope_count": len(reserved_truck_envelopes),
                }
            )
        yield options

    def search(
        fixed: dict[str, PlacedRectangleV1],
        reserved_corridors: tuple[PolygonMM, ...],
        access_results: tuple[Mapping[str, Any], ...],
    ) -> Iterator[dict[str, PlacedRectangleV1] | _SearchQuantumYield]:
        if tail_codes.issubset(fixed):
            try:
                _validate_graph_completeness(context.graph, fixed)
            except LayoutAuthorityError:
                return
            if stats is not None:
                if stats.tail_complete_access_witnesses is None:
                    stats.tail_complete_access_witnesses = []
                stats.tail_complete_access_witnesses.append(
                    {
                        "complete_geometry_signature": repr(_module_signature(fixed)),
                        "zone_bounds_mm": {
                            code: list(rectangle.bounds_mm)
                            for code, rectangle in sorted(fixed.items())
                        },
                        "zone_rotation_degrees": {
                            code: rectangle.rotation_deg
                            for code, rectangle in sorted(fixed.items())
                        },
                        "access_witnesses": [
                            {
                                "requirement_identity": row.get("requirement_identity"),
                                "from_ref": row.get("from_ref"),
                                "to_ref": row.get("to_ref"),
                                "flow_kind": row.get("flow_kind"),
                                "status": row.get("status"),
                                "codes": list(row.get("codes", [])),
                                "topology": row.get("topology"),
                                "centerline": row.get("centerline", []),
                                "route_shape": row.get("route_shape"),
                                "turn_count": row.get("turn_count"),
                                "route_length_m": row.get("route_length_m"),
                                "intersects_truck_envelope": row.get(
                                    "intersects_truck_envelope", False
                                ),
                            }
                            for row in access_results
                        ],
                        "reserved_corridors_mm": [
                            [list(point) for point in polygon] for polygon in reserved_corridors
                        ],
                        "truck_envelopes_mm": [
                            [list(point) for point in polygon]
                            for polygon in reserved_truck_envelopes
                        ],
                    }
                )
            yield dict(fixed)
            return
        option_iterator = enumerate_options(fixed, reserved_corridors)
        options: dict[str, tuple[_TailModuleOption, ...]] | None = None
        for option_event in option_iterator:
            if isinstance(option_event, _SearchQuantumYield):
                yield option_event
                continue
            options = option_event
            break
        if options is None:
            return
        pending = [
            (len(candidates), name, candidates, last_access_domain_exact.get(name, True))
            for name, candidates in options.items()
            if not module_codes[name].issubset(fixed)
        ]
        complete_empty_domains = [
            name
            for count, name, _rows, exact_domain in pending
            if count == 0
            and exact_domain
            and last_access_probe_counts.get(name, 0) >= last_raw_option_counts.get(name, 0)
        ]
        if complete_empty_domains:
            return
        positive_pending = [row for row in pending if row[0] > 0]
        if not positive_pending:
            unresolved_domains = [
                name
                for count, name, _rows, exact_domain in pending
                if count == 0
                and (
                    not exact_domain
                    or last_access_probe_counts.get(name, 0) < last_raw_option_counts.get(name, 0)
                )
            ]
            if unresolved_domains and stats is not None:
                stats.tail_candidate_space_truncated = True
                stats.normal_stop_reason = "S2_TAIL_ACCESS_REPRESENTATIVE_COVERAGE_LIMIT"
                if stats.site_module_assembly_trace is not None:
                    stats.site_module_assembly_trace.append(
                        {
                            "stage": "S2_ACCESS_AWARE_TAIL_ADMISSION",
                            "result": "UNRESOLVED_REPRESENTATIVE_COVERAGE",
                            "modules": sorted(unresolved_domains),
                            "node_budget": context.node_budget,
                        }
                    )
            return
        exact_positive = [row for row in positive_pending if row[3]]
        if exact_positive:
            _count, selected_name, selected_rows, _exact = min(
                exact_positive, key=lambda row: (row[0], row[1])
            )
        else:
            # Generic fallback access counts are sampled lower bounds. They are
            # deliberately not compared as if they were complete domains.
            _count, selected_name, selected_rows, _exact = min(
                positive_pending, key=lambda row: row[1]
            )
        for option in selected_rows:
            candidate = option.placements
            extended = {**fixed, **candidate}
            if not _site_module_is_usable(context, candidate, fixed):
                continue
            # A newly placed module can obstruct any previously established
            # witness. Re-run all active authoritative routes against the full
            # partial geometry before admitting the next recursion level.
            revalidated = _tail_access_route_rows(
                context,
                extended,
                requirements,
                module_name="S2_TAIL_EXTENSION_REVALIDATION",
                stats=stats,
                require_truck_clear_corridors=True,
                main_identity=main_identity,
            )
            if revalidated is None:
                continue
            revalidated_results, revalidated_corridors = revalidated
            yield from search(
                extended,
                revalidated_corridors,
                revalidated_results,
            )

    for complete_or_quantum in search(dict(main), (), ()):
        if isinstance(complete_or_quantum, _SearchQuantumYield):
            yield complete_or_quantum
            continue
        yield complete_or_quantum
        yielded += 1
        if yielded >= limit:
            return
    if yielded == 0 and not (stats and stats.node_budget_exhausted):
        yield None


def _site_local_composition(
    context: _PlacementSearchContext,
    layout_family: str,
    process_axis: str,
    process_direction: str,
    placements: Mapping[str, PlacedRectangleV1],
) -> LocalBuildingCompositionV1:
    outline, bounds = _local_outline_class(placements)
    spine_zones = (
        (
            "sorting_packaging_room",
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        )
        if layout_family == LONGITUDINAL_PROCESS_SPINE
        else ()
    )
    return LocalBuildingCompositionV1(
        layout_family=layout_family,
        process_axis=process_axis,
        process_direction=process_direction,
        zone_placements=tuple(
            LocalZonePlacementV1(code, zone_band_assignment(code), rectangle)
            for code, rectangle in sorted(placements.items())
        ),
        must_interfaces=tuple(pair for pair in context.graph.must_adjacencies),
        spine_axis=process_axis if spine_zones else None,
        spine_zone_codes=spine_zones,
        side_bank_zone_codes=("raw_fruit_buffer", "primary_precooling_room"),
        outline_class=outline,
        bounds_mm=bounds,
    )


def _canonical_site_main_skeleton(
    context: _PlacementSearchContext,
    placements: Mapping[str, PlacedRectangleV1],
    *,
    layout_family: str,
    process_axis: str,
    process_direction: str,
    generation_pattern: str,
) -> MainProcessSkeletonCandidateV1:
    _validate_main_process_skeleton_graph(context.graph, placements)
    classification = classify_main_process_topology_v1(placements)
    if classification.canonical_owner is None or classification.process_axis is None:
        raise _error("SKELETON_TOPOLOGY_INVALID")
    if not _topology_geometry_valid(
        placements, classification.canonical_owner, classification.process_axis
    ):
        raise _error("SKELETON_TOPOLOGY_INVALID")
    outline, bounds = _local_outline_class(placements)
    seed = MainProcessSkeletonCandidateV1.create(
        family=context.structural_composition_family,
        rectangles=placements,
        topology=classification.canonical_owner,
        generation_pattern=generation_pattern,
        hard_geometry_predicates_passed=(
            "SITE_CONTAINMENT",
            "NO_BUILD_CLEAR",
            "NON_OVERLAP",
            "MUST_ADJACENCY",
            "MODULE_INTERNAL_GEOMETRY_FROZEN",
            "SITE_AWARE_MODULE_ASSEMBLY",
        ),
        construction_policy=f"{layout_family}_SITE_PARTITIONED_MODULE_ASSEMBLY_V1",
        topology_divergence_stage="SITE_MODULE_ASSEMBLY",
        discovery_topology=context.structural_topology,
        discovery_family=context.structural_composition_family,
        building_layout_family=layout_family,
        building_envelope_family=RECTANGLE if outline == "RECTANGLE" else SIMPLE_L,
        planned_envelope_bounds_mm=bounds,
    )
    return canonicalize_main_process_skeleton_for_evaluation(
        seed, classification, site_geometry=context.site_body
    )


def _rectangle_shares_entrance_boundary(rectangle: PlacedRectangleV1, entrance: SegmentMM) -> bool:
    left, bottom, right, top = _bounds(rectangle)
    edges = (
        ((left, bottom), (right, bottom)),
        ((right, bottom), (right, top)),
        ((right, top), (left, top)),
        ((left, top), (left, bottom)),
    )
    return any(segments_share_positive_length(*edge, *entrance) for edge in edges)


def _rectangle_distance_squared_to_entrance(
    rectangle: PlacedRectangleV1, entrance: SegmentMM
) -> int:
    """Exact orthogonal rectangle-to-entrance distance used only for option order."""
    left, bottom, right, top = _bounds(rectangle)
    (x1, y1), (x2, y2) = entrance
    if x1 == x2:
        dx = max(left - x1, 0, x1 - right)
        entrance_low, entrance_high = sorted((y1, y2))
        dy = max(bottom - entrance_high, 0, entrance_low - top)
    elif y1 == y2:
        dy = max(bottom - y1, 0, y1 - top)
        entrance_low, entrance_high = sorted((x1, x2))
        dx = max(left - entrance_high, 0, entrance_low - right)
    else:
        raise ValueError("truck entrance must be axis-aligned")
    return dx * dx + dy * dy


def _candidate_options(
    code: str,
    authority: Mapping[str, Any],
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    boundary_bounds: tuple[int, int, int, int],
    obstacles: Sequence[PolygonMM],
    graph: AdjacencyGraphV1,
    structural_family: StructuralCompositionFamilyV1,
    main_entrance: SegmentMM,
    *,
    search_phase: str = LEGACY_COMPAT_PHASE,
    structural_skeleton: StructuralSkeletonV1 | None = None,
    structured_building_plan: StructuredBuildingSkeletonV1 | None = None,
    zone_authorities: Mapping[str, Mapping[str, Any]] | None = None,
    truck_entrance: SegmentMM | None = None,
) -> tuple[PlacedRectangleV1, ...]:
    variants = _dimension_variants(authority, placed, boundary)
    options: dict[tuple[int, int, int, int, int], PlacedRectangleV1] = {}
    must_neighbors = _must_neighbors(code, placed, graph)
    structural_refs = structural_anchor_references(code, tuple(placed))
    structural_neighbors = tuple(placed[reference] for reference in structural_refs)
    prioritized_bridge_keys: set[tuple[int, int, int, int, int]] = set()
    prioritized_truck_finished_keys: set[tuple[int, int, int, int, int]] = set()
    for width_mm, depth_mm, rotation in variants:
        anchor_width_mm, anchor_depth_mm = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        if search_phase == STRUCTURED_PHASE:
            legacy_anchors: set[tuple[int, int]] = set()
        elif must_neighbors:
            legacy_anchors = {
                anchor
                for neighbor in must_neighbors
                for anchor in _edge_anchors(neighbor, anchor_width_mm, anchor_depth_mm)
            }
        else:
            legacy_anchors = set(
                _free_anchors(placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm)
            )
        structural_anchor_neighbors = tuple(
            {
                neighbor.zone_code: neighbor
                for neighbor in (*must_neighbors, *structural_neighbors)
            }.values()
        )
        if structural_anchor_neighbors:
            structural_anchors = {
                anchor
                for neighbor in structural_anchor_neighbors
                for anchor in _edge_anchors(neighbor, anchor_width_mm, anchor_depth_mm)
            }
        else:
            structural_anchors = set()
        if code == "raw_fruit_buffer":
            # The first raw-side zone has no earlier room anchor; its
            # structured skeleton roots only at exact buildable-boundary
            # anchors, never at the unrestricted legacy site cross-product.
            structural_anchors.update(
                _structural_event_anchors(
                    placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm
                )
            )
        if code in SUPPORT_ZONE_CODES and search_phase == STRUCTURED_PHASE:
            # Keep support placement within the skeleton search while also
            # admitting exact site/obstacle event positions. A support room
            # can remain edge-attached to the process core at more than one
            # longitudinal offset; using only the room-edge-aligned anchor
            # can hide hard-valid peripheral placements from P2D.
            structural_anchors.update(
                _structural_event_anchors(
                    placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm
                )
            )
        if code == "sorting_packaging_room" and not placed:
            if search_phase == STRUCTURED_PHASE and structural_skeleton is not None:
                structural_anchors.update(
                    (_mm(x, field="skeleton_root.x"), _mm(y, field="skeleton_root.y"))
                    for x, y, root_rotation in structural_skeleton.root_anchor_candidates
                    if root_rotation == rotation and x >= 0 and y >= 0
                )
                # Root the family at the site's exact boundary/obstacle events
                # as well as the canonical group-derived starts. This is a
                # bounded structural skeleton search, not a legacy free-grid:
                # every admitted room still passes the exact site/no-build
                # predicates and the downstream group-band constraints.
                structural_anchors.update(
                    _structural_event_anchors(
                        placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm
                    )
                )
            else:
                structural_anchors.update(
                    _free_anchors(placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm)
                )
        if (
            code
            in {
                "coating_room",
                "secondary_precooling_room",
                "primary_precooling_room",
            }
            and placed
        ):
            # Main-flow zones may need to slide along an authoritative shared
            # edge to clear another already-placed process room or a site
            # obstacle. These are bounded geometry-event anchors; mandatory
            # adjacency and the skeleton region predicate below still decide
            # whether a candidate is admitted. They are not legacy free-form
            # options and are never mixed into the structured phase by union.
            structural_anchors.update(
                _structural_event_anchors(
                    placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm
                )
            )
        if (
            code == "coating_room"
            and search_phase == STRUCTURED_PHASE
            and structural_family.family == "CENTRAL_PROCESS_HUB"
            and structural_skeleton is not None
            and "sorting_packaging_room" in placed
        ):
            secondary_authority = (
                zone_authorities.get("secondary_precooling_room")
                if zone_authorities is not None
                else None
            )
            if isinstance(secondary_authority, Mapping):
                bridge_anchors = _central_core_bridge_anchors(
                    placed["sorting_packaging_room"],
                    secondary_authority,
                    candidate_width_mm=width_mm,
                    candidate_depth_mm=depth_mm,
                    candidate_rotation=rotation,
                    ordering_axis=structural_skeleton.ordering_axis,
                    boundary=boundary,
                )
                structural_anchors.update(bridge_anchors)
                prioritized_bridge_keys.update(
                    (x_mm, y_mm, width_mm, depth_mm, rotation) for x_mm, y_mm in bridge_anchors
                )
        if code == "changing_room":
            entrance_anchors = _entrance_anchors(main_entrance, anchor_width_mm, anchor_depth_mm)
            structural_anchors.update(entrance_anchors)
            sorting = placed.get("sorting_packaging_room")
            if sorting is not None:
                core_edge_anchors = _edge_anchors(sorting, anchor_width_mm, anchor_depth_mm)
                # Combine exact entrance-aligned X events with exact core-edge
                # Y events (and vice versa) so a personnel room can bridge
                # both authorities without moving either geometry.
                structural_anchors.update(
                    (entrance_x, core_y)
                    for entrance_x, _entrance_y in entrance_anchors
                    for _core_x, core_y in core_edge_anchors
                )
                structural_anchors.update(
                    (core_x, entrance_y)
                    for _entrance_x, entrance_y in entrance_anchors
                    for core_x, _core_y in core_edge_anchors
                )
        if code == "shipping_channel" and truck_entrance is not None:
            approach_anchors = _entrance_anchors(truck_entrance, anchor_width_mm, anchor_depth_mm)
            structural_anchors.update(approach_anchors)
            if search_phase == STRUCTURED_PHASE:
                # Intersect the exact truck-entrance alignment events with
                # the already-placed finished-goods edge events. This lets
                # P2D evaluate a shipping interface that is both P2C-adjacent
                # and entrance-aligned without P2C consuming maneuver poses
                # or computing truck routes.
                finished_edge_anchors = {
                    anchor
                    for neighbor in (*must_neighbors, *structural_neighbors)
                    for anchor in _edge_anchors(neighbor, anchor_width_mm, anchor_depth_mm)
                }
                structural_anchors.update(
                    (edge_x, entrance_y)
                    for edge_x, _edge_y in finished_edge_anchors
                    for _entry_x, entrance_y in approach_anchors
                )
                structural_anchors.update(
                    (entrance_x, edge_y)
                    for _entry_x, edge_y in finished_edge_anchors
                    for entrance_x, _entry_y in approach_anchors
                )
        if (
            code == "finished_goods_room"
            and search_phase == STRUCTURED_PHASE
            and truck_entrance is not None
            and zone_authorities is not None
            and isinstance(zone_authorities.get("shipping_channel"), Mapping)
        ):
            truck_side_finished = _finished_anchors_for_truck_interface(
                zone_authorities["shipping_channel"],
                truck_entrance,
                boundary,
                anchor_width_mm,
                anchor_depth_mm,
            )
            structural_anchors.update(truck_side_finished)
            prioritized_truck_finished_keys.update(
                (x_mm, y_mm, width_mm, depth_mm, rotation) for x_mm, y_mm in truck_side_finished
            )
        anchors = (
            tuple(sorted(structural_anchors))
            if search_phase == STRUCTURED_PHASE
            else tuple(sorted(structural_anchors | legacy_anchors))
        )
        for x_mm, y_mm in anchors:
            rectangle = _rectangle_from_mm(code, x_mm, y_mm, width_mm, depth_mm, rotation)
            if not _rectangle_is_usable(rectangle, placed, boundary, boundary_bounds, obstacles):
                continue
            if any(
                not rectangles_share_positive_edge(rectangle, neighbor)
                for neighbor in must_neighbors
            ):
                continue
            if (
                search_phase == STRUCTURED_PHASE
                and structural_skeleton is not None
                and not _candidate_fits_skeleton_region(
                    code, rectangle, placed, structural_skeleton
                )
            ):
                continue
            if (
                search_phase == STRUCTURED_PHASE
                and structured_building_plan is not None
                and not structured_building_plan.admits(code, rectangle)
            ):
                continue
            key = (x_mm, y_mm, width_mm, depth_mm, rotation)
            options[key] = rectangle

    def stable_geometry_key(rectangle: PlacedRectangleV1) -> tuple[object, ...]:
        width_mm = _mm(rectangle.width_m, field="candidate.width_m", positive=True)
        depth_mm = _mm(rectangle.depth_m, field="candidate.depth_m", positive=True)
        flexible_shape_skew = (
            Fraction(abs(width_mm - depth_mm), max(width_mm, depth_mm))
            if code in FLEXIBLE_ZONE_CODES
            else Fraction(0)
        )
        changing_entrance_rank = int(
            code == "changing_room"
            and not _rectangle_shares_entrance_boundary(rectangle, main_entrance)
        )
        entrance_midpoint_rank = 0
        if code == "changing_room":
            entrance_start, entrance_end = main_entrance
            entrance_midpoint = (
                (entrance_start[0] + entrance_end[0]) // 2,
                (entrance_start[1] + entrance_end[1]) // 2,
            )
            room_bounds = _bounds(rectangle)
            entrance_midpoint_rank = int(
                room_bounds[0] <= entrance_midpoint[0] <= room_bounds[2]
                and room_bounds[1] <= entrance_midpoint[1] <= room_bounds[3]
            )
        changing_core_edge_rank = int(
            code == "changing_room"
            and "sorting_packaging_room" in placed
            and not rectangles_share_positive_edge(rectangle, placed["sorting_packaging_room"])
        )
        office_process_attachment_rank = 0
        if code == "office":
            coating = placed.get("coating_room")
            shipping = placed.get("shipping_channel")
            office_process_attachment_rank = int(
                coating is None
                or shipping is None
                or not rectangles_share_positive_edge(rectangle, coating)
                or not rectangles_share_positive_edge(rectangle, shipping)
            )
        shipping_truck_entrance_rank = int(
            code == "shipping_channel"
            and truck_entrance is not None
            and not _rectangle_shares_entrance_boundary(rectangle, truck_entrance)
        )
        shipping_entrance_axis_rank = 0
        shipping_long_axis_rank = 0
        if code == "shipping_channel" and truck_entrance is not None:
            (entrance_start, entrance_end) = truck_entrance
            truck_approach_axis = (
                "X"
                if entrance_start[0] == entrance_end[0]
                else "Y"
                if entrance_start[1] == entrance_end[1]
                else None
            )
            if truck_approach_axis is not None:
                left, bottom, right, top = _bounds(rectangle)
                shipping_long_axis = "X" if right - left >= top - bottom else "Y"
                shipping_long_axis_rank = int(shipping_long_axis != truck_approach_axis)
                low_x, high_x = sorted((entrance_start[0], entrance_end[0]))
                low_y, high_y = sorted((entrance_start[1], entrance_end[1]))
                entrance_axis_aligned = any(
                    (edge[0][1] == edge[1][1] and low_y <= edge[0][1] <= high_y)
                    if truck_approach_axis == "X"
                    else (edge[0][0] == edge[1][0] and low_x <= edge[0][0] <= high_x)
                    for _, edge in _long_edges(rectangle)
                )
                shipping_entrance_axis_rank = int(not entrance_axis_aligned)
        process_band_axis_rank = 0
        if code == "secondary_precooling_room" and structural_skeleton is not None:
            left, bottom, right, top = _bounds(rectangle)
            zone_long_axis = "X" if right - left >= top - bottom else "Y"
            process_band_axis_rank = int(zone_long_axis != structural_skeleton.ordering_axis)
        finished_truck_interface_rank = int(
            code == "finished_goods_room"
            and (
                _mm(rectangle.x, field="candidate.x"),
                _mm(rectangle.y, field="candidate.y"),
                _mm(rectangle.width_m, field="candidate.width_m"),
                _mm(rectangle.depth_m, field="candidate.depth_m"),
                rectangle.rotation_deg,
            )
            not in prioritized_truck_finished_keys
        )
        finished_core_axis_alignment_rank = 0
        if code == "finished_goods_room" and structural_skeleton is not None:
            # Reuse an exact transverse axis from the already placed process
            # core before falling back to lexical coordinates. This keeps the
            # terminal storage band attached to the core envelope instead of
            # stretching across unrelated site space. It is a geometry fact,
            # not a route-distance score or a pass/fail threshold.
            transverse_bounds_index = (1, 3) if structural_skeleton.ordering_axis == "X" else (0, 2)
            candidate_bounds = _bounds(rectangle)
            candidate_axis_edges = (
                candidate_bounds[transverse_bounds_index[0]],
                candidate_bounds[transverse_bounds_index[1]],
            )
            core_axis_edges = tuple(
                edge
                for core_code in structural_skeleton.core_zone_codes
                if (core_zone := placed.get(core_code)) is not None
                for core_bounds in (_bounds(core_zone),)
                for edge in (
                    core_bounds[transverse_bounds_index[0]],
                    core_bounds[transverse_bounds_index[1]],
                )
            )
            if core_axis_edges:
                finished_core_axis_alignment_rank = min(
                    abs(candidate_edge - core_edge)
                    for candidate_edge in candidate_axis_edges
                    for core_edge in core_axis_edges
                )
        central_raw_side_rank = 0
        central_band_alignment_rank = 0
        support_region_rank = 0
        support_perimeter_rank = 0
        support_root_rank = 0
        support_side_coherence_rank = 0
        if (
            code == "primary_precooling_room"
            and structural_family.family == "CENTRAL_PROCESS_HUB"
            and structural_skeleton is not None
            and "sorting_packaging_room" in placed
        ):
            side = _adjacent_side(placed["sorting_packaging_room"], rectangle)
            low_side = "WEST" if structural_skeleton.ordering_axis == "X" else "SOUTH"
            high_side = "EAST" if structural_skeleton.ordering_axis == "X" else "NORTH"
            central_raw_side_rank = 0 if side == low_side else 1 if side == high_side else 2
            sorting_bounds = _bounds(placed["sorting_packaging_room"])
            primary_bounds = _bounds(rectangle)
            if structural_skeleton.ordering_axis == "Y":
                if primary_bounds[0] == sorting_bounds[0]:
                    central_band_alignment_rank = 0
                elif primary_bounds[2] == sorting_bounds[2]:
                    central_band_alignment_rank = 1
                else:
                    central_band_alignment_rank = 2
            elif primary_bounds[1] == sorting_bounds[1]:
                central_band_alignment_rank = 0
            elif primary_bounds[3] == sorting_bounds[3]:
                central_band_alignment_rank = 1
            else:
                central_band_alignment_rank = 2
        if code in SUPPORT_ZONE_CODES and structural_skeleton is not None:
            sorting = placed.get("sorting_packaging_room")
            allowed_sides = (
                {"NORTH", "SOUTH"} if structural_skeleton.ordering_axis == "X" else {"EAST", "WEST"}
            )
            direct_side = _adjacent_side(sorting, rectangle) if sorting is not None else None
            shares_core_band = False
            if sorting is not None:
                axis_low, axis_high = (0, 2) if structural_skeleton.ordering_axis == "X" else (1, 3)
                core_bounds = _bounds(sorting)
                candidate_bounds = _bounds(rectangle)
                shares_core_band = min(core_bounds[axis_high], candidate_bounds[axis_high]) > max(
                    core_bounds[axis_low], candidate_bounds[axis_low]
                )
            attachment_side: str | None = None
            if direct_side is not None:
                support_root_rank = 0
                support_region_rank = (
                    0
                    if direct_side in allowed_sides and shares_core_band
                    else 1
                    if direct_side in allowed_sides
                    else 2
                )
                attachment_side = direct_side
            elif code in {"secondary_fruit_buffer", "frozen_fruit_room"}:
                support_parent = next(
                    (
                        placed[parent_code]
                        for parent_code in (
                            "frozen_fruit_room",
                            "packaging_material_storage",
                        )
                        if parent_code != code
                        and parent_code in placed
                        and rectangles_share_positive_edge(rectangle, placed[parent_code])
                    ),
                    None,
                )
                if support_parent is not None:
                    parent_adjacent_side: str | None = (
                        _adjacent_side(sorting, support_parent) if sorting is not None else None
                    )
                    support_root_rank = 1
                    support_region_rank = (
                        0
                        if parent_adjacent_side in allowed_sides and shares_core_band
                        else 1
                        if parent_adjacent_side in allowed_sides
                        else 2
                    )
                    attachment_side = parent_adjacent_side
                else:
                    support_root_rank = 2
                    support_region_rank = 2
                    attachment_side = None
            else:
                support_root_rank = 2
                support_region_rank = 2
                attachment_side = None
            support_perimeter_rank = int(not _rectangle_touches_boundary(rectangle, boundary))
            occupied_support_sides = {
                side
                for support_code in SUPPORT_ZONE_CODES
                if (support := placed.get(support_code)) is not None
                if sorting is not None
                if (side := _adjacent_side(sorting, support)) is not None
            }
            support_side_coherence_rank = (
                (0 if attachment_side in occupied_support_sides else 1)
                if occupied_support_sides
                else 0
            )
        root_axis_rank: int | Decimal = 0
        if code == "raw_fruit_buffer":
            root_bounds = _bounds(rectangle)
            root_axis = (
                structural_skeleton.ordering_axis
                if structural_skeleton is not None
                else structural_family.dominant_axis
            )
            root_low, root_high = (
                (root_bounds[0], root_bounds[2])
                if root_axis == "X"
                else (root_bounds[1], root_bounds[3])
            )
            direction = structural_family.dominant_direction
            root_axis_rank = -root_low if direction == "NEGATIVE" else root_low
        major_axis_rank = 0
        site_center_distance = 0
        if code in {"sorting_packaging_room", "primary_precooling_room"}:
            left, bottom, right, top = _bounds(rectangle)
            min_x, min_y, max_x, max_y = boundary_bounds
            # Compare doubled centres using integers, so ranking is exact and
            # independent of floating-point/epsilon behavior.
            site_center_distance = abs((left + right) - (min_x + max_x)) + abs(
                (bottom + top) - (min_y + max_y)
            )
        if code == "sorting_packaging_room":
            left, bottom, right, top = _bounds(rectangle)
            preferred_long_axis = structural_family.dominant_axis
            if structural_family.family == "LINEAR_PROCESS_BAND":
                # A linear band's axis describes group order, not the long
                # dimension of each room. Orienting the dominant sorting hall
                # across the band leaves room for raw/core/finished bands on
                # either side instead of consuming the entire flow axis.
                preferred_long_axis = "Y" if preferred_long_axis == "X" else "X"
            major_axis_rank = int(
                not (
                    (right - left) >= (top - bottom)
                    if preferred_long_axis == "X"
                    else (top - bottom) >= (right - left)
                )
            )
        linear_rank = 0
        linear_predecessor = _structural_linear_predecessor(code)
        if structural_family.family == "LINEAR_PROCESS_BAND" and linear_predecessor is not None:
            predecessor = placed.get(linear_predecessor)
            if predecessor is not None:
                linear_rank = int(
                    not _linear_flow_anchor_matches(rectangle, predecessor, structural_family)
                )
        return (
            int(
                code == "coating_room"
                and (
                    _mm(rectangle.x, field="candidate.x"),
                    _mm(rectangle.y, field="candidate.y"),
                    _mm(rectangle.width_m, field="candidate.width_m"),
                    _mm(rectangle.depth_m, field="candidate.depth_m"),
                    rectangle.rotation_deg,
                )
                not in prioritized_bridge_keys
            ),
            changing_entrance_rank,
            entrance_midpoint_rank,
            changing_core_edge_rank,
            office_process_attachment_rank,
            flexible_shape_skew,
            process_band_axis_rank,
            finished_core_axis_alignment_rank,
            finished_truck_interface_rank,
            shipping_entrance_axis_rank,
            shipping_long_axis_rank,
            shipping_truck_entrance_rank,
            central_raw_side_rank,
            central_band_alignment_rank,
            support_root_rank,
            support_region_rank,
            support_side_coherence_rank,
            support_perimeter_rank,
            major_axis_rank,
            site_center_distance,
            root_axis_rank,
            linear_rank,
            -_finished_band_axis_reuse(code, rectangle, placed),
            -_support_group_edge_count(code, rectangle, placed),
            -_support_obstacle_x_alignment(code, rectangle, obstacles),
            -_support_process_axis_reuse(code, rectangle, placed),
            -_should_local_count(code, rectangle, placed, graph),
            rectangle.x,
            rectangle.y,
            rectangle.width_m,
            rectangle.depth_m,
            rectangle.rotation_deg,
        )

    def structurally_anchored(rectangle: PlacedRectangleV1) -> bool:
        if code == "sorting_packaging_room" and not placed:
            return True
        if structural_family.family == "LINEAR_PROCESS_BAND":
            if code == "coating_room":
                # Coating is a frozen MUST transition from secondary
                # precooling to finished goods. Sorting-to-coating is only a
                # SHOULD relationship and cannot be a phase-admission gate.
                return bool(must_neighbors) and any(
                    rectangles_share_positive_edge(rectangle, neighbor)
                    for neighbor in must_neighbors
                )
            if code == "finished_goods_room":
                return _linear_group_flow_anchor_matches(
                    rectangle,
                    placed,
                    ("secondary_precooling_room", "coating_room"),
                    structural_family,
                )
            linear_predecessor = _structural_linear_predecessor(code)
            if linear_predecessor is not None:
                predecessor = placed.get(linear_predecessor)
                return predecessor is not None and _linear_flow_anchor_matches(
                    rectangle, predecessor, structural_family
                )
        if code == "primary_precooling_room":
            return any(
                rectangles_share_positive_edge(rectangle, neighbor) for neighbor in must_neighbors
            )
        if code == "changing_room" and _rectangle_shares_entrance_boundary(
            rectangle, main_entrance
        ):
            return True
        if not structural_neighbors:
            if code != "raw_fruit_buffer":
                return False
            return _rectangle_touches_boundary(rectangle, boundary)
        if code == "secondary_precooling_room":
            # It is a frozen process interface adjacent to sorting and
            # coating, not a spatial predecessor of the entire core envelope.
            return any(
                rectangles_share_positive_edge(rectangle, neighbor)
                for neighbor in structural_neighbors
            )
        return any(
            rectangles_share_positive_edge(rectangle, neighbor) for neighbor in structural_neighbors
        )

    structured = sorted(
        (rectangle for rectangle in options.values() if structurally_anchored(rectangle)),
        key=stable_geometry_key,
    )
    general = sorted(
        (rectangle for rectangle in options.values() if not structurally_anchored(rectangle)),
        key=stable_geometry_key,
    )
    if search_phase == STRUCTURED_PHASE:
        return tuple(structured[:STRUCTURED_MAX_OPTIONS_PER_ZONE])
    if search_phase == GENERAL_FALLBACK_PHASE:
        # Preserve the R1 general-fallback candidate stream exactly: ordinary
        # exact-feasible options precede structural anchors. The phase is
        # separate for accounting, not a new candidate-ordering policy.
        return tuple((*general, *structured)[:MAX_OPTIONS_PER_ZONE])
    if search_phase == LEGACY_COMPAT_PHASE:
        return tuple((*structured, *general)[:MAX_OPTIONS_PER_ZONE])
    raise _error("PLACEMENT_SEARCH_PHASE_INVALID", search_phase=search_phase)


def _entrance_anchors(
    entrance: SegmentMM, width_mm: int, depth_mm: int
) -> tuple[tuple[int, int], ...]:
    """Place a zone edge over an authoritative site entrance, without offsets."""
    (x1, y1), (x2, y2) = entrance
    anchors: set[tuple[int, int]] = set()
    if x1 == x2:
        low_y, high_y = sorted((y1, y2))
        aligned_y = {
            (low_y + high_y - depth_mm) // 2,
            low_y,
            high_y - depth_mm,
        }
        anchors.update((x1 - width_mm, y) for y in aligned_y)
        anchors.update((x1, y) for y in aligned_y)
    elif y1 == y2:
        low_x, high_x = sorted((x1, x2))
        aligned_x = {
            (low_x + high_x - width_mm) // 2,
            low_x,
            high_x - width_mm,
        }
        anchors.update((x, y1 - depth_mm) for x in aligned_x)
        anchors.update((x, y1) for x in aligned_x)
    return tuple(sorted(anchors))


def _truck_dock_events_at_entrance(context: _PlacementSearchContext) -> tuple[dict[str, Any], ...]:
    """Project final dock poses from the bound DOCK_REVERSE templates.

    Each record retains the authoritative template and entrance event that
    produced it. It is only a necessary shipping-interface construction fact;
    full truck feasibility is still decided by the injected validator.
    """
    binding = getattr(context, "truck_maneuver_binding", None)
    if binding is None:
        return ()
    project = getattr(binding, "maneuver_project_input", None)
    if project is None and isinstance(binding, Mapping):
        project_body = binding.get("maneuver_project_input")
        if isinstance(project_body, Mapping):
            template_set = project_body.get("template_set")
            templates = (
                template_set.get("templates", ()) if isinstance(template_set, Mapping) else ()
            )
        else:
            templates = ()
    else:
        template_set = getattr(project, "template_set", None)
        templates = getattr(template_set, "templates", ())

    entrance = _truck_segment(context.site_body)
    start, end = entrance
    if start[0] == end[0]:
        low, high = sorted((start[1], end[1]))
        entry_points = ((start[0], low), (start[0], (low + high) // 2), (start[0], high))
    else:
        low, high = sorted((start[0], end[0]))
        entry_points = ((low, start[1]), ((low + high) // 2, start[1]), (high, start[1]))

    events: dict[tuple[Any, ...], dict[str, Any]] = {}
    for template_index, template in enumerate(templates):
        maneuver_class = getattr(template, "maneuver_class", None)
        reference_frame = getattr(template, "reference_frame", None)
        dock_pose = getattr(template, "final_dock_pose", None)
        template_identity = getattr(template, "identity", None)
        template_id = getattr(template, "template_id", None)
        if isinstance(template, Mapping):
            maneuver_class = template.get("maneuver_class", maneuver_class)
            reference_frame = template.get("reference_frame", reference_frame)
            dock_pose = template.get("final_dock_pose", dock_pose)
            template_identity = template.get("identity", template_identity)
            template_id = template.get("template_id", template_id)
        if maneuver_class != "DOCK_REVERSE" or not isinstance(reference_frame, Mapping):
            continue
        entry_pose = reference_frame.get("entry_pose")
        if not isinstance(entry_pose, Mapping) or not isinstance(dock_pose, Mapping):
            continue
        entry = (
            _mm(entry_pose.get("x"), field="truck_template.entry_pose.x"),
            _mm(entry_pose.get("y"), field="truck_template.entry_pose.y"),
        )
        dock = (
            _mm(dock_pose.get("x"), field="truck_template.final_dock_pose.x"),
            _mm(dock_pose.get("y"), field="truck_template.final_dock_pose.y"),
        )
        for entry_point in entry_points:
            for rotation in (0, 90, 180, 270):
                rotated_entry = _rotate_orthogonal_mm(entry, rotation)
                rotated_dock = _rotate_orthogonal_mm(dock, rotation)
                translation = (
                    entry_point[0] - rotated_entry[0],
                    entry_point[1] - rotated_entry[1],
                )
                dock_point = (
                    translation[0] + rotated_dock[0],
                    translation[1] + rotated_dock[1],
                )
                identity = str(
                    template_identity or template_id or f"DOCK_REVERSE_TEMPLATE_{template_index}"
                )
                event = {
                    "dock_point_mm": dock_point,
                    "source_entry_point_mm": entry_point,
                    "source_template_identity": identity,
                    "source_template_rotation_deg": rotation,
                }
                events[
                    (
                        dock_point,
                        entry_point,
                        identity,
                        rotation,
                    )
                ] = event
    return tuple(events[key] for key in sorted(events))


def _truck_dock_points_at_entrance(context: _PlacementSearchContext) -> tuple[tuple[int, int], ...]:
    """Return the canonical unique points from the authoritative dock events."""
    return tuple(
        sorted({tuple(event["dock_point_mm"]) for event in _truck_dock_events_at_entrance(context)})
    )


def _rotate_orthogonal_mm(point: tuple[int, int], rotation_deg: int) -> tuple[int, int]:
    x, y = point
    if rotation_deg == 0:
        return x, y
    if rotation_deg == 90:
        return -y, x
    if rotation_deg == 180:
        return -x, -y
    return y, -x


def _shipping_rectangles_for_dock_events(
    context: _PlacementSearchContext,
) -> tuple[PlacedRectangleV1, ...]:
    """Create finite shipping-rectangle candidates whose loading face includes
    a dock-template point projected from the authoritative entrance events.
    Exact placement and truck feasibility are checked by existing predicates.
    """
    points = _truck_dock_points_at_entrance(context)
    if not points:
        return ()
    authority = context.authorities.get("shipping_channel")
    if authority is None:
        return ()
    candidates: dict[tuple[int, int, int, int], PlacedRectangleV1] = {}
    for width_mm, depth_mm, rotation in _dimension_variants(authority, {}, context.boundary):
        sample = _rectangle_from_mm("shipping_channel", 0, 0, width_mm, depth_mm, rotation)
        _, local_face, _, _ = _loading_face(sample, context.site_body)
        actual_width, actual_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        for dock_x, dock_y in points:
            if local_face[0][1] == local_face[1][1]:
                x_origins = {
                    dock_x,
                    dock_x - actual_width,
                    context.boundary_bounds[0],
                    context.boundary_bounds[2] - actual_width,
                }
                y_origin = dock_y - local_face[0][1]
                origins = ((x, y_origin) for x in sorted(x_origins))
            else:
                y_origins = {
                    dock_y,
                    dock_y - actual_depth,
                    context.boundary_bounds[1],
                    context.boundary_bounds[3] - actual_depth,
                }
                x_origin = dock_x - local_face[0][0]
                origins = ((x_origin, y) for y in sorted(y_origins))
            for x_mm, y_mm in origins:
                rectangle = _rectangle_from_mm(
                    "shipping_channel", x_mm, y_mm, width_mm, depth_mm, rotation
                )
                _, loading_face, _, _ = _loading_face(rectangle, context.site_body)
                if not _on_segment((dock_x, dock_y), loading_face[0], loading_face[1]):
                    continue
                if _geometry_rejection_reason(rectangle, {}, context) is not None:
                    continue
                candidates[_bounds(rectangle)] = rectangle
    return tuple(candidates[key] for key in sorted(candidates))


def _shipping_dock_anchors_at_entrance(
    context: _PlacementSearchContext,
) -> tuple[ShippingDockAnchorV1, ...]:
    """Bind exact legal shipping rectangles to the dock points on their face."""
    events = _truck_dock_events_at_entrance(context)
    rectangles = _shipping_rectangles_for_dock_events(context)
    anchors: dict[tuple[Any, ...], ShippingDockAnchorV1] = {}
    for rectangle in rectangles:
        face_side, face, _score, _comparison = _loading_face(rectangle, context.site_body)
        for event in events:
            dock_point = tuple(event["dock_point_mm"])
            if not _on_segment(dock_point, face[0], face[1]):
                continue
            anchor = ShippingDockAnchorV1(
                dock_point_mm=dock_point,
                shipping_rectangle=rectangle,
                loading_face_side=face_side,
                loading_face_segment_mm=face,
                shipping_rotation_deg=rectangle.rotation_deg,
                source_entry_point_mm=tuple(event["source_entry_point_mm"]),
                source_template_identity=str(event["source_template_identity"]),
                source_template_rotation_deg=int(event["source_template_rotation_deg"]),
            )
            key = (
                rectangle.bounds_mm,
                rectangle.rotation_deg,
                dock_point,
                anchor.source_template_identity,
                anchor.source_template_rotation_deg,
                anchor.source_entry_point_mm,
            )
            anchors[key] = anchor
    return tuple(anchors[key] for key in sorted(anchors))


def _shipping_dock_anchor_construction_representatives(
    anchors: Sequence[ShippingDockAnchorV1],
    *,
    limit: int = 12,
    truck_entrance_segment: SegmentMM | None = None,
) -> tuple[ShippingDockAnchorV1, ...]:
    """Select a deterministic cover of exact shipping geometries and dock events.

    Every distinct legal shipping rectangle is a construction representative
    before event-only extras are considered. Grouping only by dock point can
    discard a second rectangle on that same point, even though its loading-face
    location can leave a materially different site assembly. Prefer dock
    events whose approach crosses the entrance normally, then endpoint
    witnesses. Loading-face/approach parallelism is not an authority and does
    not outrank geometry coverage; the truck validator remains authoritative.
    """
    if limit <= 0 or not anchors:
        return ()

    def identity(anchor: ShippingDockAnchorV1) -> tuple[Any, ...]:
        return (
            anchor.shipping_rectangle.bounds_mm,
            anchor.shipping_rotation_deg,
            anchor.loading_face_side,
            anchor.dock_point_mm,
            anchor.source_template_identity,
            anchor.source_template_rotation_deg,
            anchor.source_entry_point_mm,
        )

    def geometry_identity(anchor: ShippingDockAnchorV1) -> tuple[Any, ...]:
        return (
            anchor.shipping_rectangle.bounds_mm,
            anchor.shipping_rotation_deg,
            anchor.loading_face_side,
        )

    def dock_event_identity(anchor: ShippingDockAnchorV1) -> tuple[Any, ...]:
        return (
            anchor.shipping_rotation_deg,
            anchor.loading_face_side,
            anchor.dock_point_mm,
            anchor.source_template_identity,
            anchor.source_template_rotation_deg,
            anchor.source_entry_point_mm,
        )

    entrance_is_vertical = (
        truck_entrance_segment is not None
        and truck_entrance_segment[0][0] == truck_entrance_segment[1][0]
    )
    entrance_is_horizontal = (
        truck_entrance_segment is not None
        and truck_entrance_segment[0][1] == truck_entrance_segment[1][1]
    )

    def geometry_order(anchor: ShippingDockAnchorV1) -> tuple[Any, ...]:
        entry_x, entry_y = anchor.source_entry_point_mm
        dock_x, dock_y = anchor.dock_point_mm
        approach_dx, approach_dy = dock_x - entry_x, dock_y - entry_y
        approach_crosses_entrance_normally = (
            entrance_is_vertical and approach_dy == 0 and approach_dx != 0
        ) or (entrance_is_horizontal and approach_dx == 0 and approach_dy != 0)
        dock_at_face_endpoint = anchor.dock_point_mm in {
            anchor.loading_face_segment_mm[0],
            anchor.loading_face_segment_mm[1],
        }
        return (
            0 if truck_entrance_segment is None or approach_crosses_entrance_normally else 1,
            0 if dock_at_face_endpoint else 1,
            anchor.shipping_rotation_deg,
            anchor.shipping_rectangle.bounds_mm,
            anchor.loading_face_side,
            anchor.dock_point_mm,
            anchor.source_template_identity,
            anchor.source_template_rotation_deg,
            anchor.source_entry_point_mm,
        )

    geometry_groups: dict[tuple[Any, ...], list[ShippingDockAnchorV1]] = {}
    dock_event_groups: dict[tuple[Any, ...], list[ShippingDockAnchorV1]] = {}
    for anchor in anchors:
        geometry_groups.setdefault(geometry_identity(anchor), []).append(anchor)
        dock_event_groups.setdefault(dock_event_identity(anchor), []).append(anchor)

    selected: list[ShippingDockAnchorV1] = []
    selected_keys: set[tuple[Any, ...]] = set()
    represented_events: set[tuple[Any, ...]] = set()
    for geometry_key in sorted(
        geometry_groups,
        key=lambda key: geometry_order(min(geometry_groups[key], key=geometry_order)),
    ):
        row = min(geometry_groups[geometry_key], key=geometry_order)
        selected.append(row)
        selected_keys.add(identity(row))
        represented_events.add(dock_event_identity(row))
        if len(selected) >= limit:
            return tuple(selected)

    # Preserve additional template/entrance events only after every distinct
    # legal shipping rectangle has a representative.
    for event_key in sorted(dock_event_groups):
        if event_key in represented_events:
            continue
        row = min(dock_event_groups[event_key], key=geometry_order)
        row_key = identity(row)
        if row_key in selected_keys:
            continue
        selected.append(row)
        selected_keys.add(row_key)
        represented_events.add(event_key)
        if len(selected) >= limit:
            return tuple(selected)

    for row in sorted(anchors, key=geometry_order):
        row_key = identity(row)
        if row_key in selected_keys:
            continue
        selected.append(row)
        selected_keys.add(row_key)
        if len(selected) >= limit:
            break
    return tuple(selected)


def _truck_entrance_for_dock_anchor_order(
    context: _PlacementSearchContext,
) -> SegmentMM | None:
    """Expose the entrance for ordering when a production context has it."""
    site_body = getattr(context, "site_body", None)
    return _truck_segment(site_body) if isinstance(site_body, Mapping) else None


def _shipping_dock_anchor_construction_limit(
    anchors: Sequence[ShippingDockAnchorV1],
) -> int:
    """Cover each exact legal shipping rectangle once in construction order."""
    rectangle_count = len(
        {
            (
                anchor.shipping_rectangle.bounds_mm,
                anchor.shipping_rotation_deg,
                anchor.loading_face_side,
            )
            for anchor in anchors
        }
    )
    return min(len(anchors), max(12, rectangle_count))


def _bounded_site_event_rectangles(
    rectangles: Sequence[PlacedRectangleV1], *, limit: int = 12
) -> tuple[PlacedRectangleV1, ...]:
    """Select a deterministic, spread sample of exact site-event rectangles.

    Site assembly must not expand the Cartesian product of every shipping
    event, module transform, interface face, and room alignment inside one
    placement quantum. The selected entries remain exact members of the
    authoritative event set; this is a bounded construction ordering, not a
    new truck-feasibility predicate.
    """
    if limit <= 0 or not rectangles:
        return ()
    ordered = tuple(sorted(rectangles, key=lambda row: (row.bounds_mm, row.rotation_deg)))
    if len(ordered) <= limit:
        return ordered
    if limit == 1:
        return (ordered[0],)
    last_index = len(ordered) - 1
    indices = tuple((index * last_index) // (limit - 1) for index in range(limit))
    return tuple(ordered[index] for index in indices)


def _finished_band_axis_reuse(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
) -> int:
    """Prefer exact reuse of the current process-band axes for finished goods."""
    if code != "finished_goods_room":
        return 0
    left, bottom, right, top = _bounds(rectangle)
    major_x_axes = {
        coordinate
        for placed_code, existing in placed.items()
        if placed_code
        in {
            "primary_precooling_room",
            "secondary_precooling_room",
            "sorting_packaging_room",
            "coating_room",
            "packaging_material_storage",
        }
        for coordinate in (_bounds(existing)[0], _bounds(existing)[2])
    }
    major_y_axes = {
        coordinate
        for placed_code, existing in placed.items()
        if placed_code
        in {
            "primary_precooling_room",
            "secondary_precooling_room",
            "sorting_packaging_room",
            "coating_room",
            "packaging_material_storage",
        }
        for coordinate in (_bounds(existing)[1], _bounds(existing)[3])
    }
    return sum(coordinate in major_x_axes for coordinate in (left, right)) + sum(
        coordinate in major_y_axes for coordinate in (bottom, top)
    )


def _support_group_edge_count(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
) -> int:
    """Prefer support-to-support grouping over spreading branches around the core."""
    if code not in SUPPORT_ZONE_CODES:
        return 0
    return sum(
        int(
            reference in SUPPORT_ZONE_CODES
            and reference in placed
            and rectangles_share_positive_edge(rectangle, placed[reference])
        )
        for reference in SUPPORT_ZONE_CODES
        if reference != code
    )


def _support_obstacle_x_alignment(
    code: str,
    rectangle: PlacedRectangleV1,
    obstacles: Sequence[PolygonMM],
) -> int:
    """Prefer the frozen-support block on an exact vertical site-constraint axis."""
    if code != "frozen_fruit_room":
        return 0
    obstacle_x = {point[0] for polygon in obstacles for point in polygon}
    left, _, right, _ = _bounds(rectangle)
    return sum(coordinate in obstacle_x for coordinate in (left, right))


def _support_process_axis_reuse(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
) -> int:
    """Count exact support-zone boundary incidences on established process axes."""
    if code not in SUPPORT_ZONE_CODES:
        return 0
    process_x_axes = {
        coordinate
        for process_code in MAIN_PROCESS_ZONE_CODES
        if process_code in placed
        for coordinate in (_bounds(placed[process_code])[0], _bounds(placed[process_code])[2])
    }
    process_y_axes = {
        coordinate
        for process_code in MAIN_PROCESS_ZONE_CODES
        if process_code in placed
        for coordinate in (_bounds(placed[process_code])[1], _bounds(placed[process_code])[3])
    }
    left, bottom, right, top = _bounds(rectangle)
    return sum(coordinate in process_x_axes for coordinate in (left, right)) + sum(
        coordinate in process_y_axes for coordinate in (bottom, top)
    )


def _linear_flow_anchor_matches(
    rectangle: PlacedRectangleV1,
    predecessor: PlacedRectangleV1,
    family: StructuralCompositionFamilyV1,
) -> bool:
    first = _bounds(predecessor)
    second = _bounds(rectangle)
    if family.dominant_axis == "X":
        if not (first[2] == second[0] or second[2] == first[0]):
            return False
        if min(first[3], second[3]) <= max(first[1], second[1]):
            return False
        delta = second[0] + second[2] - first[0] - first[2]
    else:
        if not (first[3] == second[1] or second[3] == first[1]):
            return False
        if min(first[2], second[2]) <= max(first[0], second[0]):
            return False
        delta = second[1] + second[3] - first[1] - first[3]
    return (delta > 0 and family.dominant_direction == "POSITIVE") or (
        delta < 0 and family.dominant_direction == "NEGATIVE"
    )


def _structural_linear_predecessor(code: str) -> str | None:
    """Return the spatial predecessor used by each generated process band."""
    predecessors = {
        "primary_precooling_room": "raw_fruit_buffer",
        "sorting_packaging_room": "primary_precooling_room",
        # The secondary room is the downstream transition from sorting.
        # Coating is a core-side interface adjacent to both, not a serial
        # room on the dominant axis.
        "secondary_precooling_room": "sorting_packaging_room",
        "shipping_channel": "finished_goods_room",
    }
    return predecessors.get(code)


def _linear_group_flow_anchor_matches(
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    group_zone_codes: Sequence[str],
    family: StructuralCompositionFamilyV1,
) -> bool:
    """Require contact at the exact downstream face of an already placed group."""
    targets = tuple(placed[code] for code in group_zone_codes if code in placed)
    if not targets:
        return False
    candidate = _bounds(rectangle)
    target_bounds = tuple(_bounds(target) for target in targets)
    if family.dominant_axis == "X":
        if family.dominant_direction == "POSITIVE":
            terminal = max(bounds[2] for bounds in target_bounds)
            return candidate[0] == terminal and any(
                bounds[2] == terminal
                and min(candidate[3], bounds[3]) > max(candidate[1], bounds[1])
                for bounds in target_bounds
            )
        terminal = min(bounds[0] for bounds in target_bounds)
        return candidate[2] == terminal and any(
            bounds[0] == terminal and min(candidate[3], bounds[3]) > max(candidate[1], bounds[1])
            for bounds in target_bounds
        )
    if family.dominant_direction == "POSITIVE":
        terminal = max(bounds[3] for bounds in target_bounds)
        return candidate[1] == terminal and any(
            bounds[3] == terminal and min(candidate[2], bounds[2]) > max(candidate[0], bounds[0])
            for bounds in target_bounds
        )
    terminal = min(bounds[1] for bounds in target_bounds)
    return candidate[3] == terminal and any(
        bounds[1] == terminal and min(candidate[2], bounds[2]) > max(candidate[0], bounds[0])
        for bounds in target_bounds
    )


def _adjacent_side(reference: PlacedRectangleV1, candidate: PlacedRectangleV1) -> str | None:
    """Return candidate's exact cardinal side when it shares a positive edge."""
    first = _bounds(reference)
    second = _bounds(candidate)
    if first[2] == second[0] and min(first[3], second[3]) > max(first[1], second[1]):
        return "EAST"
    if first[0] == second[2] and min(first[3], second[3]) > max(first[1], second[1]):
        return "WEST"
    if first[3] == second[1] and min(first[2], second[2]) > max(first[0], second[0]):
        return "NORTH"
    if first[1] == second[3] and min(first[2], second[2]) > max(first[0], second[0]):
        return "SOUTH"
    return None


def _candidate_fits_skeleton_region(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    skeleton: StructuralSkeletonV1,
) -> bool:
    """Apply group-to-band projection order while each group is generated."""
    group = functional_group_for_zone(code)
    if group == SUPPORT_GROUP:
        # The support region is a search preference, not a new engineering
        # hard constraint. Its exact face/attachment facts are ranked below;
        # general fallback remains available for constrained sites.
        return True
    if group not in {RAW_SIDE_GROUP, PROCESSING_CORE_GROUP, FINISHED_SIDE_GROUP}:
        return True

    axis = skeleton.ordering_axis
    low_index, high_index = (0, 2) if axis == "X" else (1, 3)
    candidate_bounds = _bounds(rectangle)
    candidate_interval = (candidate_bounds[low_index], candidate_bounds[high_index])

    def interval(group_name: str) -> tuple[int, int] | None:
        values = [
            _bounds(existing)
            for zone_code, existing in placed.items()
            if functional_group_for_zone(zone_code) == group_name
        ]
        if not values:
            return None
        return min(row[low_index] for row in values), max(row[high_index] for row in values)

    raw_interval = interval(RAW_SIDE_GROUP)
    core_interval = interval(PROCESSING_CORE_GROUP)
    finished_interval = interval(FINISHED_SIDE_GROUP)
    if skeleton.family.family == "LINEAR_PROCESS_BAND":
        sorting = placed.get("sorting_packaging_room")
        secondary = placed.get("secondary_precooling_room")
        finished = placed.get("finished_goods_room")
        if code == "secondary_precooling_room":
            return sorting is not None and _linear_flow_anchor_matches(
                rectangle, sorting, skeleton.family
            )
        if code == "coating_room":
            return (
                sorting is not None
                and secondary is not None
                and rectangles_share_positive_edge(rectangle, sorting)
                and rectangles_share_positive_edge(rectangle, secondary)
            )
        if code == "finished_goods_room":
            return _linear_group_flow_anchor_matches(
                rectangle,
                placed,
                ("secondary_precooling_room", "coating_room"),
                skeleton.family,
            )
        if code == "shipping_channel":
            return finished is not None and _linear_flow_anchor_matches(
                rectangle, finished, skeleton.family
            )
    if group == RAW_SIDE_GROUP:
        if skeleton.family.family == "CENTRAL_PROCESS_HUB":
            sorting = placed.get("sorting_packaging_room")
            if code == "primary_precooling_room":
                if sorting is None:
                    return False
                occupied_core_sides = {
                    side
                    for zone_code in ("coating_room", "secondary_precooling_room")
                    if (zone := placed.get(zone_code)) is not None
                    if (side := _adjacent_side(sorting, zone)) is not None
                }
                primary_side = _adjacent_side(sorting, rectangle)
                return primary_side is not None and primary_side not in occupied_core_sides
            if code == "raw_fruit_buffer":
                primary = placed.get("primary_precooling_room")
                if sorting is None or primary is None:
                    return False
                primary_side = _adjacent_side(sorting, primary)
                raw_side = _adjacent_side(primary, rectangle)
                if primary_side is None or raw_side is None:
                    return False
                # The raw buffer may continue along the raw band or attach
                # laterally to the primary room, but cannot be placed on the
                # face that points back into the sorting core.
                toward_core = {
                    "NORTH": "SOUTH",
                    "SOUTH": "NORTH",
                    "EAST": "WEST",
                    "WEST": "EAST",
                }[primary_side]
                if raw_side == toward_core:
                    return False
                primary_bounds = _bounds(primary)
                if core_interval is None:
                    return False
                primary_interval = (
                    primary_bounds[low_index],
                    primary_bounds[high_index],
                )
                if primary_interval[1] <= core_interval[0]:
                    return candidate_interval[1] <= core_interval[0]
                if primary_interval[0] >= core_interval[1]:
                    return candidate_interval[0] >= core_interval[1]
                return False
        if code == "primary_precooling_room":
            if core_interval is None:
                # LINEAR lanes grow raw -> core. At this point the raw room
                # has been placed, while the core is intentionally not yet
                # present; exact MUST adjacency is checked independently.
                return (
                    skeleton.family.family == "LINEAR_PROCESS_BAND" and "raw_fruit_buffer" in placed
                )
            if skeleton.family.family == "LINEAR_PROCESS_BAND":
                if skeleton.family.dominant_direction == "POSITIVE":
                    return candidate_interval[1] <= core_interval[0]
                return candidate_interval[0] >= core_interval[1]
            # The hub lane permits either exact side of the core; the raw
            # buffer is subsequently constrained to continue outward from the
            # selected primary-precooling side.
            return (
                candidate_interval[1] <= core_interval[0]
                or candidate_interval[0] >= core_interval[1]
            )
        if code == "raw_fruit_buffer":
            primary = placed.get("primary_precooling_room")
            if primary is None:
                # In the linear skeleton the raw buffer is the deterministic
                # boundary-root zone, so it is generated before its primary
                # precooling attachment and before the process core exists.
                return skeleton.family.family == "LINEAR_PROCESS_BAND"
            if core_interval is None:
                return False
            # The raw group is a band, not a single-file chain. Its buffer
            # may attach to the primary room on a transverse face as long as
            # the complete raw-group projection remains upstream of the core.
            primary_bounds = _bounds(primary)
            primary_interval = (primary_bounds[low_index], primary_bounds[high_index])
            if primary_interval[1] <= core_interval[0]:
                return candidate_interval[1] <= core_interval[0]
            if primary_interval[0] >= core_interval[1]:
                return candidate_interval[0] >= core_interval[1]
            return False
        return False
    if group == PROCESSING_CORE_GROUP:
        if core_interval is not None:
            sorting = placed.get("sorting_packaging_room")
            if sorting is None or code != "coating_room":
                return False
            # Sorting is the core anchor; the smaller coating function joins
            # one of its free faces.  Requiring it to span the full process
            # axis made it consume an entire end face and frequently stranded
            # the frozen finished-goods adjacency.  This is an exact shared
            # edge predicate, not a route proxy or a relaxation of P2D.
            # The coating function may bridge a sorting-hall face to the
            # secondary-precooling interface. It remains part of the core
            # when it shares a real edge with sorting; containment within the
            # hall's long-axis projection is not a frozen engineering rule.
            return rectangles_share_positive_edge(rectangle, sorting)
        if skeleton.family.family == "LINEAR_PROCESS_BAND":
            # The linear skeleton deliberately generates RAW before CORE.
            # Require the sorting root to continue in the lane's frozen
            # direction from the already placed raw-side envelope.
            if code != "sorting_packaging_room" or raw_interval is None:
                return False
            if skeleton.family.dominant_direction == "POSITIVE":
                return raw_interval[1] <= candidate_interval[0]
            return candidate_interval[1] <= raw_interval[0]
        # The processing core is the structural skeleton root. It is placed
        # before raw/finished bands so those groups organize around its actual
        # feasible envelope instead of biasing it into residual space.
        return (
            code == "sorting_packaging_room" and raw_interval is None and finished_interval is None
        )
    if core_interval is None:
        return False
    if skeleton.family.family == "CENTRAL_PROCESS_HUB":
        return True
    if code == "secondary_precooling_room":
        # P2D freezes secondary precooling between sorting and coating, while
        # P1A places coating inside the process-core envelope. Keep secondary
        # precooling as the explicit spatial interface to the core.  It is a
        # transition zone, not a reason to force the finished-goods room past
        # the entire core projection.
        return True
    if raw_interval is None:
        return False
    downstream = _structural_downstream_direction(skeleton, raw_interval, core_interval)
    if downstream is None:
        return False
    finished = placed.get("finished_goods_room")
    if code == "finished_goods_room":
        # The frozen P2D graph requires this room to share edges with both
        # coating and secondary precooling.  Its band therefore starts at the
        # core interface and extends downstream; requiring full interval
        # separation would make those unchanged hard adjacencies impossible.
        return (
            candidate_interval[1] > core_interval[1]
            if downstream == "POSITIVE"
            else candidate_interval[0] < core_interval[0]
        )
    if code == "shipping_channel" and finished is not None:
        # Shipping is an interface attached to finished goods, not another
        # serial room whose full rectangle must sit beyond the goods interval.
        # Keep it on the downstream side of the process core; the final
        # finished-group envelope check verifies the group order.
        return (
            candidate_interval[1] > core_interval[1]
            if downstream == "POSITIVE"
            else candidate_interval[0] < core_interval[0]
        )
    return (
        candidate_interval[0] >= core_interval[1]
        if downstream == "POSITIVE"
        else candidate_interval[1] <= core_interval[0]
    )


def _structural_downstream_direction(
    skeleton: StructuralSkeletonV1,
    raw_interval: tuple[int, int] | None,
    core_interval: tuple[int, int] | None,
) -> str | None:
    if skeleton.family.family == "LINEAR_PROCESS_BAND":
        return skeleton.family.dominant_direction
    if raw_interval is None or core_interval is None:
        return None
    if raw_interval[1] <= core_interval[0]:
        return "POSITIVE"
    if core_interval[1] <= raw_interval[0]:
        return "NEGATIVE"
    return None


def _rectangle_touches_boundary(rectangle: PlacedRectangleV1, boundary: PolygonMM) -> bool:
    left, bottom, right, top = _bounds(rectangle)
    rectangle_edges = (
        ((left, bottom), (right, bottom)),
        ((right, bottom), (right, top)),
        ((right, top), (left, top)),
        ((left, top), (left, bottom)),
    )
    for site_start, site_end in zip(boundary, boundary[1:] + boundary[:1], strict=True):
        for room_start, room_end in rectangle_edges:
            if segments_share_positive_length(site_start, site_end, room_start, room_end):
                return True
    return False


def _cross(a: tuple[int, int], b: tuple[int, int], c: tuple[int, int]) -> int:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(point: tuple[int, int], start: tuple[int, int], end: tuple[int, int]) -> bool:
    return (
        _cross(start, end, point) == 0
        and min(start[0], end[0]) <= point[0] <= max(start[0], end[0])
        and min(start[1], end[1]) <= point[1] <= max(start[1], end[1])
    )


def _segments_intersect(
    first_start: tuple[int, int],
    first_end: tuple[int, int],
    second_start: tuple[int, int],
    second_end: tuple[int, int],
) -> bool:
    first_a = _cross(first_start, first_end, second_start)
    first_b = _cross(first_start, first_end, second_end)
    second_a = _cross(second_start, second_end, first_start)
    second_b = _cross(second_start, second_end, first_end)
    return (
        ((first_a > 0 > first_b) or (first_a < 0 < first_b))
        and ((second_a > 0 > second_b) or (second_a < 0 < second_b))
    ) or (
        (first_a == 0 and _on_segment(second_start, first_start, first_end))
        or (first_b == 0 and _on_segment(second_end, first_start, first_end))
        or (second_a == 0 and _on_segment(first_start, second_start, second_end))
        or (second_b == 0 and _on_segment(first_end, second_start, second_end))
    )


def _point_segment_distance_squared(
    point: tuple[int, int], start: tuple[int, int], end: tuple[int, int]
) -> Fraction:
    vector_x = end[0] - start[0]
    vector_y = end[1] - start[1]
    length_squared = vector_x * vector_x + vector_y * vector_y
    if length_squared == 0:
        return Fraction((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2)
    offset_x = point[0] - start[0]
    offset_y = point[1] - start[1]
    projection = Fraction(offset_x * vector_x + offset_y * vector_y, length_squared)
    projection = max(Fraction(0), min(Fraction(1), projection))
    delta_x = Fraction(point[0]) - (Fraction(start[0]) + projection * vector_x)
    delta_y = Fraction(point[1]) - (Fraction(start[1]) + projection * vector_y)
    return delta_x * delta_x + delta_y * delta_y


def segment_distance_squared(first: SegmentMM, second: SegmentMM) -> Fraction:
    """Exact squared distance in integer-mm units; no sqrt or epsilon."""
    if _segments_intersect(first[0], first[1], second[0], second[1]):
        return Fraction(0)
    return min(
        _point_segment_distance_squared(first[0], second[0], second[1]),
        _point_segment_distance_squared(first[1], second[0], second[1]),
        _point_segment_distance_squared(second[0], first[0], first[1]),
        _point_segment_distance_squared(second[1], first[0], first[1]),
    )


def _long_edges(rectangle: PlacedRectangleV1) -> tuple[tuple[str, SegmentMM], ...]:
    left, bottom, right, top = _bounds(rectangle)
    width_mm = _mm(rectangle.width_m, field="width_m", positive=True)
    depth_mm = _mm(rectangle.depth_m, field="depth_m", positive=True)
    width_is_long = width_mm >= depth_mm
    horizontal_long_edges = (width_is_long and rectangle.rotation_deg == 0) or (
        not width_is_long and rectangle.rotation_deg == 90
    )
    if horizontal_long_edges:
        return (
            ("BOTTOM_LONG_EDGE", ((left, bottom), (right, bottom))),
            ("TOP_LONG_EDGE", ((left, top), (right, top))),
        )
    return (
        ("LEFT_LONG_EDGE", ((left, bottom), (left, top))),
        ("RIGHT_LONG_EDGE", ((right, bottom), (right, top))),
    )


def _truck_segment(site_body: Mapping[str, Any]) -> SegmentMM:
    entrances = site_body.get("entrances")
    if not isinstance(entrances, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="entrances")
    value = entrances.get("truck_entrance")
    if not isinstance(value, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="truck_entrance")
    try:
        numeric = {
            "start": {
                "x": Decimal(str(value["start"]["x"])),
                "y": Decimal(str(value["start"]["y"])),
            },
            "end": {
                "x": Decimal(str(value["end"]["x"])),
                "y": Decimal(str(value["end"]["y"])),
            },
        }
    except (KeyError, TypeError, InvalidOperation, ValueError):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="truck_entrance") from None
    return normalize_segment(numeric, error_code="INVALID_SITE_GEOMETRY_RESULT")


def _main_entrance_segment(site_body: Mapping[str, Any]) -> SegmentMM:
    entrances = site_body.get("entrances")
    if not isinstance(entrances, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="entrances")
    value = entrances.get("main_entrance")
    if not isinstance(value, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="main_entrance")
    try:
        numeric = {
            "start": {
                "x": Decimal(str(value["start"]["x"])),
                "y": Decimal(str(value["start"]["y"])),
            },
            "end": {
                "x": Decimal(str(value["end"]["x"])),
                "y": Decimal(str(value["end"]["y"])),
            },
        }
    except (KeyError, TypeError, InvalidOperation, ValueError):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="main_entrance") from None
    return normalize_segment(numeric, error_code="INVALID_SITE_GEOMETRY_RESULT")


def _loading_face(
    rectangle: PlacedRectangleV1, site_body: Mapping[str, Any]
) -> tuple[str, SegmentMM, dict[str, Any], tuple[Any, ...]]:
    preferred = site_body.get("site", {}).get("preferred_loading_side", "UNSPECIFIED")
    edges = _long_edges(rectangle)
    if not isinstance(preferred, str):
        raise _error("INVALID_LOADING_SIDE")
    comparison: tuple[Any, ...]
    if preferred in {"NORTH", "EAST", "SOUTH", "WEST"}:
        side_by_cardinal = {
            "BOTTOM_LONG_EDGE": "SOUTH",
            "TOP_LONG_EDGE": "NORTH",
            "LEFT_LONG_EDGE": "WEST",
            "RIGHT_LONG_EDGE": "EAST",
        }
        matching = [row for row in edges if side_by_cardinal[row[0]] == preferred]
        selected = matching[0] if matching else edges[0]
        score = {"mode": CARDINAL_LOADING_SIDE_METRIC, "match": bool(matching)}
        comparison = (1 if matching else 0,)
    elif preferred == "NEAREST_TRUCK_ENTRANCE":
        truck = _truck_segment(site_body)
        selected = min(
            edges,
            key=lambda row: (segment_distance_squared(row[1], truck), row[0]),
        )
        distance = segment_distance_squared(selected[1], truck)
        score = {
            "mode": "MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE",
            "distance_squared_mm2": str(distance),
            "comparator": NEAREST_TRUCK_ENTRANCE_COMPARATOR,
            "internal_unit": NEAREST_TRUCK_ENTRANCE_INTERNAL_UNIT,
        }
        comparison = (-distance,)
    elif preferred == "UNSPECIFIED":
        selected = edges[0]
        score = {"mode": "DISABLED"}
        comparison = ()
    else:
        raise _error("INVALID_LOADING_SIDE")
    return selected[0], selected[1], score, comparison


def _pair_rows(
    pairs: Sequence[tuple[str, str]], placed: Mapping[str, PlacedRectangleV1]
) -> tuple[list[list[str]], list[list[str]]]:
    satisfied: list[list[str]] = []
    unsatisfied: list[list[str]] = []
    for pair in pairs:
        row = [pair[0], pair[1]]
        if rectangles_share_positive_edge(placed[pair[0]], placed[pair[1]]):
            satisfied.append(row)
        else:
            unsatisfied.append(row)
    return satisfied, unsatisfied


def _zone_record(authority: Mapping[str, Any], rectangle: PlacedRectangleV1) -> dict[str, Any]:
    code = _authority_code(authority)
    mode = _authority_mode(authority)
    required = _required_area(authority)
    if mode == "FLEXIBLE_RECTANGLE":
        if rectangle.actual_area_m2 < required:
            raise _error("FLEXIBLE_DIMENSION_AREA_UNSATISFIED", zone_code=code)
    else:
        geometry = authority.get("geometry")
        if not isinstance(geometry, Mapping):
            raise _error("DIMENSION_AUTHORITY_REQUIRED", zone_code=code)
        if _mm(geometry.get("width_m"), field="width_m", positive=True) != _mm(
            rectangle.width_m, field="width_m", positive=True
        ) or _mm(geometry.get("depth_m"), field="depth_m", positive=True) != _mm(
            rectangle.depth_m, field="depth_m", positive=True
        ):
            raise _error("FIXED_DIMENSION_RESIZE_FORBIDDEN", zone_code=code)
    return {
        "zone_code": code,
        "dimension_mode": mode,
        "required_area_m2": required,
        "x": rectangle.x,
        "y": rectangle.y,
        "width_m": rectangle.width_m,
        "depth_m": rectangle.depth_m,
        "actual_area_m2": rectangle.actual_area_m2,
        "rotation_deg": rectangle.rotation_deg,
        "dimension_authority_identity": authority.get("dimension_authority_identity"),
        "dimensioning_authority": authority.get("authority", "P1_PROJECT_HANDOFF"),
        "capacity_geometry_reference": authority.get("source_zone_hash"),
        "area_requirement": authority.get("area_requirement"),
    }


def _rectangle_edge_segments(
    rectangle: PlacedRectangleV1,
) -> dict[str, tuple[SegmentMM, ...]]:
    """Return relative long/short edge classes for observable evidence only."""
    left, bottom, right, top = _bounds(rectangle)
    width_mm = _mm(rectangle.width_m, field="width_m", positive=True)
    depth_mm = _mm(rectangle.depth_m, field="depth_m", positive=True)
    width_is_long = width_mm >= depth_mm
    horizontal_long_edges = (width_is_long and rectangle.rotation_deg == 0) or (
        not width_is_long and rectangle.rotation_deg == 90
    )
    horizontal = (
        ((left, bottom), (right, bottom)),
        ((left, top), (right, top)),
    )
    vertical = (
        ((left, bottom), (left, top)),
        ((right, bottom), (right, top)),
    )
    if horizontal_long_edges:
        return {"LONG_EDGE": horizontal, "SHORT_EDGE": vertical}
    return {"LONG_EDGE": vertical, "SHORT_EDGE": horizontal}


def _named_rectangle_edge_classes(
    rectangle: PlacedRectangleV1,
) -> tuple[tuple[str, str, SegmentMM], ...]:
    """Return cardinal rectangle edges paired with existing long/short classes."""
    left, bottom, right, top = _bounds(rectangle)
    named_edges = (
        ("LEFT", ((left, bottom), (left, top))),
        ("RIGHT", ((right, bottom), (right, top))),
        ("BOTTOM", ((left, bottom), (right, bottom))),
        ("TOP", ((left, top), (right, top))),
    )
    class_segments = _rectangle_edge_segments(rectangle)
    long_keys = {tuple(sorted(segment)) for segment in class_segments["LONG_EDGE"]}
    return tuple(
        (
            side,
            "LONG_EDGE" if tuple(sorted(segment)) in long_keys else "SHORT_EDGE",
            segment,
        )
        for side, segment in named_edges
    )


def _segment_overlap_length_mm(first: SegmentMM, second: SegmentMM) -> int:
    if first[0][1] == first[1][1] == second[0][1] == second[1][1]:
        return max(0, min(first[1][0], second[1][0]) - max(first[0][0], second[0][0]))
    if first[0][0] == first[1][0] == second[0][0] == second[1][0]:
        return max(0, min(first[1][1], second[1][1]) - max(first[0][1], second[0][1]))
    return 0


def _edge_orientation_facts(
    requirement: Mapping[str, Any],
    relationship: Mapping[str, Any] | None,
    placed: Mapping[str, PlacedRectangleV1],
) -> dict[str, Any]:
    """Observe P1 edge classes without validating a route or portal."""
    facts: dict[str, Any] = {
        "edge_orientation_observable": False,
        "edge_orientation_satisfied": None,
        "required_edge_orientation_observable": False,
        "required_edge_orientation_satisfied": None,
    }
    if relationship is None:
        return facts
    from_ref = requirement.get("from_ref")
    to_ref = requirement.get("to_ref")
    from_rectangle = placed.get(from_ref) if isinstance(from_ref, str) else None
    to_rectangle = placed.get(to_ref) if isinstance(to_ref, str) else None
    if from_rectangle is None or to_rectangle is None:
        return facts
    expected_from = relationship.get("from_edge_class")
    expected_to = relationship.get("to_edge_class")
    facts["edge_orientation_contract"] = {
        "identity": relationship.get("identity"),
        "from_edge_class": expected_from,
        "to_edge_class": expected_to,
    }
    matched: list[dict[str, Any]] = []
    from_edges = _rectangle_edge_segments(from_rectangle)
    to_edges = _rectangle_edge_segments(to_rectangle)
    for from_class, from_segments in from_edges.items():
        for to_class, to_segments in to_edges.items():
            for from_segment in from_segments:
                for to_segment in to_segments:
                    overlap = _segment_overlap_length_mm(from_segment, to_segment)
                    if overlap > 0 and segments_share_positive_length(
                        from_segment[0], from_segment[1], to_segment[0], to_segment[1]
                    ):
                        matched.append(
                            {
                                "from_edge_class": from_class,
                                "to_edge_class": to_class,
                                "shared_positive_edge_length_mm": overlap,
                            }
                        )
    facts["edge_orientation_observable"] = bool(matched)
    facts["edge_orientation_matches"] = matched
    facts["edge_orientation_satisfied"] = any(
        row["from_edge_class"] == expected_from
        and (
            row["to_edge_class"] == expected_to
            or (expected_to == "SHORT_EDGE_EXIT_SIDE" and row["to_edge_class"] == "SHORT_EDGE")
            or (expected_to == "LONG_EDGE_LOADING_FACE" and row["to_edge_class"] == "LONG_EDGE")
        )
        for row in matched
    )
    facts["required_edge_orientation_observable"] = facts["edge_orientation_observable"]
    facts["required_edge_orientation_satisfied"] = facts["edge_orientation_satisfied"]
    return facts


def _access_observations(
    access_requirements: Sequence[Mapping[str, Any]],
    spatial_relationships: Sequence[Mapping[str, Any]],
    placed: Mapping[str, PlacedRectangleV1],
    loading_face: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    relationships = {
        relationship.get("identity"): relationship
        for relationship in spatial_relationships
        if isinstance(relationship, Mapping) and isinstance(relationship.get("identity"), str)
    }
    preserved_fields = (
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
        "cold_room_refs",
        "cold_room_portal_profile_identity",
        "source_authority",
    )
    for requirement in access_requirements:
        from_ref = requirement.get("from_ref")
        to_ref = requirement.get("to_ref")
        from_rectangle = placed.get(from_ref) if isinstance(from_ref, str) else None
        to_rectangle = placed.get(to_ref) if isinstance(to_ref, str) else None
        shared = bool(
            from_rectangle is not None
            and to_rectangle is not None
            and rectangles_share_positive_edge(from_rectangle, to_rectangle)
        )
        facts: dict[str, Any] = {
            "direct_shared_edge_observed": shared,
            "shared_positive_edge_length_mm": 0,
        }
        if from_rectangle is not None and to_rectangle is not None:
            from_edges = _rectangle_edge_segments(from_rectangle)
            to_edges = _rectangle_edge_segments(to_rectangle)
            facts["shared_positive_edge_length_mm"] = max(
                (
                    _segment_overlap_length_mm(first, second)
                    for first_segments in from_edges.values()
                    for first in first_segments
                    for second_segments in to_edges.values()
                    for second in second_segments
                ),
                default=0,
            )
        requirement_identity = requirement.get("identity")
        relationship = relationships.get(requirement.get("edge_orientation_requirement"))
        if requirement.get("edge_orientation_requirement") is not None:
            facts.update(_edge_orientation_facts(requirement, relationship, placed))
        if from_ref == "truck_entrance":
            facts.update(
                {
                    "shipping_loading_face_selected": loading_face["side"],
                    "shipping_loading_face_segment_observed": True,
                    "shipping_loading_face_segment": {
                        "start": {
                            "x": _m(loading_face["segment"][0][0]),
                            "y": _m(loading_face["segment"][0][1]),
                        },
                        "end": {
                            "x": _m(loading_face["segment"][1][0]),
                            "y": _m(loading_face["segment"][1][1]),
                        },
                    },
                }
            )
        rows.append(
            {
                "observation_id": requirement_identity,
                "requirement_identity": requirement_identity,
                **{field: requirement[field] for field in preserved_fields if field in requirement},
                "status": "PENDING_ROUTE_VALIDATION",
                "observable_facts": facts,
            }
        )
    return sorted(rows, key=lambda row: (row["from_ref"], row["to_ref"], row["flow_kind"]))


def _candidate_payload(
    placed: Mapping[str, PlacedRectangleV1],
    authorities: Mapping[str, Mapping[str, Any]],
    graph: AdjacencyGraphV1,
    site_body: Mapping[str, Any],
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    source_objective_profile_hash: str,
    access_requirements: Sequence[Mapping[str, Any]],
    spatial_relationships: Sequence[Mapping[str, Any]],
    search_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    zones = [_zone_record(authorities[code], placed[code]) for code in sorted(placed)]
    must_satisfied, must_unsatisfied = _pair_rows(graph.must_adjacencies, placed)
    should_satisfied, should_unsatisfied = _pair_rows(graph.should_adjacencies, placed)
    shipping_side, shipping_segment, loading_score, loading_comparison = _loading_face(
        placed["shipping_channel"], site_body
    )
    preferred = site_body["site"]["preferred_loading_side"]
    objective_vector: dict[str, Any] = {
        "aggregation": "LEXICOGRAPHIC",
        "priority_order": [SHOULD_ADJACENT, LOADING_SIDE_PREFERENCE],
        "should_adjacency": {
            "satisfied_count": len(should_satisfied),
            "total_count": len(graph.should_adjacencies),
            "satisfied_pairs": should_satisfied,
            "unsatisfied_pairs": should_unsatisfied,
        },
        "loading_side": {
            "preferred_loading_side": preferred,
            **loading_score,
        },
    }
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "placement_result_identity": PLACEMENT_RESULT_IDENTITY,
        "source_zone_plan_hash": source_zone_plan_hash,
        "source_p1_handoff_hash": source_p1_handoff_hash,
        "source_site_geometry_hash": source_site_geometry_hash,
        "source_objective_profile_hash": source_objective_profile_hash,
        "zone_count": len(zones),
        "placement_access_requirement_count": len(access_requirements),
        "zones": zones,
        "shipping_loading_face_side": shipping_side,
        "shipping_loading_face_segment": {
            "start": {"x": _m(shipping_segment[0][0]), "y": _m(shipping_segment[0][1])},
            "end": {"x": _m(shipping_segment[1][0]), "y": _m(shipping_segment[1][1])},
        },
        "must_adjacency_evaluation": {
            "hard_constraints_passed": not must_unsatisfied,
            "satisfied_count": len(must_satisfied),
            "required_count": len(graph.must_adjacencies),
            "satisfied_pairs": must_satisfied,
            "violations": [
                {"code": "HARD_CONSTRAINT_UNSATISFIABLE", "zones": pair}
                for pair in must_unsatisfied
            ],
        },
        "placement_hard_constraints_passed": not must_unsatisfied,
        "should_adjacency_evaluation": {
            "satisfied_count": len(should_satisfied),
            "required_count": len(graph.should_adjacencies),
            "satisfied_pairs": should_satisfied,
            "unsatisfied_pairs": should_unsatisfied,
        },
        "placement_access_observations": _access_observations(
            access_requirements,
            spatial_relationships,
            placed,
            {"side": shipping_side, "segment": shipping_segment},
        ),
        "placement_objective_vector": objective_vector,
        "search_provenance": dict(search_provenance),
    }
    # Keep this local variable in the payload construction so the exact
    # comparator input is explicit and never confused with the candidate hash.
    candidate["_loading_comparison"] = list(loading_comparison)
    return candidate


def _is_better(
    candidate: Mapping[str, Any], best: Mapping[str, Any] | None, preferred_loading_side: str
) -> bool:
    if best is None:
        return True
    business_comparison = compare_placement_candidate_business_objectives(
        candidate, best, preferred_loading_side
    )
    if business_comparison != 0:
        return business_comparison > 0
    return placement_candidate_canonical_tiebreak_key(candidate) < (
        placement_candidate_canonical_tiebreak_key(best)
    )


def compare_placement_candidate_business_objectives(
    candidate: Mapping[str, Any], best: Mapping[str, Any], preferred_loading_side: str
) -> int:
    """Compare only authorized P2B2 objectives, excluding deterministic fallback."""
    candidate_vector = candidate["placement_objective_vector"]
    best_vector = best["placement_objective_vector"]
    candidate_should = int(candidate_vector["should_adjacency"]["satisfied_count"])
    best_should = int(best_vector["should_adjacency"]["satisfied_count"])
    if candidate_should != best_should:
        return 1 if candidate_should > best_should else -1
    if preferred_loading_side in {"NORTH", "EAST", "SOUTH", "WEST"}:
        candidate_match = bool(candidate_vector["loading_side"].get("match"))
        best_match = bool(best_vector["loading_side"].get("match"))
        if candidate_match != best_match:
            return 1 if candidate_match else -1
    elif preferred_loading_side == "NEAREST_TRUCK_ENTRANCE":
        candidate_distance = Fraction(str(candidate_vector["loading_side"]["distance_squared_mm2"]))
        best_distance = Fraction(str(best_vector["loading_side"]["distance_squared_mm2"]))
        if candidate_distance != best_distance:
            return 1 if candidate_distance < best_distance else -1
    return 0


def placement_candidate_canonical_tiebreak_key(candidate: Mapping[str, Any]) -> str:
    """Return stable serialization used only after all objectives compare equal."""
    return canonical_json(
        {
            key: value
            for key, value in candidate.items()
            if key
            not in {
                "_loading_comparison",
                "search_provenance",
                "canonical_candidate_hash",
                "canonical_result_hash",
                "_structural_generation_flag",
                "_structural_composition_family",
            }
        }
    )


def _validate_graph_completeness(
    graph: AdjacencyGraphV1, placed: Mapping[str, PlacedRectangleV1]
) -> None:
    if set(placed) != set(graph.nodes):
        raise _error("PLACEMENT_ZONE_SET_INCOMPLETE")
    must_satisfied, must_unsatisfied = _pair_rows(graph.must_adjacencies, placed)
    if must_unsatisfied:
        raise _error(
            "HARD_CONSTRAINT_UNSATISFIABLE",
            unsatisfied_pairs=must_unsatisfied,
            satisfied_count=len(must_satisfied),
        )


def _validate_main_process_skeleton_graph(
    graph: AdjacencyGraphV1, placed: Mapping[str, PlacedRectangleV1]
) -> None:
    """Validate the seven-zone main-chain subset without requiring tail zones."""
    if set(placed) != set(MAIN_PROCESS_ZONE_CODES):
        raise _error("MAIN_PROCESS_SKELETON_ZONE_SET_INVALID")
    main_codes = set(MAIN_PROCESS_ZONE_CODES)
    main_must_pairs = tuple(
        pair for pair in graph.must_adjacencies if pair[0] in main_codes and pair[1] in main_codes
    )
    must_satisfied, must_unsatisfied = _pair_rows(main_must_pairs, placed)
    if must_unsatisfied:
        raise _error(
            "HARD_CONSTRAINT_UNSATISFIABLE",
            unsatisfied_pairs=must_unsatisfied,
            satisfied_count=len(must_satisfied),
        )


@dataclass(frozen=True)
class _PlacementSearchContext:
    authorities: Mapping[str, Mapping[str, Any]]
    site_body: Mapping[str, Any]
    graph: AdjacencyGraphV1
    source_zone_plan_hash: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    objective_profile_hash: str
    access_requirements: tuple[Mapping[str, Any], ...]
    spatial_relationships: tuple[Mapping[str, Any], ...]
    node_budget: int
    truck_maneuver_binding: Any
    truck_node_budget: int
    truck_maneuver_validator: Callable[..., Mapping[str, Any]] | None
    access_route_validator: Callable[..., tuple[Mapping[str, Any], tuple[PolygonMM, ...]]] | None
    access_portal_event_provider: Callable[..., Mapping[str, Any]] | None
    main_entrance_route_start_points: tuple[tuple[int, int], ...]
    complete_candidate_limit: int | None
    boundary: PolygonMM
    boundary_bounds: tuple[int, int, int, int]
    main_entrance: SegmentMM
    obstacles: tuple[PolygonMM, ...]
    preferred_loading_side: str
    placement_zone_order: tuple[str, ...]
    structural_composition_family: StructuralCompositionFamilyV1
    structural_skeleton: StructuralSkeletonV1
    structured_building_plan: StructuredBuildingSkeletonV1 | None
    structural_topology: str
    search_phase: str
    direct_synthesis_enabled: bool
    global_main_process_geometry_registry: dict[str, dict[str, Any]] | None
    global_cross_topology_duplicate_trace: list[dict[str, Any]] | None
    authoritative_axis_extent_cache: dict[tuple[str, str], int] = field(
        default_factory=dict, compare=False, repr=False
    )


def _legacy_compatibility_search_plan(
    *,
    boundary: PolygonMM,
    obstacles: tuple[PolygonMM, ...],
    authorities: Mapping[str, Mapping[str, Any]],
    process_axis: str,
    process_direction: str,
    topology: str,
    main_entrance: SegmentMM,
) -> StructuredBuildingSkeletonV1:
    """Build the isolated R1-compatible topology lane search context."""
    return construct_legacy_compatibility_search_plan_v1(
        boundary=boundary,
        obstacles=obstacles,
        authorities=authorities,
        process_axis=process_axis,
        process_direction=process_direction,
        layout_family=structured_layout_family_for_topology(topology),
        main_entrance=main_entrance,
    )


@dataclass
class _PlacementSearchStats:
    visited_nodes: int = 0
    generated_candidates: int = 0
    complete_candidates: int = 0
    node_budget_exhausted: bool = False
    structured_main_skeleton_completions: dict[str, int] | None = None
    structured_core_root_completions: dict[str, int] | None = None
    constructed_main_skeletons: dict[str, MainProcessSkeletonCandidateV1] | None = None
    skeleton_generation_patterns: dict[str, int] | None = None
    rejection_reason_counts: dict[str, int] | None = None
    skeleton_construction_attempts: list[dict[str, Any]] | None = None
    skeleton_search_truncated: bool = False
    root_preflight_rows: list[dict[str, Any]] | None = None
    tail_nodes_by_skeleton: dict[str, int] | None = None
    skeleton_tail_lifecycle: list[dict[str, Any]] | None = None
    construction_nodes_by_skeleton: dict[str, int] | None = None
    tail_zone_search_facts: dict[str, dict[str, dict[str, int]]] | None = None
    topology_ownership_duplicates: list[dict[str, Any]] | None = None
    offset_transition_trace: list[dict[str, Any]] | None = None
    constructive_divergence_attempts: list[dict[str, Any]] | None = None
    site_module_assembly_trace: list[dict[str, Any]] | None = None
    site_bay_rows: tuple[BuildableBayV1, ...] | None = None
    site_module_variant_counts: dict[str, Any] | None = None
    site_packaging_anchors: tuple[PackagingAnchorV1, ...] | None = None
    site_packaging_construction_anchors: tuple[PackagingAnchorV1, ...] | None = None
    site_shipping_dock_anchors: tuple[ShippingDockAnchorV1, ...] | None = None
    site_shipping_dock_construction_anchors: tuple[ShippingDockAnchorV1, ...] | None = None
    finished_forward_site_attempt_count: int = 0
    finished_dock_backsolve_attempt_count: int = 0
    packaging_shipping_anchor_pair_count: int = 0
    packaging_shipping_pair_necessary_pass_count: int = 0
    site_packaging_sorting_roots_by_anchor: (
        dict[
            str,
            tuple[tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]], ...],
        ]
        | None
    ) = None
    sorting_rotation_site_attempt_counts: dict[str, int] | None = None
    packaging_anchor_sorting_rotation_attempts_by_group: dict[str, set[str]] | None = None
    packaging_anchor_sorting_alignment_proofs_by_group: dict[str, dict[str, str]] | None = None
    site_main_assembly_counts_by_family: dict[str, dict[str, int]] | None = None
    site_main_assembly_geometry_keys_by_family: dict[str, set[str]] | None = None
    site_main_assembly_tail_capable_geometry_keys_by_family: dict[str, set[str]] | None = None
    site_main_assembly_packaging_rejected_geometry_keys_by_family: dict[str, set[str]] | None = None
    site_main_assembly_packaging_unavailable_geometry_keys_by_family: dict[str, set[str]] | None = (
        None
    )
    packaging_sorting_core_pair_geometry_keys_by_family: dict[str, set[str]] | None = None
    site_main_source_pair_rows: list[dict[str, Any]] | None = None
    early_packaging_preflight_by_geometry: dict[str, dict[str, Any]] | None = None
    reserved_construction_space_by_critical_signature: (
        dict[str, tuple[PlacedRectangleV1, ...]] | None
    ) = None
    reserved_truck_envelopes_by_critical_signature: dict[str, tuple[PolygonMM, ...]] | None = None
    truck_maneuver_construction_witness_by_skeleton_hash: dict[str, dict[str, Any]] | None = None
    early_formal_packaging_preflight_mismatch_count: int = 0
    tail_raw_geometry_slot_count_by_module: dict[str, set[str]] | None = None
    tail_access_valid_slot_count_by_module: dict[str, set[str]] | None = None
    tail_raw_geometry_slot_total_by_module: dict[str, int] | None = None
    tail_access_sampled_slot_count_by_module: dict[str, int] | None = None
    tail_access_sample_truncated_by_module: dict[str, int] | None = None
    personnel_raw_candidate_signatures: set[str] | None = None
    personnel_access_valid_signatures: set[str] | None = None
    personnel_access_2_of_2_pass_signatures: set[str] | None = None
    secondary_raw_candidate_signatures: set[str] | None = None
    secondary_access_valid_signatures: set[str] | None = None
    secondary_access_pass_signatures: set[str] | None = None
    frozen_raw_candidate_signatures: set[str] | None = None
    frozen_access_valid_signatures: set[str] | None = None
    frozen_access_pass_signatures: set[str] | None = None
    construction_access_requirement_pass_counts: dict[str, int] | None = None
    construction_access_requirement_failure_counts: dict[str, int] | None = None
    construction_access_failure_code_counts: dict[str, int] | None = None
    direct_shared_edge_access_witness_count: int = 0
    corridor_mediated_access_witness_count: int = 0
    reserved_access_corridor_geometries: set[tuple[tuple[int, int], ...]] | None = None
    access_route_revalidation_count: int = 0
    tail_access_candidate_witnesses: list[dict[str, Any]] | None = None
    tail_complete_access_witnesses: list[dict[str, Any]] | None = None
    tail_access_trace: list[dict[str, Any]] | None = None
    tail_access_capacity_preflight_nodes_by_main: dict[str, int] | None = None
    tail_access_capacity_status_by_main: dict[str, str] | None = None
    tail_access_capacity_seed_counts_by_main: dict[str, dict[str, int]] | None = None
    tail_access_driven_candidate_counts_by_main: dict[str, dict[str, int]] | None = None
    tail_access_valid_candidate_counts_by_main: dict[str, dict[str, int]] | None = None
    tail_office_geometry_candidate_counts_by_main: dict[str, int] | None = None
    tail_access_capacity_preflight_rows: list[dict[str, Any]] | None = None
    tail_access_capacity_route_cache: (
        dict[
            tuple[str, str, tuple[tuple[str, tuple[int, ...]], ...]],
            tuple[tuple[Mapping[str, Any], ...], tuple[PolygonMM, ...]],
        ]
        | None
    ) = None
    tail_access_capacity_attempted_candidates_by_main: (
        dict[str, set[tuple[str, tuple[tuple[str, tuple[int, ...]], ...]]]] | None
    ) = None
    tail_access_capacity_candidate_cursor_by_main: dict[str, dict[str, int]] | None = None
    tail_access_capacity_domain_exhausted_by_main: dict[str, dict[str, bool]] | None = None
    sorting_side_branch_free_intervals_by_main: (
        dict[str, dict[str, dict[str, list[dict[str, Any]]]]] | None
    ) = None
    tail_direct_seed_counts_before_truck_filter_by_main: dict[str, dict[str, int]] | None = None
    tail_direct_seed_counts_after_truck_filter_by_main: dict[str, dict[str, int]] | None = None
    tail_access_s2_node_quota_exhausted_by_main: set[str] | None = None
    changing_flexible_shape_signatures: set[tuple[int, int]] | None = None
    changing_authority_shape_signatures: set[tuple[int, int, int]] | None = None
    changing_construction_footprint_signatures: set[tuple[int, int]] | None = None
    changing_dual_endpoint_seed_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] | None = (
        None
    )
    entrance_route_compatible_changing_seed_count: int = 0
    entrance_route_compatible_changing_access_pass_count: int = 0
    entrance_route_compatible_changing_seed_counts_by_main: dict[str, int] | None = None
    changing_to_sorting_direct_pass_count: int = 0
    changing_extreme_aspect_shape_signatures: set[tuple[int, int]] | None = None
    changing_extreme_aspect_probed_before_route_compatible_count: int = 0
    entrance_route_compatible_passed_by_main: set[str] | None = None
    main_entrance_to_changing_failure_code_counts: dict[str, int] | None = None
    tail_incapable_reason_by_main: dict[str, list[str]] | None = None
    tail_incapable_proof_scope_by_main: dict[str, str] | None = None
    frozen_direct_seed_truck_rejection_rows: list[dict[str, Any]] | None = None
    frozen_sorting_portal_event_count_by_main: dict[str, int] | None = None
    frozen_target_portal_event_count_by_main: dict[str, int] | None = None
    frozen_truck_clear_corridor_event_count_by_main: dict[str, int] | None = None
    frozen_truck_clear_corridor_candidate_event_count_by_main: dict[str, int] | None = None
    frozen_route_constructive_seed_count_by_main: dict[str, int] | None = None
    frozen_candidate_counts_by_main: dict[str, dict[str, int]] | None = None
    frozen_route_probe_count_by_main: dict[str, int] | None = None
    frozen_access_valid_count_by_main: dict[str, int] | None = None
    frozen_access_failure_code_counts_by_main: dict[str, dict[str, int]] | None = None
    frozen_candidate_rejection_taxonomy_by_main: dict[str, dict[str, int]] | None = None
    frozen_candidate_route_rejection_rows_by_main: dict[str, list[dict[str, Any]]] | None = None
    frozen_access_witness_by_main: dict[str, dict[str, Any]] | None = None
    frozen_constructive_candidate_witness_by_main: dict[str, list[dict[str, Any]]] | None = None
    endpoint_driven_candidate_metadata_miss_count: int = 0
    tail_access_capacity_continuation_count: int = 0
    truck_pass_main_rejected_for_tail_access_count: int = 0
    main_enumeration_continued_after_tail_access_reject: bool = False
    main_generator_resumed_from_continuation: bool = False
    replayed_main_prefix_node_count: int = 0
    tail_capacity_seed_cache_reused_in_s2: bool = False
    tail_generic_fallback_route_probe_count: int = 0
    tail_generic_fallback_truncated_count: int = 0
    tail_generic_fallback_deferred_count: int = 0
    tail_access_slot_attempt_count: int = 0
    tail_access_slot_nodes_by_main: dict[str, int] | None = None
    tail_access_slot_budget_exhausted: bool = False
    tail_candidate_space_truncated: bool = False
    family_geometry_collapse_count: int = 0
    topology_classification_failures: list[dict[str, Any]] | None = None
    geometry_evaluation_admissions: list[dict[str, Any]] | None = None
    tail_slot_preflight_rows: list[dict[str, Any]] | None = None
    main_skeleton_truck_preflight_rows: list[dict[str, Any]] | None = None
    cross_topology_duplicate_count: int = 0
    quantum_node_limit: int | None = None
    quantum_nodes_visited: int = 0
    quantum_nodes_by_layout_family: dict[str, int] | None = None
    current_work_item: dict[str, Any] | None = None
    normal_stop_reason: str | None = None
    construction_node_count: int = 0

    def record_early_packaging_preflight_mismatch(self) -> None:
        self.early_formal_packaging_preflight_mismatch_count += 1

    def reserve_construction_space(
        self, critical_signature: str, corridor: PlacedRectangleV1
    ) -> None:
        if self.reserved_construction_space_by_critical_signature is None:
            self.reserved_construction_space_by_critical_signature = {}
        self.reserved_construction_space_by_critical_signature[critical_signature] = (corridor,)

    def reserve_truck_envelopes(
        self, critical_signature: str, envelopes: Sequence[PolygonMM]
    ) -> None:
        if self.reserved_truck_envelopes_by_critical_signature is None:
            self.reserved_truck_envelopes_by_critical_signature = {}
        self.reserved_truck_envelopes_by_critical_signature[critical_signature] = tuple(envelopes)


@dataclass(frozen=True)
class _SearchQuantumYield:
    """Internal cooperative yield; the owning generator remains resumable."""

    work_item: Mapping[str, Any] | None


@dataclass(frozen=True)
class PlacementCandidateQuantumAdvanceV1:
    """One bounded advance of a persistent P2C candidate stream."""

    candidates: tuple[SitePlacementResultV1, ...]
    nodes_visited: int
    status: str
    work_item: Mapping[str, Any] | None
    search_exhausted: bool
    completed: bool


@dataclass(frozen=True)
class BuildableBayV1:
    """Exact maximal placement region or connectivity partition from site geometry."""

    bay_id: str
    bounds_mm: tuple[int, int, int, int]
    area_mm2: int
    adjacent_bay_ids: tuple[str, ...] = ()
    shared_interface_segments: tuple[SegmentMM, ...] = ()
    boundary_contact_sides: tuple[str, ...] = ()
    entrance_contact: bool = False
    truck_entrance_contact: bool = False
    bay_role: str = "MAXIMAL_PLACEMENT_REGION"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bay_id": self.bay_id,
            "bay_role": self.bay_role,
            "bounds_mm": list(self.bounds_mm),
            "area_mm2": self.area_mm2,
            "adjacent_bay_ids": list(self.adjacent_bay_ids),
            "shared_interface_segments": [
                [list(segment[0]), list(segment[1])] for segment in self.shared_interface_segments
            ],
            "boundary_contact_sides": list(self.boundary_contact_sides),
            "entrance_contact": self.entrance_contact,
            "truck_entrance_contact": self.truck_entrance_contact,
        }


def _quantum_checkpoint(stats: _PlacementSearchStats) -> _SearchQuantumYield | None:
    if stats.quantum_node_limit is None:
        return None
    work_item = dict(stats.current_work_item) if stats.current_work_item is not None else None
    if work_item is not None and isinstance(work_item.get("band_family"), str):
        if stats.quantum_nodes_by_layout_family is None:
            stats.quantum_nodes_by_layout_family = {}
        family = f"{work_item.get('topology', 'UNCLASSIFIED')}:{work_item['band_family']}"
        visited = stats.quantum_nodes_by_layout_family.get(family, 0) + 1
        if visited < stats.quantum_node_limit:
            stats.quantum_nodes_by_layout_family[family] = visited
            return None
        stats.quantum_nodes_by_layout_family[family] = 0
        return _SearchQuantumYield(work_item)
    stats.quantum_nodes_visited += 1
    if stats.quantum_nodes_visited < stats.quantum_node_limit:
        return None
    stats.quantum_nodes_visited = 0
    return _SearchQuantumYield(work_item)


def _validated_search_context(
    authorities: Mapping[str, Mapping[str, Any]],
    site_body: Mapping[str, Any],
    graph: AdjacencyGraphV1,
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    objective_profile_hash: str | None,
    access_requirements: Sequence[Mapping[str, Any]],
    spatial_relationships: Sequence[Mapping[str, Any]],
    node_budget: int,
    truck_maneuver_binding: Any = None,
    truck_node_budget: int = 20_000,
    truck_maneuver_validator: Callable[..., Mapping[str, Any]] | None = None,
    access_route_validator: (
        Callable[..., tuple[Mapping[str, Any], tuple[PolygonMM, ...]]] | None
    ) = None,
    access_portal_event_provider: Callable[..., Mapping[str, Any]] | None = None,
    main_entrance_route_start_points: Sequence[tuple[int, int]] = (),
    complete_candidate_limit: int | None,
    structural_family: StructuralCompositionFamilyV1 | None = None,
    structural_topology: str | None = None,
    search_phase: str = LEGACY_COMPAT_PHASE,
    direct_synthesis_enabled: bool = True,
    global_main_process_geometry_registry: dict[str, dict[str, Any]] | None = None,
    global_cross_topology_duplicate_trace: list[dict[str, Any]] | None = None,
) -> _PlacementSearchContext:
    if set(authorities) != set(graph.nodes) or tuple(PLACEMENT_ZONE_ORDER) != tuple(
        code for code in PLACEMENT_ZONE_ORDER if code in graph.nodes
    ):
        raise _error("PLACEMENT_ZONE_AUTHORITY_SET_INVALID")
    if len(access_requirements) != 12:
        raise _error(
            "P1_ACCESS_REQUIREMENTS_INVALID",
            expected_count=12,
            actual_count=len(access_requirements),
        )
    if node_budget <= 0 or (complete_candidate_limit is not None and complete_candidate_limit <= 0):
        raise _error("INVALID_PLACEMENT_SEARCH_BUDGET")
    if search_phase not in {STRUCTURED_PHASE, GENERAL_FALLBACK_PHASE, LEGACY_COMPAT_PHASE}:
        raise _error("PLACEMENT_SEARCH_PHASE_INVALID", search_phase=search_phase)
    site = site_body.get("site")
    obstacles_body = site_body.get("obstacles")
    entrances_body = site_body.get("entrances")
    if (
        not isinstance(site, Mapping)
        or not isinstance(obstacles_body, Mapping)
        or not isinstance(entrances_body, Mapping)
    ):
        raise _error("INVALID_SITE_GEOMETRY_RESULT")
    boundary = _polygon(site.get("effective_buildable_boundary"))
    boundary_bounds = _boundary_extents(boundary)
    main_entrance = _main_entrance_segment(site_body)
    raw_obstacles = obstacles_body.get("hard_obstacles", [])
    if not isinstance(raw_obstacles, list):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="hard_obstacles")
    obstacles = tuple(
        _polygon(row["footprint"])
        for row in raw_obstacles
        if isinstance(row, Mapping) and "footprint" in row
    )
    preferred = site.get("preferred_loading_side", "UNSPECIFIED")
    if not isinstance(preferred, str):
        raise _error("INVALID_LOADING_SIDE")
    selected_family = structural_family or select_structural_composition_family(
        site_body, authorities
    )
    selected_topology = structural_topology or (
        CENTRAL_PROCESS_HUB
        if selected_family.family == CENTRAL_PROCESS_HUB
        else STRAIGHT_LINEAR_BAND
    )
    if selected_topology not in {
        STRAIGHT_LINEAR_BAND,
        OFFSET_LINEAR_BAND,
        CENTRAL_PROCESS_HUB,
    }:
        raise _error("MAIN_PROCESS_TOPOLOGY_INVALID")
    if (selected_topology == CENTRAL_PROCESS_HUB) != (
        selected_family.family == CENTRAL_PROCESS_HUB
    ):
        raise _error("MAIN_PROCESS_TOPOLOGY_FAMILY_MISMATCH")
    skeletons = structural_skeleton_candidates(
        site_body,
        tuple(authorities),
        zone_authorities=authorities,
        family_candidates=(selected_family,),
    )
    skeleton = next(
        (
            candidate
            for candidate in skeletons
            if candidate.family.to_dict() == selected_family.to_dict()
        ),
        None,
    )
    if skeleton is None:
        raise _error("STRUCTURAL_SKELETON_UNAVAILABLE")
    structured_building_plan: StructuredBuildingSkeletonV1 | None = None
    if search_phase == STRUCTURED_PHASE:
        # Direct synthesis is admitted only with a real program-derived plan.
        for layout_family in BASE_LAYOUT_FAMILIES:
            for envelope_family in (RECTANGLE, SIMPLE_L):
                try:
                    structured_building_plan = construct_structured_building_plan_v1(
                        boundary=boundary,
                        obstacles=obstacles,
                        authorities=authorities,
                        process_axis=skeleton.ordering_axis,
                        layout_family=layout_family,
                        envelope_family=envelope_family,
                        main_entrance=main_entrance,
                    )
                except LayoutAuthorityError:
                    continue
                break
            if structured_building_plan is not None:
                break
    elif search_phase == GENERAL_FALLBACK_PHASE:
        # Compatibility search remains in the original whole-site search
        # domain.  The R2 envelope/band plan is a separate candidate source
        # and must not constrain the fallback that protects existing callers.
        structured_building_plan = _legacy_compatibility_search_plan(
            boundary=boundary,
            obstacles=obstacles,
            authorities=authorities,
            process_axis=skeleton.ordering_axis,
            process_direction=(
                selected_family.dominant_direction
                if selected_family.dominant_direction in {"POSITIVE", "NEGATIVE"}
                else "POSITIVE"
            ),
            topology=selected_topology,
            main_entrance=main_entrance,
        )
    elif search_phase != LEGACY_COMPAT_PHASE:
        raise _error("PLACEMENT_SEARCH_PHASE_INVALID", search_phase=search_phase)
    return _PlacementSearchContext(
        authorities=authorities,
        site_body=site_body,
        graph=graph,
        source_zone_plan_hash=source_zone_plan_hash,
        source_p1_handoff_hash=source_p1_handoff_hash,
        source_site_geometry_hash=source_site_geometry_hash,
        objective_profile_hash=objective_profile_hash
        or canonical_hash(approved_objective_profile().to_dict()),
        access_requirements=tuple(access_requirements),
        spatial_relationships=tuple(spatial_relationships),
        node_budget=node_budget,
        truck_maneuver_binding=truck_maneuver_binding,
        truck_node_budget=truck_node_budget,
        truck_maneuver_validator=truck_maneuver_validator,
        access_route_validator=access_route_validator,
        access_portal_event_provider=access_portal_event_provider,
        main_entrance_route_start_points=tuple(sorted(set(main_entrance_route_start_points))),
        complete_candidate_limit=complete_candidate_limit,
        boundary=boundary,
        boundary_bounds=boundary_bounds,
        main_entrance=main_entrance,
        obstacles=obstacles,
        preferred_loading_side=preferred,
        placement_zone_order=(
            (
                LINEAR_STRUCTURED_PLACEMENT_ZONE_ORDER
                if selected_family.family == "LINEAR_PROCESS_BAND"
                else STRUCTURED_PLACEMENT_ZONE_ORDER
            )
            if search_phase == STRUCTURED_PHASE
            else PLACEMENT_ZONE_ORDER
        ),
        structural_composition_family=selected_family,
        structural_skeleton=skeleton,
        structured_building_plan=structured_building_plan,
        structural_topology=selected_topology,
        search_phase=search_phase,
        direct_synthesis_enabled=direct_synthesis_enabled,
        global_main_process_geometry_registry=global_main_process_geometry_registry,
        global_cross_topology_duplicate_trace=global_cross_topology_duplicate_trace,
    )


def _group_axis_interval(
    group: str,
    placed: Mapping[str, PlacedRectangleV1],
    axis: str,
) -> tuple[int, int] | None:
    members = tuple(code for code in FUNCTIONAL_GROUPS[group] if code in placed)
    if not members:
        return None
    bounds = tuple(_bounds(placed[code]) for code in members)
    coordinate_pair = (0, 2) if axis == "X" else (1, 3)
    return (
        min(row[coordinate_pair[0]] for row in bounds),
        max(row[coordinate_pair[1]] for row in bounds),
    )


def _main_group_order_monotonic(
    placed: Mapping[str, PlacedRectangleV1], skeleton: StructuralSkeletonV1
) -> bool:
    raw = _group_axis_interval(RAW_SIDE_GROUP, placed, skeleton.ordering_axis)
    core = _group_axis_interval(PROCESSING_CORE_GROUP, placed, skeleton.ordering_axis)
    terminal_codes = ("finished_goods_room", "shipping_channel")
    terminal_bounds = tuple(_bounds(placed[code]) for code in terminal_codes if code in placed)
    if raw is None or core is None or len(terminal_bounds) != len(terminal_codes):
        return False
    if skeleton.family.family == "CENTRAL_PROCESS_HUB":
        sorting = placed.get("sorting_packaging_room")
        primary = placed.get("primary_precooling_room")
        raw_zone = placed.get("raw_fruit_buffer")
        secondary = placed.get("secondary_precooling_room")
        if any(zone is None for zone in (sorting, primary, raw_zone, secondary)):
            return False
        raw_side = _adjacent_side(sorting, primary)  # type: ignore[arg-type]
        raw_attachment = _adjacent_side(primary, raw_zone)  # type: ignore[arg-type]
        if raw_side is None or raw_attachment is None:
            return False
        toward_core = {
            "NORTH": "SOUTH",
            "SOUTH": "NORTH",
            "EAST": "WEST",
            "WEST": "EAST",
        }[raw_side]
        if raw_attachment == toward_core:
            return False
        finished_side = _adjacent_side(sorting, secondary)  # type: ignore[arg-type]
        # A hub is side-organized, not a one-dimensional three-band projection:
        # raw and finished groups must attach to distinct sorting faces, while
        # each group retains its explicit adjacent process chain.
        return finished_side is not None and finished_side != raw_side
    low_index, high_index = (0, 2) if skeleton.ordering_axis == "X" else (1, 3)
    finished = (
        min(row[low_index] for row in terminal_bounds),
        max(row[high_index] for row in terminal_bounds),
    )
    downstream = _structural_downstream_direction(skeleton, raw, core)
    if downstream == "POSITIVE":
        return raw[1] <= core[0] and finished[1] > core[1]
    if downstream == "NEGATIVE":
        return core[1] <= raw[0] and finished[0] < core[0]
    return False


def _topology_geometry_valid(
    placed: Mapping[str, PlacedRectangleV1], topology: str, longitudinal_axis: str
) -> bool:
    """Require the lane to own its exact geometry under canonical precedence."""
    classification = classify_main_process_topology_v1(placed)
    if classification.canonical_owner != topology:
        return False
    if topology in {STRAIGHT_LINEAR_BAND, OFFSET_LINEAR_BAND}:
        return classification.process_axis == longitudinal_axis
    return topology == CENTRAL_PROCESS_HUB


def _packaging_tail_slot_preflight_for_rectangles(
    context: _PlacementSearchContext,
    fixed_main_process_rectangles: Sequence[PlacedRectangleV1],
) -> dict[str, Any]:
    authority = context.authorities["packaging_material_storage"]
    dimension_variants = _dimension_variants(authority, {}, context.boundary)
    proof = evaluate_tail_zone_slot_feasibility_v1(
        zone_code="packaging_material_storage",
        dimension_variants=dimension_variants,
        dimension_authority_complete=_authority_mode(authority)
        in {"FIXED_RECTANGLE", "DETERMINISTIC_GRID_RECTANGLE"},
        boundary=context.boundary,
        obstacles=context.obstacles,
        fixed_main_process_rectangles=tuple(fixed_main_process_rectangles),
    )
    return proof.to_dict()


def _packaging_tail_slot_preflight(
    context: _PlacementSearchContext,
    skeleton: MainProcessSkeletonCandidateV1,
) -> dict[str, Any]:
    return _packaging_tail_slot_preflight_for_rectangles(
        context,
        skeleton.zone_rectangles,
    )


def _truck_maneuver_preflight_decision(result: Mapping[str, Any]) -> tuple[str, str | None]:
    """Reject only a completed authoritative search with no truck witness."""
    if result.get("truck_route_validated") is True:
        return "PASS", None
    search = result.get("search_provenance")
    search = search if isinstance(search, Mapping) else {}
    if (
        result.get("status") == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
        and search.get("search_tree_exhausted") is True
        and search.get("node_budget_exhausted") is False
    ):
        return "REJECT", "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
    if search.get("node_budget_exhausted") is True:
        return "UNRESOLVED", "TRUCK_MANEUVER_SEARCH_BUDGET_EXHAUSTED"
    return "UNRESOLVED", None


def _main_skeleton_truck_maneuver_preflight(
    context: _PlacementSearchContext,
    skeleton: MainProcessSkeletonCandidateV1,
) -> dict[str, Any]:
    """Apply the existing truck authority to only the frozen seven-zone skeleton.

    A completed no-route search is a necessary-condition rejection. Missing
    authority and bounded-search exhaustion are unresolved and still proceed
    to the normal tail/P2D path, where the existing fail-closed result remains
    authoritative.
    """
    zones = {rectangle.zone_code: rectangle for rectangle in skeleton.zone_rectangles}
    if set(zones) != set(MAIN_PROCESS_SKELETON_ZONE_CODES):
        raise _error("MAIN_PROCESS_SKELETON_ZONE_SET_INVALID")
    loading_side, loading_face, _, _ = _loading_face(zones["shipping_channel"], context.site_body)
    validator = context.truck_maneuver_validator
    if validator is None:
        return {
            "preflight_name": "MAIN_SKELETON_TRUCK_MANEUVER_NECESSARY_CONDITION_V1",
            "main_skeleton_hash": skeleton.main_process_skeleton_hash,
            "preflight_status": "UNRESOLVED",
            "preflight_action": "ALLOW_TAIL_SEARCH",
            "tail_search_started": False,
            "truck_route_validated": False,
            "failure_codes": ["TRUCK_PREFLIGHT_AUTHORITY_NOT_INJECTED"],
            "failure_reason": None,
            "search_profile_identity": None,
            "visited_nodes": 0,
            "node_budget": context.truck_node_budget,
            "node_budget_exhausted": False,
            "search_tree_exhausted": False,
            "shipping_loading_face_side": loading_side,
            "shipping_loading_face_segment": {
                "start": {"x": _m(loading_face[0][0]), "y": _m(loading_face[0][1])},
                "end": {"x": _m(loading_face[1][0]), "y": _m(loading_face[1][1])},
            },
            "zones_checked": list(MAIN_PROCESS_SKELETON_ZONE_CODES),
            "truck_validation_result_hash": None,
        }
    result = validator(
        context.truck_maneuver_binding,
        truck_entrance=_truck_segment(context.site_body),
        shipping_loading_face=loading_face,
        boundary=context.boundary,
        obstacles=context.obstacles,
        zones=zones,
        node_budget=context.truck_node_budget,
    )
    status, failure_reason = _truck_maneuver_preflight_decision(result)
    search = result.get("search_provenance")
    search = search if isinstance(search, Mapping) else {}
    face_segment = {
        "start": {"x": _m(loading_face[0][0]), "y": _m(loading_face[0][1])},
        "end": {"x": _m(loading_face[1][0]), "y": _m(loading_face[1][1])},
    }
    return {
        "preflight_name": "MAIN_SKELETON_TRUCK_MANEUVER_NECESSARY_CONDITION_V1",
        "main_skeleton_hash": skeleton.main_process_skeleton_hash,
        "preflight_status": status,
        "preflight_action": "REJECT_SKELETON" if status == "REJECT" else "ALLOW_TAIL_SEARCH",
        "tail_search_started": False,
        "truck_route_validated": result.get("truck_route_validated") is True,
        "failure_codes": list(result.get("codes", [])),
        "failure_reason": failure_reason,
        "search_profile_identity": result.get("search_profile_identity"),
        "visited_nodes": int(search.get("visited_nodes", 0)),
        "node_budget": int(search.get("node_budget", context.truck_node_budget)),
        "node_budget_exhausted": search.get("node_budget_exhausted") is True,
        "search_tree_exhausted": search.get("search_tree_exhausted") is True,
        "shipping_loading_face_side": loading_side,
        "shipping_loading_face_segment": face_segment,
        "zones_checked": list(MAIN_PROCESS_SKELETON_ZONE_CODES),
        "truck_validation_result_hash": result.get("canonical_result_hash"),
        "construction_witness": (
            {
                "maneuver_chain": list(result.get("maneuver_chain", [])),
                "truck_envelopes": list(result.get("truck_envelopes", [])),
            }
            if result.get("truck_route_validated") is True
            else None
        ),
    }


def _shipping_loading_face_approach_axis_penalty(
    context: _PlacementSearchContext, rectangle: PlacedRectangleV1
) -> int:
    """Prefer a loading-face axis aligned with the approach normal.

    This is an exact, categorical branch-order fact derived from the existing
    truck-entrance segment and the shared loading-face authority. It is not a
    hard prune; the authoritative maneuver validator still decides admission.
    """
    _, loading_face, _, _ = _loading_face(rectangle, context.site_body)
    entrance = _truck_segment(context.site_body)
    entrance_is_vertical = entrance[0][0] == entrance[1][0]
    loading_face_is_horizontal = loading_face[0][1] == loading_face[1][1]
    return int(entrance_is_vertical != loading_face_is_horizontal)


def _loading_face_dock_endpoint_penalty(
    context: _PlacementSearchContext, rectangle: PlacedRectangleV1
) -> int:
    """Visit exact dock events at loading-face endpoints before interior events."""
    _, loading_face, _, _ = _loading_face(rectangle, context.site_body)
    dock_points = _truck_dock_points_at_entrance(context)
    if any(point == loading_face[0] or point == loading_face[1] for point in dock_points):
        return 0
    if any(_on_segment(point, loading_face[0], loading_face[1]) for point in dock_points):
        return 1
    return 2


def _shipping_options_by_loading_face_approach(
    context: _PlacementSearchContext,
    options: Sequence[PlacedRectangleV1],
) -> tuple[PlacedRectangleV1, ...]:
    """Keep established edge options ahead of added dock-event branches."""
    del context
    return tuple(options)


def _interleave_finished_truck_interface_options(
    options: Sequence[PlacedRectangleV1],
    truck_interface_only_bounds: set[tuple[int, int, int, int]],
) -> tuple[PlacedRectangleV1, ...]:
    """Sample a dock-paired finished-room branch without starving legacy options."""
    ordered = tuple(options)
    established = tuple(row for row in ordered if _bounds(row) not in truck_interface_only_bounds)
    interface = tuple(row for row in ordered if _bounds(row) in truck_interface_only_bounds)
    if not established or not interface:
        return ordered
    return (established[0], interface[0], *established[1:], *interface[1:])


def _finished_options_by_shipping_approach(
    context: _PlacementSearchContext,
    placed: Mapping[str, PlacedRectangleV1],
    options: Sequence[PlacedRectangleV1],
) -> tuple[PlacedRectangleV1, ...]:
    """Preserve the established finished-room branch order deterministically."""
    del context, placed
    return tuple(options)


def _constructive_main_skeleton_tail_admission(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
    skeleton: MainProcessSkeletonCandidateV1,
    *,
    run_truck_preflight: bool = True,
) -> bool:
    """Admit only tail-capable, truck-feasible skeletons to completion quota.

    Both checks reuse their existing exact authorities. Structured module
    assembly may request the packaging-only stage before placing support and
    personnel modules, then invoke the full admission after all 12 zones are
    site-valid. Legacy search keeps the default early truck preflight.
    """
    geometry_hash = skeleton.main_process_skeleton_hash
    registry = context.global_main_process_geometry_registry
    existing = registry.get(geometry_hash) if registry is not None else None
    first_discovery_topology = (
        str(existing.get("first_discovery_topology"))
        if existing is not None and existing.get("first_discovery_topology") is not None
        else context.structural_topology
    )

    if existing is not None and existing.get("tail_search_started") is True:
        duplicate_row = {
            "event": "EXISTING_GEOMETRY_DUPLICATE_DISCOVERY",
            "skeleton_hash": geometry_hash,
            "first_discovery_topology": first_discovery_topology,
            "duplicate_discovery_topology": context.structural_topology,
            "canonical_topology_owner": skeleton.canonical_topology_owner,
            "tail_search_started_by_topology": existing.get("tail_search_discovery_topology"),
            "cross_topology_duplicate": first_discovery_topology != context.structural_topology,
            "duplicate_action": "SKIP_ALREADY_EVALUATED_GEOMETRY",
        }
        if stats.topology_ownership_duplicates is None:
            stats.topology_ownership_duplicates = []
        stats.topology_ownership_duplicates.append(duplicate_row)
        if duplicate_row["cross_topology_duplicate"]:
            stats.cross_topology_duplicate_count += 1
            if context.global_cross_topology_duplicate_trace is not None:
                context.global_cross_topology_duplicate_trace.append(duplicate_row)
        return False

    packaging_status = existing.get("packaging_preflight_status") if existing else None
    if packaging_status is None:
        packaging = _packaging_tail_slot_preflight(context, skeleton)
        proof_mode = str(packaging["proof_mode"])
        slot_exists = packaging["legal_slot_exists"]
        packaging_status = (
            "NO_LEGAL_SLOT"
            if slot_exists is False and proof_mode == EXACT_ORTHOGONAL_EVENT_ENUMERATION
            else "LEGAL_SLOT_EXISTS"
            if slot_exists is True
            else "UNAVAILABLE"
        )
        packaging_row = {
            "event": "TAIL_SLOT_PREFLIGHT_CONSTRUCTION_GATE",
            "stage": "TAIL_SLOT_PREFLIGHT",
            "skeleton_hash": geometry_hash,
            "discovery_topology": context.structural_topology,
            "canonical_topology_owner": skeleton.canonical_topology_owner,
            "canonical_family": skeleton.family.to_dict(),
            "packaging_preflight_status": packaging_status,
            "packaging_slot_exists": slot_exists,
            "tail_admissible": (
                False
                if packaging_status == "NO_LEGAL_SLOT"
                else None
                if packaging_status == "UNAVAILABLE"
                else True
            ),
            "tail_search_started": False,
            "preflight_reexecuted": True,
            "preflight": packaging,
        }
        if stats.tail_slot_preflight_rows is None:
            stats.tail_slot_preflight_rows = []
        stats.tail_slot_preflight_rows.append(packaging_row)
    else:
        slot_exists = existing.get("packaging_slot_exists") if existing else None

    registry_row = existing if existing is not None else {}
    registry_row.update(
        {
            "skeleton_hash": geometry_hash,
            "first_discovery_topology": first_discovery_topology,
            "canonical_topology_owner": skeleton.canonical_topology_owner,
            "canonical_family": skeleton.family.to_dict(),
            "packaging_preflight_status": packaging_status,
            "packaging_slot_exists": slot_exists,
            "tail_admissible": (
                False
                if packaging_status == "NO_LEGAL_SLOT"
                else None
                if packaging_status == "UNAVAILABLE"
                else True
            ),
            "tail_search_started": False,
        }
    )
    if registry is not None:
        registry[geometry_hash] = registry_row

    if packaging_status == "NO_LEGAL_SLOT":
        _record_rejection(stats, "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT")
        if stats.skeleton_tail_lifecycle is None:
            stats.skeleton_tail_lifecycle = []
        stats.skeleton_tail_lifecycle.append(
            {
                "topology": skeleton.topology,
                "skeleton_hash": geometry_hash,
                "discovery_topology": context.structural_topology,
                "canonical_topology_owner": skeleton.canonical_topology_owner,
                "canonical_family": skeleton.family.to_dict(),
                "packaging_preflight_executed": True,
                "packaging_slot_exists": False,
                "tail_admissible": False,
                "tail_search_started": False,
                "tail_nodes": 0,
                "tail_node_limit": 0,
                "complete_candidate_count": 0,
                "p2d_reached": False,
                "first_failure_stage": "TAIL_SLOT_PREFLIGHT",
                "first_failure_reason": "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT",
            }
        )
        return False

    if not run_truck_preflight:
        return True

    cached_truck_preflight = registry_row.get("main_skeleton_truck_preflight")
    if isinstance(cached_truck_preflight, Mapping):
        truck_row = dict(cached_truck_preflight)
        truck_row.update(
            {
                "event": "CACHED_MAIN_SKELETON_TRUCK_PREFLIGHT_CONSTRUCTION_GATE",
                "discovery_topology": context.structural_topology,
                "preflight_reexecuted": False,
                "preflight_compute_nodes": 0,
            }
        )
    else:
        truck_result = _main_skeleton_truck_maneuver_preflight(context, skeleton)
        planned_envelope_bounds = getattr(skeleton, "planned_envelope_bounds_mm", None)
        truck_row = {
            **truck_result,
            "event": "MAIN_SKELETON_TRUCK_PREFLIGHT_CONSTRUCTION_GATE",
            "stage": "MAIN_SKELETON_TRUCK_PREFLIGHT",
            "discovery_topology": context.structural_topology,
            "canonical_topology_owner": skeleton.canonical_topology_owner,
            "canonical_family": skeleton.family.to_dict(),
            "layout_family": getattr(skeleton, "building_layout_family", None),
            "envelope_family": getattr(skeleton, "building_envelope_family", None),
            "planned_envelope_bounds_mm": (
                list(planned_envelope_bounds)
                if isinstance(planned_envelope_bounds, tuple)
                else None
            ),
            "preflight_reexecuted": True,
            "preflight_compute_nodes": int(truck_result["visited_nodes"]),
        }
        registry_row["main_skeleton_truck_preflight"] = dict(truck_row)
        registry_row.setdefault("p2d_reached", False)
        registry_row.setdefault("p2d_candidate_count", 0)
        registry_row.setdefault("p2d_full_pass_count", 0)
        if registry is not None:
            registry[geometry_hash] = registry_row

    if truck_row["preflight_status"] == "PASS":
        witness = truck_row.get("construction_witness")
        if isinstance(witness, Mapping):
            if stats.truck_maneuver_construction_witness_by_skeleton_hash is None:
                stats.truck_maneuver_construction_witness_by_skeleton_hash = {}
            stats.truck_maneuver_construction_witness_by_skeleton_hash[geometry_hash] = {
                "main_skeleton_hash": geometry_hash,
                "maneuver_chain": list(witness.get("maneuver_chain", [])),
                "truck_envelopes": list(witness.get("truck_envelopes", [])),
            }
    if truck_row["preflight_status"] == "REJECT":
        if stats.main_skeleton_truck_preflight_rows is None:
            stats.main_skeleton_truck_preflight_rows = []
        stats.main_skeleton_truck_preflight_rows.append(truck_row)
        _record_rejection(
            stats,
            str(truck_row.get("failure_reason") or "TRUCK_MANEUVER_SEARCH_EXHAUSTED"),
        )
        if stats.skeleton_tail_lifecycle is None:
            stats.skeleton_tail_lifecycle = []
        stats.skeleton_tail_lifecycle.append(
            {
                "topology": skeleton.topology,
                "skeleton_hash": geometry_hash,
                "discovery_topology": context.structural_topology,
                "canonical_topology_owner": skeleton.canonical_topology_owner,
                "canonical_family": skeleton.family.to_dict(),
                "packaging_preflight_executed": True,
                "packaging_preflight_status": packaging_status,
                "packaging_slot_exists": slot_exists,
                "main_skeleton_truck_preflight_executed": True,
                "main_skeleton_truck_preflight_status": "REJECT",
                "truck_preflight_failure_codes": list(truck_row.get("failure_codes", [])),
                "truck_preflight_visited_nodes": int(truck_row.get("visited_nodes", 0)),
                "truck_preflight_node_budget": int(truck_row.get("node_budget", 0)),
                "truck_preflight_node_budget_exhausted": truck_row.get("node_budget_exhausted"),
                "truck_preflight_search_tree_exhausted": truck_row.get("search_tree_exhausted"),
                "tail_search_started": False,
                "tail_nodes": 0,
                "tail_node_limit": 0,
                "complete_candidate_count": 0,
                "p2d_reached": False,
                "first_failure_stage": "MAIN_SKELETON_TRUCK_PREFLIGHT",
                "first_failure_reason": (
                    truck_row.get("failure_reason") or "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
                ),
            }
        )
        return False
    return True


def _direct_candidate_plan(
    plan: StructuredBuildingSkeletonV1,
    placements: Mapping[str, PlacedRectangleV1],
) -> StructuredBuildingSkeletonV1:
    """Attach synthesized zones to the exact envelope/grid/bands that planned them."""
    return plan.with_placements(placements)


def _local_dimension_shapes(
    context: _PlacementSearchContext, zone_code: str
) -> tuple[tuple[int, int, int, int, int], ...]:
    """Return finite authority-derived ``width, depth, rotation, x-span, y-span`` shapes."""
    authority = context.authorities.get(zone_code)
    if authority is None:
        return ()
    unique: dict[tuple[int, int], tuple[int, int, int, int, int]] = {}
    dimension_options: tuple[tuple[int, int], ...]
    if _authority_mode(authority) != "FLEXIBLE_RECTANGLE":
        # A fixed rectangle has one authoritative width/depth pair. Rotation
        # changes its axis-aligned footprint, not the dimensions written into
        # the candidate record. _zone_dimension_options also returns the pair
        # swapped for projection convenience, so consuming both values here
        # would incorrectly serialize a rotated fixed room as resized.
        width_mm, depth_mm, _area = _authority_dimensions(authority)
        dimension_options = ((width_mm, depth_mm),)
    else:
        dimension_options = _zone_dimension_options(authority)
    for width_mm, depth_mm in dimension_options:
        for rotation in (0, 90):
            x_span, y_span = (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
            unique.setdefault(
                (x_span, y_span),
                (width_mm, depth_mm, rotation, x_span, y_span),
            )
    if zone_code == "coating_room" and authority.get("dimension_mode") == "FLEXIBLE_RECTANGLE":
        raw_area = authority.get("required_area_m2")
        geometry = authority.get("geometry")
        if raw_area is None and isinstance(geometry, Mapping):
            raw_area = geometry.get("required_area_m2")
        if raw_area is not None:
            required_area_mm2 = Fraction(str(raw_area)) * 1_000_000
            # Coating is the secondary-to-finished transition. Derive a small
            # finite set of flexible widths from its actual MUST-neighbour
            # edge events, rather than hoping the first Cartesian shape rows
            # happen to align with those interfaces.
            for neighbor_code in ("secondary_precooling_room", "finished_goods_room"):
                for neighbor_shape in _local_dimension_shapes(context, neighbor_code):
                    for width_mm in sorted({neighbor_shape[3], neighbor_shape[4]}):
                        if width_mm <= 0:
                            continue
                        divisor = width_mm * required_area_mm2.denominator
                        depth_mm = (required_area_mm2.numerator + divisor - 1) // divisor
                        for rotation in (0, 90):
                            x_span, y_span = (
                                (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
                            )
                            unique.setdefault(
                                (x_span, y_span),
                                (width_mm, depth_mm, rotation, x_span, y_span),
                            )
    return tuple(unique[key] for key in sorted(unique))


def _local_rectangle_at(
    zone_code: str,
    shape: tuple[int, int, int, int, int],
    x_mm: int,
    y_mm: int,
) -> PlacedRectangleV1:
    width_mm, depth_mm, rotation, _x_span, _y_span = shape
    return _rectangle_from_mm(zone_code, x_mm, y_mm, width_mm, depth_mm, rotation)


def _cached_local_rectangle_bounds_mm(
    rectangle: PlacedRectangleV1,
) -> tuple[int, int, int, int]:
    """Return the exact integer-mm bounds for a local rectangle."""
    return rectangle.bounds_mm


def _local_adjacent_origin(
    parent: PlacedRectangleV1,
    x_span_mm: int,
    y_span_mm: int,
    side: str,
    alignment: str,
) -> tuple[int, int]:
    """Derive a child origin from one exact positive-edge interface."""
    left, bottom, right, top = _cached_local_rectangle_bounds_mm(parent)
    if side in {"EAST", "WEST"}:
        y = (
            bottom
            if alignment == "LOW"
            else top - y_span_mm
            if alignment == "HIGH"
            else bottom + (top - bottom - y_span_mm) // 2
        )
        return (right if side == "EAST" else left - x_span_mm), y
    if side in {"NORTH", "SOUTH"}:
        x = (
            left
            if alignment == "LOW"
            else right - x_span_mm
            if alignment == "HIGH"
            else left + (right - left - x_span_mm) // 2
        )
        return x, (top if side == "NORTH" else bottom - y_span_mm)
    raise _error("LOCAL_COMPOSITION_SIDE_INVALID", side=side)


def _local_rectangles_clear(
    candidate: PlacedRectangleV1, placed: Mapping[str, PlacedRectangleV1]
) -> bool:
    return not any(rectangles_overlap(candidate, existing) for existing in placed.values())


def _local_bbox_bounds(
    placements: Mapping[str, PlacedRectangleV1],
) -> tuple[int, int, int, int]:
    rows = tuple(_cached_local_rectangle_bounds_mm(rectangle) for rectangle in placements.values())
    if not rows:
        return (0, 0, 0, 0)
    return (
        min(row[0] for row in rows),
        min(row[1] for row in rows),
        max(row[2] for row in rows),
        max(row[3] for row in rows),
    )


def _local_bbox_fits_site_extents(
    context: _PlacementSearchContext,
    placements: Mapping[str, PlacedRectangleV1],
) -> bool:
    """Apply only the necessary site outer-extent test in local coordinates."""
    if not placements:
        return True
    bounds = _local_bbox_bounds(placements)
    width_mm, height_mm = bounds[2] - bounds[0], bounds[3] - bounds[1]
    site_bounds = cast(tuple[int, int, int, int] | None, getattr(context, "boundary_bounds", None))
    if not isinstance(site_bounds, tuple) or len(site_bounds) != 4:
        return True
    site_width_mm = site_bounds[2] - site_bounds[0]
    site_height_mm = site_bounds[3] - site_bounds[1]
    return (width_mm <= site_width_mm and height_mm <= site_height_mm) or (
        width_mm <= site_height_mm and height_mm <= site_width_mm
    )


def _local_compactness_key(
    placements: Mapping[str, PlacedRectangleV1],
    context: _PlacementSearchContext,
    process_axis: str,
) -> tuple[object, ...]:
    """Stable local-construction ordering; not a final candidate quality score."""
    left, bottom, right, top = _local_bbox_bounds(placements)
    width_mm, height_mm = right - left, top - bottom
    feasible = _local_bbox_fits_site_extents(context, placements)
    x_usage: dict[int, int] = {}
    y_usage: dict[int, int] = {}
    for rectangle in placements.values():
        x0, y0, x1, y1 = rectangle.bounds_mm
        x_usage[x0] = x_usage.get(x0, 0) + 1
        x_usage[x1] = x_usage.get(x1, 0) + 1
        y_usage[y0] = y_usage.get(y0, 0) + 1
        y_usage[y1] = y_usage.get(y1, 0) + 1
    reused_axes = sum(count > 1 for count in x_usage.values()) + sum(
        count > 1 for count in y_usage.values()
    )
    structural_axis_count = len(x_usage) + len(y_usage)
    chain = MAIN_PROCESS_ZONE_CODES
    directions: list[str] = []
    for first_code, second_code in zip(chain, chain[1:], strict=False):
        first = placements.get(first_code)
        second = placements.get(second_code)
        if first is None or second is None:
            continue
        side = _adjacent_side(first, second)
        if side is not None:
            directions.append("X" if side in {"EAST", "WEST"} else "Y")
    direction_changes = sum(
        first != second for first, second in zip(directions, directions[1:], strict=False)
    )
    geometry_key = tuple(
        (code, rectangle.bounds_mm, rectangle.rotation_deg)
        for code, rectangle in sorted(placements.items())
    )
    return (
        not feasible,
        max(width_mm, height_mm),
        width_mm * height_mm,
        structural_axis_count,
        -reused_axes,
        direction_changes,
        0 if process_axis == "X" else 1,
        geometry_key,
    )


def _local_quadrant_occupancy_signature(
    placements: Mapping[str, PlacedRectangleV1],
) -> tuple[bool, bool, bool, bool]:
    """Describe occupied SW/SE/NW/NE regions for local-embedding coverage."""
    if not placements:
        return (False, False, False, False)
    left, bottom, right, top = _local_bbox_bounds(placements)
    middle_x, middle_y = (left + right) // 2, (bottom + top) // 2
    occupied = [False, False, False, False]
    for rectangle in placements.values():
        x0, y0, x1, y1 = rectangle.bounds_mm
        west, east = x0 < middle_x, x1 > middle_x
        south, north = y0 < middle_y, y1 > middle_y
        if west and south:
            occupied[0] = True
        if east and south:
            occupied[1] = True
        if west and north:
            occupied[2] = True
        if east and north:
            occupied[3] = True
    return tuple(occupied)  # type: ignore[return-value]


def _local_grid_occupancy_signature(
    placements: Mapping[str, PlacedRectangleV1],
) -> tuple[bool, ...]:
    """Describe room occupancy in a local 3-by-3 grid without site coordinates."""
    if not placements:
        return (False,) * 9
    left, bottom, right, top = _local_bbox_bounds(placements)
    x_edges = tuple(left + (right - left) * index // 3 for index in range(4))
    y_edges = tuple(bottom + (top - bottom) * index // 3 for index in range(4))
    occupied = [False] * 9
    for rectangle in placements.values():
        x0, y0, x1, y1 = rectangle.bounds_mm
        for row in range(3):
            for column in range(3):
                if (
                    x1 > x_edges[column]
                    and x0 < x_edges[column + 1]
                    and y1 > y_edges[row]
                    and y0 < y_edges[row + 1]
                ):
                    occupied[row * 3 + column] = True
    return tuple(occupied)


def _local_group_relative_side(
    placements: Mapping[str, PlacedRectangleV1],
    group_codes: Sequence[str],
    reference_codes: Sequence[str],
) -> str | None:
    group = {code: placements[code] for code in group_codes if code in placements}
    reference = {code: placements[code] for code in reference_codes if code in placements}
    if not group or not reference:
        return None
    group_bounds = _local_bbox_bounds(group)
    reference_bounds = _local_bbox_bounds(reference)
    dx = group_bounds[0] + group_bounds[2] - reference_bounds[0] - reference_bounds[2]
    dy = group_bounds[1] + group_bounds[3] - reference_bounds[1] - reference_bounds[3]
    if abs(dx) >= abs(dy) and dx != 0:
        return "EAST" if dx > 0 else "WEST"
    if dy != 0:
        return "NORTH" if dy > 0 else "SOUTH"
    return "OVERLAP"


def _local_embedding_diversity_key(
    placements: Mapping[str, PlacedRectangleV1],
) -> tuple[object, ...]:
    chain_sides = tuple(
        _adjacent_side(placements[first], placements[second])
        if first in placements and second in placements
        else None
        for first, second in zip(MAIN_PROCESS_ZONE_CODES, MAIN_PROCESS_ZONE_CODES[1:], strict=False)
    )
    root = placements.get("sorting_packaging_room")
    root_shape = (
        (
            root.bounds_mm[2] - root.bounds_mm[0],
            root.bounds_mm[3] - root.bounds_mm[1],
            root.rotation_deg,
        )
        if root is not None
        else None
    )
    support_side = _local_group_relative_side(
        placements,
        ("packaging_material_storage", "secondary_fruit_buffer", "frozen_fruit_room"),
        MAIN_PROCESS_ZONE_CODES,
    )
    personnel_side = _local_group_relative_side(
        placements,
        ("office", "changing_room"),
        MAIN_PROCESS_ZONE_CODES,
    )
    return (
        chain_sides,
        _local_quadrant_occupancy_signature(placements),
        _local_grid_occupancy_signature(placements),
        support_side,
        personnel_side,
        root_shape,
    )


def _retain_compact_local_states(
    states: Iterable[Mapping[str, PlacedRectangleV1]],
    context: _PlacementSearchContext,
    process_axis: str,
    limit: int,
) -> tuple[Mapping[str, PlacedRectangleV1], ...]:
    """Keep compact representatives across distinct local structure buckets."""
    if limit <= 0:
        return ()
    ordered = sorted(
        states,
        key=lambda row: _local_compactness_key(row, context, process_axis),
    )
    selected: list[Mapping[str, PlacedRectangleV1]] = []
    selected_geometries: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    selected_buckets: set[tuple[object, ...]] = set()
    spatial_representatives: dict[
        tuple[tuple[bool, ...], tuple[bool, ...]], Mapping[str, PlacedRectangleV1]
    ] = {}
    for state in ordered:
        spatial_representatives.setdefault(
            (
                _local_quadrant_occupancy_signature(state),
                _local_grid_occupancy_signature(state),
            ),
            state,
        )
    for occupancy in sorted(
        spatial_representatives,
        key=lambda row: row,
    ):
        state = spatial_representatives[occupancy]
        bucket = _local_embedding_diversity_key(state)
        geometry = tuple(
            (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
            for code, rectangle in sorted(state.items())
        )
        selected.append(state)
        selected_buckets.add(bucket)
        selected_geometries.add(geometry)
        if len(selected) >= limit:
            selected.sort(key=lambda row: _local_compactness_key(row, context, process_axis))
            return tuple(selected)
    for state in ordered:
        bucket = _local_embedding_diversity_key(state)
        if bucket in selected_buckets:
            continue
        geometry = tuple(
            (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
            for code, rectangle in sorted(state.items())
        )
        if geometry in selected_geometries:
            continue
        selected.append(state)
        selected_buckets.add(bucket)
        selected_geometries.add(geometry)
        if len(selected) >= limit:
            selected.sort(key=lambda row: _local_compactness_key(row, context, process_axis))
            return tuple(selected)
    if len(selected) < limit:
        for state in ordered:
            geometry = tuple(
                (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                for code, rectangle in sorted(state.items())
            )
            if geometry in selected_geometries:
                continue
            selected.append(state)
            selected_geometries.add(geometry)
            if len(selected) >= limit:
                break
    selected.sort(key=lambda row: _local_compactness_key(row, context, process_axis))
    return tuple(selected)


def _retain_compact_local_compositions(
    compositions: Iterable[LocalBuildingCompositionV1],
    context: _PlacementSearchContext,
    process_axis: str,
    limit: int,
) -> tuple[LocalBuildingCompositionV1, ...]:
    rows = tuple(compositions)
    state_rows = _retain_compact_local_states(
        (composition.placements() for composition in rows), context, process_axis, limit
    )
    by_signature = {
        tuple(
            (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
            for code, rectangle in sorted(composition.placements().items())
        ): composition
        for composition in rows
    }
    return tuple(
        by_signature[
            tuple(
                (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                for code, rectangle in sorted(state.items())
            )
        ]
        for state in state_rows
    )


def _local_family_partial_valid(
    layout_family: str,
    placed: Mapping[str, PlacedRectangleV1],
) -> bool:
    sorting = placed.get("sorting_packaging_room")
    primary = placed.get("primary_precooling_room")
    secondary = placed.get("secondary_precooling_room")
    if sorting is None or primary is None or secondary is None:
        return True
    raw_face = _adjacent_side(sorting, primary)
    finished_face = _adjacent_side(sorting, secondary)
    if raw_face is None or finished_face is None:
        return False
    if layout_family == CENTRAL_PROCESS_WITH_SIDE_BANKS:
        return raw_face != finished_face
    if layout_family == LONGITUDINAL_PROCESS_SPINE:
        raw_axis = "X" if raw_face in {"EAST", "WEST"} else "Y"
        finished_axis = "X" if finished_face in {"EAST", "WEST"} else "Y"
        return raw_axis != finished_axis
    return True


def _local_outline_class(
    placements: Mapping[str, PlacedRectangleV1],
) -> tuple[str, tuple[int, int, int, int]]:
    """Classify the exact rectangle union without site or visual heuristics."""
    if not placements:
        return "UNAVAILABLE", (0, 0, 0, 0)
    bounds = tuple(rectangle.bounds_mm for rectangle in placements.values())
    envelope_bounds = (
        min(row[0] for row in bounds),
        min(row[1] for row in bounds),
        max(row[2] for row in bounds),
        max(row[3] for row in bounds),
    )
    x_events = sorted({value for row in bounds for value in (row[0], row[2])})
    y_events = sorted({value for row in bounds for value in (row[1], row[3])})
    x_index = {value: index for index, value in enumerate(x_events)}
    y_index = {value: index for index, value in enumerate(y_events)}
    occupied: set[tuple[int, int]] = set()
    for left, bottom, right, top in bounds:
        for x_cell in range(x_index[left], x_index[right]):
            for y_cell in range(y_index[bottom], y_index[top]):
                occupied.add((x_cell, y_cell))
    x_cell_count = len(x_events) - 1
    y_cell_count = len(y_events) - 1
    total_cells = x_cell_count * y_cell_count
    if len(occupied) == total_cells:
        return "RECTANGLE", envelope_bounds
    missing = {
        (x_cell, y_cell)
        for x_cell in range(x_cell_count)
        for y_cell in range(y_cell_count)
        if (x_cell, y_cell) not in occupied
    }
    if not missing:
        return "RECTANGLE", envelope_bounds
    left = min(cell[0] for cell in missing)
    bottom = min(cell[1] for cell in missing)
    right = max(cell[0] for cell in missing)
    top = max(cell[1] for cell in missing)
    corner_notch = (
        len(missing) == (right - left + 1) * (top - bottom + 1)
        and (left == 0 or right == x_cell_count - 1)
        and (bottom == 0 or top == y_cell_count - 1)
    )
    if corner_notch:
        return "SIMPLE_L", envelope_bounds
    return "STAIR_STEP", envelope_bounds


def _normalize_local_placements(
    placements: Mapping[str, PlacedRectangleV1],
) -> dict[str, PlacedRectangleV1]:
    """Move a complete local composition as one rigid body to a zero lower-left."""
    if not placements:
        return {}
    left = min(rectangle.bounds_mm[0] for rectangle in placements.values())
    bottom = min(rectangle.bounds_mm[1] for rectangle in placements.values())
    return {
        code: _rectangle_from_mm(
            code,
            rectangle.bounds_mm[0] - left,
            rectangle.bounds_mm[1] - bottom,
            _mm(rectangle.width_m, field="local.width_m"),
            _mm(rectangle.depth_m, field="local.depth_m"),
            rectangle.rotation_deg,
        )
        for code, rectangle in sorted(placements.items())
    }


def _rotate_local_side(side: str, process_axis: str, process_direction: str) -> str:
    side_map = {"EAST": "NORTH", "NORTH": "WEST", "WEST": "SOUTH", "SOUTH": "EAST"}
    selected = side
    if process_axis == "Y":
        selected = side_map[selected]
    if process_direction == "NEGATIVE":
        selected = {"EAST": "WEST", "WEST": "EAST", "NORTH": "SOUTH", "SOUTH": "NORTH"}[selected]
    return selected


def _local_family_interface_patterns(
    layout_family: str, process_axis: str, process_direction: str
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """Return family-level local interfaces, not site-derived bands or room anchors."""
    if layout_family == LINEAR_3_BAND:
        # The ordered chain gets explicit straight-band alternatives first;
        # compact one-turn alternatives follow as local composition choices.
        base = tuple(
            (raw_side, process_side, path)
            for raw_side, process_side in (("WEST", "EAST"), ("SOUTH", "NORTH"))
            for path in (
                (process_side, process_side, process_side),
                (process_side, "NORTH" if process_side == "EAST" else "EAST", process_side),
                (process_side, "SOUTH" if process_side == "EAST" else "WEST", process_side),
            )
        )
    elif layout_family == CENTRAL_PROCESS_WITH_SIDE_BANKS:
        # The raw and finished banks occupy opposite core faces. Their outward
        # chains remain straight or make one finite terminal turn.
        base = tuple(
            (raw_side, finished_side, path)
            for raw_side, finished_side in (
                ("SOUTH", "NORTH"),
                ("NORTH", "SOUTH"),
                ("WEST", "EAST"),
                ("EAST", "WEST"),
            )
            for path in (
                (finished_side, finished_side, finished_side),
                (
                    finished_side,
                    "NORTH" if finished_side in {"EAST", "WEST"} else "EAST",
                    finished_side,
                ),
            )
        )
    elif layout_family == LONGITUDINAL_PROCESS_SPINE:
        base = (
            ("WEST", "EAST", ("NORTH", "NORTH", "NORTH")),
            ("WEST", "EAST", ("SOUTH", "SOUTH", "SOUTH")),
            ("SOUTH", "NORTH", ("EAST", "EAST", "EAST")),
            ("SOUTH", "NORTH", ("WEST", "WEST", "WEST")),
            ("WEST", "EAST", ("EAST", "NORTH", "EAST")),
            ("WEST", "EAST", ("EAST", "SOUTH", "EAST")),
        )
    else:
        return ()
    return tuple(
        (
            _rotate_local_side(raw_side, process_axis, process_direction),
            _rotate_local_side(secondary_side, process_axis, process_direction),
            tuple(_rotate_local_side(side, process_axis, process_direction) for side in path),
        )
        for raw_side, secondary_side, path in base
    )


def _bounded_local_shape_rows(
    shape_options: Sequence[Sequence[tuple[int, int, int, int, int]]],
) -> tuple[tuple[tuple[int, int, int, int, int], ...], ...]:
    """Return a deterministic finite sample of authoritative shape combinations.

    The 128-row cap covers the binary 0/90 orientation combinations of the
    seven main-process zones when each has one authoritative dimension shape.
    Flexible-dimension alternatives are an additional search slice, not a new
    engineering rule. The cap prevents one family attempt from expanding the
    full Cartesian product before yielding to the global placement scheduler.
    """
    return tuple(islice(product(*shape_options), LOCAL_COMPOSITION_SHAPE_VARIANT_LIMIT))


def _local_chain_side_pattern_order(link_count: int) -> tuple[tuple[str, ...], ...]:
    """Return a finite bank-pattern order before generic compactness pruning.

    Straight rows, two-row snakes, and mirrored L-banks are explicit structural
    construction classes.  Remaining orthogonal side sequences are retained as
    a bounded fallback, so the ordering describes geometry grammar rather than
    a fixture-specific coordinate template.
    """
    sides = ("EAST", "NORTH", "WEST", "SOUTH")
    preferred: list[tuple[str, ...]] = []
    if link_count == 3:
        preferred.extend((side,) * link_count for side in sides)
        preferred.extend(
            (
                ("EAST", "NORTH", "WEST"),
                ("WEST", "NORTH", "EAST"),
                ("EAST", "SOUTH", "WEST"),
                ("WEST", "SOUTH", "EAST"),
                ("NORTH", "EAST", "SOUTH"),
                ("SOUTH", "EAST", "NORTH"),
                ("NORTH", "WEST", "SOUTH"),
                ("SOUTH", "WEST", "NORTH"),
            )
        )
        preferred.extend(
            (
                ("EAST", "NORTH", "EAST"),
                ("EAST", "SOUTH", "EAST"),
                ("WEST", "NORTH", "WEST"),
                ("WEST", "SOUTH", "WEST"),
                ("NORTH", "EAST", "NORTH"),
                ("NORTH", "WEST", "NORTH"),
                ("SOUTH", "EAST", "SOUTH"),
                ("SOUTH", "WEST", "SOUTH"),
            )
        )
    preferred_set = set(preferred)
    return tuple(
        (
            *preferred,
            *(
                pattern
                for pattern in product(sides, repeat=link_count)
                if pattern not in preferred_set
            ),
        )
    )


def _explicit_local_chain_bank_modules(
    context: _PlacementSearchContext,
    zone_codes: tuple[str, ...],
    shapes: Mapping[str, Sequence[tuple[int, int, int, int, int]]],
    *,
    result_limit: int,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Synthesize exact chain interfaces while preserving bank topology classes."""
    if len(zone_codes) < 2 or result_limit <= 0:
        return ()
    shape_rows = _bounded_local_shape_rows(tuple(shapes[code] for code in zone_codes))
    if not shape_rows:
        return ()
    alignments = ("LOW", "CENTER", "HIGH")
    selected: list[dict[str, PlacedRectangleV1]] = []
    selected_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    for side_pattern in _local_chain_side_pattern_order(len(zone_codes) - 1):
        best: dict[str, PlacedRectangleV1] | None = None
        best_key: tuple[object, ...] | None = None
        for shape_row in shape_rows:
            first_shape = shape_row[0]
            initial = {zone_codes[0]: _local_rectangle_at(zone_codes[0], first_shape, 0, 0)}
            if not _local_bbox_fits_site_extents(context, initial):
                continue
            for alignment_row in product(alignments, repeat=len(zone_codes) - 1):
                state = initial
                for index, (side, alignment) in enumerate(
                    zip(side_pattern, alignment_row, strict=True), start=1
                ):
                    parent = state[zone_codes[index - 1]]
                    shape = shape_row[index]
                    x_mm, y_mm = _local_adjacent_origin(parent, shape[3], shape[4], side, alignment)
                    child = _local_rectangle_at(zone_codes[index], shape, x_mm, y_mm)
                    if not rectangles_share_positive_edge(parent, child):
                        break
                    if not _local_rectangles_clear(child, state):
                        break
                    next_state = {**state, zone_codes[index]: child}
                    if not _local_bbox_fits_site_extents(context, next_state):
                        break
                    state = next_state
                else:
                    if len(state) != len(zone_codes):
                        continue
                    normalized = _normalize_local_placements(state)
                    signature = _module_signature(normalized)
                    if signature in selected_signatures:
                        continue
                    key = _local_compactness_key(normalized, context, "X")
                    if best_key is None or key < best_key:
                        best, best_key = normalized, key
        if best is None:
            continue
        signature = _module_signature(best)
        if signature in selected_signatures:
            continue
        selected.append(best)
        selected_signatures.add(signature)
        if len(selected) >= result_limit:
            break
    return tuple(selected)


def _local_main_process_compositions(
    context: _PlacementSearchContext,
    layout_family: str,
    process_axis: str,
    process_direction: str,
    *,
    result_limit: int = 24,
) -> tuple[LocalBuildingCompositionV1, ...]:
    """Embed the frozen seven-zone MUST path in compact local 2D space.

    ``boundary_bounds`` contributes only its two extents: no boundary vertex,
    obstacle, entrance, or site event coordinate is read by this constructor.
    Each next room is attached to its already-placed MUST predecessor using an
    exact face and LOW/CENTER/HIGH edge alignment. A finite compact frontier
    prevents the old one-dimensional path from consuming the local search.
    """
    main_codes = MAIN_PROCESS_ZONE_CODES
    parent_by_zone = {
        "primary_precooling_room": "sorting_packaging_room",
        "raw_fruit_buffer": "primary_precooling_room",
        "secondary_precooling_room": "sorting_packaging_room",
        "coating_room": "secondary_precooling_room",
        "finished_goods_room": "coating_room",
        "shipping_channel": "finished_goods_room",
    }
    expansion_order = (
        "primary_precooling_room",
        "secondary_precooling_room",
        "raw_fruit_buffer",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    shapes = {code: _local_dimension_shapes(context, code) for code in main_codes}
    if any(not shapes[code] for code in main_codes):
        return ()
    alignments = ("LOW", "CENTER", "HIGH")
    frontier: list[Mapping[str, PlacedRectangleV1]] = []
    for shape in shapes["sorting_packaging_room"]:
        root = _local_rectangle_at("sorting_packaging_room", shape, 0, 0)
        candidate = {"sorting_packaging_room": root}
        if _local_bbox_fits_site_extents(context, candidate):
            frontier.append(candidate)
    frontier = list(
        _retain_compact_local_states(frontier, context, process_axis, LOCAL_COMPACT_FRONTIER_LIMIT)
    )

    for zone_code in expansion_order:
        parent_code = parent_by_zone[zone_code]
        expanded: dict[tuple[tuple[str, tuple[int, ...]], ...], dict[str, PlacedRectangleV1]] = {}
        for state in frontier:
            parent = state.get(parent_code)
            if parent is None:
                continue
            for shape in shapes[zone_code]:
                for side in ("WEST", "EAST", "SOUTH", "NORTH"):
                    for alignment in alignments:
                        x_mm, y_mm = _local_adjacent_origin(
                            parent, shape[3], shape[4], side, alignment
                        )
                        rectangle = _local_rectangle_at(zone_code, shape, x_mm, y_mm)
                        if not rectangles_share_positive_edge(parent, rectangle):
                            continue
                        if not _local_rectangles_clear(rectangle, state):
                            continue
                        next_state = {**state, zone_code: rectangle}
                        if not _local_bbox_fits_site_extents(context, next_state):
                            continue
                        if not _local_family_partial_valid(layout_family, next_state):
                            continue
                        if any(
                            zone_code in pair
                            and pair[0] in next_state
                            and pair[1] in next_state
                            and not rectangles_share_positive_edge(
                                next_state[pair[0]], next_state[pair[1]]
                            )
                            for pair in context.graph.must_adjacencies
                        ):
                            continue
                        signature = tuple(
                            (code, placed.bounds_mm + (placed.rotation_deg,))
                            for code, placed in sorted(next_state.items())
                        )
                        expanded.setdefault(signature, next_state)
        if not expanded:
            return ()
        frontier = list(
            _retain_compact_local_states(
                expanded.values(), context, process_axis, LOCAL_COMPACT_FRONTIER_LIMIT
            )
        )

    results: dict[tuple[tuple[str, tuple[int, ...]], ...], LocalBuildingCompositionV1] = {}
    for state in frontier:
        if set(state) != set(main_codes):
            continue
        try:
            _validate_main_process_skeleton_graph(context.graph, state)
        except LayoutAuthorityError:
            continue
        classification = classify_main_process_topology_v1(state)
        if layout_family == LINEAR_3_BAND and (
            classification.canonical_owner not in {STRAIGHT_LINEAR_BAND, OFFSET_LINEAR_BAND}
            or classification.process_axis != process_axis
            or classification.process_direction != process_direction
        ):
            continue
        normalized = _normalize_local_placements(state)
        outline, bounds = _local_outline_class(normalized)
        signature = tuple(
            (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
            for code, rectangle in sorted(normalized.items())
        )
        results.setdefault(
            signature,
            LocalBuildingCompositionV1(
                layout_family=layout_family,
                process_axis=process_axis,
                process_direction=process_direction,
                zone_placements=tuple(
                    LocalZonePlacementV1(code, zone_band_assignment(code), rectangle)
                    for code, rectangle in sorted(normalized.items())
                ),
                must_interfaces=tuple(
                    pair
                    for pair in context.graph.must_adjacencies
                    if pair[0] in normalized and pair[1] in normalized
                ),
                spine_axis=process_axis if layout_family == LONGITUDINAL_PROCESS_SPINE else None,
                spine_zone_codes=(
                    (
                        "sorting_packaging_room",
                        "secondary_precooling_room",
                        "coating_room",
                        "finished_goods_room",
                        "shipping_channel",
                    )
                    if layout_family == LONGITUDINAL_PROCESS_SPINE
                    else ()
                ),
                side_bank_zone_codes=("raw_fruit_buffer", "primary_precooling_room"),
                outline_class=outline,
                bounds_mm=bounds,
            ),
        )
    return _retain_compact_local_compositions(
        results.values(), context, process_axis, min(result_limit, LOCAL_COMPACT_RESULT_LIMIT)
    )


def _synthesize_linear_3_band_local(
    context: _PlacementSearchContext, process_axis: str, process_direction: str
) -> tuple[LocalBuildingCompositionV1, ...]:
    """Compose upstream, core, and downstream bands along the process axis."""
    return _local_main_process_compositions(
        context,
        LINEAR_3_BAND,
        process_axis,
        process_direction,
        result_limit=16,
    )


def _synthesize_central_side_banks_local(
    context: _PlacementSearchContext, process_axis: str, process_direction: str
) -> tuple[LocalBuildingCompositionV1, ...]:
    """Compose raw and finished banks on opposing faces of the process core."""
    return _local_main_process_compositions(
        context,
        CENTRAL_PROCESS_WITH_SIDE_BANKS,
        process_axis,
        process_direction,
        result_limit=16,
    )


def _synthesize_longitudinal_spine_local(
    context: _PlacementSearchContext, process_axis: str, process_direction: str
) -> tuple[LocalBuildingCompositionV1, ...]:
    """Compose the process spine with raw and finished side-bank transitions."""
    return _local_main_process_compositions(
        context,
        LONGITUDINAL_PROCESS_SPINE,
        process_axis,
        process_direction,
        result_limit=16,
    )


def _local_bank_compositions(
    context: _PlacementSearchContext,
    zone_codes: tuple[str, ...],
    *,
    result_limit: int = 48,
) -> tuple[tuple[dict[str, PlacedRectangleV1], str, str], ...]:
    """Jointly pack a finite row/column bank from cumulative zone dimensions."""
    shape_options = {code: _local_dimension_shapes(context, code) for code in zone_codes}
    if any(not shape_options[code] for code in zone_codes):
        return ()
    results: dict[
        tuple[tuple[str, tuple[int, ...]], ...], tuple[dict[str, PlacedRectangleV1], str, str]
    ] = {}
    orders = tuple(
        sorted(
            {
                tuple(zone_codes[index] for index in order)
                for order in (
                    tuple(range(len(zone_codes))),
                    tuple(reversed(range(len(zone_codes)))),
                    (1, 0, 2) if len(zone_codes) == 3 else tuple(range(len(zone_codes))),
                    (2, 0, 1) if len(zone_codes) == 3 else tuple(reversed(range(len(zone_codes)))),
                )
            }
        )
    )
    for order in orders:
        for axis in ("X", "Y"):
            for shape_row in product(*(shape_options[code] for code in order)):
                cursor = 0
                packed: dict[str, PlacedRectangleV1] = {}
                for code, shape in zip(order, shape_row, strict=True):
                    x_span, y_span = shape[3], shape[4]
                    x_mm, y_mm = (cursor, 0) if axis == "X" else (0, cursor)
                    packed[code] = _local_rectangle_at(code, shape, x_mm, y_mm)
                    cursor += x_span if axis == "X" else y_span
                signature = tuple(
                    (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                    for code, rectangle in sorted(packed.items())
                )
                results.setdefault(signature, (packed, axis, "ROW" if axis == "X" else "COLUMN"))

    if len(zone_codes) == 3:
        shape_rows = tuple(product(*(shape_options[code] for code in zone_codes)))
        for shape_row in shape_rows:
            shape_by_code = dict(zip(zone_codes, shape_row, strict=True))
            for singleton in zone_codes:
                pair = tuple(code for code in zone_codes if code != singleton)
                for pair_order in (pair, tuple(reversed(pair))):
                    for pair_on_low_side in (True, False):
                        pair_shapes = tuple(shape_by_code[code] for code in pair_order)
                        singleton_shape = shape_by_code[singleton]
                        pair_width = sum(shape[3] for shape in pair_shapes)
                        pair_depth = max(shape[4] for shape in pair_shapes)
                        bank_width = max(pair_width, singleton_shape[3])
                        for pair_alignment in ("LOW", "CENTER", "HIGH"):
                            for singleton_alignment in ("LOW", "CENTER", "HIGH"):
                                if pair_alignment == "LOW":
                                    pair_x = 0
                                elif pair_alignment == "HIGH":
                                    pair_x = bank_width - pair_width
                                else:
                                    pair_x = (bank_width - pair_width) // 2
                                if singleton_alignment == "LOW":
                                    singleton_x = 0
                                elif singleton_alignment == "HIGH":
                                    singleton_x = bank_width - singleton_shape[3]
                                else:
                                    singleton_x = (bank_width - singleton_shape[3]) // 2
                                pair_y = singleton_shape[4] if not pair_on_low_side else 0
                                singleton_y = 0 if not pair_on_low_side else pair_depth
                                two_row_packed: dict[str, PlacedRectangleV1] = {}
                                cursor = pair_x
                                for code, shape in zip(pair_order, pair_shapes, strict=True):
                                    two_row_packed[code] = _local_rectangle_at(
                                        code, shape, cursor, pair_y
                                    )
                                    cursor += shape[3]
                                two_row_packed[singleton] = _local_rectangle_at(
                                    singleton, singleton_shape, singleton_x, singleton_y
                                )
                                signature = tuple(
                                    (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                                    for code, rectangle in sorted(two_row_packed.items())
                                )
                                results.setdefault(signature, (two_row_packed, "Y", "TWO_ROW"))

    def bank_key(row: tuple[dict[str, PlacedRectangleV1], str, str]) -> tuple[object, ...]:
        placements = row[0]
        left, bottom, right, top = _local_bbox_bounds(placements)
        width_mm, height_mm = right - left, top - bottom
        signature = tuple(
            (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
            for code, rectangle in sorted(placements.items())
        )
        return max(width_mm, height_mm), width_mm * height_mm, width_mm, height_mm, signature

    ordered = sorted(results.values(), key=bank_key)
    return tuple(ordered[:result_limit])


def _local_must_chain_module_compositions(
    context: _PlacementSearchContext,
    zone_codes: tuple[str, ...],
    *,
    result_limit: int,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Synthesize a compact 2D rigid module from an exact directed MUST chain.

    Coordinates are cumulative room extents and positive shared-edge
    alignments in a local frame.  This is a finite module-layout enumeration,
    not a site-coordinate search; the completed module is immutable once it is
    handed to the site assembler.
    """
    if not zone_codes or result_limit <= 0:
        return ()
    shapes = {code: _local_dimension_shapes(context, code) for code in zone_codes}
    if any(not shapes[code] for code in zone_codes):
        return ()
    structural_modules = _explicit_local_chain_bank_modules(
        context,
        zone_codes,
        shapes,
        result_limit=min(result_limit, LOCAL_COMPACT_RESULT_LIMIT),
    )
    if len(structural_modules) >= result_limit:
        # The structured bank grammar already supplied the full requested
        # finite variant set.  The generic orthogonal frontier below is only
        # a compatibility fill for missing slots; expanding it cannot affect
        # the returned candidates when the structural set is complete.
        return structural_modules[:result_limit]
    frontier: tuple[Mapping[str, PlacedRectangleV1], ...] = tuple(
        {zone_codes[0]: _local_rectangle_at(zone_codes[0], shape, 0, 0)}
        for shape in shapes[zone_codes[0]]
    )
    frontier = _retain_compact_local_states(
        frontier,
        context,
        "X",
        min(LOCAL_COMPACT_FRONTIER_LIMIT, max(result_limit * 4, result_limit)),
    )
    for index, zone_code in enumerate(zone_codes[1:], start=1):
        parent_code = zone_codes[index - 1]
        expanded: dict[tuple[tuple[str, tuple[int, ...]], ...], dict[str, PlacedRectangleV1]] = {}
        for state in frontier:
            parent = state[parent_code]
            for shape in shapes[zone_code]:
                for side in ("WEST", "EAST", "SOUTH", "NORTH"):
                    for alignment in ("LOW", "CENTER", "HIGH"):
                        x_mm, y_mm = _local_adjacent_origin(
                            parent, shape[3], shape[4], side, alignment
                        )
                        rectangle = _local_rectangle_at(zone_code, shape, x_mm, y_mm)
                        if not rectangles_share_positive_edge(parent, rectangle):
                            continue
                        if not _local_rectangles_clear(rectangle, state):
                            continue
                        next_state = {**state, zone_code: rectangle}
                        if not _local_bbox_fits_site_extents(context, next_state):
                            continue
                        signature = tuple(
                            (code, placed.bounds_mm + (placed.rotation_deg,))
                            for code, placed in sorted(next_state.items())
                        )
                        expanded.setdefault(signature, next_state)
        if not expanded:
            frontier = ()
            break
        frontier = _retain_compact_local_states(
            expanded.values(),
            context,
            "X",
            min(LOCAL_COMPACT_FRONTIER_LIMIT, max(result_limit * 4, result_limit)),
        )
    result_rows: dict[tuple[tuple[str, tuple[int, ...]], ...], dict[str, PlacedRectangleV1]] = {
        _module_signature(module): module for module in structural_modules
    }
    for state in frontier:
        if all(
            rectangles_share_positive_edge(state[first], state[second])
            for first, second in zip(zone_codes, zone_codes[1:], strict=False)
        ):
            normalized = _normalize_local_placements(state)
            result_rows.setdefault(_module_signature(normalized), normalized)
    generic_rows = sorted(
        (
            row
            for signature, row in result_rows.items()
            if signature not in {_module_signature(module) for module in structural_modules}
        ),
        key=lambda row: _local_compactness_key(row, context, "X"),
    )
    return tuple(
        (*structural_modules, *generic_rows[: max(0, result_limit - len(structural_modules))])
    )


def _place_local_bank_against_zone(
    bank: Mapping[str, PlacedRectangleV1],
    root: PlacedRectangleV1,
    side: str,
    alignment: str,
) -> dict[str, PlacedRectangleV1]:
    """Translate a complete pre-packed bank rigidly to one selected core face."""
    bank_bounds = [rectangle.bounds_mm for rectangle in bank.values()]
    left = min(row[0] for row in bank_bounds)
    bottom = min(row[1] for row in bank_bounds)
    right = max(row[2] for row in bank_bounds)
    top = max(row[3] for row in bank_bounds)
    bank_width, bank_depth = right - left, top - bottom
    target_x, target_y = _local_adjacent_origin(root, bank_width, bank_depth, side, alignment)
    dx, dy = target_x - left, target_y - bottom
    return {
        code: _rectangle_from_mm(
            code,
            rectangle.bounds_mm[0] + dx,
            rectangle.bounds_mm[1] + dy,
            _mm(rectangle.width_m, field="local.width_m"),
            _mm(rectangle.depth_m, field="local.depth_m"),
            rectangle.rotation_deg,
        )
        for code, rectangle in bank.items()
    }


def _local_full_building_compositions(
    context: _PlacementSearchContext,
    main_composition: LocalBuildingCompositionV1,
    *,
    result_limit: int = 12,
) -> tuple[LocalBuildingCompositionV1, ...]:
    """Pack support/personnel as compact whole banks around the main composition."""
    main = main_composition.placements()
    main_codes = set(main)
    if main_codes != set(MAIN_PROCESS_ZONE_CODES) or not _local_bbox_fits_site_extents(
        context, main
    ):
        return ()
    support_banks = _local_bank_compositions(
        context,
        ("packaging_material_storage", "secondary_fruit_buffer", "frozen_fruit_room"),
        result_limit=12,
    )
    office_shapes = _local_dimension_shapes(context, "office")
    changing_shapes = _local_dimension_shapes(context, "changing_room")
    if not support_banks or not office_shapes or not changing_shapes:
        return ()
    results: dict[tuple[tuple[str, tuple[int, ...]], ...], LocalBuildingCompositionV1] = {}
    alignments = ("LOW", "CENTER", "HIGH")
    shipping = main["shipping_channel"]
    support_states: dict[tuple[tuple[str, tuple[int, ...]], ...], dict[str, PlacedRectangleV1]] = {}
    for bank, _bank_axis, _bank_shape in support_banks:
        for anchor_code in (
            "sorting_packaging_room",
            "secondary_precooling_room",
            "finished_goods_room",
            "shipping_channel",
        ):
            anchor = main[anchor_code]
            for support_side in ("WEST", "EAST", "SOUTH", "NORTH"):
                for support_alignment in alignments:
                    support = _place_local_bank_against_zone(
                        bank, anchor, support_side, support_alignment
                    )
                    if any(
                        not _local_rectangles_clear(rectangle, main)
                        for rectangle in support.values()
                    ):
                        continue
                    with_support = {**main, **support}
                    if not _local_bbox_fits_site_extents(context, with_support):
                        continue
                    signature = tuple(
                        (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                        for code, rectangle in sorted(with_support.items())
                    )
                    support_states.setdefault(signature, with_support)

    ordered_support_states = _retain_compact_local_states(
        support_states.values(),
        context,
        main_composition.process_axis,
        max(4, min(8, result_limit * 2)),
    )
    for support_state in ordered_support_states:
        for office_shape in office_shapes:
            for office_side in ("WEST", "EAST", "SOUTH", "NORTH"):
                for office_alignment in alignments:
                    office_x, office_y = _local_adjacent_origin(
                        shipping,
                        office_shape[3],
                        office_shape[4],
                        office_side,
                        office_alignment,
                    )
                    office = _local_rectangle_at("office", office_shape, office_x, office_y)
                    if not rectangles_share_positive_edge(office, shipping):
                        continue
                    if not _local_rectangles_clear(office, support_state):
                        continue
                    with_office = {**support_state, "office": office}
                    if not _local_bbox_fits_site_extents(context, with_office):
                        continue
                    for changing_shape in changing_shapes:
                        for changing_anchor_code in (
                            "office",
                            "shipping_channel",
                            "finished_goods_room",
                            "secondary_precooling_room",
                        ):
                            changing_anchor = with_office[changing_anchor_code]
                            for changing_side in ("WEST", "EAST", "SOUTH", "NORTH"):
                                for changing_alignment in alignments:
                                    changing_x, changing_y = _local_adjacent_origin(
                                        changing_anchor,
                                        changing_shape[3],
                                        changing_shape[4],
                                        changing_side,
                                        changing_alignment,
                                    )
                                    changing = _local_rectangle_at(
                                        "changing_room", changing_shape, changing_x, changing_y
                                    )
                                    complete = {**with_office, "changing_room": changing}
                                    if not _local_rectangles_clear(changing, with_office):
                                        continue
                                    if set(complete) != set(context.graph.nodes):
                                        continue
                                    if not _local_bbox_fits_site_extents(context, complete):
                                        continue
                                    try:
                                        _validate_graph_completeness(context.graph, complete)
                                    except LayoutAuthorityError:
                                        continue
                                    normalized = _normalize_local_placements(complete)
                                    outline, bounds = _local_outline_class(normalized)
                                    signature = tuple(
                                        (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                                        for code, rectangle in sorted(normalized.items())
                                    )
                                    results.setdefault(
                                        signature,
                                        LocalBuildingCompositionV1(
                                            layout_family=main_composition.layout_family,
                                            process_axis=main_composition.process_axis,
                                            process_direction=main_composition.process_direction,
                                            zone_placements=tuple(
                                                LocalZonePlacementV1(
                                                    code,
                                                    zone_band_assignment(code),
                                                    rectangle,
                                                )
                                                for code, rectangle in sorted(normalized.items())
                                            ),
                                            must_interfaces=tuple(
                                                pair for pair in context.graph.must_adjacencies
                                            ),
                                            spine_axis=main_composition.spine_axis,
                                            spine_zone_codes=main_composition.spine_zone_codes,
                                            side_bank_zone_codes=main_composition.side_bank_zone_codes,
                                            outline_class=outline,
                                            bounds_mm=bounds,
                                        ),
                                    )
                                    if len(results) >= max(result_limit * 8, result_limit):
                                        return _retain_compact_local_compositions(
                                            results.values(),
                                            context,
                                            main_composition.process_axis,
                                            result_limit,
                                        )
    return _retain_compact_local_compositions(
        results.values(), context, main_composition.process_axis, result_limit
    )


def _structured_plan_from_composition(
    composition: LocalBuildingCompositionV1,
    placements: Mapping[str, PlacedRectangleV1],
    *,
    obstacles: tuple[PolygonMM, ...],
    site_bounds: tuple[int, int, int, int],
) -> StructuredBuildingSkeletonV1:
    """Derive a non-authoritative planned frame and bands from fixed geometry."""
    outline, bounds = _local_outline_class(placements)
    envelope = BuildingEnvelopeV1(
        RECTANGLE,
        bounds,
        (bounds,),
        obstacles,
        site_bounds,
        "PLANNED_COMPOSITION_FRAME_NOT_FOOTPRINT_AUTHORITY",
        outline,
    )
    usage: dict[tuple[str, int], set[str]] = {}
    for code, rectangle in sorted(placements.items()):
        left, bottom, right, top = rectangle.bounds_mm
        for axis, coordinate in (
            ("X", left),
            ("X", right),
            ("Y", bottom),
            ("Y", top),
        ):
            usage.setdefault((axis, coordinate), set()).add(code)
    primary_axes = {
        key
        for key, zone_codes in usage.items()
        if len(zone_codes) > 1
        or key in {("X", bounds[0]), ("X", bounds[2]), ("Y", bounds[1]), ("Y", bounds[3])}
    }
    axis_usage = tuple(
        (axis, coordinate, tuple(sorted(usage[(axis, coordinate)])))
        for axis, coordinate in sorted(primary_axes)
    )
    grid = PrimaryGridV1(
        tuple(sorted(coordinate for axis, coordinate in primary_axes if axis == "X")),
        tuple(sorted(coordinate for axis, coordinate in primary_axes if axis == "Y")),
        (),
        (),
        axis_usage,
    )
    band_specs = (
        (
            RAW_SIDE_BAND,
            "RAW_SIDE_GROUP",
            ("raw_fruit_buffer", "primary_precooling_room"),
            "UPSTREAM",
        ),
        (
            PROCESS_CORE_BAND,
            "PROCESSING_CORE_GROUP",
            ("sorting_packaging_room", "coating_room"),
            "CORE",
        ),
        (
            FINISHED_SIDE_BAND,
            "FINISHED_SIDE_GROUP",
            ("secondary_precooling_room", "finished_goods_room", "shipping_channel"),
            "DOWNSTREAM",
        ),
        (
            SUPPORT_BAND,
            "SUPPORT_GROUP",
            ("packaging_material_storage", "secondary_fruit_buffer", "frozen_fruit_room"),
            "SUBORDINATE_BRANCH",
        ),
        (PERSONNEL_EDGE_BAND, "PERSONNEL_GROUP", ("office", "changing_room"), "PERIPHERAL"),
    )
    bands: list[FunctionalBandV1] = []
    for band_code, group_code, zone_codes, role in band_specs:
        rows = tuple(placements[code].bounds_mm for code in zone_codes)
        band_bounds = (
            min(row[0] for row in rows),
            min(row[1] for row in rows),
            max(row[2] for row in rows),
            max(row[3] for row in rows),
        )
        bands.append(
            FunctionalBandV1(
                band_code,
                group_code,
                zone_codes,
                band_bounds,
                composition.process_axis,
                role,
                None,
                ("coating_room",) if band_code == FINISHED_SIDE_BAND else (),
                rows,
            )
        )
    return StructuredBuildingSkeletonV1(
        composition.layout_family,
        composition.process_axis,
        envelope,
        grid,
        tuple(bands),
        support_side="LOCAL_COMPOSITION",
        personnel_side="LOCAL_COMPOSITION",
        process_direction=composition.process_direction,
    ).with_placements(placements)


def _synthesize_linear_3_band_main_process(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    shipping: PlacedRectangleV1 | None,
    *,
    variant_index: int,
    failure_reasons: list[str],
) -> dict[str, PlacedRectangleV1] | None:
    del shipping
    candidates = _linear_3_band_geometry(context, plan, variant_index, failure_reasons)
    if not candidates:
        if not failure_reasons:
            failure_reasons.append("LINEAR_3_BAND_JOINT_PACKING_OR_MUST_INTERFACE_UNAVAILABLE")
        return None
    return candidates[0]


def _synthesize_central_process_with_side_banks_main_process(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    shipping: PlacedRectangleV1 | None,
    *,
    variant_index: int,
    failure_reasons: list[str],
) -> dict[str, PlacedRectangleV1] | None:
    del shipping
    candidates = _central_side_bank_geometry(context, plan, variant_index, failure_reasons)
    if not candidates:
        if not failure_reasons:
            failure_reasons.append("CENTRAL_SIDE_BANK_JOINT_PACKING_OR_MUST_INTERFACE_UNAVAILABLE")
        return None
    return candidates[0]


def _synthesize_longitudinal_process_spine_main_process(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    shipping: PlacedRectangleV1 | None,
    *,
    variant_index: int,
    failure_reasons: list[str],
) -> dict[str, PlacedRectangleV1] | None:
    del shipping
    candidates = _longitudinal_spine_geometry(context, plan, variant_index, failure_reasons)
    if not candidates:
        if not failure_reasons:
            failure_reasons.append("LONGITUDINAL_SPINE_JOINT_PACKING_OR_MUST_INTERFACE_UNAVAILABLE")
        return None
    return candidates[0]


def _synthesize_family_main_process(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    shipping: PlacedRectangleV1 | None,
    *,
    variant_index: int,
    failure_reasons: list[str],
) -> dict[str, PlacedRectangleV1] | None:
    # The shipping rectangle is now packed together with the other finished
    # band members. Keep the positional parameter for the stable internal
    # call seam, but do not use it as a room-chain root.
    del shipping
    constructors = {
        LINEAR_3_BAND: _synthesize_linear_3_band_main_process,
        CENTRAL_PROCESS_WITH_SIDE_BANKS: _synthesize_central_process_with_side_banks_main_process,
        LONGITUDINAL_PROCESS_SPINE: _synthesize_longitudinal_process_spine_main_process,
    }
    constructor = constructors.get(plan.layout_family)
    if constructor is None:
        failure_reasons.append("DIRECT_LAYOUT_FAMILY_SYNTHESIZER_UNAVAILABLE")
        return None
    return constructor(
        context,
        plan,
        None,
        variant_index=variant_index,
        failure_reasons=failure_reasons,
    )


def synthesize_band_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    band_code: str,
    zone_codes: Sequence[str],
    *,
    packing_axis: str,
    reverse_order: bool,
    cross_alignment: str,
    fixed_placements: Mapping[str, PlacedRectangleV1] | None = None,
    transition_zone_codes: frozenset[str] = frozenset(),
    result_limit: int = 12,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Pack a whole functional band from its bounds and cumulative dimensions.

    This is a finite edge-derived composition: coordinates come from
    authoritative room dimensions and a selected band edge. Passing
    ``band_code=None`` constructs a complete frozen MUST chain across its
    distinct planned functional bands; production selects one deterministic
    path pattern per structural variant rather than sweeping every path.
    """
    if packing_axis not in {"X", "Y"} or cross_alignment not in {"LOW", "CENTER", "HIGH"}:
        return ()
    if result_limit <= 0 or not zone_codes:
        return ()
    band = plan.band_for_zone(zone_codes[0])
    if (
        band.band_code != band_code
        or any(
            plan.band_for_zone(code).band_code != band_code and code not in transition_zone_codes
            for code in zone_codes
        )
        or not transition_zone_codes
        <= set(next(row.transition_zone_codes for row in plan.bands if row.band_code == band_code))
    ):
        return ()
    # Treat each exact envelope component as a finite packing container first.
    # The overall band bounds are retained as a final container so a rectangle
    # spanning a contiguous component seam can still be admitted by the exact
    # union-coverage predicate.
    containers = tuple(dict.fromkeys((*band.regions_mm, band.bounds_mm)))
    order = tuple(reversed(zone_codes)) if reverse_order else tuple(zone_codes)
    candidates: list[dict[str, PlacedRectangleV1]] = []
    seen: set[tuple[tuple[str, tuple[int, int, int, int, int]], ...]] = set()
    for container in containers:
        left, bottom, right, top = container
        along_low, along_high = (left, right) if packing_axis == "X" else (bottom, top)
        cross_low, cross_high = (bottom, top) if packing_axis == "X" else (left, right)
        along_span = along_high - along_low
        cross_span = cross_high - cross_low
        choices_by_zone: list[tuple[tuple[int, int, int, int, int], ...]] = []
        for code in order:
            authority = context.authorities.get(code)
            if authority is None:
                return ()
            unique: dict[tuple[int, int], tuple[int, int, int, int, int]] = {}
            for width_mm, depth_mm in _zone_dimension_options(authority):
                for rotation in (0, 90):
                    actual_width, actual_depth = (
                        (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
                    )
                    if packing_axis == "X":
                        along_extent, cross_extent = actual_width, actual_depth
                    else:
                        along_extent, cross_extent = actual_depth, actual_width
                    if along_extent > along_span or cross_extent > cross_span:
                        continue
                    unique.setdefault(
                        (actual_width, actual_depth),
                        (width_mm, depth_mm, rotation, along_extent, cross_extent),
                    )
            variants = tuple(unique[key] for key in sorted(unique))
            if not variants:
                choices_by_zone = []
                break
            choices_by_zone.append(variants)
        if not choices_by_zone:
            continue

        for dimension_rows in product(*choices_by_zone):
            total_along = sum(row[3] for row in dimension_rows)
            max_cross = max(row[4] for row in dimension_rows)
            if total_along > along_span or max_cross > cross_span:
                continue
            cursor = along_high - total_along if reverse_order else along_low
            packed: dict[str, PlacedRectangleV1] = {}
            valid = True
            for code, (width_mm, depth_mm, rotation, along_extent, cross_extent) in zip(
                order, dimension_rows, strict=True
            ):
                if cross_alignment == "LOW":
                    cross_origin = cross_low
                elif cross_alignment == "HIGH":
                    cross_origin = cross_high - cross_extent
                else:
                    cross_origin = cross_low + (cross_span - cross_extent) // 2
                if packing_axis == "X":
                    x_mm, y_mm = cursor, cross_origin
                else:
                    x_mm, y_mm = cross_origin, cursor
                rectangle = _rectangle_from_mm(code, x_mm, y_mm, width_mm, depth_mm, rotation)
                if (
                    not plan.admits_to_band(code, rectangle, band_code)
                    or _geometry_rejection_reason(
                        rectangle, {**(fixed_placements or {}), **packed}, context
                    )
                    is not None
                ):
                    valid = False
                    break
                packed[code] = rectangle
                cursor += -along_extent if reverse_order else along_extent
            if not valid:
                continue
            signature = tuple(
                sorted(
                    (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                    for code, rectangle in packed.items()
                )
            )
            if signature in seen:
                continue
            seen.add(signature)
            candidates.append(packed)
            if len(candidates) >= result_limit:
                return tuple(candidates)
    return tuple(candidates)


def _band_chain_shape_options(
    context: _PlacementSearchContext, zone_code: str
) -> tuple[tuple[int, int, int, int, int], ...]:
    """Return unique authority-derived post-rotation shapes for a band member."""
    authority = context.authorities.get(zone_code)
    if authority is None:
        return ()
    unique: dict[tuple[int, int], tuple[int, int, int, int, int]] = {}
    for width_mm, depth_mm in _zone_dimension_options(authority):
        for rotation in (0, 90):
            actual_width, actual_depth = (
                (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
            )
            unique.setdefault(
                (actual_width, actual_depth),
                (width_mm, depth_mm, rotation, actual_width, actual_depth),
            )
    return tuple(unique[key] for key in sorted(unique))


def _direct_planned_band_edge_options(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    zone_code: str,
    placed: Mapping[str, PlacedRectangleV1],
    *,
    variant_index: int,
) -> tuple[PlacedRectangleV1, ...]:
    """Place one zone on exact MUST edges without legacy skeleton-root filters."""
    neighbors = _must_neighbors(zone_code, placed, context.graph)
    if not neighbors:
        return ()
    options: dict[tuple[int, int, int, int, int], PlacedRectangleV1] = {}
    for width_mm, depth_mm, rotation, actual_width, actual_depth in _band_chain_shape_options(
        context, zone_code
    ):
        anchors = {
            anchor
            for neighbor in neighbors
            for anchor in _edge_anchors(neighbor, actual_width, actual_depth)
        }
        for x_mm, y_mm in sorted(anchors):
            rectangle = _rectangle_from_mm(zone_code, x_mm, y_mm, width_mm, depth_mm, rotation)
            if (
                not _rectangle_is_usable(
                    rectangle,
                    placed,
                    context.boundary,
                    context.boundary_bounds,
                    context.obstacles,
                )
                or not plan.admits(zone_code, rectangle)
                or any(
                    not rectangles_share_positive_edge(rectangle, neighbor)
                    for neighbor in neighbors
                )
            ):
                continue
            bounds = rectangle.bounds_mm
            options[(*bounds, rotation)] = rectangle
    ordered = tuple(options[key] for key in sorted(options))
    if not ordered:
        return ()
    offset = variant_index % len(ordered)
    return ordered[offset:] + ordered[:offset]


def _band_edge_chain_origins(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    band_code: str,
    first_zone: str,
    width_mm: int,
    depth_mm: int,
    fixed_placements: Mapping[str, PlacedRectangleV1],
) -> tuple[tuple[int, int], ...]:
    """Derive finite root origins from band boundaries or an exact MUST edge."""
    mandatory_neighbors = tuple(
        neighbor for neighbor in _must_neighbors(first_zone, fixed_placements, context.graph)
    )
    origins: set[tuple[int, int]] = set()
    for neighbor in mandatory_neighbors:
        origins.update(_edge_anchors(neighbor, width_mm, depth_mm))
    band = plan.band_for_zone(first_zone)
    for left, bottom, right, top in dict.fromkeys((*band.regions_mm, band.bounds_mm)):
        if right - left < width_mm or top - bottom < depth_mm:
            continue
        x_positions = {left, right - width_mm, left + (right - left - width_mm) // 2}
        y_positions = {bottom, top - depth_mm, bottom + (top - bottom - depth_mm) // 2}
        origins.update((x, y) for x in x_positions for y in y_positions)
    return tuple(sorted(origins))


def synthesize_must_chain_band_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    band_code: str | None,
    zone_codes: Sequence[str],
    *,
    fixed_placements: Mapping[str, PlacedRectangleV1] | None = None,
    transition_zone_codes: frozenset[str] = frozenset(),
    construction_variant_index: int | None = None,
    path_pattern_index: int | None = None,
    result_limit: int = 12,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Jointly enumerate finite orthogonal MUST-chain patterns inside a band.

    A pattern is selected as a complete discrete combination of authoritative
    room dimensions, cardinal edge transitions, and shared-edge alignments.
    Coordinates are derived only from the first band's exact edge anchor and
    successive shared rectangle edges; no local-event-axis or free-coordinate
    search is used. The full pattern is accepted only after exact band, site,
    obstacle, overlap, and positive-edge predicates pass.
    """
    if len(zone_codes) < 2 or result_limit <= 0:
        return ()
    band = plan.band_for_zone(zone_codes[0])
    if band_code is not None:
        if (
            band.band_code != band_code
            or any(
                plan.band_for_zone(code).band_code != band_code
                and code not in transition_zone_codes
                for code in zone_codes
            )
            or not transition_zone_codes
            <= set(
                next(row.transition_zone_codes for row in plan.bands if row.band_code == band_code)
            )
        ):
            return ()
    elif transition_zone_codes:
        return ()

    def admitted(code: str, rectangle: PlacedRectangleV1) -> bool:
        if band_code is None:
            return plan.admits(code, rectangle)
        return plan.admits_to_band(code, rectangle, band_code)

    fixed = dict(fixed_placements or {})
    shape_options = tuple(_band_chain_shape_options(context, code) for code in zone_codes)
    if any(not rows for rows in shape_options):
        return ()
    side_sequences = _must_chain_side_sequences(len(zone_codes) - 1)
    alignment_sequences = _must_chain_alignment_sequences(len(zone_codes) - 1)
    if construction_variant_index is None:
        path_patterns = tuple(product(side_sequences, alignment_sequences))
    else:
        selected_path_index = (
            construction_variant_index if path_pattern_index is None else path_pattern_index
        )
        # Each production construction variant owns one deterministic band
        # path. Repeating the full side/alignment product for every envelope
        # plan turns a finite structural search into an expensive nested sweep.
        path_patterns = (
            (
                side_sequences[selected_path_index % len(side_sequences)],
                alignment_sequences[construction_variant_index % len(alignment_sequences)],
            ),
        )
    shape_rows = tuple(product(*shape_options))
    if construction_variant_index is not None and shape_rows:
        offset = construction_variant_index % len(shape_rows)
        shape_rows = shape_rows[offset:] + shape_rows[:offset]
    results: list[dict[str, PlacedRectangleV1]] = []
    signatures: set[tuple[tuple[str, tuple[int, int, int, int, int]], ...]] = set()

    for shapes in shape_rows:
        first_width, first_depth = shapes[0][3], shapes[0][4]
        origins = _band_edge_chain_origins(
            context,
            plan,
            band_code or band.band_code,
            zone_codes[0],
            first_width,
            first_depth,
            fixed,
        )
        if construction_variant_index is not None and origins:
            offset = construction_variant_index % len(origins)
            origins = origins[offset:] + origins[:offset]
        for origin_x, origin_y in origins:
            first = _rectangle_from_mm(
                zone_codes[0], origin_x, origin_y, shapes[0][0], shapes[0][1], shapes[0][2]
            )
            if (
                not admitted(zone_codes[0], first)
                or any(rectangles_overlap(first, other) for other in fixed.values())
                or any(
                    not rectangles_share_positive_edge(first, neighbor)
                    for neighbor in _must_neighbors(zone_codes[0], fixed, context.graph)
                )
            ):
                continue
            for side_sequence, alignment_sequence in path_patterns:
                packed: dict[str, PlacedRectangleV1] = {zone_codes[0]: first}
                valid = True
                for index, (side, alignment) in enumerate(
                    zip(side_sequence, alignment_sequence, strict=True), start=1
                ):
                    previous = packed[zone_codes[index - 1]]
                    width_mm, depth_mm, rotation, actual_width, actual_depth = shapes[index]
                    left, bottom, right, top = previous.bounds_mm
                    if side in {"EAST", "WEST"}:
                        y_origin = (
                            bottom
                            if alignment == "LOW"
                            else top - actual_depth
                            if alignment == "HIGH"
                            else bottom + (top - bottom - actual_depth) // 2
                        )
                        x_origin = right if side == "EAST" else left - actual_width
                    else:
                        x_origin = (
                            left
                            if alignment == "LOW"
                            else right - actual_width
                            if alignment == "HIGH"
                            else left + (right - left - actual_width) // 2
                        )
                        y_origin = top if side == "NORTH" else bottom - actual_depth
                    rectangle = _rectangle_from_mm(
                        zone_codes[index], x_origin, y_origin, width_mm, depth_mm, rotation
                    )
                    if (
                        not rectangles_share_positive_edge(previous, rectangle)
                        or not admitted(zone_codes[index], rectangle)
                        or any(
                            rectangles_overlap(rectangle, other)
                            for other in (*fixed.values(), *packed.values())
                        )
                        or any(
                            not rectangles_share_positive_edge(rectangle, neighbor)
                            for neighbor in _must_neighbors(
                                zone_codes[index], {**fixed, **packed}, context.graph
                            )
                        )
                    ):
                        valid = False
                        break
                    packed[zone_codes[index]] = rectangle
                if not valid:
                    continue
                signature = tuple(
                    sorted(
                        (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                        for code, rectangle in packed.items()
                    )
                )
                if signature in signatures:
                    continue
                signatures.add(signature)
                results.append(packed)
                if len(results) >= result_limit:
                    return tuple(results)
    return tuple(results)


def _family_main_band_packings(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    *,
    band_sequence: tuple[tuple[str, tuple[str, ...], str, frozenset[str]], ...],
    variant_index: int,
    failure_reasons: list[str] | None = None,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    reverse = bool(variant_index % 2)
    alignment = ("LOW", "CENTER", "HIGH")[variant_index % 3]
    merged_candidates: list[dict[str, PlacedRectangleV1]] = []

    def pack_band(index: int, placed: dict[str, PlacedRectangleV1]) -> None:
        if len(merged_candidates) >= 12:
            return
        if index == len(band_sequence):
            try:
                _validate_main_process_skeleton_graph(context.graph, placed)
            except LayoutAuthorityError:
                if failure_reasons is not None and not failure_reasons:
                    failure_reasons.append("GRAPH_HARD_VALIDATION")
                return
            merged_candidates.append(dict(placed))
            return

        spec = band_sequence[index]
        band_code, zone_codes, preferred_axis, transition_zone_codes = spec
        if tuple(zone_codes) in {
            ("raw_fruit_buffer", "primary_precooling_room"),
            (
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
            ),
        }:
            rows = synthesize_must_chain_band_geometry(
                context,
                plan,
                band_code,
                zone_codes,
                fixed_placements=placed,
                transition_zone_codes=transition_zone_codes,
                construction_variant_index=variant_index,
                result_limit=1,
            )
            if rows:
                for row in rows:
                    pack_band(index + 1, {**placed, **row})
                    if len(merged_candidates) >= 12:
                        return
            elif failure_reasons is not None and not failure_reasons:
                failure_reasons.append(f"BAND_PACKING_UNAVAILABLE:{band_code}")
            return
        alternate_axis = "Y" if preferred_axis == "X" else "X"
        axis_order = (
            (preferred_axis, alternate_axis) if not reverse else (alternate_axis, preferred_axis)
        )
        found_for_band = False
        for packing_axis in axis_order:
            for band_reverse in (reverse ^ bool(index % 2), not (reverse ^ bool(index % 2))):
                for cross_alignment in (alignment, "LOW", "CENTER", "HIGH"):
                    rows = synthesize_band_geometry(
                        context,
                        plan,
                        band_code,
                        zone_codes,
                        packing_axis=packing_axis,
                        reverse_order=band_reverse,
                        cross_alignment=cross_alignment,
                        fixed_placements=placed,
                        transition_zone_codes=transition_zone_codes,
                        result_limit=12,
                    )
                    if rows:
                        found_for_band = True
                    for row in rows:
                        pack_band(index + 1, {**placed, **row})
                        if len(merged_candidates) >= 12:
                            return
        if not found_for_band and failure_reasons is not None and not failure_reasons:
            failure_reasons.append(f"BAND_PACKING_UNAVAILABLE:{band_code}")

    pack_band(0, {})
    return tuple(merged_candidates)


def _linear_3_band_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    variant_index: int,
    failure_reasons: list[str],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Place the exact process chain through its three planned functional bands."""
    variant_round = (variant_index // 3) % 3
    forward_side = {
        ("X", "POSITIVE"): "EAST",
        ("X", "NEGATIVE"): "WEST",
        ("Y", "POSITIVE"): "NORTH",
        ("Y", "NEGATIVE"): "SOUTH",
    }[(plan.process_axis, plan.process_direction)]
    cross_sides = ("NORTH", "SOUTH") if plan.process_axis == "X" else ("EAST", "WEST")
    selected_cross_side = cross_sides[variant_round % len(cross_sides)]
    opposite_forward_side = {
        "EAST": "WEST",
        "WEST": "EAST",
        "NORTH": "SOUTH",
        "SOUTH": "NORTH",
    }[forward_side]
    opposite_cross_side = {
        "NORTH": "SOUTH",
        "SOUTH": "NORTH",
        "EAST": "WEST",
        "WEST": "EAST",
    }[selected_cross_side]
    finished_paths = (
        (forward_side, selected_cross_side, opposite_forward_side),
        (forward_side, opposite_cross_side, opposite_forward_side),
        (forward_side, forward_side, forward_side),
    )
    raw_sides = ("NORTH", "SOUTH") if plan.process_axis == "X" else ("EAST", "WEST")
    raw_order = raw_sides[variant_round % 2 :] + raw_sides[: variant_round % 2]
    side_sequences = _must_chain_side_sequences(3)
    finished_path_order = finished_paths[variant_round:] + finished_paths[:variant_round]
    raw_found = False
    for raw_side in raw_order:
        raw_path_index = _must_chain_side_sequences(1).index((raw_side,))
        raw_rows = synthesize_must_chain_band_geometry(
            context,
            plan,
            "RAW_SIDE_BAND",
            ("raw_fruit_buffer", "primary_precooling_room"),
            construction_variant_index=variant_index,
            path_pattern_index=raw_path_index,
            result_limit=1,
        )
        raw_found = raw_found or bool(raw_rows)
        for raw in raw_rows:
            core_options = _direct_planned_band_edge_options(
                context,
                plan,
                "sorting_packaging_room",
                raw,
                variant_index=variant_index,
            )
            for core in core_options:
                placed = {**raw, "sorting_packaging_room": core}
                for finished_path in finished_path_order:
                    finished_path_index = side_sequences.index(finished_path)
                    finished_rows = synthesize_must_chain_band_geometry(
                        context,
                        plan,
                        None,
                        (
                            "secondary_precooling_room",
                            "coating_room",
                            "finished_goods_room",
                            "shipping_channel",
                        ),
                        fixed_placements=placed,
                        transition_zone_codes=frozenset(),
                        construction_variant_index=variant_index,
                        path_pattern_index=finished_path_index,
                        result_limit=1,
                    )
                    for finished in finished_rows:
                        candidate = {**placed, **finished}
                        try:
                            _validate_main_process_skeleton_graph(context.graph, candidate)
                        except LayoutAuthorityError:
                            continue
                        return (candidate,)
    if not raw_found and failure_reasons is not None and not failure_reasons:
        failure_reasons.append("BAND_PACKING_UNAVAILABLE:RAW_SIDE_BAND")
        return ()
    if failure_reasons is not None and not failure_reasons:
        failure_reasons.append("BAND_PACKING_UNAVAILABLE:INTER_BAND_INTERFACE_OR_FINISHED_SIDE")
    return ()


def _central_side_bank_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    variant_index: int,
    failure_reasons: list[str],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Place the process core first, then construct its two opposing banks."""
    cross_axis = "Y" if plan.process_axis == "X" else "X"
    return _family_main_band_packings(
        context,
        plan,
        band_sequence=(
            ("PROCESS_CORE_BAND", ("sorting_packaging_room",), cross_axis, frozenset()),
            (
                "RAW_SIDE_BAND",
                ("raw_fruit_buffer", "primary_precooling_room"),
                plan.process_axis,
                frozenset(),
            ),
            (
                "FINISHED_SIDE_BAND",
                (
                    "secondary_precooling_room",
                    "coating_room",
                    "finished_goods_room",
                    "shipping_channel",
                ),
                plan.process_axis,
                frozenset({"coating_room"}),
            ),
        ),
        variant_index=variant_index,
        failure_reasons=failure_reasons,
    )


def _longitudinal_spine_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    variant_index: int,
    failure_reasons: list[str],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Construct the longitudinal spine from one complete band-constrained chain."""
    rows = synthesize_must_chain_band_geometry(
        context,
        plan,
        None,
        PLACEMENT_ZONE_ORDER[:7],
        construction_variant_index=variant_index + 1,
        result_limit=1,
    )
    if not rows and failure_reasons is not None and not failure_reasons:
        failure_reasons.append("BAND_PACKING_UNAVAILABLE:PROCESS_SPINE_CHAIN")
    return rows


def _direct_family_tail_zones(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    placed: Mapping[str, PlacedRectangleV1],
    *,
    variant_index: int,
    failure_reasons: list[str] | None = None,
) -> dict[str, PlacedRectangleV1] | None:
    support_axes = ("X", "Y") if variant_index % 2 == 0 else ("Y", "X")
    personnel_axes = ("Y", "X") if variant_index % 2 == 0 else ("X", "Y")
    alignments = ("LOW", "CENTER", "HIGH")
    for support_axis in support_axes:
        support_rows = synthesize_band_geometry(
            context,
            plan,
            SUPPORT_BAND,
            ("packaging_material_storage", "secondary_fruit_buffer", "frozen_fruit_room"),
            packing_axis=support_axis,
            reverse_order=bool(variant_index % 2),
            cross_alignment=alignments[variant_index % len(alignments)],
            fixed_placements=placed,
            result_limit=12,
        )
        if not support_rows:
            if failure_reasons is not None:
                failure_reasons.append("SUPPORT_BAND_PACKING_NO_GEOMETRY")
            continue
        for support_row in support_rows:
            with_support = {**placed, **support_row}
            for personnel_axis in personnel_axes:
                personnel_rows = synthesize_band_geometry(
                    context,
                    plan,
                    PERSONNEL_EDGE_BAND,
                    ("office", "changing_room"),
                    packing_axis=personnel_axis,
                    reverse_order=bool((variant_index + 1) % 2),
                    cross_alignment=alignments[(variant_index + 1) % len(alignments)],
                    fixed_placements=with_support,
                    result_limit=12,
                )
                if not personnel_rows:
                    if failure_reasons is not None:
                        failure_reasons.append("PERSONNEL_BAND_PACKING_NO_GEOMETRY")
                    continue
                for personnel_row in personnel_rows:
                    complete = {**with_support, **personnel_row}
                    if set(complete) != set(context.graph.nodes):
                        continue
                    try:
                        _validate_graph_completeness(context.graph, complete)
                    except LayoutAuthorityError:
                        if failure_reasons is not None:
                            failure_reasons.append("GRAPH_HARD_VALIDATION")
                        continue
                    return complete
    if failure_reasons is not None and not failure_reasons:
        failure_reasons.append("TAIL_BAND_PACKING_NO_VALID_COMBINATION")
    return None


def _whole_building_site_placements(
    context: _PlacementSearchContext,
    local_placements: Mapping[str, PlacedRectangleV1],
    *,
    result_limit: int = 24,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Rigidly orient/mirror/translate a complete local composition onto site events."""
    if not local_placements or result_limit <= 0:
        return ()
    source_rows = tuple(local_placements.values())
    if any(
        rectangles_overlap(first, second)
        for index, first in enumerate(source_rows)
        for second in source_rows[index + 1 :]
    ):
        return ()
    min_x, min_y, max_x, max_y = context.boundary_bounds

    x_events = {point[0] for point in context.boundary}
    y_events = {point[1] for point in context.boundary}
    for obstacle in context.obstacles:
        x_events.update(point[0] for point in obstacle)
        y_events.update(point[1] for point in obstacle)
    for segment in (context.main_entrance, _truck_segment(context.site_body)):
        x_events.update((segment[0][0], segment[1][0]))
        y_events.update((segment[0][1], segment[1][1]))

    candidates: list[dict[str, PlacedRectangleV1]] = []
    seen: set[tuple[tuple[str, tuple[int, int, int, int, int]], ...]] = set()
    source_bounds = _local_bbox_bounds(local_placements)
    source_left, source_bottom, source_right, source_top = source_bounds
    source_width, source_height = source_right - source_left, source_top - source_bottom
    rigid_variants: list[dict[str, PlacedRectangleV1]] = []
    for mirror_x, mirror_y, rotate_90 in product((False, True), repeat=3):
        transformed: dict[str, PlacedRectangleV1] = {}
        for code, rectangle in sorted(local_placements.items()):
            left, bottom, right, top = rectangle.bounds_mm
            x0, y0 = left - source_left, bottom - source_bottom
            width_mm, depth_mm = right - left, top - bottom
            if mirror_x:
                x0 = source_width - x0 - width_mm
            if mirror_y:
                y0 = source_height - y0 - depth_mm
            if rotate_90:
                x0, y0 = source_height - y0 - depth_mm, x0
                width_mm, depth_mm = depth_mm, width_mm
            transformed[code] = _rectangle_from_mm(
                code,
                x0,
                y0,
                _mm(rectangle.width_m, field="local.width_m"),
                _mm(rectangle.depth_m, field="local.depth_m"),
                (90 - rectangle.rotation_deg) % 180 if rotate_90 else rectangle.rotation_deg,
            )
        rigid_variants.append(transformed)

    variant_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    boundary_rectangle = _axis_aligned_rectangle_polygon_bounds(context.boundary)
    obstacle_rectangles = tuple(
        _axis_aligned_rectangle_polygon_bounds(obstacle) for obstacle in context.obstacles
    )
    exact_rectangle_site = boundary_rectangle is not None and all(
        obstacle is not None for obstacle in obstacle_rectangles
    )

    def ordered_pairs(x_values: set[int], y_values: set[int]) -> Iterator[tuple[int, int]]:
        """Yield finite event pairs in the former exact Manhattan order."""
        yield from sorted(
            product(x_values, y_values),
            key=lambda point: (abs(point[0]) + abs(point[1]), point[1], point[0]),
        )

    def rectangle_site_pairs(
        local_bounds: tuple[tuple[int, int, int, int], ...],
        x_values: set[int],
        y_values: set[int],
        *,
        limit_per_x: int,
    ) -> list[tuple[int, int]]:
        """Return a bounded exact prefix after subtracting obstacle dy intervals per dx."""
        ordered_x = sorted(x_values, key=lambda value: (abs(value), value))
        ordered_y = sorted(y_values, key=lambda value: (abs(value), value))
        rows: list[tuple[int, int]] = []
        exact_obstacles = tuple(row for row in obstacle_rectangles if row is not None)
        for dx in ordered_x:
            blocked_dy: list[tuple[int, int]] = []
            for left, bottom, right, top in local_bounds:
                moved_left, moved_right = left + dx, right + dx
                for obstacle_left, obstacle_bottom, obstacle_right, obstacle_top in exact_obstacles:
                    if not (moved_right < obstacle_left or moved_left > obstacle_right):
                        blocked_dy.append((obstacle_bottom - top, obstacle_top - bottom))
            blocked_dy.sort()
            merged: list[tuple[int, int]] = []
            for start, end in blocked_dy:
                if merged and start <= merged[-1][1] + 1:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            valid_for_x = 0
            interval_index = 0
            for dy in ordered_y:
                while interval_index < len(merged) and merged[interval_index][1] < dy:
                    interval_index += 1
                if interval_index < len(merged) and merged[interval_index][0] <= dy:
                    continue
                rows.append((dx, dy))
                valid_for_x += 1
                if valid_for_x >= limit_per_x:
                    break
        rows.sort(key=lambda row: (abs(row[0]) + abs(row[1]), row[1], row[0]))
        return rows

    for transformed in rigid_variants:
        local_bounds = tuple(rectangle.bounds_mm for rectangle in transformed.values())
        local_left = min(row[0] for row in local_bounds)
        local_bottom = min(row[1] for row in local_bounds)
        local_right = max(row[2] for row in local_bounds)
        local_top = max(row[3] for row in local_bounds)
        if local_right - local_left > max_x - min_x or local_top - local_bottom > max_y - min_y:
            continue
        dx_values = {
            event - edge for event in x_events for row in local_bounds for edge in (row[0], row[2])
        }
        dy_values = {
            event - edge for event in y_events for row in local_bounds for edge in (row[1], row[3])
        }
        # Closed no-build polygons reject even boundary contact. Coordinates
        # that merely coincide with an obstacle event therefore describe the
        # rejected boundary, not the first legal integer-mm placement beside
        # it. Include the immediately adjacent grid coordinate on both sides
        # of each obstacle event; this is exact 1 mm lattice enumeration, not
        # a geometric tolerance or clearance rule.
        obstacle_x_events = {point[0] for obstacle in context.obstacles for point in obstacle}
        obstacle_y_events = {point[1] for obstacle in context.obstacles for point in obstacle}
        dx_values.update(
            event - edge + step
            for event in obstacle_x_events
            for row in local_bounds
            for edge in (row[0], row[2])
            for step in (-GRID_MM, GRID_MM)
        )
        dy_values.update(
            event - edge + step
            for event in obstacle_y_events
            for row in local_bounds
            for edge in (row[1], row[3])
            for step in (-GRID_MM, GRID_MM)
        )
        dx_values.update((min_x - local_left, max_x - local_right))
        dy_values.update((min_y - local_bottom, max_y - local_top))
        dx_values = {
            value
            for value in dx_values
            if min_x <= local_left + value and local_right + value <= max_x
        }
        dy_values = {
            value
            for value in dy_values
            if min_y <= local_bottom + value and local_top + value <= max_y
        }
        variant_signature = tuple(
            (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
            for code, rectangle in sorted(transformed.items())
        )
        if variant_signature in variant_signatures:
            continue
        variant_signatures.add(variant_signature)
        translations: Iterable[tuple[int, int]]
        if exact_rectangle_site:
            translations = rectangle_site_pairs(
                local_bounds,
                dx_values,
                dy_values,
                limit_per_x=result_limit,
            )
        else:
            translations = ordered_pairs(dx_values, dy_values)
        for dx_mm, dy_mm in translations:
            if exact_rectangle_site:
                if any(
                    not (
                        row[2] + dx_mm < obstacle[0]
                        or row[0] + dx_mm > obstacle[2]
                        or row[3] + dy_mm < obstacle[1]
                        or row[1] + dy_mm > obstacle[3]
                    )
                    for row in local_bounds
                    for obstacle in obstacle_rectangles
                    if obstacle is not None
                ):
                    continue
                translated = {
                    code: _rectangle_from_mm(
                        code,
                        rectangle.bounds_mm[0] + dx_mm,
                        rectangle.bounds_mm[1] + dy_mm,
                        _mm(rectangle.width_m, field="local.width_m"),
                        _mm(rectangle.depth_m, field="local.depth_m"),
                        rectangle.rotation_deg,
                    )
                    for code, rectangle in sorted(transformed.items())
                }
                signature = tuple(
                    (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                    for code, rectangle in sorted(translated.items())
                )
                if signature in seen:
                    continue
                seen.add(signature)
                candidates.append(translated)
                if len(candidates) >= result_limit:
                    return tuple(candidates)
                continue
            translated = {
                code: _rectangle_from_mm(
                    code,
                    rectangle.bounds_mm[0] + dx_mm,
                    rectangle.bounds_mm[1] + dy_mm,
                    _mm(rectangle.width_m, field="local.width_m"),
                    _mm(rectangle.depth_m, field="local.depth_m"),
                    rectangle.rotation_deg,
                )
                for code, rectangle in sorted(transformed.items())
            }
            placed: dict[str, PlacedRectangleV1] = {}
            valid = True
            for code, rectangle in translated.items():
                if not _rectangle_is_usable(
                    rectangle,
                    placed,
                    context.boundary,
                    context.boundary_bounds,
                    context.obstacles,
                ):
                    valid = False
                    break
                placed[code] = rectangle
            if not valid:
                continue
            signature = tuple(
                (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                for code, rectangle in sorted(translated.items())
            )
            if signature in seen:
                continue
            seen.add(signature)
            candidates.append(translated)
            if len(candidates) >= result_limit:
                return tuple(candidates)
    return tuple(candidates)


def _direct_structured_candidates(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
) -> Iterator[dict[str, Any] | _SearchQuantumYield]:
    """Synthesize immutable functional modules, then assemble them at site bays."""
    reference_axis = context.structural_skeleton.ordering_axis
    alternate_axis = "Y" if reference_axis == "X" else "X"
    axis_priority = {reference_axis: 0, alternate_axis: 1}
    boundary_width = context.boundary_bounds[2] - context.boundary_bounds[0]
    boundary_depth = context.boundary_bounds[3] - context.boundary_bounds[1]
    axis_order = tuple(
        sorted(
            (reference_axis, alternate_axis),
            key=lambda axis: (
                -(boundary_width if axis == "X" else boundary_depth),
                axis_priority[axis],
            ),
        )
    )
    preferred_direction = context.structural_composition_family.dominant_direction
    if preferred_direction not in {"POSITIVE", "NEGATIVE"}:
        # An unresolved site-derived ordering prior is not a local geometry
        # direction. Keep both deterministic directional variants available.
        preferred_direction = "POSITIVE"
    directions = tuple(
        dict.fromkeys(
            (preferred_direction, "NEGATIVE" if preferred_direction == "POSITIVE" else "POSITIVE")
        )
    )
    attempt_specs = tuple(
        (layout_family, axis, direction)
        for axis in axis_order
        for direction in directions
        for layout_family in BASE_LAYOUT_FAMILIES
    )
    local_synthesizers = {
        LINEAR_3_BAND: _synthesize_linear_3_band_local,
        CENTRAL_PROCESS_WITH_SIDE_BANKS: _synthesize_central_side_banks_local,
        LONGITUDINAL_PROCESS_SPINE: _synthesize_longitudinal_spine_local,
    }
    local_compositions_by_family: dict[str, tuple[LocalBuildingCompositionV1, ...]] = {}
    module_source_pairs_by_family: dict[
        str,
        tuple[tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]], ...],
    ] = {}
    seen_hashes: set[str] = set()
    seen_full_geometry: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    seen_critical_assemblies: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    main_skeleton_admission: dict[str, bool] = {}
    family_by_geometry: dict[str, str] = {}
    pending_tail_candidates_by_identity: dict[
        str, tuple[dict[str, PlacedRectangleV1], MainProcessSkeletonCandidateV1, str]
    ] = {}
    s2_started_main_identities: set[str] = set()
    tail_incapable_main_seen = False
    site_bounds = context.boundary_bounds
    bays = _orthogonal_site_buildable_bays(context)
    stats.site_bay_rows = bays
    shipping_dock_anchors = stats.site_shipping_dock_anchors
    if shipping_dock_anchors is None:
        shipping_dock_anchors = _shipping_dock_anchors_at_entrance(context)
        stats.site_shipping_dock_anchors = shipping_dock_anchors
    # Keep main-process enumeration at its pre-R2 limit. The bounded reserve
    # below allocates only S2 capacity-preflight/completion probes from nodes
    # that remain after a Truck-pass main is found; it does not shrink S1.
    tail_phase_node_reserve = min(
        (context.node_budget * 2) // 3,
        len(_S2_TAIL_MODULES) * len(BASE_LAYOUT_FAMILIES) * 2,
    )
    tail_access_capacity_round_reserve = _tail_access_capacity_round_reserve(context.node_budget)
    preflight_round_size = tail_access_capacity_round_reserve
    # The finite S2 preflight round is also capped by the existing tail-phase
    # reserve; neither term enlarges the shared placement budget.
    tail_access_capacity_round_reserve = min(preflight_round_size, tail_phase_node_reserve)
    s1_node_ceiling = context.node_budget - tail_access_capacity_round_reserve
    main_site_candidate_limit = context.node_budget
    if stats.site_module_variant_counts is None:
        stats.site_module_variant_counts = {}
    stats.site_module_variant_counts["buildable_bays"] = len(bays)
    stats.site_module_variant_counts["main_site_candidate_limit"] = main_site_candidate_limit
    stats.site_module_variant_counts["tail_phase_node_reserve"] = tail_phase_node_reserve
    stats.site_module_variant_counts["tail_access_capacity_round_reserve"] = (
        tail_access_capacity_round_reserve
    )
    stats.site_module_variant_counts["s1_node_ceiling"] = s1_node_ceiling
    raw_bank_module_variants = tuple(
        row[0]
        for row in _local_bank_compositions(
            context, ("raw_fruit_buffer", "primary_precooling_room"), result_limit=24
        )
    )
    finished_bank_module_variants = _local_must_chain_module_compositions(
        context,
        (
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        ),
        result_limit=24,
    )
    site_module_variant_catalog = (raw_bank_module_variants, finished_bank_module_variants)
    stats.site_module_variant_counts["raw_module_variants"] = len(raw_bank_module_variants)
    stats.site_module_variant_counts["process_core_module_variants"] = len(
        _local_dimension_shapes(context, "sorting_packaging_room")
    )
    stats.site_module_variant_counts["finished_module_variants"] = len(
        finished_bank_module_variants
    )
    stats.site_module_variant_counts["packaging_module_variants"] = len(
        _local_dimension_shapes(context, "packaging_material_storage")
    )
    stats.site_module_variant_counts["secondary_support_module_variants"] = len(
        _local_dimension_shapes(context, "secondary_fruit_buffer")
    )
    stats.site_module_variant_counts["frozen_support_module_variants"] = len(
        _local_dimension_shapes(context, "frozen_fruit_room")
    )
    stats.site_module_variant_counts["office_module_variants"] = len(
        _local_dimension_shapes(context, "office")
    )
    stats.site_module_variant_counts["changing_module_variants"] = len(
        _local_dimension_shapes(context, "changing_room")
    )

    def note_module_attempt(row: dict[str, Any]) -> None:
        if stats.site_module_assembly_trace is None:
            stats.site_module_assembly_trace = []
        stats.site_module_assembly_trace.append(row)

    def advance_pending_tail_capacity_round() -> Any:
        active_rows = tuple(
            (main, seed, skeleton_hash)
            for main, seed, skeleton_hash in pending_tail_candidates_by_identity.values()
            if (stats.tail_access_capacity_status_by_main or {}).get(
                _tail_access_main_identity(skeleton_hash, main)
            )
            not in {"TAIL_ACCESS_CAPABLE_MAIN", "TAIL_ACCESS_INCAPABLE_MAIN"}
        )
        if not active_rows:
            return {}
        unresolved_module_count = sum(
            (stats.tail_access_capacity_seed_counts_by_main or {})
            .get(_tail_access_main_identity(skeleton_hash, main), {})
            .get(module_name, 0)
            == 0
            for main, _seed, skeleton_hash in active_rows
            for module_name in _S2_TAIL_MODULES
        )
        tail_access_preflight_node_limit = max(1, unresolved_module_count)
        statuses: dict[str, str] = {}
        for event in _tail_access_capacity_preflight(
            context,
            tuple((skeleton_hash, main) for main, _seed, skeleton_hash in active_rows),
            bays,
            stats,
            node_limit=tail_access_preflight_node_limit,
        ):
            if isinstance(event, _SearchQuantumYield):
                yield event
            else:
                statuses.update(event)
        return statuses

    def apply_tail_capacity_statuses(
        previous: Mapping[str, str], current: Mapping[str, str]
    ) -> int:
        nonlocal s1_node_ceiling, tail_incapable_main_seen
        newly_incapable = tuple(
            identity
            for identity, status in current.items()
            if status == "TAIL_ACCESS_INCAPABLE_MAIN"
            and previous.get(identity) != "TAIL_ACCESS_INCAPABLE_MAIN"
        )
        if newly_incapable:
            tail_incapable_main_seen = True
            releasable = max(0, context.node_budget - s1_node_ceiling)
            released = min(releasable, len(_S2_TAIL_MODULES) * len(newly_incapable))
            s1_node_ceiling += released
            if stats.site_module_variant_counts is None:
                stats.site_module_variant_counts = {}
            stats.site_module_variant_counts[
                "tail_capacity_reserve_released_for_incapable_mains"
            ] = (
                int(
                    stats.site_module_variant_counts.get(
                        "tail_capacity_reserve_released_for_incapable_mains", 0
                    )
                )
                + released
            )
        return len(newly_incapable)

    def make_full_candidate_payload(
        synthesis: Mapping[str, PlacedRectangleV1],
        seed: MainProcessSkeletonCandidateV1,
        *,
        layout_family: str,
        process_axis: str,
        process_direction: str,
    ) -> dict[str, Any] | None:
        try:
            _validate_graph_completeness(context.graph, synthesis)
            main_placements = {code: synthesis[code] for code in MAIN_PROCESS_ZONE_CODES}
            _validate_main_process_skeleton_graph(context.graph, main_placements)
            composition = _site_local_composition(
                context, layout_family, process_axis, process_direction, synthesis
            )
            exact_plan = _structured_plan_from_composition(
                composition,
                synthesis,
                obstacles=context.obstacles,
                site_bounds=site_bounds,
            )
            canonical_skeletons = structural_skeleton_candidates(
                context.site_body,
                tuple(context.authorities),
                zone_authorities=context.authorities,
                family_candidates=(seed.family,),
            )
            canonical_structural_skeleton = next(
                (
                    row
                    for row in canonical_skeletons
                    if row.family.to_dict() == seed.family.to_dict()
                ),
                None,
            )
            if canonical_structural_skeleton is None:
                raise _error("CANONICAL_STRUCTURAL_SKELETON_UNAVAILABLE")
        except LayoutAuthorityError as error:
            _record_rejection(stats, error.code)
            return None

        candidate_context = replace(
            context,
            structural_composition_family=seed.family,
            structural_skeleton=canonical_structural_skeleton,
            structured_building_plan=exact_plan,
            structural_topology=seed.canonical_topology_owner,
        )
        stats.complete_candidates += 1
        stats.generated_candidates += len(synthesis)
        payload = _candidate_payload(
            synthesis,
            context.authorities,
            context.graph,
            context.site_body,
            context.source_zone_plan_hash,
            context.source_p1_handoff_hash,
            context.source_site_geometry_hash,
            context.objective_profile_hash,
            context.access_requirements,
            context.spatial_relationships,
            _search_provenance(
                candidate_context,
                stats,
                search_tree_exhausted=False,
                objective_optimal_within_search_family=False,
            ),
        )
        payload["_structural_generation_flag"] = True
        payload["_structural_composition_family"] = seed.family.to_dict()
        payload["_structural_skeleton"] = canonical_structural_skeleton.to_dict()
        payload["_search_phase"] = STRUCTURED_PHASE
        payload["_structured_building_plan"] = exact_plan.to_dict()
        payload["_main_process_skeleton"] = seed.to_evaluation_dict()
        payload["_r5_skeleton_hash"] = seed.main_process_skeleton_hash
        payload["_r5_topology"] = seed.canonical_topology_owner
        payload["_r7_discovery_topology"] = context.structural_topology
        if stats.skeleton_tail_lifecycle is None:
            stats.skeleton_tail_lifecycle = []
        stats.skeleton_tail_lifecycle.append(
            {
                "topology": seed.canonical_topology_owner,
                "skeleton_hash": seed.main_process_skeleton_hash,
                "layout_family": layout_family,
                "envelope_family": exact_plan.envelope.family,
                "local_zone_union_outline_class": composition.outline_class,
                "construction_mode": "SITE_PARTITIONED_MODULE_ASSEMBLY",
                "tail_search_started": True,
                "tail_nodes": 0,
                "complete_candidate_count": 1,
                "p2d_reached": False,
                "p2d_pending": True,
                "first_failure_stage": None,
                "first_failure_reason": None,
            }
        )
        return payload

    for attempt_index, (layout_family, process_axis, process_direction) in enumerate(attempt_specs):
        if stats.visited_nodes >= context.node_budget:
            stats.node_budget_exhausted = True
            stats.skeleton_search_truncated = True
            return
        if stats.visited_nodes >= s1_node_ceiling:
            stats.skeleton_search_truncated = True
            stats.normal_stop_reason = "S1_NODE_CEILING_RESERVED_FOR_TAIL_ACCESS"
            break
        stats.visited_nodes += 1
        stats.construction_node_count += 1
        stats.current_work_item = {
            "topology": context.structural_topology,
            "layout_family": layout_family,
            "process_axis": process_axis,
            "process_direction": process_direction,
            "branch": "LOCAL_MODULES_THEN_SITE_BAY_ASSEMBLY",
            "family_plan_subvariant": attempt_index,
            "band_family": layout_family,
            "placement_node_charged": True,
        }
        quantum = _quantum_checkpoint(stats)
        if quantum is not None:
            yield quantum

        attempt_row: dict[str, Any] = {
            "layout_family": layout_family,
            "process_axis": process_axis,
            "process_direction": process_direction,
            "construction_policy": f"{layout_family}_LOCAL_COMPOSITION_V1",
            "construction_nodes": 1,
            "result": "LOCAL_COMPOSITION_SEARCHED",
            "first_failure_stage": None,
            "first_failure_interface": None,
            "rejection_reason": None,
            "local_composition_count": 0,
            "full_building_composition_count": 0,
            "site_rigid_placement_count": 0,
            "site_module_main_attempt_count": 0,
            "site_module_main_valid_count": 0,
            "site_module_full_attempt_count": 0,
            "site_module_full_valid_count": 0,
        }
        if stats.constructive_divergence_attempts is None:
            stats.constructive_divergence_attempts = []
        stats.constructive_divergence_attempts.append(
            {
                "layout_family": layout_family,
                "process_axis": process_axis,
                "process_direction": process_direction,
                "construction_policy": f"{layout_family}_LOCAL_COMPOSITION_V1",
                "result": "LOCAL_COMPOSITION_STARTED",
                "site_coordinates_used_during_local_synthesis": False,
                "event_axis_search_used": False,
                "greedy_room_chain_used": False,
                "module_site_assembly_used": True,
                "whole_building_rigid_body_required": False,
                "site_bay_count": len(bays),
            }
        )

        main_compositions = local_compositions_by_family.get(layout_family)
        if main_compositions is None:
            # Each family derives its immutable room modules once from the
            # canonical local axis/direction. Site-facing axis and direction
            # variants are realized later by rigid module transforms and
            # exact bay-edge alignment, not by repeating room-level synthesis.
            main_compositions = local_synthesizers[layout_family](
                context, reference_axis, preferred_direction
            )
            local_compositions_by_family[layout_family] = main_compositions
        attempt_row["local_composition_count"] = len(main_compositions)
        if not main_compositions:
            attempt_row.update(
                {
                    "result": "DETERMINISTIC_SYNTHESIS_IMPOSSIBLE",
                    "first_failure_stage": "LOCAL_MAIN_PROCESS_COMPOSITION",
                    "rejection_reason": "NO_DIMENSION_OVERLAP_MUST_VALID_SEVEN_ZONE_COMPOSITION",
                }
            )
            _record_rejection(stats, str(attempt_row["rejection_reason"]))
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(attempt_row)
            continue
        if layout_family not in module_source_pairs_by_family:
            module_source_pairs_by_family[layout_family] = _main_module_source_pairs(
                context,
                main_compositions,
                module_variants=site_module_variant_catalog,
                stats=stats,
            )

        candidate_emitted = False
        failure_stage = "SITE_MAIN_MODULE_ASSEMBLY"
        failure_reason = "NO_SITE_VALID_MAIN_PROCESS_MODULE_ASSEMBLY"

        # Keep an exact rigid-body fast path for unobstructed/simple sites only.
        if not context.obstacles:
            for main_index, main_composition in enumerate(main_compositions[:2]):
                for composition in _local_full_building_compositions(
                    context, main_composition, result_limit=2
                ):
                    local = composition.placements()
                    for translation_index, synthesis in enumerate(
                        _whole_building_site_placements(context, local, result_limit=1)
                    ):
                        main_placements = {
                            code: synthesis[code] for code in MAIN_PROCESS_ZONE_CODES
                        }
                        try:
                            seed = _canonical_site_main_skeleton(
                                context,
                                main_placements,
                                layout_family=layout_family,
                                process_axis=process_axis,
                                process_direction=process_direction,
                                generation_pattern=(
                                    f"{layout_family}:RIGID_FAST_PATH:{process_axis}:"
                                    f"{process_direction}:{main_index}:{translation_index}"
                                ),
                            )
                        except LayoutAuthorityError as error:
                            failure_stage, failure_reason = "GRAPH_HARD_VALIDATION", error.code
                            _record_rejection(stats, error.code)
                            continue
                        skeleton_hash = seed.main_process_skeleton_hash
                        if skeleton_hash in seen_hashes:
                            continue
                        seen_hashes.add(skeleton_hash)
                        if not _constructive_main_skeleton_tail_admission(context, stats, seed):
                            failure_stage, failure_reason = (
                                "MAIN_SKELETON_PREFLIGHT",
                                "PREFLIGHT_REJECTED",
                            )
                            continue
                        main_skeleton_admission[skeleton_hash] = True
                        full_signature = _module_signature(synthesis)
                        if full_signature in seen_full_geometry:
                            continue
                        seen_full_geometry.add(full_signature)
                        payload = make_full_candidate_payload(
                            synthesis,
                            seed,
                            layout_family=layout_family,
                            process_axis=process_axis,
                            process_direction=process_direction,
                        )
                        if payload is not None:
                            attempt_row["site_rigid_placement_count"] = (
                                int(attempt_row["site_rigid_placement_count"]) + 1
                            )
                            attempt_row["result"] = "RIGID_FAST_PATH_CANDIDATE_EMITTED"
                            candidate_emitted = True
                            yield payload

        module_attempts = 0
        main_rows = _module_main_site_assemblies(
            context,
            main_compositions,
            layout_family,
            process_axis,
            process_direction,
            bays,
            limit=main_site_candidate_limit,
            source_pairs=module_source_pairs_by_family[layout_family],
            stats=stats,
        )
        for main_candidate in main_rows:
            if main_candidate is not None:
                candidate_signature = _module_signature(main_candidate)
                if candidate_signature in seen_critical_assemblies:
                    note_module_attempt(
                        {
                            "layout_family": layout_family,
                            "stage": "S1_MAIN_PROCESS",
                            "result": "DUPLICATE_CRITICAL_ASSEMBLY_SKIPPED_WITHOUT_NODE_REPLAY",
                        }
                    )
                    continue
                if tail_incapable_main_seen:
                    stats.main_enumeration_continued_after_tail_access_reject = True
                    stats.main_generator_resumed_from_continuation = True
            if stats.visited_nodes >= context.node_budget:
                stats.node_budget_exhausted = True
                stats.skeleton_search_truncated = True
                return
            if stats.visited_nodes >= s1_node_ceiling:
                while stats.visited_nodes < context.node_budget:
                    previous_statuses = dict(stats.tail_access_capacity_status_by_main or {})
                    nodes_before_round = stats.visited_nodes
                    round_statuses = yield from advance_pending_tail_capacity_round()
                    new_incapable = apply_tail_capacity_statuses(previous_statuses, round_statuses)
                    if new_incapable:
                        break
                    unresolved = any(
                        status == "UNRESOLVED_COVERAGE"
                        for status in (stats.tail_access_capacity_status_by_main or {}).values()
                    )
                    if not unresolved or stats.visited_nodes == nodes_before_round:
                        break
                if stats.visited_nodes >= s1_node_ceiling:
                    stats.skeleton_search_truncated = True
                    stats.normal_stop_reason = "S1_NODE_CEILING_RESERVED_FOR_TAIL_ACCESS"
                    break
            stats.visited_nodes += 1
            stats.construction_node_count += 1
            module_attempts += 1
            attempt_row["site_module_main_attempt_count"] = module_attempts
            stats.current_work_item = {
                "topology": context.structural_topology,
                "layout_family": layout_family,
                "band_family": layout_family,
                "process_axis": process_axis,
                "process_direction": process_direction,
                "branch": "SITE_MODULE_MAIN_ASSEMBLY",
                "module_attempt": module_attempts,
                "placement_node_charged": True,
            }
            quantum = _quantum_checkpoint(stats)
            if quantum is not None:
                yield quantum
            if main_candidate is None:
                failure_reason = "MODULE_INTERFACE_OR_EXACT_SITE_PREDICATE_REJECTED"
                note_module_attempt(
                    {
                        "layout_family": layout_family,
                        "stage": "S1_MAIN_PROCESS",
                        "result": "REJECTED",
                        "reason": failure_reason,
                    }
                )
                continue
            attempt_row["site_module_main_valid_count"] = (
                int(attempt_row["site_module_main_valid_count"]) + 1
            )
            try:
                main_placements = {
                    code: main_candidate[code] for code in MAIN_PROCESS_SKELETON_ZONE_CODES
                }
                seed = _canonical_site_main_skeleton(
                    context,
                    main_placements,
                    layout_family=layout_family,
                    process_axis=process_axis,
                    process_direction=process_direction,
                    generation_pattern=(
                        f"{layout_family}:SITE_MODULE_ASSEMBLY:{process_axis}:"
                        f"{process_direction}:{module_attempts}"
                    ),
                )
            except LayoutAuthorityError as error:
                failure_stage, failure_reason = "GRAPH_HARD_VALIDATION", error.code
                _record_rejection(stats, error.code)
                continue
            skeleton_hash = seed.main_process_skeleton_hash
            critical_signature = _module_signature(main_candidate)
            if critical_signature in seen_critical_assemblies:
                note_module_attempt(
                    {
                        "layout_family": layout_family,
                        "stage": "S1_MAIN_PROCESS",
                        "result": "DUPLICATE_CRITICAL_ASSEMBLY",
                        "main_process_skeleton_hash": skeleton_hash,
                    }
                )
                continue
            seen_critical_assemblies.add(critical_signature)
            prior_family = family_by_geometry.get(skeleton_hash)
            if prior_family is not None and prior_family != layout_family:
                stats.family_geometry_collapse_count += 1
                note_module_attempt(
                    {
                        "layout_family": layout_family,
                        "stage": "S1_MAIN_PROCESS",
                        "result": "FAMILY_GEOMETRY_COLLAPSE",
                        "main_process_skeleton_hash": skeleton_hash,
                        "prior_layout_family": prior_family,
                    }
                )
                continue
            else:
                family_by_geometry.setdefault(skeleton_hash, layout_family)
            first_skeleton_visit = skeleton_hash not in seen_hashes
            if first_skeleton_visit:
                seen_hashes.add(skeleton_hash)
                if stats.constructed_main_skeletons is None:
                    stats.constructed_main_skeletons = {}
                stats.constructed_main_skeletons.setdefault(skeleton_hash, seed)
                if stats.skeleton_generation_patterns is None:
                    stats.skeleton_generation_patterns = {}
                stats.skeleton_generation_patterns[seed.generation_pattern] = (
                    stats.skeleton_generation_patterns.get(seed.generation_pattern, 0) + 1
                )
                admitted = _constructive_main_skeleton_tail_admission(
                    context, stats, seed, run_truck_preflight=True
                )
                main_skeleton_admission[skeleton_hash] = admitted
                early_proof = (stats.early_packaging_preflight_by_geometry or {}).get(
                    repr(_module_signature(main_placements))
                )
                registry_row = (context.global_main_process_geometry_registry or {}).get(
                    skeleton_hash
                )
                formal_slot_exists = (
                    registry_row.get("packaging_slot_exists")
                    if isinstance(registry_row, Mapping)
                    else None
                )
                if (
                    isinstance(early_proof, Mapping)
                    and early_proof.get("legal_slot_exists") is not formal_slot_exists
                ):
                    stats.early_formal_packaging_preflight_mismatch_count += 1
                    note_module_attempt(
                        {
                            "layout_family": layout_family,
                            "stage": "S1_TAIL_CAPACITY_PREFLIGHT",
                            "result": "EARLY_FORMAL_PREFLIGHT_MISMATCH",
                            "main_process_skeleton_hash": skeleton_hash,
                            "early_slot_exists": early_proof.get("legal_slot_exists"),
                            "formal_slot_exists": formal_slot_exists,
                        }
                    )
                if not admitted:
                    failure_stage, failure_reason = (
                        "MAIN_SKELETON_PREFLIGHT",
                        "PREFLIGHT_REJECTED",
                    )
                    note_module_attempt(
                        {
                            "layout_family": layout_family,
                            "stage": "S1_MAIN_PROCESS",
                            "result": "PACKAGING_SLOT_PREFLIGHT_REJECTED",
                            "main_process_skeleton_hash": skeleton_hash,
                        }
                    )
                    continue
            else:
                if not main_skeleton_admission.get(skeleton_hash, False):
                    continue
                seed = (stats.constructed_main_skeletons or {}).get(skeleton_hash, seed)
            truck_registry_row = (context.global_main_process_geometry_registry or {}).get(
                skeleton_hash, {}
            )
            truck_preflight_row = truck_registry_row.get("main_skeleton_truck_preflight")
            if (
                isinstance(truck_preflight_row, Mapping)
                and truck_preflight_row.get("preflight_status") == "PASS"
            ):
                witness = truck_preflight_row.get("construction_witness")
                if isinstance(witness, Mapping):
                    raw_envelopes = witness.get("truck_envelopes", ())
                    polygons = tuple(
                        normalize_polygon(envelope, error_code="INVALID_TRUCK_ENVELOPE")
                        for envelope in raw_envelopes
                        if isinstance(envelope, Mapping)
                    )
                    stats.reserve_truck_envelopes(repr(_module_signature(main_candidate)), polygons)
            note_module_attempt(
                {
                    "layout_family": layout_family,
                    "stage": "S1_MAIN_PROCESS",
                    "result": (
                        "PACKAGING_PREFLIGHT_ADMITTED"
                        if first_skeleton_visit
                        else "PACKAGING_PREFLIGHT_ADMITTED_ALTERNATE_ANCHOR"
                    ),
                    "main_process_skeleton_hash": skeleton_hash,
                    "raw_interface_side": _adjacent_side(
                        main_placements["sorting_packaging_room"],
                        main_placements["primary_precooling_room"],
                    ),
                    "finished_interface_side": _adjacent_side(
                        main_placements["sorting_packaging_room"],
                        main_placements["secondary_precooling_room"],
                    ),
                    "packaging_anchor": main_candidate["packaging_material_storage"].to_dict(),
                    "critical_zone_count": len(main_candidate),
                    "module_internal_geometry_frozen": True,
                }
            )
            if (
                isinstance(truck_preflight_row, Mapping)
                and truck_preflight_row.get("preflight_status") == "PASS"
            ):
                main_identity = _tail_access_main_identity(skeleton_hash, main_candidate)
                pending_tail_candidates_by_identity.setdefault(
                    main_identity, (dict(main_candidate), seed, skeleton_hash)
                )
                previous_statuses = dict(stats.tail_access_capacity_status_by_main or {})
                round_statuses = yield from advance_pending_tail_capacity_round()
                apply_tail_capacity_statuses(previous_statuses, round_statuses)

        # Continue finite capacity domains round-robin while this context has
        # budget. UNRESOLVED mains are not admitted to full S2; an exhausted
        # domain frees a small, formula-derived part of the same node budget
        # for the still-live main generator.
        while stats.visited_nodes < context.node_budget and any(
            status == "UNRESOLVED_COVERAGE"
            for status in (stats.tail_access_capacity_status_by_main or {}).values()
        ):
            previous_statuses = dict(stats.tail_access_capacity_status_by_main or {})
            nodes_before_round = stats.visited_nodes
            round_statuses = yield from advance_pending_tail_capacity_round()
            apply_tail_capacity_statuses(previous_statuses, round_statuses)
            if stats.visited_nodes == nodes_before_round:
                break
        if stats.node_budget_exhausted:
            return
        s2_main_candidates = [
            (
                main_candidate,
                seed,
                skeleton_hash,
                (stats.tail_access_capacity_status_by_main or {}).get(
                    _tail_access_main_identity(skeleton_hash, main_candidate),
                    "UNRESOLVED_COVERAGE",
                ),
            )
            for main_candidate, seed, skeleton_hash in pending_tail_candidates_by_identity.values()
            if _tail_access_main_is_s2_admissible(
                (stats.tail_access_capacity_status_by_main or {}).get(
                    _tail_access_main_identity(skeleton_hash, main_candidate),
                    "UNRESOLVED_COVERAGE",
                )
            )
            and _tail_access_main_identity(skeleton_hash, main_candidate)
            not in s2_started_main_identities
        ]
        for main_index, (main_candidate, seed, skeleton_hash, capacity_status) in enumerate(
            s2_main_candidates
        ):
            main_identity = _tail_access_main_identity(skeleton_hash, main_candidate)
            s2_started_main_identities.add(main_identity)
            remaining_main_candidates = len(s2_main_candidates) - main_index
            remaining_context_nodes = max(0, context.node_budget - stats.visited_nodes)
            family_s2_node_cap = max(
                1,
                tail_phase_node_reserve // max(1, 2 * len(BASE_LAYOUT_FAMILIES)),
            )
            per_main_s2_node_limit = max(
                1,
                min(
                    remaining_context_nodes // max(1, remaining_main_candidates),
                    family_s2_node_cap,
                ),
            )
            note_module_attempt(
                {
                    "layout_family": layout_family,
                    "stage": "S2_TAIL_ACCESS_CAPACITY_PREFLIGHT",
                    "result": capacity_status,
                    "main_process_skeleton_hash": skeleton_hash,
                    "seed_counts_by_module": (
                        stats.tail_access_capacity_seed_counts_by_main or {}
                    ).get(_tail_access_main_identity(skeleton_hash, main_candidate), {}),
                }
            )
            for complete_or_quantum in _module_full_site_assemblies(
                context,
                main_candidate,
                bays,
                limit=1,
                stats=stats,
                main_skeleton_hash=skeleton_hash,
                node_limit=per_main_s2_node_limit,
            ):
                if isinstance(complete_or_quantum, _SearchQuantumYield):
                    yield complete_or_quantum
                    continue
                attempt_row["site_module_full_attempt_count"] = (
                    int(attempt_row["site_module_full_attempt_count"]) + 1
                )
                complete = complete_or_quantum
                if stats.node_budget_exhausted:
                    return
                if complete is None:
                    if _tail_access_main_identity(skeleton_hash, main_candidate) in (
                        stats.tail_access_s2_node_quota_exhausted_by_main or set()
                    ):
                        note_module_attempt(
                            {
                                "layout_family": layout_family,
                                "stage": "S2_SUPPORT_PERSONNEL",
                                "result": "UNRESOLVED_COVERAGE",
                                "main_process_skeleton_hash": skeleton_hash,
                                "per_main_node_limit": per_main_s2_node_limit,
                                "nodes_used": stats.tail_access_slot_attempt_count,
                            }
                        )
                        continue
                    note_module_attempt(
                        {
                            "layout_family": layout_family,
                            "stage": "S2_SUPPORT_PERSONNEL",
                            "result": "REJECTED",
                            "main_process_skeleton_hash": skeleton_hash,
                            "reason": "NO_SITE_VALID_ACCESS_AWARE_TAIL_MODULE_COMBINATION",
                        }
                    )
                    failure_stage = "SITE_TAIL_MODULE_ASSEMBLY"
                    failure_reason = "NO_SITE_VALID_ACCESS_AWARE_TAIL_MODULE_COMBINATION"
                    continue
                signature = _module_signature(complete)
                if signature in seen_full_geometry:
                    continue
                seen_full_geometry.add(signature)
                attempt_row["site_module_full_valid_count"] = (
                    int(attempt_row["site_module_full_valid_count"]) + 1
                )
                note_module_attempt(
                    {
                        "layout_family": layout_family,
                        "stage": "S2_SUPPORT_PERSONNEL",
                        "result": "TWELVE_ZONE_SITE_ASSEMBLY_COMPLETE",
                        "main_process_skeleton_hash": skeleton_hash,
                        "full_geometry_signature": repr(signature),
                        "module_internal_geometry_frozen": True,
                    }
                )
                if not _constructive_main_skeleton_tail_admission(context, stats, seed):
                    failure_stage, failure_reason = (
                        "MAIN_SKELETON_TRUCK_PREFLIGHT",
                        "TRUCK_PREFLIGHT_REJECTED_AFTER_12_ZONE_ASSEMBLY",
                    )
                    note_module_attempt(
                        {
                            "layout_family": layout_family,
                            "stage": "TRUCK_PREFLIGHT",
                            "result": "REJECTED",
                            "main_process_skeleton_hash": skeleton_hash,
                            "full_geometry_signature": repr(signature),
                            "failure_reason": failure_reason,
                        }
                    )
                    continue
                payload = make_full_candidate_payload(
                    complete,
                    seed,
                    layout_family=layout_family,
                    process_axis=process_axis,
                    process_direction=process_direction,
                )
                if payload is None:
                    failure_stage, failure_reason = (
                        "GRAPH_HARD_VALIDATION",
                        "FULL_CANDIDATE_PLAN_REJECTED",
                    )
                    continue
                attempt_row["result"] = "FULL_12_ZONE_SITE_MODULE_CANDIDATE_EMITTED"
                candidate_emitted = True
                yield payload

        if not candidate_emitted and module_attempts == 0:
            exhausted_pairs = [
                row
                for row in stats.site_main_source_pair_rows or []
                if row.get("layout_family") == layout_family
                and row.get("process_axis") == process_axis
                and row.get("process_direction") == process_direction
            ]
            if any(row.get("tail_capacity_exhausted") is True for row in exhausted_pairs):
                failure_stage = "TAIL_SLOT_PREFLIGHT"
                failure_reason = "SOURCE_PAIR_TAIL_CAPACITY_EXHAUSTED"
        if not candidate_emitted:
            attempt_row["result"] = "SITE_MODULE_SYNTHESIS_DID_NOT_EMIT_COMPLETE_CANDIDATE"
            attempt_row["first_failure_stage"] = failure_stage
            attempt_row["rejection_reason"] = failure_reason
            _record_rejection(stats, failure_reason)
        if stats.skeleton_construction_attempts is None:
            stats.skeleton_construction_attempts = []
        stats.skeleton_construction_attempts.append(attempt_row)


def _dual_interface_sorting_roots(
    context: _PlacementSearchContext,
    packaging_anchor: PackagingAnchorV1,
    dock_anchor: ShippingDockAnchorV1,
    bays: Sequence[BuildableBayV1],
    *,
    packaging_roots: Sequence[
        tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]]
    ]
    | None = None,
    dock_finished_module: Mapping[str, PlacedRectangleV1] | None = None,
    layout_family: str | None = None,
    process_axis: str = "Y",
    process_direction: str = "POSITIVE",
    stats: _PlacementSearchStats | None = None,
) -> tuple[tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]], ...]:
    """Derive sorting roots constrained by both package and dock interfaces.

    In the dock-backsolved path, a root must be generated at the exact frozen
    secondary-room interface of a finished module already translated onto the
    shipping dock anchor, and that same root must carry a packaging-derived
    straight-interface construction witness. This is a joint construction
    intersection, not a post-hoc collision filter.
    """
    package_roots = (
        tuple(packaging_roots)
        if packaging_roots is not None
        else (_packaging_driven_sorting_roots(context, packaging_anchor, bays=bays, stats=stats))
    )
    fixed_external = {
        "packaging_material_storage": packaging_anchor.rectangle,
        "shipping_channel": dock_anchor.shipping_rectangle,
    }
    if dock_finished_module is not None:
        shipping = dock_finished_module.get("shipping_channel")
        secondary = dock_finished_module.get("secondary_precooling_room")
        if (
            shipping is None
            or secondary is None
            or shipping.bounds_mm != dock_anchor.shipping_rectangle.bounds_mm
            or shipping.rotation_deg != dock_anchor.shipping_rotation_deg
        ):
            return ()
        finished_zones = {
            code: rectangle
            for code, rectangle in dock_finished_module.items()
            if code != "shipping_channel"
        }
        if not _site_module_is_usable(context, finished_zones, fixed_external):
            return ()

        package_roots_by_geometry: dict[
            tuple[tuple[int, ...], int],
            list[tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]]],
        ] = {}
        for row in package_roots:
            package_roots_by_geometry.setdefault(
                (row[0].bounds_mm, row[0].rotation_deg), []
            ).append(row)

        allowed_finished_sides = tuple(
            sorted(
                {
                    finished_side
                    for _raw_side, finished_side in _family_core_face_pairs(
                        layout_family or LINEAR_3_BAND,
                        process_axis,
                        process_direction,
                    )
                }
            )
        )
        opposite_side = {
            "NORTH": "SOUTH",
            "SOUTH": "NORTH",
            "EAST": "WEST",
            "WEST": "EAST",
        }
        joint_roots: dict[
            tuple[tuple[int, ...], int, str, tuple[int, ...] | None],
            tuple[PlacedRectangleV1, str, PlacedRectangleV1 | None, dict[str, Any]],
        ] = {}
        for shape in _local_dimension_shapes(context, "sorting_packaging_room"):
            for finished_side in allowed_finished_sides:
                root_side = opposite_side[finished_side]
                for alignment in ("LOW", "CENTER", "HIGH"):
                    x_mm, y_mm = _local_adjacent_origin(
                        secondary, shape[3], shape[4], root_side, alignment
                    )
                    root = _local_rectangle_at("sorting_packaging_room", shape, x_mm, y_mm)
                    if _adjacent_side(root, secondary) != finished_side:
                        continue
                    package_rows = package_roots_by_geometry.get(
                        (root.bounds_mm, root.rotation_deg), ()
                    )
                    if not package_rows:
                        continue
                    fixed_with_finished = {**fixed_external, **finished_zones}
                    if not _site_module_is_usable(
                        context, {"sorting_packaging_room": root}, fixed_with_finished
                    ):
                        continue
                    for package_row in package_rows:
                        package_root, package_side, corridor, package_witness = package_row
                        if corridor is not None and any(
                            rectangles_overlap(corridor, rectangle)
                            for rectangle in (
                                *fixed_with_finished.values(),
                                root,
                            )
                        ):
                            continue
                        witness = {
                            **package_witness,
                            "dock_anchor_identity": {
                                "dock_point_mm": list(dock_anchor.dock_point_mm),
                                "shipping_bounds_mm": list(
                                    dock_anchor.shipping_rectangle.bounds_mm
                                ),
                                "template_identity": dock_anchor.source_template_identity,
                            },
                            "dock_backsolved_secondary_bounds_mm": list(secondary.bounds_mm),
                            "sorting_secondary_interface_side": finished_side,
                            "sorting_secondary_alignment": alignment,
                            "joint_external_interface_match": True,
                        }
                        signature = (
                            root.bounds_mm,
                            root.rotation_deg,
                            package_side,
                            corridor.bounds_mm if corridor is not None else None,
                        )
                        joint_roots.setdefault(
                            signature,
                            (root, package_side, corridor, witness),
                        )
        return tuple(joint_roots[key] for key in sorted(joint_roots, key=lambda row: repr(row)))

    accepted = []
    for root, package_side, corridor, witness in package_roots:
        if not _site_module_is_usable(context, {"sorting_packaging_room": root}, fixed_external):
            continue
        if corridor is not None and any(
            rectangles_overlap(corridor, rectangle)
            for rectangle in (*fixed_external.values(), root)
        ):
            continue
        accepted.append((root, package_side, corridor, witness))
    return tuple(accepted)


def _module_main_site_assemblies_dock_backsolved_preselected_variants(
    context: _PlacementSearchContext,
    main_compositions: Sequence[LocalBuildingCompositionV1],
    layout_family: str,
    process_axis: str,
    process_direction: str,
    bays: Sequence[BuildableBayV1],
    *,
    limit: int,
    source_pairs: Sequence[tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]]]
    | None = None,
    stats: _PlacementSearchStats | None = None,
) -> Iterator[dict[str, PlacedRectangleV1]]:
    """Build critical assemblies with packaging and dock fixed before sorting.

    Finished-chain modules are rigidly translated onto exact shipping dock
    anchors; sorting roots are then the intersection of package-derived roots
    and those sharing the authorized MUST edge with the backsolved secondary
    room. No room coordinate is searched independently.
    """
    if limit <= 0 or not bays:
        return
    stats_variant_counts: dict[str, Any] | None = None
    selected_source_pairs = tuple(
        source_pairs or _main_module_source_pairs(context, main_compositions)
    )
    if not selected_source_pairs:
        return
    if stats is not None:
        if stats.site_module_variant_counts is None:
            stats.site_module_variant_counts = {}
        stats_variant_counts = stats.site_module_variant_counts
        if stats.site_packaging_anchors is None:
            stats.site_packaging_anchors = _enumerate_packaging_site_anchors(context, bays)
        package_root_options = stats.site_packaging_sorting_roots_by_anchor
        if package_root_options is None:
            package_root_options = {}
            stats.site_packaging_sorting_roots_by_anchor = package_root_options
        if stats.site_packaging_construction_anchors is None:
            stats.site_packaging_construction_anchors = (
                _packaging_anchor_construction_representatives(
                    context,
                    stats.site_packaging_anchors,
                    bays,
                    root_options_by_anchor=package_root_options,
                    stats=stats,
                )
            )
        package_anchors = stats.site_packaging_construction_anchors
    else:
        all_packages = _enumerate_packaging_site_anchors(context, bays)
        package_root_options = {}
        package_anchors = _packaging_anchor_construction_representatives(
            context, all_packages, bays, root_options_by_anchor=package_root_options
        )
    if not package_anchors:
        return
    if stats is not None:
        if stats.site_shipping_dock_anchors is None:
            stats.site_shipping_dock_anchors = _shipping_dock_anchors_at_entrance(context)
        if stats.site_shipping_dock_construction_anchors is None:
            stats.site_shipping_dock_construction_anchors = (
                _shipping_dock_anchor_construction_representatives(
                    stats.site_shipping_dock_anchors,
                    limit=_shipping_dock_anchor_construction_limit(
                        stats.site_shipping_dock_anchors
                    ),
                    truck_entrance_segment=_truck_entrance_for_dock_anchor_order(context),
                )
            )
        dock_anchors = stats.site_shipping_dock_construction_anchors
        dock_points = _truck_dock_events_at_entrance(context)
        assert stats_variant_counts is not None
        stats_variant_counts.update(
            {
                "truck_dock_point_count": len({tuple(row["dock_point_mm"]) for row in dock_points}),
                "shipping_dock_rectangle_count": len(
                    {row.shipping_rectangle.bounds_mm for row in stats.site_shipping_dock_anchors}
                ),
                "shipping_dock_rectangle_count_by_rotation": {
                    str(rotation): len(
                        {
                            row.shipping_rectangle.bounds_mm
                            for row in stats.site_shipping_dock_anchors
                            if row.shipping_rotation_deg == rotation
                        }
                    )
                    for rotation in (0, 90)
                },
                "shipping_dock_rectangle_count_by_loading_face_side": {
                    side: len(
                        {
                            row.shipping_rectangle.bounds_mm
                            for row in stats.site_shipping_dock_anchors
                            if row.loading_face_side == side
                        }
                    )
                    for side in sorted(
                        {row.loading_face_side for row in stats.site_shipping_dock_anchors}
                    )
                },
                "shipping_dock_construction_representative_count": len(dock_anchors),
            }
        )
    else:
        dock_anchors = _shipping_dock_anchor_construction_representatives(
            _shipping_dock_anchors_at_entrance(context),
            limit=_shipping_dock_anchor_construction_limit(
                _shipping_dock_anchors_at_entrance(context)
            ),
            truck_entrance_segment=_truck_entrance_for_dock_anchor_order(context),
        )
    if not dock_anchors:
        return

    pair_variants: list[tuple[int, dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]]] = []
    seen_module_pairs: set[tuple[object, ...]] = set()
    for source_pair_index, (raw_source, finished_source) in enumerate(selected_source_pairs):
        for raw_module, finished_module in _balanced_site_module_pair_variants(
            raw_source, finished_source
        ):
            identity = (_module_signature(raw_module), _module_signature(finished_module))
            if identity in seen_module_pairs:
                continue
            seen_module_pairs.add(identity)
            pair_variants.append((source_pair_index, raw_module, finished_module))

    finished_variants_by_dock_anchor: dict[
        tuple[Any, ...],
        tuple[tuple[int, dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]], ...],
    ] = {}
    for dock_anchor in dock_anchors:
        dock_key = (
            dock_anchor.shipping_rectangle.bounds_mm,
            dock_anchor.shipping_rotation_deg,
            dock_anchor.dock_point_mm,
            dock_anchor.source_template_identity,
            dock_anchor.source_template_rotation_deg,
        )
        translated_variants = []
        for source_pair_index, raw_module, finished_module in pair_variants:
            if stats is not None:
                stats.finished_dock_backsolve_attempt_count += 1
            backsolved = _dock_backsolved_finished_module(finished_module, dock_anchor)
            if backsolved is not None:
                translated_variants.append((source_pair_index, raw_module, backsolved))
        finished_variants_by_dock_anchor[dock_key] = tuple(translated_variants)

    face_pairs = set(_family_core_face_pairs(layout_family, process_axis, process_direction))
    alignments = ("CENTER", "LOW", "HIGH")
    emitted_signatures: set[str] = set()
    dock_capable_hashes: set[str] = set()
    pair_count = 0
    necessary_pass_count = 0
    yielded = 0
    dock_stage_counts = {
        "dock_backsolved_finished_site_valid_count": 0,
        "packaging_dock_joint_sorting_root_count": 0,
        "raw_attachment_candidate_count": 0,
        "raw_attachment_site_valid_count": 0,
        "main_must_graph_valid_count": 0,
        "dock_capable_main_process_count": 0,
    }
    for package_anchor in package_anchors:
        package_options = package_root_options.get(package_anchor.anchor_id)
        if package_options is None:
            package_options = _packaging_driven_sorting_roots(
                context, package_anchor, bays=bays, stats=stats
            )
            package_root_options[package_anchor.anchor_id] = package_options
        for dock_anchor in dock_anchors:
            pair_count += 1
            fixed_interfaces = {
                "packaging_material_storage": package_anchor.rectangle,
                "shipping_channel": dock_anchor.shipping_rectangle,
            }
            if not _site_module_is_usable(context, fixed_interfaces, {}):
                continue
            dock_key = (
                dock_anchor.shipping_rectangle.bounds_mm,
                dock_anchor.shipping_rotation_deg,
                dock_anchor.dock_point_mm,
                dock_anchor.source_template_identity,
                dock_anchor.source_template_rotation_deg,
            )
            joint_rows_by_root: dict[
                tuple[tuple[int, ...], int, str, tuple[int, ...] | None],
                tuple[
                    PlacedRectangleV1,
                    str,
                    PlacedRectangleV1 | None,
                    dict[str, Any],
                    list[tuple[int, dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]]],
                    str,
                ],
            ] = {}
            for (
                source_pair_index,
                raw_module,
                dock_finished,
            ) in finished_variants_by_dock_anchor.get(dock_key, ()):
                finished_zones = {
                    code: rectangle
                    for code, rectangle in dock_finished.items()
                    if code != "shipping_channel"
                }
                if not _site_module_is_usable(context, finished_zones, fixed_interfaces):
                    continue
                dock_stage_counts["dock_backsolved_finished_site_valid_count"] += 1
                dock_roots = _dual_interface_sorting_roots(
                    context,
                    package_anchor,
                    dock_anchor,
                    bays,
                    packaging_roots=package_options,
                    dock_finished_module=dock_finished,
                    layout_family=layout_family,
                    process_axis=process_axis,
                    process_direction=process_direction,
                    stats=stats,
                )
                for root, package_side, corridor, witness in dock_roots:
                    finished_side = _adjacent_side(root, dock_finished["secondary_precooling_room"])
                    if finished_side is None or not any(
                        side == finished_side for _raw, side in face_pairs
                    ):
                        continue
                    root_key = (
                        root.bounds_mm,
                        root.rotation_deg,
                        package_side,
                        corridor.bounds_mm if corridor is not None else None,
                    )
                    existing = joint_rows_by_root.get(root_key)
                    if existing is None:
                        joint_rows_by_root[root_key] = (
                            root,
                            package_side,
                            corridor,
                            witness,
                            [(source_pair_index, raw_module, dock_finished)],
                            finished_side,
                        )
                    else:
                        existing[4].append((source_pair_index, raw_module, dock_finished))
            sorting_roots = tuple(
                (
                    row[0],
                    row[1],
                    row[2],
                    {
                        **row[3],
                        "joint_external_interface_match": True,
                        "dock_backsolved_secondary_bounds_mm": list(
                            row[4][0][2]["secondary_precooling_room"].bounds_mm
                        ),
                    },
                )
                for _key, row in sorted(joint_rows_by_root.items(), key=lambda item: repr(item[0]))
            )
            if sorting_roots:
                necessary_pass_count += 1
                dock_stage_counts["packaging_dock_joint_sorting_root_count"] += len(sorting_roots)
            if stats is not None:
                if stats.site_module_assembly_trace is None:
                    stats.site_module_assembly_trace = []
                stats.site_module_assembly_trace.append(
                    {
                        "stage": "S0_DUAL_EXTERNAL_INTERFACE_SORTING_ROOTS",
                        "layout_family": layout_family,
                        "packaging_anchor": package_anchor.to_dict(),
                        "shipping_dock_anchor": dock_anchor.to_dict(),
                        "sorting_roots": [
                            {
                                "bounds_mm": list(root.bounds_mm),
                                "rotation_deg": root.rotation_deg,
                                "package_side_of_sorting": package_side,
                                "alignment_witness": witness,
                                "reserved_corridor_bounds_mm": (
                                    list(corridor.bounds_mm) if corridor is not None else None
                                ),
                            }
                            for root, package_side, corridor, witness in sorting_roots
                        ],
                        "root_generation_uses_dock_backsolved_secondary": True,
                        "joint_interface_root_set_empty": not bool(sorting_roots),
                        "counts_as_placement_node": False,
                    }
                )
            if not sorting_roots:
                continue
            for root, _package_side, reserved_corridor, _alignment_witness in sorting_roots:
                core = {
                    "packaging_material_storage": package_anchor.rectangle,
                    "sorting_packaging_room": root,
                    "shipping_channel": dock_anchor.shipping_rectangle,
                }
                if not _site_module_is_usable(
                    context, {"sorting_packaging_room": root}, fixed_interfaces
                ):
                    continue
                for (
                    source_pair_index,
                    raw_module,
                    dock_finished,
                ) in joint_rows_by_root[
                    (
                        root.bounds_mm,
                        root.rotation_deg,
                        _package_side,
                        reserved_corridor.bounds_mm if reserved_corridor is not None else None,
                    )
                ][4]:
                    finished_side = _adjacent_side(root, dock_finished["secondary_precooling_room"])
                    if finished_side is None or not any(
                        side == finished_side for _raw, side in face_pairs
                    ):
                        continue
                    if not _site_module_is_usable(
                        context,
                        {
                            code: rectangle
                            for code, rectangle in dock_finished.items()
                            if code != "shipping_channel"
                        },
                        {
                            "packaging_material_storage": package_anchor.rectangle,
                            "sorting_packaging_room": root,
                        },
                    ):
                        continue
                    if reserved_corridor is not None and any(
                        rectangles_overlap(reserved_corridor, rectangle)
                        for rectangle in (*core.values(), *dock_finished.values())
                    ):
                        continue
                    # Finished and raw modules may use distinct core faces;
                    # preserve every authorized face pair for this family.
                    raw_sides = tuple(
                        dict.fromkeys(
                            raw_side
                            for raw_side, candidate_finished_side in _family_core_face_pairs(
                                layout_family, process_axis, process_direction
                            )
                            if candidate_finished_side == finished_side
                        )
                    )
                    for raw_side in raw_sides:
                        for raw_alignment in alignments:
                            raw_attached = _module_attached_to_zone(
                                raw_module,
                                "primary_precooling_room",
                                root,
                                raw_side,
                                raw_alignment,
                            )
                            if raw_attached is None:
                                continue
                            dock_stage_counts["raw_attachment_candidate_count"] += 1
                            fixed_main = {
                                **core,
                                **{
                                    code: rectangle
                                    for code, rectangle in dock_finished.items()
                                    if code != "shipping_channel"
                                },
                            }
                            if not _site_module_is_usable(context, raw_attached, fixed_main):
                                continue
                            if reserved_corridor is not None and any(
                                rectangles_overlap(reserved_corridor, rectangle)
                                for rectangle in raw_attached.values()
                            ):
                                continue
                            dock_stage_counts["raw_attachment_site_valid_count"] += 1
                            candidate = {**fixed_main, **raw_attached}
                            main = {
                                code: candidate[code] for code in MAIN_PROCESS_SKELETON_ZONE_CODES
                            }
                            try:
                                _validate_main_process_skeleton_graph(context.graph, main)
                            except LayoutAuthorityError:
                                continue
                            dock_stage_counts["main_must_graph_valid_count"] += 1
                            if not _site_module_is_usable(context, main, {}):
                                continue
                            try:
                                seed = _canonical_site_main_skeleton(
                                    context,
                                    main,
                                    layout_family=layout_family,
                                    process_axis=process_axis,
                                    process_direction=process_direction,
                                    generation_pattern=(
                                        f"{layout_family}:DUAL_INTERFACE_DOCK_BACKSOLVE:"
                                        f"{dock_anchor.source_template_identity}:"
                                        f"{source_pair_index}"
                                    ),
                                )
                            except LayoutAuthorityError:
                                continue
                            dock_capable_hashes.add(seed.main_process_skeleton_hash)
                            dock_stage_counts["dock_capable_main_process_count"] = len(
                                dock_capable_hashes
                            )
                            critical_signature = repr(_module_signature(candidate))
                            if critical_signature in emitted_signatures:
                                continue
                            emitted_signatures.add(critical_signature)
                            if stats is not None:
                                assert stats_variant_counts is not None
                                if stats.site_module_assembly_trace is None:
                                    stats.site_module_assembly_trace = []
                                stats.site_module_assembly_trace.append(
                                    {
                                        "stage": "S1_DOCK_CAPABLE_MAIN_PROCESS",
                                        "result": "DOCK_CAPABLE_MAIN_PROCESS",
                                        "layout_family": layout_family,
                                        "main_process_skeleton_hash": (
                                            seed.main_process_skeleton_hash
                                        ),
                                        "packaging_anchor": package_anchor.to_dict(),
                                        "shipping_dock_anchor": dock_anchor.to_dict(),
                                        "shipping_exact_dock_anchor_match": True,
                                        "sorting_rotation_deg": root.rotation_deg,
                                        "sorting_root_bounds_mm": list(root.bounds_mm),
                                        "finished_site_construction": "BACKWARD_FROM_DOCK",
                                        "source_pair_index": source_pair_index,
                                        "packaging_slot_exists": True,
                                        "formal_packaging_preflight": "PENDING_OUTER_GATE",
                                        "zones": [
                                            candidate[code].to_dict() for code in sorted(candidate)
                                        ],
                                        "counts_as_placement_node": False,
                                    }
                                )
                                stats_variant_counts["dock_capable_main_process_count"] = len(
                                    dock_capable_hashes
                                )
                                stats_variant_counts["packaging_shipping_anchor_pair_count"] = (
                                    pair_count
                                )
                                stats_variant_counts[
                                    "packaging_shipping_pair_necessary_pass_count"
                                ] = necessary_pass_count
                            yielded += 1
                            yield candidate
                            if yielded >= limit:
                                return
    if stats is not None:
        assert stats_variant_counts is not None
        stats_variant_counts["packaging_shipping_anchor_pair_count"] = pair_count
        stats_variant_counts["packaging_shipping_pair_necessary_pass_count"] = necessary_pass_count
        stats_variant_counts["dock_capable_main_process_count"] = len(dock_capable_hashes)
        stats_variant_counts["dual_interface_stage_counts"] = dock_stage_counts


def _module_main_site_assemblies_dock_backsolved(
    context: _PlacementSearchContext,
    main_compositions: Sequence[LocalBuildingCompositionV1],
    layout_family: str,
    process_axis: str,
    process_direction: str,
    bays: Sequence[BuildableBayV1],
    *,
    limit: int,
    source_pairs: Sequence[tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]]]
    | None = None,
    stats: _PlacementSearchStats | None = None,
) -> Iterator[dict[str, PlacedRectangleV1] | None]:
    """Jointly assemble packaging, sorting, and dock-backed process geometry.

    The previous finite local finished-module catalog could be too narrow for
    a site dock event: translating a compact preselected chain onto shipping
    did not guarantee that its secondary room met any package-derived sorting
    root.  This path instead enumerates the authoritative MUST chain from the
    fixed site-frame shipping rectangle inward for each package-derived root.
    Room dimensions and each positive shared edge remain unchanged authority.
    """
    if limit <= 0 or not bays:
        return
    selected_source_pairs = tuple(
        source_pairs or _main_module_source_pairs(context, main_compositions)
    )
    if not selected_source_pairs:
        return

    if stats is not None:
        if stats.site_module_variant_counts is None:
            stats.site_module_variant_counts = {}
        counts = stats.site_module_variant_counts
        if stats.site_packaging_anchors is None:
            stats.site_packaging_anchors = _enumerate_packaging_site_anchors(context, bays)
        package_root_options = stats.site_packaging_sorting_roots_by_anchor
        if package_root_options is None:
            package_root_options = {}
            stats.site_packaging_sorting_roots_by_anchor = package_root_options
        if stats.site_packaging_construction_anchors is None:
            stats.site_packaging_construction_anchors = (
                _packaging_anchor_construction_representatives(
                    context,
                    stats.site_packaging_anchors,
                    bays,
                    root_options_by_anchor=package_root_options,
                    stats=stats,
                )
            )
        package_anchors = stats.site_packaging_construction_anchors
        if stats.site_shipping_dock_anchors is None:
            stats.site_shipping_dock_anchors = _shipping_dock_anchors_at_entrance(context)
        if stats.site_shipping_dock_construction_anchors is None:
            stats.site_shipping_dock_construction_anchors = (
                _shipping_dock_anchor_construction_representatives(
                    stats.site_shipping_dock_anchors,
                    limit=_shipping_dock_anchor_construction_limit(
                        stats.site_shipping_dock_anchors
                    ),
                    truck_entrance_segment=_truck_entrance_for_dock_anchor_order(context),
                )
            )
        dock_anchors = stats.site_shipping_dock_construction_anchors
        dock_points = _truck_dock_events_at_entrance(context)
        counts.update(
            {
                "truck_dock_point_count": len({tuple(row["dock_point_mm"]) for row in dock_points}),
                "shipping_dock_rectangle_count": len(
                    {row.shipping_rectangle.bounds_mm for row in stats.site_shipping_dock_anchors}
                ),
                "shipping_dock_rectangle_count_by_rotation": {
                    str(rotation): len(
                        {
                            row.shipping_rectangle.bounds_mm
                            for row in stats.site_shipping_dock_anchors
                            if row.shipping_rotation_deg == rotation
                        }
                    )
                    for rotation in (0, 90)
                },
                "shipping_dock_rectangle_count_by_loading_face_side": {
                    side: len(
                        {
                            row.shipping_rectangle.bounds_mm
                            for row in stats.site_shipping_dock_anchors
                            if row.loading_face_side == side
                        }
                    )
                    for side in sorted(
                        {row.loading_face_side for row in stats.site_shipping_dock_anchors}
                    )
                },
                "shipping_dock_construction_representative_count": len(dock_anchors),
            }
        )
    else:
        all_packages = _enumerate_packaging_site_anchors(context, bays)
        package_root_options = {}
        package_anchors = _packaging_anchor_construction_representatives(
            context, all_packages, bays, root_options_by_anchor=package_root_options
        )
        dock_anchors = _shipping_dock_anchor_construction_representatives(
            _shipping_dock_anchors_at_entrance(context),
            limit=_shipping_dock_anchor_construction_limit(
                _shipping_dock_anchors_at_entrance(context)
            ),
            truck_entrance_segment=_truck_entrance_for_dock_anchor_order(context),
        )
        counts = None
    if not package_anchors or not dock_anchors:
        return

    raw_modules: list[tuple[int, dict[str, PlacedRectangleV1]]] = []
    seen_raw: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    for source_pair_index, (raw_source, _finished_source) in enumerate(selected_source_pairs):
        for raw_module in _site_assembly_module_variants(raw_source):
            signature = _module_signature(raw_module)
            if signature in seen_raw:
                continue
            seen_raw.add(signature)
            raw_modules.append((source_pair_index, raw_module))
    if not raw_modules:
        return

    chain_cache: dict[tuple[Any, ...], tuple[dict[str, PlacedRectangleV1], ...]] = {}
    emitted_signatures: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()
    emitted_external_interface_pairs: set[tuple[Any, ...]] = set()
    dock_capable_hashes: set[str] = set()
    stage_counts = {
        "dock_backsolved_finished_site_valid_count": 0,
        "packaging_dock_joint_sorting_root_count": 0,
        "raw_attachment_candidate_count": 0,
        "raw_attachment_site_valid_count": 0,
        "main_must_graph_valid_count": 0,
        "dock_capable_main_process_count": 0,
    }
    pair_count = 0
    necessary_pair_count = 0
    yielded = 0
    truck_preflight_attempt_count = 0
    face_pairs = _family_core_face_pairs(layout_family, process_axis, process_direction)

    for package_anchor in package_anchors:
        package_roots = package_root_options.get(package_anchor.anchor_id)
        if package_roots is None:
            package_roots = _packaging_driven_sorting_roots(
                context, package_anchor, bays=bays, stats=stats
            )
            package_root_options[package_anchor.anchor_id] = package_roots
        for dock_anchor in dock_anchors:
            pair_count += 1
            external_pair_identity = (
                package_anchor.rectangle.bounds_mm,
                dock_anchor.shipping_rectangle.bounds_mm,
                dock_anchor.shipping_rotation_deg,
                dock_anchor.dock_point_mm,
                dock_anchor.source_template_identity,
                dock_anchor.source_template_rotation_deg,
                dock_anchor.source_entry_point_mm,
            )
            fixed_interfaces = {
                "packaging_material_storage": package_anchor.rectangle,
                "shipping_channel": dock_anchor.shipping_rectangle,
            }
            if not _site_module_is_usable(context, fixed_interfaces, {}):
                continue

            viable_roots: list[
                tuple[
                    PlacedRectangleV1,
                    str,
                    PlacedRectangleV1 | None,
                    dict[str, Any],
                    tuple[dict[str, PlacedRectangleV1], ...],
                ]
            ] = []
            for root, package_side, corridor, package_witness in _dual_interface_sorting_roots(
                context,
                package_anchor,
                dock_anchor,
                bays,
                packaging_roots=package_roots,
                layout_family=layout_family,
                process_axis=process_axis,
                process_direction=process_direction,
                stats=stats,
            ):
                if corridor is not None and any(
                    rectangles_overlap(corridor, rectangle)
                    for rectangle in (*fixed_interfaces.values(), root)
                ):
                    continue
                cache_key = (
                    dock_anchor.shipping_rectangle.bounds_mm,
                    dock_anchor.shipping_rotation_deg,
                    dock_anchor.dock_point_mm,
                    dock_anchor.source_template_identity,
                    dock_anchor.source_template_rotation_deg,
                    root.bounds_mm,
                    root.rotation_deg,
                    layout_family,
                    process_axis,
                    process_direction,
                )
                chains = chain_cache.get(cache_key)
                if chains is None:
                    if stats is not None:
                        stats.finished_dock_backsolve_attempt_count += 1
                    chains = _dock_backsolved_finished_chains(
                        context,
                        dock_anchor,
                        root,
                        {},
                        layout_family,
                        process_axis,
                        process_direction,
                    )
                    chain_cache[cache_key] = chains
                package_root_fixed = {
                    "packaging_material_storage": package_anchor.rectangle,
                    "sorting_packaging_room": root,
                    "shipping_channel": dock_anchor.shipping_rectangle,
                }
                accepted_chains = tuple(
                    chain
                    for chain in chains
                    if _site_module_is_usable(context, chain, package_root_fixed)
                    and (
                        corridor is None
                        or not any(
                            rectangles_overlap(corridor, rectangle) for rectangle in chain.values()
                        )
                    )
                )
                if not accepted_chains:
                    continue
                stage_counts["packaging_dock_joint_sorting_root_count"] += 1
                stage_counts["dock_backsolved_finished_site_valid_count"] += len(accepted_chains)
                viable_roots.append(
                    (root, package_side, corridor, package_witness, accepted_chains)
                )
            if viable_roots:
                necessary_pair_count += 1
            if stats is not None:
                if stats.site_module_assembly_trace is None:
                    stats.site_module_assembly_trace = []
                stats.site_module_assembly_trace.append(
                    {
                        "stage": "S0_DUAL_EXTERNAL_INTERFACE_SORTING_ROOTS",
                        "layout_family": layout_family,
                        "packaging_anchor": package_anchor.to_dict(),
                        "shipping_dock_anchor": dock_anchor.to_dict(),
                        "sorting_roots": [
                            {
                                "bounds_mm": list(root.bounds_mm),
                                "rotation_deg": root.rotation_deg,
                                "package_side_of_sorting": package_side,
                                "alignment_witness": {
                                    **package_witness,
                                    "dock_backsolved_chain_count": len(accepted_chains),
                                    "site_valid_joint_chain_count": len(accepted_chains),
                                    "joint_external_interface_match": True,
                                },
                                "reserved_corridor_bounds_mm": (
                                    list(corridor.bounds_mm) if corridor is not None else None
                                ),
                            }
                            for (
                                root,
                                package_side,
                                corridor,
                                package_witness,
                                accepted_chains,
                            ) in viable_roots
                        ],
                        "root_generation_uses_dock_backsolved_secondary": True,
                        "joint_interface_root_set_empty": not bool(viable_roots),
                        "counts_as_placement_node": False,
                    }
                )

            pair_emitted = False
            for root, _package_side, corridor, package_witness, chains in viable_roots:
                if pair_emitted:
                    break
                root_emitted = False
                fixed_main = {
                    "packaging_material_storage": package_anchor.rectangle,
                    "sorting_packaging_room": root,
                    "shipping_channel": dock_anchor.shipping_rectangle,
                }
                for dock_finished_zones in chains:
                    if root_emitted:
                        break
                    secondary = dock_finished_zones["secondary_precooling_room"]
                    finished_side = _adjacent_side(root, secondary)
                    raw_sides = tuple(
                        dict.fromkeys(
                            raw_side
                            for raw_side, candidate_finished_side in face_pairs
                            if candidate_finished_side == finished_side
                        )
                    )
                    if not raw_sides:
                        continue
                    fixed_main.update(dock_finished_zones)
                    for source_pair_index, raw_module in raw_modules:
                        if root_emitted:
                            break
                        for raw_side in raw_sides:
                            if root_emitted:
                                break
                            for raw_alignment in ("CENTER", "LOW", "HIGH"):
                                if root_emitted:
                                    break
                                raw_attached = _module_attached_to_zone(
                                    raw_module,
                                    "primary_precooling_room",
                                    root,
                                    raw_side,
                                    raw_alignment,
                                )
                                if raw_attached is None:
                                    continue
                                stage_counts["raw_attachment_candidate_count"] += 1
                                if not _site_module_is_usable(context, raw_attached, fixed_main):
                                    continue
                                if corridor is not None and any(
                                    rectangles_overlap(corridor, rectangle)
                                    for rectangle in raw_attached.values()
                                ):
                                    continue
                                stage_counts["raw_attachment_site_valid_count"] += 1
                                candidate = {**fixed_main, **raw_attached}
                                main = {
                                    code: candidate[code]
                                    for code in MAIN_PROCESS_SKELETON_ZONE_CODES
                                }
                                try:
                                    _validate_main_process_skeleton_graph(context.graph, main)
                                except LayoutAuthorityError:
                                    continue
                                stage_counts["main_must_graph_valid_count"] += 1
                                if not _site_module_is_usable(context, main, {}):
                                    continue
                                try:
                                    seed = _canonical_site_main_skeleton(
                                        context,
                                        main,
                                        layout_family=layout_family,
                                        process_axis=process_axis,
                                        process_direction=process_direction,
                                        generation_pattern=(
                                            f"{layout_family}:DUAL_INTERFACE_DOCK_BACKSOLVE:"
                                            f"{dock_anchor.source_template_identity}:"
                                            f"{source_pair_index}"
                                        ),
                                    )
                                except LayoutAuthorityError:
                                    continue
                                dock_capable_hashes.add(seed.main_process_skeleton_hash)
                                stage_counts["dock_capable_main_process_count"] = len(
                                    dock_capable_hashes
                                )
                                signature = _module_signature(candidate)
                                if signature in emitted_signatures:
                                    continue
                                emitted_signatures.add(signature)
                                if stats is not None:
                                    assert counts is not None
                                    # The caller charges each yielded attempt (including a
                                    # rejected ``None`` marker) to the single placement-node
                                    # budget. Stop before doing another preflight once that
                                    # shared budget has been reached.
                                    if stats.visited_nodes >= context.node_budget:
                                        counts["dock_main_preflight_attempt_limit_reached"] = True
                                        return
                                    truck_preflight_attempt_count += 1
                                    counts["dock_main_truck_preflight_attempt_count"] = (
                                        truck_preflight_attempt_count
                                    )
                                    if not _constructive_main_skeleton_tail_admission(
                                        context, stats, seed, run_truck_preflight=True
                                    ):
                                        registry = context.global_main_process_geometry_registry
                                        registry_row = (
                                            registry.get(seed.main_process_skeleton_hash, {})
                                            if registry is not None
                                            else {}
                                        )
                                        truck_row = registry_row.get(
                                            "main_skeleton_truck_preflight"
                                        )
                                        if (
                                            isinstance(truck_row, Mapping)
                                            and truck_row.get("preflight_status") == "REJECT"
                                        ):
                                            stage_counts["truck_preflight_reject_count"] = (
                                                stage_counts.get("truck_preflight_reject_count", 0)
                                                + 1
                                            )
                                        else:
                                            stage_counts["formal_admission_reject_count"] = (
                                                stage_counts.get("formal_admission_reject_count", 0)
                                                + 1
                                            )
                                        if stats.site_module_assembly_trace is None:
                                            stats.site_module_assembly_trace = []
                                        stats.site_module_assembly_trace.append(
                                            {
                                                "stage": "S1_MAIN_TRUCK_PREFLIGHT",
                                                "result": "REJECTED",
                                                "layout_family": layout_family,
                                                "main_process_skeleton_hash": (
                                                    seed.main_process_skeleton_hash
                                                ),
                                                "truck_preflight": (
                                                    dict(truck_row)
                                                    if isinstance(truck_row, Mapping)
                                                    else None
                                                ),
                                                "tail_search_started": False,
                                            }
                                        )
                                        # Surface the rejected construction attempt so the
                                        # scheduler charges exactly one placement node, then
                                        # resume this external-anchor pair at its next finite
                                        # sorting root. A rejected root is not an S1 candidate.
                                        yield None
                                        continue
                                    registry = context.global_main_process_geometry_registry
                                    registry_row = (
                                        registry.get(seed.main_process_skeleton_hash, {})
                                        if registry is not None
                                        else {}
                                    )
                                    truck_row = registry_row.get("main_skeleton_truck_preflight")
                                    if isinstance(truck_row, Mapping):
                                        status = truck_row.get("preflight_status")
                                        if status == "PASS":
                                            stage_counts["truck_preflight_pass_count"] = (
                                                stage_counts.get("truck_preflight_pass_count", 0)
                                                + 1
                                            )
                                        elif status == "UNRESOLVED":
                                            stage_counts["truck_preflight_unresolved_count"] = (
                                                stage_counts.get(
                                                    "truck_preflight_unresolved_count", 0
                                                )
                                                + 1
                                            )
                                if stats is not None:
                                    if stats.site_module_assembly_trace is None:
                                        stats.site_module_assembly_trace = []
                                    if stats.site_main_source_pair_rows is None:
                                        stats.site_main_source_pair_rows = []
                                    stats.site_main_source_pair_rows.append(
                                        {
                                            "layout_family": layout_family,
                                            "source_pair_index": source_pair_index,
                                            "input_geometry_signature": repr(
                                                _module_signature(raw_module)
                                            ),
                                            "result": (
                                                "PACKAGING_RESERVED_MAIN_LIMIT_REACHED"
                                                if yielded + 1 >= limit
                                                else "PACKAGING_RESERVED_MAIN_EMITTED"
                                            ),
                                            "tail_capacity_exhausted": False,
                                            "dock_backsolved": True,
                                            "shipping_dock_point_mm": list(
                                                dock_anchor.dock_point_mm
                                            ),
                                            "sorting_root_bounds_mm": list(root.bounds_mm),
                                        }
                                    )
                                    stats.site_module_assembly_trace.append(
                                        {
                                            "stage": "S1_DOCK_CAPABLE_MAIN_PROCESS",
                                            "result": "DOCK_CAPABLE_MAIN_PROCESS",
                                            "layout_family": layout_family,
                                            "main_process_skeleton_hash": (
                                                seed.main_process_skeleton_hash
                                            ),
                                            "packaging_anchor": package_anchor.to_dict(),
                                            "shipping_dock_anchor": dock_anchor.to_dict(),
                                            "shipping_exact_dock_anchor_match": True,
                                            "sorting_rotation_deg": root.rotation_deg,
                                            "sorting_root_bounds_mm": list(root.bounds_mm),
                                            "finished_site_construction": "BACKWARD_FROM_DOCK",
                                            "dock_backsolved_secondary_bounds_mm": list(
                                                secondary.bounds_mm
                                            ),
                                            "packaging_interface_witness": package_witness,
                                            "source_pair_index": source_pair_index,
                                            "packaging_slot_exists": True,
                                            "formal_packaging_preflight": "PENDING_OUTER_GATE",
                                            "zones": [
                                                candidate[code].to_dict()
                                                for code in sorted(candidate)
                                            ],
                                            "counts_as_placement_node": False,
                                        }
                                    )
                                yielded += 1
                                if stats is not None:
                                    assert counts is not None
                                    counts["dock_capable_main_process_count"] = len(
                                        dock_capable_hashes
                                    )
                                    counts["packaging_shipping_anchor_pair_count"] = pair_count
                                    counts["packaging_shipping_pair_necessary_pass_count"] = (
                                        necessary_pair_count
                                    )
                                    counts["dual_interface_stage_counts"] = dict(stage_counts)
                                root_emitted = True
                                pair_emitted = True
                                emitted_external_interface_pairs.add(external_pair_identity)
                                yield candidate
                                if yielded >= limit:
                                    break
                            if yielded >= limit:
                                break
                        if yielded >= limit:
                            break
                    fixed_main = {
                        "packaging_material_storage": package_anchor.rectangle,
                        "sorting_packaging_room": root,
                        "shipping_channel": dock_anchor.shipping_rectangle,
                    }
                    if yielded >= limit:
                        break
                if yielded >= limit:
                    break
            if yielded >= limit:
                break
        if yielded >= limit:
            break

    if stats is not None:
        assert counts is not None
        counts["dock_capable_main_process_count"] = len(dock_capable_hashes)
        counts["packaging_shipping_anchor_pair_count"] = pair_count
        counts["packaging_shipping_pair_necessary_pass_count"] = necessary_pair_count
        counts["candidate_emitted_external_interface_pair_count"] = len(
            emitted_external_interface_pairs
        )
        counts["dual_interface_stage_counts"] = stage_counts


def _module_main_site_assemblies(
    context: _PlacementSearchContext,
    main_compositions: Sequence[LocalBuildingCompositionV1],
    layout_family: str,
    process_axis: str,
    process_direction: str,
    bays: Sequence[BuildableBayV1],
    *,
    limit: int,
    source_pairs: Sequence[tuple[dict[str, PlacedRectangleV1], dict[str, PlacedRectangleV1]]]
    | None = None,
    stats: _PlacementSearchStats | None = None,
) -> Iterator[dict[str, Any] | None]:
    """Prioritize exact dock-backsolved assemblies, then use forward fallback."""
    if limit <= 0:
        return
    dock_rows = iter(
        _module_main_site_assemblies_dock_backsolved(
            context,
            main_compositions,
            layout_family,
            process_axis,
            process_direction,
            bays,
            limit=limit,
            source_pairs=source_pairs,
            stats=stats,
        )
    )
    forward_rows = iter(
        _module_main_site_assemblies_forward(
            context,
            main_compositions,
            layout_family,
            process_axis,
            process_direction,
            bays,
            limit=limit,
            source_pairs=source_pairs,
            stats=stats,
        )
    )
    emitted = 0
    for candidate in dock_rows:
        yield candidate
        emitted += 1
        if emitted >= limit:
            return
    for forward_candidate in forward_rows:
        yield forward_candidate
        emitted += 1
        if emitted >= limit:
            return


def _search_provenance(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
    *,
    search_tree_exhausted: bool,
    objective_optimal_within_search_family: bool,
) -> dict[str, Any]:
    return {
        "search_profile_identity": SEARCH_PROFILE_IDENTITY,
        "node_budget": context.node_budget,
        "complete_candidate_limit": context.complete_candidate_limit,
        "complete_candidate_limit_stops_search": False,
        "visited_nodes": stats.visited_nodes,
        "generated_candidates": stats.generated_candidates,
        "complete_candidates": stats.complete_candidates,
        "budget_exhausted": stats.node_budget_exhausted,
        "node_budget_exhausted": stats.node_budget_exhausted,
        "search_tree_exhausted": search_tree_exhausted,
        "objective_optimal_within_search_family": objective_optimal_within_search_family,
        "node_budget_is_only_search_cutoff": True,
        "candidate_family": "MULTI_FAMILY_STRUCTURAL_SKELETON_V1",
        "structural_composition_identity": "structural-composition-family@1.0.0",
        "structural_skeleton": context.structural_skeleton.to_dict(),
        "search_phase": context.search_phase,
        "placement_zone_order": list(context.placement_zone_order),
        "structured_main_skeleton_diversity": {
            "policy_identity": "main-process-skeleton-sampling@1.0.0",
            "completion_cap_per_skeleton": STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON,
            "distinct_skeletons_with_complete_candidate": len(
                stats.structured_main_skeleton_completions or {}
            ),
            "completion_counts": sorted(
                (stats.structured_main_skeleton_completions or {}).values()
            ),
        },
        "structured_core_root_diversity": {
            "policy_identity": "process-core-root-sampling@1.0.0",
            "distinct_roots_with_complete_candidate": len(
                stats.structured_core_root_completions or {}
            ),
            "completion_cap_per_root": STRUCTURED_COMPLETIONS_PER_CORE_ROOT,
        },
        "main_process_skeleton_construction": {
            "identity": "main-process-skeleton-construction@1.0.0",
            "constructed_candidate_count": len(stats.constructed_main_skeletons or {}),
            "generation_patterns": dict(sorted((stats.skeleton_generation_patterns or {}).items())),
            "rejection_reason_counts": dict(sorted((stats.rejection_reason_counts or {}).items())),
            "candidates": [
                {
                    "main_process_skeleton_hash": candidate.main_process_skeleton_hash,
                    "family": candidate.family.to_dict(),
                    "generation_pattern": candidate.generation_pattern,
                    "layout_family": candidate.building_layout_family,
                    "envelope_family": candidate.building_envelope_family,
                }
                for candidate in sorted(
                    (stats.constructed_main_skeletons or {}).values(),
                    key=lambda row: row.main_process_skeleton_hash,
                )
            ],
        },
    }


def _record_rejection(stats: _PlacementSearchStats, reason: str) -> None:
    if stats.rejection_reason_counts is None:
        stats.rejection_reason_counts = {}
    stats.rejection_reason_counts[reason] = stats.rejection_reason_counts.get(reason, 0) + 1


def _geometry_rejection_reason(
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    context: _PlacementSearchContext,
) -> str | None:
    left, bottom, right, top = _bounds(rectangle)
    min_x, min_y, max_x, max_y = context.boundary_bounds
    if left < min_x or bottom < min_y or right > max_x or top > max_y:
        return "SITE_OUTSIDE"
    if not rectangle_inside_polygon(rectangle, context.boundary):
        return "SITE_OUTSIDE"
    if any(
        rectangle_intersects_closed_obstacle(rectangle, obstacle) for obstacle in context.obstacles
    ):
        return "NO_BUILD_COLLISION"
    if any(rectangles_overlap(rectangle, other) for other in placed.values()):
        return "ZONE_OVERLAP"
    return None


def _constructive_edge_options(
    context: _PlacementSearchContext,
    code: str,
    placed: Mapping[str, PlacedRectangleV1],
    neighbor_code: str,
    *,
    required_side: str | tuple[str, ...] | None = None,
    bridge_code: str | None = None,
    bank_alignment_code: str | None = None,
    anchor_reference_codes: Sequence[str] = (),
    prefer_truck_entrance: bool = False,
    stats: _PlacementSearchStats,
) -> tuple[PlacedRectangleV1, ...]:
    """Construct exact adjacent options for one named skeleton edge."""
    neighbor = placed[neighbor_code]
    authority = context.authorities[code]
    variants = _dimension_variants(authority, placed, context.boundary)
    if not variants:
        _record_rejection(stats, "DIMENSION_VARIANT_UNAVAILABLE")
        return ()
    options: dict[tuple[int, int, int, int], PlacedRectangleV1] = {}
    truck_interface_shipping = (
        _shipping_rectangles_for_dock_events(context)
        if code in {"shipping_channel", "finished_goods_room"}
        else ()
    )
    truck_interface_only_bounds: set[tuple[int, int, int, int]] = set()
    graph_neighbors = _must_neighbors(code, placed, context.graph)
    anchor_references = tuple(
        placed[reference_code]
        for reference_code in anchor_reference_codes
        if reference_code in placed and reference_code != neighbor_code
    )
    for width_mm, depth_mm, rotation in variants:
        actual_width, actual_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        candidate_anchors = set(_edge_anchors(neighbor, actual_width, actual_depth))
        established_anchors = set(candidate_anchors)
        if code == "shipping_channel":
            truck_event_anchors = {
                (rectangle.bounds_mm[0], rectangle.bounds_mm[1])
                for rectangle in truck_interface_shipping
            }
            candidate_anchors.update(truck_event_anchors)
        elif code == "finished_goods_room":
            truck_event_anchors = set()
            for shipping_rectangle in truck_interface_shipping:
                truck_event_anchors.update(
                    _edge_anchors(shipping_rectangle, actual_width, actual_depth)
                )
            candidate_anchors.update(truck_event_anchors)
        else:
            truck_event_anchors = set()
        for anchor_reference in anchor_references:
            reference_anchors = set(_edge_anchors(anchor_reference, actual_width, actual_depth))
            established_anchors.update(reference_anchors)
            candidate_anchors.update(reference_anchors)
        for x_mm, y_mm in sorted(candidate_anchors):
            rectangle = _rectangle_from_mm(code, x_mm, y_mm, width_mm, depth_mm, rotation)
            candidate_side = _adjacent_side(neighbor, rectangle)
            if required_side is not None and candidate_side not in (
                required_side if isinstance(required_side, tuple) else (required_side,)
            ):
                continue
            rejection = _geometry_rejection_reason(rectangle, placed, context)
            if rejection is not None:
                _record_rejection(stats, rejection)
                continue
            structured_plan = getattr(context, "structured_building_plan", None)
            if structured_plan is not None and not structured_plan.admits(code, rectangle):
                _record_rejection(stats, "ENVELOPE_OR_BAND_REJECT")
                continue
            if any(
                not rectangles_share_positive_edge(rectangle, must_neighbor)
                for must_neighbor in graph_neighbors
            ):
                _record_rejection(stats, "MUST_ADJACENCY_FAIL")
                continue
            left, bottom, right, top = _bounds(rectangle)
            key = (left, bottom, right, top)
            if (
                code in {"shipping_channel", "finished_goods_room"}
                and (x_mm, y_mm) in truck_event_anchors
                and (x_mm, y_mm) not in established_anchors
            ):
                truck_interface_only_bounds.add(key)
            current = options.get(key)
            current_variant = (
                (
                    _mm(current.width_m, field="candidate.width_m"),
                    _mm(current.depth_m, field="candidate.depth_m"),
                    current.rotation_deg,
                )
                if current is not None
                else None
            )
            variant = (width_mm, depth_mm, rotation)
            if current_variant is None or variant < current_variant:
                options[key] = rectangle
    rows = tuple(options[key] for key in sorted(options))
    if not rows:
        _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
        return ()

    def preference(
        rectangle: PlacedRectangleV1,
    ) -> tuple[int, ...]:
        alignment_penalty = 0
        topology_alignment_penalty = 0
        truck_distance_squared = 0
        truck_dock_ordering = (0, 0, 0)
        if bank_alignment_code is not None:
            bank_reference = placed[bank_alignment_code]
            reference_bounds = _bounds(bank_reference)
            candidate_bounds = _bounds(rectangle)
            candidate_side = _adjacent_side(neighbor, rectangle)
            if candidate_side in {"EAST", "WEST"}:
                alignment_penalty = int(
                    candidate_bounds[1] != reference_bounds[1]
                    or candidate_bounds[3] != reference_bounds[3]
                )
            else:
                alignment_penalty = int(
                    candidate_bounds[0] != reference_bounds[0]
                    or candidate_bounds[2] != reference_bounds[2]
                )
        if context.structural_topology == OFFSET_LINEAR_BAND and code in {
            "primary_precooling_room",
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        }:
            candidate_bounds = _bounds(rectangle)
            neighbor_bounds = _bounds(neighbor)
            candidate_side = _adjacent_side(neighbor, rectangle)
            if candidate_side in {"NORTH", "SOUTH"}:
                cross_axis_aligned = (
                    candidate_bounds[0] == neighbor_bounds[0]
                    and candidate_bounds[2] == neighbor_bounds[2]
                )
            else:
                cross_axis_aligned = (
                    candidate_bounds[1] == neighbor_bounds[1]
                    and candidate_bounds[3] == neighbor_bounds[3]
                )
            # For the offset topology, aligned/unaligned is only an ordering
            # preference. Positive edge adjacency and the exact final topology
            # predicate remain mandatory.
            topology_alignment_penalty = int(cross_axis_aligned)
        bridge_penalty = int(
            bridge_code is not None
            and not rectangles_share_positive_edge(rectangle, placed[bridge_code])
        )
        entrance_penalty = int(
            prefer_truck_entrance
            and not _rectangle_shares_entrance_boundary(
                rectangle, _truck_segment(context.site_body)
            )
        )
        if code == "shipping_channel" and prefer_truck_entrance:
            truck_distance_squared = _rectangle_distance_squared_to_entrance(
                rectangle, _truck_segment(context.site_body)
            )
            _, loading_face, _, _ = _loading_face(rectangle, context.site_body)
            dock_location_penalty = _loading_face_dock_endpoint_penalty(context, rectangle)
            truck_dock_ordering = (
                _shipping_loading_face_approach_axis_penalty(context, rectangle),
                0 if dock_location_penalty == 0 else 1 if dock_location_penalty == 1 else 2,
                int(
                    not any(
                        _on_segment(point, loading_face[0], loading_face[1])
                        for point in _truck_dock_points_at_entrance(context)
                    )
                ),
            )
        return (
            alignment_penalty,
            topology_alignment_penalty,
            bridge_penalty,
            entrance_penalty,
            int(_bounds(rectangle) in truck_interface_only_bounds),
            *truck_dock_ordering,
            truck_distance_squared,
            -(
                context_plan.primary_grid.aligned_edge_count(rectangle)
                if (context_plan := getattr(context, "structured_building_plan", None)) is not None
                else 0
            ),
            *_bounds(rectangle)[:2],
            _bounds(rectangle)[2],
            rectangle.rotation_deg,
        )

    ordered_rows = tuple(sorted(rows, key=preference))
    if code == "finished_goods_room" and truck_interface_only_bounds:
        # Preserve one established branch first, then interleave a room
        # explicitly paired to an entrance/dock-derived shipping event.
        # This is deterministic coverage ordering, not a hard constraint
        # or topology ranking bonus.
        return _interleave_finished_truck_interface_options(
            ordered_rows, truck_interface_only_bounds
        )
    return ordered_rows


def _constructive_sorting_roots(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
) -> tuple[PlacedRectangleV1, ...]:
    plan = context.structured_building_plan
    if plan is None:
        return ()
    authority = context.authorities["sorting_packaging_room"]
    variants = _dimension_variants(authority, {}, context.boundary)
    if not variants:
        _record_rejection(stats, "DIMENSION_VARIANT_UNAVAILABLE")
        return ()
    skeleton_roots = set(context.structural_skeleton.root_anchor_candidates)
    roots: dict[tuple[int, int, int, int], PlacedRectangleV1] = {}
    for width_mm, depth_mm, rotation in variants:
        actual_width, actual_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        anchors = set(
            _structural_event_anchors(
                {}, context.boundary, context.obstacles, actual_width, actual_depth
            )
        )
        anchors.update(
            (int(x * MILLIMETRES_PER_METRE), int(y * MILLIMETRES_PER_METRE))
            for x, y, root_rotation in skeleton_roots
            if root_rotation == rotation
        )
        process_band = next(band for band in plan.bands if band.band_code == "PROCESS_CORE_BAND")
        grid = plan.primary_grid
        planned_origins = {
            *((x_mm, y_mm) for x_mm in grid.event_x_mm for y_mm in grid.y_axes_mm),
            *((x_mm, y_mm) for x_mm in grid.x_axes_mm for y_mm in grid.event_y_mm),
        }
        anchors.update(
            (x_mm, y_mm)
            for x_mm, y_mm in planned_origins
            if process_band.contains(
                _rectangle_from_mm(
                    "sorting_packaging_room", x_mm, y_mm, width_mm, depth_mm, rotation
                )
            )
        )
        for x_mm, y_mm in sorted(anchors):
            rectangle = _rectangle_from_mm(
                "sorting_packaging_room", x_mm, y_mm, width_mm, depth_mm, rotation
            )
            rejection = _geometry_rejection_reason(rectangle, {}, context)
            if rejection is not None:
                _record_rejection(stats, rejection)
                continue
            if not plan.admits("sorting_packaging_room", rectangle):
                _record_rejection(stats, "ENVELOPE_OR_BAND_REJECT")
                continue
            left, bottom, right, top = _bounds(rectangle)
            key = (left, bottom, right, top)
            current = roots.get(key)
            current_variant = (
                (
                    _mm(current.width_m, field="sorting.width_m"),
                    _mm(current.depth_m, field="sorting.depth_m"),
                    current.rotation_deg,
                )
                if current is not None
                else None
            )
            variant = (width_mm, depth_mm, rotation)
            if current_variant is None or variant < current_variant:
                roots[key] = rectangle

    preferred_positions = {
        (int(x * MILLIMETRES_PER_METRE), int(y * MILLIMETRES_PER_METRE))
        for x, y, _rotation in skeleton_roots
    }
    canonical_roots = sorted(
        roots.values(),
        key=lambda row: (row.bounds_mm[1], row.bounds_mm[0], row.rotation_deg),
    )
    preflight_penalties = {
        row.bounds_mm: _topology_root_ordering_penalty(context, row) for row in canonical_roots
    }
    if not canonical_roots:
        _record_rejection(stats, "NO_ROOT_INSIDE_STRUCTURED_PROCESS_BAND")
        return ()
    if context.structural_topology == CENTRAL_PROCESS_HUB:
        # Preserve the established, deterministic Hub root lane. Ordering the
        # existing structural anchor events first is important: the recent
        # envelope penalty reordered them and caused a known hard-valid Hub
        # path to disappear inside its unchanged tail budget.
        ordered = [row for row in canonical_roots if row.bounds_mm[:2] in preferred_positions]
        remaining = [row for row in canonical_roots if row.bounds_mm[:2] not in preferred_positions]
        if not ordered and remaining:
            ordered.append(remaining.pop(0))
    else:
        first = min(
            canonical_roots,
            key=lambda row: (
                preflight_penalties[row.bounds_mm],
                row.bounds_mm[:2] not in preferred_positions,
                row.bounds_mm[1],
                row.bounds_mm[0],
                row.rotation_deg,
            ),
        )
        ordered = [first]
        remaining = [row for row in canonical_roots if row != first]
    if stats.root_preflight_rows is None:
        stats.root_preflight_rows = []
    bounds_by_anchor = {row: row.bounds_mm for row in canonical_roots}
    penalties_by_anchor = {
        row: preflight_penalties[bounds_by_anchor[row]] for row in canonical_roots
    }

    def anchor_key(row: PlacedRectangleV1) -> tuple[int, int, int, int]:
        return bounds_by_anchor[row]

    minimum_squared_distances: dict[PlacedRectangleV1, int] = {}
    for row in remaining:
        row_left, row_bottom, _row_right, _row_top = anchor_key(row)
        minimum_squared_distances[row] = min(
            (row_left - chosen.bounds_mm[0]) ** 2 + (row_bottom - chosen.bounds_mm[1]) ** 2
            for chosen in ordered
        )
    while remaining:

        def diversity_key(row: PlacedRectangleV1) -> tuple[int, int, int, int, int]:
            x_mm, y_mm, _right_mm, _top_mm = anchor_key(row)
            minimum_squared_distance = minimum_squared_distances[row]
            # Max-min anchor spacing samples genuinely different potential
            # process cores without introducing a weighted quality score.
            if context.structural_topology == CENTRAL_PROCESS_HUB:
                return (
                    minimum_squared_distance,
                    -y_mm,
                    -x_mm,
                    -row.rotation_deg,
                    -row.bounds_mm[2],
                )
            return (
                -penalties_by_anchor[row],
                minimum_squared_distance,
                -y_mm,
                -x_mm,
                -row.rotation_deg,
            )

        next_root = max(remaining, key=diversity_key)
        ordered.append(next_root)
        remaining.remove(next_root)
        next_left, next_bottom, _next_right, _next_top = anchor_key(next_root)
        for row in remaining:
            left, bottom, _right, _top = anchor_key(row)
            distance = (left - next_left) ** 2 + (bottom - next_bottom) ** 2
            minimum_squared_distances[row] = min(minimum_squared_distances[row], distance)
    stats.root_preflight_rows.extend(
        {
            "sorting_root_bounds_mm": list(row.bounds_mm),
            "estimated_topology_envelope_penalty_mm": penalties_by_anchor[row],
            "use": "ORDERING_ONLY",
            "hard_pruned": False,
        }
        for row in ordered
    )
    return tuple(ordered)


def _family_attachment_sides(
    family: StructuralCompositionFamilyV1,
    topology: str | None = None,
) -> tuple[tuple[str, str], ...]:
    if family.family == "LINEAR_PROCESS_BAND":
        raw_side = {
            ("X", "POSITIVE"): "WEST",
            ("X", "NEGATIVE"): "EAST",
            ("Y", "POSITIVE"): "SOUTH",
            ("Y", "NEGATIVE"): "NORTH",
        }[(family.dominant_axis, family.dominant_direction)]
        return ((raw_side, _OPPOSITE_SIDE[raw_side]),)
    if topology == CENTRAL_PROCESS_HUB:
        # Distinct adjacent faces are explored first because they create a
        # genuine two-dimensional hub candidate space; opposite-face pairs
        # remain available after this constructive divergence is attempted.
        return (
            ("SOUTH", "WEST"),
            ("SOUTH", "EAST"),
            ("NORTH", "WEST"),
            ("NORTH", "EAST"),
            ("WEST", "SOUTH"),
            ("WEST", "NORTH"),
            ("EAST", "SOUTH"),
            ("EAST", "NORTH"),
            ("SOUTH", "NORTH"),
            ("NORTH", "SOUTH"),
            ("WEST", "EAST"),
            ("EAST", "WEST"),
        )
    return (
        ("SOUTH", "NORTH"),
        ("SOUTH", "WEST"),
        ("NORTH", "SOUTH"),
        ("EAST", "NORTH"),
        ("WEST", "NORTH"),
        ("WEST", "SOUTH"),
        ("EAST", "SOUTH"),
        ("NORTH", "EAST"),
        ("NORTH", "WEST"),
        ("SOUTH", "EAST"),
        ("WEST", "EAST"),
        ("EAST", "WEST"),
    )


def _sorting_roots_for_attachment_pair(
    context: _PlacementSearchContext,
    roots: Sequence[PlacedRectangleV1],
    raw_side: str,
    finished_side: str,
) -> tuple[PlacedRectangleV1, ...]:
    """Order planned core roots by exact adjacent-room projection room.

    This is an ordering prior only. Site polygons, obstacles, band membership,
    adjacency, and all later hard predicates remain authoritative. In
    particular, legacy topology anchors no longer get first service merely
    because they appeared in the old rectangle-first root list.
    """
    return tuple(
        sorted(
            roots,
            key=lambda rectangle: _sorting_root_attachment_pair_key(
                context, rectangle, raw_side, finished_side
            ),
        )
    )


def _sorting_root_attachment_pair_key(
    context: _PlacementSearchContext,
    rectangle: PlacedRectangleV1,
    raw_side: str,
    finished_side: str,
) -> tuple[int, int, int, int, int, int]:
    bounds = _bounds(rectangle)
    side_indexes = {"WEST": 0, "EAST": 2, "SOUTH": 1, "NORTH": 3}
    deficits: list[int] = []
    residual_clearances: list[int] = []
    for side, zone_code in (
        (raw_side, "primary_precooling_room"),
        (finished_side, "secondary_precooling_room"),
    ):
        index = side_indexes[side]
        available = (
            bounds[index] - context.boundary_bounds[index]
            if side in {"WEST", "SOUTH"}
            else context.boundary_bounds[index] - bounds[index]
        )
        normal_axis = "X" if side in {"WEST", "EAST"} else "Y"
        required = _minimum_authoritative_axis_extent(context, zone_code, normal_axis)
        deficits.append(max(0, required - available))
        residual_clearances.append(available - required)
    return (
        sum(deficits),
        max(deficits, default=0),
        -min(residual_clearances, default=0),
        _topology_root_ordering_penalty(context, rectangle),
        bounds[1],
        bounds[0],
    )


def _offset_transition_options(
    context: _PlacementSearchContext,
    placed: Mapping[str, PlacedRectangleV1],
    sorting: PlacedRectangleV1,
    candidates: Sequence[PlacedRectangleV1],
    direction: str,
    required_side: str,
    stats: _PlacementSearchStats,
) -> tuple[tuple[PlacedRectangleV1, ...], dict[tuple[int, int, int, int], int]]:
    """Construct only exact CORE->FINISHED edge options with nonzero band shift."""
    process_axis = context.structural_skeleton.ordering_axis
    cross_axis = "Y" if process_axis == "X" else "X"
    raw = _group_axis_interval(RAW_SIDE_GROUP, placed, cross_axis)
    core = _group_axis_interval(PROCESSING_CORE_GROUP, placed, cross_axis)
    if raw is None or core is None:
        return (), {}
    common_low = max(raw[0], core[0])
    common_high = min(raw[1], core[1])
    if common_low >= common_high:
        return (), {}
    cross_low_index, cross_high_index = (1, 3) if cross_axis == "Y" else (0, 2)
    sorting_bounds = _bounds(sorting)
    sorting_cross_low = sorting_bounds[cross_low_index]
    sorting_cross_high = sorting_bounds[cross_high_index]
    expanded_options = {_bounds(row): row for row in candidates}
    authority = context.authorities["secondary_precooling_room"]
    for width_mm, depth_mm, rotation in _dimension_variants(authority, placed, context.boundary):
        actual_width, actual_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        cross_extent = actual_width if cross_axis == "X" else actual_depth
        cross_start = common_high if direction == "POSITIVE" else common_low - cross_extent
        for anchor_x, anchor_y in _edge_anchors(sorting, actual_width, actual_depth):
            x_mm = cross_start if cross_axis == "X" else anchor_x
            y_mm = cross_start if cross_axis == "Y" else anchor_y
            candidate = _rectangle_from_mm(
                "secondary_precooling_room", x_mm, y_mm, width_mm, depth_mm, rotation
            )
            candidate_side = _adjacent_side(sorting, candidate)
            if candidate_side != required_side:
                continue
            rejection = _geometry_rejection_reason(candidate, placed, context)
            if rejection is not None:
                _record_rejection(stats, rejection)
                continue
            if candidate_side not in _CARDINAL_SIDES or not rectangles_share_positive_edge(
                sorting, candidate
            ):
                continue
            if any(
                not rectangles_share_positive_edge(candidate, neighbor)
                for neighbor in _must_neighbors("secondary_precooling_room", placed, context.graph)
            ):
                _record_rejection(stats, "MUST_ADJACENCY_FAIL")
                continue
            expanded_options[_bounds(candidate)] = candidate
    shifts_by_key: dict[tuple[int, int, int, int], int] = {}
    selected: list[PlacedRectangleV1] = []
    for candidate in (expanded_options[key] for key in sorted(expanded_options)):
        bounds = _bounds(candidate)
        interval = (bounds[cross_low_index], bounds[cross_high_index])
        core_overlap = max(interval[0], core[0]) < min(interval[1], core[1])
        if not core_overlap:
            continue
        if _adjacent_side(sorting, candidate) not in {"NORTH", "SOUTH", "EAST", "WEST"}:
            continue
        if direction == "POSITIVE":
            shift_mm = interval[0] - sorting_cross_low
            transition_valid = shift_mm > 0 and interval[0] >= common_high
        else:
            shift_mm = interval[1] - sorting_cross_high
            transition_valid = shift_mm < 0 and interval[1] <= common_low
        if transition_valid:
            selected.append(candidate)
            shifts_by_key[bounds] = shift_mm
    selected.sort(key=lambda row: (*_bounds(row), row.rotation_deg))
    if stats.offset_transition_trace is None:
        stats.offset_transition_trace = []
    stats.offset_transition_trace.append(
        {
            "topology": OFFSET_LINEAR_BAND,
            "transition_stage": "CORE_TO_FINISHED",
            "direction": direction,
            "cross_axis": cross_axis,
            "sorting_root_mm": list(sorting.bounds_mm),
            "raw_side": _adjacent_side(sorting, placed["primary_precooling_room"]),
            "finished_side": required_side,
            "raw_core_common_interval_mm": [common_low, common_high],
            "candidate_option_count": len(candidates),
            "transition_option_count": len(selected),
            "cross_axis_shifts_mm": sorted(shifts_by_key.values()),
            "transition_option_bounds_mm": [list(_bounds(row)) for row in selected],
        }
    )
    return tuple(selected), shifts_by_key


def _interleave_raw_bank_options(
    primary: PlacedRectangleV1,
    options: Sequence[PlacedRectangleV1],
    side_order: Sequence[str],
) -> tuple[PlacedRectangleV1, ...]:
    """Visit each legal raw-bank attachment face before repeating one face."""
    grouped: dict[str, list[PlacedRectangleV1]] = {}
    for option in options:
        side = _adjacent_side(primary, option)
        if side is not None:
            grouped.setdefault(side, []).append(option)
    interleaved: list[PlacedRectangleV1] = []
    while any(grouped.values()):
        for side in side_order:
            candidates = grouped.get(side)
            if candidates:
                interleaved.append(candidates.pop(0))
    return tuple(interleaved)


def _construct_face_skeletons(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
    sorting: PlacedRectangleV1,
    raw_side: str,
    finished_side: str,
    skeleton_node_limit: int,
    skeleton_limit: int,
    offset_direction: str | None = None,
) -> Iterator[MainProcessSkeletonCandidateV1 | _SearchQuantumYield]:
    """Construct one complete seven-zone skeleton for one core topology.

    Shipping-interface alternatives are deliberately not allowed to consume
    the whole constructive lane before another raw/finished face topology is
    tried.  Candidate diversity must come from the main process geometry, not
    merely from moving the terminal shipping rectangle.
    """
    plan = context.structured_building_plan
    if plan is None:
        return
    placed: dict[str, PlacedRectangleV1] = {"sorting_packaging_room": sorting}
    emitted_skeletons = 0
    primary_options = _constructive_edge_options(
        context,
        "primary_precooling_room",
        placed,
        "sorting_packaging_room",
        required_side=raw_side,
        stats=stats,
    )
    raw_required_sides: tuple[str, ...] = (
        ("WEST", "EAST") if context.structural_skeleton.ordering_axis == "Y" else ("SOUTH", "NORTH")
    )
    if context.structural_composition_family.family != "LINEAR_PROCESS_BAND":
        raw_required_sides = tuple(
            side for side in _CARDINAL_SIDES if side != _OPPOSITE_SIDE[raw_side]
        )
    for primary in primary_options:
        if stats.visited_nodes >= context.node_budget:
            stats.node_budget_exhausted = True
            stats.skeleton_search_truncated = True
            return
        stats.current_work_item = {
            "topology": context.structural_topology,
            "envelope_family": plan.envelope.family,
            "band_family": plan.layout_family,
            "sorting_root_mm": list(sorting.bounds_mm),
            "raw_side": raw_side,
            "finished_side": finished_side,
            "offset_direction": offset_direction,
            "branch": "PRIMARY",
        }
        stats.visited_nodes += 1
        stats.construction_node_count += 1
        quantum = _quantum_checkpoint(stats)
        if quantum is not None:
            yield quantum
        for descendant in (
            "raw_fruit_buffer",
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        ):
            placed.pop(descendant, None)
        placed["primary_precooling_room"] = primary
        raw_options = _constructive_edge_options(
            context,
            "raw_fruit_buffer",
            placed,
            "primary_precooling_room",
            required_side=raw_required_sides,
            bank_alignment_code="primary_precooling_room",
            stats=stats,
        )
        # Sample each legal raw-bank attachment face before consuming the
        # remaining options on one face.  This is deterministic candidate
        # coverage, not a geometry preference or a hard constraint.
        raw_options = _interleave_raw_bank_options(primary, raw_options, raw_required_sides)
        for raw in raw_options:
            if stats.visited_nodes >= context.node_budget:
                stats.node_budget_exhausted = True
                stats.skeleton_search_truncated = True
                return
            stats.current_work_item = {
                "topology": context.structural_topology,
                "envelope_family": plan.envelope.family,
                "band_family": plan.layout_family,
                "sorting_root_mm": list(sorting.bounds_mm),
                "raw_side": raw_side,
                "finished_side": finished_side,
                "offset_direction": offset_direction,
                "branch": "RAW",
            }
            stats.visited_nodes += 1
            stats.construction_node_count += 1
            quantum = _quantum_checkpoint(stats)
            if quantum is not None:
                yield quantum
            for descendant in (
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
            ):
                placed.pop(descendant, None)
            placed["raw_fruit_buffer"] = raw
            secondary_options = _constructive_edge_options(
                context,
                "secondary_precooling_room",
                placed,
                "sorting_packaging_room",
                required_side=finished_side,
                stats=stats,
            )
            offset_shifts: dict[tuple[int, int, int, int], int] = {}
            if context.structural_topology == OFFSET_LINEAR_BAND:
                if offset_direction not in {"POSITIVE", "NEGATIVE"}:
                    _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                    continue
                secondary_options_tuple, offset_shifts = _offset_transition_options(
                    context,
                    placed,
                    sorting,
                    secondary_options,
                    offset_direction,
                    finished_side,
                    stats,
                )
                secondary_options = secondary_options_tuple
                if not secondary_options:
                    _record_rejection(stats, "OFFSET_TRANSITION_UNAVAILABLE")
            for secondary in secondary_options:
                if stats.visited_nodes >= context.node_budget:
                    stats.node_budget_exhausted = True
                    stats.skeleton_search_truncated = True
                    return
                stats.current_work_item = {
                    "topology": context.structural_topology,
                    "envelope_family": plan.envelope.family,
                    "band_family": plan.layout_family,
                    "sorting_root_mm": list(sorting.bounds_mm),
                    "raw_side": raw_side,
                    "finished_side": finished_side,
                    "offset_direction": offset_direction,
                    "branch": "SECONDARY",
                }
                stats.visited_nodes += 1
                stats.construction_node_count += 1
                quantum = _quantum_checkpoint(stats)
                if quantum is not None:
                    yield quantum
                for descendant in ("coating_room", "finished_goods_room", "shipping_channel"):
                    placed.pop(descendant, None)
                placed["secondary_precooling_room"] = secondary
                coating_options = _constructive_edge_options(
                    context,
                    "coating_room",
                    placed,
                    "secondary_precooling_room",
                    bridge_code="sorting_packaging_room",
                    stats=stats,
                )
                for coating in coating_options:
                    if stats.visited_nodes >= context.node_budget:
                        stats.node_budget_exhausted = True
                        stats.skeleton_search_truncated = True
                        return
                    stats.current_work_item = {
                        "topology": context.structural_topology,
                        "envelope_family": plan.envelope.family,
                        "band_family": plan.layout_family,
                        "sorting_root_mm": list(sorting.bounds_mm),
                        "raw_side": raw_side,
                        "finished_side": finished_side,
                        "offset_direction": offset_direction,
                        "branch": "COATING",
                    }
                    stats.visited_nodes += 1
                    stats.construction_node_count += 1
                    quantum = _quantum_checkpoint(stats)
                    if quantum is not None:
                        yield quantum
                    placed.pop("finished_goods_room", None)
                    placed.pop("shipping_channel", None)
                    placed["coating_room"] = coating
                    finished_options = _constructive_edge_options(
                        context,
                        "finished_goods_room",
                        placed,
                        "coating_room",
                        anchor_reference_codes=(
                            ("secondary_precooling_room",)
                            if context.structural_topology == OFFSET_LINEAR_BAND
                            else ()
                        ),
                        stats=stats,
                    )
                    finished_options = _finished_options_by_shipping_approach(
                        context,
                        placed,
                        finished_options,
                    )
                    for finished in finished_options:
                        if stats.visited_nodes >= context.node_budget:
                            stats.node_budget_exhausted = True
                            stats.skeleton_search_truncated = True
                            return
                        stats.current_work_item = {
                            "topology": context.structural_topology,
                            "envelope_family": plan.envelope.family,
                            "band_family": plan.layout_family,
                            "sorting_root_mm": list(sorting.bounds_mm),
                            "raw_side": raw_side,
                            "finished_side": finished_side,
                            "offset_direction": offset_direction,
                            "branch": "FINISHED",
                        }
                        stats.visited_nodes += 1
                        stats.construction_node_count += 1
                        quantum = _quantum_checkpoint(stats)
                        if quantum is not None:
                            yield quantum
                        placed.pop("shipping_channel", None)
                        placed["finished_goods_room"] = finished
                        shipping_options = _constructive_edge_options(
                            context,
                            "shipping_channel",
                            placed,
                            "finished_goods_room",
                            prefer_truck_entrance=True,
                            stats=stats,
                        )
                        shipping_options = _shipping_options_by_loading_face_approach(
                            context, shipping_options
                        )
                        if not shipping_options:
                            _record_rejection(stats, "SHIPPING_INTERFACE_FAIL")
                        for shipping in shipping_options:
                            if stats.visited_nodes >= context.node_budget:
                                stats.node_budget_exhausted = True
                                stats.skeleton_search_truncated = True
                                return
                            stats.current_work_item = {
                                "topology": context.structural_topology,
                                "envelope_family": plan.envelope.family,
                                "band_family": plan.layout_family,
                                "sorting_root_mm": list(sorting.bounds_mm),
                                "raw_side": raw_side,
                                "finished_side": finished_side,
                                "offset_direction": offset_direction,
                                "branch": "SHIPPING",
                            }
                            stats.visited_nodes += 1
                            stats.construction_node_count += 1
                            quantum = _quantum_checkpoint(stats)
                            if quantum is not None:
                                yield quantum
                            placed["shipping_channel"] = shipping
                            if set(placed) != set(MAIN_PROCESS_ZONE_CODES):
                                _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                            elif not _main_group_order_monotonic(
                                placed, context.structural_skeleton
                            ):
                                _record_rejection(stats, "GROUP_ORDER_FAIL")
                            else:
                                try:
                                    classification = classify_main_process_topology_v1(placed)
                                    if classification.canonical_owner is None:
                                        _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                                        if stats.topology_classification_failures is None:
                                            stats.topology_classification_failures = []
                                        stats.topology_classification_failures.append(
                                            {
                                                "topology": context.structural_topology,
                                                "canonical_owner": None,
                                                "matched_topologies": list(
                                                    classification.matched_topologies
                                                ),
                                                "process_axis": classification.process_axis,
                                                "expected_process_axis": (
                                                    context.structural_skeleton.ordering_axis
                                                ),
                                                "zone_bounds_mm": {
                                                    code: list(_bounds(rectangle))
                                                    for code, rectangle in sorted(placed.items())
                                                },
                                            }
                                        )
                                        continue
                                    offset_shift = offset_shifts.get(_bounds(secondary))
                                    discovery_seed = MainProcessSkeletonCandidateV1.create(
                                        family=context.structural_composition_family,
                                        rectangles=placed,
                                        topology=context.structural_topology,
                                        generation_pattern=(
                                            f"{context.structural_topology}:"
                                            f"{plan.layout_family}:"
                                            f"RAW_{raw_side}:"
                                            f"RAW_BANK_{_adjacent_side(primary, raw)}:"
                                            f"FINISHED_{finished_side}:"
                                            f"ROOT_{sorting.x}_{sorting.y}_"
                                            "CONSTRUCTIVE_PROCESS_CHAIN"
                                        ),
                                        hard_geometry_predicates_passed=(
                                            "SITE_CONTAINMENT",
                                            "NO_BUILD_CLEAR",
                                            "NON_OVERLAP",
                                            "MUST_ADJACENCY",
                                            "GROUP_ORDER",
                                            "TOPOLOGY_RULE",
                                        ),
                                        construction_policy=(
                                            f"{context.structural_topology}_{plan.layout_family}_V1"
                                        ),
                                        topology_divergence_stage="ENVELOPE_GRID_BAND_FORMATION",
                                        offset_transition_stage=(
                                            "CORE_TO_FINISHED"
                                            if context.structural_topology == OFFSET_LINEAR_BAND
                                            else None
                                        ),
                                        offset_direction=offset_direction,
                                        offset_cross_axis_shift_mm=offset_shift,
                                        discovery_topology=context.structural_topology,
                                        discovery_family=context.structural_composition_family,
                                        building_layout_family=plan.layout_family,
                                        building_envelope_family=plan.envelope.family,
                                        planned_envelope_bounds_mm=getattr(
                                            plan.envelope, "bounds_mm", None
                                        ),
                                    )
                                    seed = canonicalize_main_process_skeleton_for_evaluation(
                                        discovery_seed,
                                        classification,
                                        site_geometry=context.site_body,
                                    )
                                    geometry_hash = seed.main_process_skeleton_hash
                                    if not _topology_geometry_valid(
                                        placed,
                                        seed.topology,
                                        seed.dominant_axis,
                                    ):
                                        _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                                        if stats.topology_classification_failures is None:
                                            stats.topology_classification_failures = []
                                        stats.topology_classification_failures.append(
                                            {
                                                "discovery_topology": context.structural_topology,
                                                "canonical_owner": seed.canonical_topology_owner,
                                                "matched_topologies": list(
                                                    classification.matched_topologies
                                                ),
                                                "process_axis": classification.process_axis,
                                                "expected_process_axis": seed.dominant_axis,
                                                "zone_bounds_mm": {
                                                    code: list(_bounds(rectangle))
                                                    for code, rectangle in sorted(placed.items())
                                                },
                                            }
                                        )
                                        continue
                                    if not _constructive_main_skeleton_tail_admission(
                                        context, stats, seed
                                    ):
                                        continue
                                    registry = context.global_main_process_geometry_registry
                                    existing = (
                                        registry.get(geometry_hash)
                                        if registry is not None
                                        else None
                                    )
                                    first_discovery_topology = (
                                        str(existing["first_discovery_topology"])
                                        if existing is not None
                                        else None
                                    )
                                    cached_preflight_status = (
                                        existing.get("packaging_preflight_status")
                                        if existing is not None
                                        else None
                                    )
                                    if cached_preflight_status == "NO_LEGAL_SLOT":
                                        assert existing is not None
                                        duplicate_preflight_row = {
                                            "event": "DUPLICATE_PRETAIL_REJECTED_GEOMETRY",
                                            "skeleton_hash": geometry_hash,
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "packaging_preflight_status": (cached_preflight_status),
                                            "packaging_slot_exists": False,
                                            "tail_admissible": False,
                                            "tail_search_started": False,
                                            "preflight_reexecuted": False,
                                        }
                                        if stats.tail_slot_preflight_rows is None:
                                            stats.tail_slot_preflight_rows = []
                                        stats.tail_slot_preflight_rows.append(
                                            duplicate_preflight_row
                                        )
                                        if (
                                            context.global_cross_topology_duplicate_trace
                                            is not None
                                            and existing.get("first_discovery_topology")
                                            != context.structural_topology
                                        ):
                                            stats.cross_topology_duplicate_count += 1
                                            context.global_cross_topology_duplicate_trace.append(
                                                duplicate_preflight_row
                                            )
                                        continue

                                    if cached_preflight_status is None:
                                        preflight_result = _packaging_tail_slot_preflight(
                                            context, seed
                                        )
                                        proof_mode = str(preflight_result["proof_mode"])
                                        slot_exists = preflight_result["legal_slot_exists"]
                                        preflight_status = (
                                            "NO_LEGAL_SLOT"
                                            if slot_exists is False
                                            and proof_mode == EXACT_ORTHOGONAL_EVENT_ENUMERATION
                                            else "LEGAL_SLOT_EXISTS"
                                            if slot_exists is True
                                            else "UNAVAILABLE"
                                        )
                                        tail_search_admitted = preflight_status != "NO_LEGAL_SLOT"
                                        preflight_row = {
                                            "event": "TAIL_SLOT_PREFLIGHT",
                                            "stage": "TAIL_SLOT_PREFLIGHT",
                                            "skeleton_hash": geometry_hash,
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "canonical_family": seed.family.to_dict(),
                                            "packaging_preflight_status": preflight_status,
                                            "packaging_slot_exists": slot_exists,
                                            "tail_admissible": (
                                                False
                                                if preflight_status == "NO_LEGAL_SLOT"
                                                else None
                                                if preflight_status == "UNAVAILABLE"
                                                else True
                                            ),
                                            "tail_search_started": tail_search_admitted,
                                            "preflight_reexecuted": True,
                                            "preflight": preflight_result,
                                        }
                                        if stats.tail_slot_preflight_rows is None:
                                            stats.tail_slot_preflight_rows = []
                                        stats.tail_slot_preflight_rows.append(preflight_row)
                                        if registry is not None:
                                            registry_row = existing if existing is not None else {}
                                            registry_row.update(
                                                {
                                                    "skeleton_hash": geometry_hash,
                                                    "first_discovery_topology": (
                                                        first_discovery_topology
                                                        or context.structural_topology
                                                    ),
                                                    "canonical_topology_owner": (
                                                        seed.canonical_topology_owner
                                                    ),
                                                    "canonical_family": seed.family.to_dict(),
                                                    "packaging_preflight_status": preflight_status,
                                                    "packaging_slot_exists": slot_exists,
                                                    "tail_admissible": preflight_row[
                                                        "tail_admissible"
                                                    ],
                                                    "tail_search_started": False,
                                                    "tail_search_discovery_topology": None,
                                                    "p2d_reached": False,
                                                    "p2d_candidate_count": 0,
                                                    "p2d_full_pass_count": 0,
                                                }
                                            )
                                            registry[geometry_hash] = registry_row
                                        if preflight_status == "NO_LEGAL_SLOT":
                                            _record_rejection(
                                                stats,
                                                "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT",
                                            )
                                            if stats.skeleton_tail_lifecycle is None:
                                                stats.skeleton_tail_lifecycle = []
                                            stats.skeleton_tail_lifecycle.append(
                                                {
                                                    "topology": seed.topology,
                                                    "skeleton_hash": geometry_hash,
                                                    "discovery_topology": (
                                                        context.structural_topology
                                                    ),
                                                    "canonical_topology_owner": (
                                                        seed.canonical_topology_owner
                                                    ),
                                                    "canonical_family": seed.family.to_dict(),
                                                    "packaging_preflight_executed": True,
                                                    "packaging_slot_exists": False,
                                                    "tail_admissible": False,
                                                    "tail_search_started": False,
                                                    "tail_nodes": 0,
                                                    "tail_node_limit": 0,
                                                    "complete_candidate_count": 0,
                                                    "p2d_reached": False,
                                                    "first_failure_stage": "TAIL_SLOT_PREFLIGHT",
                                                    "first_failure_reason": (
                                                        "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT"
                                                    ),
                                                }
                                            )
                                            continue
                                    else:
                                        assert existing is not None
                                        preflight_status = str(cached_preflight_status)
                                        slot_exists = existing.get("packaging_slot_exists")
                                        preflight_row = {
                                            "event": "CACHED_TAIL_SLOT_PREFLIGHT",
                                            "stage": "TAIL_SLOT_PREFLIGHT",
                                            "skeleton_hash": geometry_hash,
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "packaging_preflight_status": preflight_status,
                                            "packaging_slot_exists": slot_exists,
                                            "tail_admissible": existing.get("tail_admissible"),
                                            "tail_search_started": False,
                                            "preflight_reexecuted": False,
                                        }
                                        if stats.tail_slot_preflight_rows is None:
                                            stats.tail_slot_preflight_rows = []
                                        stats.tail_slot_preflight_rows.append(preflight_row)

                                    cached_truck_preflight = (
                                        existing.get("main_skeleton_truck_preflight")
                                        if existing is not None
                                        else None
                                    )
                                    if isinstance(cached_truck_preflight, Mapping):
                                        truck_preflight_row = {
                                            **dict(cached_truck_preflight),
                                            "event": "CACHED_MAIN_SKELETON_TRUCK_PREFLIGHT",
                                            "discovery_topology": context.structural_topology,
                                            "preflight_reexecuted": False,
                                            "preflight_compute_nodes": int(
                                                cached_truck_preflight.get(
                                                    "preflight_compute_nodes",
                                                    cached_truck_preflight.get("visited_nodes", 0),
                                                )
                                            ),
                                        }
                                    else:
                                        truck_preflight_result = (
                                            _main_skeleton_truck_maneuver_preflight(context, seed)
                                        )
                                        truck_preflight_row = {
                                            **truck_preflight_result,
                                            "event": "MAIN_SKELETON_TRUCK_PREFLIGHT",
                                            "stage": "MAIN_SKELETON_TRUCK_PREFLIGHT",
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "canonical_family": seed.family.to_dict(),
                                            "preflight_reexecuted": True,
                                            "preflight_compute_nodes": int(
                                                truck_preflight_result["visited_nodes"]
                                            ),
                                        }
                                    truck_preflight_row.update(
                                        {
                                            "layout_family": seed.building_layout_family,
                                            "envelope_family": seed.building_envelope_family,
                                            "planned_envelope_bounds_mm": (
                                                list(seed.planned_envelope_bounds_mm)
                                                if seed.planned_envelope_bounds_mm is not None
                                                else None
                                            ),
                                        }
                                    )
                                    if registry is not None:
                                        registry_row = (
                                            existing
                                            if existing is not None
                                            else registry.get(geometry_hash, {})
                                        )
                                        registry_row.update(
                                            {
                                                "skeleton_hash": geometry_hash,
                                                "first_discovery_topology": (
                                                    first_discovery_topology
                                                    or context.structural_topology
                                                ),
                                                "main_skeleton_truck_preflight": dict(
                                                    truck_preflight_row
                                                ),
                                            }
                                        )
                                        registry_row.setdefault("tail_search_started", False)
                                        registry_row.setdefault(
                                            "tail_search_discovery_topology", None
                                        )
                                        registry_row.setdefault("p2d_reached", False)
                                        registry_row.setdefault("p2d_candidate_count", 0)
                                        registry_row.setdefault("p2d_full_pass_count", 0)
                                        registry[geometry_hash] = registry_row
                                    if stats.main_skeleton_truck_preflight_rows is None:
                                        stats.main_skeleton_truck_preflight_rows = []
                                    stats.main_skeleton_truck_preflight_rows.append(
                                        truck_preflight_row
                                    )
                                    if truck_preflight_row["preflight_status"] == "REJECT":
                                        if stats.skeleton_tail_lifecycle is None:
                                            stats.skeleton_tail_lifecycle = []
                                        stats.skeleton_tail_lifecycle.append(
                                            {
                                                "topology": seed.topology,
                                                "skeleton_hash": geometry_hash,
                                                "discovery_topology": context.structural_topology,
                                                "canonical_topology_owner": (
                                                    seed.canonical_topology_owner
                                                ),
                                                "canonical_family": seed.family.to_dict(),
                                                "packaging_preflight_executed": True,
                                                "packaging_preflight_status": preflight_status,
                                                "packaging_slot_exists": slot_exists,
                                                "main_skeleton_truck_preflight_executed": True,
                                                "main_skeleton_truck_preflight_status": "REJECT",
                                                "truck_preflight_failure_codes": list(
                                                    truck_preflight_row.get("failure_codes", [])
                                                ),
                                                "truck_preflight_visited_nodes": int(
                                                    truck_preflight_row.get("visited_nodes", 0)
                                                ),
                                                "truck_preflight_node_budget": int(
                                                    truck_preflight_row.get("node_budget", 0)
                                                ),
                                                "truck_preflight_node_budget_exhausted": (
                                                    truck_preflight_row.get("node_budget_exhausted")
                                                ),
                                                "truck_preflight_search_tree_exhausted": (
                                                    truck_preflight_row.get("search_tree_exhausted")
                                                ),
                                                "tail_search_started": False,
                                                "tail_nodes": 0,
                                                "tail_node_limit": 0,
                                                "complete_candidate_count": 0,
                                                "p2d_reached": False,
                                                "first_failure_stage": (
                                                    "MAIN_SKELETON_TRUCK_PREFLIGHT"
                                                ),
                                                "first_failure_reason": (
                                                    truck_preflight_row.get("failure_reason")
                                                    or "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
                                                ),
                                            }
                                        )
                                        continue

                                    tail_search_discovery_topology = (
                                        str(existing["tail_search_discovery_topology"])
                                        if existing is not None
                                        and existing.get("tail_search_discovery_topology")
                                        is not None
                                        else None
                                    )
                                    ownership_decision = decide_main_process_topology_ownership_v1(
                                        lane_topology=context.structural_topology,
                                        canonical_owner=seed.canonical_topology_owner,
                                        first_discovery_topology=first_discovery_topology,
                                        tail_search_discovery_topology=(
                                            tail_search_discovery_topology
                                        ),
                                        geometry_previously_seen=existing is not None,
                                        tail_search_started=(
                                            existing is not None
                                            and existing.get("tail_search_started") is True
                                        ),
                                    )
                                    truck_preflight_row["tail_search_started"] = (
                                        ownership_decision.start_tail_search
                                    )
                                    if not ownership_decision.start_tail_search:
                                        if ownership_decision.cross_topology_duplicate:
                                            stats.cross_topology_duplicate_count += 1
                                        duplicate_row = {
                                            "event": "EXISTING_GEOMETRY_DUPLICATE_DISCOVERY",
                                            "skeleton_hash": geometry_hash,
                                            "first_discovery_topology": first_discovery_topology,
                                            "duplicate_discovery_topology": (
                                                context.structural_topology
                                            ),
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "tail_search_started_by_topology": (
                                                tail_search_discovery_topology
                                            ),
                                            "cross_topology_duplicate": (
                                                ownership_decision.cross_topology_duplicate
                                            ),
                                            "duplicate_action": ownership_decision.action,
                                            "construction_attempt_index": len(
                                                stats.skeleton_construction_attempts or []
                                            ),
                                        }
                                        if stats.topology_ownership_duplicates is None:
                                            stats.topology_ownership_duplicates = []
                                        stats.topology_ownership_duplicates.append(duplicate_row)
                                        if (
                                            ownership_decision.cross_topology_duplicate
                                            and context.global_cross_topology_duplicate_trace
                                            is not None
                                        ):
                                            context.global_cross_topology_duplicate_trace.append(
                                                duplicate_row
                                            )
                                        continue

                                    if registry is not None:
                                        registry_row = (
                                            existing
                                            if existing is not None
                                            else registry.get(geometry_hash, {})
                                        )
                                        registry_row.update(
                                            {
                                                "skeleton_hash": geometry_hash,
                                                "first_discovery_topology": (
                                                    first_discovery_topology
                                                    or context.structural_topology
                                                ),
                                                "canonical_topology_owner": (
                                                    seed.canonical_topology_owner
                                                ),
                                                "canonical_family": seed.family.to_dict(),
                                                "tail_search_started": True,
                                                "tail_search_discovery_topology": (
                                                    context.structural_topology
                                                ),
                                                "packaging_preflight_status": preflight_status,
                                                "packaging_slot_exists": slot_exists,
                                                "tail_admissible": (
                                                    existing.get("tail_admissible")
                                                    if existing is not None
                                                    else preflight_row.get("tail_admissible")
                                                ),
                                            }
                                        )
                                        truck_preflight = registry_row.get(
                                            "main_skeleton_truck_preflight"
                                        )
                                        if isinstance(truck_preflight, Mapping):
                                            registry_row["main_skeleton_truck_preflight"] = {
                                                **dict(truck_preflight),
                                                "tail_search_started": True,
                                            }
                                        registry_row.setdefault("p2d_reached", False)
                                        registry_row.setdefault("p2d_candidate_count", 0)
                                        registry_row.setdefault("p2d_full_pass_count", 0)
                                        registry[geometry_hash] = registry_row
                                    if stats.geometry_evaluation_admissions is None:
                                        stats.geometry_evaluation_admissions = []
                                    stats.geometry_evaluation_admissions.append(
                                        {
                                            "event": (
                                                "NEW_GEOMETRY_NON_OWNER_DISCOVERY"
                                                if context.structural_topology
                                                != seed.canonical_topology_owner
                                                else "NEW_GEOMETRY_DISCOVERY"
                                            ),
                                            "skeleton_hash": geometry_hash,
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "discovery_lane_matches_canonical_owner": (
                                                context.structural_topology
                                                == seed.canonical_topology_owner
                                            ),
                                            "discovery_family": (
                                                context.structural_composition_family.to_dict()
                                            ),
                                            "canonical_family": seed.family.to_dict(),
                                            "geometry_previously_seen": (
                                                ownership_decision.geometry_previously_seen
                                            ),
                                            "action": ownership_decision.action,
                                            "evaluation_admission": "TAIL_SEARCH_STARTED",
                                        }
                                    )
                                except LayoutAuthorityError:
                                    _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                                else:
                                    # Emit this seed only after every exact geometry,
                                    # packaging-slot, truck, and ownership gate above
                                    # completed successfully. This is the try/except
                                    # success clause; a for-else here can run after an
                                    # invalid branch and reference an unbound `seed`.
                                    emitted_skeletons += 1
                                    yield seed
                        if emitted_skeletons >= skeleton_limit:
                            return


def _construct_main_process_skeletons(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
) -> Iterator[MainProcessSkeletonCandidateV1 | _SearchQuantumYield]:
    """Try distinct band construction policies under the shared node budget."""
    reference_plan = context.structured_building_plan
    if reference_plan is None:
        return
    if stats.constructive_divergence_attempts is None:
        stats.constructive_divergence_attempts = []
    preferred_axis = reference_plan.process_axis
    alternate_axis = "X" if preferred_axis == "Y" else "Y"
    if context.search_phase == GENERAL_FALLBACK_PHASE:
        primary_family = reference_plan.layout_family
        legacy_family_order = {
            LINEAR_3_BAND: (
                LINEAR_3_BAND,
                LONGITUDINAL_PROCESS_SPINE,
                CENTRAL_PROCESS_WITH_SIDE_BANKS,
            ),
            LONGITUDINAL_PROCESS_SPINE: (
                LONGITUDINAL_PROCESS_SPINE,
                LINEAR_3_BAND,
                CENTRAL_PROCESS_WITH_SIDE_BANKS,
            ),
            CENTRAL_PROCESS_WITH_SIDE_BANKS: (
                CENTRAL_PROCESS_WITH_SIDE_BANKS,
                LONGITUDINAL_PROCESS_SPINE,
                LINEAR_3_BAND,
            ),
        }.get(primary_family, (primary_family,))
        variant_pairs = tuple((family, preferred_axis) for family in legacy_family_order)
    else:
        variant_pairs = tuple(
            (family, process_axis)
            for family in BASE_LAYOUT_FAMILIES
            for process_axis in (preferred_axis, alternate_axis)
        )
    searches: list[
        tuple[tuple[str, str], Iterator[MainProcessSkeletonCandidateV1 | _SearchQuantumYield]]
    ] = []
    for layout_family, process_axis in variant_pairs:
        plan: StructuredBuildingSkeletonV1 | None = None
        envelope_failures: list[str] = []
        if context.search_phase == GENERAL_FALLBACK_PHASE:
            plan = construct_legacy_compatibility_search_plan_v1(
                boundary=context.boundary,
                obstacles=context.obstacles,
                authorities=context.authorities,
                process_axis=process_axis,
                process_direction=(
                    context.structural_composition_family.dominant_direction
                    if context.structural_composition_family.dominant_direction
                    in {"POSITIVE", "NEGATIVE"}
                    else "POSITIVE"
                ),
                layout_family=layout_family,
                main_entrance=context.main_entrance,
            )
        else:
            # Axis is an explicit candidate dimension, not an exclusive
            # selector outcome. Each family constructs its own envelope,
            # grid, and bands on both orthogonal orientations.
            for envelope_family in (RECTANGLE, SIMPLE_L):
                try:
                    plan = construct_structured_building_plan_v1(
                        boundary=context.boundary,
                        obstacles=context.obstacles,
                        authorities=context.authorities,
                        process_axis=process_axis,
                        layout_family=layout_family,
                        envelope_family=envelope_family,
                        main_entrance=context.main_entrance,
                    )
                except LayoutAuthorityError as error:
                    envelope_failures.append(error.code)
                    continue
                break
        stats.constructive_divergence_attempts.append(
            {
                "topology": context.structural_topology,
                "layout_family": layout_family,
                "process_axis": process_axis,
                "attempted": True,
                "construction_policy": f"{layout_family}_{process_axis}_V1",
                "divergence_stage": "ENVELOPE_GRID_BAND_FORMATION",
                "result": "PLAN_READY" if plan is not None else "NO_SITE_FEASIBLE_ENVELOPE",
                "envelope_failures": envelope_failures,
                "selected_envelope_family": plan.envelope.family if plan is not None else None,
                "envelope_bounds_mm": (list(plan.envelope.bounds_mm) if plan is not None else None),
                "envelope_components_mm": (
                    [list(row) for row in plan.envelope.components_mm] if plan is not None else []
                ),
                "primary_x_axes_mm": (
                    list(plan.primary_grid.x_axes_mm) if plan is not None else []
                ),
                "primary_y_axes_mm": (
                    list(plan.primary_grid.y_axes_mm) if plan is not None else []
                ),
                "local_event_x_axis_count": (
                    len(plan.primary_grid.event_x_mm) if plan is not None else 0
                ),
                "local_event_y_axis_count": (
                    len(plan.primary_grid.event_y_mm) if plan is not None else 0
                ),
                "functional_band_bounds_mm": (
                    {band.band_code: list(band.bounds_mm) for band in plan.bands}
                    if plan is not None
                    else {}
                ),
                "support_band_is_full_envelope": (
                    plan.band_for_zone("packaging_material_storage").bounds_mm
                    == plan.envelope.bounds_mm
                    if plan is not None
                    else None
                ),
                "personnel_band_is_full_envelope": (
                    plan.band_for_zone("office").bounds_mm == plan.envelope.bounds_mm
                    if plan is not None
                    else None
                ),
            }
        )
        if plan is None:
            continue
        plan_context = replace(
            context,
            structured_building_plan=plan,
            structural_skeleton=replace(context.structural_skeleton, ordering_axis=process_axis),
        )
        searches.append(
            (
                (layout_family, process_axis),
                iter(_construct_main_process_skeletons_for_plan(plan_context, stats)),
            )
        )

    # Completion coverage is selector-global, not a per-lane quotient.  A
    # lane's node allowance already bounds its work; dividing that allowance
    # by a nominal per-skeleton estimate here used to stop at two seeds in a
    # 40-node lane and prevented the remaining band policies from running.
    skeleton_limit = CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT
    eligible_variants = tuple(variant for variant, _search in searches)

    def family_coverage_count(variant: tuple[str, str]) -> int:
        family, axis = variant
        return sum(
            1
            for skeleton in (stats.constructed_main_skeletons or {}).values()
            if skeleton.building_layout_family == family and skeleton.dominant_axis == axis
        )

    while searches:
        if stats.node_budget_exhausted:
            return
        coverage_complete = all(family_coverage_count(variant) > 0 for variant in eligible_variants)
        if len(stats.constructed_main_skeletons or {}) >= skeleton_limit and coverage_complete:
            stats.normal_stop_reason = "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT"
            return
        selected_index = min(
            range(len(searches)),
            key=lambda index: (
                family_coverage_count(searches[index][0]),
                index,
            ),
        )
        layout_variant, search = searches.pop(selected_index)
        try:
            item = next(search)
        except StopIteration:
            continue
        yield item
        if stats.node_budget_exhausted:
            return
        coverage_complete = all(family_coverage_count(variant) > 0 for variant in eligible_variants)
        if len(stats.constructed_main_skeletons or {}) >= skeleton_limit and coverage_complete:
            stats.normal_stop_reason = "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT"
            return
        searches.append((layout_variant, search))


def _construct_main_process_skeletons_for_plan(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
) -> Iterator[MainProcessSkeletonCandidateV1 | _SearchQuantumYield]:
    """Build full seven-zone candidates before any support/personnel search."""
    plan = context.structured_building_plan
    if plan is None:
        return
    # This is a selector-wide coverage ceiling.  Per-lane/context node budgets
    # are enforced at each exact search node below; using them again to derive
    # a lifetime completion cap starves later envelope/grid/band policies.
    skeleton_completion_limit = CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT
    if stats.constructed_main_skeletons is None:
        stats.constructed_main_skeletons = {}
    if stats.skeleton_generation_patterns is None:
        stats.skeleton_generation_patterns = {}
    if stats.skeleton_construction_attempts is None:
        stats.skeleton_construction_attempts = []
    roots = _constructive_sorting_roots(context, stats)
    emitted = sum(
        1
        for skeleton in stats.constructed_main_skeletons.values()
        if getattr(skeleton, "building_layout_family", None) == plan.layout_family
    )
    previous_seed_node = 0
    if stats.constructive_divergence_attempts is None:
        stats.constructive_divergence_attempts = []
    directions: tuple[str | None, ...] = (
        ("POSITIVE", "NEGATIVE") if context.structural_topology == OFFSET_LINEAR_BAND else (None,)
    )
    stats.constructive_divergence_attempts.append(
        {
            "topology": context.structural_topology,
            "attempted": True,
            "construction_policy": f"{context.structural_topology}_V1",
            "divergence_stage": (
                "CORE_TO_FINISHED"
                if context.structural_topology == OFFSET_LINEAR_BAND
                else "RAW_FINISHED_FACE_PAIR"
                if context.structural_topology == CENTRAL_PROCESS_HUB
                else "ROOT_OR_GROUP_BAND_FORMATION"
            ),
            "offset_directions": [value for value in directions if value is not None],
        }
    )
    face_pairs = _family_attachment_sides(
        context.structural_composition_family, context.structural_topology
    )
    attempts = tuple(
        (raw_side, finished_side, offset_direction)
        for raw_side, finished_side in face_pairs
        for offset_direction in directions
    )

    def attachment_attempt_key(
        item: tuple[int, tuple[str, str, str | None]],
    ) -> tuple[int, int, int, int, int, int, int]:
        original_index, (raw_side, finished_side, _offset_direction) = item
        best_root_key = min(
            (
                _sorting_root_attachment_pair_key(context, root, raw_side, finished_side)
                for root in roots
            ),
            default=(10**18, 10**18, 10**18, 10**18, 10**18, 10**18),
        )
        return (*best_root_key, original_index)

    ordered_attempts = sorted(enumerate(attempts), key=attachment_attempt_key)
    for face_pair_index, (raw_side, finished_side, offset_direction) in ordered_attempts:
        if emitted >= skeleton_completion_limit:
            stats.normal_stop_reason = "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT"
            return
        face_pair_roots = (
            roots
            if context.search_phase == GENERAL_FALLBACK_PHASE
            else _sorting_roots_for_attachment_pair(context, roots, raw_side, finished_side)
        )
        for sorting in face_pair_roots:
            if stats.visited_nodes >= context.node_budget:
                stats.node_budget_exhausted = True
                stats.skeleton_search_truncated = True
                return
            stats.current_work_item = {
                "topology": context.structural_topology,
                "envelope_family": plan.envelope.family,
                "band_family": plan.layout_family,
                "family": context.structural_composition_family.to_dict(),
                "axis": context.structural_composition_family.dominant_axis,
                "direction": context.structural_composition_family.dominant_direction,
                "sorting_root_mm": list(sorting.bounds_mm),
                "raw_side": raw_side,
                "finished_side": finished_side,
                "offset_direction": offset_direction,
                "branch": "SORTING_ROOT",
                "face_pair_index": face_pair_index,
            }
            stats.visited_nodes += 1
            stats.construction_node_count += 1
            quantum = _quantum_checkpoint(stats)
            if quantum is not None:
                yield quantum
            face_pair_node_quantum = CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET
            sorting_root_node_quantum = CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET
            emitted_for_face = 0
            rejection_counts_before = dict(stats.rejection_reason_counts or {})
            attempt_skeleton_hashes: list[str] = []
            attempt_node_start = stats.visited_nodes
            for seed in _construct_face_skeletons(
                context,
                stats,
                sorting,
                raw_side,
                finished_side,
                context.node_budget,
                skeleton_limit=max(1, skeleton_completion_limit - emitted),
                offset_direction=offset_direction,
            ):
                if isinstance(seed, _SearchQuantumYield):
                    yield seed
                    continue
                if seed.main_process_skeleton_hash in stats.constructed_main_skeletons:
                    _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                    continue
                stats.constructed_main_skeletons[seed.main_process_skeleton_hash] = seed
                if stats.construction_nodes_by_skeleton is None:
                    stats.construction_nodes_by_skeleton = {}
                stats.construction_nodes_by_skeleton[seed.main_process_skeleton_hash] = max(
                    0, stats.visited_nodes - previous_seed_node
                )
                previous_seed_node = stats.visited_nodes
                attempt_skeleton_hashes.append(seed.main_process_skeleton_hash)
                stats.skeleton_generation_patterns[seed.generation_pattern] = (
                    stats.skeleton_generation_patterns.get(seed.generation_pattern, 0) + 1
                )
                emitted += 1
                emitted_for_face += 1
                yield seed
                if emitted >= skeleton_completion_limit:
                    stats.normal_stop_reason = "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT"
                    stats.skeleton_construction_attempts.append(
                        {
                            "topology": context.structural_topology,
                            "envelope_family": plan.envelope.family,
                            "band_family": plan.layout_family,
                            "offset_direction": offset_direction,
                            "construction_attempt_index": len(stats.skeleton_construction_attempts),
                            "raw_side": raw_side,
                            "finished_side": finished_side,
                            "sorting_root_mm": list(sorting.bounds_mm),
                            "result": "SKELETON_CONSTRUCTED",
                            "skeleton_hashes": attempt_skeleton_hashes,
                            "face_pair_node_quantum": face_pair_node_quantum,
                            "sorting_root_node_quantum": sorting_root_node_quantum,
                            "search_truncated": False,
                            "visited_node_delta": stats.visited_nodes - attempt_node_start,
                        }
                    )
                    return
            if stats.node_budget_exhausted:
                return
            rejection_counts_after = stats.rejection_reason_counts or {}
            stats.skeleton_construction_attempts.append(
                {
                    "topology": context.structural_topology,
                    "envelope_family": plan.envelope.family,
                    "band_family": plan.layout_family,
                    "offset_direction": offset_direction,
                    "construction_attempt_index": len(stats.skeleton_construction_attempts),
                    "raw_side": raw_side,
                    "finished_side": finished_side,
                    "sorting_root_mm": list(sorting.bounds_mm),
                    "result": "TRUNCATED"
                    if stats.node_budget_exhausted
                    else "SKELETON_CONSTRUCTED"
                    if attempt_skeleton_hashes
                    else "REJECTED",
                    "face_pair_node_quantum": face_pair_node_quantum,
                    "sorting_root_node_quantum": sorting_root_node_quantum,
                    "search_truncated": stats.node_budget_exhausted,
                    "skeleton_hashes": attempt_skeleton_hashes,
                    "rejection_reason_counts": {
                        reason: rejection_counts_after.get(reason, 0) - count
                        for reason, count in sorted(rejection_counts_before.items())
                        if rejection_counts_after.get(reason, 0) > count
                    }
                    | {
                        reason: count
                        for reason, count in sorted(rejection_counts_after.items())
                        if reason not in rejection_counts_before and count > 0
                    },
                    "visited_node_delta": stats.visited_nodes - attempt_node_start,
                }
            )


def _canonical_tail_search_context(
    discovery_context: _PlacementSearchContext,
    skeleton: MainProcessSkeletonCandidateV1,
) -> _PlacementSearchContext:
    """Bind tail search to the canonical geometry family without moving it."""
    canonical_topology = skeleton.canonical_topology_owner
    canonical_family = skeleton.family
    if canonical_topology != skeleton.topology or canonical_family.family not in {
        CENTRAL_PROCESS_HUB,
        LINEAR_PROCESS_BAND,
    }:
        raise _error("CANONICAL_SKELETON_IDENTITY_INCONSISTENT")
    structural_skeleton = next(
        (
            row
            for row in structural_skeleton_candidates(
                discovery_context.site_body,
                tuple(discovery_context.authorities),
                zone_authorities=discovery_context.authorities,
                family_candidates=(canonical_family,),
            )
            if row.family.to_dict() == canonical_family.to_dict()
        ),
        None,
    )
    if structural_skeleton is None:
        raise _error("CANONICAL_STRUCTURAL_SKELETON_UNAVAILABLE")
    placement_zone_order = (
        LINEAR_STRUCTURED_PLACEMENT_ZONE_ORDER
        if canonical_family.family == LINEAR_PROCESS_BAND
        else STRUCTURED_PLACEMENT_ZONE_ORDER
    )
    if discovery_context.search_phase == GENERAL_FALLBACK_PHASE:
        compatibility_plan = discovery_context.structured_building_plan
        if compatibility_plan is None:
            raise _error("GENERAL_FALLBACK_SEARCH_PLAN_UNAVAILABLE")
        canonical_plan = replace(
            compatibility_plan,
            layout_family=structured_layout_family_for_topology(canonical_topology),
            process_axis=structural_skeleton.ordering_axis,
            process_direction=canonical_family.dominant_direction,
        )
    else:
        canonical_plan = construct_structured_building_plan_v1(
            boundary=discovery_context.boundary,
            obstacles=discovery_context.obstacles,
            authorities=discovery_context.authorities,
            process_axis=structural_skeleton.ordering_axis,
            layout_family=skeleton.building_layout_family or LINEAR_3_BAND,
            envelope_family=skeleton.building_envelope_family or RECTANGLE,
            main_entrance=discovery_context.main_entrance,
        )
    return replace(
        discovery_context,
        structural_composition_family=canonical_family,
        structural_skeleton=structural_skeleton,
        structured_building_plan=canonical_plan,
        structural_topology=canonical_topology,
        placement_zone_order=placement_zone_order,
    )


def _walk_complete_candidate_payloads(
    context: _PlacementSearchContext, stats: _PlacementSearchStats
) -> Iterator[dict[str, Any] | _SearchQuantumYield]:
    """Yield every complete P2C candidate until the node budget is exhausted."""
    if context.search_phase == STRUCTURED_PHASE and context.direct_synthesis_enabled:
        yield from _direct_structured_candidates(context, stats)
        return
    if context.search_phase == STRUCTURED_PHASE and context.structured_building_plan is None:
        return
    placed: dict[str, PlacedRectangleV1] = {}
    # Keep the separately accounted R2 fallback phase on the R1 structured
    # candidate mechanics. The phase label remains GENERAL_FALLBACK_PHASE;
    # only candidate anchoring/admission follows the compatibility path.
    candidate_policy_phase = (
        STRUCTURED_PHASE if context.search_phase == GENERAL_FALLBACK_PHASE else context.search_phase
    )
    truck_entrance = _truck_segment(context.site_body)
    if stats.structured_main_skeleton_completions is None:
        stats.structured_main_skeleton_completions = {}
    if stats.structured_core_root_completions is None:
        stats.structured_core_root_completions = {}
    main_skeleton_completions = stats.structured_main_skeleton_completions
    core_root_completions = stats.structured_core_root_completions
    assert main_skeleton_completions is not None
    assert core_root_completions is not None

    def main_skeleton_signature() -> str:
        return canonical_json(
            [
                {
                    "zone_code": code,
                    "x": str(placed[code].x),
                    "y": str(placed[code].y),
                    "width_m": str(placed[code].width_m),
                    "depth_m": str(placed[code].depth_m),
                    "rotation_deg": placed[code].rotation_deg,
                }
                for code in MAIN_PROCESS_SKELETON_ZONE_CODES
                if code in placed
            ]
        )

    def core_root_signature() -> str | None:
        sorting = placed.get("sorting_packaging_room")
        if sorting is None:
            return None
        return canonical_json(
            {
                "x": str(sorting.x),
                "y": str(sorting.y),
                "width_m": str(sorting.width_m),
                "depth_m": str(sorting.depth_m),
                "rotation_deg": sorting.rotation_deg,
            }
        )

    def visit(
        index: int,
        structurally_generated: bool,
        main_process_skeleton: MainProcessSkeletonCandidateV1 | None = None,
    ) -> Iterator[dict[str, Any] | _SearchQuantumYield]:
        root_signature = core_root_signature()
        if (
            candidate_policy_phase == STRUCTURED_PHASE
            and index >= len(MAIN_PROCESS_ZONE_CODES)
            and len(placed) >= len(MAIN_PROCESS_ZONE_CODES)
            and main_skeleton_completions.get(main_skeleton_signature(), 0)
            >= STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON
        ):
            return
        if (
            candidate_policy_phase == STRUCTURED_PHASE
            and index > 0
            and root_signature is not None
            and core_root_completions.get(root_signature, 0) >= STRUCTURED_COMPLETIONS_PER_CORE_ROOT
        ):
            return
        if stats.visited_nodes >= context.node_budget:
            stats.node_budget_exhausted = True
            return
        stats.visited_nodes += 1
        stats.current_work_item = {
            "topology": context.structural_topology,
            "band_family": (
                context.structured_building_plan.layout_family
                if context.structured_building_plan is not None
                else None
            ),
            "envelope_family": (
                context.structured_building_plan.envelope.family
                if context.structured_building_plan is not None
                else None
            ),
            "skeleton_hash": (
                main_process_skeleton.main_process_skeleton_hash
                if main_process_skeleton is not None
                else None
            ),
            "zone_code": context.placement_zone_order[index]
            if index < len(context.placement_zone_order)
            else None,
            "branch": "TAIL" if main_process_skeleton is not None else "GENERAL",
        }
        if main_process_skeleton is not None:
            if stats.tail_nodes_by_skeleton is None:
                stats.tail_nodes_by_skeleton = {}
            skeleton_hash = main_process_skeleton.main_process_skeleton_hash
            stats.tail_nodes_by_skeleton[skeleton_hash] = (
                stats.tail_nodes_by_skeleton.get(skeleton_hash, 0) + 1
            )
        quantum = _quantum_checkpoint(stats)
        if quantum is not None:
            yield quantum
        # Constructed main-process skeletons have already passed their
        # discovery-topology construction predicates and exact canonical
        # classification. Reapplying this lane-oriented proxy after family
        # rebinding would turn canonical identity into a second admission gate.
        if (
            candidate_policy_phase == STRUCTURED_PHASE
            and main_process_skeleton is None
            and index == len(MAIN_PROCESS_ZONE_CODES)
            and not _main_group_order_monotonic(placed, context.structural_skeleton)
        ):
            return
        if index == len(context.placement_zone_order):
            _validate_graph_completeness(context.graph, placed)
            stats.complete_candidates += 1
            if candidate_policy_phase == STRUCTURED_PHASE:
                signature = main_skeleton_signature()
                main_skeleton_completions[signature] = (
                    main_skeleton_completions.get(signature, 0) + 1
                )
                root_signature = core_root_signature()
                if root_signature is not None:
                    core_root_completions[root_signature] = (
                        core_root_completions.get(root_signature, 0) + 1
                    )
            payload = _candidate_payload(
                placed,
                context.authorities,
                context.graph,
                context.site_body,
                context.source_zone_plan_hash,
                context.source_p1_handoff_hash,
                context.source_site_geometry_hash,
                context.objective_profile_hash,
                context.access_requirements,
                context.spatial_relationships,
                _search_provenance(
                    context,
                    stats,
                    search_tree_exhausted=False,
                    objective_optimal_within_search_family=False,
                ),
            )
            payload["_structural_generation_flag"] = structurally_generated
            payload["_structural_composition_family"] = (
                context.structural_composition_family.to_dict()
            )
            payload["_structural_skeleton"] = context.structural_skeleton.to_dict()
            payload["_search_phase"] = context.search_phase
            if candidate_policy_phase == STRUCTURED_PHASE:
                assert context.structured_building_plan is not None
                payload["_structured_building_plan"] = (
                    context.structured_building_plan.with_placements(placed).to_dict()
                )
            if main_process_skeleton is not None:
                payload["_main_process_skeleton"] = main_process_skeleton.to_evaluation_dict()
            yield payload
            return
        code = context.placement_zone_order[index]
        option_arguments = (
            code,
            context.authorities[code],
            placed,
            context.boundary,
            context.boundary_bounds,
            context.obstacles,
            context.graph,
            context.structural_composition_family,
            context.main_entrance,
        )
        if context.search_phase == LEGACY_COMPAT_PHASE:
            options = _candidate_options(*option_arguments)
        else:
            options = _candidate_options(
                *option_arguments,
                search_phase=candidate_policy_phase,
                structural_skeleton=context.structural_skeleton,
                structured_building_plan=context.structured_building_plan,
                zone_authorities=context.authorities,
                truck_entrance=truck_entrance,
            )
        if main_process_skeleton is not None and index >= len(MAIN_PROCESS_ZONE_CODES):
            if stats.tail_zone_search_facts is None:
                stats.tail_zone_search_facts = {}
            skeleton_facts = stats.tail_zone_search_facts.setdefault(
                main_process_skeleton.main_process_skeleton_hash, {}
            )
            zone_facts = skeleton_facts.setdefault(
                code,
                {
                    "branch_visits": 0,
                    "candidate_options": 0,
                    "skeleton_region_options": 0,
                    "empty_option_branches": 0,
                },
            )
            zone_facts["branch_visits"] += 1
            zone_facts["candidate_options"] += len(options)
            skeleton_region_options = sum(
                int(
                    candidate_policy_phase != STRUCTURED_PHASE
                    or _candidate_fits_skeleton_region(
                        code, rectangle, placed, context.structural_skeleton
                    )
                )
                for rectangle in options
            )
            zone_facts["skeleton_region_options"] += skeleton_region_options
            if not skeleton_region_options:
                zone_facts["empty_option_branches"] += 1
        stats.generated_candidates += len(options)
        for rectangle in options:
            if candidate_policy_phase == STRUCTURED_PHASE and not _candidate_fits_skeleton_region(
                code, rectangle, placed, context.structural_skeleton
            ):
                continue
            structural_refs = structural_anchor_references(code, tuple(placed))
            if candidate_policy_phase == STRUCTURED_PHASE and code in MAIN_PROCESS_ZONE_CODES:
                # Main-flow candidates are structurally generated only after
                # passing the versioned group/band predicate and existing
                # MUST-edge checks performed by _candidate_options.
                anchored = _candidate_fits_skeleton_region(
                    code, rectangle, placed, context.structural_skeleton
                )
            elif code == "sorting_packaging_room" and candidate_policy_phase == STRUCTURED_PHASE:
                anchored = True
            elif code == "raw_fruit_buffer" and candidate_policy_phase != STRUCTURED_PHASE:
                anchored = _rectangle_touches_boundary(rectangle, context.boundary)
            elif (
                context.structural_composition_family.family == "LINEAR_PROCESS_BAND"
                and _structural_linear_predecessor(code) is not None
            ):
                predecessor = placed.get(_structural_linear_predecessor(code) or "")
                anchored = predecessor is not None and _linear_flow_anchor_matches(
                    rectangle, predecessor, context.structural_composition_family
                )
            else:
                anchored = any(
                    rectangles_share_positive_edge(rectangle, placed[reference])
                    for reference in structural_refs
                )
            placed[code] = rectangle
            yield from visit(
                index + 1,
                structurally_generated
                and anchored
                and context.search_phase != GENERAL_FALLBACK_PHASE,
                main_process_skeleton,
            )
            placed.pop(code)
            if stats.node_budget_exhausted:
                return

    if context.search_phase == STRUCTURED_PHASE:
        # Admit each exact, preflight-passing skeleton to tail search as soon
        # as it is constructed. Draining the constructor first can consume the
        # shared budget collecting seeds while leaving no quantum for the
        # already-admissible seed's tail, regressing existing full-chain cases.
        discovery_context = context
        for seed_or_quantum in _construct_main_process_skeletons(discovery_context, stats):
            if isinstance(seed_or_quantum, _SearchQuantumYield):
                yield seed_or_quantum
                continue
            seed = seed_or_quantum
            context = _canonical_tail_search_context(discovery_context, seed)
            placed.update({row.zone_code: row for row in seed.zone_rectangles})
            if len(placed) != len(MAIN_PROCESS_ZONE_CODES):
                raise _error("MAIN_PROCESS_SKELETON_ZONE_SET_INVALID")
            tail_node_limit = max(0, context.node_budget - stats.visited_nodes)
            tail_start_node = stats.visited_nodes
            complete_start_count = stats.complete_candidates
            lifecycle_row: dict[str, Any] = {
                "topology": seed.topology,
                "skeleton_hash": seed.main_process_skeleton_hash,
                "layout_family": seed.building_layout_family,
                "envelope_family": seed.building_envelope_family,
                "planned_envelope_bounds_mm": (
                    list(seed.planned_envelope_bounds_mm)
                    if seed.planned_envelope_bounds_mm is not None
                    else None
                ),
                "discovery_topology": seed.discovery_topology,
                "canonical_topology_owner": seed.canonical_topology_owner,
                "discovery_family": (seed.discovery_family or seed.family).to_dict(),
                "canonical_family": seed.family.to_dict(),
                "tail_search_started_by_topology": seed.discovery_topology,
                "construction_nodes": (stats.construction_nodes_by_skeleton or {}).get(
                    seed.main_process_skeleton_hash, 0
                ),
                "tail_nodes": 0,
                "tail_node_limit": tail_node_limit,
                "complete_candidate_count": 0,
                "p2d_reached": False,
                "p2d_full_pass_count": 0,
                "search_status": "ACTIVE",
                "first_failure_stage": None,
                "first_failure_reason": None,
            }
            if stats.skeleton_tail_lifecycle is None:
                stats.skeleton_tail_lifecycle = []
            stats.skeleton_tail_lifecycle.append(lifecycle_row)
            for tail_event in visit(len(MAIN_PROCESS_ZONE_CODES), True, seed):
                complete_count_so_far = stats.complete_candidates - complete_start_count
                lifecycle_row["tail_nodes"] = stats.visited_nodes - tail_start_node
                lifecycle_row["complete_candidate_count"] = complete_count_so_far
                lifecycle_row["p2d_reached"] = complete_count_so_far > 0
                if isinstance(tail_event, _SearchQuantumYield):
                    lifecycle_row["search_status"] = "QUANTUM_EXHAUSTED"
                    yield tail_event
                else:
                    yield tail_event
            complete_count = stats.complete_candidates - complete_start_count
            lifecycle_row["tail_nodes"] = stats.visited_nodes - tail_start_node
            lifecycle_row["complete_candidate_count"] = complete_count
            lifecycle_row["p2d_reached"] = complete_count > 0
            lifecycle_row["search_status"] = (
                "SEARCH_EXHAUSTED" if not stats.node_budget_exhausted else "ACTIVE"
            )
            if complete_count == 0 and stats.node_budget_exhausted:
                lifecycle_row["first_failure_stage"] = "TAIL_SEARCH"
                lifecycle_row["first_failure_reason"] = "GLOBAL_PLACEMENT_NODE_BUDGET_EXHAUSTED"
            elif complete_count == 0:
                lifecycle_row["first_failure_stage"] = "TAIL_SEARCH"
                lifecycle_row["first_failure_reason"] = (
                    "TAIL_SEARCH_COMPLETED_WITHOUT_COMPLETE_P2C_CANDIDATE"
                )
            placed.clear()
            context = discovery_context
            if stats.node_budget_exhausted:
                return
        if stats.node_budget_exhausted:
            return
    elif context.search_phase == GENERAL_FALLBACK_PHASE:
        # Keep the pre-R2 skeleton constructor as a genuine independent
        # compatibility source, while retaining GENERAL_FALLBACK semantics
        # for its tail: canonical identity is rebound, but the new envelope
        # must not become an admission boundary for legacy layouts.
        discovery_context = context
        for seed_or_quantum in _construct_main_process_skeletons(discovery_context, stats):
            if isinstance(seed_or_quantum, _SearchQuantumYield):
                yield seed_or_quantum
                continue
            seed = seed_or_quantum
            context = _canonical_tail_search_context(discovery_context, seed)
            placed.update({row.zone_code: row for row in seed.zone_rectangles})
            if len(placed) != len(MAIN_PROCESS_ZONE_CODES):
                raise _error("MAIN_PROCESS_SKELETON_ZONE_SET_INVALID")
            complete_start_count = stats.complete_candidates
            tail_start_node = stats.visited_nodes
            lifecycle_row = {
                "topology": seed.topology,
                "skeleton_hash": seed.main_process_skeleton_hash,
                "layout_family": seed.building_layout_family,
                "envelope_family": seed.building_envelope_family,
                "discovery_topology": seed.discovery_topology,
                "canonical_topology_owner": seed.canonical_topology_owner,
                "discovery_family": (seed.discovery_family or seed.family).to_dict(),
                "canonical_family": seed.family.to_dict(),
                "tail_search_started_by_topology": seed.discovery_topology,
                "construction_nodes": (stats.construction_nodes_by_skeleton or {}).get(
                    seed.main_process_skeleton_hash, 0
                ),
                "tail_nodes": 0,
                "tail_node_limit": max(0, context.node_budget - stats.visited_nodes),
                "complete_candidate_count": 0,
                "p2d_reached": False,
                "p2d_full_pass_count": 0,
                "search_status": "ACTIVE",
                "first_failure_stage": None,
                "first_failure_reason": None,
            }
            if stats.skeleton_tail_lifecycle is None:
                stats.skeleton_tail_lifecycle = []
            stats.skeleton_tail_lifecycle.append(lifecycle_row)
            for tail_event in visit(len(MAIN_PROCESS_ZONE_CODES), True, seed):
                lifecycle_row["tail_nodes"] = stats.visited_nodes - tail_start_node
                lifecycle_row["complete_candidate_count"] = (
                    stats.complete_candidates - complete_start_count
                )
                lifecycle_row["p2d_reached"] = lifecycle_row["complete_candidate_count"] > 0
                if isinstance(tail_event, _SearchQuantumYield):
                    lifecycle_row["search_status"] = "QUANTUM_EXHAUSTED"
                yield tail_event
            lifecycle_row["tail_nodes"] = stats.visited_nodes - tail_start_node
            lifecycle_row["complete_candidate_count"] = (
                stats.complete_candidates - complete_start_count
            )
            lifecycle_row["p2d_reached"] = lifecycle_row["complete_candidate_count"] > 0
            lifecycle_row["search_status"] = (
                "ACTIVE" if stats.node_budget_exhausted else "SEARCH_EXHAUSTED"
            )
            if not lifecycle_row["p2d_reached"]:
                lifecycle_row["first_failure_stage"] = "TAIL_SEARCH"
                lifecycle_row["first_failure_reason"] = (
                    "GLOBAL_PLACEMENT_NODE_BUDGET_EXHAUSTED"
                    if stats.node_budget_exhausted
                    else "TAIL_SEARCH_COMPLETED_WITHOUT_COMPLETE_P2C_CANDIDATE"
                )
            placed.clear()
            context = discovery_context
            if stats.node_budget_exhausted:
                return
    # GENERAL_FALLBACK_PHASE is the independent whole-layout compatibility
    # room-level source. It uses the exact pre-R2 candidate ordering and any
    # remaining nodes after the legacy skeleton constructor above.
    yield from visit(0, True)


def _materialize_candidate_result(
    payload: Mapping[str, Any], *, provenance: Mapping[str, Any] | None = None
) -> SitePlacementResultV1:
    content = dict(payload)
    content.pop("_loading_comparison", None)
    content.pop("_structural_generation_flag", None)
    content.pop("_structural_composition_family", None)
    content.pop("_structural_skeleton", None)
    content.pop("_search_phase", None)
    content.pop("_main_process_skeleton", None)
    if provenance is not None:
        content["search_provenance"] = dict(provenance)
    content.setdefault("placement_engine_identity", IDENTITY)
    content.setdefault("search_profile_identity", SEARCH_PROFILE_IDENTITY)
    content.setdefault("status", "PLACEMENT_FOUND")
    content.setdefault("placement_available", True)
    content.setdefault("placement_hard_constraints_passed", True)
    content.setdefault("routing_validated", False)
    content.setdefault("access_route_validated", False)
    content.setdefault("truck_route_validated", False)
    content.setdefault("project_layout_validated", False)
    content.setdefault("p2_complete", False)
    content.setdefault("layout_infeasible_proof_implemented", False)
    content.setdefault("requires_review", True)
    candidate = PlacementCandidateV1.from_payload(content)
    content["canonical_candidate_hash"] = candidate.canonical_candidate_hash
    return SitePlacementResultV1.from_payload(content)


class PlacementCandidateEnumerationV1:
    """Deterministic P2C stream with an optional resumable quantum interface.

    The same generator and its branch stack survive every ``advance_quantum``
    call. No prefix is replayed when a scheduler gives the lane another turn.
    """

    def __init__(self, context: _PlacementSearchContext) -> None:
        self._context = context
        self._stats = _PlacementSearchStats()
        self._started = False
        self._finished = False
        self._structural_flags: dict[str, bool] = {}
        self._candidate_skeleton_hashes: dict[str, str | None] = {}
        self._candidate_topologies: dict[str, str] = {}
        self._candidate_families: dict[str, StructuralCompositionFamilyV1] = {}
        self._candidate_discovery_topologies: dict[str, str] = {}
        self._iterator: Iterator[dict[str, Any] | _SearchQuantumYield] | None = None
        self._quantum_mode = False

    def _ensure_iterator(self) -> Iterator[dict[str, Any] | _SearchQuantumYield]:
        if self._iterator is None:
            self._iterator = _walk_complete_candidate_payloads(self._context, self._stats)
        return self._iterator

    def _materialize_payload(self, payload: Mapping[str, Any]) -> SitePlacementResultV1:
        structural_flag = payload.get("_structural_generation_flag") is True
        internal_skeleton = payload.get("_main_process_skeleton")
        candidate = _materialize_candidate_result(payload)
        candidate_hash = candidate.to_dict().get("canonical_candidate_hash")
        if isinstance(candidate_hash, str):
            self._structural_flags[candidate_hash] = structural_flag
            skeleton_hash = (
                internal_skeleton.get("main_process_skeleton_hash")
                if isinstance(internal_skeleton, Mapping)
                else None
            )
            self._candidate_skeleton_hashes[candidate_hash] = (
                skeleton_hash if isinstance(skeleton_hash, str) else None
            )
            topology = (
                internal_skeleton.get("topology")
                if isinstance(internal_skeleton, Mapping)
                else self._context.structural_topology
            )
            self._candidate_topologies[candidate_hash] = str(topology)
            family_body = (
                internal_skeleton.get("family") if isinstance(internal_skeleton, Mapping) else None
            )
            if isinstance(family_body, Mapping):
                family_name = family_body.get("family")
                axis = family_body.get("dominant_axis")
                direction = family_body.get("dominant_direction")
                reason = family_body.get("generation_reason")
                if all(isinstance(value, str) for value in (family_name, axis, direction, reason)):
                    self._candidate_families[candidate_hash] = StructuralCompositionFamilyV1(
                        str(family_name), str(axis), str(direction), str(reason)
                    )
            discovery_topology = (
                internal_skeleton.get("discovery_topology")
                if isinstance(internal_skeleton, Mapping)
                else None
            )
            if isinstance(discovery_topology, str):
                self._candidate_discovery_topologies[candidate_hash] = discovery_topology
        return candidate

    def iter_candidates(self) -> Iterator[SitePlacementResultV1]:
        if self._started or self._quantum_mode:
            raise RuntimeError("placement candidate enumeration is one-shot")
        self._started = True
        iterator = self._ensure_iterator()
        while True:
            try:
                item = next(iterator)
            except StopIteration:
                self._finished = True
                return
            if isinstance(item, _SearchQuantumYield):
                continue
            yield self._materialize_payload(item)

    def advance_quantum(self, node_limit: int) -> PlacementCandidateQuantumAdvanceV1:
        """Advance this persistent generator by at most one scheduler slice."""
        if self._finished:
            return PlacementCandidateQuantumAdvanceV1((), 0, "COMPLETED", None, True, True)
        if self._started and not self._quantum_mode:
            raise RuntimeError("candidate iterator already started without quantum scheduling")
        if node_limit <= 0:
            raise ValueError("node_limit must be positive")
        self._started = True
        self._quantum_mode = True
        share_numerator = (
            ALTERNATIVE_TOPOLOGY_CONSTRUCTION_SHARE_NUMERATOR
            if self._context.structural_topology in {OFFSET_LINEAR_BAND, CENTRAL_PROCESS_HUB}
            else STRUCTURED_SKELETON_CONSTRUCTION_SHARE_NUMERATOR
        )
        share_denominator = (
            ALTERNATIVE_TOPOLOGY_CONSTRUCTION_SHARE_DENOMINATOR
            if self._context.structural_topology in {OFFSET_LINEAR_BAND, CENTRAL_PROCESS_HUB}
            else STRUCTURED_SKELETON_CONSTRUCTION_SHARE_DENOMINATOR
        )
        share_quantum_ceiling = max(
            1, self._context.node_budget * share_numerator // share_denominator
        )
        self._stats.quantum_node_limit = min(
            node_limit,
            CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET,
            CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET,
            share_quantum_ceiling,
        )
        self._stats.quantum_nodes_visited = 0
        start_nodes = self._stats.visited_nodes
        candidates: list[SitePlacementResultV1] = []
        iterator = self._ensure_iterator()
        while True:
            try:
                item = next(iterator)
            except StopIteration:
                self._finished = True
                self._stats.quantum_node_limit = None
                search_exhausted = self.search_tree_exhausted
                return PlacementCandidateQuantumAdvanceV1(
                    tuple(candidates),
                    self._stats.visited_nodes - start_nodes,
                    "SEARCH_EXHAUSTED" if search_exhausted else "COMPLETED",
                    dict(self._stats.current_work_item or {}),
                    search_exhausted,
                    True,
                )
            if isinstance(item, _SearchQuantumYield):
                work_item = dict(item.work_item or {})
                return PlacementCandidateQuantumAdvanceV1(
                    tuple(candidates),
                    self._stats.visited_nodes - start_nodes,
                    "QUANTUM_EXHAUSTED",
                    work_item,
                    False,
                    False,
                )
            candidates.append(self._materialize_payload(item))

    @property
    def completed(self) -> bool:
        return self._finished

    @property
    def candidate_count(self) -> int:
        return self._stats.complete_candidates

    @property
    def generated_candidate_count(self) -> int:
        return self._stats.generated_candidates

    @property
    def distinct_main_process_skeleton_count(self) -> int:
        return len(self._stats.constructed_main_skeletons or {})

    @property
    def skeleton_generation_report(self) -> dict[str, Any]:
        changing_shapes = self._stats.changing_flexible_shape_signatures or set()
        changing_aspects = tuple(
            max(width_mm, depth_mm) / min(width_mm, depth_mm)
            for width_mm, depth_mm in changing_shapes
            if min(width_mm, depth_mm) > 0
        )
        return {
            "identity": "main-process-skeleton-construction@1.0.0",
            "topology": self._context.structural_topology,
            "constructed_candidate_count": len(self._stats.constructed_main_skeletons or {}),
            "candidates": [
                candidate.to_evaluation_dict()
                for candidate in sorted(
                    (self._stats.constructed_main_skeletons or {}).values(),
                    key=lambda row: row.main_process_skeleton_hash,
                )
            ],
            "rejection_reason_counts": dict(
                sorted((self._stats.rejection_reason_counts or {}).items())
            ),
            "construction_attempts": list(self._stats.skeleton_construction_attempts or []),
            "root_preflight_mode": "EXACT_NECESSARY_PREDICATE_OR_ORDERING_ONLY",
            "heuristic_root_pruning": False,
            "root_preflight_ordering": list(self._stats.root_preflight_rows or []),
            "tail_slot_preflight_rows": list(self._stats.tail_slot_preflight_rows or []),
            "skeleton_tail_lifecycle": list(self._stats.skeleton_tail_lifecycle or []),
            "tail_search_zone_facts": {
                skeleton_hash: {
                    zone_code: dict(zone_facts)
                    for zone_code, zone_facts in sorted(zone_rows.items())
                }
                for skeleton_hash, zone_rows in sorted(
                    (self._stats.tail_zone_search_facts or {}).items()
                )
            },
            "node_budget_exhausted": self._stats.node_budget_exhausted,
            "construction_search_truncated": self._stats.skeleton_search_truncated,
            "normal_stop_reason": self._stats.normal_stop_reason,
            "construction_node_count": self._stats.construction_node_count,
            "tail_node_count": sum((self._stats.tail_nodes_by_skeleton or {}).values()),
            "continuation_work_item": dict(self._stats.current_work_item or {}),
            "site_bay_decomposition": {
                "identity": "orthogonal-site-buildable-bays@1.0.0",
                "status": "EXACT_ORTHOGONAL"
                if self._stats.site_bay_rows
                else "UNAVAILABLE_OR_EMPTY",
                "bay_count": len(self._stats.site_bay_rows or ()),
                "adjacency_count": sum(
                    len(bay.adjacent_bay_ids) for bay in self._stats.site_bay_rows or ()
                )
                // 2,
                "bays": [bay.to_dict() for bay in self._stats.site_bay_rows or ()],
            },
            "site_module_assembly": {
                "identity": "site-partitioned-module-placement@1.0.0",
                "module_internal_geometry_rigid": True,
                "module_level_site_adaptation": True,
                "individual_room_site_movement": False,
                "local_module_synthesis_uses_site_events": False,
                "module_site_assembly_uses_site_events": True,
                "packaging_joint_site_assembly": True,
                "packaging_module_independent": True,
                "critical_assembly_zone_count": len(MAIN_PROCESS_ZONE_CODES) + 1,
                "packaging_site_anchors": [
                    row.to_dict() for row in self._stats.site_packaging_anchors or ()
                ],
                "sorting_rotation_site_attempt_counts": dict(
                    sorted((self._stats.sorting_rotation_site_attempt_counts or {}).items())
                ),
                "variant_counts": dict(
                    sorted((self._stats.site_module_variant_counts or {}).items())
                ),
                "family_geometry_collapse_count": self._stats.family_geometry_collapse_count,
                "tail_access_aware_completion": {
                    "tail_geometry_only_admission": False,
                    "tail_access_aware_admission": True,
                    "office_changing_rigid_relation": False,
                    "access_endpoint_driven_tail_synthesis": True,
                    "generic_representative_sampling_is_primary": False,
                    "access_route_revalidator_injected": (
                        self._context.access_route_validator is not None
                    ),
                    "truck_pass_main_count": len(
                        self._stats.tail_access_capacity_status_by_main or ()
                    ),
                    "tail_access_preflighted_main_count": len(
                        self._stats.tail_access_capacity_status_by_main or ()
                    ),
                    "tail_access_capable_main_count": sum(
                        status == "TAIL_ACCESS_CAPABLE_MAIN"
                        for status in (
                            self._stats.tail_access_capacity_status_by_main or {}
                        ).values()
                    ),
                    "tail_access_incapable_main_count": sum(
                        status == "TAIL_ACCESS_INCAPABLE_MAIN"
                        for status in (
                            self._stats.tail_access_capacity_status_by_main or {}
                        ).values()
                    ),
                    "tail_access_unresolved_main_count": sum(
                        status == "UNRESOLVED_COVERAGE"
                        for status in (
                            self._stats.tail_access_capacity_status_by_main or {}
                        ).values()
                    ),
                    "tail_access_capacity_status_by_main": dict(
                        sorted((self._stats.tail_access_capacity_status_by_main or {}).items())
                    ),
                    "tail_incapable_reason_by_main": {
                        main: list(modules)
                        for main, modules in sorted(
                            (self._stats.tail_incapable_reason_by_main or {}).items()
                        )
                    },
                    "tail_incapable_proof_scope_by_main": dict(
                        sorted((self._stats.tail_incapable_proof_scope_by_main or {}).items())
                    ),
                    "global_infeasibility_proven": False,
                    "tail_access_capacity_candidate_cursor_by_main": {
                        main: dict(sorted(module_rows.items()))
                        for main, module_rows in sorted(
                            (
                                self._stats.tail_access_capacity_candidate_cursor_by_main or {}
                            ).items()
                        )
                    },
                    "tail_access_capacity_domain_exhausted_by_main": {
                        main: dict(sorted(module_rows.items()))
                        for main, module_rows in sorted(
                            (
                                self._stats.tail_access_capacity_domain_exhausted_by_main or {}
                            ).items()
                        )
                    },
                    "sorting_side_branch_free_intervals_by_main": {
                        main: {
                            module_name: {
                                interval_kind: list(rows)
                                for interval_kind, rows in sorted(interval_sets.items())
                            }
                            for module_name, interval_sets in sorted(module_rows.items())
                        }
                        for main, module_rows in sorted(
                            (self._stats.sorting_side_branch_free_intervals_by_main or {}).items()
                        )
                    },
                    "secondary_direct_seed_count_before_truck_filter_by_main": {
                        main: row.get("SECONDARY_SUPPORT_MODULE", 0)
                        for main, row in sorted(
                            (
                                self._stats.tail_direct_seed_counts_before_truck_filter_by_main
                                or {}
                            ).items()
                        )
                    },
                    "secondary_direct_seed_count_after_truck_filter_by_main": {
                        main: row.get("SECONDARY_SUPPORT_MODULE", 0)
                        for main, row in sorted(
                            (
                                self._stats.tail_direct_seed_counts_after_truck_filter_by_main or {}
                            ).items()
                        )
                    },
                    "frozen_direct_seed_count_before_truck_filter_by_main": {
                        main: row.get("FROZEN_SUPPORT_MODULE", 0)
                        for main, row in sorted(
                            (
                                self._stats.tail_direct_seed_counts_before_truck_filter_by_main
                                or {}
                            ).items()
                        )
                    },
                    "frozen_direct_seed_count_after_truck_filter_by_main": {
                        main: row.get("FROZEN_SUPPORT_MODULE", 0)
                        for main, row in sorted(
                            (
                                self._stats.tail_direct_seed_counts_after_truck_filter_by_main or {}
                            ).items()
                        )
                    },
                    "tail_access_capacity_continuation_count": (
                        self._stats.tail_access_capacity_continuation_count
                    ),
                    "truck_pass_main_rejected_for_tail_access_count": (
                        self._stats.truck_pass_main_rejected_for_tail_access_count
                    ),
                    "main_enumeration_continued_after_tail_access_reject": (
                        self._stats.main_enumeration_continued_after_tail_access_reject
                    ),
                    "main_generator_resumed_from_continuation": (
                        self._stats.main_generator_resumed_from_continuation
                    ),
                    "replayed_main_prefix_node_count": self._stats.replayed_main_prefix_node_count,
                    "tail_capacity_seed_cache_reused_in_s2": (
                        self._stats.tail_capacity_seed_cache_reused_in_s2
                    ),
                    "changing_flexible_authority_source": "P2C_UNIQUE_DIMENSIONS",
                    "changing_flexible_shape_count": len(changing_shapes),
                    "changing_authority_shape_count": len(
                        self._stats.changing_authority_shape_signatures or ()
                    ),
                    "changing_construction_canonical_shape_count": len(
                        self._stats.changing_construction_footprint_signatures or ()
                    ),
                    "changing_equivalent_footprint_dedup_count": max(
                        0,
                        len(self._stats.changing_authority_shape_signatures or ())
                        - len(self._stats.changing_construction_footprint_signatures or ()),
                    ),
                    "changing_extreme_aspect_shape_count": len(
                        self._stats.changing_extreme_aspect_shape_signatures or ()
                    ),
                    "changing_extreme_aspect_diagnostic_ratio_threshold": 10,
                    "changing_extreme_aspect_threshold_is_authority": False,
                    "changing_extreme_aspect_probed_before_route_compatible_count": (
                        self._stats.changing_extreme_aspect_probed_before_route_compatible_count
                    ),
                    "changing_non_square_shape_count": sum(
                        width_mm != depth_mm for width_mm, depth_mm in changing_shapes
                    ),
                    "changing_min_aspect_ratio": min(changing_aspects, default=None),
                    "changing_max_aspect_ratio": max(changing_aspects, default=None),
                    "changing_dual_endpoint_direct_seed_count": len(
                        self._stats.changing_dual_endpoint_seed_signatures or ()
                    ),
                    "entrance_route_compatible_changing_seed_count": (
                        self._stats.entrance_route_compatible_changing_seed_count
                    ),
                    "entrance_route_compatible_changing_seed_count_by_main": dict(
                        sorted(
                            (
                                self._stats.entrance_route_compatible_changing_seed_counts_by_main
                                or {}
                            ).items()
                        )
                    ),
                    "entrance_route_compatible_changing_access_pass_count": (
                        self._stats.entrance_route_compatible_changing_access_pass_count
                    ),
                    "changing_to_sorting_direct_pass_count": (
                        self._stats.changing_to_sorting_direct_pass_count
                    ),
                    "main_entrance_to_changing_failure_code_counts": dict(
                        sorted(
                            (
                                self._stats.main_entrance_to_changing_failure_code_counts or {}
                            ).items()
                        )
                    ),
                    "frozen_direct_seed_truck_rejection_count": len(
                        self._stats.frozen_direct_seed_truck_rejection_rows or ()
                    ),
                    "frozen_direct_seed_truck_rejection_rows": list(
                        self._stats.frozen_direct_seed_truck_rejection_rows or ()
                    ),
                    "endpoint_driven_candidate_metadata_miss_count": (
                        self._stats.endpoint_driven_candidate_metadata_miss_count
                    ),
                    "tail_access_preflight_nodes_by_main": dict(
                        sorted(
                            (self._stats.tail_access_capacity_preflight_nodes_by_main or {}).items()
                        )
                    ),
                    "changing_access_driven_candidate_count_by_main": {
                        key: row.get("CHANGING_MODULE", 0)
                        for key, row in sorted(
                            (self._stats.tail_access_driven_candidate_counts_by_main or {}).items()
                        )
                    },
                    "changing_access_valid_count_by_main": {
                        key: row.get("CHANGING_MODULE", 0)
                        for key, row in sorted(
                            (self._stats.tail_access_capacity_seed_counts_by_main or {}).items()
                        )
                    },
                    "secondary_access_driven_candidate_count_by_main": {
                        key: row.get("SECONDARY_SUPPORT_MODULE", 0)
                        for key, row in sorted(
                            (self._stats.tail_access_driven_candidate_counts_by_main or {}).items()
                        )
                    },
                    "secondary_access_valid_count_by_main": {
                        key: row.get("SECONDARY_SUPPORT_MODULE", 0)
                        for key, row in sorted(
                            (self._stats.tail_access_capacity_seed_counts_by_main or {}).items()
                        )
                    },
                    "frozen_access_driven_candidate_count_by_main": {
                        key: row.get("FROZEN_SUPPORT_MODULE", 0)
                        for key, row in sorted(
                            (self._stats.tail_access_driven_candidate_counts_by_main or {}).items()
                        )
                    },
                    "frozen_tail_capacity_seed_count_by_main": {
                        key: row.get("FROZEN_SUPPORT_MODULE", 0)
                        for key, row in sorted(
                            (self._stats.tail_access_capacity_seed_counts_by_main or {}).items()
                        )
                    },
                    "office_geometry_candidate_count_by_main": dict(
                        sorted(
                            (
                                self._stats.tail_office_geometry_candidate_counts_by_main or {}
                            ).items()
                        )
                    ),
                    "tail_access_capacity_preflight_rows": list(
                        self._stats.tail_access_capacity_preflight_rows or ()
                    ),
                    "generic_fallback_route_probe_count": (
                        self._stats.tail_generic_fallback_route_probe_count
                    ),
                    "generic_fallback_truncated_count": (
                        self._stats.tail_generic_fallback_truncated_count
                    ),
                    "generic_fallback_deferred_count": (
                        self._stats.tail_generic_fallback_deferred_count
                    ),
                    "main_entrance_influences_changing_enumeration": True,
                    "sorting_influences_changing_enumeration": True,
                    "sorting_influences_secondary_enumeration": True,
                    "sorting_influences_frozen_enumeration": True,
                    "shipping_influences_office_enumeration": True,
                    "raw_geometry_slot_count_by_module": {
                        name: len(signatures)
                        for name, signatures in sorted(
                            (self._stats.tail_raw_geometry_slot_count_by_module or {}).items()
                        )
                    },
                    "access_valid_slot_count_by_module": {
                        name: len(signatures)
                        for name, signatures in sorted(
                            (self._stats.tail_access_valid_slot_count_by_module or {}).items()
                        )
                    },
                    "personnel_raw_candidate_count": len(
                        self._stats.personnel_raw_candidate_signatures or ()
                    ),
                    "personnel_access_2_of_2_pass_count": len(
                        self._stats.personnel_access_2_of_2_pass_signatures or ()
                    ),
                    "secondary_raw_candidate_count": len(
                        self._stats.secondary_raw_candidate_signatures or ()
                    ),
                    "secondary_access_pass_count": len(
                        self._stats.secondary_access_pass_signatures or ()
                    ),
                    "frozen_raw_candidate_count": len(
                        self._stats.frozen_raw_candidate_signatures or ()
                    ),
                    "frozen_access_pass_count": len(
                        self._stats.frozen_access_pass_signatures or ()
                    ),
                    "frozen_sorting_portal_event_count_by_main": dict(
                        sorted(
                            (self._stats.frozen_sorting_portal_event_count_by_main or {}).items()
                        )
                    ),
                    "frozen_target_portal_event_count_by_main": dict(
                        sorted((self._stats.frozen_target_portal_event_count_by_main or {}).items())
                    ),
                    "frozen_truck_clear_corridor_event_count_by_main": dict(
                        sorted(
                            (
                                self._stats.frozen_truck_clear_corridor_event_count_by_main or {}
                            ).items()
                        )
                    ),
                    "frozen_truck_clear_corridor_candidate_event_count_by_main": dict(
                        sorted(
                            (
                                self._stats.frozen_truck_clear_corridor_candidate_event_count_by_main
                                or {}
                            ).items()
                        )
                    ),
                    "frozen_route_constructive_seed_count_by_main": dict(
                        sorted(
                            (self._stats.frozen_route_constructive_seed_count_by_main or {}).items()
                        )
                    ),
                    "frozen_candidate_counts_by_main": {
                        main: dict(sorted(counts.items()))
                        for main, counts in sorted(
                            (self._stats.frozen_candidate_counts_by_main or {}).items()
                        )
                    },
                    "frozen_route_probe_count_by_main": dict(
                        sorted((self._stats.frozen_route_probe_count_by_main or {}).items())
                    ),
                    "frozen_access_valid_count_by_main": dict(
                        sorted((self._stats.frozen_access_valid_count_by_main or {}).items())
                    ),
                    "frozen_access_failure_code_counts_by_main": {
                        main: dict(sorted(codes.items()))
                        for main, codes in sorted(
                            (self._stats.frozen_access_failure_code_counts_by_main or {}).items()
                        )
                    },
                    "frozen_candidate_rejection_taxonomy_by_main": {
                        main: dict(sorted(counts.items()))
                        for main, counts in sorted(
                            (self._stats.frozen_candidate_rejection_taxonomy_by_main or {}).items()
                        )
                    },
                    "frozen_candidate_route_rejection_rows_by_main": {
                        main: list(rows)
                        for main, rows in sorted(
                            (
                                self._stats.frozen_candidate_route_rejection_rows_by_main or {}
                            ).items()
                        )
                    },
                    "frozen_constructive_candidate_witness_by_main": {
                        main: list(rows)
                        for main, rows in sorted(
                            (
                                self._stats.frozen_constructive_candidate_witness_by_main or {}
                            ).items()
                        )
                    },
                    "frozen_access_witness_by_main": {
                        main: dict(row)
                        for main, row in sorted(
                            (self._stats.frozen_access_witness_by_main or {}).items()
                        )
                    },
                    "construction_access_requirement_pass_counts": dict(
                        sorted(
                            (self._stats.construction_access_requirement_pass_counts or {}).items()
                        )
                    ),
                    "construction_access_requirement_failure_counts": dict(
                        sorted(
                            (
                                self._stats.construction_access_requirement_failure_counts or {}
                            ).items()
                        )
                    ),
                    "construction_access_failure_code_counts": dict(
                        sorted((self._stats.construction_access_failure_code_counts or {}).items())
                    ),
                    "direct_shared_edge_access_witness_count": (
                        self._stats.direct_shared_edge_access_witness_count
                    ),
                    "corridor_mediated_access_witness_count": (
                        self._stats.corridor_mediated_access_witness_count
                    ),
                    "reserved_access_corridor_count": len(
                        self._stats.reserved_access_corridor_geometries or ()
                    ),
                    "access_route_revalidation_count": (
                        self._stats.access_route_revalidation_count
                    ),
                    "access_slot_placement_nodes_charged": (
                        self._stats.tail_access_slot_attempt_count
                    ),
                    "access_slot_placement_budget_exhausted": (
                        self._stats.tail_access_slot_budget_exhausted
                    ),
                    "candidate_space_truncated": self._stats.tail_candidate_space_truncated,
                    "revalidate_after_each_tail_extension": True,
                    "access_candidate_witnesses": list(
                        self._stats.tail_access_candidate_witnesses or ()
                    ),
                    "complete_candidate_access_witnesses": list(
                        self._stats.tail_complete_access_witnesses or ()
                    ),
                },
                "attempts": list(self._stats.site_module_assembly_trace or []),
            },
            "_r6_topology_ownership_duplicates": list(
                self._stats.topology_ownership_duplicates or []
            ),
            "_r7_geometry_evaluation_admissions": list(
                self._stats.geometry_evaluation_admissions or []
            ),
            "_r6_offset_transition_trace": list(self._stats.offset_transition_trace or []),
            "_r6_constructive_divergence_attempts": list(
                self._stats.constructive_divergence_attempts or []
            ),
            "_r6_topology_classification_failures": list(
                self._stats.topology_classification_failures or []
            ),
            "_r6_cross_topology_duplicate_count": self._stats.cross_topology_duplicate_count,
        }

    @property
    def distinct_structural_core_root_count(self) -> int:
        return len(self._stats.structured_core_root_completions or {})

    @property
    def main_skeleton_truck_preflight_rows(self) -> list[dict[str, Any]]:
        """Internal selector diagnostics, kept out of Tool 7 serialization."""
        return list(self._stats.main_skeleton_truck_preflight_rows or [])

    @property
    def visited_node_count(self) -> int:
        return self._stats.visited_nodes

    @property
    def search_tree_exhausted(self) -> bool:
        return (
            self.completed
            and not self._stats.node_budget_exhausted
            and not self._stats.skeleton_search_truncated
            and self._stats.normal_stop_reason is None
        )

    @property
    def node_budget_exhausted(self) -> bool:
        return self._stats.node_budget_exhausted

    @property
    def provenance(self) -> dict[str, Any]:
        return _search_provenance(
            self._context,
            self._stats,
            search_tree_exhausted=self.search_tree_exhausted,
            objective_optimal_within_search_family=self.search_tree_exhausted,
        )

    @property
    def structural_composition_family(self) -> StructuralCompositionFamilyV1:
        return self._context.structural_composition_family

    @property
    def structural_skeleton(self) -> StructuralSkeletonV1:
        return self._context.structural_skeleton

    @property
    def search_phase(self) -> str:
        return self._context.search_phase

    @property
    def structural_topology(self) -> str:
        return self._context.structural_topology

    def structurally_generated(self, candidate_hash: str) -> bool:
        """Report whether every assigned zone used a group/band anchor."""
        return self._structural_flags.get(candidate_hash, False)

    def candidate_main_process_skeleton_hash(self, candidate_hash: str) -> str | None:
        return self._candidate_skeleton_hashes.get(candidate_hash)

    def candidate_topology(self, candidate_hash: str) -> str | None:
        return self._candidate_topologies.get(candidate_hash)

    def candidate_structural_family(
        self, candidate_hash: str
    ) -> StructuralCompositionFamilyV1 | None:
        return self._candidate_families.get(candidate_hash)

    def candidate_discovery_topology(self, candidate_hash: str) -> str | None:
        return self._candidate_discovery_topologies.get(candidate_hash)


def enumerate_placement_candidates(
    authorities: Mapping[str, Mapping[str, Any]],
    site_body: Mapping[str, Any],
    graph: AdjacencyGraphV1,
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    objective_profile_hash: str | None = None,
    access_requirements: Sequence[Mapping[str, Any]] = (),
    spatial_relationships: Sequence[Mapping[str, Any]] = (),
    node_budget: int = DEFAULT_NODE_BUDGET,
    truck_maneuver_binding: Any = None,
    truck_node_budget: int = 20_000,
    truck_maneuver_validator: Callable[..., Mapping[str, Any]] | None = None,
    access_route_validator: (
        Callable[..., tuple[Mapping[str, Any], tuple[PolygonMM, ...]]] | None
    ) = None,
    access_portal_event_provider: Callable[..., Mapping[str, Any]] | None = None,
    main_entrance_route_start_points: Sequence[tuple[int, int]] = (),
    complete_candidate_limit: int | None = None,
    structural_family: StructuralCompositionFamilyV1 | None = None,
    structural_topology: str | None = None,
    search_phase: str = LEGACY_COMPAT_PHASE,
    direct_synthesis_enabled: bool = True,
    global_main_process_geometry_registry: dict[str, dict[str, Any]] | None = None,
    global_cross_topology_duplicate_trace: list[dict[str, Any]] | None = None,
) -> PlacementCandidateEnumerationV1:
    """Expose the same validated P2C search family as a lazy candidate stream."""
    return PlacementCandidateEnumerationV1(
        _validated_search_context(
            authorities,
            site_body,
            graph,
            source_zone_plan_hash=source_zone_plan_hash,
            source_p1_handoff_hash=source_p1_handoff_hash,
            source_site_geometry_hash=source_site_geometry_hash,
            objective_profile_hash=objective_profile_hash,
            access_requirements=access_requirements,
            spatial_relationships=spatial_relationships,
            node_budget=node_budget,
            truck_maneuver_binding=truck_maneuver_binding,
            truck_node_budget=truck_node_budget,
            truck_maneuver_validator=truck_maneuver_validator,
            access_route_validator=access_route_validator,
            access_portal_event_provider=access_portal_event_provider,
            main_entrance_route_start_points=main_entrance_route_start_points,
            complete_candidate_limit=complete_candidate_limit,
            structural_family=structural_family,
            structural_topology=structural_topology,
            search_phase=search_phase,
            direct_synthesis_enabled=direct_synthesis_enabled,
            global_main_process_geometry_registry=global_main_process_geometry_registry,
            global_cross_topology_duplicate_trace=global_cross_topology_duplicate_trace,
        )
    )


def placement_candidate_is_better(
    candidate: Mapping[str, Any], best: Mapping[str, Any] | None, preferred_loading_side: str
) -> bool:
    """Apply the existing P2B2 objective comparator to one P2C candidate."""
    return _is_better(candidate, best, preferred_loading_side)


def search_placement(
    authorities: Mapping[str, Mapping[str, Any]],
    site_body: Mapping[str, Any],
    graph: AdjacencyGraphV1,
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    objective_profile_hash: str | None = None,
    access_requirements: Sequence[Mapping[str, Any]] = (),
    spatial_relationships: Sequence[Mapping[str, Any]] = (),
    node_budget: int = DEFAULT_NODE_BUDGET,
    complete_candidate_limit: int | None = None,
) -> SitePlacementResultV1:
    """Search a finite candidate family and return found/exhausted semantics.

    This search is intentionally incomplete.  A bounded search that finds no
    candidate returns ``LAYOUT_SEARCH_EXHAUSTED`` rather than claiming a proof
    of infeasibility.
    """
    context = _validated_search_context(
        authorities,
        site_body,
        graph,
        source_zone_plan_hash=source_zone_plan_hash,
        source_p1_handoff_hash=source_p1_handoff_hash,
        source_site_geometry_hash=source_site_geometry_hash,
        objective_profile_hash=objective_profile_hash,
        access_requirements=access_requirements,
        spatial_relationships=spatial_relationships,
        node_budget=node_budget,
        complete_candidate_limit=complete_candidate_limit,
    )
    stats = _PlacementSearchStats()
    best_payload: dict[str, Any] | None = None
    for payload in _walk_complete_candidate_payloads(context, stats):
        if isinstance(payload, _SearchQuantumYield):
            continue
        if _is_better(payload, best_payload, context.preferred_loading_side):
            best_payload = payload
    search_tree_exhausted = not stats.node_budget_exhausted
    objective_optimal_within_search_family = best_payload is not None and search_tree_exhausted
    provenance = _search_provenance(
        context,
        stats,
        search_tree_exhausted=search_tree_exhausted,
        objective_optimal_within_search_family=objective_optimal_within_search_family,
    )

    if best_payload is None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "placement_result_identity": PLACEMENT_RESULT_IDENTITY,
            "placement_engine_identity": IDENTITY,
            "search_profile_identity": SEARCH_PROFILE_IDENTITY,
            "status": "LAYOUT_SEARCH_EXHAUSTED",
            "placement_available": False,
            "placement_hard_constraints_passed": False,
            "zone_count": 0,
            "source_zone_plan_hash": context.source_zone_plan_hash,
            "source_p1_handoff_hash": context.source_p1_handoff_hash,
            "source_site_geometry_hash": context.source_site_geometry_hash,
            "source_objective_profile_hash": context.objective_profile_hash,
            "placement_access_requirement_count": len(access_requirements),
            "search_provenance": provenance,
            "routing_validated": False,
            "access_route_validated": False,
            "truck_route_validated": False,
            "project_layout_validated": False,
            "p2_complete": False,
            "layout_infeasible_proof_implemented": False,
            "requires_review": True,
            "warnings": [
                (
                    "Search budget exhausted before a placement was found; "
                    "this is not an infeasibility proof."
                    if stats.node_budget_exhausted
                    else (
                        "Finite placement candidate family was exhausted; "
                        "this is not an infeasibility proof."
                    )
                )
            ],
        }
        return SitePlacementResultV1.from_payload(payload)

    best_payload.pop("_loading_comparison", None)
    best_payload.pop("_structural_generation_flag", None)
    best_payload.pop("_structural_composition_family", None)
    best_payload["search_provenance"] = provenance
    best_payload["status"] = "PLACEMENT_FOUND"
    best_payload["placement_available"] = True
    best_payload["placement_engine_identity"] = IDENTITY
    best_payload["search_profile_identity"] = SEARCH_PROFILE_IDENTITY
    best_payload["constraint_evaluation"] = {
        "hard_constraints_passed": True,
        "all_zones_inside_effective_buildable_boundary": True,
        "all_hard_obstacles_clear": True,
        "no_interior_zone_overlap": True,
        "must_adjacencies_passed": True,
        "access_status": "PENDING_ROUTE_VALIDATION",
    }
    best_payload["routing_validated"] = False
    best_payload["access_route_validated"] = False
    best_payload["truck_route_validated"] = False
    best_payload["project_layout_validated"] = False
    best_payload["p2_complete"] = False
    best_payload["layout_infeasible_proof_implemented"] = False
    best_payload["requires_review"] = True
    best_payload["warnings"] = [
        (
            "Placement selected by the deterministic objective within the exhausted finite "
            "search family; portal, corridor and truck routes remain unvalidated."
            if search_tree_exhausted
            else "Placement selected among deterministically explored candidates; "
            "search-family optimum is not proven because the search budget was exhausted; "
            "portal, corridor and truck routes remain unvalidated."
        )
    ]
    selected_candidate = PlacementCandidateV1.from_payload(best_payload)
    best_payload["canonical_candidate_hash"] = selected_candidate.canonical_candidate_hash
    return SitePlacementResultV1.from_payload(best_payload)
