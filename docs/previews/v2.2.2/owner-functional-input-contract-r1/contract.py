"""OwnerFactoryFunctionalInputsV1: offline facts/arithmetic, not production authority."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
IDENTITY = "OwnerFactoryFunctionalInputsV1"
VERSION = "owner-factory-functional-inputs@1.0.0"
TASK = "V2_2_2_OWNER_FACTORY_FUNCTIONAL_INPUT_CONTRACT_R1"
REFERENCE = "f1b284f94f153153c8b67d5eb963bc7378056aaa"
CONFIRMATION_DATE = "2026-10-19"

# Only values explicitly confirmed in this task; no inferred size-class thresholds.
CONFIRMED: tuple[tuple[str, Any, str, str], ...] = (
    ("OFFICE_DESIGN_STAFF.SMALL", 12, "people", "Explicitly selected SMALL factory"),
    ("OFFICE_DESIGN_STAFF.MEDIUM", 20, "people", "Explicitly selected MEDIUM factory"),
    ("OFFICE_DESIGN_STAFF.LARGE", 30, "people", "Explicitly selected LARGE factory"),
    ("PACKAGING_PIECES_PER_PERSON_HOUR", 15, "pieces/person/hour", "Packaging staff"),
    ("PACKAGING_WEIGHT_PER_PIECE_KG", "1.6", "kg/piece", "Packaged-product mass"),
    ("SHIFT_HOURS", 8, "hours/shift", "Each of the two packaging shifts"),
    ("SHIFTS_PER_DAY", 2, "shifts/day", "Separate staffing per shift"),
    ("PACKAGING_WORK_HOURS_PER_DAY", 16, "hours/day", "Facility packaging schedule only"),
    ("PERSON_SHIFT_CAPACITY_KG", 192, "kg/person/shift", "15 * 1.6 * 8; not per-person day"),
    ("PACKAGING_MASS_BASIS", "PACKAGED_PRODUCT_MASS", "enum", "Both shift inputs"),
    ("SHIFT_ALLOCATION_POLICY", "EXPLICIT_INPUT_REQUIRED", "enum", "No default equal split"),
    ("CHANGING_ROOM_USERS", "PACKAGING_WORKERS_ONLY", "enum", "No other jobs included"),
    ("SHIFT_CHANGE_POLICY", "NON_OVERLAPPING", "enum", "Two shifts do not change together"),
    ("PERSONAL_LOCKER_PER_EMPLOYEE", 1, "locker/employee", "One per distinct shift employee"),
    ("LOCKER_SHARED_BETWEEN_SHIFTS", False, "boolean", "Separate employee sets per shift"),
    ("LOCKER_INTERNAL_SEPARATION", True, "boolean", "Inside each personal locker"),
    (
        "INTERNAL_STORAGE",
        "WORK_CLOTHES_AND_PERSONAL_CLOTHES_SEPARATE",
        "enum",
        "Internal segregation does not double locker count",
    ),
    ("LOCKER_COUNT_FORMULA", "SHIFT_1_WORKERS + SHIFT_2_WORKERS", "expression", "Two shifts"),
    (
        "SIMULTANEOUS_CHANGING_USERS_FORMULA",
        "max(SHIFT_1_WORKERS, SHIFT_2_WORKERS)",
        "expression",
        "Whole-shift changing; no intra-shift staggering assumed",
    ),
    (
        "GENDER_INDEPENDENT_ZONING_PRESET",
        False,
        "boolean",
        "Owner business preference only; professional hygiene/privacy review still required",
    ),
    ("ZONE_CODE", "coating_room", "zone_code", "Existing role identity retained"),
    ("PROCESS_TYPE", "PACKAGING_BOX_FILM_SEALING", "enum", "Not fruit wax/pallet wrapping"),
    ("ROOM_TYPE", "INDEPENDENT", "enum", "Existing coating_room"),
    (
        "PROCESS_SEQUENCE",
        ["SORTING_PACKAGING", "SECONDARY_PRECOOLING", "COATING_ROOM", "FINISHED_GOODS"],
        "ordered_roles",
        "No process reordering or new room implied",
    ),
    ("DESIGN_FILM_SEALING_RATIO", "1.0", "fraction", "All entering packaged product at design"),
    ("ACTUAL_FILM_SEALING_RATIO", "PROJECT_DEPENDENT", "policy", "Not a design-load reduction"),
    ("NON_SEALING_PRODUCT_PASS_THROUGH_ALLOWED", True, "boolean", "Inside coating_room"),
    ("PASS_THROUGH_MUST_USE_SEALING_EQUIPMENT", False, "boolean", "No equipment processing"),
    ("INDEPENDENT_BYPASS_ROOM_ASSUMED", False, "boolean", "No extra bypass room default"),
    ("SEALING_RUNTIME_INHERITS_PACKAGING_HOURS", False, "boolean", "Confirm separately"),
    ("OFFICE_AREA_AUTHORITY", 60, "m2", "Existing P1 geometric area unchanged"),
    ("CHANGING_AREA_AUTHORITY", 40, "m2", "Existing P1 geometric area unchanged"),
    ("COATING_AREA_AUTHORITY", 80, "m2", "Existing P1 geometric area unchanged"),
)

PROTECTED = (
    "backend/src/cold_storage/modules/calculations/domain/zone_planning.py",
    "backend/src/cold_storage/modules/layout/domain/dimension_handoff.py",
    "backend/src/cold_storage/modules/layout/domain/adjacency.py",
    "backend/src/cold_storage/modules/layout/infrastructure/global_cp_sat_model.py",
    "docs/tasks/V2_1_2-patch-release-closure-readiness.md",
    "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md",
    "docs/tasks/V2_2_2-version-plan.md",
    "docs/previews/v2.2.2/stage-b/layout-quality-baseline-01/inputs/server_authorities.json",
    "docs/previews/v2.2.2/functional-room-dimension-calibration-01/source_manifest.json",
)


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def confirmed_records() -> list[dict[str, Any]]:
    return [
        {
            "FIELD_NAME": name,
            "VALUE": value,
            "UNIT": unit,
            "SOURCE": "OWNER_CONFIRMED",
            "CONFIRMATION_DATE": CONFIRMATION_DATE,
            "APPLICABILITY": applies,
            "CONTRACT_VERSION": VERSION,
        }
        for name, value, unit, applies in CONFIRMED
    ]


def values() -> dict[str, Any]:
    return {name: value for name, value, _, _ in CONFIRMED}


def missing(fields: list[str]) -> dict[str, Any]:
    return {"status": "OWNER_INPUT_REQUIRED", "missing_inputs": fields, "result": None}


def exact(value: str | int | Decimal, *, field: str) -> Fraction:
    # Binary float, bool, non-finite and negative quantities are never silently rounded.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f"INVALID_EXACT_NONNEGATIVE_INPUT:{field}")
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"INVALID_EXACT_NONNEGATIVE_INPUT:{field}") from error
    if result < 0:
        raise ValueError(f"INVALID_EXACT_NONNEGATIVE_INPUT:{field}")
    return result


def rational(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def capacity_per_shift() -> Fraction:
    v = values()
    result = (
        Fraction(v["PACKAGING_PIECES_PER_PERSON_HOUR"])
        * Fraction(v["PACKAGING_WEIGHT_PER_PIECE_KG"])
        * Fraction(v["SHIFT_HOURS"])
    )
    assert result == v["PERSON_SHIFT_CAPACITY_KG"]
    return result


def office(factory_size: str | None) -> dict[str, Any]:
    sizes = {size: values()["OFFICE_DESIGN_STAFF." + size] for size in ("SMALL", "MEDIUM", "LARGE")}
    if factory_size not in sizes:
        return {**missing(["EXPLICIT_FACTORY_SIZE"]), "OFFICE_STAFF_STATUS": "OWNER_INPUT_REQUIRED"}
    return {
        "status": "OWNER_RULE_APPLIED_OFFLINE",
        "OFFICE_STAFF_STATUS": "OWNER_CONFIRMED",
        "factory_size": factory_size,
        "OFFICE_DESIGN_STAFF": sizes[factory_size],
        "unit": "people",
        "classification_thresholds": None,
        "area_authority_m2": 60,
        "functional_space_pass": None,
        "contract_version": VERSION,
    }


def staffing(
    *,
    shift_1_kg: str | int | Decimal | None,
    shift_2_kg: str | int | Decimal | None,
    mass_basis: str | None,
    mass_source: str | None,
    daily_packaged_kg: str | int | Decimal | None = None,
) -> dict[str, Any]:
    absent = []
    if shift_1_kg is None:
        absent.append("SHIFT_1_PACKAGING_KG")
    if shift_2_kg is None:
        absent.append("SHIFT_2_PACKAGING_KG")
    if mass_basis != "PACKAGED_PRODUCT_MASS":
        absent.append("PACKAGED_PRODUCT_MASS_BASIS_OR_VERIFIED_UPSTREAM_CONVERSION")
    if not isinstance(mass_source, str) or not mass_source.strip():
        absent.append("PACKAGING_PRODUCT_MASS_SOURCE")
    if absent:
        return missing(absent)
    assert shift_1_kg is not None and shift_2_kg is not None
    masses = [
        exact(v, field=f"SHIFT_{i}_PACKAGING_KG") for i, v in enumerate((shift_1_kg, shift_2_kg), 1)
    ]
    if daily_packaged_kg is not None:
        daily = exact(daily_packaged_kg, field="DAILY_PACKAGED_KG")
        if sum(masses) != daily:
            raise ValueError("SHIFT_PRODUCT_MASS_SUM_MISMATCH")
    capacity = capacity_per_shift()
    workers = []
    for mass in masses:
        quotient = mass / capacity
        workers.append((quotient.numerator + quotient.denominator - 1) // quotient.denominator)
    return {
        "status": "OFFLINE_BUSINESS_CALCULATION_ONLY",
        "contract_version": VERSION,
        "input": {
            "shift_1_packaging_kg": rational(masses[0]),
            "shift_2_packaging_kg": rational(masses[1]),
            "mass_basis": mass_basis,
            "mass_source": mass_source,
        },
        "source_reference_verification": "REFERENCE_RECORDED_NOT_FILE_AUTHENTICATED",
        "person_shift_capacity_kg": rational(capacity),
        "formulas": {
            "shift_workers": "ceil(shift_packaged_product_kg / (15 * 1.6 * 8))",
            "lockers": "shift_1_workers + shift_2_workers",
            "simultaneous_changing": "max(shift_1_workers, shift_2_workers)",
        },
        "SHIFT_1_WORKERS": workers[0],
        "SHIFT_2_WORKERS": workers[1],
        "LOCKER_COUNT": sum(workers),
        "SIMULTANEOUS_CHANGING_USERS": max(workers),
        "LOCKER_COUNT_UNIT": "independent_personal_lockers",
        "SHIFT_CHANGE_POLICY": "NON_OVERLAPPING",
        "LOCKER_INTERNAL_SEPARATION": True,
        "OTHER_JOB_USERS_ADDED": 0,
        "area_authority_m2": 40,
        "functional_space_pass": None,
        "hygiene_privacy_compliance": "PROFESSIONAL_REVIEW_REQUIRED",
    }


def film_sealing(
    *,
    entering_product_kg: str | int | Decimal | None,
    mass_source: str | None,
    actual_ratio: str | int | Decimal | None = None,
) -> dict[str, Any]:
    actual = (
        None if actual_ratio is None else exact(actual_ratio, field="ACTUAL_FILM_SEALING_RATIO")
    )
    if actual is not None and actual > 1:
        raise ValueError("ACTUAL_RATIO_OUTSIDE_ZERO_ONE")
    absent = []
    if entering_product_kg is None:
        absent.append("ENTERING_PACKAGED_PRODUCT_KG")
    if not isinstance(mass_source, str) or not mass_source.strip():
        absent.append("ENTERING_PACKAGED_PRODUCT_MASS_SOURCE")
    load = None
    if not absent:
        assert entering_product_kg is not None
        load = rational(exact(entering_product_kg, field="ENTERING_PRODUCT_KG"))
    return {
        "status": "OWNER_RULE_RECORDED_EQUIPMENT_INPUT_REQUIRED",
        "contract_version": VERSION,
        "PROCESS_TYPE": "PACKAGING_BOX_FILM_SEALING",
        "ROOM_TYPE": "INDEPENDENT",
        "mass_source": mass_source,
        "source_reference_verification": "REFERENCE_RECORDED_NOT_FILE_AUTHENTICATED",
        "DESIGN_FILM_SEALING_RATIO": "1.0",
        "design_load_kg": load,
        "ACTUAL_FILM_SEALING_RATIO": None if actual is None else rational(actual),
        "actual_ratio_status": "OWNER_INPUT_REQUIRED"
        if actual is None
        else "PROJECT_SCENARIO_ONLY",
        "NON_SEALING_PRODUCT_PASS_THROUGH_ALLOWED": True,
        "INDEPENDENT_BYPASS_ROOM_ASSUMED": False,
        "EQUIPMENT_MODEL": {"value": None, "status": "UNAVAILABLE"},
        "EQUIPMENT_CAPACITY": {"value": None, "status": "UNAVAILABLE"},
        "EQUIPMENT_COUNT": {"value": None, "status": "UNAVAILABLE"},
        "EQUIPMENT_ENVELOPE": {"value": None, "status": "UNAVAILABLE"},
        "EFFECTIVE_EQUIPMENT_RUNTIME_HOURS": {"value": None, "status": "OWNER_INPUT_REQUIRED"},
        "missing_inputs": [
            *absent,
            "EQUIPMENT_SELECTION_AND_STATE_ENVELOPES",
            "EFFECTIVE_EQUIPMENT_RUNTIME_HOURS",
        ],
        "area_authority_m2": 80,
        "functional_space_pass": None,
    }


def build() -> dict[str, Any]:
    v = values()
    header = {
        "identity": IDENTITY,
        "contract_version": VERSION,
        "task": TASK,
        "reference_head": REFERENCE,
    }
    requirements = [
        (
            "FACTORY_SIZE_CLASS_THRESHOLDS",
            "OWNER_INPUT_REQUIRED",
            "No throughput-derived class",
            "office",
        ),
        (
            "PROJECT_FACTORY_SIZE",
            "OWNER_INPUT_REQUIRED",
            "Explicit size choice; 12/20/30 are design staff",
            "office",
        ),
        (
            "SHIFT_PRODUCT_MASS_AND_SOURCE",
            "OWNER_INPUT_REQUIRED",
            "Two shift quantities, kg of packaged product",
            "staffing",
        ),
        (
            "UPSTREAM_YIELD_CONVERSION",
            "IF_RAW_MASS_USED_INPUT_REQUIRED",
            "Traceable product yield/mass balance",
            "staffing",
        ),
        (
            "OFFICE_FURNITURE_AND_AISLES",
            "OWNER_INPUT_REQUIRED",
            "Stations, furnishings, use envelopes, doors/windows",
            "office",
        ),
        (
            "LOCKER_MODEL_AND_DIMENSIONS",
            "UNAVAILABLE",
            "Assembled width/depth, internal separation, door sweep",
            "changing_room",
        ),
        (
            "CHANGING_OPERATION_AND_AISLES",
            "OWNER_INPUT_REQUIRED",
            "Whole-shift operation, bench and traffic envelopes",
            "changing_room",
        ),
        (
            "HYGIENE_PRIVACY_APPLICABILITY",
            "PROFESSIONAL_REVIEW_REQUIRED",
            "No preset gender split is not a compliance waiver",
            "changing_room",
        ),
        (
            "ACTUAL_FILM_SEALING_RATIO",
            "PROJECT_DEPENDENT",
            "Does not reduce design ratio 1.0",
            "coating_room",
        ),
        (
            "EQUIPMENT_MODEL",
            "UNAVAILABLE",
            "Packaging box film sealing model/revision",
            "coating_room",
        ),
        (
            "EQUIPMENT_CAPACITY",
            "UNAVAILABLE",
            "Rated/effective capacity and product/operating basis",
            "coating_room",
        ),
        (
            "EQUIPMENT_COUNT",
            "UNAVAILABLE",
            "Derived only after selected capacity/runtime",
            "coating_room",
        ),
        (
            "EQUIPMENT_ENVELOPE",
            "UNAVAILABLE",
            "Actual equipment geometry, not inferred from room area",
            "coating_room",
        ),
        (
            "EFFECTIVE_EQUIPMENT_RUNTIME_HOURS",
            "OWNER_INPUT_REQUIRED",
            "Independent of packaging 16h/day",
            "coating_room",
        ),
        (
            "FILM_SEALING_OPERATION_MAINTENANCE_MATERIAL_ENVELOPES",
            "OWNER_INPUT_REQUIRED",
            "Infeed/outfeed, staff, service and unsealed pass-through",
            "coating_room",
        ),
        (
            "CLEAR_SPACE_REFERENCE",
            "OWNER_INPUT_REQUIRED",
            "Geometric/axis/gross/finished-clear basis and deductions",
            "all_rooms",
        ),
        (
            "FUNCTIONAL_LAYOUT_AND_CONFLICT_REVIEW",
            "PROFESSIONAL_REVIEW_REQUIRED",
            "Personnel/material conflicts and applicable codes",
            "all_rooms",
        ),
    ]
    outputs: dict[str, Any] = {}
    outputs["owner-confirmed-business-rules.json"] = {
        **header,
        "confirmation_basis": (
            "Owner instruction in this conversation; no third-party standard approval implied"
        ),
        "confirmation_date_basis": (
            "Date this task's Owner confirmation was received, Asia/Shanghai"
        ),
        "status": "OWNER_BUSINESS_FACTS_CONFIRMED_NOT_PRODUCTION_AUTHORITY",
        "rules": confirmed_records(),
        "not_a_solver_grant": True,
        "professional_compliance_pass": False,
    }
    outputs["staffing-calculation-contract.json"] = {
        **header,
        "productivity_policy": "packaging-owner-two-shift@1.0.0",
        "inputs": [
            "SHIFT_1_PACKAGING_KG",
            "SHIFT_2_PACKAGING_KG",
            "PACKAGED_PRODUCT_MASS_BASIS",
            "PACKAGING_PRODUCT_MASS_SOURCE",
        ],
        "optional_consistency_input": "DAILY_PACKAGED_KG must equal both shift quantities added",
        "fixed_parameter_field_refs": [
            "PACKAGING_PIECES_PER_PERSON_HOUR",
            "PACKAGING_WEIGHT_PER_PIECE_KG",
            "SHIFT_HOURS",
            "SHIFTS_PER_DAY",
        ],
        "formulas": {
            "PERSON_SHIFT_CAPACITY_KG": (
                "15 pieces/person/hour * 1.6 kg/piece * 8 hours/shift = 192 kg/person/shift"
            ),
            "SHIFT_1_WORKERS": "ceil(SHIFT_1_PACKAGING_KG / 192)",
            "SHIFT_2_WORKERS": "ceil(SHIFT_2_PACKAGING_KG / 192)",
            "LOCKER_COUNT": "SHIFT_1_WORKERS + SHIFT_2_WORKERS",
            "SIMULTANEOUS_CHANGING_USERS": "max(SHIFT_1_WORKERS, SHIFT_2_WORKERS)",
            "PACKAGING_WORK_HOURS_PER_DAY": (
                "2 shifts/day * 8 hours/shift = 16 hours/day (facility schedule)"
            ),
        },
        "arithmetic": (
            "Exact rational quantities; ceil each shift separately; no binary-float rounding"
        ),
        "staffing_semantics": (
            "Independent shift employee sets; no lockers shared. "
            "No other job staff and no intra-shift changing batches."
        ),
        "missing_shift_allocation": (
            "OWNER_INPUT_REQUIRED; never infer equal allocation or derive a missing shift"
        ),
        "product_mass_rule": (
            "Raw inbound fruit is not packaged-product mass. "
            "A documented upstream conversion is needed; "
            "this offline module does not invent or calculate yield."
        ),
        "source_verification_limit": (
            "Requires and records an explicit mass-basis/reference; "
            "it does not authenticate external files or create server authority."
        ),
        "zero_mass": (
            "Zero assigned product yields zero packaging staff for that shift; "
            "not proof a real facility needs no other workers"
        ),
        "legacy_rule": {
            "person_daily_capacity_kg": 336,
            "document": "docs/tasks/V2_1_2-patch-release-closure-readiness.md:48",
            "frozen_fixture": (
                "docs/previews/v2.2.2/stage-b/layout-quality-baseline-01/"
                "inputs/server_authorities.json"
            ),
            "production_consumer": (
                "backend/src/cold_storage/modules/calculations/domain/zone_planning.py:"
                "_packing_person_daily_capacity_kg"
            ),
            "status": "PRESERVED_UNCHANGED_NOT_REPLACED",
            "future_activation": (
                "Separate Owner-authorized version selection, source binding, "
                "compatibility tests and explicit migration; never silent override"
            ),
        },
    }
    outputs["functional-room-input-contract.json"] = {
        **header,
        "kind": "DOCUMENTED_BUSINESS_INPUT_CONTRACT_NOT_REGISTERED_PUBLIC_API",
        "office": {
            "design_staff_by_explicit_size": {
                size: v["OFFICE_DESIGN_STAFF." + size] for size in ("SMALL", "MEDIUM", "LARGE")
            },
            "size_class_thresholds": None,
            "unknown_size": "OFFICE_STAFF_STATUS=OWNER_INPUT_REQUIRED",
            "future_check": (
                "People, workstations, equipment, doors/windows and clear circulation; "
                "not area/person inference"
            ),
            "area_authority_m2": 60,
        },
        "changing_room": {
            "users": v["CHANGING_ROOM_USERS"],
            "shift_change_policy": v["SHIFT_CHANGE_POLICY"],
            "lockers_per_employee": 1,
            "shared_between_shifts": False,
            "internal_work_personal_clothing_separation": True,
            "locker_formula": v["LOCKER_COUNT_FORMULA"],
            "simultaneous_formula": v["SIMULTANEOUS_CHANGING_USERS_FORMULA"],
            "intra_shift_staggering_assumed": False,
            "gender_independent_zoning_preset": False,
            "hygiene_privacy_review": "PROFESSIONAL_REVIEW_REQUIRED",
            "area_authority_m2": 40,
        },
        "coating_room": {
            "zone_code": "coating_room",
            "process_type": v["PROCESS_TYPE"],
            "room_type": "INDEPENDENT",
            "process_sequence": v["PROCESS_SEQUENCE"],
            "existing_zone_sequence": [
                "sorting_packaging_room",
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
            ],
            "design_film_sealing_ratio": "1.0",
            "actual_film_sealing_ratio": {"value": None, "status": "PROJECT_DEPENDENT"},
            "non_sealing_pass_through": {
                "allowed": True,
                "inside_same_room": True,
                "uses_sealing_equipment": False,
                "independent_bypass_room_assumed": False,
            },
            "required_checks": [
                "EQUIPMENT",
                "INFEED_OUTFEED",
                "OPERATOR",
                "MAINTENANCE",
                "NON_SEALING_PRODUCT_PASS_THROUGH",
                "PERSONNEL_MATERIAL_CONFLICTS",
            ],
            "equipment_model": {"value": None, "status": "UNAVAILABLE"},
            "equipment_capacity": {"value": None, "status": "UNAVAILABLE"},
            "equipment_count": {"value": None, "status": "UNAVAILABLE"},
            "equipment_envelope": {"value": None, "status": "UNAVAILABLE"},
            "effective_runtime_hours": {
                "value": None,
                "status": "OWNER_INPUT_REQUIRED",
                "inherits_packaging_16h": False,
            },
            "area_authority_m2": 80,
        },
        "all_rooms": {
            "functional_dimension_thresholds": None,
            "functional_space_pass": None,
            "code_compliance_pass": None,
        },
        "numeric_calibration_ready": False,
        "source_binding": (
            "All confirmed values resolve to FIELD_NAME in owner-confirmed-business-rules.json; "
            "no production P1 hash rebinding this task"
        ),
    }
    outputs["unresolved-engineering-inputs.json"] = {
        **header,
        "numeric_calibration_ready": False,
        "inputs": [
            {
                "FIELD_NAME": field,
                "VALUE": None,
                "STATUS": status,
                "REQUIRED_EVIDENCE": evidence,
                "APPLICABILITY": room,
                "CONTRACT_VERSION": VERSION,
            }
            for field, status, evidence, room in requirements
        ],
        "not_blocking_offline_business_arithmetic": True,
        "blocks_functional_space_acceptance": True,
    }
    scenario = {
        "mass_basis": "PACKAGED_PRODUCT_MASS",
        "mass_source": "SYNTHETIC_EXAMPLE_EXPLICIT_PACKAGED_PRODUCT_QUANTITIES",
    }
    outputs["calculation-examples.json"] = {
        **header,
        "status": "SYNTHETIC_EXAMPLES_NOT_REAL_FACTORY_INPUT",
        "equal_split_is_example_only": True,
        "examples": [
            {
                "name": "EXPLICIT_EQUAL_1000_KG",
                "allocation_source": (
                    "Example author explicitly chooses 500+500, not a contract default"
                ),
                "output": staffing(
                    shift_1_kg=500, shift_2_kg=500, daily_packaged_kg=1000, **scenario
                ),
            },
            {
                "name": "EXPLICIT_UNEQUAL_SAME_1000_KG",
                "allocation_source": "Example author explicitly chooses 800+200",
                "output": staffing(
                    shift_1_kg=800, shift_2_kg=200, daily_packaged_kg=1000, **scenario
                ),
            },
            {
                "name": "SHIFT_ALLOCATION_MISSING",
                "output": staffing(
                    shift_1_kg=None, shift_2_kg=None, daily_packaged_kg=1000, **scenario
                ),
            },
            {
                "name": "RAW_MASS_NOT_CONVERTED",
                "output": staffing(
                    shift_1_kg=500,
                    shift_2_kg=500,
                    mass_basis="RAW_INBOUND_FRUIT",
                    mass_source="EXAMPLE_RAW_FRUIT_RECORD",
                ),
            },
            {
                "name": "PACKAGED_MASS_SOURCE_MISSING",
                "output": staffing(
                    shift_1_kg=500,
                    shift_2_kg=500,
                    mass_basis="PACKAGED_PRODUCT_MASS",
                    mass_source=None,
                ),
            },
            {
                "name": "OFFICE_EXPLICIT_CLASSES",
                "outputs": [office(size) for size in ("SMALL", "MEDIUM", "LARGE", None)],
            },
            {
                "name": "FILM_ACTUAL_HALF_DESIGN_ALL",
                "output": film_sealing(
                    entering_product_kg=1000,
                    mass_source=scenario["mass_source"],
                    actual_ratio="0.5",
                ),
            },
        ],
    }
    outputs["historical-integrity.json"] = {
        **header,
        "protected_source_files_sha256": {name: sha(REPO / name) for name in PROTECTED},
        "area_authority_m2": {"office": 60, "changing_room": 40, "coating_room": 80},
        "engineering_authority_changed": False,
        "historical_336_rule_changed": False,
        "p0_process_authority_changed": False,
        "d04_rounds_changed": False,
        "p3_historical_unknown_count": 262,
        "production_consumer_implemented": False,
    }
    for name, value in outputs.items():
        (HERE / name).write_bytes(encoded(value))
    return outputs


if __name__ == "__main__":
    build()
