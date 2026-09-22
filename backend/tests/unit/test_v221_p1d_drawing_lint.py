"""V2.2.1 P1D deterministic drawing-lint tests."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest

from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.drawing_lint import (
    lint_validated_layout_drawing,
)
from cold_storage.modules.layout.application.svg_projection import (
    project_validated_layout_to_svg,
)
from cold_storage.modules.layout.domain.svg_projection import SVG_PAGE_PROFILES
from tests.unit.test_v22_p2d_access_routing import (
    representative_context as p2d_representative_context,
)


@pytest.fixture(scope="module")
def validated_layout_and_geometry():
    zone_plan, handoff, geometry, placement, binding = p2d_representative_context.__wrapped__()
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


def _render(validated_layout_and_geometry, profile: str):
    layout, geometry = validated_layout_and_geometry
    return project_validated_layout_to_svg(
        layout,
        site_geometry=geometry,
        page_profile=profile,
    )


def test_clean_presentation_lint_passes_without_mutating_projection(
    validated_layout_and_geometry,
):
    projection = _render(validated_layout_and_geometry, "PRESENTATION")
    before = projection.to_dict()
    report = lint_validated_layout_drawing(projection)
    after = projection.to_dict()

    assert report.drawing_lint_gate == "PASS"
    assert report.error_count == 0
    assert report.metrics["ROOM_LABEL_WALL_CROSSING_COUNT"] == 0
    assert report.metrics["ROOM_LABEL_LABEL_OVERLAP_COUNT"] == 0
    assert report.metrics["AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP"] is False
    assert report.metrics["AREA_SCHEDULE_ROW_OVERLAP_COUNT"] == 0
    assert report.metrics["INTERNAL_ZONE_CODE_VISIBLE"] is False
    assert report.metrics["SOURCE_HASH_VISIBLE"] is False
    assert report.metrics["PORTAL_DEBUG_TEXT_VISIBLE"] is False
    assert report.metrics["SCHEMA_IDENTITY_VISIBLE"] is False
    assert before["svg"] == after["svg"]
    assert before["svg_sha256"] == after["svg_sha256"]


def test_mobile_lint_passes_and_is_deterministic(validated_layout_and_geometry):
    projection = _render(validated_layout_and_geometry, "MOBILE_PREVIEW")
    first = lint_validated_layout_drawing(projection)
    second = lint_validated_layout_drawing(projection.to_dict())

    assert first.drawing_lint_gate == "PASS"
    assert first.error_count == 0
    assert first.to_dict() == second.to_dict()
    assert first.canonical_lint_hash == second.canonical_lint_hash


def test_engineering_sheet_debug_metadata_is_an_explicit_warning_only(
    validated_layout_and_geometry,
):
    projection = _render(validated_layout_and_geometry, "ENGINEERING_SHEET")
    report = lint_validated_layout_drawing(projection)

    assert report.drawing_lint_gate == "PASS"
    assert report.error_count == 0
    assert report.warning_count >= 0
    leakage_codes = {
        "INTERNAL_ZONE_CODE_VISIBLE",
        "SOURCE_HASH_VISIBLE",
        "PORTAL_DEBUG_TEXT_VISIBLE",
        "SCHEMA_IDENTITY_VISIBLE",
    }
    assert all(
        issue.severity == "WARNING" for issue in report.issues if issue.code in leakage_codes
    )


def test_engineering_review_debug_policy_is_not_business_view_leakage(
    validated_layout_and_geometry,
):
    projection = _render(validated_layout_and_geometry, "ENGINEERING_REVIEW")
    report = lint_validated_layout_drawing(projection)

    assert report.drawing_lint_gate == "PASS"
    assert report.error_count == 0
    assert report.metrics["INTERNAL_ZONE_CODE_VISIBLE"] is True
    assert report.metrics["SOURCE_HASH_VISIBLE"] is True
    assert report.metrics["PORTAL_DEBUG_TEXT_VISIBLE"] is True
    assert report.metrics["SCHEMA_IDENTITY_VISIBLE"] is True
    assert not any(
        issue.code
        in {
            "INTERNAL_ZONE_CODE_VISIBLE",
            "SOURCE_HASH_VISIBLE",
            "PORTAL_DEBUG_TEXT_VISIBLE",
            "SCHEMA_IDENTITY_VISIBLE",
        }
        for issue in report.issues
    )


@pytest.fixture(scope="module")
def presentation_body(validated_layout_and_geometry):
    return _render(validated_layout_and_geometry, "PRESENTATION").to_dict()


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    (
        ("ROOM_LABEL_LABEL_OVERLAP_COUNT", 1, "ROOM_LABEL_LABEL_OVERLAP_COUNT"),
        ("AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP", True, "AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP"),
        ("AREA_SCHEDULE_CONTENT_CLIP_COUNT", 1, "AREA_SCHEDULE_CONTENT_CLIP_COUNT"),
        ("PAGE_FURNITURE_OVERLAP_COUNT", 1, "PAGE_FURNITURE_OVERLAP_COUNT"),
        ("ROOM_LABEL_OUT_OF_PAGE_COUNT", 1, "ROOM_LABEL_OUT_OF_PAGE_COUNT"),
        (
            "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT",
            1,
            "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT",
        ),
    ),
)
def test_synthetic_presentation_diagnostics_fail_closed(
    presentation_body, field, value, expected_code
):
    body = deepcopy(presentation_body)
    body[field] = value

    report = lint_validated_layout_drawing(body)

    assert report.drawing_lint_gate == "FAIL"
    assert report.error_count >= 1
    assert expected_code in {issue.code for issue in report.issues}


def test_internal_identifier_leak_is_an_error_in_business_view(presentation_body):
    body = deepcopy(presentation_body)
    body["internal_zone_code_visible"] = True

    report = lint_validated_layout_drawing(body)

    assert report.drawing_lint_gate == "FAIL"
    issue = next(issue for issue in report.issues if issue.code == "INTERNAL_ZONE_CODE_VISIBLE")
    assert issue.severity == "ERROR"


def test_page_furniture_out_of_page_is_reported(presentation_body):
    body = deepcopy(presentation_body)
    body["page_furniture"]["legend"]["x"] = str(Decimal(body["page_size"]["width"]) + Decimal("1"))

    report = lint_validated_layout_drawing(body)

    assert report.drawing_lint_gate == "FAIL"
    assert report.metrics["PAGE_FURNITURE_OUT_OF_PAGE_COUNT"] == 1


def test_area_schedule_content_box_clipping_is_reported(presentation_body):
    body = deepcopy(presentation_body)
    body["page_furniture"]["area_schedule"]["height"] = "100"

    report = lint_validated_layout_drawing(body)

    assert report.drawing_lint_gate == "FAIL"
    assert report.metrics["AREA_SCHEDULE_CONTENT_CLIP_COUNT"] == 1


def test_diagnostics_are_stably_sorted_and_hashed(presentation_body):
    first_body = deepcopy(presentation_body)
    first_body["CALLOUT_OUT_OF_PAGE_COUNT"] = 1
    first_body["ROOM_LABEL_WALL_CROSSING_COUNT"] = 1
    second_body = deepcopy(presentation_body)
    second_body["ROOM_LABEL_WALL_CROSSING_COUNT"] = 1
    second_body["CALLOUT_OUT_OF_PAGE_COUNT"] = 1

    first = lint_validated_layout_drawing(first_body)
    second = lint_validated_layout_drawing(second_body)

    assert [issue.code for issue in first.issues] == [
        "CALLOUT_OUT_OF_PAGE_COUNT",
        "ROOM_LABEL_WALL_CROSSING_COUNT",
    ]
    assert first.to_dict() == second.to_dict()
    assert first.canonical_lint_hash == second.canonical_lint_hash


def test_profile_validation_is_explicit():
    with pytest.raises(ValueError) as error:
        lint_validated_layout_drawing({"page_profile": "UNKNOWN"})
    assert getattr(error.value, "code", None) == "DRAWING_LINT_PROFILE_INVALID"
    assert SVG_PAGE_PROFILES == (
        "PRESENTATION",
        "MOBILE_PREVIEW",
        "ENGINEERING_SHEET",
        "ENGINEERING_REVIEW",
    )
