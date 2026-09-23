"""Cross-fixture P1A-P1E drawing robustness evaluation.

The full-chain cases reuse existing repository fixtures. Composition-only
cases pass only source/primary bounds to the frozen P1E composition builder;
they do not represent validated projects or generate room/truck geometry.
"""

from __future__ import annotations

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
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
from cold_storage.modules.layout.domain.dimensioning import canonical_json
from cold_storage.modules.layout.domain.engineering_sheet_composition import (
    ENGINEERING_SHEET_CANDIDATE_ORDER,
    ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY,
    ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY,
    ENGINEERING_SHEET_PRIMARY_PLAN_MIN_HEIGHT_RATIO,
    ENGINEERING_SHEET_PRIMARY_PLAN_MIN_OCCUPANCY,
    ENGINEERING_SHEET_PRIMARY_PLAN_MIN_WIDTH_RATIO,
    build_engineering_sheet_composition,
)
from cold_storage.modules.layout.domain.svg_projection import (
    SVG_PAGE_PROFILES,
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
from tests.unit.test_v22_p4_site_layout_mcp import (
    _FIVE_KEYS,
    _real_selector_site_constraints,
    _real_selector_tool_payload,
)

_ZERO_COUNT_FACTS = (
    "ROOM_LABEL_WALL_CROSSING_COUNT",
    "ROOM_LABEL_LABEL_OVERLAP_COUNT",
    "ROOM_LABEL_DIMENSION_COLLISION_COUNT",
    "ROOM_LABEL_PORTAL_COLLISION_COUNT",
    "ROOM_LABEL_OUT_OF_PAGE_COUNT",
    "PAGE_FURNITURE_OVERLAP_COUNT",
    "PAGE_FURNITURE_OUT_OF_PAGE_COUNT",
    "AREA_SCHEDULE_ROW_OVERLAP_COUNT",
    "AREA_SCHEDULE_CONTENT_CLIP_COUNT",
    "AREA_SCHEDULE_OUT_OF_PAGE_COUNT",
    "VISIBLE_DIMENSION_OUT_OF_PAGE_COUNT",
)
_CALLOUT_FACTS = (
    "CALLOUT_LABEL_COLLISION_COUNT",
    "CALLOUT_LEADER_SELF_INTERSECTION_COUNT",
    "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT",
    "CALLOUT_OUT_OF_PAGE_COUNT",
)
_BUSINESS_VIEW_FLAGS = (
    "INTERNAL_ZONE_CODE_VISIBLE",
    "SOURCE_HASH_VISIBLE",
    "PORTAL_DEBUG_TEXT_VISIBLE",
    "SCHEMA_IDENTITY_VISIBLE",
)
_EXPECTED_REPRESENTATIVE_HASHES = {
    "PRESENTATION": "sha256:e89ca6e1f797fedca41780d2027e728b3a3f37db19c979c0fa9dc863531b2f1a",
    "MOBILE_PREVIEW": "sha256:dc0b5313113e69fdfc6c59b88f4bd911316d74b71762bae83768c1bdd70153f2",
    "ENGINEERING_SHEET": "sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3",
    "ENGINEERING_REVIEW": "sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d",
}
_CONTEXT_INSET_PROFILES = frozenset({"PRESENTATION", "MOBILE_PREVIEW", "ENGINEERING_SHEET"})


@dataclass(frozen=True)
class _FullChainScenario:
    scenario_id: str
    source_type: str
    site_input: Mapping[str, Any]
    layout: Any
    site_geometry: Any
    p2c_selector_used: bool
    selector_replay_passed: bool


def _layout_hash(layout: Any) -> str:
    if hasattr(layout, "canonical_result_hash"):
        return str(layout.canonical_result_hash)
    if isinstance(layout, Mapping):
        value = layout.get("canonical_result_hash")
        if isinstance(value, str):
            return value
    raise AssertionError("full-chain fixture did not expose its canonical layout hash")


def _assert_full_pass(layout: Any) -> None:
    body = layout.to_dict() if hasattr(layout, "to_dict") else layout
    assert isinstance(body, Mapping)
    assert body.get("project_layout_validated") is True
    assert body.get("p2_complete") is True
    assert body.get("zone_count") == 12


def _p2d_scenario(
    *, scenario_id: str, site_input: Mapping[str, Any], concave: bool
) -> _FullChainScenario:
    zone_plan, handoff, original_geometry, _, binding = p2d_representative_context.__wrapped__()
    case_site = deepcopy(dict(site_input))
    if concave:
        case_site["site_boundary"] = {
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
    geometry = (
        validate_site_geometry(
            {"site_constraints": case_site, "truck_access": truck_input()},
            zone_plan,
            p1_handoff=handoff,
        )
        if concave
        else original_geometry
    )
    placement = _placement(zone_plan, handoff, geometry)
    first = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    replay = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    _assert_full_pass(first)
    assert first.canonical_result_hash == replay.canonical_result_hash
    return _FullChainScenario(
        scenario_id=scenario_id,
        source_type="EXISTING_P2D_VALIDATED_TEST_FIXTURE",
        site_input=case_site,
        layout=first,
        site_geometry=geometry,
        p2c_selector_used=False,
        selector_replay_passed=True,
    )


def _p4_selector_scenario() -> _FullChainScenario:
    payload = _real_selector_tool_payload()
    first = preview_site_layout(payload)
    replay = preview_site_layout(payload)
    assert first["validated_layout_selected"] is True
    assert first["project_layout_validated"] is True
    assert first["p2_complete"] is True
    assert first["layout"]["canonical_result_hash"] == replay["layout"]["canonical_result_hash"]
    assert first["drawing"]["svg"] == replay["drawing"]["svg"]
    assert first["drawing"]["svg_sha256"] == replay["drawing"]["svg_sha256"]
    trace = first["selection"]["candidate_validation_trace"]
    assert len(trace) >= 2
    assert trace[0]["p2d_full_pass"] is False
    assert any(item["p2d_full_pass"] is True for item in trace[1:])
    _assert_full_pass(first["layout"])

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
    return _FullChainScenario(
        scenario_id="P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES",
        source_type="EXISTING_UNMOCKED_TOOL7_FULL_CHAIN_FIXTURE",
        site_input=site,
        layout=first["layout"],
        site_geometry=geometry,
        p2c_selector_used=True,
        selector_replay_passed=True,
    )


@pytest.fixture(scope="module")
def full_chain_scenarios() -> tuple[_FullChainScenario, ...]:
    representative = _p2d_scenario(
        scenario_id="P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE",
        site_input=_site_input(),
        concave=False,
    )
    concave_site = _p2d_scenario(
        scenario_id="P3_EXISTING_CONCAVE_SITE_VALIDATED_LAYOUT",
        site_input=_site_input(),
        concave=True,
    )
    selector_site = _p4_selector_scenario()
    return representative, concave_site, selector_site


def _aspect_ratio(bounds: Mapping[str, Any]) -> Decimal:
    width = Decimal(str(bounds["max_x_m"])) - Decimal(str(bounds["min_x_m"]))
    height = Decimal(str(bounds["max_y_m"])) - Decimal(str(bounds["min_y_m"]))
    return max(width, height) / min(width, height)


def _site_aspect_ratio(site_input: Mapping[str, Any]) -> Decimal:
    polygon = site_input["site_boundary"]
    assert isinstance(polygon, Mapping)
    points = polygon["points"]
    assert isinstance(points, list)
    xs = [Decimal(str(point["x"])) for point in points]
    ys = [Decimal(str(point["y"])) for point in points]
    return max(max(xs) - min(xs), max(ys) - min(ys)) / min(max(xs) - min(xs), max(ys) - min(ys))


def _context_inset_evidence(
    scenario: _FullChainScenario, projection: Mapping[str, Any], profile: str
) -> dict[str, Any]:
    if profile not in _CONTEXT_INSET_PROFILES:
        return {
            "required": False,
            "visible": False,
            "loading_interface_visible": None,
            "loading_face_endpoint_matches_authority": None,
            "inset_bounds_px": None,
        }

    assert projection["context_inset"]
    root = ET.fromstring(str(projection["svg"]))
    element_ids = {element.get("id", "") for element in root.iter()}
    body = scenario.layout.to_dict() if hasattr(scenario.layout, "to_dict") else scenario.layout
    assert isinstance(body, Mapping)
    zone_codes = [zone["zone_code"] for zone in body["zones"]]
    required_ids = {
        "site-context-inset-frame",
        "site-boundary-polygon",
        "effective-buildable-boundary",
        "site-context-layout",
        "context-building-footprint-polygon",
        "main-entrance",
        "truck-entrance",
        *(f"context-zone-footprint-{code}" for code in zone_codes),
        *(
            f"no-build-zone-{index}"
            for index, _ in enumerate(scenario.site_input.get("no_build_zones", []))
        ),
    }
    missing_ids = sorted(required_ids - element_ids)
    context_group = next(
        (element for element in root.iter() if element.get("id") == "site-context-layout"),
        None,
    )
    loading_face = next(
        (
            element
            for element in root.iter()
            if element.get("id") == "context-shipping-loading-face"
        ),
        None,
    )
    loading_interface_visible = False
    if context_group is not None and loading_face is not None:
        body = scenario.layout.to_dict() if hasattr(scenario.layout, "to_dict") else scenario.layout
        assert isinstance(body, Mapping)
        source_segment = body["shipping_loading_face_segment"]
        source_points: list[tuple[int, int]] = []
        for endpoint in (source_segment["start"], source_segment["end"]):
            coordinates = tuple(Decimal(str(endpoint[axis])) * 1000 for axis in ("x", "y"))
            assert all(value == value.to_integral_value() for value in coordinates)
            source_points.append((int(coordinates[0]), int(coordinates[1])))

        geometry_bounds = projection["engineering_geometry_bounds"]
        inset = projection["context_inset"]
        padding = Decimal(str(inset["inner_padding"]))
        context_transform = SvgProjectionTransformV1(
            min_x_m=Decimal(str(geometry_bounds["min_x_m"])),
            max_y_m=Decimal(str(geometry_bounds["max_y_m"])),
            scale=Decimal(str(inset["scale"])),
            offset_x_px=Decimal(str(inset["x"])) + padding,
            offset_y_px=Decimal(str(inset["y"])) + padding,
        )
        expected = tuple(context_transform.point(point) for point in source_points)
        actual = tuple(Decimal(loading_face.attrib[name]) for name in ("x1", "y1", "x2", "y2"))
        loading_interface_visible = loading_face in list(context_group) and actual == (
            *expected[0],
            *expected[1],
        )
    if not loading_interface_visible:
        missing_ids.append("context-shipping-loading-face")
    return {
        "required": True,
        "visible": True,
        "loading_interface_visible": loading_interface_visible,
        "loading_face_endpoint_matches_authority": loading_interface_visible,
        "inset_bounds_px": {
            name: str(projection["context_inset"][name]) for name in ("x", "y", "width", "height")
        },
        "missing_elements": missing_ids,
        "contract_pass": not missing_ids,
    }


def _project_all_profiles(scenario: _FullChainScenario) -> dict[str, dict[str, Any]]:
    original_layout_hash = _layout_hash(scenario.layout)
    original_geometry_hash = scenario.site_geometry.canonical_result_hash
    profile_results: dict[str, dict[str, Any]] = {}
    for profile in SVG_PAGE_PROFILES:
        first = project_validated_layout_to_svg(
            scenario.layout,
            site_geometry=scenario.site_geometry,
            page_profile=profile,
        ).to_dict()
        replay = project_validated_layout_to_svg(
            scenario.layout,
            site_geometry=scenario.site_geometry,
            page_profile=profile,
        ).to_dict()
        first_lint = lint_validated_layout_drawing(first, page_profile=profile)
        replay_lint = lint_validated_layout_drawing(replay, page_profile=profile)
        assert first["svg"] == replay["svg"]
        assert first["svg_sha256"] == replay["svg_sha256"]
        if scenario.scenario_id == "P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE":
            assert first["svg_sha256"] == _EXPECTED_REPRESENTATIVE_HASHES[profile]
        assert first_lint.to_dict() == replay_lint.to_dict()
        assert first_lint.canonical_lint_hash == replay_lint.canonical_lint_hash
        assert first_lint.drawing_lint_gate == "PASS"
        assert first_lint.error_count == 0
        assert first_lint.unavailable_required_fact_count == 0

        if profile in {"PRESENTATION", "MOBILE_PREVIEW", "ENGINEERING_SHEET"}:
            assert all(first_lint.metrics[name] is False for name in _BUSINESS_VIEW_FLAGS)
        for name in _ZERO_COUNT_FACTS:
            evidence = first_lint.metric_evidence[name]
            assert evidence.status in {"MEASURED", "DERIVED", "NOT_APPLICABLE"}
            assert evidence.value == 0
        callout_count = first_lint.metrics["ROOM_LABEL_CALLOUT_COUNT"]
        for name in _CALLOUT_FACTS:
            evidence = first_lint.metric_evidence[name]
            if callout_count == 0:
                assert evidence.status == "NOT_APPLICABLE"
            else:
                assert evidence.status in {"MEASURED", "DERIVED"}
                assert evidence.value == 0
        if profile == "ENGINEERING_SHEET":
            assert first["engineering_sheet_full_room_dimensions"] is True
            assert first["engineering_sheet_context_inset_visible"] is True
            assert first["full_site_context_preserved"] is True
        context_evidence = _context_inset_evidence(scenario, first, profile)

        profile_results[profile] = {
            "projection": first,
            "lint": first_lint,
            "determinism": True,
            "context_evidence": context_evidence,
        }
    assert _layout_hash(scenario.layout) == original_layout_hash
    assert scenario.site_geometry.canonical_result_hash == original_geometry_hash
    return profile_results


def _composition_out_of_page_count(composition: Mapping[str, Any]) -> int:
    page = composition["page_size"]
    furniture = composition["furniture"]
    assert isinstance(page, Mapping) and isinstance(furniture, Mapping)
    page_width = Decimal(str(page["width"]))
    page_height = Decimal(str(page["height"]))
    count = 0
    for panel in furniture.values():
        assert isinstance(panel, Mapping)
        x, y = Decimal(str(panel["x"])), Decimal(str(panel["y"]))
        width, height = Decimal(str(panel["width"])), Decimal(str(panel["height"]))
        if x < 0 or y < 0 or x + width > page_width or y + height > page_height:
            count += 1
    return count


def _composition_candidate_passes(composition: Mapping[str, Any]) -> bool:
    return (
        ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY
        <= Decimal(str(composition["main_drawing_occupancy"]))
        <= ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY
        and Decimal(str(composition["primary_plan_screen_occupancy"]))
        >= ENGINEERING_SHEET_PRIMARY_PLAN_MIN_OCCUPANCY
        and Decimal(str(composition["primary_plan_width_ratio"]))
        >= ENGINEERING_SHEET_PRIMARY_PLAN_MIN_WIDTH_RATIO
        and Decimal(str(composition["primary_plan_height_ratio"]))
        >= ENGINEERING_SHEET_PRIMARY_PLAN_MIN_HEIGHT_RATIO
        and composition["page_furniture_overlap_count"] == 0
        and _composition_out_of_page_count(composition) == 0
    )


def _select_bounds_only_candidate(
    geometry_bounds: Mapping[str, Decimal], primary_bounds: Mapping[str, Decimal]
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for candidate in ENGINEERING_SHEET_CANDIDATE_ORDER:
        composition = build_engineering_sheet_composition(
            candidate=candidate,
            geometry_bounds=dict(geometry_bounds),
            primary_bounds=dict(primary_bounds),
        )
        attempts.append(
            {
                "candidate": candidate,
                "composition": composition,
                "hard_gates_pass": _composition_candidate_passes(composition),
            }
        )
        if attempts[-1]["hard_gates_pass"]:
            return {"selected": candidate, "attempts": attempts, "composition": composition}
    raise AssertionError("no bounds-only composition candidate passed the frozen P1E gates")


def _bounds_only_scenarios() -> list[dict[str, Any]]:
    inputs = (
        (
            "COMPOSITION_ONLY_WIDE_SITE_RIGHT_RAIL",
            {"min_x_m": "0", "min_y_m": "0", "max_x_m": "400", "max_y_m": "100"},
            {"min_x_m": "20", "min_y_m": "10", "max_x_m": "260", "max_y_m": "80"},
        ),
        (
            "COMPOSITION_ONLY_WIDE_PLAN_BOTTOM_RAIL",
            {"min_x_m": "0", "min_y_m": "0", "max_x_m": "520", "max_y_m": "180"},
            {"min_x_m": "20", "min_y_m": "20", "max_x_m": "400", "max_y_m": "150"},
        ),
    )
    results: list[dict[str, Any]] = []
    for scenario_id, geometry_source, primary_source in inputs:
        geometry_bounds = {name: Decimal(value) for name, value in geometry_source.items()}
        primary_bounds = {name: Decimal(value) for name, value in primary_source.items()}
        first = _select_bounds_only_candidate(geometry_bounds, primary_bounds)
        replay = _select_bounds_only_candidate(geometry_bounds, primary_bounds)
        assert canonical_json(first) == canonical_json(replay)
        composition = first["composition"]
        results.append(
            {
                "scenario_id": scenario_id,
                "source_type": "COMPOSITION_ONLY_SYNTHETIC_BOUNDS",
                "full_chain_fixture": False,
                "geometry_bounds": geometry_source,
                "primary_bounds": primary_source,
                "site_aspect_ratio": str(_aspect_ratio(geometry_bounds)),
                "primary_aspect_ratio": str(_aspect_ratio(primary_bounds)),
                "selected_composition": first["selected"],
                "attempts": [
                    {
                        "candidate": item["candidate"],
                        "hard_gates_pass": item["hard_gates_pass"],
                        "main_drawing_occupancy": str(
                            item["composition"]["main_drawing_occupancy"]
                        ),
                    }
                    for item in first["attempts"]
                ],
                "drawing_lint_gate": "NOT_RUN_COMPOSITION_ONLY",
                "errors": None,
                "warnings": None,
                "unavailable_facts": None,
                "room_label_collisions": None,
                "page_furniture_overlaps": composition["page_furniture_overlap_count"],
                "page_furniture_out_of_page": _composition_out_of_page_count(composition),
                "main_drawing_occupancy": str(composition["main_drawing_occupancy"]),
                "primary_plan_occupancy": str(composition["primary_plan_screen_occupancy"]),
                "svg_hash": None,
                "determinism": True,
                "result": "PASS_COMPOSITION_ONLY",
            }
        )
    return results


def _scenario_report(
    scenarios: tuple[_FullChainScenario, ...],
    results_by_id: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    inventory: list[dict[str, Any]] = []
    acceptance: list[dict[str, Any]] = []
    for scenario in scenarios:
        profiles = results_by_id[scenario.scenario_id]
        any_projection = profiles["ENGINEERING_SHEET"]["projection"]
        site_bounds = any_projection["engineering_geometry_bounds"]
        primary_bounds = any_projection["primary_plan_bounds"]
        site_polygon = scenario.site_input["site_boundary"]
        points = site_polygon["points"]
        layout = (
            scenario.layout.to_dict() if hasattr(scenario.layout, "to_dict") else scenario.layout
        )
        inventory.append(
            {
                "fixture_id": scenario.scenario_id,
                "source": scenario.source_type,
                "site_aspect_ratio": str(_site_aspect_ratio(scenario.site_input)),
                "primary_plan_aspect_ratio": str(_aspect_ratio(primary_bounds)),
                "site_irregularity": len(points) > 4,
                "no_build_present": bool(scenario.site_input.get("no_build_zones", [])),
                "truck_geometry_present": bool(layout.get("truck_maneuver_chain")),
                "full_p2d_validated": bool(layout.get("p2_complete")),
                "p2c_candidate_selection": scenario.p2c_selector_used,
                "usable_for_full_svg": True,
                "site_bounds": site_bounds,
                "primary_bounds": primary_bounds,
                "layout_hash": _layout_hash(scenario.layout),
            }
        )
        for profile in SVG_PAGE_PROFILES:
            profile_data = profiles[profile]
            projection = profile_data["projection"]
            lint = profile_data["lint"]
            context_evidence = profile_data["context_evidence"]
            context_blocked = context_evidence["required"] and not context_evidence.get(
                "contract_pass", False
            )
            acceptance.append(
                {
                    "scenario": scenario.scenario_id,
                    "source_type": scenario.source_type,
                    "site_aspect_ratio": inventory[-1]["site_aspect_ratio"],
                    "primary_aspect_ratio": inventory[-1]["primary_plan_aspect_ratio"],
                    "profile": profile,
                    "selected_composition": projection.get(
                        "engineering_sheet_composition_candidate", "NOT_APPLICABLE"
                    ),
                    "drawing_lint_gate": lint.drawing_lint_gate,
                    "errors": lint.error_count,
                    "warnings": lint.warning_count,
                    "unavailable_facts": lint.unavailable_required_fact_count,
                    "room_label_collisions": lint.metrics["ROOM_LABEL_LABEL_OVERLAP_COUNT"],
                    "page_furniture_overlaps": lint.metrics["PAGE_FURNITURE_OVERLAP_COUNT"],
                    "main_drawing_occupancy": str(projection.get("main_drawing_occupancy")),
                    "primary_plan_occupancy": str(projection.get("primary_plan_screen_occupancy")),
                    "svg_hash": projection["svg_sha256"],
                    "determinism": profile_data["determinism"],
                    "context_inset_visible": context_evidence["visible"],
                    "context_loading_interface_visible": context_evidence[
                        "loading_interface_visible"
                    ],
                    "context_loading_face_endpoint_matches_authority": context_evidence[
                        "loading_face_endpoint_matches_authority"
                    ],
                    "context_inset_bounds_px": context_evidence["inset_bounds_px"],
                    "context_inset_contract_pass": context_evidence.get("contract_pass"),
                    "context_inset_missing_elements": context_evidence.get("missing_elements", []),
                    "result": (
                        "BLOCKED_CONTEXT_INSET_INCOMPLETE"
                        if context_blocked
                        else "DRAWING_LINT_FAILED"
                        if lint.drawing_lint_gate != "PASS"
                        else "DETERMINISM_FAILED"
                        if not profile_data["determinism"]
                        else "PASS"
                    ),
                    "lint_hash": lint.canonical_lint_hash,
                    "metric_evidence": {
                        name: evidence.to_dict() for name, evidence in lint.metric_evidence.items()
                    },
                }
            )
    synthetic = _bounds_only_scenarios()
    context_blockers = [row for row in acceptance if row["context_inset_contract_pass"] is False]
    drawing_lint_failures = [row for row in acceptance if row["drawing_lint_gate"] != "PASS"]
    determinism_failures = [row for row in acceptance if row["determinism"] is not True]
    visual_blockers = [row for row in acceptance if row["result"] != "PASS"]
    automated_pass = not (
        context_blockers or drawing_lint_failures or determinism_failures or visual_blockers
    )
    return {
        "task_id": "V2_2_1_P1F_CROSS_FIXTURE_DRAWING_ROBUSTNESS_RERUN_R2",
        "drawing_lint_identity": "drawing-lint@1.0.0",
        "authoritative_full_chain_fixtures": inventory,
        "composition_only_scenarios": synthetic,
        "acceptance_matrix": acceptance,
        "scenario_count": len(inventory) + len(synthetic),
        "full_chain_authoritative_fixture_count": len(inventory),
        "composition_only_fixture_count": len(synthetic),
        "context_inset_blocker_profile_count": len(context_blockers),
        "visual_blocker_scenario_count": len({row["scenario"] for row in context_blockers}),
        "visual_blocker_profile_combinations": len(visual_blockers),
        "drawing_lint_failed_scenario_count": len(drawing_lint_failures),
        "determinism_failed_scenario_count": len(determinism_failures),
        "previous_failed_profile_combinations": 6,
        "after_failed_profile_combinations": len(visual_blockers),
        "p1f_acceptance_complete": automated_pass,
        "p1f_blocker": (
            "CONTEXT_INSET_MISSING_SHIPPING_LOADING_FACE"
            if context_blockers
            else "DRAWING_LINT_FAILED"
            if drawing_lint_failures
            else "DETERMINISM_FAILED"
            if determinism_failures
            else None
        ),
        "resolved_by_merged_pr": 298,
        "context_inset_blockers": [
            {
                "scenario": row["scenario"],
                "profile": row["profile"],
                "missing_elements": row["context_inset_missing_elements"],
            }
            for row in context_blockers
        ],
    }


def _context_inset_page_rect(
    page: Any, svg_bytes: bytes, inset: Mapping[str, Any], fitz_module: Any
) -> Any:
    root = ET.fromstring(svg_bytes)
    view_box = tuple(Decimal(value) for value in root.attrib["viewBox"].split())
    assert len(view_box) == 4
    view_x, view_y, view_width, view_height = view_box
    preserve = root.attrib.get("preserveAspectRatio", "xMidYMid meet").split()
    alignment = preserve[0] if preserve else "xMidYMid"
    mode = preserve[1] if len(preserve) > 1 else "meet"
    assert alignment != "none" and mode == "meet"
    scale = min(
        Decimal(str(page.rect.width)) / view_width,
        Decimal(str(page.rect.height)) / view_height,
    )
    spare_x = Decimal(str(page.rect.width)) - (view_width * scale)
    spare_y = Decimal(str(page.rect.height)) - (view_height * scale)
    offset_x = (
        spare_x / 2 if "xMid" in alignment else spare_x if "xMax" in alignment else Decimal("0")
    )
    offset_y = (
        spare_y / 2 if "YMid" in alignment else spare_y if "YMax" in alignment else Decimal("0")
    )
    inset_x = Decimal(str(inset["x"]))
    inset_y = Decimal(str(inset["y"]))
    inset_width = Decimal(str(inset["width"]))
    inset_height = Decimal(str(inset["height"]))
    left = offset_x + ((inset_x - view_x) * scale)
    top = offset_y + ((inset_y - view_y) * scale)
    right = left + (inset_width * scale)
    bottom = top + (inset_height * scale)
    return fitz_module.Rect(float(left), float(top), float(right), float(bottom))


def _context_loading_face_detail_page_rect(page: Any, svg_bytes: bytes, fitz_module: Any) -> Any:
    root = ET.fromstring(svg_bytes)
    loading_face = next(
        (
            element
            for element in root.iter()
            if element.get("id") == "context-shipping-loading-face"
        ),
        None,
    )
    assert loading_face is not None
    face_x = [Decimal(loading_face.attrib[name]) for name in ("x1", "x2")]
    face_y = [Decimal(loading_face.attrib[name]) for name in ("y1", "y2")]
    padding = Decimal("12")
    left = min(face_x) - padding
    top = min(face_y) - padding
    right = max(face_x) + padding
    bottom = max(face_y) + padding
    return _context_inset_page_rect(
        page,
        svg_bytes,
        {
            "x": str(left),
            "y": str(top),
            "width": str(right - left),
            "height": str(bottom - top),
        },
        fitz_module,
    )


def _save_optional_evidence(report: Mapping[str, Any], results_by_id: Mapping[str, Any]) -> None:
    output_dir_value = os.environ.get("P1F_EVIDENCE_DIR")
    if not output_dir_value:
        return
    output_dir = Path(output_dir_value)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = (
        ("P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE", "PRESENTATION"),
        ("P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE", "MOBILE_PREVIEW"),
        ("P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE", "ENGINEERING_SHEET"),
        ("P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES", "ENGINEERING_SHEET"),
        ("P3_EXISTING_CONCAVE_SITE_VALIDATED_LAYOUT", "ENGINEERING_REVIEW"),
    )
    import fitz

    evidence_hashes: dict[str, dict[str, str]] = {}
    context_crop_hashes: dict[str, dict[str, str]] = {}
    context_detail_crop_hashes: dict[str, dict[str, str]] = {}
    for scenario_id, profile in selected:
        projection = results_by_id[scenario_id][profile]["projection"]
        file_stem = f"{scenario_id.lower()}-{profile.lower()}"
        svg_path = output_dir / f"{file_stem}.svg"
        png_path = output_dir / f"{file_stem}.png"
        svg_bytes = str(projection["svg"]).encode("utf-8")
        svg_path.write_bytes(svg_bytes)
        doc = fitz.open(stream=svg_bytes, filetype="svg")
        page = doc[0]
        scale = min(2400 / page.rect.width, 2400 / page.rect.height)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        pixmap.save(png_path)
        evidence_hashes[file_stem] = {
            "svg_sha256": str(projection["svg_sha256"]),
            "png_sha256": hashlib.sha256(png_path.read_bytes()).hexdigest(),
        }
        if profile in {"PRESENTATION", "MOBILE_PREVIEW"}:
            inset = projection["context_inset"]
            clip = _context_inset_page_rect(page, svg_bytes, inset, fitz)
            crop_scale = min(1600 / clip.width, 1600 / clip.height)
            crop_path = output_dir / f"{file_stem}-context-inset.png"
            crop_path.write_bytes(
                page.get_pixmap(
                    matrix=fitz.Matrix(crop_scale, crop_scale), clip=clip, alpha=False
                ).tobytes("png")
            )
            context_crop_hashes[file_stem] = {
                "png_sha256": hashlib.sha256(crop_path.read_bytes()).hexdigest(),
                "viewport_px": {
                    "x": str(inset["x"]),
                    "y": str(inset["y"]),
                    "width": str(inset["width"]),
                    "height": str(inset["height"]),
                },
            }
            detail_clip = _context_loading_face_detail_page_rect(page, svg_bytes, fitz)
            detail_scale = min(1800 / detail_clip.width, 1800 / detail_clip.height)
            detail_path = output_dir / f"{file_stem}-context-loading-face-detail.png"
            detail_path.write_bytes(
                page.get_pixmap(
                    matrix=fitz.Matrix(detail_scale, detail_scale),
                    clip=detail_clip,
                    alpha=False,
                ).tobytes("png")
            )
            context_detail_crop_hashes[file_stem] = {
                "png_sha256": hashlib.sha256(detail_path.read_bytes()).hexdigest(),
                "source_element_id": "context-shipping-loading-face",
                "source_segment_authority": "shipping_loading_face_segment",
            }
    complete_report = dict(report)
    complete_report["visual_evidence"] = evidence_hashes
    complete_report["context_inset_crop_evidence"] = context_crop_hashes
    complete_report["context_loading_face_detail_crop_evidence"] = context_detail_crop_hashes
    (output_dir / "acceptance-matrix.json").write_text(
        json.dumps(complete_report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def test_existing_authoritative_fixtures_pass_all_profiles_and_replay_deterministically(
    full_chain_scenarios: tuple[_FullChainScenario, ...],
) -> None:
    results_by_id: dict[str, dict[str, dict[str, Any]]] = {}
    for scenario in full_chain_scenarios:
        results_by_id[scenario.scenario_id] = _project_all_profiles(scenario)
    report = _scenario_report(full_chain_scenarios, results_by_id)

    assert report["full_chain_authoritative_fixture_count"] == 3
    assert report["composition_only_fixture_count"] == 2
    assert report["scenario_count"] == 5
    assert all(row["result"] == "PASS" for row in report["acceptance_matrix"])
    assert all(item["full_p2d_validated"] for item in report["authoritative_full_chain_fixtures"])
    assert report["context_inset_blocker_profile_count"] == 0
    assert report["visual_blocker_scenario_count"] == 0
    assert report["visual_blocker_profile_combinations"] == 0
    assert report["drawing_lint_failed_scenario_count"] == 0
    assert report["determinism_failed_scenario_count"] == 0
    assert report["after_failed_profile_combinations"] == 0
    assert report["p1f_acceptance_complete"] is True
    assert report["p1f_blocker"] is None
    assert all(
        row["context_inset_contract_pass"] is True
        and row["context_loading_interface_visible"] is True
        and row["context_loading_face_endpoint_matches_authority"] is True
        for row in report["acceptance_matrix"]
        if row["context_inset_visible"]
    )
    selector = next(
        item
        for item in report["authoritative_full_chain_fixtures"]
        if item["fixture_id"] == "P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES"
    )
    assert selector["p2c_candidate_selection"] is True
    _save_optional_evidence(report, results_by_id)


def test_synthetic_bounds_select_both_frozen_composition_paths_without_claiming_layout() -> None:
    scenarios = _bounds_only_scenarios()
    assert len(scenarios) == 2
    selected = {scenario["selected_composition"] for scenario in scenarios}
    assert selected == {"RIGHT_RAIL", "BOTTOM_RAIL"}
    assert all(scenario["full_chain_fixture"] is False for scenario in scenarios)
    assert all(
        scenario["drawing_lint_gate"] == "NOT_RUN_COMPOSITION_ONLY" for scenario in scenarios
    )
    assert all(scenario["svg_hash"] is None for scenario in scenarios)
    assert all(scenario["page_furniture_overlaps"] == 0 for scenario in scenarios)
    assert all(scenario["page_furniture_out_of_page"] == 0 for scenario in scenarios)
    assert all(scenario["determinism"] is True for scenario in scenarios)


def test_p1e_corrected_occupancy_values_are_documented() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    expected = (
        "0.7943176771550949",
        "0.8998748435544431",
        "0.8826979472140762",
    )
    for relative_path in (
        Path("docs/tasks/V2_2-version-plan.md"),
        Path("docs/tasks/V2_2_1-P1E-engineering-sheet-composition.md"),
    ):
        document = (repo_root / relative_path).read_text(encoding="utf-8")
        assert all(value in document for value in expected)
