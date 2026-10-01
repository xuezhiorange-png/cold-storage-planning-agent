"""Run real Xinzhao Tool 7 and capture local-first structured synthesis facts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.domain import placement as placement_domain
from cold_storage.modules.layout.domain.structured_building import (
    FINISHED_SIDE_BAND,
    PERSONNEL_EDGE_BAND,
    PROCESS_CORE_BAND,
    RAW_SIDE_BAND,
    SUPPORT_BAND,
    zone_band_assignment,
)
from tests.evaluation.final_selection_authority import _capture_tool7, _rasterize
from tests.evaluation.r13_main_skeleton_truck_preflight import EVIDENCE_DIR, FIXTURE

EVIDENCE_PATH = EVIDENCE_DIR / "xinzhao_p1a_r2_local_composition_first.json"
LOCAL_IMAGE_STEMS = {
    "LINEAR_3_BAND": "xinzhao_local_linear_composition",
    "CENTRAL_PROCESS_WITH_SIDE_BANKS": "xinzhao_local_central_composition",
    "LONGITUDINAL_PROCESS_SPINE": "xinzhao_local_spine_composition",
}
_BAND_COLORS = {
    RAW_SIDE_BAND: "#b7d5eb",
    PROCESS_CORE_BAND: "#8dc5a4",
    FINISHED_SIDE_BAND: "#f1cb86",
    SUPPORT_BAND: "#c5b6df",
    PERSONNEL_EDGE_BAND: "#dfb8bd",
}


def _local_svg(composition: Any) -> str:
    placements = composition.placements()
    left, bottom, right, top = composition.bounds_mm
    padding = 4000
    width_mm, height_mm = right - left, top - bottom
    scale = min(1100 / max(width_mm, 1), 760 / max(height_mm, 1))
    canvas_width, canvas_height = 1200, 860
    x_offset = (canvas_width - width_mm * scale) / 2
    y_offset = (canvas_height - height_mm * scale) / 2
    rows: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" '
        f'height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="28" y="34" font-family="Arial,sans-serif" font-size="20" '
        'fill="#263244">Local building composition · no site coordinates</text>',
        (
            f'<rect x="{x_offset:.3f}" y="{y_offset:.3f}" '
            f'width="{width_mm * scale:.3f}" height="{height_mm * scale:.3f}" '
            'fill="none" stroke="#17212b" stroke-width="3" stroke-dasharray="8 5"/>'
        ),
    ]
    for code, rectangle in sorted(placements.items()):
        x0, y0, x1, y1 = rectangle.bounds_mm
        x = x_offset + (x0 - left) * scale
        y = y_offset + (top - y1) * scale
        rect_width, rect_height = (x1 - x0) * scale, (y1 - y0) * scale
        color = _BAND_COLORS[zone_band_assignment(code)]
        rows.append(
            f'<rect x="{x:.3f}" y="{y:.3f}" width="{rect_width:.3f}" '
            f'height="{rect_height:.3f}" fill="{color}" stroke="#263244" '
            'stroke-width="2"/>'
        )
        rows.append(
            f'<text x="{x + rect_width / 2:.3f}" y="{y + rect_height / 2:.3f}" '
            'text-anchor="middle" dominant-baseline="middle" '
            'font-family="Arial,sans-serif" font-size="12" fill="#17212b">'
            f"{code}</text>"
        )
    rows.append(
        f'<text x="28" y="{canvas_height - padding / 4:.1f}" '
        'font-family="Arial,sans-serif" font-size="14" fill="#263244">'
        f"Family: {composition.layout_family} · Outline: {composition.outline_class} "
        f"· {width_mm / 1000:.3f} m × {height_mm / 1000:.3f} m</text>"
    )
    rows.append("</svg>")
    return "\n".join(rows)


def _write_local_image(composition: Any) -> dict[str, str]:
    stem = LOCAL_IMAGE_STEMS[composition.layout_family]
    svg_path = EVIDENCE_DIR / f"{stem}.svg"
    png_path = EVIDENCE_DIR / f"{stem}.png"
    svg = _local_svg(composition)
    svg_path.write_text(svg, encoding="utf-8")
    _rasterize(svg, png_path)
    return {
        "svg": str(svg_path),
        "png": str(png_path),
        "svg_sha256": "sha256:" + hashlib.sha256(svg.encode("utf-8")).hexdigest(),
        "png_sha256": "sha256:" + hashlib.sha256(png_path.read_bytes()).hexdigest(),
    }


def capture_local_composition_replay() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    real_main = placement_domain._local_main_process_compositions
    real_full = placement_domain._local_full_building_compositions
    main_rows: list[dict[str, Any]] = []
    full_rows: list[dict[str, Any]] = []
    local_full_examples: dict[str, Any] = {}

    def observe_main(context: Any, family: str, axis: str, direction: str, **kwargs: Any) -> Any:
        compositions = real_main(context, family, axis, direction, **kwargs)
        main_rows.append(
            {
                "layout_family": family,
                "process_axis": axis,
                "process_direction": direction,
                "local_main_composition_count": len(compositions),
                "compositions": [row.to_dict() for row in compositions],
            }
        )
        return compositions

    def observe_full(context: Any, main: Any, **kwargs: Any) -> Any:
        compositions = real_full(context, main, **kwargs)
        row = {
            "layout_family": main.layout_family,
            "process_axis": main.process_axis,
            "process_direction": main.process_direction,
            "main_outline_class": main.outline_class,
            "complete_12_zone_count": len(compositions),
            "compositions": [candidate.to_dict() for candidate in compositions],
        }
        full_rows.append(row)
        if compositions:
            local_full_examples.setdefault(main.layout_family, compositions[0])
        return compositions

    placement_domain._local_main_process_compositions = observe_main
    placement_domain._local_full_building_compositions = observe_full
    try:
        run = _capture_tool7(payload, allow_failed_selection=True)
    finally:
        placement_domain._local_main_process_compositions = real_main
        placement_domain._local_full_building_compositions = real_full

    local_images = {
        family: _write_local_image(composition)
        for family, composition in sorted(local_full_examples.items())
    }
    internal = run.get("internal")
    internal = internal if isinstance(internal, Mapping) else {}
    result = run.get("result")
    result = result if isinstance(result, Mapping) else {}
    layout = result.get("layout")
    layout = layout if isinstance(layout, Mapping) else {}
    full_pass_rows = run.get("full_pass_records")
    full_pass_rows = full_pass_rows if isinstance(full_pass_rows, list) else []
    structured_full_passes = [
        row
        for row in full_pass_rows
        if isinstance(row, Mapping)
        and isinstance(row.get("candidate"), Mapping)
        and isinstance(row["candidate"].get("search_provenance"), Mapping)
        and row["candidate"]["search_provenance"].get("search_phase") == "STRUCTURED"
    ]
    fallback_full_passes = [
        row
        for row in full_pass_rows
        if isinstance(row, Mapping)
        and isinstance(row.get("candidate"), Mapping)
        and isinstance(row["candidate"].get("search_provenance"), Mapping)
        and row["candidate"]["search_provenance"].get("search_phase") == "GENERAL_FALLBACK"
    ]
    drawing = result.get("drawing")
    drawing = drawing if isinstance(drawing, Mapping) else {}
    svg = drawing.get("svg")
    footprint = layout.get("building_footprint")
    evidence = {
        "task_id": "V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2",
        "mode": "R2_LOCAL_COMPOSITION_FIRST_RECOVERY",
        "input_fixture": str(FIXTURE),
        "tool7_unmocked": True,
        "local_composition_first": True,
        "precomputed_site_envelope_used_as_synthesis_gate": False,
        "individual_zone_movement_after_local_composition": False,
        "local_main_composition_attempts": main_rows,
        "local_full_building_attempts": full_rows,
        "local_full_building_images": local_images,
        "local_full_building_composition_exists_by_family": {
            family: family in local_full_examples for family in LOCAL_IMAGE_STEMS
        },
        "structured_p2d_full_pass_candidate_count": len(structured_full_passes),
        "general_fallback_p2d_full_pass_candidate_count": len(fallback_full_passes),
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
        "selected_canonical_result_hash": result.get("canonical_result_hash"),
        "selected_layout_svg_sha256": (
            "sha256:" + hashlib.sha256(svg.encode("utf-8")).hexdigest()
            if isinstance(svg, str)
            else None
        ),
        "selected_layout_building_footprint_present": isinstance(footprint, Mapping)
        and bool(footprint),
        "family_lane_count": len(internal.get("family_lanes", []))
        if isinstance(internal.get("family_lanes"), list)
        else 0,
    }
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence


if __name__ == "__main__":
    print(json.dumps(capture_local_composition_replay(), ensure_ascii=False, indent=2))
