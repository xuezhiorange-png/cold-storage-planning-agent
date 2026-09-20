"""V2.2.1 P1A canvas, viewBox and page-composition tests."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from decimal import Decimal

import pytest

from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.application.svg_projection import (
    project_validated_layout_to_svg,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from tests.unit.test_v22_p1f_project_truck_input import truck_input
from tests.unit.test_v22_p2d_access_routing import (
    _placement,
    _site_input,
)
from tests.unit.test_v22_p2d_access_routing import (
    representative_context as p2d_representative_context,
)

SVG_NS = "{http://www.w3.org/2000/svg}"


def _render(layout_and_geometry, *, profile: str = "PRESENTATION") -> dict[str, object]:
    layout, geometry = layout_and_geometry
    return project_validated_layout_to_svg(
        layout,
        site_geometry=geometry,
        page_profile=profile,
    ).to_dict()


def _rect_overlap(left: dict[str, object], right: dict[str, object]) -> bool:
    lx = Decimal(str(left["x"]))
    ly = Decimal(str(left["y"]))
    lw = Decimal(str(left["width"]))
    lh = Decimal(str(left["height"]))
    rx = Decimal(str(right["x"]))
    ry = Decimal(str(right["y"]))
    rw = Decimal(str(right["width"]))
    rh = Decimal(str(right["height"]))
    return not (lx + lw <= rx or rx + rw <= lx or ly + lh <= ry or ry + rh <= ly)


def _element_by_id(root: ET.Element, element_id: str) -> ET.Element:
    for element in root.iter():
        if element.get("id") == element_id:
            return element
    raise AssertionError(f"missing SVG element {element_id}")


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


def test_engineering_and_page_bounds_are_separate(validated_layout_and_geometry):
    body = _render(validated_layout_and_geometry)
    geometry_bounds = body["engineering_geometry_bounds"]
    drawing_bounds = body["engineering_drawing_bounds"]
    page_bounds = body["page_layout_bounds"]

    assert geometry_bounds["max_x_m"] < drawing_bounds["max_x_m"]
    assert drawing_bounds["max_x_m"] < page_bounds["max_x_m"]
    assert body["drawing_bounds"] == drawing_bounds
    assert Decimal(str(body["main_drawing_occupancy"])) >= Decimal("0.70")
    assert Decimal(str(body["main_drawing_occupancy"])) <= Decimal("0.88")
    assert Decimal(str(body["source_geometry_occupancy"])) >= Decimal("0.70")


def test_page_furniture_is_outside_main_drawing_and_non_overlapping(
    validated_layout_and_geometry,
):
    body = _render(validated_layout_and_geometry)
    drawing = body["engineering_drawing_rect"]
    furniture = list(body["page_furniture"].values())

    assert furniture
    assert all(
        Decimal(str(rect["x"])) >= Decimal(str(drawing["x"])) + Decimal(str(drawing["width"]))
        for rect in furniture
    )
    for index, left in enumerate(furniture):
        for right in furniture[index + 1 :]:
            assert not _rect_overlap(left, right)
    assert body["title_block_overlap"] is False
    assert body["area_table_overlap"] is False
    assert body["legend_overlap"] is False
    assert body["page_furniture_overlap"] is False


def test_mobile_preview_keeps_plan_prominent_and_collapses_page_furniture(
    validated_layout_and_geometry,
):
    body = _render(validated_layout_and_geometry, profile="MOBILE_PREVIEW")
    assert body["page_profile"] == "MOBILE_PREVIEW"
    assert body["page_furniture"] == {}
    assert Decimal(str(body["main_drawing_occupancy"])) >= Decimal("0.80")
    root = ET.fromstring(body["svg"])
    assert not any(
        element.get("id") in {"legend", "area-schedule", "title-block"} for element in root.iter()
    )


def test_engineering_sheet_retains_schedule_legend_and_title(
    validated_layout_and_geometry,
):
    body = _render(validated_layout_and_geometry, profile="ENGINEERING_SHEET")
    assert body["page_profile"] == "ENGINEERING_SHEET"
    assert Decimal(str(body["main_drawing_occupancy"])) >= Decimal("0.70")
    root = ET.fromstring(body["svg"])
    for element_id in ("legend", "area-schedule", "title-block"):
        _element_by_id(root, element_id)


def test_profiles_do_not_change_source_geometry_or_projection_coordinates(
    validated_layout_and_geometry,
):
    presentation = _render(validated_layout_and_geometry, profile="PRESENTATION")
    mobile = _render(validated_layout_and_geometry, profile="MOBILE_PREVIEW")
    sheet = _render(validated_layout_and_geometry, profile="ENGINEERING_SHEET")

    for field in (
        "source_validated_layout_hash",
        "source_zone_plan_hash",
        "source_p1_handoff_hash",
        "source_site_geometry_hash",
        "source_placement_result_hash",
        "source_truck_maneuver_binding_hash",
        "engineering_geometry_bounds",
    ):
        assert presentation[field] == mobile[field] == sheet[field]

    for element_id in (
        "site-boundary-polygon",
        "effective-buildable-boundary",
        "building-footprint-polygon",
        "zone-footprint-primary_precooling_room",
        "shipping-loading-face",
    ):
        values = []
        for body in (presentation, mobile, sheet):
            values.append(_element_by_id(ET.fromstring(body["svg"]), element_id).attrib)
        assert values[0] == values[1] == values[2]


def test_concave_site_remains_complete_under_page_composition(representative_context):
    zone_plan, handoff, _, _, binding = representative_context
    site_input = deepcopy(_site_input())
    site_input["site_boundary"] = {
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
    geometry = validate_site_geometry(
        {"site_constraints": site_input, "truck_access": truck_input()},
        zone_plan,
        p1_handoff=handoff,
    )
    placement = _placement(zone_plan, handoff, geometry)
    layout = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    body = project_validated_layout_to_svg(
        layout,
        site_geometry=geometry,
        page_profile="PRESENTATION",
    ).to_dict()
    assert Decimal(str(body["main_drawing_occupancy"])) >= Decimal("0.70")
    site = _element_by_id(ET.fromstring(body["svg"]), "site-boundary-polygon")
    assert len(site.get("points", "").split()) == 12


def test_same_profile_input_is_byte_and_hash_deterministic(validated_layout_and_geometry):
    first = _render(validated_layout_and_geometry, profile="PRESENTATION")
    second = _render(validated_layout_and_geometry, profile="PRESENTATION")
    assert first["svg"] == second["svg"]
    assert first["svg_sha256"] == second["svg_sha256"]
    assert first["same_input_same_svg_bytes"] is True
    assert first["same_input_same_svg_hash"] is True


def test_invalid_page_profile_fails_closed(validated_layout_and_geometry):
    layout, geometry = validated_layout_and_geometry
    with pytest.raises(LayoutAuthorityError) as error:
        project_validated_layout_to_svg(
            layout,
            site_geometry=geometry,
            page_profile="UNAUTHORIZED_PROFILE",
        )
    assert error.value.code == "SVG_PAGE_PROFILE_INVALID"
