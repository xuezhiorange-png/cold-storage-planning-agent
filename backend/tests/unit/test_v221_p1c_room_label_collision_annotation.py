"""V2.2.1 P1C deterministic room-label and annotation tests."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal

import pytest

from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.svg_projection import (
    project_validated_layout_to_svg,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.domain.svg_projection import (
    SvgProjectionTransformV1,
    _build_room_label_plan,
)
from tests.unit.test_v22_p2d_access_routing import (
    representative_context as p2d_representative_context,
)

SVG_NS = "{http://www.w3.org/2000/svg}"
ZONE_CODES = (
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
)
DISPLAY_NAMES = (
    "办公室",
    "更衣室",
    "一级预冷间",
    "二级预冷间",
    "原果暂存间",
    "分选包装间",
    "覆膜间",
    "成品间",
    "次果暂存间",
    "冻果间",
    "包材库",
    "出货通道",
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


def _render(validated_layout_and_geometry, *, profile: str = "PRESENTATION"):
    layout, geometry = validated_layout_and_geometry
    return project_validated_layout_to_svg(
        layout,
        site_geometry=geometry,
        page_profile=profile,
    ).to_dict()


def _visible_text(svg: str) -> str:
    root = ET.fromstring(svg)
    values: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] in {"text", "tspan", "title"}:
            values.append("".join(element.itertext()))
    return " ".join(values)


def _element_by_id(root: ET.Element, element_id: str) -> ET.Element:
    for element in root.iter():
        if element.get("id") == element_id:
            return element
    raise AssertionError(f"missing SVG element {element_id}")


def test_business_views_use_chinese_labels_and_hide_internal_identifiers(
    validated_layout_and_geometry,
):
    presentation = _render(validated_layout_and_geometry)
    mobile = _render(validated_layout_and_geometry, profile="MOBILE_PREVIEW")

    for body in (presentation, mobile):
        visible = _visible_text(body["svg"])
        assert all(name in visible for name in DISPLAY_NAMES)
        assert all(code not in visible for code in ZONE_CODES)
        assert body["internal_zone_code_visible"] is False
        assert body["source_hash_visible"] is False
        assert body["portal_debug_text_visible"] is False
        assert body["schema_identity_visible"] is False
        assert body["ROOM_LABEL_WALL_CROSSING_COUNT"] == 0
        assert body["ROOM_LABEL_PRIMARY_COLLISION_COUNT"] == 0


def test_label_fallback_chain_is_deterministic_and_measured(validated_layout_and_geometry):
    first = _render(validated_layout_and_geometry)
    second = _render(validated_layout_and_geometry)

    for body in (first, second):
        assert body["ROOM_LABEL_3_LINE_COUNT"] > 0
        assert (
            body["ROOM_LABEL_3_LINE_COUNT"]
            + body["ROOM_LABEL_2_LINE_COUNT"]
            + body["ROOM_LABEL_1_LINE_COUNT"]
            + body["ROOM_LABEL_NUMERIC_ID_COUNT"]
            == 12
        )
        assert body["ROOM_LABEL_CALLOUT_COUNT"] == 0
    assert first["svg"] == second["svg"]
    assert first["svg_sha256"] == second["svg_sha256"]


def test_area_schedule_is_numeric_id_to_business_name_and_area(
    validated_layout_and_geometry,
):
    body = _render(validated_layout_and_geometry, profile="ENGINEERING_SHEET")
    root = ET.fromstring(body["svg"])
    schedule = _element_by_id(root, "area-schedule")
    schedule_text = " ".join(schedule.itertext())
    assert "编号 | 中文名称 | 面积" in schedule_text
    assert "01 | 办公室 |" in schedule_text
    assert "02 | 更衣室 |" in schedule_text
    assert all(code not in schedule_text for code in ZONE_CODES)


def test_engineering_review_preserves_debug_label_and_metadata_visibility(
    validated_layout_and_geometry,
):
    body = _render(validated_layout_and_geometry, profile="ENGINEERING_REVIEW")
    visible = _visible_text(body["svg"])
    assert "office" in visible
    assert body["internal_zone_code_visible"] is True
    assert body["source_hash_visible"] is True
    assert body["portal_debug_text_visible"] is True
    assert body["schema_identity_visible"] is True
    assert ET.fromstring(body["svg"]).find(f".//{SVG_NS}metadata") is not None


def test_focused_views_keep_primary_composition_and_dimension_policy(
    validated_layout_and_geometry,
):
    presentation = _render(validated_layout_and_geometry)
    mobile = _render(validated_layout_and_geometry, profile="MOBILE_PREVIEW")
    assert presentation["primary_plan_bounds"] == mobile["primary_plan_bounds"]
    assert presentation["source_engineering_geometry_changed"] is False
    assert presentation["engineering_coordinates_mutated"] is False
    assert presentation["dimension_codes_rendered"] == [
        "primary_precooling_room",
        "secondary_precooling_room",
        "sorting_packaging_room",
        "shipping_channel",
    ]
    assert mobile["dimension_codes_rendered"] == []
    assert _element_by_id(ET.fromstring(presentation["svg"]), "dimension-level-1-total") is not None
    assert _element_by_id(ET.fromstring(mobile["svg"]), "dimension-level-1-total") is not None


def test_extremely_small_rooms_use_numeric_or_callout_fallback():
    rectangles = {
        code: PlacedRectangleV1(
            code,
            Decimal(index),
            Decimal("0"),
            Decimal("0.3"),
            Decimal("0.2"),
            0,
        )
        for index, code in enumerate(ZONE_CODES)
    }
    plans, metrics = _build_room_label_plan(
        rectangles,
        SvgProjectionTransformV1(Decimal("0"), Decimal("0.2")),
        page_profile="PRESENTATION",
        portal_segments=(),
        dimension_codes=(),
    )
    assert all(plan["mode"] in {"NUMERIC_ID", "CALLOUT"} for plan in plans.values())
    assert metrics["ROOM_LABEL_3_LINE_COUNT"] == 0
    assert metrics["ROOM_LABEL_2_LINE_COUNT"] == 0
    assert metrics["ROOM_LABEL_1_LINE_COUNT"] == 0
    assert metrics["ROOM_LABEL_NUMERIC_ID_COUNT"] + metrics["ROOM_LABEL_CALLOUT_COUNT"] == 12


def test_label_elements_record_stable_mode_and_index(validated_layout_and_geometry):
    body = _render(validated_layout_and_geometry)
    root = ET.fromstring(body["svg"])
    labels = [element for element in root.iter() if element.get("id", "").startswith("label-zone-")]
    assert len(labels) == 12
    assert {element.get("data-label-index") for element in labels} == {
        f"{index:02d}" for index in range(1, 13)
    }
    assert all(element.get("data-label-mode") for element in labels)
