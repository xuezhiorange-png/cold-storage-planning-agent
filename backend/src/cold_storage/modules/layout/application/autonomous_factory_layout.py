"""Explicit standalone concept-design composition, separate from production/MCP.

Reads one geometry/specification input, replays existing area and P1 rules, and
does bounded non-native placement. Conditional results cannot enter P2D selection.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.access_routing import _zone_authority_checks
from cold_storage.modules.layout.application.layout_authority_binding import (
    LayoutAuthorityBindingV1,
    bind_layout_authority,
)
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import (
    ValidatedSiteGeometryV1,
    validate_site_geometry,
)
from cold_storage.modules.layout.domain.access_routing import (
    derive_building_footprint,
    route_access_requirement,
)
from cold_storage.modules.layout.domain.adjacency import (
    RectangleObservationV1,
    evaluate_adjacency,
    process_graph,
)
from cold_storage.modules.layout.domain.autonomous_equipment import (
    place_factory_equipment,
    positive_intersection,
)
from cold_storage.modules.layout.domain.autonomous_process_routes import (
    route_equipment_aware_interiors,
)
from cold_storage.modules.layout.domain.autonomous_room_search import (
    PROFILES,
    search_room_arrangements,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    SegmentMM,
    normalize_polygon,
)

VERSION = "autonomous-factory-layout-concept@1.0.0"


def _polygon(b: Sequence[int]) -> dict[str, Any]:
    return {
        "type": "polygon",
        "points": [
            {"x": x / 1000, "y": y / 1000}
            for x, y in ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3]))
        ],
    }


def _segment(ps: Sequence[Sequence[int]]) -> dict[str, Any]:
    return {
        name: {"x": p[0] / 1000, "y": p[1] / 1000}
        for name, p in zip(("start", "end"), ps, strict=True)
    }


@dataclass(frozen=True)
class AutonomousContext:
    plan: dict[str, Any]
    p1: Any
    site: ValidatedSiteGeometryV1
    binding: LayoutAuthorityBindingV1
    boundary: PolygonMM
    columns: tuple[PolygonMM, ...]
    walls: tuple[PolygonMM, ...]


def bind_autonomous_input(project: Mapping[str, Any]) -> AutonomousContext:
    if project.get("schema_version") != "autonomous-factory-input@1.0.0":
        raise LayoutAuthorityError("AUTONOMOUS_INPUT_VERSION_INVALID")
    b = project["building"]
    if b.get("source_type") != "OWNER_ORIGINAL_DRAWING_STRUCTURE_ONLY":
        raise LayoutAuthorityError("ORIGINAL_BUILDING_STRUCTURE_SOURCE_REQUIRED")
    forbidden = {
        "rooms",
        "zones",
        "room_positions",
        "candidates",
        "equipment_positions",
        "initial_layout",
        "hints",
        "historical_coordinates",
    }
    if forbidden.intersection(project) or forbidden.intersection(b):
        raise LayoutAuthorityError("HISTORICAL_LAYOUT_INPUT_FORBIDDEN")
    if b["coordinate_mapping"]["axis_x_mm"] != list(range(0, 108001, 6000)):
        raise LayoutAuthorityError("ARCHIVED_AXIS_MAPPING_MISMATCH")
    if any(
        key in str(project["equipment_specs"]).lower()
        for key in ("bbox_mm", "world_x", "world_y", "center_mm")
    ):
        raise LayoutAuthorityError("EQUIPMENT_WORLD_SEED_FORBIDDEN")
    floor = b["clear_building_bbox_mm"]
    columns: list[dict[str, Any]] = []
    walls: list[dict[str, Any]] = []

    def clipped(box: Sequence[int]) -> dict[str, Any] | None:
        q = [
            max(box[0], floor[0]),
            max(box[1], floor[1]),
            min(box[2], floor[2]),
            min(box[3], floor[3]),
        ]
        return _polygon(q) if q[2] > q[0] and q[3] > q[1] else None

    for col in b["columns"]:
        if value := clipped(col["bbox_mm"]):
            columns.append(value)
    for wall in b["retained_walls"]:
        for a, c in wall["segments_mm"]:
            value = clipped(
                [min(a[0], c[0]) - 1, min(a[1], c[1]) - 1, max(a[0], c[0]) + 1, max(a[1], c[1]) + 1]
            )
            if value:
                walls.append(value)
    plan = asdict(ColdRoomZonePlanner().plan(ColdRoomZonePlanInput(**project["business"])))
    p1 = build_p1_project_handoff(plan, {})
    room_obstacles = (
        walls
        if project["search"].get("column_policy") == "RETAIN_INTERNAL_COLUMNS_CONDITIONAL"
        else columns + walls
    )
    site = validate_site_geometry(
        {
            "site_constraints": {
                "site_boundary": _polygon(floor),
                "main_entrance": _segment(b["openings"][1]["segment_mm"]),
                "truck_entrance": _segment(b["openings"][0]["segment_mm"]),
                "no_build_zones": room_obstacles,
                "preferred_loading_side": "SOUTH",
            },
            "truck_access": {},
        },
        plan,
        p1_handoff=p1,
    )
    body = site.to_dict()
    return AutonomousContext(
        plan,
        p1,
        site,
        bind_layout_authority(plan, p1, site),
        normalize_polygon(body["site"]["effective_buildable_boundary"], allow_numeric_string=True),
        tuple(normalize_polygon(p, allow_numeric_string=True) for p in columns),
        tuple(normalize_polygon(p, allow_numeric_string=True) for p in walls),
    )


def structural_signature(rooms: Mapping[str, PlacedRectangleV1]) -> str:
    """Contact graph is invariant to translation, reflection and 90-degree rotation."""
    contacts = []
    for a, first in sorted(rooms.items()):
        x, y, r, t = first.bounds_mm
        for b, second in sorted(rooms.items()):
            if b <= a:
                continue
            u, v, s, z = second.bounds_mm
            if ((r == u or s == x) and min(t, z) > max(y, v)) or (
                (t == v or z == y) and min(r, s) > max(x, u)
            ):
                contacts.append([a, b])
    return canonical_hash(contacts)


def _room_rows(
    rooms: Mapping[str, PlacedRectangleV1], project: Mapping[str, Any], context: AutonomousContext
) -> list[dict[str, Any]]:
    names = {z["zone_code"]: z["zone_name"] for z in context.plan["result"]["zones"]}
    rows = []
    for code, q in sorted(rooms.items()):
        a = context.binding.dimension_authorities[code]
        cols = []
        area = 0
        for c in project["building"]["columns"]:
            b = c["bbox_mm"]
            if positive_intersection(q.bounds_mm, b):
                cols.append(c["id"])
                area += (min(q.bounds_mm[2], b[2]) - max(q.bounds_mm[0], b[0])) * (
                    min(q.bounds_mm[3], b[3]) - max(q.bounds_mm[1], b[1])
                )
        rows.append(
            {
                "zone_code": code,
                "name": names[code],
                "bbox_mm": list(q.bounds_mm),
                "x_mm": q.bounds_mm[0],
                "y_mm": q.bounds_mm[1],
                "width_mm": q.bounds_mm[2] - q.bounds_mm[0],
                "depth_mm": q.bounds_mm[3] - q.bounds_mm[1],
                "authority_width_m": str(q.width_m),
                "authority_depth_m": str(q.depth_m),
                "rotation_deg": q.rotation_deg,
                "area_m2": str(q.actual_area_m2),
                "required_area_m2": a["required_area_m2"],
                "dimension_mode": a["dimension_mode"],
                "dimension_authority_identity": a["dimension_authority_identity"],
                "area_requirement": a["area_requirement"],
                "internal_columns": cols,
                "column_area_m2": str(Decimal(area) / 1000000),
                "floor_minus_columns_m2": str(q.actual_area_m2 - Decimal(area) / 1000000),
                "net_functional_capacity_status": "NOT_EVALUATED_GROSS_P1_AREA_IS_NOT_NET_CAPACITY",
            }
        )
    return rows


def evaluate_generated_rooms(
    rooms: dict[str, PlacedRectangleV1],
    project: Mapping[str, Any],
    context: AutonomousContext,
    profile: str,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    observations = tuple(
        RectangleObservationV1(
            q.zone_code,
            Decimal(str(q.x)),
            Decimal(str(q.y)),
            Decimal(str(q.width_m)),
            Decimal(str(q.depth_m)),
            q.rotation_deg,
        )
        for q in rooms.values()
    )
    adjacency = evaluate_adjacency(process_graph(), observations)
    if not adjacency["geometry_passed"]:
        raise LayoutAuthorityError("GENERATED_ADJACENCY_OR_OVERLAP_REJECTED")
    legacy: dict[str, Any] = {
        "status": "PASS",
        "scope": (
            "Original P1 gross dimensions, real building boundary an"
            "d retained walls; Owner permits retained internal colum"
            "ns"
        ),
    }
    legacy_rows = [
        {
            "zone_code": code,
            "x": str(q.x),
            "y": str(q.y),
            "width_m": str(q.width_m),
            "depth_m": str(q.depth_m),
            "rotation_deg": q.rotation_deg,
        }
        for code, q in rooms.items()
    ]
    try:
        _zone_authority_checks(
            legacy_rows,
            context.binding.dimension_authorities,
            context.boundary,
            context.walls
            + (
                context.columns
                if project["search"]["column_policy"] == "EXCLUDE_COLUMNS_FROM_ROOMS"
                else ()
            ),
        )
    except LayoutAuthorityError as error:
        legacy = {
            "status": "REJECTED_BY_ORIGINAL_ROOM_OBSTACLE_MODEL",
            "code": error.code,
            "details": error.details,
        }
    access = []
    corridors: list[PolygonMM] = []
    relation = {str(q["identity"]): q for q in context.binding.spatial_relationships}
    ent = project["building"]["openings"]
    entrances: dict[str, SegmentMM] = {}
    for ref, item in (("main_entrance", ent[1]), ("truck_entrance", ent[0])):
        a, b = item["segment_mm"]
        entrances[ref] = ((int(a[0]), int(a[1])), (int(b[0]), int(b[1])))
    for requirement in context.binding.access_requirements:
        if requirement["flow_kind"] == "TRUCK":
            access.append(
                {
                    "requirement_identity": requirement["identity"],
                    "flow_kind": "TRUCK",
                    "status": "INPUT_REQUIRED_ACTUAL_VEHICLE_AND_LAND_SITE",
                    "truck_pass": False,
                }
            )
            continue
        if progress:
            progress("ACCESS " + str(requirement["identity"]))
        row, polys = route_access_requirement(
            requirement,
            relationships=relation,
            zones=rooms,
            boundary=context.boundary,
            obstacles=context.columns + context.walls,
            entrances=entrances,
            route_node_budget=24,
        )
        access.append(row)
        corridors.extend(polys)
    try:
        footprint = derive_building_footprint(rooms, corridors)
        fp: dict[str, Any] = {
            "status": "SINGLE_CONNECTED_ZERO_HOLE_UNION",
            "points_mm": [list(p) for p in footprint],
            "note": "Generated occupied room/corridor union, not original building envelope",
            "area_m2": str(
                Decimal(
                    abs(
                        sum(
                            a[0] * b[1] - a[1] * b[0]
                            for a, b in zip(footprint, (*footprint[1:], footprint[0]), strict=True)
                        )
                    )
                )
                / 2000000
            ),
            "perimeter_m": str(
                Decimal(
                    sum(
                        abs(a[0] - b[0]) + abs(a[1] - b[1])
                        for a, b in zip(footprint, (*footprint[1:], footprint[0]), strict=True)
                    )
                )
                / 1000
            ),
        }
    except LayoutAuthorityError as error:
        fp = {"status": "NOT_VERIFIED", "code": error.code, "details": error.details}
    equipment = place_factory_equipment(
        rooms, project["equipment_specs"], context.plan, project["building"]["columns"], access
    )
    interior_routes = route_equipment_aware_interiors(
        rooms, access, equipment, project["building"]["columns"]
    )
    rows = _room_rows(rooms, project, context)
    result = {
        "schema_version": VERSION,
        "profile_requested": profile,
        "profile_certification": "SEARCH_PREFERENCE_NOT_FORMAL_V2_COMPOSITION_ACCEPTANCE",
        "candidate_status": "CONDITIONAL_CONCEPT_NOT_P2D",
        "source_input_hash": canonical_hash(project),
        "source_zone_plan_hash": context.binding.canonical_zone_plan_hash,
        "source_p1_handoff_hash": context.binding.p1_handoff_hash,
        "source_building_hash": canonical_hash(project["building"]),
        "structural_signature": structural_signature(rooms),
        "rooms": rows,
        "original_building": project["building"],
        "dimension_and_area_authorities_unchanged": True,
        "room_non_overlap_and_MUST": adjacency,
        "legacy_room_obstacle_oracle": legacy,
        "access_results": access,
        "non_truck_access_pass_count": sum(
            r.get("status") == "PASS" for r in access if r["flow_kind"] != "TRUCK"
        ),
        "building_footprint": fp,
        "equipment": equipment,
        "equipment_aware_interior_paths": interior_routes,
        "metrics": {
            "room_count": len(rows),
            "gross_room_area_m2": str(sum(q.actual_area_m2 for q in rooms.values())),
            "retained_internal_column_area_m2": str(
                sum(Decimal(q["column_area_m2"]) for q in rows)
            ),
            "validated_interroom_route_length_m": str(
                sum(
                    Decimal(str(q.get("route_length_m", 0)))
                    for q in access
                    if q.get("status") == "PASS"
                )
            ),
            "validated_interroom_turns": sum(
                int(q.get("turn_count", 0)) for q in access if q.get("status") == "PASS"
            ),
            "route_metric_scope": (
                "Original P1 inter-room portal/corridor routes only; int"
                "erior equipment routes not included"
            ),
        },
        "truck_route_validated": False,
        "P2D_full_pass": False,
        "factory_applicability": "NOT_EVALUATED",
        "engineering_approval": "NOT_EVALUATED",
        "native_calls": 0,
    }
    result["result_hash"] = canonical_hash(result)
    return result


def generate_autonomous_layouts(
    project: Mapping[str, Any], *, progress: Callable[[str], None] | None = None
) -> dict[str, Any]:
    context = bind_autonomous_input(project)
    policy = project["search"].get("column_policy", "EXCLUDE_COLUMNS_FROM_ROOMS")
    if policy not in ("EXCLUDE_COLUMNS_FROM_ROOMS", "RETAIN_INTERNAL_COLUMNS_CONDITIONAL"):
        raise LayoutAuthorityError("COLUMN_INTERPRETATION_INVALID")
    results = []
    attempts = []
    signatures = set()
    for profile in PROFILES:
        if progress:
            progress("SEARCH " + profile)
        entry = project["building"]["openings"][1]["segment_mm"]
        rooms, stats = search_room_arrangements(
            context.binding.dimension_authorities,
            context.boundary,
            context.walls + (context.columns if policy == "EXCLUDE_COLUMNS_FROM_ROOMS" else ()),
            internal_columns=context.columns
            if policy == "RETAIN_INTERNAL_COLUMNS_CONDITIONAL"
            else (),
            personnel_entry=((entry[0][0] + entry[1][0]) // 2, entry[0][1]),
            profile=profile,
            node_budget=int(project["search"]["node_budget"]),
            complete_limit=1,
        )
        attempts.append(stats)
        if rooms:
            signature = structural_signature(rooms[0])
            if signature not in signatures:
                if progress:
                    progress("ROOMS_FOUND " + profile)
                results.append(
                    evaluate_generated_rooms(rooms[0], project, context, profile, progress)
                )
                signatures.add(signature)
        if len(results) >= int(project["search"]["candidate_limit"]):
            break
    body = {
        "task_id": "V2_2_2_AUTONOMOUS_FACTORY_LAYOUT_GENERATION_V1",
        "calculator_version": VERSION,
        "source_input_hash": canonical_hash(project),
        "business_input": project["business"],
        "zone_plan": context.plan,
        "p1_handoff_hash": context.binding.p1_handoff_hash,
        "column_policy": policy,
        "column_policy_basis": project["search"].get("column_policy_source"),
        "attempts": attempts,
        "candidate_count": len(results),
        "candidates": results,
        "native_calls": 0,
        "MAIN": False,
        "grant_claim_accessed": False,
        "production_default_changed": False,
        "global_infeasibility_proven": False,
        "source_layout_coordinates_loaded": False,
        "status": "CONDITIONAL_CANDIDATES_GENERATED" if results else "BOUNDED_SEARCH_NO_CANDIDATE",
    }
    body["result_hash"] = canonical_hash(body)
    return body
