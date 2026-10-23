"""Controlled stage-A global generation, separate from the P1A/P3 selector.

Only a current server replay constructs solver input. No external composition,
coordinates, hint, historical file, or arbitrary engineering budget is accepted.
The solver port is wired at bootstrap; this module owns authority and validation.
"""

from __future__ import annotations

import resource
import sys
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from itertools import combinations
from json import dumps
from types import FrameType
from typing import Any, Protocol

from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.composition_placement import _assert_server_replay
from cold_storage.modules.layout.application.layout_authority_binding import (
    LayoutAuthorityBindingV1,
    bind_layout_authority,
)
from cold_storage.modules.layout.application.site_geometry import (
    ValidatedSiteGeometryV1,
    validate_rectangle_against_site,
)
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.access_authority import resolve_access_profile
from cold_storage.modules.layout.domain.access_routing import (
    _segment,
    _segment_from_mapping,
)
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.composition_handoff import (
    StructuralCompositionPlacementHandoffV1,
)
from cold_storage.modules.layout.domain.composition_placement import (
    _domain_faces,
    _intent_preserved,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.objective_profile import approved_objective_profile
from cold_storage.modules.layout.domain.placement import _long_edges
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    normalize_polygon,
    rectangles_share_positive_edge,
)
from cold_storage.modules.layout.domain.validated_site_obstacles import (
    validated_hard_obstacle_polygons,
)

IDENTITY = "controlled-global-composition-generation@1.0.0"
RESOURCE_SCOPE = "STAGE_A_INTERNAL_CP_SAT_NOT_MAPPED_TO_P3_DFS"
DEFAULT_STAGE_A_COMPOSITION = (
    "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"
)


class ExecutionAuthorization(Protocol):
    """Resource scope owned by bootstrap's trusted durable authority, not callers."""

    def validate(self, ledger: StageALedger) -> None: ...

    def begin(self, sources: Mapping[str, str]) -> None: ...

    def checkpoint(self, phase: str, snapshot: Mapping[str, Any]) -> None: ...


@dataclass
class StageALedger:
    """Explicit B0 ceiling; CP-SAT counters are never converted to DFS work."""

    started: float = field(default_factory=time.monotonic)
    model_work: int = 0
    solver_wall: float = 0
    solver_monotonic_wall: float = 0
    attempts: list[dict[str, Any]] = field(default_factory=list)
    native_host_work: int = 0
    native_requirements: list[dict[str, Any]] = field(default_factory=list)
    peak_rss_bytes: int = 0
    solver_history_verified: bool = False
    native_solver_active: bool = False
    checked_solutions: int = 0
    audit_sink: Callable[[dict[str, Any]], None] | None = field(default=None, repr=False)
    execution_authorization: ExecutionAuthorization | None = field(default=None, repr=False)
    native_grid_searches: list[dict[str, Any]] = field(default_factory=list)
    resource_events: dict[str, int] = field(default_factory=dict)

    def checkpoint(self, phase: str) -> None:
        if self.execution_authorization is not None:
            self.execution_authorization.checkpoint(
                phase,
                {
                    "model_work": self.model_work,
                    "native_host_work": self.native_host_work,
                    "solver_wall": self.solver_wall,
                    "solver_monotonic_wall": self.solver_monotonic_wall,
                    "attempts": self.attempts,
                    "native_solver_active": self.native_solver_active,
                    "checked_solutions": self.checked_solutions,
                    "native_requirements": self.native_requirements,
                    "native_grid_searches": self.native_grid_searches,
                    "resource_events": self.resource_events,
                    "peak_rss_bytes": self.peak_rss_bytes,
                    "elapsed_seconds": time.monotonic() - self.started,
                },
            )
        if self.audit_sink is not None:
            self.audit_sink(
                {
                    "phase": phase,
                    "model_work": self.model_work,
                    "native_host_work": self.native_host_work,
                    "solver_wall_observed_seconds": self.solver_wall,
                    "solver_history_verified": self.solver_history_verified,
                    "native_solver_active": self.native_solver_active,
                    "checked_solutions": self.checked_solutions,
                    "solver_attempts": self.attempts,
                    "native_requirements": self.native_requirements,
                    "elapsed_seconds": time.monotonic() - self.started,
                }
            )

    def remaining_solver_seconds(self) -> float:
        """Never grant a fresh allowance when continuation history is unknown."""
        if not self.solver_history_verified or self.native_solver_active:
            raise LayoutAuthorityError("CP_SAT_CUMULATIVE_HISTORY_UNVERIFIED")
        if self.execution_authorization is None:
            raise LayoutAuthorityError("CP_SAT_EXECUTION_IDENTITY_REQUIRED")
        self.execution_authorization.validate(self)
        scoped_remaining = getattr(self.execution_authorization, "remaining_solver_seconds", None)
        if scoped_remaining is not None:
            return float(scoped_remaining(self))
        remaining = 100 - self.solver_wall
        if self.solver_wall < 0 or remaining <= 0:
            raise LayoutAuthorityError("CP_SAT_CUMULATIVE_ALLOWANCE_EXHAUSTED")
        return remaining

    def precharge_work(self, n: int) -> None:
        """Admit the whole operation before changing any cumulative counter."""
        if type(n) is not int or n < 0:
            raise LayoutAuthorityError("STAGE_A_INVALID_WORK_CHARGE")
        self.guard()
        if self.model_work + self.native_host_work + n > 1_200_000:
            raise LayoutAuthorityError("STAGE_A_RESOURCE_LIMIT")
        scoped = getattr(self.execution_authorization, "precharge_work", None)
        if scoped is not None:
            scoped(self, n)

    def charge(self, label: str, n: int = 1) -> None:
        self.precharge_work(n)
        self.model_work += n
        self.resource_events[label] = self.resource_events.get(label, 0) + n

    def guard(self) -> None:
        scoped_guard = getattr(self.execution_authorization, "guard", None)
        if scoped_guard is not None:
            scoped_guard(self)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        self.peak_rss_bytes = max(
            self.peak_rss_bytes, rss if sys.platform == "darwin" else rss * 1024
        )
        if (
            self.model_work + self.native_host_work > 1_200_000
            or time.monotonic() - self.started > 180
            or self.peak_rss_bytes > 512 * 1024 * 1024
        ):
            raise LayoutAuthorityError("STAGE_A_RESOURCE_LIMIT")

    @contextmanager
    def observe_native(self) -> Iterator[None]:
        """Same observable domain primitives as B0, not CP-SAT native work.

        Per-requirement 20,000 is a research Host guard, distinct from the
        unchanged route-node budget. Never disables the actual domain budget.
        The entry is intentionally single-worker and cannot replace a profiler.
        """
        if sys.getprofile() is not None:
            raise LayoutAuthorityError("STAGE_A_PROFILER_ALREADY_ACTIVE")
        primitives = {
            "_cross",
            "_fraction_cross",
            "_on_segment",
            "_segments_intersect_closed",
            "_segment_intersection_parameters",
            "point_in_polygon",
            "_point_on_fraction_segment",
            "rectangles_overlap",
            "rectangles_share_positive_edge",
            "_portal_candidates",
            "_apply_template",
        }
        current: dict[str, Any] | None = None
        grid_frames: dict[int, dict[str, Any]] = {}

        def profile(frame: FrameType, event: str, value: Any) -> None:
            nonlocal current
            if "/layout/domain/" not in frame.f_code.co_filename:
                return
            name = frame.f_code.co_name
            if event == "call" and name == "_route_grid_path":
                grid = {
                    "requirement": current["identity"] if current else None,
                    "budget": frame.f_locals["node_budget"],
                    "visited_nodes": 0,
                    "completed": False,
                }
                grid_frames[id(frame)] = grid
                self.native_grid_searches.append(grid)
            if event == "call" and name == "neighbors":
                parent = frame.f_back
                if parent is not None and id(parent) in grid_frames:
                    grid_frames[id(parent)]["visited_nodes"] = parent.f_locals.get("visited", 0)
            if event == "return" and name == "_route_grid_path" and id(frame) in grid_frames:
                grid = grid_frames.pop(id(frame))
                grid["visited_nodes"] = frame.f_locals.get("visited", 0)
                grid["completed"] = value is not None
                grid["return_code"] = value[1] if value is not None else "INTERRUPTED"
            if event == "call" and name == "route_access_requirement":
                req = frame.f_locals["requirement"]
                current = {"identity": req["identity"], "host_work": 0, "status": "STARTED"}
                self.native_requirements.append(current)
                self.checkpoint("NATIVE_REQUIREMENT_STARTED")
            if event == "call" and name in primitives:
                if current and current["host_work"] >= 20_000:
                    current["status"] = "RESOURCE_INTERRUPTED"
                    ancestor: FrameType | None = frame
                    while ancestor is not None:
                        if id(ancestor) in grid_frames:
                            grid_frames[id(ancestor)]["visited_nodes"] = ancestor.f_locals.get(
                                "visited", 0
                            )
                        ancestor = ancestor.f_back
                    self.checkpoint("NATIVE_REQUIREMENT_HOST_LIMIT")
                    raise LayoutAuthorityError("STAGE_A_REQUIREMENT_HOST_LIMIT")
                self.precharge_work(1)
                if current:
                    current["host_work"] += 1
                self.native_host_work += 1
            if event == "return" and name == "route_access_requirement" and current:
                if value is not None:
                    current["status"] = value[0]["status"]
                    current["raw_result"] = value[0]
                    current["corridor_polygons"] = value[1]
                current = None
                self.checkpoint("NATIVE_REQUIREMENT_FINISHED")

        sys.setprofile(profile)
        try:
            yield
        finally:
            sys.setprofile(None)
            self.checkpoint("NATIVE_OBSERVER_FINISHED")


def rectangular_scope(poly: PolygonMM) -> tuple[int, int, int, int]:
    """Reject unsupported polygons instead of silently replacing with a bbox."""
    x, y = min(p[0] for p in poly), min(p[1] for p in poly)
    right, top = max(p[0] for p in poly), max(p[1] for p in poly)
    if len(poly) != 4 or set(poly) != {(x, y), (right, y), (right, top), (x, top)}:
        raise LayoutAuthorityError("GLOBAL_SOLVER_RECTANGULAR_SCOPE_REQUIRED")
    return x, y, right, top


def zone_geometry_hash(zones: list[dict[str, Any]]) -> str:
    """B0 normalization: sorted roles, compact sorted JSON, no runtime fields."""
    raw = dumps(
        sorted(zones, key=lambda r: r["zone_code"]),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return "sha256:" + sha256(raw.encode()).hexdigest()


def _route_geometry_errors(route: Mapping[str, Any]) -> list[str]:
    """Reconstruct complete strip and corner envelopes from the actual path."""
    errors: list[str] = []
    path = [tuple(point) for point in route["path_mm"]]
    if route["topology"] == "DIRECT_SHARED_EDGE":
        if (
            path
            or route["envelopes_mm"]
            or route["portal_from_center_mm"] != route["portal_to_center_mm"]
        ):
            errors.append("DIRECT_GEOMETRY")
        return errors
    if route["topology"] != "CORRIDOR_MEDIATED" or len(path) < 2:
        return ["ROUTE_TOPOLOGY_OR_CONTINUITY"]
    if path[0] != tuple(route["portal_from_center_mm"]) or path[-1] != tuple(
        route["portal_to_center_mm"]
    ):
        errors.append("PORTAL_PATH_ENDPOINTS")
    width = route["width_mm"]
    half = width // 2
    expected: list[tuple[int, ...]] = []
    turns = 0
    length = 0
    axes: list[int] = []
    for a, b in zip(path, path[1:], strict=False):
        if a == b or (a[0] != b[0] and a[1] != b[1]):
            return ["NON_ORTHOGONAL_OR_ZERO_SEGMENT"]
        length += abs(a[0] - b[0]) + abs(a[1] - b[1])
        axis = int(a[0] == b[0])
        axes.append(axis)
        expected.append(
            (a[0] - half, min(a[1], b[1]), a[0] + width - half, max(a[1], b[1]))
            if axis
            else (min(a[0], b[0]), a[1] - half, max(a[0], b[0]), a[1] + width - half)
        )
    for index, (x, y) in enumerate(path[1:-1]):
        if axes[index] != axes[index + 1]:
            turns += 1
        expected.append((x - half, y - half, x + width - half, y + width - half))
    if length != route["length_mm"] or turns != route["turn_count"]:
        errors.append("ROUTE_LENGTH_OR_TURNS")
    if sorted(expected) != sorted(tuple(box) for box in route["envelopes_mm"]):
        errors.append("INCOMPLETE_CORRIDOR_ENVELOPE")
    return errors


@dataclass(frozen=True)
class GlobalGenerationContext:
    binding: LayoutAuthorityBindingV1
    site: ValidatedSiteGeometryV1
    boundary: PolygonMM
    obstacles: tuple[PolygonMM, ...]
    sitebox: tuple[int, int, int, int]
    obsboxes: tuple[tuple[int, int, int, int], ...]
    entrances: Mapping[str, Any]
    must: tuple[tuple[str, str], ...]
    pack_req: Mapping[str, Any]
    profile: Any
    ledger: StageALedger


class GlobalCompositionSolver(Protocol):
    def solve(
        self, context: GlobalGenerationContext, handoff: StructuralCompositionPlacementHandoffV1
    ) -> dict[str, Any]: ...


def _overlap(a: tuple[int, ...], b: tuple[int, ...], *, closed: bool = False) -> bool:
    if closed:
        return max(a[0], b[0]) <= min(a[2], b[2]) and max(a[1], b[1]) <= min(a[3], b[3])
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def validate_global_geometry(
    context: GlobalGenerationContext,
    handoff: StructuralCompositionPlacementHandoffV1,
    zones: Mapping[str, PlacedRectangleV1],
    routes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Integer interval oracle independent of CP-SAT satisfaction flags.

    Rectangular scope is checked before modeling. All dimensions, physical
    rotation, closed obstacles and positive edge MUSTs are recomputed here.
    Corridor envelopes must avoid *all* rooms, including incident interiors.
    """
    errors: list[str] = []
    if set(zones) != set(ZONE_CODES):
        return {"pass": False, "errors": ["ROLE_SET_MISMATCH"]}
    boxes = {k: rectangular_scope(r.polygon_mm) for k, r in zones.items()}
    for k, r in zones.items():
        a = context.binding.dimension_authorities[k]
        if r.rotation_deg not in a["rotation_allowed"]:
            errors.append("ROTATION:" + k)
        if a["dimension_mode"] == "FLEXIBLE_RECTANGLE":
            if min(r.width_m, r.depth_m) <= 0 or Decimal(str(r.width_m)) * Decimal(
                str(r.depth_m)
            ) < Decimal(str(a["required_area_m2"])):
                errors.append("AREA:" + k)
        elif (r.width_m, r.depth_m) != (
            Decimal(str(a["geometry"]["width_m"])),
            Decimal(str(a["geometry"]["depth_m"])),
        ):
            errors.append("DIMENSION:" + k)
        validate_rectangle_against_site(r, context.site)
    for first, second in combinations(boxes, 2):
        if _overlap(boxes[first], boxes[second]):
            errors.append("ROOM_OVERLAP:" + first + ":" + second)
    must_count = sum(rectangles_share_positive_edge(zones[a], zones[b]) for a, b in context.must)
    if must_count != len(context.must):
        errors.append("MUST")
    if not _intent_preserved(handoff, zones, _domain_faces(handoff, 1)):
        errors.append("COMPOSITION_INTENT")
    expected = {
        str(r["identity"]): r
        for r in context.binding.access_requirements
        if r["flow_kind"] != "TRUCK"
    }
    if len(routes) != len(expected) or {r["requirement_identity"] for r in routes} != set(expected):
        errors.append("ROUTE_IDENTITIES")
    sx, sy, sr, st = context.sitebox
    all_envelopes: list[tuple[str, tuple[int, ...]]] = []
    for route in routes:
        errors.extend(_route_geometry_errors(route))
        req = expected[route["requirement_identity"]]
        profile = resolve_access_profile(req["profile_identity"])
        if route["width_mm"] != int(profile.corridor_clear_width_m * 1000):
            errors.append("CORRIDOR_WIDTH")
        if route["topology"] == "DIRECT_SHARED_EDGE":
            if (
                not req["direct_allowed"]
                or req["from_ref"] not in zones
                or not rectangles_share_positive_edge(zones[req["from_ref"]], zones[req["to_ref"]])
            ):
                errors.append("DIRECT_SHARED_EDGE")
        elif not req["corridor_allowed"]:
            errors.append("CORRIDOR_NOT_ALLOWED")
        if req["route_shape_constraint"] == "STRAIGHT_ONLY" and route["turn_count"]:
            errors.append("STRAIGHT_ONLY")
        # Portal segment must lie entirely on an actual room/entrance edge.
        for ref, key in (
            (req["from_ref"], "portal_from_center_mm"),
            (req["to_ref"], "portal_to_center_mm"),
        ):
            px, py = route[key]
            pw = route["portal_width_mm"]
            if pw < int(profile.portal_clear_width_m * 1000):
                errors.append("PORTAL_WIDTH")
            if ref in zones:
                x, y, right, top = boxes[ref]
                vertical = px in (x, right) and 2 * y + pw <= 2 * py <= 2 * top - pw
                horizontal = py in (y, top) and 2 * x + pw <= 2 * px <= 2 * right - pw
                if not (vertical or horizontal):
                    errors.append("PORTAL_FACE:" + ref)
                if req["identity"] == context.pack_req["identity"]:
                    length, other = (top - y, right - x) if vertical else (right - x, top - y)
                    if (ref == req["from_ref"] and length < other) or (
                        ref == req["to_ref"] and length > other
                    ):
                        errors.append("PACKAGING_EDGE")
            else:
                a, b = context.entrances[ref]
                if not (
                    (
                        a[0] == b[0] == px
                        and 2 * min(a[1], b[1]) + pw <= 2 * py <= 2 * max(a[1], b[1]) - pw
                    )
                    or (
                        a[1] == b[1] == py
                        and 2 * min(a[0], b[0]) + pw <= 2 * px <= 2 * max(a[0], b[0]) - pw
                    )
                ):
                    errors.append("ENTRANCE_PORTAL")
        for envelope in route["envelopes_mm"]:
            box = tuple(envelope)
            if box[0] < sx or box[1] < sy or box[2] > sr or box[3] > st:
                errors.append("CORRIDOR_SITE")
            if any(_overlap(box, b) for b in boxes.values()):
                errors.append("INCIDENT_OR_OTHER_ROOM_TRANSIT")
            if any(_overlap(box, b, closed=True) for b in context.obsboxes):
                errors.append("CORRIDOR_CLOSED_OBSTACLE")
            all_envelopes.append((route["requirement_identity"], box))
    coexist = not any(
        a != b and _overlap(x, y) for (a, x), (b, y) in combinations(all_envelopes, 2)
    )
    if not coexist:
        errors.append("SHARED_CORRIDOR_REQUIRES_OWNER_REVIEW")
    return {
        "pass": not errors,
        "errors": errors,
        "zone_count": len(zones),
        "must_pass_count": must_count,
        "access_count": len(routes),
        "coexistence": coexist,
    }


def validate_native_access_geometry(
    context: GlobalGenerationContext,
    zones: Mapping[str, PlacedRectangleV1],
    application: Mapping[str, Any],
) -> dict[str, Any]:
    """Independent interval checks of actual native output, never model routes.

    Portal connectors use the original portal width; interior route strips
    use corridor width. Union coverage includes all compressed open cells.
    """
    requirements = {
        str(r["identity"]): r
        for r in context.binding.access_requirements
        if r["flow_kind"] != "TRUCK"
    }
    rows = [r for r in application["access_results"] if r["flow_kind"] != "TRUCK"]
    errors: list[str] = []
    if len(rows) != 11 or {r["requirement_identity"] for r in rows} != set(requirements):
        return {"pass": False, "errors": ["NATIVE_RESULT_IDENTITIES"]}
    room_boxes = {k: rectangular_scope(v.polygon_mm) for k, v in zones.items()}
    all_boxes: list[tuple[str, tuple[int, ...]]] = []

    def point(raw: Mapping[str, Any]) -> tuple[int, int]:
        values = [Decimal(str(raw[axis])) * 1000 for axis in ("x", "y")]
        if any(v != v.to_integral_value() for v in values):
            raise LayoutAuthorityError("NATIVE_ACCESS_NON_MM_OUTPUT")
        return int(values[0]), int(values[1])

    def covered(target: tuple[int, ...], boxes: Sequence[tuple[int, ...]]) -> bool:
        xs = sorted(
            {target[0], target[2]}
            | {v for b in boxes for v in (b[0], b[2]) if target[0] < v < target[2]}
        )
        ys = sorted(
            {target[1], target[3]}
            | {v for b in boxes for v in (b[1], b[3]) if target[1] < v < target[3]}
        )
        for x, right in zip(xs, xs[1:], strict=False):
            for y, top in zip(ys, ys[1:], strict=False):
                context.ledger.charge("NATIVE_ENVELOPE_COVERAGE_CELL")
                if not any(a <= x and c >= right and b <= y and d >= top for a, b, c, d in boxes):
                    return False
        return True

    for row in rows:
        key = row["requirement_identity"]
        req = requirements[key]
        if row["status"] != "PASS":
            errors.append("NATIVE_NOT_PASS:" + key)
            continue
        portals = []
        for ref, name in ((req["from_ref"], "portal_from"), (req["to_ref"], "portal_to")):
            portal = row[name]
            a, b = _segment_from_mapping(portal["segment"], field=name)
            portals.append(((a[0] + b[0]) // 2, (a[1] + b[1]) // 2))
            allowed = zones[ref].polygon_mm if ref in zones else context.entrances[ref]
            if ref in zones:
                valid = any(
                    (
                        u[0] == v[0] == a[0] == b[0]
                        and min(u[1], v[1]) <= min(a[1], b[1]) <= max(a[1], b[1]) <= max(u[1], v[1])
                    )
                    or (
                        u[1] == v[1] == a[1] == b[1]
                        and min(u[0], v[0]) <= min(a[0], b[0]) <= max(a[0], b[0]) <= max(u[0], v[0])
                    )
                    for u, v in zip(allowed, allowed[1:] + allowed[:1], strict=True)
                )
            else:
                u, v = allowed
                valid = (
                    u[0] == v[0] == a[0] == b[0]
                    and min(u[1], v[1]) <= min(a[1], b[1]) <= max(a[1], b[1]) <= max(u[1], v[1])
                ) or (
                    u[1] == v[1] == a[1] == b[1]
                    and min(u[0], v[0]) <= min(a[0], b[0]) <= max(a[0], b[0]) <= max(u[0], v[0])
                )
            if not valid:
                errors.append("NATIVE_PORTAL_FACE:" + key)
        if row["topology"] == "DIRECT_SHARED_EDGE":
            if portals[0] != portals[1]:
                errors.append("NATIVE_DIRECT_NOT_SHARED:" + key)
            continue
        boxes = [
            rectangular_scope(normalize_polygon(p, allow_numeric_string=True))
            for p in row["corridor_envelope"]
        ]
        sx, sy, sr, st = context.sitebox
        for box in boxes:
            if (
                box[0] < sx
                or box[1] < sy
                or box[2] > sr
                or box[3] > st
                or any(_overlap(box, r) for r in room_boxes.values())
                or any(_overlap(box, r, closed=True) for r in context.obsboxes)
            ):
                errors.append("NATIVE_CORRIDOR_COLLISION:" + key)
            all_boxes.append((key, box))
        path = [point(p) for p in row["centerline"]]
        if len(path) < 2:
            errors.append("NATIVE_CORRIDOR_PATH_MISSING:" + key)
            continue
        width = int(Decimal(str(row["clear_width_m"])) * 1000)
        pw = int(Decimal(str(row["portal_from"]["clear_width_m"])) * 1000)
        for a, b, w in [(a, b, width) for a, b in zip(path, path[1:], strict=False)] + [
            (portals[0], path[0], pw),
            (path[-1], portals[1], pw),
        ]:
            if a == b:
                continue
            half = w // 2
            if a[0] == b[0]:
                target = (a[0] - half, min(a[1], b[1]), a[0] + w - half, max(a[1], b[1]))
            elif a[1] == b[1]:
                target = (min(a[0], b[0]), a[1] - half, max(a[0], b[0]), a[1] + w - half)
            else:
                errors.append("NATIVE_NONORTHOGONAL_ROUTE:" + key)
                continue
            if not covered(target, boxes):
                errors.append("NATIVE_INCOMPLETE_ENVELOPE:" + key)
        half = width // 2
        for x, y in path[1:-1]:
            if not covered((x - half, y - half, x + width - half, y + width - half), boxes):
                errors.append("NATIVE_TURN_ENVELOPE_MISSING:" + key)
    coexist = not any(a != b and _overlap(x, y) for (a, x), (b, y) in combinations(all_boxes, 2))
    if not coexist:
        errors.append("NATIVE_SHARED_CORRIDOR_REQUIRES_REVIEW")
    return {
        "pass": not errors,
        "errors": errors,
        "coexistence": coexist,
        "pass_count": 11 if not errors else None,
        "source": "ACTUAL_NATIVE_APPLICATION_CORRIDORS",
    }


def generate_global_composition_candidate(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    *,
    solver: GlobalCompositionSolver,
    composition_identity: str = DEFAULT_STAGE_A_COMPOSITION,
    execution_ledger: StageALedger | None = None,
) -> dict[str, Any]:
    """Server-owned internal entry; does not enter the official P3 selector."""
    ledger = execution_ledger if execution_ledger is not None else StageALedger()
    ledger.checkpoint("SERVER_AUTHORITY_REPLAY_STARTED")
    binding = bind_layout_authority(canonical_zone_plan, p1_handoff, site_geometry)
    compositions = build_structural_compositions(canonical_zone_plan, p1_handoff, site_geometry)
    _assert_server_replay(compositions, binding)
    selected = [
        h for h in compositions.placement_handoffs if h.composition_identity == composition_identity
    ]
    if len(selected) != 1:
        raise LayoutAuthorityError("GLOBAL_COMPOSITION_NOT_SERVER_GENERATED")
    # Reservations remain obligations. They neither add MUSTs nor turn the
    # historical P3 UNKNOWN gate into a positive or negative capacity proof.
    reserved = {
        (item.endpoint_a_role, item.endpoint_b_role)
        for item in selected[0].mandatory_interface_reservations
    }
    projected = {
        (item.endpoint_a_role, item.endpoint_b_role)
        for item in selected[0].mandatory_hard_interfaces
    }
    if reserved != set(process_graph().must_adjacencies) or projected != reserved:
        raise LayoutAuthorityError("GLOBAL_MANDATORY_RESERVATION_BINDING_MISMATCH")
    body = site_geometry.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = validated_hard_obstacle_polygons(body)
    pack_req = next(
        r
        for r in binding.access_requirements
        if r["from_ref"] == "packaging_material_storage" and r["to_ref"] == "sorting_packaging_room"
    )
    context = GlobalGenerationContext(
        binding,
        site_geometry,
        boundary,
        obstacles,
        rectangular_scope(boundary),
        tuple(rectangular_scope(p) for p in obstacles),
        {
            k: _segment_from_mapping(v, field=k)
            for k, v in body["entrances"].items()
            if k in {"main_entrance", "truck_entrance"}
        },
        tuple(process_graph().must_adjacencies),
        pack_req,
        resolve_access_profile(pack_req["profile_identity"]),
        ledger,
    )
    if ledger.execution_authorization is not None:
        ledger.execution_authorization.begin(
            {
                "zone_plan_hash": binding.canonical_zone_plan_hash,
                "p1_hash": binding.p1_handoff_hash,
                "site_hash": binding.site_geometry_hash,
                "composition_hash": selected[0].source_composition_hash,
            }
        )
    try:
        proposal = solver.solve(context, selected[0])
    finally:
        ledger.checkpoint("GENERATION_RETURNED_OR_INTERRUPTED")
    return validate_generated_global_proposal(
        canonical_zone_plan, p1_handoff, site_geometry, context, selected[0], proposal
    )


def validate_generated_global_proposal(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    context: GlobalGenerationContext,
    handoff: StructuralCompositionPlacementHandoffV1,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """Existing complete oracle, shared after trusted one-time context admission.

    Internal continuation helper, not an alternate public authority boundary.
    Every proposal repeats its own geometry/Access/Footprint validation.
    """
    ledger, binding, selected = context.ledger, context.binding, [handoff]
    if proposal.get("zones"):
        proposal["geometry_hash"] = zone_geometry_hash(proposal["zones"])
    result: dict[str, Any] = {
        "identity": IDENTITY,
        "server_owned_generation": bool(proposal.get("zones")),
        "historical_candidate_injected": False,
        "resource_scope": RESOURCE_SCOPE,
        "p3_complete": False,
        "p2_complete": False,
        "server_replay_accepted": False,
        "source_zone_plan_hash": binding.canonical_zone_plan_hash,
        "source_p1_handoff_hash": binding.p1_handoff_hash,
        "source_site_geometry_hash": binding.site_geometry_hash,
        "source_composition_hash": selected[0].source_composition_hash,
        "source_composition_handoff_hash": canonical_hash(selected[0].to_dict()),
        "composition_handoff": selected[0].to_dict(),
        "proposal": proposal,
    }
    if proposal.get("zones"):
        zones = {
            row["zone_code"]: PlacedRectangleV1(
                row["zone_code"],
                Decimal(str(row["x"])),
                Decimal(str(row["y"])),
                Decimal(str(row["width_m"])),
                Decimal(str(row["depth_m"])),
                row["rotation_deg"],
            )
            for row in proposal["zones"]
        }
        independent = validate_global_geometry(context, selected[0], zones, proposal["routes"])
        result["independent_validation"] = independent
        if independent["pass"]:
            side, face = _long_edges(zones["shipping_channel"])[0]
            placement = {
                "placement_result_identity": "site_constrained_factory_layout@1.0.0",
                "schema_version": "1.0.0",
                "source_zone_plan_hash": binding.canonical_zone_plan_hash,
                "source_p1_handoff_hash": binding.p1_handoff_hash,
                "source_site_geometry_hash": binding.site_geometry_hash,
                "source_objective_profile_hash": approved_objective_profile().canonical_result_hash,
                "placement_hard_constraints_passed": True,
                "zones": proposal["zones"],
                "shipping_loading_face_side": side,
                "shipping_loading_face_segment": _segment(face),
                "controlled_stage_a_candidate": True,
                "server_replay_accepted": False,
            }
            result["placement"] = placement
            placement["canonical_result_hash"] = canonical_hash(placement)
            try:
                with ledger.observe_native():
                    application = route_site_placement(
                        canonical_zone_plan,
                        p1_handoff,
                        site_geometry,
                        placement,
                        None,
                        route_search_hints={
                            route["requirement_identity"]: tuple(
                                tuple(point) for point in route["path_mm"]
                            )
                            for route in proposal["routes"]
                            if route["path_mm"]
                        },
                    ).to_dict()
                result["engineering_validation"] = application
                result["native_independent_validation"] = validate_native_access_geometry(
                    context, zones, application
                )
            except LayoutAuthorityError as error:
                result["engineering_validation_error"] = {
                    "code": error.code,
                    "details": error.details,
                }
    result["resource_ledger"] = {
        "model_construction_work": ledger.model_work,
        "native_host_work": ledger.native_host_work,
        "native_requirement_results": ledger.native_requirements,
        "peak_rss_bytes": ledger.peak_rss_bytes,
        "solver_wall_seconds": ledger.solver_wall,
        "attempts": ledger.attempts,
        "total_wall_seconds": time.monotonic() - ledger.started,
        "solver_wall_cap_seconds": 100,
        "experiment_wall_cap_seconds": 180,
        "workers": 1,
        "cp_sat_memory_cap_mib": 512,
        "formal_selector_replaced": False,
        "production_budget_mapping": getattr(
            ledger.execution_authorization,
            "resource_policy",
            "NOT_ESTABLISHED_CONTROLLED_INTERNAL_ENTRY_ONLY",
        ),
        "solver_history_verified": ledger.solver_history_verified,
        "native_solver_active": ledger.native_solver_active,
        "checked_solutions": ledger.checked_solutions,
        "native_grid_searches": ledger.native_grid_searches,
        "resource_events": ledger.resource_events,
    }
    app = result.get("engineering_validation", {})
    native_pass_count = sum(
        row.get("flow_kind") != "TRUCK" and row.get("status") == "PASS"
        for row in app.get("access_results", [])
    )
    result["stage_a_engineering_accepted"] = bool(
        result.get("independent_validation", {}).get("pass")
        and native_pass_count == 11
        and result.get("native_independent_validation", {}).get("pass")
        and app.get("building_footprint")
    )
    result["acceptance_status"] = (
        "STAGE_A_ENGINEERING_PASS"
        if result["stage_a_engineering_accepted"]
        else "STAGE_A_ENGINEERING_INCOMPLETE_NOT_FOR_SELECTOR"
    )
    result["canonical_result_hash"] = canonical_hash(result)
    return result
