"""Capture real Tool 7 evidence for access-aware structured tail completion."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application import (
    placement as placement_application,
)
from cold_storage.modules.layout.application import (
    validated_candidate_selection as selection_application,
)
from cold_storage.modules.layout.domain import placement as placement_domain
from cold_storage.modules.layout.domain.structural_quality import _outline_class
from tests.evaluation.final_selection_authority import _capture_tool7
from tests.evaluation.r13_main_skeleton_truck_preflight import EVIDENCE_DIR, FIXTURE

EVIDENCE_PATH = EVIDENCE_DIR / "xinzhao_p1a_r2_access_endpoint_driven_tail_synthesis.json"
TAIL_IMAGE = EVIDENCE_DIR / "xinzhao_access_endpoint_driven_tail_seeds.png"
P2D_IMAGE = EVIDENCE_DIR / "xinzhao_structured_p2d_fullpass_gallery.png"

_TAIL_REQUIREMENTS = (
    "main_entrance->changing_room",
    "changing_room->sorting_packaging_room",
    "sorting_packaging_room->secondary_fruit_buffer",
    "sorting_packaging_room->frozen_fruit_room",
)
_ROUTE_COLORS = {
    "main_entrance->changing_room": "#b23a48",
    "changing_room->sorting_packaging_room": "#d17c00",
    "sorting_packaging_room->secondary_fruit_buffer": "#247a5a",
    "sorting_packaging_room->frozen_fruit_room": "#3156a3",
}
_MODULE_COLORS = {
    "RAW_MODULE": "#b8d8ec",
    "PROCESS_CORE_MODULE": "#91c9a6",
    "FINISHED_MODULE": "#f1cb86",
    "PACKAGING_MODULE": "#c9b8df",
    "SECONDARY_SUPPORT_MODULE": "#bca8d8",
    "FROZEN_SUPPORT_MODULE": "#d3c5e6",
    "OFFICE_MODULE": "#dfb9bf",
    "CHANGING_MODULE": "#e7a7ad",
}
_ZONE_MODULE = {
    "raw_fruit_buffer": "RAW_MODULE",
    "primary_precooling_room": "RAW_MODULE",
    "sorting_packaging_room": "PROCESS_CORE_MODULE",
    "secondary_precooling_room": "FINISHED_MODULE",
    "coating_room": "FINISHED_MODULE",
    "finished_goods_room": "FINISHED_MODULE",
    "shipping_channel": "FINISHED_MODULE",
    "packaging_material_storage": "PACKAGING_MODULE",
    "secondary_fruit_buffer": "SECONDARY_SUPPORT_MODULE",
    "frozen_fruit_room": "FROZEN_SUPPORT_MODULE",
    "office": "OFFICE_MODULE",
    "changing_room": "CHANGING_MODULE",
}
_ZONE_LABELS = {
    "raw_fruit_buffer": "RAW",
    "primary_precooling_room": "PRIMARY",
    "sorting_packaging_room": "SORTING",
    "secondary_precooling_room": "SECONDARY",
    "coating_room": "COATING",
    "finished_goods_room": "FINISHED",
    "shipping_channel": "SHIPPING",
    "packaging_material_storage": "PACKAGING",
    "secondary_fruit_buffer": "SEC. FRUIT",
    "frozen_fruit_room": "FROZEN",
    "office": "OFFICE",
    "changing_room": "CHANGING",
}


def _json_write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _object_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    converter = getattr(value, "to_dict", None)
    return dict(converter()) if callable(converter) else {}


def _zone_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(row.get("bounds_mm"), list):
        return {
            "zone_code": str(row.get("zone_code", "")),
            "bounds_mm": [int(value) for value in row["bounds_mm"]],
            "rotation_deg": int(row.get("rotation_deg", 0)),
        }
    left = round(float(row.get("x", 0)) * 1000)
    bottom = round(float(row.get("y", 0)) * 1000)
    width = round(float(row.get("width_m", 0)) * 1000)
    depth = round(float(row.get("depth_m", 0)) * 1000)
    rotation = int(row.get("rotation_deg", 0))
    if rotation == 90:
        width, depth = depth, width
    return {
        "zone_code": str(row.get("zone_code", "")),
        "bounds_mm": [left, bottom, left + width, bottom + depth],
        "rotation_deg": rotation,
    }


def _geometry_key(rows: Sequence[Mapping[str, Any]]) -> str:
    canonical = sorted(
        (
            str(row.get("zone_code", "")),
            tuple(int(value) for value in row.get("bounds_mm", [])),
            int(row.get("rotation_deg", 0)),
        )
        for row in rows
    )
    return json.dumps(canonical, separators=(",", ":"))


def _witness_zone_rows(witness: Mapping[str, Any]) -> list[dict[str, Any]]:
    bounds = witness.get("zone_bounds_mm")
    rotations = witness.get("zone_rotation_degrees")
    if not isinstance(bounds, Mapping):
        return []
    rotations = rotations if isinstance(rotations, Mapping) else {}
    return [
        {
            "zone_code": str(code),
            "bounds_mm": [int(value) for value in row],
            "rotation_deg": int(rotations.get(code, 0)),
        }
        for code, row in sorted(bounds.items())
        if isinstance(row, list) and len(row) == 4
    ]


def _capture_one(payload: Mapping[str, Any]) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    full_site_candidates: list[dict[str, Any]] = []
    p2d_rows: list[dict[str, Any]] = []
    app_route_counts: Counter[str] = Counter()
    real_direct = placement_domain._direct_structured_candidates
    real_full = placement_domain._module_full_site_assemblies
    real_access_validator = placement_application.route_access_requirement
    real_p2d = selection_application.route_site_placement

    def observe_access_validator(*args: Any, **kwargs: Any) -> Any:
        requirement = args[0] if args else kwargs["requirement"]
        key = f"{requirement.get('from_ref')}->{requirement.get('to_ref')}"
        app_route_counts[key] += 1
        return real_access_validator(*args, **kwargs)

    def observe_full(
        context: Any,
        main: Any,
        bays: Any,
        *,
        limit: int,
        stats: Any = None,
        main_skeleton_hash: str | None = None,
        node_limit: int | None = None,
    ) -> Any:
        for complete in real_full(
            context,
            main,
            bays,
            limit=limit,
            stats=stats,
            main_skeleton_hash=main_skeleton_hash,
            node_limit=node_limit,
        ):
            if isinstance(complete, Mapping):
                full_site_candidates.append(
                    {
                        "geometry_key": _geometry_key(
                            [
                                {
                                    "zone_code": code,
                                    "bounds_mm": list(rectangle.bounds_mm),
                                    "rotation_deg": rectangle.rotation_deg,
                                }
                                for code, rectangle in sorted(complete.items())
                            ]
                        ),
                        "zones": [
                            {
                                "zone_code": code,
                                "bounds_mm": list(rectangle.bounds_mm),
                                "rotation_deg": rectangle.rotation_deg,
                            }
                            for code, rectangle in sorted(complete.items())
                        ],
                    }
                )
            yield complete

    def observe_direct(context: Any, stats: Any) -> Any:
        iterator = real_direct(context, stats)
        try:
            yield from iterator
        finally:
            snapshots.append(
                {
                    "boundary_mm": [list(point) for point in context.boundary],
                    "obstacles_mm": [
                        [list(point) for point in polygon] for polygon in context.obstacles
                    ],
                    "truck_entrance_segment_mm": [
                        list(point) for point in placement_domain._truck_segment(context.site_body)
                    ],
                    "tail_raw_geometry_slot_count_by_module": {
                        name: sorted(values)
                        for name, values in (
                            stats.tail_raw_geometry_slot_count_by_module or {}
                        ).items()
                    },
                    "tail_access_valid_slot_count_by_module": {
                        name: sorted(values)
                        for name, values in (
                            stats.tail_access_valid_slot_count_by_module or {}
                        ).items()
                    },
                    "personnel_raw_candidate_signatures": sorted(
                        stats.personnel_raw_candidate_signatures or ()
                    ),
                    "personnel_access_2_of_2_pass_signatures": sorted(
                        stats.personnel_access_2_of_2_pass_signatures or ()
                    ),
                    "secondary_raw_candidate_signatures": sorted(
                        stats.secondary_raw_candidate_signatures or ()
                    ),
                    "secondary_access_pass_signatures": sorted(
                        stats.secondary_access_pass_signatures or ()
                    ),
                    "frozen_raw_candidate_signatures": sorted(
                        stats.frozen_raw_candidate_signatures or ()
                    ),
                    "frozen_access_pass_signatures": sorted(
                        stats.frozen_access_pass_signatures or ()
                    ),
                    "requirement_pass_counts": dict(
                        stats.construction_access_requirement_pass_counts or {}
                    ),
                    "requirement_failure_counts": dict(
                        stats.construction_access_requirement_failure_counts or {}
                    ),
                    "failure_code_counts": dict(
                        stats.construction_access_failure_code_counts or {}
                    ),
                    "direct_shared_edge_witness_count": (
                        stats.direct_shared_edge_access_witness_count
                    ),
                    "corridor_mediated_witness_count": (
                        stats.corridor_mediated_access_witness_count
                    ),
                    "reserved_access_corridors_mm": [
                        [list(point) for point in polygon]
                        for polygon in sorted(stats.reserved_access_corridor_geometries or ())
                    ],
                    "access_route_revalidation_count": stats.access_route_revalidation_count,
                    "tail_access_slot_attempt_count": stats.tail_access_slot_attempt_count,
                    "tail_access_slot_nodes_by_main": dict(
                        stats.tail_access_slot_nodes_by_main or {}
                    ),
                    "tail_access_slot_budget_exhausted": (stats.tail_access_slot_budget_exhausted),
                    "tail_candidate_space_truncated": stats.tail_candidate_space_truncated,
                    "tail_raw_geometry_slot_total_by_module": dict(
                        stats.tail_raw_geometry_slot_total_by_module or {}
                    ),
                    "tail_access_sampled_slot_count_by_module": dict(
                        stats.tail_access_sampled_slot_count_by_module or {}
                    ),
                    "tail_access_sample_truncated_by_module": dict(
                        stats.tail_access_sample_truncated_by_module or {}
                    ),
                    "tail_route_representative_limit": (
                        placement_domain.TAIL_ACCESS_ROUTE_REPRESENTATIVE_LIMIT
                    ),
                    "placement_nodes_visited": stats.visited_nodes,
                    "placement_node_budget": context.node_budget,
                    "placement_node_budget_exhausted": stats.node_budget_exhausted,
                    "main_skeleton_truck_preflight_rows": [
                        {
                            "main_skeleton_hash": str(skeleton_hash),
                            "preflight_status": row.get("preflight_status"),
                            "failure_codes": list(row.get("failure_codes", [])),
                            "visited_nodes": int(row.get("visited_nodes", 0)),
                            "node_budget_exhausted": row.get("node_budget_exhausted"),
                            "search_tree_exhausted": row.get("search_tree_exhausted"),
                        }
                        for skeleton_hash, registry_row in sorted(
                            (context.global_main_process_geometry_registry or {}).items()
                        )
                        if isinstance(registry_row, Mapping)
                        and isinstance(
                            (row := registry_row.get("main_skeleton_truck_preflight")),
                            Mapping,
                        )
                    ],
                    "access_candidate_witnesses": list(stats.tail_access_candidate_witnesses or ()),
                    "complete_access_witnesses": list(stats.tail_complete_access_witnesses or ()),
                    "tail_access_capacity_status_by_main": dict(
                        stats.tail_access_capacity_status_by_main or {}
                    ),
                    "tail_access_capacity_preflight_nodes_by_main": dict(
                        stats.tail_access_capacity_preflight_nodes_by_main or {}
                    ),
                    "tail_access_capacity_seed_counts_by_main": dict(
                        stats.tail_access_capacity_seed_counts_by_main or {}
                    ),
                    "tail_access_driven_candidate_counts_by_main": dict(
                        stats.tail_access_driven_candidate_counts_by_main or {}
                    ),
                    "tail_access_valid_candidate_counts_by_main": dict(
                        stats.tail_access_valid_candidate_counts_by_main or {}
                    ),
                    "tail_office_geometry_candidate_counts_by_main": dict(
                        stats.tail_office_geometry_candidate_counts_by_main or {}
                    ),
                    "tail_access_capacity_preflight_rows": list(
                        stats.tail_access_capacity_preflight_rows or ()
                    ),
                    "tail_generic_fallback_route_probe_count": (
                        stats.tail_generic_fallback_route_probe_count
                    ),
                    "tail_generic_fallback_truncated_count": (
                        stats.tail_generic_fallback_truncated_count
                    ),
                    "tail_generic_fallback_deferred_count": (
                        stats.tail_generic_fallback_deferred_count
                    ),
                    "site_module_trace": list(stats.site_module_assembly_trace or ()),
                }
            )

    def observe_p2d(*args: Any, **kwargs: Any) -> Any:
        candidate = args[3] if len(args) > 3 else kwargs.get("placement")
        candidate_body = _object_dict(candidate)
        routed = real_p2d(*args, **kwargs)
        routed_body = _object_dict(routed)
        zones = candidate_body.get("zones", [])
        zone_rows = (
            [_zone_row(row) for row in zones if isinstance(row, Mapping)]
            if isinstance(zones, list)
            else []
        )
        access_results = routed_body.get("access_results", [])
        relevant = (
            [
                row
                for row in access_results
                if isinstance(row, Mapping)
                and f"{row.get('from_ref')}->{row.get('to_ref')}" in _TAIL_REQUIREMENTS
            ]
            if isinstance(access_results, list)
            else []
        )
        p2d_rows.append(
            {
                "search_phase": (
                    candidate_body.get("search_provenance", {}).get("search_phase")
                    if isinstance(candidate_body.get("search_provenance"), Mapping)
                    else None
                ),
                "skeleton_hash": candidate_body.get("_r5_skeleton_hash"),
                "canonical_candidate_hash": candidate_body.get("canonical_candidate_hash"),
                "geometry_key": _geometry_key(zone_rows),
                "zones": zone_rows,
                "project_layout_validated": routed_body.get("project_layout_validated"),
                "p2_complete": routed_body.get("p2_complete"),
                "access_pass_count": routed_body.get("access_pass_count"),
                "access_requirement_count": routed_body.get("access_requirement_count"),
                "truck_route_validated": routed_body.get("truck_route_validated"),
                "p2d_building_footprint_outline_class": _outline_class(routed_body)[0],
                "layout_family": (
                    candidate_body.get("_structured_building_plan", {}).get("layout_family")
                    if isinstance(candidate_body.get("_structured_building_plan"), Mapping)
                    else None
                ),
                "tail_access_results": [
                    {
                        "requirement_identity": row.get("requirement_identity"),
                        "from_ref": row.get("from_ref"),
                        "to_ref": row.get("to_ref"),
                        "status": row.get("status"),
                        "codes": list(row.get("codes", [])),
                        "topology": row.get("topology"),
                        "centerline": row.get("centerline", []),
                        "route_length_m": row.get("route_length_m"),
                        "turn_count": row.get("turn_count"),
                    }
                    for row in relevant
                ],
            }
        )
        return routed

    placement_domain._direct_structured_candidates = observe_direct
    placement_domain._module_full_site_assemblies = observe_full
    placement_application.route_access_requirement = observe_access_validator
    selection_application.route_site_placement = observe_p2d
    try:
        tool7 = _capture_tool7(payload, allow_failed_selection=True)
    finally:
        placement_domain._direct_structured_candidates = real_direct
        placement_domain._module_full_site_assemblies = real_full
        placement_application.route_access_requirement = real_access_validator
        selection_application.route_site_placement = real_p2d

    result = tool7.get("result")
    result = result if isinstance(result, Mapping) else {}
    layout = result.get("layout")
    layout = layout if isinstance(layout, Mapping) else {}
    drawing = result.get("drawing")
    drawing = drawing if isinstance(drawing, Mapping) else {}
    return {
        "tool7": tool7,
        "snapshots": snapshots,
        "full_site_candidates": full_site_candidates,
        "p2d_rows": p2d_rows,
        "app_route_counts": dict(sorted(app_route_counts.items())),
        "selected": {
            "skeleton_hash": layout.get("selected_main_process_skeleton_hash"),
            "project_layout_validated": result.get("project_layout_validated"),
            "p2_complete": result.get("p2_complete"),
            "access_pass_count": layout.get("access_pass_count"),
            "access_requirement_count": layout.get("access_requirement_count"),
            "truck_route_validated": layout.get("truck_route_validated"),
            "zone_count": result.get("zone_count"),
            "canonical_result_hash": result.get("canonical_result_hash"),
            "svg_sha256": drawing.get("svg_sha256"),
            "svg": drawing.get("svg"),
        },
    }


def _merge_stat_sets(snapshots: Sequence[Mapping[str, Any]], field: str) -> dict[str, set[str]]:
    merged: dict[str, set[str]] = {}
    for snapshot in snapshots:
        rows = snapshot.get(field, {})
        if not isinstance(rows, Mapping):
            continue
        for name, values in rows.items():
            if isinstance(values, list):
                merged.setdefault(str(name), set()).update(str(value) for value in values)
    return merged


def _sum_snapshot_dicts(snapshots: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for snapshot in snapshots:
        rows = snapshot.get(field, {})
        if isinstance(rows, Mapping):
            for name, value in rows.items():
                totals[str(name)] += int(value)
    return dict(sorted(totals.items()))


def _witness_geometry_key(witness: Mapping[str, Any]) -> str:
    return _geometry_key(_witness_zone_rows(witness))


def _distinct_rows(rows: Sequence[Mapping[str, Any]], key_name: str) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get(key_name, ""))
        if key:
            unique.setdefault(key, dict(row))
    return [unique[key] for key in sorted(unique)]


def _point_mm(point: Any) -> tuple[int, int] | None:
    if isinstance(point, Mapping) and "x" in point and "y" in point:
        return round(float(point["x"]) * 1000), round(float(point["y"]) * 1000)
    if isinstance(point, (list, tuple)) and len(point) == 2:
        return int(point[0]), int(point[1])
    return None


def _svg_image(
    rows: Sequence[Mapping[str, Any]],
    boundary: Sequence[Sequence[int]],
    obstacles: Sequence[Sequence[Sequence[int]]],
    *,
    title: str,
) -> str:
    width, height = 1800, 1100
    panel_w, panel_h, columns = 580, 485, 3
    min_x = min(point[0] for point in boundary)
    max_x = max(point[0] for point in boundary)
    min_y = min(point[1] for point in boundary)
    max_y = max(point[1] for point in boundary)
    span_x, span_y = max_x - min_x, max_y - min_y
    scale = min((panel_w - 80) / span_x, (panel_h - 115) / span_y)

    def polygon_points(points: Sequence[Sequence[int]], transform: Any) -> str:
        return " ".join(
            f"{transform(int(point[0]), int(point[1]))[0]:.2f},"
            f"{transform(int(point[0]), int(point[1]))[1]:.2f}"
            for point in points
        )

    def render_panel(index: int, row: Mapping[str, Any]) -> list[str]:
        panel_x = 18 + (index % columns) * panel_w
        panel_y = 68 + (index // columns) * panel_h
        origin_x = panel_x + 35 + (panel_w - 70 - span_x * scale) / 2
        origin_y = panel_y + 43 + (panel_h - 95 - span_y * scale) / 2

        def transform(x: int, y: int) -> tuple[float, float]:
            return origin_x + (x - min_x) * scale, origin_y + (max_y - y) * scale

        parts = [
            f'<text x="{panel_x + 8}" y="{panel_y + 24}" font-family="Arial,sans-serif" '
            f'font-size="15" fill="#17212b">Candidate {index + 1} · '
            f"{row.get('layout_family', 'structured')} · "
            f"{str(row.get('skeleton_hash', ''))[-8:]}</text>",
            f'<polygon points="{polygon_points(boundary, transform)}" fill="#fff" '
            'stroke="#263244" stroke-width="2.2"/>',
        ]
        event_classes = row.get("candidate_event_classes", [])
        if event_classes:
            compact_events = ", ".join(str(value) for value in event_classes[:5])
            parts.append(
                f'<text x="{panel_x + 8}" y="{panel_y + 39}" font-family="Arial,sans-serif" '
                f'font-size="8" fill="#354454">{compact_events}</text>'
            )
        entrance = row.get("truck_entrance_segment_mm", [])
        if isinstance(entrance, list) and len(entrance) == 2:
            start = _point_mm(entrance[0])
            end = _point_mm(entrance[1])
            if start is not None and end is not None:
                start_x, start_y = transform(*start)
                end_x, end_y = transform(*end)
                parts.append(
                    f'<line x1="{start_x:.2f}" y1="{start_y:.2f}" '
                    f'x2="{end_x:.2f}" y2="{end_y:.2f}" stroke="#b23a48" '
                    'stroke-width="5" stroke-linecap="round"/>'
                )
        for obstacle in obstacles:
            parts.append(
                f'<polygon points="{polygon_points(obstacle, transform)}" '
                'fill="#59636e" stroke="#25303a" stroke-width="1.2"/>'
            )
        for polygon in row.get("truck_envelopes_mm", []):
            if isinstance(polygon, list) and len(polygon) >= 3:
                parts.append(
                    f'<polygon points="{polygon_points(polygon, transform)}" '
                    'fill="#ec8c3525" stroke="#df751e" stroke-width="1.5" '
                    'stroke-dasharray="5 3"/>'
                )
        for polygon in row.get("reserved_corridors_mm", []):
            if isinstance(polygon, list) and len(polygon) >= 3:
                parts.append(
                    f'<polygon points="{polygon_points(polygon, transform)}" '
                    'fill="#278c7c35" stroke="#278c7c" stroke-width="1.2"/>'
                )
        for zone in row.get("zones", []):
            if not isinstance(zone, Mapping):
                continue
            bounds = zone.get("bounds_mm")
            if not isinstance(bounds, list) or len(bounds) != 4:
                continue
            left, bottom, right, top = (int(value) for value in bounds)
            x, y = transform(left, top)
            rect_w, rect_h = (right - left) * scale, (top - bottom) * scale
            code = str(zone.get("zone_code", ""))
            module = _ZONE_MODULE.get(code, "PROCESS_CORE_MODULE")
            is_seed = zone.get("seed_candidate") is True
            fill_opacity = 0.38 if is_seed else 1.0
            stroke = "#a33b68" if is_seed else "#263244"
            stroke_width = 2.0 if is_seed else 1.3
            dash = "5 3" if is_seed else "none"
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{rect_w:.2f}" '
                f'height="{rect_h:.2f}" fill="{_MODULE_COLORS[module]}" '
                f'fill-opacity="{fill_opacity}" stroke="{stroke}" '
                f'stroke-width="{stroke_width}" stroke-dasharray="{dash}"/>'
            )
            if rect_w > 44 and rect_h > 16:
                parts.append(
                    f'<text x="{x + rect_w / 2:.2f}" y="{y + rect_h / 2:.2f}" '
                    'text-anchor="middle" dominant-baseline="middle" '
                    'font-family="Arial,sans-serif" font-size="9" fill="#17212b">'
                    f"{_ZONE_LABELS.get(code, code)}</text>"
                )
        for access in row.get("access_witnesses", []):
            if not isinstance(access, Mapping):
                continue
            pair = f"{access.get('from_ref')}->{access.get('to_ref')}"
            centerline = access.get("centerline", [])
            points = [point for value in centerline if (point := _point_mm(value)) is not None]
            if len(points) >= 2:
                transformed = [transform(x, y) for x, y in points]
                serialized = " ".join(f"{x:.2f},{y:.2f}" for x, y in transformed)
                color = _ROUTE_COLORS.get(pair, "#111827")
                parts.append(
                    f'<polyline points="{serialized}" fill="none" stroke="{color}" '
                    'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
                )
        parts.append(
            f'<text x="{panel_x + 8}" y="{panel_y + panel_h - 13}" '
            'font-family="Arial,sans-serif" font-size="11" fill="#354454">'
            "Truck envelopes: orange dashed · reserved access corridors: teal · "
            "route labels in legend</text>"
        )
        return parts

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#f5f7f9"/>',
        f'<text x="24" y="35" font-family="Arial,sans-serif" font-size="24" '
        f'fill="#17212b">{title}</text>',
    ]
    for index, row in enumerate(rows[:6]):
        parts.extend(render_panel(index, row))
    if not rows:
        parts.append(
            '<text x="36" y="105" font-family="Arial,sans-serif" font-size="20" '
            'fill="#8a3d3d">No Truck-PASS main skeleton reached tail preflight '
            "in this replay</text>"
        )
    legend_y = 1060
    for index, (name, color) in enumerate(_ROUTE_COLORS.items()):
        x = 30 + index * 430
        parts.append(
            f'<line x1="{x}" y1="{legend_y}" x2="{x + 28}" y2="{legend_y}" '
            f'stroke="{color}" stroke-width="4"/><text x="{x + 36}" y="{legend_y + 4}" '
            'font-family="Arial,sans-serif" font-size="11" fill="#17212b">'
            f"{name}</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _rasterize(svg: str, destination: Path) -> str:
    sips = shutil.which("sips")
    if sips is None:
        raise RuntimeError("sips is required to rasterize the SVG evidence on this host")
    with tempfile.TemporaryDirectory(prefix="r2-access-tail-svg-") as directory:
        source = Path(directory) / "source.svg"
        source.write_text(svg, encoding="utf-8")
        subprocess.run(
            [sips, "-s", "format", "png", str(source), "--out", str(destination)],
            check=True,
            capture_output=True,
            text=True,
        )
    return "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()


def _summarize_run(run: Mapping[str, Any]) -> dict[str, Any]:
    snapshots = [row for row in run["snapshots"] if isinstance(row, Mapping)]
    raw_sets = _merge_stat_sets(snapshots, "tail_raw_geometry_slot_count_by_module")
    access_sets = _merge_stat_sets(snapshots, "tail_access_valid_slot_count_by_module")
    requirement_pass_counts = _sum_snapshot_dicts(snapshots, "requirement_pass_counts")
    requirement_failure_counts = _sum_snapshot_dicts(snapshots, "requirement_failure_counts")
    failure_codes = _sum_snapshot_dicts(snapshots, "failure_code_counts")
    complete_witnesses = _distinct_rows(
        [
            witness
            for snapshot in snapshots
            for witness in snapshot.get("complete_access_witnesses", [])
            if isinstance(witness, Mapping)
        ],
        "complete_geometry_signature",
    )
    complete_by_key = {_witness_geometry_key(row): row for row in complete_witnesses}
    p2d_by_key: dict[str, list[Mapping[str, Any]]] = {}
    for row in run["p2d_rows"]:
        if row.get("search_phase") == "STRUCTURED":
            p2d_by_key.setdefault(str(row.get("geometry_key", "")), []).append(row)
    witness_mismatch_count = 0
    p2d_matching_geometry_count = 0
    for key, witness in complete_by_key.items():
        final_rows = p2d_by_key.get(key, [])
        if not final_rows:
            witness_mismatch_count += 1
            continue
        p2d_matching_geometry_count += 1
        construction_pairs = {
            f"{row.get('from_ref')}->{row.get('to_ref')}": row
            for row in witness.get("access_witnesses", [])
            if isinstance(row, Mapping)
        }
        if any(
            construction_pairs.get(pair, {}).get("status") != "PASS"
            or not any(
                f"{route.get('from_ref')}->{route.get('to_ref')}" == pair
                and route.get("status") == "PASS"
                for final in final_rows
                for route in final.get("tail_access_results", [])
                if isinstance(route, Mapping)
            )
            for pair in _TAIL_REQUIREMENTS
        ):
            witness_mismatch_count += 1
    structured_full_pass_rows = [
        row
        for row in run["p2d_rows"]
        if row.get("search_phase") == "STRUCTURED"
        and row.get("project_layout_validated") is True
        and row.get("p2_complete") is True
        and row.get("access_pass_count") == 12
        and row.get("access_requirement_count") == 12
        and row.get("truck_route_validated") is True
    ]
    full_pass_hashes = sorted(
        {
            str(row.get("skeleton_hash"))
            for row in structured_full_pass_rows
            if row.get("skeleton_hash")
        }
    )
    visual_full_pass_rows = [
        row
        for row in structured_full_pass_rows
        if row.get("p2d_building_footprint_outline_class") in {"RECTANGLE", "SIMPLE_L"}
    ]
    visually_distinct_full_pass_count = len(
        {str(row.get("geometry_key")) for row in visual_full_pass_rows}
    )
    full_pass_layout_family_count = len(
        {
            str(row.get("layout_family"))
            for row in visual_full_pass_rows
            if isinstance(row.get("layout_family"), str)
        }
    )
    full_site_candidates = _distinct_rows(run["full_site_candidates"], "geometry_key")
    preflight_rows_by_key: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        for row in snapshot.get("tail_access_capacity_preflight_rows", []):
            if not isinstance(row, Mapping):
                continue
            identity = json.dumps(
                [
                    row.get("critical_assembly_id"),
                    row.get("main_skeleton_hash"),
                    row.get("module_name"),
                    row.get("zone_bounds_mm"),
                ],
                sort_keys=True,
                separators=(",", ":"),
            )
            preflight_rows_by_key.setdefault(identity, dict(row))
    preflight_rows = [preflight_rows_by_key[key] for key in sorted(preflight_rows_by_key)]
    capacity_status: dict[str, str] = {}
    truck_preflight_by_hash: dict[str, dict[str, Any]] = {}
    capacity_nodes: Counter[str] = Counter()
    tail_nodes_by_main: Counter[str] = Counter()
    seed_counts: dict[str, dict[str, int]] = {}
    driven_counts: dict[str, dict[str, int]] = {}
    valid_counts: dict[str, dict[str, int]] = {}
    office_counts: dict[str, int] = {}
    for snapshot in snapshots:
        for row in snapshot.get("main_skeleton_truck_preflight_rows", []):
            if isinstance(row, Mapping):
                key = str(row.get("main_skeleton_hash", ""))
                if key:
                    truck_preflight_by_hash.setdefault(key, dict(row))
        for key, value in snapshot.get("tail_access_capacity_status_by_main", {}).items():
            capacity_status[str(key)] = str(value)
        capacity_nodes.update(
            {
                str(key): int(value)
                for key, value in snapshot.get(
                    "tail_access_capacity_preflight_nodes_by_main", {}
                ).items()
            }
        )
        tail_nodes_by_main.update(
            {
                str(key): int(value)
                for key, value in snapshot.get("tail_access_slot_nodes_by_main", {}).items()
            }
        )
        for target, field in (
            (seed_counts, "tail_access_capacity_seed_counts_by_main"),
            (driven_counts, "tail_access_driven_candidate_counts_by_main"),
            (valid_counts, "tail_access_valid_candidate_counts_by_main"),
        ):
            for main_hash, counts in snapshot.get(field, {}).items():
                merged = target.setdefault(str(main_hash), {})
                for module_name, count in counts.items():
                    merged[str(module_name)] = max(merged.get(str(module_name), 0), int(count))
        for main_hash, count in snapshot.get(
            "tail_office_geometry_candidate_counts_by_main", {}
        ).items():
            office_counts[str(main_hash)] = max(office_counts.get(str(main_hash), 0), int(count))
    first_snapshot = snapshots[0] if snapshots else {}
    image_rows: list[dict[str, Any]] = []
    preflight_by_main: dict[str, list[Mapping[str, Any]]] = {}
    for row in preflight_rows:
        preflight_by_main.setdefault(
            str(row.get("critical_assembly_id", row.get("main_skeleton_hash", ""))), []
        ).append(row)
    for critical_assembly_id, rows in sorted(preflight_by_main.items())[:6]:
        first = rows[0]
        zones = [
            {
                "zone_code": code,
                "bounds_mm": bounds,
                "rotation_deg": first.get("main_zone_rotation_degrees", {}).get(code, 0),
            }
            for code, bounds in sorted(first.get("main_zone_bounds_mm", {}).items())
        ]
        access_witnesses: list[Mapping[str, Any]] = []
        reserved_corridors: list[Any] = []
        probe_totals: Counter[str] = Counter()
        probe_passes: Counter[str] = Counter()
        module_labels = {
            "CHANGING_MODULE": "CHG",
            "SECONDARY_SUPPORT_MODULE": "SEC",
            "FROZEN_SUPPORT_MODULE": "FRZ",
            "OFFICE_MODULE": "OFF",
        }
        for row in rows:
            module_name = str(row.get("module_name", ""))
            probe_totals[module_name] += 1
            if (
                row.get("route_witness_status") == "PASS"
                or row.get("result") == "GEOMETRY_SEED_FOUND"
            ):
                probe_passes[module_name] += 1
            zone_codes = row.get("zone_bounds_mm", {})
            for code, bounds in sorted(zone_codes.items()):
                zones.append(
                    {
                        "zone_code": code,
                        "bounds_mm": bounds,
                        "rotation_deg": 0,
                        "seed_candidate": True,
                        "candidate_module": module_name,
                    }
                )
            for witness in row.get("route_witnesses", []):
                if isinstance(witness, Mapping):
                    access_witnesses.append(witness)
            reserved_corridors.extend(row.get("reserved_corridors_mm", []))
        probe_summary = " · ".join(
            f"{module_labels.get(name, name)} {probe_passes[name]}/{count}"
            for name, count in probe_totals.items()
        )
        image_rows.append(
            {
                "layout_family": "TAIL SEEDS",
                "skeleton_hash": first.get("main_skeleton_hash"),
                "critical_assembly_id": critical_assembly_id,
                "zones": zones,
                "access_witnesses": access_witnesses,
                "reserved_corridors_mm": reserved_corridors,
                "truck_envelopes_mm": first.get("truck_envelopes_mm", []),
                "candidate_event_classes": [probe_summary],
                "truck_entrance_segment_mm": first_snapshot.get("truck_entrance_segment_mm", []),
            }
        )
    p2d_gallery_rows = [
        {
            "layout_family": "P2D FULL PASS",
            "skeleton_hash": row.get("skeleton_hash"),
            "zones": row.get("zones", []),
            "access_witnesses": row.get("tail_access_results", []),
            "reserved_corridors_mm": [],
            "truck_envelopes_mm": [],
        }
        for row in structured_full_pass_rows[:6]
    ]
    evidence = {
        "structured_phase_only": True,
        "tail_geometry_only_admission": False,
        "tail_access_aware_admission": True,
        "office_changing_rigid_relation": False,
        "access_endpoint_driven_tail_synthesis": True,
        "generic_representative_sampling_is_primary": False,
        "main_entrance_influences_changing_enumeration": True,
        "sorting_influences_changing_enumeration": True,
        "sorting_influences_secondary_enumeration": True,
        "sorting_influences_frozen_enumeration": True,
        "shipping_influences_office_enumeration": True,
        "placement_domain_imports_access_routing": False,
        "access_route_validator_injected_from_application": True,
        "final_p2d_access_authority_changed": False,
        "budgets": {"placement_node": 120, "truck_node": 5000, "route_node": 20000},
        "structured_phase_node_budgets_by_context": [
            int(snapshot.get("placement_node_budget", 0)) for snapshot in snapshots
        ],
        "raw_geometry_slot_count_by_module": {
            name: len(values) for name, values in sorted(raw_sets.items())
        },
        "raw_geometry_slot_count_semantics": (
            "distinct sampled candidates encountered by exact route checks"
        ),
        "access_valid_slot_count_by_module": {
            name: len(values) for name, values in sorted(access_sets.items())
        },
        "raw_geometry_slot_occurrences_by_module": _sum_snapshot_dicts(
            snapshots, "tail_raw_geometry_slot_total_by_module"
        ),
        "access_route_probe_count_by_module": _sum_snapshot_dicts(
            snapshots, "tail_access_sampled_slot_count_by_module"
        ),
        "access_route_sample_truncated_state_count_by_module": _sum_snapshot_dicts(
            snapshots, "tail_access_sample_truncated_by_module"
        ),
        "tail_route_representative_limit": placement_domain.TAIL_ACCESS_ROUTE_REPRESENTATIVE_LIMIT,
        "main_skeleton_truck_preflight_rows": [
            truck_preflight_by_hash[key] for key in sorted(truck_preflight_by_hash)
        ],
        "truck_pass_main_hashes": sorted(
            key
            for key, row in truck_preflight_by_hash.items()
            if row.get("preflight_status") == "PASS"
        ),
        "truck_pass_main_count": sum(
            row.get("preflight_status") == "PASS" for row in truck_preflight_by_hash.values()
        ),
        "tail_access_preflighted_main_count": len(capacity_status),
        "tail_access_capable_main_count": sum(
            status == "TAIL_ACCESS_CAPABLE_MAIN" for status in capacity_status.values()
        ),
        "tail_access_capacity_status_by_main": dict(sorted(capacity_status.items())),
        "tail_access_preflight_nodes_by_main": dict(sorted(capacity_nodes.items())),
        "tail_access_nodes_by_main": dict(sorted(tail_nodes_by_main.items())),
        "changing_access_driven_candidate_count_by_main": {
            key: row.get("CHANGING_MODULE", 0) for key, row in sorted(driven_counts.items())
        },
        "changing_access_valid_count_by_main": {
            key: row.get("CHANGING_MODULE", 0) for key, row in sorted(seed_counts.items())
        },
        "secondary_access_driven_candidate_count_by_main": {
            key: row.get("SECONDARY_SUPPORT_MODULE", 0)
            for key, row in sorted(driven_counts.items())
        },
        "secondary_access_valid_count_by_main": {
            key: row.get("SECONDARY_SUPPORT_MODULE", 0) for key, row in sorted(seed_counts.items())
        },
        "frozen_access_driven_candidate_count_by_main": {
            key: row.get("FROZEN_SUPPORT_MODULE", 0) for key, row in sorted(driven_counts.items())
        },
        "frozen_access_valid_count_by_main": {
            key: row.get("FROZEN_SUPPORT_MODULE", 0) for key, row in sorted(seed_counts.items())
        },
        "tail_access_valid_candidate_count_by_main": {
            key: dict(sorted(row.items())) for key, row in sorted(valid_counts.items())
        },
        "office_geometry_candidate_count_by_main": dict(sorted(office_counts.items())),
        "tail_access_capacity_preflight_rows": preflight_rows,
        "global_infeasibility_proven": False,
        "tail_access_coverage_status": (
            "NO_TRUCK_PASS_MAIN_REACHED_S2"
            if not any(
                row.get("preflight_status") == "PASS" for row in truck_preflight_by_hash.values()
            )
            else "FINITE_ACCESS_SEED_COVERAGE_ONLY"
        ),
        "generic_fallback_route_probe_count": sum(
            int(snapshot.get("tail_generic_fallback_route_probe_count", 0))
            for snapshot in snapshots
        ),
        "generic_fallback_truncated_count": sum(
            int(snapshot.get("tail_generic_fallback_truncated_count", 0)) for snapshot in snapshots
        ),
        "generic_fallback_deferred_count": sum(
            int(snapshot.get("tail_generic_fallback_deferred_count", 0)) for snapshot in snapshots
        ),
        "personnel_raw_candidate_count": len(
            {
                value
                for snapshot in snapshots
                for value in snapshot.get("personnel_raw_candidate_signatures", [])
            }
        ),
        "personnel_access_2_of_2_pass_count": len(
            {
                value
                for snapshot in snapshots
                for value in snapshot.get("personnel_access_2_of_2_pass_signatures", [])
            }
        ),
        "secondary_raw_candidate_count": len(
            {
                value
                for snapshot in snapshots
                for value in snapshot.get("secondary_raw_candidate_signatures", [])
            }
        ),
        "secondary_access_pass_count": len(
            {
                value
                for snapshot in snapshots
                for value in snapshot.get("secondary_access_pass_signatures", [])
            }
        ),
        "frozen_raw_candidate_count": len(
            {
                value
                for snapshot in snapshots
                for value in snapshot.get("frozen_raw_candidate_signatures", [])
            }
        ),
        "frozen_access_pass_count": len(
            {
                value
                for snapshot in snapshots
                for value in snapshot.get("frozen_access_pass_signatures", [])
            }
        ),
        "construction_access_requirement_pass_counts": requirement_pass_counts,
        "construction_access_requirement_failure_counts": requirement_failure_counts,
        "construction_access_failure_code_counts": failure_codes,
        "application_route_validator_call_counts": run["app_route_counts"],
        "direct_shared_edge_access_witness_count": sum(
            int(snapshot.get("direct_shared_edge_witness_count", 0)) for snapshot in snapshots
        ),
        "corridor_mediated_access_witness_count": sum(
            int(snapshot.get("corridor_mediated_witness_count", 0)) for snapshot in snapshots
        ),
        "reserved_access_corridor_count": len(
            {
                tuple(tuple(point) for point in polygon)
                for snapshot in snapshots
                for polygon in snapshot.get("reserved_access_corridors_mm", [])
            }
        ),
        "access_route_revalidation_count": sum(
            int(snapshot.get("access_route_revalidation_count", 0)) for snapshot in snapshots
        ),
        "tail_access_slot_placement_node_attempt_count": sum(
            int(snapshot.get("tail_access_slot_attempt_count", 0)) for snapshot in snapshots
        ),
        "tail_access_slot_placement_budget_exhausted": any(
            snapshot.get("tail_access_slot_budget_exhausted") is True for snapshot in snapshots
        ),
        "tail_candidate_space_truncated": any(
            snapshot.get("tail_candidate_space_truncated") is True for snapshot in snapshots
        ),
        "placement_nodes_visited_by_context": [
            int(snapshot.get("placement_nodes_visited", 0)) for snapshot in snapshots
        ],
        "placement_node_budget_exhausted_by_context": [
            snapshot.get("placement_node_budget_exhausted") is True for snapshot in snapshots
        ],
        "complete_access_aware_site_valid_12_zone_count": len(full_site_candidates),
        "construction_complete_witness_count": len(complete_witnesses),
        "construction_witness_p2d_matching_geometry_count": p2d_matching_geometry_count,
        "tail_construction_access_witness_final_p2d_mismatch_count": witness_mismatch_count,
        "structured_p2d_full_pass_count": len(
            {str(row.get("geometry_key")) for row in structured_full_pass_rows}
        ),
        "p2d_building_footprint_outline_classes": sorted(
            {
                str(row.get("p2d_building_footprint_outline_class"))
                for row in structured_full_pass_rows
            }
        ),
        "visually_distinct_full_pass_candidate_count": visually_distinct_full_pass_count,
        "full_pass_layout_family_count": full_pass_layout_family_count,
        "distinct_structured_full_pass_skeleton_count": len(full_pass_hashes),
        "structured_full_pass_skeleton_hashes": full_pass_hashes,
        "structured_p2d_attempt_count": sum(
            row.get("search_phase") == "STRUCTURED" for row in run["p2d_rows"]
        ),
        "selected": {key: value for key, value in run["selected"].items() if key != "svg"},
        "structured_p2d_full_pass_rows": structured_full_pass_rows,
        "complete_access_witnesses": complete_witnesses,
        "sample_tail_access_witnesses": preflight_rows[:24],
        "p2d_route_rows": run["p2d_rows"],
        "site": {
            "boundary_mm": first_snapshot.get("boundary_mm", []),
            "obstacles_mm": first_snapshot.get("obstacles_mm", []),
            "truck_entrance_segment_mm": first_snapshot.get("truck_entrance_segment_mm", []),
        },
        "image_rows": image_rows,
        "p2d_gallery_rows": p2d_gallery_rows,
    }
    return evidence


def capture_access_aware_tail_replay() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise AssertionError("canonical Xinzhao fixture must be an object")
    first = _capture_one(payload)
    second = _capture_one(payload)
    first_summary = _summarize_run(first)
    second_summary = _summarize_run(second)
    determinism = {
        "same_input_same_access_slot_counts": (
            first_summary["raw_geometry_slot_count_by_module"]
            == second_summary["raw_geometry_slot_count_by_module"]
            and first_summary["access_valid_slot_count_by_module"]
            == second_summary["access_valid_slot_count_by_module"]
        ),
        "same_input_same_access_witnesses": (
            first_summary["complete_access_witnesses"]
            == second_summary["complete_access_witnesses"]
        ),
        "same_input_same_p2d_route_rows": (
            first_summary["p2d_route_rows"] == second_summary["p2d_route_rows"]
        ),
        "same_input_same_selected_layout": (
            first_summary["selected"].get("skeleton_hash")
            == second_summary["selected"].get("skeleton_hash")
        ),
        "same_input_same_canonical_result_hash": (
            first_summary["selected"].get("canonical_result_hash")
            == second_summary["selected"].get("canonical_result_hash")
        ),
        "same_input_same_svg_bytes": first["selected"].get("svg") == second["selected"].get("svg"),
        "same_input_same_svg_hash": (
            first_summary["selected"].get("svg_sha256")
            == second_summary["selected"].get("svg_sha256")
        ),
    }
    first_summary["determinism"] = determinism
    first_summary["determinism_result"] = "PASS" if all(determinism.values()) else "FAIL"
    first_summary["result"] = (
        "PASS"
        if all(determinism.values())
        and first_summary.get("visually_distinct_full_pass_candidate_count", 0) >= 5
        and first_summary.get("full_pass_layout_family_count", 0) >= 3
        else "FAIL"
    )
    first_summary["result_semantics"] = (
        "PASS requires deterministic double replay, at least five visually acceptable "
        "structured P2D full-pass candidates, and at least three layout families; "
        "determinism alone is reported separately."
    )
    site = first_summary.get("site", {})
    boundary = site.get("boundary_mm", [])
    obstacles = site.get("obstacles_mm", [])
    tail_svg = _svg_image(
        first_summary.get("image_rows", []),
        boundary,
        obstacles,
        title="R2 access-aware tail construction · exact route witnesses",
    )
    TAIL_IMAGE.with_suffix(".svg").write_text(tail_svg, encoding="utf-8")
    first_summary["tail_access_aware_image"] = {
        "png": str(TAIL_IMAGE),
        "svg": str(TAIL_IMAGE.with_suffix(".svg")),
        "png_sha256": _rasterize(tail_svg, TAIL_IMAGE),
        "route_legend": {
            "main_entrance->changing_room": "PEOPLE · 2.0 m corridor",
            "changing_room->sorting_packaging_room": "PEOPLE · 2.0 m corridor",
            "sorting_packaging_room->secondary_fruit_buffer": "SECONDARY · 2.5 m corridor",
            "sorting_packaging_room->frozen_fruit_room": "FROZEN · 2.5 m corridor",
        },
    }
    if first_summary.get("p2d_gallery_rows"):
        p2d_svg = _svg_image(
            first_summary["p2d_gallery_rows"],
            boundary,
            obstacles,
            title="Structured P2D full-pass gallery · final route authority",
        )
        P2D_IMAGE.with_suffix(".svg").write_text(p2d_svg, encoding="utf-8")
        first_summary["p2d_fullpass_gallery"] = {
            "png": str(P2D_IMAGE),
            "svg": str(P2D_IMAGE.with_suffix(".svg")),
            "png_sha256": _rasterize(p2d_svg, P2D_IMAGE),
        }
    _json_write(EVIDENCE_PATH, first_summary)
    return first_summary


if __name__ == "__main__":
    print(
        json.dumps(
            capture_access_aware_tail_replay(),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
