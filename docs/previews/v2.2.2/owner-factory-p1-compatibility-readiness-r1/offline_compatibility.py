"""Offline compatibility sidecar; reads legacy calculators, never activates Owner P1."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from cold_storage.modules.calculations.domain import zone_planning as legacy
from cold_storage.modules.layout.application.dimension_handoff import build_dimension_handoff
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OWNER = HERE.parent / "owner-functional-input-contract-r1"
BASELINE = HERE.parent / "stage-b/layout-quality-baseline-01/inputs/server_authorities.json"
IDENTITY = "OwnerFactoryP1CompatibilityReadinessV1"
VERSION = "owner-factory-p1-compatibility-readiness@1.0.0"
REFERENCE = "75188edb520c49bd4500008a68bd13aaa3448426"
TASK = "V2_2_2_OWNER_FACTORY_INPUT_P1_COMPATIBILITY_READINESS_R1"


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def owner_module() -> Any:
    manifest = json.loads((OWNER / "source_manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if sha(OWNER / name) != digest:
            raise ValueError("OWNER_CONTRACT_SOURCE_CHANGED")
    spec = importlib.util.spec_from_file_location("owner_inputs_offline_r1", OWNER / "contract.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy_replay() -> dict[str, Any]:
    source_hash = sha(BASELINE)
    source = json.loads(BASELINE.read_text())
    stored = source["canonical_zone_plan"]
    result = asdict(
        legacy.ColdRoomZonePlanner().plan(legacy.ColdRoomZonePlanInput(**stored["input"]))
    )
    assert result == stored and canonical_json(result) == canonical_json(stored)

    def compact(obj: Any) -> bytes:
        return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()

    assert compact(result) == compact(stored)
    original_dimension = source["p1_handoff"]["p1e_historical_handoff"]["dimension_handoff"]
    dimension = build_dimension_handoff(result)
    assert dimension.canonical_json() == canonical_json(original_dimension)
    assert dimension.canonical_result_hash == canonical_hash(original_dimension)
    assert canonical_hash(result) == original_dimension["source_zone_plan_result_hash"]
    assert sha(BASELINE) == source_hash
    return {
        "mode": "LEGACY_CANONICAL",
        "status": "READ_ONLY_FULL_SNAPSHOT_AND_DIMENSION_REPLAY_PASS",
        "source_file_sha256": source_hash,
        "canonical_result": result,
        "canonical_result_hash": canonical_hash(result),
        "dimension_handoff_hash": dimension.canonical_result_hash,
        "sorted_compact_json_bytes_equal": True,
        "sorted_compact_json_sha256": hashlib.sha256(compact(result)).hexdigest(),
        "project_canonical_bytes_equal": True,
        "identity_changed": False,
        "authority_changed": False,
        "new_canonical_result_created_for_owner_mode": False,
    }


def source_check(payload: dict[str, Any], root: Path) -> tuple[dict[str, Any] | None, str]:
    """Local content binding only. A matching hash never proves Owner project approval."""
    if any(key in payload for key in ("verified", "authoritative", "authority_token")):
        return None, "CALLER_AUTHORITY_ASSERTION_NOT_ACCEPTED"
    if payload.get("mass_basis") not in (None, "PACKAGED_PRODUCT_MASS"):
        return None, "PACKAGED_PRODUCT_MASS_KG_REQUIRED"
    reference = payload.get("mass_source")
    if not isinstance(reference, dict):
        return None, "PACKAGED_MASS_SOURCE_REQUIRED"
    name, digest = reference.get("path"), reference.get("sha256")
    if not isinstance(name, str) or not isinstance(digest, str):
        return None, "SOURCE_FILE_AND_ACTUAL_CONTENT_HASH_REQUIRED"
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return None, "INVALID_SOURCE_HASH"
    relative = Path(name)
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root.resolve()):
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
        return None, "PACKAGED_PRODUCT_MASS_KG_REQUIRED"
    if not payload.get("project_id") or not payload.get("period_id"):
        return None, "PROJECT_AND_PERIOD_ID_REQUIRED"
    if any(body.get(key) != payload[key] for key in ("project_id", "period_id")):
        return None, "SOURCE_PROJECT_OR_PERIOD_MISMATCH"
    quantities = ("shift_1_packaging_kg", "shift_2_packaging_kg")
    owner = owner_module()
    for key in quantities:
        if payload.get(key) is None or body.get(key) is None:
            return None, "EXPLICIT_BOTH_SHIFT_ALLOCATIONS_REQUIRED"
        try:
            if owner.exact(payload[key], field=key) != owner.exact(body[key], field=key):
                return None, "SOURCE_SHIFT_QUANTITY_MISMATCH"
        except ValueError:
            return None, "INVALID_SHIFT_PRODUCT_MASS"
    return body, "ACTUAL_LOCAL_BYTES_AND_QUANTITIES_MATCH_NOT_APPROVAL"


def table_sensitivity(n1: int, n2: int, *, reuse_between_shifts: bool | None) -> dict[str, Any]:
    if any(type(n) is not int or n < 0 for n in (n1, n2)):
        raise ValueError("INVALID_SHIFT_WORKER_COUNT")
    if reuse_between_shifts is not None and type(reuse_between_shifts) is not bool:
        raise ValueError("INVALID_REUSE_ASSUMPTION")
    header = {
        "policy": "PROPOSED_PEAK_CONCURRENCY_TABLE_POLICY",
        "status": "ENGINEERING_PROPOSAL_NOT_APPROVED",
        "workers_per_table": 3,
        "workers_per_table_source": "Legacy constant only; Owner approval for new policy pending",
        "reuse_between_shifts": reuse_between_shifts,
        "total_shift_workers": n1 + n2,
        "peak_concurrent_packaging_workers": max(n1, n2),
        "peak_basis": (
            "Proposed non-overlapping production-shift scenario; changing non-overlap "
            "alone does not approve workstation handover, cleaning or overlap policy"
        ),
        "formal_p1_table_count": None,
        "formal_p1_area_m2": None,
        "new_total_factory_area_m2": None,
    }
    if reuse_between_shifts is None:
        return {**header, "proposal_table_count": None, "area_projection": None}
    first, second = (n1 + 2) // 3, (n2 + 2) // 3
    # Shared stations must meet each shift's demand, not both employee sets added.
    count = max(first, second) if reuse_between_shifts else first + second
    layout = legacy.ColdRoomZonePlanner()._pack_sorting_rectangle(count)
    raw = round(layout.required_area_m2, 2)
    return {
        **header,
        "proposal_table_count": count,
        "formula": "max(ceil(N1/3),ceil(N2/3))"
        if reuse_between_shifts
        else "ceil(N1/3)+ceil(N2/3)",
        "area_projection": {
            "status": "HYPOTHETICAL_LEGACY_FORMULA_PROJECTION_NOT_NEW_P1",
            "assumptions": (
                "If existing three-worker stations, pitches, clearances, "
                "packing rank and1.1 factor remain suitable and are separately approved"
            ),
            "raw_area_m2": raw,
            "factor": legacy.SORTING_PACKAGING_AREA_FACTOR,
            "reported_area_m2": round(raw * legacy.SORTING_PACKAGING_AREA_FACTOR, 2),
            "grid": asdict(layout),
            "grid_cells_not_installed_inventory_authority": True,
        },
    }


def proposed(payload: dict[str, Any], *, evidence_root: Path) -> dict[str, Any]:
    owner = owner_module()
    body, verification = source_check(payload, evidence_root)
    office = owner.office(payload.get("factory_size"))
    staffing = None
    tables = None
    if body is not None:
        staffing = owner.staffing(
            shift_1_kg=payload["shift_1_packaging_kg"],
            shift_2_kg=payload["shift_2_packaging_kg"],
            daily_packaged_kg=payload.get("daily_packaged_kg"),
            mass_basis=body["mass_basis"],
            mass_source="Local matching source bytes, not project approval",
        )
        tables = table_sensitivity(
            staffing["SHIFT_1_WORKERS"],
            staffing["SHIFT_2_WORKERS"],
            reuse_between_shifts=payload.get("hypothetical_table_reuse"),
        )
    return {
        "identity": IDENTITY,
        "version": VERSION,
        "mode": "OWNER_V1_PROPOSED",
        "input_identity": {
            "project_id": payload.get("project_id"),
            "period_id": payload.get("period_id"),
        },
        "input_mass_basis": "PACKAGED_PRODUCT_MASS_REQUIRED",
        "source_verification": verification,
        "source_record": body,
        "input_mass_source": payload.get("mass_source"),
        "owner_contract_version": owner.VERSION,
        "owner_contract_source_manifest_sha256": sha(OWNER / "source_manifest.json"),
        "staffing_and_lockers": staffing,
        "office": office,
        "table_policy": tables,
        "film_sealing": owner.film_sealing(
            entering_product_kg=payload.get("film_entering_product_kg"),
            mass_source=payload.get("film_mass_source_reference"),
            actual_ratio=payload.get("actual_film_sealing_ratio"),
        ),
        "new_functional_area_m2": {"office": None, "changing_room": None, "coating_room": None},
        "COMPARISON_STATUS": "NOT_COMPARABLE",
        "comparison_reason": (
            "Legacy raw inbound mass and Owner packaged-product mass/staffing semantics differ; "
            "no algorithm superiority or approved area delta"
        ),
        "canonical_p1_result": None,
        "server_authority_created": False,
        "formal_source_admission": "BLOCKED_NOT_IMPLEMENTED_BY_OFFLINE_CONTENT_CHECK",
        "BLOCKING_INPUTS": [
            "Project size, workstations and clear-space basis",
            "Locker and equipment/state envelopes",
            "Equipment effective runtime and actual mass provenance approval",
        ],
        "BLOCKING_AUTHORITY_DECISIONS": [
            "New table concurrency/reuse and three-worker capacity approval",
            "Functional areas and profile version/supersession approval",
        ],
        "BLOCKING_IMPLEMENTATION_ITEMS": [
            "Trusted upstream content/provenance binding",
            "Separate version selector, canonical identity and P1/P2 migration",
            "Consumer implementation, regression, CI and rollback gates",
        ],
        "BUSINESS_RULES_READY": True,
        "P1_INTEGRATION_IMPLEMENTATION_READY": False,
        "P1_PRODUCTION_ACTIVATED": False,
    }


def evaluate(mode: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if mode == "LEGACY_CANONICAL":
        if payload:
            raise ValueError("OWNER_INPUT_CANNOT_OVERRIDE_LEGACY_CANONICAL")
        return legacy_replay()
    if mode == "OWNER_V1_PROPOSED":
        return proposed(payload or {}, evidence_root=HERE)
    raise ValueError("EXPLICIT_COMPATIBILITY_MODE_REQUIRED")


def code_locations() -> dict[str, Any]:
    result = {}
    paths = (
        "backend/src/cold_storage/modules/calculations/domain/zone_planning.py",
        "backend/src/cold_storage/modules/layout/application/dimension_handoff.py",
        "backend/src/cold_storage/modules/layout/application/dimension_zones.py",
        "backend/src/cold_storage/modules/layout/application/layout_authority_binding.py",
        "backend/src/cold_storage/modules/layout/application/sorting_dimension_authority.py",
        "backend/src/cold_storage/modules/layout/domain/dimension_handoff.py",
        "backend/src/cold_storage/modules/layout/domain/dimensioning.py",
        "backend/src/cold_storage/modules/layout/infrastructure/global_cp_sat_model.py",
        "docs/tasks/V2_2_2-version-plan.md",
        "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md",
        "docs/tasks/V2_2-P1C-sorting-packaging-dimension-authority.md",
        "docs/tasks/V2_2-P1D3-flexible-rectangle-handoff-contract.md",
        "docs/tasks/V2_2-P2C-deterministic-placement-engine.md",
    )
    for name in paths:
        path = REPO / name
        symbols = {}
        if path.suffix == ".py":
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    symbols[node.name] = {"line": node.lineno, "end_line": node.end_lineno}
        result[name] = {"sha256": sha(path), "symbols": symbols}
    return result


def build() -> dict[str, Any]:
    old = legacy_replay()
    snapshot = old["canonical_result"]
    base_input = legacy.ColdRoomZonePlanInput(**snapshot["input"])
    planner = legacy.ColdRoomZonePlanner()
    changed = planner.plan(
        replace(
            base_input, office_fixed_area_m2=1, changing_fixed_area_m2=2, coating_fixed_area_m2=3
        )
    )
    assert asdict(changed)["result"] == snapshot["result"]
    assert canonical_hash(asdict(changed)) != canonical_hash(snapshot)
    invalid = planner.plan(replace(base_input, office_fixed_area_m2=0))
    assert not invalid.success
    bands = []
    for kg in (24999, 25000, 49999, 50000):
        result = planner.plan(replace(base_input, daily_inbound_mass_kg=kg))
        assert result.success
        areas = {row["zone_code"]: row["required_area_m2"] for row in result.result["zones"]}
        bands.append(
            {
                "raw_kg_day": kg,
                "office": areas["office"],
                "changing_room": areas["changing_room"],
                "coating_room": areas["coating_room"],
            }
        )
    owner = owner_module()
    # Explicit fictional product records; not a conversion of the old20t raw input.
    scenario_outputs = []
    for label, first, second in (("equal", "10000", "10000"), ("unequal", "16000", "4000")):
        record = {
            "project_id": "SYNTHETIC_COMPATIBILITY_ONLY",
            "period_id": "EXAMPLE_DAY",
            "unit": "kg",
            "mass_basis": "PACKAGED_PRODUCT_MASS",
            "shift_1_packaging_kg": first,
            "shift_2_packaging_kg": second,
            "scope": "SYNTHETIC_TEST_ONLY_NOT_APPROVED_PROJECT",
        }
        name = f"synthetic-{label}-mass-source.json"
        (HERE / name).write_bytes(encoded(record))
        payload = {
            "project_id": record["project_id"],
            "period_id": record["period_id"],
            "shift_1_packaging_kg": first,
            "shift_2_packaging_kg": second,
            "daily_packaged_kg": 20000,
            "mass_source": {"path": name, "sha256": sha(HERE / name)},
            "hypothetical_table_reuse": True,
            "factory_size": None,
        }
        scenario_outputs.append(
            {"name": label, "input": payload, "output": proposed(payload, evidence_root=HERE)}
        )
    missing = proposed({}, evidence_root=HERE)
    alias_mapping = {
        "identity": "owner-business-alias-map-proposal@1.0.0",
        "status": "EXPLICIT_OFFLINE_MAPPING_NOT_PRODUCTION_ENUM_CHANGE",
        "roles": {
            "SORTING_PACKAGING": "SORTING_PACKAGING",
            "SECONDARY_PRECOOLING": "SECONDARY_PRECOOL",
            "COATING_ROOM": "COATING",
            "FINISHED_GOODS": "FINISHED_STORAGE",
        },
        "ordered_business_roles": owner.values()["PROCESS_SEQUENCE"],
        "ordered_p0_roles": [
            "SORTING_PACKAGING",
            "SECONDARY_PRECOOL",
            "COATING",
            "FINISHED_STORAGE",
        ],
        "field_migration": {
            "historical_field": "GENDER_INDEPENDENT_ZONING_PRESET",
            "historical_value": False,
            "ambiguity": (
                "Could be read as gender-neutral zoning or as gender-based separate zones; "
                "do not infer from name alone"
            ),
            "owner_intent": "Do not preset separate male/female functional zones",
            "proposed_field": "SEPARATE_GENDER_ZONES_PRESET",
            "proposed_value": False,
            "migration_status": "PROPOSAL_ONLY_HISTORICAL_CONTRACT_UNCHANGED",
            "professional_review": "HYGIENE_PRIVACY_AND_APPLICABLE_CODES_REQUIRED",
        },
    }
    mappings = (
        (
            "daily_inbound_mass_kg",
            "PACKAGED_PRODUCT_MASS",
            "kg/day",
            "Raw input differs from packaged product",
            "Traceable yield/mass-balance and common period; never default1",
            "NOT_INTERCHANGEABLE",
            "Canonical source changes if activated",
            "BLOCKED_MASS_SOURCE",
        ),
        (
            "daily_inbound_mass_kg",
            "SHIFT_1_PACKAGING_KG",
            "kg/shift",
            "Explicit first shift allocation",
            "Product source and shift allocation",
            "EXPLICIT_INPUT_REQUIRED",
            "New staffing source",
            "OWNER_INPUT_REQUIRED",
        ),
        (
            "daily_inbound_mass_kg",
            "SHIFT_2_PACKAGING_KG",
            "kg/shift",
            "Explicit second shift allocation",
            "No equal allocation or daily remainder default",
            "EXPLICIT_INPUT_REQUIRED",
            "New staffing source",
            "OWNER_INPUT_REQUIRED",
        ),
        (
            "person_daily_capacity_kg_day=336",
            "PERSON_SHIFT_CAPACITY_KG=192",
            "kg/person/day vs kg/person/shift",
            "16*1.5*14 versus15*1.6*8",
            "Independent version selector, never simple coefficient replacement",
            "DIFFERENT_SEMANTICS",
            "New formula/profile identity needed",
            "KEEP_LEGACY_UNCHANGED",
        ),
        (
            "worker_count",
            "SHIFT_1_WORKERS",
            "people",
            "Old ceil(raw/336) vs ceil(Q1/192)",
            "Explicit Q1",
            "NOT_EQUIVALENT",
            "Staffing changes may affect layout",
            "OWNER_INPUT_REQUIRED",
        ),
        (
            "worker_count",
            "SHIFT_2_WORKERS",
            "people",
            "Old daily count vs second shift",
            "Explicit Q2",
            "NOT_EQUIVALENT",
            "Staffing changes may affect layout",
            "OWNER_INPUT_REQUIRED",
        ),
        (
            "worker_count",
            "TOTAL_SHIFT_WORKERS",
            "distinct employees",
            "N1+N2 for personal lockers",
            "Independent shift employee sets",
            "NOT_TABLE_CONCURRENCY",
            "Locker input only until area calibrated",
            "OWNER_INPUT_REQUIRED",
        ),
        (
            "worker_count",
            "PEAK_CONCURRENT_PACKAGING_WORKERS",
            "people concurrently",
            "max(N1,N2), not N1+N2",
            "Non-overlapping shifts; time/overlap policy",
            "PROPOSAL_FOR_TABLES",
            "Table policy approval pending",
            "OWNER_INPUT_REQUIRED",
        ),
        (
            "table_count",
            "PROPOSED_PEAK_CONCURRENCY_TABLE_POLICY",
            "tables",
            "Legacy ceil(worker/3), proposal ceil(max(N1,N2)/3) if reused",
            "Approve reuse and three-worker station suitability",
            "ENGINEERING_PROPOSAL_NOT_APPROVED",
            "Would change sorting area and P1 dimensions",
            "NO_FORMAL_TABLE_RESULT",
        ),
        (
            "n_actual/position_count",
            "PROPOSAL_GRID_CELLS",
            "grid cells",
            "Actual grid can exceed required table count",
            "Retain n_need/n_actual/unused separately",
            "SENSITIVITY_ONLY",
            "Do not mistake spare cells for installed inventory",
            "NO_FORMAL_P1_RESULT",
        ),
        (
            "sorting_packaging_room.required_area_m2",
            "PROPOSED_SORTING_AREA",
            "m2",
            "Grid pitches, clearances, rank, factor and reporting matter",
            "Same legacy formula only as hypothetical projection",
            "NO_APPROVED_AREA_DELTA",
            "Exact-area binder and downstream envelopes affected",
            "AREA_CALIBRATION_REQUIRED",
        ),
        (
            "office area by raw25/50t bands",
            "OFFICE_DESIGN_STAFF",
            "m2 vs people",
            "Explicit size12/20/30 not raw tonnage classification",
            "Approve scale definitions and furniture/clear-space model",
            "NO_AUTOMATIC_MAPPING",
            "Legacy60/80/100 retained",
            "UNKNOWN_SIZE_OWNER_INPUT_REQUIRED",
        ),
        (
            "changing area40/80/120",
            "LOCKER_COUNT",
            "m2 vs personal lockers",
            "Sum of shift employee sets, no sharing",
            "Locker dimensions, door sweep, operation, aisles",
            "STAFFING_ONLY",
            "No new area/person rule",
            "AREA_UNAVAILABLE",
        ),
        (
            "changing area40/80/120",
            "SIMULTANEOUS_CHANGING_USERS",
            "m2 vs concurrent people",
            "Whole largest shift, no intra-shift staging",
            "Actual hygiene/operation/door envelopes",
            "STAFFING_ONLY",
            "No inference40m2 sufficient",
            "AREA_UNAVAILABLE",
        ),
        (
            "coating area80/120/200",
            "DESIGN_FILM_SEALING_RATIO=1.0",
            "m2 vs fraction/load",
            "Packaging box sealing, all entering products at design",
            "Product mass period, equipment and runtime",
            "PROCESS_SPECIFIC_NEW_INPUT",
            "Legacy areas and process order preserved",
            "EQUIPMENT_INPUT_REQUIRED",
        ),
        (
            "working_time_h_per_day / packing hours14",
            "PACKAGING_WORK_HOURS_PER_DAY=16",
            "hours/day",
            "Facility schedule not equipment effective runtime",
            "Separate sealing runtime source",
            "NOT_EQUIPMENT_RUNTIME",
            "No implicit equipment count",
            "OWNER_INPUT_REQUIRED",
        ),
        (
            "GENDER_INDEPENDENT_ZONING_PRESET",
            "SEPARATE_GENDER_ZONES_PRESET (proposal)",
            "boolean",
            "Explicit Owner intent resolves ambiguous name",
            "Versioned alias, keep historical bytes",
            "MIGRATION_DESIGN_ONLY",
            "No compliance waiver",
            "PROFESSIONAL_REVIEW_REQUIRED",
        ),
    )
    outputs = {
        "legacy-canonical-replay.json": old,
        "legacy-current-rule-audit.json": {
            "reference_head": REFERENCE,
            "source_locations": code_locations(),
            "constants": {
                name: getattr(legacy, name)
                for name in (
                    "PACKING_PIECES_PER_PERSON_HOUR",
                    "PACKING_WEIGHT_PER_PIECE_KG",
                    "PACKING_WORKING_HOURS_PER_DAY",
                    "PERSON_DAILY_CAPACITY_KG",
                    "WORKERS_PER_PACKING_TABLE",
                    "OFFICE_AREA_BY_BAND_M2",
                    "CHANGING_AREA_BY_BAND_M2",
                    "COATING_AREA_BY_BAND_M2",
                    "PACKING_TABLE_PITCH_LONG_M",
                    "PACKING_TABLE_PITCH_SHORT_M",
                    "SORTING_CLEARANCE_LONG_M",
                    "SORTING_CLEARANCE_SHORT_M",
                    "SORTING_PACKAGING_AREA_FACTOR",
                )
            },
            "band_boundary_replays": bands,
            "sorting_input_vs_active_formula": {
                "input_packing_area_factor": base_input.packing_area_factor,
                "active_sorting_area_factor": legacy.SORTING_PACKAGING_AREA_FACTOR,
                "input_pitches": [
                    base_input.packing_table_horizontal_spacing_m,
                    base_input.packing_table_vertical_spacing_m,
                ],
                "active_pitches": [
                    legacy.PACKING_TABLE_PITCH_LONG_M,
                    legacy.PACKING_TABLE_PITCH_SHORT_M,
                ],
                "source_explanation": (
                    "_sorting_packaging_zone reads constructor-owned "
                    "self._sorting_packaging_area_factor, not data.packing_area_factor; "
                    "_pack_sorting_rectangle uses global pitches, not input pitch fields. "
                    "workers_per_packing_table is actually read from data."
                ),
            },
            "fixed_area_input_audit": {
                "defaults": {
                    name: getattr(base_input, name)
                    for name in (
                        "office_fixed_area_m2",
                        "changing_fixed_area_m2",
                        "coating_fixed_area_m2",
                    )
                },
                "positive_override_1_2_3_result_unchanged": True,
                "positive_override_full_snapshot_hash_changed": True,
                "zero_still_rejected_by_generic_validation": True,
                "meaning": (
                    "Fields are serialized and positivity-validated but not consumed "
                    "as the three areas; full input/hash changes under override, "
                    "result areas do not"
                ),
            },
            "sorting_grid_rank": [
                "aspect-band membership of n_long/n_short",
                "unused cells",
                "distance from2.0",
                "raw area",
            ],
            "scope": (
                "Read-only deterministic area/dimension arithmetic, not CP-SAT or layout generation"
            ),
        },
        "owner-v1-input-mapping.json": {
            "owner_contract_version": owner.VERSION,
            "owner_source_manifest_sha256": sha(OWNER / "source_manifest.json"),
            "rows": [
                dict(
                    zip(
                        (
                            "LEGACY_INPUT",
                            "OWNER_V1_INPUT",
                            "UNIT",
                            "BUSINESS_SEMANTICS",
                            "TRANSFORMATION_REQUIRED",
                            "COMPATIBILITY_STATUS",
                            "AUTHORITY_IMPACT",
                            "MISSING_INPUT_BEHAVIOR",
                        ),
                        row,
                        strict=True,
                    ),
                    DATA_SOURCE={
                        "legacy": (
                            "legacy-current-rule-audit.json source_locations "
                            "and frozen canonical snapshot"
                        ),
                        "owner": (
                            "../owner-functional-input-contract-r1/"
                            "owner-confirmed-business-rules.json"
                        ),
                    },
                )
                for row in mappings
            ],
        },
        "staffing-and-table-compatibility.json": {
            "status": "OFFLINE_SENSITIVITY_NOT_APPROVED_POLICY",
            "scenarios": scenario_outputs,
            "missing_input_scenario": missing,
            "historical_table_rule_not_changed": True,
            "new_sorting_area_authority": None,
        },
        "role-and-field-alias-mapping.json": alias_mapping,
        "p1-compatibility-output-contract.json": {
            "identity": IDENTITY,
            "version": VERSION,
            "registration": "UNREGISTERED_OFFLINE_DRAFT",
            "explicit_modes": ["LEGACY_CANONICAL", "OWNER_V1_PROPOSED"],
            "legacy": "Actual production result and identity unchanged; separate wrapper only",
            "owner": "Proposed staffing and locker facts, never canonical P1",
            "required_fields": list(missing),
            "output_hash_semantics": (
                "Offline sidecar digest only; "
                "never substitute for production canonical_hash or source approval"
            ),
            "P1_INTEGRATION_IMPLEMENTATION_READY": False,
            "P1_PRODUCTION_ACTIVATED": False,
        },
        "missing-input-admission.json": {
            "status": "DESIGN_AND_OFFLINE_CHECK_NOT_FORMAL_ADMISSION",
            "actual_file_and_hash_checked": True,
            "hash_alone_is_project_approval": False,
            "caller_verified_flag_accepted": False,
            "source_fail_closed_reasons": [
                "PACKAGED_MASS_SOURCE_REQUIRED",
                "SOURCE_FILE_MISSING",
                "SOURCE_CONTENT_HASH_MISMATCH",
                "PACKAGED_PRODUCT_MASS_KG_REQUIRED",
                "EXPLICIT_BOTH_SHIFT_ALLOCATIONS_REQUIRED",
                "SOURCE_SHIFT_QUANTITY_MISMATCH",
                "SOURCE_PROJECT_OR_PERIOD_MISMATCH",
                "CALLER_AUTHORITY_ASSERTION_NOT_ACCEPTED",
            ],
            "BLOCKING_INPUTS": missing["BLOCKING_INPUTS"],
            "BLOCKING_AUTHORITY_DECISIONS": missing["BLOCKING_AUTHORITY_DECISIONS"],
            "BLOCKING_IMPLEMENTATION_ITEMS": missing["BLOCKING_IMPLEMENTATION_ITEMS"],
            "BUSINESS_RULES_READY": True,
            "P1_INTEGRATION_IMPLEMENTATION_READY": False,
            "P1_PRODUCTION_ACTIVATED": False,
        },
    }
    for name, value in outputs.items():
        (HERE / name).write_bytes(encoded(value))
    return outputs


if __name__ == "__main__":
    build()
