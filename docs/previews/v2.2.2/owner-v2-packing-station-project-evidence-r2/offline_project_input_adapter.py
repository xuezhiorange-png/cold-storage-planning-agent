"""Offline, review-register-bound source admission; reuses immutable R1 geometry.

The local reviewer/launcher is trusted, request JSON is not. A register is an
extraction-review record, NOT an execution grant or equipment/engineering approval.
Changing its pinned bytes requires a separately recorded human evidence review.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent
R1 = HERE.parent / "owner-v2-three-person-packing-station-module-r1"
R1_MANIFEST_SHA = "409d0e6bc83d81b51f1664dc611e52b716c250a5b02bfc6ec814339999c306ae"
IDENTITY = "ProjectPackingStationEvidenceV1"
VERSION = "project-packing-station-evidence@1.0.0"
META = (
    "PROJECT_ID",
    "FACTORY_ID",
    "EQUIPMENT_ID",
    "MANUFACTURER",
    "MODEL",
    "DRAWING_NUMBER",
    "DOCUMENT_REVISION",
    "ISSUE_DATE",
    "SOURCE_PATH_OR_URL",
    "SOURCE_FILE_SHA256",
    "SHEET_OR_PAGE",
    "SOURCE_TYPE",
    "PROJECT_APPLICABILITY",
    "SELECTION_STATUS",
    "REVIEW_STATUS",
    "APPROVAL_EVIDENCE",
    "SOURCE_ID",
)
SOURCE_TYPES = (
    "PUBLIC_MANUFACTURER_REFERENCE",
    "PROJECT_CANDIDATE_EQUIPMENT",
    "PROJECT_SELECTED_EQUIPMENT",
    "PROJECT_APPROVED_GEOMETRY",
)
NUMERIC_KEYS = {"BOUNDS_MM", "TRANSLATION_MM", "POINT_MM", "POINTS_MM", "WIDTH_MM", "ROTATION_DEG"}
REQUIRED_REQUEST = {
    "IDENTITY",
    "VERSION",
    "PROJECT_ID",
    "FACTORY_ID",
    "DOCUMENTS",
    "DIMENSIONS",
    "MODULE_TEMPLATE",
    "STRUCTURAL_EVIDENCE",
}


class AdmissionError(ValueError):
    """Stable offline source-admission rejection."""


def encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require(condition: bool, code: str) -> None:
    if not condition:
        raise AdmissionError(code)


def read_json(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw)
    require(isinstance(value, dict), "OBJECT_REQUIRED")
    return cast(dict[str, Any], value)


@dataclass(frozen=True)
class ReviewContext:
    """Immutable bytes supplied by the trusted offline review launcher, never JSON input."""

    raw: bytes

    @property
    def data(self) -> dict[str, Any]:
        return read_json(self.raw)

    @property
    def digest(self) -> str:
        return sha(self.raw)

    @property
    def test_only(self) -> bool:
        return bool(self.data["SCOPE"] == "SOFTWARE_TEST_ONLY")


def load_review_context(path: Path, pinned_sha256: str) -> ReviewContext:
    raw = path.read_bytes()
    require(
        bool(re.fullmatch(r"[0-9a-f]{64}", pinned_sha256)) and sha(raw) == pinned_sha256,
        "PINNED_REVIEW_REGISTER_HASH_MISMATCH",
    )
    data = read_json(raw)
    require(
        data.get("IDENTITY") == "LocalStationEvidenceReviewRegisterV1",
        "REVIEW_REGISTER_IDENTITY_REQUIRED",
    )
    require(
        data.get("SCOPE") in ("PROJECT_EVIDENCE_REVIEW", "SOFTWARE_TEST_ONLY"),
        "REVIEW_SCOPE_REQUIRED",
    )
    require(isinstance(data.get("SOURCES"), dict), "REVIEWED_SOURCE_MAP_REQUIRED")
    require(
        isinstance(data.get("DENIED_SOURCE_HASHES"), list), "KNOWN_TEST_REFERENCE_DENYLIST_REQUIRED"
    )
    return ReviewContext(raw)


def local_file(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and "://" not in relative, "LOCAL_CACHED_SOURCE_REQUIRED")
    rel = Path(relative)
    resolved = (root / rel).resolve()
    require(
        not rel.is_absolute() and resolved.is_relative_to(root.resolve()) and resolved.is_file(),
        "SOURCE_OUTSIDE_PRIVATE_ROOT_OR_MISSING",
    )
    return resolved


def pointer_get(body: Any, path: str) -> Any:
    require(isinstance(path, str) and path.startswith("/"), "JSON_POINTER_REQUIRED")
    node = body
    for part in path[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            require(part.isdigit() and int(part) < len(node), "JSON_POINTER_INDEX_INVALID")
            node = node[int(part)]
        else:
            require(isinstance(node, dict) and part in node, "SOURCE_LOCATION_NOT_FOUND")
            node = node[part]
    return node


def pointer_set(body: Any, path: str, value: Any) -> None:
    parent, name = path.rsplit("/", 1)
    node = pointer_get(body, parent)
    if isinstance(node, list):
        require(name.isdigit() and int(name) < len(node), "TARGET_INDEX_INVALID")
        node[int(name)] = value
    else:
        require(isinstance(node, dict) and name in node, "TARGET_LOCATION_NOT_FOUND")
        node[name] = value


def numeric_slots(body: Any, path: str = "", parent_key: str = "") -> list[str]:
    if isinstance(body, dict):
        return [
            p for key, value in body.items() for p in numeric_slots(value, path + "/" + key, key)
        ]
    if isinstance(body, list):
        return [
            p
            for i, value in enumerate(body)
            for p in numeric_slots(value, path + "/" + str(i), parent_key)
        ]
    return [path] if parent_key in NUMERIC_KEYS else []


def target_semantics(template: dict[str, Any], target: str) -> tuple[str, str]:
    if target.endswith("/ROTATION_DEG"):
        return "ORIENTATION_ANGLE", "ASSEMBLY_GLOBAL" if target.startswith(
            ("/INSTANCES/", "/ASSEMBLY_")
        ) else "STATION_LOCAL"
    if "/TRANSLATION_MM/" in target:
        return "LOCAL_COORDINATE_OFFSET", "ASSEMBLY_GLOBAL" if target.startswith(
            ("/INSTANCES/", "/ASSEMBLY_")
        ) else "STATION_LOCAL"
    if target.endswith("/WIDTH_MM"):
        return "CLEAR_AISLE_DIMENSION", "ASSEMBLY_GLOBAL" if target.startswith(
            "/ASSEMBLY_ROUTES/"
        ) else "STATION_LOCAL"
    if target.startswith("/COMPONENTS/"):
        component = template["COMPONENTS"][int(target.split("/")[2])]
        role = component["COMPONENT_TYPE"]
        kinds = {
            "PACKING_STATION_ENVELOPE": "EQUIPMENT_BODY_COORDINATE",
            "OPERATOR_ENVELOPE": "OPERATOR_ENVELOPE_COORDINATE",
            "MATERIAL_SUPPLY_ENVELOPE": "MATERIAL_ENVELOPE_COORDINATE",
            "PRODUCT_OUTFEED_ENVELOPE": "MATERIAL_ENVELOPE_COORDINATE",
            "CIRCULATION_ENVELOPE": "CIRCULATION_ENVELOPE_COORDINATE",
            "CLEANING_MAINTENANCE_ENVELOPE": "MAINTENANCE_ENVELOPE_COORDINATE",
        }
        return kinds[role], "STATION_LOCAL"
    return "ROUTE_OR_INTERFACE_COORDINATE", "ASSEMBLY_GLOBAL" if target.startswith(
        "/ASSEMBLY_"
    ) else "STATION_LOCAL"


def normalize_value(value: Any, unit: str, kind: str, measurement: str) -> int:
    require(
        type(value) is int
        or (isinstance(value, str) and bool(re.fullmatch(r"-?\d+(?:\.\d+)?", value))),
        "EXPLICIT_INTEGER_OR_DECIMAL_STRING_REQUIRED",
    )
    q = Fraction(value)
    if kind == "ORIENTATION_ANGLE":
        require(unit == "deg" and q in (0, 90, 180, 270), "EXPLICIT_QUARTER_TURN_REQUIRED")
        return int(q)
    require(unit in ("mm", "cm", "m"), "UNSUPPORTED_UNIT_NO_PIXEL_SCALE_INFERENCE")
    q *= {"mm": 1, "cm": 10, "m": 1000}[unit]
    require(q.denominator == 1, "OFF_INTEGER_MM_GRID_NO_ROUNDING")
    if measurement in ("LENGTH", "WIDTH", "HEIGHT", "CLEAR_WIDTH"):
        require(q > 0, "POSITIVE_PHYSICAL_DIMENSION_REQUIRED")
    return q.numerator


def verify_document(
    meta: dict[str, Any], request: dict[str, Any], context: ReviewContext, source_root: Path
) -> tuple[bytes, dict[str, Any]]:
    require(set(meta) == set(META), "COMPLETE_DOCUMENT_IDENTITY_REQUIRED")
    require(meta["SOURCE_TYPE"] in SOURCE_TYPES, "EXPLICIT_SOURCE_CLASSIFICATION_REQUIRED")
    raw = local_file(source_root, meta["SOURCE_PATH_OR_URL"]).read_bytes()
    require(sha(raw) == meta["SOURCE_FILE_SHA256"], "SOURCE_FILE_HASH_MISMATCH")
    policy = context.data
    require(
        sha(raw) not in policy["DENIED_SOURCE_HASHES"],
        "HISTORICAL_SYNTHETIC_OR_REFERENCE_SOURCE_DENIED",
    )
    anchor = policy["SOURCES"].get(meta["SOURCE_ID"])
    require(isinstance(anchor, dict), "SOURCE_BYTES_MATCH_BUT_NO_TRUSTED_REVIEW")
    require(anchor["SOURCE_FILE_SHA256"] == sha(raw), "REVIEWED_SOURCE_HASH_CHANGED")
    require(
        anchor["METADATA_SHA256"] == sha(encode(meta)),
        "DOCUMENT_IDENTITY_REVISION_OR_CLASSIFICATION_CONFLICT",
    )
    require(
        anchor["REVIEW_KIND"] == "EXTRACTION_CHECKED_NOT_ENGINEERING_APPROVAL"
        and bool(anchor["REVIEW_RECORD_ID"])
        and bool(anchor["REVIEWER_ID"]),
        "MANUAL_SOURCE_REVIEW_REQUIRED",
    )
    require(
        meta["SOURCE_TYPE"] != "PUBLIC_MANUFACTURER_REFERENCE",
        "PUBLIC_REFERENCE_NOT_PROJECT_SELECTION",
    )
    require(
        meta["PROJECT_ID"] == request["PROJECT_ID"] == policy["PROJECT_ID"]
        and meta["FACTORY_ID"] == request["FACTORY_ID"] == policy["FACTORY_ID"],
        "PROJECT_FACTORY_ID_MISMATCH",
    )
    require(
        all(
            isinstance(meta[k], str) and meta[k].strip()
            for k in (
                "EQUIPMENT_ID",
                "MANUFACTURER",
                "MODEL",
                "DRAWING_NUMBER",
                "DOCUMENT_REVISION",
                "ISSUE_DATE",
                "SHEET_OR_PAGE",
            )
        ),
        "DOCUMENT_IDENTIFICATION_FIELDS_UNAVAILABLE",
    )
    if meta["SOURCE_TYPE"] in ("PROJECT_SELECTED_EQUIPMENT", "PROJECT_APPROVED_GEOMETRY"):
        require(
            bool(anchor.get("EXISTING_APPROVAL_EVIDENCE_HASHES"))
            and meta["APPROVAL_EVIDENCE"] == anchor["EXISTING_APPROVAL_EVIDENCE_HASHES"],
            "PREEXISTING_SELECTION_EVIDENCE_REQUIRED_NOT_CALLER_APPROVED",
        )
        # This prototype does not verify signatories or grant selection/engineering approval.
        raise AdmissionError(
            "SELECTED_OR_APPROVED_CLASS_REQUIRES_INDEPENDENT_REVIEW_NOT_IMPLEMENTED"
        )
    fmt = anchor["FORMAT"]
    if fmt == "JSON":
        body = read_json(raw)
        require(
            body.get("PURPOSE")
            == ("SOFTWARE_TEST_ONLY" if context.test_only else "PROJECT_ENGINEERING_INPUT"),
            "SOURCE_PURPOSE_CANNOT_BE_RELABELLED_AS_REAL_PROJECT",
        )
    return raw, anchor


def extracted(raw: bytes, location: dict[str, Any], anchor: dict[str, Any]) -> Any:
    fmt = location["FORMAT"]
    require(fmt == anchor["FORMAT"], "SOURCE_FORMAT_CONFLICT")
    if fmt == "JSON":
        return pointer_get(read_json(raw), location["JSON_POINTER"])
    if fmt in ("TEXT_CALLOUT", "PDF_TEXT_CALLOUT"):
        if fmt == "TEXT_CALLOUT":
            text = raw.decode("utf-8")
        else:
            import fitz

            try:
                with fitz.open(stream=raw, filetype="pdf") as doc:
                    page = location["PAGE"]
                    require(type(page) is int and 1 <= page <= len(doc), "PDF_PAGE_INVALID")
                    text = doc[page - 1].get_text()
            except (RuntimeError, ValueError) as exc:
                raise AdmissionError("PDF_TEXT_UNREADABLE_MANUAL_REVIEW_REQUIRED") from exc
        pattern = re.compile(
            r"^" + re.escape(location["CALLOUT_KEY"]) + r"\s*=\s*(-?\d+(?:\.\d+)?)\s+(mm|cm|m|deg)$"
        )
        hits = [
            match.groups()
            for line in text.splitlines()
            if (match := pattern.fullmatch(line.strip()))
        ]
        require(len(hits) == 1, "EXPLICIT_UNAMBIGUOUS_CALLOUT_REQUIRED_NO_IMAGE_MEASUREMENT")
        return {"VALUE": hits[0][0], "UNIT": hits[0][1]}
    raise AdmissionError("FORMAT_REQUIRES_MANUAL_REVIEW_NO_CAD_OR_IMAGE_SCALE_GUESS")


def load_r1() -> tuple[Any, Any]:
    raw = (R1 / "source_manifest.json").read_bytes()
    require(sha(raw) == R1_MANIFEST_SHA, "R1_MANIFEST_CHANGED")
    for name, expected in read_json(raw)["files"].items():
        require(sha((R1 / name).read_bytes()) == expected, "R1_FILE_CHANGED:" + name)

    def module(name: str, filename: str) -> Any:
        old = sys.modules.get(name)
        if old is not None:
            require(
                Path(str(old.__file__)).resolve() == (R1 / filename).resolve(),
                "FOREIGN_R1_MODULE_NAME_COLLISION",
            )
            return old
        spec = importlib.util.spec_from_file_location(name, R1 / filename)
        require(spec is not None and spec.loader is not None, "R1_MODULE_UNAVAILABLE")
        assert spec and spec.loader
        result = importlib.util.module_from_spec(spec)
        sys.modules[name] = result
        spec.loader.exec_module(result)
        return result

    geometry = module("offline_station_geometry", "offline_station_geometry.py")
    renderer = module("offline_station_renderer", "offline_station_renderer.py")
    return geometry, renderer


def required_result() -> dict[str, Any]:
    return {
        "IDENTITY": IDENTITY,
        "VERSION": VERSION,
        "PROJECT_INPUT_ADMISSION": "BLOCKED",
        "PROJECT_SELECTED_EQUIPMENT": "UNAVAILABLE",
        "STAGES": {"DISCOVERED": "NOT_EVALUATED"},
        "DOCUMENTS": [],
        "DIMENSION_RECORDS": [],
        "BLOCKERS": [],
        "MISSING_INPUTS": [],
        "OPERATOR_LAYOUT_STATUS": "REVIEW_REQUIRED",
        "OPERATOR_FIT_APPROVED": False,
        "CLEAR_WIDTH_STATUS": "UNAVAILABLE",
        "MODULE_ENGINEERING_APPROVAL": "NOT_APPROVED",
        "REAL_PROJECT_MODULE_VALIDATED": False,
        "FORMAL_MODULE_DIMENSIONS_APPROVED": False,
        "PACKAGING_AREA_CALIBRATION_READY": False,
        "FORMAL_P1_AUTHORITY_APPROVED": False,
        "FUNCTIONAL_ROOM_AREA": None,
        "FIT_18_TABLES": "NOT_EVALUATED",
        "FIT_28_TABLES": "NOT_EVALUATED",
        "REAL_FACTORY_SOLVES": 0,
        "NATIVE_SOLVER_CALLS": 0,
        "NEW_OWNER_GRANT": False,
    }


def adapt(
    request: dict[str, Any], context: ReviewContext, source_root: Path
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    result = required_result()
    try:
        require(
            isinstance(request, dict) and set(request) == REQUIRED_REQUEST,
            "EXACT_REQUEST_FIELDS_NO_VERIFIED_APPROVED_OR_REGISTER_OVERRIDE",
        )
        require(
            request["IDENTITY"] == IDENTITY and request["VERSION"] == VERSION,
            "PROJECT_EVIDENCE_VERSION_REQUIRED",
        )
        require(
            context.data["PROJECT_ID"] == request["PROJECT_ID"]
            and context.data["FACTORY_ID"] == request["FACTORY_ID"],
            "PROJECT_FACTORY_ID_MISMATCH",
        )
        require(
            isinstance(request["DOCUMENTS"], list) and isinstance(request["DIMENSIONS"], list),
            "SOURCE_AND_DIMENSION_LISTS_REQUIRED",
        )
        result.update(
            PROJECT_ID=request["PROJECT_ID"],
            FACTORY_ID=request["FACTORY_ID"],
            REVIEW_REGISTER_SHA256=context.digest,
            SCOPE="SOFTWARE_TEST_ONLY" if context.test_only else "PROJECT_EVIDENCE_REVIEW",
        )
        stages = result["STAGES"] = {
            "DISCOVERED": "COMPLETE",
            "INDEXED": "COMPLETE",
            "SOURCE_BYTES_VERIFIED": "NOT_COMPLETE",
            "DIMENSIONS_EXTRACTED": "NOT_COMPLETE",
            "GEOMETRY_NORMALIZED": "NOT_COMPLETE",
            "GEOMETRY_DIAGNOSTIC_COMPLETE": "NOT_EXECUTED",
            "ENGINEERING_REVIEW_REQUIRED": True,
        }
        sources: dict[str, tuple[bytes, dict[str, Any]]] = {}
        for meta in request["DOCUMENTS"]:
            try:
                key = meta["SOURCE_ID"]
                require(key not in sources, "DUPLICATE_SOURCE_ID")
                sources[key] = verify_document(meta, request, context, source_root)
                result["DOCUMENTS"].append(
                    {
                        "SOURCE_ID": key,
                        "STATUS": "SOURCE_BYTES_AND_REVIEW_PIN_MATCH_ONLY",
                        "SOURCE_FILE_SHA256": meta["SOURCE_FILE_SHA256"],
                        "SOURCE_TYPE": meta["SOURCE_TYPE"],
                        "DOCUMENT_REVISION": meta["DOCUMENT_REVISION"],
                        "SELECTION_STATUS": "NOT_GRANTED_BY_ADAPTER",
                    }
                )
            except (AdmissionError, KeyError, TypeError, OSError, ValueError) as exc:
                result["BLOCKERS"].append(str(exc))
        require(bool(sources), "PROJECT_SOURCE_DOCUMENTS_REQUIRED")
        require(not result["BLOCKERS"], "SOURCE_VERIFICATION_INCOMPLETE")
        stages["SOURCE_BYTES_VERIFIED"] = "COMPLETE_NOT_AUTHENTICATION_OR_APPROVAL"
        revisions: dict[tuple[str, str], set[str]] = {}
        for meta in request["DOCUMENTS"]:
            revisions.setdefault((meta["EQUIPMENT_ID"], meta["DRAWING_NUMBER"]), set()).add(
                meta["DOCUMENT_REVISION"]
            )
        require(
            all(len(values) == 1 for values in revisions.values()),
            "UNRESOLVED_DRAWING_REVISION_CONFLICT",
        )
        template = request["MODULE_TEMPLATE"]
        structure = request["STRUCTURAL_EVIDENCE"]
        require(
            isinstance(template, dict) and isinstance(structure, dict),
            "SOURCED_TASK_STATE_AND_MODULE_STRUCTURE_REQUIRED",
        )
        raw, anchor = sources[structure["SOURCE_ID"]]
        require(
            anchor["STRUCTURAL_RECORD_SHA256"] == sha(encode(structure)),
            "STRUCTURAL_SOURCE_LOCATION_NOT_REVIEWED",
        )
        require(
            extracted(raw, structure["SOURCE_LOCATION"], anchor) == template,
            "TASK_STATE_OR_TEMPLATE_SOURCE_MISMATCH",
        )
        result["STRUCTURAL_EVIDENCE"] = deepcopy(structure)
        result["DOCUMENT_METADATA"] = deepcopy(request["DOCUMENTS"])
        require(
            template["PROJECT_ID"] == request["PROJECT_ID"]
            and template["MODE"] == "OWNER_PROJECT"
            and template["SOURCES"] == {},
            "NO_CALLER_R1_SOURCE_OR_MODE_OVERRIDE",
        )
        slots = set(numeric_slots(template))
        require(
            all(pointer_get(template, path) is None for path in slots),
            "UNBOUND_NUMERIC_TEMPLATE_VALUE_NO_DEFAULTS",
        )
        module = deepcopy(template)
        used, record_ids = set(), set()
        body_sizes: dict[str, dict[str, int]] = {}
        for record in request["DIMENSIONS"]:
            normalized: dict[str, Any] = {
                **record,
                "NORMALIZED_VALUE": None,
                "VALIDATION_STATUS": "UNAVAILABLE",
            }
            result["DIMENSION_RECORDS"].append(normalized)
            try:
                key = record["RECORD_ID"]
                require(key not in record_ids, "DUPLICATE_DIMENSION_RECORD")
                record_ids.add(key)
                raw, anchor = sources[record["SOURCE_ID"]]
                require(
                    anchor["DIMENSION_RECORD_HASHES"].get(key) == sha(encode(record)),
                    "DIMENSION_LOCATION_OR_SEMANTICS_NOT_REVIEWED",
                )
                require(
                    record["EXTRACTION_METHOD"]
                    in ("EXPLICIT_STRUCTURED_CALLOUT", "EXPLICIT_TEXT_CALLOUT"),
                    "NO_PIXEL_OR_UNCALIBRATED_SCALE_EXTRACTION",
                )
                found = extracted(raw, record["SOURCE_LOCATION"], anchor)
                require(
                    isinstance(found, dict) and found.get("VALUE") is not None,
                    "DIMENSION_CALLOUT_UNAVAILABLE",
                )
                require(
                    found["VALUE"] == record["VALUE"] and found["UNIT"] == record["UNIT"],
                    "DIMENSION_VALUE_OR_UNIT_MISMATCH",
                )
                if record["SOURCE_LOCATION"]["FORMAT"] == "JSON":
                    require(
                        found["DIMENSION_TYPE"] == record["DIMENSION_TYPE"]
                        and found["COORDINATE_REFERENCE"] == record["COORDINATE_REFERENCE"],
                        "DIMENSION_CLASS_OR_FRAME_MISMATCH",
                    )
                value = normalize_value(
                    record["VALUE"], record["UNIT"], record["DIMENSION_TYPE"], record["MEASUREMENT"]
                )
                target = record["TARGET_PATH"]
                if target is not None:
                    require(
                        target in slots and target not in used,
                        "DUPLICATE_OR_UNKNOWN_NUMERIC_TARGET",
                    )
                    require(
                        (record["DIMENSION_TYPE"], record["COORDINATE_REFERENCE"])
                        == target_semantics(template, target),
                        "DIMENSION_TYPE_CANNOT_SUBSTITUTE_EQUIPMENT_AISLE_OR_ROOM",
                    )
                    pointer_set(module, target, value)
                    used.add(target)
                else:
                    require(
                        record["DIMENSION_TYPE"] == "EQUIPMENT_BODY_DIMENSION"
                        and record["MEASUREMENT"] in ("LENGTH", "WIDTH", "HEIGHT"),
                        "UNTARGETED_RECORD_NOT_BODY_SIZE",
                    )
                    sizes = body_sizes.setdefault(record["COMPONENT_ID"], {})
                    require(record["MEASUREMENT"] not in sizes, "DUPLICATE_BODY_DIMENSION")
                    sizes[record["MEASUREMENT"]] = value
                normalized.update(
                    NORMALIZED_VALUE=value,
                    NORMALIZED_UNIT="deg" if record["UNIT"] == "deg" else "mm",
                    VALIDATION_STATUS="EXPLICIT_SOURCE_AND_REVIEW_MATCH_NOT_APPROVAL",
                )
            except (AdmissionError, KeyError, TypeError, OSError, ValueError) as exc:
                result["BLOCKERS"].append(str(exc))
        result["MISSING_INPUTS"] = sorted(slots - used)
        require(not result["MISSING_INPUTS"], "MISSING_SOURCED_GEOMETRY_NO_DEFAULTS")
        for component in module["COMPONENTS"]:
            if component["ROLE"] != "BODY":
                continue
            sizes = body_sizes.get(component["COMPONENT_ID"], {})
            require(
                set(sizes) == {"LENGTH", "WIDTH", "HEIGHT"}, "BODY_LENGTH_WIDTH_HEIGHT_REQUIRED"
            )
            a, b, c, d = component["GEOMETRY"]["BOUNDS_MM"]
            require(
                c - a == sizes["LENGTH"] and d - b == sizes["WIDTH"],
                "BODY_SIZE_AND_COORDINATE_EXTENT_MISMATCH",
            )
        require(not result["BLOCKERS"], "DIMENSION_EXTRACTION_INCOMPLETE")
        stages["DIMENSIONS_EXTRACTED"] = "COMPLETE_SOURCE_BOUND"
        stages["GEOMETRY_NORMALIZED"] = "COMPLETE_INTEGER_MM_QUARTER_TURNS"
        module["MODE"] = "SYNTHETIC_TEST" if context.test_only else "OWNER_PROJECT"
        result["PROJECT_INPUT_ADMISSION"] = (
            "SOFTWARE_TEST_ONLY" if context.test_only else "ADMITTED_FOR_UNAPPROVED_GEOMETRY_ONLY"
        )
        return result, module
    except (AdmissionError, KeyError, TypeError, OSError, ValueError) as exc:
        result["BLOCKERS"].append(str(exc))
        result["MISSING_INPUTS"] = result["MISSING_INPUTS"] or [
            "Reviewed project equipment, operator, route and four-state source evidence"
        ]
        return result, None


def bind_r1_evidence(
    module: dict[str, Any], result: dict[str, Any], directory: Path
) -> dict[str, Any]:
    """Private derived bridge, not original evidence nor a public project approval."""
    bound = deepcopy(module)
    collections = (
        ("COMPONENTS", "COMPONENT", "COMPONENT_ID"),
        ("OPERATORS", "OPERATOR", "OPERATOR_ID"),
        ("INTERFACES", "INTERFACE", "INTERFACE_ID"),
        ("ROUTES", "ROUTE", "ROUTE_ID"),
        ("INSTANCES", "INSTANCE", "INSTANCE_ID"),
        ("ASSEMBLY_CIRCULATION", "ASSEMBLY", "COMPONENT_ID"),
        ("ASSEMBLY_ROUTES", "ASSEMBLY_ROUTE", "ROUTE_ID"),
        ("SHARING_CONDITIONS", "SHARING", "RULE_ID"),
    )
    facts = {}
    for group, prefix, field in collections:
        for record in bound[group]:
            record["SOURCE_ID"] = "admitted"
            facts[prefix + ":" + record[field]] = record
    kind = "SYNTHETIC_TEST_GEOMETRY" if result["SCOPE"] == "SOFTWARE_TEST_ONLY" else "PROJECT_INPUT"
    evidence = {
        "EVIDENCE_KIND": kind,
        "PROJECT_ID": bound["PROJECT_ID"],
        "FACTS": facts,
        "PROVENANCE": {
            "REVIEW_REGISTER_SHA256": result["REVIEW_REGISTER_SHA256"],
            "SOURCE_DOCUMENTS": result["DOCUMENTS"],
            "DIMENSION_RECORDS": result["DIMENSION_RECORDS"],
            "STRUCTURAL_EVIDENCE": result["STRUCTURAL_EVIDENCE"],
        },
        "APPROVAL": "NOT_APPROVED; derived geometry bridge only",
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "derived-r1-evidence.json"
    path.write_bytes(encode(evidence))
    bound["SOURCES"] = {
        "admitted": {"PATH": path.name, "SHA256": sha(path.read_bytes()), "EVIDENCE_KIND": kind}
    }
    return bound
