from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.layout.application.access_critical_construction import (
    build_access_critical_construction_intent,
)
from cold_storage.modules.layout.application.layout_authority_binding import (
    bind_layout_authority,
)
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain import composition_placement as placement_domain
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.composition_placement import (
    FORWARD_CHECK_BUDGET_EXHAUSTION_CAN_PRUNE,
    FORWARD_CHECK_ENGINEERING_AUTHORITY,
    FORWARD_CHECK_IS_OPTIMISTIC,
    FORWARD_CHECK_VALIDATION_AUTHORITY,
    MAIN_CHAIN_SOURCE,
    UNKNOWN_FORWARD_CHECK_CAN_PRUNE,
    _authority_shapes,
    _canonical_construction_shapes,
    _domain_arrangement,
    _main_chain_roles_from_process_graph,
    _MainChainForwardCheckResultV1,
    _optimistic_main_chain_completion_probe,
    _search_one,
    _SearchDiagnostics,
    _Shape,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    normalize_polygon,
)
from cold_storage.modules.layout.domain.truck_maneuver import (
    validate_truck_maneuver_project_binding,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context

BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = BACKEND_ROOT / "tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"


def _rectangle_from_bounds(role: str, bounds: tuple[int, int, int, int]) -> PlacedRectangleV1:
    left, bottom, right, top = bounds
    return PlacedRectangleV1(
        role,
        Decimal(left) / 1000,
        Decimal(bottom) / 1000,
        Decimal(right - left) / 1000,
        Decimal(top - bottom) / 1000,
    )


@pytest.fixture(scope="module")
def context() -> dict[str, Any]:
    zone_plan, p1_handoff, site_geometry = _context()
    fixture = json.loads(FIXTURE_PATH.read_text())
    truck_binding = validate_truck_maneuver_project_binding(
        fixture["truck_access"], fixture["truck_maneuver"]
    )
    binding = bind_layout_authority(zone_plan, p1_handoff, site_geometry)
    intent = build_access_critical_construction_intent(
        zone_plan, p1_handoff, site_geometry, truck_binding
    )
    body = site_geometry.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = tuple(
        normalize_polygon(row["footprint"], allow_numeric_string=True)
        for row in body["obstacles"]["hard_obstacles"]
    )
    compositions = build_structural_compositions(zone_plan, p1_handoff, site_geometry)
    handoffs = {item.composition_identity: item for item in compositions.placement_handoffs}
    handoff = handoffs["whole-building-structural-composition@2.0.0:LINEAR_BANDED:X:NEGATIVE:r0"]
    authoritative_shapes = _authority_shapes(
        binding.dimension_authorities, boundary, obstacles, intent
    )
    shapes = {
        role: _canonical_construction_shapes(variants)
        for role, variants in authoritative_shapes.items()
    }
    return {
        "binding": binding,
        "boundary": boundary,
        "obstacles": obstacles,
        "handoff": handoff,
        "intent": intent,
        "shapes": shapes,
        "authoritative_shapes": authoritative_shapes,
        "dimension_authorities": binding.dimension_authorities,
        "handoffs": handoffs,
    }


def test_main_chain_source_is_existing_material_flow_authority() -> None:
    flows = tuple(flow for flow in process_graph().flows if flow.kind == "MATERIAL")
    assert _main_chain_roles_from_process_graph() == (
        flows[0].from_ref,
        *(flow.to_ref for flow in flows),
    )
    assert MAIN_CHAIN_SOURCE == "EXISTING_PROCESS_GRAPH"
    assert FORWARD_CHECK_ENGINEERING_AUTHORITY is False
    assert FORWARD_CHECK_VALIDATION_AUTHORITY is False
    assert FORWARD_CHECK_IS_OPTIMISTIC is True
    assert UNKNOWN_FORWARD_CHECK_CAN_PRUNE is False
    assert FORWARD_CHECK_BUDGET_EXHAUSTION_CAN_PRUNE is False
    assert _main_chain_roles_from_process_graph() == (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )


def test_cr2_finished_goods_starvation_witness_is_detected(context) -> None:
    identity = "whole-building-structural-composition@2.0.0:LINEAR_BANDED:X:NEGATIVE:r0"
    bounds = {
        "changing_room": (14700, 11399, 34700, 13399),
        "coating_room": (24900, 37049, 33845, 45994),
        "frozen_fruit_room": (0, 43050, 10800, 51250),
        "packaging_material_storage": (0, 18850, 14500, 36150),
        "primary_precooling_room": (63979, 0, 74029, 14700),
        "raw_fruit_buffer": (48779, 0, 63979, 8700),
        "secondary_fruit_buffer": (0, 36150, 8400, 43050),
        "secondary_precooling_room": (24900, 26999, 34700, 37049),
        "shipping_channel": (0, 0, 6500, 7693),
        "sorting_packaging_room": (18219, 13399, 63979, 26999),
    }
    partial = {role: _rectangle_from_bounds(role, value) for role, value in bounds.items()}
    handoff = context["handoffs"][identity]
    domains = _domain_arrangement(
        handoff,
        1,
        context["boundary"],
        context["dimension_authorities"],
    )
    diagnostics = _SearchDiagnostics(node_limit=20_000)

    result = _optimistic_main_chain_completion_probe(
        handoff,
        context["shapes"],
        domains,
        1,
        partial,
        context["boundary"],
        context["obstacles"],
        context["intent"],
        diagnostics,
        "shipping_channel",
    )

    assert result.status == "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
    assert result.first_unplaceable_role == "finished_goods_room"
    assert result.probe_nodes_used > 0
    assert diagnostics.nodes == diagnostics.forward_check_nodes


def test_packaging_compatible_cr2_partial_retains_an_optimistic_chain_witness(context) -> None:
    handoff_identity = "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"
    bounds = {
        "packaging_material_storage": (60610, 0, 75110, 17300),
        "primary_precooling_room": (14698, 21968, 29398, 32018),
        "raw_fruit_buffer": (5998, 18751, 14698, 33951),
        "secondary_precooling_room": (29398, 21968, 39448, 31768),
        "sorting_packaging_room": (14850, 8368, 60610, 21968),
    }
    partial = {role: _rectangle_from_bounds(role, value) for role, value in bounds.items()}
    handoff = context["handoffs"][handoff_identity]
    domains = _domain_arrangement(handoff, 1, context["boundary"], context["dimension_authorities"])
    diagnostics = _SearchDiagnostics(node_limit=20_000)

    result = _optimistic_main_chain_completion_probe(
        handoff,
        context["shapes"],
        domains,
        1,
        partial,
        context["boundary"],
        context["obstacles"],
        context["intent"],
        diagnostics,
        "packaging_material_storage",
    )

    assert result.status == "PASS_TO_SEARCH"
    assert result.witness_role_order
    assert "packaging_material_storage" not in result.unplaced_main_chain_roles
    for role, bounds in result.witness_zone_bounds_mm:
        witness_rect = _rectangle_from_bounds(role, bounds)
        assert all(
            not placement_domain.rectangles_overlap(witness_rect, fixed_rect)
            for fixed_rect in partial.values()
        )


def test_zero_shared_probe_slice_is_unknown_and_never_a_negative_proof(context) -> None:
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 20, "y": 0},
                {"x": 20, "y": 20},
                {"x": 0, "y": 20},
            ],
        }
    )
    tiny_shapes = {role: (_Shape(1000, 1000, 0),) for role in context["shapes"]}
    partial = {"sorting_packaging_room": PlacedRectangleV1("sorting_packaging_room", 2, 0, 1, 1)}
    handoff = context["handoff"]
    domains = _domain_arrangement(handoff, 1, boundary, context["dimension_authorities"])
    diagnostics = _SearchDiagnostics(node_limit=0)

    result = _optimistic_main_chain_completion_probe(
        handoff,
        tiny_shapes,
        domains,
        1,
        partial,
        boundary,
        (),
        context["intent"],
        diagnostics,
        "sorting_packaging_room",
    )

    assert result.status == "UNKNOWN_BUDGET_EXHAUSTED"
    assert result.probe_nodes_used == 0
    assert diagnostics.forward_check_proved_no_completion_count == 0
    assert diagnostics.forward_check_unknown_budget_count == 1


def test_unknown_forward_check_does_not_prune_parent_search(context, monkeypatch) -> None:
    boundary = context["boundary"]
    handoff = context["handoff"]
    domains = _domain_arrangement(handoff, 1, boundary, context["dimension_authorities"])
    monkeypatch.setattr(
        placement_domain,
        "_domain_derived_anchors",
        lambda *_args, **_kwargs: ((0, 0),),
    )
    monkeypatch.setattr(
        placement_domain,
        "_generic_fallback_anchors",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(placement_domain, "_candidate_rejection", lambda *_args: None)
    monkeypatch.setattr(placement_domain, "rectangles_share_positive_edge", lambda *_args: True)
    monkeypatch.setattr(placement_domain, "_side_ok", lambda *_args: True)
    monkeypatch.setattr(placement_domain, "_intent_preserved", lambda *_args: True)
    monkeypatch.setattr(placement_domain, "_partial_intent_possible", lambda *_args: True)
    monkeypatch.setattr(
        placement_domain, "_packaging_straight_interface_possible", lambda *_args: True
    )
    monkeypatch.setattr(
        placement_domain, "_packaging_interface_capacity_remains", lambda *_args: True
    )
    probe_triggers: list[str] = []

    def unknown_probe(*args: Any, **kwargs: Any) -> _MainChainForwardCheckResultV1:
        del kwargs
        trigger_role = args[-1]
        probe_triggers.append(trigger_role)
        return _MainChainForwardCheckResultV1(
            status="UNKNOWN_BUDGET_EXHAUSTED",
            partial_geometry_hash=f"partial-{len(probe_triggers)}",
            fixed_main_chain_roles=(),
            unplaced_main_chain_roles=_main_chain_roles_from_process_graph(),
            witness_role_order=(),
            witness_zone_bounds_mm=(),
            probe_nodes_used=0,
            first_unplaceable_role=None,
            failure_taxonomy="SHARED_ATTEMPT_FORWARD_CHECK_SLICE_EXHAUSTED",
        )

    monkeypatch.setattr(placement_domain, "_optimistic_main_chain_completion_probe", unknown_probe)
    tiny_shapes = {role: (_Shape(1000, 1000, 0),) for role in context["shapes"]}

    outcome = _search_one(
        handoff,
        tiny_shapes,
        tiny_shapes,
        context["dimension_authorities"],
        boundary,
        context["obstacles"],
        domains,
        1,
        "S3_COMPATIBILITY_ORDER",
        100,
        context["intent"],
    )

    assert outcome.solution is not None
    assert "packaging_material_storage" in probe_triggers
    assert outcome.diagnostics.chain_starvation_prune_count_by_trigger_role == {}
    assert len(outcome.solution) == 12


def test_shipping_before_finished_hole_is_inserted_between_both_fixed_neighbors(context) -> None:
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 20, "y": 0},
                {"x": 20, "y": 20},
                {"x": 0, "y": 20},
            ],
        }
    )
    chain = _main_chain_roles_from_process_graph()
    tiny_shapes = {role: (_Shape(1000, 1000, 0),) for role in context["shapes"]}
    fixed = {
        role: PlacedRectangleV1(role, index, 0, 1, 1)
        for index, role in enumerate(chain)
        if role != "finished_goods_room"
    }
    domains = _domain_arrangement(context["handoff"], 1, boundary, context["dimension_authorities"])
    diagnostics = _SearchDiagnostics(node_limit=1000)

    result = _optimistic_main_chain_completion_probe(
        context["handoff"],
        tiny_shapes,
        domains,
        1,
        fixed,
        boundary,
        (),
        context["intent"],
        diagnostics,
        "shipping_channel",
    )

    assert result.status == "PASS_TO_SEARCH"
    assert result.fixed_main_chain_roles == tuple(
        role for role in chain if role != "finished_goods_room"
    )
    assert result.witness_role_order == ("finished_goods_room",)
    assert result.witness_zone_bounds_mm[0][1] == (5000, 0, 6000, 1000)
    assert diagnostics.nodes == diagnostics.forward_check_nodes
