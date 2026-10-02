"""Capture real Tool 7 evidence for R2 site-partitioned module placement."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain import placement as placement_domain
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from tests.evaluation.final_selection_authority import _capture_tool7, _rasterize
from tests.evaluation.r2_local_composition_first import _p2d_footprint_regularity_facts
from tests.evaluation.r12_access_failure_audit import _zone_skeleton_hash
from tests.evaluation.r13_main_skeleton_truck_preflight import EVIDENCE_DIR, FIXTURE

EVIDENCE_PATH = EVIDENCE_DIR / "xinzhao_p1a_r2_tail_capacity_aware_site_module_assembly.json"
MAIN_IMAGE = EVIDENCE_DIR / "xinzhao_r2_tail_capacity_raw_site_valid_main_candidates.png"
TAIL_CAPABLE_IMAGE = EVIDENCE_DIR / "xinzhao_tail_capable_main_candidates.png"
FULL_IMAGE = EVIDENCE_DIR / "xinzhao_r2_tail_capacity_12zone_candidates.png"
P2D_IMAGE = EVIDENCE_DIR / "xinzhao_r2_tail_capacity_p2d_gallery.png"

MODULE_ZONES = {
    "RAW_MODULE": ("raw_fruit_buffer", "primary_precooling_room"),
    "PROCESS_CORE_MODULE": ("sorting_packaging_room",),
    "FINISHED_MODULE": (
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    ),
    "SUPPORT_MODULE": (
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
    ),
    "PERSONNEL_MODULE": ("office", "changing_room"),
}
MODULE_COLORS = {
    "RAW_MODULE": "#b8d8ec",
    "PROCESS_CORE_MODULE": "#91c9a6",
    "FINISHED_MODULE": "#f1cb86",
    "SUPPORT_MODULE": "#c9b8df",
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
        module_bounds: dict[str, list[tuple[int, int, int, int]]] = {}
        for zone in candidate.get("zones", []):
            if not isinstance(zone, Mapping):
                continue
            bounds = zone.get("bounds_mm")
            if not isinstance(bounds, list) or len(bounds) != 4:
                continue
            left, bottom, right, top = (int(value) for value in bounds)
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
    context_geometry: dict[str, Any] = {}
    real_direct = placement_domain._direct_structured_candidates
    real_main = placement_domain._module_main_site_assemblies
    real_full = placement_domain._module_full_site_assemblies

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
                try:
                    seed = placement_domain._canonical_site_main_skeleton(
                        context,
                        candidate,
                        layout_family=layout_family,
                        process_axis=process_axis,
                        process_direction=process_direction,
                        generation_pattern="R2_SITE_PARTITIONED_EVIDENCE_CAPTURE",
                    )
                    skeleton_hash = seed.main_process_skeleton_hash
                except LayoutAuthorityError:
                    skeleton_hash = "UNAVAILABLE"
                geometry_signature = repr(placement_domain._module_signature(candidate))
                search_stats = kwargs.get("stats")
                early_proof = (
                    (search_stats.early_packaging_preflight_by_geometry or {}).get(
                        geometry_signature
                    )
                    if search_stats is not None
                    else None
                )
                witness_body = (
                    early_proof.get("first_witness_rectangle")
                    if isinstance(early_proof, Mapping)
                    else None
                )
                witness_mm = None
                if isinstance(witness_body, Mapping):
                    wx = round(float(witness_body.get("x", 0)) * 1000)
                    wy = round(float(witness_body.get("y", 0)) * 1000)
                    ww = round(float(witness_body.get("width_m", 0)) * 1000)
                    wd = round(float(witness_body.get("depth_m", 0)) * 1000)
                    if int(witness_body.get("rotation_deg", 0)) == 90:
                        ww, wd = wd, ww
                    witness_mm = [wx, wy, wx + ww, wy + wd]
                captured_main.append(
                    {
                        "layout_family": layout_family,
                        "process_axis": process_axis,
                        "process_direction": process_direction,
                        "skeleton_hash": skeleton_hash,
                        "geometry_signature": geometry_signature,
                        "packaging_slot_exists": (
                            early_proof.get("legal_slot_exists")
                            if isinstance(early_proof, Mapping)
                            else None
                        ),
                        "packaging_slot_witness_mm": witness_mm,
                        "zones": [
                            _zone_row(rectangle) for _code, rectangle in sorted(candidate.items())
                        ],
                    }
                )
            yield candidate

    def observe_full(context: Any, main: Any, bays: Any, *, limit: int) -> Any:
        main_signature = repr(placement_domain._module_signature(main))
        main_hash = next(
            (
                row["skeleton_hash"]
                for row in reversed(captured_main)
                if row["geometry_signature"] == main_signature
            ),
            "UNAVAILABLE",
        )
        for candidate in real_full(context, main, bays, limit=limit):
            captured_full.append(
                {
                    "main_geometry_signature": repr(placement_domain._module_signature(main)),
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
                    "site_bays": [bay.to_dict() for bay in stats.site_bay_rows or ()],
                    "module_variant_counts": dict(stats.site_module_variant_counts or {}),
                    "site_main_assembly_counts_by_family": {
                        family: dict(counts)
                        for family, counts in (
                            stats.site_main_assembly_counts_by_family or {}
                        ).items()
                    },
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
    try:
        tool7 = _capture_tool7(payload, allow_failed_selection=True)
    finally:
        placement_domain._direct_structured_candidates = real_direct
        placement_domain._module_main_site_assemblies = real_main
        placement_domain._module_full_site_assemblies = real_full

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
    variant_counts: dict[str, int] = {}
    runtime_s1_counts_by_family: dict[str, dict[str, int]] = {}
    source_pair_rows: list[dict[str, Any]] = []
    s1_geometry_attempts: list[dict[str, Any]] = []
    early_formal_mismatch_count = 0
    for snapshot in first["snapshots"]:
        for name, value in snapshot["module_variant_counts"].items():
            variant_counts[name] = max(variant_counts.get(name, 0), int(value))
        for family, counts in snapshot["site_main_assembly_counts_by_family"].items():
            aggregate = runtime_s1_counts_by_family.setdefault(family, {})
            for name, value in counts.items():
                aggregate[name] = aggregate.get(name, 0) + int(value)
        source_pair_rows.extend(snapshot["site_main_source_pair_rows"])
        for trace_row in snapshot["site_module_assembly_trace"]:
            if trace_row.get("stage") != "S1_TAIL_CAPACITY_PREFLIGHT" or not isinstance(
                trace_row.get("zones"), list
            ):
                continue
            attempt = dict(trace_row)
            attempt["main_process_skeleton_hash"] = _zone_skeleton_hash(trace_row["zones"])
            s1_geometry_attempts.append(attempt)
        early_formal_mismatch_count += int(
            snapshot["early_formal_packaging_preflight_mismatch_count"]
        )
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
        elif row.get("result") == "TAIL_CAPABLE_MAIN_ADMITTED":
            counts["tail_capable_main_count"] += 1
        else:
            counts["packaging_slot_unavailable_main_count"] += 1
    raw_site_main_candidates: list[dict[str, Any]] = []
    for (family, skeleton_hash), row in sorted(unique_s1_geometries.items()):
        raw_zones: list[dict[str, Any]] = []
        for zone in row.get("zones", []):
            if not isinstance(zone, Mapping):
                continue
            x = round(float(zone.get("x", 0)) * 1000)
            y = round(float(zone.get("y", 0)) * 1000)
            width = round(float(zone.get("width_m", 0)) * 1000)
            depth = round(float(zone.get("depth_m", 0)) * 1000)
            rotation = int(zone.get("rotation_deg", 0))
            if rotation == 90:
                width, depth = depth, width
            raw_zones.append(
                {
                    "zone_code": zone.get("zone_code"),
                    "bounds_mm": [x, y, x + width, y + depth],
                    "rotation_deg": rotation,
                }
            )
        witness = row.get("packaging_preflight", {}).get("first_witness_rectangle")
        witness_mm = None
        if isinstance(witness, Mapping):
            wx = round(float(witness.get("x", 0)) * 1000)
            wy = round(float(witness.get("y", 0)) * 1000)
            ww = round(float(witness.get("width_m", 0)) * 1000)
            wd = round(float(witness.get("depth_m", 0)) * 1000)
            if int(witness.get("rotation_deg", 0)) == 90:
                ww, wd = wd, ww
            witness_mm = [wx, wy, wx + ww, wy + wd]
        raw_site_main_candidates.append(
            {
                "layout_family": family,
                "skeleton_hash": skeleton_hash,
                "packaging_slot_exists": row.get("packaging_slot_exists"),
                "packaging_slot_witness_mm": witness_mm,
                "zones": raw_zones,
            }
        )
    main_image = _write_image(
        MAIN_IMAGE,
        "R2 raw site-valid seven-zone main-process assemblies (S1)",
        raw_site_main_candidates,
        boundary,
        obstacles,
        "No site-valid seven-zone module assembly was observed.",
    )
    tail_capable_image = _write_image(
        TAIL_CAPABLE_IMAGE,
        "R2 tail-capable main-process assemblies · exact packaging slot witnesses",
        [row for row in main_candidates if row.get("packaging_slot_exists") is True],
        boundary,
        obstacles,
        "No seven-zone main assembly passed the exact packaging-slot preflight.",
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

    first_diag = first["diagnostics"]
    second_diag = second["diagnostics"]
    preflight_rows = first_diag.get("main_skeleton_truck_preflight_trace", [])
    main_candidate_hashes = {str(row.get("skeleton_hash")) for row in main_candidates}
    structured_truck_pass_hashes = sorted(
        str(row.get("main_skeleton_hash"))
        for row in preflight_rows
        if isinstance(row, Mapping)
        and row.get("preflight_status") == "PASS"
        and row.get("main_skeleton_hash") in main_candidate_hashes
    )
    budget = first_diag.get("r11_budget_accounting", {})
    selected = first["selected"]
    evidence = {
        "identity": "v222-p1a-r2-tail-capacity-aware-site-module-assembly@1.0.0",
        "task_id": "V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2",
        "mode": "R2_TAIL_CAPACITY_AWARE_SITE_MODULE_ASSEMBLY_RECOVERY",
        "baseline_head": "55710bcd45d92eca74fd2681122da94849218f6f",
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
            "module_variant_counts": variant_counts,
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
            "tail_capable_site_valid_main_process_count": len(main_candidates),
            "tail_capable_main_count_by_family": {
                family: sum(row.get("layout_family") == family for row in main_candidates)
                for family in (
                    "LINEAR_3_BAND",
                    "CENTRAL_PROCESS_WITH_SIDE_BANKS",
                    "LONGITUDINAL_PROCESS_SPINE",
                )
            },
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
            "early_packaging_preflight_geometry_evaluation_count": sum(
                row.get("preflight_reused") is False for row in s1_geometry_attempts
            ),
            "early_packaging_preflight_geometry_cache_reuse_count": sum(
                row.get("preflight_reused") is True for row in s1_geometry_attempts
            ),
            "raw_site_valid_main_attempt_count": len(s1_geometry_attempts),
            "packaging_slot_preflight_pass_count": sum(
                row.get("result") == "PACKAGING_PREFLIGHT_ADMITTED"
                for snapshot in first["snapshots"]
                for row in snapshot["site_module_assembly_trace"]
            ),
            "site_valid_12_zone_structured_count": len(full_candidates),
            "structured_truck_pass_count": len(structured_truck_pass_hashes),
            "structured_truck_pass_hashes": structured_truck_pass_hashes,
            "structured_p2d_full_pass_count": structured_full_pass_count,
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
            "main_process": main_image,
            "tail_capable_main_process": tail_capable_image,
            "full_12_zone": full_image,
            "p2d_full_pass_gallery": p2d_image,
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
            and first["full_attempts"] == second["full_attempts"],
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
                "site_bay_count": report["orthogonal_site_bay_decomposition"]["bay_count"],
                "module_variant_counts": report["module_contract"]["module_variant_counts"],
                "stage_counts": report["stage_counts"],
                "selected_tool7_layout": report["selected_tool7_layout"],
                "placement_budget": report["placement_budget"],
                "determinism": report["determinism"],
                "images": report["images"],
                "s1_counts_by_family": report["s1_counts_by_family"],
                "runtime_s1_stats_by_family": report["runtime_s1_stats_by_family"],
                "source_pair_rows": report["source_pair_rows"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
