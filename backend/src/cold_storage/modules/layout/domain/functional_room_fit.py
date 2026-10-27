"""R11 conditional room-use witnesses, independent of P1 and layout acceptance.

No placement search, engineering defaults, source approval, or solver constraints.
All dimensions are explicit integer millimetres; a rejected witness is not proof
that every possible arrangement in the room is impossible.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Any, Literal

from cold_storage.modules.layout.domain.access_routing import _path_envelopes

VERSION = "functional-room-fit-r11@1.0.0"
STATES = ("USE", "SHIFT_CHANGE", "CLEANING", "MAINTENANCE")
BODY_ROLES = frozenset({"LOCKER", "BENCH", "DESK", "STORAGE", "EQUIPMENT", "PARTITION"})
SPACE_ROLES = frozenset(
    {"PERSON", "CHAIR", "OPERATION", "MAINTENANCE", "INFEED", "OUTFEED", "BUFFER"}
)
ROLES = BODY_ROLES | SPACE_ROLES | {"AISLE", "DOOR_OPERATION", "CLEAN", "UNCLEAN"}
COMMON = MappingProxyType(
    {
        "finished_clear_bounds_mm": "mm",
        "clear_height_mm": "mm",
        "aisle_width_mm": "mm",
        "door_operation": "enum",
        "door_operation_envelopes_mm": "mm",
        "cleaning_maintenance_basis": "text",
    }
)
REQUIRED = MappingProxyType(
    {
        k: MappingProxyType(v)
        for k, v in {
            "changing_room": {
                "simultaneous_users": "people",
                "shift_locker_counts": "lockers",
                "shift_change_policy": "enum",
                "locker_model": "text",
                "locker_internal_separation_available": "boolean",
                "locker_dimensions_mm": "mm",
                "locker_arrangement": "enum",
                "locker_front_clearance_mm": "mm",
                "person_space_mm": "mm",
                "bench_count": "count",
                "bench_dimensions_mm": "mm",
                "bench_operation_mm": "mm",
                "internal_clothing_separation": "boolean",
                "clean_separation": "enum",
            },
            "office": {
                "staff_count": "people",
                "desk_dimensions_mm": "mm",
                "chair_movement_mm": "mm",
                "storage_count": "count",
                "storage_dimensions_mm": "mm",
                "necessary_functions": "text",
            },
            "coating_room": {
                "process_type": "enum",
                "equipment_model": "text",
                "equipment_count": "count",
                "equipment_dimensions_mm": "mm",
                "operating_clearances_mm": "mm",
                "maintenance_clearances_mm": "mm",
                "infeed_space_mm": "mm",
                "outfeed_space_mm": "mm",
                "buffer_space_mm": "mm",
                "effective_capacity_basis": "text",
                "logistics_direction_basis": "text",
                "process_portal_roles": "mapping",
                "equipment_flow_faces": "mapping",
            },
        }.items()
    }
)


@dataclass(frozen=True)
class BasisValue:
    """Application-reviewed design datum, NOT an authorization/approval token.

    Requests contain references only. The embedding application supplies this
    catalogue after source/applicability review; a JSON label cannot approve it.
    """

    value: Any
    unit: str
    source_label: Literal["OWNER_CONFIRMED", "ENGINEERING_DERIVED"]
    reference: str
    scope_id: str
    field_name: str


Rect = tuple[int, int, int, int]


def integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("EXPLICIT_INTEGER_REQUIRED")
    return value


def rectangle(value: Any) -> Rect:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("RECTANGLE_REQUIRED")
    x, y, r, t = (integer(v) for v in value)
    if x >= r or y >= t:
        raise ValueError("POSITIVE_RECTANGLE_REQUIRED")
    return x, y, r, t


def area(r: Rect) -> int:
    return (r[2] - r[0]) * (r[3] - r[1])


def intersection(a: Rect, b: Rect) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def covered(target: Rect, cover: Sequence[Rect]) -> bool:
    """Exact rectangle-union coverage, sweeping x slabs and merged y intervals."""
    xs = sorted(
        {
            target[0],
            target[2],
            *(x for r in cover for x in (r[0], r[2]) if target[0] < x < target[2]),
        }
    )
    total = 0
    for x0, x1 in zip(xs, xs[1:], strict=False):
        intervals = sorted(
            (max(target[1], r[1]), min(target[3], r[3]))
            for r in cover
            if r[0] <= x0 and x1 <= r[2] and max(target[1], r[1]) < min(target[3], r[3])
        )
        end = target[1]
        length = 0
        for lo, hi in intervals:
            length += max(0, hi - max(lo, end))
            end = max(end, hi)
        total += (x1 - x0) * length
    return total == area(target)


def dimensions(value: Any, count: int = 3) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError("EXPLICIT_DIMENSIONS_REQUIRED")
    return tuple(integer(v, 1) for v in value)


def connected(a: Rect, b: Rect, clear_width: int) -> bool:
    """A positive-area overlap or a shared edge of explicitly required width."""
    ox = min(a[2], b[2]) - max(a[0], b[0])
    oy = min(a[3], b[3]) - max(a[1], b[1])
    horizontal = a[2] - a[0] >= a[3] - a[1] and b[2] - b[0] >= b[3] - b[1]
    vertical = a[3] - a[1] >= a[2] - a[0] and b[3] - b[1] >= b[2] - b[0]
    return (
        (ox >= clear_width and oy >= clear_width)
        or (horizontal and ox > 0 and oy >= clear_width)
        or (vertical and oy > 0 and ox >= clear_width)
        or ((a[2] == b[0] or b[2] == a[0]) and min(a[3], b[3]) - max(a[1], b[1]) >= clear_width)
        or ((a[3] == b[1] or b[3] == a[1]) and min(a[2], b[2]) - max(a[0], b[0]) >= clear_width)
    )


def clearance_ring(body: Rect, amounts: Sequence[int]) -> list[Rect]:
    left, right, bottom, top = (integer(v) for v in amounts)
    x, y, r, t = body
    result = []
    if left:
        result.append((x - left, y, x, t))
    if right:
        result.append((r, y, r + right, t))
    if bottom:
        result.append((x - left, y - bottom, r + right, y))
    if top:
        result.append((x - left, t, r + right, t + top))
    return result


def evaluate_functional_room(
    room: Mapping[str, Any],
    field_refs: Mapping[str, str] | None = None,
    witness: Mapping[str, Any] | None = None,
    *,
    reviewed_basis: Mapping[str, BasisValue] | None = None,
) -> dict[str, Any]:
    """Validate a supplied physical witness under explicit, scoped design inputs.

    CONDITIONAL_FIT is a geometric/capacity result, never professional or project
    approval. Missing inputs and unavailable source review fail closed.
    """
    result: dict[str, Any] = dict(
        version=VERSION,
        scope_id=room.get("scope_id"),
        room_code=room.get("room_code"),
        functional_status="INPUT_REQUIRED",
        source_label="INPUT_REQUIRED",
        engineering_approval=False,
        modifies_p1=False,
        modifies_engineering_acceptance=False,
        native_solves=0,
        units="integer mm; area mm2",
        missing_inputs=[],
        conflicts=[],
        input_facts={},
        state_results={},
        assumptions=["Supplied arrangement only; no global room infeasibility proof"],
        warnings=["Source review and hygiene/fire/accessibility compliance remain separate"],
        formulas=[
            "A=W*D",
            "locker_count=sum(distinct shift locker allocations)",
            "full_width_route=original P2 corridor envelopes",
            "exact rectangle-union coverage",
        ],
    )
    refs, basis = field_refs or {}, reviewed_basis or {}
    try:
        zone = room["room_code"]
        if zone not in REQUIRED:
            raise ValueError("UNSUPPORTED_FUNCTIONAL_ROOM")
        bounds = rectangle(room["local_bounds_mm"])
        result["room_area_mm2"] = area(bounds)
        demand = integer(room["p1_required_area_mm2"], 1)
        width, depth = bounds[2] - bounds[0], bounds[3] - bounds[1]
        ratio = Fraction(max(width, depth), min(width, depth))
        excess = Fraction(area(bounds), demand) - 1
        percent = Decimal(excess.numerator) * 100 / Decimal(excess.denominator)
        result["physical_facts"] = dict(
            width_m=str(Decimal(width) / 1000),
            depth_m=str(Decimal(depth) / 1000),
            area_m2=str(Decimal(area(bounds)) / 1_000_000),
            required_area_m2=str(Decimal(demand) / 1_000_000),
            aspect_ratio_exact=str(ratio),
            aspect_ratio_display=f"{Decimal(ratio.numerator) / Decimal(ratio.denominator):.6f}",
            overallocation_ratio_exact=str(excess),
            overallocation_percent_display=f"{percent:.4f}",
            source_label="ENGINEERING_DERIVED",
        )
        result["p1_area_status"] = "AREA_SATISFIED" if area(bounds) >= demand else "AREA_SHORTFALL"
        # Existing geometry/Access acceptance is an independent input observation.
        result["original_engineering_status"] = room.get(
            "original_engineering_status", "NOT_EVALUATED"
        )
        values: dict[str, Any] = {}
        if not room.get("portals"):
            result["missing_inputs"].append("actual_room_portal")
        for name, unit in (COMMON | REQUIRED[zone]).items():
            datum = basis.get(refs.get(name, ""))
            if (
                datum is None
                or datum.value is None
                or not datum.reference.strip()
                or datum.scope_id != room["scope_id"]
                or datum.field_name != name
                or datum.unit != unit
                or datum.source_label not in {"OWNER_CONFIRMED", "ENGINEERING_DERIVED"}
            ):
                result["missing_inputs"].append(name)
            else:
                values[name] = datum.value
                result["input_facts"][name] = dict(
                    value=datum.value,
                    unit=unit,
                    source_label=datum.source_label,
                    reference=datum.reference,
                )
        if witness is None:
            result["missing_inputs"].append("explicit_layout_witness")
        if result["missing_inputs"]:
            return result
        assert witness is not None
        clear = rectangle(values["finished_clear_bounds_mm"])
        if not covered(clear, [bounds]):
            raise ValueError("FINISHED_CLEAR_BOUNDS_OUTSIDE_PHYSICAL_ROOM")
        height = integer(values["clear_height_mm"], 1)
        aisle_width = integer(values["aisle_width_mm"], 1)
        if values["door_operation"] not in {"HINGED", "SLIDING", "OPEN_PORTAL"}:
            raise ValueError("DOOR_OPERATION_BASIS_REQUIRED")
        if not isinstance(values["door_operation_envelopes_mm"], Mapping):
            raise ValueError("REVIEWED_DOOR_ENVELOPE_MAPPING_REQUIRED")
        if (
            not isinstance(values["cleaning_maintenance_basis"], str)
            or not values["cleaning_maintenance_basis"].strip()
        ):
            raise ValueError("CLEANING_MAINTENANCE_BASIS_REQUIRED")
        components = witness.get("components", [])
        routes = witness.get("routes", [])
        if not components or len(components) > 256 or len(routes) > 64:
            raise ValueError("BOUNDED_EXPLICIT_WITNESS_REQUIRED")
        seen: set[str] = set()
        parsed = []
        for item in components:
            if (
                not isinstance(item["id"], str)
                or not item["id"]
                or item["id"] in seen
                or item["role"] not in ROLES
            ):
                raise ValueError("DUPLICATE_OR_UNKNOWN_COMPONENT")
            seen.add(item["id"])
            active = item["states"]
            if not active or len(set(active)) != len(active) or not set(active) <= set(STATES):
                raise ValueError("EXPLICIT_OPERATION_STATES_REQUIRED")
            if item["role"] in BODY_ROLES and set(active) != set(STATES):
                raise ValueError("BODY_CANNOT_DISAPPEAR_BETWEEN_STATES")
            allowed_bodies = {
                "changing_room": {"LOCKER", "BENCH"},
                "office": {"DESK", "STORAGE"},
                "coating_room": {"EQUIPMENT"},
            }
            if item["role"] in BODY_ROLES and item["role"] not in allowed_bodies[zone]:
                result["missing_inputs"].append("reviewed_extra_body_specification:" + item["id"])
            parsed.append(dict(item, rect=rectangle(item["bounds_mm"])))
        portals = room.get("portals", [])
        if not portals:
            result["missing_inputs"].append("actual_room_portal")
        for portal in portals:
            a, b = portal["segment_mm"]
            x0, y0, x1, y1 = bounds
            if not (
                (
                    a[0] == b[0]
                    and a[0] in (x0, x1)
                    and y0 <= min(a[1], b[1]) < max(a[1], b[1]) <= y1
                )
                or (
                    a[1] == b[1]
                    and a[1] in (y0, y1)
                    and x0 <= min(a[0], b[0]) < max(a[0], b[0]) <= x1
                )
            ):
                raise ValueError("PORTAL_NOT_ON_PHYSICAL_ROOM_BOUNDARY")
            opening = abs(a[0] - b[0]) + abs(a[1] - b[1])
            if integer(portal["clear_width_mm"], 1) > opening:
                raise ValueError("PORTAL_CLEAR_WIDTH_EXCEEDS_SEGMENT")
            operations = [
                c
                for c in parsed
                if c["role"] == "DOOR_OPERATION" and c.get("portal_id") == portal["id"]
            ]
            expected_operations = values["door_operation_envelopes_mm"].get(portal["id"])
            if expected_operations is None:
                result["missing_inputs"].append("reviewed_door_operation:" + portal["id"])
            elif sorted(rectangle(r) for r in expected_operations) != sorted(
                c["rect"] for c in operations
            ):
                raise ValueError("DOOR_OPERATION_WITNESS_DIFFERS_FROM_REVIEWED_BASIS")
            for operation in operations:
                r = operation["rect"]
                attached = (
                    a[0] == b[0]
                    and r[0] <= a[0] <= r[2]
                    and max(r[1], min(a[1], b[1])) <= min(r[3], max(a[1], b[1]))
                ) or (
                    a[1] == b[1]
                    and r[1] <= a[1] <= r[3]
                    and max(r[0], min(a[0], b[0])) <= min(r[2], max(a[0], b[0]))
                )
                if not attached:
                    raise ValueError("DOOR_OPERATION_NOT_ATTACHED_TO_ACTUAL_PORTAL")
            if (not operations and values["door_operation"] != "OPEN_PORTAL") or any(
                set(c["states"]) != set(STATES) for c in operations
            ):
                result["missing_inputs"].append("door_operation_envelope:" + portal["id"])
        conflict = result["conflicts"]

        def fail(code: str, *items: str) -> None:
            conflict.append(dict(code=code, components=list(items)))

        def bodies(role: str) -> list[dict[str, Any]]:
            return [c for c in parsed if c["role"] == role]

        specs: dict[str, tuple[int, ...]] = {}
        if zone == "changing_room":
            shifts = dimensions(values["shift_locker_counts"], 2)
            users = integer(values["simultaneous_users"], 1)
            locker = dimensions(values["locker_dimensions_mm"])
            specs["LOCKER"] = locker
            if integer(values["bench_count"]) > 0:
                specs["BENCH"] = dimensions(values["bench_dimensions_mm"])
                integer(values["bench_operation_mm"], 1)
            if values["locker_arrangement"] not in {"SINGLE_SIDE", "DOUBLE_SIDE"}:
                raise ValueError("EXPLICIT_SINGLE_OR_DOUBLE_SIDE_REQUIRED")
            if not isinstance(values["locker_model"], str) or not values["locker_model"].strip():
                result["missing_inputs"].append("locker_model")
            if (
                type(values["internal_clothing_separation"]) is not bool
                or type(values["locker_internal_separation_available"]) is not bool
            ):
                raise ValueError("EXPLICIT_LOCKER_SEPARATION_FEATURE_REQUIRED")
            if (
                values["internal_clothing_separation"]
                and not values["locker_internal_separation_available"]
            ):
                fail("REQUIRED_INTERNAL_CLOTHING_SEPARATION_UNAVAILABLE")
            for shift, required in enumerate(shifts, 1):
                if sum(c.get("shift") == shift for c in bodies("LOCKER")) < required:
                    fail("INDEPENDENT_SHIFT_LOCKERS_INSUFFICIENT", str(shift))
            if any(
                type(c.get("shift")) is not int or c["shift"] not in (1, 2)
                for c in bodies("LOCKER")
            ):
                fail("INDEPENDENT_SHIFT_LOCKER_IDENTITY_INVALID")
            if values["shift_change_policy"] not in {"NON_OVERLAPPING", "OVERLAPPING"}:
                raise ValueError("EXPLICIT_SHIFT_CHANGE_POLICY_REQUIRED")
            if users > (
                max(shifts) if values["shift_change_policy"] == "NON_OVERLAPPING" else sum(shifts)
            ):
                fail("SIMULTANEOUS_USERS_EXCEED_SHIFT_ALLOCATION")
            if len(bodies("BENCH")) < integer(values["bench_count"]):
                fail("BENCH_COUNT_INSUFFICIENT")
            fronts = {c.get("front") for c in bodies("LOCKER")}
            if values["locker_arrangement"] == "SINGLE_SIDE" and len(fronts) != 1:
                fail("SINGLE_SIDE_ARRANGEMENT_MISMATCH")
            if values["locker_arrangement"] == "DOUBLE_SIDE" and fronts not in (
                {"N", "S"},
                {"E", "W"},
            ):
                fail("DOUBLE_SIDE_ARRANGEMENT_MISMATCH")
            if values["clean_separation"] not in {"NOT_REQUIRED", "PARTITION_REQUIRED"}:
                raise ValueError("EXPLICIT_CLEAN_SEPARATION_BASIS_REQUIRED")
            if values["clean_separation"] == "PARTITION_REQUIRED":
                # Arbitrary partition/hygiene topology requires a reviewed specific design.
                result["missing_inputs"].append(
                    "reviewed_clean_unclean_partition_and_portal_design"
                )
            person = dimensions(values["person_space_mm"], 2)
            for state in ("USE", "SHIFT_CHANGE"):
                people = [c for c in bodies("PERSON") if state in c["states"]]
                if len(people) < users:
                    fail("SIMULTANEOUS_PERSON_SPACES_INSUFFICIENT", state)
                for c in people:
                    if (c["rect"][2] - c["rect"][0], c["rect"][3] - c["rect"][1]) not in (
                        person,
                        person[::-1],
                    ):
                        fail("PERSON_SPACE_DIMENSIONS_MISMATCH", c["id"])
        elif zone == "office":
            specs["DESK"] = dimensions(values["desk_dimensions_mm"])
            if integer(values["storage_count"]) > 0:
                specs["STORAGE"] = dimensions(values["storage_dimensions_mm"])
            if len(bodies("DESK")) < integer(values["staff_count"], 1) or len(
                bodies("STORAGE")
            ) < integer(values["storage_count"]):
                fail("OFFICE_FURNITURE_CAPACITY_INSUFFICIENT")
            dimensions(values["chair_movement_mm"], 2)
            if not values["necessary_functions"]:
                result["missing_inputs"].append("necessary_functions")
        else:
            if (
                values["process_type"] != "PACKAGING_BOX_FILM_SEALING"
                or not values["equipment_model"]
            ):
                raise ValueError("EXPLICIT_BOX_FILM_SEALING_EQUIPMENT_REQUIRED")
            specs["EQUIPMENT"] = dimensions(values["equipment_dimensions_mm"])
            if not isinstance(values["process_portal_roles"], Mapping) or not isinstance(
                values["equipment_flow_faces"], Mapping
            ):
                raise ValueError("REVIEWED_PROCESS_PORTAL_AND_FACE_MAPPING_REQUIRED")
            if len(bodies("EQUIPMENT")) < integer(values["equipment_count"], 1):
                fail("EQUIPMENT_COUNT_INSUFFICIENT")
            for key in ("operating_clearances_mm", "maintenance_clearances_mm"):
                if len(values[key]) != 4 or any(integer(v) < 0 for v in values[key]):
                    raise ValueError("EXPLICIT_FOUR_SIDE_CLEARANCES_REQUIRED")
            for key in ("effective_capacity_basis", "logistics_direction_basis"):
                if not values[key]:
                    result["missing_inputs"].append(key)
            for role in ("INFEED", "OUTFEED", "BUFFER"):
                dims = dimensions(values[role.lower() + "_space_mm"], 2)
                if not any(
                    c["rect"][2] - c["rect"][0] >= dims[0]
                    and c["rect"][3] - c["rect"][1] >= dims[1]
                    for c in bodies(role)
                ):
                    fail("PROCESS_SPACE_INSUFFICIENT", role)
            for role in ("INFEED", "OUTFEED"):
                portal_id = values["process_portal_roles"].get(role)
                face = values["equipment_flow_faces"].get(role)
                if portal_id not in {p["id"] for p in portals} or face not in {"N", "S", "E", "W"}:
                    result["missing_inputs"].append(role + ":actual_process_portal_and_face")
                for equipment in bodies("EQUIPMENT"):
                    a = equipment["rect"]

                    def on_face(
                        c: dict[str, Any],
                        equipment: dict[str, Any] = equipment,
                        face: Any = face,
                        a: Rect = a,
                    ) -> bool:
                        b = c["rect"]
                        return bool(
                            c.get("serves") == equipment["id"]
                            and (
                                face == "W"
                                and b[2] == a[0]
                                and min(a[3], b[3]) > max(a[1], b[1])
                                or face == "E"
                                and b[0] == a[2]
                                and min(a[3], b[3]) > max(a[1], b[1])
                                or face == "S"
                                and b[3] == a[1]
                                and min(a[2], b[2]) > max(a[0], b[0])
                                or face == "N"
                                and b[1] == a[3]
                                and min(a[2], b[2]) > max(a[0], b[0])
                            )
                        )

                    if not any(on_face(c) for c in bodies(role)):
                        fail("PROCESS_SPACE_NOT_AT_CONFIRMED_EQUIPMENT_FACE", role, equipment["id"])
        for c in parsed:
            if c["role"] in specs:
                w, d, h = specs[c["role"]]
                if (c["rect"][2] - c["rect"][0], c["rect"][3] - c["rect"][1]) not in (
                    (w, d),
                    (d, w),
                ):
                    fail("BODY_DIMENSIONS_MISMATCH", c["id"])
                if h > height:
                    fail("CLEAR_HEIGHT_INSUFFICIENT", c["id"])
        for state in STATES:
            active = [c for c in parsed if state in c["states"]]
            solids = [c for c in active if c["role"] in BODY_ROLES]
            aisles = [c["rect"] for c in active if c["role"] == "AISLE"]
            if not aisles:
                result["missing_inputs"].append(state + ":aisles")
            for c in active:
                if not covered(c["rect"], [clear]):
                    fail("COMPONENT_OUTSIDE_FINISHED_CLEAR_ROOM", state, c["id"])
                if (
                    c["role"] == "AISLE"
                    and min(c["rect"][2] - c["rect"][0], c["rect"][3] - c["rect"][1]) < aisle_width
                ):
                    fail("AISLE_WIDTH_INSUFFICIENT", state, c["id"])
                for other in solids:
                    if c is not other and intersection(c["rect"], other["rect"]):
                        fail("BODY_OR_CLEARANCE_COLLISION", state, c["id"], other["id"])
            for i, c in enumerate(active):
                if c["role"] not in {"PERSON", "CHAIR"}:
                    continue
                for other in active[i + 1 :]:
                    if other["role"] == c["role"] and intersection(c["rect"], other["rect"]):
                        fail("SIMULTANEOUS_USE_SPACES_OVERLAP", state, c["id"], other["id"])
            operation_rings: list[tuple[str, Rect]] = []
            for c in solids:
                ring: list[Rect] = []
                if c["role"] == "LOCKER":
                    amounts = [0, 0, 0, 0]
                    direction = {"W": 0, "E": 1, "S": 2, "N": 3}.get(c.get("front"))
                    if direction is None:
                        raise ValueError("LOCKER_FRONT_REQUIRED")
                    amounts[direction] = integer(values["locker_front_clearance_mm"], 1)
                    ring = clearance_ring(c["rect"], amounts)
                if c["role"] == "EQUIPMENT":
                    ring = clearance_ring(
                        c["rect"],
                        values["maintenance_clearances_mm"]
                        if state == "MAINTENANCE"
                        else values["operating_clearances_mm"],
                    )
                if c["role"] == "BENCH":
                    amounts = [0, 0, 0, 0]
                    direction = {"W": 0, "E": 1, "S": 2, "N": 3}.get(c.get("front"))
                    if direction is None:
                        raise ValueError("BENCH_FRONT_REQUIRED")
                    amounts[direction] = integer(values["bench_operation_mm"], 1)
                    ring = clearance_ring(c["rect"], amounts)
                if c["role"] == "DESK" and state == "USE":
                    chairs = [
                        a for a in active if a["role"] == "CHAIR" and a.get("serves") == c["id"]
                    ]
                    dims = dimensions(values["chair_movement_mm"], 2)
                    if not any(
                        (a["rect"][2] - a["rect"][0], a["rect"][3] - a["rect"][1])
                        in (dims, dims[::-1])
                        and connected(a["rect"], c["rect"], min(dims))
                        for a in chairs
                    ):
                        fail("DESK_CHAIR_MOVEMENT_MISSING", c["id"])
                for rect in ring:
                    operation_rings.append((c["id"], rect))
                    if not covered(rect, [clear]) or any(
                        intersection(rect, b["rect"]) for b in solids if b is not c
                    ):
                        fail("REQUIRED_OPERATION_OR_MAINTENANCE_CLEARANCE_BLOCKED", state, c["id"])
            connected_portals = set()
            route_records = []
            for route in routes:
                if state not in route["states"]:
                    continue
                points: list[tuple[int, int]] = []
                for point in route["points_mm"]:
                    if len(point) != 2:
                        raise ValueError("TWO_DIMENSIONAL_ROUTE_POINT_REQUIRED")
                    points.append((integer(point[0]), integer(point[1])))
                width = integer(route["width_mm"], 1)
                if width < aisle_width or len(points) < 2 or len(set(points)) < 2:
                    raise ValueError("REAL_FULL_WIDTH_ROUTE_REQUIRED")
                envelopes = [r.bounds_mm for r in _path_envelopes(points, width)]
                proven = []
                for portal in portals:
                    a, b = portal["segment_mm"]
                    for end in (points[0], points[-1]):
                        if (
                            (
                                a[0] == b[0] == end[0]
                                and min(a[1], b[1]) + width // 2
                                <= end[1]
                                <= max(a[1], b[1]) - (width - width // 2)
                            )
                            or (
                                a[1] == b[1] == end[1]
                                and min(a[0], b[0]) + width // 2
                                <= end[0]
                                <= max(a[0], b[0]) - (width - width // 2)
                            )
                        ) and width <= portal["clear_width_mm"]:
                            proven.append(portal["id"])
                            connected_portals.add(portal["id"])
                valid = bool(proven) and all(
                    covered(e, [clear])
                    and covered(e, aisles)
                    and not any(intersection(e, b["rect"]) for b in solids)
                    for e in envelopes
                )
                if not valid:
                    fail("PORTAL_ROUTE_BLOCKED_OR_UNPROVEN", state, route["id"])
                route_records.append(
                    dict(
                        id=route["id"],
                        valid=valid,
                        portal_ids=proven,
                        envelopes_mm=envelopes,
                        source_label="ENGINEERING_DERIVED",
                    )
                )
            for portal in portals:
                if portal["id"] not in connected_portals:
                    result["missing_inputs"].append(state + ":route_to_portal:" + portal["id"])
            # A free but disconnected furniture/locker island is not usable.
            reached = {
                i
                for i, aisle in enumerate(aisles)
                if any(
                    r["valid"] and any(intersection(aisle, e) for e in r["envelopes_mm"])
                    for r in route_records
                )
            }
            while True:
                expanded = reached | {
                    i
                    for i, aisle in enumerate(aisles)
                    if any(connected(aisle, aisles[j], aisle_width) for j in reached)
                }
                if expanded == reached:
                    break
                reached = expanded
            usable = [aisles[i] for i in reached]
            for c in active:
                if c["role"] in SPACE_ROLES and not any(
                    connected(
                        c["rect"], a, min(c["rect"][2] - c["rect"][0], c["rect"][3] - c["rect"][1])
                    )
                    for a in usable
                ):
                    fail("FUNCTIONAL_SPACE_NOT_CONNECTED_TO_PORTAL_AISLE", state, c["id"])
            for identifier, rect in operation_rings:
                if not any(
                    connected(rect, a, min(rect[2] - rect[0], rect[3] - rect[1])) for a in usable
                ):
                    fail("OPERATION_CLEARANCE_NOT_REACHABLE", state, identifier)
            result["state_results"][state] = dict(
                route_results=route_records,
                component_ids=[c["id"] for c in active],
                operation_clearance_rectangles=[
                    dict(serves=i, bounds_mm=r, source_label="ENGINEERING_DERIVED")
                    for i, r in operation_rings
                ],
                portal_reachable_aisle_count=len(reached),
            )
        result["missing_inputs"] = sorted(set(result["missing_inputs"]))
        result["functional_status"] = (
            "INPUT_REQUIRED"
            if result["missing_inputs"]
            else "CONFIGURATION_NOT_FIT"
            if conflict
            else "CONDITIONAL_FIT"
        )
        result["source_label"] = (
            "INPUT_REQUIRED" if result["missing_inputs"] else "ENGINEERING_DERIVED"
        )
        result["witness"] = dict(witness)
        result["finished_clear_bounds_mm"] = clear
        result["no_fit_proof_scope"] = "SUPPLIED_CONFIGURATION_ONLY_NOT_GLOBAL_INFEASIBILITY"
    except (KeyError, TypeError, ValueError, IndexError) as error:
        result["missing_inputs"].append(str(error))
        result["functional_status"] = "INPUT_REQUIRED"
    return result
