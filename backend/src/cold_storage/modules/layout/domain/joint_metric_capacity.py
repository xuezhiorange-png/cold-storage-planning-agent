"""Exact positive certificates for connected HARD components, never event absence proofs.

The finite witness probe is deliberately incomplete. Exhaustion is UNKNOWN.
Only revalidated necessary-origin contradictions under real placed rooms prune.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256

from cold_storage.modules.layout.domain.authority_shapes import AuthoritativeZoneShapeV1 as Shape
from cold_storage.modules.layout.domain.conditional_metric_support import (
    ConditionalMetricSupportQueryV2,
    ConditionalMetricSupportStateV2,
    NegativeGeometryCertificateV2,
    OriginBox,
    intersect,
    necessary_origin_boxes,
    subtract,
)
from cold_storage.modules.layout.domain.conditional_metric_support import (
    ConditionalSupportStatusV2 as Status,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.metric_interface_reservation import Bounds, physical_status
from cold_storage.modules.layout.domain.metric_reservation_consumption import _edge, _overlap
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

REVISION = "connected-hard-component-positive-proof@1.1.0"
type Assignment = tuple[tuple[str, Bounds, Shape], ...]
type ShapeOriginSpaces = tuple[tuple[Shape, OriginBox], ...]


def _coalesce_origin_spaces(values: Sequence[tuple[Shape, OriginBox]]) -> ShapeOriginSpaces:
    """Exact integer strip union, not a bbox approximation or point sampling."""
    grouped: dict[Shape, list[OriginBox]] = defaultdict(list)
    for shape, box in values:
        grouped[shape].append(box)
    result: list[tuple[Shape, OriginBox]] = []
    for shape, boxes in grouped.items():
        for axis in (0, 1, 0, 1):
            strips: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
            for box in boxes:
                strips[box[1 - axis], box[3 - axis]].append((box[axis], box[axis + 2]))
            boxes = []
            for fixed, intervals in sorted(strips.items()):
                merged: list[tuple[int, int]] = []
                for low, high in sorted(intervals):
                    if merged and low <= merged[-1][1] + 1:
                        merged[-1] = merged[-1][0], max(high, merged[-1][1])
                    else:
                        merged.append((low, high))
                for low, high in merged:
                    boxes.append(
                        (low, fixed[0], high, fixed[1])
                        if axis == 0
                        else (fixed[0], low, fixed[1], high)
                    )
        result.extend((shape, box) for box in sorted(set(boxes)))
    return tuple(result)


@dataclass(frozen=True)
class JointMetricCapacityCertificateV1:
    source_graph_identity: str
    source_reservation_identities: tuple[str, ...]
    authority_identity: str
    partial_geometry_identity: str
    domain_identity: str
    assignment: Assignment
    hard_edges: tuple[tuple[str, str], ...]
    coverage_scope: str = "CONNECTED_HARD_COMPONENT_JOINTLY_SUPPORTED"
    engineering_authority: bool = False

    def proof(self) -> dict[str, object]:
        geometries = {r: b for r, b, _ in self.assignment}
        body = {
            "source_graph_identity": self.source_graph_identity,
            "source_reservation_identities": self.source_reservation_identities,
            "authority_identity": self.authority_identity,
            "partial_geometry_identity": self.partial_geometry_identity,
            "domain_identity": self.domain_identity,
            "dynamic_domain_revision": REVISION,
            "assignment": [
                {"role": r, "bounds_mm": b, "shape": asdict(s)} for r, b, s in self.assignment
            ],
            "edge_checks": [
                {"roles": (a, b), "positive_shared_edge_valid": _edge(geometries[a], geometries[b])}
                for a, b in self.hard_edges
            ],
            "coverage_scope": self.coverage_scope,
            "site_valid": True,
            "hard_obstacles_clear": True,
            "pairwise_non_overlap_valid": True,
            "all_placed_must_neighbors_valid": True,
            "composition_intent_valid": True,
            "fixed_endpoint_geometry_matches": True,
            "engineering_authority": False,
            "whole_building_feasibility_proven": False,
        }
        return {**body, "certificate_identity": canonical_hash(body)}


@dataclass(frozen=True)
class JointMetricSupportStateV1:
    roles: tuple[str, ...]
    source_reservation_identities: tuple[str, ...]
    status: Status
    domain_identity: str
    certificate: JointMetricCapacityCertificateV1 | None = None
    negative_certificate: (
        NegativeGeometryCertificateV2 | JointNecessarySpaceCertificateV1 | None
    ) = None
    reason: str = "JOINT_ASSIGNMENT_UNPROVEN"
    checked_candidate_count: int = 0


@dataclass(frozen=True)
class JointNecessarySpaceCertificateV1:
    domain_identity: str
    proof_kind: str
    roles: tuple[str, ...]
    necessary_space_digest: str
    coverage_scope: str = "ALL_INTEGER_ORIGINS_FOR_CANONICAL_CONSTRUCTION_FOOTPRINTS"


class JointMetricCapacityQueryV1:
    """Unify shared variables; immutable output, fresh proof checks, no negative cache."""

    proof_scope = "PER_CONNECTED_HARD_COMPONENT"

    def __init__(
        self,
        pairwise: ConditionalMetricSupportQueryV2,
        *,
        graph_identity: str,
        evaluation_cap: int = 256,
        event_cap: int = 1024,
    ) -> None:
        self.pairwise = pairwise
        self.graph_identity = graph_identity
        self.evaluation_cap, self.event_cap = evaluation_cap, event_cap
        self.edges = pairwise.must_edges
        if {frozenset(e) for e in self.edges} != {
            frozenset(d.summary.roles) for d in pairwise.domains
        }:
            raise ValueError("JOINT_RESERVATION_AUTHORITY_COVERAGE_MISMATCH")
        adjacency: dict[str, set[str]] = {}
        for a, b in self.edges:
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
        self.neighbors = adjacency
        remaining = set(adjacency)
        components = []
        while remaining:
            todo = [min(remaining)]
            component: set[str] = set()
            while todo:
                r = todo.pop()
                if r in component:
                    continue
                component.add(r)
                todo.extend(sorted(adjacency[r] - component, reverse=True))
            remaining -= component
            components.append(tuple(sorted(component)))
        self.components = tuple(components)
        self.counts: Counter[str] = Counter()
        self.by_edge: dict[str, Counter[str]] = {}
        self.sequence = sha256()
        self.positive_cache: dict[tuple[str, ...], JointMetricCapacityCertificateV1] = {}

    def identity(self, roles: tuple[str, ...], placed: Mapping[str, PlacedRectangleV1]) -> str:
        return canonical_hash(
            (REVISION, self.graph_identity, roles, self.pairwise.identity("joint", placed))
        )

    def edge_ids(self, roles: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            d.source_edge_identity
            for d in self.pairwise.domains
            if set(d.summary.roles) <= set(roles)
        )

    def verify(
        self,
        certificate: JointMetricCapacityCertificateV1,
        placed: Mapping[str, PlacedRectangleV1],
    ) -> bool:
        q = self.pairwise
        roles = tuple(r for r, _, _ in certificate.assignment)
        edges = tuple(e for e in self.edges if set(e) <= set(roles))
        if (
            roles not in self.components
            or len(roles) != len(set(roles))
            or certificate.source_graph_identity != self.graph_identity
            or certificate.source_reservation_identities != self.edge_ids(roles)
            or certificate.authority_identity != q.authority_identity
            or certificate.partial_geometry_identity != q.identity("partial", placed)
            or certificate.domain_identity != self.identity(roles, placed)
            or certificate.hard_edges != edges
            or certificate.coverage_scope != "CONNECTED_HARD_COMPONENT_JOINTLY_SUPPORTED"
            or certificate.engineering_authority
        ):
            return False
        combined = dict(placed)
        shapes = {}
        for role, bounds, shape in certificate.assignment:
            if (
                shape not in q.shapes[role]
                or (bounds[2] - bounds[0], bounds[3] - bounds[1])
                != (shape.world_width_mm, shape.world_depth_mm)
                or role in placed
                and placed[role].bounds_mm != bounds
            ):
                return False
            combined[role] = q.rectangle(role, bounds, shape)
            shapes[role] = shape
        # Reuse the current exact pair validator with the WHOLE common assignment.
        # This checks physical authority, all overlaps, every fixed MUST and intent.
        return all(
            q.compatible(
                (a, b),
                (combined[a].bounds_mm, combined[b].bounds_mm, shapes[a], shapes[b]),
                combined,
            )
            for a, b in edges
        )

    def negative(
        self, roles: tuple[str, ...], placed: Mapping[str, PlacedRectangleV1]
    ) -> NegativeGeometryCertificateV2 | JointNecessarySpaceCertificateV1 | None:
        for domain in self.pairwise.domains:
            if domain.source_edge_identity not in self.edge_ids(roles):
                continue
            proof = self.pairwise.negative(domain, placed)
            if proof is not None:
                self.pairwise.verify_negative(proof, domain, placed)
                return proof
        return self.joint_necessary_contradiction(roles, placed)

    def joint_necessary_contradiction(
        self, roles: tuple[str, ...], placed: Mapping[str, PlacedRectangleV1]
    ) -> JointNecessarySpaceCertificateV1 | None:
        """Necessary supersets only: area and conservative MUST arc projection.

        Each neighbor's union is enlarged to four face-projection bounding boxes.
        Lost correlations enlarge capacity; they never justify a false empty.
        Resource guards discard the negative attempt, not a geometric variable.
        """
        q = self.pairwise
        missing = tuple(r for r in roles if r not in placed)
        if any(not q.shapes[r] for r in missing):
            return None
        xs, ys = tuple(x for x, _ in q.boundary), tuple(y for _, y in q.boundary)
        required_area = sum(
            (p.bounds_mm[2] - p.bounds_mm[0]) * (p.bounds_mm[3] - p.bounds_mm[1])
            for p in placed.values()
        ) + sum(min(s.world_width_mm * s.world_depth_mm for s in q.shapes[r]) for r in missing)
        bbox_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if required_area > bbox_area:
            placed_values = tuple(placed.values())
            if all(
                physical_status(p, q.boundary, q.obstacles) == "VALID" for p in placed_values
            ) and not any(
                _overlap(a.bounds_mm, b.bounds_mm)
                for i, a in enumerate(placed_values)
                for b in placed_values[i + 1 :]
            ):
                return JointNecessarySpaceCertificateV1(
                    self.identity(roles, placed),
                    "MINIMUM_COMPONENT_AREA_EXCEEDS_SITE_BBOX",
                    roles,
                    canonical_hash((required_area, bbox_area)),
                )
        spaces: dict[str, tuple[tuple[Shape, OriginBox], ...]] = {}
        for role in missing:
            values: list[tuple[Shape, OriginBox]] = []
            for shape in q.shapes[role]:
                boxes = necessary_origin_boxes(role, shape, placed, q.boundary, q.must_edges)
                if boxes is None:
                    return None
                values.extend((shape, b) for b in boxes)
            spaces[role] = tuple(values)
        relation_work = 0
        for _ in range(len(roles)):
            changed = False
            for role in missing:
                for neighbor in sorted(self.neighbors[role] & set(missing)):
                    other = spaces[neighbor]
                    if not other:
                        return JointNecessarySpaceCertificateV1(
                            self.identity(roles, placed),
                            "EMPTY_RELAXED_MUST_ARC_SPACE",
                            roles,
                            canonical_hash(
                                (
                                    neighbor,
                                    {r: [(asdict(s), b) for s, b in v] for r, v in spaces.items()},
                                )
                            ),
                        )
                    low_x = min(b[0] for _, b in other)
                    low_y = min(b[1] for _, b in other)
                    high_x = max(b[2] for _, b in other)
                    high_y = max(b[3] for _, b in other)
                    low_right = min(b[0] + s.world_width_mm for s, b in other)
                    low_top = min(b[1] + s.world_depth_mm for s, b in other)
                    high_right = max(b[2] + s.world_width_mm for s, b in other)
                    high_top = max(b[3] + s.world_depth_mm for s, b in other)
                    result = []
                    seen = set()
                    for shape, box in spaces[role]:
                        w, h = shape.world_width_mm, shape.world_depth_mm
                        projections = (
                            (low_x - w, low_y - h + 1, high_x - w, high_top - 1),
                            (low_right, low_y - h + 1, high_right, high_top - 1),
                            (low_x - w + 1, low_y - h, high_right - 1, high_y - h),
                            (low_x - w + 1, low_top, high_right - 1, high_top),
                        )
                        for projection in projections:
                            if relation_work >= 8192:
                                self.counts["necessary_arc_resource_unknown"] += 1
                                return None
                            relation_work += 1
                            self.counts["necessary_arc_intersections"] += 1
                            hit = intersect(box, projection)
                            if hit is not None and (shape, hit) not in seen:
                                result.append((shape, hit))
                                seen.add((shape, hit))
                        if len(result) > 8192:
                            self.counts["necessary_arc_resource_unknown"] += 1
                            return None
                    if not result:
                        return JointNecessarySpaceCertificateV1(
                            self.identity(roles, placed),
                            "EMPTY_RELAXED_MUST_ARC_SPACE",
                            roles,
                            canonical_hash(
                                (
                                    role,
                                    neighbor,
                                    {r: [(asdict(s), b) for s, b in v] for r, v in spaces.items()},
                                )
                            ),
                        )
                    following = tuple(result)
                    changed |= following != spaces[role]
                    spaces[role] = following
            if not changed:
                break
        return None

    def verify_negative(
        self, state: JointMetricSupportStateV1, placed: Mapping[str, PlacedRectangleV1]
    ) -> None:
        proof = self.negative(state.roles, placed)
        if (
            state.roles not in self.components
            or state.domain_identity != self.identity(state.roles, placed)
            or state.source_reservation_identities != self.edge_ids(state.roles)
            or state.status != Status.NONE
            or proof is None
            or state.negative_certificate != proof
        ):
            raise ValueError("UNSOUND_OR_STALE_JOINT_NEGATIVE_CERTIFICATE")

    def certificate(
        self,
        roles: tuple[str, ...],
        assignment: Assignment,
        placed: Mapping[str, PlacedRectangleV1],
    ) -> JointMetricCapacityCertificateV1 | None:
        candidate = JointMetricCapacityCertificateV1(
            self.graph_identity,
            self.edge_ids(roles),
            self.pairwise.authority_identity,
            self.pairwise.identity("partial", placed),
            self.identity(roles, placed),
            assignment,
            tuple(e for e in self.edges if set(e) <= set(roles)),
        )
        return candidate if self.verify(candidate, placed) else None

    def positive_origin_spaces(
        self, roles: tuple[str, ...], placed: Mapping[str, PlacedRectangleV1]
    ) -> dict[str, ShapeOriginSpaces]:
        """Necessary supersets for positive queries only; never prune on this map.

        Exact rectangular obstacle subtraction includes forbidden boundary contact.
        Other polygons remain relaxed until exact witness validation. All guards
        return an enlarged/less-propagated space, never a false empty region.
        """
        q = self.pairwise
        result: dict[str, ShapeOriginSpaces] = {}
        for role in roles:
            if role in placed:
                continue
            values: list[tuple[Shape, OriginBox]] = []
            for shape in q.shapes[role]:
                boxes = necessary_origin_boxes(role, shape, placed, q.boundary, q.must_edges)
                if boxes is None:
                    boxes = (
                        (
                            min(x for x, _ in q.boundary),
                            min(y for _, y in q.boundary),
                            max(x for x, _ in q.boundary) - shape.world_width_mm,
                            max(y for _, y in q.boundary) - shape.world_depth_mm,
                        ),
                    )
                original = boxes
                for polygon in q.obstacles:
                    xs, ys = {x for x, _ in polygon}, {y for _, y in polygon}
                    if (
                        len(xs) != 2
                        or len(ys) != 2
                        or set(polygon) != {(x, y) for x in xs for y in ys}
                    ):
                        continue
                    forbidden = (
                        min(xs) - shape.world_width_mm,
                        min(ys) - shape.world_depth_mm,
                        max(xs),
                        max(ys),
                    )
                    boxes = tuple(piece for box in boxes for piece in subtract(box, forbidden))
                    self.counts["positive_obstacle_space_subtractions"] += 1
                    if len(boxes) > 8192:
                        boxes = original
                        self.counts["positive_space_resource_relaxations"] += 1
                        break
                values.extend(
                    (shape, box) for box in boxes if box[0] <= box[2] and box[1] <= box[3]
                )
            result[role] = _coalesce_origin_spaces(values)
        work = 0
        for _ in range(len(result)):
            changed = False
            for role in result:
                for neighbor in sorted(self.neighbors[role] & result.keys()):
                    other = result[neighbor]
                    if not other:
                        changed |= bool(result[role])
                        result[role] = ()
                        continue
                    low_x = min(b[0] for _, b in other)
                    low_y = min(b[1] for _, b in other)
                    high_x = max(b[2] for _, b in other)
                    high_y = max(b[3] for _, b in other)
                    low_right = min(b[0] + s.world_width_mm for s, b in other)
                    low_top = min(b[1] + s.world_depth_mm for s, b in other)
                    high_right = max(b[2] + s.world_width_mm for s, b in other)
                    high_top = max(b[3] + s.world_depth_mm for s, b in other)
                    following: list[tuple[Shape, OriginBox]] = []
                    seen = set()
                    for shape, box in result[role]:
                        w, h = shape.world_width_mm, shape.world_depth_mm
                        projections = (
                            (low_x - w, low_y - h + 1, high_x - w, high_top - 1),
                            (low_right, low_y - h + 1, high_right, high_top - 1),
                            (low_x - w + 1, low_y - h, high_right - 1, high_y - h),
                            (low_x - w + 1, low_top, high_right - 1, high_top),
                        )
                        for projection in projections:
                            if work >= 8192:
                                self.counts["positive_space_resource_relaxations"] += 1
                                return result
                            work += 1
                            self.counts["positive_constraint_intersections"] += 1
                            hit = intersect(box, projection)
                            if hit is not None and (shape, hit) not in seen:
                                following.append((shape, hit))
                                seen.add((shape, hit))
                    coalesced = _coalesce_origin_spaces(following)
                    changed |= coalesced != result[role]
                    result[role] = coalesced
            if not changed:
                break
        return result

    def candidates(
        self,
        role: str,
        placed: Mapping[str, PlacedRectangleV1],
        hints: tuple[tuple[str, Bounds, Shape], ...],
        event_limit: int,
        spaces: ShapeOriginSpaces | None = None,
    ) -> Iterator[tuple[Bounds, Shape]]:
        q = self.pairwise
        spaces = self.positive_origin_spaces((role,), placed)[role] if spaces is None else spaces
        groups: dict[Shape, list[OriginBox]] = defaultdict(list)
        for shape, box in spaces:
            groups[shape].append(box)
        seen = set()
        for r, bounds, shape in hints:
            if r != role or shape not in groups:
                continue
            x, y = bounds[:2]
            if not any(a <= x <= c and b <= y <= d for a, b, c, d in groups[shape]):
                self.counts["necessary_hint_exclusions"] += 1
                continue
            if (bounds, shape) not in seen:
                seen.add((bounds, shape))
                yield bounds, shape
        for shape in q.shapes[role]:
            if shape not in groups:
                self.counts["empty_necessary_shape_spaces"] += 1
                continue
            boxes = groups[shape]
            base = necessary_origin_boxes(role, shape, placed, q.boundary, q.must_edges)
            origins = q.origin_provider(role, shape, placed)
            # Keep existing coarse events first, then refine all four box corners.
            critical = tuple(
                point
                for x, y, right, top in base or ()
                for point in ((x, y), (right, top), ((x + right) // 2, (y + top) // 2))
            )
            refined = tuple(
                point
                for x, y, right, top in boxes
                for point in (
                    (x, y),
                    (right, top),
                    ((x + right) // 2, (y + top) // 2),
                    (x, top),
                    (right, y),
                )
            )
            admissible: list[tuple[int, int]] = []
            other: list[tuple[int, int]] = []
            for point in origins:
                target = (
                    admissible
                    if any(a <= point[0] <= c and b <= point[1] <= d for a, b, c, d in boxes)
                    else other
                )
                target.append(point)
            for x, y in (*critical, *admissible, *refined, *other):
                if self.counts["origin_events"] >= event_limit:
                    return
                self.counts["origin_events"] += 1
                if not any(a <= x <= c and b <= y <= d for a, b, c, d in boxes):
                    continue
                bounds = x, y, x + shape.world_width_mm, y + shape.world_depth_mm
                key = bounds, shape
                if key not in seen:
                    seen.add(key)
                    yield key

    def probe(
        self,
        roles: tuple[str, ...],
        placed: Mapping[str, PlacedRectangleV1],
        hints: tuple[tuple[str, Bounds, Shape], ...],
    ) -> tuple[JointMetricCapacityCertificateV1 | None, int, str]:
        q = self.pairwise
        working = dict(placed)
        selected: dict[str, Shape] = {}
        for r in roles:
            if r in placed:
                shape = q.fixed_shape(r, placed)
                if shape is None:
                    return None, 0, "AUTHORITATIVE_SHAPE_UNRESOLVED"
                selected[r] = shape
        checked = 0
        initial_events = self.counts["origin_events"]
        exhausted = False

        def recurse() -> JointMetricCapacityCertificateV1 | None:
            nonlocal checked, exhausted
            missing = tuple(r for r in roles if r not in working)
            if not missing:
                assignment = tuple((r, working[r].bounds_mm, selected[r]) for r in roles)
                return self.certificate(roles, assignment, placed)
            space_map = self.positive_origin_spaces(roles, working)
            fixed_degree = {r: sum(n in working for n in self.neighbors[r]) for r in missing}
            role = min(
                missing,
                key=lambda r: (
                    -fixed_degree[r],
                    len(q.shapes[r]),
                    -len(self.neighbors[r]),
                    sum((c - a + 1) * (d - b + 1) for _, (a, b, c, d) in space_map[r])
                    if fixed_degree[r] >= 2
                    else 0,
                    r,
                ),
            )
            for bounds, shape in self.candidates(
                role, working, hints, initial_events + self.event_cap, space_map[role]
            ):
                if (
                    checked >= self.evaluation_cap
                    or self.counts["origin_events"] - initial_events > self.event_cap
                ):
                    exhausted = True
                    return None
                checked += 1
                rect = q.rectangle(role, bounds, shape)
                if any(_overlap(bounds, p.bounds_mm) for p in working.values()):
                    self.counts["overlap_conflicts"] += 1
                    continue
                if any(
                    n in working and not _edge(bounds, working[n].bounds_mm)
                    for n in self.neighbors[role]
                ):
                    self.counts["fixed_neighbor_conflicts"] += 1
                    continue
                if bounds not in q.physical_cache:
                    q.physical_cache[bounds] = (
                        physical_status(rect, q.boundary, q.obstacles) == "VALID"
                    )
                if not q.physical_cache[bounds]:
                    continue
                working[role] = rect
                selected[role] = shape
                if q.intent_possible(working):
                    answer = recurse()
                    if answer is not None:
                        return answer
                else:
                    self.counts["composition_intent_conflicts"] += 1
                working.pop(role)
                selected.pop(role)
                if exhausted:
                    return None
            if self.counts["origin_events"] - initial_events >= self.event_cap:
                exhausted = True
            return None

        answer = recurse()
        return (
            answer,
            checked,
            "JOINT_WITNESS_VERIFIED"
            if answer is not None
            else "POSITIVE_PROBE_CAP_EXHAUSTED"
            if exhausted
            else "JOINT_ASSIGNMENT_UNPROVEN",
        )

    def update(
        self,
        placed: Mapping[str, PlacedRectangleV1],
        pairwise_states: tuple[ConditionalMetricSupportStateV2, ...],
        parent: tuple[JointMetricSupportStateV1, ...] = (),
    ) -> tuple[JointMetricSupportStateV1, ...]:
        if tuple(s.source_edge_identity for s in pairwise_states) != tuple(
            d.source_edge_identity for d in self.pairwise.domains
        ):
            raise ValueError("JOINT_PAIRWISE_PROVENANCE_MISMATCH")
        if parent and tuple(s.roles for s in parent) != self.components:
            raise ValueError("JOINT_PARENT_COMPONENT_MISMATCH")
        states = []
        for i, roles in enumerate(self.components):
            self.counts["checks"] += 1
            old = (parent[i].certificate if parent else None) or self.positive_cache.get(roles)
            hints = tuple(
                (r, bounds, shape)
                for s in pairwise_states
                if s.certificate is not None
                for r, bounds, shape in zip(
                    s.certificate.roles, s.certificate.slot[:2], s.certificate.slot[2:], strict=True
                )
            )
            certificate = self.certificate(roles, old.assignment, placed) if old else None
            if certificate:
                self.counts["reuse"] += 1
            elif old:
                self.counts["invalidations"] += 1
                hints = old.assignment + hints
            # Natural join on a shared role's exact geometry, not a union of facts.
            joined: dict[str, tuple[Bounds, Shape]] = {}
            inconsistent = False
            for role, bounds, shape in hints:
                if role not in roles:
                    continue
                if role in joined and joined[role] != (bounds, shape):
                    inconsistent = True
                joined[role] = bounds, shape
            if inconsistent:
                self.counts["shared_role_witness_disagreements"] += 1
            elif certificate is None and set(joined) == set(roles):
                certificate = self.certificate(roles, tuple((r, *joined[r]) for r in roles), placed)
                if certificate is not None:
                    self.counts["pairwise_natural_join_certificates"] += 1
            checked, reason = 0, "JOINT_CERTIFICATE_REVALIDATED"
            proof = None
            if certificate is None:
                proof = self.negative(roles, placed)
                if proof is None:
                    certificate, checked, reason = self.probe(roles, placed, hints)
                    self.counts["candidate_evaluations"] += checked
            status = Status.SUPPORTED if certificate else Status.NONE if proof else Status.UNKNOWN
            self.counts[status.value] += 1
            if certificate and not old:
                self.counts["certificates_created"] += 1
            if certificate:
                self.positive_cache[roles] = certificate
                self.counts["positive_certificates"] += 1
            if status == Status.UNKNOWN:
                self.counts[reason] += 1
            state = JointMetricSupportStateV1(
                roles,
                self.edge_ids(roles),
                status,
                self.identity(roles, placed),
                certificate,
                proof,
                proof.proof_kind if proof else reason,
                checked,
            )
            if proof:
                self.verify_negative(state, placed)
            for edge in state.source_reservation_identities:
                counter = self.by_edge.setdefault(edge, Counter())
                counter[status.value] += 1
                counter["candidate_evaluations"] += checked
            self.sequence.update((canonical_hash(asdict(state)) + "\n").encode())
            states.append(state)
        return tuple(states)

    def diagnostics(self) -> dict[str, object]:
        return {
            "proof_scope": self.proof_scope,
            "query_evaluation_cap": self.evaluation_cap,
            "query_origin_event_cap": self.event_cap,
            "counts": dict(self.counts),
            "by_edge": {e: dict(v) for e, v in self.by_edge.items()},
            "sequence_digest": self.sequence.hexdigest(),
        }
