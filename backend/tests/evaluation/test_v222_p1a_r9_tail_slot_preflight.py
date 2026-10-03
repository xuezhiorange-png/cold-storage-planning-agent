"""Full-chain checks for R9 preflight lifecycle and deterministic Tool 7 output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.modules.aily.application import site_layout_preview
from cold_storage.modules.aily.application.mcp_site_layout import invoke_preview_site_layout_tool
from cold_storage.modules.aily.application.preview_bundle import json_ready
from cold_storage.modules.layout.domain.truck_maneuver import (
    DOCK_FACE_REFERENCE,
    DOCK_REVERSE,
    FORWARD_AXIS,
    ORIGIN_REFERENCE,
    REFERENCE_FRAME,
    STRAIGHT_APPROACH,
    TURN_90,
)
from tests.unit.test_v22_p2b1_truck_maneuver_templates import (
    p1f_input,
    project_payload,
    template_payload,
)

ROOT = Path(__file__).resolve().parents[3]
XINZHAO_INPUT = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
R8_SECOND_SKELETON = "sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc"
R5_HARD_VALID_SKELETON = "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"


def _capture_real_tool7(
    monkeypatch: Any,
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    original = site_layout_preview.select_validated_placement

    def instrumented_selector(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        captured.append(result.internal_evaluation)
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(
            site_layout_preview,
            "select_validated_placement",
            instrumented_selector,
        )
        response = invoke_preview_site_layout_tool(payload)
    assert response.get("ok") is True
    assert len(captured) == 1
    return response, captured[0]


def _preflight_row(evaluation: Mapping[str, Any], skeleton_hash: str) -> Mapping[str, Any]:
    diagnostics = evaluation["r6_topology_diagnostics"]
    rows = diagnostics["tail_slot_preflight_trace"]
    return next(row for row in rows if row.get("skeleton_hash") == skeleton_hash)


def _lifecycle_row(evaluation: Mapping[str, Any], skeleton_hash: str) -> Mapping[str, Any]:
    return next(
        row for row in evaluation["skeleton_survival"] if row.get("skeleton_hash") == skeleton_hash
    )


def _representative_tool7_payload() -> dict[str, Any]:
    def point(x: object, y: object) -> dict[str, object]:
        return {"x": x, "y": y}

    def reference_frame(exit_pose: dict[str, object]) -> dict[str, object]:
        return {
            "reference_frame": REFERENCE_FRAME,
            "forward_axis": FORWARD_AXIS,
            "origin_reference": ORIGIN_REFERENCE,
            "vehicle_reference_point": point(0, 0),
            "entry_pose": {**point(0, 0), "rotation_deg": 0},
            "exit_pose": exit_pose,
        }

    site = {
        "site_boundary": {
            "type": "polygon",
            "points": [point(0, 0), point(75.46, 0), point(75.46, 55), point(0, 55)],
        },
        "main_entrance": {"start": point(75.46, 24.525), "end": point(75.46, 26.525)},
        "truck_entrance": {"start": point(0, 33.7), "end": point(0, 33.701)},
        "preferred_loading_side": "UNSPECIFIED",
        "no_build_zones": [
            {
                "type": "polygon",
                "points": [
                    point(0, 8.701),
                    point(14.699, 8.701),
                    point(14.699, 18.75),
                    point(0, 18.75),
                ],
            },
            {
                "type": "polygon",
                "points": [
                    point(41.718, 27),
                    point(74.999, 27),
                    point(74.999, 39.385),
                    point(41.718, 39.385),
                ],
            },
            {
                "type": "polygon",
                "points": [
                    point(41.718, 39.386),
                    point(74.999, 39.386),
                    point(74.999, 53.886),
                    point(41.718, 53.886),
                ],
            },
        ],
    }
    truck_access = dict(p1f_input())
    truck_access["vehicle_width_m"] = float(truck_access["vehicle_width_m"])
    truck_access["vehicle_length_m"] = float(truck_access["vehicle_length_m"])
    straight = template_payload(
        STRAIGHT_APPROACH,
        template_id="straight",
        vehicle_width_m="2.731",
        vehicle_length_m="11.113",
        envelope_geometry={
            "type": "polygon",
            "points": [point(0, 0), point("0.1", 0), point("0.1", "0.001"), point(0, "0.001")],
        },
        reference_frame=reference_frame({**point(0, 0), "rotation_deg": 0}),
    )
    turn = template_payload(
        TURN_90,
        template_id="turn",
        vehicle_width_m="2.731",
        vehicle_length_m="11.113",
        envelope_geometry={
            "type": "polygon",
            "points": [
                point(39, "-31.7"),
                point("39.5", "-31.7"),
                point("39.5", "-23.9"),
                point(39, "-23.9"),
            ],
        },
        reference_frame=reference_frame({**point(0, 0), "rotation_deg": 0}),
        turn_direction="LEFT",
    )
    dock = template_payload(
        DOCK_REVERSE,
        template_id="dock",
        vehicle_width_m="2.731",
        vehicle_length_m="11.113",
        envelope_geometry={
            "type": "polygon",
            "points": [point(0, 0), point("0.1", 0), point("0.1", "0.001"), point(0, "0.001")],
        },
        reference_frame=reference_frame({**point(0, 0), "rotation_deg": 0}),
        dock_face_reference=DOCK_FACE_REFERENCE,
        approach_pose={**point(0, 0), "rotation_deg": 0},
        final_dock_pose={**point("1.624", 0), "rotation_deg": 180},
    )
    return {
        "daily_inbound_mass_kg": 20_000,
        "finished_storage_days": 7,
        "frozen_storage_days": 10,
        "main_packaging_storage_days": 4,
        "auxiliary_packaging_storage_days": 12,
        "site_constraints": site,
        "truck_access": truck_access,
        "truck_maneuver": json_ready(
            project_payload(
                templates=[straight, turn, dock], classes=[STRAIGHT_APPROACH, TURN_90, DOCK_REVERSE]
            )
        ),
    }


def test_r9_checked_in_preflight_evidence_is_immutable_and_consistent() -> None:
    evidence_path = (
        Path(__file__).resolve().parents[3]
        / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r9_slot_preflight_evidence.json"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["task_id"] == "V2_2_2_P1A_R9_TAIL_SLOT_AWARE_MAIN_SKELETON_SEARCH_R1"
    assert evidence["result"] == "PARTIAL"
    assert (
        evidence["fixture"]["sha256"]
        == "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
    )
    assert evidence["fixture"]["tool7_replays"] == 2
    assert evidence["fixture"]["same_internal_evaluation"] is True
    assert evidence["preflight"]["proof_mode"] == "EXACT_ORTHOGONAL_EVENT_ENUMERATION"
    assert evidence["preflight"]["integer_mm_brute_force_runtime"] is False
    fixed_rows = {row["skeleton_hash"]: row for row in evidence["fixed_skeleton_results"]}
    rejected = fixed_rows[R8_SECOND_SKELETON]
    assert rejected["slot_exists"] is False
    assert rejected["tail_search_started"] is False
    assert rejected["first_failure_stage"] == "TAIL_SLOT_PREFLIGHT"
    assert rejected["first_failure_reason"] == "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT"
    admissible = fixed_rows[R5_HARD_VALID_SKELETON]
    assert admissible["slot_exists"] is True
    assert admissible["tail_search_started"] is True
    assert admissible["p2d_full_pass_candidates"] == 2
    assert evidence["selected_result"]["project_layout_validated"] is True
    assert evidence["selected_result"]["p2_complete"] is True


def test_cross_fixture_real_tool7_is_not_removed_by_packaging_preflight(
    monkeypatch: Any,
) -> None:
    response, _evaluation = _capture_real_tool7(monkeypatch, _representative_tool7_payload())

    assert response["project_layout_validated"] is True
    assert response["p2_complete"] is True
    assert response["layout"]["access_pass_count"] == response["layout"]["access_requirement_count"]
    # R15 can reject a skeleton at the earlier authoritative truck preflight,
    # so a packaging-slot trace row is not guaranteed for this legacy fixture.
    # The live invariant is that this previously valid fixture still completes
    # the unchanged engineering validation chain.
