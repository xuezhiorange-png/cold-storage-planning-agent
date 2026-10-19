"""Versioned Owner V2 business arithmetic only; no production P1 area activation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
V1 = HERE.parent / "owner-functional-input-contract-r1"
READINESS = HERE.parent / "owner-factory-p1-compatibility-readiness-r1"
TASK = "V2_2_2_OWNER_FACTORY_FUNCTIONAL_INPUT_CONTRACT_R2"
IDENTITY = "OwnerFactoryFunctionalInputsV2"
VERSION = "owner-factory-functional-inputs@2.0.0"
REFERENCE = "3787008de1206797dc098d42f420730590bfe929"
CONFIRMATION_DATE = "2026-10-19"


def encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_previous(folder: Path, script: str) -> Any:
    for name, digest in json.loads((folder / "source_manifest.json").read_text())["files"].items():
        if sha(folder / name) != digest:
            raise ValueError("HISTORICAL_SOURCE_INTEGRITY_MISMATCH")
    spec = importlib.util.spec_from_file_location("offline_" + folder.name, folder / script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def business_rules() -> dict[str, Any]:
    old = json.loads((V1 / "owner-confirmed-business-rules.json").read_text())
    records = []
    for original in old["rules"]:
        record = {
            **original,
            "CONTRACT_VERSION": VERSION,
            "CONFIRMATION_DATE": CONFIRMATION_DATE,
            "INHERITED_FROM": {
                "identity": old["identity"],
                "version": old["contract_version"],
                "field": original["FIELD_NAME"],
            },
        }
        if record["FIELD_NAME"] == "SHIFT_ALLOCATION_POLICY":
            record.update(
                VALUE="DEFAULT_EQUAL_SPLIT",
                APPLICABILITY="V2 only; requires sourced packaged-product daily mass",
            )
            record["REVISION_FROM"] = original["VALUE"]
        records.append(record)
    additions = (
        ("SHIFT_1_RATIO", "0.5", "fraction", "V2 default mode only"),
        ("SHIFT_2_RATIO", "0.5", "fraction", "V2 default mode only"),
        ("EXPLICIT_SHIFT_OVERRIDE_ALLOWED", True, "boolean", "Both shift quantities supplied"),
        ("WORKERS_PER_PACKING_TABLE", 3, "people/table", "Owner V2 business policy"),
        (
            "PACKING_TABLE_SHARED_BETWEEN_SHIFTS",
            True,
            "boolean",
            "Same station set; engineering turnover review remains",
        ),
        (
            "PACKING_TABLE_CAPACITY_POLICY",
            "PEAK_CONCURRENT_WORKERS",
            "enum",
            "max(N1,N2), not total employees",
        ),
        (
            "PACKING_TABLE_COUNT_FORMULA",
            "ceil(max(N1,N2)/3)",
            "expression",
            "Required tables, not layout n_actual cells",
        ),
        (
            "EXPLICIT_SHIFT_OVERRIDE_MODE",
            "EXPLICIT_SHIFT_OVERRIDE",
            "enum",
            "No default ratios applied",
        ),
    )
    for field, value, unit, applies in additions:
        records.append(
            {
                "FIELD_NAME": field,
                "VALUE": value,
                "UNIT": unit,
                "SOURCE": "OWNER_CONFIRMED",
                "CONFIRMATION_DATE": CONFIRMATION_DATE,
                "APPLICABILITY": applies,
                "CONTRACT_VERSION": VERSION,
            }
        )
    return {
        "identity": IDENTITY,
        "contract_version": VERSION,
        "task": TASK,
        "reference_head": REFERENCE,
        "confirmation_date_basis": (
            "Owner task received 2026-10-19 Asia/Shanghai; not retrospective project approval"
        ),
        "status": "OWNER_BUSINESS_POLICY_CONFIRMED_NOT_PRODUCTION_P1",
        "v1_original_rules_sha256": sha(V1 / "owner-confirmed-business-rules.json"),
        "rules": records,
    }


def rational(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def ceil_exact(value: Fraction) -> int:
    return (value.numerator + value.denominator - 1) // value.denominator


def source_check(
    request: dict[str, Any],
    evidence_root: Path,
    mode: str,
    masses: tuple[Fraction, Fraction, Fraction],
) -> tuple[dict[str, Any] | None, str]:
    if any(key in request for key in ("verified", "authoritative", "authority_token")):
        return None, "CALLER_AUTHORITY_ASSERTION_NOT_ACCEPTED"
    if request.get("mass_basis") != "PACKAGED_PRODUCT_MASS":
        return None, "PACKAGED_PRODUCT_MASS_REQUIRED_NO_RAW_DEFAULT"
    ref = request.get("mass_source")
    if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
        return None, "PACKAGED_MASS_SOURCE_REQUIRED"
    digest = ref.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return None, "ACTUAL_SOURCE_CONTENT_HASH_REQUIRED"
    relative = Path(ref["path"])
    path = (evidence_root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(evidence_root.resolve()):
        return None, "SOURCE_PATH_OUTSIDE_OFFLINE_EVIDENCE_ROOT"
    if not path.is_file():
        return None, "SOURCE_FILE_MISSING"
    if sha(path) != digest:
        return None, "SOURCE_CONTENT_HASH_MISMATCH"
    try:
        body = json.loads(path.read_text())
    except (ValueError, UnicodeError):
        return None, "SOURCE_JSON_INVALID"
    if not isinstance(body, dict):
        return None, "SOURCE_RECORD_INVALID"
    if body.get("mass_basis") != "PACKAGED_PRODUCT_MASS" or body.get("unit") != "kg":
        return None, "SOURCE_NOT_PACKAGED_PRODUCT_KG"
    if mode == "DEFAULT_EQUAL_SPLIT" and any(
        body.get(key) is not None for key in ("shift_1_packaging_kg", "shift_2_packaging_kg")
    ):
        return None, "SOURCE_EXPLICIT_SHIFT_DATA_REQUIRES_EXPLICIT_REQUEST"
    for key in ("project_id", "period_id"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            return None, "PROJECT_AND_PERIOD_REQUIRED"
        if request[key] != body.get(key):
            return None, "SOURCE_PROJECT_OR_PERIOD_MISMATCH"
    exact = load_previous(V1, "contract.py").exact
    required = (
        {"daily_packaged_kg": masses[0]}
        if mode == "DEFAULT_EQUAL_SPLIT"
        else {"shift_1_packaging_kg": masses[1], "shift_2_packaging_kg": masses[2]}
    )
    # If the source also states a daily amount, it may not contradict the shift sum.
    if body.get("daily_packaged_kg") is not None:
        required["daily_packaged_kg"] = masses[0]
    for key, expected in required.items():
        if body.get(key) is None:
            return None, "SOURCE_QUANTITY_MISSING"
        try:
            if exact(body[key], field=key) != expected:
                return None, "SOURCE_QUANTITY_MISMATCH"
        except ValueError:
            return None, "INVALID_SOURCE_QUANTITY"
    return body, "LOCAL_CONTENT_MATCH_NOT_PROJECT_APPROVAL"


def seal_result(body: dict[str, Any]) -> dict[str, Any]:
    return {
        **body,
        "offline_result_sha256": hashlib.sha256(encode(body)).hexdigest(),
        "hash_scope": (
            "Offline V2 business result, never a production P1 canonical Hash or approval"
        ),
    }


def calculate(request: dict[str, Any], *, evidence_root: Path = HERE) -> dict[str, Any]:
    if request.get("contract_identity") != IDENTITY or request.get("contract_version") != VERSION:
        raise ValueError("EXPLICIT_OWNER_V2_IDENTITY_AND_VERSION_REQUIRED")
    owner = load_previous(V1, "contract.py")
    rules = business_rules()
    rule_values = {row["FIELD_NAME"]: row["VALUE"] for row in rules["rules"]}
    capacity = (
        Fraction(rule_values["PACKAGING_PIECES_PER_PERSON_HOUR"])
        * Fraction(rule_values["PACKAGING_WEIGHT_PER_PIECE_KG"])
        * Fraction(rule_values["SHIFT_HOURS"])
    )
    assert capacity == 192 == rule_values["PERSON_SHIFT_CAPACITY_KG"]
    common = {
        "identity": IDENTITY,
        "contract_version": VERSION,
        "request_identity": {
            "project_id": request.get("project_id"),
            "period_id": request.get("period_id"),
        },
        "owner_rule_file_sha256": hashlib.sha256(encode(rules)).hexdigest(),
        "person_shift_capacity_kg": rational(capacity),
        "production_p1_area_m2": None,
        "P1_AUTHORITY_PASS": False,
        "P1_AREA_CALIBRATION_READY": False,
        "P1_PRODUCTION_ACTIVATED": False,
        "source_approval_status": "NOT_ESTABLISHED_BY_OFFLINE_FILE_BINDING",
        "unapproved_spatial_values": {
            "new_functional_area_m2": {"office": None, "changing_room": None, "coating_room": None},
            "minimum_clear_width_m": None,
            "minimum_functional_depth_m": None,
            "aisle_clear_width_m": None,
            "status": "OWNER_INPUT_REQUIRED_OR_NUMERIC_CALIBRATION_NOT_APPROVED",
        },
    }

    def blocked(code: str) -> dict[str, Any]:
        return seal_result(
            {**common, "status": "BLOCKED_INPUT", "reason": code, "staffing_and_tables": None}
        )

    first, second, daily = (
        request.get(key)
        for key in ("shift_1_packaging_kg", "shift_2_packaging_kg", "daily_packaged_kg")
    )
    if (first is None) != (second is None):
        return blocked("PARTIAL_SHIFT_OVERRIDE_REJECTED_NO_REMAINDER_OR_DEFAULT")
    try:
        if first is not None and second is not None:
            mode = "EXPLICIT_SHIFT_OVERRIDE"
            q1 = owner.exact(first, field="SHIFT_1_PACKAGING_KG")
            q2 = owner.exact(second, field="SHIFT_2_PACKAGING_KG")
            q = q1 + q2
            if daily is not None and owner.exact(daily, field="DAILY_PACKAGED_KG") != q:
                return blocked("SHIFT_PRODUCT_MASS_SUM_MISMATCH")
            allocation_origin = "Project explicit shift allocation; no50/50 applied"
        else:
            mode = "DEFAULT_EQUAL_SPLIT"
            if daily is None:
                return blocked("DAILY_PACKAGED_PRODUCT_MASS_REQUIRED")
            q = owner.exact(daily, field="DAILY_PACKAGED_KG")
            q1, q2 = (
                q * Fraction(rule_values["SHIFT_1_RATIO"]),
                q * Fraction(rule_values["SHIFT_2_RATIO"]),
            )
            assert q1 + q2 == q
            allocation_origin = (
                "Owner V2 default ratios applied exactly to sourced daily product mass"
            )
    except ValueError:
        return blocked("INVALID_EXACT_NONNEGATIVE_PRODUCT_MASS")
    source, source_status = source_check(request, evidence_root, mode, (q, q1, q2))
    if source is None:
        return blocked(source_status)
    n1, n2 = ceil_exact(q1 / capacity), ceil_exact(q2 / capacity)
    peak = max(n1, n2)
    stations = ceil_exact(Fraction(peak, rule_values["WORKERS_PER_PACKING_TABLE"]))
    old_office = owner.office(request.get("factory_size"))
    return seal_result(
        {
            **common,
            "status": "OFFLINE_V2_BUSINESS_CALCULATION_ONLY",
            "allocation_mode": mode,
            "allocation_origin": allocation_origin,
            "allocation_source": {
                "packaged_product_mass_source": request["mass_source"],
                "daily_mass_origin": "EXPLICIT_DAILY_INPUT"
                if daily is not None
                else "SUM_OF_EXPLICIT_SOURCE_SHIFTS",
                "policy_version": VERSION,
                "project_override_source": request["mass_source"]
                if mode == "EXPLICIT_SHIFT_OVERRIDE"
                else None,
            },
            "mass_source_verification": source_status,
            "source_record": source,
            "quantities": {
                "DAILY_PACKAGED_KG": rational(q),
                "SHIFT_1_PACKAGING_KG": rational(q1),
                "SHIFT_2_PACKAGING_KG": rational(q2),
                "unit": "kg",
            },
            "staffing_and_tables": {
                "SHIFT_1_WORKERS": n1,
                "SHIFT_2_WORKERS": n2,
                "TOTAL_WORKERS": n1 + n2,
                "PEAK_WORKERS": peak,
                "WORKERS_PER_PACKING_TABLE": 3,
                "TABLE_SHARED_BETWEEN_SHIFTS": True,
                "PACKING_TABLE_COUNT": stations,
                "LOCKER_COUNT": n1 + n2,
                "SIMULTANEOUS_CHANGING_USERS": peak,
                "LOCKER_INTERNAL_SEPARATION": True,
                "LOCKER_SHARED_BETWEEN_SHIFTS": False,
                "OTHER_JOB_STAFF_ADDED": 0,
                "n_actual_grid_cells": None,
            },
            "office": {
                "status": old_office["OFFICE_STAFF_STATUS"],
                "design_staff": old_office.get("OFFICE_DESIGN_STAFF"),
                "factory_size": request.get("factory_size"),
                "size_thresholds": None,
                "rule_version": VERSION,
                "functional_area_m2": None,
            },
            "film_sealing": {
                "zone_code": "coating_room",
                "room_type": "INDEPENDENT",
                "process_type": rule_values["PROCESS_TYPE"],
                "process_sequence": rule_values["PROCESS_SEQUENCE"],
                "DESIGN_FILM_SEALING_RATIO": "1.0",
                "NON_SEALING_PRODUCT_PASS_THROUGH_ALLOWED": True,
                "PASS_THROUGH_USES_EQUIPMENT": False,
                "SEPARATE_BYPASS_ROOM_ASSUMED": False,
                "ACTUAL_RATIO": {"value": None, "status": "PROJECT_DEPENDENT"},
                "EQUIPMENT_MODEL": {"value": None, "status": "UNAVAILABLE"},
                "EQUIPMENT_CAPACITY": {"value": None, "status": "UNAVAILABLE"},
                "EQUIPMENT_COUNT": {"value": None, "status": "UNAVAILABLE"},
                "EQUIPMENT_ENVELOPE": {"value": None, "status": "UNAVAILABLE"},
                "EFFECTIVE_RUNTIME_HOURS": {"value": None, "status": "OWNER_INPUT_REQUIRED"},
                "functional_area_m2": None,
            },
            "engineering_review_required": [
                "Shift-change cleaning and station availability/buffers",
                "Office workstations and clear-space basis",
                "Locker model, door sweep, operation, aisles and hygiene/privacy",
                "Sealing equipment, runtime, all state envelopes and pass-through conflicts",
                "Legacy packing area formula applicability to V2",
            ],
            "BUSINESS_POLICY_READY": True,
        }
    )


def build() -> dict[str, Any]:
    load_previous(V1, "contract.py")
    rules = business_rules()
    examples = []
    for name, daily, first, second in (
        ("default-20t-product", "20000", None, None),
        ("explicit-unequal-20t-product", "20000", "16000", "4000"),
        ("explicit-no-daily", None, "800", "200"),
        ("default-1kg", "1", None, None),
        ("default-192kg", "192", None, None),
        ("default-384kg", "384", None, None),
    ):
        source = {
            "project_id": "SYNTHETIC_V2_ONLY",
            "period_id": "EXAMPLE_DAY",
            "unit": "kg",
            "mass_basis": "PACKAGED_PRODUCT_MASS",
            "scope": "SYNTHETIC_TEST_ONLY_NOT_PROJECT_APPROVAL",
        }
        if daily is not None:
            source["daily_packaged_kg"] = daily
        if first is not None and second is not None:
            source.update(shift_1_packaging_kg=first, shift_2_packaging_kg=second)
        filename = name + "-source.json"
        (HERE / filename).write_bytes(encode(source))
        request = {
            "contract_identity": IDENTITY,
            "contract_version": VERSION,
            "project_id": source["project_id"],
            "period_id": source["period_id"],
            "mass_basis": "PACKAGED_PRODUCT_MASS",
            "mass_source": {"path": filename, "sha256": sha(HERE / filename)},
            "daily_packaged_kg": daily,
            "shift_1_packaging_kg": first,
            "shift_2_packaging_kg": second,
        }
        examples.append({"name": name, "input": request, "result": calculate(request)})
    previous = load_previous(READINESS, "offline_compatibility.py")
    replay = previous.legacy_replay()
    sealed = json.loads((READINESS / "legacy-canonical-replay.json").read_text())
    assert replay == sealed
    protected = {}
    for folder in (V1, READINESS):
        manifest = folder / "source_manifest.json"
        protected[str(manifest.relative_to(REPO))] = sha(manifest)
        for name, digest in json.loads(manifest.read_text())["files"].items():
            protected[str((folder / name).relative_to(REPO))] = digest
    for name, item in json.loads((READINESS / "legacy-current-rule-audit.json").read_text())[
        "source_locations"
    ].items():
        assert sha(REPO / name) == item["sha256"]
        protected[name] = item["sha256"]
    outputs = {
        "owner-confirmed-business-rules-v2.json": rules,
        "shift-allocation-policy.json": {
            "identity": IDENTITY,
            "version": VERSION,
            "policy": "DEFAULT_EQUAL_SPLIT",
            "default_ratios": ["0.5", "0.5"],
            "override_allowed": True,
            "override_mode": "EXPLICIT_SHIFT_OVERRIDE",
            "partial_override": "REJECT",
            "daily_mass_required_for_default": True,
            "daily_mass_optional_for_explicit": True,
            "sum_check_if_daily_given": "EXACT_Q1_PLUS_Q2_EQUALS_Q",
            "source_basis": "PACKAGED_PRODUCT_MASS_WITH_ACTUAL_FILE_HASH_AND_QUANTITY_BINDING",
            "formal_source_approval": "NOT_ESTABLISHED_BY_OFFLINE_HASH",
            "explicit_version_required": True,
        },
        "packing-table-policy.json": {
            "identity": IDENTITY,
            "version": VERSION,
            "SOURCE": "OWNER_CONFIRMED",
            "WORKERS_PER_PACKING_TABLE": 3,
            "PACKING_TABLE_SHARED_BETWEEN_SHIFTS": True,
            "PACKING_TABLE_CAPACITY_POLICY": "PEAK_CONCURRENT_WORKERS",
            "formula": "ceil(max(ceil(Q1/192),ceil(Q2/192))/3)",
            "count_semantics": "Required stations n_need, not layout n_actual cells",
            "production_area_formula_approved_for_v2": False,
            "production_area_m2": None,
            "turnover_review": (
                "Cleaning, actual availability and necessary buffers require engineering review"
            ),
            "confirmed_field_metadata": "owner-confirmed-business-rules-v2.json",
        },
        "staffing-and-locker-calculation.json": {
            "identity": IDENTITY,
            "version": VERSION,
            "formulas": {
                "capacity": "15*1.6*8=192kg/person/shift",
                "N1": "ceil(Q1/192)",
                "N2": "ceil(Q2/192)",
                "total_and_lockers": "N1+N2",
                "peak_and_simultaneous_changing": "max(N1,N2)",
                "required_tables": "ceil(max(N1,N2)/3)",
            },
            "examples_scope": "SYNTHETIC_PRODUCT_MASS_NOT_RAW_INBOUND_CONVERSION",
            "examples": examples,
        },
        "missing-authority-and-engineering-inputs.json": {
            "BUSINESS_POLICY_READY": True,
            "P1_AREA_CALIBRATION_READY": False,
            "P1_PRODUCTION_ACTIVATED": False,
            "UNRESOLVED_SPATIAL_VALUES": {
                "new_functional_area_m2": {
                    "office": None,
                    "changing_room": None,
                    "coating_room": None,
                },
                "minimum_clear_width_m": None,
                "minimum_functional_depth_m": None,
                "aisle_clear_width_m": None,
                "status": "OWNER_INPUT_REQUIRED_OR_NUMERIC_CALIBRATION_NOT_APPROVED",
            },
            "resolved_owner_policy_decisions": [
                "Default equal split and explicit override",
                "3people/table",
                "Shared table set and peak-based table count",
            ],
            "BLOCKING_INPUTS": [
                "Approved real packaged-product mass and project/period provenance",
                "Office size classification thresholds or explicit project size, "
                "furniture and clear-space reference",
                "Locker model/dimensions, doors/operation/aisles and hygiene/privacy review",
                "Sealing model/capacity/count/envelopes and independent effective runtime",
                "Station turnover cleaning, availability and buffers",
            ],
            "BLOCKING_AUTHORITY_DECISIONS": [
                "Legacy grid/pitches/clearances/rank/1.1 formula applicability to V2",
                "New functional areas, dimensions, exact/reporting profiles and migration approval",
            ],
            "BLOCKING_IMPLEMENTATION_ITEMS": [
                "Trusted input and approval binding, explicit P1 version selection",
                "Separately authorized consumers, regression, CI and activation/rollback",
            ],
        },
        "historical-compatibility.json": {
            "reference_head": REFERENCE,
            "protected_files_sha256": protected,
            "v1_policy": "EXPLICIT_INPUT_REQUIRED",
            "v2_policy": "DEFAULT_EQUAL_SPLIT",
            "legacy_capacity_kg_person_day": 336,
            "legacy_full_replay_equals_sealed_bytes_and_hashes": True,
            "legacy_canonical_hash": replay["canonical_result_hash"],
            "legacy_p1_dimension_hash": replay["dimension_handoff_hash"],
            "new_p1_result_created": False,
        },
    }
    for name, value in outputs.items():
        (HERE / name).write_bytes(encode(value))
    return outputs


if __name__ == "__main__":
    build()
