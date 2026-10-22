"""Offline functional-room evidence, arithmetic and conditional screening only."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASELINE = HERE.parent / "stage-b/layout-quality-baseline-01"
VERSION = "functional-room-conditional-screening@1.0.0"
ROOMS = ("office", "changing_room", "coating_room")
REFERENCE = "78f42b3956d3569e5a887fb578ce5e773275cc5b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def text(value: Fraction | int) -> str:
    with localcontext() as context:
        context.prec = 40
        if value.denominator == 1:
            return str(value.numerator)
        return (
            format(Decimal(value.numerator) / Decimal(value.denominator), "f")
            .rstrip("0")
            .rstrip(".")
        )


def mm(value: Any) -> int:
    exact = Fraction(str(value)) * 1000
    if exact.denominator != 1:
        raise ValueError("OFFLINE_INPUT_NOT_ON_MM_GRID")
    return exact.numerator


def require_numbers(values: dict[str, int | None]) -> dict[str, Any]:
    missing = [k for k, v in values.items() if v is None]
    if missing:
        return {"status": "OWNER_INPUT_REQUIRED", "missing": missing, "value": None}
    if any(type(v) is not int or v < 0 for v in values.values()):
        raise ValueError("INVALID_NONNEGATIVE_INTEGER_INPUT")
    return {"status": "INPUT_COMPLETE_ARITHMETIC_ONLY", "missing": [], "value": values}


def office_module(
    *,
    people: int | None,
    rows: int | None,
    desk_width: int | None,
    desk_depth: int | None,
    user_zone: int | None,
    through_aisle: int | None,
    side_storage: int | None,
    end_space: int | None,
) -> dict[str, Any]:
    """Separate user/passage lanes; no shared-lane assumption or default dimensions."""
    values = dict(
        people=people,
        rows=rows,
        desk_width=desk_width,
        desk_depth=desk_depth,
        user_zone=user_zone,
        through_aisle=through_aisle,
        side_storage=side_storage,
        end_space=end_space,
    )
    checked = require_numbers(values)
    if checked["value"] is None:
        return checked
    v = checked["value"]
    if min(v["people"], v["rows"], v["desk_width"], v["desk_depth"]) <= 0:
        raise ValueError("INVALID_OFFICE_MODULE")
    columns = (v["people"] + v["rows"] - 1) // v["rows"]
    return {
        "status": "HYPOTHETICAL_OFFLINE_SCREENING",
        "project_approved": False,
        "cross_section_mm": v["rows"] * (v["desk_depth"] + v["user_zone"])
        + v["through_aisle"]
        + v["side_storage"],
        "length_mm": columns * v["desk_width"] + 2 * v["end_space"],
        "limitation": (
            "Arithmetic rectangle module, not door/window/fire/accessibility or packing approval"
        ),
    }


def locker_module(
    *,
    users: int | None,
    rows: int | None,
    unit_width: int | None,
    unit_depth: int | None,
    slots_per_unit: int | None,
    front_service_zone: int | None,
    bench: int | None,
    independent_aisle: int | None,
    end_space: int | None,
) -> dict[str, Any]:
    values = dict(
        users=users,
        rows=rows,
        unit_width=unit_width,
        unit_depth=unit_depth,
        slots_per_unit=slots_per_unit,
        front_service_zone=front_service_zone,
        bench=bench,
        independent_aisle=independent_aisle,
        end_space=end_space,
    )
    checked = require_numbers(values)
    if checked["value"] is None:
        return checked
    v = checked["value"]
    if min(v["users"], v["rows"], v["unit_width"], v["unit_depth"], v["slots_per_unit"]) <= 0:
        raise ValueError("INVALID_LOCKER_MODULE")
    units = (v["users"] + v["slots_per_unit"] - 1) // v["slots_per_unit"]
    columns = (units + v["rows"] - 1) // v["rows"]
    return {
        "status": "HYPOTHETICAL_OFFLINE_SCREENING",
        "project_approved": False,
        "unit_count": units,
        "length_mm": columns * v["unit_width"] + 2 * v["end_space"],
        "cross_section_mm": v["rows"] * v["unit_depth"]
        + v["front_service_zone"]
        + v["bench"]
        + v["independent_aisle"],
        "limitation": (
            "Front zone must already include approved door/user overlap "
            "policy; no clearance defaults"
        ),
    }


def envelope_state(
    *,
    equipment: list[list[int]] | None,
    operation: list[list[int]] | None,
    maintenance: list[list[int]] | None,
    material: list[list[int]] | None,
    mode: str,
) -> dict[str, Any]:
    """Compute necessary bounding extents, never claim full collision-free fitting."""
    if mode not in {"NORMAL", "MAINTENANCE"}:
        raise ValueError("UNKNOWN_MODE")
    required = {
        "equipment": equipment,
        "material": material,
        "operation" if mode == "NORMAL" else "maintenance": operation
        if mode == "NORMAL"
        else maintenance,
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        return {"status": "OWNER_INPUT_REQUIRED", "mode": mode, "missing": missing, "bbox_mm": None}
    rectangles = [r for group in required.values() for r in (group or [])]
    if not rectangles or any(
        len(r) != 4 or any(type(x) is not int for x in r) or r[2] <= r[0] or r[3] <= r[1]
        for r in rectangles
    ):
        raise ValueError("INVALID_EXPLICIT_ENVELOPE")
    return {
        "status": "HYPOTHETICAL_OFFLINE_SCREENING",
        "mode": mode,
        "bbox_mm": [
            min(r[0] for r in rectangles),
            min(r[1] for r in rectangles),
            max(r[2] for r in rectangles),
            max(r[3] for r in rectangles),
        ],
        "project_approved": False,
        "limitation": (
            "Necessary extents only; no containment, access, collision or full feasibility PASS"
        ),
    }


def source_audit() -> dict[str, Any]:
    paths = [
        "backend/src/cold_storage/modules/layout/infrastructure/global_cp_sat_model.py",
        "backend/src/cold_storage/modules/layout/application/layout_authority_binding.py",
        "backend/src/cold_storage/modules/layout/application/dimension_handoff.py",
        "backend/src/cold_storage/modules/layout/domain/dimension_handoff.py",
        "backend/src/cold_storage/modules/layout/domain/dimensioning.py",
        "backend/src/cold_storage/modules/layout/domain/placement.py",
        "docs/tasks/V2_2_2-version-plan.md",
        "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md",
        "docs/tasks/V2_2_2-P0C-golden-layout-abstraction-and-calibration.md",
        "docs/tasks/V2_2_2-multi-structural-construction-stage-b.md",
        "docs/architecture/ADR-047-process-flow-layout-regularity-authority.md",
        "docs/architecture/ADR-049-whole-building-group-band-composition.md",
        "docs/architecture/ADR-050-structural-hard-interface-projection.md",
        "backend/tests/unit/test_v22_p1d3_hybrid_handoff.py",
    ]
    model = REPO / paths[0]
    source = model.read_text()
    tree = ast.parse(source)
    global_class = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GlobalModel"
    )
    access = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AccessModel")
    guard = next(
        n
        for n in ast.walk(global_class)
        if isinstance(n, ast.If)
        and "UNMODELED_FLEXIBLE_DIMENSION_RULE" in (ast.get_source_segment(source, n) or "")
        and "aspect_ratio_bounds" in (ast.get_source_segment(source, n.test) or "")
    )
    return {
        "reference_head": REFERENCE,
        "files": {p: sha(REPO / p) for p in paths},
        "GlobalModel_line": global_class.lineno,
        "AccessModel_line": access.lineno,
        "unsupported_rule_guard_line": guard.lineno,
        "guard_fields": [
            n.value
            for n in ast.walk(guard.test)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ],
        "guard_preserved": True,
        "production_code_imported": False,
        "cause": (
            "Nominal integer dimensions begin at1mm; product area lower "
            "bound; rotation/site/interfaces restrict rest. Function-specific "
            "use constraints absent."
        ),
        "constraint_inheritance": (
            "AccessModel inherits GlobalModel and calls super().__init__; "
            "this task only inspects source"
        ),
    }


def build(directory: Path = HERE) -> dict[str, Any]:
    sources = json.loads((directory / "engineering-sources.json").read_text())
    by_id = {s["ID"]: s for s in sources["sources"]}
    baseline_sources = json.loads((BASELINE / "sources.json").read_text())
    baseline_manifest = json.loads((BASELINE / "source_manifest.json").read_text())["files"]
    for name in ["facts.json", "rooms.csv", "sources.json", "inputs/server_authorities.json"]:
        assert sha(BASELINE / name) == baseline_manifest[name]["sha256"]
    authority = json.loads((BASELINE / "inputs/server_authorities.json").read_text())
    rows = authority["p1_handoff"]["p1e_historical_handoff"]["dimension_handoff"]["authorities"]
    authorities = {r["zone_code"]: r for r in rows if r["zone_code"] in ROOMS}
    for role, a in authorities.items():
        assert a["dimension_mode"] == "FLEXIBLE_RECTANGLE"
        assert all(
            a[k] is None
            for k in [
                "min_width_m",
                "min_depth_m",
                "max_width_m",
                "max_depth_m",
                "aspect_ratio_bounds",
            ]
        )
        assert (
            Fraction(a["required_area_m2"])
            == {"office": 60, "changing_room": 40, "coating_room": 80}[role]
        )
    desk = by_id["S05"]["numeric_facts"]
    locker = by_id["S06"]["numeric_facts"]
    wrapper = by_id["S09"]["numeric_facts"]
    impacts = []
    for record in baseline_sources["candidates"]:
        path = BASELINE / record["input"]
        assert sha(path) == record["projection_sha256"]
        candidate = json.loads(path.read_text())
        p = candidate["provenance"]
        for z in candidate["engineering_validation"]["zones"]:
            role = z["zone_code"]
            if role not in ROOMS:
                continue
            w, d = mm(z["width_m"]), mm(z["depth_m"])
            if z["rotation_deg"] == 90:
                w, d = d, w
            elif z["rotation_deg"] != 0:
                raise ValueError("UNSUPPORTED_ROTATION")
            short, long = min(w, d), max(w, d)
            area = Fraction(w * d, 1000000)
            assert area == Fraction(z["actual_area_m2"])
            conditions = {
                "screening_only": True,
                "project_model_selected": False,
                "geometry_reference": (
                    "Assume geometric short side is an optimistic upper bound for a "
                    "usable rectangular cross-section; no wall/column deduction "
                    "invented"
                ),
                "actual_functional_pass": None,
                "formal_contract_violation": False,
            }
            if role == "office":
                missing = [
                    "STAFF_COUNT",
                    "FURNITURE_SELECTION",
                    "CHAIR_AND_PULLBACK_ENVELOPE",
                    "PASSAGE",
                    "DOORS_WINDOWS",
                    "WALLS_COLUMNS",
                    "MEETING_OR_DUTY_USE",
                ]
                risk = (
                    "Usable chair/passage space not evidenced by area; evaluate "
                    "actual workstation modules, not aspect alone"
                )
                conditions.update(
                    {
                        "source_ids": ["S05"],
                        "desk_along_long_axis_example": True,
                        "one_desk_remaining_cross_section_mm": short - desk["desk_depth_mm"],
                        "two_opposing_desks_remaining_cross_section_mm": short
                        - 2 * desk["desk_depth_mm"],
                        "remaining_is_not_clear_aisle": True,
                    }
                )
            elif role == "changing_room":
                missing = [
                    "PEAK_SHIFT_COUNT",
                    "SIMULTANEOUS_CHANGE_COUNT",
                    "STORAGE_USERS",
                    "LOCKER_MODEL_AND_COUNT",
                    "CLEAN_DIRTY_CLOTHING_POLICY",
                    "DOOR_SWEEP",
                    "FRONT_SERVICE_ZONE",
                    "BENCH_AND_AISLE",
                    "HYGIENE_FUNCTIONS",
                ]
                risk = (
                    "Cabinet placement and simultaneous change/hygiene space require "
                    "review; narrow short side is not a proved Authority violation"
                )
                conditions.update(
                    {
                        "source_ids": ["S01", "S06"],
                        "cabinet_rows_along_opposite_long_walls": True,
                        "single_row_remaining_before_all_clearances_mm": short
                        - locker["locker_depth_mm"],
                        "double_row_remaining_before_all_clearances_mm": short
                        - 2 * locker["locker_depth_mm"],
                        "double_row_furniture_alone_impossible_under_this_scenario": short
                        < 2 * locker["locker_depth_mm"],
                        (
                            "zero_clearance_is_only_a_mathematical_lower_bound_not_a_permitted"
                            "_design"
                        ): True,
                    }
                )
            else:
                missing = [
                    "COATING_PROCESS_TYPE",
                    "OPERATOR_COUNT_AND_SHIFTS",
                    "PRODUCT_AND_PACKAGE",
                    "EQUIPMENT_MODELS_AND_COUNT",
                    "CAPACITY_AND_LINE",
                    "INSTALLATION_REVISION",
                    "OPERATION_ENVELOPE",
                    "MAINTENANCE_ENVELOPE",
                    "MATERIAL_FLOW_ENVELOPE",
                    "PORTAL_ENDPOINTS",
                    "HEIGHT_UTILITIES",
                ]
                risk = (
                    "Long room may serve a line, but width cannot be certified "
                    "without chosen process, equipment and operating states"
                )
                conditions.update(
                    {
                        "source_ids": ["S07", "S08", "S09"],
                        "if_pallet_wrap_Base_Std_19_02_E_across_short_side": True,
                        "remaining_after_bare_machine_E_mm": short - wrapper["base_std_E_mm"],
                        "bare_fit_is_not_installation_or_process_fit": True,
                        "operation_clearance_not_automatically_added_to_all_sides": True,
                    }
                )
            impacts.append(
                {
                    "candidate_id": p["candidate_id"],
                    "zone_code": role,
                    "source_head": p["source_head"],
                    "source_geometry_hash": p["geometry_hash"],
                    "major_family_hash": p["family_hash"],
                    "v2_counted": p["v2_counted"],
                    "source_raw_candidate_sha256": p["raw_candidate_sha256"],
                    "actual_area_m2": text(area),
                    "physical_width_m": text(Fraction(w, 1000)),
                    "physical_depth_m": text(Fraction(d, 1000)),
                    "short_side_m": text(Fraction(short, 1000)),
                    "long_side_m": text(Fraction(long, 1000)),
                    "aspect_ratio": text(Fraction(long, short)),
                    "aspect_exact": str(Fraction(long, short)),
                    "rotation_deg": z["rotation_deg"],
                    "current_authority": authorities[role],
                    "STAFF_COUNT": "UNAVAILABLE",
                    "current_area_requirement_met": area
                    >= Fraction(authorities[role]["required_area_m2"]),
                    "classification": "ENGINEERING_RISK",
                    "risk": risk,
                    "missing_use_conditions": missing,
                    "requested_owner_inputs": missing,
                    "conditional_screening": {
                        "status": "HYPOTHETICAL_OFFLINE_SCREENING",
                        **conditions,
                    },
                }
            )
    assert len(impacts) == 24
    requirements = {}
    for role in ROOMS:
        row = next(r for r in impacts if r["zone_code"] == role)
        requirements[role] = {
            "status": "OWNER_INPUT_REQUIRED",
            "calibration_status": "NUMERIC_CALIBRATION_NOT_READY",
            "current_area_authority_m2": authorities[role]["required_area_m2"],
            "current_area_basis": "GEOMETRIC_RECTANGLE; clear/axis/gross basis not specified",
            "staff_count": None,
            "functional_minimum_short_side_m": None,
            "functional_minimum_depth_m": None,
            "recommended_aspect_ratio_range": None,
            "missing_inputs": row["missing_use_conditions"],
            "current_authority": authorities[role],
            "formal_threshold_approved": False,
            "condition_for_hard": (
                "Applicable requirement plus verified project inputs, dimension "
                "basis and Owner approval; separate solver-consumption "
                "implementation required"
            ),
            "reasonable_exceptions": (
                "Purposeful line-shaped room or site-constrained form may be "
                "acceptable only with evidenced functional envelopes and all "
                "existing engineering validation; no aspect-only rejection"
            ),
            "if_missing": (
                "OWNER_INPUT_REQUIRED / NUMERIC_CALIBRATION_NOT_READY; no new functional PASS"
            ),
        }
    proposals = {
        "status": "ENGINEERING_PROPOSAL_NOT_APPROVED_NOT_IMPLEMENTED",
        "calibration_status": "NUMERIC_CALIBRATION_NOT_READY",
        "version": VERSION,
        "numeric_calibration_ready": False,
        "formal_thresholds_frozen": False,
        "universal_minimum_width_m": None,
        "universal_recommended_aspect_ratio": None,
        "office": {
            "formula": (
                "W_clear >= rows*(desk_depth + user_zone) + independent_aisle + "
                "side_storage; L_clear >= ceil(N_staff/rows)*desk_width "
                "+2*end_space"
            ),
            "conditions": (
                "Separate non-overlapping user/passage lanes assumed; different "
                "actual furniture layouts need their own envelope, not this "
                "module as a universal hard bound"
            ),
            "source_ids": ["S03", "S05", "S10", "S11"],
            "N_staff": None,
        },
        "changing_room": {
            "formula": (
                "units=ceil(storage_users/slots_per_unit); "
                "columns=ceil(units/rows); L_clear >= "
                "columns*locker_width+2*end_space; W_clear >= "
                "rows*locker_depth+front_service_zone+bench+independent_aisle"
            ),
            "front_service_zone": (
                "Project envelope for door movement, changing users and any "
                "approved sharing. Never use max() to assume simultaneous overlap "
                "safe. Peak shift, stored-clothes users and simultaneous users "
                "are different inputs."
            ),
            "source_ids": ["S01", "S06", "S10", "S11"],
        },
        "coating_room": {
            "normal": "U_equipment union U_operation union U_material_flow",
            "maintenance": (
                "U_equipment union U_maintenance union U_material_flow_if_that_state_requires_it"
            ),
            "condition": (
                "All sets project-bound in a common local frame; absence is not "
                "an empty envelope. Assess both states; overlap/shutdown "
                "assumptions need explicit approval."
            ),
            "source_ids": ["S01", "S07", "S08", "S09", "S11"],
            "selected_process_or_model": None,
        },
        "A_to_G": {
            "A": (
                "Retain existing60/40/80m2 authority; clarify area reference "
                "before deriving net needs"
            ),
            "B": (
                "Minimum short side is derived from an approved functional "
                "arrangement, not a default scalar"
            ),
            "C": (
                "Minimum local depth depends on chosen arrangement/orientation and actual envelopes"
            ),
            "D": (
                "Recommended aspect range UNAVAILABLE pending comparable positive functional cases"
            ),
            "E": "Equipment/personnel/door/column/hygiene arrangement must actually fit",
            "F": (
                "Evidence-backed long line or irregular-site solutions remain "
                "admissible; no beauty-only gate"
            ),
            "G": (
                "Missing inputs return OWNER_INPUT_REQUIRED; source unverified "
                "returns UNVERIFIED; no PASS"
            ),
        },
        "hypothetical_screening_counts": {
            "double_opposing_500mm_lockers_furniture_alone_impossible": sum(
                r["conditional_screening"].get(
                    "double_row_furniture_alone_impossible_under_this_scenario", False
                )
                for r in impacts
            ),
            "scope": (
                "Only two Changing rooms under the explicitly unselected S06 "
                "scenario; not project rejection or calibration"
            ),
        },
    }
    impact = {
        "version": VERSION,
        "reference_head": REFERENCE,
        "room_count": 24,
        "physical_geometries": 8,
        "meaningful_constructions": 6,
        "major_families": 4,
        "p2d_full_pass": 0,
        "numeric_calibration_ready": False,
        "no_new_engineering_acceptance": True,
        "rooms": impacts,
    }
    for filename, value in [
        ("functional-room-requirements.json", requirements),
        ("dimension-calibration-proposal.json", proposals),
        ("existing-layout-impact.json", impact),
        ("code-audit.json", source_audit()),
    ]:
        (directory / filename).write_bytes(encode(value))
    with (directory / "existing-layout-impact.csv").open("w", newline="") as stream:
        keys = [
            "candidate_id",
            "zone_code",
            "actual_area_m2",
            "short_side_m",
            "long_side_m",
            "aspect_ratio",
            "major_family_hash",
            "classification",
        ]
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(impacts)
    baseline_files = [
        "facts.json",
        "rooms.csv",
        "sources.json",
        "source_manifest.json",
        "inputs/server_authorities.json",
    ] + [r["input"] for r in baseline_sources["candidates"]]
    (directory / "baseline-integrity.json").write_bytes(
        encode(
            {
                "baseline_reference_head": REFERENCE,
                "files": {
                    str((BASELINE / p).relative_to(REPO)): sha(BASELINE / p) for p in baseline_files
                },
                "all_source_projections_match_sealed_manifest": True,
                "no_source_geometries_edited": True,
                "source_count": 8,
            }
        )
    )
    return impact


if __name__ == "__main__":
    build()
