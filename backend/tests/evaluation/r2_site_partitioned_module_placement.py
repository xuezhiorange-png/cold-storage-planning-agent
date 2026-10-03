"""Capture real Tool 7 evidence for R2 packaging-anchored module assembly."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application import (
    validated_candidate_selection as selection_domain,
)
from cold_storage.modules.layout.domain import placement as placement_domain
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from tests.evaluation.final_selection_authority import _capture_tool7, _rasterize
from tests.evaluation.r2_local_composition_first import _p2d_footprint_regularity_facts
from tests.evaluation.r12_access_failure_audit import _zone_skeleton_hash
from tests.evaluation.r13_main_skeleton_truck_preflight import EVIDENCE_DIR, FIXTURE

EVIDENCE_PATH = EVIDENCE_DIR / "xinzhao_p1a_r2_dual_external_interface_truck_dock.json"
ANCHOR_IMAGE = EVIDENCE_DIR / "xinzhao_r2_dual_interface_packaging_anchor_candidates.png"
CORE_IMAGE = EVIDENCE_DIR / "xinzhao_r2_dual_interface_packaging_sorting_core_pairs.png"
MAIN_IMAGE = EVIDENCE_DIR / "xinzhao_r2_dual_interface_critical_8zone_candidates.png"
FULL_IMAGE = EVIDENCE_DIR / "xinzhao_r2_dual_interface_12zone_candidates.png"
P2D_IMAGE = EVIDENCE_DIR / "xinzhao_structured_p2d_fullpass_gallery.png"
DOCK_ANCHOR_IMAGE = EVIDENCE_DIR / "xinzhao_shipping_dock_anchor_candidates.png"
DUAL_INTERFACE_IMAGE = EVIDENCE_DIR / "xinzhao_dual_interface_critical_main_candidates.png"
TRUCK_PASS_IMAGE = EVIDENCE_DIR / "xinzhao_truck_pass_main_candidates.png"
DUAL_INTERFACE_EVIDENCE_PATH = (
    EVIDENCE_DIR / "xinzhao_p1a_r2_dual_external_interface_truck_dock.json"
)

MODULE_ZONES = {
    "RAW_MODULE": ("raw_fruit_buffer", "primary_precooling_room"),
    "PROCESS_CORE_MODULE": ("sorting_packaging_room",),
    "FINISHED_MODULE": (
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    ),
    "PACKAGING_MODULE": ("packaging_material_storage",),
    "SECONDARY_SUPPORT_MODULE": ("secondary_fruit_buffer",),
    "FROZEN_SUPPORT_MODULE": ("frozen_fruit_room",),
    "PERSONNEL_MODULE": ("office", "changing_room"),
}
MODULE_COLORS = {
    "RAW_MODULE": "#b8d8ec",
    "PROCESS_CORE_MODULE": "#91c9a6",
    "FINISHED_MODULE": "#f1cb86",
    "PACKAGING_MODULE": "#c9b8df",
    "SECONDARY_SUPPORT_MODULE": "#bca8d8",
    "FROZEN_SUPPORT_MODULE": "#d3c5e6",
    "PERSONNEL_MODULE": "#dfb9bf",
}
ZONE_LABELS = {
    "raw_fruit_buffer": "RAW",
    "primary_precooling_room": "PRIMARY",
    "sorting_packaging_room": "SORTING",
    "secondary_precooling_room": "SECONDARY",
    "coating_room": "COATING",
    "finished_goods_room": "FINISHED",
    "shipping_channel": "SHIPPING",
    "packaging_material_storage": "PACKAGING",
    "secondary_fruit_buffer": "FRUIT BUFFER",
    "frozen_fruit_room": "FROZEN",
    "office": "OFFICE",
    "changing_room": "CHANGING",
}


def _zone_row(rectangle: PlacedRectangleV1) -> dict[str, Any]:
    return {
        "zone_code": rectangle.zone_code,
        "bounds_mm": list(rectangle.bounds_mm),
        "rotation_deg": rectangle.rotation_deg,
    }


def _trace_zone_row(row: Mapping[str, Any]) -> dict[str, Any]:
    x = round(float(row.get("x", 0)) * 1000)
    y = round(float(row.get("y", 0)) * 1000)
    width = round(float(row.get("width_m", 0)) * 1000)
    depth = round(float(row.get("depth_m", 0)) * 1000)
    rotation = int(row.get("rotation_deg", 0))
    if rotation == 90:
        width, depth = depth, width
    return {
        "zone_code": row.get("zone_code"),
        "bounds_mm": [x, y, x + width, y + depth],
        "rotation_deg": rotation,
    }


def _polygon_rows(polygon: Sequence[tuple[int, int]]) -> list[list[int]]:
    return [[int(x), int(y)] for x, y in polygon]


def _polygon_points(points: Sequence[Sequence[int]], transform: Any) -> str:
    return " ".join(
        f"{transform(point[0], point[1])[0]:.2f},{transform(point[0], point[1])[1]:.2f}"
        for point in points
    )


def _module_for_zone(zone_code: str) -> str:
    return next(name for name, members in MODULE_ZONES.items() if zone_code in members)


def _candidate_svg(
    rows: Sequence[Mapping[str, Any]],
    boundary: Sequence[Sequence[int]],
    obstacles: Sequence[Sequence[Sequence[int]]],
    *,
    title: str,
    empty_message: str,
) -> str:
    width, height = 1800, 1040
    columns, panel_width, panel_height = 3, 580, 490
    if boundary:
        min_x = min(point[0] for point in boundary)
        max_x = max(point[0] for point in boundary)
        min_y = min(point[1] for point in boundary)
        max_y = max(point[1] for point in boundary)
    else:
        min_x, min_y, max_x, max_y = 0, 0, 75_460, 55_000
    span_x, span_y = max(1, max_x - min_x), max(1, max_y - min_y)
    scale = min((panel_width - 64) / span_x, (panel_height - 106) / span_y)

    def draw_panel(index: int, candidate: Mapping[str, Any]) -> list[str]:
        x0 = 18 + (index % columns) * panel_width
        y0 = 70 + (index // columns) * panel_height
        site_x = x0 + (panel_width - span_x * scale) / 2
        site_y = y0 + 50 + (panel_height - 100 - span_y * scale) / 2
        packaging_status = (
            "PACKAGING SLOT PASS"
            if candidate.get("packaging_slot_exists") is True
            else "PACKAGING SLOT REJECT"
        )

        def transform(x: int, y: int) -> tuple[float, float]:
            return site_x + (x - min_x) * scale, site_y + (max_y - y) * scale

        parts = [
            f'<text x="{x0 + 8}" y="{y0 + 24}" font-family="Arial,sans-serif" '
            f'font-size="15" fill="#17212b">Candidate {index + 1} · '
            f"{html.escape(str(candidate.get('layout_family', 'family unavailable')))} · "
            f"{html.escape(str(candidate.get('skeleton_hash', 'hash unavailable'))[-8:])} · "
            f"{packaging_status}</text>",
            f'<polygon points="{_polygon_points(boundary, transform)}" fill="#fff" '
            'stroke="#263244" stroke-width="2.2"/>',
        ]
        for obstacle in obstacles:
            parts.append(
                f'<polygon points="{_polygon_points(obstacle, transform)}" '
                'fill="#59636e" stroke="#25303a" stroke-width="1.2"/>'
            )
        entrance = candidate.get("truck_entrance_segment_mm")
        if isinstance(entrance, list) and len(entrance) == 2:
            start = transform(int(entrance[0][0]), int(entrance[0][1]))
            end = transform(int(entrance[1][0]), int(entrance[1][1]))
            parts.append(
                f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" '
                f'x2="{end[0]:.2f}" y2="{end[1]:.2f}" stroke="#e4572e" '
                'stroke-width="5" stroke-linecap="round"/>'
            )
        module_bounds: dict[str, list[tuple[int, int, int, int]]] = {}
        zone_bounds: dict[str, tuple[int, int, int, int]] = {}
        for zone in candidate.get("zones", []):
            if not isinstance(zone, Mapping):
                continue
            bounds = zone.get("bounds_mm")
            if not isinstance(bounds, list) or len(bounds) != 4:
                continue
            left, bottom, right, top = (int(value) for value in bounds)
            zone_bounds[str(zone.get("zone_code", ""))] = (
                left,
                bottom,
                right,
                top,
            )
            module = _module_for_zone(str(zone.get("zone_code", "")))
            module_bounds.setdefault(module, []).append((left, bottom, right, top))
            x, y = transform(left, top)
            rect_width, rect_height = (right - left) * scale, (top - bottom) * scale
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{rect_width:.2f}" '
                f'height="{rect_height:.2f}" fill="{MODULE_COLORS[module]}" '
                'stroke="#263244" stroke-width="1.4"/>'
            )
            if rect_width >= 56 and rect_height >= 19:
                label = ZONE_LABELS.get(str(zone.get("zone_code")), "ZONE")
                parts.append(
                    f'<text x="{x + rect_width / 2:.2f}" y="{y + rect_height / 2:.2f}" '
                    'text-anchor="middle" dominant-baseline="middle" '
                    'font-family="Arial,sans-serif" font-size="9" fill="#17212b">'
                    f"{html.escape(label)}</text>"
                )
        dock_anchor = candidate.get("shipping_dock_anchor")
        if isinstance(dock_anchor, Mapping):
            dock_point = dock_anchor.get("dock_point_mm")
            loading_face = dock_anchor.get("loading_face_segment_mm")
            if isinstance(loading_face, list) and len(loading_face) == 2:
                start = transform(int(loading_face[0][0]), int(loading_face[0][1]))
                end = transform(int(loading_face[1][0]), int(loading_face[1][1]))
                parts.append(
                    f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" '
                    f'x2="{end[0]:.2f}" y2="{end[1]:.2f}" stroke="#125f91" '
                    'stroke-width="4"/>'
                )
            if isinstance(dock_point, list) and len(dock_point) == 2:
                point = transform(int(dock_point[0]), int(dock_point[1]))
                parts.append(
                    f'<circle cx="{point[0]:.2f}" cy="{point[1]:.2f}" r="5" '
                    'fill="#d62828" stroke="#fff" stroke-width="1.5"/>'
                )
                parts.append(
                    f'<text x="{point[0] + 7:.2f}" y="{point[1] - 7:.2f}" '
                    'font-family="Arial,sans-serif" font-size="9" fill="#8e1717">'
                    "AUTHORITATIVE DOCK POINT</text>"
                )
        interface_witness = candidate.get("packaging_interface_witness")
        if isinstance(interface_witness, Mapping):
            package_bounds = zone_bounds.get("packaging_material_storage")
            sorting_bounds = zone_bounds.get("sorting_packaging_room")
            if package_bounds is not None and sorting_bounds is not None:
                package_center = (
                    (package_bounds[0] + package_bounds[2]) / 2,
                    (package_bounds[1] + package_bounds[3]) / 2,
                )
                sorting_center = (
                    (sorting_bounds[0] + sorting_bounds[2]) / 2,
                    (sorting_bounds[1] + sorting_bounds[3]) / 2,
                )
                start = transform(*package_center)
                end = transform(*sorting_center)
                parts.append(
                    f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" '
                    f'x2="{end[0]:.2f}" y2="{end[1]:.2f}" stroke="#a13e32" '
                    'stroke-width="3" marker-end="url(#packagingArrow)"/>'
                )
                mid_x, mid_y = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
                parts.append(
                    f'<text x="{mid_x:.2f}" y="{mid_y - 5:.2f}" '
                    'font-family="Arial,sans-serif" font-size="10" '
                    'text-anchor="middle" fill="#8a3028">PACKAGING → SORTING</text>'
                )
        corridor_bounds = candidate.get("reserved_construction_corridor_bounds_mm")
        if isinstance(corridor_bounds, list) and len(corridor_bounds) == 4:
            left, bottom, right, top = (int(value) for value in corridor_bounds)
            x, y = transform(left, top)
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{(right - left) * scale:.2f}" '
                f'height="{(top - bottom) * scale:.2f}" fill="#e6a04a22" '
                'stroke="#c36e19" stroke-width="2" stroke-dasharray="5 4"/>'
            )
            parts.append(
                f'<text x="{x + 3:.2f}" y="{y + 12:.2f}" '
                'font-family="Arial,sans-serif" font-size="9" fill="#8d4a0c">'
                "RESERVED CONSTRUCTION SPACE · NOT FINAL P2D ROUTE</text>"
            )
        witness = candidate.get("packaging_slot_witness_mm")
        if isinstance(witness, list) and len(witness) == 4:
            left, bottom, right, top = (int(value) for value in witness)
            x, y = transform(left, top)
            rect_width, rect_height = (right - left) * scale, (top - bottom) * scale
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{rect_width:.2f}" '
                f'height="{rect_height:.2f}" fill="#6aaed633" stroke="#176b87" '
                'stroke-width="2.2" stroke-dasharray="8 5"/>'
            )
            parts.append(
                f'<text x="{x + 4:.2f}" y="{y + 14:.2f}" font-family="Arial,sans-serif" '
                'font-size="10" fill="#13556b">PACKAGING SLOT WITNESS · '
                "NOT FINAL SUPPORT PLACEMENT</text>"
            )
        for module, rectangles in sorted(module_bounds.items()):
            left = min(row[0] for row in rectangles)
            bottom = min(row[1] for row in rectangles)
            right = max(row[2] for row in rectangles)
            top = max(row[3] for row in rectangles)
            x, y = transform(left, top)
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{(right - left) * scale:.2f}" '
                f'height="{(top - bottom) * scale:.2f}" fill="none" stroke="#27384a" '
                'stroke-width="1.8" stroke-dasharray="6 4"/>'
            )
            parts.append(
                f'<text x="{x + 3:.2f}" y="{y + 12:.2f}" font-family="Arial,sans-serif" '
                f'font-size="9" fill="#22313f">{html.escape(module)}</text>'
            )
        return parts

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<defs><marker id="packagingArrow" markerWidth="8" markerHeight="8" '
        'refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" '
        'fill="#a13e32"/></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="#f5f7f9"/>',
        f'<text x="26" y="38" font-family="Arial,sans-serif" font-size="24" '
        f'fill="#17212b">{html.escape(title)}</text>',
    ]
    if not rows:
        parts.append(
            f'<text x="36" y="116" font-family="Arial,sans-serif" font-size="20" '
            f'fill="#8a3d3d">{html.escape(empty_message)}</text>'
        )
        # Keep the authoritative site and obstacle context visible even when
        # no candidate reached this stage.
        placeholder = {"layout_family": "NO CANDIDATE", "skeleton_hash": "none", "zones": []}
        parts.extend(draw_panel(0, placeholder))
    else:
        for index, candidate in enumerate(rows[:6]):
            parts.extend(draw_panel(index, candidate))
    parts.append(
        '<text x="28" y="1010" font-family="Arial,sans-serif" font-size="14" '
        'fill="#354454">Site boundary and hard no-build polygons shown. Dashed outlines '
        "group fixed module geometry; no hidden bays or filler space are drawn.</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _write_image(
    path: Path,
    title: str,
    rows: Sequence[Mapping[str, Any]],
    boundary: Any,
    obstacles: Any,
    empty: str,
) -> dict[str, str]:
    svg = _candidate_svg(rows, boundary, obstacles, title=title, empty_message=empty)
    svg_path = path.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    _rasterize(svg, path)
    return {
        "png": str(path),
        "svg": str(svg_path),
        "png_sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "svg_sha256": "sha256:" + hashlib.sha256(svg.encode("utf-8")).hexdigest(),
    }


def _capture_one(payload: Mapping[str, Any]) -> dict[str, Any]:
    captured_main: list[dict[str, Any]] = []
    captured_full: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    p2d_route_rows: list[dict[str, Any]] = []
    context_geometry: dict[str, Any] = {}
    real_direct = placement_domain._direct_structured_candidates
    real_main = placement_domain._module_main_site_assemblies
    real_full = placement_domain._module_full_site_assemblies
    real_route = selection_domain.route_site_placement

    def observe_p2d_route(*args: Any, **kwargs: Any) -> Any:
        candidate = args[3] if len(args) > 3 else kwargs.get("placement")
        routed = real_route(*args, **kwargs)
        candidate_body = (
            candidate.to_dict() if callable(getattr(candidate, "to_dict", None)) else {}
        )
        routed_body = routed.to_dict()
        zone_rows = candidate_body.get("zones", [])
        p2d_route_rows.append(
            {
                "candidate_index": len(p2d_route_rows) + 1,
                "canonical_candidate_hash": candidate_body.get("canonical_candidate_hash"),
                "main_skeleton_hash": (
                    _zone_skeleton_hash(zone_rows)
                    if isinstance(zone_rows, list)
                    and set(placement_domain.MAIN_PROCESS_SKELETON_ZONE_CODES).issubset(
                        {str(row.get("zone_code")) for row in zone_rows if isinstance(row, Mapping)}
                    )
                    else "UNAVAILABLE_FROM_P2C_BODY"
                ),
                "search_phase": (
                    candidate_body.get("search_provenance", {}).get("search_phase")
                    if isinstance(candidate_body.get("search_provenance"), Mapping)
                    else None
                ),
                "zones": [_trace_zone_row(row) for row in zone_rows if isinstance(row, Mapping)]
                if isinstance(zone_rows, list)
                else [],
                "project_layout_validated": routed_body.get("project_layout_validated"),
                "p2_complete": routed_body.get("p2_complete"),
                "access_pass_count": routed_body.get("access_pass_count"),
                "access_requirement_count": routed_body.get("access_requirement_count"),
                "truck_route_validated": routed_body.get("truck_route_validated"),
                "truck_route_codes": list(routed_body.get("truck_route_codes", [])),
                "warnings": list(routed_body.get("warnings", [])),
                "access_results": [
                    {
                        "requirement_identity": row.get("requirement_identity"),
                        "from_ref": row.get("from_ref"),
                        "to_ref": row.get("to_ref"),
                        "flow_kind": row.get("flow_kind"),
                        "status": row.get("status"),
                        "codes": list(row.get("codes", [])),
                        "route_shape": row.get("route_shape"),
                        "turn_count": row.get("turn_count"),
                        "route_length_m": row.get("route_length_m"),
                    }
                    for row in routed_body.get("access_results", [])
                    if isinstance(row, Mapping)
                ],
                "personnel_truck_evaluation": routed_body.get("personnel_truck_evaluation"),
                "building_footprint_source": (
                    routed_body.get("building_footprint", {}).get("source")
                    if isinstance(routed_body.get("building_footprint"), Mapping)
                    else None
                ),
            }
        )
        return routed

    def main_process_only(
        candidate: Mapping[str, PlacedRectangleV1],
    ) -> dict[str, PlacedRectangleV1]:
        return {
            code: candidate[code]
            for code in placement_domain.MAIN_PROCESS_SKELETON_ZONE_CODES
            if code in candidate
        }

    def observe_main(
        context: Any,
        main_compositions: Any,
        layout_family: str,
        process_axis: str,
        process_direction: str,
        bays: Any,
        **kwargs: Any,
    ) -> Any:
        for candidate in real_main(
            context,
            main_compositions,
            layout_family,
            process_axis,
            process_direction,
            bays,
            **kwargs,
        ):
            if candidate is not None:
                main_geometry = main_process_only(candidate)
                try:
                    seed = placement_domain._canonical_site_main_skeleton(
                        context,
                        main_geometry,
                        layout_family=layout_family,
                        process_axis=process_axis,
                        process_direction=process_direction,
                        generation_pattern="R2_SITE_PARTITIONED_EVIDENCE_CAPTURE",
                    )
                    skeleton_hash = seed.main_process_skeleton_hash
                except LayoutAuthorityError:
                    skeleton_hash = "UNAVAILABLE"
                geometry_signature = repr(placement_domain._module_signature(main_geometry))
                package = candidate.get("packaging_material_storage")
                package_bounds = list(package.bounds_mm) if package is not None else None
                sorting = candidate.get("sorting_packaging_room")
                sorting_bounds = list(sorting.bounds_mm) if sorting is not None else None
                stats = kwargs.get("stats")
                trace_rows = (
                    getattr(stats, "site_module_assembly_trace", None) or ()
                    if stats is not None
                    else ()
                )
                assembly_trace = next(
                    (
                        row
                        for row in reversed(trace_rows)
                        if row.get("stage")
                        in {
                            "S1_DOCK_CAPABLE_MAIN_PROCESS",
                            "S1_PACKAGING_RESERVED_MAIN_ASSEMBLY",
                        }
                        and row.get("sorting_root_bounds_mm") == sorting_bounds
                        and isinstance(row.get("packaging_anchor"), Mapping)
                        and isinstance(row["packaging_anchor"].get("rectangle"), Mapping)
                        and _trace_zone_row(
                            {
                                "zone_code": "packaging_material_storage",
                                **row["packaging_anchor"]["rectangle"],
                            }
                        )["bounds_mm"]
                        == package_bounds
                    ),
                    {},
                )
                reserved_corridor = assembly_trace.get("reserved_construction_space")
                reserved_corridor_bounds = (
                    _trace_zone_row(
                        {
                            "zone_code": "__reserved_packaging_corridor__",
                            **reserved_corridor,
                        }
                    )["bounds_mm"]
                    if isinstance(reserved_corridor, Mapping)
                    else None
                )
                captured_main.append(
                    {
                        "layout_family": layout_family,
                        "process_axis": process_axis,
                        "process_direction": process_direction,
                        "skeleton_hash": skeleton_hash,
                        "geometry_signature": geometry_signature,
                        "packaging_slot_exists": package is not None,
                        "packaging_anchor_bounds_mm": package_bounds,
                        "packaging_interface_witness": assembly_trace.get(
                            "packaging_sorting_alignment_witness"
                        ),
                        "reserved_construction_corridor_bounds_mm": reserved_corridor_bounds,
                        "shipping_dock_anchor": assembly_trace.get("shipping_dock_anchor"),
                        "shipping_exact_dock_anchor_match": assembly_trace.get(
                            "shipping_exact_dock_anchor_match"
                        ),
                        "finished_site_construction": assembly_trace.get(
                            "finished_site_construction"
                        ),
                        "shipping_dock_anchor_exact_match": assembly_trace.get(
                            "shipping_exact_dock_anchor_match"
                        ),
                        "zones": [
                            _zone_row(rectangle) for _code, rectangle in sorted(candidate.items())
                        ],
                    }
                )
            yield candidate

    def observe_full(context: Any, main: Any, bays: Any, *, limit: int, stats: Any = None) -> Any:
        main_signature = repr(placement_domain._module_signature(main_process_only(main)))
        main_hash = next(
            (
                row["skeleton_hash"]
                for row in reversed(captured_main)
                if row["geometry_signature"] == main_signature
            ),
            "UNAVAILABLE",
        )
        for candidate in real_full(context, main, bays, limit=limit, stats=stats):
            captured_full.append(
                {
                    "main_geometry_signature": main_signature,
                    "skeleton_hash": main_hash,
                    "result": "SITE_VALID_12_ZONE"
                    if candidate is not None
                    else "NO_SITE_VALID_12_ZONE",
                    "zones": [
                        _zone_row(rectangle) for _code, rectangle in sorted(candidate.items())
                    ]
                    if candidate is not None
                    else [],
                }
            )
            yield candidate

    def observe_direct(context: Any, stats: Any) -> Any:
        context_geometry.setdefault("boundary_mm", _polygon_rows(context.boundary))
        context_geometry.setdefault(
            "obstacles_mm", [_polygon_rows(row) for row in context.obstacles]
        )
        iterator = real_direct(context, stats)
        try:
            yield from iterator
        finally:
            snapshots.append(
                {
                    "topology": context.structural_topology,
                    "truck_entrance_segment_mm": [
                        list(point) for point in placement_domain._truck_segment(context.site_body)
                    ],
                    "layout_family": getattr(
                        context.structured_building_plan, "layout_family", "UNKNOWN"
                    ),
                    "site_bays": [bay.to_dict() for bay in stats.site_bay_rows or ()],
                    "module_variant_counts": dict(stats.site_module_variant_counts or {}),
                    "packaging_anchors": [
                        row.to_dict() for row in stats.site_packaging_anchors or ()
                    ],
                    "packaging_construction_anchors": [
                        row.to_dict() for row in stats.site_packaging_construction_anchors or ()
                    ],
                    "packaging_anchor_sorting_rotation_attempts_by_group": {
                        key: sorted(values)
                        for key, values in (
                            stats.packaging_anchor_sorting_rotation_attempts_by_group or {}
                        ).items()
                    },
                    "packaging_anchor_sorting_alignment_proofs_by_group": {
                        key: dict(values)
                        for key, values in (
                            stats.packaging_anchor_sorting_alignment_proofs_by_group or {}
                        ).items()
                    },
                    "sorting_rotation_site_attempt_counts": dict(
                        stats.sorting_rotation_site_attempt_counts or {}
                    ),
                    "site_main_assembly_counts_by_family": {
                        family: dict(counts)
                        for family, counts in (
                            stats.site_main_assembly_counts_by_family or {}
                        ).items()
                    },
                    "shipping_dock_anchors": [
                        row.to_dict() for row in stats.site_shipping_dock_anchors or ()
                    ],
                    "shipping_dock_construction_anchors": [
                        row.to_dict() for row in stats.site_shipping_dock_construction_anchors or ()
                    ],
                    "finished_forward_site_attempt_count": (
                        stats.finished_forward_site_attempt_count
                    ),
                    "finished_dock_backsolve_attempt_count": (
                        stats.finished_dock_backsolve_attempt_count
                    ),
                    "main_skeleton_truck_preflight_rows": [
                        dict(row.get("main_skeleton_truck_preflight"))
                        for row in (context.global_main_process_geometry_registry or {}).values()
                        if isinstance(row, Mapping)
                        and isinstance(row.get("main_skeleton_truck_preflight"), Mapping)
                    ],
                    "truck_maneuver_construction_witness_by_skeleton_hash": dict(
                        stats.truck_maneuver_construction_witness_by_skeleton_hash or {}
                    ),
                    "site_main_source_pair_rows": list(stats.site_main_source_pair_rows or ()),
                    "early_formal_packaging_preflight_mismatch_count": (
                        stats.early_formal_packaging_preflight_mismatch_count
                    ),
                    "family_geometry_collapse_count": stats.family_geometry_collapse_count,
                    "site_module_assembly_trace": list(stats.site_module_assembly_trace or ()),
                    "construction_attempts": list(stats.skeleton_construction_attempts or ()),
                }
            )

    placement_domain._direct_structured_candidates = observe_direct
    placement_domain._module_main_site_assemblies = observe_main
    placement_domain._module_full_site_assemblies = observe_full
    selection_domain.route_site_placement = observe_p2d_route
    try:
        tool7 = _capture_tool7(payload, allow_failed_selection=True)
    finally:
        placement_domain._direct_structured_candidates = real_direct
        placement_domain._module_main_site_assemblies = real_main
        placement_domain._module_full_site_assemblies = real_full
        selection_domain.route_site_placement = real_route

    result = tool7.get("result")
    result = result if isinstance(result, Mapping) else {}
    internal = tool7.get("internal")
    internal = internal if isinstance(internal, Mapping) else {}
    diagnostics = internal.get("r6_topology_diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    layout = result.get("layout")
    layout = layout if isinstance(layout, Mapping) else {}
    drawing = result.get("drawing")
    drawing = drawing if isinstance(drawing, Mapping) else {}
    full_pass_records = tool7.get("full_pass_records")
    full_pass_records = full_pass_records if isinstance(full_pass_records, list) else []
    structured_full_passes = [
        row
        for row in full_pass_records
        if isinstance(row, Mapping)
        and isinstance(row.get("candidate"), Mapping)
        and isinstance(row["candidate"].get("search_provenance"), Mapping)
        and row["candidate"]["search_provenance"].get("search_phase") == "STRUCTURED"
    ]
    structured_full_pass_candidates: list[dict[str, Any]] = []
    for row in structured_full_passes:
        candidate = row.get("candidate")
        if not isinstance(candidate, Mapping):
            continue
        zone_rows = candidate.get("zones")
        rendered_zones: list[dict[str, Any]] = []
        if isinstance(zone_rows, list):
            for zone in zone_rows:
                if not isinstance(zone, Mapping):
                    continue
                left = round(float(zone.get("x", 0)) * 1000)
                bottom = round(float(zone.get("y", 0)) * 1000)
                width = round(float(zone.get("width_m", 0)) * 1000)
                depth = round(float(zone.get("depth_m", 0)) * 1000)
                if int(zone.get("rotation_deg", 0)) == 90:
                    width, depth = depth, width
                rendered_zones.append(
                    {
                        "zone_code": zone.get("zone_code"),
                        "bounds_mm": [left, bottom, left + width, bottom + depth],
                    }
                )
        plan = candidate.get("_structured_building_plan")
        plan = plan if isinstance(plan, Mapping) else {}
        structured_full_pass_candidates.append(
            {
                "layout_family": plan.get("layout_family", "STRUCTURED"),
                "skeleton_hash": candidate.get("_r5_skeleton_hash", "UNAVAILABLE"),
                "zones": rendered_zones,
            }
        )
    return {
        "tool7": tool7,
        "context_geometry": context_geometry,
        "main_candidates": captured_main,
        "full_attempts": captured_full,
        "snapshots": snapshots,
        "diagnostics": diagnostics,
        "selected": {
            "skeleton_hash": layout.get("selected_main_process_skeleton_hash")
            or _zone_skeleton_hash(layout.get("zones", [])),
            "validated": layout.get("project_layout_validated"),
            "p2_complete": layout.get("p2_complete"),
            "access_pass_count": layout.get("access_pass_count"),
            "access_requirement_count": layout.get("access_requirement_count"),
            "truck_route_validated": layout.get("truck_route_validated"),
            "zone_count": result.get("zone_count"),
            "canonical_result_hash": result.get("canonical_result_hash"),
            "svg_sha256": result.get("svg_sha256"),
            "svg_bytes": drawing.get("svg"),
        },
        "structured_full_passes": len(structured_full_passes),
        "structured_full_pass_candidates": structured_full_pass_candidates,
        "p2d_route_rows": p2d_route_rows,
    }


def capture_site_partitioned_replay() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    replays = [_capture_one(payload), _capture_one(payload)]
    first, second = replays
    boundary = first["context_geometry"].get("boundary_mm", [])
    obstacles = first["context_geometry"].get("obstacles_mm", [])

    def dedupe(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = json.dumps(row.get("zones", []), sort_keys=True, separators=(",", ":"))
            unique.setdefault(key, dict(row))
        return list(unique.values())

    main_candidates = dedupe(first["main_candidates"])
    full_candidates = dedupe(
        [row for row in first["full_attempts"] if row.get("result") == "SITE_VALID_12_ZONE"]
    )
    structured_full_pass_count = first["structured_full_passes"]
    structured_full_pass_candidates = first["structured_full_pass_candidates"]
    for candidate_record, source_record in zip(
        structured_full_pass_candidates,
        (
            row
            for row in first["tool7"]["full_pass_records"]
            if isinstance(row, Mapping)
            and isinstance(row.get("candidate"), Mapping)
            and isinstance(row["candidate"].get("search_provenance"), Mapping)
            and row["candidate"]["search_provenance"].get("search_phase") == "STRUCTURED"
        ),
        strict=False,
    ):
        p2d_result = source_record.get("p2d_result")
        if isinstance(p2d_result, Mapping):
            candidate_record.update(
                _p2d_footprint_regularity_facts(source_record["candidate"], p2d_result)
            )
    regular_full_passes = [
        row
        for row in structured_full_pass_candidates
        if row.get("p2d_building_footprint_outline_class") in {"RECTANGLE", "SIMPLE_L"}
    ]
    bay_rows: list[dict[str, Any]] = next(
        (snapshot["site_bays"] for snapshot in first["snapshots"] if snapshot["site_bays"]),
        [],
    )
    variant_counts: dict[str, Any] = {}
    runtime_s1_counts_by_family: dict[str, dict[str, int]] = {}
    source_pair_rows: list[dict[str, Any]] = []
    s1_geometry_attempts: list[dict[str, Any]] = []
    all_packaging_anchors: dict[str, dict[str, Any]] = {}
    construction_anchors: dict[str, dict[str, Any]] = {}
    all_shipping_dock_anchors: dict[str, dict[str, Any]] = {}
    construction_dock_anchors: dict[str, dict[str, Any]] = {}
    captured_truck_preflight_rows: dict[str, dict[str, Any]] = {}
    captured_truck_witnesses: dict[str, dict[str, Any]] = {}
    dual_pair_keys: set[tuple[str, str]] = set()
    dual_pair_necessary_keys: set[tuple[str, str]] = set()
    sorting_roots_by_external_pair: dict[str, dict[str, str]] = {}
    truck_entrance_segment: list[list[int]] = []
    anchor_rotation_attempts: dict[str, set[str]] = {}
    anchor_rotation_proofs: dict[str, dict[str, str]] = {}
    core_pair_rows_by_geometry: dict[str, dict[str, Any]] = {}
    sorting_attempts_by_family: dict[str, dict[str, int]] = {}
    early_formal_mismatch_count = 0
    for snapshot in first["snapshots"]:
        for name, value in snapshot["module_variant_counts"].items():
            if isinstance(value, Mapping):
                variant_counts[name] = dict(value)
            elif isinstance(value, (int, float)):
                variant_counts[name] = max(int(variant_counts.get(name, 0)), int(value))
            else:
                variant_counts[name] = value
        for anchor in snapshot["packaging_anchors"]:
            all_packaging_anchors.setdefault(str(anchor["anchor_id"]), dict(anchor))
        for anchor in snapshot["packaging_construction_anchors"]:
            construction_anchors.setdefault(str(anchor["anchor_id"]), dict(anchor))
        for anchor in snapshot.get("shipping_dock_anchors", []):
            key = json.dumps(anchor, sort_keys=True, separators=(",", ":"), default=str)
            all_shipping_dock_anchors.setdefault(key, dict(anchor))
        for anchor in snapshot.get("shipping_dock_construction_anchors", []):
            key = json.dumps(anchor, sort_keys=True, separators=(",", ":"), default=str)
            construction_dock_anchors.setdefault(key, dict(anchor))
        for preflight in snapshot.get("main_skeleton_truck_preflight_rows", []):
            if isinstance(preflight, Mapping):
                skeleton_hash = str(preflight.get("main_skeleton_hash", "UNAVAILABLE"))
                captured_truck_preflight_rows.setdefault(skeleton_hash, dict(preflight))
        for skeleton_hash, witness in snapshot.get(
            "truck_maneuver_construction_witness_by_skeleton_hash", {}
        ).items():
            if isinstance(witness, Mapping):
                captured_truck_witnesses.setdefault(str(skeleton_hash), dict(witness))
        if not truck_entrance_segment and snapshot.get("truck_entrance_segment_mm"):
            truck_entrance_segment = snapshot["truck_entrance_segment_mm"]
        for anchor_id, rotations in snapshot[
            "packaging_anchor_sorting_rotation_attempts_by_group"
        ].items():
            anchor_rotation_attempts.setdefault(anchor_id, set()).update(
                str(rotation) for rotation in rotations
            )
        for anchor_id, proofs in snapshot[
            "packaging_anchor_sorting_alignment_proofs_by_group"
        ].items():
            anchor_rotation_proofs.setdefault(anchor_id, {}).update(
                {str(rotation): str(reason) for rotation, reason in proofs.items()}
            )
        family = str(snapshot["layout_family"])
        counts = snapshot["sorting_rotation_site_attempt_counts"]
        if isinstance(counts, Mapping):
            aggregate = sorting_attempts_by_family.setdefault(family, {"0": 0, "90": 0})
            for rotation, count in counts.items():
                aggregate[str(rotation)] = max(aggregate.get(str(rotation), 0), int(count))
        for family, counts in snapshot["site_main_assembly_counts_by_family"].items():
            aggregate = runtime_s1_counts_by_family.setdefault(family, {})
            for name, value in counts.items():
                aggregate[name] = max(aggregate.get(name, 0), int(value))
        source_pair_rows.extend(snapshot["site_main_source_pair_rows"])
        for trace_row in snapshot["site_module_assembly_trace"]:
            if trace_row.get("stage") == "S0_DUAL_EXTERNAL_INTERFACE_SORTING_ROOTS":
                package_anchor = trace_row.get("packaging_anchor")
                dock_anchor = trace_row.get("shipping_dock_anchor")
                if isinstance(package_anchor, Mapping) and isinstance(dock_anchor, Mapping):
                    dock_key = json.dumps(
                        {
                            "dock_point_mm": dock_anchor.get("dock_point_mm"),
                            "shipping_rectangle": dock_anchor.get("shipping_rectangle"),
                            "shipping_rotation_deg": dock_anchor.get("shipping_rotation_deg"),
                            "loading_face_side": dock_anchor.get("loading_face_side"),
                            "source_template_identity": dock_anchor.get("source_template_identity"),
                            "source_template_rotation_deg": dock_anchor.get(
                                "source_template_rotation_deg"
                            ),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    )
                    pair_key = (str(package_anchor.get("anchor_id")), dock_key)
                    if trace_row.get("sorting_roots"):
                        dual_pair_necessary_keys.add(pair_key)
                    dual_pair_keys.add(pair_key)
                    root_signature = json.dumps(
                        [
                            {
                                "bounds_mm": row.get("bounds_mm"),
                                "rotation_deg": row.get("rotation_deg"),
                            }
                            for row in trace_row.get("sorting_roots", [])
                            if isinstance(row, Mapping)
                        ],
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    package_scope = f"{trace_row.get('layout_family')}:{pair_key[0]}"
                    sorting_roots_by_external_pair.setdefault(package_scope, {})[dock_key] = (
                        root_signature
                    )
            if trace_row.get("stage") == "S0_PACKAGING_ANCHOR_DRIVEN_SORTING_ROOTS":
                anchor = trace_row.get("packaging_anchor")
                anchor_rect = anchor.get("rectangle") if isinstance(anchor, Mapping) else None
                if isinstance(anchor, Mapping) and isinstance(anchor_rect, Mapping):
                    package_zone = _trace_zone_row(
                        {
                            "zone_code": "packaging_material_storage",
                            **anchor_rect,
                        }
                    )
                    for root in trace_row.get("sorting_roots", []):
                        if not isinstance(root, Mapping):
                            continue
                        sorting_zone = {
                            "zone_code": "sorting_packaging_room",
                            "bounds_mm": root.get("bounds_mm"),
                            "rotation_deg": root.get("rotation_deg", 0),
                        }
                        zones = [package_zone, sorting_zone]
                        geometry_key = json.dumps(zones, sort_keys=True, separators=(",", ":"))
                        core_pair_rows_by_geometry.setdefault(
                            geometry_key,
                            {
                                "layout_family": trace_row.get("layout_family"),
                                "skeleton_hash": str(anchor.get("anchor_id", "")),
                                "packaging_slot_exists": True,
                                "packaging_interface_witness": root.get("alignment_witness"),
                                "reserved_construction_corridor_bounds_mm": root.get(
                                    "reserved_corridor_bounds_mm"
                                ),
                                "zones": zones,
                            },
                        )
            if trace_row.get("stage") != "S1_PACKAGING_RESERVED_MAIN_PREFLIGHT" or not isinstance(
                trace_row.get("zones"), list
            ):
                continue
            attempt = dict(trace_row)
            attempt["main_process_skeleton_hash"] = _zone_skeleton_hash(trace_row["zones"])
            proof = attempt.get("formal_preflight")
            legal_slot = proof.get("legal_slot_exists") if isinstance(proof, Mapping) else None
            attempt["packaging_slot_exists"] = legal_slot
            attempt["result"] = (
                "PACKAGING_RESERVED_MAIN_ADMITTED"
                if legal_slot is True
                else "PACKAGING_SLOT_REJECTED"
                if legal_slot is False
                else "PACKAGING_PREFLIGHT_UNAVAILABLE"
            )
            s1_geometry_attempts.append(attempt)
        early_formal_mismatch_count += int(
            snapshot["early_formal_packaging_preflight_mismatch_count"]
        )
    unique_source_rows: dict[str, dict[str, Any]] = {}
    for row in source_pair_rows:
        key = json.dumps(
            {
                field: row.get(field)
                for field in (
                    "layout_family",
                    "process_axis",
                    "process_direction",
                    "source_pair_index",
                    "packaging_anchor_id",
                )
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        unique_source_rows.setdefault(key, row)
    source_pair_rows = list(unique_source_rows.values())
    unique_s1_geometries: dict[tuple[str, str], dict[str, Any]] = {}
    for row in s1_geometry_attempts:
        key = (str(row.get("layout_family")), str(row.get("main_process_skeleton_hash")))
        unique_s1_geometries.setdefault(key, row)
    s1_counts_by_family: dict[str, dict[str, int]] = {}
    for row in unique_s1_geometries.values():
        family = str(row.get("layout_family"))
        counts = s1_counts_by_family.setdefault(
            family,
            {
                "raw_site_valid_main_count": 0,
                "packaging_slot_rejected_main_count": 0,
                "packaging_slot_unavailable_main_count": 0,
                "tail_capable_main_count": 0,
            },
        )
        counts["raw_site_valid_main_count"] += 1
        if row.get("result") == "PACKAGING_SLOT_REJECTED":
            counts["packaging_slot_rejected_main_count"] += 1
        elif row.get("result") == "PACKAGING_RESERVED_MAIN_ADMITTED":
            counts["tail_capable_main_count"] += 1
        else:
            counts["packaging_slot_unavailable_main_count"] += 1
    raw_site_main_candidates = [
        {
            "layout_family": family,
            "skeleton_hash": skeleton_hash,
            "packaging_slot_exists": row.get("packaging_slot_exists"),
            "packaging_anchor_bounds_mm": row.get("packaging_anchor_bounds_mm"),
            "zones": [
                _trace_zone_row(zone) for zone in row.get("zones", []) if isinstance(zone, Mapping)
            ],
        }
        for (family, skeleton_hash), row in sorted(unique_s1_geometries.items())
    ]
    core_pair_candidates = list(core_pair_rows_by_geometry.values())
    anchor_group_coverage = {
        anchor_id: {
            "sorting_rotations_attempted": sorted(anchor_rotation_attempts.get(anchor_id, set())),
            "sorting_rotation_impossibility_proofs": dict(
                sorted(anchor_rotation_proofs.get(anchor_id, {}).items())
            ),
        }
        for anchor_id in sorted(construction_anchors)
    }
    anchor_groups_with_rot0 = sum(
        "0" in row["sorting_rotations_attempted"]
        or "0" in row["sorting_rotation_impossibility_proofs"]
        for row in anchor_group_coverage.values()
    )
    anchor_groups_with_rot90 = sum(
        "90" in row["sorting_rotations_attempted"]
        or "90" in row["sorting_rotation_impossibility_proofs"]
        for row in anchor_group_coverage.values()
    )
    sorting_geometries_by_anchor = {
        anchor_id: {
            json.dumps(root.get("bounds_mm"), separators=(",", ":"))
            + f"@{root.get('rotation_deg', 0)}"
            for snapshot in first["snapshots"]
            for trace in snapshot["site_module_assembly_trace"]
            if trace.get("stage") == "S0_PACKAGING_ANCHOR_DRIVEN_SORTING_ROOTS"
            and isinstance(trace.get("packaging_anchor"), Mapping)
            and trace["packaging_anchor"].get("anchor_id") == anchor_id
            for root in trace.get("sorting_roots", [])
            if isinstance(root, Mapping)
        }
        for anchor_id in construction_anchors
    }
    packaging_anchor_influences_sorting_roots = (
        len({tuple(sorted(roots)) for roots in sorting_geometries_by_anchor.values()}) > 1
    )
    source_pair_attempt_rows_by_family: dict[str, int] = {}
    source_pair_distinct_inputs_by_family: dict[str, set[str]] = {}
    source_pair_site_valid_by_family: dict[str, set[str]] = {}
    for row in source_pair_rows:
        family = str(row.get("layout_family", "UNKNOWN"))
        source_pair_attempt_rows_by_family[family] = (
            source_pair_attempt_rows_by_family.get(family, 0) + 1
        )
        source_pair_identity = str(
            row.get(
                "source_pair_geometry_signature",
                f"{row.get('process_axis')}:{row.get('process_direction')}:{row.get('source_pair_index')}",
            )
        )
        source_pair_distinct_inputs_by_family.setdefault(family, set()).add(source_pair_identity)
        if int(row.get("site_valid_critical_geometry_count", 0)) > 0:
            source_pair_site_valid_by_family.setdefault(family, set()).add(source_pair_identity)
    source_pair_attempt_rows_by_family = dict(sorted(source_pair_attempt_rows_by_family.items()))
    source_pair_distinct_inputs_count_by_family = {
        family: len(rows) for family, rows in sorted(source_pair_distinct_inputs_by_family.items())
    }
    source_pair_site_valid_count_by_family = {
        family: len(rows) for family, rows in sorted(source_pair_site_valid_by_family.items())
    }
    main_geometry_keys_by_family: dict[str, set[str]] = {}
    for row in first["main_candidates"]:
        family = str(row.get("layout_family", "UNKNOWN"))
        geometry_key = json.dumps(row.get("zones", []), sort_keys=True, separators=(",", ":"))
        main_geometry_keys_by_family.setdefault(family, set()).add(geometry_key)
    packaging_reserved_by_family = {
        family: len(main_geometry_keys_by_family.get(family, set()))
        for family in (
            "LINEAR_3_BAND",
            "CENTRAL_PROCESS_WITH_SIDE_BANKS",
            "LONGITUDINAL_PROCESS_SPINE",
        )
    }
    critical_8_zone_geometry_count = len(main_candidates)
    distinct_structured_full_pass_hashes = {
        str(row.get("skeleton_hash"))
        for row in structured_full_pass_candidates
        if row.get("skeleton_hash") not in {None, "UNAVAILABLE"}
    }
    first_diag = first["diagnostics"]
    second_diag = second["diagnostics"]
    preflight_by_hash = dict(captured_truck_preflight_rows)
    for row in first_diag.get("main_skeleton_truck_preflight_trace", []):
        if isinstance(row, Mapping):
            preflight_by_hash.setdefault(
                str(row.get("main_skeleton_hash", "UNAVAILABLE")), dict(row)
            )
    preflight_rows = [preflight_by_hash[key] for key in sorted(preflight_by_hash)]
    dock_capable_main_candidates = [
        row
        for row in main_candidates
        if row.get("shipping_dock_anchor")
        and row.get("shipping_exact_dock_anchor_match") is True
        and row.get("skeleton_hash") not in {None, "UNAVAILABLE"}
    ]
    dock_capable_hashes = {str(row["skeleton_hash"]) for row in dock_capable_main_candidates}
    structured_truck_pass_hashes = sorted(
        skeleton_hash
        for skeleton_hash in dock_capable_hashes
        if preflight_by_hash.get(skeleton_hash, {}).get("preflight_status") == "PASS"
    )
    dock_anchor_rows = []
    for anchor in sorted(
        construction_dock_anchors.values(),
        key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":"), default=str),
    ):
        rectangle = anchor.get("shipping_rectangle")
        if not isinstance(rectangle, Mapping):
            continue
        dock_anchor_rows.append(
            {
                "layout_family": (
                    f"DOCK · {anchor.get('loading_face_side')} · "
                    f"{anchor.get('source_template_identity')}"
                ),
                "skeleton_hash": str(anchor.get("dock_point_mm")),
                "packaging_slot_exists": True,
                "shipping_dock_anchor": anchor,
                "truck_entrance_segment_mm": truck_entrance_segment,
                "zones": [_trace_zone_row({"zone_code": "shipping_channel", **rectangle})],
            }
        )
    package_anchor_rows = []
    for anchor in sorted(all_packaging_anchors.values(), key=lambda row: row["anchor_id"]):
        rectangle = anchor.get("rectangle", {})
        if not isinstance(rectangle, Mapping):
            continue
        x, y = (
            round(float(rectangle.get("x", 0)) * 1000),
            round(float(rectangle.get("y", 0)) * 1000),
        )
        width, depth = (
            round(float(rectangle.get("width_m", 0)) * 1000),
            round(float(rectangle.get("depth_m", 0)) * 1000),
        )
        if int(rectangle.get("rotation_deg", 0)) == 90:
            width, depth = depth, width
        package_anchor_rows.append(
            {
                "layout_family": f"PACKAGING ANCHOR · {anchor.get('bay_id')}",
                "skeleton_hash": str(anchor.get("anchor_id", "")),
                "packaging_slot_exists": True,
                "zones": [
                    {
                        "zone_code": "packaging_material_storage",
                        "bounds_mm": [x, y, x + width, y + depth],
                        "rotation_deg": rectangle.get("rotation_deg", 0),
                    }
                ],
            }
        )
    core_image = _write_image(
        CORE_IMAGE,
        "Packaging + sorting construction core pairs (S0)",
        core_pair_candidates,
        boundary,
        obstacles,
        "No package-driven sorting core pair was enumerated.",
    )
    anchor_image = _write_image(
        ANCHOR_IMAGE,
        "Exact authoritative packaging site anchors (17.3 × 14.5 m, allowed orientations)",
        package_anchor_rows,
        boundary,
        obstacles,
        "No exact site-valid packaging anchor was enumerated.",
    )
    dock_anchor_image = _write_image(
        DOCK_ANCHOR_IMAGE,
        "Authoritative truck dock events and legal shipping rectangles",
        dock_anchor_rows,
        boundary,
        obstacles,
        "No legal shipping rectangle was bound to an authoritative dock point.",
    )
    dual_interface_image = _write_image(
        DUAL_INTERFACE_IMAGE,
        "Packaging + sorting + exact shipping dock critical assemblies",
        dock_capable_main_candidates,
        boundary,
        obstacles,
        "No dock-capable seven-zone main skeleton passed construction admission.",
    )
    truck_pass_candidates = [
        row
        for row in dock_capable_main_candidates
        if row["skeleton_hash"] in structured_truck_pass_hashes
    ]
    truck_pass_hash_set = set(structured_truck_pass_hashes)
    truck_qualified_site_full_candidates = [
        row for row in full_candidates if str(row.get("skeleton_hash")) in truck_pass_hash_set
    ]
    truck_pass_image = _write_image(
        TRUCK_PASS_IMAGE,
        "Structured main skeletons admitted by authoritative truck preflight",
        truck_pass_candidates,
        boundary,
        obstacles,
        "No structured main skeleton passed authoritative truck preflight.",
    )
    main_image = _write_image(
        MAIN_IMAGE,
        "Eight-zone packaging-reserved critical main assemblies (S1)",
        main_candidates,
        boundary,
        obstacles,
        "No packaging-reserved eight-zone main assembly was observed.",
    )
    full_image = _write_image(
        FULL_IMAGE,
        "R2 complete site-aware 12-zone module assemblies (S2)",
        full_candidates,
        boundary,
        obstacles,
        "No complete site-valid 12-zone module assembly was observed.",
    )
    p2d_image = _write_image(
        P2D_IMAGE,
        "R2 structured P2D full-pass module candidates",
        structured_full_pass_candidates,
        boundary,
        obstacles,
        "No structured P2D full-pass candidate was observed; fallback is not shown as structured.",
    )

    budget = first_diag.get("r11_budget_accounting", {})
    selected = first["selected"]
    critical_assembly_failure_by_family: dict[str, dict[str, Any]] = {}
    for family, counts in sorted(runtime_s1_counts_by_family.items()):
        if counts.get("packaging_sorting_core_pair_count", 0) == 0:
            first_failure_stage = "PACKAGING_SORTING_CORE_PAIR"
        elif counts.get("raw_attachment_site_valid_count", 0) == 0:
            first_failure_stage = "RAW_ATTACHMENT"
        elif counts.get("finished_attachment_site_valid_count", 0) == 0:
            first_failure_stage = "FINISHED_ATTACHMENT"
        elif counts.get("main_must_graph_valid_count", 0) == 0:
            first_failure_stage = "MUST_INTERFACE"
        elif counts.get("critical_8_zone_count", 0) == 0:
            first_failure_stage = "FORMAL_PACKAGING_PREFLIGHT_OR_JOINT_ANCHOR_MISMATCH"
        else:
            first_failure_stage = "NONE"
        critical_assembly_failure_by_family[family] = {
            "first_failure_stage": first_failure_stage,
            "packaging_sorting_core_pair_count": counts.get("packaging_sorting_core_pair_count", 0),
            "raw_attachment_candidate_count": counts.get("raw_attachment_candidate_count", 0),
            "raw_attachment_site_valid_count": counts.get("raw_attachment_site_valid_count", 0),
            "finished_attachment_candidate_count": counts.get(
                "finished_attachment_candidate_count", 0
            ),
            "finished_attachment_site_valid_count": counts.get(
                "finished_attachment_site_valid_count", 0
            ),
            "main_must_graph_valid_count": counts.get("main_must_graph_valid_count", 0),
            "critical_8_zone_count": counts.get("critical_8_zone_count", 0),
        }
    evidence = {
        "identity": "v222-p1a-r2-dual-external-interface-truck-dock-recovery@1.0.0",
        "task_id": "V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2",
        "mode": "R2_DUAL_EXTERNAL_INTERFACE_PACKAGING_TRUCK_DOCK_RECOVERY",
        "baseline_head": "73d7c6c151c6b1f1351a02fd8b615343bc5c107c",
        "input_fixture": str(FIXTURE),
        "tool7_unmocked_replay_count": 2,
        "site_geometry": first["context_geometry"],
        "orthogonal_site_bay_decomposition": {
            "status": "EXACT_ORTHOGONAL" if bay_rows else "UNAVAILABLE_OR_EMPTY",
            "bay_count": len(bay_rows),
            "adjacency_count": sum(len(row.get("adjacent_bay_ids", [])) for row in bay_rows) // 2,
            "bays": bay_rows,
        },
        "module_contract": {
            "module_internal_geometry_rigid": True,
            "module_level_site_adaptation": True,
            "individual_room_site_movement": False,
            "local_module_synthesis_uses_site_events": False,
            "module_site_assembly_uses_site_events": True,
            "packaging_joint_site_assembly": True,
            "packaging_module_independent": True,
            "critical_assembly_zone_count": 8,
            "true_packaging_first_construction": True,
            "packaging_anchor_influences_sorting_root_enumeration": (
                packaging_anchor_influences_sorting_roots
            ),
            "packaging_sorting_must_shared_edge": False,
            "formal_packaging_preflight_retained": True,
            "sorting_rotation_site_attempt_count_by_family": sorting_attempts_by_family,
            "module_variant_counts": variant_counts,
        },
        "dual_external_interface": {
            "true_packaging_first_construction": True,
            "shipping_dock_anchor_first_class": bool(all_shipping_dock_anchors),
            "two_external_interface_aware": True,
            "truck_entrance_segment_mm": truck_entrance_segment,
            "truck_dock_point_count": len(
                {
                    tuple(row.get("dock_point_mm", []))
                    for row in all_shipping_dock_anchors.values()
                    if isinstance(row.get("dock_point_mm"), list)
                }
            ),
            "shipping_dock_rectangle_count": len(
                {
                    tuple(
                        _trace_zone_row(
                            {"zone_code": "shipping_channel", **row["shipping_rectangle"]}
                        )["bounds_mm"]
                    )
                    for row in all_shipping_dock_anchors.values()
                    if isinstance(row.get("shipping_rectangle"), Mapping)
                }
            ),
            "shipping_dock_rectangle_count_by_rotation": {
                str(rotation): len(
                    {
                        tuple(
                            _trace_zone_row(
                                {"zone_code": "shipping_channel", **row["shipping_rectangle"]}
                            )["bounds_mm"]
                        )
                        for row in all_shipping_dock_anchors.values()
                        if isinstance(row.get("shipping_rectangle"), Mapping)
                        and int(row.get("shipping_rotation_deg", -1)) == rotation
                    }
                )
                for rotation in (0, 90)
            },
            "shipping_dock_rectangle_count_by_loading_face_side": {
                side: len(
                    {
                        tuple(
                            _trace_zone_row(
                                {"zone_code": "shipping_channel", **row["shipping_rectangle"]}
                            )["bounds_mm"]
                        )
                        for row in all_shipping_dock_anchors.values()
                        if isinstance(row.get("shipping_rectangle"), Mapping)
                        and row.get("loading_face_side") == side
                    }
                )
                for side in sorted(
                    {
                        str(row.get("loading_face_side"))
                        for row in all_shipping_dock_anchors.values()
                    }
                )
            },
            "shipping_dock_construction_representative_count": len(construction_dock_anchors),
            "packaging_shipping_anchor_pair_count": int(
                max(
                    int(variant_counts.get("packaging_shipping_anchor_pair_count", 0)),
                    len(dual_pair_keys),
                )
            ),
            "packaging_shipping_pair_necessary_pass_count": int(
                max(
                    int(variant_counts.get("packaging_shipping_pair_necessary_pass_count", 0)),
                    len(dual_pair_necessary_keys),
                )
            ),
            "packaging_anchor_influences_sorting_root_enumeration": (
                packaging_anchor_influences_sorting_roots
            ),
            "shipping_dock_anchor_influences_sorting_root_enumeration": bool(
                any(
                    len(set(dock_rows.values())) > 1
                    for dock_rows in sorting_roots_by_external_pair.values()
                )
            ),
            "finished_forward_site_attempt_count": max(
                (
                    int(snapshot.get("finished_forward_site_attempt_count", 0))
                    for snapshot in first["snapshots"]
                ),
                default=0,
            ),
            "finished_dock_backsolve_attempt_count": max(
                (
                    int(snapshot.get("finished_dock_backsolve_attempt_count", 0))
                    for snapshot in first["snapshots"]
                ),
                default=0,
            ),
            "dock_capable_main_process_count": len(dock_capable_hashes),
            "structured_main_truck_preflight_pass_count": len(structured_truck_pass_hashes),
            "structured_main_truck_preflight_reject_count": sum(
                preflight_by_hash.get(hash_value, {}).get("preflight_status") == "REJECT"
                for hash_value in dock_capable_hashes
            ),
            "truck_pass_main_skeleton_hashes": structured_truck_pass_hashes,
            "truck_maneuver_construction_witness_count": sum(
                hash_value in captured_truck_witnesses
                for hash_value in structured_truck_pass_hashes
            ),
            "truck_construction_witness_final_validation_mismatch_count": len(
                {
                    str(row.get("main_skeleton_hash"))
                    for row in first["p2d_route_rows"]
                    if row.get("search_phase") == "STRUCTURED"
                    and (
                        str(row.get("main_skeleton_hash")) not in captured_truck_witnesses
                        or row.get("truck_route_validated") is not True
                    )
                }
            ),
            "all_shipping_dock_anchors": list(all_shipping_dock_anchors.values()),
            "construction_shipping_dock_anchors": list(construction_dock_anchors.values()),
            "dock_capable_main_candidates": dock_capable_main_candidates,
            "main_truck_preflight_rows": preflight_rows,
            "truck_maneuver_construction_witnesses": captured_truck_witnesses,
        },
        "stage_gates": {
            "T0_shipping_dock_rectangle_exists": bool(all_shipping_dock_anchors),
            "T1_dock_capable_main_process_exists": bool(dock_capable_hashes),
            "T2_structured_main_truck_preflight_pass_exists": bool(structured_truck_pass_hashes),
            "T3_truck_pass_main_has_site_valid_12_zone_candidate": bool(
                truck_qualified_site_full_candidates
            ),
            "T4_structured_p2d_full_pass_exists": bool(structured_full_pass_candidates),
            "site_valid_12_zone_from_truck_pass_main_count": len(
                truck_qualified_site_full_candidates
            ),
        },
        "packaging_anchor_coverage": {
            "legal_site_anchor_count": len(all_packaging_anchors),
            "construction_representative_count": len(construction_anchors),
            "legal_anchor_count_by_bay": dict(
                sorted(variant_counts.get("packaging_anchor_count_by_bay", {}).items())
            ),
            "construction_anchor_group_count": len(anchor_group_coverage),
            "groups_with_sorting_rotation_0_attempt_or_exact_impossibility": (
                anchor_groups_with_rot0
            ),
            "groups_with_sorting_rotation_90_attempt_or_exact_impossibility": (
                anchor_groups_with_rot90
            ),
            "groups": anchor_group_coverage,
        },
        "packaging_sorting_core_pairs": {
            "distinct_geometry_count": len(core_pair_rows_by_geometry),
            "candidates": core_pair_candidates,
        },
        "critical_assembly_failure_by_family": critical_assembly_failure_by_family,
        "source_pair_coverage": {
            "raw_module_distinct_signature_count": variant_counts.get(
                "raw_module_distinct_signature_count", 0
            ),
            "finished_module_distinct_signature_count": variant_counts.get(
                "finished_module_distinct_signature_count", 0
            ),
            "raw_module_construction_rep_count": variant_counts.get(
                "raw_module_construction_rep_count", 0
            ),
            "finished_module_construction_rep_count": variant_counts.get(
                "finished_module_construction_rep_count", 0
            ),
            "attempt_row_count_by_family": source_pair_attempt_rows_by_family,
            "distinct_input_geometry_count_by_family": source_pair_distinct_inputs_count_by_family,
            "with_site_valid_critical_geometry_count_by_family": (
                source_pair_site_valid_count_by_family
            ),
        },
        "stage_counts": {
            "raw_site_valid_main_count": sum(
                counts.get("raw_site_valid_main_count", 0)
                for counts in s1_counts_by_family.values()
            ),
            "raw_site_valid_main_count_by_family": {
                family: counts.get("raw_site_valid_main_count", 0)
                for family, counts in sorted(s1_counts_by_family.items())
            },
            "packaging_slot_rejected_main_count": sum(
                counts.get("packaging_slot_rejected_main_count", 0)
                for counts in s1_counts_by_family.values()
            ),
            "packaging_slot_rejected_main_count_by_family": {
                family: counts.get("packaging_slot_rejected_main_count", 0)
                for family, counts in sorted(s1_counts_by_family.items())
            },
            "tail_capable_site_valid_main_process_count": len(
                {row.get("skeleton_hash") for row in main_candidates}
            ),
            "tail_capable_main_count_by_family": {
                family: count for family, count in packaging_reserved_by_family.items()
            },
            "packaging_reserved_main_count": len(main_candidates),
            "packaging_reserved_main_count_by_family": packaging_reserved_by_family,
            "critical_8_zone_count": critical_8_zone_geometry_count,
            "packaging_sorting_core_pair_count": len(core_pair_rows_by_geometry),
            "critical_assembly_failure_by_family": critical_assembly_failure_by_family,
            "source_pair_count_by_family": {
                family: counts.get("source_pair_count", 0)
                for family, counts in sorted(runtime_s1_counts_by_family.items())
            },
            "source_pairs_exhausted_by_family": {
                family: counts.get("source_pairs_exhausted", 0)
                for family, counts in sorted(runtime_s1_counts_by_family.items())
            },
            "source_pair_tail_capacity_exhausted_by_family": {
                family: counts.get("source_pair_tail_capacity_exhausted", 0)
                for family, counts in sorted(runtime_s1_counts_by_family.items())
            },
            "early_formal_packaging_preflight_mismatch_count": early_formal_mismatch_count,
            "packaging_site_anchor_count": len(all_packaging_anchors),
            "packaging_construction_rep_count": len(construction_anchors),
            "packaging_anchor_count_by_bay": dict(
                sorted(variant_counts.get("packaging_anchor_count_by_bay", {}).items())
            ),
            "sorting_rotation_site_attempt_count_by_family": sorting_attempts_by_family,
            "early_packaging_preflight_geometry_evaluation_count": sum(
                row.get("preflight_reused") is False for row in s1_geometry_attempts
            ),
            "early_packaging_preflight_geometry_cache_reuse_count": sum(
                row.get("preflight_reused") is True for row in s1_geometry_attempts
            ),
            "raw_site_valid_main_attempt_count": len(s1_geometry_attempts),
            "packaging_slot_preflight_pass_count": sum(
                row.get("result") == "PACKAGING_RESERVED_MAIN_ADMITTED"
                for snapshot in first["snapshots"]
                for row in snapshot["site_module_assembly_trace"]
            ),
            "site_valid_12_zone_structured_count": len(full_candidates),
            "structured_truck_pass_count": len(structured_truck_pass_hashes),
            "structured_truck_pass_hashes": structured_truck_pass_hashes,
            "structured_p2d_full_pass_count": structured_full_pass_count,
            "distinct_structured_full_pass_skeleton_count": len(
                distinct_structured_full_pass_hashes
            ),
            "stage_a_complete_12_zone_exists": bool(full_candidates),
            "stage_b_three_families_complete": all(
                any(row.get("layout_family") == family for row in full_candidates)
                for family in (
                    "LINEAR_3_BAND",
                    "CENTRAL_PROCESS_WITH_SIDE_BANKS",
                    "LONGITUDINAL_PROCESS_SPINE",
                )
            ),
            "stage_c_structured_p2d_full_pass_exists": bool(structured_full_pass_candidates),
            "stage_d_final_visual_acceptance": (
                len({row.get("skeleton_hash") for row in regular_full_passes}) >= 5
                and len({row.get("layout_family") for row in regular_full_passes}) >= 3
            ),
            "p2d_building_footprint_outline_classes": sorted(
                {
                    str(row.get("p2d_building_footprint_outline_class"))
                    for row in structured_full_pass_candidates
                }
            ),
            "visually_distinct_p2d_full_pass_candidate_count": len(
                {row.get("skeleton_hash") for row in regular_full_passes}
            ),
            "structured_full_pass_layout_family_count": len(
                {row.get("layout_family") for row in regular_full_passes}
            ),
            "stair_step_presented_count": sum(
                row.get("p2d_building_footprint_outline_class") not in {"RECTANGLE", "SIMPLE_L"}
                for row in structured_full_pass_candidates
            ),
        },
        "raw_site_valid_main_candidates": raw_site_main_candidates,
        "site_main_candidates": main_candidates,
        "s1_geometry_attempts": s1_geometry_attempts,
        "packaging_slot_rejected_skeleton_hashes": sorted(
            {
                str(row["main_process_skeleton_hash"])
                for row in s1_geometry_attempts
                if row.get("result") == "PACKAGING_SLOT_REJECTED"
            }
        ),
        "s1_counts_by_family": s1_counts_by_family,
        "runtime_s1_stats_by_family": runtime_s1_counts_by_family,
        "source_pair_rows": source_pair_rows,
        "site_full_candidates": full_candidates,
        "site_module_attempt_traces": [
            row for snapshot in first["snapshots"] for row in snapshot["site_module_assembly_trace"]
        ],
        "p2d_candidate_validation_trace": first["p2d_route_rows"],
        "structured_p2d_access_failure_summary": [
            {
                "main_skeleton_hash": row.get("main_skeleton_hash"),
                "canonical_candidate_hash": row.get("canonical_candidate_hash"),
                "access_pass_count": row.get("access_pass_count"),
                "access_requirement_count": row.get("access_requirement_count"),
                "truck_route_validated": row.get("truck_route_validated"),
                "failed_requirements": [
                    {
                        "requirement_identity": access_row.get("requirement_identity"),
                        "status": access_row.get("status"),
                        "codes": access_row.get("codes", []),
                    }
                    for access_row in row.get("access_results", [])
                    if access_row.get("status") != "PASS"
                ],
            }
            for row in first["p2d_route_rows"]
            if row.get("search_phase") == "STRUCTURED"
        ],
        "truck_preflight_trace": preflight_rows,
        "placement_budget": budget,
        "selected_tool7_layout": {
            key: selected.get(key)
            for key in (
                "skeleton_hash",
                "validated",
                "p2_complete",
                "access_pass_count",
                "access_requirement_count",
                "truck_route_validated",
                "zone_count",
                "canonical_result_hash",
                "svg_sha256",
            )
        },
        "structured_full_pass_candidates": structured_full_pass_candidates,
        "images": {
            "packaging_anchors": anchor_image,
            "packaging_sorting_core_pairs": core_image,
            "main_process": main_image,
            "full_12_zone": full_image,
            "p2d_full_pass_gallery": p2d_image,
            "shipping_dock_anchors": dock_anchor_image,
            "dual_interface_critical_main": dual_interface_image,
            "truck_pass_main": truck_pass_image,
        },
        "determinism": {
            "same_selected_layout": first["selected"]["skeleton_hash"]
            == second["selected"]["skeleton_hash"]
            and first["tool7"]["result"].get("layout") == second["tool7"]["result"].get("layout"),
            "same_canonical_result_hash": selected["canonical_result_hash"]
            == second["selected"]["canonical_result_hash"],
            "same_svg_bytes": selected["svg_bytes"] == second["selected"]["svg_bytes"],
            "same_work_queue_and_module_trace": first_diag == second_diag
            and first["snapshots"] == second["snapshots"]
            and first["main_candidates"] == second["main_candidates"]
            and first["full_attempts"] == second["full_attempts"]
            and first["p2d_route_rows"] == second["p2d_route_rows"],
        },
        "family_geometry_collapse_count": max(
            (int(snapshot["family_geometry_collapse_count"]) for snapshot in first["snapshots"]),
            default=0,
        ),
        "result": "PASS"
        if (
            len({row.get("skeleton_hash") for row in regular_full_passes}) >= 5
            and len({row.get("layout_family") for row in regular_full_passes}) >= 3
            and not any(
                row.get("p2d_building_footprint_outline_class") not in {"RECTANGLE", "SIMPLE_L"}
                for row in structured_full_pass_candidates
            )
        )
        else "FAIL",
    }
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return evidence


if __name__ == "__main__":
    report = capture_site_partitioned_replay()
    print(
        json.dumps(
            {
                "result": report["result"],
                "mode": report["mode"],
                "packaging_anchor_coverage": report["packaging_anchor_coverage"],
                "dual_external_interface": {
                    key: report["dual_external_interface"].get(key)
                    for key in (
                        "truck_dock_point_count",
                        "shipping_dock_rectangle_count",
                        "shipping_dock_rectangle_count_by_rotation",
                        "shipping_dock_rectangle_count_by_loading_face_side",
                        "shipping_dock_construction_representative_count",
                        "packaging_shipping_anchor_pair_count",
                        "packaging_shipping_pair_necessary_pass_count",
                        "shipping_dock_anchor_influences_sorting_root_enumeration",
                        "finished_forward_site_attempt_count",
                        "finished_dock_backsolve_attempt_count",
                        "dock_capable_main_process_count",
                        "structured_main_truck_preflight_pass_count",
                        "structured_main_truck_preflight_reject_count",
                        "truck_pass_main_skeleton_hashes",
                        "truck_maneuver_construction_witness_count",
                        "truck_construction_witness_final_validation_mismatch_count",
                    )
                },
                "packaging_sorting_core_pairs": report["packaging_sorting_core_pairs"][
                    "distinct_geometry_count"
                ],
                "source_pair_coverage": report["source_pair_coverage"],
                "site_bay_count": report["orthogonal_site_bay_decomposition"]["bay_count"],
                "module_variant_counts": report["module_contract"]["module_variant_counts"],
                "stage_counts": report["stage_counts"],
                "stage_gates": report["stage_gates"],
                "structured_p2d_access_failure_summary": report[
                    "structured_p2d_access_failure_summary"
                ],
                "selected_tool7_layout": report["selected_tool7_layout"],
                "placement_budget": report["placement_budget"],
                "determinism": report["determinism"],
                "images": report["images"],
                "s1_counts_by_family": report["s1_counts_by_family"],
                "runtime_s1_stats_by_family": report["runtime_s1_stats_by_family"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
