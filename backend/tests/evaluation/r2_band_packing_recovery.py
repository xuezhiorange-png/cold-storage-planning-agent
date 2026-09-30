"""Capture one unmocked Xinzhao Tool 7 replay for R2 recovery evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.application.svg_projection import project_validated_layout_to_svg
from tests.evaluation.final_selection_authority import _capture_tool7, _comparison_svg, _rasterize
from tests.evaluation.r13_main_skeleton_truck_preflight import EVIDENCE_DIR, FIXTURE


def _compact_rows(rows: object, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [
        {field: row.get(field) for field in fields if field in row}
        for row in rows
        if isinstance(row, Mapping)
    ]


def _record_search_phase(row: Mapping[str, Any]) -> str | None:
    candidate = row.get("candidate")
    if not isinstance(candidate, Mapping):
        return None
    provenance = candidate.get("search_provenance")
    if not isinstance(provenance, Mapping):
        return None
    value = provenance.get("search_phase")
    return value if isinstance(value, str) else None


def capture_r2_recovery_replay() -> dict[str, Any]:
    """Run the real preview chain once and persist bounded current evidence."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    run = _capture_tool7(payload, allow_failed_selection=True)
    internal = run["internal"]
    diagnostics = internal.get("r6_topology_diagnostics", {})
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    result = run.get("result")
    result = result if isinstance(result, Mapping) else {}
    layout = result.get("layout")
    layout = layout if isinstance(layout, Mapping) else {}
    lane_rows = internal.get("family_lanes", [])
    lane_summary: list[dict[str, Any]] = []
    for lane in lane_rows if isinstance(lane_rows, list) else []:
        if not isinstance(lane, Mapping):
            continue
        phases = lane.get("phases", [])
        lane_summary.append(
            {
                "composition_family": lane.get("composition_family"),
                "p2d_full_pass_candidate_count": lane.get("p2d_full_pass_candidate_count"),
                "phases": [
                    {
                        key: phase.get(key)
                        for key in (
                            "search_phase",
                            "visited_nodes",
                            "candidate_count",
                            "p2d_full_pass_candidate_count",
                            "status",
                            "search_exhausted",
                            "search_truncated",
                        )
                        if key in phase
                    }
                    for phase in phases
                    if isinstance(phase, Mapping)
                ]
                if isinstance(phases, list)
                else [],
            }
        )

    attempts = _compact_rows(
        diagnostics.get("construction_attempts"),
        (
            "layout_family",
            "process_axis",
            "envelope_family",
            "support_side",
            "result",
            "first_failure_stage",
            "first_failure_interface",
            "rejection_reason",
            "skeleton_hash",
        ),
    )
    constructive = _compact_rows(
        diagnostics.get("constructive_divergence_trace"),
        (
            "layout_family",
            "process_axis",
            "envelope_family",
            "result",
            "envelope_bounds_mm",
            "envelope_components_mm",
            "support_band_is_full_envelope",
            "personnel_band_is_full_envelope",
            "reason",
            "rejection_reason",
        ),
    )
    failures_by_family: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        family = str(attempt.get("layout_family", "UNCLASSIFIED"))
        failures_by_family.setdefault(
            family,
            {
                "attempt_count": 0,
                "complete_12_zone_count": 0,
                "first_failure_stage": None,
                "first_failure_reason": None,
            },
        )
        summary = failures_by_family[family]
        summary["attempt_count"] += 1
        summary["complete_12_zone_count"] += int(
            attempt.get("result") == "FULL_12_ZONE_CANDIDATE_EMITTED"
        )
        if summary["first_failure_reason"] is None and attempt.get("rejection_reason"):
            summary["first_failure_stage"] = attempt.get("first_failure_stage")
            summary["first_failure_reason"] = attempt.get("rejection_reason")

    truck_rows = diagnostics.get("main_skeleton_truck_preflight_trace", [])
    truck_rows = truck_rows if isinstance(truck_rows, list) else []
    skeleton_hashes = sorted(
        {
            row.get("main_skeleton_hash")
            for row in truck_rows
            if isinstance(row, Mapping) and isinstance(row.get("main_skeleton_hash"), str)
        }
    )
    preflight_counts = Counter(
        str(row.get("preflight_status", "UNAVAILABLE"))
        for row in truck_rows
        if isinstance(row, Mapping)
    )

    full_pass_records = run.get("full_pass_records", [])
    full_pass_records = full_pass_records if isinstance(full_pass_records, list) else []

    structured_records = [
        row
        for row in full_pass_records
        if isinstance(row, Mapping)
        and record_search_phase(row) == "STRUCTURED"
    ]
    fallback_records = [
        row
        for row in full_pass_records
        if isinstance(row, Mapping)
        and record_search_phase(row) == "GENERAL_FALLBACK"
    ]
    evidence_rows: list[dict[str, Any]] = []
    gallery_sources: list[tuple[str, str]] = []
    site_geometry = run["site_geometry"]
    for index, row in enumerate(structured_records, start=1):
        candidate = row["candidate"]
        p2d_result = row["p2d_result"]
        plan = candidate.get("_structured_building_plan")
        family = (
            str(plan.get("layout_family", "UNAVAILABLE"))
            if isinstance(plan, Mapping)
            else "UNAVAILABLE"
        )
        projected = project_validated_layout_to_svg(
            p2d_result,
            site_geometry=site_geometry,
        ).to_dict()
        svg = projected.get("svg")
        if not isinstance(svg, str):
            continue
        skeleton_hash = str(candidate.get("_r5_skeleton_hash", "UNAVAILABLE"))
        stem = f"xinzhao_structured_r2_recovery_candidate_{index:02d}"
        svg_path = EVIDENCE_DIR / f"{stem}.svg"
        png_path = EVIDENCE_DIR / f"{stem}.png"
        svg_path.write_text(svg, encoding="utf-8")
        _rasterize(svg, png_path)
        gallery_sources.append(
            (
                f"Candidate {index:02d} | {family} | {skeleton_hash[-12:]} | P2D PASS | Truck PASS",
                svg,
            )
        )
        evidence_rows.append(
            {
                "candidate_number": index,
                "skeleton_hash": skeleton_hash,
                "layout_family": family,
                "p2d_full_pass": True,
                "truck_route_validated": p2d_result.get("truck_route_validated"),
                "access_pass_count": p2d_result.get("access_pass_count"),
                "access_requirement_count": p2d_result.get("access_requirement_count"),
                "project_layout_validated": p2d_result.get("project_layout_validated"),
                "p2_complete": p2d_result.get("p2_complete"),
                "svg_sha256": "sha256:" + hashlib.sha256(svg.encode("utf-8")).hexdigest(),
                "svg_path": str(svg_path),
                "png_path": str(png_path),
            }
        )

    fallback_rows: list[dict[str, Any]] = []
    fallback_gallery_sources: list[tuple[str, str]] = []
    for index, row in enumerate(fallback_records, start=1):
        candidate = row["candidate"]
        p2d_result = row["p2d_result"]
        projected = project_validated_layout_to_svg(
            p2d_result,
            site_geometry=site_geometry,
        ).to_dict()
        svg = projected.get("svg")
        if not isinstance(svg, str):
            continue
        skeleton_hash = str(candidate.get("_r5_skeleton_hash", "UNAVAILABLE"))
        stem = f"xinzhao_general_fallback_r2_recovery_candidate_{index:02d}"
        svg_path = EVIDENCE_DIR / f"{stem}.svg"
        png_path = EVIDENCE_DIR / f"{stem}.png"
        svg_path.write_text(svg, encoding="utf-8")
        _rasterize(svg, png_path)
        fallback_gallery_sources.append(
            (
                f"Fallback {index:02d} | {row['family'].get('family', 'UNAVAILABLE')} "
                f"| {skeleton_hash[-12:]} "
                "| P2D PASS | Truck PASS",
                svg,
            )
        )
        fallback_rows.append(
            {
                "candidate_number": index,
                "skeleton_hash": skeleton_hash,
                "search_phase": "GENERAL_FALLBACK",
                "p2d_full_pass": True,
                "truck_route_validated": p2d_result.get("truck_route_validated"),
                "access_pass_count": p2d_result.get("access_pass_count"),
                "access_requirement_count": p2d_result.get("access_requirement_count"),
                "project_layout_validated": p2d_result.get("project_layout_validated"),
                "p2_complete": p2d_result.get("p2_complete"),
                "svg_sha256": "sha256:" + hashlib.sha256(svg.encode("utf-8")).hexdigest(),
                "svg_path": str(svg_path),
                "png_path": str(png_path),
            }
        )

    gallery_path: str | None = None
    if gallery_sources:
        gallery_svg, canvas = _comparison_svg(gallery_sources, columns=3)
        gallery_svg_path = EVIDENCE_DIR / "xinzhao_structured_r2_recovery_gallery.svg"
        gallery_png_path = EVIDENCE_DIR / "xinzhao_structured_r2_recovery_gallery.png"
        gallery_svg_path.write_text(gallery_svg, encoding="utf-8")
        _rasterize(gallery_svg, gallery_png_path)
        gallery_path = str(gallery_png_path)
    else:
        canvas = {"same_canvas": False, "same_scale": False, "uncropped": False}

    fallback_gallery_path: str | None = None
    if fallback_gallery_sources:
        fallback_svg, fallback_canvas = _comparison_svg(fallback_gallery_sources, columns=3)
        fallback_svg_path = EVIDENCE_DIR / "xinzhao_general_fallback_r2_recovery_gallery.svg"
        fallback_png_path = EVIDENCE_DIR / "xinzhao_general_fallback_r2_recovery_gallery.png"
        fallback_svg_path.write_text(fallback_svg, encoding="utf-8")
        _rasterize(fallback_svg, fallback_png_path)
        fallback_gallery_path = str(fallback_png_path)
    else:
        fallback_canvas = {"same_canvas": False, "same_scale": False, "uncropped": False}

    selected_layout = run.get("selector_result", {}).get("selected_layout")
    selected_layout = selected_layout if isinstance(selected_layout, Mapping) else None
    selected_svg_sha = None
    if result:
        drawing = result.get("drawing")
        svg = drawing.get("svg") if isinstance(drawing, Mapping) else None
        if isinstance(svg, str):
            selected_svg_sha = "sha256:" + hashlib.sha256(svg.encode("utf-8")).hexdigest()

    evidence = {
        "identity": "v222-p1a-r2-band-packing-recovery-replay@1.0.0",
        "task_id": "V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2",
        "mode": "R2_BAND_PACKING_AND_COMPATIBILITY_RECOVERY",
        "replay": "UNMOCKED_TOOL7_SINGLE_RUN",
        "fixture_path": str(FIXTURE),
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "preview_error": run.get("preview_error"),
        "selector_status": run.get("selector_result", {}).get("status"),
        "selected_layout_present": selected_layout is not None,
        "placement_node_budget": diagnostics.get("r11_budget_accounting", {}).get("global_budget")
        if isinstance(diagnostics.get("r11_budget_accounting"), Mapping)
        else None,
        "budget_accounting": diagnostics.get("r11_budget_accounting"),
        "phase_lanes": lane_summary,
        "layout_family_failure_summary": failures_by_family,
        "construction_attempts": attempts,
        "constructive_plan_attempts": constructive,
        "truck_preflight": {
            "skeleton_hashes": skeleton_hashes,
            "unique_skeleton_count": len(skeleton_hashes),
            "status_counts": dict(sorted(preflight_counts.items())),
            "rows": _compact_rows(
                truck_rows,
                (
                    "main_skeleton_hash",
                    "layout_family",
                    "preflight_status",
                    "failure_reason",
                    "visited_nodes",
                    "node_budget",
                    "tail_search_started",
                ),
            ),
        },
        "full_pass_candidates": evidence_rows,
        "structured_full_pass_candidate_count": len(evidence_rows),
        "gallery_png": gallery_path,
        "gallery_canvas": canvas,
        "legacy_fallback_full_pass_candidates": fallback_rows,
        "legacy_fallback_full_pass_candidate_count": len(fallback_rows),
        "legacy_fallback_gallery_png": fallback_gallery_path,
        "legacy_fallback_gallery_canvas": fallback_canvas,
        "selected_result": {
            "project_layout_validated": result.get("project_layout_validated"),
            "p2_complete": result.get("p2_complete"),
            "access_pass_count": layout.get("access_pass_count"),
            "access_requirement_count": layout.get("access_requirement_count"),
            "truck_route_validated": layout.get("truck_route_validated"),
            "zone_count": result.get("zone_count"),
            "building_footprint_present": bool(layout.get("building_footprint")),
            "canonical_result_hash": result.get("canonical_result_hash"),
            "svg_sha256": selected_svg_sha,
        }
        if result
        else None,
        "legacy_fallback_candidate_count": sum(
            int(row.get("candidate_count", 0))
            for lane in lane_summary
            for row in lane["phases"]
            if row.get("search_phase") == "GENERAL_FALLBACK"
        ),
        "determinism": "NOT_ASSESSED_BY_SINGLE_REPLAY",
    }
    output = EVIDENCE_DIR / "xinzhao_p1a_r2_recovery_runtime.json"
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return evidence


if __name__ == "__main__":
    print(json.dumps(capture_r2_recovery_replay(), ensure_ascii=False, sort_keys=True))
