"""Independent bounded, non-Native room-root and process-feedback generation."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.access_routing import _zone_authority_checks
from cold_storage.modules.layout.application.autonomous_adaptive_layout import (
    _metrics,
    generate_adaptive_layout,
)
from cold_storage.modules.layout.application.autonomous_factory_layout import (
    AutonomousContext,
    _room_rows,
    bind_autonomous_input,
    structural_signature,
)
from cold_storage.modules.layout.application.autonomous_process_continuity import (
    evaluate_process_rooms,
    validate_process_parameters,
)
from cold_storage.modules.layout.domain import access_routing as routing
from cold_storage.modules.layout.domain.access_predicates import _evaluate_bound_requirement
from cold_storage.modules.layout.domain.adaptive_room_feedback import room_state_hash
from cold_storage.modules.layout.domain.adjacency import (
    RectangleObservationV1,
    evaluate_adjacency,
    process_graph,
)
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.autonomous_room_search import (
    search_room_arrangements,
)
from cold_storage.modules.layout.domain.constraint_guided_feedback import (
    passage_connection_feedback,
)
from cold_storage.modules.layout.domain.constraint_guided_installation import (
    joint_installation_candidates,
    precooling_installation_options,
    sorting_installation_options,
    storage_capacity_check,
)
from cold_storage.modules.layout.domain.current_process_requirements import (
    current_passage_requirements,
    current_storage_requirements,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.functional_changing_layout import changing_dimensions
from cold_storage.modules.layout.domain.functional_equipment_layout import (
    build_functional_equipment,
    coating_dimensions,
)
from cold_storage.modules.layout.domain.functional_portal_layout import joint_portals
from cold_storage.modules.layout.domain.functional_storage_layout import storage_layouts
from cold_storage.modules.layout.domain.multi_root_space import (
    candidate_distinction,
    organisation_key,
    physical_candidate_key,
    space_difference,
    uncovered_pockets,
)
from cold_storage.modules.layout.domain.process_endpoint_routes import room_rectangles
from cold_storage.modules.layout.domain.process_flow_arrangement import (
    arrange_process_workplaces,
    coating_service_depth,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

VERSION = "autonomous-multi-root-layout@1.4.1"

DEFAULT_SEARCH: Mapping[str, int] = MappingProxyType(
    {
        "root_search_limit": 64,
        "total_room_node_budget": 20000,
        "nodes_per_root_search": 400,
        "roots_per_search": 2,
        "full_pipeline_limit": 12,
        "accepted_limit": 2,
        "feedback_depth": 4,
        "feedback_children": 8,
    }
)

PORTAL_ORDER: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {"changing_room": ("S", "W"), "sorting_packaging_room": ("N",)}
)


def precheck_root_footprint(
    candidate: Mapping[str, Any],
    project: Mapping[str, Any],
    context: AutonomousContext,
    *,
    option_index: int = 0,
) -> dict[str, Any]:
    """Cheap necessary gate; an eventual survivor still reruns full admission."""
    rooms = room_rectangles(candidate)
    entrances: dict[str, Any] = {
        "main_entrance": tuple(tuple(p) for p in project["building"]["openings"][1]["segment_mm"]),
        "truck_entrance": tuple(tuple(p) for p in project["building"]["openings"][0]["segment_mm"]),
    }
    access, corridors, approaches = joint_portals(
        rooms,
        context.binding.access_requirements,
        context.binding.spatial_relationships,
        candidate["equipment"],
        context.boundary,
        context.columns + context.walls,
        entrances,
        portal_preferences=PORTAL_ORDER,
        option_index=option_index,
        candidate_pair_limit=8,
    )
    result: dict[str, Any] = {
        "portal_option_index": option_index,
        "failure_scope": "CURRENT_PORTAL_ORDER_ONLY_NOT_ALL_CONTINUOUS_PORTALS",
        "access_results": access,
        "portal_approaches": approaches,
        "full_admission_reuse": False,
        "passed": False,
    }
    required = {q["identity"]: q for q in context.binding.access_requirements}
    result["original_predicates"] = [
        {
            "requirement_identity": q["requirement_identity"],
            **_evaluate_bound_requirement(
                routing._requirement_object(required[q["requirement_identity"]]), q
            ),
        }
        for q in access
        if q["flow_kind"] != "TRUCK"
    ]
    try:
        fp = routing.derive_building_footprint(rooms, corridors)
        result["points_mm"] = [list(p) for p in fp]
        result["passed"] = all(q["status"] == "PASS" for q in result["original_predicates"])
    except LayoutAuthorityError as error:
        boxes = [list(q.bounds_mm) for q in rooms.values()]
        boxes += [list(b) for p in corridors if (b := routing._rectangle_bounds(p))]
        result.update(
            code=error.code,
            details=error.details,
            uncovered_pockets=uncovered_pockets(boxes),
        )
    return result


def prepare_root(
    rooms: Mapping[str, PlacedRectangleV1],
    project: Mapping[str, Any],
    context: AutonomousContext,
    *,
    storage_choice_rank: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Fresh room/equipment state, with no inherited path or acceptance flags."""
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
            for k, q in rooms.items()
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
            for q in rooms.values()
        ),
    )
    if not adjacency["geometry_passed"]:
        raise LayoutAuthorityError("MULTI_ROOT_ORIGINAL_ROOM_CONSTRAINT_REJECTED")
    eq = build_functional_equipment(
        rooms,
        project["equipment_specs"],
        context.plan,
        project["building"]["columns"],
        context.binding.access_requirements,
        adaptive_storage=True,
        storage_choice_rank=storage_choice_rank,
    )
    return {
        "schema_version": VERSION,
        "source_input_hash": canonical_hash(project),
        "source_zone_plan_hash": context.binding.canonical_zone_plan_hash,
        "source_p1_handoff_hash": context.binding.p1_handoff_hash,
        "source_building_hash": canonical_hash(project["building"]),
        "rooms": _room_rows(rooms, project, context),
        "original_building": project["building"],
        "room_non_overlap_and_MUST": adjacency,
        "equipment": eq,
        "access_results": [],
        "metrics": {},
        "dimension_and_area_authorities_unchanged": True,
        "structural_signature": structural_signature(rooms),
        "native_calls": 0,
        "truck_route_validated": False,
        "P2D_full_pass": False,
        "engineering_approval": "NOT_EVALUATED",
        "factory_applicability": "NOT_EVALUATED",
    }


def room_roots(
    project: Mapping[str, Any],
    parameters: Mapping[str, Any],
    context: AutonomousContext,
    *,
    profile: str,
    preferences: Mapping[str, str],
    limit: int = 2,
    node_budget: int = 1000,
    anchor: tuple[int, int, int] | None = None,
    root_index: int | None = None,
    rotation: int | None = None,
    constraint_guided: bool = False,
    partial_cache: dict[str, dict[str, Any]] | None = None,
    attachment_offsets: Mapping[str, list[tuple[int, int]]] | None = None,
    shape_variant: int = 0,
    room_targets: Mapping[str, list[tuple[int, int]]] | None = None,
) -> tuple[list[dict[str, PlacedRectangleV1]], dict[str, Any]]:
    g = changing_dimensions()
    cw, _ = coating_dimensions(project["equipment_specs"]["case_film_line"])
    shapes = {
        "changing_room": [(g["width_mm"], g["depth_mm"])],
        "coating_room": [(cw, coating_service_depth(parameters)["depth_mm"])],
    }
    if constraint_guided:
        depth = shapes["coating_room"][0][1]
        # Original device chain plus reserved full-width service sections.
        # These are finite preferences inside the existing flexible Authority.
        alternatives = [
            (cw + dw, depth + dh)
            for dw, dh in ((0, 0), (0, 1000), (0, 2000), (1000, 0), (2000, 0), (1000, 1000))
        ]
        shapes["coating_room"] = [alternatives[shape_variant % len(alternatives)]]
    zones = {q["zone_code"]: q for q in context.plan["result"]["zones"]}
    cache = partial_cache if partial_cache is not None else {}
    binding_key = canonical_hash(
        [canonical_hash(project), canonical_hash(parameters), context.binding.p1_handoff_hash]
    )

    def partial(state: Mapping[str, PlacedRectangleV1], role: str) -> Mapping[str, Any]:
        rect = state[role]
        key = canonical_hash(
            [
                binding_key,
                role,
                rect.bounds_mm,
                rect.rotation_deg,
            ]
        )
        if key not in cache:
            if role in current_storage_requirements(context.plan):
                cache[key] = storage_capacity_check(
                    rect,
                    zones[role],
                    project["building"]["columns"],
                    erector=project["equipment_specs"]["case_erector"]
                    if role == "packaging_material_storage"
                    else None,
                )
            elif role == "sorting_packaging_room":
                opts, record = sorting_installation_options(
                    rect,
                    project["equipment_specs"],
                    parameters,
                    project["building"]["columns"],
                    limit=1,
                )
                cache[key] = {
                    "admissible": bool(opts),
                    "status": record["status"],
                    "room_bbox_mm": list(rect.bounds_mm),
                    "installation": record,
                    "global_infeasibility_proven": False,
                }
            elif role in ("primary_precooling_room", "secondary_precooling_room"):
                opts, record = precooling_installation_options(
                    rect, project["building"]["columns"], limit=1
                )
                cache[key] = {
                    "admissible": bool(opts),
                    "status": record["status"],
                    "room_bbox_mm": list(rect.bounds_mm),
                    "installation": record,
                    "global_infeasibility_proven": False,
                }
            else:
                cache[key] = {"admissible": True, "status": "NO_PARTIAL_REJECTION"}
            cache[key]["check_id"] = key
        return cache[key]

    ent = project["building"]["openings"][1]["segment_mm"]
    return search_room_arrangements(
        context.binding.dimension_authorities,
        context.boundary,
        context.walls,
        profile=profile,
        node_budget=node_budget,
        complete_limit=limit,
        internal_columns=context.columns,
        personnel_entry=((ent[0][0] + ent[1][0]) // 2, ent[0][1]),
        functional_shapes=shapes,
        functional_alignment=True,
        functional_open_chain=True,
        diverse_cores=True,
        side_preferences=preferences,
        event_root_anchors=True,
        root_anchor_mm=anchor,
        root_index=root_index if anchor is None else None,
        root_rotation_deg=rotation,
        partial_feasibility=partial if constraint_guided else None,
        attachment_offsets=attachment_offsets,
        room_targets=room_targets,
    )


def collision_root_feedback(
    seed: Mapping[str, Any], arranged: Mapping[str, Any], *, max_proposals: int = 6
) -> list[dict[str, Any]]:
    """Actual obstacle/operation intersections -> a new initial attachment search.

    Nothing is accepted here and no old layout is translated into a witness.
    The proposed sorting anchor starts a fresh twelve-room search.
    """
    c = arranged["candidate"]
    eq = c["equipment"]
    objects = {
        q["id"]: q
        for q in [
            *eq["items"],
            *eq.get("process_operator_zones", []),
            *c["original_building"]["columns"],
        ]
    }
    aisles = {
        (code, q["id"]): q
        for code, layout in eq["layouts"].items()
        for q in layout["service_corridors"]
    }
    origin = next(q for q in seed["rooms"] if q["zone_code"] == "sorting_packaging_room")
    found: dict[tuple[int, ...], dict[str, Any]] = {}
    failures = sorted(
        arranged["static_conflicts"],
        key=lambda q: (
            q.get("room") != "secondary_precooling_room",
            q.get("code", ""),
            q.get("id", q.get("aisle", "")),
        ),
    )
    axes = c["original_building"]["coordinate_mapping"]["axis_x_mm"]
    max_move = max(b - a for a, b in zip(axes, axes[1:], strict=False))
    for failure in failures:
        moving = (
            aisles.get((failure.get("room"), failure.get("aisle")))
            if failure["code"] == "RESERVED_AISLE_OCCUPIED"
            else objects.get(failure.get("id"))
        )
        obstacle = objects.get(failure.get("other"))
        if moving is None or obstacle is None:
            continue
        a, b = moving["bbox_mm"], obstacle["bbox_mm"]
        for axis in (1, 0):
            for delta in (b[axis] - a[axis + 2] - 100, b[axis + 2] - a[axis] + 100):
                if not 0 < abs(delta) <= max_move:
                    continue
                anchor = [origin["x_mm"], origin["y_mm"], origin["rotation_deg"]]
                anchor[axis] += delta
                key = tuple(anchor)
                found.setdefault(
                    key,
                    {
                        "root_anchor_mm": anchor,
                        "trigger": dict(failure),
                        "moving_bbox_mm": a,
                        "obstacle_bbox_mm": b,
                        "separation_margin_mm": 100,
                        "source_type": "demo",
                        "validity_status": "unverified",
                        "requires_review": True,
                    },
                )
                if len(found) >= max_proposals:
                    return list(found.values())
    return list(found.values())


def storage_interface_feedback(
    seed: Mapping[str, Any], project: Mapping[str, Any], context: AutonomousContext
) -> list[dict[str, Any]]:
    """Blocked alternative full-width stock aisles feed the room anchor search."""
    rooms = room_rectangles(seed)
    zone = next(
        q for q in context.plan["result"]["zones"] if q["zone_code"] == "finished_goods_room"
    )
    layouts = storage_layouts(
        rooms["finished_goods_room"],
        zone,
        project["building"]["columns"],
        allow_pallet_rotation=True,
    )
    selected = next(
        q["layout"]
        for q in seed["equipment"]["storage"]
        if q["layout"]["room"] == "finished_goods_room"
    )
    alternatives = []
    turns = set()
    columns = {q["id"]: q for q in project["building"]["columns"]}
    for layout in layouts:
        turn = layout["turn"]
        if turn == selected["turn"] or turn in turns:
            continue
        turns.add(turn)
        for other in layout["main_aisle_column_conflicts"]:
            if other not in columns:
                continue
            arranged = {
                "candidate": seed,
                "static_conflicts": [
                    {
                        "code": "RESERVED_AISLE_OCCUPIED",
                        "room": "finished_goods_room",
                        "aisle": "STORAGE-MAIN",
                        "other": other,
                    }
                ],
            }
            # Supply the examined alternative aisle solely to derive feedback.
            diagnostic = copy.deepcopy(seed)
            diagnostic["equipment"]["layouts"]["finished_goods_room"]["service_corridors"] = [
                {"id": "STORAGE-MAIN", "bbox_mm": layout["main_aisle_bbox_mm"]}
            ]
            arranged["candidate"] = diagnostic
            for f in collision_root_feedback(seed, arranged, max_proposals=4):
                alternatives.append(
                    {
                        **f,
                        "constraint": "FAILED_STOCK_PORTAL_REQUIRES_ALTERNATE_FULL_WIDTH_AISLE",
                        "examined_layout": layout["id"],
                        "placed_positions": layout["placed_positions"],
                        "required_positions": layout["required_grid_capacity"],
                    }
                )
    return alternatives


def partial_constraint_feedback(
    stats: Mapping[str, Any], preferences: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Move the actual failed room/aisle at real obstruction events, not an unrelated root."""
    result = []
    seen = set()
    for failure in stats.get("partial_constraint_rejections", []):
        code = failure["room"]
        if code in seen:
            continue
        seen.add(code)
        r = failure["room_bbox_mm"]
        if "best_layout" in failure:
            a = failure["best_layout"]["main_aisle_bbox_mm"]
            blockers = failure.get("columns", [])
        else:
            trial: dict[str, Any] = next(
                (
                    q
                    for q in failure.get("installation", {}).get("trials", [])
                    if q["body_failures"]
                ),
                {},
            )
            f: dict[str, Any] = next(
                (q for q in trial.get("body_failures", []) if "obstacle_bbox_mm" in q), {}
            )
            a = f.get("bbox_mm", r)
            blockers = [{"bbox_mm": f["obstacle_bbox_mm"]}] if "obstacle_bbox_mm" in f else []
        for obstacle in blockers[:3]:
            b = obstacle["bbox_mm"]
            if not positive_intersection(a, b):
                continue
            for axis in (0, 1):
                for delta in (b[axis] - a[axis + 2] - 50, b[axis + 2] - a[axis] + 50):
                    p = r[:2].copy()
                    p[axis] += delta
                    result.append(
                        {
                            "room_targets": {code: [p]},
                            "constraint": "PARTIAL_ROOM_OBSTACLE_EVENT",
                            "failed_room": code,
                            "room_bbox_mm": r,
                            "necessary_width_mm": failure.get("main_aisle_mm"),
                            "moving_bbox_mm": a,
                            "obstacle_bbox_mm": b,
                            "global_infeasibility_proven": False,
                        }
                    )
        result.extend(
            {
                "preferences": {**preferences, code: side},
                "constraint": "PARTIAL_CAPACITY_OR_INSTALLATION_ATTACHMENT",
                "failed_room": code,
                "room_bbox_mm": r,
            }
            for side in ("N", "S", "E", "W")
        )
    return result


def generate_multi_root_layout(
    project: Mapping[str, Any],
    parameters: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    validate_process_parameters(parameters)
    required = set(DEFAULT_SEARCH)
    if set(config) != required or any(type(config[k]) is not int for k in required):
        raise LayoutAuthorityError("MULTI_ROOT_CONFIGURATION_INVALID")
    limits = {
        "root_search_limit": (3, 64),
        "total_room_node_budget": (100, 60000),
        "nodes_per_root_search": (12, 2000),
        "roots_per_search": (1, 4),
        "full_pipeline_limit": (4, 24),
        "accepted_limit": (2, 6),
        "feedback_depth": (1, 6),
        "feedback_children": (1, 12),
    }
    if any(not lo <= config[k] <= hi for k, (lo, hi) in limits.items()):
        raise LayoutAuthorityError("MULTI_ROOT_CONFIGURATION_OUT_OF_BOUNDS")
    context = bind_autonomous_input(project)
    requirements = current_storage_requirements(context.plan)
    # Re-execute the V1.3 reference at this input, never read an archived PASS.
    reference = generate_adaptive_layout(
        project,
        parameters,
        {
            "candidate_node_budget": 12,
            "full_evaluation_budget": min(12, config["full_pipeline_limit"]),
            "candidate_limit": 1,
        },
        progress=progress,
    )
    initial_runs = reference["search_budget"]["initial_room_search_runs"]
    search_calls = len(initial_runs)
    room_nodes = sum(r.get("search", {}).get("nodes_used", 0) for r in initial_runs)
    full_used = reference["search_budget"]["full_evaluations_used"]
    accepted = []
    if reference["candidates"]:
        c = copy.deepcopy(reference["candidates"][0])
        c["multi_root_origin"] = {
            "root_id": "REFERENCE_CURRENT_INPUT_RERUN",
            "kind": "V13_RECOMPUTED_REFERENCE",
        }
        accepted.append(c)
    reference_c = accepted[0] if accepted else None
    seen_candidates = {physical_candidate_key(c) for c in accepted}
    full_failure_families: set[str] = set()
    partial_cache: dict[str, dict[str, Any]] = {}
    same_organisation_variants: list[dict[str, Any]] = []
    seen_organisations = {organisation_key(c) for c in accepted}
    seen_rooms: set[str] = set()
    root_rows: list[dict[str, Any]] = []
    search_rows: list[dict[str, Any]] = []
    descriptors_seen = set()
    serial = 0
    # Each descriptor performs a real search, not a relabelled existing layout.
    profiles = ("LINEAR_BANDED", "CENTRAL_PROCESS_CORE", "PROCESS_SPINE_WITH_PERIPHERAL_BANKS")
    pending: list[dict[str, Any]] = []
    rotations = context.binding.dimension_authorities["sorting_packaging_room"]["rotation_allowed"]
    for profile in profiles:
        choices = [(0, None), (1, None), *[(0, r) for r in rotations if r != 0]]
        for index, rotation in choices:
            pending.append(
                {
                    "profile": profile,
                    "preferences": {},
                    "depth": 0,
                    "priority": -1,
                    "serial": len(pending),
                    "root_index": index,
                    "rotation": rotation,
                    "shape_variant": 0,
                }
            )
    serial = len(pending)
    profile_uses = dict.fromkeys((d["profile"] for d in pending), 0)
    passage = current_passage_requirements(
        context.binding.access_requirements, list(context.binding.dimension_authorities)
    )

    def enqueue(
        desc: dict[str, Any], row: dict[str, Any], score: int, causes: list[dict[str, Any]]
    ) -> None:
        nonlocal serial
        if desc["depth"] >= config["feedback_depth"]:
            return
        children = []
        for cause in causes[: config["feedback_children"]]:
            child = {
                "profile": desc["profile"],
                "preferences": cause.get("preferences", desc["preferences"]),
                "anchor": cause.get("root_anchor_mm", desc.get("anchor")),
                "root_index": desc.get("root_index"),
                "rotation": desc.get("rotation"),
                "depth": desc["depth"] + 1,
                "priority": score,
                "serial": serial,
                "parent_root": row["root_id"],
                "trigger": cause,
                "attachment_offsets": cause.get(
                    "attachment_offsets", desc.get("attachment_offsets")
                ),
                "shape_variant": cause.get("shape_variant", desc.get("shape_variant", 0)),
                "room_targets": {
                    **(desc.get("room_targets") or {}),
                    **cause.get("room_targets", {}),
                },
                "storage_choice_rank": cause.get(
                    "storage_choice_rank", desc.get("storage_choice_rank")
                ),
                "focus_role": cause.get(
                    "focus_role", cause.get("failed_room", desc.get("focus_role"))
                ),
                "focus_rank": cause.get("focus_rank", 1),
            }
            serial += 1
            pending.append(child)
            children.append(serial - 1)
        row["feedback_descriptors_enqueued"] = children

    while (
        pending
        and search_calls < config["root_search_limit"]
        and room_nodes < config["total_room_node_budget"]
        and full_used < config["full_pipeline_limit"]
    ):
        # A low-score failure family cannot consume every root allocation.
        pending.sort(key=lambda d: (profile_uses[d["profile"]], d["priority"], d["serial"]))
        desc = pending.pop(0)
        dkey = canonical_hash(
            {
                k: desc.get(k)
                for k in (
                    "profile",
                    "preferences",
                    "anchor",
                    "root_index",
                    "rotation",
                    "attachment_offsets",
                    "shape_variant",
                    "room_targets",
                    "storage_choice_rank",
                    "focus_role",
                    "focus_rank",
                )
            }
        )
        if dkey in descriptors_seen:
            continue
        descriptors_seen.add(dkey)
        profile_uses[desc["profile"]] += 1
        remaining = config["total_room_node_budget"] - room_nodes
        budget = min(config["nodes_per_root_search"], remaining)
        groups, stats = room_roots(
            project,
            parameters,
            context,
            profile=desc["profile"],
            preferences=desc["preferences"],
            limit=config["roots_per_search"],
            node_budget=budget,
            anchor=tuple(desc["anchor"]) if desc.get("anchor") else None,
            root_index=desc.get("root_index"),
            rotation=desc.get("rotation"),
            constraint_guided=True,
            partial_cache=partial_cache,
            attachment_offsets=desc.get("attachment_offsets"),
            shape_variant=desc.get("shape_variant", 0),
            room_targets=desc.get("room_targets"),
        )
        search_calls += 1
        room_nodes += stats["nodes_used"]
        search_rows.append(
            {
                "search_number": search_calls,
                "descriptor": desc,
                "stats": stats,
                "generated_roots": len(groups),
            }
        )
        if progress:
            progress(
                f"MULTI_ROOT_SEARCH {search_calls} {desc['profile']} "
                f"roots={len(groups)} nodes={stats['nodes_used']}"
            )
        if not groups:
            search_rows[-1]["root_id"] = f"PARTIAL-SEARCH-{search_calls}"
            partial_causes = partial_constraint_feedback(stats, desc["preferences"])
            enqueue(desc, search_rows[-1], 2000 + 100 * (12 - stats["max_roles"]), partial_causes)
        for state in groups:
            geometry_hash = room_state_hash(state)
            room_option_key = canonical_hash(
                [
                    geometry_hash,
                    desc.get("storage_choice_rank"),
                    desc.get("focus_role"),
                    desc.get("focus_rank"),
                ]
            )
            if room_option_key in seen_rooms:
                search_rows[-1].setdefault("duplicate_room_geometries", []).append(geometry_hash)
                continue
            seen_rooms.add(room_option_key)
            row: dict[str, Any] = {
                "root_id": f"ROOT-{len(root_rows) + 1:03}",
                "search_number": search_calls,
                "source_input_hash": canonical_hash(project),
                "room_geometry_hash": geometry_hash,
                "origin": desc,
                "room_coordinates": [
                    {
                        "zone_code": k,
                        "bbox_mm": list(q.bounds_mm),
                        "width_m": str(q.width_m),
                        "depth_m": str(q.depth_m),
                        "rotation_deg": q.rotation_deg,
                    }
                    for k, q in sorted(state.items())
                ],
            }
            root_rows.append(row)
            row["operation_counts"] = dict.fromkeys(
                (
                    "stock_layout_trials",
                    "selected_stock_motion_attempts",
                    "selected_stock_event_grid_nodes",
                    "process_route_grid_nodes",
                    "necessary_portal_prechecks",
                ),
                0,
            )
            try:
                seed = prepare_root(
                    state, project, context, storage_choice_rank=desc.get("storage_choice_rank")
                )
            except LayoutAuthorityError as error:
                row.update(
                    status="ORIGINAL_ROOM_AUTHORITY_REJECTED",
                    code=error.code,
                    details=error.details,
                )
                continue
            row["equipment_coordinates"] = [
                {k: q.get(k) for k in ("id", "room", "kind", "bbox_mm", "rotation_deg")}
                for q in seed["equipment"]["items"]
            ]
            stock = [
                {
                    "room": s["layout"]["room"],
                    "placed": s["layout"]["placed_positions"],
                    "required": requirements[s["layout"]["room"]]["required_positions"],
                    "pick_put": s["movement"]["conditional_pick_put_geometry_pass"],
                    "layout": s["layout"]["id"],
                }
                for s in seed["equipment"]["storage"]
            ]
            row["storage"] = stock
            row["storage_trials"] = seed["equipment"]["storage_trials"]
            row["operation_counts"] = {
                "stock_layout_trials": len(seed["equipment"]["storage_trials"]),
                "selected_stock_motion_attempts": sum(
                    s["movement"]["motion_attempts"] for s in seed["equipment"]["storage"]
                ),
                "selected_stock_event_grid_nodes": sum(
                    s["movement"]["event_grid_nodes"] for s in seed["equipment"]["storage"]
                ),
                "process_route_grid_nodes": 0,
                "necessary_portal_prechecks": 0,
            }
            local_options, installation = joint_installation_candidates(
                seed,
                parameters,
                project["equipment_specs"],
                limit=4,
                focus_role=desc.get("focus_role"),
                focus_rank=desc.get("focus_rank", 1),
            )
            row["local_installation_search"] = installation
            arranged = (
                local_options[0] if local_options else arrange_process_workplaces(seed, parameters)
            )
            c = arranged["candidate"]
            objects = {
                q["id"]: q
                for q in [
                    *c["equipment"]["items"],
                    *c["equipment"].get("process_operator_zones", []),
                    *project["building"]["columns"],
                ]
            }
            aisles = {
                (r, q["id"]): q
                for r, layout in c["equipment"]["layouts"].items()
                for q in layout["service_corridors"]
            }
            conflicts = []
            for f in arranged["static_conflicts"]:
                moving = (
                    aisles.get((f.get("room"), f.get("aisle")))
                    if f["code"] == "RESERVED_AISLE_OCCUPIED"
                    else objects.get(f.get("id"))
                )
                other = objects.get(f.get("other"))
                conflicts.append(
                    {
                        **f,
                        "moving_bbox_mm": moving["bbox_mm"] if moving else None,
                        "obstacle_bbox_mm": other["bbox_mm"] if other else None,
                    }
                )
            bad = [
                f
                for f in conflicts
                if not (f.get("room") == "coating_room" and f["code"] == "RESERVED_AISLE_OCCUPIED")
            ]
            deficit = sum(max(s["required"] - s["placed"], 0) for s in stock)
            row["static_conflicts"] = conflicts
            row["capacity_deficit"] = deficit
            causes = collision_root_feedback(
                seed, arranged, max_proposals=config["feedback_children"]
            )
            if installation["status"] == "BOUNDED_LOCAL_INSTALLATION_REJECTED":
                failed_roles = [
                    role
                    for role, q in installation["rooms"].items()
                    if q["status"] == "BOUNDED_INSTALLATION_NOT_FOUND"
                ]
                causes = [
                    {
                        "preferences": {**desc["preferences"], role: side},
                        "failed_room": role,
                        "constraint": "LOCAL_INSTALLATION_EXHAUSTED_ROOM_REATTACHMENT",
                        "local_evidence": installation["rooms"][role],
                    }
                    for role in failed_roles
                    for side in ("N", "S", "E", "W")
                ] + causes
            causes += [
                {
                    "shape_variant": i,
                    "constraint": "FLEXIBLE_FUNCTIONAL_SECTION_ALTERNATIVE",
                    "room": "coating_room",
                }
                for i in range(1, 6)
                if i != desc.get("shape_variant", 0)
            ]
            score = deficit + len(bad)
            precheck: dict[str, Any] = {}
            if not deficit and not bad and all(s["pick_put"] for s in stock):
                portal_trials = []
                for local in (local_options or [arranged])[:2]:
                    for portal_index in range(2):
                        trial = precheck_root_footprint(
                            local["candidate"], project, context, option_index=portal_index
                        )
                        portal_trials.append(trial)
                        row["operation_counts"]["necessary_portal_prechecks"] += 1
                        if trial["passed"]:
                            arranged, c, precheck = local, local["candidate"], trial
                            break
                    if precheck.get("passed"):
                        break
                if not precheck:
                    precheck = portal_trials[0]
                row["portal_option_trials"] = portal_trials
                row["current_necessary_portal_footprint_check"] = precheck
            row["equipment_coordinates"] = [
                {k: q.get(k) for k in ("id", "room", "kind", "bbox_mm", "rotation_deg")}
                for q in c["equipment"]["items"]
            ]
            row["selected_local_installation"] = arranged.get("local_option_selection")
            family = organisation_key(seed)
            diagnose_failed_gate = False  # Failed necessary checks feed spatial search directly.
            if precheck and not precheck["passed"]:
                if precheck.get("uncovered_pockets"):
                    involved = sorted(
                        {
                            r["zone_code"]
                            for r in seed["rooms"]
                            if any(
                                positive_intersection(
                                    r["bbox_mm"],
                                    [
                                        p["bbox_mm"][0] - 1,
                                        p["bbox_mm"][1] - 1,
                                        p["bbox_mm"][2] + 1,
                                        p["bbox_mm"][3] + 1,
                                    ],
                                )
                                for p in precheck["uncovered_pockets"]
                            )
                        }
                    )
                    causes = [
                        {
                            "preferences": {**desc["preferences"], role: side},
                            "constraint": "ENCLOSED_EMPTY_POCKET_IN_ORIGINAL_ROOM_CORRIDOR_UNION",
                            "pockets": precheck["uncovered_pockets"],
                        }
                        for role in involved
                        for side in ("S", "N", "E", "W")
                    ]
                else:
                    causes = storage_interface_feedback(seed, project, context) + causes
                causes = (
                    passage_connection_feedback(c, precheck, context.binding.access_requirements)
                    + causes
                )
            if deficit or any(not s["pick_put"] for s in stock):
                row["status"] = "CURRENT_P1_STORAGE_REJECTED"
                room = next(
                    s["room"] for s in stock if s["placed"] < s["required"] or not s["pick_put"]
                )
                capacity_causes = [
                    {
                        "preferences": {**desc["preferences"], room: side},
                        "constraint": "CURRENT_P1_GRID_AND_PICK_PUT",
                        "failed_room": room,
                        "stock": stock,
                    }
                    for side in ("E", "N", "W", "S")
                ]
                causes = causes + capacity_causes if bad else capacity_causes + causes
                score = 2000 + deficit
            elif bad:
                row["status"] = "EQUIPMENT_OR_RESERVED_PASSAGE_REJECTED"
                score = 1000 + len(bad)
            elif not precheck.get("passed") and not diagnose_failed_gate:
                row["status"] = "ORIGINAL_PORTAL_OR_ZERO_HOLE_PRECHECK_REJECTED"
                score = (
                    100
                    + sum(q["status"] != "PASS" for q in precheck.get("original_predicates", []))
                    + 10 * bool(precheck.get("uncovered_pockets"))
                )
            elif (
                c["equipment"]["layouts"]["changing_room"]
                .get("functional_geometry", {})
                .get("status")
                != "STATIC_GEOMETRY_READY"
            ):
                row["status"] = "SUPPORTED_CHANGING_GEOMETRY_NOT_GENERATED"
            elif full_used >= config["full_pipeline_limit"]:
                row["status"] = "NOT_EVALUATED_FULL_PIPELINE_BUDGET_EXHAUSTED"
            else:
                full_used += 1
                if diagnose_failed_gate:
                    full_failure_families.add(family)
                    row["full_validation_after_failed_necessary_check"] = True
                try:
                    c = evaluate_process_rooms(
                        seed,
                        passage,
                        project,
                        parameters,
                        context,
                        adaptive_endpoints=True,
                        revalidate_changing=True,
                        multi_root_interfaces=True,
                        portal_preferences=PORTAL_ORDER,
                        local_installation=arranged,
                        portal_option_index=precheck.get("portal_option_index", 0),
                    )
                    row["process_admission"] = c["process_admission"]
                    if not c["process_admission"]["accepted"]:
                        row["rejected_full_witness"] = c
                    row["operation_counts"]["process_route_grid_nodes"] += sum(
                        s.get("nodes", 0)
                        for r in c["process_continuity"]["routes"]
                        for s in r["segments"]
                    )
                    row["footprint"] = c["building_footprint"]
                    row["changing_entry_exit"] = c["changing_function"].get("entry_exit")
                    chosen = set(c["process_admission"]["selected_route_ids"])
                    row["failed_route_witnesses"] = [
                        r
                        for r in c["process_continuity"]["routes"]
                        if r["id"] in chosen and r.get("geometry_status") != "GEOMETRY_VERIFIED"
                    ]
                    row["status"] = c["process_admission"]["status"]
                    if c["process_admission"]["accepted"]:
                        c["multi_root_origin"] = {
                            "root_id": row["root_id"],
                            "kind": "FULL_CURRENT_ROOT_RECOMPUTED",
                            "descriptor": desc,
                        }
                        c["adaptive_metrics"] = _metrics(c)
                        c["adaptive_origin"] = desc["profile"]
                        c["adaptive_search_node"] = len(root_rows)
                        c["current_storage_requirements"] = requirements
                        key = physical_candidate_key(c)
                        classification = (
                            candidate_distinction(reference_c, c)
                            if reference_c
                            else {"new_qualified_organisation": True}
                        )
                        row["candidate_classification"] = c["candidate_classification"] = (
                            classification
                        )
                        if not classification["new_qualified_organisation"]:
                            row["qualified_but_not_materially_distinct_not_selected"] = True
                            if key not in seen_candidates:
                                same_organisation_variants.append(c)
                                seen_candidates.add(key)
                        elif key not in seen_candidates:
                            if organisation_key(c) not in seen_organisations:
                                accepted.append(c)
                                seen_candidates.add(key)
                                seen_organisations.add(organisation_key(c))
                        else:
                            row["duplicate_physical_candidate_not_counted"] = True
                    else:
                        failed_storage = [
                            role
                            for role in requirements
                            if any(
                                role in str(r.get("source_object", ""))
                                or role in str(r.get("target_object", ""))
                                for r in row.get("failed_route_witnesses", [])
                            )
                        ]
                        if any(
                            "FINISHED" in f.get("id", "")
                            for f in c["process_admission"]["failures"]
                        ):
                            failed_storage.append("finished_goods_room")
                        stock_causes = [
                            {
                                "storage_choice_rank": {
                                    **(desc.get("storage_choice_rank") or {}),
                                    role: rank,
                                },
                                "constraint": "CURRENT_FAILED_STORAGE_INTERFACE_ALTERNATIVE_GRID",
                                "failed_room": role,
                                "trigger": c["process_admission"]["failures"],
                            }
                            for role in sorted(set(failed_storage))
                            for rank in (1, 3, 7)
                            if rank != (desc.get("storage_choice_rank") or {}).get(role, 0)
                        ]
                        causes = (
                            stock_causes
                            + storage_interface_feedback(seed, project, context)
                            + causes
                        )
                        causes.extend(
                            {
                                "preferences": {**desc["preferences"], "changing_room": side},
                                "constraint": "CURRENT_PORTAL_AND_ZERO_HOLE_RECOMPUTATION",
                                "full_failures": c["process_admission"]["failures"],
                            }
                            for side in ("N", "E")
                        )
                        score = len(c["process_admission"]["failures"])
                except (LayoutAuthorityError, ValueError) as error:
                    row.update(
                        status="CURRENT_PROCESS_INTERFACE_REJECTED",
                        error=str(error),
                        details=getattr(error, "details", {}),
                    )
                    details = getattr(error, "details", {})
                    role = details.get("room")
                    if role in requirements:
                        causes = [
                            {
                                "storage_choice_rank": {
                                    **(desc.get("storage_choice_rank") or {}),
                                    role: rank,
                                },
                                "failed_room": role,
                                "constraint": "ACTUAL_FAILED_LOAD_DOCK_REGRID",
                                "failure_object": details,
                            }
                            for rank in (1, 3, 7)
                            if rank != (desc.get("storage_choice_rank") or {}).get(role, 0)
                        ] + causes
                    elif role in state:
                        causes = [
                            {
                                "focus_role": role,
                                "focus_rank": rank,
                                "failed_room": role,
                                "constraint": "ACTUAL_FAILED_DEVICE_DOCK_LOCAL_OPTION",
                                "failure_object": details,
                            }
                            for rank in (1, 2, 3)
                            if rank != desc.get("focus_rank", 0)
                        ] + causes
                    score += 1
            enqueue(desc, row, score, causes)
            if progress:
                progress(f"{row['root_id']} {row['status']} stock_deficit={deficit}")
        families = {organisation_key(c) for c in accepted}
        if len(accepted) >= config["accepted_limit"] and len(families) > 1:
            break
    for c in [*accepted, *same_organisation_variants]:
        c["organisation_key"] = organisation_key(c)
        c["difference_from_current_reference"] = (
            space_difference(reference_c, c) if reference_c else None
        )
        c["schema_version"] = VERSION
        c.pop("result_hash", None)
        c["result_hash"] = canonical_hash(c)
    # Keep the recomputed reference. Select other families before within-family variants.
    others = sorted(
        accepted[1:] if reference_c else accepted,
        key=lambda c: (
            c["adaptive_metrics"]["potential_route_crossings"],
            c["adaptive_metrics"]["selected_transport_reference_length_mm"],
            c["adaptive_metrics"]["selected_transport_turns"],
            Decimal(c["adaptive_metrics"]["footprint_area_m2"]),
            c["result_hash"],
        ),
    )
    selected = [accepted[0]] if reference_c else []
    keys = {organisation_key(c) for c in selected}
    for c in [*others, *others]:
        if len(selected) >= config["accepted_limit"]:
            break
        if c in selected:
            continue
        if organisation_key(c) in keys and len(keys) < len({organisation_key(q) for q in accepted}):
            continue
        selected.append(c)
        keys.add(organisation_key(c))
    result = {
        "task_id": "V2_2_2_AUTONOMOUS_MULTI_ROOT_FACTORY_SEARCH_R1",
        "calculator_version": VERSION,
        "source_input_hash": canonical_hash(project),
        "source_process_parameter_hash": canonical_hash(parameters),
        "source_search_config_hash": canonical_hash(config),
        "search_configuration": dict(config),
        "current_storage_requirements": requirements,
        "zone_plan": context.plan,
        "p1_handoff_hash": context.binding.p1_handoff_hash,
        "candidates": selected,
        "candidate_count": len(selected),
        "organisation_count": len({organisation_key(c) for c in selected}),
        "new_qualified_organisation_count": sum(
            c.get("candidate_classification", {}).get("new_qualified_organisation", False)
            for c in selected
        ),
        "qualified_variant_count": len(same_organisation_variants),
        "qualified_same_organisation_variant_count": sum(
            not c["candidate_classification"]["core_organisation_different"]
            for c in same_organisation_variants
        ),
        "qualified_non_novel_variants": same_organisation_variants,
        "status": "CONDITIONAL_MULTI_ROOT_ORGANISATIONS"
        if len({organisation_key(c) for c in selected}) > 1
        else "NO_NEW_ORGANISATION_WITHIN_BOUNDED_SEARCH",
        "reference_execution": {
            k: v for k, v in reference.items() if k not in ("candidates", "zone_plan")
        },
        "root_searches": search_rows,
        "roots": root_rows,
        "search_budget": {
            "root_search_calls_used": search_calls,
            "room_nodes_used": room_nodes,
            "full_pipeline_attempts_used": full_used,
            "failed_necessary_gate_full_diagnostics": len(full_failure_families),
            "remaining_descriptors": len(pending),
            "profile_search_allocations": profile_uses,
            "limits": dict(config),
            "stop_reason": (
                "QUALIFIED_DIVERSE_CANDIDATE_LIMIT"
                if len(selected) >= config["accepted_limit"] and len(keys) > 1
                else "ROOT_SEARCH_LIMIT"
                if search_calls >= config["root_search_limit"]
                else "ROOM_DFS_NODE_BUDGET"
                if room_nodes >= config["total_room_node_budget"]
                else "FULL_PIPELINE_LIMIT"
                if full_used >= config["full_pipeline_limit"]
                else "FINITE_FEEDBACK_EXHAUSTED"
            ),
        },
        "operation_counts": {
            k: sum(row["operation_counts"][k] for row in root_rows)
            for k in (
                "stock_layout_trials",
                "selected_stock_motion_attempts",
                "selected_stock_event_grid_nodes",
                "process_route_grid_nodes",
                "necessary_portal_prechecks",
            )
        },
        "partial_capacity_installation_cache_entries": len(partial_cache),
        "local_search_limits": {
            "installation_trials_per_room": 48,
            "installation_options_per_room": 4,
            "precheck_installations_per_root": 2,
            "precheck_portal_orders_per_installation": 2,
            "portal_route_pairs_per_requirement": 8,
            "portal_route_nodes_per_pair": 400,
            "failed_precheck_full_diagnostics": 0,
            "feedback_target_span_mm": 16000,
            "scope": "FINITE_SEARCH_CHOICES_NOT_ENGINEERING_HARD_THRESHOLDS",
        },
        "partial_constraint_evidence": partial_cache,
        "partial_constraint_check_counts": {
            k: sum(s["stats"].get(k, 0) for s in search_rows)
            for k in ("partial_constraint_checks",)
        },
        "accounting_scope": {
            "room_nodes": "ACTUAL_ATTACHMENT_DFS_NODES_INCLUDING_REFERENCE_BOOTSTRAP",
            "equipment_counts": "ACTUAL_LAYOUT_TRIALS_AND_SELECTED_ORDERED_STOCK_WITNESSES",
            "route_nodes": "ACTUAL_REPORTED_FULL_PIPELINE_TRANSPORT_GRID_NODES",
            "uninstrumented_operations": "NOT_INFERRED_NOT_TOTAL_CPU_WORK",
            "reference_operations": "REPORTED_SEPARATELY_IN_REFERENCE_EXECUTION",
            "stage_a_b_work_or_lease_issued": False,
            "work_counting_rules_changed": False,
        },
        "native_calls": 0,
        "MAIN": False,
        "grant_claim_accessed": False,
        "production_default_changed": False,
        "global_infeasibility_proven": False,
        "source_layout_coordinates_loaded": False,
        "ranking": "QUALIFIED_ONLY_DIVERSITY_THEN_CROSSINGS_LENGTH_TURNS_AREA_NOT_FORMAL_PARETO",
    }
    result["result_hash"] = canonical_hash(result)
    return result
