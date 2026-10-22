"""FunctionalRoomFitEvaluatorV1: supplied-layout diagnostics, never design approval.

Reuse the sealed candidate loader, R2 source review and R1 exact geometry.
No search, defaults for spatial dimensions, production writes or approval tokens.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from fractions import Fraction
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
REFERENCE = "a34dff1f45dcbc930b3ca3d4e0a07117dbf8d592"
IDENTITY = "FunctionalRoomFitEvaluatorV1"
VERSION = "functional-room-fit@1.0.0"
STATES = ("NORMAL_OPERATION", "SHIFT_CHANGE", "CLEANING", "MAINTENANCE")
ZONES = ("office", "changing_room", "coating_room")
MODELS = dict(
    zip(
        ZONES,
        (
            "OfficeFunctionalModuleV1",
            "ChangingRoomFunctionalModuleV1",
            "FilmSealingRoomFunctionalModuleV1",
        ),
        strict=True,
    )
)
REQUIRED = {
    "office": (
        "factory_size",
        "design_staff",
        "workstations",
        "furniture_model",
        "chair_movement",
        "storage",
        "necessary_functions",
    ),
    "changing_room": (
        "locker_count",
        "simultaneous_users",
        "locker_model",
        "locker_unit_mm",
        "arrangement",
        "door_sweep",
        "bench",
        "clothing_separation",
        "hygiene_facilities",
    ),
    "coating_room": (
        "process_type",
        "equipment_model",
        "equipment_count",
        "capacity",
        "effective_runtime_hours",
        "body_height_mm",
        "infeed_direction",
        "outfeed_direction",
        "operator_tasks",
        "product_buffer",
    ),
}
COMMON = (
    "finished_clear_bounds_mm",
    "door_operation",
    "shift_change_duration",
    "cleaning_duration",
    "maintenance_procedure",
)
ROLES = {
    "BODY",
    "STANDING",
    "REACH",
    "CHAIR",
    "DOOR_SWEEP",
    "SUPPLY",
    "OUTFEED",
    "AISLE",
    "SERVICE",
    "BUFFER",
}


@lru_cache
def previous(folder: str, script: str, manifest_sha: str) -> Any:
    """Verify immutable prior delivery before importing; not a project approver."""
    import hashlib

    root = HERE.parent / folder
    raw = (root / "source_manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest_sha:
        raise ValueError("DEPENDENCY_MANIFEST_CHANGED")
    for name, item in json.loads(raw)["files"].items():
        expected = item if isinstance(item, str) else item["sha256"]
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("DEPENDENCY_FILE_CHANGED:" + name)
    name = "fit_dependency_" + folder.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, root / script)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


@lru_cache
def dependencies() -> tuple[Any, Any, Any, Any]:
    adapter = previous(
        "owner-v2-packing-station-project-evidence-r2",
        "offline_project_input_adapter.py",
        "9ed3c36f01baf83693f097819c2a9e54c54a3082ce6d25d294b95f7300c460d6",
    )
    geometry, _ = adapter.load_r1()
    loader = previous(
        "stage-b-truck-p2d-preflight-r1",
        "offline_stage_b_truck_preflight.py",
        "b8e3bdacdbd3493b2d8947e0cda432adbaaeac6726c04784ba88cfd70ce84927",
    )
    owner = previous(
        "owner-functional-input-contract-r2",
        "offline_contract_v2.py",
        "63c33b66661ded8c7ad5f8b0d88908a7529f360230da5ba5a10e9c2cf8cf264d",
    )
    return geometry, adapter, loader, owner


def encode(value: Any) -> bytes:
    return cast(bytes, dependencies()[0].encode(value))


def mm(value: Any) -> int:
    return cast(int, dependencies()[1].normalize_value(value, "m", "COORDINATE", "COORDINATE"))


def local_point(point: list[int], room: dict[str, Any]) -> list[int]:
    """Local XY parallel to physical world XY, origin at physical lower-left.

    Nominal dimension rotation is already consumed by the original rectangle decoder.
    No second rotation is applied to world Portal coordinates.
    """
    x0, y0, _, _ = room["WORLD_BOUNDS_MM"]
    return [point[0] - x0, point[1] - y0]


def business_examples() -> dict[str, Any]:
    _, _, _, owner = dependencies()
    root = owner.HERE
    example = json.loads((root / ("staffing-and-locker-calculation.json")).read_bytes())[
        "examples"
    ][0]
    result = owner.calculate(example["input"], evidence_root=root)
    old = owner.load_previous(owner.V1, "contract.py")
    return {
        "VERSION": owner.VERSION,
        ("OFFICE_CONDITIONAL_SCENARIOS"): {s: old.office(s) for s in ("SMALL", "MEDIUM", "LARGE")},
        "UNKNOWN_FACTORY_SIZE": old.office(None),
        "CONDITIONAL_20T_PACKAGED_PRODUCT_EXAMPLE": result,
        "BOUND_TO_HISTORICAL_LAYOUT_STAFFING": False,
        "PROJECT_STAFFING": None,
    }


def audit_rooms(artifact_root: Path) -> dict[str, Any]:
    _, _, loader, _ = dependencies()
    authorities, sources = loader.load_sealed(artifact_root)
    from cold_storage.modules.layout.application.access_routing import _rectangle_from_row
    from cold_storage.modules.layout.domain.dimensioning import canonical_hash

    rows = []
    for source in sources:
        engineering = source["raw"]["engineering_validation"]
        for zone in ZONES:
            original = next(z for z in engineering["zones"] if z["zone_code"] == zone)
            rect = _rectangle_from_row(original)
            bounds = list(rect.bounds_mm)
            x0, y0, x1, y1 = bounds
            portals = []
            for portal in engineering["portals"]:
                if portal["access_ref"] != zone:
                    continue
                flows = sorted(
                    {
                        r["flow_kind"]
                        for r in engineering["access_results"]
                        if any(
                            (r.get(k) or {}).get("identity") == portal["identity"]
                            for k in ("portal_from", "portal_to")
                        )
                    }
                )
                segment = [
                    [mm(portal["segment"][k][axis]) for axis in ("x", "y")]
                    for k in ("start", "end")
                ]
                portals.append(
                    {
                        "ORIGINAL": portal,
                        "WORLD_SEGMENT_MM": segment,
                        "LOCAL_SEGMENT_MM": [[x - x0, y - y0] for x, y in segment],
                        "FLOW_KINDS": flows,
                        "CLEAR_WIDTH_MM": mm(portal["clear_width_m"]),
                        "DOOR_SWING": None,
                        "PORTAL_FUNCTIONAL_ACCESS": "NOT_EVALUATED",
                    }
                )
            rows.append(
                {
                    "CANDIDATE_ID": source["catalog"]["candidate_id"],
                    "ZONE_CODE": zone,
                    ("SOURCE_GEOMETRY_HASH"): source["projection"]["provenance"]["geometry_hash"],
                    "RAW_CANDIDATE_SHA256": source["catalog"]["raw_candidate_sha256"],
                    "SOURCE_ZONE": original,
                    "WORLD_BOUNDS_MM": bounds,
                    "LOCAL_COORDINATES": "PHYSICAL_XY_LOWER_LEFT_NOT_NOMINAL_ROTATED_FRAME",
                    "ROOM_WIDTH_MM": x1 - x0,
                    "ROOM_DEPTH_MM": y1 - y0,
                    "ROOM_AREA_MM2": (x1 - x0) * (y1 - y0),
                    "AREA_AUTHORITY_M2": {"office": 60, "changing_room": 40, "coating_room": 80}[
                        zone
                    ],
                    "SHORT_EDGE_MM": min(x1 - x0, y1 - y0),
                    "LONG_EDGE_MM": max(x1 - x0, y1 - y0),
                    "PORTALS": portals,
                    "FUNCTIONAL_INPUT_STATUS": "INPUT_REQUIRED",
                    "MODEL_ORIENTATION": None,
                    "EQUIPMENT_FIT_STATUS": "NOT_EVALUATED",
                    "OPERATION_STATUS": "NOT_EVALUATED",
                    "CIRCULATION_STATUS": "NOT_EVALUATED",
                    "PORTAL_ACCESS_STATUS": "NOT_EVALUATED",
                    "PORTAL_FUNCTIONAL_ACCESS": "NOT_EVALUATED",
                    "CLEANING_MAINTENANCE_STATUS": "NOT_EVALUATED",
                    "CONFLICTS": [],
                    "MISSING_INPUTS": [
                        *REQUIRED[zone],
                        *COMMON,
                        "state_bound_components",
                        "full_width_internal_routes",
                        "project_source_review",
                    ],
                    "FUNCTIONAL_FIT_STATUS": "INPUT_REQUIRED",
                    "FORMAL_AUTHORITY_STATUS": "NOT_APPROVED",
                    "PROJECT_FUNCTIONAL_FIT_APPROVED": False,
                }
            )
    return {
        "IDENTITY": IDENTITY,
        "VERSION": VERSION,
        "ROOMS": rows,
        "CANDIDATES_AUDITED": len(sources),
        "ROOMS_AUDITED": len(rows),
        "AUTHORITY_BYTE_HASH": loader.sha(
            (loader.BASELINE / "inputs/server_authorities.json").read_bytes()
        ),
        "CANONICAL_HASH": canonical_hash(authorities["canonical_zone_plan"]),
        "P1_DIMENSION_HASH": canonical_hash(
            authorities["p1_handoff"]["p1e_historical_handoff"]["dimension_handoff"]
        ),
        "REAL_FACTORY_SOLVES": 0,
        "REAL_TRUCK_SEARCHES": 0,
        "NATIVE_SOLVER_CALLS": 0,
        "NEW_OWNER_GRANT": False,
        "P2D_FULL_PASS_COUNT": 0,
        "STAGE_B_COMPLETE": False,
        "VERSION_COMPLETE": False,
    }


def bind_record(
    record: dict[str, Any], key: str, doc: dict[str, Any], root: Path, context: Any = None
) -> str:
    geo, adapter, _, _ = dependencies()
    if doc["MODE"] == "SYNTHETIC_TEST":
        geo.source_record(record, key, doc, root)
        return "SYNTHETIC_TEST"
    if doc["MODE"] != "PROJECT_CANDIDATE_INPUT" or context is None or context.test_only:
        raise ValueError("EXISTING_PROJECT_SOURCE_REVIEW_CONTEXT_REQUIRED")
    ref = doc["PROJECT_RECORD_REFERENCES"][key]
    raw, anchor = adapter.verify_document(ref["DOCUMENT"], doc, context, root)
    if adapter.extracted(raw, ref["LOCATION"], anchor) != record:
        raise ValueError("REVIEWED_SOURCE_RECORD_MISMATCH")
    return "PROJECT_CANDIDATE_INPUT_NOT_APPROVED"


def evaluate(doc: dict[str, Any], evidence_root: Path, *, context: Any = None) -> dict[str, Any]:
    """Evaluate one explicit room/configuration; never infer or search a placement."""
    geo, _, _, _ = dependencies()
    result: dict[str, Any] = {
        "IDENTITY": IDENTITY,
        "VERSION": VERSION,
        "FUNCTIONAL_FIT_STATUS": "INPUT_REQUIRED",
        "FORMAL_AUTHORITY_STATUS": "NOT_APPROVED",
        "PROJECT_FUNCTIONAL_FIT_APPROVED": False,
        "SOURCE_STATUS": "UNAVAILABLE",
        "MISSING_INPUTS": [],
        "CONFLICTS": [],
        "STATE_RESULTS": {},
        "FUNCTIONAL_ROOM_AREA": None,
        "CAPACITY_VALIDATED": False,
        "TIME_SHARING_APPROVED": False,
        "MODEL_ORIENTATION": doc.get("MODEL_ORIENTATION"),
    }
    try:
        if any(k.lower() in ("verified", "approved", "authority_token") for k in doc):
            raise ValueError("CALLER_APPROVAL_NOT_ACCEPTED")
        if doc["IDENTITY"] != IDENTITY or doc["VERSION"] != VERSION:
            raise ValueError("EXPLICIT_FUNCTIONAL_MODEL_IDENTITY_REQUIRED")
        zone = doc["ZONE_CODE"]
        if zone not in ZONES or doc["MODEL"] != MODELS[zone]:
            raise ValueError("FUNCTIONAL_MODEL_ZONE_MISMATCH")
        if doc["DIMENSION_UNIT"] != "mm" or doc["COORDINATE_SYSTEM"] != "ROOM_LOCAL_XY_Y_UP":
            raise ValueError("INTEGER_MM_ROOM_LOCAL_REQUIRED")
        config = doc["CONFIGURATION"]
        source = bind_record(config, "CONFIGURATION", doc, evidence_root, context)
        result["SOURCE_STATUS"] = source
        missing = [k for k in (*REQUIRED[zone], *COMMON) if config.get(k) is None]
        if zone == "office":
            old = dependencies()[3].load_previous(dependencies()[3].V1, "contract.py")
            office = old.office(config.get("factory_size"))
            result["OFFICE_BUSINESS_INPUT"] = office
            if office.get("OFFICE_DESIGN_STAFF") != config.get("design_staff"):
                missing.append("explicit_factory_size_and_matching_owner_staff")
        if zone == "changing_room" and config.get("arrangement") not in (
            "SINGLE_ROW",
            "OPPOSED_ROWS",
            "PROJECT_DEFINED_LAYOUT",
        ):
            missing.append("explicit_changing_arrangement")
        if zone == "coating_room" and config.get("process_type") != ("PACKAGING_BOX_FILM_SEALING"):
            raise ValueError("BOX_FILM_SEALING_ONLY_NOT_WAXING_OR_PALLET_WRAPPING")
        room = geo.transform_rect(doc["ROOM_BOUNDS_MM"], [])
        clear_raw = config.get("finished_clear_bounds_mm")
        if clear_raw is None:
            result["MISSING_INPUTS"] = sorted(set([*missing, "finished_clear_bounds_mm"]))
            return result
        clear = geo.transform_rect(clear_raw, [])
        if not geo.covered(clear, [room]):
            raise ValueError("FINISHED_CLEAR_BOUNDS_OUTSIDE_SOURCE_ROOM")
        components = []
        seen = set()
        for item in doc["COMPONENTS"]:
            bind_record(item, "COMPONENT:" + item["ID"], doc, evidence_root, context)
            if item["ID"] in seen or item["ROLE"] not in ROLES:
                raise ValueError("DUPLICATE_OR_UNKNOWN_COMPONENT")
            seen.add(item["ID"])
            active = item["ACTIVE_STATES"]
            if (
                not active
                or len(set(active)) != len(active)
                or any(s not in STATES for s in active)
            ):
                raise ValueError("EXPLICIT_KNOWN_ACTIVE_STATES_REQUIRED")
            if item["ROLE"] == "BODY" and set(active) != set(STATES):
                raise ValueError("PHYSICAL_BODY_CANNOT_DISAPPEAR")
            rect = geo.transform_rect(item["BOUNDS_MM"], [item["TRANSFORM"]])
            components.append({**item, "RECT": rect})
        routes = []
        for route in doc["ROUTES"]:
            bind_record(route, "ROUTE:" + route["ID"], doc, evidence_root, context)
            if not route["ACTIVE_STATES"] or any(s not in STATES for s in route["ACTIVE_STATES"]):
                raise ValueError("ROUTE_STATE_REQUIRED")
            points = [geo.point(p) for p in route["POINTS_MM"]]
            route_envelope = geo.path_envelope(points, route["WIDTH_MM"])
            routes.append({**route, "RECTS": route_envelope})
        portals = []
        for portal in doc["PORTALS"]:
            bind_record(portal, "PORTAL:" + portal["ID"], doc, evidence_root, context)
            a, b = [geo.point(p) for p in portal["SEGMENT_MM"]]
            if a == b or (a[0] != b[0] and a[1] != b[1]):
                raise ValueError("AXIAL_PORTAL_REQUIRED")
            portals.append((portal, a, b))
        if not components:
            missing.append("components")
        for state in STATES:
            active = [c for c in components if state in c["ACTIVE_STATES"]]
            conflicts: list[dict[str, Any]] = []

            def conflict(
                kind: str, code: str, ids: list[str], target: list[dict[str, Any]] = conflicts
            ) -> None:
                target.append({"CLASS": kind, "CODE": code, "COMPONENT_IDS": ids})

            for c in active:
                if not geo.covered(c["RECT"], [clear]):
                    conflict(("HARD_GEOMETRY_CONFLICT"), ("OUTSIDE_FINISHED_CLEAR_ROOM"), [c["ID"]])
            for a, b in combinations(active, 2):
                if not geo.intersection(a["RECT"], b["RECT"]):
                    continue
                roles = {a["ROLE"], b["ROLE"]}
                hard = roles <= {"BODY", "STANDING"} or (
                    "BODY" in roles and bool(roles & {"AISLE", "DOOR_SWEEP", "SUPPLY", "OUTFEED"})
                )
                conflict(
                    "HARD_GEOMETRY_CONFLICT" if hard else "INTERACTION_REVIEW_REQUIRED",
                    "ACTIVE_" + "_".join(sorted(roles)),
                    [a["ID"], b["ID"]],
                )
            for portal, a, b in portals:
                for c in active:
                    if c["ROLE"] != "BODY":
                        continue
                    x0, y0, x1, y1 = c["RECT"]
                    intersects = (
                        a[0] == b[0]
                        and x0 <= a[0] <= x1
                        and max(min(a[1], b[1]), y0) < min(max(a[1], b[1]), y1)
                    ) or (
                        a[1] == b[1]
                        and y0 <= a[1] <= y1
                        and max(min(a[0], b[0]), x0) < min(max(a[0], b[0]), x1)
                    )
                    if intersects:
                        conflict(
                            "HARD_GEOMETRY_CONFLICT",
                            "PORTAL_BLOCKED_BY_BODY",
                            [portal["ID"], c["ID"]],
                        )
            state_routes = [r for r in routes if state in r["ACTIVE_STATES"]]
            if not state_routes:
                missing.append(state + ":full_width_circulation")
            cover = [c["RECT"] for c in active if c["ROLE"] in {"AISLE", "STANDING"}]
            route_results = []
            for route in state_routes:
                clear_path = all(
                    geo.covered(r, [clear]) and geo.covered(r, cover) for r in route["RECTS"]
                )
                body_hit = any(
                    geo.intersection(r, c["RECT"]) > 0
                    for r in route["RECTS"]
                    for c in active
                    if c["ROLE"] == "BODY"
                )
                if not clear_path or body_hit:
                    conflict(
                        "HARD_GEOMETRY_CONFLICT",
                        "FULL_WIDTH_ROUTE_BLOCKED_OR_UNCOVERED",
                        [route["ID"]],
                    )
                portal_id = route.get("PORTAL_ID")
                portal_matches = [
                    p for p in portals if p[0]["ID"] in (portal_id, route.get("EXIT_PORTAL_ID"))
                ]
                connected = False
                caps: list[tuple[Fraction, Fraction, Fraction, Fraction]] = []
                connected_ids = []
                for matched_portal, a, b in portal_matches:
                    ends = (geo.point(route["POINTS_MM"][0]), geo.point(route["POINTS_MM"][-1]))
                    matched = any(
                        (
                            a[0] == b[0] == p[0]
                            and min(a[1], b[1]) <= p[1] - Fraction(route["WIDTH_MM"], 2)
                            and p[1] + Fraction(route["WIDTH_MM"], 2) <= max(a[1], b[1])
                        )
                        or (
                            a[1] == b[1] == p[1]
                            and min(a[0], b[0]) <= p[0] - Fraction(route["WIDTH_MM"], 2)
                            and p[0] + Fraction(route["WIDTH_MM"], 2) <= max(a[0], b[0])
                        )
                        for p in ends
                    )
                    if matched:
                        connected_ids.append(matched_portal["ID"])
                        half = Fraction(route["WIDTH_MM"], 2)
                        # Only the square endpoint cap crossing an explicitly bound opening.
                        # No outside road/path clearance or usable room area is inferred.
                        caps.extend(
                            (p[0] - half, p[1] - half, p[0] + half, p[1] + half)
                            for p in ends
                            if (a[0] == b[0] == p[0] or a[1] == b[1] == p[1])
                        )
                connected = portal_id in connected_ids
                if route.get("EXIT_PORTAL_ID") is not None:
                    connected = connected and route["EXIT_PORTAL_ID"] in connected_ids
                if connected:
                    clear_path = all(
                        geo.covered(r, [clear, *caps]) and geo.covered(r, [*cover, *caps])
                        for r in route["RECTS"]
                    )
                    # Replace the preliminary square-cap boundary conflict only if
                    # the whole width is covered by room plus proven portal caps.
                    if clear_path and not body_hit:
                        conflicts[:] = [
                            c
                            for c in conflicts
                            if not (
                                c["CODE"] == "FULL_WIDTH_ROUTE_BLOCKED_OR_UNCOVERED"
                                and c["COMPONENT_IDS"] == [route["ID"]]
                            )
                        ]
                else:
                    missing.append(route["ID"] + ":source_portal_connection")
                route_results.append(
                    {
                        "ID": route["ID"],
                        "FULL_WIDTH_GEOMETRY_CLEAR": clear_path and not body_hit,
                        "PORTAL_CONNECTION_PROVEN": connected,
                        "PORTAL_FUNCTIONAL_ACCESS": "NOT_EVALUATED",
                    }
                )
            if not any(c["ROLE"] == "SERVICE" for c in active) and state in (
                "CLEANING",
                "MAINTENANCE",
            ):
                missing.append(state + ":service_envelope")
            if not any(c["ROLE"] == "STANDING" for c in active) and state == "NORMAL_OPERATION":
                missing.append("operator_standing")
            if zone == "coating_room" and state == "NORMAL_OPERATION":
                if not any(r["KIND"] == "NON_SEALING_PASS_THROUGH" for r in state_routes):
                    missing.append("non_sealing_pass_through")
                for role in ("SUPPLY", "OUTFEED", "BUFFER"):
                    if not any(c["ROLE"] == role for c in active):
                        missing.append(role.lower())
            area = geo.union_area([c["RECT"] for c in active])
            result["STATE_RESULTS"][state] = {
                "CONFLICTS": conflicts,
                "ROUTES": route_results,
                "GEOMETRIC_UNION_AREA_MM2": geo.number(area),
                "BOUNDS_MM": geo.bounds([c["RECT"] for c in active]),
                "STATUS": "HARD_GEOMETRY_CONFLICT"
                if any(c["CLASS"] == "HARD_GEOMETRY_CONFLICT" for c in conflicts)
                else "INTERACTION_REVIEW_REQUIRED"
                if conflicts
                else "GEOMETRY_CHECK_ONLY",
            }
            result["CONFLICTS"].extend({**c, "STATE": state} for c in conflicts)
        result["MISSING_INPUTS"] = sorted(set(missing))
        hard = any(c["CLASS"] == "HARD_GEOMETRY_CONFLICT" for c in result["CONFLICTS"])
        result["FUNCTIONAL_FIT_STATUS"] = (
            "CONDITIONAL_SCENARIO_NOT_FIT"
            if hard
            else "INPUT_REQUIRED"
            if missing
            else "INTERACTION_REVIEW_REQUIRED"
            if result["CONFLICTS"]
            else "GEOMETRY_CHECK_ONLY"
        )
        result["NO_FIT_PROOF_SCOPE"] = (
            "SUPPLIED_CONFIGURATION_AND_ORIENTATION_ONLY_NOT_ALL_ROOM_USES" if hard else None
        )
        result["PORTAL_FUNCTIONAL_ACCESS"] = "NOT_EVALUATED"
        result["ROOM_GEOMETRIC_AREA_MM2"] = geo.number(geo.union_area([room]))
        result["TIME_SHARING_STATUS"] = "ENGINEERING_REVIEW_REQUIRED_NOT_GRANTED_BY_INACTIVE_STATES"
    except (KeyError, TypeError, ValueError) as exc:
        result["MISSING_INPUTS"] = [str(exc)]
        result["FUNCTIONAL_FIT_STATUS"] = "INPUT_REQUIRED"
    return result


def opposed_width_proof(clear_width: int, first_depth: int, second_depth: int) -> dict[str, Any]:
    geo = dependencies()[0]
    values = [geo.integer(v) for v in (clear_width, first_depth, second_depth)]
    if any(v <= 0 for v in values):
        raise ValueError("POSITIVE_EXPLICIT_MM_REQUIRED")
    need = first_depth + second_depth
    return {
        "CONFIGURATION": "SPECIFIED_OPPOSED_ROWS_NO_CLEARANCES_ASSUMED_APPROVED",
        "NECESSARY_BODY_WIDTH_MM": need,
        "AVAILABLE_WIDTH_MM": clear_width,
        "DEFICIT_MM": max(0, need - clear_width),
        "STATUS": ("CONDITIONAL_SCENARIO_NOT_FIT") if need > clear_width else "GEOMETRY_CHECK_ONLY",
        "OTHER_ARRANGEMENTS_EXCLUDED": False,
        "PROJECT_FUNCTIONAL_FIT_APPROVED": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--evidence-root", type=Path, default=HERE / "examples")
    args = parser.parse_args()
    if args.input:
        result = evaluate(json.loads(args.input.read_bytes()), args.evidence_root)
    elif args.artifact_root:
        result = audit_rooms(args.artifact_root)
    else:
        parser.error("Explicit sealed artifact root or offline input required")
    sys.stdout.buffer.write(encode(result))


if __name__ == "__main__":
    main()
