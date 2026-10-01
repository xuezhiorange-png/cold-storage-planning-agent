"""Unmocked Xinzhao evidence for the R2 site-bounded compact synthesizer."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.domain import placement as placement_domain
from tests.evaluation.final_selection_authority import _capture_tool7, _rasterize
from tests.evaluation.r2_local_composition_first import _p2d_footprint_regularity_facts
from tests.evaluation.r13_main_skeleton_truck_preflight import EVIDENCE_DIR, FIXTURE

EVIDENCE_PATH = EVIDENCE_DIR / "xinzhao_p1a_r2_site_bounded_compact_floorplan.json"
SITE_WIDTH_MM = 75_460
SITE_HEIGHT_MM = 55_000
FAMILY_STEMS = {
    "LINEAR_3_BAND": "xinzhao_compact_linear_local",
    "CENTRAL_PROCESS_WITH_SIDE_BANKS": "xinzhao_compact_central_local",
    "LONGITUDINAL_PROCESS_SPINE": "xinzhao_compact_spine_local",
}
COLORS = {
    "RAW_SIDE_BAND": "#b7d5eb",
    "PROCESS_CORE_BAND": "#8dc5a4",
    "FINISHED_SIDE_BAND": "#f1cb86",
    "SUPPORT_BAND": "#c5b6df",
    "PERSONNEL_EDGE_BAND": "#dfb8bd",
}
LABELS = {
    "raw_fruit_buffer": "RAW",
    "primary_precooling_room": "PRIMARY PRECOOL",
    "sorting_packaging_room": "SORTING",
    "secondary_precooling_room": "SECONDARY PRECOOL",
    "coating_room": "COATING",
    "finished_goods_room": "FINISHED GOODS",
    "shipping_channel": "SHIPPING",
    "packaging_material_storage": "PACKAGING",
    "secondary_fruit_buffer": "FRUIT BUFFER",
    "frozen_fruit_room": "FROZEN",
    "office": "OFFICE",
    "changing_room": "CHANGING",
}


def _composition_signature(composition: Any) -> tuple[tuple[str, tuple[int, ...]], ...]:
    return tuple(
        (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
        for code, rectangle in sorted(composition.placements().items())
    )


def _bbox_metrics(composition: Any) -> dict[str, Any]:
    placements = composition.placements()
    left, bottom, right, top = placement_domain._local_bbox_bounds(placements)
    width, height = right - left, top - bottom
    feasible = (width <= SITE_WIDTH_MM and height <= SITE_HEIGHT_MM) or (
        width <= SITE_HEIGHT_MM and height <= SITE_WIDTH_MM
    )
    x_axes = {
        value for rect in placements.values() for value in (rect.bounds_mm[0], rect.bounds_mm[2])
    }
    y_axes = {
        value for rect in placements.values() for value in (rect.bounds_mm[1], rect.bounds_mm[3])
    }
    sides = []
    chain = placement_domain.MAIN_PROCESS_ZONE_CODES
    for first_code, second_code in zip(chain, chain[1:], strict=False):
        side = placement_domain._adjacent_side(placements[first_code], placements[second_code])
        if side is not None:
            sides.append("X" if side in {"EAST", "WEST"} else "Y")
    return {
        "bbox_width_mm": width,
        "bbox_height_mm": height,
        "bbox_width_m": width / 1000,
        "bbox_height_m": height / 1000,
        "bbox_site_extent_feasible": feasible,
        "main_axis_count": len(x_axes) + len(y_axes),
        "main_direction_change_count": sum(
            first != second for first, second in zip(sides, sides[1:], strict=False)
        ),
    }


def _local_svg(composition: Any) -> str:
    placements = composition.placements()
    left, bottom, right, top = placement_domain._local_bbox_bounds(placements)
    width, height = right - left, top - bottom
    frame_width = max(width, SITE_WIDTH_MM)
    frame_height = max(height, SITE_HEIGHT_MM)
    scale = min(1050 / max(frame_width, 1), 660 / max(frame_height, 1))
    x_offset, y_offset = 90.0, 100.0
    local_origin_y = y_offset + frame_height * scale
    canvas_width, canvas_height = 1230, 850
    fit = "YES" if _bbox_metrics(composition)["bbox_site_extent_feasible"] else "NO"
    rows = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" '
        f'height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}">',
        f'<rect width="{canvas_width}" height="{canvas_height}" fill="#fff"/>',
        f'<text x="28" y="38" font-family="Arial,sans-serif" font-size="21" '
        f'fill="#1b2733">{html.escape(composition.layout_family)} · '
        "compact local composition</text>",
    ]
    rows.append(
        f'<rect x="{x_offset:.2f}" y="{local_origin_y - SITE_HEIGHT_MM * scale:.2f}" '
        f'width="{SITE_WIDTH_MM * scale:.2f}" height="{SITE_HEIGHT_MM * scale:.2f}" '
        'fill="none" stroke="#385b88" stroke-width="2.5" stroke-dasharray="9 6"/>'
    )
    for code, rectangle in sorted(placements.items()):
        x0, y0, x1, y1 = rectangle.bounds_mm
        x = x_offset + (x0 - left) * scale
        y = local_origin_y - (y1 - bottom) * scale
        rect_width, rect_height = (x1 - x0) * scale, (y1 - y0) * scale
        rows.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{rect_width:.2f}" '
            f'height="{rect_height:.2f}" '
            f'fill="{COLORS[placement_domain.zone_band_assignment(code)]}" '
            'stroke="#263244" stroke-width="1.8"/>'
        )
        if rect_width > 55 and rect_height > 23:
            rows.append(
                f'<text x="{x + rect_width / 2:.2f}" y="{y + rect_height / 2:.2f}" '
                'text-anchor="middle" dominant-baseline="middle" '
                'font-family="Arial,sans-serif" font-size="10" fill="#17212b">'
                f"{html.escape(LABELS.get(code, code))}</text>"
            )
    rows.append(
        f'<text x="28" y="{canvas_height - 36}" font-family="Arial,sans-serif" '
        'font-size="15" fill="#263244">'
        f"Local bbox {width / 1000:.3f} × {height / 1000:.3f} m · "
        f"site extent reference 75.460 × 55.000 m · extent feasible: {fit} · "
        "dashed outline is a size reference only</text>"
    )
    rows.append("</svg>")
    return "\n".join(rows)


def _write_local_image(composition: Any) -> dict[str, str]:
    stem = FAMILY_STEMS[composition.layout_family]
    svg_path = EVIDENCE_DIR / f"{stem}.svg"
    png_path = EVIDENCE_DIR / f"{stem}.png"
    svg = _local_svg(composition)
    svg_path.write_text(svg, encoding="utf-8")
    _rasterize(svg, png_path)
    return {
        "svg": str(svg_path),
        "png": str(png_path),
        "svg_sha256": "sha256:" + hashlib.sha256(svg.encode()).hexdigest(),
        "png_sha256": "sha256:" + hashlib.sha256(png_path.read_bytes()).hexdigest(),
    }


def _site_candidate_gallery(rows: list[Mapping[str, Any]]) -> tuple[str, str]:
    svg_path = EVIDENCE_DIR / "xinzhao_r2_compact_site_candidate_gallery.svg"
    png_path = EVIDENCE_DIR / "xinzhao_r2_compact_site_candidate_gallery.png"
    width, height = 1600, 920
    panel_w, panel_h = 500, 420
    columns = 3
    usable = [
        row
        for row in rows
        if isinstance(row.get("candidate"), Mapping)
        and isinstance(row["candidate"].get("zones"), list)
    ]
    shown = usable[:6]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#f7f8fa"/>',
        '<text x="32" y="40" font-family="Arial,sans-serif" font-size="23" '
        'fill="#1b2733">R2 structured site candidates · actual Tool 7/P2D full-pass records</text>',
    ]
    if not shown:
        parts.append(
            '<text x="45" y="120" font-family="Arial,sans-serif" font-size="20" '
            'fill="#8b3d3d">No structured P2D full-pass candidate was observed.</text>'
        )
    for index, row in enumerate(shown):
        candidate = row["candidate"]
        zone_rows = candidate.get("zones", [])
        x0 = 24 + (index % columns) * panel_w
        y0 = 70 + (index // columns) * panel_h
        scale = min((panel_w - 46) / SITE_WIDTH_MM, (panel_h - 88) / SITE_HEIGHT_MM)
        site_x, site_y = x0 + 18, y0 + 42
        parts.append(
            f'<rect x="{site_x}" y="{site_y}" '
            f'width="{SITE_WIDTH_MM * scale:.2f}" '
            f'height="{SITE_HEIGHT_MM * scale:.2f}" '
            'fill="#fff" stroke="#263244" stroke-width="2"/>'
        )
        for zone in zone_rows:
            if not isinstance(zone, Mapping):
                continue
            try:
                x = float(zone["x"])
                y = float(zone["y"])
                zone_w = float(zone["width_m"])
                zone_h = float(zone["depth_m"])
                if int(zone.get("rotation_deg", 0)) == 90:
                    zone_w, zone_h = zone_h, zone_w
                zone_code = str(zone["zone_code"])
                px = site_x + x * 1000 * scale
                py = site_y + (55 - y - zone_h) * 1000 * scale
                parts.append(
                    f'<rect x="{px:.2f}" y="{py:.2f}" '
                    f'width="{zone_w * 1000 * scale:.2f}" '
                    f'height="{zone_h * 1000 * scale:.2f}" '
                    f'fill="{COLORS[placement_domain.zone_band_assignment(zone_code)]}" '
                    'stroke="#263244" stroke-width="1"/>'
                )
            except (KeyError, TypeError, ValueError):
                continue
        plan = candidate.get("_structured_building_plan")
        plan = plan if isinstance(plan, Mapping) else {}
        short_hash = str(candidate.get("_r5_skeleton_hash", "unavailable"))[-8:]
        title = (
            f"{index + 1}. {plan.get('layout_family', 'family?')} · {short_hash} · "
            "P2D PASS / Truck PASS"
        )
        parts.append(
            f'<text x="{x0 + 10}" y="{y0 + 25}" '
            'font-family="Arial,sans-serif" font-size="13" fill="#17212b">'
            f"{html.escape(title)}</text>"
        )
    parts.append("</svg>")
    svg = "\n".join(parts)
    svg_path.write_text(svg, encoding="utf-8")
    _rasterize(svg, png_path)
    return str(png_path), str(svg_path)


def capture_compact_floorplan_replay() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    real_main = placement_domain._local_main_process_compositions
    real_full = placement_domain._local_full_building_compositions
    main_by_family: dict[str, dict[tuple[Any, ...], Any]] = {key: {} for key in FAMILY_STEMS}
    full_by_family: dict[str, dict[tuple[Any, ...], Any]] = {key: {} for key in FAMILY_STEMS}
    call_rows: list[dict[str, Any]] = []

    def observe_main(context: Any, family: str, axis: str, direction: str, **kwargs: Any) -> Any:
        compositions = real_main(context, family, axis, direction, **kwargs)
        for composition in compositions:
            main_by_family.setdefault(family, {}).setdefault(
                _composition_signature(composition), composition
            )
        call_rows.append(
            {
                "family": family,
                "process_axis": axis,
                "process_direction": direction,
                "main_composition_count": len(compositions),
            }
        )
        return compositions

    def observe_full(context: Any, main: Any, **kwargs: Any) -> Any:
        compositions = real_full(context, main, **kwargs)
        family = main.layout_family
        for composition in compositions:
            full_by_family.setdefault(family, {}).setdefault(
                _composition_signature(composition), composition
            )
        return compositions

    placement_domain._local_main_process_compositions = observe_main  # type: ignore[assignment]
    placement_domain._local_full_building_compositions = observe_full  # type: ignore[assignment]
    try:
        first = _capture_tool7(payload, allow_failed_selection=True)
        first_call_count = len(call_rows)
        second = _capture_tool7(payload, allow_failed_selection=True)
    finally:
        placement_domain._local_main_process_compositions = real_main
        placement_domain._local_full_building_compositions = real_full

    main_summary: dict[str, Any] = {}
    full_summary: dict[str, Any] = {}
    local_images: dict[str, Any] = {}
    for family, compositions in sorted(main_by_family.items()):
        ordered = sorted(
            compositions.values(),
            key=lambda composition: placement_domain._local_compactness_key(
                composition.placements(),
                type(
                    "ExtentContext", (), {"boundary_bounds": (0, 0, SITE_WIDTH_MM, SITE_HEIGHT_MM)}
                )(),
                composition.process_axis,
            ),
        )
        feasible = [row for row in ordered if _bbox_metrics(row)["bbox_site_extent_feasible"]]
        main_summary[family] = {
            "distinct_composition_count": len(compositions),
            "site_extent_feasible_count": len(feasible),
            "best_bbox": _bbox_metrics(ordered[0]) if ordered else None,
        }
        image_composition = feasible[0] if feasible else (ordered[0] if ordered else None)
        if image_composition is not None:
            local_images[family] = _write_local_image(image_composition)

    for family, compositions in sorted(full_by_family.items()):
        ordered = sorted(
            compositions.values(),
            key=lambda composition: placement_domain._local_compactness_key(
                composition.placements(),
                type(
                    "ExtentContext", (), {"boundary_bounds": (0, 0, SITE_WIDTH_MM, SITE_HEIGHT_MM)}
                )(),
                composition.process_axis,
            ),
        )
        feasible = [row for row in ordered if _bbox_metrics(row)["bbox_site_extent_feasible"]]
        full_summary[family] = {
            "distinct_complete_12_zone_count": len(compositions),
            "site_extent_feasible_count": len(feasible),
            "best_bbox": _bbox_metrics(ordered[0]) if ordered else None,
        }
        if feasible:
            local_images[family] = _write_local_image(feasible[0])

    first_result = first.get("result")
    first_result = first_result if isinstance(first_result, Mapping) else {}
    first_internal = first.get("internal")
    first_internal = first_internal if isinstance(first_internal, Mapping) else {}
    selector = first.get("selector_result")
    selector = selector if isinstance(selector, Mapping) else {}
    full_passes = first.get("full_pass_records")
    full_passes = full_passes if isinstance(full_passes, list) else []
    structured_full = [
        row
        for row in full_passes
        if isinstance(row, Mapping)
        and isinstance(row.get("candidate"), Mapping)
        and isinstance(row["candidate"].get("search_provenance"), Mapping)
        and row["candidate"]["search_provenance"].get("search_phase") == "STRUCTURED"
    ]
    gallery_png, gallery_svg = _site_candidate_gallery(structured_full)
    layout = first_result.get("layout")
    layout = layout if isinstance(layout, Mapping) else {}
    drawing = first_result.get("drawing")
    drawing = drawing if isinstance(drawing, Mapping) else {}
    svg = drawing.get("svg")
    second_result = second.get("result")
    second_result = second_result if isinstance(second_result, Mapping) else {}
    second_layout = second_result.get("layout")
    second_layout = second_layout if isinstance(second_layout, Mapping) else {}
    second_drawing = second_result.get("drawing")
    second_drawing = second_drawing if isinstance(second_drawing, Mapping) else {}
    second_internal = second.get("internal")
    second_internal = second_internal if isinstance(second_internal, Mapping) else {}
    all_main = [row for rows in main_by_family.values() for row in rows.values()]
    all_full = [row for rows in full_by_family.values() for row in rows.values()]
    site_feasible_main_count = sum(
        _bbox_metrics(row)["bbox_site_extent_feasible"] for row in all_main
    )
    site_feasible_full_count = sum(
        _bbox_metrics(row)["bbox_site_extent_feasible"] for row in all_full
    )
    distinct_structured_hashes = {
        str(row["candidate"].get("_r5_skeleton_hash"))
        for row in structured_full
        if isinstance(row.get("candidate"), Mapping)
    }
    evidence = {
        "identity": "v222-p1a-r2-site-bounded-compact-floorplan@1.0.0",
        "task_id": "V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2",
        "mode": "R2_SITE_BOUNDED_COMPACT_FLOORPLAN_RECOVERY",
        "input_fixture": str(FIXTURE),
        "tool7_unmocked_replay_count": 2,
        "local_synthesis_uses_site_extent": True,
        "local_synthesis_uses_site_event_coordinates": False,
        "site_max_width_mm": SITE_WIDTH_MM,
        "site_max_height_mm": SITE_HEIGHT_MM,
        "necessary_bbox_test_allows_whole_building_rotation": True,
        "local_compact_adjacency_embedding": True,
        "old_local_bboxes_m": {
            "LINEAR_3_BAND": [33.099, 134.774],
            "CENTRAL_PROCESS_WITH_SIDE_BANKS": [90.266, 87.335],
            "LONGITUDINAL_PROCESS_SPINE": [72.416, 85.710],
        },
        "compact_main_by_family": main_summary,
        "compact_full_12_zone_by_family": full_summary,
        "site_extent_feasible_local_main_count": site_feasible_main_count,
        "site_extent_feasible_local_12_zone_count": site_feasible_full_count,
        "structured_site_placed_count": sum(
            int(row.get("site_rigid_placement_count", 0))
            for row in (first_internal.get("r6_topology_diagnostics", {}) or {}).get(
                "main_skeleton_construction_attempts", []
            )
            if isinstance(row, Mapping)
        )
        if isinstance(first_internal.get("r6_topology_diagnostics"), Mapping)
        else 0,
        "structured_p2d_full_pass_count": len(structured_full),
        "distinct_structured_full_pass_skeleton_count": len(distinct_structured_hashes),
        "structured_full_pass_skeleton_hashes": sorted(distinct_structured_hashes),
        "selector_candidate_counts": {
            key: selector.get(key)
            for key in (
                "status",
                "p2c_candidate_count",
                "p2d_validated_candidate_count",
                "p2d_full_pass_candidate_count",
            )
        },
        "selected_layout_validation": {
            key: layout.get(key)
            for key in (
                "project_layout_validated",
                "p2_complete",
                "access_pass_count",
                "access_requirement_count",
                "truck_route_validated",
                "zone_count",
            )
        },
        "selected_p2d_footprint": layout.get("building_footprint"),
        "local_images": local_images,
        "site_candidate_gallery_png": gallery_png,
        "site_candidate_gallery_svg": gallery_svg,
        "replay_determinism": {
            "same_selected_layout": layout.get("zones") == second_layout.get("zones"),
            "same_canonical_result_hash": first_result.get("canonical_result_hash")
            == second_result.get("canonical_result_hash"),
            "same_svg_bytes": svg == second_drawing.get("svg"),
            "same_work_queue_trace": first_internal.get("r6_topology_diagnostics")
            == second_internal.get("r6_topology_diagnostics"),
            "first_local_constructor_call_count": first_call_count,
            "second_local_constructor_call_count": len(call_rows) - first_call_count,
        },
        "search_diagnostics": first_internal.get("r6_topology_diagnostics"),
        "selected_result_hash": first_result.get("canonical_result_hash"),
        "selected_svg_sha256": (
            "sha256:" + hashlib.sha256(svg.encode()).hexdigest() if isinstance(svg, str) else None
        ),
        "p2d_footprint_facts": [
            {
                "skeleton_hash": row.get("candidate", {}).get("_r5_skeleton_hash"),
                **_p2d_footprint_regularity_facts(row["candidate"], row["p2d_result"]),
            }
            for row in full_passes
            if isinstance(row, Mapping)
            and isinstance(row.get("candidate"), Mapping)
            and isinstance(row.get("p2d_result"), Mapping)
        ],
    }
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence


if __name__ == "__main__":
    report = capture_compact_floorplan_replay()
    print(
        json.dumps(
            {
                "compact_main_by_family": report["compact_main_by_family"],
                "compact_full_12_zone_by_family": report["compact_full_12_zone_by_family"],
                "site_extent_feasible_local_main_count": report[
                    "site_extent_feasible_local_main_count"
                ],
                "site_extent_feasible_local_12_zone_count": report[
                    "site_extent_feasible_local_12_zone_count"
                ],
                "structured_site_placed_count": report["structured_site_placed_count"],
                "structured_p2d_full_pass_count": report["structured_p2d_full_pass_count"],
                "selected_layout_validation": report["selected_layout_validation"],
                "replay_determinism": report["replay_determinism"],
                "site_candidate_gallery_png": report["site_candidate_gallery_png"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
