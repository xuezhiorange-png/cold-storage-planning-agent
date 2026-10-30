"""Scoped R13 inputs and fresh R10/R12 rechecks; never an approval interface."""

import hashlib
import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, fields
from datetime import date
from pathlib import PurePosixPath
from typing import Any

from cold_storage.modules.layout.application.functional_project_input_binding import (
    ReviewedProjectDatum,
)
from cold_storage.modules.layout.application.functional_site_impact_review import (
    review_functional_site_impact,
)
from cold_storage.modules.layout.application.functional_sizing_sources import (
    HISTORICAL,
    HISTORICAL_FILES,
    checked_bytes,
    verify_sizing_evidence,
)
from cold_storage.modules.layout.application.room_reverse_sizing_review import evaluate_sizing_point
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_room_sizing_input import RoomUseConditions
from cold_storage.modules.layout.domain.functional_sizing_advisory import area_text
from cold_storage.modules.layout.domain.physical_room_calibration import (
    FIELDS,
    IDENTITY,
    SEQUENCE,
    case_physical_checks,
    field_schema,
    input_conflicts,
    storage_checks,
    validate_value,
)

TASK = "V2_2_2_R11_R13_H5_PHYSICAL_INPUT_CALIBRATION_R1"
BASE_HEAD = "5b7ec33f258bacc0797148edb70766b47c47298f"
R12 = "docs/previews/v2.2.2/r11-r12-site-impact-review-r1"
R12_MANIFEST_SHA = "4d49e59e037925ba2dd9888b5bd95b78d07306f3314181e1a6cea911ccfe9859"
SOURCE_TYPES = ("SUPPLIER_UNREVIEWED", "SITE_MEASUREMENT_UNREVIEWED", "HYPOTHETICAL_NOT_APPROVED")
PACKET_KEYS = frozenset(
    {
        "schema_version",
        "project_scope_id",
        "physical_room_id",
        "owner_template_sha256",
        "parameters",
        "source_documents",
    }
)
PARAMETER_KEYS = frozenset({"value", "unit", "document_id", "locator"})
DOCUMENT_KEYS = frozenset(
    {
        "source_type",
        "file_name",
        "sha256",
        "document_date",
        "project_scope_id",
        "reference",
    }
)


def calibration_context(files: Mapping[str, bytes]) -> dict[str, Any]:
    name = f"{R12}/source-manifest.json"
    manifest = json.loads(checked_bytes(files, name, R12_MANIFEST_SHA))
    for path, digest in manifest["source_files"].items():
        checked_bytes(files, path, digest)
    for relative, digest in manifest["derived_files"].items():
        checked_bytes(files, f"{R12}/{relative}", digest)
    archived = json.loads(files[f"{R12}/site-impact.json"])
    candidates = {
        record: json.loads(files[f"{HISTORICAL}/{path}"])
        for record, path in zip(("P01", "P02"), HISTORICAL_FILES[2:], strict=True)
    }
    # Recompute from the original rooms, corridors and Site, not a saved PASS.
    overlay = review_functional_site_impact(
        files, project_scope_id=archived["project_scope_id"], candidate_records=candidates
    )
    if json.loads(json.dumps(overlay, ensure_ascii=False)) != archived:
        raise ValueError("R12_ARCHIVED_OVERLAY_RECOMPUTATION_MISMATCH")
    source = verify_sizing_evidence(files)
    group = next(g for g in source["catalog"]["groups"] if g["group"] == "G01")
    return dict(
        overlay=overlay,
        source=source,
        room=group["room"],
        demand=source["catalog"]["demands"]["INTERNAL_PARTITION"],
        owner_template=json.loads(files[f"{R12}/owner-input-template.json"]),
        template_sha256=hashlib.sha256(files[f"{R12}/owner-input-template.json"]).hexdigest(),
        r12_manifest_sha256=R12_MANIFEST_SHA,
        source_hashes={
            **manifest["source_files"],
            **{f"{R12}/{n}": s for n, s in manifest["derived_files"].items()},
            name: R12_MANIFEST_SHA,
        },
    )


def input_template(ctx: dict[str, Any]) -> dict[str, Any]:
    return dict(
        schema_version=IDENTITY,
        project_scope_id=ctx["overlay"]["project_scope_id"],
        physical_room_id=ctx["overlay"]["physical_room_id"],
        owner_template_sha256=ctx["template_sha256"],
        parameters={
            k: dict(value=None, unit=spec.unit, document_id=None, locator=None)
            for k, spec in FIELDS.items()
        },
        source_documents={},
    )


def review_reference(document: Mapping[str, Any], locator: str) -> str:
    """Exact existing ReviewedProjectDatum reference; not a signing/approval API."""
    return f"{document['file_name']}#{locator}; sha256:{document['sha256']}"


def bind_physical_inputs(
    ctx: dict[str, Any],
    packet: Mapping[str, Any],
    source_files: Mapping[str, bytes],
    *,
    reviewed_project: Mapping[str, ReviewedProjectDatum] | None = None,
) -> dict[str, Any]:
    if not isinstance(packet, dict) or set(packet) != PACKET_KEYS:
        raise ValueError("PHYSICAL_INPUT_CONTRACT_OR_UNTRUSTED_APPROVAL_LABEL")
    expected = input_template(ctx)
    for key in ("schema_version", "project_scope_id", "physical_room_id", "owner_template_sha256"):
        if packet[key] != expected[key]:
            raise ValueError("PHYSICAL_INPUT_PROJECT_ROOM_OR_SOURCE_MISMATCH:" + key)
    if not isinstance(packet["parameters"], dict) or set(packet["parameters"]) != set(FIELDS):
        raise ValueError("COMPLETE_PHYSICAL_FIELD_VOCABULARY_REQUIRED")
    if not isinstance(packet["source_documents"], dict) or len(packet["source_documents"]) > 32:
        raise ValueError("BOUNDED_SOURCE_DOCUMENTS_REQUIRED")
    docs = packet["source_documents"]
    explicit_regression_sources = {}
    for key, doc in docs.items():
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key)
            or not isinstance(doc, dict)
            or set(doc) != DOCUMENT_KEYS
        ):
            raise ValueError("PHYSICAL_SOURCE_DOCUMENT_CONTRACT_REQUIRED")
        if (
            doc["source_type"] not in SOURCE_TYPES
            or doc["project_scope_id"] != packet["project_scope_id"]
        ):
            raise ValueError("UNREVIEWED_SOURCE_TYPE_AND_MATCHING_PROJECT_REQUIRED")
        if (
            not isinstance(doc["file_name"], str)
            or not doc["file_name"]
            or PurePosixPath(doc["file_name"]).is_absolute()
            or ".." in PurePosixPath(doc["file_name"]).parts
            or "\\" in doc["file_name"]
            or not re.fullmatch(r"[0-9a-f]{64}", str(doc["sha256"]))
        ):
            raise ValueError("SOURCE_FILE_AND_SHA256_REQUIRED")
        if not isinstance(doc["reference"], str) or not doc["reference"].strip():
            raise ValueError("SOURCE_DOCUMENT_REFERENCE_REQUIRED")
        if doc["document_date"] is not None:
            try:
                date.fromisoformat(doc["document_date"])
            except (TypeError, ValueError) as exc:
                raise ValueError("SOURCE_DOCUMENT_DATE_INVALID") from exc
        data = source_files.get(doc["file_name"])
        if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != doc["sha256"]:
            raise ValueError("PHYSICAL_SOURCE_BYTES_MISSING_OR_HASH_MISMATCH")
        try:
            decoded = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            decoded = None
        if isinstance(decoded, dict) and decoded.get("identity") == (
            "R13_EXPLICIT_HISTORICAL_REGRESSION_NOT_APPROVED"
        ):
            if doc["source_type"] != "HYPOTHETICAL_NOT_APPROVED":
                raise ValueError("HISTORICAL_HYPOTHESIS_CANNOT_BE_RELABELLED_AS_ACTUAL")
            explicit_regression_sources[key] = decoded
    reviewed = reviewed_project or {}
    if not set(reviewed) <= set(FIELDS) or any(
        not isinstance(d, ReviewedProjectDatum) for d in reviewed.values()
    ):
        raise ValueError("EXISTING_TYPED_PROJECT_REVIEW_REQUIRED")
    params = {}
    values = {}
    for name, raw in packet["parameters"].items():
        if (
            not isinstance(raw, dict)
            or set(raw) != PARAMETER_KEYS
            or raw["unit"] != FIELDS[name].unit
        ):
            raise ValueError("PHYSICAL_PARAMETER_UNIT_OR_APPROVAL_LABEL:" + name)
        value = raw["value"]
        validate_value(name, value)
        values[name] = value
        datum = reviewed.get(name)
        if value is None:
            if raw["document_id"] is not None or raw["locator"] is not None or datum:
                raise ValueError("MISSING_VALUE_CANNOT_HAVE_REVIEW_OR_SOURCE:" + name)
            params[name] = dict(
                **deepcopy(raw),
                source_type="MISSING",
                review_status="INPUT_REQUIRED",
                is_reviewed=False,
            )
            continue
        if (
            raw["document_id"] not in docs
            or not isinstance(raw["locator"], str)
            or not raw["locator"].strip()
        ):
            raise ValueError("PARAMETER_SOURCE_AND_LOCATION_REQUIRED:" + name)
        doc = docs[raw["document_id"]]
        known_regression = explicit_regression_sources.get(raw["document_id"])
        if known_regression is not None and (
            raw["locator"] != "/parameters/" + name
            or known_regression.get("parameters", {}).get(name) != value
        ):
            raise ValueError("REGRESSION_PARAMETER_SOURCE_VALUE_MISMATCH:" + name)
        if datum is not None and (
            datum.field_name != name
            or datum.value != value
            or type(datum.value) is not type(value)
            or datum.unit != raw["unit"]
            or datum.project_scope_id != packet["project_scope_id"]
            or datum.reference != review_reference(doc, raw["locator"])
            or datum.source_label not in {"OWNER_CONFIRMED", "ENGINEERING_DERIVED"}
            or doc["source_type"] == "HYPOTHETICAL_NOT_APPROVED"
        ):
            raise ValueError("EXISTING_PROJECT_REVIEW_SOURCE_SCOPE_OR_VALUE_MISMATCH:" + name)
        params[name] = dict(
            **deepcopy(raw),
            source_type=doc["source_type"],
            source_sha256=doc["sha256"],
            document_date=doc["document_date"],
            source_reference=review_reference(doc, raw["locator"]),
            review_status="REVIEWED_VIA_EXISTING_PROJECT_INPUT" if datum else doc["source_type"],
            is_reviewed=datum is not None,
            reviewed_project_datum=asdict(datum) if datum else None,
        )
    conflicts = input_conflicts(values)
    if conflicts:
        raise ValueError("PHYSICAL_CONFIGURATION_INPUT_CONFLICT:" + ",".join(conflicts))
    payload = dict(
        project_scope_id=packet["project_scope_id"],
        physical_room_id=packet["physical_room_id"],
        parameters=params,
        source_documents=deepcopy(docs),
        adapter=IDENTITY,
        source_hashes=deepcopy(ctx["source_hashes"]),
        owner_requirements=deepcopy(ctx["owner_template"]["reviewed_inputs"]),
    )
    return dict(
        **payload,
        values=values,
        input_fingerprint=canonical_hash(payload),
        missing=[k for k, v in values.items() if v is None],
        unreviewed=[k for k, p in params.items() if not p["is_reviewed"]],
        approval_from_json=False,
        review_mechanism="EXISTING_ReviewedProjectDatum_ONLY_NO_CLI_APPROVAL",
    )


CORE_KEYS = frozenset(
    {
        "unit_width_mm",
        "unit_depth_mm",
        "column_width_mm",
        "cabinet_height_mm",
        "columns_per_unit",
        "plinth_mm",
        "shelf_mm",
        "actual_tier_count",
        "door_kind",
        "hinge_side",
        "door_open_angle_deg",
        "door_frame_mm",
        "hinge_axis_offset_mm",
        "door_leaf_width_mm",
        "door_leaf_height_mm",
        "door_leaf_thickness_mm",
        "door_simultaneity",
        "operation_sequence",
        "static_width_mm",
        "static_depth_mm",
        "body_height_mm",
        "transport_width_mm",
        "transport_depth_mm",
        "activity_width_mm",
        "activity_depth_mm",
        "activity_height_mm",
        "turn_width_mm",
        "turn_depth_mm",
        "operator_standoff_mm",
        "waiting_gap_mm",
        "aisle_required_mm",
        "finish_mm",
        "installation_gap_mm",
        "unit_gap_mm",
        "construction_tolerance_mm",
        "room_clear_height_mm",
        "room_door_intrusion_mm",
        "room_door_kind",
        "reach_low_mm",
        "reach_high_mm",
        "reach_horizontal_mm",
        "front_concurrency",
        "margin_target_mm",
        *(f"tier_{t}_{part}" for t in range(1, 6) for part in ("clear_height_mm", "bottom_mm")),
    }
)


def supported_projection(binding: dict[str, Any]) -> dict[str, Any]:
    v = binding["values"]
    missing = sorted(k for k in CORE_KEYS if v[k] is None)
    if missing:
        return dict(status="INPUT_REQUIRED", missing=missing, unsupported=[], conditions=None)
    unsupported = []

    def require(ok: bool, code: str) -> None:
        if not ok:
            unsupported.append(code)

    pitch = v["column_width_mm"]
    require(
        v["unit_width_mm"] == v["columns_per_unit"] * pitch,
        "UNIT_OUTER_WIDTH_CANNOT_BE_SILENTLY_RESCALED",
    )
    tail = 11 % v["columns_per_unit"]
    if tail:
        if any(v[k] is None for k in ("partial_unit_available", "partial_unit_width_mm")):
            missing.extend(
                [k for k in ("partial_unit_available", "partial_unit_width_mm") if v[k] is None]
            )
        else:
            require(
                v["partial_unit_available"] == "AVAILABLE"
                and v["partial_unit_width_mm"] == tail * pitch,
                "DEDICATED_11_COLUMN_SHIFT_REQUIRES_DOCUMENTED_PARTIAL_UNIT",
            )
    h = v["tier_1_clear_height_mm"]
    for t in range(1, 6):
        require(
            v[f"tier_{t}_clear_height_mm"] == h
            and v[f"tier_{t}_bottom_mm"] == v["plinth_mm"] + (t - 1) * (h + v["shelf_mm"]),
            f"NONUNIFORM_TIER_{t}_NEEDS_PHYSICAL_ADAPTER",
        )
    for ok, code in (
        (
            v["transport_width_mm"] >= 450
            and v["transport_depth_mm"] >= 650
            and v["body_height_mm"] >= 1800
            and v["activity_width_mm"] >= 600
            and v["activity_depth_mm"] >= 900
            and v["waiting_gap_mm"] >= 100
            and v["aisle_required_mm"] >= 1200,
            "DO_NOT_SHRINK_UNREVIEWED_REFERENCE_BODY_ACTIVITY_GAP_OR_PASSAGE_TO_PASS",
        ),
        (v["hinge_side"] == "LEFT", "R10_ADAPTER_LEFT_HINGE_ONLY"),
        (
            v["door_frame_mm"] == v["hinge_axis_offset_mm"] == 20,
            "R10_ADAPTER_FRAME_AND_HINGE_OFFSET_20_ONLY",
        ),
        (v["door_leaf_thickness_mm"] == 15, "R10_ADAPTER_DOOR_THICKNESS_15_ONLY"),
        (
            v["door_leaf_width_mm"] == pitch - 40 and v["door_leaf_height_mm"] == h,
            "DOOR_LEAF_DIMENSIONS_NOT_REPRESENTABLE",
        ),
        (
            v["door_open_angle_deg"] == 90
            and v["door_kind"] in {"OUTWARD_HINGED_90", "NO_PLAN_INTRUSION"},
            "DOOR_MECHANISM_OR_ANGLE_NOT_REPRESENTABLE",
        ),
        (
            v["door_simultaneity"] == "ONE_OPERATOR_PER_COLUMN"
            and v["operation_sequence"] == SEQUENCE,
            "DOOR_RULE_OR_SEQUENCE_NOT_REPRESENTABLE",
        ),
        (
            (v["static_width_mm"], v["static_depth_mm"], v["activity_height_mm"])
            == (v["transport_width_mm"], v["transport_depth_mm"], v["body_height_mm"]),
            "INDEPENDENT_STATIC_OR_ACTIVITY_BODY_NEEDS_ADAPTER",
        ),
        (v["front_concurrency"] == 4, "R10_FIXED_REQUESTED_CONCURRENCY_4_ONLY"),
        (
            (v["reach_low_mm"], v["reach_high_mm"], v["reach_horizontal_mm"]) == (100, 1700, 600),
            "R10_REFERENCE_REACH_PROFILE_NOT_AN_APPROVED_LIMIT",
        ),
        (
            v["room_door_intrusion_mm"] == 0
            and v["room_door_kind"] == "OPEN_RECESSED_WITHOUT_SWEEP",
            "ROOM_DOOR_SWEEP_NEEDS_PHYSICAL_ADAPTER",
        ),
        (
            v["room_clear_height_mm"] >= max(v["body_height_mm"], v["cabinet_height_mm"]),
            "DECLARED_ROOM_HEIGHT_INSUFFICIENT",
        ),
        (0 <= v["margin_target_mm"] <= 150, "R10_FINITE_PADDING_RANGE_0_TO_150_ONLY"),
    ):
        require(ok, code)
    turn = ((math.isqrt(v["transport_width_mm"] ** 2 + v["transport_depth_mm"] ** 2) + 2) // 2) * 2
    require(
        v["turn_width_mm"] == v["turn_depth_mm"] == turn,
        "DECLARED_TURN_ENVELOPE_DIFFERS_FROM_CONTINUOUS_R10_YAW_MODEL",
    )
    if missing or unsupported:
        return dict(
            status="UNSUPPORTED_PHYSICAL_CONFIGURATION" if unsupported else "INPUT_REQUIRED",
            missing=missing,
            unsupported=unsupported,
            conditions=None,
        )
    c = RoomUseConditions(
        **{
            f.name: (
                h
                if f.name == "cell_height_mm"
                else v["unit_depth_mm"]
                if f.name == "column_depth_mm"
                else v["finish_mm"] + v["construction_tolerance_mm"]
                if f.name == "finish_mm"
                else v[f.name]
            )
            for f in fields(RoomUseConditions)
        }
    )
    try:
        c.checked()
    except ValueError as e:
        return dict(
            status="UNSUPPORTED_PHYSICAL_CONFIGURATION",
            missing=[],
            unsupported=[str(e)],
            conditions=None,
        )
    return dict(
        status="SUPPORTED_EXPLICIT_CONDITIONAL_ADAPTER",
        missing=[],
        unsupported=[],
        conditions=asdict(c),
        margin_target_mm=v["margin_target_mm"],
        profile="MIXED",
        construction_tolerance_projection="PER_FACE_INWARD_FINISH_BUDGET_ADDED_TO_FINISH_NOT_AUTHORITY",
        reach_scope="UNCHANGED_UNAPPROVED_R10_REFERENCE_PROFILE_NOT_ERGONOMIC_APPROVAL",
    )


def witness_is_current(binding: dict[str, Any], witness: dict[str, Any]) -> bool:
    # Integrity / matching only; never project review or engineering approval.
    keys = (
        "project_scope_id",
        "physical_room_id",
        "parameters",
        "source_documents",
        "adapter",
        "source_hashes",
        "owner_requirements",
    )
    current = canonical_hash({k: binding[k] for k in keys})
    if current != binding["input_fingerprint"] or binding["values"] != {
        k: p["value"] for k, p in binding["parameters"].items()
    }:
        return False
    if (
        witness.get("input_fingerprint") != binding["input_fingerprint"]
        or witness.get("adapter") != IDENTITY
    ):
        return False
    payload = witness.get("payload")
    return (
        isinstance(payload, dict)
        and payload.get("input_fingerprint") == current
        and canonical_hash(payload) == witness.get("evidence_hash")
    )


def review_calibration(
    ctx: dict[str, Any],
    packet: Mapping[str, Any],
    source_files: Mapping[str, bytes],
    *,
    reviewed_project: Mapping[str, ReviewedProjectDatum] | None = None,
) -> dict[str, Any]:
    binding = bind_physical_inputs(ctx, packet, source_files, reviewed_project=reviewed_project)
    projection = supported_projection(binding)
    cases = []
    # Each width gets a new actual invocation. No saved R10 flow is used as PASS.
    for label, width, index in (("C", 3550, 0), ("3850", 3850, 1)):
        case = None
        if projection["conditions"] is not None:
            case = evaluate_sizing_point(
                ctx["room"],
                ctx["demand"],
                RoomUseConditions(**projection["conditions"]),
                dict(
                    length_mm=26331,
                    width_mm=width,
                    margin_mm=projection["margin_target_mm"],
                    profile="MIXED",
                    mode="R13_FIXED_CASE_RECHECK",
                ),
            )
        site = []
        for r in ctx["overlay"]["records"]:
            p = r["proposals"][index]
            site.append(
                dict(
                    record=r["record"],
                    candidate_hash=r["candidate_hash"],
                    source_file=r["source_file"],
                    outer_bounds_mm=deepcopy(p["expanded_room_bounds_mm"]),
                    zone_intersections=deepcopy(p["zone_intersections"]),
                    corridor_intersections=deepcopy(p["corridor_intersections"]),
                    site=deepcopy(p["site"]),
                    footprint=deepcopy(p["footprint"]),
                    access=deepcopy(p["access"]),
                    status=p["checked_geometry_status"],
                    factory_applicability="NOT_EVALUATED",
                    recomputed_from_archived_geometry=True,
                    uses_archived_functional_pass=False,
                )
            )
        physical = (
            case_physical_checks(case, binding["values"])
            if case
            else dict(
                storage=storage_checks(binding["values"]),
                door_status="NOT_EVALUATED",
                actual_functional_status="INPUT_REQUIRED",
            )
        )
        payload = dict(
            label=label,
            input_fingerprint=binding["input_fingerprint"],
            projection=projection,
            case=case,
            physical_checks=physical,
            site=site,
        )
        witness = dict(
            adapter=IDENTITY,
            input_fingerprint=binding["input_fingerprint"],
            evidence_hash=canonical_hash(payload),
            payload=payload,
        )
        cases.append(
            dict(
                label=label,
                length_mm=26331,
                width_mm=width,
                area_mm2=26331 * width,
                area_m2=area_text(26331 * width),
                physical_room_count=1,
                projection_status=projection["status"],
                functional_status="INPUT_REQUIRED",
                summary=case["summary"] if case else None,
                physical_checks=physical,
                site=site,
                witness=witness,
            )
        )
    historical_b = [
        dict(
            record=r["record"],
            advisory_hash=r["proposals"][2]["advisory_hash"],
            corridor_intersection_m2=r["proposals"][2]["corridor_intersections"][
                "unique_intersection_area_m2"
            ],
            prohibited_intersection_m2=r["proposals"][2]["site"][
                "unique_hard_and_no_build_intersection_area_m2"
            ],
        )
        for r in ctx["overlay"]["records"]
    ]
    return dict(
        identity=IDENTITY,
        task=TASK,
        base_head=BASE_HEAD,
        binding=binding,
        projection=projection,
        cases=cases,
        physical_room_count=1,
        record_aliases=["P01", "P02"],
        parameter_catalog=field_schema(),
        historical_b_preserved=historical_b,
        owner_confirmation_checklist=deepcopy(ctx["overlay"]["owner_confirmation_checklist"]),
        actual_calibration=(
            "INPUT_REQUIRED"
            if binding["missing"] or binding["unreviewed"]
            else "UNSUPPORTED_PHYSICAL_CONFIGURATION"
            if projection["conditions"] is None
            else "REVIEWED_PARAMETER_RECHECK_COMPLETE_NOT_FUNCTIONAL_APPROVAL"
        ),
        engineering_approval="NOT_EVALUATED",
        factory_applicability="NOT_EVALUATED",
        source_type="demo"
        if any(
            d["source_type"] == "HYPOTHETICAL_NOT_APPROVED"
            for d in binding["source_documents"].values()
        )
        else "unreviewed_project_input",
        validity_status="unverified",
        requires_review=True,
        native_solves=0,
        main_executed=False,
        historical_records_changed=False,
        calculation_basis=dict(
            version=IDENTITY,
            units="INTEGER_MM_MM2; ANGLE_INTEGER_DEGREES",
            coefficients=[],
            formulas=[
                "capacity=22*5; demand=53*2",
                "room_area_mm2=26331*width",
                "effective_finish=finish+per_face_inward_tolerance",
                "fresh R10 construction + both complete shift simulations + located margins",
            ],
            assumptions=[
                "Only supported explicit R10 projection; no silent physical substitution",
                "Outer C/3850 bounds unchanged by interior parameters; "
                "R12 overlay recomputed from source",
                "Storage envelope and reach are necessary checks, never hygiene/ergonomic approval",
            ],
            review_status="INPUT_REQUIRED",
        ),
    )


def historical_hypothesis_packet(
    ctx: dict[str, Any], key: str
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Explicit regression fixture, not equipment evidence or an Owner review."""
    if key not in {"R10-L26331-W3550-M50-MIXED", "R10-L26331-W3850-M100-MIXED-SENSITIVITY"}:
        raise ValueError("EXPLICIT_ARCHIVED_REGRESSION_CONDITIONS_REQUIRED")
    old = ctx["source"]["cases"][key]
    g = old["geometry"]
    c, p = g["conditions"], g["parameters"]
    v: dict[str, Any] = {k: None for k in FIELDS}
    v.update({k: x for k, x in c.items() if k in FIELDS})
    turn = ((math.isqrt(c["transport_width_mm"] ** 2 + c["transport_depth_mm"] ** 2) + 2) // 2) * 2
    v.update(
        unit_width_mm=c["column_width_mm"] * c["columns_per_unit"],
        unit_depth_mm=c["column_depth_mm"],
        actual_tier_count=5,
        partial_unit_available="AVAILABLE",
        partial_unit_width_mm=c["column_width_mm"]
        * (11 % c["columns_per_unit"] or c["columns_per_unit"]),
        door_leaf_width_mm=c["column_width_mm"] - 2 * p["frame_mm"],
        door_leaf_height_mm=c["cell_height_mm"],
        door_leaf_thickness_mm=p["leaf_thickness_mm"],
        door_frame_mm=p["frame_mm"],
        hinge_axis_offset_mm=p["frame_mm"],
        door_open_angle_deg=90,
        hinge_side=p["hinge"],
        door_simultaneity="ONE_OPERATOR_PER_COLUMN",
        operation_sequence=SEQUENCE,
        static_width_mm=c["transport_width_mm"],
        static_depth_mm=c["transport_depth_mm"],
        activity_height_mm=c["body_height_mm"],
        turn_width_mm=turn,
        turn_depth_mm=turn,
        reach_low_mm=p["reach_low_mm"],
        reach_high_mm=p["reach_high_mm"],
        reach_horizontal_mm=p["reach_horizontal_mm"],
        front_concurrency=p["front_concurrency"],
        room_door_kind="OPEN_RECESSED_WITHOUT_SWEEP",
        construction_tolerance_mm=0,
        room_clear_height_mm=p["clear_height_mm"],
        margin_target_mm=g["point"]["margin_mm"],
    )
    for tier in range(1, 6):
        v[f"tier_{tier}_clear_height_mm"] = c["cell_height_mm"]
        v[f"tier_{tier}_bottom_mm"] = c["plinth_mm"] + (tier - 1) * (
            c["cell_height_mm"] + c["shelf_mm"]
        )
    payload = dict(
        identity="R13_EXPLICIT_HISTORICAL_REGRESSION_NOT_APPROVED",
        source_case=key,
        source_witness_sha256=old["summary"]["witness_sha256"],
        old_conditions=c,
        old_parameters=p,
        parameters=v,
        formulas=[
            "unit width = old column pitch * columns per unit",
            "turn = existing R9/R10 continuous yaw square",
            "uniform tier bottom = plinth+(tier-1)*(reference clear height+shelf)",
        ],
        warnings=[
            "Partial one-column end units are an unapproved R10 hypothesis, "
            "not a supplier offering",
            "No model, manufacturer, net cell width/depth, clothes or hygiene "
            "data have been supplied",
        ],
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
    )
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode()
    name = "historical-hypothesis-" + ("20-20" if c["finish_mm"] == 20 else "30-40") + ".json"
    packet = input_template(ctx)
    packet["source_documents"]["historical_hypothesis"] = dict(
        source_type="HYPOTHETICAL_NOT_APPROVED",
        file_name=name,
        sha256=hashlib.sha256(data).hexdigest(),
        document_date=None,
        project_scope_id=packet["project_scope_id"],
        reference="Read-only R10 selected evidence / " + key + "; explicit regression only",
    )
    for k, value in v.items():
        if value is not None:
            packet["parameters"][k].update(
                value=value, document_id="historical_hypothesis", locator="/parameters/" + k
            )
    return packet, {name: data}
