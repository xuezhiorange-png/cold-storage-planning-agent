"""Runtime-only complete P2 domains and branch-local advisory support.

This is a construction-domain invariant, never engineering infeasibility proof.
No representative slots or role-specific recovery are consumed here.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from functools import lru_cache
from hashlib import sha256
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.domain.authority_shapes import (
    AuthoritativeZoneShapeV1,
    authoritative_zone_shapes,
    canonical_construction_shapes,
)
from cold_storage.modules.layout.domain.composition_handoff import (
    StructuralCompositionPlacementHandoffV1,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.metric_interface_reservation import (
    DEFAULT_PAIR_EVALUATION_CAP,
    Bounds,
    PairwiseMetricDomainResultV1,
    evaluate_pair_domain,
    rectangle_at,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    normalize_polygon,
)
from cold_storage.modules.layout.domain.validated_site_obstacles import (
    validated_hard_obstacle_polygons,
)

type SlotKey = tuple[Bounds, Bounds, AuthoritativeZoneShapeV1, AuthoritativeZoneShapeV1]
type IntentPredicate = Callable[[Mapping[str, PlacedRectangleV1]], bool]


class MetricSupportStatusV1(StrEnum):
    SUPPORTED = "SUPPORTED"
    NONE = "NO_STATIC_EVENT_DOMAIN_MEMBER"
    UNKNOWN = "UNKNOWN_SUPPORT_DOMAIN"


@dataclass(frozen=True)
class MetricReservationSupportStateV1:
    source_edge_identity: str
    status: MetricSupportStatusV1
    support_index: int | None = None
    cursor: int = 0
    checked_slot_count: int = 0
    support_reused: bool = False


@dataclass(frozen=True)
class RuntimeMetricReservationDomainV1:
    source_edge_identity: str
    summary: PairwiseMetricDomainResultV1
    slots: tuple[SlotKey, ...]
    endpoint_indexes: tuple[Mapping[Bounds, tuple[int, ...]], Mapping[Bounds, tuple[int, ...]]]
    engineering_authority: bool = False

    def __post_init__(self) -> None:
        digest = sha256()
        for a, b, _, _ in self.slots:
            digest.update((str((a, b)) + "\n").encode("ascii"))
        if (
            self.engineering_authority
            or len(self.slots) != self.summary.valid_count
            or "sha256:" + digest.hexdigest() != self.summary.slot_set_digest
        ):
            raise ValueError("P2_RUNTIME_DOMAIN_PARITY_MISMATCH")

    def candidates(self, placed: Mapping[str, PlacedRectangleV1]) -> Sequence[int]:
        indexes = [
            self.endpoint_indexes[i].get(placed[role].bounds_mm, ())
            for i, role in enumerate(self.summary.roles)
            if role in placed
        ]
        return min(indexes, key=len) if indexes else range(len(self.slots))

    def proof(self, index: int) -> dict[str, object]:
        a, b, sa, sb = self.slots[index]
        return {
            "source_edge_identity": self.source_edge_identity,
            "roles": self.summary.roles,
            "endpoint_bounds_mm": (a, b),
            "endpoint_shapes": (asdict(sa), asdict(sb)),
            "slot_identity": canonical_hash(
                (self.source_edge_identity, a, b, asdict(sa), asdict(sb))
            ),
            "p2_domain_member": True,
        }


@lru_cache(maxsize=7)
def build_runtime_domain(
    edge_identity: str,
    roles: tuple[str, str],
    shapes: tuple[tuple[AuthoritativeZoneShapeV1, ...], tuple[AuthoritativeZoneShapeV1, ...]],
    boundary: PolygonMM,
    obstacles: tuple[PolygonMM, ...],
    *,
    evaluation_cap: int = DEFAULT_PAIR_EVALUATION_CAP,
) -> RuntimeMetricReservationDomainV1:
    slots: list[SlotKey] = []
    # The P2 evaluator owns all enumeration, hard predicates, order and cap.
    summary = evaluate_pair_domain(
        roles, shapes, boundary, obstacles, slot_sink=slots.append, evaluation_cap=evaluation_cap
    )
    indexes: tuple[dict[Bounds, list[int]], dict[Bounds, list[int]]] = ({}, {})
    for index, slot in enumerate(slots):
        for endpoint, bounds in enumerate((slot[0], slot[1])):
            indexes[endpoint].setdefault(bounds, []).append(index)
    return RuntimeMetricReservationDomainV1(
        edge_identity,
        summary,
        tuple(slots),
        (
            MappingProxyType({b: tuple(v) for b, v in indexes[0].items()}),
            MappingProxyType({b: tuple(v) for b, v in indexes[1].items()}),
        ),
    )


@dataclass(frozen=True)
class MetricRuntimeContextV1:
    source_site_geometry_hash: str
    source_dimension_authorities_hash: str
    handoff_hashes: tuple[str, ...]
    domains: tuple[RuntimeMetricReservationDomainV1, ...]


def build_metric_runtime_context(
    handoffs: Sequence[StructuralCompositionPlacementHandoffV1],
    authorities: Mapping[str, Mapping[str, Any]],
    site_payload: Mapping[str, Any],
    site_hash: str,
) -> MetricRuntimeContextV1:
    boundary = normalize_polygon(
        site_payload["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = validated_hard_obstacle_polygons(site_payload)
    shapes = authoritative_zone_shapes(authorities, boundary, obstacles)
    construction = {role: canonical_construction_shapes(values) for role, values in shapes.items()}
    domains = {}
    for handoff in handoffs:
        for reservation in handoff.mandatory_interface_reservations:
            edge = reservation.interface_source_edge_identity
            if edge not in domains:
                roles = (reservation.endpoint_a_role, reservation.endpoint_b_role)
                domains[edge] = build_runtime_domain(
                    edge,
                    roles,
                    (construction[roles[0]], construction[roles[1]]),
                    boundary,
                    obstacles,
                )
    return MetricRuntimeContextV1(
        site_hash,
        canonical_hash(authorities),
        tuple(h.canonical_result_hash for h in handoffs),
        tuple(domains.values()),
    )


def _overlap(a: Bounds, b: Bounds) -> bool:
    """Integer form of rectangles_overlap; the same exact positive-area relation."""
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _edge(a: Bounds, b: Bounds) -> bool:
    """Integer form of the existing positive shared-edge predicate (no new threshold)."""
    return ((a[2] == b[0] or b[2] == a[0]) and min(a[3], b[3]) > max(a[1], b[1])) or (
        (a[3] == b[1] or b[3] == a[1]) and min(a[2], b[2]) > max(a[0], b[0])
    )


@dataclass
class MetricSupportDiagnosticsV1:
    by_edge: dict[str, dict[str, int]] = field(default_factory=dict)
    sequence_digest: Any = field(default_factory=sha256, repr=False)

    def count(self, edge: str, event: str, index: int | None = None) -> None:
        counts = self.by_edge.setdefault(edge, {})
        counts[event] = counts.get(event, 0) + 1
        self.sequence_digest.update(f"{edge}|{event}|{index}\n".encode())

    def to_dict(self) -> dict[str, object]:
        return {"by_edge": self.by_edge, "sequence_digest": self.sequence_digest.hexdigest()}


class MetricReservationSupportQueryV1:
    """Legacy static-membership diagnostic, NOT a conditional capacity authority.

    Production placement uses ConditionalMetricSupportQueryV2. NONE here means
    only no static-domain member and must never authorize a placement prune.
    """

    def __init__(
        self,
        domains: tuple[RuntimeMetricReservationDomainV1, ...],
        must_edges: Sequence[tuple[str, str]],
        intent_possible: IntentPredicate,
    ) -> None:
        self.domains = domains
        self.must_edges = tuple(must_edges)
        self.intent_possible = intent_possible
        self.diagnostics = MetricSupportDiagnosticsV1()
        self.rectangles: dict[tuple[str, Bounds], PlacedRectangleV1] = {}

    def compatible(
        self,
        domain: RuntimeMetricReservationDomainV1,
        index: int,
        placed: Mapping[str, PlacedRectangleV1],
        fixed_bounds: Mapping[str, Bounds] | None = None,
    ) -> bool:
        if fixed_bounds is None:
            fixed_bounds = {role: rectangle.bounds_mm for role, rectangle in placed.items()}
        slot = domain.slots[index]
        roles = domain.summary.roles
        provisional = dict(zip(roles, (slot[0], slot[1]), strict=True))
        shapes = dict(zip(roles, (slot[2], slot[3]), strict=True))
        for role, bounds in provisional.items():
            if role in fixed_bounds and fixed_bounds[role] != bounds:
                return False
            if any(
                _overlap(bounds, fixed) for other, fixed in fixed_bounds.items() if other != role
            ):
                return False
        combined = dict(fixed_bounds)
        combined.update(provisional)
        if any(
            a in combined and b in combined and not _edge(combined[a], combined[b])
            for a, b in self.must_edges
        ):
            return False
        temporary = dict(placed)
        for role, bounds in provisional.items():
            key = role, bounds
            if key not in self.rectangles:
                self.rectangles[key] = rectangle_at(role, bounds[:2], shapes[role])
            temporary[role] = self.rectangles[key]
        return self.intent_possible(temporary)

    def update(
        self,
        placed: Mapping[str, PlacedRectangleV1],
        parent: tuple[MetricReservationSupportStateV1, ...] = (),
    ) -> tuple[MetricReservationSupportStateV1, ...]:
        if parent and len(parent) != len(self.domains):
            raise ValueError("METRIC_SUPPORT_PARENT_COVERAGE_MISMATCH")
        # Fixed geometry is identical throughout this query. Avoid repeating
        # Decimal-to-mm conversion for every alternative in the complete domain.
        fixed_bounds = {role: rectangle.bounds_mm for role, rectangle in placed.items()}
        self.diagnostics.sequence_digest.update((canonical_hash(fixed_bounds) + "\n").encode())
        states = []
        for i, domain in enumerate(self.domains):
            edge = domain.source_edge_identity
            counts = self.diagnostics
            counts.count(edge, "checks")
            previous = parent[i] if parent else None
            if previous is not None and previous.source_edge_identity != edge:
                raise ValueError("METRIC_SUPPORT_PARENT_PROVENANCE_MISMATCH")
            checked = 0
            cursor = previous.cursor if previous else 0
            if previous is not None and previous.support_index is not None:
                counts.count(edge, "slot_evaluations")
                checked += 1
                if self.compatible(domain, previous.support_index, placed, fixed_bounds):
                    counts.count(edge, "reuse", previous.support_index)
                    states.append(
                        MetricReservationSupportStateV1(
                            edge,
                            MetricSupportStatusV1.SUPPORTED,
                            previous.support_index,
                            previous.support_index,
                            checked,
                            True,
                        )
                    )
                    continue
                counts.count(edge, "invalidations", previous.support_index)
                cursor = previous.support_index + 1
            counts.count(edge, "rescans")
            candidates = domain.candidates(placed)
            start = bisect_left(candidates, cursor)
            support = None
            for index in candidates[start:]:
                counts.count(edge, "slot_evaluations")
                checked += 1
                if self.compatible(domain, index, placed, fixed_bounds):
                    support = index
                    break
            if support is not None:
                counts.count(edge, "support", support)
                if previous is not None and previous.support_index is not None:
                    counts.count(edge, "migrations", support)
                states.append(
                    MetricReservationSupportStateV1(
                        edge, MetricSupportStatusV1.SUPPORTED, support, support, checked
                    )
                )
            else:
                status = (
                    MetricSupportStatusV1.NONE
                    if domain.summary.complete
                    else MetricSupportStatusV1.UNKNOWN
                )
                counts.count(edge, "proved_none" if domain.summary.complete else "unknown")
                states.append(
                    MetricReservationSupportStateV1(edge, status, None, len(domain.slots), checked)
                )
        return tuple(states)

    def support_candidates(
        self,
        role: str,
        placed: Mapping[str, PlacedRectangleV1],
        states: tuple[MetricReservationSupportStateV1, ...],
    ) -> tuple[tuple[AuthoritativeZoneShapeV1, tuple[int, int]], ...]:
        candidates = []
        for domain, state in zip(self.domains, states, strict=True):
            roles = domain.summary.roles
            if role not in roles or state.support_index is None:
                continue
            if sum(r in placed for r in roles) != 1 or role in placed:
                continue
            i = roles.index(role)
            slot = domain.slots[state.support_index]
            key = (slot[2], slot[3])[i], (slot[0], slot[1])[i][:2]
            if key not in candidates:
                candidates.append(key)
        return tuple(candidates)

    def consumed(
        self,
        placed: Mapping[str, PlacedRectangleV1],
        states: tuple[MetricReservationSupportStateV1, ...],
    ) -> bool:
        return len(states) == len(self.domains) and all(
            state.status == MetricSupportStatusV1.SUPPORTED
            and state.support_index is not None
            and all(role in placed for role in domain.summary.roles)
            and self.compatible(domain, state.support_index, placed)
            for domain, state in zip(self.domains, states, strict=True)
        )

    def candidate_event(
        self,
        event: str,
        role: str,
        candidate: tuple[AuthoritativeZoneShapeV1, tuple[int, int]],
        placed: Mapping[str, PlacedRectangleV1],
        states: tuple[MetricReservationSupportStateV1, ...],
    ) -> None:
        for domain, state in zip(self.domains, states, strict=True):
            if candidate in MetricReservationSupportQueryV1(
                (domain,), self.must_edges, self.intent_possible
            ).support_candidates(role, placed, (state,)):
                self.diagnostics.count(domain.source_edge_identity, event, state.support_index)
