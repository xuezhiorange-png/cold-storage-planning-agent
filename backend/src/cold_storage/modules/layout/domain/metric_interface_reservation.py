"""Finite pairwise hard-interface capacity; not a whole-building placement engine.

The declared domain is the union of both endpoint-first event constructions.
It is not the continuous feasible set. Topological hosts have no metric footprint.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from functools import lru_cache
from hashlib import sha256
from typing import Any

from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.authority_shapes import AuthoritativeZoneShapeV1, _m
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.mandatory_interface_reservation import (
    MandatoryInterfaceReservationV1,
    MandatoryReservationKindV1,
    StructuralContainerReferenceV1,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
)
from cold_storage.modules.layout.domain.structural_composition import _mandatory_edge_identity

DOMAIN_POLICY = "symmetric-boundary-obstacle-corner-and-shared-face-events@1.0.0"
METRIC_SCOPE = "PAIRWISE_SITE_DIMENSION_HARD_INTERFACE_CAPACITY"
DEFAULT_PAIR_EVALUATION_CAP = 10_000_000
Bounds = tuple[int, int, int, int]
Pair = tuple[
    PlacedRectangleV1, PlacedRectangleV1, AuthoritativeZoneShapeV1, AuthoritativeZoneShapeV1
]


class MetricReservationStatusV1(StrEnum):
    NONEMPTY = "PASS_METRIC_RESERVATION_NONEMPTY"
    EMPTY = "PROVED_NO_METRIC_RESERVATION_IN_CURRENT_FINITE_DOMAIN"
    UNKNOWN = "UNKNOWN_METRIC_RESERVATION_DOMAIN_INCOMPLETE"


class MetricCapacityGateStatusV1(StrEnum):
    READY = "PASS_METRIC_RESERVATIONS_TO_FUTURE_PLACEMENT"
    REJECT = "REJECT_COMPOSITION_IN_CURRENT_METRIC_DOMAIN"
    UNKNOWN = "UNKNOWN_METRIC_RESERVATION_CAPACITY"


@dataclass(frozen=True)
class MetricAttachmentSlotV1:
    source_edge_identity: str
    endpoint_a_role: str
    endpoint_b_role: str
    endpoint_a_shape_authority_identity: str
    endpoint_b_shape_authority_identity: str
    endpoint_a_bounds_mm: Bounds
    endpoint_b_bounds_mm: Bounds
    endpoint_a_shape: AuthoritativeZoneShapeV1
    endpoint_b_shape: AuthoritativeZoneShapeV1
    shared_edge_side: str
    shared_edge_segment_mm: tuple[tuple[int, int], tuple[int, int]]
    shared_edge_length_mm: int
    source_site_geometry_hash: str
    source_dimension_authority_identity: str
    structural_reservation_kind: MandatoryReservationKindV1
    structural_host_a: StructuralContainerReferenceV1
    structural_host_b: StructuralContainerReferenceV1
    site_valid: bool = True
    hard_obstacles_clear: bool = True
    positive_shared_edge_valid: bool = True
    pair_non_overlap_valid: bool = True
    metric_slot_is_final_room_placement: bool = False
    metric_slot_is_engineering_layout: bool = False

    def __post_init__(self) -> None:
        a = rectangle_at(self.endpoint_a_role, self.endpoint_a_bounds_mm[:2], self.endpoint_a_shape)
        b = rectangle_at(self.endpoint_b_role, self.endpoint_b_bounds_mm[:2], self.endpoint_b_shape)
        if (
            a.bounds_mm != self.endpoint_a_bounds_mm
            or b.bounds_mm != self.endpoint_b_bounds_mm
            or not rectangles_share_positive_edge(a, b)
            or rectangles_overlap(a, b)
            or shared_edge(a, b)
            != (self.shared_edge_side, self.shared_edge_segment_mm, self.shared_edge_length_mm)
            or not all(
                (
                    self.site_valid,
                    self.hard_obstacles_clear,
                    self.positive_shared_edge_valid,
                    self.pair_non_overlap_valid,
                )
            )
            or self.metric_slot_is_final_room_placement
            or self.metric_slot_is_engineering_layout
        ):
            raise ValueError("INVALID_METRIC_ATTACHMENT_SLOT")


@dataclass(frozen=True)
class MetricInterfaceReservationV1:
    source_edge_identity: str
    source_structural_reservation_identity: str
    endpoint_a_role: str
    endpoint_b_role: str
    metric_scope: str
    finite_domain_identity: str
    finite_domain_complete: bool
    evaluated_candidate_pair_count: int
    valid_slot_count: int
    slot_set_digest: str
    representative_slots: tuple[MetricAttachmentSlotV1, ...]
    attachment_orientations: tuple[str, ...]
    authority_shape_counts: tuple[int, int]
    construction_shape_counts: tuple[int, int]
    rejection_counts: tuple[tuple[str, int], ...]
    incomplete_reason: str | None
    status: MetricReservationStatusV1
    global_infeasibility_proven: bool = False
    representative_slots_are_not_exclusive_domain: bool = True
    structural_host_metric_footprint_proven: bool = False

    def __post_init__(self) -> None:
        expected = (
            MetricReservationStatusV1.UNKNOWN
            if not self.finite_domain_complete
            else MetricReservationStatusV1.NONEMPTY
            if self.valid_slot_count
            else MetricReservationStatusV1.EMPTY
        )
        if (
            self.metric_scope != METRIC_SCOPE
            or self.status != expected
            or self.global_infeasibility_proven
            or self.structural_host_metric_footprint_proven
            or not self.representative_slots_are_not_exclusive_domain
            or self.valid_slot_count < 0
            or sum(v for _, v in self.rejection_counts) + self.valid_slot_count
            != self.evaluated_candidate_pair_count
            or bool(self.incomplete_reason) == self.finite_domain_complete
            or bool(self.representative_slots) != bool(self.valid_slot_count)
            or any(
                s.source_edge_identity != self.source_edge_identity
                for s in self.representative_slots
            )
        ):
            raise ValueError("INVALID_METRIC_RESERVATION_RESULT")


@dataclass(frozen=True)
class MetricMandatoryInterfaceCapacityGateV1:
    status: MetricCapacityGateStatusV1
    metric_scope: str = METRIC_SCOPE
    metric_gate_is_project_layout_validation: bool = False
    metric_gate_is_p2d: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, MetricCapacityGateStatusV1)
            or self.metric_scope != METRIC_SCOPE
            or self.metric_gate_is_project_layout_validation
            or self.metric_gate_is_p2d
        ):
            raise ValueError("INVALID_METRIC_GATE_SCOPE")


def aggregate_metric_gate(
    items: Sequence[MetricInterfaceReservationV1],
) -> MetricMandatoryInterfaceCapacityGateV1:
    statuses = {i.status for i in items}
    status = (
        MetricCapacityGateStatusV1.REJECT
        if MetricReservationStatusV1.EMPTY in statuses
        else MetricCapacityGateStatusV1.UNKNOWN
        if not items or MetricReservationStatusV1.UNKNOWN in statuses
        else MetricCapacityGateStatusV1.READY
    )
    return MetricMandatoryInterfaceCapacityGateV1(status)


def rectangle_at(
    role: str, origin: tuple[int, ...], shape: AuthoritativeZoneShapeV1
) -> PlacedRectangleV1:
    return PlacedRectangleV1(
        role,
        _m(origin[0]),
        _m(origin[1]),
        _m(shape.width_mm),
        _m(shape.depth_mm),
        shape.rotation_deg,
    )


def physical_status(
    rect: PlacedRectangleV1, boundary: PolygonMM, obstacles: Sequence[PolygonMM]
) -> str:
    if not rectangle_inside_polygon(rect, boundary):
        return "SITE"
    if any(rectangle_intersects_closed_obstacle(rect, o) for o in obstacles):
        return "HARD_OBSTACLE"
    return "VALID"


def pair_status(
    a: PlacedRectangleV1, b: PlacedRectangleV1, boundary: PolygonMM, obstacles: Sequence[PolygonMM]
) -> str:
    for rect in (a, b):
        status = physical_status(rect, boundary, obstacles)
        if status != "VALID":
            return status
    if rectangles_overlap(a, b):
        return "PAIR_OVERLAP"
    return "VALID" if rectangles_share_positive_edge(a, b) else "NO_POSITIVE_SHARED_EDGE"


def event_origins(
    shape: AuthoritativeZoneShapeV1, boundary: PolygonMM, obstacles: Sequence[PolygonMM]
) -> tuple[tuple[int, int], ...]:
    """Corner-align at every polygon vertex, including closed-obstacle ±1mm events.

    All four footprint corners are declared; obstacle events use ±1mm diagonals.
    This is a finite event policy, not a raster or an assertion of continuous completeness.
    """
    w, h = shape.world_width_mm, shape.world_depth_mm
    return tuple(
        sorted(
            {(x - dx, y - dy) for x, y in boundary for dx in (0, w) for dy in (0, h)}
            | {
                (x - dx + gx, y - dy + gy)
                for polygon in obstacles
                for x, y in polygon
                for dx in (0, w)
                for dy in (0, h)
                for gx, gy in ((-1, -1), (-1, 1), (1, -1), (1, 1))
            }
        )
    )


def face_origins(
    a: PlacedRectangleV1, shape: AuthoritativeZoneShapeV1
) -> tuple[tuple[int, int], ...]:
    """Start/end/center shared-face events, all four sides."""
    return _face_origins_from_bounds(a.bounds_mm, shape)


def _face_origins_from_bounds(
    bounds: Bounds, shape: AuthoritativeZoneShapeV1
) -> tuple[tuple[int, int], ...]:
    left, d, r, t = bounds
    w, h = shape.world_width_mm, shape.world_depth_mm
    ys = {d, t - h, (d + t - h) // 2}
    xs = {left, r - w, (left + r - w) // 2}
    return tuple(
        sorted(
            {(x, y) for x in (left - w, r) for y in ys} | {(x, y) for y in (d - h, t) for x in xs}
        )
    )


def finite_pairs(
    roles: tuple[str, str],
    shapes: tuple[tuple[AuthoritativeZoneShapeV1, ...], tuple[AuthoritativeZoneShapeV1, ...]],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> Iterator[Pair]:
    """A-first union B-first; callers deduplicate using canonical role order."""
    for a, b, sa, sb in _finite_bound_pairs(shapes, boundary, obstacles):
        yield rectangle_at(roles[0], a[:2], sa), rectangle_at(roles[1], b[:2], sb), sa, sb


def _shape_bounds(origin: tuple[int, int], shape: AuthoritativeZoneShapeV1) -> Bounds:
    x, y = origin
    return x, y, x + shape.world_width_mm, y + shape.world_depth_mm


def _finite_bound_pairs(
    shapes: tuple[tuple[AuthoritativeZoneShapeV1, ...], tuple[AuthoritativeZoneShapeV1, ...]],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> Iterator[tuple[Bounds, Bounds, AuthoritativeZoneShapeV1, AuthoritativeZoneShapeV1]]:
    """Same exact event union, without repeatedly materializing Decimal rectangles."""
    origins_a = {s: frozenset(event_origins(s, boundary, obstacles)) for s in shapes[0]}
    for first in (0, 1):
        other = 1 - first
        for fs in shapes[first]:
            for origin in event_origins(fs, boundary, obstacles):
                fixed = _shape_bounds(origin, fs)
                for ss in shapes[other]:
                    for second_origin in _face_origins_from_bounds(fixed, ss):
                        partner = _shape_bounds(second_origin, ss)
                        if (
                            first == 1
                            and second_origin in origins_a[ss]
                            and origin in _face_origins_from_bounds(partner, fs)
                        ):
                            # Exact set-union duplicate, already emitted in A-first pass.
                            continue
                        yield (fixed, partner, fs, ss) if first == 0 else (partner, fixed, ss, fs)


def shared_edge(
    a: PlacedRectangleV1, b: PlacedRectangleV1
) -> tuple[str, tuple[tuple[int, int], tuple[int, int]], int]:
    if not rectangles_share_positive_edge(a, b):
        raise ValueError("NO_POSITIVE_SHARED_EDGE")
    left, d, r, t = a.bounds_mm
    bl, bd, br, bt = b.bounds_mm
    if r == bl or left == br:
        x = r if r == bl else left
        low, high = max(d, bd), min(t, bt)
        return ("EAST" if r == bl else "WEST", ((x, low), (x, high)), high - low)
    y = t if t == bd else d
    low, high = max(left, bl), min(r, br)
    return ("NORTH" if t == bd else "SOUTH", ((low, y), (high, y)), high - low)


@dataclass(frozen=True)
class PairwiseMetricDomainResultV1:
    roles: tuple[str, str]
    finite_domain_identity: str
    complete: bool
    evaluated: int
    valid_count: int
    slot_set_digest: str
    witnesses: tuple[Pair, ...]
    orientations: tuple[str, ...]
    rejections: tuple[tuple[str, int], ...]
    incomplete_reason: str | None


def evaluate_pair_domain(
    roles: tuple[str, str],
    shapes: tuple[tuple[AuthoritativeZoneShapeV1, ...], tuple[AuthoritativeZoneShapeV1, ...]],
    boundary: PolygonMM,
    obstacles: tuple[PolygonMM, ...],
    *,
    evaluation_cap: int = DEFAULT_PAIR_EVALUATION_CAP,
) -> PairwiseMetricDomainResultV1:
    if evaluation_cap < 0:
        raise ValueError("INVALID_METRIC_EVALUATION_CAP")
    # Canonicalize endpoint order independently of supplied orientation.
    if roles[0] > roles[1]:
        roles, shapes = (roles[1], roles[0]), (shapes[1], shapes[0])
    identity = canonical_hash(
        {
            "policy": DOMAIN_POLICY,
            "roles": roles,
            "shapes": [[asdict(s) for s in group] for group in shapes],
            "boundary": boundary,
            "hard_obstacles": obstacles,
        }
    )
    evaluated = valid_count = 0
    digest = sha256()
    witnesses: dict[str, Pair] = {}
    rejections: dict[str, int] = {}
    complete = True

    min_x, min_y = min(p[0] for p in boundary), min(p[1] for p in boundary)
    max_x, max_y = max(p[0] for p in boundary), max(p[1] for p in boundary)

    @lru_cache(maxsize=100_000)
    def unary(bounds: Bounds) -> tuple[str, PlacedRectangleV1 | None]:
        left, bottom, right, top = bounds
        # Necessary bbox rejection only. Every surviving/positive footprint
        # still passes the exact polygon and closed-obstacle predicates.
        if left < min_x or bottom < min_y or right > max_x or top > max_y:
            return "SITE", None
        rect = rectangle_at(
            "metric-physical-footprint",
            bounds[:2],
            AuthoritativeZoneShapeV1(right - left, top - bottom, 0),
        )
        return physical_status(rect, boundary, obstacles), rect

    for ba, bb, sa, sb in _finite_bound_pairs(shapes, boundary, obstacles):
        key = (ba, bb)
        if evaluated >= evaluation_cap:
            complete = False
            break
        evaluated += 1
        status, a = unary(ba)
        b = None
        if status == "VALID":
            status, b = unary(bb)
        if status == "VALID":
            assert a is not None and b is not None
            if rectangles_overlap(a, b):
                status = "PAIR_OVERLAP"
            elif not rectangles_share_positive_edge(a, b):
                status = "NO_POSITIVE_SHARED_EDGE"
        if status != "VALID":
            rejections[status] = rejections.get(status, 0) + 1
            continue
        valid_count += 1
        digest.update((str(key) + "\n").encode("ascii"))
        assert a is not None and b is not None
        side, _, _ = shared_edge(a, b)
        if side not in witnesses:
            witnesses[side] = (
                rectangle_at(roles[0], ba[:2], sa),
                rectangle_at(roles[1], bb[:2], sb),
                sa,
                sb,
            )
    if not all(shapes):
        complete = False
    reason = (
        None
        if complete
        else "AUTHORITY_SHAPE_DOMAIN_EMPTY"
        if not all(shapes)
        else "EVALUATION_CAP_EXHAUSTED"
    )
    return PairwiseMetricDomainResultV1(
        roles,
        identity,
        complete,
        evaluated,
        valid_count,
        "sha256:" + digest.hexdigest(),
        tuple(witnesses[k] for k in sorted(witnesses)),
        tuple(sorted(witnesses)),
        tuple(sorted(rejections.items())),
        reason,
    )


def realize_interface(
    reservation: MandatoryInterfaceReservationV1,
    domain: PairwiseMetricDomainResultV1,
    *,
    site_hash: str,
    dimension_identity: str,
    shape_counts: tuple[int, int],
    construction_counts: tuple[int, int],
) -> MetricInterfaceReservationV1:
    roles = (reservation.endpoint_a_role, reservation.endpoint_b_role)
    graph = process_graph()
    edge = tuple(sorted(roles))
    if (
        frozenset(roles) not in {frozenset(e) for e in graph.must_adjacencies}
        or reservation.source_graph_identity != graph.identity
        or reservation.interface_source_edge_identity != _mandatory_edge_identity(graph, edge)
    ):
        raise ValueError("NON_AUTHORITY_METRIC_RESERVATION")
    if tuple(sorted(roles)) != domain.roles:
        raise ValueError("METRIC_DOMAIN_ENDPOINT_MISMATCH")
    slots = []
    for a, b, sa, sb in domain.witnesses:
        if a.zone_code != roles[0]:
            a, b, sa, sb = b, a, sb, sa
        side, segment, length = shared_edge(a, b)
        slots.append(
            MetricAttachmentSlotV1(
                reservation.interface_source_edge_identity,
                *roles,
                canonical_hash(
                    {"authority": dimension_identity, "role": roles[0], "shape": asdict(sa)}
                ),
                canonical_hash(
                    {"authority": dimension_identity, "role": roles[1], "shape": asdict(sb)}
                ),
                a.bounds_mm,
                b.bounds_mm,
                sa,
                sb,
                side,
                segment,
                length,
                site_hash,
                dimension_identity,
                reservation.reservation_kind,
                reservation.host_a,
                reservation.host_b,
            )
        )
    status = (
        MetricReservationStatusV1.UNKNOWN
        if not domain.complete
        else MetricReservationStatusV1.NONEMPTY
        if domain.valid_count
        else MetricReservationStatusV1.EMPTY
    )
    return MetricInterfaceReservationV1(
        reservation.interface_source_edge_identity,
        canonical_hash(asdict(reservation)),
        *roles,
        METRIC_SCOPE,
        domain.finite_domain_identity,
        domain.complete,
        domain.evaluated,
        domain.valid_count,
        domain.slot_set_digest,
        tuple(slots),
        tuple(sorted({s.shared_edge_side for s in slots})),
        shape_counts,
        construction_counts,
        domain.rejections,
        domain.incomplete_reason,
        status,
    )


def verify_metric_replay(supplied: Any, expected: Any) -> None:
    """Artifacts are data, never authority: verify all provenance and result fields."""
    if type(supplied) is not type(expected) or canonical_hash(asdict(supplied)) != canonical_hash(
        asdict(expected)
    ):
        raise ValueError("METRIC_RESERVATION_REPLAY_MISMATCH")
