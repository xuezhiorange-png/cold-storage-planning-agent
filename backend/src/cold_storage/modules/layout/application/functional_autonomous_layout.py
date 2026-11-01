"""Opt-in bounded room/equipment feedback, independent of Native and production.

Only flexible room shapes may respond to functional requests. Fixed P1 sizes,
area sources, profiles and original geometry predicates remain authoritative.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.application.access_routing import _zone_authority_checks
from cold_storage.modules.layout.application.autonomous_factory_layout import (
    _room_rows,
    bind_autonomous_input,
    structural_signature,
)
from cold_storage.modules.layout.domain.access_routing import derive_building_footprint
from cold_storage.modules.layout.domain.adjacency import (
    RectangleObservationV1,
    evaluate_adjacency,
    process_graph,
)
from cold_storage.modules.layout.domain.autonomous_room_search import search_room_arrangements
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.functional_changing_layout import (
    evaluate_changing_entry_exit,
    evaluate_changing_use,
)
from cold_storage.modules.layout.domain.functional_equipment_layout import (
    build_functional_equipment,
)
from cold_storage.modules.layout.domain.functional_portal_layout import (
    functional_interior_routes,
    joint_portals,
    storage_portal_interfaces,
)

VERSION = "autonomous-functional-feedback@1.1.0"


def generate_functional_layout(
    project: Mapping[str, Any],
    *,
    progress: Callable[[str], None] | None = None,
    coating_service_depth_mm: int | None = None,
) -> dict[str, Any]:
    specs = project["equipment_specs"]
    facts = project.get("owner_facts", {})
    expected = {
        "persons_per_shift": 53,
        "shifts": 2,
        "people_in_changing": 53,
        "locker_units": 11,
        "locker_columns": 22,
        "locker_compartments": 110,
        "changing_posture": "CABINET_FRONT_STANDING",
        "bench_count": 0,
    }
    if any(facts.get(k) != v for k, v in expected.items()):
        raise LayoutAuthorityError("UNSUPPORTED_FUNCTIONAL_OWNER_CONFIGURATION")
    if any(
        specs[k]["quantity"] != n
        for k, n in (
            ("packing_line", 6),
            ("case_erector", 5),
            ("locker", 11),
            ("case_film_line", 1),
        )
    ):
        raise LayoutAuthorityError("UNSUPPORTED_FUNCTIONAL_EQUIPMENT_CONFIGURATION")
    if [specs["locker"][k] for k in ("width_mm", "depth_mm", "height_mm")] != [850, 390, 1800]:
        raise LayoutAuthorityError("UNSUPPORTED_FUNCTIONAL_LOCKER_CONFIGURATION")
    if project["search"]["column_policy"] != "RETAIN_INTERNAL_COLUMNS_CONDITIONAL":
        raise LayoutAuthorityError("FUNCTIONAL_COLUMN_POLICY_NOT_SUPPORTED")
    context = bind_autonomous_input(project)
    b = project["building"]
    ent = b["openings"][1]["segment_mm"]
    shapes: dict[str, list[tuple[int, int]]] = {}
    open_chain = False
    attempts = []
    candidate: dict[str, Any] | None = None
    for iteration in range(3):
        if progress:
            progress(f"ROOM_EQUIPMENT_ITERATION {iteration + 1}")
        groups, stats = search_room_arrangements(
            context.binding.dimension_authorities,
            context.boundary,
            context.walls,
            internal_columns=context.columns,
            personnel_entry=((ent[0][0] + ent[1][0]) // 2, ent[0][1]),
            profile="LINEAR_BANDED",
            node_budget=int(project["search"]["node_budget"]),
            complete_limit=1,
            functional_shapes=shapes or None,
            functional_alignment=bool(shapes),
            functional_open_chain=open_chain,
        )
        if not groups:
            attempts.append(
                {
                    "iteration": iteration + 1,
                    "search": stats,
                    "status": "BOUNDED_ROOM_SEARCH_NO_CANDIDATE",
                }
            )
            break
        rooms = groups[0]
        equipment = build_functional_equipment(
            rooms,
            project["equipment_specs"],
            context.plan,
            b["columns"],
            context.binding.access_requirements,
        )
        requests = [f for f in equipment["failures"] if f.get("requested_shape_mm")]
        attempts.append(
            {
                "iteration": iteration + 1,
                "search": stats,
                "room_geometry_hash": canonical_hash(
                    {k: list(q.bounds_mm) for k, q in rooms.items()}
                ),
                "equipment_failures": equipment["failures"],
                "storage_trials": equipment["storage_trials"],
                "requested_flexible_shapes": requests,
                "status": "FEEDBACK_REQUESTED" if requests else "JOINT_CANDIDATE_GENERATED",
            }
        )
        if requests:
            for req in requests:
                code = req["room"]
                if (
                    context.binding.dimension_authorities[code]["dimension_mode"]
                    != "FLEXIBLE_RECTANGLE"
                ):
                    raise LayoutAuthorityError("FUNCTIONAL_FEEDBACK_CANNOT_RESIZE_FIXED_AUTHORITY")
                requested = tuple(req["requested_shape_mm"])
                if code == "coating_room" and coating_service_depth_mm is not None:
                    if not 7100 <= coating_service_depth_mm <= 12000:
                        raise LayoutAuthorityError("BOUNDED_COATING_SERVICE_DEPTH_REQUIRED")
                    requested = (requested[0], max(requested[1], coating_service_depth_mm))
                shapes[code] = [requested]
            continue
        rows = _room_rows(rooms, project, context)
        _zone_authority_checks(
            [
                {
                    "zone_code": code,
                    "x": str(q.x),
                    "y": str(q.y),
                    "width_m": str(q.width_m),
                    "depth_m": str(q.depth_m),
                    "rotation_deg": q.rotation_deg,
                }
                for code, q in rooms.items()
            ],
            context.binding.dimension_authorities,
            context.boundary,
            context.walls,
        )
        adjacency = evaluate_adjacency(
            process_graph(),
            tuple(
                RectangleObservationV1(
                    q.zone_code,
                    Decimal(str(q.x)),
                    Decimal(str(q.y)),
                    Decimal(str(q.width_m)),
                    Decimal(str(q.depth_m)),
                    q.rotation_deg,
                )
                for q in rooms.values()
            ),
        )
        if not adjacency["geometry_passed"]:
            raise LayoutAuthorityError("JOINT_CANDIDATE_ORIGINAL_GEOMETRY_REJECTED")
        entrances: dict[str, Any] = {
            "main_entrance": tuple(tuple(p) for p in ent),
            "truck_entrance": tuple(tuple(p) for p in b["openings"][0]["segment_mm"]),
        }
        if progress:
            progress("JOINT_LEGAL_PORTALS_AND_INTERIOR_ROUTES")
        access, corridors, approaches = joint_portals(
            rooms,
            context.binding.access_requirements,
            context.binding.spatial_relationships,
            equipment,
            context.boundary,
            context.columns + context.walls,
            entrances,
        )
        paths = functional_interior_routes(rooms, access, equipment, b["columns"])
        storage_interfaces = storage_portal_interfaces(rooms, access, equipment, b["columns"])
        try:
            fp = derive_building_footprint(rooms, corridors)
            footprint: dict[str, Any] = {
                "status": "SINGLE_CONNECTED_ZERO_HOLE_UNION",
                "points_mm": [list(p) for p in fp],
                "note": "Generated occupied union, not original building boundary",
            }
        except LayoutAuthorityError as error:
            footprint = {"status": "NOT_VERIFIED", "code": error.code, "details": error.details}
        if footprint["status"] != "SINGLE_CONNECTED_ZERO_HOLE_UNION" and iteration < 2:
            attempts[-1]["topology_feedback"] = footprint
            attempts[-1]["status"] = "TOPOLOGY_FEEDBACK_REQUESTED"
            open_chain = True
            continue
        g = equipment["layouts"]["changing_room"].get("functional_geometry", {})
        if progress:
            progress("TWO_SHIFTS_53_REAL_HOME_AND_CABINET_CYCLES")
        changing = evaluate_changing_use(g)
        changing["entry_exit"] = evaluate_changing_entry_exit(g, rooms["changing_room"], access)
        changing["conditional_complete_sequence_verified"] = bool(
            changing.get("initial_53_people_verified")
            and all(s["cycle_geometry_pass"] for s in changing.get("shifts", []))
            and changing["entry_exit"].get("entry_exit_verified")
        )
        remaining: list[dict[str, Any]] = []
        remaining.extend(
            {
                "code": "PORTAL_APPROACH_CONFLICT",
                "room": a["room"],
                "requirement": a["requirement_identity"],
            }
            for a in approaches
            if a["status"] != "BODY_FREE_APPROACH"
        )
        remaining.extend(
            {"code": "INTERIOR_ROUTE_NOT_PROVEN", "room": p["room"]}
            for p in paths
            if p["status"] != "INTERIOR_FULL_WIDTH_PATH_VERIFIED"
        )
        remaining.extend(
            {
                "code": "RESERVED_AISLE_COLUMN_OR_BODY_CONFLICT",
                "room": a["room"],
                "objects": a["conflicts"],
            }
            for a in equipment["operating_spaces"]
            if a["conflicts"]
        )
        remaining.extend(
            {"code": "STORAGE_PORTAL_INTERFACE_NOT_PROVEN", "room": p["room"]}
            for p in storage_interfaces
            if p["status"] != "STORAGE_AISLE_TO_REAL_PORTAL_VERIFIED"
        )
        candidate = {
            "schema_version": VERSION,
            "candidate_status": "CONDITIONAL_CONCEPT_NOT_P2D",
            "profile_requested": "LINEAR_BANDED",
            "source_input_hash": canonical_hash(project),
            "source_zone_plan_hash": context.binding.canonical_zone_plan_hash,
            "source_p1_handoff_hash": context.binding.p1_handoff_hash,
            "source_building_hash": canonical_hash(b),
            "structural_signature": structural_signature(rooms),
            "rooms": rows,
            "original_building": b,
            "dimension_and_area_authorities_unchanged": True,
            "room_non_overlap_and_MUST": adjacency,
            "legacy_room_obstacle_oracle": {
                "status": "PASS",
                "internal_columns": "RETAINED_OWNER_ALLOWED; NET_AREA_SEPARATE",
            },
            "access_results": access,
            "portal_approach_checks": approaches,
            "non_truck_access_pass_count": sum(
                a.get("status") == "PASS" for a in access if a["flow_kind"] != "TRUCK"
            ),
            "equipment": equipment,
            "equipment_aware_interior_paths": paths,
            "storage_portal_interfaces": storage_interfaces,
            "changing_function": changing,
            "building_footprint": footprint,
            "remaining_geometry_issues": remaining,
            "metrics": {
                "room_count": len(rows),
                "gross_room_area_m2": str(sum(q.actual_area_m2 for q in rooms.values())),
                "retained_internal_column_area_m2": str(
                    sum(Decimal(r["column_area_m2"]) for r in rows)
                ),
                "portal_approach_conflict_count": sum(
                    a["status"] != "BODY_FREE_APPROACH" for a in approaches
                ),
                "verified_interior_route_count": sum(
                    p["status"] == "INTERIOR_FULL_WIDTH_PATH_VERIFIED" for p in paths
                ),
            },
            "truck_route_validated": False,
            "P2D_full_pass": False,
            "factory_applicability": "NOT_EVALUATED",
            "engineering_approval": "NOT_EVALUATED",
            "native_calls": 0,
        }
        candidate["result_hash"] = canonical_hash(candidate)
        break
    result = {
        "task_id": "V2_2_2_AUTONOMOUS_FACTORY_LAYOUT_FUNCTIONAL_CLOSURE_R1",
        "calculator_version": VERSION,
        "business_input": project["business"],
        "source_input_hash": canonical_hash(project),
        "p1_handoff_hash": context.binding.p1_handoff_hash,
        "zone_plan": context.plan,
        "attempts": attempts,
        "candidate_count": int(candidate is not None),
        "candidates": [candidate] if candidate else [],
        "status": "CONDITIONAL_JOINT_CANDIDATE_GENERATED"
        if candidate
        else "BOUNDED_SEARCH_NO_CANDIDATE",
        "source_layout_coordinates_loaded": False,
        "native_calls": 0,
        "MAIN": False,
        "grant_claim_accessed": False,
        "production_default_changed": False,
        "global_infeasibility_proven": False,
    }
    result["result_hash"] = canonical_hash(result)
    return result
