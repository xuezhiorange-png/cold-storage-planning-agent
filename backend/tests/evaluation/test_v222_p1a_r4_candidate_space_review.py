"""Contract tests for the evidence-only P1A R4 candidate-space review."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a"


def _load(name: str) -> dict[str, Any]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_family_audit_preserves_partial_status_and_distinguishes_a_to_g() -> None:
    audit = _load("xinzhao_r4_family_search_audit.json")
    assert audit["replay"]["matches_saved_r3"] is True
    assert audit["replay"]["project_layout_validated"] is True
    assert audit["replay"]["p2_complete"] is True
    assert audit["replay"]["zone_count"] == 12
    assert audit["replay"]["access_requirement_count"] == 12
    assert audit["replay"]["access_pass_count"] == 12
    assert audit["replay"]["truck_route_validated"] is True
    assert audit["replay"]["building_footprint_present"] is True

    lanes = audit["family_lanes"]
    assert {row["family"] + "/" + row["dominant_direction"] for row in lanes} == {
        "CENTRAL_PROCESS_HUB/UNRESOLVED",
        "LINEAR_PROCESS_BAND/POSITIVE",
        "LINEAR_PROCESS_BAND/NEGATIVE",
    }
    assert sum(row["lane_budget"] for row in lanes) == 120
    assert all(row["search_exhausted"] is False for row in lanes)
    by_lane = {row["family"] + "/" + row["dominant_direction"]: row for row in lanes}
    assert by_lane["LINEAR_PROCESS_BAND/POSITIVE"]["visited_nodes"] == 15
    assert by_lane["LINEAR_PROCESS_BAND/NEGATIVE"]["visited_nodes"] == 15
    assert by_lane["CENTRAL_PROCESS_HUB/UNRESOLVED"]["lane_budget"] == 80
    assert by_lane["CENTRAL_PROCESS_HUB/UNRESOLVED"]["constructed_skeleton_count"] == 2
    assert by_lane["CENTRAL_PROCESS_HUB/UNRESOLVED"]["distinct_full_pass_skeleton_count"] == 1

    states = audit["candidate_state_classification"]
    assert set(states) == {
        "A_FAMILY_NOT_EXPLORED",
        "B_FAMILY_SEARCH_TRUNCATED",
        "C_SKELETON_CONSTRUCTION_FAILED",
        "D_SKELETON_CONSTRUCTED_BUT_TAIL_FAILED",
        "E_COMPLETE_CANDIDATE_FAILED_P2D",
        "F_P2D_FULL_PASS_LOST_STRUCTURAL_COMPARISON",
        "G_STRUCTURAL_TIE_THEN_P2B2_LOSS",
    }
    assert states["A_FAMILY_NOT_EXPLORED"]["count"] == 0
    assert states["D_SKELETON_CONSTRUCTED_BUT_TAIL_FAILED"]["first_failure_stage"] == "TAIL_SEARCH"
    assert states["E_COMPLETE_CANDIDATE_FAILED_P2D"]["count"] == 0
    assert states["G_STRUCTURAL_TIE_THEN_P2B2_LOSS"]["first_decisive_component"] == (
        "P2B2_FINAL_TIE_BREAK"
    )


def test_linear_rejection_matrix_has_zone_root_face_and_reason_dimensions() -> None:
    matrix = _load("xinzhao_r4_linear_rejection_matrix.json")
    assert matrix["event_count"] == 513
    assert matrix["aggregated_row_count"] == len(matrix["rows"]) == 366
    required = {
        "family",
        "dominant_direction",
        "sorting_root_mm",
        "raw_side",
        "finished_side",
        "zone_code",
        "reason",
        "stage",
        "count",
    }
    assert all(required <= row.keys() for row in matrix["rows"])
    assert {row["dominant_direction"] for row in matrix["rows"]} == {"POSITIVE", "NEGATIVE"}
    assert {row["zone_code"] for row in matrix["rows"]} >= {
        "sorting_packaging_room",
        "primary_precooling_room",
        "raw_fruit_buffer",
    }
    totals = Counter(
        {
            (
                row["family"],
                row["dominant_direction"],
                row["zone_code"],
                row["reason"],
                row["stage"],
            ): row["count"]
            for row in matrix["event_count_by_family_direction_zone_reason_stage"]
        }
    )
    assert (
        totals[
            (
                "LINEAR_PROCESS_BAND",
                "POSITIVE",
                "sorting_packaging_room",
                "SITE_OUTSIDE",
                "SORTING_ROOT_CANDIDATE",
            )
        ]
        == 135
    )
    assert (
        totals[
            (
                "LINEAR_PROCESS_BAND",
                "NEGATIVE",
                "raw_fruit_buffer",
                "SITE_OUTSIDE",
                "SKELETON_CONSTRUCTION",
            )
        ]
        == 54
    )


def test_hub_seed_lifecycle_identifies_tail_budget_failure_before_p2d() -> None:
    trace = _load("xinzhao_r4_hub_skeleton_survival_trace.json")
    assert trace["constructed_skeleton_count"] == 2
    assert trace["distinct_full_pass_skeleton_count"] == 1
    seeds = {row["skeleton_hash"]: row for row in trace["skeletons"]}
    second = seeds["sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc"]
    assert second["tail_search"]["nodes_at_start"] == 44
    assert second["tail_search"]["node_share_limit"] == 80
    assert second["tail_search"]["nodes_at_end"] == 80
    assert second["tail_search"]["node_share_exhausted"] is True
    assert second["tail_search"]["complete_p2c_candidate_count"] == 0
    assert second["p2d"]["reached"] is False
    assert second["first_failure_stage"] == "TAIL_SEARCH"
    assert (
        second["first_failure_reason"] == "TAIL_NODE_SHARE_EXHAUSTED_WITHOUT_COMPLETE_P2C_CANDIDATE"
    )
    assert second["access_failure"] == "NOT_REACHED"
    first = seeds["sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"]
    assert first["tail_search"]["complete_p2c_candidate_count"] == 2
    assert first["p2d"]["full_pass_candidate_count"] == 2


def test_topology_design_gate_and_version_plan_are_evidence_only() -> None:
    design = _load("xinzhao_r4_candidate_space_design_matrix.json")
    topology_names = {row["topology"] for row in design["topologies"]}
    assert topology_names == {
        "STRAIGHT_LINEAR_BAND",
        "OFFSET_LINEAR_BAND",
        "FOLDED_LINEAR_BAND",
        "CENTRAL_PROCESS_HUB",
        "HUB_WITH_STORAGE_BANK",
    }
    assert {row["policy"] for row in design["lane_allocation_policy_options"]} == {
        "A_PREFERRED_FAMILY_BIASED",
        "B_EQUAL_FAMILY_EXPLORATION",
        "C_SKELETON_COUNT_TARGETED",
        "D_STAGED_COVERAGE_THEN_PREFERENCE",
    }
    gate = design["design_gate"]
    assert gate["CANDIDATE_SPACE_DESIGN_REVIEW_COMPLETE"] is True
    assert gate["LINEAR_FAMILY_FAILURE_CLASSIFIED"] is True
    assert gate["SECOND_HUB_SKELETON_FAILURE_CLASSIFIED"] is True
    assert gate["NEXT_IMPLEMENTATION_ENTRY_READY"] is True
    assert gate["NEXT_IMPLEMENTATION_AUTHORIZED"] is False
    assert gate["P1B_NUMERIC_THRESHOLD_USED"] is False

    plan = (ROOT / "docs/tasks/V2_2-version-plan.md").read_text(encoding="utf-8")
    assert "P1A_R1_INITIAL_PRODUCTION_PLACEMENT_NODE_BUDGET=15" in plan
    assert "P1A_R2_PRODUCTION_PLACEMENT_NODE_BUDGET=120" in plan
    assert "P1A_R3_PRODUCTION_PLACEMENT_NODE_BUDGET=120" in plan
    assert "P1A_R3_RESULT=PARTIAL" in plan
    assert "P1A_R3_MAIN_PROCESS_GEOMETRY_CHANGED=false" in plan
    assert "P1A_R3_LINEAR_FAMILY_INFEASIBILITY_PROVEN=false" in plan
    assert "P1A_R4_RUNTIME_IMPLEMENTATION_AUTHORIZED=false" in plan
