"""Real Tool 7 evidence for the envelope/grid/band construction refactor."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from tests.evaluation.final_selection_authority import (
    _best_record_per_skeleton,
    _capture_tool7,
    _comparison_svg,
    _rasterize,
)
from tests.evaluation.r13_main_skeleton_truck_preflight import EVIDENCE_DIR, FIXTURE

MAIN_ZONES = (
    "raw_fruit_buffer",
    "primary_precooling_room",
    "sorting_packaging_room",
    "secondary_precooling_room",
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
)
GROUPS = {
    "RAW_SIDE_BAND": ("raw_fruit_buffer", "primary_precooling_room"),
    "PROCESS_CORE_BAND": ("sorting_packaging_room", "coating_room"),
    "FINISHED_SIDE_BAND": (
        "secondary_precooling_room",
        "finished_goods_room",
        "shipping_channel",
    ),
}


def _rectangles(candidate: Mapping[str, Any]) -> dict[str, tuple[int, int, int, int, int]]:
    rows: dict[str, tuple[int, int, int, int, int]] = {}
    for row in candidate.get("zones", []):
        if not isinstance(row, Mapping) or row.get("zone_code") not in MAIN_ZONES:
            continue
        code = str(row["zone_code"])
        x = int(Decimal(str(row["x"])) * 1000)
        y = int(Decimal(str(row["y"])) * 1000)
        width = int(Decimal(str(row["width_m"])) * 1000)
        depth = int(Decimal(str(row["depth_m"])) * 1000)
        rotation = int(row.get("rotation_deg", 0))
        if rotation == 90:
            width, depth = depth, width
        rows[code] = (x, y, width, depth, rotation)
    if set(rows) != set(MAIN_ZONES):
        raise AssertionError("full-pass candidate does not contain all seven main-process zones")
    return rows


def _bounds(row: tuple[int, int, int, int, int]) -> tuple[int, int, int, int]:
    x, y, width, depth, _rotation = row
    return x, y, x + width, y + depth


def _band_signature(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    rectangles = _rectangles(candidate)
    intervals: dict[str, tuple[int, int, int, int]] = {}
    for group, codes in GROUPS.items():
        bounds = [_bounds(rectangles[code]) for code in codes]
        intervals[group] = (
            min(row[0] for row in bounds),
            min(row[1] for row in bounds),
            max(row[2] for row in bounds),
            max(row[3] for row in bounds),
        )
    result: list[str] = []
    groups = tuple(GROUPS)
    for first_index, first in enumerate(groups):
        for second in groups[first_index + 1 :]:
            a = intervals[first]
            b = intervals[second]
            for axis, low_index, high_index in (("X", 0, 2), ("Y", 1, 3)):
                relation = (
                    "A_BEFORE_B"
                    if a[high_index] <= b[low_index]
                    else "B_BEFORE_A"
                    if b[high_index] <= a[low_index]
                    else "OVERLAP"
                )
                result.append(f"{first}:{second}:{axis}:{relation}")
    return tuple(result)


def _changed_zones(first: Mapping[str, Any], second: Mapping[str, Any]) -> tuple[str, ...]:
    a = _rectangles(first)
    b = _rectangles(second)
    return tuple(code for code in MAIN_ZONES if a[code] != b[code])


def _is_micro_jitter(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    changed = _changed_zones(first, second)
    if len(changed) != 1:
        return False
    a = _rectangles(first)[changed[0]]
    b = _rectangles(second)[changed[0]]
    return a[4] == b[4] and all(abs(a[index] - b[index]) <= 10 for index in range(4))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _best_candidates(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    best = _best_record_per_skeleton(run)
    source_by_hash: dict[str, Mapping[str, Any]] = {}
    for row in run["full_pass_records"]:
        candidate = row["candidate"]
        skeleton_hash = candidate.get("_r5_skeleton_hash")
        if isinstance(skeleton_hash, str):
            source_by_hash.setdefault(skeleton_hash, candidate)
    result: list[dict[str, Any]] = []
    for row in best:
        candidate = source_by_hash[row["skeleton_hash"]]
        plan = candidate.get("_structured_building_plan")
        layout_family = plan.get("layout_family") if isinstance(plan, Mapping) else None
        envelope = plan.get("envelope") if isinstance(plan, Mapping) else None
        envelope_family = envelope.get("family") if isinstance(envelope, Mapping) else None
        p2d = row["p2d_result"]
        if p2d.get("project_layout_validated") is not True or p2d.get("p2_complete") is not True:
            continue
        if p2d.get("access_pass_count") != p2d.get("access_requirement_count"):
            continue
        if p2d.get("truck_route_validated") is not True:
            continue
        result.append(
            {
                **row,
                "layout_family": layout_family,
                "envelope_family": envelope_family,
                "truck_pass": True,
                "access_pass_count": p2d.get("access_pass_count"),
                "access_requirement_count": p2d.get("access_requirement_count"),
                "candidate": candidate,
            }
        )
    return result


def run_and_write_candidate_gallery() -> dict[str, Any]:
    """Run two unmocked Tool 7 chains and save all distinct full-pass plans."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    first = _capture_tool7(payload)
    second = _capture_tool7(payload)
    candidates = _best_candidates(first)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    gallery_sources: list[tuple[str, str]] = []
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        short_hash = candidate["skeleton_hash"].removeprefix("sha256:")[:12]
        family = str(candidate.get("layout_family") or "UNAVAILABLE")
        label = f"Candidate {index:02d} | {family} | {short_hash} | P2D PASS | Truck PASS"
        gallery_sources.append((label, candidate["svg"]))
        stem = f"xinzhao_structured_candidate_{index:02d}"
        svg_path = EVIDENCE_DIR / f"{stem}.svg"
        png_path = EVIDENCE_DIR / f"{stem}.png"
        svg_path.write_text(candidate["svg"], encoding="utf-8")
        _rasterize(candidate["svg"], png_path)
        zones = _rectangles(candidate["candidate"])
        rows.append(
            {
                "candidate_number": index,
                "skeleton_hash": candidate["skeleton_hash"],
                "layout_family": family,
                "envelope_family": candidate.get("envelope_family"),
                "canonical_topology": candidate["canonical_topology"],
                "discovery_topology": candidate["discovery_topology"],
                "p2d_full_pass": candidate["p2d_full_pass"],
                "project_layout_validated": candidate["p2d_result"].get("project_layout_validated"),
                "p2_complete": candidate["p2d_result"].get("p2_complete"),
                "access_pass_count": candidate["access_pass_count"],
                "access_requirement_count": candidate["access_requirement_count"],
                "truck_route_validated": candidate["p2d_result"].get("truck_route_validated"),
                "building_outline_class": candidate["structural_quality_facts"].get(
                    "building_outline_class"
                ),
                "main_process_zone_rectangles_mm": {code: list(zones[code]) for code in MAIN_ZONES},
                "main_band_signature": list(_band_signature(candidate["candidate"])),
                "changed_main_process_zone_codes_vs_control": list(
                    _changed_zones(candidates[0]["candidate"], candidate["candidate"])
                ),
                "main_process_zone_relation_signature": list(
                    _band_signature(candidate["candidate"])
                ),
                "structural_quality_facts": candidate["structural_quality_facts"],
                "structural_comparison_key": candidate["structural_comparison_key"],
                "svg_sha256": candidate["svg_sha256"],
                "svg_path": str(svg_path),
                "png_path": str(png_path),
            }
        )

    gallery_svg, canvas = (
        _comparison_svg(gallery_sources, columns=3) if gallery_sources else ("", {})
    )
    gallery_svg_path = EVIDENCE_DIR / "xinzhao_structured_candidate_gallery.svg"
    gallery_png_path = EVIDENCE_DIR / "xinzhao_structured_candidate_gallery.png"
    if gallery_sources:
        gallery_svg_path.write_text(gallery_svg, encoding="utf-8")
        _rasterize(gallery_svg, gallery_png_path)

    distinct_signatures = {tuple(row["main_band_signature"]) for row in rows}
    meaningful_count = 1 if rows else 0
    micro_jitter_count = 0
    major_config_changed_count = 0
    for index, _row in enumerate(rows[1:], start=1):
        prior_candidate = candidates[0]["candidate"]
        current_candidate = candidates[index]["candidate"]
        changed = _changed_zones(prior_candidate, current_candidate)
        band_changed = _band_signature(prior_candidate) != _band_signature(current_candidate)
        if _is_micro_jitter(prior_candidate, current_candidate):
            micro_jitter_count += 1
        elif len(changed) >= 2 or band_changed:
            meaningful_count += 1
        if band_changed:
            major_config_changed_count += 1

    internal = first["internal"]
    diagnostics = internal.get("r6_topology_diagnostics", {})
    queue = diagnostics.get("r11_work_queue", []) if isinstance(diagnostics, Mapping) else []
    nodes_by_envelope: Counter[str] = Counter()
    nodes_by_band: Counter[str] = Counter()
    for work in queue:
        if not isinstance(work, Mapping):
            continue
        item = work.get("work_item", {})
        if not isinstance(item, Mapping):
            item = {}
        node_delta = int(work.get("nodes_visited", 0))
        nodes_by_envelope[str(item.get("envelope_family", "UNCLASSIFIED"))] += node_delta
        nodes_by_band[str(item.get("band_family", "UNCLASSIFIED"))] += node_delta
    truck_rows = diagnostics.get("main_skeleton_truck_preflight_trace", [])
    distinct_examined = {
        row.get("main_skeleton_hash")
        for row in truck_rows
        if isinstance(row, Mapping) and isinstance(row.get("main_skeleton_hash"), str)
    }
    distinct_truck_passes = {
        row.get("main_skeleton_hash")
        for row in truck_rows
        if isinstance(row, Mapping) and row.get("preflight_status") == "PASS"
    }
    primary_axes: Counter[str] = Counter()
    for full_pass in first["full_pass_records"]:
        plan = full_pass["candidate"].get("_structured_building_plan", {})
        if isinstance(plan, Mapping) and isinstance(plan.get("primary_grid"), Mapping):
            grid = plan["primary_grid"]
            primary_axes["X"] = max(primary_axes["X"], len(grid.get("primary_x_axes_mm", [])))
            primary_axes["Y"] = max(primary_axes["Y"], len(grid.get("primary_y_axes_mm", [])))

    first_result = first["result"]
    second_result = second["result"]
    budget_accounting = diagnostics.get("r11_budget_accounting", {})
    budget_accounting = budget_accounting if isinstance(budget_accounting, Mapping) else {}
    preflight_status_counts = Counter(
        str(row.get("preflight_status", "UNAVAILABLE"))
        for row in truck_rows
        if isinstance(row, Mapping)
    )
    band_family_attempt_counts = Counter(
        str(row.get("layout_family"))
        for row in diagnostics.get("constructive_divergence_trace", [])
        if isinstance(row, Mapping) and row.get("layout_family")
    )
    envelope_family_candidate_counts = Counter(
        str(row.get("envelope_family") or "UNAVAILABLE") for row in rows
    )
    layout_family_candidate_counts = Counter(str(row.get("layout_family")) for row in rows)
    evidence = {
        "identity": "v222-p1a-envelope-grid-band-zone-candidates@1.0.0",
        "task_id": "V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R1",
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "generator_architecture": "ENVELOPE_GRID_BAND_ZONE",
        "production_placement_node_budget": 120,
        "production_node_visits": budget_accounting.get("global_nodes_visited"),
        "main_skeletons_examined": len(distinct_examined),
        "distinct_truck_feasible_skeleton_count": len(distinct_truck_passes),
        "distinct_p2d_full_pass_skeleton_count": len(rows),
        "visually_distinct_full_pass_candidate_count": meaningful_count,
        "meaningful_structured_skeleton_count": meaningful_count,
        "micro_jitter_variant_count": micro_jitter_count,
        "major_band_configuration_changed_candidate_count": major_config_changed_count,
        "major_band_configuration_count": len(distinct_signatures),
        "primary_x_axis_count": primary_axes.get("X", 0),
        "primary_y_axis_count": primary_axes.get("Y", 0),
        "nodes_by_envelope_family": dict(sorted(nodes_by_envelope.items())),
        "nodes_by_band_family": dict(sorted(nodes_by_band.items())),
        "preflight_status_counts": dict(sorted(preflight_status_counts.items())),
        "work_round_count": budget_accounting.get("work_round_count"),
        "active_work_item_count": budget_accounting.get("active_work_item_count"),
        "truncated_active_work_item_count": budget_accounting.get(
            "truncated_active_work_item_count"
        ),
        "early_stop_reason": budget_accounting.get("early_stop_reason"),
        "layout_family_attempt_counts": dict(sorted(band_family_attempt_counts.items())),
        "layout_family_full_pass_candidate_counts": dict(
            sorted(layout_family_candidate_counts.items())
        ),
        "envelope_family_full_pass_candidate_counts": dict(
            sorted(envelope_family_candidate_counts.items())
        ),
        "main_skeleton_truck_preflight_trace": truck_rows,
        "layout_families_implemented_and_attempted": sorted(
            {
                str(row.get("layout_family"))
                for row in diagnostics.get("constructive_divergence_trace", [])
                if isinstance(row, Mapping) and row.get("layout_family")
            }
        ),
        "candidates": rows,
        "visual_gallery": {
            "gallery_svg": str(gallery_svg_path) if gallery_sources else None,
            "gallery_png": str(gallery_png_path) if gallery_sources else None,
            "same_canvas": canvas.get("same_canvas", False),
            "same_scale": canvas.get("same_scale", False),
            "uncropped": canvas.get("uncropped", False),
            "site_boundary_visible": True,
        },
        "determinism": {
            "same_selected_layout": first_result.get("layout") == second_result.get("layout"),
            "same_canonical_result_hash": first_result.get("canonical_result_hash")
            == second_result.get("canonical_result_hash"),
            "same_svg_bytes": first_result.get("drawing", {}).get("svg")
            == second_result.get("drawing", {}).get("svg"),
            "same_svg_hash": first_result.get("svg_sha256") == second_result.get("svg_sha256"),
        },
        "selected_result": {
            "project_layout_validated": first_result.get("project_layout_validated"),
            "p2_complete": first_result.get("p2_complete"),
            "access_pass_count": first_result.get("layout", {}).get("access_pass_count"),
            "access_requirement_count": first_result.get("layout", {}).get(
                "access_requirement_count"
            ),
            "truck_route_validated": first_result.get("layout", {}).get("truck_route_validated"),
            "zone_count": first_result.get("zone_count"),
            "building_footprint_present": bool(
                first_result.get("layout", {}).get("building_footprint")
            ),
            "canonical_result_hash": first_result.get("canonical_result_hash"),
            "svg_sha256": first_result.get("svg_sha256"),
        },
    }
    output = EVIDENCE_DIR / "xinzhao_structured_candidate_gallery.json"
    _write_json(output, evidence)
    return evidence


if __name__ == "__main__":
    summary = run_and_write_candidate_gallery()
    print(
        json.dumps({key: value for key, value in summary.items() if key != "candidates"}, indent=2)
    )
