"""P1E deterministic Engineering Sheet composition regressions."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, localcontext

import pytest

from cold_storage.modules.layout.application.drawing_lint import (
    lint_validated_layout_drawing,
)
from cold_storage.modules.layout.application.svg_projection import (
    project_validated_layout_to_svg,
)
from cold_storage.modules.layout.domain.engineering_sheet_composition import (
    ENGINEERING_SHEET_CANDIDATE_IDENTITY,
    ENGINEERING_SHEET_CANDIDATE_ORDER,
    ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY,
    ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY,
    ENGINEERING_SHEET_PRIMARY_PLAN_MIN_HEIGHT_RATIO,
    ENGINEERING_SHEET_PRIMARY_PLAN_MIN_OCCUPANCY,
    ENGINEERING_SHEET_PRIMARY_PLAN_MIN_WIDTH_RATIO,
    build_engineering_sheet_composition,
)
from cold_storage.modules.layout.domain.svg_projection import EXPECTED_ZONE_CODES
from tests.unit.test_v221_p1d_drawing_lint import (
    validated_layout_and_geometry as p1d_layout_fixture,
)

SVG_NS = "{http://www.w3.org/2000/svg}"


@pytest.fixture(scope="module")
def validated_layout_and_geometry():
    return p1d_layout_fixture.__wrapped__()


def _render(context, profile: str) -> dict[str, object]:
    layout, geometry = context
    return project_validated_layout_to_svg(
        layout,
        site_geometry=geometry,
        page_profile=profile,
    ).to_dict()


def _element(root: ET.Element, element_id: str) -> ET.Element:
    found = next((item for item in root.iter() if item.get("id") == element_id), None)
    assert found is not None, element_id
    return found


def test_engineering_sheet_focuses_primary_plan_and_preserves_full_context(
    validated_layout_and_geometry,
):
    layout, geometry = validated_layout_and_geometry
    source_layout = layout.to_dict()
    source_geometry_hash = geometry.canonical_result_hash
    body = _render(validated_layout_and_geometry, "ENGINEERING_SHEET")

    assert body["engineering_sheet_primary_plan_focus"] is True
    assert body["engineering_sheet_context_inset_visible"] is True
    assert body["full_site_context_preserved"] is True
    assert body["engineering_sheet_composition_candidate"] == "RIGHT_RAIL"
    assert body["engineering_sheet_composition_identity"] == ENGINEERING_SHEET_CANDIDATE_IDENTITY
    assert tuple(body["dimension_codes_rendered"]) == EXPECTED_ZONE_CODES
    assert body["engineering_sheet_full_room_dimensions"] is True
    assert body["source_validated_layout_hash"] == layout.canonical_result_hash
    assert geometry.canonical_result_hash == source_geometry_hash
    assert layout.to_dict() == source_layout

    root = ET.fromstring(str(body["svg"]))
    for element_id in (
        "site-boundary-polygon",
        "effective-buildable-boundary",
        "site-context-layout",
        "context-building-footprint-polygon",
        "context-shipping-loading-face",
        "context-shipping-loading-face-visible",
        "main-entrance",
        "truck-entrance",
        "truck-maneuvers",
    ):
        _element(root, element_id)
    assert (
        len([element for element in root.iter() if element.get("id", "").startswith("zone-")]) >= 12
    )


def test_engineering_sheet_composition_bounds_and_metrics_are_hard_gated(
    validated_layout_and_geometry,
):
    body = _render(validated_layout_and_geometry, "ENGINEERING_SHEET")
    lint = lint_validated_layout_drawing(body, page_profile="ENGINEERING_SHEET")

    primary_bounds = body["primary_plan_bounds"]
    drawing_bounds = body["engineering_drawing_bounds"]
    assert isinstance(primary_bounds, dict)
    assert isinstance(drawing_bounds, dict)
    primary_width_m = Decimal(str(primary_bounds["max_x_m"])) - Decimal(
        str(primary_bounds["min_x_m"])
    )
    primary_height_m = Decimal(str(primary_bounds["max_y_m"])) - Decimal(
        str(primary_bounds["min_y_m"])
    )
    drawing_width_m = Decimal(str(drawing_bounds["max_x_m"])) - Decimal(
        str(drawing_bounds["min_x_m"])
    )
    drawing_height_m = Decimal(str(drawing_bounds["max_y_m"])) - Decimal(
        str(drawing_bounds["min_y_m"])
    )
    with localcontext() as context:
        context.prec = 60
        expected_width_ratio = primary_width_m / drawing_width_m
        expected_height_ratio = primary_height_m / drawing_height_m
        expected_occupancy = (primary_width_m * primary_height_m) / (
            drawing_width_m * drawing_height_m
        )

    assert primary_width_m == Decimal("71.9")
    assert primary_height_m == Decimal("60.2")
    assert Decimal(str(body["primary_plan_screen_occupancy"])) == expected_occupancy
    assert Decimal(str(body["primary_plan_width_ratio"])) == expected_width_ratio
    assert Decimal(str(body["primary_plan_height_ratio"])) == expected_height_ratio
    assert body["primary_plan_screen_occupancy"] != 1
    assert body["primary_plan_width_ratio"] != 1
    assert body["primary_plan_height_ratio"] != 1

    assert float(body["main_drawing_occupancy"]) >= float(
        ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY
    )
    assert float(body["main_drawing_occupancy"]) <= float(
        ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY
    )
    assert float(body["primary_plan_screen_occupancy"]) >= float(
        ENGINEERING_SHEET_PRIMARY_PLAN_MIN_OCCUPANCY
    )
    assert float(body["primary_plan_width_ratio"]) >= float(
        ENGINEERING_SHEET_PRIMARY_PLAN_MIN_WIDTH_RATIO
    )
    assert float(body["primary_plan_height_ratio"]) >= float(
        ENGINEERING_SHEET_PRIMARY_PLAN_MIN_HEIGHT_RATIO
    )
    assert body["title_block_overlap"] is False
    assert body["area_table_overlap"] is False
    assert body["legend_overlap"] is False
    assert body["page_furniture_overlap"] is False

    page = body["page_size"]
    assert isinstance(page, dict)
    page_width = float(page["width"])
    page_height = float(page["height"])
    for panel in body["page_furniture"].values():
        assert float(panel["x"]) >= 0
        assert float(panel["y"]) >= 0
        assert float(panel["x"]) + float(panel["width"]) <= page_width
        assert float(panel["y"]) + float(panel["height"]) <= page_height

    assert lint.drawing_lint_gate == "PASS"
    assert lint.error_count == 0
    assert lint.warning_count == 0
    assert lint.unavailable_required_fact_count == 0


def test_engineering_sheet_hides_debug_metadata_but_keeps_review_policy(
    validated_layout_and_geometry,
):
    sheet = _render(validated_layout_and_geometry, "ENGINEERING_SHEET")
    review = _render(validated_layout_and_geometry, "ENGINEERING_REVIEW")
    sheet_root = ET.fromstring(str(sheet["svg"]))
    review_root = ET.fromstring(str(review["svg"]))
    sheet_text = " ".join(element.text or "" for element in sheet_root.iter())

    for name in (
        "internal_zone_code_visible",
        "source_hash_visible",
        "portal_debug_text_visible",
        "schema_identity_visible",
    ):
        assert sheet[name] is False
    assert sheet["engineering_sheet_debug_metadata_visible"] is False
    assert sheet_root.find(f"{SVG_NS}metadata") is None
    assert "sha256:" not in sheet_text
    assert "Layout status: VALIDATED" not in sheet_text
    assert "portal " not in sheet_text
    assert all(code not in sheet_text for code in EXPECTED_ZONE_CODES)

    assert review["source_hash_visible"] is True
    assert review["portal_debug_text_visible"] is True
    assert review["schema_identity_visible"] is True
    assert review["internal_zone_code_visible"] is True
    assert review_root.find(f"{SVG_NS}metadata") is not None
    assert review["svg_sha256"] == (
        "sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d"
    )


def test_engineering_sheet_selection_is_deterministic_and_other_profiles_are_byte_stable(
    validated_layout_and_geometry,
):
    first_sheet = _render(validated_layout_and_geometry, "ENGINEERING_SHEET")
    second_sheet = _render(validated_layout_and_geometry, "ENGINEERING_SHEET")

    assert ENGINEERING_SHEET_CANDIDATE_ORDER == ("RIGHT_RAIL", "BOTTOM_RAIL")
    assert first_sheet["engineering_sheet_composition_candidate"] == "RIGHT_RAIL"
    assert first_sheet["svg"] == second_sheet["svg"]
    assert first_sheet["svg_sha256"] == second_sheet["svg_sha256"]
    assert (
        first_sheet["svg_sha256"]
        == "sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3"
    )
    bottom_rail = build_engineering_sheet_composition(
        candidate="BOTTOM_RAIL",
        geometry_bounds={
            key: Decimal(value) for key, value in first_sheet["engineering_geometry_bounds"].items()
        },
        primary_bounds={
            key: Decimal(value) for key, value in first_sheet["primary_plan_bounds"].items()
        },
    )
    assert float(bottom_rail["main_drawing_occupancy"]) < float(
        ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY
    )

    expected_hashes = {
        "PRESENTATION": "sha256:e89ca6e1f797fedca41780d2027e728b3a3f37db19c979c0fa9dc863531b2f1a",
        "MOBILE_PREVIEW": "sha256:dc0b5313113e69fdfc6c59b88f4bd911316d74b71762bae83768c1bdd70153f2",
        "ENGINEERING_REVIEW": (
            "sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d"
        ),
    }
    for profile, expected in expected_hashes.items():
        assert _render(validated_layout_and_geometry, profile)["svg_sha256"] == expected
