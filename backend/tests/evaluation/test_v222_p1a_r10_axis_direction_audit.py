"""Test the evaluation-only R10 axis/direction matrix runner."""

from __future__ import annotations

import json
from pathlib import Path


def test_r10_checked_in_axis_direction_matrix_is_historically_consistent() -> None:
    evidence_root = Path(__file__).resolve().parents[3] / "docs/tasks/evidence/v2_2_2_p1a"
    matrix = json.loads(
        (evidence_root / "xinzhao_p1a_r10_axis_direction_matrix.json").read_text(encoding="utf-8")
    )
    assert matrix["matrix_complete"] is True
    assert matrix["linear_diagnostic_variant_count"] == 8
    assert matrix["hub_reference_variant_count"] == 1
    assert matrix["current_runtime"]["alternate_axis_enumerated"] is False
    assert matrix["current_runtime"]["negative_process_direction_enumerated"] is False
    assert matrix["diagnostic_policy"]["p2d_mocked"] is False
    assert matrix["diagnostic_policy"]["diagnostic_budget_is_production_budget"] is False
    assert all(row["lane_budget"] == 120 for row in matrix["variants"])
    variants = {row["variant_id"]: row for row in matrix["variants"]}
    assert len(variants) == 9
    skeletons = json.loads(
        (evidence_root / "xinzhao_p1a_r10_skeleton_matrix.json").read_text(encoding="utf-8")
    )["skeletons"]
    assert any(
        skeleton["hash"]
        == "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"
        and skeleton["variant_id"] == "STRAIGHT_LINEAR_BAND_Y_POSITIVE"
        and skeleton["p2d_full_pass_count"] == 2
        for skeleton in skeletons
    )


def test_r10_evidence_and_version_history_are_aligned() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    evidence_root = repository_root / "docs/tasks/evidence/v2_2_2_p1a"
    matrix = json.loads(
        (evidence_root / "xinzhao_p1a_r10_axis_direction_matrix.json").read_text(encoding="utf-8")
    )
    runtime_gap = json.loads(
        (evidence_root / "xinzhao_p1a_r10_runtime_gap_analysis.json").read_text(encoding="utf-8")
    )
    expected_variants = {
        f"{topology}_{axis}_{direction}"
        for topology in ("STRAIGHT_LINEAR_BAND", "OFFSET_LINEAR_BAND")
        for axis in ("X", "Y")
        for direction in ("POSITIVE", "NEGATIVE")
    }
    actual_variants = {row["variant_id"] for row in matrix["variants"]}
    assert matrix["matrix_complete"] is True
    assert actual_variants == expected_variants | {"CENTRAL_PROCESS_HUB_REFERENCE"}
    assert all(row["search_truncated"] for row in matrix["variants"])
    assert runtime_gap["findings"]["infeasibility_proven"] is False
    assert runtime_gap["findings"]["ordering_only_claim_accurate"] is False
    assert runtime_gap["production_search_accounting"]["placement_node_visits"] == 98
    assert runtime_gap["production_search_accounting"]["placement_nodes_remaining"] == 22

    version_plan = (repository_root / "docs/tasks/V2_2-version-plan.md").read_text(encoding="utf-8")
    for fact in (
        "P1A_R6_RESULT=PARTIAL",
        "P1A_R7_RESULT=PARTIAL",
        "P1A_R8_RESULT=PASS_DIAGNOSTIC",
        "P1A_R9_RESULT=PARTIAL",
        "P1A_R10_RESULT=PASS",
        "CURRENT_PRODUCTION_PLACEMENT_NODE_BUDGET=120",
    ):
        assert fact in version_plan
