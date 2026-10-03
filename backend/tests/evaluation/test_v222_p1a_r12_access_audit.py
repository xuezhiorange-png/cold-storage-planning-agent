"""R12 evidence contract for exact Tool 7 access-failure attribution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.evaluation.r12_access_failure_audit import _classify_failure


def _evidence(name: str) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[3]
    path = repository_root / "docs/tasks/evidence/v2_2_2_p1a" / f"xinzhao_p1a_r12_{name}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_r12_captures_all_six_real_tool7_candidates_and_twelve_requirements() -> None:
    evidence = _evidence("candidate_access_matrix")

    assert evidence["replay"]["tool7_ok"] is True
    assert evidence["replay"]["complete_p2c_capture_count"] == 6
    assert evidence["replay"]["project_layout_validated"] is True
    assert evidence["replay"]["p2_complete"] is True
    by_skeleton: dict[str, list[dict[str, Any]]] = {}
    for candidate in evidence["candidates"]:
        assert candidate["access_requirement_count"] == 12
        assert len(candidate["access_rows"]) == 12
        by_skeleton.setdefault(candidate["skeleton_hash"], []).append(candidate)

    assert (
        len(by_skeleton["sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"])
        == 2
    )
    assert (
        len(by_skeleton["sha256:062f563bec94c66ff2769d08da8f06a76b9b853c6441b148e4b7a72b6dc0d51c"])
        == 2
    )
    assert (
        len(by_skeleton["sha256:a148aab89040232091a5486897ac3d895a2685ae3c3cf0c48b0362d08d9eeff3"])
        == 2
    )


def test_r12_targets_are_blocked_only_by_the_same_exhaustive_truck_requirement() -> None:
    matrix = _evidence("candidate_access_matrix")
    counterfactual = _evidence("main_skeleton_access_counterfactual")
    root_cause = _evidence("access_root_cause")
    targets = {
        candidate["skeleton_hash"]: candidate
        for candidate in matrix["candidates"]
        if candidate["skeleton_hash"]
        in {
            "sha256:062f563bec94c66ff2769d08da8f06a76b9b853c6441b148e4b7a72b6dc0d51c",
            "sha256:a148aab89040232091a5486897ac3d895a2685ae3c3cf0c48b0362d08d9eeff3",
        }
    }
    assert len(targets) == 2
    for candidate in matrix["candidates"]:
        if candidate["skeleton_hash"] not in targets:
            continue
        assert candidate["access_pass_count"] == 11
        assert candidate["access_fail_count"] == 0
        assert candidate["access_blocked_count"] == 1
        assert candidate["failed_requirement_ids"] == [
            "access:truck_entrance->shipping_channel@1.0.0"
        ]
        failed = [row for row in candidate["access_rows"] if row["status"] != "PASS"]
        assert failed[0]["codes"] == ["TRUCK_MANEUVER_SEARCH_EXHAUSTED"]

    assert len(counterfactual["rows"]) == 4
    assert all(
        row["counterfactual"]["exact_no_route_within_enumerated_authority"] is True
        for row in counterfactual["rows"]
    )
    assert all(
        row["failure_present_with_main_skeleton_only"] is True
        and row["failure_disappears_when_unrelated_tail_removed"] is False
        for row in counterfactual["rows"]
    )
    assert all(
        target["main_skeleton_access_infeasibility_proven"] is True
        for target in root_cause["targets"]
    )


def test_r12_owner_taxonomy_keeps_truck_maneuver_distinct_from_planar_route_codes() -> None:
    classes = _classify_failure(
        {
            "flow_kind": "TRUCK",
            "from_ref": "truck_entrance",
            "to_ref": "shipping_channel",
        },
        {"codes": ["TRUCK_MANEUVER_SEARCH_EXHAUSTED"]},
        counterfactual_status="TRUCK_MANEUVER_SEARCH_EXHAUSTED",
        main_only=True,
    )

    assert classes == [
        "OTHER_EXACT_ACCESS_CONFLICT",
        "MAIN_SKELETON_ACCESS_GEOMETRY_CONFLICT",
    ]


def test_r12_portal_trace_distinguishes_failed_alternative_from_requirement_failure() -> None:
    trace = _evidence("portal_route_failure_trace")

    assert trace["portal_pair_count"] == 12
    assert trace["portal_pair_pass_count"] == 6
    assert trace["portal_pair_failure_counts"] == {"FAIL": 6, "PASS": 6}
    assert trace["portal_pair_failure_counts"]["FAIL"] <= trace["portal_pair_count"]
