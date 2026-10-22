"""Source-bound offline preflight tests; forbidden search entry points fail immediately."""

from __future__ import annotations

import ast
import base64
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import offline_stage_b_truck_preflight as pre
from cold_storage.modules.layout.application import access_routing as application
from cold_storage.modules.layout.domain import access_routing as routing
from cold_storage.modules.layout.domain import truck_parameter_input as r13
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.project_truck_input import validate_project_truck_input
from cold_storage.modules.layout.domain.truck_maneuver import (
    DOCK_REVERSE,
    STRAIGHT_APPROACH,
    TURN_90,
    validate_truck_maneuver_project_binding,
)
from tests.unit.test_v22_p2b1_truck_maneuver_templates import project_payload
from tests.unit.test_v222_r13_truck_parameter_preview import example


@pytest.fixture(scope="module")
def sealed() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    import os

    root = os.environ.get("STAGE_B_PREFLIGHT_ARTIFACT_ROOT")
    assert root, "Explicit authorized project evidence root required, no home scan/default"
    return pre.load_sealed(Path(root))


@pytest.fixture(autouse=True)
def forbid_search(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("REAL_SEARCH_ENTRY_FORBIDDEN_IN_OFFLINE_PREFLIGHT")

    monkeypatch.setattr(routing, "validate_truck_maneuver_chain", forbidden)
    monkeypatch.setattr(application, "validate_truck_maneuver_chain", forbidden)
    monkeypatch.setattr(application, "route_site_placement", forbidden)
    monkeypatch.setattr(r13, "preview_parameterized_truck", forbidden)


@pytest.mark.parametrize("index", range(8))
def test_each_raw_candidate_hash_context_and_eleven_access_readback(
    sealed: Any, index: int
) -> None:
    authorities, rows = sealed
    row = rows[index]
    result = pre.audit_candidate(row["projection"], row["catalog"], authorities)
    assert result["CANDIDATE_PREFLIGHT_STATUS"] == "PROJECT_INPUT_BLOCKED"
    assert result["zone_count"] == 12 and result["must_pass_count"] == 7
    assert result["non_truck_access_pass_count"] == 11
    assert len(result["non_truck_access_results"]) == 11
    assert all(v["status"] == "PASS" for v in result["non_truck_access_results"])
    assert result["source_truck_maneuver_binding_hash"] is None
    assert result["truck_search_provenance"]["visited_nodes"] == 0
    assert result["truck_route_codes"] == ["BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED"]
    assert result["HISTORICAL_TRUCK_STATE"] == "PROJECT_INPUT_BLOCKED"
    assert not result["TRUCK_SEARCH_READY"] and not result["P2D_FULL_PASS"]
    assert result["LOADING_FACE_FACTS"]["R13_FULL_LONG_EDGE_MATCH"]


def test_exact_one_mm_is_locator_not_measured_gate(sealed: Any) -> None:
    authorities, _ = sealed
    facts = pre.entrance_facts(authorities["typed_site"])
    assert facts["LENGTH_MM"] == 1 and facts["LENGTH_M"] == "0.001"
    assert facts["SITE_TRUCK_ENTRANCE_SEGMENT"] == {
        "start": {"x": "0", "y": "33.7"},
        "end": {"x": "0", "y": "33.701"},
    }
    assert facts["MEASURED_GATE_CLEAR_OPENING"] is None
    assert facts["MEASURED_GATE_STATUS"] == "UNAVAILABLE"
    assert facts["R13_CLEAR_OPENING_SEGMENT"] is None
    assert not facts["AUTOMATIC_SEGMENT_ENLARGEMENT_ALLOWED"]


def test_original_p1f_complete_is_not_p2b1_or_document_complete(sealed: Any) -> None:
    authorities, _ = sealed
    source = pre.frozen_p1f(authorities["p1_handoff"])
    p1f = validate_project_truck_input(source)
    assert p1f["status"] == "COMPLETE" and p1f["evidence_contents_verified"] is False
    with pytest.raises((LayoutAuthorityError, TypeError)):
        validate_truck_maneuver_project_binding(source, {})
    assert pre.check_input_contract(None)["PROJECT_TRUCK_INPUT_ADMISSION"] == "BLOCKED"


def test_synthetic_input_uses_original_predicates_without_search_or_project_pass() -> None:
    result = pre.check_input_contract(example())
    assert result["STATUS"] == "INPUT_VALIDATED_NOT_ROUTE_PASS", result
    assert result["SOURCE_BYTE_STATUS"] == "SOURCE_BYTES_VERIFIED_NOT_APPROVAL"
    assert result["SYNTHETIC_TEST_ONLY"]
    assert result["PROJECT_APPLICABILITY_STATUS"] == "REFERENCE_ONLY"
    assert not result["TRUCK_SEARCH_READY"] and not result["P2D_FULL_PASS"]
    assert result["PROJECT_TRUCK_INPUT_ADMISSION"] == "BLOCKED"


@pytest.mark.parametrize("field", ["vehicle_width_m", "vehicle_length_m"])
def test_missing_vehicle_dimensions_rejected(field: str) -> None:
    payload = example()
    del payload["truck_access"][field]
    result = pre.check_input_contract(payload)
    assert result["STATUS"] == "BLOCKED" and result["REASON_CODES"] == [("PROJECT_INPUT_REQUIRED")]


@pytest.mark.parametrize("flag", ["verified", "APPROVED", "TRUCK_SEARCH_READY", "p2_complete"])
def test_caller_flags_cannot_override_preflight(flag: str) -> None:
    payload = example()
    payload[flag] = True
    assert pre.check_input_contract(payload)["REASON_CODES"] == [("INVALID_TRUCK_PREVIEW_INPUT")]


@pytest.mark.parametrize(
    "case",
    [
        "project",
        "vehicle",
        "version",
        "template_hash",
        "document_bytes",
        "no_documents",
        "gate",
        "locator",
        "body",
        "loading_face",
        "source_reference",
        "missing_class",
    ],
)
def test_original_validator_fail_closed_paths(case: str) -> None:
    payload = example()
    if case == "project":
        payload["truck_access"]["project_id"] = "OTHER_PROJECT"
    elif case == "vehicle":
        payload["truck_access"]["vehicle_length_m"] = 5
    elif case == "version":
        payload["truck_maneuver"]["schema_version"] = "2.0.0"
    elif case == "template_hash":
        payload["truck_maneuver"]["template_set"]["templates"][0]["content_sha256"] = (
            "sha256:" + "0" * 64
        )
    elif case == "document_bytes":
        payload["evidence"][0]["content_base64"] = "d3Jvbmc="
    elif case == "no_documents":
        payload["evidence"] = []
    elif case == "gate":
        payload["entrance"]["clear_width_m"] = 1
    elif case == "locator":
        payload["entrance"]["locator_segment"] = {
            "start": {"x": 0, "y": 1},
            "end": {"x": 0, "y": 2},
        }
    elif case == "body":
        payload["vehicle_body"]["points"][1]["x"] = 5
    elif case == "loading_face":
        payload[("shipping_loading_face")] = {
            "start": {"x": 10, "y": 16},
            "end": {"x": 10, "y": 20},
        }
    elif case == "source_reference":
        payload["vehicle_source_reference"] = "UNKNOWN_REFERENCE"
    elif case == "missing_class":
        payload["truck_maneuver"] = project_payload(
            payload["truck_maneuver"]["template_set"]["templates"][:1],
            (STRAIGHT_APPROACH, TURN_90, DOCK_REVERSE),
        )
    result = pre.check_input_contract(payload)
    assert result["STATUS"] == "BLOCKED", (case, result)
    assert not result["TRUCK_SEARCH_READY"] and not result["P2D_FULL_PASS"]


def test_expected_project_identity_cannot_be_relabelled() -> None:
    payload = example()
    expected = deepcopy(payload["truck_access"])
    expected["project_id"] = "REAL_PROJECT_NOT_FIXTURE"
    result = pre.check_input_contract(payload, expected_p1f=expected)
    assert result["REASON_CODES"] == ["P1F_PROJECT_VEHICLE_BINDING_MISMATCH"]


def test_two_required_classes_do_not_require_unneeded_turn() -> None:
    payload = example()
    templates = [
        t
        for t in payload["truck_maneuver"]["template_set"]["templates"]
        if t["maneuver_class"] != TURN_90
    ]
    payload["truck_maneuver"] = project_payload(templates, (STRAIGHT_APPROACH, DOCK_REVERSE))
    result = pre.check_input_contract(payload)
    assert result["STATUS"] == "INPUT_VALIDATED_NOT_ROUTE_PASS", result
    assert TURN_90 not in result["REQUIRED_MANEUVER_CLASSES"]


def test_p2b1_subset_complete_does_not_imply_p2d_docking_ready() -> None:
    payload = example()
    templates = [
        t
        for t in payload["truck_maneuver"]["template_set"]["templates"]
        if t["maneuver_class"] == STRAIGHT_APPROACH
    ]
    payload["truck_maneuver"] = project_payload(templates, (STRAIGHT_APPROACH,))
    bound = validate_truck_maneuver_project_binding(
        payload["truck_access"], payload["truck_maneuver"]
    )
    assert bound.maneuver_project_input.template_input_complete
    assert pre.check_input_contract(payload)["REASON_CODES"] == ["P2D_DOCK_REVERSE_REQUIRED"]


@pytest.mark.parametrize(
    "field", [("shipping_loading_face_side"), ("shipping_loading_face_segment")]
)
def test_wrong_selected_loading_face_rejected_by_original_p2d(sealed: Any, field: str) -> None:
    _, rows = sealed
    engine = deepcopy(rows[0]["projection"]["engineering_validation"])
    if field.endswith("side"):
        engine[field] = "RIGHT_LONG_EDGE"
    else:
        engine[field] = {"start": {"x": 0, "y": 0}, "end": {"x": 0, "y": 1}}
    with pytest.raises(LayoutAuthorityError):
        pre.loading_face(engine)


def test_result_copy_between_candidates_rejected(sealed: Any) -> None:
    authorities, rows = sealed
    projection = deepcopy(rows[1]["projection"])
    projection[("engineering_validation")] = deepcopy(
        rows[0]["projection"][("engineering_validation")]
    )
    result = pre.audit_candidate(projection, rows[1]["catalog"], authorities)
    assert result["REASON_CODES"] == ["CANDIDATE_PROJECTION_HASH_MISMATCH"]


def test_stale_site_and_handoff_detected(sealed: Any) -> None:
    authorities, rows = sealed
    changed = deepcopy(authorities)
    changed["typed_site"]["entrances"]["truck_entrance"]["end"]["y"] = "38.7"
    result = pre.audit_candidate(rows[0]["projection"], rows[0]["catalog"], changed)
    assert result["REASON_CODES"] == ["CANDIDATE_SITE_HASH_MISMATCH"]
    assert canonical_hash(changed["p1_handoff"]) == canonical_hash(authorities["p1_handoff"])
    assert canonical_hash(changed["canonical_zone_plan"]) == canonical_hash(
        authorities["canonical_zone_plan"]
    )


def test_raw_file_hash_tampering_rejected_before_facts(tmp_path: Path) -> None:
    raw = tmp_path / (
        "stage-b-real-multi-solution-validation-01/real-execution/main/candidate-01/candidate.json"
    )
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"{}\n")
    with pytest.raises(LayoutAuthorityError, match="RAW_CANDIDATE_HASH_MISMATCH"):
        pre.load_sealed(tmp_path)


def test_prospective_input_bound_to_exact_candidate_not_just_project() -> None:
    payload = example()
    candidate = {
        "zones": deepcopy(payload["site_geometry"]["zones"]),
        "shipping_loading_face_segment": deepcopy(payload["shipping_loading_face"]),
        "corridors": [],
        "access_results": [],
    }
    result = pre.check_input_contract(payload, candidate_engineering=candidate)
    assert result["STATUS"] == "INPUT_VALIDATED_NOT_ROUTE_PASS", result
    candidate["zones"][0]["x"] += 1
    assert pre.check_input_contract(payload, candidate_engineering=candidate)["REASON_CODES"] == [
        "CANDIDATE_TRUCK_CONTEXT_MISMATCH"
    ]


def test_all_contexts_independent_and_repeated_bytes_deterministic(sealed: Any) -> None:
    authorities, rows = sealed

    def run() -> list[dict[str, Any]]:
        return [pre.audit_candidate(row["projection"], row["catalog"], authorities) for row in rows]

    first, second = run(), run()
    assert pre.encode(first) == pre.encode(second)
    assert len({row["CANDIDATE_TRUCK_CONTEXT_HASH"] for row in first}) == 8
    assert sum(v["P2D_FULL_PASS"] for v in first) == 0
    assert len({row["source_site_geometry_hash"] for row in first}) == 1


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("review", "TRUCK_ROUTE_ENGINEERING_REVIEW_REQUIRED"),
        ("failed", "TRUCK_SEARCH_EXECUTED_WITHOUT_VALIDATED_ROUTE_NOT_GLOBAL_INFEASIBILITY"),
        ("valid", "TRUCK_ROUTE_VALIDATED_NOT_P2D_FULL_PASS"),
    ],
)
def test_state_categories_not_conflated(kind: str, expected: str) -> None:
    value: dict[str, Any] = {
        "truck_search_provenance": {"visited_nodes": 10},
        "source_truck_maneuver_binding_hash": "bound",
    }
    if kind == "review":
        value["truck_route_status"] = "REQUIRES_ENGINEERING_REVIEW"
    elif kind == "valid":
        value["truck_route_validated"] = True
    assert pre.historical_truck_state(value) == expected


def test_no_solver_grant_or_forbidden_entry_calls_in_tool() -> None:
    tree = ast.parse((pre.HERE / "offline_stage_b_truck_preflight.py").read_text())
    calls = [
        node.func.attr
        if isinstance(node.func, ast.Attribute)
        else node.func.id
        if isinstance(node.func, ast.Name)
        else ""
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    ]
    assert not set(calls) & {
        "route_site_placement",
        "validate_truck_maneuver_chain",
        "preview_parameterized_truck",
        "invoke_truck_preview",
        "Solve",
        "solve",
        "Claim",
        "PoolLease",
    }
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any("ortools" in name or "pool_execution" in name for name in imports)


def test_uploaded_approved_label_and_matching_digest_are_not_project_approval() -> None:
    payload = example()
    payload["mode"] = "OWNER_PROJECT"
    payload["approval_reference"] = "synthetic-forged-approval"
    document = pre.encode(
        {
            "project_id": "fixture-project",
            "status": "APPROVED",
            "reviewed_by": "SYNTHETIC_TEST_ONLY",
            "approved_input_hash": canonical_hash(
                {k: v for k, v in payload.items() if k != "evidence"}
            ),
        }
    )
    payload["evidence"].append(
        {
            "reference": ("synthetic-forged-approval"),
            "content_sha256": "sha256:" + pre.sha(document),
            "content_base64": base64.b64encode(document).decode(),
        }
    )
    result = pre.check_input_contract(payload)
    assert result["SOURCE_BYTE_STATUS"] == "SOURCE_BYTES_VERIFIED_NOT_APPROVAL"
    assert result["PROJECT_TRUCK_INPUT_ADMISSION"] == "BLOCKED"
    assert result["APPROVAL_STATUS"] == "PROJECT_APPROVAL_REQUIRED_NOT_EVALUATED"
    assert result["REAL_PROJECT_APPROVED"] is False
    assert not result["TRUCK_SEARCH_READY"] and not result["P2D_FULL_PASS"]


def test_personnel_interaction_review_not_hidden_by_valid_truck_flag() -> None:
    assert pre.historical_truck_state(
        {
            "truck_route_validated": True,
            ("personnel_truck_evaluation"): {"status": ("REQUIRES_ENGINEERING_REVIEW")},
        }
    ) == ("TRUCK_ROUTE_ENGINEERING_REVIEW_REQUIRED")
