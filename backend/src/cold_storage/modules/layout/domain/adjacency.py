"""Directed process authority and undirected positive-edge adjacency predicates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from cold_storage.modules.layout.domain.dimensioning import GRID, LayoutAuthorityError

ZONE_CODES = (
    "office",
    "changing_room",
    "primary_precooling_room",
    "secondary_precooling_room",
    "raw_fruit_buffer",
    "sorting_packaging_room",
    "coating_room",
    "finished_goods_room",
    "secondary_fruit_buffer",
    "frozen_fruit_room",
    "packaging_material_storage",
    "shipping_channel",
)
PROCESS_FLOW = (
    "raw_fruit_buffer",
    "primary_precooling_room",
    "sorting_packaging_room",
    "secondary_precooling_room",
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
)


@dataclass(frozen=True)
class FlowV1:
    kind: str
    from_ref: str
    to_ref: str


@dataclass(frozen=True)
class AdjacencyGraphV1:
    identity: str
    nodes: tuple[str, ...]
    must_adjacencies: tuple[tuple[str, str], ...]
    should_adjacencies: tuple[tuple[str, str], ...]
    flows: tuple[FlowV1, ...]
    zone_access_proximities: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if len(self.nodes) != len(set(self.nodes)) or set(self.nodes) != set(ZONE_CODES):
            raise LayoutAuthorityError("INVALID_ADJACENCY_GRAPH")
        seen: set[frozenset[str]] = set()
        for pair in (*self.must_adjacencies, *self.should_adjacencies):
            edge = frozenset(pair)
            if len(pair) != 2 or len(edge) != 2 or not edge <= set(self.nodes) or edge in seen:
                raise LayoutAuthorityError("INVALID_ADJACENCY_GRAPH")
            seen.add(edge)
        for flow in self.flows:
            if flow.from_ref not in (*self.nodes, "main_entrance") or flow.to_ref not in self.nodes:
                raise LayoutAuthorityError("INVALID_ADJACENCY_GRAPH")


def process_graph() -> AdjacencyGraphV1:
    main = tuple(zip(PROCESS_FLOW[:-1], PROCESS_FLOW[1:], strict=True))
    return AdjacencyGraphV1(
        "charles-v22-process-flow@1.0.0",
        ZONE_CODES,
        main,
        (
            ("sorting_packaging_room", "coating_room"),
            ("sorting_packaging_room", "secondary_fruit_buffer"),
            ("sorting_packaging_room", "frozen_fruit_room"),
            ("changing_room", "sorting_packaging_room"),
        ),
        tuple(FlowV1("MATERIAL", a, b) for a, b in main)
        + (
            FlowV1("PACKAGING", "packaging_material_storage", "sorting_packaging_room"),
            FlowV1("SECONDARY", "sorting_packaging_room", "secondary_fruit_buffer"),
            FlowV1("FROZEN", "sorting_packaging_room", "frozen_fruit_room"),
            FlowV1("PEOPLE", "main_entrance", "changing_room"),
            FlowV1("PEOPLE", "changing_room", "sorting_packaging_room"),
        ),
        (("shipping_channel", "truck_entrance"),),
    )


@dataclass(frozen=True)
class RectangleObservationV1:
    """Caller-supplied observation for predicates, never a generated placement."""

    zone_code: str
    x: Decimal
    y: Decimal
    width_m: Decimal
    depth_m: Decimal
    rotation_deg: int = 0

    def __post_init__(self) -> None:
        with localcontext(Context(prec=80)):
            for key in ("x", "y", "width_m", "depth_m"):
                val = getattr(self, key)
                if (
                    not isinstance(val, Decimal)
                    or not val.is_finite()
                    or abs(val) > Decimal("1000000000")
                    or val % GRID
                    or (key in ("width_m", "depth_m") and val <= 0)
                ):
                    raise LayoutAuthorityError("INVALID_RECTANGLE_OBSERVATION")
        if type(self.rotation_deg) is not int or self.rotation_deg not in (0, 90):
            raise LayoutAuthorityError("INVALID_ROTATION")

    def bounds(self) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        width, depth = self.width_m, self.depth_m
        if self.rotation_deg == 90:
            width, depth = depth, width
        with localcontext(Context(prec=80)):
            return self.x, self.y, self.x + width, self.y + depth


def shared_edge_adjacent(a: RectangleObservationV1, b: RectangleObservationV1) -> bool:
    ax, ay, ar, at = a.bounds()
    bx, by, br, bt = b.bounds()
    return ((ar == bx or br == ax) and min(at, bt) > max(ay, by)) or (
        (at == by or bt == ay) and min(ar, br) > max(ax, bx)
    )


def evaluate_adjacency(
    graph: AdjacencyGraphV1,
    observations: tuple[RectangleObservationV1, ...],
) -> dict[str, object]:
    observations = tuple(sorted(observations, key=lambda row: row.zone_code))
    rows = {row.zone_code: row for row in observations}
    if len(rows) != len(observations) or not set(rows) <= set(graph.nodes):
        raise LayoutAuthorityError("INVALID_RECTANGLE_OBSERVATION")
    missing = sorted(set(graph.nodes) - set(rows))
    violations: list[dict[str, object]] = []
    unsatisfied_should: list[tuple[str, str]] = []
    for i, a in enumerate(observations):
        for b in observations[i + 1 :]:
            ax, ay, ar, at = a.bounds()
            bx, by, br, bt = b.bounds()
            if min(ar, br) > max(ax, bx) and min(at, bt) > max(ay, by):
                violations.append(
                    {"code": "ZONE_OVERLAP", "zones": sorted((a.zone_code, b.zone_code))}
                )
    for first, second in graph.must_adjacencies:
        if first in rows and second in rows and not shared_edge_adjacent(rows[first], rows[second]):
            violations.append({"code": "HARD_CONSTRAINT_UNSATISFIABLE", "zones": [first, second]})
    for first, second in graph.should_adjacencies:
        if first in rows and second in rows and not shared_edge_adjacent(rows[first], rows[second]):
            unsatisfied_should.append((first, second))
    # This is only the adjacency/no-overlap subset, never full site hard acceptance.
    return {
        "evaluation_scope": "ADJACENCY_AND_OVERLAP_ONLY",
        "missing_observations": missing,
        "geometry_passed": not missing and not violations,
        "violations": violations,
        "unsatisfied_should": unsatisfied_should,
        "access_status": "NOT_EVALUATED",
    }
