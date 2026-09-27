"""Full-chain checks for R9 preflight lifecycle and deterministic Tool 7 output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.modules.aily.application import site_layout_preview
from cold_storage.modules.aily.application.mcp_site_layout import invoke_preview_site_layout_tool
from cold_storage.modules.aily.application.preview_bundle import json_ready
from cold_storage.modules.layout.domain.dimensioning import canonical_json
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


def test_xinzhao_real_tool7_preflights_956e_and_keeps_55589_admissible(
    monkeypatch: Any,
) -> None:
    payload = json.loads(XINZHAO_INPUT.read_text(encoding="utf-8"))
    first, first_evaluation = _capture_real_tool7(monkeypatch, payload)
    second, second_evaluation = _capture_real_tool7(monkeypatch, payload)

    assert json.dumps(first_evaluation, sort_keys=True, default=str) == json.dumps(
        second_evaluation,
        sort_keys=True,
        default=str,
    )

    rejected = _preflight_row(first_evaluation, R8_SECOND_SKELETON)
    assert rejected["event"] == "TAIL_SLOT_PREFLIGHT"
    assert rejected["packaging_preflight_status"] == "NO_LEGAL_SLOT"
    assert rejected["packaging_slot_exists"] is False
    assert rejected["tail_admissible"] is False
    assert rejected["tail_search_started"] is False
    assert rejected["preflight"]["proof_mode"] == "EXACT_ORTHOGONAL_EVENT_ENUMERATION"

    rejected_lifecycle = _lifecycle_row(first_evaluation, R8_SECOND_SKELETON)
    assert rejected_lifecycle["first_failure_stage"] == "TAIL_SLOT_PREFLIGHT"
    assert rejected_lifecycle["first_failure_reason"] == (
        "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT"
    )
    assert rejected_lifecycle["tail_search_started"] is False
    assert rejected_lifecycle["p2d_reached"] is False

    admissible = _preflight_row(first_evaluation, R5_HARD_VALID_SKELETON)
    assert admissible["packaging_slot_exists"] is True
    assert admissible["tail_search_started"] is True
    admissible_lifecycle = _lifecycle_row(first_evaluation, R5_HARD_VALID_SKELETON)
    assert admissible_lifecycle["tail_search_started_by_topology"] is not None
    assert admissible_lifecycle["p2d_reached"] is True

    first_layout = first["layout"]
    second_layout = second["layout"]
    first_drawing = first["drawing"]
    second_drawing = second["drawing"]
    assert first_layout["project_layout_validated"] is True
    assert first_layout["p2_complete"] is True
    assert first_layout["access_pass_count"] == first_layout["access_requirement_count"]
    assert first_layout["truck_route_validated"] is True
    assert first_layout["building_footprint"]["footprint"]
    # R11 continues constructive search after each admissible seed instead of
    # stopping after the historical R9 pair. Preserve the semantic check (both
    # known geometries were discovered) without freezing the old search count.
    assert first_evaluation["constructed_main_process_skeleton_count"] >= 2
    assert first_evaluation["p2d_evaluated_distinct_main_process_skeleton_count"] >= 1
    assert first_evaluation["p2d_full_pass_distinct_main_process_skeleton_count"] >= 1
    assert first["canonical_result_hash"] == second["canonical_result_hash"]
    assert first["svg_sha256"] == second["svg_sha256"]
    assert canonical_json(first_layout) == canonical_json(second_layout)
    assert first_drawing["svg"] == second_drawing["svg"]
    assert canonical_json(first_drawing) == canonical_json(second_drawing)
    assert (
        first_evaluation["selected_main_process_skeleton_hash"]
        == second_evaluation["selected_main_process_skeleton_hash"]
    )


def test_cross_fixture_real_tool7_is_not_removed_by_packaging_preflight(
    monkeypatch: Any,
) -> None:
    response, evaluation = _capture_real_tool7(monkeypatch, _representative_tool7_payload())

    assert response["project_layout_validated"] is True
    assert response["p2_complete"] is True
    assert response["layout"]["access_pass_count"] == response["layout"]["access_requirement_count"]
    rows = evaluation["r6_topology_diagnostics"]["tail_slot_preflight_trace"]
    assert rows
    assert any(
        row.get("packaging_preflight_status") == "LEGAL_SLOT_EXISTS"
        and row.get("tail_search_started") is True
        for row in rows
    )
