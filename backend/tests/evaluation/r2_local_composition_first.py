"""Run real Xinzhao Tool 7 and capture local-first structured synthesis facts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.domain import placement as placement_domain
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.domain.structural_quality import _outline_class
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

EVIDENCE_PATH = EVIDENCE_DIR / "xinzhao_p1a_r2_footprint_regularity_recovery.json"
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
_ZONE_LABELS = {
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
        '<rect x="0" y="0" width="1200" height="860" fill="#ffffff"/>',
        '<text x="28" y="34" font-family="Arial,sans-serif" font-size="20" '
        'fill="#263244">Local composition · no site coordinates</text>',
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
            'font-family="Arial,sans-serif" font-size="10" fill="#17212b">'
            f"{_ZONE_LABELS.get(code, code)}</text>"
        )
    rows.append(
        f'<text x="28" y="{canvas_height - padding / 4:.1f}" '
        'font-family="Arial,sans-serif" font-size="14" fill="#263244">'
        f"Family: {composition.layout_family} · Local zone union: {composition.outline_class} "
        f"· Planned frame (not footprint): {width_mm / 1000:.3f} m × "
        f"{height_mm / 1000:.3f} m · Unoccupied space remains blank</text>"
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


def _p2d_footprint_regularity_facts(
    candidate: Mapping[str, Any], p2d_result: Mapping[str, Any]
) -> dict[str, Any]:
    zone_rows = candidate.get("zones")
    rectangles: dict[str, PlacedRectangleV1] = {}
    local_outline_error: dict[str, Any] | None = None
    if isinstance(zone_rows, list):
        for row in zone_rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("zone_code"), str):
                rectangles = {}
                local_outline_error = {"code": "ZONE_ROW_SHAPE_UNAVAILABLE"}
                break
            code = str(row["zone_code"])
            try:
                rectangles[code] = PlacedRectangleV1(
                    code,
                    Decimal(str(row.get("x"))),
                    Decimal(str(row.get("y"))),
                    Decimal(str(row.get("width_m"))),
                    Decimal(str(row.get("depth_m"))),
                    row.get("rotation_deg", 0),
                )
            except (LayoutAuthorityError, TypeError, ValueError) as error:
                rectangles = {}
                local_outline_error = {
                    "zone_code": code,
                    "code": getattr(error, "code", type(error).__name__),
                    "details": getattr(error, "details", {}),
                    "geometry_fields": {
                        field: row.get(field)
                        for field in ("x", "y", "width_m", "depth_m", "rotation_deg")
                    },
                }
                break
    elif zone_rows is not None:
        local_outline_error = {"code": "ZONE_ROWS_NOT_A_LIST"}
    local_outline = (
        placement_domain._local_outline_class(rectangles)[0] if rectangles else "UNAVAILABLE"
    )
    footprint = p2d_result.get("building_footprint")
    footprint = footprint if isinstance(footprint, Mapping) else {}
    p2d_outline = _outline_class(p2d_result)[0]
    return {
        "local_zone_union_outline_class": local_outline,
        "local_zone_union_outline_error": local_outline_error,
        "p2d_building_footprint_outline_class": p2d_outline,
        "visual_regularity_pass": p2d_outline in {"RECTANGLE", "SIMPLE_L"},
        "p2d_building_footprint_source": footprint.get("source"),
    }


def capture_local_composition_replay() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    real_main = placement_domain._local_main_process_compositions
    real_full = placement_domain._local_full_building_compositions
    main_rows: list[dict[str, Any]] = []
    full_rows: list[dict[str, Any]] = []
    local_main_examples: dict[str, Any] = {}
    local_full_examples: dict[str, Any] = {}

    def observe_main(context: Any, family: str, axis: str, direction: str, **kwargs: Any) -> Any:
        compositions = real_main(context, family, axis, direction, **kwargs)
        main_rows.append(
            {
                "layout_family": family,
                "process_axis": axis,
                "process_direction": direction,
                "local_main_composition_count": len(compositions),
                "local_zone_union_outline_classes": sorted(
                    {row.outline_class for row in compositions}
                ),
            }
        )
        if compositions:
            local_main_examples.setdefault(family, compositions[0])
        return compositions

    def observe_full(context: Any, main: Any, **kwargs: Any) -> Any:
        compositions = real_full(context, main, **kwargs)
        row = {
            "layout_family": main.layout_family,
            "process_axis": main.process_axis,
            "process_direction": main.process_direction,
            "main_outline_class": main.outline_class,
            "complete_12_zone_count": len(compositions),
            "complete_zone_union_outline_classes": sorted(
                {candidate.outline_class for candidate in compositions}
            ),
        }
        full_rows.append(row)
        if compositions:
            local_full_examples.setdefault(main.layout_family, compositions[0])
        return compositions

    placement_domain._local_main_process_compositions = observe_main  # type: ignore[assignment]
    placement_domain._local_full_building_compositions = observe_full  # type: ignore[assignment]
    try:
        run = _capture_tool7(payload, allow_failed_selection=True)
    finally:
        placement_domain._local_main_process_compositions = real_main
        placement_domain._local_full_building_compositions = real_full

    local_render_examples = dict(local_full_examples)
    for family, composition in local_main_examples.items():
        local_render_examples.setdefault(family, composition)
    local_composition_images = {
        family: _write_local_image(composition)
        for family, composition in sorted(local_render_examples.items())
    }
    local_full_images = {
        family: local_composition_images[family] for family in sorted(local_full_examples)
    }
    local_image_source_by_family = {
        family: ("FULL_12_ZONE" if family in local_full_examples else "MAIN_7_ZONE")
        for family in local_render_examples
    }
    internal = run.get("internal")
    internal = internal if isinstance(internal, Mapping) else {}
    selector_result = run.get("selector_result")
    selector_result = selector_result if isinstance(selector_result, Mapping) else {}
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

    p2d_outline_rows: list[dict[str, Any]] = []
    for row in full_pass_rows:
        if not isinstance(row, Mapping):
            continue
        candidate = row.get("candidate")
        p2d_result = row.get("p2d_result")
        if not isinstance(candidate, Mapping) or not isinstance(p2d_result, Mapping):
            continue
        provenance = candidate.get("search_provenance")
        provenance = provenance if isinstance(provenance, Mapping) else {}
        structured_plan = candidate.get("_structured_building_plan")
        structured_plan = structured_plan if isinstance(structured_plan, Mapping) else {}
        footprint_facts = _p2d_footprint_regularity_facts(candidate, p2d_result)
        p2d_outline_rows.append(
            {
                "skeleton_hash": candidate.get("_r5_skeleton_hash"),
                "search_phase": provenance.get("search_phase"),
                "layout_family": structured_plan.get("layout_family"),
                **footprint_facts,
            }
        )
    structured_visual_skeletons = {
        row["skeleton_hash"]
        for row in p2d_outline_rows
        if row["search_phase"] == "STRUCTURED"
        and row["visual_regularity_pass"]
        and isinstance(row["skeleton_hash"], str)
    }
    raw_local_main_count_by_family = {
        family: sum(
            int(row["local_main_composition_count"])
            for row in main_rows
            if row["layout_family"] == family
        )
        for family in LOCAL_IMAGE_STEMS
    }
    phase_summaries: list[dict[str, Any]] = []
    for lane in internal.get("family_lanes", []):
        if not isinstance(lane, Mapping):
            continue
        for phase in lane.get("phases", []):
            if not isinstance(phase, Mapping):
                continue
            generation = phase.get("main_process_skeleton_generation")
            generation = generation if isinstance(generation, Mapping) else {}
            phase_summaries.append(
                {
                    "topology": lane.get("topology"),
                    "search_phase": phase.get("search_phase"),
                    "node_budget": phase.get("node_budget"),
                    "visited_nodes": phase.get("visited_nodes"),
                    "complete_candidates": phase.get("complete_candidates"),
                    "validated_unique_candidates": phase.get("validated_unique_candidates"),
                    "p2d_rejected_candidate_count": phase.get("p2d_rejected_candidate_count"),
                    "p2d_full_pass_candidate_count": phase.get("p2d_full_pass_candidate_count"),
                    "node_budget_exhausted": phase.get("node_budget_exhausted"),
                    "search_tree_exhausted": phase.get("search_tree_exhausted"),
                    "construction_node_count": generation.get("construction_node_count"),
                    "tail_node_count": generation.get("tail_node_count"),
                    "rejection_reason_counts": generation.get("rejection_reason_counts", {}),
                    "construction_attempts": [
                        {
                            key: attempt.get(key)
                            for key in (
                                "layout_family",
                                "process_axis",
                                "process_direction",
                                "result",
                                "first_failure_stage",
                                "first_failure_interface",
                                "rejection_reason",
                                "skeleton_hash",
                                "local_composition_count",
                                "full_building_composition_count",
                                "site_rigid_placement_count",
                            )
                        }
                        for attempt in generation.get("construction_attempts", [])
                        if isinstance(attempt, Mapping)
                    ],
                }
            )
    drawing = result.get("drawing")
    drawing = drawing if isinstance(drawing, Mapping) else {}
    svg = drawing.get("svg")
    footprint = layout.get("building_footprint")
    evidence = {
        "task_id": "V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2",
        "mode": "R2_P2D_FOOTPRINT_REGULARITY_RECOVERY",
        "input_fixture": str(FIXTURE),
        "tool7_unmocked": True,
        "local_composition_first": True,
        "precomputed_site_envelope_used_as_synthesis_gate": False,
        "zones_only_outline_used_as_pre_p2d_hard_gate": False,
        "planned_composition_envelope_authority": False,
        "p2d_building_footprint_authority": "EXACT_ZONE_RECTANGLES_PLUS_ACCESS_CORRIDOR_ENVELOPES",
        "individual_zone_movement_after_local_composition": False,
        "local_main_composition_attempts": main_rows,
        "raw_local_main_composition_count": sum(raw_local_main_count_by_family.values()),
        "raw_local_main_composition_count_by_family": raw_local_main_count_by_family,
        "local_full_building_attempts": full_rows,
        "local_full_building_images": local_full_images,
        "local_composition_images": local_composition_images,
        "local_composition_image_source_by_family": local_image_source_by_family,
        "local_composition_examples": {
            family: composition.to_dict()
            for family, composition in sorted(local_render_examples.items())
        },
        "local_full_building_composition_exists_by_family": {
            family: family in local_full_examples for family in LOCAL_IMAGE_STEMS
        },
        "structured_p2d_full_pass_candidate_count": len(structured_full_passes),
        "structured_p2d_footprint_regularity_pass_skeleton_count": len(structured_visual_skeletons),
        "structured_p2d_footprint_regularity_pass_layout_family_count": len(
            {
                row["layout_family"]
                for row in p2d_outline_rows
                if row["search_phase"] == "STRUCTURED"
                and row["visual_regularity_pass"]
                and isinstance(row["layout_family"], str)
            }
        ),
        "p2d_footprint_outline_classifications": p2d_outline_rows,
        "local_zone_union_outline_classes": sorted(
            {
                str(row.get("main_outline_class"))
                for row in full_rows
                if isinstance(row.get("main_outline_class"), str)
            }
            | {
                str(outline_class)
                for row in main_rows
                for outline_class in row.get("local_zone_union_outline_classes", [])
                if isinstance(outline_class, str)
            }
            | {
                str(outline_class)
                for row in full_rows
                for outline_class in row.get("complete_zone_union_outline_classes", [])
                if isinstance(outline_class, str)
            }
        ),
        "selector_candidate_counts": {
            key: selector_result.get(key)
            for key in (
                "status",
                "p2c_candidate_count",
                "p2d_validated_candidate_count",
                "p2d_full_pass_candidate_count",
            )
        },
        "search_phase_summaries": phase_summaries,
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
    report = capture_local_composition_replay()
    print(
        json.dumps(
            {
                "raw_local_main_composition_count": report["raw_local_main_composition_count"],
                "raw_local_main_composition_count_by_family": report[
                    "raw_local_main_composition_count_by_family"
                ],
                "local_full_building_composition_exists_by_family": report[
                    "local_full_building_composition_exists_by_family"
                ],
                "structured_p2d_full_pass_candidate_count": report[
                    "structured_p2d_full_pass_candidate_count"
                ],
                "structured_p2d_footprint_regularity_pass_skeleton_count": report[
                    "structured_p2d_footprint_regularity_pass_skeleton_count"
                ],
                "p2d_footprint_outline_classifications": report[
                    "p2d_footprint_outline_classifications"
                ],
                "selector_candidate_counts": report["selector_candidate_counts"],
                "search_phase_summaries": report["search_phase_summaries"],
                "general_fallback_p2d_full_pass_candidate_count": report[
                    "general_fallback_p2d_full_pass_candidate_count"
                ],
                "selected_layout_validation": report["selected_layout_validation"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
