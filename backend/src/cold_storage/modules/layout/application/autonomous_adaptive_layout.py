"""Opt-in deterministic, bounded room/storage/process regeneration.

Each invocation starts from current business input and the existing attachment
search. No candidate files, Owner layout coordinates, Native or Store are read.
All retained results pass the V1.2 full process admission after regeneration.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.application.access_routing import _zone_authority_checks
from cold_storage.modules.layout.application.autonomous_factory_layout import (
    _room_rows,
    bind_autonomous_input,
)
from cold_storage.modules.layout.application.autonomous_process_continuity import (
    evaluate_process_rooms,
    validate_process_parameters,
)
from cold_storage.modules.layout.application.functional_autonomous_layout import (
    generate_functional_layout,
)
from cold_storage.modules.layout.domain.adaptive_room_feedback import feedback_room_proposals
from cold_storage.modules.layout.domain.adjacency import (
    RectangleObservationV1,
    evaluate_adjacency,
    process_graph,
)
from cold_storage.modules.layout.domain.current_process_requirements import (
    current_passage_requirements,
    current_storage_requirements,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.functional_equipment_layout import (
    build_functional_equipment,
)
from cold_storage.modules.layout.domain.functional_storage_layout import storage_layouts
from cold_storage.modules.layout.domain.process_flow_arrangement import coating_service_depth
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

VERSION = "autonomous-adaptive-process-layout@1.3.0"


def _rectangles(c: Mapping[str, Any]) -> dict[str, PlacedRectangleV1]:
    return {
        r["zone_code"]: PlacedRectangleV1(
            r["zone_code"],
            Decimal(r["x_mm"]) / 1000,
            Decimal(r["y_mm"]) / 1000,
            Decimal(r["authority_width_m"]),
            Decimal(r["authority_depth_m"]),
            r["rotation_deg"],
        )
        for r in c["rooms"]
    }


def _space_signature(c: Mapping[str, Any]) -> str:
    return canonical_hash(
        {
            "rooms": c["rooms"],
            "equipment": [(q["id"], q["bbox_mm"]) for q in c["equipment"]["items"]],
        }
    )


def _metrics(c: Mapping[str, Any]) -> dict[str, Any]:
    from cold_storage.modules.layout.domain.access_routing import _turn_count

    selected = set(c["process_admission"]["selected_route_ids"])
    transport = [
        q for q in c["process_continuity"]["routes"] if q["id"] in selected and "source_dock" in q
    ]
    horizontal = []
    vertical = []
    for r in transport:
        for a, b in zip(r["centerline_mm"], r["centerline_mm"][1:], strict=False):
            if a[1] == b[1] and a[0] != b[0]:
                horizontal.append((min(a[0], b[0]), max(a[0], b[0]), a[1], r["id"]))
            if a[0] == b[0] and a[1] != b[1]:
                vertical.append((a[0], min(a[1], b[1]), max(a[1], b[1]), r["id"]))
    crossings = {
        (x, y, min(a, b), max(a, b))
        for x0, x1, y, a in horizontal
        for x, y0, y1, b in vertical
        if a != b and x0 < x < x1 and y0 < y < y1
    }
    fp = c["building_footprint"]["points_mm"]
    edges = list(zip(fp, [*fp[1:], fp[0]], strict=True))
    twice_area = abs(sum(a[0] * b[1] - a[1] * b[0] for a, b in edges))
    return {
        "selected_transport_reference_length_mm": sum(q["length_mm"] for q in transport),
        "selected_transport_turns": sum(
            _turn_count([tuple(p) for p in q["centerline_mm"]]) for q in transport
        ),
        "gross_room_area_m2": str(sum(Decimal(r["area_m2"]) for r in c["rooms"])),
        "footprint_area_m2": str(Decimal(twice_area) / 2_000_000),
        "footprint_perimeter_mm": sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in edges),
        "footprint_corners": len(fp),
        "potential_route_crossings": len(crossings),
        "crossing_scope": "INTERIOR_CENTRELINE_INTERSECTIONS_NOT_SIMULTANEOUS_TRAFFIC_COLLISIONS",
        "length_scope": "DISTINCT_SELECTED_TRANSPORT_REFERENCE_SEGMENTS_NOT_SINGLE_VEHICLE_MILEAGE",
        "formal_nine_twelve_comparison": "NOT_EVALUATED_UNCHANGED_AUTHORITY_COMPARATORS",
    }


def generate_adaptive_layout(
    project: Mapping[str, Any],
    parameters: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    validate_process_parameters(parameters)
    budget = int(config["candidate_node_budget"])
    full_budget = int(config["full_evaluation_budget"])
    limit = int(config["candidate_limit"])
    if (
        not 3 <= budget <= 48
        or not 2 <= full_budget <= 12
        or not 1 <= limit <= 4
        or not 0 <= int(config.get("initial_endpoint_rank", 0)) <= 3
        or not 0 <= int(config.get("initial_storage_choice_rank", 0)) <= 7
    ):
        raise LayoutAuthorityError("ADAPTIVE_SEARCH_BOUNDS_INVALID")
    context = bind_autonomous_input(project)
    config_hash = canonical_hash(config)
    requirements = current_storage_requirements(context.plan)
    prepared = generate_functional_layout(
        project,
        progress=progress,
        coating_service_depth_mm=coating_service_depth(parameters)["depth_mm"],
    )
    attempts: list[dict[str, Any]] = []
    accepted = []
    signatures: set[str] = set()
    full_used = 0
    if not prepared["candidates"]:
        exhausted = {
            "task_id": "V2_2_2_AUTONOMOUS_ADAPTIVE_LAYOUT_REGENERATION_R1",
            "calculator_version": VERSION,
            "source_input_hash": canonical_hash(project),
            "source_process_parameter_hash": canonical_hash(parameters),
            "source_search_config_hash": config_hash,
            "search_configuration": dict(config),
            "current_storage_requirements": requirements,
            "zone_plan": context.plan,
            "status": "BOUNDED_INITIAL_ATTACHMENT_SEARCH_NO_CANDIDATE",
            "candidates": [],
            "candidate_count": 0,
            "initial_search": prepared,
            "attempts": [],
            "search_budget": {
                "candidate_node_budget": budget,
                "candidate_nodes_used": 0,
                "full_evaluation_budget": full_budget,
                "full_evaluations_used": 0,
                "initial_room_search_runs": prepared.get("attempts", []),
            },
            "operation_counts": {},
            "native_calls": 0,
            "global_infeasibility_proven": False,
        }
        exhausted["result_hash"] = canonical_hash(exhausted)
        return exhausted
    source = prepared["candidates"][0]
    rooms = _rectangles(source)
    passage_requirements = current_passage_requirements(
        context.binding.access_requirements, list(rooms)
    )
    initial_check = {
        "accepted": False,
        "status": "ROOM_SEED_ONLY_NOT_PROCESS_ADMITTED",
        "stored_grid_counts": {
            s["layout"]["room"]: s["layout"]["placed_positions"]
            for s in source["equipment"]["storage"]
        },
        "requirements_only_no_prior_geometry_pass": True,
    }
    queue = feedback_room_proposals(
        rooms,
        project["building"]["columns"],
        context.binding.dimension_authorities,
        node_budget=budget,
    )

    def enqueue_feedback(
        row: dict[str, Any], proposal: dict[str, Any], reasons: Any, storage_rank: int, rank: int
    ) -> None:
        if int(proposal.get("feedback_depth", 0)) >= 1:
            return
        next_storage = 0 if storage_rank else 1
        next_endpoint = 0 if rank else 1
        retry = {
            **proposal,
            "kind": "INTERFACE_FAILURE_FEEDBACK",
            "endpoint_rank": next_endpoint,
            "storage_rank": next_storage,
            "feedback_depth": 1,
            "feedback_from_node": row["node"],
        }
        queue.insert(0, retry)
        row["feedback_enqueued"] = {
            "endpoint_rank": next_endpoint,
            "storage_rank": next_storage,
            "cause": reasons,
        }

    seen = set()
    while queue and len(attempts) < budget and full_used < full_budget:
        proposal = queue.pop(0)
        state = proposal["rooms"]
        rank = int(proposal.get("endpoint_rank", config.get("initial_endpoint_rank", 0)))
        storage_rank = int(
            proposal.get("storage_rank", config.get("initial_storage_choice_rank", 0))
        )
        identity = canonical_hash([proposal["room_geometry_hash"], rank, storage_rank])
        if identity in seen:
            continue
        seen.add(identity)
        row = {k: v for k, v in proposal.items() if k != "rooms"}
        row.update(
            node=len(attempts) + 1,
            room_coordinates=[
                {
                    "zone_code": k,
                    "bbox_mm": list(q.bounds_mm),
                    "width_m": str(q.width_m),
                    "depth_m": str(q.depth_m),
                    "rotation_deg": q.rotation_deg,
                }
                for k, q in sorted(state.items())
            ],
        )
        attempts.append(row)
        if progress:
            progress(f"ADAPTIVE_NODE {row['node']} {proposal['kind']}")
        try:
            _zone_authority_checks(
                [
                    {
                        "zone_code": k,
                        "x": str(q.x),
                        "y": str(q.y),
                        "width_m": str(q.width_m),
                        "depth_m": str(q.depth_m),
                        "rotation_deg": q.rotation_deg,
                    }
                    for k, q in state.items()
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
                        Decimal(q.x),
                        Decimal(q.y),
                        Decimal(q.width_m),
                        Decimal(q.depth_m),
                        q.rotation_deg,
                    )
                    for q in state.values()
                ),
            )
            if not adjacency["geometry_passed"]:
                raise LayoutAuthorityError("ADAPTIVE_ORIGINAL_ADJACENCY_OR_OVERLAP_REJECTED")
            for q in state.values():
                a, b, r, t = q.bounds_mm
                if any(
                    min(r, o["bbox_mm"][2]) > max(a, o["bbox_mm"][0])
                    and min(t, o["bbox_mm"][3]) > max(b, o["bbox_mm"][1])
                    and not (
                        a <= o["bbox_mm"][0]
                        and b <= o["bbox_mm"][1]
                        and r >= o["bbox_mm"][2]
                        and t >= o["bbox_mm"][3]
                    )
                    for o in project["building"]["columns"]
                ):
                    raise LayoutAuthorityError(
                        "ADAPTIVE_PARTITION_CUTS_RETAINED_COLUMN", details={"room": q.zone_code}
                    )
        except LayoutAuthorityError as error:
            row.update(
                status="ORIGINAL_ROOM_CONSTRAINT_REJECTED", code=error.code, details=error.details
            )
            continue
        zone = next(
            z for z in context.plan["result"]["zones"] if z["zone_code"] == "finished_goods_room"
        )
        layouts = storage_layouts(
            state["finished_goods_room"],
            zone,
            project["building"]["columns"],
            allow_pallet_rotation=True,
        )
        row["finished_storage_trials"] = [
            {
                "layout": q["id"],
                "positions": q["placed_positions"],
                "required": q["required_grid_capacity"],
                "blocking_columns": q["main_aisle_column_conflicts"],
                "static_pass": q["static_capacity_pass"],
            }
            for q in layouts
        ]
        if not any(q["static_capacity_pass"] for q in layouts):
            row["status"] = "CURRENT_GRID_CAPACITY_REJECTED"
            row["failure_location"] = {
                "room": "finished_goods_room",
                "bbox_mm": list(state["finished_goods_room"].bounds_mm),
                "required_positions": requirements["finished_goods_room"]["required_positions"],
                "blocking_column_ids": sorted(
                    {id_ for trial in layouts for id_ in trial["main_aisle_column_conflicts"]}
                ),
                "next_search_families": sorted({p["kind"] for p in queue}),
            }
            continue
        full_used += 1
        fresh = copy.deepcopy(source)
        fresh.pop("storage_preservation_failure", None)
        fresh["rooms"] = _room_rows(state, project, context)
        fresh["room_non_overlap_and_MUST"] = adjacency
        equipment = build_functional_equipment(
            state,
            project["equipment_specs"],
            context.plan,
            project["building"]["columns"],
            context.binding.access_requirements,
            adaptive_storage=True,
            storage_choice_rank={"finished_goods_room": storage_rank},
        )
        row["operation_counts"] = {
            "stock_motion_attempts": sum(
                s["movement"]["motion_attempts"] for s in equipment["storage"]
            ),
            "stock_event_grid_nodes": sum(
                s["movement"]["event_grid_nodes"] for s in equipment["storage"]
            ),
            "process_route_grid_nodes": 0,
        }
        fresh["equipment"] = equipment
        if (
            equipment["layouts"]["changing_room"].get("functional_geometry", {}).get("status")
            != "STATIC_GEOMETRY_READY"
        ):
            row.update(status="FUNCTIONAL_ROOM_REJECTED", equipment_failures=equipment["failures"])
            continue
        try:
            c = evaluate_process_rooms(
                fresh,
                passage_requirements,
                project,
                parameters,
                context,
                adaptive_endpoints=True,
                endpoint_rank=rank,
                revalidate_changing=True,
            )
        except (LayoutAuthorityError, ValueError) as error:
            row.update(
                status="PROCESS_BUILD_REJECTED",
                failure=str(error),
                details=getattr(error, "details", None),
            )
            enqueue_feedback(row, proposal, str(error), storage_rank, rank)
            continue
        admission = c["process_admission"]
        item_index = {q["id"]: q for q in c["equipment"]["items"]}
        row.update(
            status=admission["status"],
            failures=admission["failures"],
            main_lines=admission["main_line_count"],
            stock_counts={
                s["layout"]["room"]: s["layout"]["placed_positions"] for s in equipment["storage"]
            },
            selected_route_failures=[
                {
                    "id": r["id"],
                    "failure": r.get("failure", r["status"]),
                    "source": r["source_object"],
                    "target": r["target_object"],
                    "source_bbox_mm": item_index[r["source_object"]]["bbox_mm"],
                    "target_bbox_mm": item_index[r["target_object"]]["bbox_mm"],
                    "reserved_width_mm": r.get("main_reserved_width_mm"),
                    "turn_square_mm": r.get("turn_square_mm"),
                }
                for r in c["process_continuity"]["routes"]
                if r["id"] in admission["selected_route_ids"]
                and r.get("geometry_status") != "GEOMETRY_VERIFIED"
            ],
        )
        row["operation_counts"].update(
            process_route_grid_nodes=sum(
                s.get("nodes", 0) for r in c["process_continuity"]["routes"] for s in r["segments"]
            ),
        )
        if admission["accepted"]:
            c["schema_version"] = VERSION
            c["current_storage_requirements"] = requirements
            c["adaptive_metrics"] = _metrics(c)
            c["adaptive_origin"] = proposal["kind"]
            c["adaptive_search_node"] = row["node"]
            c["source_search_config_hash"] = config_hash
            c.pop("result_hash", None)
            c["result_hash"] = canonical_hash(c)
            signature = _space_signature(c)
            if signature not in signatures:
                accepted.append(c)
                signatures.add(signature)
            else:
                row["duplicate_physical_space_not_counted"] = True
            if len(accepted) >= limit:
                break
        else:
            enqueue_feedback(row, proposal, admission["failures"], storage_rank, rank)
    accepted.sort(
        key=lambda c: (
            c["adaptive_metrics"]["potential_route_crossings"],
            c["adaptive_metrics"]["selected_transport_reference_length_mm"],
            c["adaptive_metrics"]["selected_transport_turns"],
            Decimal(c["adaptive_metrics"]["gross_room_area_m2"]),
            c["result_hash"],
        )
    )
    result = {
        "task_id": "V2_2_2_AUTONOMOUS_ADAPTIVE_LAYOUT_REGENERATION_R1",
        "calculator_version": VERSION,
        "source_input_hash": canonical_hash(project),
        "source_process_parameter_hash": canonical_hash(parameters),
        "source_search_config_hash": config_hash,
        "search_configuration": dict(config),
        "p1_handoff_hash": context.binding.p1_handoff_hash,
        "zone_plan": context.plan,
        "current_storage_requirements": requirements,
        "candidates": accepted,
        "candidate_count": len(accepted),
        "status": "CONDITIONAL_ADAPTIVE_CANDIDATES"
        if accepted
        else "BOUNDED_ADAPTIVE_SEARCH_NO_CANDIDATE",
        "initial_status": prepared["status"],
        "initial_admission": initial_check,
        "attempts": attempts,
        "search_budget": {
            "candidate_node_budget": budget,
            "candidate_nodes_used": len(attempts),
            "full_evaluation_budget": full_budget,
            "full_evaluations_used": full_used,
            "completed_full_admissions": sum("main_lines" in a for a in attempts),
            "full_evaluation_scope": "Heavy pipeline attempts including early interface rejection",
            "remaining_queue": len(queue),
            "stop_reason": (
                "CANDIDATE_LIMIT_REACHED"
                if len(accepted) >= limit
                else "CANDIDATE_NODE_BUDGET_REACHED"
                if len(attempts) >= budget
                else "FULL_PIPELINE_BUDGET_REACHED"
                if full_used >= full_budget
                else "FINITE_PROPOSALS_EXHAUSTED"
            ),
            "initial_room_search_runs": prepared.get("attempts", []),
        },
        "ranking": "QUALIFIED_ONLY_LEXICOGRAPHIC_CROSSINGS_LENGTH_TURNS_AREA_NOT_FORMAL_PARETO",
        "operation_counts": {
            k: sum(a.get("operation_counts", {}).get(k, 0) for a in attempts)
            for k in ("stock_motion_attempts", "stock_event_grid_nodes", "process_route_grid_nodes")
        },
        "operation_scope": (
            "Selected stock witness counters and recorded per-route segment nodes only; "
            "shared cached paths can recur. These are not total host operations "
            "and not Stage A/B Work "
            "credits or a preissued solve budget. Initial preparation is recorded separately."
        ),
        "search_assumptions": {
            "source_type": "demo",
            "validity_status": "unverified",
            "requires_review": True,
            "column_edge_positioning_margins_mm": [100, 300, 600],
            "maximum_event_displacement_mm": 5000,
            "pallet_spacing_rotated_with_pallet": True,
            "physical_constraints_relaxed": False,
        },
        "source_layout_coordinates_loaded": False,
        "native_calls": 0,
        "MAIN": False,
        "grant_claim_accessed": False,
        "production_default_changed": False,
        "global_infeasibility_proven": False,
    }
    result["result_hash"] = canonical_hash(result)
    return result
