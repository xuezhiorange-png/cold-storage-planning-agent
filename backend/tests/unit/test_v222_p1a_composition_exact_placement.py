"""P1-S3 composition-constrained exact placement MVP contract tests."""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from cold_storage.modules.layout.application.composition_placement import (
    enumerate_composition_placements,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.composition_placement import (
    DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    MAX_COMPOSITION_PLACEMENT_NODE_BUDGET,
    _authority_shapes,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import (
    normalize_polygon,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
    validate_flexible_candidate,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import (
    S1_EVIDENCE,
    _context,
    _result,
)


@pytest.fixture(scope="module")
def xinzhao_placement() -> tuple[Any, Any, Any, Any]:
    zone_plan, p1_handoff, site_geometry = _context()
    result = enumerate_composition_placements(zone_plan, p1_handoff, site_geometry)
    return zone_plan, p1_handoff, site_geometry, result


def test_public_api_replays_server_compositions_and_never_accepts_a_handoff() -> None:
    parameters = inspect.signature(enumerate_composition_placements).parameters
    assert tuple(parameters) == (
        "canonical_zone_plan",
        "p1_handoff",
        "site_geometry",
        "node_budget",
    )
    zone_plan, p1_handoff, site_geometry = _context()
    result = enumerate_composition_placements(zone_plan, p1_handoff, site_geometry, node_budget=3)
    assert result.caller_handoff_consumed is False
    assert result.composition_replay_enforced is True
    assert result.replayed_server_handoff_count == 6
    assert result.project_layout_validated_claimed is False
    with pytest.raises(ValueError, match="INVALID_COMPOSITION_PLACEMENT_NODE_BUDGET"):
        enumerate_composition_placements(
            zone_plan,
            p1_handoff,
            site_geometry,
            node_budget=MAX_COMPOSITION_PLACEMENT_NODE_BUDGET + 1,
        )


def test_replayed_handoff_rejects_forged_and_stale_provenance() -> None:
    from cold_storage.modules.layout.application.composition_placement import (
        _validate_replayed_handoff,
    )

    zone_plan, p1_handoff, site_geometry = _context()
    binding = bind_layout_authority(zone_plan, p1_handoff, site_geometry)
    handoff = build_structural_compositions(
        zone_plan, p1_handoff, site_geometry
    ).placement_handoffs[0]
    historical = binding.p1_body["p1e_historical_handoff"]
    authority_identity = historical["dimension_handoff"]["calculator_identity"]
    sources = {
        "source_zone_plan_hash": binding.canonical_zone_plan_hash,
        "source_p1_handoff_hash": binding.p1_handoff_hash,
        "source_site_geometry_hash": binding.site_geometry_hash,
        "dimension_authority_identity": authority_identity,
    }
    _validate_replayed_handoff(handoff, handoff, **sources)

    forged = replace(handoff, composition_signature="forged-signature")
    with pytest.raises(LayoutAuthorityError, match="COMPOSITION_HANDOFF_REPLAY_MISMATCH"):
        _validate_replayed_handoff(forged, handoff, **sources)

    with pytest.raises(LayoutAuthorityError, match="COMPOSITION_HANDOFF_REPLAY_MISMATCH"):
        _validate_replayed_handoff(
            handoff,
            handoff,
            **{**sources, "source_p1_handoff_hash": "sha256:stale"},
        )


def test_authoritative_fixed_and_flexible_dimensions_are_the_only_shapes() -> None:
    zone_plan, p1_handoff, site_geometry = _context()
    binding = bind_layout_authority(zone_plan, p1_handoff, site_geometry)
    geometry = site_geometry.to_dict()
    boundary = normalize_polygon(
        geometry["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = tuple(
        normalize_polygon(item, allow_numeric_string=True)
        for item in geometry["obstacles"]["no_build_zones"]
    )
    shapes = _authority_shapes(binding.dimension_authorities, boundary, obstacles)
    for role, authority in binding.dimension_authorities.items():
        allowed_rotations = set(authority["rotation_allowed"])
        assert {shape.rotation_deg for shape in shapes[role]} <= allowed_rotations
        if authority["dimension_mode"] == "FLEXIBLE_RECTANGLE":
            assert all(
                validate_flexible_candidate(
                    authority,
                    Decimal(shape.width_mm) / 1000,
                    Decimal(shape.depth_mm) / 1000,
                )["actual_area_m2"]
                >= Decimal(authority["required_area_m2"])
                for shape in shapes[role]
            )
        else:
            expected = authority["geometry"]
            assert {(shape.width_mm, shape.depth_mm) for shape in shapes[role]} == {
                (int(Decimal(expected["width_m"]) * 1000), int(Decimal(expected["depth_m"]) * 1000))
            }


def test_all_families_get_bounded_composition_first_attempts(xinzhao_placement) -> None:
    _, _, _, application_result = xinzhao_placement
    enumeration = application_result.placements
    assert enumeration.node_budget == DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET
    assert enumeration.nodes_used <= enumeration.node_budget
    assert enumeration.family_coverage_order == (
        "LINEAR_BANDED",
        "CENTRAL_PROCESS_CORE",
        "PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
    )
    assert enumeration.family_first_round_complete is True
    assert dict(enumeration.attempt_count_by_family) == {
        "LINEAR_BANDED": 4,
        "CENTRAL_PROCESS_CORE": 4,
        "PROCESS_SPINE_WITH_PERIPHERAL_BANKS": 4,
    }
    assert len(enumeration.search_attempts) == 12
    assert all(attempt.construction_domains for attempt in enumeration.search_attempts)
    assert all(
        attempt.nodes_visited <= attempt.nodes_allocated for attempt in enumeration.search_attempts
    )
    assert enumeration.exact_placement_performed is True
    assert enumeration.access_routing_performed is False
    assert enumeration.truck_validation_performed is False
    assert enumeration.p2d_performed is False
    assert enumeration.project_layout_validated_claimed is False


def test_xinzhao_has_a_complete_composition_native_candidate(xinzhao_placement) -> None:
    _, _, _, application_result = xinzhao_placement
    assert application_result.placements.candidates, (
        "S3 MVP gate failed: no complete composition-constrained 12-zone candidate "
        f"within {application_result.placements.node_budget} nodes; deepest roles="
        f"{dict(application_result.placements.deepest_role_reached_by_family)}; "
        f"failures={dict(application_result.placements.failure_reason_by_family)}"
    )


def test_every_emitted_candidate_is_exact_hard_subset_and_keeps_intent(xinzhao_placement) -> None:
    zone_plan, p1_handoff, site_geometry, application_result = xinzhao_placement
    binding = bind_layout_authority(zone_plan, p1_handoff, site_geometry)
    body = site_geometry.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = tuple(
        normalize_polygon(item, allow_numeric_string=True)
        for item in body["obstacles"]["no_build_zones"]
    )
    for candidate in application_result.placements.candidates:
        assert candidate.zone_count == 12
        assert {zone.zone_code for zone in candidate.zones} == set(ZONE_CODES)
        by_role = {zone.zone_code: zone for zone in candidate.zones}
        assert all(rectangle_inside_polygon(zone, boundary) for zone in candidate.zones)
        assert all(
            not rectangle_intersects_closed_obstacle(zone, obstacle)
            for zone in candidate.zones
            for obstacle in obstacles
        )
        assert all(
            not rectangles_overlap(first, second)
            for index, first in enumerate(candidate.zones)
            for second in candidate.zones[index + 1 :]
        )
        assert all(
            rectangles_share_positive_edge(by_role[first], by_role[second])
            for first, second in process_graph().must_adjacencies
        )
        for zone in candidate.zones:
            authority = binding.dimension_authorities[zone.zone_code]
            if authority["dimension_mode"] == "FLEXIBLE_RECTANGLE":
                assert validate_flexible_candidate(authority, zone.width_m, zone.depth_m) is None
            else:
                dimensions = authority["geometry"]
                assert (str(zone.width_m), str(zone.depth_m)) == (
                    dimensions["width_m"],
                    dimensions["depth_m"],
                )
            assert zone.rotation_deg in authority["rotation_allowed"]
        assert candidate.must_adjacency_satisfied_count == 7
        assert candidate.composition_intent_preserved is True
        assert candidate.access_validation_status == "PENDING_ROUTE_VALIDATION"
        assert candidate.access_routing_performed is False
        assert candidate.truck_validation_performed is False
        assert candidate.p2d_performed is False
        assert candidate.project_layout_validated_claimed is False
        assert candidate.p2_complete_claimed is False
        assert candidate.legacy_fallback_used is False


def test_s1_topology_signatures_are_unchanged() -> None:
    result = _result()
    old_signatures = [
        item["signature"] for item in json.loads(S1_EVIDENCE.read_text())["candidates"]
    ]
    replayed = [plan.to_dict()["signature"] for plan in result.compositions[:3]]
    assert replayed == old_signatures
