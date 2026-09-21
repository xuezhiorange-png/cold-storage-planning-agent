"""V2.2.1 P1B monochrome CAD visual hierarchy tests."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from decimal import Decimal

import pytest

from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.svg_projection import (
    project_validated_layout_to_svg,
)
from cold_storage.modules.layout.domain.svg_projection import (
    SVG_COLOR_MODE,
    SVG_NO_BUILD_HATCH_COLOR,
    SVG_STROKE_W0,
    SVG_STROKE_W1,
    SVG_STROKE_W2,
    SVG_STROKE_W3,
    SVG_STROKE_W4,
    SVG_STROKE_W5,
    SVG_STYLE_ID,
    SVG_STYLE_NAME,
    SvgDrawingThemeV1,
)
from tests.unit.test_v22_p2d_access_routing import (
    representative_context as p2d_representative_context,
)

SVG_NS = "{http://www.w3.org/2000/svg}"
BRIGHT_LEGACY_PAINTS = {
    "#dbeafe",
    "#bfdbfe",
    "#fef3c7",
    "#7c3aed",
    "#059669",
    "#ea580c",
    "#fecaca",
}


@pytest.fixture(scope="module")
def representative_context():
    return p2d_representative_context.__wrapped__()


@pytest.fixture(scope="module")
def validated_layout_and_geometry(representative_context):
    zone_plan, handoff, geometry, placement, binding = representative_context
    layout = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    return layout, geometry


def _render(validated_layout_and_geometry, *, profile: str = "PRESENTATION"):
    layout, geometry = validated_layout_and_geometry
    return project_validated_layout_to_svg(
        layout,
        site_geometry=geometry,
        page_profile=profile,
    ).to_dict()


def _element_by_id(root: ET.Element, element_id: str) -> ET.Element:
    for element in root.iter():
        if element.get("id") == element_id:
            return element
    raise AssertionError(f"missing SVG element {element_id}")


def _paint_values(svg: str) -> set[str]:
    root = ET.fromstring(svg)
    values: set[str] = set()
    for element in root.iter():
        for name in ("fill", "stroke"):
            value = element.get(name)
            if value and value != "none" and not value.startswith("url(#"):
                values.add(value)
    return values


def _is_grayscale(value: str) -> bool:
    match = re.fullmatch(r"#([0-9A-Fa-f]{6})", value)
    if match is None:
        return False
    red, green, blue = (int(match.group(1)[offset : offset + 2], 16) for offset in (0, 2, 4))
    return red == green == blue


def test_default_style_is_monochrome_and_profile_accent_is_scoped(
    validated_layout_and_geometry,
):
    presentation = _render(validated_layout_and_geometry)
    mobile = _render(validated_layout_and_geometry, profile="MOBILE_PREVIEW")
    sheet = _render(validated_layout_and_geometry, profile="ENGINEERING_SHEET")
    review = _render(validated_layout_and_geometry, profile="ENGINEERING_REVIEW")

    assert presentation["style_id"] == SVG_STYLE_ID == "LAYOUT_DRAWING_STYLE_V1"
    assert presentation["style_name"] == SVG_STYLE_NAME == "CAD_FACTORY_LAYOUT"
    assert presentation["color_mode"] == SVG_COLOR_MODE == "MONOCHROME_PRIMARY"
    assert presentation["presentation_accent_color_count"] == 0
    assert mobile["mobile_accent_color_count"] == 0
    assert sheet["review_accent_visible"] is False
    assert review["review_accent_visible"] is True
    assert review["engineering_review_accent_color_count"] == 1

    assert all(_is_grayscale(value) for value in _paint_values(presentation["svg"]))
    assert all(_is_grayscale(value) for value in _paint_values(mobile["svg"]))
    assert not (BRIGHT_LEGACY_PAINTS & _paint_values(presentation["svg"]))
    assert not (BRIGHT_LEGACY_PAINTS & _paint_values(mobile["svg"]))
    assert "#B3261E" not in _paint_values(presentation["svg"])
    assert "#B3261E" not in _paint_values(mobile["svg"])
    assert "#B3261E" in _paint_values(review["svg"])
    assert _paint_values(sheet["svg"]).issubset(_paint_values(presentation["svg"]) | {"#777777"})


def test_default_palette_and_stroke_hierarchy_are_versioned(
    validated_layout_and_geometry,
):
    theme = SvgDrawingThemeV1()
    assert theme.background == "#FFFFFF"
    assert theme.zone_fill == "#FAFAFA"
    assert theme.cold_zone_fill == "#F3F3F3"
    assert theme.corridor_fill == "#F7F7F7"
    assert theme.building_outline == "#111111"
    assert theme.site_outline == "#555555"
    assert theme.obstacle_fill == "#999999"
    assert theme.portal_stroke == "#666666"
    assert theme.loading_face == "#222222"
    assert theme.entrance_stroke == "#555555"
    assert SVG_NO_BUILD_HATCH_COLOR == "#B5B5B5"

    weights = (
        SVG_STROKE_W5,
        SVG_STROKE_W4,
        SVG_STROKE_W3,
        SVG_STROKE_W2,
        SVG_STROKE_W1,
        SVG_STROKE_W0,
    )
    assert all(left > right for left, right in zip(weights, weights[1:], strict=False))

    body = _render(validated_layout_and_geometry)
    root = ET.fromstring(body["svg"])
    assert (
        Decimal(_element_by_id(root, "building-footprint-polygon").get("stroke-width", "0"))
        == SVG_STROKE_W5
    )
    assert (
        Decimal(_element_by_id(root, "zone-footprint-office").get("stroke-width", "0"))
        == SVG_STROKE_W3
    )
    assert (
        Decimal(_element_by_id(root, "dimension-zone-office").find("*").get("stroke-width", "0"))
        == SVG_STROKE_W1
    )
    hatch_line = next(
        element
        for element in root.iter()
        if element.get("id") is None
        and element.tag == f"{SVG_NS}line"
        and element.get("stroke") == SVG_NO_BUILD_HATCH_COLOR
    )
    assert Decimal(hatch_line.get("stroke-width", "0")) == SVG_STROKE_W0


def test_visual_style_does_not_change_engineering_geometry_or_composition(
    validated_layout_and_geometry,
):
    presentation = _render(validated_layout_and_geometry)
    mobile = _render(validated_layout_and_geometry, profile="MOBILE_PREVIEW")
    review = _render(validated_layout_and_geometry, profile="ENGINEERING_REVIEW")

    for field in (
        "source_validated_layout_hash",
        "source_zone_plan_hash",
        "source_p1_handoff_hash",
        "source_site_geometry_hash",
        "source_placement_result_hash",
        "source_truck_maneuver_binding_hash",
        "engineering_geometry_bounds",
        "primary_plan_bounds",
        "source_drawing_bounds",
    ):
        assert presentation[field] == mobile[field] == review[field]
    assert presentation["page_layout_bounds"] != mobile["page_layout_bounds"]
    assert presentation["source_engineering_geometry_changed"] is False
    assert presentation["engineering_coordinates_mutated"] is False
    assert presentation["same_input_same_svg_bytes"] is True
    assert presentation["same_input_same_svg_hash"] is True
