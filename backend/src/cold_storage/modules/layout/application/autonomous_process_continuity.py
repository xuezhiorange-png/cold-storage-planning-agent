"""Opt-in V1.2 device-to-device composition using deterministic existing geometry.

No solver, Store, production default or MCP entry point selects this module.
Unsuccessful bounded arrangements and routes remain part of the output.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping
from dataclasses import replace
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.application.access_routing import _zone_authority_checks
from cold_storage.modules.layout.application.autonomous_factory_layout import (
    AutonomousContext,
    _room_rows,
    bind_autonomous_input,
    structural_signature,
)
from cold_storage.modules.layout.application.functional_autonomous_layout import (
    generate_functional_layout,
)
from cold_storage.modules.layout.domain import access_routing as routing
from cold_storage.modules.layout.domain.adjacency import (
    RectangleObservationV1,
    evaluate_adjacency,
    process_graph,
)
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.functional_equipment_layout import (
    build_functional_equipment,
)
from cold_storage.modules.layout.domain.functional_portal_layout import (
    functional_interior_routes,
    joint_portals,
    storage_portal_interfaces,
)
from cold_storage.modules.layout.domain.process_continuity_acceptance import (
    assess_process_continuity,
    coverage_identity,
)
from cold_storage.modules.layout.domain.process_endpoint_routes import (
    ProcessRoutePlanner,
    room_rectangles,
)
from cold_storage.modules.layout.domain.process_flow_arrangement import (
    arrange_process_workplaces,
    coating_service_depth,
    realize_coating_aisles,
    relocation_capacity_trials,
)
from cold_storage.modules.layout.domain.process_transfer_interfaces import (
    GEOMETRY,
    connect_transfer,
    geometry_fingerprint,
    route_is_conditionally_usable,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, PolygonMM

VERSION = "autonomous-process-continuity@1.2.2"
VERIFIED = GEOMETRY


def assess_process_candidate(
    c: Mapping[str, Any], project: Mapping[str, Any], parameters: Mapping[str, Any]
) -> dict[str, Any]:
    """One full admission point, using original Authority and P1 predicates."""
    from cold_storage.modules.layout.domain.access_predicates import _evaluate_bound_requirement

    context = bind_autonomous_input(project)
    rooms = {
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
    authority = True
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
                for k, q in rooms.items()
            ],
            context.binding.dimension_authorities,
            context.boundary,
            context.walls,
        )
    except LayoutAuthorityError:
        authority = False
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
    required_access = {
        q["identity"]: q for q in context.binding.access_requirements if q["flow_kind"] != "TRUCK"
    }
    observed = {
        q["requirement_identity"]: q for q in c["access_results"] if q["flow_kind"] != "TRUCK"
    }
    access_ok = set(observed) == set(required_access) and all(
        q["status"] == "PASS"
        and _evaluate_bound_requirement(routing._requirement_object(required_access[k]), q)[
            "status"
        ]
        == "PASS"
        for k, q in observed.items()
    )
    footprint = False
    try:
        # Original exported route envelopes are exact integer-mm polygons.
        corridors: list[PolygonMM] = []
        # External people route must be included from the original bound access.
        for q in observed.values():
            if q.get("topology") == "CORRIDOR_MEDIATED":
                path = tuple(
                    (round(Decimal(str(p["x"])) * 1000), round(Decimal(str(p["y"])) * 1000))
                    for p in q["centerline"]
                )
                corridors.extend(
                    e.polygon_mm
                    for e in routing._path_envelopes(
                        path, round(Decimal(str(q["corridor_clear_width_m"])) * 1000)
                    )
                )
        actual_fp = routing.derive_building_footprint(rooms, corridors)
        footprint = [list(p) for p in actual_fp] == c["building_footprint"].get("points_mm")
    except LayoutAuthorityError:
        footprint = False
    fixed = [*c["equipment"]["items"], *c["equipment"].get("process_operator_zones", [])]
    fixed.extend(
        q
        for layout in c["equipment"]["layouts"].values()
        for q in layout.get("operator_positions", [])
    )
    static = all(
        rooms[q["room"]].bounds_mm[0]
        <= q["bbox_mm"][0]
        < q["bbox_mm"][2]
        <= rooms[q["room"]].bounds_mm[2]
        and rooms[q["room"]].bounds_mm[1]
        <= q["bbox_mm"][1]
        < q["bbox_mm"][3]
        <= rooms[q["room"]].bounds_mm[3]
        and not any(
            positive_intersection(q["bbox_mm"], other["bbox_mm"])
            for other in [*fixed[:i], *c["original_building"]["columns"]]
        )
        for i, q in enumerate(fixed)
    )
    counts = {
        k: sum(q["kind"] == k for q in c["equipment"]["items"])
        for k in (
            "packing_line",
            "case_erector",
            "ten_door_locker",
            "PRI_pallet",
            "SEC_pallet",
            "case_film_component",
        )
    }
    expected_stock = {
        "packaging_material_storage": 67,
        "finished_goods_room": 324,
        "raw_fruit_buffer": 45,
        "secondary_fruit_buffer": 21,
        "frozen_fruit_room": 36,
    }
    stock = {q["layout"]["room"]: q for q in c["equipment"]["storage"]}
    stock_ok = set(stock) == set(expected_stock) and all(
        stock[k]["layout"]["placed_positions"]
        >= max(
            n,
            stock[k]["layout"]["minimum_positions"],
            stock[k]["layout"]["original_grid_positions"],
        )
        and len(stock[k]["layout"]["items"]) == stock[k]["layout"]["placed_positions"]
        and sum(q["kind"] == k + "_pallet" for q in c["equipment"]["items"])
        == stock[k]["layout"]["placed_positions"]
        and stock[k]["movement"]["conditional_pick_put_geometry_pass"]
        for k, n in expected_stock.items()
    )
    checks = {
        "original_project_and_building_binding": c["source_input_hash"] == canonical_hash(project)
        and c["source_building_hash"] == canonical_hash(project["building"])
        and canonical_hash(c["original_building"]) == canonical_hash(project["building"])
        and c["source_zone_plan_hash"] == context.binding.canonical_zone_plan_hash,
        "original_authority_and_12_rooms": authority
        and len(rooms) == 12
        and c["source_p1_handoff_hash"] == context.binding.p1_handoff_hash,
        "original_MUST_and_room_nonoverlap": bool(adjacency["geometry_passed"]),
        "all_eleven_original_nontruck_access": access_ok,
        "single_connected_zero_hole_footprint": footprint,
        "all_equipment_operators_columns_clear": static,
        "all_original_device_counts": counts
        == {
            "packing_line": 6,
            "case_erector": 5,
            "ten_door_locker": 11,
            "PRI_pallet": 18,
            "SEC_pallet": 12,
            "case_film_component": 4,
        },
        "existing_493_stock_addresses_and_pick_put": stock_ok,
        "original_53_person_two_shift_conditional_model": bool(
            c["changing_function"]["conditional_complete_sequence_verified"]
        ),
        "no_unresolved_layout_feedback": not c["remaining_geometry_issues"]
        and not c.get("storage_preservation_failure"),
    }
    return assess_process_continuity(c, parameters, checks)


def _no_candidate(
    project: Mapping[str, Any],
    parameters: Mapping[str, Any],
    source: dict[str, Any],
    status: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    result = {
        **source,
        "calculator_version": VERSION,
        "status": status,
        "candidates": [],
        "candidate_count": 0,
        "source_input_hash": canonical_hash(project),
        "process_parameter_hash": canonical_hash(parameters),
        "attempts": attempts,
    }
    result.pop("result_hash", None)
    result["result_hash"] = canonical_hash(result)
    return result


def _preserve_storage_feedback(
    original: Mapping[str, Any],
    expanded: dict[str, Any],
    project: Mapping[str, Any],
    context: AutonomousContext,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Bounded column-row feedback, never delete original pallet addresses.

    North growth can move the finished-store aisle onto retained columns. Try
    translating the coupled downstream group past that measured column row.
    Only original geometry/Authority and complete storage motion can accept it.
    """

    def counts(c: Mapping[str, Any]) -> dict[str, int]:
        return {
            s["layout"]["room"]: s["layout"]["placed_positions"] for s in c["equipment"]["storage"]
        }

    required = {
        s["layout"]["room"]: max(
            s["layout"]["placed_positions"], s["layout"]["original_grid_positions"]
        )
        for s in original["equipment"]["storage"]
    }
    trials: list[dict[str, Any]] = [
        {
            "variant": "NORTH_GROWTH",
            "required_existing_positions": required,
            "placed_positions": counts(expanded),
        }
    ]
    if all(counts(expanded).get(k, 0) >= n for k, n in required.items()):
        trials[-1]["status"] = "EXISTING_CAPACITY_PRESERVED"
        return expanded, trials
    trials[-1]["status"] = "EXISTING_CAPACITY_REJECTED"
    rooms = {
        r["zone_code"]: PlacedRectangleV1(
            r["zone_code"],
            Decimal(r["x_mm"]) / 1000,
            Decimal(r["y_mm"]) / 1000,
            Decimal(r["authority_width_m"]),
            Decimal(r["authority_depth_m"]),
            r["rotation_deg"],
        )
        for r in expanded["rooms"]
    }
    old_coat = next(r for r in original["rooms"] if r["zone_code"] == "coating_room")
    delta = (
        rooms["coating_room"].bounds_mm[3]
        - rooms["coating_room"].bounds_mm[1]
        - old_coat["depth_mm"]
    )
    f = rooms["finished_goods_room"].bounds_mm
    original_store = next(
        s["layout"]
        for s in original["equipment"]["storage"]
        if s["layout"]["room"] == "finished_goods_room"
    )
    aisle_width = original_store["main_aisle_width_mm"]
    target_aisle = [f[0], f[1], f[2], f[1] + aisle_width]
    blockers = [
        q
        for q in project["building"]["columns"]
        if positive_intersection(target_aisle, q["bbox_mm"])
    ]
    shift = max((q["bbox_mm"][3] + 100 - f[1] for q in blockers), default=0)
    for code in ("coating_room", "finished_goods_room", "shipping_channel", "office"):
        rooms[code] = replace(rooms[code], y=Decimal(rooms[code].y) + Decimal(shift) / 1000)
    trial: dict[str, Any] = {
        "variant": "COUPLED_GROUP_NORTH_OF_RETAINED_COLUMN_ROW",
        "coating_depth_increment_mm": delta,
        "group_translation_north_mm": shift,
        "triggering_columns": [q["id"] for q in blockers],
        "separation_assumption_mm": 100,
        "formula": "max(trigger_column_top_mm) + separation_assumption_mm - finished_room_south_mm",
        "finished_room_south_mm_before_translation": f[1],
        "trigger_column_top_mm": [q["bbox_mm"][3] for q in blockers],
        "source_type": "demo",
        "validity_status": "unverified",
        "requires_review": True,
        "required_existing_positions": required,
        "source": "FRESH_IN_MEMORY_ROOM_CANDIDATES",
    }
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
            raise LayoutAuthorityError("PROCESS_FEEDBACK_MUST_OR_OVERLAP_REJECTED")
        eq = build_functional_equipment(
            rooms,
            project["equipment_specs"],
            context.plan,
            project["building"]["columns"],
            context.binding.access_requirements,
        )
        new = {
            **expanded,
            "rooms": _room_rows(rooms, project, context),
            "equipment": eq,
            "room_non_overlap_and_MUST": adjacency,
        }
        trial["placed_positions"] = counts(new)
        if eq["failures"] or not all(counts(new).get(k, 0) >= n for k, n in required.items()):
            trial["status"] = "BOUNDED_VARIANT_REJECTED"
            trial["equipment_failures"] = eq["failures"]
        else:
            trial["status"] = "EXISTING_CAPACITY_PRESERVED"
            trials.append(trial)
            return new, trials
    except LayoutAuthorityError as error:
        trial.update(status="ORIGINAL_AUTHORITY_REJECTED", code=error.code, details=error.details)
    trials.append(trial)
    expanded["storage_preservation_failure"] = trials
    return expanded, trials


def _flow_routes(
    c: dict[str, Any], parameters: Mapping[str, Any], walls: list[list[int]]
) -> dict[str, Any]:
    p = ProcessRoutePlanner(c, parameters, walls)
    items = p.items

    def pal(id_: str, face: str = "N") -> str:
        return p.endpoint(id_, "PALLET-TRANSFER", face, "LOADED_PALLET")

    raw_slots = [q for q in items.values() if q["kind"] == "raw_fruit_buffer_pallet"]
    front = max(q["bbox_mm"][2] for q in raw_slots)
    raw_clear = p.rooms["raw_fruit_buffer"]
    half = parameters["main_aisle_mm"] // 2
    raw = min(
        (
            q
            for q in raw_slots
            if q["bbox_mm"][2] == front
            and raw_clear[1] + half
            <= (q["bbox_mm"][1] + q["bbox_mm"][3]) // 2
            <= raw_clear[3] - half
        ),
        key=lambda q: -q["bbox_mm"][1],
    )
    pri = next(q for q in items.values() if q["kind"] == "PRI_pallet" and q["id"].endswith("C1-P6"))
    sec = next(q for q in items.values() if q["kind"] == "SEC_pallet" and q["id"].endswith("C1-P6"))
    raw_ep = pal(raw["id"], "E")
    pri_ep = pal(pri["id"])
    sec_ep = pal(sec["id"])
    unload = pal("RAW-UNLOAD")
    common = [
        p.route(raw_ep, pri_ep, "PRODUCT-RAW-PRI", "RAW_CRATES_TO_PRIMARY_PRECOOL"),
        p.route(pri_ep, unload, "PRODUCT-PRI-PACKING", "PRIMARY_PRECOOL_TO_RAW_UNLOAD"),
    ]
    raw_crates = p.endpoint("RAW-UNLOAD", "CRATE-OUT", "N", "FOOD_TOTE_CARRY")
    depal = pal("DEPALLETIZE")
    repal = pal("REPALLETIZE")
    downstream = [p.route(sec_ep, depal, "PRODUCT-SEC-DEPAL", "SECONDARY_PRECOOL_TO_DEPALLETIZE")]
    film = sorted(
        (q for q in items.values() if q["kind"] == "case_film_component"),
        key=lambda q: q["bbox_mm"][0],
    )
    downstream.append(p.handoff("DEPALLETIZE", film[0]["id"], "FILM-DEPAL-INFEED"))
    for i, q in enumerate(film):
        downstream.append(p.handoff(q["id"], q["id"], "INTERNAL-" + q["id"], internal=True))
        if i + 1 < len(film):
            downstream.append(p.handoff(q["id"], film[i + 1]["id"], "LINK-" + q["id"]))
    downstream.append(p.handoff(film[-1]["id"], "REPALLETIZE", "FILM-OUT-REPAL"))
    finished = [q for q in items.values() if q["kind"] == "finished_goods_room_pallet"]
    storage = next(
        s["layout"]
        for s in c["equipment"]["storage"]
        if s["layout"]["room"] == "finished_goods_room"
    )
    face = {0: "S", 1: "E", 2: "N", 3: "W"}[storage["turn"]]
    finish = min(
        (q for q in finished if q["grid_row"] == 0 and q["grid_column"] >= 1),
        key=lambda q: abs(q["bbox_mm"][1] - p.rooms["finished_goods_room"][1] - 2500),
    )
    finish_ep = pal(finish["id"], face)
    dispatch = pal("DISPATCH-01", "N")
    downstream.extend(
        [
            p.route(repal, finish_ep, "PRODUCT-REPAL-FINISHED", "FILMED_PALLET_TO_FINISHED_STORE"),
            p.route(finish_ep, dispatch, "PRODUCT-FINISHED-DISPATCH", "FINISHED_STORE_TO_DISPATCH"),
        ]
    )
    buffers = []
    for group in ("N", "S"):
        for i in range(1, 8):
            ident = f"BUF-{group}-{i:02}"
            ep = pal(ident)
            buffers.append(
                p.route(ep, sec_ep, "BUFFER-SEC-" + ident, "BUFFER_POSITION_TO_SECONDARY_PRECOOL")
            )
    chains = []
    transfers: dict[str, dict[str, Any]] = {}
    packing_inputs = []
    packing_outputs = []
    for i in range(1, 7):
        machine = f"PACK-{i:02}"
        inp = p.endpoint(machine, "RAW-IN", "W", "FOOD_TOTE_CARRY")
        out = p.endpoint(machine, "PRODUCT-OUT", "E", "CARTON_CARRY")
        packing_inputs.append(p.endpoint(machine, "BOX-IN", "W", "CARTON_CARRY"))
        work = f"WORK-PACK-{i:02}"
        case_work = p.endpoint(work, "CASE-IN", "N", "CARTON_CARRY")
        work_ep = pal(work)
        group = "N" if i <= 3 else "S"
        bid = f"BUF-{group}-{(i - 1) % 3 + 1:02}"
        be = p.endpoints[bid + ":PALLET-TRANSFER"]["id"]
        a = p.route(raw_crates, inp, "RAW-LINE-" + str(i), "FOOD_TOTE_TO_PACKING_INLET")
        machine_process = p.handoff(machine, machine, "PROCESS-" + machine, internal=True)
        machine_process.update(
            purpose="PACKING_MACHINE_INTERNAL",
            physical_input_endpoint=inp,
            physical_output_endpoint=out,
            note="Declared equipment-internal transfer; no vendor performance approval",
        )
        b = p.route(
            out, case_work, "PACK-PALLET-" + str(i), "PACKED_CARTONS_TO_LINE_PALLET_WORKPLACE"
        )
        packing_outputs.append(b)
        d = p.route(work_ep, be, "LINE-BUFFER-" + str(i), "FULL_PALLET_TO_ASSIGNED_BUFFER")
        e = next(q for q in buffers if q["id"] == "BUFFER-SEC-" + bid)
        legs = [*common, a, machine_process, b, d, e, *downstream]
        failed = [q["id"] for q in legs if not route_is_conditionally_usable(q)]
        transfer_ids = []
        for left, right in zip(legs, legs[1:], strict=False):
            tid = "TRANSFER:" + left["id"] + ":" + right["id"]
            if tid not in transfers:
                transfers[tid] = connect_transfer(
                    c, parameters, left, right, p.endpoints, identity=tid
                )
            transfer_ids.append(tid)
        chains.append(
            {
                "id": "PRODUCT-CHAIN-" + str(i),
                "line": machine,
                "service_group": group,
                "stages": [
                    {
                        "route_id": q["id"],
                        "source_object": q["source_object"],
                        "target_object": q["target_object"],
                        "status": q["status"],
                    }
                    for q in legs
                ],
                "failed_segments": failed,
                "transfer_ids": transfer_ids,
                "continuous_object_chain": all(
                    a["target_object"] == b["source_object"]
                    for a, b in zip(legs, legs[1:], strict=False)
                ),
                "length_mm": sum(q["length_mm"] for q in legs),
                "status": "CONTINUOUS_CONDITIONAL_CHAIN"
                if not failed
                else "INTERRUPTED_BOUNDED_SEARCH",
                "packing_process": "DESIGN_CONDITION_NOT_MACHINE_ACCEPTANCE",
            }
        )
    # All five erectors receive blanks from a real front stock position. Their
    # output-to-line assignments are selected by verified path length, not XY.
    package = [q for q in items.values() if q["kind"] == "packaging_material_storage_pallet"]
    edge = max(q["bbox_mm"][2] for q in package)
    blank = min(
        (q for q in package if q["bbox_mm"][2] == edge),
        key=lambda q: abs(q["bbox_mm"][1] - p.rooms["packaging_material_storage"][1] - 7000),
    )
    blank_ep = p.endpoint(blank["id"], "BLANKS", "E", "BLANK_BUNDLE")
    erectors = sorted(
        (q for q in items.values() if q["kind"] == "case_erector"), key=lambda q: q["id"]
    )
    blank_routes = []
    deliveries = []
    for machine in erectors:
        mid = machine["id"]
        inp = p.endpoint(
            mid,
            "BLANK-IN",
            machine.get("magazine_face", "E"),
            "BLANK_BUNDLE",
            offset_tangent=-700 if mid == "ERECT-05" else 0,
        )
        output = p.endpoint(
            mid,
            "CASE-OUT",
            machine.get("output_face", "E"),
            "CARTON_CARRY",
            offset_tangent=700 if mid == "ERECT-05" else 0,
        )
        blank_routes.append(p.route(blank_ep, inp, "BLANK-" + mid, "PAPER_BLANK_SUPPLY"))
        deliveries.append(
            [
                p.route(
                    output, dest, f"EMPTY-CASE-{mid}-LINE-{i + 1}", "ERECTED_CASE_TO_PACKING_LINE"
                )
                for i, dest in enumerate(packing_inputs)
            ]
        )
    choices = []
    for assignment in itertools.product(range(5), repeat=6):
        if len(set(assignment)) != 5 or any(assignment.count(k) > 2 for k in range(5)):
            continue
        routes = [deliveries[e][i] for i, e in enumerate(assignment)]
        if all(q["status"] == VERIFIED for q in [*routes, *blank_routes]):
            choices.append((sum(q["length_mm"] for q in routes), assignment))
    selected = min(choices) if choices else None
    assignments = (
        [
            {
                "line": f"PACK-{i + 1:02}",
                "erector": erectors[e]["id"],
                "route_id": deliveries[e][i]["id"],
                "length_mm": deliveries[e][i]["length_mm"],
            }
            for i, e in enumerate(selected[1])
        ]
        if selected
        else []
    )
    branches = []
    for prefix, room, line in (
        ("SECONDARY", "secondary_fruit_buffer", 1),
        ("FROZEN", "frozen_fruit_room", 2),
    ):
        machine = f"PACK-{line:02}"
        source = p.endpoint(machine, prefix + "-CONDITIONAL-SORT-OUT", "E", "FOOD_TOTE_CARRY")
        target = p.endpoint(f"WORK-PACK-{line:02}", prefix + "-BIN-IN", "N", "FOOD_TOTE_CARRY")
        feeding = p.route(source, target, prefix + "-SORT-WORK", prefix + "_SORT_OUT_TO_WORKPLACE")
        stock = [q for q in items.values() if q["kind"] == room + "_pallet"]
        # Selection uses the actual legal portal, not an archived room coordinate.
        door = next(q for q in c["access_results"] if q.get("to_ref") == room)
        seg = door["portal_to"]["segment"]
        centre = round((Decimal(str(seg["start"]["x"])) + Decimal(str(seg["end"]["x"]))) * 500)
        slot = min(
            (q for q in stock if q["grid_row"] == 0),
            key=lambda q: abs((q["bbox_mm"][0] + q["bbox_mm"][2]) // 2 - centre),
        )
        delivery = p.route(
            pal(f"WORK-PACK-{line:02}"),
            pal(slot["id"]),
            prefix + "-WORK-STORE",
            prefix + "_WORKPLACE_TO_STORAGE",
        )
        tid = "TRANSFER:" + feeding["id"] + ":" + delivery["id"]
        transfers[tid] = connect_transfer(
            c, parameters, feeding, delivery, p.endpoints, identity=tid
        )
        split_id = "SPLIT:" + prefix
        raw_line = next(q for q in p.routes if q["id"] == "RAW-LINE-" + str(line))
        transfers[split_id] = connect_transfer(
            c, parameters, raw_line, feeding, p.endpoints, identity=split_id
        )
        branches.append(
            {
                "flow_kind": prefix,
                "from_ref": "sorting_packaging_room",
                "to_ref": room,
                "source_interface": source,
                "interface_basis": "CONDITIONAL_REJECT_OUTLET_NOT_VENDOR_CONFIRMED",
                "route_ids": [feeding["id"], delivery["id"]],
                "transfer_ids": [split_id, tid],
                "stock_handoff_object": slot["id"],
                "workplace_policy": "TIME_SEPARATED_FROM_MAIN_PRODUCT_PALLET_ASSEMBLY",
                "actual_sort_outlet_and_storage_process": "INPUT_REQUIRED",
            }
        )
    for machine in erectors:
        mid = machine["id"]
        supply = next(q for q in blank_routes if q["target_object"] == mid)
        selected_delivery = next((q for q in assignments if q["erector"] == mid), None)
        if selected_delivery:
            delivery = next(q for q in p.routes if q["id"] == selected_delivery["route_id"])
            tid = "FORMING:" + mid
            transfers[tid] = connect_transfer(
                c, parameters, supply, delivery, p.endpoints, identity=tid
            )
    for route in p.routes:
        route.pop("witness_hash", None)
        route["witness_hash"] = canonical_hash(route)
    verified = [q for q in p.routes if route_is_conditionally_usable(q)]
    return {
        "schema_version": VERSION,
        "endpoints": list(p.endpoints.values()),
        "routes": p.routes,
        "product_chains": chains,
        "transfers": list(transfers.values()),
        "auxiliary_branches": branches,
        "continuous_main_product_chain_count": sum(
            q["status"] == "CONTINUOUS_CONDITIONAL_CHAIN" and q["continuous_object_chain"]
            for q in chains
        ),
        "case_supply": {
            "erector_count": 5,
            "blank_supply_routes": [q["id"] for q in blank_routes],
            "all_five_blank_supplies_verified": all(q["status"] == VERIFIED for q in blank_routes),
            "bounded_assignment_count": len(choices),
            "line_assignments": assignments,
            "status": "FIVE_ERECTORS_SIX_LINES_CONNECTED"
            if selected
            else "INTERRUPTED_BOUNDED_ASSIGNMENT",
        },
        "buffer_routes": [q["id"] for q in buffers],
        "buffer_count": 14,
        "line_pallet_workplace_count": 6,
        "buffer_verified_count": sum(q["status"] == VERIFIED for q in buffers),
        "verified_route_count": len(verified),
        "failed_route_count": len(p.routes) - len(verified),
        "shared_space_policy": (
            "TIME_SEPARATION_REQUIRED; occupied waiting pallets retained; "
            "no simultaneous traffic or throughput PASS"
        ),
        "capacity_conditions": parameters["source_conditions"],
        "vehicle_kinematics": "INPUT_REQUIRED",
        "assumptions": parameters["assumptions"],
        "native_calls": 0,
    }


def generate_process_layout(
    project: Mapping[str, Any],
    parameters: Mapping[str, Any],
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if parameters.get("schema_version") != "autonomous-process-parameters@1.2.0":
        raise LayoutAuthorityError("PROCESS_PARAMETER_VERSION_REQUIRED")
    if (
        parameters["line_workers"] != [10, 10, 10, 8, 8, 7]
        or parameters["buffer_slots_per_group"] != 7
    ):
        raise LayoutAuthorityError("PROCESS_DESIGN_BASIS_MISMATCH")
    if parameters["main_aisle_mm"] < 2500 or parameters["pallet_mm"] != [1200, 1000]:
        raise LayoutAuthorityError("PROCESS_AISLE_OR_LOAD_REDUCTION_FORBIDDEN")
    if not 1 <= parameters["routing_node_budget"] <= 20000:
        raise LayoutAuthorityError("PROCESS_BOUNDED_ROUTING_REQUIRED")
    if any(k in parameters for k in ("rooms", "initial_layout", "hints", "equipment_positions")):
        raise LayoutAuthorityError("PROCESS_COORDINATE_SEEDS_FORBIDDEN")
    if any(
        type(n) is not int or n <= 0
        for key in ("carton_projection_mm", "station_operator_mm")
        for n in parameters[key]
    ):
        raise LayoutAuthorityError("POSITIVE_INTEGER_PHYSICAL_ENVELOPES_REQUIRED")
    context = bind_autonomous_input(project)
    base = generate_functional_layout(project, progress=progress)
    if not base["candidates"]:
        return _no_candidate(
            project, parameters, base, "BOUNDED_ROOM_SEARCH_NO_CANDIDATE", base["attempts"]
        )
    original = base["candidates"][0]
    attempts = relocation_capacity_trials(
        room_rectangles(original),
        context.plan,
        project["equipment_specs"],
        project["building"]["columns"],
    )
    preliminary = arrange_process_workplaces(original, parameters)
    attempts.append(
        {
            "variant": "DEVICE_DOCKS_IN_EXISTING_ROOMS",
            "status": "STATIC_REJECTED" if preliminary["static_conflicts"] else "STATIC_ONLY",
            "conflicts": preliminary["static_conflicts"],
            "coating_depth_mm": next(
                r["depth_mm"] for r in original["rooms"] if r["zone_code"] == "coating_room"
            ),
        }
    )
    required = coating_service_depth(parameters)
    if progress:
        progress("DEVICE_OPERATION_FEEDBACK_AND_ROOM_REGENERATION")
    regenerated = generate_functional_layout(
        project, progress=progress, coating_service_depth_mm=required["depth_mm"]
    )
    if not regenerated["candidates"]:
        return _no_candidate(
            project,
            parameters,
            regenerated,
            "BOUNDED_FEEDBACK_SEARCH_NO_CANDIDATE",
            attempts + regenerated["attempts"],
        )
    repaired, storage_trials = _preserve_storage_feedback(
        original, regenerated["candidates"][0], project, context
    )
    attempts.extend(storage_trials)
    arranged = arrange_process_workplaces(repaired, parameters)
    c = arranged["candidate"]
    eq = c["equipment"]
    rooms = room_rectangles(c)
    entrances: dict[str, Any] = {
        "main_entrance": tuple(tuple(p) for p in project["building"]["openings"][1]["segment_mm"]),
        "truck_entrance": tuple(tuple(p) for p in project["building"]["openings"][0]["segment_mm"]),
    }
    access, corridors, approaches = joint_portals(
        rooms,
        context.binding.access_requirements,
        context.binding.spatial_relationships,
        eq,
        context.boundary,
        context.columns + context.walls,
        entrances,
    )
    c["access_results"] = access
    c["portal_approach_checks"] = approaches
    c["non_truck_access_pass_count"] = sum(
        q.get("status") == "PASS" for q in access if q["flow_kind"] != "TRUCK"
    )
    # The original changing adapter and portals are not re-designed. If these
    # two portal identities/geometries changed, do not inherit the old motion PASS.
    old_people = [
        q for q in regenerated["candidates"][0]["access_results"] if q["flow_kind"] == "PEOPLE"
    ]
    new_people = [q for q in access if q["flow_kind"] == "PEOPLE"]
    c["changing_existing_witness_preserved"] = canonical_hash(old_people) == canonical_hash(
        new_people
    )
    c["changing_internal_model_unchanged"] = True
    if not c["changing_existing_witness_preserved"]:
        from cold_storage.modules.layout.domain.functional_changing_layout import (
            evaluate_changing_entry_exit,
        )

        g = eq["layouts"]["changing_room"]["functional_geometry"]
        check = evaluate_changing_entry_exit(g, rooms["changing_room"], access)
        c["changing_function"]["entry_exit"] = check
        c["changing_function"]["conditional_complete_sequence_verified"] = bool(
            c["changing_function"]["initial_53_people_verified"]
            and all(s["cycle_geometry_pass"] for s in c["changing_function"]["shifts"])
            and check["entry_exit_verified"]
        )
        c["changing_function"]["entry_exit_revalidation"] = "EXISTING_UNMODIFIED_ADAPTER_REEXECUTED"
    try:
        fp = routing.derive_building_footprint(rooms, corridors)
        c["building_footprint"] = {
            "status": "SINGLE_CONNECTED_ZERO_HOLE_UNION",
            "points_mm": [list(p) for p in fp],
        }
    except LayoutAuthorityError as error:
        c["building_footprint"] = {"status": "NOT_VERIFIED", "code": error.code}
    if progress:
        progress("DEVICE_PORTS_PALLET_SWEEPS_AND_REAL_DOOR_CROSSINGS")
    walls = [list(b) for w in context.walls if (b := routing._rectangle_bounds(w))]
    flows = _flow_routes(c, parameters, walls)
    aisle_feedback = realize_coating_aisles(c, flows, arranged["static_conflicts"])
    c["coating_actual_aisle_feedback"] = aisle_feedback
    route_index = {r["id"]: r for r in flows["routes"]}
    endpoint_index = {e["id"]: e for e in flows["endpoints"]}
    flows["transfers"] = [
        connect_transfer(
            c,
            parameters,
            route_index[t["upstream_route"]],
            route_index[t["downstream_route"]],
            endpoint_index,
            identity=t["id"],
        )
        for t in flows["transfers"]
    ]
    c["schema_version"] = VERSION
    c["structural_signature"] = structural_signature(rooms)
    c["source_process_parameter_hash"] = canonical_hash(parameters)
    flows["carrier_parameters"] = parameters["carriers"]
    flows["carton_projection_mm"] = parameters["carton_projection_mm"]
    c["process_continuity"] = flows
    # Reuse only the original requirement identities; recompute all geometry.
    flows["v11_required_coverage"] = {
        "interior": [
            coverage_identity(q, "interior") for q in original["equipment_aware_interior_paths"]
        ],
        "storage": [coverage_identity(q, "storage") for q in original["storage_portal_interfaces"]],
    }
    route_obstacles = [*c["original_building"]["columns"], *eq.get("process_operator_zones", [])]
    route_obstacles.extend(
        q for layout in eq["layouts"].values() for q in layout.get("operator_positions", [])
    )
    c["equipment_aware_interior_paths"] = functional_interior_routes(
        rooms, access, eq, route_obstacles, use_reserved_waypoints=True
    )
    c["storage_portal_interfaces"] = storage_portal_interfaces(
        rooms, access, eq, route_obstacles, use_reserved_waypoints=True
    )
    for kind, field in (
        ("interior", "equipment_aware_interior_paths"),
        ("storage", "storage_portal_interfaces"),
    ):
        for row in c[field]:
            row["coverage_id"] = coverage_identity(row, kind)
            row["geometry_context_hash"] = geometry_fingerprint(c, parameters)
            row["evidence_origin"] = "CURRENT_A12_RECOMPUTED_WITH_ORIGINAL_PREDICATES"

    c["metrics"].update(
        gross_room_area_m2=str(sum(Decimal(q["area_m2"]) for q in c["rooms"])),
        retained_internal_column_area_m2=str(sum(Decimal(q["column_area_m2"]) for q in c["rooms"])),
        portal_approach_conflict_count=sum(q["status"] != "BODY_FREE_APPROACH" for q in approaches),
        verified_interior_route_count=sum(
            q["status"] == "INTERIOR_FULL_WIDTH_PATH_VERIFIED"
            for q in c["equipment_aware_interior_paths"]
        ),
        verified_device_route_count=flows["verified_route_count"],
        continuous_product_chain_count=flows["continuous_main_product_chain_count"],
    )
    c["remaining_geometry_issues"] = arranged["static_conflicts"]
    c["process_workplace_groups"] = arranged["group_mapping"]
    admission = assess_process_candidate(c, project, parameters)
    c["process_admission"] = admission
    c["status"] = admission["status"]
    flows["continuous_main_product_chain_count"] = admission["main_line_count"]
    c["metrics"]["continuous_product_chain_count"] = admission["main_line_count"]
    for chain, check in zip(flows["product_chains"], admission["main_lines"], strict=True):
        chain["status"] = check["status"]
        transfer_index = {t["id"]: t for t in flows["transfers"]}
        chain["failed_transfers"] = [
            i for i in chain["transfer_ids"] if transfer_index[i]["geometry_status"] != GEOMETRY
        ]
        chain["continuous_transfer_chain"] = not chain["failed_transfers"]
    c.pop("result_hash", None)
    c["result_hash"] = canonical_hash(c)
    attempts.append(
        {
            "variant": "ROTATE_FOUR_ERECTORS_PLUS_DISTINCT_BUFFER_AND_WORK_POSITIONS",
            "coating_service_depth": required,
            "static_conflicts": arranged["static_conflicts"],
            "actual_nontruck_access_pass": c["non_truck_access_pass_count"],
            "continuous_main_product_chains": flows["continuous_main_product_chain_count"],
            "route_failures": [
                {"id": q["id"], "failure": q.get("failure", q["status"])}
                for q in flows["routes"]
                if not route_is_conditionally_usable(q)
            ],
        }
    )
    old = {q["id"]: q for q in original["equipment"]["items"]}
    changes = [
        {
            "id": q["id"],
            "kind": q["kind"],
            "old_bbox_mm": old.get(q["id"], {}).get("bbox_mm"),
            "new_bbox_mm": q["bbox_mm"],
            "reason": "DETERMINISTIC_DEVICE_PORT_AND_WORKPLACE_FEEDBACK",
        }
        for q in eq["items"]
        if old.get(q["id"], {}).get("bbox_mm") != q["bbox_mm"]
    ]
    result = {
        "task_id": "V2_2_2_AUTONOMOUS_PROCESS_FLOW_CONTINUITY_R1",
        "calculator_version": VERSION,
        "source_input_hash": canonical_hash(project),
        "process_parameter_hash": canonical_hash(parameters),
        "p1_handoff_hash": context.binding.p1_handoff_hash,
        "zone_plan": context.plan,
        "baseline": {
            "result_hash": original["result_hash"],
            "rooms": original["rooms"],
            "equipment_endpoint_route_count": 0,
            "note": (
                "V1.1 only proved room interior/portal interfaces; "
                "full equipment logistics was NOT_EVALUATED"
            ),
        },
        "attempts": attempts,
        "candidates": [c],
        "candidate_count": 1,
        "equipment_changes": changes,
        "room_changes": [
            {
                "zone_code": q["zone_code"],
                "original_bbox_mm": old_room["bbox_mm"],
                "new_bbox_mm": q["bbox_mm"],
                "added_area_m2": str(Decimal(q["area_m2"]) - Decimal(old_room["area_m2"])),
                "translation_x_mm": q["x_mm"] - old_room["x_mm"],
                "translation_y_mm": q["y_mm"] - old_room["y_mm"],
            }
            for q in c["rooms"]
            for old_room in original["rooms"]
            if q["zone_code"] == old_room["zone_code"] and q["bbox_mm"] != old_room["bbox_mm"]
        ],
        "room_search_runs": [
            {"purpose": "A1_BASELINE", "attempts": base["attempts"]},
            {"purpose": "PHYSICAL_WORKPLACE_FEEDBACK", "attempts": regenerated["attempts"]},
        ],
        "status": c["status"],
        "source_layout_coordinates_loaded": False,
        "native_calls": 0,
        "MAIN": False,
        "grant_claim_accessed": False,
        "production_default_changed": False,
        "global_infeasibility_proven": False,
    }
    result["result_hash"] = canonical_hash(result)
    return result
