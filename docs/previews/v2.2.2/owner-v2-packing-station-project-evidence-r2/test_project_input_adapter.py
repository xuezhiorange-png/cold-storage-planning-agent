"""Offline admission tests. Every positive geometry case is SOFTWARE_TEST_ONLY."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import offline_project_diagnostic as diagnostic
import offline_project_input_adapter as adapter
import software_test_evidence as fixtures


def run_case(
    root: Path, request: dict[str, Any], document: dict[str, Any], register: dict[str, Any]
) -> dict[str, Any]:
    context = fixtures.resign(root, request, document, register)
    return diagnostic.diagnose(request, context, root, root / "result")


def test_bound_source_pipeline_is_synthetic_not_project_approval(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    result = run_case(tmp_path, q, b, r)
    assert result["PROJECT_INPUT_ADMISSION"] == "SOFTWARE_TEST_ONLY"
    assert result["R1_DIAGNOSTIC"]["GEOMETRY_INPUT_STATUS"] == "VALID_SOURCE_BOUND_OFFLINE_INPUT"
    assert result["R1_DIAGNOSTIC"]["PHYSICAL_COMPONENT_STATUS"] == "GEOMETRY_PASS_ONLY"
    assert result["MODULE_ENGINEERING_APPROVAL"] == "NOT_APPROVED"
    assert result["FUNCTIONAL_ROOM_AREA"] is None
    assert result["REAL_FACTORY_SOLVES"] == result["NATIVE_SOLVER_CALLS"] == 0
    assert result["NEW_OWNER_GRANT"] is False
    assert result["FIT_18_TABLES"] == result["FIT_28_TABLES"] == "NOT_EVALUATED"
    assert result["PROJECT_SELECTED_EQUIPMENT"] == "UNAVAILABLE"


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("hash", "SOURCE_FILE_HASH_MISMATCH"),
        ("identity", "PROJECT_FACTORY_ID_MISMATCH"),
        ("revision", "DOCUMENT_IDENTITY_REVISION_OR_CLASSIFICATION_CONFLICT"),
        ("unreviewed", "SOURCE_BYTES_MATCH_BUT_NO_TRUSTED_REVIEW"),
        ("denied", "HISTORICAL_SYNTHETIC_OR_REFERENCE_SOURCE_DENIED"),
        ("numeric", "UNBOUND_NUMERIC_TEMPLATE_VALUE_NO_DEFAULTS"),
        ("task", "TASK_STATE_OR_TEMPLATE_SOURCE_MISMATCH"),
        ("claim", "DIMENSION_LOCATION_OR_SEMANTICS_NOT_REVIEWED"),
        ("verified", "EXACT_REQUEST_FIELDS_NO_VERIFIED_APPROVED_OR_REGISTER_OVERRIDE"),
        ("approved", "EXACT_REQUEST_FIELDS_NO_VERIFIED_APPROVED_OR_REGISTER_OVERRIDE"),
        ("register", "EXACT_REQUEST_FIELDS_NO_VERIFIED_APPROVED_OR_REGISTER_OVERRIDE"),
        ("purpose", "SOURCE_PURPOSE_CANNOT_BE_RELABELLED_AS_REAL_PROJECT"),
        ("traversal", "SOURCE_OUTSIDE_PRIVATE_ROOT_OR_MISSING"),
    ],
)
def test_untrusted_request_cannot_promote_or_mutate_evidence(
    tmp_path: Path, mutation: str, code: str
) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    if mutation == "hash":
        q["DOCUMENTS"][0]["SOURCE_FILE_SHA256"] = "0" * 64
    elif mutation == "identity":
        q["PROJECT_ID"] = "REAL_PROJECT"
    elif mutation == "revision":
        q["DOCUMENTS"][0]["DOCUMENT_REVISION"] = "B"
    elif mutation == "unreviewed":
        r["SOURCES"] = {}
    elif mutation == "denied":
        r["DENIED_SOURCE_HASHES"] = [adapter.sha(adapter.encode(b))]
    elif mutation == "numeric":
        adapter.pointer_set(q["MODULE_TEMPLATE"], q["DIMENSIONS"][0]["TARGET_PATH"], 5600)
        b["module_template"] = q["MODULE_TEMPLATE"]
        fixtures.resign(tmp_path, q, b, r)
    elif mutation == "task":
        q["MODULE_TEMPLATE"] = deepcopy(q["MODULE_TEMPLATE"])
        q["MODULE_TEMPLATE"]["OPERATORS"][0]["TASK"] = "caller-invented"
    elif mutation == "claim":
        q["DIMENSIONS"][0]["VALUE"] = 5600
    elif mutation in ("verified", "approved", "register"):
        q[
            {"verified": "verified", "approved": "APPROVED", "register": "REVIEW_REGISTER"}[
                mutation
            ]
        ] = True
    elif mutation == "purpose":
        b["PURPOSE"] = "PROJECT_ENGINEERING_INPUT"
        fixtures.resign(tmp_path, q, b, r)
    elif mutation == "traversal":
        q["DOCUMENTS"][0]["SOURCE_PATH_OR_URL"] = "../../private-file"
    result, module = adapter.adapt(q, adapter.ReviewContext(adapter.encode(r)), tmp_path)
    assert module is None
    assert result["PROJECT_INPUT_ADMISSION"] == "BLOCKED"
    assert code in result["BLOCKERS"]


@pytest.mark.parametrize(
    "classification",
    ["PUBLIC_MANUFACTURER_REFERENCE", "PROJECT_SELECTED_EQUIPMENT", "PROJECT_APPROVED_GEOMETRY"],
)
def test_reference_and_caller_approval_cannot_be_project_selection(
    tmp_path: Path, classification: str
) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    q["DOCUMENTS"][0]["SOURCE_TYPE"] = classification
    context = fixtures.resign(tmp_path, q, b, r)
    result, module = adapter.adapt(q, context, tmp_path)
    assert module is None and result["PROJECT_SELECTED_EQUIPMENT"] == "UNAVAILABLE"


def test_pin_mismatch_rejected(tmp_path: Path) -> None:
    _, _, register = fixtures.fixture(tmp_path)
    path = tmp_path / "register.json"
    path.write_bytes(adapter.encode(register))
    with pytest.raises(adapter.AdmissionError, match="PINNED_REVIEW_REGISTER_HASH_MISMATCH"):
        adapter.load_review_context(path, "0" * 64)
    assert adapter.load_review_context(path, adapter.sha(path.read_bytes())).test_only


def test_matching_bytes_without_any_review_are_not_admitted(tmp_path: Path) -> None:
    q, _, r = fixtures.fixture(tmp_path)
    r["SOURCES"] = {}
    result = diagnostic.diagnose(
        q, adapter.ReviewContext(adapter.encode(r)), tmp_path, tmp_path / "out"
    )
    assert result["PROJECT_INPUT_ADMISSION"] == "BLOCKED"
    svg = (tmp_path / "out" / "project-input-required.svg").read_bytes()
    ET.fromstring(svg)
    assert b"NO DIMENSIONED PROJECT DRAWING" in svg
    assert b"NOT_P1_AUTHORITY" in svg
    assert not (tmp_path / "out" / "PROJECT_STATION_DIAGNOSTIC.svg").exists()


@pytest.mark.parametrize(
    "value,unit,expected",
    [(2400, "mm", 2400), ("2.4", "m", 2400), ("240", "cm", 2400), (0, "mm", 0), (-7, "mm", -7)],
)
def test_exact_integer_mm_conversion(value: Any, unit: str, expected: int) -> None:
    assert (
        adapter.normalize_value(value, unit, "EQUIPMENT_BODY_COORDINATE", "COORDINATE") == expected
    )


@pytest.mark.parametrize(
    "value,unit",
    [(True, "mm"), (2.4, "m"), ("0.0001", "m"), (2400, "pixels"), (0, "mm"), (-1, "mm")],
)
def test_bad_or_nonpositive_dimensions_not_guessed(value: Any, unit: str) -> None:
    with pytest.raises(adapter.AdmissionError):
        adapter.normalize_value(value, unit, "EQUIPMENT_BODY_DIMENSION", "LENGTH")


def test_text_callout_not_image_scaling() -> None:
    assert adapter.extracted(
        b"L = 2.4 m\n", {"FORMAT": "TEXT_CALLOUT", "CALLOUT_KEY": "L"}, {"FORMAT": "TEXT_CALLOUT"}
    ) == {"VALUE": "2.4", "UNIT": "m"}
    for raw in (b"L approximately 2.4 m", b"L = 2.4 m\nL = 2.5 m"):
        with pytest.raises(adapter.AdmissionError):
            adapter.extracted(
                raw, {"FORMAT": "TEXT_CALLOUT", "CALLOUT_KEY": "L"}, {"FORMAT": "TEXT_CALLOUT"}
            )
    with pytest.raises(adapter.AdmissionError):
        adapter.extracted(b"image", {"FORMAT": "IMAGE_SCALE"}, {"FORMAT": "IMAGE_SCALE"})


@pytest.mark.parametrize(
    "kind", ["STATION_PITCH", "ROOM_CLEAR_INTERNAL_DIMENSION", "BUILDING_EXTERNAL_DIMENSION"]
)
def test_dimension_classes_cannot_substitute_for_equipment(tmp_path: Path, kind: str) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    record = q["DIMENSIONS"][0]
    record["DIMENSION_TYPE"] = kind
    b["dimensions"][record["RECORD_ID"]]["DIMENSION_TYPE"] = kind
    context = fixtures.resign(tmp_path, q, b, r)
    result, module = adapter.adapt(q, context, tmp_path)
    assert module is None
    assert "DIMENSION_TYPE_CANNOT_SUBSTITUTE_EQUIPMENT_AISLE_OR_ROOM" in result["BLOCKERS"]


def test_missing_dimension_no_historical_pitch_default(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    removed = q["DIMENSIONS"].pop(0)
    context = fixtures.resign(tmp_path, q, b, r)
    result, module = adapter.adapt(q, context, tmp_path)
    assert module is None
    assert removed["TARGET_PATH"] in result["MISSING_INPUTS"]


def test_body_height_required_and_body_not_module_size(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    q["DIMENSIONS"] = [v for v in q["DIMENSIONS"] if v["MEASUREMENT"] != "HEIGHT"]
    context = fixtures.resign(tmp_path, q, b, r)
    result, module = adapter.adapt(q, context, tmp_path)
    assert module is None
    assert "BODY_LENGTH_WIDTH_HEIGHT_REQUIRED" in result["BLOCKERS"]


def test_three_operator_identity_and_tasks_preserved(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    result = run_case(tmp_path, q, b, r)
    normalized = json.loads((tmp_path / "result" / "normalized-module.json").read_bytes())
    assert {v["OPERATOR_ID"] for v in normalized["OPERATORS"]} == {
        "OPERATOR_1",
        "OPERATOR_2",
        "OPERATOR_3",
    }
    assert all(v["TASK"] and v["SOURCE_ID"] == "admitted" for v in normalized["OPERATORS"])
    assert result["OPERATOR_FIT_APPROVED"] is False
    assert normalized["SHIFT_CHANGE"]["DURATION_MINUTES"] is None
    assert result["PATH_DIAGNOSTICS"]["ACTUAL_GEOMETRIC_CLEARANCE_MM"] is None


@pytest.mark.parametrize("missing", ["OPERATORS", "ROUTES", "MAINTENANCE"])
def test_missing_functional_evidence_does_not_pass(tmp_path: Path, missing: str) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    if missing == "MAINTENANCE":
        for component in q["MODULE_TEMPLATE"]["COMPONENTS"]:
            component["ACTIVE_STATES"] = [
                s for s in component["ACTIVE_STATES"] if s != "MAINTENANCE"
            ]
    else:
        q["MODULE_TEMPLATE"][missing] = []
    b["module_template"] = deepcopy(q["MODULE_TEMPLATE"])
    result = run_case(tmp_path, q, b, r)
    assert result["MODULE_ENGINEERING_APPROVAL"] == "NOT_APPROVED"
    assert result["OPERATOR_FIT_APPROVED"] is False
    if missing == "MAINTENANCE":
        assert result["R1_DIAGNOSTIC"]["MAINTENANCE_STATUS"] != "PASS"
    else:
        assert result["PROJECT_INPUT_ADMISSION"] == "BLOCKED"


def test_known_entity_collision_remains_detected(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    # Move body onto standing regions; preserve standing/entry interface consistency.
    index = next(i for i, c in enumerate(q["MODULE_TEMPLATE"]["COMPONENTS"]) if c["ROLE"] == "BODY")
    for record in q["DIMENSIONS"]:
        if record["TARGET_PATH"] in (
            f"/COMPONENTS/{index}/GEOMETRY/BOUNDS_MM/1",
            f"/COMPONENTS/{index}/GEOMETRY/BOUNDS_MM/3",
        ):
            record["VALUE"] -= 700
            b["dimensions"][record["RECORD_ID"]]["VALUE"] = record["VALUE"]
    result = run_case(tmp_path, q, b, r)
    assert result["R1_DIAGNOSTIC"]["PHYSICAL_COMPONENT_STATUS"] == "FAIL"
    assert result["R1_DIAGNOSTIC"]["GEOMETRIC_COLLISIONS"]


@pytest.mark.parametrize(
    "arrangement", ["LINEAR_ARRANGEMENT", "OPPOSED_ARRANGEMENT", "PARALLEL_ROWS"]
)
def test_multi_station_reuses_r1_union_routes_and_transforms(
    tmp_path: Path, arrangement: str
) -> None:
    q, b, r = fixtures.fixture(tmp_path, arrangement)
    result = run_case(tmp_path, q, b, r)
    assert result["PROJECT_INPUT_ADMISSION"] == "SOFTWARE_TEST_ONLY"
    assert result["R1_DIAGNOSTIC"]["GEOMETRY_INPUT_STATUS"] == "VALID_SOURCE_BOUND_OFFLINE_INPUT"
    assert result["R1_DIAGNOSTIC"]["FUNCTIONAL_ROOM_AREA"] is None


def test_deterministic_bytes_and_svg_safety(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    context = fixtures.resign(tmp_path, q, b, r)
    a = diagnostic.diagnose(q, context, tmp_path, tmp_path / "a")
    c = diagnostic.diagnose(q, context, tmp_path, tmp_path / "c")
    assert adapter.encode(a) == adapter.encode(c)
    svg = (tmp_path / "a" / a["SVG"]["PATH"]).read_bytes()
    assert svg == (tmp_path / "c" / c["SVG"]["PATH"]).read_bytes()
    assert b"SYNTHETIC_TEST_GEOMETRY" in svg
    root = ET.fromstring(svg)
    assert not any(e.tag.endswith(("script", "foreignObject")) for e in root.iter())
    assert not any("href" in k or k.lower().startswith("on") for e in root.iter() for k in e.attrib)


def test_historical_r1_manifest_unmodified() -> None:
    adapter.load_r1()
    assert (
        adapter.sha((adapter.R1 / "source_manifest.json").read_bytes()) == adapter.R1_MANIFEST_SHA
    )


def test_no_overwrite_private_diagnostic(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    context = fixtures.resign(tmp_path, q, b, r)
    with pytest.raises(adapter.AdmissionError, match="FRESH_OUTPUT_DIRECTORY_REQUIRED"):
        diagnostic.diagnose(q, context, tmp_path, tmp_path)


def test_two_reviewed_revisions_conflict_instead_of_choosing_latest(tmp_path: Path) -> None:
    q, _, r = fixtures.fixture(tmp_path)
    second = deepcopy(q["DOCUMENTS"][0])
    second.update(SOURCE_ID="SECOND-REVISION", DOCUMENT_REVISION="B")
    q["DOCUMENTS"].append(second)
    anchor = deepcopy(r["SOURCES"]["TEST-DOC"])
    anchor["METADATA_SHA256"] = adapter.sha(adapter.encode(second))
    r["SOURCES"][second["SOURCE_ID"]] = anchor
    result, module = adapter.adapt(q, adapter.ReviewContext(adapter.encode(r)), tmp_path)
    assert module is None
    assert "UNRESOLVED_DRAWING_REVISION_CONFLICT" in result["BLOCKERS"]


def test_rehashing_synthetic_file_does_not_refresh_review(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    b["PURPOSE"] = "PROJECT_ENGINEERING_INPUT"
    raw = adapter.encode(b)
    (tmp_path / "test-source.json").write_bytes(raw)
    q["DOCUMENTS"][0]["SOURCE_FILE_SHA256"] = adapter.sha(raw)
    result, module = adapter.adapt(q, adapter.ReviewContext(adapter.encode(r)), tmp_path)
    assert module is None and "REVIEWED_SOURCE_HASH_CHANGED" in result["BLOCKERS"]


def test_changing_test_context_scope_does_not_promote_test_file(tmp_path: Path) -> None:
    q, _, r = fixtures.fixture(tmp_path)
    r["SCOPE"] = "PROJECT_EVIDENCE_REVIEW"
    result, module = adapter.adapt(q, adapter.ReviewContext(adapter.encode(r)), tmp_path)
    assert module is None
    assert "SOURCE_PURPOSE_CANNOT_BE_RELABELLED_AS_REAL_PROJECT" in result["BLOCKERS"]


def test_reviewed_wrong_body_size_does_not_override_geometry(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    record = next(v for v in q["DIMENSIONS"] if v["MEASUREMENT"] == "LENGTH")
    record["VALUE"] = 5600
    b["dimensions"][record["RECORD_ID"]]["VALUE"] = 5600
    context = fixtures.resign(tmp_path, q, b, r)
    result, module = adapter.adapt(q, context, tmp_path)
    assert module is None
    assert "BODY_SIZE_AND_COORDINATE_EXTENT_MISMATCH" in result["BLOCKERS"]


def test_cli_works_from_other_directory_and_preserves_review_boundary(tmp_path: Path) -> None:
    q, b, r = fixtures.fixture(tmp_path)
    fixtures.resign(tmp_path, q, b, r)
    (tmp_path / "request.json").write_bytes(adapter.encode(q))
    (tmp_path / "register.json").write_bytes(adapter.encode(r))
    command = [
        sys.executable,
        str(adapter.HERE / "offline_project_diagnostic.py"),
        str(tmp_path / "request.json"),
        "--source-root",
        str(tmp_path),
        "--output",
        str(tmp_path / "cli-output"),
        "--review-register",
        str(tmp_path / "register.json"),
        "--review-register-sha256",
        adapter.sha(adapter.encode(r)),
    ]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["PROJECT_INPUT_ADMISSION"] == "SOFTWARE_TEST_ONLY"


def test_adapter_has_no_production_solver_or_network_imports() -> None:
    import ast

    for name in ("offline_project_input_adapter.py", "offline_project_diagnostic.py"):
        tree = ast.parse((adapter.HERE / name).read_text())
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [
            alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names
        ]
        assert not any(
            any(
                word in name
                for word in ("cold_storage", "ortools", "requests", "httpx", "pool_execution")
            )
            for name in imports
        )


@pytest.mark.parametrize("degrees,expected", [(0, 0), (90, 90), (180, 180), (270, 270)])
def test_explicit_rotations_remain_exact(degrees: int, expected: int) -> None:
    assert adapter.normalize_value(degrees, "deg", "ORIENTATION_ANGLE", "ANGLE") == expected


def test_missing_real_project_template_is_rejected_and_undimensioned(tmp_path: Path) -> None:
    request = adapter.read_json((adapter.HERE / "project-input-template.json").read_bytes())
    register_path = adapter.HERE / "local-review-register.json"
    context = adapter.load_review_context(register_path, adapter.sha(register_path.read_bytes()))
    result = diagnostic.diagnose(request, context, adapter.HERE, tmp_path / "missing")
    assert result["PROJECT_INPUT_ADMISSION"] == "BLOCKED"
    assert result["PROJECT_GEOMETRY_DIAGNOSTIC"] == "NOT_EXECUTED_MISSING_OR_REJECTED_EVIDENCE"
    assert result["FORMAL_MODULE_DIMENSIONS_APPROVED"] is False
    assert result["PACKAGING_AREA_CALIBRATION_READY"] is False
