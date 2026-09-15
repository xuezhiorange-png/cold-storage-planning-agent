"""V2.2 P3 deterministic validated-layout SVG projection tests."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from copy import deepcopy
from decimal import Decimal

import pytest

from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.application.svg_projection import project_validated_layout_to_svg
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.svg_projection import (
    LAYER_ORDER,
    SvgProjectionTransformV1,
)
from tests.unit.test_v22_p1f_project_truck_input import truck_input
from tests.unit.test_v22_p2d_access_routing import (
    _placement,
    _site_input,
)
from tests.unit.test_v22_p2d_access_routing import (
    representative_context as p2d_representative_context,
)

SVG_NS = "{http://www.w3.org/2000/svg}"
UNSAFE_SVG_TOKENS = (
    "<script",
    "<foreignObject",
    "javascript:",
    " onload=",
    " onclick=",
    ' href="http',
    " xlink:href",
)


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


def _rendered(validated_layout_and_geometry):
    layout, geometry = validated_layout_and_geometry
    return project_validated_layout_to_svg(layout, site_geometry=geometry)


def _elements_with_id(root: ET.Element, element_id: str) -> list[ET.Element]:
    return [element for element in root.iter() if element.get("id") == element_id]


def test_representative_layout_renders_all_required_layers_and_geometry(
    validated_layout_and_geometry,
):
    projection = _rendered(validated_layout_and_geometry)
    body = projection.to_dict()
    root = ET.fromstring(body["svg"])

    assert body["identity"] == "validated-layout-svg-projection@1.0.0"
    assert body["project_layout_validated"] is True
    assert body["p2_complete"] is True
    assert body["zone_count"] == 12
    assert body["portal_count"] == 22
    assert body["corridor_count"] == 1
    assert body["truck_maneuver_count"] == 3
    assert body["projection_only"] is True
    assert body["engineering_coordinates_mutated"] is False
    assert body["layer_order"] == list(LAYER_ORDER)

    for layer in LAYER_ORDER:
        assert _elements_with_id(root, layer)
    for code in (
        "office",
        "changing_room",
        "primary_precooling_room",
        "secondary_precooling_room",
        "raw_fruit_buffer",
        "sorting_packaging_room",
        "coating_room",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "packaging_material_storage",
        "shipping_channel",
    ):
        assert _elements_with_id(root, f"zone-{code}")
        assert _elements_with_id(root, f"label-zone-{code}")
        assert _elements_with_id(root, f"dimension-zone-{code}")
    assert _elements_with_id(root, "building-footprint-polygon")
    assert _elements_with_id(root, "main-entrance")
    assert _elements_with_id(root, "truck-entrance")
    assert _elements_with_id(root, "shipping-loading-face")
    assert _elements_with_id(root, "title-block")


def test_svg_is_static_well_formed_and_has_no_unsafe_execution_surface(
    validated_layout_and_geometry,
):
    svg = _rendered(validated_layout_and_geometry).to_dict()["svg"]
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert all(token not in svg for token in UNSAFE_SVG_TOKENS)
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg"
    assert root.get("viewBox") == _rendered(validated_layout_and_geometry).to_dict()["view_box"]
    assert "14.700000000000001" not in svg


def test_projection_is_byte_and_hash_deterministic(validated_layout_and_geometry):
    first = _rendered(validated_layout_and_geometry)
    second = _rendered(validated_layout_and_geometry)
    assert first.to_dict()["svg"] == second.to_dict()["svg"]
    assert first.to_dict()["svg_sha256"] == second.to_dict()["svg_sha256"]
    assert first.to_dict()["same_input_same_svg_bytes"] is True
    assert first.to_dict()["same_input_same_svg_hash"] is True
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash


def test_engineering_y_is_inverted_without_mutating_source_coordinates():
    transform = SvgProjectionTransformV1(Decimal("-8"), Decimal("18"))
    bottom = transform.point((1000, 1000))
    top = transform.point((1000, 17000))
    assert bottom[0] == top[0]
    assert bottom[1] > top[1]


def test_concave_site_boundary_is_projected_from_validated_geometry(
    representative_context,
):
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
    concave_geometry = validate_site_geometry(
        {"site_constraints": site_input, "truck_access": truck_input()},
        zone_plan,
        p1_handoff=handoff,
    )
    placement = _placement(zone_plan, handoff, concave_geometry)
    layout = route_site_placement(
        zone_plan,
        handoff,
        concave_geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    projection = project_validated_layout_to_svg(layout, site_geometry=concave_geometry)
    root = ET.fromstring(projection.to_dict()["svg"])
    site_polygon = _elements_with_id(root, "site-boundary-polygon")[0]
    assert len(site_polygon.get("points", "").split()) == 12


@pytest.mark.parametrize("flag", ["project_layout_validated", "p2_complete"])
def test_unvalidated_layout_is_rejected(validated_layout_and_geometry, flag):
    layout, geometry = validated_layout_and_geometry
    payload = layout.to_dict()
    payload.pop("canonical_result_hash")
    payload[flag] = False
    with pytest.raises(LayoutAuthorityError) as error:
        project_validated_layout_to_svg(payload, site_geometry=geometry)
    assert error.value.code == "VALIDATED_LAYOUT_REQUIRED"


def test_source_hash_tampering_is_rejected(validated_layout_and_geometry):
    layout, geometry = validated_layout_and_geometry
    payload = layout.to_dict()
    payload["zones"][0]["x"] = "999"
    with pytest.raises(LayoutAuthorityError) as error:
        project_validated_layout_to_svg(payload, site_geometry=geometry)
    assert error.value.code == "P2D_RESULT_INTEGRITY_MISMATCH"


def test_projection_keeps_source_hashes_and_display_labels_non_authoritative(
    validated_layout_and_geometry,
):
    layout, _ = validated_layout_and_geometry
    body = _rendered(validated_layout_and_geometry).to_dict()
    source = layout.to_dict()
    for field in (
        "source_zone_plan_hash",
        "source_p1_handoff_hash",
        "source_site_geometry_hash",
        "source_objective_profile_hash",
        "source_placement_result_hash",
        "source_truck_maneuver_binding_hash",
    ):
        assert body[field] == source[field]
    assert body["display_label_authority"] is False
    assert body["engineering_semantics_changed"] is False
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", body["source_validated_layout_hash"])
