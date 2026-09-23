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


def test_missing_required_room_label_fact_fails_closed(presentation_body):
    body = deepcopy(presentation_body)
    del body["ROOM_LABEL_WALL_CROSSING_COUNT"]

    report = lint_validated_layout_drawing(body)

    assert report.drawing_lint_gate == "FAIL"
    assert report.unavailable_required_fact_count >= 1
    assert report.metric_evidence["ROOM_LABEL_WALL_CROSSING_COUNT"].status == "UNAVAILABLE"
    assert any(
        issue.code == "DRAWING_LINT_REQUIRED_FACT_UNAVAILABLE"
        and issue.metrics["fact"] == "ROOM_LABEL_WALL_CROSSING_COUNT"
        for issue in report.issues
    )


def _synthetic_callout_body(presentation_body, *, points, other_boxes):
    body = deepcopy(presentation_body)
    callout_metric_names = (
        "CALLOUT_LABEL_COLLISION_COUNT",
        "CALLOUT_LEADER_SELF_INTERSECTION_COUNT",
        "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT",
        "CALLOUT_OUT_OF_PAGE_COUNT",
    )
    for name in callout_metric_names:
        body.pop(name, None)
    callout_metrics = body.get("callout_metrics")
    if isinstance(callout_metrics, dict):
        for name in callout_metric_names:
            callout_metrics.pop(name, None)

    own_box = {
        "x": "80",
        "y": "20",
        "width": "20",
        "height": "10",
    }
    label_boxes = [
        {"element_id": "label-own", "box": own_box},
        *({"element_id": element_id, "box": box} for element_id, box in other_boxes),
    ]
    body["ROOM_LABEL_CALLOUT_COUNT"] = 1
    facts = body["drawing_lint_facts"]
    facts["label_boxes"] = label_boxes
    facts["callout_leaders"] = [
        {
            "element_id": "leader-a",
            "label_element_id": "label-own",
            "points": points,
            "label_box": own_box,
        }
    ]
    return body


def test_callout_leader_crossing_other_label_is_an_error(presentation_body):
    body = _synthetic_callout_body(
        presentation_body,
        points=[
            {"x": "10", "y": "45"},
            {"x": "80", "y": "45"},
            {"x": "80", "y": "25"},
        ],
        other_boxes=(
            (
                "label-other",
                {"x": "40", "y": "40", "width": "20", "height": "10"},
            ),
        ),
    )

    report = lint_validated_layout_drawing(body)

    assert report.metrics["CALLOUT_LEADER_LABEL_INTERSECTION_COUNT"] == 1
    issue = next(
        issue for issue in report.issues if issue.code == "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT"
    )
    assert issue.severity == "ERROR"
    assert report.drawing_lint_gate == "FAIL"


def test_callout_leader_endpoint_touching_own_label_is_not_an_intersection(
    presentation_body,
):
    body = _synthetic_callout_body(
        presentation_body,
        points=[
            {"x": "70", "y": "10"},
            {"x": "80", "y": "10"},
            {"x": "80", "y": "25"},
        ],
        other_boxes=(
            (
                "label-other",
                {"x": "40", "y": "40", "width": "20", "height": "10"},
            ),
        ),
    )

    report = lint_validated_layout_drawing(body)

    assert report.metrics["CALLOUT_LEADER_LABEL_INTERSECTION_COUNT"] == 0
    assert report.drawing_lint_gate == "PASS"


def test_callout_leader_touching_other_label_boundary_is_not_an_intersection(
    presentation_body,
):
    body = _synthetic_callout_body(
        presentation_body,
        points=[
            {"x": "10", "y": "40"},
            {"x": "80", "y": "40"},
            {"x": "80", "y": "25"},
        ],
        other_boxes=(
            (
                "label-other",
                {"x": "40", "y": "40", "width": "20", "height": "10"},
            ),
        ),
    )

    report = lint_validated_layout_drawing(body)

    assert report.metrics["CALLOUT_LEADER_LABEL_INTERSECTION_COUNT"] == 0
    assert report.drawing_lint_gate == "PASS"


def test_callout_leader_crosses_each_other_label_once(presentation_body):
    body = _synthetic_callout_body(
        presentation_body,
        points=[
            {"x": "10", "y": "45"},
            {"x": "80", "y": "45"},
            {"x": "80", "y": "25"},
        ],
        other_boxes=(
            (
                "label-other-a",
                {"x": "30", "y": "40", "width": "20", "height": "10"},
            ),
            (
                "label-other-b",
                {"x": "55", "y": "40", "width": "20", "height": "10"},
            ),
        ),
    )

    report = lint_validated_layout_drawing(body)

    assert report.metrics["CALLOUT_LEADER_LABEL_INTERSECTION_COUNT"] == 2
    assert report.drawing_lint_gate == "FAIL"


def test_missing_required_boolean_fact_is_not_false(presentation_body):
    body = deepcopy(presentation_body)
    del body["internal_zone_code_visible"]

    report = lint_validated_layout_drawing(body)

    assert report.drawing_lint_gate == "FAIL"
    evidence = report.metric_evidence["INTERNAL_ZONE_CODE_VISIBLE"]
    assert evidence.status == "UNAVAILABLE"
    assert evidence.value is None


def test_explicit_zero_is_measured_and_passes(presentation_body):
    body = deepcopy(presentation_body)
    body["ROOM_LABEL_WALL_CROSSING_COUNT"] = 0

    report = lint_validated_layout_drawing(body)

    assert report.drawing_lint_gate == "PASS"
    evidence = report.metric_evidence["ROOM_LABEL_WALL_CROSSING_COUNT"]
    assert evidence.status == "MEASURED"
    assert evidence.value == 0


def test_page_furniture_out_of_page_is_derived_from_facts(presentation_body):
    body = deepcopy(presentation_body)
    body.pop("PAGE_FURNITURE_OUT_OF_PAGE_COUNT", None)

    report = lint_validated_layout_drawing(body)

    evidence = report.metric_evidence["PAGE_FURNITURE_OUT_OF_PAGE_COUNT"]
    assert evidence.status == "DERIVED"
    assert evidence.value == 0
    assert report.drawing_lint_gate == "PASS"


def test_non_rendered_callout_checks_are_not_applicable(validated_layout_and_geometry):
    report = lint_validated_layout_drawing(_render(validated_layout_and_geometry, "PRESENTATION"))

    assert report.metrics["ROOM_LABEL_CALLOUT_COUNT"] == 0
    assert report.not_applicable_fact_count >= 4
    assert all(
        report.metric_evidence[name].status == "NOT_APPLICABLE"
        for name in (
            "CALLOUT_LABEL_COLLISION_COUNT",
            "CALLOUT_LEADER_SELF_INTERSECTION_COUNT",
            "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT",
            "CALLOUT_OUT_OF_PAGE_COUNT",
        )
    )


def test_engineering_review_callout_facts_are_evaluated(validated_layout_and_geometry):
    report = lint_validated_layout_drawing(
        _render(validated_layout_and_geometry, "ENGINEERING_REVIEW")
    )

    assert report.metrics["ROOM_LABEL_CALLOUT_COUNT"] == 7
    for name in (
        "CALLOUT_LABEL_COLLISION_COUNT",
        "CALLOUT_LEADER_SELF_INTERSECTION_COUNT",
        "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT",
        "CALLOUT_OUT_OF_PAGE_COUNT",
    ):
        assert report.metric_evidence[name].status in {"MEASURED", "DERIVED"}
        assert report.metric_evidence[name].status != "UNAVAILABLE"
        assert report.metrics[name] == 0
    assert report.drawing_lint_gate == "PASS"


def test_evidence_status_and_hash_are_deterministic(presentation_body):
    first = lint_validated_layout_drawing(deepcopy(presentation_body))
    second = lint_validated_layout_drawing(deepcopy(presentation_body))

    assert first.to_dict() == second.to_dict()
    assert first.canonical_lint_hash == second.canonical_lint_hash
    assert {name: evidence.status for name, evidence in first.metric_evidence.items()} == {
        name: evidence.status for name, evidence in second.metric_evidence.items()
    }
    assert first.to_dict()["evidence_status_hashed"] is True
    assert first.to_dict()["evidence_source_hashed"] is True
    assert first.to_dict()["same_input_same_evidence_status"] is True


def test_evidence_status_and_source_are_part_of_lint_hash(presentation_body):
    measured_body = deepcopy(presentation_body)
    derived_body = deepcopy(presentation_body)
    del derived_body["ROOM_LABEL_LABEL_OVERLAP_COUNT"]

    measured = lint_validated_layout_drawing(measured_body)
    derived = lint_validated_layout_drawing(derived_body)

    assert measured.metrics["ROOM_LABEL_LABEL_OVERLAP_COUNT"] == 0
    assert derived.metrics["ROOM_LABEL_LABEL_OVERLAP_COUNT"] == 0
    assert measured.metric_evidence["ROOM_LABEL_LABEL_OVERLAP_COUNT"].status == "MEASURED"
    assert derived.metric_evidence["ROOM_LABEL_LABEL_OVERLAP_COUNT"].status == "DERIVED"
    assert measured.canonical_lint_hash != derived.canonical_lint_hash


@pytest.mark.parametrize(
    "profile,expected_hash",
    (
        ("PRESENTATION", "sha256:97e7c9083050dc1e1edd01c8880f4c7aa1d2526d72e8eff809ee792bda8cf59e"),
        (
            "MOBILE_PREVIEW",
            "sha256:db6a39e7ad38ca8c0b0fc2063d4189bdd295691d92aaf7a922e59d7c200954c8",
        ),
        (
            "ENGINEERING_SHEET",
            "sha256:9383f8686189ab9152f1203a9c4af20d85545293e46952f25ed7af13bfac3237",
        ),
        (
            "ENGINEERING_REVIEW",
            "sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d",
        ),
    ),
)
def test_lint_sidecar_does_not_change_svg_baseline_hash(
    validated_layout_and_geometry, profile, expected_hash
):
    projection = _render(validated_layout_and_geometry, profile)
    body = projection.to_dict()

    lint_validated_layout_drawing(projection)

    assert body["svg_sha256"] == expected_hash
    assert "drawing_lint_facts" not in body["svg"]


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
