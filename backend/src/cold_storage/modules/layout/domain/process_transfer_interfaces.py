"""Explicit load/contact/operation transitions for the V1.2 process chain.

Projection geometry never certifies machine internals or human reach. Those
operations retain CONDITIONAL_OPERATION_ASSUMED and their real inputs remain
INPUT_REQUIRED. No authorization, database or Native solver is involved.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_material_geometry import (
    bounds_inside,
    rectilinear_path,
    swept_boxes,
)

GEOMETRY = "GEOMETRY_VERIFIED"
ASSUMED = "CONDITIONAL_OPERATION_ASSUMED"
REQUIRED = "INPUT_REQUIRED"


def geometry_fingerprint(c: Mapping[str, Any], parameters: Mapping[str, Any]) -> str:
    return canonical_hash(
        {
            "rooms": c["rooms"],
            "building": c["original_building"],
            "p1": c["source_p1_handoff_hash"],
            "parameters": parameters,
            "items": c["equipment"]["items"],
            "operators": c["equipment"].get("process_operator_zones", []),
            "packing_operators": c["equipment"]["layouts"]["sorting_packaging_room"].get(
                "operator_positions", []
            ),
            "access": c["access_results"],
            "storage": c["equipment"]["storage"],
            "changing": c["changing_function"],
        }
    )


def endpoint_fingerprint(e: Mapping[str, Any]) -> str:
    return canonical_hash(e)


def route_is_conditionally_usable(r: Mapping[str, Any]) -> bool:
    return r.get("geometry_status") == GEOMETRY and r.get("status") in (GEOMETRY, ASSUMED)


def route_states(r: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    purpose = r["purpose"]
    carrier = r.get("carrier", "")
    form = ""
    transport = ""
    if purpose in ("RAW_CRATES_TO_PRIMARY_PRECOOL", "PRIMARY_PRECOOL_TO_RAW_UNLOAD"):
        form = "FRUIT_IN_TURNOVER_CRATES"
        transport = "PALLET_JACK"
    elif purpose == "FOOD_TOTE_TO_PACKING_INLET":
        form = "LOOSE_FRUIT_IN_FOOD_BIN"
        transport = "HAND_CARRIED_FOOD_BIN"
    elif purpose == "PACKING_MACHINE_INTERNAL":
        return (
            {"payload_form": "LOOSE_FRUIT_FLOW", "carrier": "PACKING_CONVEYOR"},
            {"payload_form": "PACKED_CARTON", "carrier": "PACKING_CONVEYOR"},
        )
    elif purpose == "PACKED_CARTONS_TO_LINE_PALLET_WORKPLACE":
        form = "PACKED_CARTON"
        transport = "HAND_CARRIED_CARTON"
    elif purpose in (
        "FULL_PALLET_TO_ASSIGNED_BUFFER",
        "BUFFER_POSITION_TO_SECONDARY_PRECOOL",
        "SECONDARY_PRECOOL_TO_DEPALLETIZE",
        "FILMED_PALLET_TO_FINISHED_STORE",
        "FINISHED_STORE_TO_DISPATCH",
    ):
        form = "PALLETIZED_CARTONS"
        transport = "PALLET_JACK"
    elif purpose in ("SECONDARY_SORT_OUT_TO_WORKPLACE", "FROZEN_SORT_OUT_TO_WORKPLACE"):
        form = purpose.split("_")[0] + "_FRUIT_IN_FOOD_BIN"
        transport = "HAND_CARRIED_FOOD_BIN"
    elif purpose in ("SECONDARY_WORKPLACE_TO_STORAGE", "FROZEN_WORKPLACE_TO_STORAGE"):
        form = "PALLETIZED_" + purpose.split("_")[0] + "_FRUIT_BINS"
        transport = "PALLET_JACK"
    elif purpose == "PAPER_BLANK_SUPPLY":
        form = "PAPER_BLANK_BUNDLE"
        transport = "BLANK_BUNDLE_TROLLEY"
    elif purpose == "ERECTED_CASE_TO_PACKING_LINE":
        form = "EMPTY_ERECTED_CASE"
        transport = "HAND_CARRIED_EMPTY_CASE"
    elif purpose in ("CARTON_MACHINE_INTERNAL", "CARTON_SHORT_HANDOFF"):
        form = "PACKED_CARTON"
        transport = "FILM_CONVEYOR"
        if r["source_object"] == "DEPALLETIZE":
            transport = "MANUAL_CARTON_TRANSFER"
    if not form:
        return (
            {"payload_form": "UNSUPPORTED", "carrier": carrier},
            {"payload_form": "UNSUPPORTED", "carrier": carrier},
        )
    state = {"payload_form": form, "carrier": transport}
    return dict(state), dict(state)


def route_anchor(
    r: Mapping[str, Any],
    side: str,
    endpoints: Mapping[str, Mapping[str, Any]],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    e = endpoints[r[side + "_endpoint"]]
    reference = list(e.get("dock_reference_mm", e["contact_mm"]))
    load = list(reference)
    if "dock_reference_mm" in e:
        spec = parameters["carriers"][e["carrier"]]
        normal = e["normal"]
        load = [
            reference[i] - normal[i] * (spec["normal_mm"] - spec["load_normal_mm"]) // 2
            for i in range(2)
        ]
    return {
        "endpoint": e["id"],
        "object_id": e["object_id"],
        "room": e["room"],
        "reference_mm": reference,
        "load_anchor_mm": load,
        "contact_mm": e["contact_mm"],
    }


def operation_kind(before: Mapping[str, str], after: Mapping[str, str], owner: str) -> str:
    a, b = before["payload_form"], after["payload_form"]
    if a == "FRUIT_IN_TURNOVER_CRATES" and b == "LOOSE_FRUIT_IN_FOOD_BIN":
        return "UNLOAD_CRATES_TO_FOOD_BIN"
    if a == "LOOSE_FRUIT_IN_FOOD_BIN" and b in (
        "SECONDARY_FRUIT_IN_FOOD_BIN",
        "FROZEN_FRUIT_IN_FOOD_BIN",
    ):
        return "CONDITIONAL_SORT_REJECTION"
    if a == "LOOSE_FRUIT_IN_FOOD_BIN" and b == "LOOSE_FRUIT_FLOW":
        return "TIP_FOOD_BIN_INTO_PACKING"
    if a == "PACKED_CARTON" and b == "PALLETIZED_CARTONS":
        return "REPALLETIZE" if owner == "REPALLETIZE" else "ASSEMBLE_LINE_PALLET"
    if a == "PALLETIZED_CARTONS" and b == "PACKED_CARTON":
        return "DEPALLETIZE"
    if b.startswith("PALLETIZED_") and a.endswith("_FRUIT_IN_FOOD_BIN"):
        return "ASSEMBLE_BRANCH_PALLET"
    if a == "PAPER_BLANK_BUNDLE" and b == "EMPTY_ERECTED_CASE":
        return "ERECT_EMPTY_CASE"
    if a == b and before["carrier"] == after["carrier"]:
        return "SAME_PHYSICAL_LOAD_INTERFACE"
    if a == b:
        return "REGISTERED_MACHINE_MANUAL_HANDOFF"
    return "UNSUPPORTED_STATE_TRANSITION"


def _box(p: Sequence[int], w: int, d: int) -> list[int]:
    return [p[0] - w // 2, p[1] - d // 2, p[0] + w - w // 2, p[1] + d - d // 2]


def _physical_boxes(path: Sequence[Sequence[int]], w: int, d: int) -> list[list[int]]:
    boxes = [list(b) for b in swept_boxes([(p[0], p[1]) for p in path], w, d)]
    # A stationary interface still occupies space; zero-length is not a waiver.
    return boxes or ([_box(path[0], w, d)] if path else [])


def connect_transfer(
    c: Mapping[str, Any],
    parameters: Mapping[str, Any],
    upstream: Mapping[str, Any],
    downstream: Mapping[str, Any],
    endpoints: Mapping[str, Mapping[str, Any]],
    *,
    identity: str,
) -> dict[str, Any]:
    left = route_anchor(upstream, "target", endpoints, parameters)
    right = route_anchor(downstream, "source", endpoints, parameters)
    before = route_states(upstream)[1]
    after = route_states(downstream)[0]
    owner = left["object_id"]
    kind = operation_kind(before, after, owner)
    items = {q["id"]: q for q in c["equipment"]["items"]}
    body = items[owner]["bbox_mm"]
    room = left["room"]
    clear = next(q["bbox_mm"] for q in c["rooms"] if q["zone_code"] == room)
    exceptions = {owner}
    # The two named mouths of the adjoining short transfer are checked as one
    # registered interface, not as arbitrary permission to cross other frames.
    if upstream["purpose"] == "CARTON_SHORT_HANDOFF":
        exceptions.add(upstream["source_object"])
    if downstream["purpose"] == "CARTON_SHORT_HANDOFF":
        exceptions.add(downstream["target_object"])
    fixed = [
        *c["equipment"]["items"],
        *c["equipment"].get("process_operator_zones", []),
        *c["original_building"]["columns"],
    ]
    for layout in c["equipment"]["layouts"].values():
        fixed.extend(layout.get("operator_positions", []))
    obs = [q["bbox_mm"] for q in fixed if q["id"] not in exceptions]
    same = before == after and left["load_anchor_mm"] == right["load_anchor_mm"]
    projection = (
        [body[2] - body[0], body[3] - body[1]]
        if same and endpoints[left["endpoint"]].get("carried_pallet")
        else list(parameters["carton_projection_mm"])
    )
    path = (
        [left["load_anchor_mm"], right["load_anchor_mm"]]
        if same
        else [
            left["load_anchor_mm"],
            left["contact_mm"],
            right["contact_mm"],
            right["load_anchor_mm"],
        ]
    )
    path = [p for i, p in enumerate(path) if i == 0 or p != path[i - 1]]
    if len(path) == 1:
        path.append(path[0])
    # Face-to-face corners are expanded into a deterministic rectilinear contact
    # path. The registered owner projection is the only body exception.
    joined = [path[0]]
    for p in path[1:]:
        a = joined[-1]
        if a[0] != p[0] and a[1] != p[1]:
            joined.append([p[0], a[1]])
        joined.append(p)
    boxes = _physical_boxes(joined, *projection)
    collisions = [
        {
            "bbox_mm": b,
            "objects": [
                q["id"]
                for q in fixed
                if q["id"] not in exceptions and positive_intersection(b, q["bbox_mm"])
            ],
        }
        for b in boxes
        if not bounds_inside(b, clear) or any(positive_intersection(b, o) for o in obs)
    ]
    same = before == after and left["load_anchor_mm"] == right["load_anchor_mm"]
    workspaces = []
    actor_paths = []
    internal_mouths = all(
        "dock_reference_mm" not in endpoints[a["endpoint"]] for a in (left, right)
    )
    if not same and not internal_mouths:
        if owner in ("DEPALLETIZE", "REPALLETIZE"):
            workspaces = [
                dict(q)
                for q in c["equipment"]["process_operator_zones"]
                if q["id"] == owner + "-OPERATOR"
            ]
        else:
            endpoint = (
                endpoints[right["endpoint"]]
                if "dock_reference_mm" in endpoints[right["endpoint"]]
                and not endpoints[right["endpoint"]].get("carried_pallet")
                else endpoints[left["endpoint"]]
            )
            face = endpoint["face"]
            cx, cy = (body[0] + body[2]) // 2, (body[1] + body[3]) // 2
            # Declared 600x900 standing action; carrier reference and actor pose
            # are distinct, and the difference is preserved rather than hidden.
            p = (
                [body[0] - 550, cy]
                if face == "W"
                else [body[2] + 550, cy]
                if face == "E"
                else [cx, body[1] - 550]
                if face == "S"
                else [cx, body[3] + 550]
            )
            w, d = (900, 600) if face in ("E", "W") else (600, 900)
            workspaces = [
                {
                    "id": identity + ":ACTOR",
                    "room": room,
                    "bbox_mm": _box(p, w, d),
                    "actor_reference_mm": p,
                    "standing_envelope_mm": [w, d],
                    "scope": "ACTING_TRANSFER_PERSON_NOT_AN_ADDITIONAL_STATIONARY_PERSON",
                }
            ]
            if kind == "UNLOAD_CRATES_TO_FOOD_BIN":
                start = [body[2] + 550, cy]
                blockers = [
                    q["bbox_mm"] for q in fixed
                ]  # Actor cannot walk through its own pallet.
                actor_path, nodes = rectilinear_path(
                    tuple(start), tuple(p), clear, blockers, 900, 900, node_budget=4000
                )
                actor_paths = [
                    {
                        "centerline_mm": [list(x) for x in actor_path],
                        "body_mm": [900, 900],
                        "nodes": nodes,
                        "geometry_status": GEOMETRY
                        if actor_path
                        else "BOUNDED_ACTOR_PATH_NOT_FOUND",
                    }
                ]
                workspaces.insert(
                    0,
                    {
                        "id": identity + ":CRATE_TIP",
                        "room": room,
                        "bbox_mm": _box(start, 900, 600),
                        "scope": "EAST_SIDE_CONDITIONAL_CRATE_TRANSFER",
                    },
                )
        for workspace in workspaces:
            b = workspace["bbox_mm"]
            blocked = [
                q["id"]
                for q in fixed
                if q["id"] != workspace["id"] and positive_intersection(b, q["bbox_mm"])
            ]
            if not bounds_inside(b, clear) or blocked:
                collisions.append(
                    {"operation_space": workspace["id"], "bbox_mm": b, "objects": blocked}
                )
    aisles = c["equipment"]["layouts"][room]["service_corridors"]
    shared = sorted(
        {
            a["id"]
            for a in aisles
            for w in workspaces
            if positive_intersection(a["bbox_mm"], w["bbox_mm"])
        }
    )
    valid = (
        left["object_id"] == right["object_id"]
        and room == right["room"]
        and kind != "UNSUPPORTED_STATE_TRANSITION"
        and not collisions
        and all(a["geometry_status"] == GEOMETRY for a in actor_paths)
    )
    operation_status = GEOMETRY if same else ASSUMED
    row = {
        "id": identity,
        "kind": kind,
        "upstream_route": upstream["id"],
        "downstream_route": downstream["id"],
        "from": left,
        "to": right,
        "before_state": before,
        "after_state": after,
        "reference_gap_mm": sum(
            abs(a - b) for a, b in zip(left["reference_mm"], right["reference_mm"], strict=True)
        ),
        "load_path_mm": joined,
        "load_projection_mm": projection,
        "load_swept_bbox_mm": boxes,
        "owner_body_exceptions": sorted(exceptions),
        "operation_spaces": workspaces,
        "actor_paths": actor_paths,
        "shared_reserved_aisles": shared,
        "traffic_policy": "TIME_SEPARATION_REQUIRED" if shared else "NO_RESERVED_AISLE_OVERLAP",
        "geometry_status": GEOMETRY if valid else "TRANSFER_GEOMETRY_REJECTED",
        "validation_status": operation_status if valid else REQUIRED,
        "actual_operation_status": REQUIRED if not same else "NOT_AN_INTERNAL_PROCESS_APPROVAL",
        "required_inputs": []
        if same
        else [
            "Actual transfer mechanism and payload/container",
            "Operator reach, handling posture and lifting conditions",
            "Vendor input/output details and process hygiene",
            "Transfer scheduling where reserved aisles are shared",
        ],
        "collisions": collisions,
        "geometry_context_hash": geometry_fingerprint(c, parameters),
        "verification_scope": "PROJECTED_LOAD_AND_OPERATION_SPACE_NOT_MACHINE_OR_HUMAN_APPROVAL",
        "source_type": "demo",
        "validity_status": "unverified",
        "requires_review": True,
    }
    return row
