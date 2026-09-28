"""Test the evaluation-only R10 axis/direction matrix runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tests.evaluation.v222_p1a_r10_axis_direction_audit import (
    _write_evidence_pack,
    run_full_matrix,
)


def test_r10_axis_direction_matrix_runs_all_variants_with_real_tool7(
    monkeypatch: Any,
) -> None:
    matrix = run_full_matrix(monkeypatch)
    assert matrix["matrix_complete"] is True
    assert matrix["linear_diagnostic_variant_count"] == 8
    assert matrix["hub_reference_variant_count"] == 1
    assert matrix["current_runtime"]["alternate_axis_enumerated"] is False
    assert matrix["current_runtime"]["negative_process_direction_enumerated"] is False
    assert matrix["diagnostic_policy"]["p2d_mocked"] is False
    assert all(row["diagnostic_node_limit"] == 120 for row in matrix["variants"])
    assert matrix["aggregate"]["search_truncated_variant_count"] == 9
    assert matrix["aggregate"]["search_exhausted_variant_count"] == 0
    # Live replay now uses the R11 resumable scheduler; the frozen R10 evidence
    # artifact remains the historical 15-skeleton result.
    # R13's truck necessary preflight rejects proven no-route seeds before
    # tail search, so bounded construction reaches more exact geometries.
    assert matrix["aggregate"]["distinct_main_skeleton_count"] == 20
    # R10's tail-admissible measure is its packaging-slot preflight; R13 then
    # applies the independent truck necessary condition before P2D.
    assert matrix["aggregate"]["tail_admissible_distinct_skeleton_count"] == 6
    assert matrix["aggregate"]["p2d_evaluated_distinct_skeleton_count"] == 1
    assert matrix["aggregate"]["p2d_full_pass_distinct_skeleton_count"] == 1
    assert matrix["aggregate"]["runtime_excluded_full_pass_skeleton_found"] is False
    assert matrix["findings"]["ordering_only_claim_accurate"] is False
    assert matrix["production_search_accounting"]["production_budget"] == 120
    assert matrix["production_search_accounting"]["placement_node_visits"] == 120
    assert matrix["production_search_accounting"]["placement_nodes_remaining"] == 0
    assert matrix["default_tool7_response_ok"] is True

    variants = {row["variant_id"]: row for row in matrix["variants"]}
    straight_y_positive = variants["STRAIGHT_LINEAR_BAND_Y_POSITIVE"]
    assert straight_y_positive["p2d_full_pass_distinct_skeleton_count"] == 1
    assert any(
        skeleton["hash"]
        == "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"
        and skeleton["p2d_full_pass_count"] == 2
        for skeleton in straight_y_positive["skeletons"]
    )
    hub = variants["CENTRAL_PROCESS_HUB_REFERENCE"]
    assert any(
        skeleton["hash"]
        == "sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc"
        and skeleton["packaging_slot_exists"] is False
        for skeleton in hub["skeletons"]
    )
    if os.environ.get("R10_WRITE_EVIDENCE") == "1":
        _write_evidence_pack(
            matrix,
            Path(__file__).resolve().parents[3] / "docs/tasks/evidence/v2_2_2_p1a",
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
