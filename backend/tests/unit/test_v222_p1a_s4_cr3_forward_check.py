from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
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
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.composition_placement import (
    FORWARD_CHECK_BUDGET_EXHAUSTION_CAN_PRUNE,
    FORWARD_CHECK_ENGINEERING_AUTHORITY,
    FORWARD_CHECK_IS_OPTIMISTIC,
    FORWARD_CHECK_VALIDATION_AUTHORITY,
    MAIN_CHAIN_SOURCE,
    UNKNOWN_FORWARD_CHECK_CAN_PRUNE,
    _authority_shapes,
    _canonical_construction_shapes,
    _completion_witness_from_probe,
    _completion_witness_incompatibility,
    _composition_intent_projection_decision,
    _CompositionIntentProjectionDecisionV1,
    _domain_arrangement,
    _feasible_successor_domain,
    _main_chain_partial_geometry_hash,
    _main_chain_roles_from_process_graph,
    _MainChainForwardCheckResultV1,
    _must_neighbors,
    _optimistic_main_chain_completion_probe,
    _partial_intent_possible,
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


def _rectangle_at_center(role: str, x_mm: int, y_mm: int, size_mm: int = 100) -> PlacedRectangleV1:
    half = size_mm // 2
    return _rectangle_from_bounds(
        role,
        (x_mm - half, y_mm - half, x_mm + (size_mm - half), y_mm + (size_mm - half)),
    )


def _two_metre_square() -> Any:
    return normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 2, "y": 0},
                {"x": 2, "y": 2},
                {"x": 0, "y": 2},
                {"x": 0, "y": 0},
            ],
        }
    )


def _family_handoff(context: Mapping[str, Any], family: str):
    return next(
        item
        for item in context["handoffs"].values()
        if item.family.value == family
        and item.process_axis.value == "Y"
        and item.process_direction.value == "POSITIVE"
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


def test_linear_raw_core_projection_bound_filters_only_proven_candidates(context) -> None:
    handoff = _family_handoff(context, "LINEAR_BANDED")
    boundary = _two_metre_square()
    fixed = {
        "raw_fruit_buffer": _rectangle_at_center("raw_fruit_buffer", 500, 500),
        "primary_precooling_room": _rectangle_at_center("primary_precooling_room", 500, 500),
        "sorting_packaging_room": _rectangle_at_center("sorting_packaging_room", 500, 600),
        "secondary_precooling_room": _rectangle_at_center("secondary_precooling_room", 500, 600),
    }
    impossible = {
        **fixed,
        "coating_room": _rectangle_at_center("coating_room", 500, 100),
    }
    possible = {
        **fixed,
        "coating_room": _rectangle_at_center("coating_room", 500, 950),
    }
    rejected = _composition_intent_projection_decision(handoff, impossible, boundary)
    retained = _composition_intent_projection_decision(handoff, possible, boundary)

    assert rejected.status == "PROVABLY_INCOMPATIBLE"
    assert "LINEAR_RAW_CORE" in rejected.rejected_rules
    assert retained.status == "POSSIBLY_COMPATIBLE"
    assert _partial_intent_possible(handoff, possible, {}) is True
    assert _partial_intent_possible(handoff, impossible, {}) is False


def test_linear_projection_bounds_respect_negative_process_direction(context) -> None:
    handoff = next(
        item
        for item in context["handoffs"].values()
        if item.family.value == "LINEAR_BANDED"
        and item.process_axis.value == "X"
        and item.process_direction.value == "NEGATIVE"
    )
    boundary = _two_metre_square()
    valid = {
        "raw_fruit_buffer": _rectangle_at_center("raw_fruit_buffer", 1500, 500),
        "primary_precooling_room": _rectangle_at_center("primary_precooling_room", 1500, 500),
        "sorting_packaging_room": _rectangle_at_center("sorting_packaging_room", 1000, 500),
        "secondary_precooling_room": _rectangle_at_center("secondary_precooling_room", 1000, 500),
        "coating_room": _rectangle_at_center("coating_room", 1000, 500),
        "finished_goods_room": _rectangle_at_center("finished_goods_room", 500, 500),
        "shipping_channel": _rectangle_at_center("shipping_channel", 500, 500),
    }
    invalid = {
        **valid,
        "raw_fruit_buffer": _rectangle_at_center("raw_fruit_buffer", 500, 500),
        "primary_precooling_room": _rectangle_at_center("primary_precooling_room", 500, 500),
    }

    assert _partial_intent_possible(handoff, valid, {}) is True
    assert (
        _composition_intent_projection_decision(handoff, valid, boundary).status
        == "POSSIBLY_COMPATIBLE"
    )
    assert _partial_intent_possible(handoff, invalid, {}) is False
    decision = _composition_intent_projection_decision(handoff, invalid, boundary)
    assert decision.status == "PROVABLY_INCOMPATIBLE"
    assert "LINEAR_RAW_CORE" in decision.rejected_rules


def test_linear_finished_chain_hole_projection_uses_existing_group_average(context) -> None:
    handoff = _family_handoff(context, "LINEAR_BANDED")
    boundary = _two_metre_square()
    fixed = {
        "raw_fruit_buffer": _rectangle_at_center("raw_fruit_buffer", 500, 100),
        "primary_precooling_room": _rectangle_at_center("primary_precooling_room", 500, 100),
        "sorting_packaging_room": _rectangle_at_center("sorting_packaging_room", 500, 800),
        "secondary_precooling_room": _rectangle_at_center("secondary_precooling_room", 500, 900),
        "coating_room": _rectangle_at_center("coating_room", 500, 1000),
        "shipping_channel": _rectangle_at_center("shipping_channel", 500, 100),
    }
    impossible = {
        **fixed,
        "finished_goods_room": _rectangle_at_center("finished_goods_room", 500, 200),
    }
    possible = {
        **fixed,
        "finished_goods_room": _rectangle_at_center("finished_goods_room", 500, 1900),
    }

    rejected = _composition_intent_projection_decision(handoff, impossible, boundary)
    retained = _composition_intent_projection_decision(handoff, possible, boundary)
    assert "LINEAR_CORE_FINISHED" in rejected.rejected_rules
    assert rejected.status == "PROVABLY_INCOMPATIBLE"
    assert retained.status == "POSSIBLY_COMPATIBLE"
    assert _partial_intent_possible(handoff, possible, {}) is True
    assert _partial_intent_possible(handoff, impossible, {}) is False


def test_central_propagation_uses_only_central_sorting_center_rules(context) -> None:
    handoff = _family_handoff(context, "CENTRAL_PROCESS_CORE")
    boundary = _two_metre_square()
    raw_partial = {
        "sorting_packaging_room": _rectangle_at_center("sorting_packaging_room", 500, 1000),
        "raw_fruit_buffer": _rectangle_at_center("raw_fruit_buffer", 500, 1200),
        "primary_precooling_room": _rectangle_at_center("primary_precooling_room", 500, 1300),
    }
    finished_partial = {
        "sorting_packaging_room": raw_partial["sorting_packaging_room"],
        "finished_goods_room": _rectangle_at_center("finished_goods_room", 500, 500),
        "shipping_channel": _rectangle_at_center("shipping_channel", 500, 600),
    }

    raw_decision = _composition_intent_projection_decision(handoff, raw_partial, boundary)
    finished_decision = _composition_intent_projection_decision(handoff, finished_partial, boundary)
    assert raw_decision.status == "PROVABLY_INCOMPATIBLE"
    assert "CENTRAL_RAW_SORTING" in raw_decision.rejected_rules
    assert finished_decision.status == "PROVABLY_INCOMPATIBLE"
    assert "CENTRAL_FINISHED_SORTING" in finished_decision.rejected_rules
    assert all("LINEAR_" not in item for item in raw_decision.evaluated_rules)
    assert all("LINEAR_" not in item for item in finished_decision.evaluated_rules)


def test_spine_propagation_uses_existing_material_chain_monotonicity(context) -> None:
    handoff = _family_handoff(context, "PROCESS_SPINE_WITH_PERIPHERAL_BANKS")
    boundary = _two_metre_square()
    fixed = {
        "raw_fruit_buffer": _rectangle_at_center("raw_fruit_buffer", 500, 100),
        "primary_precooling_room": _rectangle_at_center("primary_precooling_room", 500, 200),
        "sorting_packaging_room": _rectangle_at_center("sorting_packaging_room", 500, 500),
        "secondary_precooling_room": _rectangle_at_center("secondary_precooling_room", 500, 1000),
    }
    impossible = {
        **fixed,
        "coating_room": _rectangle_at_center("coating_room", 500, 900),
    }
    possible = {
        **fixed,
        "coating_room": _rectangle_at_center("coating_room", 500, 1200),
    }

    rejected = _composition_intent_projection_decision(handoff, impossible, boundary)
    retained = _composition_intent_projection_decision(handoff, possible, boundary)
    assert rejected.status == "PROVABLY_INCOMPATIBLE"
    assert "SPINE_MONOTONIC" in rejected.rejected_rules
    assert retained.status == "POSSIBLY_COMPATIBLE"


def test_projection_rejection_has_no_false_prune_in_exhaustive_small_domain(context) -> None:
    handoff = _family_handoff(context, "LINEAR_BANDED")
    boundary = _two_metre_square()
    fixed = {
        "raw_fruit_buffer": _rectangle_at_center("raw_fruit_buffer", 500, 1500),
        "primary_precooling_room": _rectangle_at_center("primary_precooling_room", 500, 1500),
        "sorting_packaging_room": _rectangle_at_center("sorting_packaging_room", 500, 500),
        "secondary_precooling_room": _rectangle_at_center("secondary_precooling_room", 500, 500),
        "coating_room": _rectangle_at_center("coating_room", 500, 100),
    }
    decision = _composition_intent_projection_decision(handoff, fixed, boundary)
    assert decision.status == "PROVABLY_INCOMPATIBLE"
    # Exhaust all remaining finite finished-group positions. The unchanged
    # final predicate rejects every completion because RAW cannot precede CORE.
    for finished_y in (100, 1000, 1900):
        for shipping_y in (100, 1000, 1900):
            complete = {
                **fixed,
                "finished_goods_room": _rectangle_at_center("finished_goods_room", 500, finished_y),
                "shipping_channel": _rectangle_at_center("shipping_channel", 500, shipping_y),
            }
            assert _partial_intent_possible(handoff, complete, {}) is False


def test_poor_projection_slack_is_rank_only_not_a_hard_rejection(context) -> None:
    handoff = _family_handoff(context, "LINEAR_BANDED")
    boundary = _two_metre_square()
    partial = {
        "raw_fruit_buffer": _rectangle_at_center("raw_fruit_buffer", 500, 700),
        "primary_precooling_room": _rectangle_at_center("primary_precooling_room", 500, 700),
        "sorting_packaging_room": _rectangle_at_center("sorting_packaging_room", 500, 700),
        "secondary_precooling_room": _rectangle_at_center("secondary_precooling_room", 500, 700),
        "coating_room": _rectangle_at_center("coating_room", 500, 750),
    }
    decision = _composition_intent_projection_decision(handoff, partial, boundary)
    assert decision.status == "POSSIBLY_COMPATIBLE"
    assert decision.slack > 0
    assert _partial_intent_possible(handoff, partial, {}) is True
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
    # CR7 exhausts the exact physical origin domain before recursive
    # expansion; zero expansion nodes is valid when every origin is blocked.
    assert diagnostics.successor_free_space_profiles
    assert all(row["unclassified_count"] == 0 for row in diagnostics.successor_free_space_profiles)
    assert diagnostics.nodes == diagnostics.forward_check_nodes


def test_packaging_compatible_cr2_partial_retains_an_optimistic_chain_witness(
    context, monkeypatch
) -> None:
    # Isolate the optimistic physical/adjacency witness search. Composition
    # monotonicity is separately enforced when a forward witness is built for
    # primary-DFS reuse.
    monkeypatch.setattr(placement_domain, "_partial_intent_possible", lambda *_args: True)
    monkeypatch.setattr(
        placement_domain,
        "_composition_intent_projection_decision",
        lambda *_args: _CompositionIntentProjectionDecisionV1(
            "POSSIBLY_COMPATIBLE", 0, "TEST_PHYSICAL_PROBE_ONLY"
        ),
    )
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


def test_cr3_optimistic_witness_is_rejected_by_existing_composition_intent(context) -> None:
    """Historical CR3 geometry is a negative fixture, never a runtime seed."""
    handoff = context["handoffs"][
        "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"
    ]
    initial_bounds = {
        "packaging_material_storage": (60610, 0, 75110, 17300),
        "primary_precooling_room": (14698, 21968, 29398, 32018),
        "raw_fruit_buffer": (5998, 18751, 14698, 33951),
        "secondary_precooling_room": (29398, 21968, 39448, 31768),
        "sorting_packaging_room": (14850, 8368, 60610, 21968),
    }
    cr3_witness_bounds = {
        "coating_room": (32772, 31768, 41717, 40713),
        "finished_goods_room": (372, 33951, 32772, 52551),
        "shipping_channel": (32772, 40713, 40465, 47213),
    }
    placed = {role: _rectangle_from_bounds(role, bounds) for role, bounds in initial_bounds.items()}
    for role, bounds in cr3_witness_bounds.items():
        candidate = _rectangle_from_bounds(role, bounds)
        assert (
            placement_domain._candidate_rejection(
                candidate, placed, context["boundary"], context["obstacles"]
            )
            is None
        )
        assert all(
            placement_domain.rectangles_share_positive_edge(candidate, placed[neighbor])
            for neighbor in _must_neighbors(role)
            if neighbor in placed
        )
        placed[role] = candidate

    assert (
        _partial_intent_possible(handoff, placed, placement_domain._domain_faces(handoff, 1))
        is False
    )


def test_known_linear_probe_reports_propagation_funnel_within_cr4_slice(context) -> None:
    handoff = context["handoffs"][
        "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"
    ]
    partial_bounds = {
        "packaging_material_storage": (60610, 0, 75110, 17300),
        "primary_precooling_room": (14698, 21968, 29398, 32018),
        "raw_fruit_buffer": (5998, 18751, 14698, 33951),
        "secondary_precooling_room": (29398, 21968, 39448, 31768),
        "sorting_packaging_room": (14850, 8368, 60610, 21968),
    }
    partial = {
        role: _rectangle_from_bounds(role, bounds) for role, bounds in partial_bounds.items()
    }
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

    assert diagnostics.forward_check_node_limit == 5_000
    assert result.probe_nodes_used <= 1_666
    assert diagnostics.composition_propagation_evaluation_count > 0
    assert diagnostics.composition_propagation_provable_rejection_count > 0
    assert result.status in {"PASS_TO_SEARCH", "UNKNOWN_BUDGET_EXHAUSTED"}
    assert result.status != "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
    assert sum(
        metrics["raw_anchor_count"] for metrics in diagnostics.forward_probe_funnel.values()
    ) == sum(
        metrics["must_edge_rejected_count"]
        + metrics["propagation_rejected_count"]
        + metrics["after_propagation_count"]
        for metrics in diagnostics.forward_probe_funnel.values()
    )
    if result.status == "PASS_TO_SEARCH":
        assert result.witness_role_order
        witness = _completion_witness_from_probe(
            result, handoff, 1, context["dimension_authorities"]
        )
        assert witness is not None
        assert (
            _completion_witness_incompatibility(
                witness,
                handoff,
                1,
                context["shapes"],
                context["authoritative_shapes"],
                context["dimension_authorities"],
                partial,
                context["boundary"],
                context["obstacles"],
                placement_domain._domain_faces(handoff, 1),
            )
            is None
        )
    else:
        assert result.probe_nodes_used == 1_666
        assert result.failure_taxonomy == "SHARED_ATTEMPT_FORWARD_CHECK_SLICE_EXHAUSTED"
        assert diagnostics.forward_probe_funnel["coating_room"]["propagation_rejected_count"] > 0
        assert (
            diagnostics.forward_probe_funnel["finished_goods_room"]["after_propagation_count"] > 0
        )


def _chain_hole_probe_inputs(context, monkeypatch, *, shipping_x_mm: int, origins):
    handoff = context["handoffs"][
        "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"
    ]
    chain = _main_chain_roles_from_process_graph()
    material_flows = tuple(
        SimpleNamespace(kind="MATERIAL", from_ref=first, to_ref=second)
        for first, second in zip(chain, chain[1:], strict=False)
    )
    graph = SimpleNamespace(
        flows=material_flows,
        must_adjacencies=tuple(zip(chain, chain[1:], strict=False)),
    )
    monkeypatch.setattr(placement_domain, "process_graph", lambda: graph)
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 12, "y": 0},
                {"x": 12, "y": 3},
                {"x": 0, "y": 3},
            ],
        }
    )
    shape = _Shape(1000, 1000, 0)
    shapes = {role: (shape,) for role in context["shapes"]}
    fixed_x = {
        "raw_fruit_buffer": 0,
        "primary_precooling_room": 1000,
        "sorting_packaging_room": 2000,
        "secondary_precooling_room": 3000,
        "coating_room": 4000,
        "shipping_channel": shipping_x_mm,
    }
    partial = {
        role: _rectangle_from_bounds(role, (x, 0, x + 1000, 1000)) for role, x in fixed_x.items()
    }
    monkeypatch.setattr(
        placement_domain,
        "_domain_derived_anchors",
        lambda role, *_args, **_kwargs: tuple(origins) if role == "finished_goods_room" else (),
    )
    monkeypatch.setattr(placement_domain, "_generic_fallback_anchors", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(placement_domain, "_anchors_at_must_faces", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(placement_domain, "_partial_intent_possible", lambda *_args: True)
    monkeypatch.setattr(
        placement_domain,
        "_composition_intent_projection_decision",
        lambda *_args: _CompositionIntentProjectionDecisionV1(
            "POSSIBLY_COMPATIBLE", 0, "TEST_SUCCESSOR_CAPACITY"
        ),
    )
    domains = _domain_arrangement(handoff, 1, boundary, context["dimension_authorities"])
    return handoff, shapes, domains, boundary, partial


def test_successor_domain_is_exact_union_filter_for_multiple_must_neighbors(context, monkeypatch):
    handoff = context["handoff"]
    monkeypatch.setattr(
        placement_domain,
        "_must_neighbors",
        lambda role: ("coating_room", "shipping_channel") if role == "finished_goods_room" else (),
    )
    fixed = {
        "coating_room": _rectangle_from_bounds("coating_room", (0, 0, 1000, 1000)),
        "shipping_channel": _rectangle_from_bounds("shipping_channel", (2000, 0, 3000, 1000)),
    }
    shape = _Shape(1000, 1000, 0)
    primary_origins = ((3000, 0), (1000, 1000))
    must_face_origins = ((1000, 0),)
    finite_origin_union = (*primary_origins, *must_face_origins)
    domain = _feasible_successor_domain(
        "finished_goods_room", shape, finite_origin_union, fixed, handoff, 1
    )
    expected = tuple(
        origin
        for origin in sorted(set(finite_origin_union))
        if all(
            placement_domain.rectangles_share_positive_edge(
                placement_domain._rectangle("finished_goods_room", *origin, shape),
                fixed[neighbor],
            )
            for neighbor in ("coating_room", "shipping_channel")
        )
    )

    assert domain.fixed_must_neighbors == ("coating_room", "shipping_channel")
    assert domain.raw_finite_origin_count == 3
    assert set(must_face_origins) <= set(finite_origin_union)
    assert domain.origins == expected == ((1000, 0),)
    assert domain.engineering_authority is False
    assert domain.validation_authority is False


def test_successor_capacity_exhausts_impossible_chain_hole_without_extra_domain(
    context, monkeypatch
):
    handoff, shapes, domains, boundary, partial = _chain_hole_probe_inputs(
        context,
        monkeypatch,
        shipping_x_mm=7000,
        origins=((5000, 0), (6000, 0)),
    )
    diagnostics = _SearchDiagnostics(node_limit=1000)
    result = _optimistic_main_chain_completion_probe(
        handoff,
        shapes,
        domains,
        1,
        partial,
        boundary,
        (),
        None,
        diagnostics,
        "shipping_channel",
        chain_hole=True,
        dimension_authorities=context["dimension_authorities"],
    )

    assert result.status == "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
    assert result.first_unplaceable_role == "finished_goods_room"
    edge = diagnostics.successor_capacity_edge_diagnostics["coating_room->finished_goods_room"]
    assert edge["finite_candidates"] > 0
    assert edge["must_edge_compatible"] == 0
    shipping_edge = diagnostics.successor_capacity_edge_diagnostics[
        "finished_goods_room->shipping_channel"
    ]
    assert shipping_edge["finite_candidates"] > 0
    assert shipping_edge["must_edge_compatible"] == 0
    assert diagnostics.successor_capacity_proved_none_count == 2
    assert diagnostics.forward_check_nodes == 0


def test_first_hard_valid_successor_stops_probe_and_emits_replayable_capacity_witness(
    context, monkeypatch
):
    handoff, shapes, domains, boundary, partial = _chain_hole_probe_inputs(
        context,
        monkeypatch,
        shipping_x_mm=6000,
        origins=((5000, 0), (5000, 1)),
    )
    shape = shapes["finished_goods_room"][0]
    diagnostics = _SearchDiagnostics(node_limit=1000)
    result = _optimistic_main_chain_completion_probe(
        handoff,
        shapes,
        domains,
        1,
        partial,
        boundary,
        (),
        None,
        diagnostics,
        "shipping_channel",
        chain_hole=True,
        dimension_authorities=context["dimension_authorities"],
    )

    assert result.status == "PASS_TO_SEARCH"
    assert result.witness_role_order == ("finished_goods_room",)
    assert result.witness_zone_bounds_mm == (("finished_goods_room", (5000, 0, 6000, 1000)),)
    assert diagnostics.forward_check_nodes == 1
    assert diagnostics.forward_probe_funnel["finished_goods_room"]["raw_anchor_count"] == 2
    assert diagnostics.forward_probe_funnel["finished_goods_room"]["full_hard_valid_count"] == 1
    assert (
        diagnostics.successor_capacity_edge_diagnostics["coating_room->finished_goods_room"][
            "pass_count"
        ]
        == 1
    )
    assert (
        diagnostics.successor_capacity_edge_diagnostics["finished_goods_room->shipping_channel"][
            "pass_count"
        ]
        == 1
    )
    witness = diagnostics.successor_capacity_witnesses[0]
    assert witness["parent_partial_geometry_hash"] == _main_chain_partial_geometry_hash(
        handoff, 1, partial
    )
    assert witness["authoritative_shape_identity"] == placement_domain._shape_authority_identity(
        "finished_goods_room",
        context["dimension_authorities"]["finished_goods_room"],
        shape,
    )
    assert witness["forward_probe_candidate_revalidated"] is True


def test_successor_capacity_unknown_budget_does_not_prune(context, monkeypatch):
    handoff, shapes, domains, boundary, partial = _chain_hole_probe_inputs(
        context,
        monkeypatch,
        shipping_x_mm=6000,
        origins=((5000, 0), (5000, 1)),
    )
    monkeypatch.setattr(
        placement_domain,
        "_candidate_rejection",
        lambda candidate, *_args: "OVERLAP" if candidate.y == 0 else None,
    )
    diagnostics = _SearchDiagnostics(node_limit=4)
    result = _optimistic_main_chain_completion_probe(
        handoff,
        shapes,
        domains,
        1,
        partial,
        boundary,
        (),
        None,
        diagnostics,
        "shipping_channel",
        chain_hole=True,
    )

    assert result.status == "UNKNOWN_BUDGET_EXHAUSTED"
    assert result.probe_nodes_used == 1
    assert diagnostics.successor_capacity_proved_none_count == 0
    assert diagnostics.successor_capacity_unknown_budget_count == 2
    assert diagnostics.chain_starvation_prune_count_by_trigger_role == {}


def test_no_successor_capacity_prunes_parent_after_exhaustive_domain(context, monkeypatch):
    boundary, handoff, shapes, authorities, domains, _anchors, lane = _cr4_search_inputs(
        context, monkeypatch
    )

    def no_successor_probe(*args, **kwargs):
        del kwargs
        return _cr4_forward_probe_result(
            args[0],
            args[3],
            args[4],
            args[8],
            {},
            status="PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN",
        )

    monkeypatch.setattr(
        placement_domain, "_optimistic_main_chain_completion_probe", no_successor_probe
    )
    outcome = _search_one(
        handoff,
        shapes,
        shapes,
        authorities,
        boundary,
        (),
        domains,
        1,
        lane,
        2000,
        context["intent"],
    )

    assert outcome.solution is None
    assert outcome.diagnostics.chain_starvation_prune_count_by_trigger_role == {
        "packaging_material_storage": 1
    }


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
        placement_domain,
        "_composition_intent_projection_decision",
        lambda *_args: _CompositionIntentProjectionDecisionV1(
            "POSSIBLY_COMPATIBLE", 0, "TEST_PHYSICAL_PROBE_ONLY"
        ),
    )
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


def test_shipping_before_finished_hole_is_inserted_between_both_fixed_neighbors(
    context, monkeypatch
) -> None:
    monkeypatch.setattr(placement_domain, "_partial_intent_possible", lambda *_args: True)
    monkeypatch.setattr(
        placement_domain,
        "_composition_intent_projection_decision",
        lambda *_args: _CompositionIntentProjectionDecisionV1(
            "POSSIBLY_COMPATIBLE", 0, "TEST_CHAIN_HOLE_ONLY"
        ),
    )
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


def _cr4_search_inputs(context, monkeypatch, *, lane: str = "S3_COMPATIBILITY_ORDER"):
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 100},
                {"x": 0, "y": 100},
            ],
        }
    )
    handoff = context["handoffs"][
        "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"
    ]
    shape = _Shape(1000, 1000, 0)
    shapes = {role: (shape,) for role in ZONE_CODES}
    authorities = {
        role: {
            "required_area_m2": "1",
            "dimension_mode": "FIXED_RECTANGLE",
            "rotation_allowed": [0],
            "geometry": {"width_m": "1", "depth_m": "1"},
        }
        for role in ZONE_CODES
    }
    domains = _domain_arrangement(handoff, 1, boundary, authorities)
    anchor_by_role = {role: (index * 2000, 1000) for index, role in enumerate(ZONE_CODES)}
    monkeypatch.setattr(
        placement_domain,
        "_domain_derived_anchors",
        lambda role, *_args, **_kwargs: (anchor_by_role[role],),
    )
    monkeypatch.setattr(placement_domain, "_generic_fallback_anchors", lambda *_args, **_kwargs: ())
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
    monkeypatch.setattr(
        placement_domain,
        "_shipping_office_candidate_preflight_status",
        lambda *_args: "PASS_TO_SEARCH",
    )
    return boundary, handoff, shapes, authorities, domains, anchor_by_role, lane


def _cr4_forward_probe_result(
    handoff,
    bank_sign: int,
    placed,
    diagnostics,
    witness_bounds: dict[str, tuple[int, int, int, int]],
    *,
    status: str = "PASS_TO_SEARCH",
) -> _MainChainForwardCheckResultV1:
    signature = _main_chain_partial_geometry_hash(handoff, bank_sign, placed)
    diagnostics.forward_check_invocation_count += 1
    diagnostics.forward_check_signatures.add(signature)
    if status == "PASS_TO_SEARCH":
        diagnostics.forward_check_pass_count += 1
        witness_roles = tuple(witness_bounds)
        unplaced = _main_chain_roles_from_process_graph()
        result = _MainChainForwardCheckResultV1(
            status=status,
            partial_geometry_hash=signature,
            fixed_main_chain_roles=tuple(role for role in unplaced if role in placed),
            unplaced_main_chain_roles=tuple(role for role in unplaced if role not in placed),
            witness_role_order=witness_roles,
            witness_zone_bounds_mm=tuple((role, witness_bounds[role]) for role in witness_roles),
            probe_nodes_used=0,
            first_unplaceable_role=None,
            failure_taxonomy="OPTIMISTIC_MAIN_CHAIN_WITNESS_FOUND",
            witness_shape_specs=tuple((role, _Shape(1000, 1000, 0)) for role in witness_roles),
        )
    elif status == "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN":
        diagnostics.forward_check_proved_no_completion_count += 1
        result = _MainChainForwardCheckResultV1(
            status=status,
            partial_geometry_hash=signature,
            fixed_main_chain_roles=tuple(
                role for role in _main_chain_roles_from_process_graph() if role in placed
            ),
            unplaced_main_chain_roles=tuple(
                role for role in _main_chain_roles_from_process_graph() if role not in placed
            ),
            witness_role_order=(),
            witness_zone_bounds_mm=(),
            probe_nodes_used=0,
            first_unplaceable_role="coating_room",
            failure_taxonomy="NO_SUCCESSOR_CAPACITY_IN_TEST_FINITE_DOMAIN",
        )
    else:
        diagnostics.forward_check_unknown_budget_count += 1
        result = _MainChainForwardCheckResultV1(
            status=status,
            partial_geometry_hash=signature,
            fixed_main_chain_roles=(),
            unplaced_main_chain_roles=_main_chain_roles_from_process_graph(),
            witness_role_order=(),
            witness_zone_bounds_mm=(),
            probe_nodes_used=0,
            first_unplaceable_role=None,
            failure_taxonomy="SHARED_ATTEMPT_FORWARD_CHECK_SLICE_EXHAUSTED",
        )
    diagnostics.forward_check_sequence.append(("test", signature, status, False))
    return result


def test_successor_capacity_witness_is_first_primary_candidate(context, monkeypatch) -> None:
    boundary, handoff, shapes, authorities, domains, anchors, lane = _cr4_search_inputs(
        context, monkeypatch
    )
    witness_bounds = (80_000, 80_000, 81_000, 81_000)
    attempted_coating_bounds: list[tuple[int, int, int, int]] = []
    original_rejection = placement_domain._candidate_rejection

    def successor_probe(*args, **kwargs):
        del kwargs
        if args[9] == "packaging_material_storage":
            diagnostics = args[8]
            diagnostics.successor_capacity_witnesses.append(
                {
                    "parent_partial_geometry_hash": _main_chain_partial_geometry_hash(
                        args[0], args[3], args[4]
                    ),
                    "composition_identity": args[0].composition_identity,
                    "composition_signature": args[0].composition_signature,
                    "bank_sign": args[3],
                    "predecessor_roles": ["secondary_precooling_room"],
                    "successor_role": "coating_room",
                    "bounds_mm": list(witness_bounds),
                    "shape": {
                        "width_mm": 1000,
                        "depth_mm": 1000,
                        "rotation_deg": 0,
                    },
                    "authoritative_shape_identity": placement_domain._shape_authority_identity(
                        "coating_room", authorities["coating_room"], _Shape(1000, 1000, 0)
                    ),
                    "source_finite_domain_identity": "same-invocation-test-domain",
                    "engineering_authority": False,
                    "validation_authority": False,
                }
            )
        return _cr4_forward_probe_result(
            args[0], args[3], args[4], args[8], {}, status="UNKNOWN_BUDGET_EXHAUSTED"
        )

    def record_attempt(candidate, *args):
        if candidate.zone_code == "coating_room":
            attempted_coating_bounds.append(candidate.bounds_mm)
        return original_rejection(candidate, *args)

    monkeypatch.setattr(
        placement_domain, "_optimistic_main_chain_completion_probe", successor_probe
    )
    monkeypatch.setattr(placement_domain, "_candidate_rejection", record_attempt)
    outcome = _search_one(
        handoff,
        shapes,
        shapes,
        authorities,
        boundary,
        (),
        domains,
        1,
        lane,
        2000,
        context["intent"],
    )

    assert outcome.solution is not None
    assert attempted_coating_bounds[0] == witness_bounds
    assert any(
        event["event"] == "SUCCESSOR_CAPACITY_WITNESS_REUSED" and event["role"] == "coating_room"
        for event in outcome.diagnostics.witness_events
    )
    assert outcome.diagnostics.successor_capacity_witness_reuse_attempt_count == 1
    assert anchors["coating_room"] != witness_bounds[:2]


def test_changed_parent_does_not_reuse_stale_successor_capacity_witness(
    context, monkeypatch
) -> None:
    boundary, handoff, shapes, authorities, domains, anchors, lane = _cr4_search_inputs(
        context, monkeypatch
    )
    stale_bounds = (80_000, 80_000, 81_000, 81_000)

    def stale_successor_probe(*args, **kwargs):
        del kwargs
        if args[9] == "packaging_material_storage":
            diagnostics = args[8]
            diagnostics.successor_capacity_witnesses.append(
                {
                    "parent_partial_geometry_hash": "different-parent-partial-hash",
                    "composition_identity": args[0].composition_identity,
                    "composition_signature": args[0].composition_signature,
                    "bank_sign": args[3],
                    "predecessor_roles": ["secondary_precooling_room"],
                    "successor_role": "coating_room",
                    "bounds_mm": list(stale_bounds),
                    "shape": {
                        "width_mm": 1000,
                        "depth_mm": 1000,
                        "rotation_deg": 0,
                    },
                    "authoritative_shape_identity": placement_domain._shape_authority_identity(
                        "coating_room", authorities["coating_room"], _Shape(1000, 1000, 0)
                    ),
                    "source_finite_domain_identity": "stale-test-domain",
                    "engineering_authority": False,
                    "validation_authority": False,
                }
            )
        return _cr4_forward_probe_result(
            args[0], args[3], args[4], args[8], {}, status="UNKNOWN_BUDGET_EXHAUSTED"
        )

    monkeypatch.setattr(
        placement_domain, "_optimistic_main_chain_completion_probe", stale_successor_probe
    )
    outcome = _search_one(
        handoff,
        shapes,
        shapes,
        authorities,
        boundary,
        (),
        domains,
        1,
        lane,
        2000,
        context["intent"],
    )

    assert outcome.solution is not None
    assert not any(
        event["event"] == "SUCCESSOR_CAPACITY_WITNESS_REUSE_ATTEMPTED"
        for event in outcome.diagnostics.witness_events
    )
    assert outcome.diagnostics.funnel["coating_room"]["domain_derived_anchor_count"] > 0
    assert anchors["coating_room"] != stale_bounds[:2]


def test_successor_capacity_witness_is_revalidated_before_acceptance(context, monkeypatch) -> None:
    boundary, handoff, shapes, authorities, domains, _anchors, lane = _cr4_search_inputs(
        context, monkeypatch
    )
    rejected_bounds: list[int] = []

    def overlapping_successor_probe(*args, **kwargs):
        del kwargs
        if args[9] == "packaging_material_storage":
            diagnostics = args[8]
            overlapping_bounds = args[4]["sorting_packaging_room"].bounds_mm
            rejected_bounds[:] = list(overlapping_bounds)
            diagnostics.successor_capacity_witnesses.append(
                {
                    "parent_partial_geometry_hash": _main_chain_partial_geometry_hash(
                        args[0], args[3], args[4]
                    ),
                    "composition_identity": args[0].composition_identity,
                    "composition_signature": args[0].composition_signature,
                    "bank_sign": args[3],
                    "predecessor_roles": ["secondary_precooling_room"],
                    "successor_role": "coating_room",
                    "bounds_mm": list(overlapping_bounds),
                    "shape": {
                        "width_mm": 1000,
                        "depth_mm": 1000,
                        "rotation_deg": 0,
                    },
                    "authoritative_shape_identity": placement_domain._shape_authority_identity(
                        "coating_room", authorities["coating_room"], _Shape(1000, 1000, 0)
                    ),
                    "source_finite_domain_identity": "intentionally-invalid-test-witness",
                    "engineering_authority": False,
                    "validation_authority": False,
                }
            )
        return _cr4_forward_probe_result(
            args[0], args[3], args[4], args[8], {}, status="UNKNOWN_BUDGET_EXHAUSTED"
        )

    monkeypatch.setattr(
        placement_domain,
        "_optimistic_main_chain_completion_probe",
        overlapping_successor_probe,
    )
    outcome = _search_one(
        handoff,
        shapes,
        shapes,
        authorities,
        boundary,
        (),
        domains,
        1,
        lane,
        2000,
        context["intent"],
    )

    assert outcome.solution is not None
    invalidations = [
        event
        for event in outcome.diagnostics.witness_events
        if event["event"] == "SUCCESSOR_CAPACITY_WITNESS_INVALIDATED"
        and event["role"] == "coating_room"
    ]
    assert invalidations
    assert invalidations[0]["reason"] == "OVERLAP"
    assert invalidations[0]["same_parent_replay_mismatch"] is True
    assert invalidations[0]["candidate_bounds_mm"] == rejected_bounds
    assert outcome.diagnostics.successor_capacity_same_parent_replay_mismatch is True
    assert outcome.diagnostics.successor_capacity_witness_invalidated_count >= 1
    assert outcome.diagnostics.funnel["coating_room"]["domain_derived_anchor_count"] > 0


def test_constructive_forward_witness_is_first_primary_candidate_and_suffix_is_inherited(
    context, monkeypatch
) -> None:
    boundary, handoff, shapes, authorities, domains, _anchors, lane = _cr4_search_inputs(
        context, monkeypatch
    )
    witness_bounds = {
        "coating_room": (60_000, 60_000, 61_000, 61_000),
        "finished_goods_room": (62_000, 60_000, 63_000, 61_000),
        "shipping_channel": (64_000, 60_000, 65_000, 61_000),
    }
    probe_triggers: list[str] = []

    def positive_probe(*args, **kwargs):
        del kwargs
        probe_triggers.append(args[9])
        return _cr4_forward_probe_result(args[0], args[3], args[4], args[8], witness_bounds)

    monkeypatch.setattr(placement_domain, "_optimistic_main_chain_completion_probe", positive_probe)
    outcome = _search_one(
        handoff,
        shapes,
        shapes,
        authorities,
        boundary,
        (),
        domains,
        1,
        lane,
        1000,
        context["intent"],
    )

    assert outcome.solution is not None
    attempts = [
        item for item in outcome.diagnostics.witness_events if item["event"] == "REUSE_ATTEMPTED"
    ]
    assert [item["role"] for item in attempts] == [
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    ]
    assert attempts[0]["bounds_mm"] == list(witness_bounds["coating_room"])
    assert outcome.diagnostics.witness_reuse_accepted_count == 3
    assert outcome.diagnostics.witness_inheritance_count >= 2
    assert probe_triggers == ["packaging_material_storage"]
    assert not any(
        item.get("same_parent_replay_mismatch") for item in outcome.diagnostics.witness_events
    )


def test_forward_witness_reuse_is_accounted_as_primary_search_work(context, monkeypatch) -> None:
    boundary, handoff, shapes, authorities, domains, _anchors, lane = _cr4_search_inputs(
        context, monkeypatch
    )
    witness_bounds = {
        "coating_room": (60_000, 60_000, 61_000, 61_000),
        "finished_goods_room": (62_000, 60_000, 63_000, 61_000),
        "shipping_channel": (64_000, 60_000, 65_000, 61_000),
    }

    monkeypatch.setattr(
        placement_domain,
        "_optimistic_main_chain_completion_probe",
        lambda *args, **kwargs: _cr4_forward_probe_result(
            args[0], args[3], args[4], args[8], witness_bounds
        ),
    )
    node_budget = 1_000
    outcome = _search_one(
        handoff,
        shapes,
        shapes,
        authorities,
        boundary,
        (),
        domains,
        1,
        lane,
        node_budget,
        context["intent"],
    )

    assert outcome.diagnostics.witness_reuse_attempt_count == 3
    assert outcome.diagnostics.primary_search_nodes >= 3
    assert outcome.diagnostics.nodes == (
        outcome.diagnostics.primary_search_nodes + outcome.diagnostics.forward_check_nodes
    )
    assert outcome.diagnostics.nodes <= node_budget


def test_support_geometry_overlap_invalidates_but_does_not_hard_reserve_witness(
    context, monkeypatch
) -> None:
    boundary, handoff, shapes, authorities, domains, anchors, _lane = _cr4_search_inputs(
        context, monkeypatch, lane="ACCESS_AWARE_ORDER"
    )
    frozen_x, frozen_y = anchors["frozen_fruit_room"]
    witness_bounds = {
        "coating_room": (frozen_x, frozen_y, frozen_x + 1000, frozen_y + 1000),
        "finished_goods_room": (60_000, 60_000, 61_000, 61_000),
        "shipping_channel": (62_000, 60_000, 63_000, 61_000),
    }
    probe_count = 0

    def pass_then_unknown(*args, **kwargs):
        nonlocal probe_count
        del kwargs
        probe_count += 1
        if probe_count == 1:
            return _cr4_forward_probe_result(args[0], args[3], args[4], args[8], witness_bounds)
        return _cr4_forward_probe_result(
            args[0], args[3], args[4], args[8], {}, status="UNKNOWN_BUDGET_EXHAUSTED"
        )

    monkeypatch.setattr(
        placement_domain, "_optimistic_main_chain_completion_probe", pass_then_unknown
    )
    outcome = _search_one(
        handoff,
        shapes,
        shapes,
        authorities,
        boundary,
        (),
        domains,
        1,
        "ACCESS_AWARE_ORDER",
        2000,
        context["intent"],
    )

    assert outcome.solution is not None
    assert probe_count >= 2
    assert outcome.diagnostics.funnel["frozen_fruit_room"]["accepted_partial_placement_count"] >= 1
    assert any(
        item["event"] == "INVALIDATED"
        and item["role"] == "frozen_fruit_room"
        and item["reason"] == "OVERLAP"
        for item in outcome.diagnostics.witness_events
    )
    assert outcome.diagnostics.forward_check_unknown_budget_count >= 1
    assert outcome.diagnostics.chain_starvation_prune_count_by_trigger_role == {}


def test_support_preserves_witness_and_skips_redundant_forward_probe(context, monkeypatch) -> None:
    boundary, handoff, shapes, authorities, domains, _anchors, _lane = _cr4_search_inputs(
        context, monkeypatch, lane="ACCESS_AWARE_ORDER"
    )
    witness_bounds = {
        "coating_room": (60_000, 60_000, 61_000, 61_000),
        "finished_goods_room": (62_000, 60_000, 63_000, 61_000),
        "shipping_channel": (64_000, 60_000, 65_000, 61_000),
    }
    probe_triggers: list[str] = []

    def positive_probe(*args, **kwargs):
        del kwargs
        probe_triggers.append(args[9])
        return _cr4_forward_probe_result(args[0], args[3], args[4], args[8], witness_bounds)

    monkeypatch.setattr(placement_domain, "_optimistic_main_chain_completion_probe", positive_probe)
    outcome = _search_one(
        handoff,
        shapes,
        shapes,
        authorities,
        boundary,
        (),
        domains,
        1,
        "ACCESS_AWARE_ORDER",
        3000,
        context["intent"],
    )

    assert outcome.solution is not None
    assert probe_triggers
    assert outcome.diagnostics.forward_check_skipped_due_to_valid_witness_count >= 1
    assert any(
        event["event"] == "REDUNDANT_FORWARD_CHECK_SKIPPED"
        and event["trigger_role"] in {"frozen_fruit_room", "shipping_channel"}
        for event in outcome.diagnostics.witness_events
    )
    assert any(
        event["event"] == "INHERITED" and event["role"] in {"frozen_fruit_room", "shipping_channel"}
        for event in outcome.diagnostics.witness_events
    )
    assert not any(
        event["event"] == "INVALIDATED"
        and event["role"] in {"frozen_fruit_room", "shipping_channel"}
        for event in outcome.diagnostics.witness_events
    )


def test_chain_hole_finished_witness_is_reused_after_coating_and_shipping_are_fixed(
    context, monkeypatch
) -> None:
    boundary, handoff, shapes, authorities, domains, _anchors, _lane = _cr4_search_inputs(
        context, monkeypatch, lane="ACCESS_AWARE_ORDER"
    )
    probe_states: list[tuple[tuple[str, ...], str]] = []
    witness_bounds = {"finished_goods_room": (60_000, 60_000, 61_000, 61_000)}

    def chain_hole_probe(*args, **kwargs):
        del kwargs
        placed = args[4]
        fixed_chain = _main_chain_roles_from_process_graph()
        state = tuple(role for role in fixed_chain if role in placed)
        probe_states.append((state, args[9]))
        if "coating_room" in placed and "shipping_channel" in placed:
            return _cr4_forward_probe_result(args[0], args[3], placed, args[8], witness_bounds)
        return _cr4_forward_probe_result(
            args[0], args[3], placed, args[8], {}, status="UNKNOWN_BUDGET_EXHAUSTED"
        )

    monkeypatch.setattr(
        placement_domain, "_optimistic_main_chain_completion_probe", chain_hole_probe
    )
    outcome = _search_one(
        handoff,
        shapes,
        shapes,
        authorities,
        boundary,
        (),
        domains,
        1,
        "ACCESS_AWARE_ORDER",
        5000,
        context["intent"],
    )

    assert outcome.solution is not None
    assert any(
        "coating_room" in fixed
        and "shipping_channel" in fixed
        and "finished_goods_room" not in fixed
        for fixed, _trigger in probe_states
    )
    attempts = [
        event
        for event in outcome.diagnostics.witness_events
        if event["event"] == "REUSE_ATTEMPTED" and event["role"] == "finished_goods_room"
    ]
    assert attempts
    assert attempts[0]["bounds_mm"] == list(witness_bounds["finished_goods_room"])
    assert outcome.diagnostics.witness_reuse_accepted_count == 1


def test_forward_witness_value_is_created_only_from_positive_probe(context) -> None:
    handoff = context["handoffs"][
        "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"
    ]
    shape = context["shapes"]["finished_goods_room"][0]
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 200, "y": 0},
                {"x": 200, "y": 200},
                {"x": 0, "y": 200},
            ],
        }
    )
    obstacles = ()
    finished_origin = (0, 0)
    finished_rect = placement_domain._rectangle("finished_goods_room", *finished_origin, shape)
    positive = _MainChainForwardCheckResultV1(
        status="PASS_TO_SEARCH",
        partial_geometry_hash="parent-hash",
        fixed_main_chain_roles=("sorting_packaging_room",),
        unplaced_main_chain_roles=("finished_goods_room",),
        witness_role_order=("finished_goods_room",),
        witness_zone_bounds_mm=(("finished_goods_room", finished_rect.bounds_mm),),
        probe_nodes_used=1,
        first_unplaceable_role=None,
        failure_taxonomy="OPTIMISTIC_MAIN_CHAIN_WITNESS_FOUND",
        witness_shape_specs=(("finished_goods_room", shape),),
    )
    witness = _completion_witness_from_probe(positive, handoff, 1, context["dimension_authorities"])
    assert witness is not None
    assert witness.source_forward_check_status == "PASS_TO_SEARCH"
    assert witness.geometry_for("finished_goods_room") is not None
    assert witness.engineering_authority is False
    assert witness.validation_authority is False

    frozen_role_shape = context["shapes"]["frozen_fruit_room"][0]
    preserving_frozen = placement_domain._rectangle(
        "frozen_fruit_room", 50_000, 0, frozen_role_shape
    )
    assert placement_domain._candidate_rejection(preserving_frozen, {}, boundary, obstacles) is None
    assert (
        _completion_witness_incompatibility(
            witness,
            handoff,
            1,
            context["shapes"],
            context["authoritative_shapes"],
            context["dimension_authorities"],
            {"frozen_fruit_room": preserving_frozen},
            boundary,
            obstacles,
            placement_domain._domain_faces(handoff, 1),
        )
        is None
    )
    overlapping_frozen = placement_domain._rectangle(
        "frozen_fruit_room", finished_origin[0], finished_origin[1], frozen_role_shape
    )
    assert (
        placement_domain._candidate_rejection(overlapping_frozen, {}, boundary, obstacles) is None
    )
    assert (
        _completion_witness_incompatibility(
            witness,
            handoff,
            1,
            context["shapes"],
            context["authoritative_shapes"],
            context["dimension_authorities"],
            {"frozen_fruit_room": overlapping_frozen},
            boundary,
            obstacles,
            placement_domain._domain_faces(handoff, 1),
        )
        == "OVERLAP"
    )

    for status in ("UNKNOWN_BUDGET_EXHAUSTED", "UNKNOWN_INCOMPLETE_PROOF"):
        unknown = replace(positive, status=status)
        assert (
            _completion_witness_from_probe(unknown, handoff, 1, context["dimension_authorities"])
            is None
        )
