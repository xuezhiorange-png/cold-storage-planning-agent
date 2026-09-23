"""P1F regression for authoritative loading-face visibility in context insets."""

from __future__ import annotations

import hashlib
import os
import xml.etree.ElementTree as ET
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.aily.application import site_layout_preview
from cold_storage.modules.aily.application.preview_bundle import assemble_preview_context
from cold_storage.modules.aily.application.site_layout_preview import (
    _bound_truck_input,
    preview_site_layout,
)
from cold_storage.modules.aily.application.stage_preview import execute_zone_preview_authority
from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.drawing_lint import lint_validated_layout_drawing
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.application.svg_projection import project_validated_layout_to_svg
from cold_storage.modules.layout.domain.svg_projection import SvgProjectionTransformV1
from tests.unit.test_v22_p1f_project_truck_input import truck_input
from tests.unit.test_v22_p2d_access_routing import (
    _placement,
    _site_input,
)
from tests.unit.test_v22_p2d_access_routing import (
    representative_context as p2d_representative_context,
)
from tests.unit.test_v22_p4_site_layout_mcp import (
    _FIVE_KEYS,
    _real_selector_site_constraints,
    _real_selector_tool_payload,
)

REPRESENTATIVE_BASELINE_HASHES = {
    "PRESENTATION": "sha256:97e7c9083050dc1e1edd01c8880f4c7aa1d2526d72e8eff809ee792bda8cf59e",
    "MOBILE_PREVIEW": "sha256:db6a39e7ad38ca8c0b0fc2063d4189bdd295691d92aaf7a922e59d7c200954c8",
    "ENGINEERING_SHEET": "sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3",
    "ENGINEERING_REVIEW": "sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d",
}
REPRESENTATIVE_CORRECTED_HASHES = {
    **REPRESENTATIVE_BASELINE_HASHES,
    "PRESENTATION": "sha256:e89ca6e1f797fedca41780d2027e728b3a3f37db19c979c0fa9dc863531b2f1a",
    "MOBILE_PREVIEW": "sha256:dc0b5313113e69fdfc6c59b88f4bd911316d74b71762bae83768c1bdd70153f2",
}


def _full_pass(layout: Any) -> bool:
    body = layout.to_dict() if hasattr(layout, "to_dict") else layout
    return (
        isinstance(body, dict)
        and body.get("project_layout_validated") is True
        and body.get("p2_complete") is True
        and body.get("zone_count") == 12
    )


def _selector_site_scenario() -> tuple[str, Any, Any]:
    payload = _real_selector_tool_payload()
    result = preview_site_layout(payload)
    assert result["validated_layout_selected"] is True
    assert result["project_layout_validated"] is True
    assert result["p2_complete"] is True
    trace = result["selection"]["candidate_validation_trace"]
    assert len(trace) >= 2
    assert trace[0]["p2d_full_pass"] is False
    assert any(item["p2d_full_pass"] is True for item in trace[1:])

    context = assemble_preview_context(_FIVE_KEYS)
    zone_plan = site_layout_preview._zone_plan_snapshot(execute_zone_preview_authority(context))
    _, p1f_input = _bound_truck_input(payload["truck_access"], payload["truck_maneuver"])
    handoff = build_p1_project_handoff(zone_plan, p1f_input)
    site = _real_selector_site_constraints()
    geometry = validate_site_geometry(
        {"site_constraints": site, "truck_access": p1f_input},
        zone_plan,
        p1_handoff=handoff,
    )
    return "P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES", result["layout"], geometry


@pytest.fixture(scope="module")
def authoritative_full_pass_scenarios() -> tuple[tuple[str, Any, Any], ...]:
    zone_plan, handoff, original_geometry, placement, binding = (
        p2d_representative_context.__wrapped__()
    )
    rectangular = route_site_placement(
        zone_plan,
        handoff,
        original_geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    assert _full_pass(rectangular)

    concave_site = deepcopy(_site_input())
    concave_site["site_boundary"] = {
        "type": "polygon",
        "points": [
            {"x": 0, "y": 0},
            {"x": 220, "y": 0},
            {"x": 220, "y": 100},
            {"x": 160, "y": 100},
            {"x": 160, "y": 160},
            {"x": 0, "y": 160},
        ],
    }
    concave_geometry = validate_site_geometry(
        {"site_constraints": concave_site, "truck_access": truck_input()},
        zone_plan,
        p1_handoff=handoff,
    )
    concave_placement = _placement(zone_plan, handoff, concave_geometry)
    concave_layout = route_site_placement(
        zone_plan,
        handoff,
        concave_geometry,
        concave_placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    assert _full_pass(concave_layout)

    selector = _selector_site_scenario()
    assert _full_pass(selector[1])
    return (
        ("P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE", rectangular, original_geometry),
        ("P3_EXISTING_CONCAVE_SITE_VALIDATED_LAYOUT", concave_layout, concave_geometry),
        selector,
    )


def _element(root: ET.Element, element_id: str) -> ET.Element:
    found = next((item for item in root.iter() if item.get("id") == element_id), None)
    assert found is not None, element_id
    return found


def _source_loading_face_mm(layout: Any) -> tuple[tuple[int, int], tuple[int, int]]:
    body = layout.to_dict() if hasattr(layout, "to_dict") else layout
    segment = body["shipping_loading_face_segment"]
    result: list[tuple[int, int]] = []
    for endpoint in (segment["start"], segment["end"]):
        coordinates = tuple(Decimal(str(endpoint[axis])) * 1000 for axis in ("x", "y"))
        assert all(value == value.to_integral_value() for value in coordinates)
        result.append((int(coordinates[0]), int(coordinates[1])))
    return result[0], result[1]


def _expected_context_endpoints(layout: Any, projection: dict[str, Any]):
    geometry = projection["engineering_geometry_bounds"]
    inset = projection["context_inset"]
    padding = Decimal(str(inset["inner_padding"]))
    transform = SvgProjectionTransformV1(
        min_x_m=Decimal(str(geometry["min_x_m"])),
        max_y_m=Decimal(str(geometry["max_y_m"])),
        scale=Decimal(str(inset["scale"])),
        offset_x_px=Decimal(str(inset["x"])) + padding,
        offset_y_px=Decimal(str(inset["y"])) + padding,
    )
    return tuple(transform.point(point) for point in _source_loading_face_mm(layout))


def _write_optional_representative_evidence(projection: dict[str, Any], profile: str) -> None:
    evidence_dir_value = os.environ.get("P1F_CONTEXT_CORRECTION_EVIDENCE_DIR")
    if not evidence_dir_value:
        return
    import fitz

    evidence_dir = Path(evidence_dir_value)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    svg_path = evidence_dir / f"after_{profile.lower()}.svg"
    png_path = evidence_dir / f"after_{profile.lower()}.png"
    svg_bytes = str(projection["svg"]).encode("utf-8")
    svg_path.write_bytes(svg_bytes)
    document = fitz.open(stream=svg_bytes, filetype="svg")
    page = document[0]
    scale = min(2400 / page.rect.width, 2400 / page.rect.height)
    page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(png_path)
    (evidence_dir / f"after_{profile.lower()}.sha256").write_text(
        f"svg=sha256:{hashlib.sha256(svg_bytes).hexdigest()}\n"
        f"png=sha256:{hashlib.sha256(png_path.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("profile", ("PRESENTATION", "MOBILE_PREVIEW"))
def test_all_authoritative_p1f_context_insets_show_the_loading_face(
    authoritative_full_pass_scenarios: tuple[tuple[str, Any, Any], ...], profile: str
) -> None:
    assert len(authoritative_full_pass_scenarios) == 3
    for scenario_id, layout, geometry in authoritative_full_pass_scenarios:
        before_hash = (
            layout.canonical_result_hash
            if hasattr(layout, "canonical_result_hash")
            else layout["canonical_result_hash"]
        )
        first = project_validated_layout_to_svg(
            layout, site_geometry=geometry, page_profile=profile
        ).to_dict()
        replay = project_validated_layout_to_svg(
            layout, site_geometry=geometry, page_profile=profile
        ).to_dict()

        assert first["context_inset"]
        assert first["svg"] == replay["svg"]
        assert first["svg_sha256"] == replay["svg_sha256"]
        assert _full_pass(layout)
        after_hash = (
            layout.canonical_result_hash
            if hasattr(layout, "canonical_result_hash")
            else layout["canonical_result_hash"]
        )
        assert after_hash == before_hash

        root = ET.fromstring(str(first["svg"]))
        inset_frame = _element(root, "site-context-inset-frame")
        context_group = _element(root, "site-context-layout")
        loading_face = _element(root, "context-shipping-loading-face")
        assert inset_frame is not None
        assert loading_face in list(context_group)

        start, end = _expected_context_endpoints(layout, first)
        actual = tuple(Decimal(loading_face.attrib[name]) for name in ("x1", "y1", "x2", "y2"))
        assert actual == (*start, *end), scenario_id

        lint = lint_validated_layout_drawing(first, page_profile=profile)
        assert lint.drawing_lint_gate == "PASS"
        assert lint.error_count == 0
        assert lint.warning_count == 0
        assert lint.unavailable_required_fact_count == 0

        if scenario_id == "P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE":
            _write_optional_representative_evidence(first, profile)


def test_engineering_sheet_context_loading_face_is_unchanged_and_review_has_no_inset(
    authoritative_full_pass_scenarios: tuple[tuple[str, Any, Any], ...],
) -> None:
    _, representative, geometry = authoritative_full_pass_scenarios[0]
    sheet = project_validated_layout_to_svg(
        representative, site_geometry=geometry, page_profile="ENGINEERING_SHEET"
    ).to_dict()
    review = project_validated_layout_to_svg(
        representative, site_geometry=geometry, page_profile="ENGINEERING_REVIEW"
    ).to_dict()
    sheet_root = ET.fromstring(str(sheet["svg"]))
    review_root = ET.fromstring(str(review["svg"]))

    _element(sheet_root, "context-shipping-loading-face")
    _element(sheet_root, "context-shipping-loading-face-visible")
    assert sheet["svg_sha256"] == REPRESENTATIVE_BASELINE_HASHES["ENGINEERING_SHEET"]

    assert not review["context_inset"]
    assert not any(
        element.get("id")
        in {
            "site-context-inset-frame",
            "context-shipping-loading-face",
            "context-shipping-loading-face-visible",
        }
        for element in review_root.iter()
    )
    assert review["svg_sha256"] == REPRESENTATIVE_BASELINE_HASHES["ENGINEERING_REVIEW"]


def test_presentation_and_mobile_hashes_change_only_for_the_added_context_line(
    authoritative_full_pass_scenarios: tuple[tuple[str, Any, Any], ...],
) -> None:
    _, representative, geometry = authoritative_full_pass_scenarios[0]
    for profile in ("PRESENTATION", "MOBILE_PREVIEW"):
        first = project_validated_layout_to_svg(
            representative, site_geometry=geometry, page_profile=profile
        ).to_dict()
        assert first["svg_sha256"] != REPRESENTATIVE_BASELINE_HASHES[profile]
        assert first["svg_sha256"] == REPRESENTATIVE_CORRECTED_HASHES[profile]
        _element(ET.fromstring(str(first["svg"])), "context-shipping-loading-face")
