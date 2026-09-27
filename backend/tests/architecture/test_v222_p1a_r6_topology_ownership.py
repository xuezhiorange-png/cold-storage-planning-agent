"""R6 topology identity, serialization, and evidence scope locks."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from cold_storage.modules.aily.application.site_layout_preview import P4_PLACEMENT_NODE_BUDGET

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = ROOT / "backend/src/cold_storage/modules/layout/domain"
EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a"


def test_r6_candidate_provenance_stays_out_of_tool7_skeleton_serialization() -> None:
    source = (LAYOUT / "main_process_skeleton.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    skeleton_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MainProcessSkeletonCandidateV1"
    )
    methods = {
        node.name: node
        for node in skeleton_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "to_dict" in methods
    assert "to_evaluation_dict" in methods

    def mapping_keys(method: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        return {
            key.value
            for node in ast.walk(method)
            if isinstance(node, ast.Dict)
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }

    public_keys = mapping_keys(methods["to_dict"])
    evaluation_keys = mapping_keys(methods["to_evaluation_dict"])
    internal_r6_keys = {
        "canonical_topology_owner",
        "construction_policy",
        "topology_divergence_stage",
        "offset_transition_stage",
        "offset_direction",
        "offset_cross_axis_shift_mm",
    }
    assert not public_keys & internal_r6_keys
    assert internal_r6_keys <= evaluation_keys


def test_r6_evidence_records_partial_without_promoting_unmet_acceptance() -> None:
    metrics = json.loads((EVIDENCE / "xinzhao_p1a_r6_metrics.json").read_text(encoding="utf-8"))
    ownership = json.loads(
        (EVIDENCE / "xinzhao_p1a_r6_topology_ownership.json").read_text(encoding="utf-8")
    )
    offset = json.loads(
        (EVIDENCE / "xinzhao_p1a_r6_offset_transition.json").read_text(encoding="utf-8")
    )

    assert P4_PLACEMENT_NODE_BUDGET == 120
    assert metrics["production_budget_changed"] is False
    assert metrics["actual_lane_node_visits"]["total"] <= 120
    assert metrics["topology_count_explored"] == 3
    assert metrics["p2d_full_pass_distinct_main_process_skeleton_count"] == 1
    assert metrics["selected_main_process_geometry_changed_from_r5"] is False
    assert metrics["r6_svg_hash_equals_r5"] is True
    assert metrics["result"] == "PARTIAL"
    assert metrics["owner_xinzhao_p1a_r6_visual_review"] == "PENDING"
    assert ownership["r5_shared_skeleton_canonical_owner"] == "STRAIGHT_LINEAR_BAND"
    assert ownership["hub_reaccepted_r5_shared_skeleton"] is False
    assert offset["offset_transition_present"] is True
    assert offset["complete_offset_skeleton_count"] == 0
    assert metrics["p1b_threshold_activated"] is False
    assert metrics["weighted_score_used"] is False
    assert metrics["tool7_contract_changed"] is False


def test_r6_runtime_has_no_xinzhao_fixture_special_case_or_golden_coordinates() -> None:
    topology_source = (LAYOUT / "main_process_topology.py").read_text(encoding="utf-8")
    skeleton_source = (LAYOUT / "main_process_skeleton.py").read_text(encoding="utf-8")

    for source in (topology_source, skeleton_source):
        lowered = source.lower()
        assert "xinzhao" not in lowered
        assert "d03ecae9e1e2808cba346eb83a39f853" not in lowered
        assert "golden" not in lowered
