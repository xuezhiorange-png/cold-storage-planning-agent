"""Conditional pair certificates; event-domain absence is never a negative proof.

The analytic negative uses a necessary superset of ALL integer-mm origins for
the unchanged canonical construction footprints, not an event enumeration.
Pairwise certificates are explicitly not a joint unplaced-role assignment.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from itertools import islice
from typing import Any

from cold_storage.modules.layout.domain.authority_shapes import (
    AuthoritativeZoneShapeV1 as Shape,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.metric_interface_reservation import (
    Bounds,
    physical_status,
    rectangle_at,
)
from cold_storage.modules.layout.domain.metric_reservation_consumption import (
    IntentPredicate,
    MetricSupportDiagnosticsV1,
    RuntimeMetricReservationDomainV1,
    SlotKey,
    _edge,
    _overlap,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
)

REVISION = "conditional-metric-certificate@2.0.0"
type OriginProvider = Callable[
    [str, Shape, Mapping[str, PlacedRectangleV1]], Sequence[tuple[int, int]]
]
type OriginBox = tuple[int, int, int, int]  # inclusive INTEGER origin coordinates


class ConditionalSupportStatusV2(StrEnum):
    SUPPORTED = "SUPPORTED"
    NONE = "PROVED_NO_SUPPORT"
    UNKNOWN = "UNKNOWN_SUPPORT"


@dataclass(frozen=True)
class ConditionalMetricCertificateV2:
    source_edge_identity: str
    domain_identity: str
    roles: tuple[str, str]
    slot: SlotKey
    source: str
    engineering_authority: bool = False
    joint_unplaced_role_capacity_proven: bool = False

    def proof(self) -> dict[str, object]:
        a, b, sa, sb = self.slot
        return {
            "source_edge_identity": self.source_edge_identity,
            "roles": self.roles,
            "endpoint_bounds_mm": (a, b),
            "endpoint_shapes": (asdict(sa), asdict(sb)),
            "slot_identity": canonical_hash(
                (self.source_edge_identity, a, b, asdict(sa), asdict(sb))
            ),
            "conditional_domain_identity": self.domain_identity,
            "certificate_source": self.source,
            "engineering_authority": False,
            "joint_unplaced_role_capacity_proven": False,
        }


@dataclass(frozen=True)
class NegativeGeometryCertificateV2:
    source_edge_identity: str
    domain_identity: str
    endpoint_role: str
    proof_kind: str
    construction_shape_count: int
    coverage_scope: str = "ALL_INTEGER_ORIGINS_FOR_CANONICAL_CONSTRUCTION_FOOTPRINTS"


@dataclass(frozen=True)
class ConditionalMetricSupportStateV2:
    source_edge_identity: str
    status: ConditionalSupportStatusV2
    domain_identity: str
    certificate: ConditionalMetricCertificateV2 | None = None
    negative_certificate: NegativeGeometryCertificateV2 | None = None
    checked_slot_count: int = 0
    support_reused: bool = False


def intersect(a: OriginBox, b: OriginBox) -> OriginBox | None:
    c = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return c if c[0] <= c[2] and c[1] <= c[3] else None


def subtract(a: OriginBox, b: OriginBox) -> tuple[OriginBox, ...]:
    """Exact integer-lattice box subtraction, without coordinate sampling."""
    c = intersect(a, b)
    if c is None:
        return (a,)
    x, y, r, t = c
    pieces = (
        (a[0], a[1], x - 1, a[3]),
        (r + 1, a[1], a[2], a[3]),
        (x, a[1], r, y - 1),
        (x, t + 1, r, a[3]),
    )
    return tuple(p for p in pieces if p[0] <= p[2] and p[1] <= p[3])


def necessary_origin_boxes(
    role: str,
    shape: Shape,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    must_edges: Sequence[tuple[str, str]],
    *,
    box_cap: int = 8192,
) -> tuple[OriginBox, ...] | None:
    """Conservative relaxation: bbox + fixed-room overlap + ALL fixed MUST.

    Ignores polygon concavity, obstacles and intent, enlarging capacity. Empty
    therefore proves impossibility even if FUTURE event origins are introduced.
    Resource overflow returns None, never an empty domain/negative certificate.
    """
    w, h = shape.world_width_mm, shape.world_depth_mm
    start = (
        min(x for x, _ in boundary),
        min(y for _, y in boundary),
        max(x for x, _ in boundary) - w,
        max(y for _, y in boundary) - h,
    )
    boxes: tuple[OriginBox, ...] = (start,) if start[0] <= start[2] and start[1] <= start[3] else ()
    for other, rect in placed.items():
        if other == role:
            continue
        left, bottom, right, top = rect.bounds_mm
        forbidden = (left - w + 1, bottom - h + 1, right - 1, top - 1)
        boxes = tuple(p for box in boxes for p in subtract(box, forbidden))
        if len(boxes) > box_cap:
            return None
    for a, b in must_edges:
        neighbor = b if a == role else a if b == role else None
        if neighbor is None or neighbor not in placed:
            continue
        left, bottom, right, top = placed[neighbor].bounds_mm
        faces = (
            (left - w, bottom - h + 1, left - w, top - 1),
            (right, bottom - h + 1, right, top - 1),
            (left - w + 1, bottom - h, right - 1, bottom - h),
            (left - w + 1, top, right - 1, top),
        )
        boxes = tuple(
            c for box in boxes for face in faces if (c := intersect(box, face)) is not None
        )
        if len(boxes) > box_cap:
            return None
    return boxes


class ConditionalMetricSupportQueryV2:
    """Server-owned authority, immutable branch proofs; no inherited negative cursor."""

    def __init__(
        self,
        domains: tuple[RuntimeMetricReservationDomainV1, ...],
        must_edges: Sequence[tuple[str, str]],
        intent_possible: IntentPredicate,
        *,
        shapes: Mapping[str, tuple[Shape, ...]],
        boundary: PolygonMM,
        obstacles: Sequence[PolygonMM],
        origin_provider: OriginProvider,
        provenance: Mapping[str, Any],
        static_cap: int = 256,
        dynamic_cap: int = 256,
    ) -> None:
        self.domains, self.must_edges, self.intent_possible = (
            domains,
            tuple(must_edges),
            intent_possible,
        )
        self.shapes, self.boundary, self.obstacles = shapes, boundary, tuple(obstacles)
        self.origin_provider = origin_provider
        self.authority_identity = canonical_hash(
            (
                REVISION,
                provenance,
                {r: [asdict(s) for s in values] for r, values in shapes.items()},
                boundary,
                obstacles,
            )
        )
        self.static_cap, self.dynamic_cap = static_cap, dynamic_cap
        self.diagnostics = MetricSupportDiagnosticsV1()
        self.physical_cache: dict[Bounds, bool] = {}
        self.rectangle_cache: dict[tuple[str, Bounds], PlacedRectangleV1] = {}

    def identity(self, edge: str, placed: Mapping[str, PlacedRectangleV1]) -> str:
        return canonical_hash(
            (self.authority_identity, edge, {r: p.bounds_mm for r, p in placed.items()})
        )

    def rectangle(self, role: str, bounds: Bounds, shape: Shape) -> PlacedRectangleV1:
        key = role, bounds
        if key not in self.rectangle_cache:
            self.rectangle_cache[key] = rectangle_at(role, bounds[:2], shape)
        return self.rectangle_cache[key]

    def compatible(
        self,
        roles: tuple[str, str],
        slot: SlotKey,
        placed: Mapping[str, PlacedRectangleV1],
    ) -> bool:
        provisional = dict(zip(roles, slot[:2], strict=True))
        for role, bounds, shape in zip(roles, slot[:2], slot[2:], strict=True):
            if shape not in self.shapes[role]:
                return False
            if (bounds[2] - bounds[0], bounds[3] - bounds[1]) != (
                shape.world_width_mm,
                shape.world_depth_mm,
            ):
                return False
            if role in placed and placed[role].bounds_mm != bounds:
                return False
            if any(_overlap(bounds, p.bounds_mm) for other, p in placed.items() if other != role):
                return False
            if bounds not in self.physical_cache:
                self.physical_cache[bounds] = (
                    physical_status(
                        self.rectangle(role, bounds, shape),
                        self.boundary,
                        self.obstacles,
                    )
                    == "VALID"
                )
            if not self.physical_cache[bounds]:
                return False
        if _overlap(slot[0], slot[1]) or not _edge(slot[0], slot[1]):
            return False
        combined = {r: p.bounds_mm for r, p in placed.items()} | provisional
        if any(
            a in combined and b in combined and not _edge(combined[a], combined[b])
            for a, b in self.must_edges
        ):
            return False
        temp = dict(placed)
        for role, bounds, shape in zip(roles, slot[:2], slot[2:], strict=True):
            temp[role] = self.rectangle(role, bounds, shape)
        return self.intent_possible(temp)

    def fixed_shape(self, role: str, placed: Mapping[str, PlacedRectangleV1]) -> Shape | None:
        b = placed[role].bounds_mm
        return next(
            (
                s
                for s in self.shapes[role]
                if (s.world_width_mm, s.world_depth_mm) == (b[2] - b[0], b[3] - b[1])
            ),
            None,
        )

    def dynamic_slots(
        self, roles: tuple[str, str], placed: Mapping[str, PlacedRectangleV1]
    ) -> Iterator[SlotKey | None]:
        # Both directions; placed MUST connectivity only affects ordering.
        firsts = sorted(
            (0, 1),
            key=lambda j: (
                roles[j] not in placed,
                not any(
                    roles[j] in edge and any(r in placed for r in edge if r != roles[j])
                    for edge in self.must_edges
                ),
                j,
            ),
        )
        for first in firsts:
            second = 1 - first
            ar, br = roles[first], roles[second]
            a_shapes = (self.fixed_shape(ar, placed),) if ar in placed else self.shapes[ar]
            for sa in a_shapes:
                if sa is None:
                    continue
                origins = (
                    (placed[ar].bounds_mm[:2],)
                    if ar in placed
                    else self.origin_provider(ar, sa, placed)
                )
                for origin in origins:
                    yield None  # Count every first-endpoint expansion against query cap.
                    a = rectangle_at(ar, origin, sa)
                    if physical_status(a, self.boundary, self.obstacles) != "VALID" or any(
                        _overlap(a.bounds_mm, p.bounds_mm) for r, p in placed.items() if r != ar
                    ):
                        continue
                    temp = dict(placed)
                    temp[ar] = a
                    b_shapes = (self.fixed_shape(br, placed),) if br in placed else self.shapes[br]
                    for sb in b_shapes:
                        if sb is None:
                            continue
                        b_origins = (
                            (placed[br].bounds_mm[:2],)
                            if br in placed
                            else self.origin_provider(br, sb, temp)
                        )
                        for bo in b_origins:
                            b = rectangle_at(br, bo, sb)
                            yield (
                                (a.bounds_mm, b.bounds_mm, sa, sb)
                                if first == 0
                                else (b.bounds_mm, a.bounds_mm, sb, sa)
                            )

    def negative(
        self,
        domain: RuntimeMetricReservationDomainV1,
        placed: Mapping[str, PlacedRectangleV1],
    ) -> NegativeGeometryCertificateV2 | None:
        for role in domain.summary.roles:
            if role in placed:
                continue
            # A complete analytic cover of a SUPERSET, across every construction
            # footprint. Empty lists of authority shapes cannot prove anything.
            if self.shapes[role] and all(
                necessary_origin_boxes(role, s, placed, self.boundary, self.must_edges) == ()
                for s in self.shapes[role]
            ):
                return NegativeGeometryCertificateV2(
                    domain.source_edge_identity,
                    self.identity(domain.source_edge_identity, placed),
                    role,
                    "EMPTY_NECESSARY_ORIGIN_SPACE",
                    len(self.shapes[role]),
                )
        return None

    def verify_negative(
        self,
        proof: NegativeGeometryCertificateV2,
        domain: RuntimeMetricReservationDomainV1,
        placed: Mapping[str, PlacedRectangleV1],
    ) -> None:
        if proof != self.negative(domain, placed):
            raise ValueError("UNSOUND_OR_STALE_NEGATIVE_CERTIFICATE")

    def update(
        self,
        placed: Mapping[str, PlacedRectangleV1],
        parent: tuple[ConditionalMetricSupportStateV2, ...] = (),
    ) -> tuple[ConditionalMetricSupportStateV2, ...]:
        if parent and len(parent) != len(self.domains):
            raise ValueError("CONDITIONAL_PARENT_COVERAGE_MISMATCH")
        states = []
        for j, domain in enumerate(self.domains):
            edge, roles = domain.source_edge_identity, domain.summary.roles
            identity = self.identity(edge, placed)
            count = self.diagnostics.count
            count(edge, "checks")
            old = parent[j] if parent else None
            if old and old.source_edge_identity != edge:
                raise ValueError("CONDITIONAL_PARENT_PROVENANCE_MISMATCH")
            checked = 0
            certificate = None
            reused = False
            if all(r in placed for r in roles):
                sa, sb = (self.fixed_shape(r, placed) for r in roles)
                if sa is not None and sb is not None:
                    direct_slot = (
                        placed[roles[0]].bounds_mm,
                        placed[roles[1]].bounds_mm,
                        sa,
                        sb,
                    )
                    checked += 1
                    count(edge, "direct_pair_evaluations")
                    if self.compatible(roles, direct_slot, placed):
                        certificate = ConditionalMetricCertificateV2(
                            edge, identity, roles, direct_slot, "DIRECT_FINAL"
                        )
            elif old and old.certificate:
                checked += 1
                count(edge, "reuse_evaluations")
                if self.compatible(roles, old.certificate.slot, placed):
                    reused = True
                    certificate = ConditionalMetricCertificateV2(
                        edge, identity, roles, old.certificate.slot, old.certificate.source
                    )
                    count(edge, "reuse")
            if certificate is None and not all(r in placed for r in roles):
                if old and old.certificate:
                    count(edge, "invalidations")
                count(edge, "rescans")
                for idx in islice(domain.candidates(placed), self.static_cap):
                    checked += 1
                    count(edge, "static_pair_evaluations")
                    if self.compatible(roles, domain.slots[idx], placed):
                        certificate = ConditionalMetricCertificateV2(
                            edge, identity, roles, domain.slots[idx], "STATIC_POSITIVE"
                        )
                        break
                if certificate is None:
                    for slot in islice(self.dynamic_slots(roles, placed), self.dynamic_cap):
                        checked += 1
                        count(
                            edge,
                            "dynamic_origin_evaluations"
                            if slot is None
                            else "dynamic_pair_evaluations",
                        )
                        if slot is not None and self.compatible(roles, slot, placed):
                            certificate = ConditionalMetricCertificateV2(
                                edge, identity, roles, slot, "DYNAMIC_POSITIVE"
                            )
                            break
            for _ in range(checked):
                count(edge, "slot_evaluations")
            if certificate:
                count(edge, certificate.source.lower())
                if old and old.certificate and old.certificate.slot != certificate.slot:
                    count(edge, "migrations")
                states.append(
                    ConditionalMetricSupportStateV2(
                        edge,
                        ConditionalSupportStatusV2.SUPPORTED,
                        identity,
                        certificate,
                        checked_slot_count=checked,
                        support_reused=reused,
                    )
                )
                continue
            proof = self.negative(domain, placed)
            if proof:
                self.verify_negative(proof, domain, placed)
                count(edge, "proved_none")
                states.append(
                    ConditionalMetricSupportStateV2(
                        edge,
                        ConditionalSupportStatusV2.NONE,
                        identity,
                        negative_certificate=proof,
                        checked_slot_count=checked,
                    )
                )
            else:
                count(edge, "unknown")
                states.append(
                    ConditionalMetricSupportStateV2(
                        edge,
                        ConditionalSupportStatusV2.UNKNOWN,
                        identity,
                        checked_slot_count=checked,
                    )
                )
        return tuple(states)

    def support_candidates(
        self,
        role: str,
        placed: Mapping[str, PlacedRectangleV1],
        states: tuple[ConditionalMetricSupportStateV2, ...],
    ) -> tuple[tuple[Shape, tuple[int, int]], ...]:
        keys: list[tuple[Shape, tuple[int, int]]] = []
        for state in states:
            cert = state.certificate
            if (
                cert is None
                or role not in cert.roles
                or sum(r in placed for r in cert.roles) != 1
                or role in placed
            ):
                continue
            if cert.domain_identity != self.identity(cert.source_edge_identity, placed):
                continue
            i = cert.roles.index(role)
            key = cert.slot[2:][i], cert.slot[:2][i][:2]
            if key not in keys:
                keys.append(key)
        return tuple(keys)

    def candidate_event(
        self,
        event: str,
        role: str,
        candidate: tuple[Shape, tuple[int, int]],
        placed: Mapping[str, PlacedRectangleV1],
        states: tuple[ConditionalMetricSupportStateV2, ...],
    ) -> None:
        for state in states:
            if candidate in self.support_candidates(role, placed, (state,)):
                self.diagnostics.count(state.source_edge_identity, event)

    def consumed(
        self,
        placed: Mapping[str, PlacedRectangleV1],
        states: tuple[ConditionalMetricSupportStateV2, ...],
    ) -> bool:
        return len(states) == len(self.domains) and all(
            state.status == ConditionalSupportStatusV2.SUPPORTED
            and state.certificate is not None
            and state.certificate.source == "DIRECT_FINAL"
            and state.domain_identity == self.identity(domain.source_edge_identity, placed)
            and all(r in placed for r in domain.summary.roles)
            and self.compatible(domain.summary.roles, state.certificate.slot, placed)
            for domain, state in zip(self.domains, states, strict=True)
        )
