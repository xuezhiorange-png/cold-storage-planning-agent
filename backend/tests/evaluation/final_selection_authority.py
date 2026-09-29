"""Capture and visualize real Tool 7 full-pass candidates for selection review."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.modules.aily.application import site_layout_preview
from cold_storage.modules.layout.application import validated_candidate_selection as selection
from cold_storage.modules.layout.application.svg_projection import project_validated_layout_to_svg
from tests.evaluation.r13_main_skeleton_truck_preflight import FIXTURE
from tests.evaluation.r15_truck_feasible_layout_delivery import (
    CONTROL_SVG,
    EVIDENCE_DIR,
    SVG_NAMESPACE,
    _svg_view_box,
)

TASK_ID = "V2_2_2_P1A_FINAL_SELECTION_AUTHORITY_CLOSURE_R1"
SELECTION_EVIDENCE = EVIDENCE_DIR / "xinzhao_p1a_final_selection_candidates.json"
SELECTION_RESULT = EVIDENCE_DIR / "xinzhao_p1a_final_selection_result.json"


def _capture_tool7(payload: Mapping[str, Any]) -> dict[str, Any]:
    captured_records: list[dict[str, Any]] = []
    selection_holder: dict[str, Any] = {}
    site_holder: dict[str, Any] = {}
    real_select = site_layout_preview.select_validated_placement
    real_build = selection.build_structural_quality_facts

    def capture_select(*args: Any, **kwargs: Any) -> Any:
        site_holder["geometry"] = args[2] if len(args) > 2 else kwargs["site_geometry"]
        selected = real_select(*args, **kwargs)
        selection_holder["result"] = selected.to_dict()
        selection_holder["internal"] = selected.internal_evaluation
        return selected

    def capture_facts(
        candidate: Mapping[str, Any],
        routed: Mapping[str, Any],
        site: Mapping[str, Any],
        family: Any,
        **kwargs: Any,
    ) -> Any:
        facts = real_build(candidate, routed, site, family, **kwargs)
        captured_records.append(
            {
                "candidate": copy.deepcopy(dict(candidate)),
                "p2d_result": copy.deepcopy(dict(routed)),
                "structural_facts": facts.to_dict(),
                "structural_comparison_key": list(facts.comparison_key),
                "family": family.to_dict(),
            }
        )
        return facts

    site_layout_preview.select_validated_placement = capture_select
    selection.build_structural_quality_facts = capture_facts
    try:
        result = site_layout_preview.preview_site_layout(dict(payload))
    finally:
        site_layout_preview.select_validated_placement = real_select
        selection.build_structural_quality_facts = real_build
    if "geometry" not in site_holder or "internal" not in selection_holder:
        raise AssertionError("real Tool 7 selector capture is incomplete")
    return {
        "result": result,
        "selector_result": selection_holder["result"],
        "internal": selection_holder["internal"],
        "site_geometry": site_holder["geometry"],
        "full_pass_records": captured_records,
    }


def _preferred_loading_side(site_geometry: Any) -> str:
    body = site_geometry.to_dict()
    site = body.get("site")
    if not isinstance(site, Mapping):
        raise AssertionError("validated site geometry has no site authority")
    value = site.get("preferred_loading_side")
    if not isinstance(value, str):
        raise AssertionError("preferred loading side is unavailable")
    return value


def _best_record_per_skeleton(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    preferred_side = _preferred_loading_side(run["site_geometry"])
    best: dict[str, tuple[dict[str, Any], dict[str, Any], Any, Any]] = {}
    source_rows: dict[str, dict[str, Any]] = {}
    for row in run["full_pass_records"]:
        candidate = row["candidate"]
        skeleton_hash = candidate.get("_r5_skeleton_hash")
        if not isinstance(skeleton_hash, str):
            raise AssertionError("full-pass candidate has no main skeleton identity")
        record = (
            candidate,
            row["p2d_result"],
            selection.StructuralQualityFactsV1(
                json.dumps(row["structural_facts"], sort_keys=True, separators=(",", ":")),
                tuple(int(value) for value in row["structural_comparison_key"]),
            ),
            selection.StructuralCompositionFamilyV1(
                row["family"]["family"],
                row["family"]["dominant_axis"],
                row["family"]["dominant_direction"],
                row["family"]["generation_reason"],
            ),
        )
        current = best.get(skeleton_hash)
        if selection._record_is_better(record, current, preferred_side):
            best[skeleton_hash] = record
            source_rows[skeleton_hash] = row
    records: list[dict[str, Any]] = []
    site_geometry = run["site_geometry"]
    for skeleton_hash in sorted(best):
        row = source_rows[skeleton_hash]
        candidate, p2d_result, _, family = best[skeleton_hash]
        projection = project_validated_layout_to_svg(
            p2d_result,
            site_geometry=site_geometry,
        ).to_dict()
        svg = projection.get("svg")
        if not isinstance(svg, str):
            raise AssertionError("validated candidate SVG projection is unavailable")
        records.append(
            {
                "skeleton_hash": skeleton_hash,
                "candidate_hash": candidate.get("canonical_candidate_hash"),
                "p2d_result_hash": p2d_result.get("canonical_result_hash"),
                "discovery_topology": candidate.get("_r7_discovery_topology"),
                "canonical_topology": candidate.get("_r5_topology"),
                "structural_family": family.to_dict(),
                "zones": copy.deepcopy(candidate.get("zones")),
                "p2d_full_pass": p2d_result.get("project_layout_validated") is True
                and p2d_result.get("p2_complete") is True,
                "p2d_result": p2d_result,
                "structural_quality_facts": row["structural_facts"],
                "structural_comparison_key": row["structural_comparison_key"],
                "svg": svg,
                "svg_sha256": "sha256:" + hashlib.sha256(svg.encode("utf-8")).hexdigest(),
            }
        )
    return records


def _nested_svg(source_svg: str, x: float, y: float, width: float, height: float) -> ET.Element:
    min_x, min_y, source_width, source_height = _svg_view_box(source_svg)
    nested = ET.Element(
        f"{{{SVG_NAMESPACE}}}svg",
        {
            "x": f"{x:.3f}",
            "y": f"{y:.3f}",
            "width": f"{width:.3f}",
            "height": f"{height:.3f}",
            "viewBox": f"{min_x:.3f} {min_y:.3f} {source_width:.3f} {source_height:.3f}",
            "preserveAspectRatio": "xMidYMid meet",
        },
    )
    source = ET.fromstring(source_svg)
    for child in list(source):
        nested.append(copy.deepcopy(child))
    return nested


def _comparison_svg(sources: list[tuple[str, str]], *, columns: int) -> tuple[str, dict[str, Any]]:
    boxes = [_svg_view_box(svg) for _, svg in sources]
    canvas_width = max(box[2] for box in boxes)
    canvas_height = max(box[3] for box in boxes)
    header_height = 48.0
    gutter = 32.0
    rows = (len(sources) + columns - 1) // columns
    overall_width = columns * canvas_width + (columns - 1) * gutter
    overall_height = rows * (canvas_height + header_height) + (rows - 1) * gutter
    outer = ET.Element(
        f"{{{SVG_NAMESPACE}}}svg",
        {
            "width": f"{overall_width:.3f}px",
            "height": f"{overall_height:.3f}px",
            "viewBox": f"0 0 {overall_width:.3f} {overall_height:.3f}",
            "preserveAspectRatio": "xMinYMin meet",
        },
    )
    ET.SubElement(
        outer,
        f"{{{SVG_NAMESPACE}}}rect",
        {
            "x": "0",
            "y": "0",
            "width": str(overall_width),
            "height": str(overall_height),
            "fill": "#ffffff",
        },
    )
    for index, (label, svg) in enumerate(sources):
        column = index % columns
        row = index // columns
        x = column * (canvas_width + gutter)
        y = row * (canvas_height + header_height + gutter)
        title = ET.SubElement(
            outer,
            f"{{{SVG_NAMESPACE}}}text",
            {
                "x": f"{x + canvas_width / 2:.3f}",
                "y": f"{y + 32:.3f}",
                "text-anchor": "middle",
                "font-family": "sans-serif",
                "font-size": "25",
                "font-weight": "600",
                "fill": "#1f2937",
            },
        )
        title.text = label
        outer.append(_nested_svg(svg, x, y + header_height, canvas_width, canvas_height))
    return ET.tostring(outer, encoding="unicode"), {
        "same_canvas": True,
        "same_scale": len({(round(box[2], 3), round(box[3], 3)) for box in boxes}) == 1,
        "uncropped": True,
        "canvas_width": overall_width,
        "canvas_height": overall_height,
    }


def _rasterize(svg: str, destination: Path) -> None:
    sips = shutil.which("sips")
    if sips is None:
        raise RuntimeError("sips is required to rasterize the SVG evidence on this host")
    with tempfile.TemporaryDirectory(prefix="selection-authority-svg-") as temp_name:
        source = Path(temp_name) / "source.svg"
        source.write_text(svg, encoding="utf-8")
        subprocess.run(
            [sips, "-s", "format", "png", str(source), "--out", str(destination)],
            check=True,
            capture_output=True,
            text=True,
        )


def _write_visuals(records: list[dict[str, Any]], selected_svg: str) -> dict[str, Any]:
    if len(records) != 3:
        raise AssertionError(f"expected 3 distinct P2D full-pass skeletons, got {len(records)}")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    labeled: list[tuple[str, str]] = []
    candidate_paths: list[dict[str, str]] = []
    for index, row in enumerate(records):
        label = f"Candidate {chr(ord('A') + index)}"
        stem = f"xinzhao_p1a_final_candidate_{chr(ord('a') + index)}"
        svg_path = EVIDENCE_DIR / f"{stem}.svg"
        png_path = EVIDENCE_DIR / f"{stem}.png"
        svg_path.write_text(row["svg"], encoding="utf-8")
        _rasterize(row["svg"], png_path)
        labeled.append((label, row["svg"]))
        candidate_paths.append({"label": label, "svg": str(svg_path), "png": str(png_path)})

    candidates_svg, candidates_canvas = _comparison_svg(labeled, columns=3)
    candidates_svg_path = EVIDENCE_DIR / "xinzhao_p1a_final_selection_candidates.svg"
    candidates_png_path = EVIDENCE_DIR / "xinzhao_p1a_final_selection_candidates.png"
    candidates_svg_path.write_text(candidates_svg, encoding="utf-8")
    _rasterize(candidates_svg, candidates_png_path)

    control_svg = CONTROL_SVG.read_text(encoding="utf-8")
    before_svg_path = EVIDENCE_DIR / "xinzhao_p1a_final_before.svg"
    after_svg_path = EVIDENCE_DIR / "xinzhao_p1a_final_after.svg"
    before_svg_path.write_text(control_svg, encoding="utf-8")
    after_svg_path.write_text(selected_svg, encoding="utf-8")
    before_after_svg, before_after_canvas = _comparison_svg(
        [("Before - control", control_svg), ("After - selected", selected_svg)],
        columns=2,
    )
    comparison_path = EVIDENCE_DIR / "xinzhao_p1a_final_side_by_side.svg"
    comparison_path.write_text(before_after_svg, encoding="utf-8")
    before_png_path = EVIDENCE_DIR / "xinzhao_p1a_final_before.png"
    after_png_path = EVIDENCE_DIR / "xinzhao_p1a_final_after.png"
    side_by_side_png_path = EVIDENCE_DIR / "xinzhao_p1a_final_side_by_side.png"
    _rasterize(control_svg, before_png_path)
    _rasterize(selected_svg, after_png_path)
    _rasterize(before_after_svg, side_by_side_png_path)
    return {
        "candidate_panels": candidate_paths,
        "candidates_svg": str(candidates_svg_path),
        "candidates_png": str(candidates_png_path),
        "candidates_canvas": candidates_canvas,
        "before_svg": str(before_svg_path),
        "after_svg": str(after_svg_path),
        "before_png": str(before_png_path),
        "after_png": str(after_png_path),
        "side_by_side_svg": str(comparison_path),
        "side_by_side_png": str(side_by_side_png_path),
        "before_after_canvas": before_after_canvas,
    }


def run_and_write_selection_evidence() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    first = _capture_tool7(payload)
    second = _capture_tool7(payload)
    records = _best_record_per_skeleton(first)
    labels = [f"Candidate {chr(ord('A') + index)}" for index in range(len(records))]
    rows = []
    for label, record in zip(labels, records, strict=True):
        rows.append(
            {key: value for key, value in record.items() if key != "svg"} | {"label": label}
        )
    selected_svg = first["result"]["drawing"]["svg"]
    visuals = _write_visuals(records, selected_svg)
    comparison = first["internal"]
    result = first["result"]
    evidence = {
        "identity": "v222-p1a-final-selection-candidates@1.0.0",
        "task_id": TASK_ID,
        "source_fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "candidate_count": len(rows),
        "all_candidates_p2d_full_pass": all(row["p2d_full_pass"] for row in rows),
        "candidate_rows": rows,
        "selection": {
            "selected_skeleton_hash": comparison.get("selected_main_process_skeleton_hash"),
            "selected_candidate_hash": comparison.get("selected_candidate_hash"),
            "runner_up_skeleton_hash": comparison.get("distinct_runner_up_skeleton_hash"),
            "first_decisive_component": comparison.get(
                "distinct_skeleton_first_decisive_component"
            ),
            "winner_value": comparison.get("distinct_skeleton_winner_value"),
            "runner_up_value": comparison.get("distinct_skeleton_runner_up_value"),
            "p2b2_business_objective_used": comparison.get("p2b2_tiebreak_used"),
            "canonical_json_tiebreak_used": comparison.get("canonical_json_tiebreak_used"),
            "canonical_json_tiebreak_scope": comparison.get("canonical_json_tiebreak_scope"),
            "distinct_skeleton_p2b2_business_objective_used": comparison.get(
                "distinct_skeleton_p2b2_business_objective_used"
            ),
            "distinct_skeleton_canonical_json_tiebreak_used": comparison.get(
                "distinct_skeleton_canonical_json_tiebreak_used"
            ),
            "project_layout_validated": result.get("project_layout_validated") is True,
            "p2_complete": result.get("p2_complete") is True,
            "access_pass_count": result.get("layout", {}).get("access_pass_count"),
            "access_requirement_count": result.get("layout", {}).get("access_requirement_count"),
            "truck_route_validated": result.get("layout", {}).get("truck_route_validated") is True,
            "zone_count": result.get("zone_count"),
            "building_footprint_present": bool(result.get("layout", {}).get("building_footprint")),
            "canonical_result_hash": result.get("canonical_result_hash"),
            "svg_sha256": result.get("svg_sha256"),
        },
        "determinism": {
            "same_selected_layout": first["result"].get("layout") == second["result"].get("layout"),
            "same_canonical_result_hash": first["result"].get("canonical_result_hash")
            == second["result"].get("canonical_result_hash"),
            "same_svg_bytes": first["result"].get("drawing", {}).get("svg")
            == second["result"].get("drawing", {}).get("svg"),
            "same_svg_hash": first["result"].get("svg_sha256")
            == second["result"].get("svg_sha256"),
        },
        "visuals": visuals,
    }
    SELECTION_EVIDENCE.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    SELECTION_RESULT.write_text(
        json.dumps(evidence["selection"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence


if __name__ == "__main__":
    report = run_and_write_selection_evidence()
    print(json.dumps(report["selection"], ensure_ascii=False, indent=2, sort_keys=True))
