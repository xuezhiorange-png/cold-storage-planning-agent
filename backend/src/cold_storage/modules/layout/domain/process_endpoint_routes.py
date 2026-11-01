"""Actual device docks and bounded rectilinear inter-room logistics.

The existing swept-body planner is reused. Main aisles, docking bodies, doorway
throats and conservative turn squares have distinct witnesses. This is not a
manufacturer vehicle kinematic model, nor a simultaneous traffic simulation.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_material_geometry import (
    bounds_inside,
    motion_clear,
    rectilinear_path,
    swept_boxes,
)

NORMALS = MappingProxyType({"W": (-1, 0), "E": (1, 0), "S": (0, -1), "N": (0, 1)})


def room_rectangles(candidate: Mapping[str, Any]) -> dict[str, Any]:
    from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

    return {
        q["zone_code"]: PlacedRectangleV1(
            q["zone_code"],
            Decimal(q["bbox_mm"][0]) / 1000,
            Decimal(q["bbox_mm"][1]) / 1000,
            Decimal(q["bbox_mm"][2] - q["bbox_mm"][0]) / 1000,
            Decimal(q["bbox_mm"][3] - q["bbox_mm"][1]) / 1000,
        )
        for q in candidate["rooms"]
    }


def path_length(path: Sequence[Sequence[int]]) -> int:
    return sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(path, path[1:], strict=False))


def _box(p: Sequence[int], w: int, d: int) -> list[int]:
    return [p[0] - w // 2, p[1] - d // 2, p[0] + w - w // 2, p[1] + d - d // 2]


def shared_sweep_inside(
    e: Sequence[int], room_a: Sequence[int], room_b: Sequence[int], segment: Mapping[str, Any]
) -> bool:
    ps = [
        (round(Decimal(str(segment[k]["x"])) * 1000), round(Decimal(str(segment[k]["y"])) * 1000))
        for k in ("start", "end")
    ]
    axis = 0 if ps[0][0] == ps[1][0] else 1
    tangent = 1 - axis
    fixed = ps[0][axis]
    if (
        not min(ps[0][tangent], ps[1][tangent])
        <= e[tangent]
        < e[tangent + 2]
        <= max(ps[0][tangent], ps[1][tangent])
    ):
        return False
    first = list(e)
    second = list(e)
    first[axis + 2] = fixed
    second[axis] = fixed
    low, high = (room_a, room_b) if room_a[axis] < fixed else (room_b, room_a)
    return bounds_inside(first, low) and bounds_inside(second, high)


class ProcessRoutePlanner:
    """One run-local equipment/obstacle index; no historic layout access or Solve."""

    def __init__(
        self,
        candidate: Mapping[str, Any],
        parameters: Mapping[str, Any],
        wall_boxes: Sequence[Sequence[int]] = (),
    ) -> None:
        self.candidate = candidate
        self.parameters = parameters
        self.rooms = {q["zone_code"]: q["bbox_mm"] for q in candidate["rooms"]}
        self.items = {q["id"]: q for q in candidate["equipment"]["items"]}
        self.extra = list(candidate["equipment"].get("process_operator_zones", []))
        for layout in candidate["equipment"]["layouts"].values():
            self.extra.extend(layout.get("operator_positions", []))
        self.columns = candidate["original_building"]["columns"]
        self.wall_boxes = list(wall_boxes)
        self.endpoints: dict[str, dict[str, Any]] = {}
        self.routes: list[dict[str, Any]] = []
        self._cache: dict[tuple[Any, ...], tuple[list[tuple[int, int]], int]] = {}

    def endpoint(
        self, object_id: str, role: str, face: str, carrier: str, *, offset_tangent: int = 0
    ) -> str:
        q = self.items[object_id]
        b = q["bbox_mm"]
        n = NORMALS[face]
        spec = self.parameters["carriers"][carrier]
        is_pallet = carrier != "CARTON_CARRY" and (
            "pallet" in q["kind"] or q["kind"] in ("raw_crate_handoff", "precooling_buffer")
        )
        centre = [(b[0] + b[2]) // 2, (b[1] + b[3]) // 2]
        contact = [
            b[0] if face == "W" else b[2] if face == "E" else centre[0] + offset_tangent,
            b[1] if face == "S" else b[3] if face == "N" else centre[1] + offset_tangent,
        ]
        if is_pallet:
            offset = (spec["normal_mm"] - spec["load_normal_mm"]) // 2
            pose = [centre[i] + n[i] * offset for i in range(2)]
            tangent_size = (b[3] - b[1]) if n[0] else (b[2] - b[0])
            normal_size = (b[2] - b[0]) if n[0] else (b[3] - b[1])
            compatible = (
                normal_size == spec["load_normal_mm"] and tangent_size <= spec["tangent_mm"]
            )
        else:
            pose = [contact[i] + n[i] * (spec["normal_mm"] // 2 + 50) for i in range(2)]
            compatible = True
        identity = object_id + ":" + role
        row = {
            "id": identity,
            "object_id": object_id,
            "room": q["room"],
            "role": role,
            "face": face,
            "normal": list(n),
            "contact_mm": contact,
            "dock_reference_mm": pose,
            "carrier": carrier,
            "carried_pallet": is_pallet,
            "load_dimensions_compatible": compatible,
            "interface_basis": "DESIGN_ASSUMPTION_NOT_VENDOR_CONFIRMED",
            "object_bbox_mm": list(b),
            "source_type": "demo",
            "validity_status": "unverified",
            "requires_review": True,
        }
        self.endpoints[identity] = row
        return identity

    def obstacles(self, room: str, carried: set[str]) -> list[dict[str, Any]]:
        return [
            q
            for q in [*self.items.values(), *self.extra]
            if q["room"] == room and q["id"] not in carried
        ] + [
            *self.columns,
            *({"id": f"WALL-{i}", "bbox_mm": b} for i, b in enumerate(self.wall_boxes)),
        ]

    def _path(
        self,
        room: str,
        a: Sequence[int],
        b: Sequence[int],
        blocked: list[dict[str, Any]],
        width: int,
    ) -> tuple[list[tuple[int, int]], int]:
        boxes = [q["bbox_mm"] for q in blocked]
        key = (
            room,
            tuple(a),
            tuple(b),
            width,
            tuple((q["id"], tuple(q["bbox_mm"])) for q in blocked),
        )
        if key not in self._cache:
            aisles = self.candidate["equipment"]["layouts"][room]["service_corridors"]
            waypoints = [
                ((q["bbox_mm"][0] + q["bbox_mm"][2]) // 2, (q["bbox_mm"][1] + q["bbox_mm"][3]) // 2)
                for q in aisles
            ]
            self._cache[key] = rectilinear_path(
                (a[0], a[1]),
                (b[0], b[1]),
                self.rooms[room],
                boxes,
                width,
                width,
                node_budget=int(self.parameters["routing_node_budget"]),
                waypoints=waypoints,
            )
        return self._cache[key]

    def _dock(
        self, endpoint: Mapping[str, Any], blocked: list[dict[str, Any]], main: int
    ) -> dict[str, Any]:
        spec = self.parameters["carriers"][endpoint["carrier"]]
        n = endpoint["normal"]
        pose = tuple(endpoint["dock_reference_mm"])
        room = endpoint["room"]
        w, d = (
            (spec["normal_mm"], spec["tangent_mm"])
            if n[0]
            else (spec["tangent_mm"], spec["normal_mm"])
        )
        turn = 2 * math.ceil(math.hypot(w, d) / 2)
        boxes = [q["bbox_mm"] for q in blocked]
        clear = self.rooms[room]
        if not endpoint["load_dimensions_compatible"]:
            return {"status": "LOAD_ORIENTATION_NOT_SUPPORTED", "centerline_mm": []}
        trials = []
        owner = self.items[endpoint["object_id"]]
        if endpoint["role"] == "BLANK-IN" and owner.get("magazine_face"):
            # Explicit 1800mm operation bay, then the unchanged 2500mm middle aisle.
            cases = sorted(
                (q for q in self.items.values() if q.get("magazine_face")), key=lambda q: q["id"]
            )
            bay_x = (cases[0]["bbox_mm"][2] + cases[1]["bbox_mm"][0]) // 2
            aisle = next(
                q
                for q in self.candidate["equipment"]["layouts"][room]["service_corridors"]
                if q["id"] == "CASE-MIDDLE"
            )["bbox_mm"]
            trials.append([pose, (bay_x, pose[1]), (bay_x, (aisle[1] + aisle[3]) // 2)])
        else:
            distances = {
                0,
                100,
                250,
                500,
                750,
                1000,
                1250,
                1500,
                1750,
                2000,
                2500,
                3000,
                4000,
                5000,
            }
            axis = 0 if n[0] else 1
            for bounds in [clear, *boxes]:
                for edge in (bounds[axis], bounds[axis + 2]):
                    for sign in (-1, 1):
                        for epsilon in (0, 1):
                            value = (edge + sign * (main // 2 + epsilon) - pose[axis]) * n[axis]
                            if 0 <= value <= 8000:
                                distances.add(value)
            for dist in sorted(distances):
                trials.append([pose, (pose[0] + n[0] * dist, pose[1] + n[1] * dist)])
        failed = []
        for path in trials:
            dock_segments = []
            for a, b in zip(path, path[1:], strict=False):
                # Rotations take place inside the circumscribed turn square.
                # The following segment uses the newly oriented rectangle.
                parallel = (a[0] == b[0]) == bool(n[1])
                sw, sd = (w, d) if parallel or a == b else (d, w)
                dock_segments.append(
                    {
                        "centerline_mm": [list(a), list(b)],
                        "body_mm": [sw, sd],
                        "swept_bbox_mm": [list(e) for e in swept_boxes([a, b], sw, sd)],
                    }
                )
            if not all(
                motion_clear(s["centerline_mm"], clear, boxes, *s["body_mm"]) for s in dock_segments
            ):
                failed.append("ORIENTED_DOCK_SWEEP_BLOCKED")
                continue
            turns = [
                _box(path[i], turn, turn)
                for i in range(1, len(path) - 1)
                if path[i - 1] != path[i] and path[i] != path[i + 1]
            ]
            if any(
                not bounds_inside(b, clear) or any(positive_intersection(b, o) for o in boxes)
                for b in turns
            ):
                failed.append("OPERATION_BAY_TURN_BLOCKED")
                continue
            end = _box(path[-1], main, main)
            if not bounds_inside(end, clear) or any(positive_intersection(end, o) for o in boxes):
                failed.append("MAIN_AISLE_STAGING_BLOCKED")
                continue
            return {
                "status": "DOCK_AND_TURN_VERIFIED",
                "centerline_mm": [list(p) for p in path],
                "oriented_body_mm": [w, d],
                "segments": dock_segments,
                "swept_bbox_mm": [e for s in dock_segments for e in s["swept_bbox_mm"]],
                "turn_square_mm": turn,
                "turn_envelopes_mm": turns,
                "main_staging_square_mm": end,
                "checked_candidates": len(failed) + 1,
            }
        return {
            "status": "BOUNDED_DOCK_NOT_FOUND",
            "centerline_mm": [],
            "checked_candidates": len(trials),
            "reasons": sorted(set(failed)),
        }

    def _room_chain(
        self, source: str, target: str
    ) -> list[tuple[str, str, Mapping[str, Any], str]] | None:
        queue: deque[tuple[str, list[tuple[str, str, Mapping[str, Any], str]]]] = deque(
            [(source, [])]
        )
        seen = {source}
        while queue:
            room, chain = queue.popleft()
            if room == target:
                return chain
            for row in self.candidate["access_results"]:
                if row.get("status") != "PASS" or row.get("flow_kind") in ("PEOPLE", "TRUCK"):
                    continue
                a, b = row["from_ref"], row["to_ref"]
                if room not in (a, b):
                    continue
                other = b if room == a else a
                if other in self.rooms and other not in seen:
                    seen.add(other)
                    queue.append(
                        (other, [*chain, (room, other, row, "from" if room == a else "to")])
                    )
        return None

    def _contact_transfer(self, endpoint: Mapping[str, Any], carried: set[str]) -> dict[str, Any]:
        """Register load-to-machine contact separately from the carrier centre."""
        q = self.items[endpoint["object_id"]]
        spec = self.parameters["carriers"][endpoint["carrier"]]
        n = endpoint["normal"]
        pose = endpoint["dock_reference_mm"]
        load_centre = [
            pose[i] - n[i] * (spec["normal_mm"] - spec["load_normal_mm"]) // 2 for i in range(2)
        ]
        if endpoint["carried_pallet"]:
            centre = [
                (q["bbox_mm"][0] + q["bbox_mm"][2]) // 2,
                (q["bbox_mm"][1] + q["bbox_mm"][3]) // 2,
            ]
            return {
                "kind": "PALLET_BODY_PICK_OR_PLACE",
                "object_id": q["id"],
                "load_centre_mm": load_centre,
                "actual_pallet_bbox_mm": q["bbox_mm"],
                "status": "BOUND_TO_ACTUAL_LOAD"
                if centre == load_centre
                else "LOAD_OFFSET_MISMATCH",
            }
        normal, tangent = (
            self.parameters["carton_projection_mm"]
            if endpoint["carrier"] == "CARTON_CARRY"
            else self.parameters["pallet_mm"]
        )
        width, depth = (normal, tangent) if n[0] else (tangent, normal)
        path = [endpoint["contact_mm"], load_centre]
        obs = self.obstacles(endpoint["room"], carried | {q["id"]})
        clear = motion_clear(
            path, self.rooms[endpoint["room"]], [o["bbox_mm"] for o in obs], width, depth
        )
        return {
            "kind": "REGISTERED_MANUAL_LOAD_HANDOFF",
            "object_id": q["id"],
            "centerline_mm": path,
            "load_projection_mm": [width, depth],
            "swept_bbox_mm": [list(b) for b in swept_boxes(path, width, depth)],
            "owner_body_exception": q["id"],
            "status": "CONTACT_SWEEP_VERIFIED" if clear else "CONTACT_SWEEP_BLOCKED",
            "vendor_mouth_and_manual_handling": "INPUT_REQUIRED",
        }

    def route(self, source_id: str, target_id: str, identity: str, purpose: str) -> dict[str, Any]:
        source = self.endpoints[source_id]
        target = self.endpoints[target_id]
        if source["carrier"] != target["carrier"]:
            raise ValueError("CARRIER_INTERFACE_MISMATCH")
        carrier = source["carrier"]
        spec = self.parameters["carriers"][carrier]
        turn = 2 * math.ceil(math.hypot(spec["tangent_mm"], spec["normal_mm"]) / 2)
        main = max(int(self.parameters["main_aisle_mm"]), turn)
        carried = {q["object_id"] for q in (source, target) if q["carried_pallet"]}
        all_blocked = {room: self.obstacles(room, carried) for room in self.rooms}
        sd = self._dock(source, all_blocked[source["room"]], main)
        td = self._dock(target, all_blocked[target["room"]], main)
        row = {
            "id": identity,
            "purpose": purpose,
            "source_endpoint": source_id,
            "target_endpoint": target_id,
            "source_object": source["object_id"],
            "target_object": target["object_id"],
            "carrier": carrier,
            "main_reserved_width_mm": main,
            "turn_square_mm": turn,
            "load_state": {
                "carried_source_or_empty_reserved_destination": sorted(carried),
                "all_other_pallet_positions_occupied": True,
            },
            "source_dock": sd,
            "target_dock": td,
            "segments": [],
            "portal_crossings": [],
            "centerline_mm": [],
            "length_mm": 0,
            "status": "BOUNDED_PATH_NOT_FOUND",
            "vehicle_kinematics": "INPUT_REQUIRED",
            "simultaneous_traffic": "NOT_EVALUATED",
            "source_type": "demo",
            "validity_status": "unverified",
            "requires_review": True,
        }
        row["trajectory_reference"] = (
            "CARRIER_REFERENCE; offset load/contact transfers recorded separately"
        )
        contacts = [self._contact_transfer(e, carried) for e in (source, target)]
        row["endpoint_contact_transfers"] = contacts
        if any(
            q["status"] not in ("BOUND_TO_ACTUAL_LOAD", "CONTACT_SWEEP_VERIFIED") for q in contacts
        ):
            row["failure"] = "ACTUAL_DEVICE_CONTACT_BLOCKED"
            self.routes.append(row)
            return row
        if sd["status"] != "DOCK_AND_TURN_VERIFIED" or td["status"] != "DOCK_AND_TURN_VERIFIED":
            row["failure"] = (
                "SOURCE_DOCK" if sd["status"] != "DOCK_AND_TURN_VERIFIED" else "TARGET_DOCK"
            )
            self.routes.append(row)
            return row
        chain = self._room_chain(source["room"], target["room"])
        if chain is None:
            row["failure"] = "NO_EXISTING_MATERIAL_PORTAL_CHAIN"
            self.routes.append(row)
            return row
        current = sd["centerline_mm"][-1]
        room = source["room"]
        segments: list[dict[str, Any]] = []
        from cold_storage.modules.layout.domain.autonomous_process_routes import _inward

        rr = room_rectangles(self.candidate)
        for fr, to, access, side in chain:
            pf = access["portal_" + side]
            pt = access["portal_" + ("to" if side == "from" else "from")]
            a = _inward(pf, rr[fr], main // 2)
            b = _inward(pt, rr[to], main // 2)
            path, nodes = self._path(fr, current, a, all_blocked[fr], main)
            segments.append(
                {
                    "kind": "ROOM_MAIN_AISLE",
                    "room": fr,
                    "centerline_mm": [list(p) for p in path],
                    "reserved_width_mm": main,
                    "nodes": nodes,
                    "checked_obstacle_ids": [q["id"] for q in all_blocked[fr]],
                }
            )
            if not path:
                row["failure"] = "ROOM_PATH:" + fr
                break
            portal_width = round(Decimal(str(pf["clear_width_m"])) * 1000)
            throat = max(turn, spec["tangent_mm"])
            ca = pf["segment"]
            cb = pt["segment"]
            if ca != cb or a[0] != b[0] and a[1] != b[1] or portal_width < throat:
                row["failure"] = "PORTAL_THROAT_OR_NON_SHARED_ROUTE_NOT_SUPPORTED"
                break
            # Straight throat is contained in the union of THESE two adjoining
            # rooms. Its tangential extent stays within the actual doorway.
            boxes = [q["bbox_mm"] for q in all_blocked[fr] if q["id"] not in carried]
            boxes += [q["bbox_mm"] for q in all_blocked[to] if q["id"] not in carried]
            envelopes = swept_boxes([a, b], throat, throat)
            if any(
                not shared_sweep_inside(e, self.rooms[fr], self.rooms[to], ca)
                or any(positive_intersection(e, o) for o in boxes)
                for e in envelopes
            ):
                row["failure"] = "PORTAL_SWEEP_BLOCKED"
                break
            crossing = {
                "kind": "REAL_SHARED_PORTAL",
                "requirement_identity": access["requirement_identity"],
                "portal_from_identity": pf["identity"],
                "portal_to_identity": pt["identity"],
                "portal_segment": ca,
                "clear_width_mm": portal_width,
                "throat_envelope_mm": throat,
                "centerline_mm": [list(a), list(b)],
                "swept_bbox_mm": [list(e) for e in envelopes],
                "from_room": fr,
                "to_room": to,
                "turn_in_doorway": False,
            }
            segments.append(crossing)
            row["portal_crossings"].append(crossing)
            current = b
            room = to
        else:
            path, nodes = self._path(
                room, current, td["centerline_mm"][-1], all_blocked[room], main
            )
            segments.append(
                {
                    "kind": "ROOM_MAIN_AISLE",
                    "room": room,
                    "centerline_mm": [list(p) for p in path],
                    "reserved_width_mm": main,
                    "nodes": nodes,
                    "checked_obstacle_ids": [q["id"] for q in all_blocked[room]],
                }
            )
            if path:
                row["status"] = "CONDITIONAL_DEVICE_ROUTE_VERIFIED"
            else:
                row["failure"] = "ROOM_PATH:" + room
        row["segments"] = segments
        if row["status"] == "CONDITIONAL_DEVICE_ROUTE_VERIFIED":
            points = [*sd["centerline_mm"]]
            for seg in segments:
                points.extend(seg["centerline_mm"])
            points.extend(reversed(td["centerline_mm"]))
            row["centerline_mm"] = [
                list(p) for i, p in enumerate(points) if i == 0 or p != points[i - 1]
            ]
            row["length_mm"] = path_length(row["centerline_mm"])
            row["witness_hash"] = canonical_hash(row)
        self.routes.append(row)
        return row

    def handoff(
        self, source_object: str, target_object: str, identity: str, *, internal: bool = False
    ) -> dict[str, Any]:
        """Measured carton transfer at declared machine mouths, not room centres.

        Only these two named bodies may occupy the source/target throat. The
        segment inside a machine is explicitly an unverified internal transfer.
        """
        a = self.items[source_object]
        b = self.items[target_object]
        x = a["bbox_mm"][0] if internal else a["bbox_mm"][2]
        z = b["bbox_mm"][2] if internal else b["bbox_mm"][0]
        y = (a["bbox_mm"][1] + a["bbox_mm"][3]) // 2
        v = (b["bbox_mm"][1] + b["bbox_mm"][3]) // 2
        path = [(x, y), (z, v)]
        for obj, face in ((a, "W" if internal else "E"), (b, "E" if internal else "W")):
            ident = obj["id"] + ":" + face
            contact = [
                obj["bbox_mm"][0] if face == "W" else obj["bbox_mm"][2],
                (obj["bbox_mm"][1] + obj["bbox_mm"][3]) // 2,
            ]
            self.endpoints[ident] = {
                "id": ident,
                "object_id": obj["id"],
                "room": obj["room"],
                "role": "DECLARED_INTERNAL_CARTON_MOUTH",
                "face": face,
                "normal": list(NORMALS[face]),
                "contact_mm": contact,
                "object_bbox_mm": obj["bbox_mm"],
                "interface_basis": "DESIGN_ASSUMPTION_NOT_VENDOR_CONFIRMED",
                "manufacturer_mouth_clearance_mm": None,
                "source_type": "demo",
                "validity_status": "unverified",
                "requires_review": True,
            }
        excluded = {source_object, target_object}
        obstacles = self.obstacles(a["room"], excluded)
        carton_normal, carton_tangent = self.parameters["carton_projection_mm"]
        envelopes = [list(e) for e in swept_boxes(path, carton_normal, carton_tangent)]
        if internal:
            own = a["bbox_mm"]
            envelopes = [[max(e[0], own[0]), e[1], min(e[2], own[2]), e[3]] for e in envelopes]
        clear = (not internal or all(bounds_inside(e, a["bbox_mm"]) for e in envelopes)) and (
            a["room"] == b["room"]
            and y == v
            and all(
                bounds_inside(e, self.rooms[a["room"]])
                and not any(positive_intersection(e, q["bbox_mm"]) for q in obstacles)
                for e in envelopes
            )
        )
        row = {
            "id": identity,
            "purpose": "CARTON_MACHINE_INTERNAL" if internal else "CARTON_SHORT_HANDOFF",
            "source_object": source_object,
            "target_object": target_object,
            "source_endpoint": source_object + ":E" if not internal else source_object + ":W",
            "target_endpoint": target_object + (":E" if internal else ":W"),
            "centerline_mm": [list(p) for p in path] if clear else [],
            "length_mm": path_length(path) if clear else 0,
            "status": "CONDITIONAL_DEVICE_ROUTE_VERIFIED" if clear else "HANDOFF_COLLISION",
            "segments": [
                {
                    "kind": "REGISTERED_OWNED_MACHINE_THROAT"
                    if not internal
                    else "OWNED_MACHINE_INTERNAL_TRANSFER",
                    "owner_body_exceptions": sorted(excluded),
                    "centerline_mm": [list(p) for p in path],
                    "swept_bbox_mm": envelopes,
                    "internal_projection_clipped_at_registered_machine_mouths": internal,
                }
            ],
            "vendor_internal_transport": "INPUT_REQUIRED",
            "carton_projection_mm": [carton_normal, carton_tangent],
            "source_type": "demo",
            "validity_status": "unverified",
            "requires_review": True,
        }
        self.routes.append(row)
        return row
