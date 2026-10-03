"""Regenerate deterministic P1A-R5 Xinzhao selection and debug evidence."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from cold_storage.modules.aily.application import site_layout_preview
from cold_storage.modules.layout.domain.structural_quality import _group_edge_facts

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
R3_LAYOUT = EVIDENCE / "xinzhao_p1a_r3_after_layout.json"
R3_METRICS = EVIDENCE / "xinzhao_p1a_r3_metrics.json"
INPUT_SHA256 = "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
MAIN_PROCESS_CODES = (
    "raw_fruit_buffer",
    "primary_precooling_room",
    "sorting_packaging_room",
    "secondary_precooling_room",
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
)
GROUPS = {
    "RAW_SIDE_GROUP": ("raw_fruit_buffer", "primary_precooling_room"),
    "PROCESSING_CORE_GROUP": ("sorting_packaging_room", "coating_room"),
    "FINISHED_SIDE_GROUP": (
        "secondary_precooling_room",
        "finished_goods_room",
        "shipping_channel",
    ),
    "SUPPORT_GROUP": (
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
    ),
    "PERSONNEL_GROUP": ("office", "changing_room"),
}
GROUP_COLORS = {
    "RAW_SIDE_GROUP": "#1f77b4",
    "PROCESSING_CORE_GROUP": "#c44e52",
    "FINISHED_SIDE_GROUP": "#2a8f5b",
    "SUPPORT_GROUP": "#aa7c19",
    "PERSONNEL_GROUP": "#79569a",
}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _png_record(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n") or len(payload) < 24:
        raise AssertionError(f"visual evidence is not a PNG: {path.name}")
    width, height = struct.unpack(">II", payload[16:24])
    return {
        "file": path.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "width": width,
        "height": height,
        "rasterizer": "macOS Quick Look qlmanage -t -s 2400",
    }


def _zone_map(layout: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    zones = layout.get("zones")
    if not isinstance(zones, list):
        raise AssertionError("selected R5 layout has no zones list")
    return {
        str(zone["zone_code"]): zone
        for zone in zones
        if isinstance(zone, Mapping) and isinstance(zone.get("zone_code"), str)
    }


def _rect(zone: Mapping[str, Any]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    x = Decimal(str(zone["x"]))
    y = Decimal(str(zone["y"]))
    width = Decimal(str(zone["width_m"]))
    depth = Decimal(str(zone["depth_m"]))
    if int(zone.get("rotation_deg", 0)) == 90:
        width, depth = depth, width
    return x, y, x + width, y + depth


def _main_geometry(layout: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    zones = _zone_map(layout)
    return {
        code: {
            key: zones[code].get(key)
            for key in ("x", "y", "width_m", "depth_m", "rotation_deg")
        }
        for code in MAIN_PROCESS_CODES
    }


def _debug_overlay(layout: Mapping[str, Any], evaluation: Mapping[str, Any]) -> str:
    zones = _zone_map(layout)
    zone_bounds = {code: _rect(zone) for code, zone in zones.items()}
    all_bounds = tuple(zone_bounds.values())
    min_x = min(row[0] for row in all_bounds)
    min_y = min(row[1] for row in all_bounds)
    max_x = max(row[2] for row in all_bounds)
    max_y = max(row[3] for row in all_bounds)
    plot_width = Decimal("1120")
    plot_height = Decimal("1000")
    scale = min(plot_width / (max_x - min_x), plot_height / (max_y - min_y))
    x_offset = Decimal("55")
    y_offset = Decimal("105")

    def project(x: Decimal, y: Decimal) -> tuple[Decimal, Decimal]:
        return x_offset + (x - min_x) * scale, y_offset + (max_y - y) * scale

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1800" viewBox="0 0 1800 1800">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<g font-family="sans-serif">',
        '<text x="40" y="44" font-size="24" font-weight="bold">P1A-R5 selected skeleton debug overlay</text>',
        '<text x="40" y="72" font-size="15">Evaluation-only; geometry is read from the selected Tool 7 layout.</text>',
    ]
    for code in sorted(zone_bounds):
        left, bottom, right, top = zone_bounds[code]
        x, y = project(left, top)
        width = (right - left) * scale
        height = (top - bottom) * scale
        parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" '
            'fill="#fafafa" stroke="#333" stroke-width="1.3"/>'
        )
        if width >= 85 and height >= 20:
            cx, cy = project((left + right) / 2, (bottom + top) / 2)
            parts.append(
                f'<text x="{cx:.2f}" y="{cy:.2f}" text-anchor="middle" '
                f'dominant-baseline="middle" font-size="10">{escape(code)}</text>'
            )
    for group, codes in GROUPS.items():
        rows = [zone_bounds[code] for code in codes if code in zone_bounds]
        if not rows:
            continue
        left = min(row[0] for row in rows)
        bottom = min(row[1] for row in rows)
        right = max(row[2] for row in rows)
        top = max(row[3] for row in rows)
        x, y = project(left, top)
        width = (right - left) * scale
        height = (top - bottom) * scale
        color = GROUP_COLORS[group]
        parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" '
            f'fill="none" stroke="{color}" stroke-width="4" stroke-dasharray="12 8"/>'
        )
    for index, (group, color) in enumerate(GROUP_COLORS.items()):
        y = Decimal(150 + index * 34)
        parts.append(
            f'<line x1="1240" y1="{y:.0f}" x2="1285" y2="{y:.0f}" '
            f'stroke="{color}" stroke-width="4" stroke-dasharray="10 6"/>'
            f'<text x="1295" y="{y + 5:.0f}" font-size="14">{group}</text>'
        )
    family = evaluation.get("selected_composition_family", {})
    axis = str(family.get("dominant_axis"))
    direction = str(family.get("dominant_direction"))
    axis_description = f"{axis} / {direction} (ordering preference only)"
    parts.extend(
        (
            f'<text x="1240" y="390" font-size="15">topology={escape(str(evaluation.get("selected_topology")))}</text>',
            f'<text x="1240" y="418" font-size="15">dominant_axis={escape(axis_description)}</text>',
            '<line x1="1240" y1="462" x2="1330" y2="462" stroke="#111" stroke-width="3"/>',
            '<polygon points="1330,456 1342,462 1330,468" fill="#111"/>',
            f'<text x="1350" y="467" font-size="14">+{escape(axis)}</text>',
            f'<text x="1240" y="506" font-size="15">distinct_full_pass_skeletons={evaluation.get("p2d_full_pass_distinct_main_process_skeleton_count")}</text>',
            f'<text x="1240" y="534" font-size="15">distinct_runner_up={evaluation.get("distinct_runner_up_present")}</text>',
            '<text x="1240" y="582" font-size="13">Dashed envelopes bound current group members;</text>',
            '<text x="1240" y="604" font-size="13">they are evaluation facts, not engineering geometry.</text>',
            '</g>',
            '</svg>',
        )
    )
    return "\n".join(parts) + "\n"


def main() -> None:
    raw = FIXTURE.read_bytes()
    input_sha = hashlib.sha256(raw).hexdigest()
    if input_sha != INPUT_SHA256:
        raise AssertionError(f"canonical Xinzhao fixture hash mismatch: {input_sha}")
    payload = json.loads(raw)
    captured: list[dict[str, Any]] = []
    original_selector = site_layout_preview.select_validated_placement

    def capture_selector(*args: Any, **kwargs: Any) -> Any:
        selection = original_selector(*args, **kwargs)
        captured.append(selection.internal_evaluation)
        return selection

    site_layout_preview.select_validated_placement = capture_selector
    try:
        first = site_layout_preview.preview_site_layout(payload)
        first_evaluation = captured[-1]
        second = site_layout_preview.preview_site_layout(payload)
        second_evaluation = captured[-1]
    finally:
        site_layout_preview.select_validated_placement = original_selector

    layout = first["layout"]
    r3_layout = json.loads(R3_LAYOUT.read_text(encoding="utf-8"))
    r3_metrics = json.loads(R3_METRICS.read_text(encoding="utf-8"))
    old_geometry = _main_geometry(r3_layout)
    new_geometry = _main_geometry(layout)
    changed_zones = [code for code in MAIN_PROCESS_CODES if old_geometry[code] != new_geometry[code]]
    svg_bytes = first["drawing"]["svg"].encode("utf-8")
    r3_svg_bytes = (EVIDENCE / "xinzhao_p1a_r3_after.svg").read_bytes()
    canonical_layout_bytes = json.dumps(
        layout, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
    ).encode("utf-8")
    second_layout_bytes = json.dumps(
        second["layout"], ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
    ).encode("utf-8")
    if first_evaluation != second_evaluation:
        raise AssertionError("Tool 7 internal selection evidence is not deterministic")
    if first["canonical_result_hash"] != second["canonical_result_hash"]:
        raise AssertionError("Tool 7 canonical result is not deterministic")
    if svg_bytes != second["drawing"]["svg"].encode("utf-8"):
        raise AssertionError("Tool 7 SVG bytes are not deterministic")

    lane_rows = first_evaluation["family_lanes"]
    skeleton_survival = first_evaluation["skeleton_survival"]
    support_group_shared_edges = _group_edge_facts(_zone_map(layout))["SUPPORT_GROUP"]
    visual_render_records = {
        name: _png_record(EVIDENCE / filename)
        for name, filename in (
            ("selected", "xinzhao_p1a_r5_selected.png"),
            ("structural_debug", "xinzhao_p1a_r5_structural_debug.png"),
        )
    }
    metrics = {
        "task_id": "V2_2_2_P1A_R5_STAGED_MULTI_TOPOLOGY_SEARCH_IMPLEMENTATION_R1",
        "result": "PARTIAL",
        "owner_xinzhao_p1a_r5_visual_review": "PENDING",
        "input_sha256": input_sha,
        "production_placement_node_budget": 120,
        "production_budget_changed": False,
        "search_policy": first_evaluation["search_policy"],
        "topology_count_explored": first_evaluation["topology_count_explored"],
        "topology_count_with_constructed_skeleton": first_evaluation[
            "topology_count_with_constructed_skeleton"
        ],
        "constructed_main_process_skeleton_count": first_evaluation[
            "constructed_main_process_skeleton_count"
        ],
        "constructed_skeleton_topologies": sorted(
            {
                str(row["topology"])
                for row in skeleton_survival
                if row.get("topology") and row.get("skeleton_hash")
            }
        ),
        "constructed_main_process_skeleton_hashes": sorted(
            {
                str(row["skeleton_hash"])
                for row in skeleton_survival
                if row.get("skeleton_hash")
            }
        ),
        "p2d_full_pass_candidate_count": sum(
            int(lane.get("p2d_full_pass_candidate_count", 0)) for lane in lane_rows
        ),
        "p2d_evaluated_distinct_main_process_skeleton_count": first_evaluation[
            "p2d_evaluated_distinct_main_process_skeleton_count"
        ],
        "distinct_p2d_full_pass_main_process_skeleton_count": first_evaluation[
            "p2d_full_pass_distinct_main_process_skeleton_count"
        ],
        "selected_topology": first_evaluation["selected_topology"],
        "support_group_shared_internal_edge_count": support_group_shared_edges,
        "selected_main_process_geometry_changed_from_r3": bool(changed_zones),
        "selected_main_process_changed_zone_count": len(changed_zones),
        "selected_main_process_changed_zones": changed_zones,
        "r3_canonical_result_hash": r3_metrics["canonical_result_hash"],
        "r5_canonical_result_hash": first["canonical_result_hash"],
        "r3_svg_sha256": r3_metrics["svg_sha256"],
        "r5_svg_sha256": first["svg_sha256"],
        "r5_svg_hash_equals_r3": svg_bytes == r3_svg_bytes,
        "distinct_runner_up_present": first_evaluation["distinct_runner_up_present"],
        "distinct_runner_up_skeleton_hash": first_evaluation[
            "distinct_runner_up_skeleton_hash"
        ],
        "distinct_runner_up_topology": first_evaluation["distinct_runner_up_topology"],
        "distinct_skeleton_first_decisive_component": first_evaluation[
            "distinct_skeleton_first_decisive_component"
        ],
        "first_decisive_component": first_evaluation["first_decisive_component"],
        "project_layout_validated": first["project_layout_validated"],
        "p2_complete": first["p2_complete"],
        "zone_count": first["zone_count"],
        "access_requirement_count": layout["access_requirement_count"],
        "access_pass_count": layout["access_pass_count"],
        "truck_route_validated": layout["truck_route_validated"],
        "building_footprint_present": bool(layout.get("building_footprint")),
        "visited_node_count": sum(int(lane.get("visited_nodes", 0)) for lane in lane_rows),
        "root_preflight_mode": "EXACT_NECESSARY_PREDICATE_OR_ORDERING_ONLY",
        "heuristic_root_pruning_used": False,
        "visual_render_records": visual_render_records,
        "same_input_same_selected_main_skeleton": _main_geometry(layout)
        == _main_geometry(second["layout"]),
        "same_input_same_layout_bytes": canonical_layout_bytes == second_layout_bytes,
        "same_input_same_canonical_hash": first["canonical_result_hash"]
        == second["canonical_result_hash"],
        "same_input_same_svg_bytes": svg_bytes == second["drawing"]["svg"].encode("utf-8"),
        "same_input_same_svg_hash": first["svg_sha256"] == second["svg_sha256"],
        "p1b_threshold_activated": False,
        "weighted_score_used": False,
    }
    _write_json(EVIDENCE / "xinzhao_p1a_r5_metrics.json", metrics)
    _write_json(EVIDENCE / "xinzhao_p1a_r5_topology_search.json", {
        "identity": "p1a-r5-topology-search-evidence@1.0.0",
        "search_policy": first_evaluation["search_policy"],
        "placement_node_budget": 120,
        "topology_lanes": lane_rows,
    })
    _write_json(EVIDENCE / "xinzhao_p1a_r5_skeleton_survival.json", {
        "identity": "p1a-r5-skeleton-survival-evidence@1.0.0",
        "skeleton_lifecycle": skeleton_survival,
        "tail_search_zone_facts_by_lane": [
            {
                "topology": lane.get("topology"),
                "search_phase": phase.get("search_phase"),
                "facts": phase.get("main_process_skeleton_generation", {}).get(
                    "tail_search_zone_facts", {}
                ),
            }
            for lane in lane_rows
            for phase in lane.get("phases", [])
        ],
    })
    _write_json(EVIDENCE / "xinzhao_p1a_r5_budget_accounting.json", {
        "production_placement_node_budget": 120,
        "production_budget_changed": False,
        "coverage_node_budget_per_topology": 15,
        "diversity_expansion_node_budget_per_topology": [
            lane.get("diversity_expansion_node_budget") for lane in lane_rows
        ],
        "preferred_topology_extra_budget": [
            lane.get("preference_extra_node_budget") for lane in lane_rows
        ],
        "allocated_lane_budgets": [lane.get("lane_node_budget") for lane in lane_rows],
        "allocated_total": sum(int(lane.get("lane_node_budget", 0)) for lane in lane_rows),
        "visited_lane_nodes": [lane.get("visited_nodes") for lane in lane_rows],
        "visited_total": sum(int(lane.get("visited_nodes", 0)) for lane in lane_rows),
        "skeleton_tail_lifecycle": skeleton_survival,
        "node_budget_is_bounded_search_cutoff": True,
        "global_optimum_claimed": False,
    })
    (EVIDENCE / "xinzhao_p1a_r5_selected_layout.json").write_text(
        json.dumps(layout, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (EVIDENCE / "xinzhao_p1a_r5_selected.svg").write_bytes(svg_bytes)
    (EVIDENCE / "xinzhao_p1a_r5_structural_debug.svg").write_text(
        _debug_overlay(layout, first_evaluation), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
