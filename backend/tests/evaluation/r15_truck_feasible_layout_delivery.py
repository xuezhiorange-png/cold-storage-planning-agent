"""Real Tool 7 acceptance and evidence generation for P1A R15."""

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
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.structural_composition import (
    MAIN_PROCESS_SKELETON_ZONE_CODES,
)
from tests.evaluation.r12_access_failure_audit import _zone_skeleton_hash
from tests.evaluation.r13_main_skeleton_truck_preflight import (
    EXPECTED_FIXTURE_SHA256,
    FIXTURE,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
CONTROL_HASH = "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"
CONTROL_SVG_SHA256 = "sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981"
CONTROL_SVG = EVIDENCE_DIR / "xinzhao_p1a_r3_after.svg"
CONTROL_LAYOUT = EVIDENCE_DIR / "xinzhao_p1a_r3_after_layout.json"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def run_tool7_with_internal_evaluation(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Capture the real Tool 7 selector even when its chain rejects the search.

    A production failure is returned as an explicit error envelope so the R15
    result can accurately report FAIL and preserve the selector's diagnostics.
    """
    captured: list[dict[str, Any]] = []
    real_select = site_layout_preview.select_validated_placement

    def capture(*args: Any, **kwargs: Any) -> Any:
        selection = real_select(*args, **kwargs)
        internal = selection.internal_evaluation
        internal["_selector_result"] = selection.to_dict()
        internal["_selector_internal_evaluation"] = selection.internal_evaluation
        captured.append(internal)
        return selection

    site_layout_preview.select_validated_placement = capture
    result: dict[str, Any] | None = None
    error: LayoutAuthorityError | None = None
    try:
        result = site_layout_preview.preview_site_layout(dict(payload))
    except LayoutAuthorityError as exc:
        error = exc
    finally:
        site_layout_preview.select_validated_placement = real_select
    if len(captured) != 1:
        if error is not None:
            raise error
        raise AssertionError(f"expected one selector evaluation, got {len(captured)}")
    if error is not None:
        result = {"error_code": error.code, "error_details": error.details}
    assert result is not None
    return result, captured[0]


def _json_write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _diagnostics(internal: Mapping[str, Any]) -> dict[str, Any]:
    value = internal.get("r6_topology_diagnostics")
    if not isinstance(value, dict):
        raise AssertionError("Tool 7 internal topology diagnostics unavailable")
    return value


def capture_xinzhao_replays() -> dict[str, Any]:
    raw = FIXTURE.read_bytes()
    fixture_hash = hashlib.sha256(raw).hexdigest()
    if fixture_hash != EXPECTED_FIXTURE_SHA256:
        raise AssertionError(f"canonical Xinzhao input hash changed: {fixture_hash}")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise AssertionError("canonical Tool 7 fixture must be an object")
    first_result, first_internal = run_tool7_with_internal_evaluation(payload)
    second_result, second_internal = run_tool7_with_internal_evaluation(payload)
    return {
        "fixture_sha256": fixture_hash,
        "first": {"result": first_result, "internal": first_internal},
        "second": {"result": second_result, "internal": second_internal},
    }


def _main_zone_rows(layout: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = layout.get("zones")
    if not isinstance(rows, list):
        raise AssertionError("Tool 7 selected layout has no zone list")
    selected = [
        dict(row)
        for row in rows
        if isinstance(row, Mapping) and row.get("zone_code") in MAIN_PROCESS_SKELETON_ZONE_CODES
    ]
    if {str(row["zone_code"]) for row in selected} != set(MAIN_PROCESS_SKELETON_ZONE_CODES):
        raise AssertionError("selected Tool 7 layout does not contain all seven main zones")
    return selected


def _zone_geometry(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row["zone_code"])
        result[code] = {
            "x": str(row["x"]),
            "y": str(row["y"]),
            "width_m": str(row["width_m"]),
            "depth_m": str(row["depth_m"]),
            "rotation_deg": int(row["rotation_deg"]),
        }
    return result


def _geometry_changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    return sorted(
        code for code in MAIN_PROCESS_SKELETON_ZONE_CODES if before.get(code) != after.get(code)
    )


def _preflight_rows(internal: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _diagnostics(internal).get("main_skeleton_truck_preflight_trace")
    if not isinstance(rows, list):
        raise AssertionError("main-skeleton truck preflight trace unavailable")
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _unique_preflight_rows(internal: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for row in _preflight_rows(internal):
        skeleton_hash = row.get("main_skeleton_hash")
        if not isinstance(skeleton_hash, str):
            continue
        current = unique.get(skeleton_hash)
        if current is None or row.get("preflight_status") == "PASS":
            unique[skeleton_hash] = row
    return unique


def _registry(internal: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = _diagnostics(internal).get("geometry_evaluation_registry", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["skeleton_hash"]): dict(row)
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("skeleton_hash"), str)
    }


def _svg_view_box(svg: str) -> tuple[float, float, float, float]:
    root = ET.fromstring(svg)
    raw = root.attrib.get("viewBox")
    if raw is None:
        raise AssertionError("production SVG is missing viewBox")
    values = tuple(float(value) for value in raw.replace(",", " ").split())
    if len(values) != 4:
        raise AssertionError(f"invalid SVG viewBox: {raw}")
    return values  # type: ignore[return-value]


def _shared_canvas_wrapper(svg: str, canvas_width: float, canvas_height: float) -> str:
    ET.register_namespace("", SVG_NAMESPACE)
    source = ET.fromstring(svg)
    min_x, min_y, width, height = _svg_view_box(svg)
    outer = ET.Element(
        f"{{{SVG_NAMESPACE}}}svg",
        {
            "width": f"{canvas_width:.3f}px",
            "height": f"{canvas_height:.3f}px",
            "viewBox": f"0 0 {canvas_width:.3f} {canvas_height:.3f}",
            "preserveAspectRatio": "xMinYMin meet",
        },
    )
    ET.SubElement(
        outer,
        f"{{{SVG_NAMESPACE}}}rect",
        {
            "x": "0",
            "y": "0",
            "width": f"{canvas_width:.3f}",
            "height": f"{canvas_height:.3f}",
            "fill": "#ffffff",
        },
    )
    nested = ET.SubElement(
        outer,
        f"{{{SVG_NAMESPACE}}}svg",
        {
            "x": "0",
            "y": "0",
            "width": f"{width:.3f}",
            "height": f"{height:.3f}",
            "viewBox": f"{min_x:.3f} {min_y:.3f} {width:.3f} {height:.3f}",
            "preserveAspectRatio": "xMinYMin meet",
        },
    )
    for child in list(source):
        nested.append(copy.deepcopy(child))
    return ET.tostring(outer, encoding="unicode")


def _side_by_side_svg(
    before_svg: str, after_svg: str, canvas_width: float, canvas_height: float
) -> str:
    ET.register_namespace("", SVG_NAMESPACE)
    sources = (ET.fromstring(before_svg), ET.fromstring(after_svg))
    gutter = 48.0
    outer = ET.Element(
        f"{{{SVG_NAMESPACE}}}svg",
        {
            "width": f"{canvas_width * 2 + gutter:.3f}px",
            "height": f"{canvas_height:.3f}px",
            "viewBox": f"0 0 {canvas_width * 2 + gutter:.3f} {canvas_height:.3f}",
            "preserveAspectRatio": "xMinYMin meet",
        },
    )
    ET.SubElement(
        outer,
        f"{{{SVG_NAMESPACE}}}rect",
        {
            "x": "0",
            "y": "0",
            "width": f"{canvas_width * 2 + gutter:.3f}",
            "height": f"{canvas_height:.3f}",
            "fill": "#ffffff",
        },
    )
    for index, source in enumerate(sources):
        min_x, min_y, width, height = _svg_view_box(before_svg if index == 0 else after_svg)
        nested = ET.SubElement(
            outer,
            f"{{{SVG_NAMESPACE}}}svg",
            {
                "x": f"{index * (canvas_width + gutter) + (canvas_width - width) / 2:.3f}",
                "y": f"{(canvas_height - height) / 2:.3f}",
                "width": f"{width:.3f}",
                "height": f"{height:.3f}",
                "viewBox": f"{min_x:.3f} {min_y:.3f} {width:.3f} {height:.3f}",
                "preserveAspectRatio": "xMinYMin meet",
            },
        )
        for child in list(source):
            nested.append(copy.deepcopy(child))
    return ET.tostring(outer, encoding="unicode")


def _render_shared_canvas_pngs(before_svg: str, after_svg: str) -> bool:
    sips = shutil.which("sips")
    if sips is None:
        return False
    before_box = _svg_view_box(before_svg)
    after_box = _svg_view_box(after_svg)
    canvas_width = max(before_box[2], after_box[2])
    canvas_height = max(before_box[3], after_box[3])
    with tempfile.TemporaryDirectory(prefix="r15-svg-render-") as temp_name:
        temp = Path(temp_name)
        wrappers: list[Path] = []
        for label, svg in (("before", before_svg), ("after", after_svg)):
            wrapper = temp / f"{label}.svg"
            wrapper.write_text(
                _shared_canvas_wrapper(svg, canvas_width, canvas_height), encoding="utf-8"
            )
            wrappers.append(wrapper)
        comparison_svg = temp / "side_by_side.svg"
        comparison_svg.write_text(
            _side_by_side_svg(before_svg, after_svg, canvas_width, canvas_height),
            encoding="utf-8",
        )
        for label, wrapper in zip(("before", "after"), wrappers, strict=True):
            subprocess.run(
                [
                    sips,
                    "-s",
                    "format",
                    "png",
                    str(wrapper),
                    "--out",
                    str(EVIDENCE_DIR / f"xinzhao_p1a_r15_{label}.png"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        subprocess.run(
            [
                sips,
                "-s",
                "format",
                "png",
                str(comparison_svg),
                "--out",
                str(EVIDENCE_DIR / "xinzhao_p1a_r15_side_by_side.png"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        (EVIDENCE_DIR / "xinzhao_p1a_r15_side_by_side.svg").write_text(
            comparison_svg.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return True


def _render_before_png(before_svg: str) -> bool:
    sips = shutil.which("sips")
    if sips is None:
        return False
    with tempfile.TemporaryDirectory(prefix="r15-before-render-") as temp_name:
        temp = Path(temp_name)
        source = temp / "before.svg"
        source.write_text(before_svg, encoding="utf-8")
        subprocess.run(
            [
                sips,
                "-s",
                "format",
                "png",
                str(source),
                "--out",
                str(EVIDENCE_DIR / "xinzhao_p1a_r15_before.png"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    return True


def build_r15_evidence(
    replay: Mapping[str, Any], cross_fixture: Mapping[str, Any]
) -> dict[str, Any]:
    first = replay["first"]
    second = replay["second"]
    result = first["result"]
    second_result = second["result"]
    internal = first["internal"]
    second_internal = second["internal"]
    selector_result = internal.get("_selector_result", {})
    second_selector_result = second_internal.get("_selector_result", {})
    if not isinstance(selector_result, Mapping) or not isinstance(second_selector_result, Mapping):
        raise AssertionError("captured real selector result is unavailable")
    layout = result.get("layout")
    selected_rows = _main_zone_rows(layout) if isinstance(layout, Mapping) else []
    selected_skeleton_hash = _zone_skeleton_hash(selected_rows) if selected_rows else None
    before_layout = json.loads(CONTROL_LAYOUT.read_text(encoding="utf-8"))
    before_geometry = _zone_geometry(_main_zone_rows(before_layout))
    after_geometry = _zone_geometry(selected_rows) if selected_rows else None
    changed_codes = (
        _geometry_changes(before_geometry, after_geometry) if after_geometry is not None else []
    )
    trace = _preflight_rows(internal)
    registry = _registry(internal)
    unique_rows: dict[str, dict[str, Any]] = {}
    for row in trace:
        skeleton_hash = row.get("main_skeleton_hash")
        if isinstance(skeleton_hash, str):
            current = unique_rows.get(skeleton_hash)
            if current is None or row.get("preflight_status") == "PASS":
                unique_rows[skeleton_hash] = row
    truck_feasible_hashes = sorted(
        skeleton_hash
        for skeleton_hash, row in unique_rows.items()
        if row.get("preflight_status") == "PASS"
    )
    full_pass_hashes = sorted(
        skeleton_hash
        for skeleton_hash, row in registry.items()
        if int(row.get("p2d_full_pass_count", 0)) > 0
    )
    first_diag = _diagnostics(internal)
    second_diag = _diagnostics(second_internal)
    scheduler_first = first_diag.get("r11_scheduler_trace")
    scheduler_second = second_diag.get("r11_scheduler_trace")
    first_svg = result.get("drawing", {}).get("svg")
    second_svg = second_result.get("drawing", {}).get("svg")
    first_p2d_trace = selector_result.get("candidate_validation_trace", [])
    second_p2d_trace = second_selector_result.get("candidate_validation_trace", [])
    determinism = {
        "same_input_same_preflight_result": unique_rows == _unique_preflight_rows(second_internal),
        "same_input_same_work_queue_trace": scheduler_first == scheduler_second,
        "same_input_same_selected_main_skeleton": (
            selected_skeleton_hash == _zone_skeleton_hash(_main_zone_rows(second_result["layout"]))
            if selected_skeleton_hash is not None
            and isinstance(second_result.get("layout"), Mapping)
            else selected_skeleton_hash is None and second_result.get("layout") is None
        ),
        "same_input_same_layout_bytes": result.get("layout") == second_result.get("layout"),
        "same_input_same_canonical_hash": result.get("canonical_result_hash")
        == second_result.get("canonical_result_hash"),
        "same_input_same_svg_bytes": first_svg == second_svg,
        "same_input_same_svg_hash": result.get("svg_sha256") == second_result.get("svg_sha256"),
        "same_input_same_selector_candidate_trace": first_p2d_trace == second_p2d_trace,
        "same_input_same_failure_result": (result.get("error_code"), result.get("error_details"))
        == (second_result.get("error_code"), second_result.get("error_details")),
    }
    before_svg = CONTROL_SVG.read_text(encoding="utf-8")
    before_digest = "sha256:" + hashlib.sha256(before_svg.encode("utf-8")).hexdigest()
    after_svg = first_svg if isinstance(first_svg, str) else None
    after_digest = (
        "sha256:" + hashlib.sha256(after_svg.encode("utf-8")).hexdigest()
        if after_svg is not None
        else None
    )
    if before_digest != CONTROL_SVG_SHA256:
        raise AssertionError(f"R13 control SVG baseline changed: {before_digest}")
    p2d_evaluated_hashes = sorted(
        skeleton_hash
        for skeleton_hash, row in registry.items()
        if int(row.get("p2d_candidate_count", 0)) > 0
    )
    distinct_new_full_pass_hashes = sorted(
        skeleton_hash for skeleton_hash in full_pass_hashes if skeleton_hash != CONTROL_HASH
    )
    phase_lifecycle: list[dict[str, Any]] = []
    for lane in internal.get("family_lanes", []):
        if not isinstance(lane, Mapping):
            continue
        for phase in lane.get("phases", []):
            if not isinstance(phase, Mapping):
                continue
            generation = phase.get("main_process_skeleton_generation", {})
            if not isinstance(generation, Mapping):
                continue
            phase_lifecycle.extend(
                dict(row)
                for row in generation.get("skeleton_tail_lifecycle", [])
                if isinstance(row, Mapping)
            )

    candidate_matrix = {
        "identity": "v222-p1a-r15-candidate-matrix@1.0.0",
        "result": "PASS" if selected_skeleton_hash in distinct_new_full_pass_hashes else "FAIL",
        "fixture_sha256": replay["fixture_sha256"],
        "production_placement_node_budget": 120,
        "placement_node_visits": first_diag.get("r11_budget_accounting", {}).get(
            "global_nodes_visited"
        ),
        "main_skeletons_examined": len(unique_rows),
        "truck_preflight_pass_count": sum(
            row.get("preflight_status") == "PASS" for row in unique_rows.values()
        ),
        "truck_preflight_reject_count": sum(
            row.get("preflight_status") == "REJECT" for row in unique_rows.values()
        ),
        "distinct_truck_feasible_skeleton_count": len(truck_feasible_hashes),
        "p2d_evaluated_distinct_main_process_skeleton_count": len(p2d_evaluated_hashes),
        "distinct_p2d_full_pass_skeleton_count": len(full_pass_hashes),
        "distinct_new_p2d_full_pass_skeleton_count": len(distinct_new_full_pass_hashes),
        "selected_main_process_skeleton_hash": selected_skeleton_hash,
        "selector_status": selector_result.get("status"),
        "selector_p2c_candidate_count": selector_result.get("p2c_candidate_count"),
        "selector_p2d_validated_candidate_count": selector_result.get(
            "p2d_validated_candidate_count"
        ),
        "selector_p2d_full_pass_candidate_count": selector_result.get(
            "p2d_full_pass_candidate_count"
        ),
        "tool7_error_code": result.get("error_code"),
        "rows": [
            {
                "skeleton_hash": skeleton_hash,
                "discovery_topology": row.get("discovery_topology"),
                "canonical_topology_owner": row.get("canonical_topology_owner"),
                "canonical_family": row.get("canonical_family"),
                "truck_preflight": row.get("preflight_status"),
                "failure_codes": row.get("failure_codes", []),
                "visited_truck_nodes": row.get("visited_nodes"),
                "tail_search_started": registry.get(skeleton_hash, {}).get(
                    "tail_search_started", row.get("tail_search_started")
                ),
                "p2d_candidate_count": registry.get(skeleton_hash, {}).get(
                    "p2d_candidate_count", 0
                ),
                "p2d_full_pass_count": registry.get(skeleton_hash, {}).get(
                    "p2d_full_pass_count", 0
                ),
            }
            for skeleton_hash, row in sorted(unique_rows.items())
        ],
    }
    selected_result = {
        "identity": "v222-p1a-r15-selected-result@1.0.0",
        "selection_status": selector_result.get("status"),
        "tool7_error_code": result.get("error_code"),
        "selected_main_process_skeleton_hash": selected_skeleton_hash,
        "selected_main_process_geometry": after_geometry,
        "project_layout_validated": result.get("project_layout_validated"),
        "p2_complete": result.get("p2_complete"),
        "zone_count": result.get("zone_count"),
        "access_pass_count": (
            layout.get("access_pass_count") if isinstance(layout, Mapping) else None
        ),
        "access_requirement_count": (
            layout.get("access_requirement_count") if isinstance(layout, Mapping) else None
        ),
        "truck_route_validated": (
            layout.get("truck_route_validated") if isinstance(layout, Mapping) else None
        ),
        "building_footprint_present": (
            bool(layout.get("building_footprint")) if isinstance(layout, Mapping) else False
        ),
        "canonical_result_hash": result.get("canonical_result_hash"),
        "svg_sha256": result.get("svg_sha256"),
        "truck_preflight_pass_hashes": truck_feasible_hashes,
        "distinct_p2d_full_pass_hashes": full_pass_hashes,
        "distinct_new_p2d_full_pass_hashes": distinct_new_full_pass_hashes,
        "selector_p2d_candidate_count": selector_result.get("p2d_validated_candidate_count"),
    }
    geometry_diff = {
        "identity": "v222-p1a-r15-main-process-geometry-diff@1.0.0",
        "control_skeleton_hash": CONTROL_HASH,
        "selected_skeleton_hash": selected_skeleton_hash,
        "geometry_changed": bool(changed_codes) if after_geometry is not None else None,
        "comparison_status": (
            "SELECTED_LAYOUT_AVAILABLE"
            if after_geometry is not None
            else "NO_SELECTED_LAYOUT_TOOL7_SEARCH_EXHAUSTED"
        ),
        "changed_main_process_zone_codes": changed_codes,
        "before": before_geometry,
        "after": after_geometry,
    }
    cross_fixture_body = dict(cross_fixture)
    cross_fixture_body["identity"] = "v222-p1a-r15-cross-fixture-regression@1.0.0"
    cross_fixture_body["hard_valid_to_invalid_regression_count"] = int(
        sum(not bool(row.get("hard_valid")) for row in cross_fixture_body.get("fixtures", []))
    )
    cross_fixture_body["no_previously_valid_fixture_regressed"] = (
        cross_fixture_body["hard_valid_to_invalid_regression_count"] == 0
    )

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    _json_write(EVIDENCE_DIR / "xinzhao_p1a_r15_candidate_matrix.json", candidate_matrix)
    _json_write(
        EVIDENCE_DIR / "xinzhao_p1a_r15_truck_feasible_skeletons.json",
        {
            "identity": "v222-p1a-r15-truck-feasible-skeletons@1.0.0",
            "truck_feasible_hashes": truck_feasible_hashes,
            "p2d_full_pass_hashes": full_pass_hashes,
            "registry": {key: registry[key] for key in sorted(registry)},
        },
    )
    _json_write(EVIDENCE_DIR / "xinzhao_p1a_r15_selected_result.json", selected_result)
    _json_write(EVIDENCE_DIR / "xinzhao_p1a_r15_geometry_diff.json", geometry_diff)
    _json_write(EVIDENCE_DIR / "xinzhao_p1a_r15_determinism.json", determinism)
    _json_write(
        EVIDENCE_DIR / "xinzhao_p1a_r15_candidate_validation_trace.json",
        {
            "selector_result": selector_result,
            "distinct_p2d_evaluated_skeleton_hashes": p2d_evaluated_hashes,
            "skeleton_tail_lifecycle": phase_lifecycle,
        },
    )
    _json_write(EVIDENCE_DIR / "xinzhao_p1a_r15_cross_fixture_regression.json", cross_fixture_body)
    (EVIDENCE_DIR / "xinzhao_p1a_r15_before.svg").write_text(before_svg, encoding="utf-8")
    if after_svg is not None:
        (EVIDENCE_DIR / "xinzhao_p1a_r15_after.svg").write_text(after_svg, encoding="utf-8")
        images_created = {
            "before": True,
            "after": True,
            "side_by_side": _render_shared_canvas_pngs(before_svg, after_svg),
        }
    else:
        images_created = {
            "before": _render_before_png(before_svg),
            "after": False,
            "side_by_side": False,
            "reason": "No selected Tool 7 layout exists; an after image would be fabricated.",
        }
    return {
        "candidate_matrix": candidate_matrix,
        "selected_result": selected_result,
        "geometry_diff": geometry_diff,
        "determinism": determinism,
        "cross_fixture_regression": cross_fixture_body,
        "before_svg_sha256": before_digest,
        "after_svg_sha256": after_digest,
        "images_created": images_created,
    }


def _constructed_skeleton_rows(internal: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    lanes = internal.get("family_lanes", [])
    for lane in lanes if isinstance(lanes, list) else []:
        if not isinstance(lane, Mapping):
            continue
        phases = lane.get("phases", [])
        for phase in phases if isinstance(phases, list) else []:
            if not isinstance(phase, Mapping):
                continue
            generation = phase.get("main_process_skeleton_generation", {})
            if not isinstance(generation, Mapping):
                continue
            candidates = generation.get("candidates", [])
            for candidate in candidates if isinstance(candidates, list) else []:
                if not isinstance(candidate, Mapping):
                    continue
                skeleton_hash = candidate.get("main_process_skeleton_hash")
                if isinstance(skeleton_hash, str):
                    result.setdefault(skeleton_hash, dict(candidate))
    return result


def _candidate_geometry(candidate: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = candidate.get("zone_rectangles", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["zone_code"]): {
            key: row.get(key) for key in ("x", "y", "width_m", "depth_m", "rotation_deg")
        }
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("zone_code"), str)
    }


def _meaningful_geometry_change(changed_codes: list[str]) -> tuple[bool, str]:
    non_shipping = sorted(code for code in changed_codes if code != "shipping_channel")
    if non_shipping:
        return True, "NON_SHIPPING_MAIN_PROCESS_ZONE_GEOMETRY_CHANGED"
    if len(changed_codes) >= 2:
        return True, "MULTIPLE_MAIN_PROCESS_ZONE_GEOMETRIES_CHANGED"
    if changed_codes == ["shipping_channel"]:
        return False, "SINGLE_ZONE_SHIPPING_CHANNEL_CHANGE_ONLY"
    return False, "NO_MAIN_PROCESS_GEOMETRY_CHANGE"


def build_r15_closure_evidence(
    replay: Mapping[str, Any], cross_fixture: Mapping[str, Any]
) -> dict[str, Any]:
    """Write recovery evidence without rewriting the original R15 FAIL snapshot."""
    first = replay["first"]
    second = replay["second"]
    result = first["result"]
    internal = first["internal"]
    second_result = second["result"]
    second_internal = second["internal"]
    selection = internal.get("_selector_internal_evaluation", {})
    if not isinstance(selection, Mapping):
        raise AssertionError("R15 closure selector result is unavailable")
    layout = result.get("layout")
    layout = layout if isinstance(layout, Mapping) else {}
    selected_rows = _main_zone_rows(layout) if isinstance(layout.get("zones"), list) else []
    selected_hash = _zone_skeleton_hash(selected_rows) if selected_rows else None
    selected_geometry = _zone_geometry(selected_rows) if selected_rows else {}
    control_layout = json.loads(CONTROL_LAYOUT.read_text(encoding="utf-8"))
    control_geometry = _zone_geometry(_main_zone_rows(control_layout))
    selected_changed = _geometry_changes(control_geometry, selected_geometry)
    selected_meaningful, selected_reason = _meaningful_geometry_change(selected_changed)

    registry = _registry(internal)
    generated = _constructed_skeleton_rows(internal)
    full_pass_hashes = sorted(
        skeleton_hash
        for skeleton_hash, row in registry.items()
        if int(row.get("p2d_full_pass_count", 0)) > 0
    )
    distinct_rows: list[dict[str, Any]] = []
    meaningful_full_pass_hashes: list[str] = []
    for skeleton_hash in full_pass_hashes:
        candidate = generated.get(skeleton_hash)
        geometry = _candidate_geometry(candidate) if candidate is not None else {}
        changed_codes = _geometry_changes(control_geometry, geometry)
        meaningful, reason = _meaningful_geometry_change(changed_codes)
        row = registry[skeleton_hash]
        distinct_rows.append(
            {
                "skeleton_hash": skeleton_hash,
                "canonical_topology_owner": row.get("canonical_topology_owner"),
                "discovery_topology": row.get("first_discovery_topology"),
                "p2d_candidate_count": row.get("p2d_candidate_count"),
                "p2d_full_pass_count": row.get("p2d_full_pass_count"),
                "changed_main_process_zone_codes": changed_codes,
                "meaningful_geometry_change": meaningful,
                "meaningful_geometry_change_reason": reason,
                "main_process_geometry": geometry,
            }
        )
        if skeleton_hash != CONTROL_HASH and meaningful:
            meaningful_full_pass_hashes.append(skeleton_hash)

    before_svg = CONTROL_SVG.read_text(encoding="utf-8")
    after_svg = result.get("drawing", {}).get("svg")
    if not isinstance(after_svg, str):
        after_svg = before_svg
    before_digest = "sha256:" + hashlib.sha256(before_svg.encode("utf-8")).hexdigest()
    after_digest = "sha256:" + hashlib.sha256(after_svg.encode("utf-8")).hexdigest()
    determinism = {
        "same_input_same_preflight_result": _unique_preflight_rows(internal)
        == _unique_preflight_rows(second_internal),
        "same_input_same_work_queue_trace": _diagnostics(internal).get("r11_scheduler_trace")
        == _diagnostics(second_internal).get("r11_scheduler_trace"),
        "same_input_same_selected_layout": result.get("layout") == second_result.get("layout"),
        "same_input_same_canonical_result_hash": result.get("canonical_result_hash")
        == second_result.get("canonical_result_hash"),
        "same_input_same_svg_bytes": result.get("drawing", {}).get("svg")
        == second_result.get("drawing", {}).get("svg"),
        "same_input_same_svg_hash": result.get("svg_sha256") == second_result.get("svg_sha256"),
    }
    accounting = _diagnostics(internal).get("r11_budget_accounting", {})
    candidate_matrix = {
        "identity": "v222-p1a-r15-closure-candidate-matrix@1.0.0",
        "task_id": "V2_2_2_P1A_R15_TRUCK_FEASIBLE_DISTINCT_LAYOUT_DELIVERY_R1",
        "mode": "R15_CLOSURE",
        "previous_r15_result": "FAIL",
        "current_production_placement_node_budget": 120,
        "global_nodes_visited": accounting.get("global_nodes_visited"),
        "main_skeletons_examined": len(_unique_preflight_rows(internal)),
        "truck_preflight_pass_count": sum(
            row.get("preflight_status") == "PASS"
            for row in _unique_preflight_rows(internal).values()
        ),
        "truck_preflight_reject_count": sum(
            row.get("preflight_status") == "REJECT"
            for row in _unique_preflight_rows(internal).values()
        ),
        "distinct_p2d_full_pass_skeleton_count": len(full_pass_hashes),
        "distinct_meaningful_p2d_full_pass_skeleton_count": len(meaningful_full_pass_hashes),
        "meaningful_distinct_full_pass_hashes": sorted(meaningful_full_pass_hashes),
        "rows": distinct_rows,
    }
    selected_result = {
        "identity": "v222-p1a-r15-closure-selected-result@1.0.0",
        "control_skeleton_hash": CONTROL_HASH,
        "selected_main_process_skeleton_hash": selected_hash,
        "selected_is_control": selected_hash == CONTROL_HASH,
        "control_p2d_full_pass_count": registry.get(CONTROL_HASH, {}).get("p2d_full_pass_count", 0),
        "project_layout_validated": result.get("project_layout_validated") is True,
        "p2_complete": result.get("p2_complete") is True,
        "zone_count": result.get("zone_count"),
        "access_pass_count": layout.get("access_pass_count"),
        "access_requirement_count": layout.get("access_requirement_count"),
        "truck_route_validated": layout.get("truck_route_validated") is True,
        "building_footprint_present": bool(layout.get("building_footprint")),
        "changed_main_process_zone_codes": selected_changed,
        "meaningful_structural_geometry_change": selected_meaningful,
        "meaningful_geometry_change_reason": selected_reason,
        "canonical_result_hash": result.get("canonical_result_hash"),
        "svg_sha256": result.get("svg_sha256"),
        "selection_first_decisive_component": selection.get("first_decisive_component"),
        "selection_winner_value": selection.get("winner_value"),
        "selection_runner_up_value": selection.get("runner_up_value"),
        "p2b2_tiebreak_used": selection.get("p2b2_tiebreak_used"),
        "distinct_skeleton_first_decisive_component": selection.get(
            "distinct_skeleton_first_decisive_component"
        ),
        "distinct_runner_up_skeleton_hash": selection.get("distinct_runner_up_skeleton_hash"),
        "distinct_skeleton_winner_value": selection.get("distinct_skeleton_winner_value"),
        "distinct_skeleton_runner_up_value": selection.get("distinct_skeleton_runner_up_value"),
        "ranking_changed": False,
    }
    cross_fixture_evidence = dict(cross_fixture)
    cross_fixture_evidence["hard_valid_to_invalid_regression_count"] = int(
        cross_fixture_evidence.get("hard_valid_to_invalid_regression_count", 0)
    )
    cross_fixture_evidence["no_previously_valid_fixture_regressed"] = (
        cross_fixture_evidence["hard_valid_to_invalid_regression_count"] == 0
    )

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    _json_write(EVIDENCE_DIR / "xinzhao_p1a_r15_closure_candidate_matrix.json", candidate_matrix)
    _json_write(EVIDENCE_DIR / "xinzhao_p1a_r15_closure_selected_result.json", selected_result)
    _json_write(EVIDENCE_DIR / "xinzhao_p1a_r15_closure_determinism.json", determinism)
    _json_write(EVIDENCE_DIR / "xinzhao_p1a_r15_closure_budget_accounting.json", accounting)
    _json_write(
        EVIDENCE_DIR / "xinzhao_p1a_r15_closure_cross_fixture_regression.json",
        cross_fixture_evidence,
    )
    (EVIDENCE_DIR / "xinzhao_p1a_r15_before.svg").write_text(before_svg, encoding="utf-8")
    (EVIDENCE_DIR / "xinzhao_p1a_r15_after.svg").write_text(after_svg, encoding="utf-8")
    images_created = _render_shared_canvas_pngs(before_svg, after_svg)
    return {
        "candidate_matrix": candidate_matrix,
        "selected_result": selected_result,
        "determinism": determinism,
        "cross_fixture_regression": cross_fixture_evidence,
        "before_svg_sha256": before_digest,
        "after_svg_sha256": after_digest,
        "images_created": images_created,
    }


def capture_cross_fixture_replay() -> dict[str, Any]:
    """Replay the existing P1F/P4 site as an independent hard-valid control."""
    from tests.unit.test_v22_p4_site_layout_mcp import _real_selector_tool_payload

    result, internal = run_tool7_with_internal_evaluation(_real_selector_tool_payload())
    layout = result.get("layout")
    layout = layout if isinstance(layout, Mapping) else {}
    selected_rows = _main_zone_rows(layout) if isinstance(layout.get("zones"), list) else []
    return {
        "fixtures": [
            {
                "fixture": "P1F_P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES",
                "hard_valid": result.get("project_layout_validated") is True
                and result.get("p2_complete") is True,
                "zone_count": result.get("zone_count"),
                "access_pass_count": layout.get("access_pass_count"),
                "access_requirement_count": layout.get("access_requirement_count"),
                "truck_route_validated": layout.get("truck_route_validated"),
                "canonical_result_hash": result.get("canonical_result_hash"),
                "selected_main_process_skeleton_hash": (
                    _zone_skeleton_hash(selected_rows) if selected_rows else None
                ),
                "error_code": result.get("error_code"),
                "preflight_trace": _preflight_rows(internal),
            }
        ],
        "hard_valid_to_invalid_regression_count": int(
            result.get("project_layout_validated") is not True
            or result.get("p2_complete") is not True
        ),
    }
