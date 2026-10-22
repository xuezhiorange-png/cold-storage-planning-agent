"""PackingStationModuleV1: exact, offline rectilinear diagnostics, never P1 Authority.

Input coordinates/widths are integer mm; internal half-widths use exact Fractions.
Only rectangles and orthogonal polylines with quarter-turn transforms are supported.
Source-content matching is not publisher authentication or engineering approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from typing import Any

IDENTITY = "PackingStationModuleV1"
VERSION = "packing-station-module@1.0.0"
STATES = ("NORMAL_PRODUCTION", "SHIFT_CHANGE", "CLEANING", "MAINTENANCE")
TYPES = (
    "PACKING_STATION_ENVELOPE",
    "OPERATOR_ENVELOPE",
    "MATERIAL_SUPPLY_ENVELOPE",
    "PRODUCT_OUTFEED_ENVELOPE",
    "CIRCULATION_ENVELOPE",
    "CLEANING_MAINTENANCE_ENVELOPE",
)
ROLES = {
    TYPES[0]: {"BODY"},
    TYPES[1]: {"STANDING", "REACH"},
    TYPES[2]: {"SUPPLY"},
    TYPES[3]: {"OUTFEED", "REJECT"},
    TYPES[4]: {"PERSONNEL_AISLE", "MATERIAL_AISLE", "SHARED_AISLE"},
    TYPES[5]: {"SERVICE"},
}
DIRECTIONS = {"X_POS": (1, 0), "Y_POS": (0, 1), "X_NEG": (-1, 0), "Y_NEG": (0, -1)}
Point = tuple[Fraction, Fraction]
Rect = tuple[Fraction, Fraction, Fraction, Fraction]


class InputError(ValueError):
    """Stable offline input rejection, not a production engineering error code."""


def encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def number(value: Fraction | int) -> int | str:
    q = Fraction(value)
    return q.numerator if q.denominator == 1 else f"{q.numerator}/{q.denominator}"


def integer(value: Any) -> int:
    if type(value) is not int:
        raise InputError("INTEGER_MM_REQUIRED")
    return value


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise InputError("INVALID_IDENTIFIER")
    return value


def point(value: Any) -> Point:
    if not isinstance(value, list) or len(value) != 2:
        raise InputError("TWO_INTEGER_COORDINATES_REQUIRED")
    return Fraction(integer(value[0])), Fraction(integer(value[1]))


def transform(p: Point, pose: dict[str, Any]) -> Point:
    angle = integer(pose["ROTATION_DEG"])
    if angle not in (0, 90, 180, 270):
        raise InputError("QUARTER_TURN_REQUIRED")
    x, y = p
    u, v = ((x, y), (-y, x), (-x, -y), (y, -x))[angle // 90]
    dx, dy = point(pose["TRANSLATION_MM"])
    return u + dx, v + dy


def transform_rect(raw: Any, poses: list[dict[str, Any]]) -> Rect:
    if not isinstance(raw, list) or len(raw) != 4:
        raise InputError("RECTANGLE_FOUR_INTEGERS_REQUIRED")
    x0, y0, x1, y1 = (Fraction(integer(v)) for v in raw)
    if x0 >= x1 or y0 >= y1:
        raise InputError("NON_DEGENERATE_RECTANGLE_REQUIRED")
    corners = [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]
    for pose in poses:
        corners = [transform(p, pose) for p in corners]
    return (
        min(p[0] for p in corners),
        min(p[1] for p in corners),
        max(p[0] for p in corners),
        max(p[1] for p in corners),
    )


def intersection(a: Rect, b: Rect) -> Fraction:
    return max(Fraction(0), min(a[2], b[2]) - max(a[0], b[0])) * max(
        Fraction(0), min(a[3], b[3]) - max(a[1], b[1])
    )


def touches(a: Rect, b: Rect) -> bool:
    return min(a[2], b[2]) >= max(a[0], b[0]) and min(a[3], b[3]) >= max(a[1], b[1])


def union_area(rectangles: list[Rect]) -> Fraction:
    xs = sorted({r[i] for r in rectangles for i in (0, 2)})
    result = Fraction(0)
    for x0, x1 in zip(xs, xs[1:], strict=False):
        intervals = sorted((r[1], r[3]) for r in rectangles if r[0] <= x0 < x1 <= r[2])
        length, end = Fraction(0), None
        for a, b in intervals:
            start = a if end is None else max(a, end)
            length += max(Fraction(0), b - start)
            end = b if end is None else max(end, b)
        result += (x1 - x0) * length
    return result


def covered(rect: Rect, cover: list[Rect]) -> bool:
    return union_area([*cover, rect]) == union_area(cover)


def bounds(rects: list[Rect]) -> list[int | str] | None:
    if not rects:
        return None
    return [number(f(r[i] for r in rects)) for f, i in ((min, 0), (min, 1), (max, 2), (max, 3))]


def path_envelope(points: list[Point], width: int) -> list[Rect]:
    if type(width) is not int or width <= 0 or len(points) < 2:
        raise InputError("POSITIVE_PATH_WIDTH_AND_TWO_POINTS_REQUIRED")
    half = Fraction(width, 2)
    result = []
    for a, b in zip(points, points[1:], strict=False):
        if a == b or (a[0] != b[0] and a[1] != b[1]):
            raise InputError("ORTHOGONAL_NONZERO_PATH_REQUIRED")
        result.append(
            (
                min(a[0], b[0]) - half,
                min(a[1], b[1]) - half,
                max(a[0], b[0]) + half,
                max(a[1], b[1]) + half,
            )
        )
    return result


def source_record(record: dict[str, Any], key: str, doc: dict[str, Any], root: Path) -> str:
    source_id = identifier(record["SOURCE_ID"])
    reference = doc["SOURCES"].get(source_id)
    if not isinstance(reference, dict):
        raise InputError("SOURCE_REFERENCE_REQUIRED:" + key)
    relative = Path(reference["PATH"])
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root.resolve()) or not path.is_file():
        raise InputError("LOCAL_SOURCE_OUTSIDE_EVIDENCE_ROOT_OR_MISSING")
    raw = path.read_bytes()
    if digest(raw) != reference["SHA256"]:
        raise InputError("SOURCE_CONTENT_HASH_MISMATCH:" + source_id)
    body = json.loads(raw)
    if not isinstance(body, dict) or not isinstance(body.get("FACTS"), dict):
        raise InputError("SOURCE_OBJECT_WITH_FACTS_REQUIRED")
    kind = body.get("EVIDENCE_KIND")
    if kind != reference["EVIDENCE_KIND"]:
        raise InputError("SOURCE_KIND_MISMATCH")
    required = "SYNTHETIC_TEST_GEOMETRY" if doc["MODE"] == "SYNTHETIC_TEST" else "PROJECT_INPUT"
    if kind != required or body.get("PROJECT_ID") != doc["PROJECT_ID"]:
        raise InputError("SYNTHETIC_REFERENCE_CANNOT_BE_PROJECT_EVIDENCE")
    if body.get("FACTS", {}).get(key) != record:
        raise InputError("SOURCE_FACT_DOES_NOT_BIND_RECORD:" + key)
    return "CONTENT_MATCH_ONLY_NOT_ENGINEERING_APPROVAL"


def active_states(value: Any) -> list[str]:
    if not isinstance(value, list) or not value or len(set(value)) != len(value):
        raise InputError("EXPLICIT_ACTIVE_STATES_REQUIRED")
    if any(state not in STATES for state in value):
        raise InputError("UNKNOWN_OPERATING_STATE")
    return value


def flatten(
    doc: dict[str, Any], root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    for field in (
        "COMPONENTS",
        "OPERATORS",
        "INTERFACES",
        "ROUTES",
        "INSTANCES",
        "ASSEMBLY_CIRCULATION",
        "ASSEMBLY_ROUTES",
        "SHARING_CONDITIONS",
    ):
        if not isinstance(doc.get(field), list) or any(not isinstance(v, dict) for v in doc[field]):
            raise InputError("EXPLICIT_RECORD_LIST_REQUIRED:" + field)
    if not isinstance(doc.get("SOURCES"), dict):
        raise InputError("SOURCE_OBJECT_REQUIRED")
    handover = doc.get("SHIFT_CHANGE")
    if not isinstance(handover, dict) or "DURATION_MINUTES" not in handover:
        raise InputError("EXPLICIT_SHIFT_CHANGE_INPUT_REQUIRED")
    duration = handover["DURATION_MINUTES"]
    if duration is not None and (type(duration) is not int or duration < 0):
        raise InputError("INTEGER_NONNEGATIVE_MINUTES_OR_NULL_REQUIRED")
    if doc["IDENTITY"] != IDENTITY or doc["VERSION"] != VERSION:
        raise InputError("OFFLINE_MODULE_IDENTITY_REQUIRED")
    if doc["MODE"] not in ("SYNTHETIC_TEST", "OWNER_PROJECT"):
        raise InputError("EXPLICIT_MODE_REQUIRED")
    if doc["DIMENSION_UNIT"] != "mm" or doc["COORDINATE_SYSTEM"] != "RIGHT_HANDED_XY_Y_UP":
        raise InputError("INTEGER_MM_LOCAL_CARTESIAN_REQUIRED")
    if doc["ARRANGEMENT"] not in (
        "SINGLE",
        "LINEAR_ARRANGEMENT",
        "OPPOSED_ARRANGEMENT",
        "PARALLEL_ROWS",
    ):
        raise InputError("UNKNOWN_ARRANGEMENT")
    identifier(doc["PROJECT_ID"])
    components, routes, operators = [], [], []
    world_interfaces: dict[str, Point] = {}
    station_ids: set[str] = set()
    for instance in doc["INSTANCES"]:
        station = identifier(instance["INSTANCE_ID"])
        if station in station_ids:
            raise InputError("DUPLICATE_STATION_INSTANCE")
        station_ids.add(station)
        source_record(instance, "INSTANCE:" + station, doc, root)
        pose = instance["TRANSFORM"]
        transform((Fraction(0), Fraction(0)), pose)
        local: dict[str, dict[str, Any]] = {}
        for item in doc["COMPONENTS"]:
            key = identifier(item["COMPONENT_ID"])
            if key in local:
                raise InputError("DUPLICATE_COMPONENT")
            kind = item["COMPONENT_TYPE"]
            if kind not in ROLES or item["ROLE"] not in ROLES[kind]:
                raise InputError("UNKNOWN_COMPONENT_OR_ROLE")
            if item["COORDINATE_SYSTEM"] != "STATION_LOCAL" or item["DIMENSION_UNIT"] != "mm":
                raise InputError("COMPONENT_COORDINATE_OR_UNIT_INVALID")
            if (
                item["SOURCE_VERIFICATION"] != "CONTENT_REQUIRED"
                or item["APPROVAL_STATUS"] != "NOT_PROJECT_APPROVED"
            ):
                raise InputError("CALLER_CANNOT_ASSERT_ENGINEERING_APPROVAL")
            if item["SIMULTANEITY"] != "ALL_ACTIVE_COMPONENTS_IN_STATE":
                raise InputError("EXPLICIT_SIMULTANEITY_REQUIRED")
            if item["OVERLAP_POLICY"] not in (
                "PHYSICAL_EXCLUSIVE",
                "INTERACTION_REVIEW",
                "EXPLICIT_SHARED_REVIEW",
            ):
                raise InputError("UNKNOWN_OVERLAP_POLICY")
            source_record(item, "COMPONENT:" + key, doc, root)
            states = active_states(item["ACTIVE_STATES"])
            if item["ROLE"] == "BODY" and set(states) != set(STATES):
                raise InputError("EQUIPMENT_BODY_CANNOT_DISAPPEAR_IN_NONPRODUCTION")
            if item["GEOMETRY"]["TYPE"] != "RECTANGLE":
                raise InputError("RECTANGLE_ONLY_NO_APPROXIMATE_POLYGON_BOUNDING")
            rect = transform_rect(item["GEOMETRY"]["BOUNDS_MM"], [item["TRANSFORM"], pose])
            row = {**item, "KEY": station + "/" + key, "STATION": station, "RECT": rect}
            local[key] = row
            components.append(row)
        if {r["COMPONENT_TYPE"] for r in local.values()} != set(TYPES):
            raise InputError("ALL_SIX_COMPONENT_TYPES_REQUIRED")
        if any(
            not any(
                r["COMPONENT_TYPE"] == kind and "NORMAL_PRODUCTION" in r["ACTIVE_STATES"]
                for r in local.values()
            )
            for kind in TYPES[:5]
        ):
            raise InputError("NORMAL_PRODUCTION_COMPONENT_COVERAGE_REQUIRED")
        if any(
            not any(
                r["COMPONENT_TYPE"] == TYPES[4] and state in r["ACTIVE_STATES"]
                for r in local.values()
            )
            for state in STATES
        ):
            raise InputError("CIRCULATION_REQUIRED_IN_EVERY_STATE")
        services = [r for r in local.values() if r["ROLE"] == "SERVICE"]
        if any(
            not any(s in r["ACTIVE_STATES"] for r in services) for s in ("CLEANING", "MAINTENANCE")
        ):
            raise InputError("CLEANING_AND_MAINTENANCE_GEOMETRY_REQUIRED")
        local_interfaces = {}
        interface_defs = {}
        for interface in doc["INTERFACES"]:
            key = identifier(interface["INTERFACE_ID"])
            if key in local_interfaces:
                raise InputError("DUPLICATE_INTERFACE")
            source_record(interface, "INTERFACE:" + key, doc, root)
            if interface["KIND"] not in (
                "PERSONNEL_ENTRY",
                "OPERATOR_POSITION",
                "MATERIAL_IN",
                "SUPPLY",
                "PRODUCT_OUT",
                "OUTFEED",
            ):
                raise InputError("UNKNOWN_INTERFACE_KIND")
            component = local[interface["COMPONENT_ID"]]
            allowed_roles = {
                "PERSONNEL_ENTRY": ROLES[TYPES[4]],
                "OPERATOR_POSITION": {"STANDING"},
                "MATERIAL_IN": ROLES[TYPES[4]],
                "SUPPLY": {"SUPPLY"},
                "PRODUCT_OUT": ROLES[TYPES[4]],
                "OUTFEED": {"OUTFEED", "REJECT"},
            }
            if component["ROLE"] not in allowed_roles[interface["KIND"]]:
                raise InputError("INTERFACE_KIND_COMPONENT_ROLE_MISMATCH")
            p = transform(point(interface["POINT_MM"]), pose)
            r = component["RECT"]
            if not (r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]):
                raise InputError("INTERFACE_OUTSIDE_OWN_COMPONENT")
            local_interfaces[key] = p
            interface_defs[key] = interface
            world_interfaces[station + "/" + key] = p
        local_routes = {}
        for route in doc["ROUTES"]:
            key = identifier(route["ROUTE_ID"])
            if key in local_routes:
                raise InputError("DUPLICATE_ROUTE")
            source_record(route, "ROUTE:" + key, doc, root)
            active_states(route["ACTIVE_STATES"])
            if route["FLOW_KIND"] not in ("PERSONNEL", "MATERIAL_IN", "PRODUCT_OUT"):
                raise InputError("UNKNOWN_FLOW_KIND")
            required_kinds = {
                "PERSONNEL": ("PERSONNEL_ENTRY", "OPERATOR_POSITION"),
                "MATERIAL_IN": ("MATERIAL_IN", "SUPPLY"),
                "PRODUCT_OUT": ("OUTFEED", "PRODUCT_OUT"),
            }
            actual_kinds = (
                interface_defs[route["FROM_INTERFACE"]]["KIND"],
                interface_defs[route["TO_INTERFACE"]]["KIND"],
            )
            if actual_kinds != required_kinds[route["FLOW_KIND"]]:
                raise InputError("FLOW_DIRECTION_INTERFACE_KIND_MISMATCH")
            pts = [transform(point(p), pose) for p in route["POINTS_MM"]]
            if (
                pts[0] != local_interfaces[route["FROM_INTERFACE"]]
                or pts[-1] != local_interfaces[route["TO_INTERFACE"]]
            ):
                raise InputError("ROUTE_INTERFACE_ENDPOINT_MISMATCH")
            corridor = path_envelope(pts, route["WIDTH_MM"])
            allowances = [local[k] for k in route["END_COMPONENTS"]]
            for allowed in allowances:
                permitted = (
                    {"STANDING"}
                    if route["FLOW_KIND"] == "PERSONNEL"
                    else {"SUPPLY", "OUTFEED", "REJECT"}
                )
                if allowed["ROLE"] not in permitted:
                    raise InputError("INVALID_ROUTE_TERMINAL_COVER")
            local_routes[key] = route
            routes.append(
                {
                    **route,
                    "KEY": station + "/" + key,
                    "STATION": station,
                    "POINTS": pts,
                    "RECTS": corridor,
                    "END_KEYS": [station + "/" + k for k in route["END_COMPONENTS"]],
                }
            )
        if {r["FLOW_KIND"] for r in local_routes.values()} != {
            "PERSONNEL",
            "MATERIAL_IN",
            "PRODUCT_OUT",
        }:
            raise InputError("PERSONNEL_SUPPLY_AND_OUTFEED_ROUTES_REQUIRED")
        ids = [op["OPERATOR_ID"] for op in doc["OPERATORS"]]
        if sorted(ids) != ["OPERATOR_1", "OPERATOR_2", "OPERATOR_3"]:
            raise InputError("EXACTLY_THREE_DISTINCT_OPERATORS_REQUIRED")
        assigned: set[str] = set()
        for op in doc["OPERATORS"]:
            source_record(op, "OPERATOR:" + op["OPERATOR_ID"], doc, root)
            if (
                not isinstance(op["TASK"], str)
                or not op["TASK"].strip()
                or op["WORK_DIRECTION"] not in DIRECTIONS
            ):
                raise InputError("OPERATOR_TASK_AND_DIRECTION_REQUIRED")
            for field, role in (("STANDING_COMPONENT", "STANDING"), ("REACH_COMPONENT", "REACH")):
                key = op[field]
                if (
                    key in assigned
                    or local[key]["ROLE"] != role
                    or "NORMAL_PRODUCTION" not in local[key]["ACTIVE_STATES"]
                ):
                    raise InputError("DISTINCT_ACTIVE_OPERATOR_ENVELOPES_REQUIRED")
                assigned.add(key)
            route = local_routes[op["ENTRY_PATH"]]
            if (
                route["FLOW_KIND"] != "PERSONNEL"
                or route["END_COMPONENTS"] != [op["STANDING_COMPONENT"]]
                or "NORMAL_PRODUCTION" not in route["ACTIVE_STATES"]
            ):
                raise InputError("INDIVIDUAL_OPERATOR_ENTRY_PATH_REQUIRED")
            center = local_interfaces[route["TO_INTERFACE"]]
            standing = local[op["STANDING_COMPONENT"]]["RECT"]
            if not (
                standing[0] < center[0] < standing[2] and standing[1] < center[1] < standing[3]
            ):
                raise InputError("OPERATOR_PATH_MUST_ENTER_STANDING_INTERIOR")
            direction = DIRECTIONS[op["WORK_DIRECTION"]]
            rotated = transform(
                (Fraction(direction[0]), Fraction(direction[1])), {**pose, "TRANSLATION_MM": [0, 0]}
            )
            operators.append(
                {
                    **op,
                    "KEY": station + "/" + op["OPERATOR_ID"],
                    "STATION": station,
                    "POSITION": [number(v) for v in center],
                    "DIRECTION": [number(v) for v in rotated],
                }
            )
        if len([r for r in local.values() if r["ROLE"] in ("STANDING", "REACH")]) != 6:
            raise InputError("UNASSIGNED_EXTRA_OPERATOR_ENVELOPE")
    if not station_ids:
        raise InputError("AT_LEAST_ONE_EXPLICIT_INSTANCE_REQUIRED")
    # Shared circulation is explicit assembly geometry, never inferred from station spacing.
    for item in doc["ASSEMBLY_CIRCULATION"]:
        key = identifier(item["COMPONENT_ID"])
        source_record(item, "ASSEMBLY:" + key, doc, root)
        if item["ROLE"] not in ROLES[TYPES[4]] or set(active_states(item["ACTIVE_STATES"])) != set(
            STATES
        ):
            raise InputError("ASSEMBLY_CIRCULATION_REQUIRED_ALL_STATES")
        if (
            item["COORDINATE_SYSTEM"] != "ASSEMBLY_GLOBAL"
            or item["DIMENSION_UNIT"] != "mm"
            or item["COMPONENT_TYPE"] != TYPES[4]
            or item["SOURCE_VERIFICATION"] != "CONTENT_REQUIRED"
            or item["APPROVAL_STATUS"] != "NOT_PROJECT_APPROVED"
            or item["SIMULTANEITY"] != "ALL_ACTIVE_COMPONENTS_IN_STATE"
            or item["OVERLAP_POLICY"] != "EXPLICIT_SHARED_REVIEW"
            or item["GEOMETRY"]["TYPE"] != "RECTANGLE"
        ):
            raise InputError("EXPLICIT_ASSEMBLY_COMPONENT_METADATA_REQUIRED")
        components.append(
            {
                **item,
                "KEY": "ASSEMBLY/" + key,
                "STATION": "ASSEMBLY",
                "COMPONENT_TYPE": TYPES[4],
                "RECT": transform_rect(item["GEOMETRY"]["BOUNDS_MM"], [item["TRANSFORM"]]),
            }
        )
    keys = [r["KEY"] for r in components]
    if len(keys) != len(set(keys)):
        raise InputError("DUPLICATE_ASSEMBLY_COMPONENT")
    for rule in doc["SHARING_CONDITIONS"]:
        source_record(rule, "SHARING:" + identifier(rule["RULE_ID"]), doc, root)
        if len(set(rule["COMPONENT_KEYS"])) != 2 or any(
            k not in keys for k in rule["COMPONENT_KEYS"]
        ):
            raise InputError("SHARING_REQUIRES_TWO_EXISTING_COMPONENTS")
        active_states(rule["STATES"])
        if not isinstance(rule["CONDITION_TEXT"], str) or not rule["CONDITION_TEXT"].strip():
            raise InputError("EXPLICIT_SHARING_CONDITION_REQUIRED")
    for route in doc["ASSEMBLY_ROUTES"]:
        key = identifier(route["ROUTE_ID"])
        source_record(route, "ASSEMBLY_ROUTE:" + key, doc, root)
        active_states(route["ACTIVE_STATES"])
        if route["FLOW_KIND"] not in ("PERSONNEL", "MATERIAL_IN", "PRODUCT_OUT"):
            raise InputError("UNKNOWN_ASSEMBLY_FLOW")
        pts = [point(p) for p in route["POINTS_MM"]]
        if (
            pts[0] != world_interfaces[route["FROM_KEY"]]
            or pts[-1] != world_interfaces[route["TO_KEY"]]
        ):
            raise InputError("ASSEMBLY_INTERFACE_ENDPOINT_MISMATCH")
        routes.append(
            {
                **route,
                "KEY": "ASSEMBLY/" + key,
                "STATION": "ASSEMBLY",
                "POINTS": pts,
                "RECTS": path_envelope(pts, route["WIDTH_MM"]),
                "END_KEYS": [],
            }
        )
    return components, routes, operators


def conflict(a: dict[str, Any], b: dict[str, Any]) -> tuple[str, bool]:
    roles = {a["ROLE"], b["ROLE"]}
    if roles <= {"BODY", "STANDING"}:
        return (
            "STANDING_VS_EQUIPMENT"
            if roles == {"BODY", "STANDING"}
            else "SOLID_OR_STANDING_COLLISION"
        ), True
    if "REACH" in roles:
        return "REACH_INTERACTION_NOT_SOLID_COLLISION", False
    if "SERVICE" in roles:
        return "SERVICE_INTERACTION_REVIEW", False
    if roles <= ROLES[TYPES[4]]:
        return "CIRCULATION_SHARING_REVIEW", False
    if "BODY" in roles:
        return "EQUIPMENT_VS_FLOW_OR_CIRCULATION", True
    if "STANDING" in roles:
        return "STANDING_VS_LOGISTICS_OR_CIRCULATION", True
    return "SUPPLY_OUTFEED_OR_FLOW_INTERACTION", False


def empty_result(reason: str, mode: str | None) -> dict[str, Any]:
    return {
        "IDENTITY": IDENTITY,
        "VERSION": VERSION,
        "MODE": mode,
        "GEOMETRY_INPUT_STATUS": "INPUT_REQUIRED_OR_INVALID",
        "DIAGNOSTICS": [reason],
        **{
            k: "INPUT_REQUIRED"
            for k in (
                "PHYSICAL_COMPONENT_STATUS",
                "OPERATOR_FIT_STATUS",
                "MATERIAL_FLOW_STATUS",
                "CIRCULATION_STATUS",
                "MAINTENANCE_STATUS",
                "SOURCE_STATUS",
            )
        },
        "GEOMETRIC_COLLISIONS": [],
        "FUNCTIONAL_CONFLICTS": [],
        "MODULE_BOUNDS": None,
        "MODULE_GEOMETRIC_AREA": None,
        "STATES": {},
        "MODULE_ENGINEERING_APPROVAL": "NOT_APPROVED",
        "REAL_PROJECT_MODULE_VALIDATED": False,
        "FORMAL_MODULE_DIMENSIONS_APPROVED": False,
        "OPERATOR_LAYOUT_APPROVED": False,
        "PACKAGING_AREA_CALIBRATION_READY": False,
        "FUNCTIONAL_ROOM_AREA": None,
        "SYNTHETIC_GEOMETRY_TEST_PASS": False,
        "REAL_FACTORY_SOLVES": 0,
        "NATIVE_SOLVER_CALLS": 0,
        "NEW_OWNER_GRANT": False,
    }


def evaluate(doc: dict[str, Any], evidence_root: Path) -> dict[str, Any]:
    if not isinstance(doc, dict):
        return empty_result("OBJECT_INPUT_REQUIRED", None)
    try:
        components, routes, operators = flatten(doc, evidence_root)
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        return empty_result(str(exc), doc.get("MODE"))
    state_results: dict[str, Any] = {}
    collisions: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    path_checks = []
    for state in STATES:
        active = [c for c in components if state in c["ACTIVE_STATES"]]
        for a, b in combinations(active, 2):
            overlap = intersection(a["RECT"], b["RECT"])
            if not overlap:
                continue
            kind, hard = conflict(a, b)
            matching = [
                r["RULE_ID"]
                for r in doc["SHARING_CONDITIONS"]
                if state in r["STATES"] and set(r["COMPONENT_KEYS"]) == {a["KEY"], b["KEY"]}
            ]
            item = {
                "STATE": state,
                "FIRST": a["KEY"],
                "SECOND": b["KEY"],
                "TYPE": kind,
                "POSITIVE_OVERLAP_MM2": number(overlap),
                "SOURCE_BOUND_CONDITIONS": matching,
                "STATUS": "FAIL" if hard else "REVIEW_REQUIRED",
            }
            (collisions if hard else reviews).append(item)
        circulation = [r["RECT"] for r in active if r["COMPONENT_TYPE"] == TYPES[4]]
        for route in routes:
            if state not in route["ACTIVE_STATES"]:
                continue
            terminals = [r["RECT"] for r in active if r["KEY"] in route["END_KEYS"]]
            covers = all(covered(r, [*circulation, *terminals]) for r in route["RECTS"])
            blocked = [
                c["KEY"]
                for c in active
                if c["ROLE"] == "BODY" and any(intersection(r, c["RECT"]) for r in route["RECTS"])
            ]
            path_checks.append(
                {
                    "STATE": state,
                    "KEY": route["KEY"],
                    "FLOW_KIND": route["FLOW_KIND"],
                    "FULL_WIDTH_COVERED": covers,
                    "EQUIPMENT_BLOCKERS": blocked,
                    "STATUS": "GEOMETRY_PASS_ONLY" if covers and not blocked else "FAIL",
                }
            )
        for a, b in combinations([r for r in routes if state in r["ACTIVE_STATES"]], 2):
            if a["FLOW_KIND"] == b["FLOW_KIND"]:
                continue
            area = union_area(
                [
                    r
                    for x in a["RECTS"]
                    for y in b["RECTS"]
                    if intersection(x, y)
                    for r in [(max(x[0], y[0]), max(x[1], y[1]), min(x[2], y[2]), min(x[3], y[3]))]
                ]
            )
            contact = any(touches(x, y) for x in a["RECTS"] for y in b["RECTS"])
            if area or contact:
                reviews.append(
                    {
                        "STATE": state,
                        "FIRST": a["KEY"],
                        "SECOND": b["KEY"],
                        "TYPE": "PERSONNEL_MATERIAL_OR_FLOW_CROSSING",
                        "STATUS": "REVIEW_REQUIRED",
                        "POSITIVE_OVERLAP_MM2": number(area),
                        "BOUNDARY_CONTACT": contact,
                    }
                )
        rects = [c["RECT"] for c in active]
        state_bounds = bounds(rects)
        assert state_bounds
        area = union_area(rects)
        state_results[state] = {
            "BOUNDS_MM": state_bounds,
            "WIDTH_MM": number(Fraction(state_bounds[2]) - Fraction(state_bounds[0])),
            "DEPTH_MM": number(Fraction(state_bounds[3]) - Fraction(state_bounds[1])),
            "GEOMETRIC_UNION_AREA_MM2": number(area),
            "BOUNDING_RECTANGLE_AREA_MM2": number(
                (Fraction(state_bounds[2]) - Fraction(state_bounds[0]))
                * (Fraction(state_bounds[3]) - Fraction(state_bounds[1]))
            ),
            "SUM_COMPONENT_AREAS_MM2": number(sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects)),
            "ACTIVE_COMPONENT_KEYS": [c["KEY"] for c in active],
            "FUNCTIONAL_ROOM_AREA": None,
        }
    failed_paths = any(p["STATUS"] == "FAIL" for p in path_checks)
    graph: dict[str, set[str]] = {op["STATION"]: set() for op in operators}
    for route in routes:
        if route["STATION"] == "ASSEMBLY" and route["FLOW_KIND"] == "PERSONNEL":
            check = next(
                (
                    p
                    for p in path_checks
                    if p["STATE"] == "NORMAL_PRODUCTION" and p["KEY"] == route["KEY"]
                ),
                None,
            )
            if check and check["STATUS"] == "GEOMETRY_PASS_ONLY":
                a, b = route["FROM_KEY"].split("/")[0], route["TO_KEY"].split("/")[0]
                graph[a].add(b)
                graph[b].add(a)
    reached = {sorted(graph)[0]}
    while True:
        more = reached | {v for u in reached for v in graph[u]}
        if more == reached:
            break
        reached = more
    connected = reached == set(graph)
    all_rects = [c["RECT"] for c in components]
    all_bounds = bounds(all_rects)
    assert all_bounds
    temporal = [
        {
            "FIRST": a["KEY"],
            "SECOND": b["KEY"],
            "FIRST_STATES": a["ACTIVE_STATES"],
            "SECOND_STATES": b["ACTIVE_STATES"],
            "OVERLAP_MM2": number(intersection(a["RECT"], b["RECT"])),
            "STATUS": "NON_SIMULTANEOUS_BY_DECLARED_STATE_NOT_SHARING_APPROVAL",
        }
        for a, b in combinations(components, 2)
        if not set(a["ACTIVE_STATES"]) & set(b["ACTIVE_STATES"])
        and intersection(a["RECT"], b["RECT"])
    ]
    result = {
        "IDENTITY": IDENTITY,
        "VERSION": VERSION,
        "MODE": doc["MODE"],
        "INPUT_SHA256": digest(encode(doc)),
        "GEOMETRY_INPUT_STATUS": "VALID_SOURCE_BOUND_OFFLINE_INPUT",
        "SOURCE_STATUS": "ACTUAL_LOCAL_CONTENT_MATCH_NOT_PUBLISHER_AUTHENTICATION",
        "PHYSICAL_COMPONENT_STATUS": "FAIL" if collisions else "GEOMETRY_PASS_ONLY",
        "OPERATOR_FIT_STATUS": "FAIL"
        if collisions or failed_paths
        else "REVIEW_REQUIRED_TASK_AND_REACH",
        "MATERIAL_FLOW_STATUS": "FAIL"
        if any(p["STATUS"] == "FAIL" and p["FLOW_KIND"] != "PERSONNEL" for p in path_checks)
        else "GEOMETRY_ONLY_ENGINEERING_REVIEW_REQUIRED",
        "CIRCULATION_STATUS": "FAIL"
        if failed_paths
        else "EXPLICIT_FULL_WIDTH_PATHS_CHECKED_NOT_SAFETY_APPROVAL",
        "ASSEMBLY_CONNECTIVITY_STATUS": "EXPLICIT_PERSONNEL_ROUTES_CONNECTED"
        if connected
        else "REVIEW_REQUIRED_UNCONNECTED_STATIONS",
        "MAINTENANCE_STATUS": "REVIEW_REQUIRED_STATE_GEOMETRY_NOT_PROCEDURE_APPROVAL",
        "SHIFT_CHANGE_STATUS": "REVIEW_REQUIRED_NO_ZERO_TIME_ASSUMPTION",
        "GEOMETRIC_COLLISIONS": collisions,
        "FUNCTIONAL_CONFLICTS": reviews,
        "MODULE_BOUNDS": all_bounds,
        "DIMENSION_UNIT": "mm",
        "MODULE_GEOMETRIC_AREA": {
            "GEOMETRIC_UNION_AREA_MM2": number(union_area(all_rects)),
            "BOUNDING_RECTANGLE_AREA_MM2": number(
                (Fraction(all_bounds[2]) - Fraction(all_bounds[0]))
                * (Fraction(all_bounds[3]) - Fraction(all_bounds[1]))
            ),
            "SCOPE": "All-state swept occupation, not room demand or simultaneous-state area",
            "FUNCTIONAL_ROOM_AREA": None,
        },
        "STATES": state_results,
        "NON_SIMULTANEOUS_OCCUPATIONS": temporal,
        "PATH_CHECKS": path_checks,
        "OPERATORS": operators,
        "MODULE_ENGINEERING_APPROVAL": "NOT_APPROVED",
        "OPERATOR_LAYOUT_APPROVED": False,
        "REAL_PROJECT_MODULE_VALIDATED": False,
        "FORMAL_MODULE_DIMENSIONS_APPROVED": False,
        "FUNCTIONAL_ROOM_AREA": None,
        "PACKAGING_AREA_CALIBRATION_READY": False,
        "SYNTHETIC_GEOMETRY_TEST_PASS": doc["MODE"] == "SYNTHETIC_TEST"
        and not collisions
        and not failed_paths
        and connected,
        "REAL_FACTORY_SOLVES": 0,
        "NATIVE_SOLVER_CALLS": 0,
        "NEW_OWNER_GRANT": False,
        "LIMITATIONS": [
            "Axis-aligned rectangles and orthogonal full-width paths only",
            "Source-bound overlap conditions are recorded, not automatically approved",
            "No anthropometric reach, task suitability, door sweep or fire/hygiene approval",
            "Arrangement labels do not prove line continuity or room capacity",
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        doc = json.loads(args.input.read_bytes())
        output = evaluate(doc, args.evidence_root)
    except (ValueError, OSError) as exc:
        output = empty_result(str(exc), None)
    print(encode(output).decode(), end="")


if __name__ == "__main__":
    main()
