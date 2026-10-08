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
from cold_storage.modules.layout.domain import composition_placement as placement_domain
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.composition_placement import (
    DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    MAX_COMPOSITION_PLACEMENT_NODE_BUDGET,
    _authority_shapes,
    _canonical_construction_shapes,
    _domain_arrangement,
    _domain_derived_anchors,
    _domain_faces,
    _rectangle,
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
    replayed = enumerate_composition_placements(zone_plan, p1_handoff, site_geometry, node_budget=3)
    assert replayed.canonical_result_hash == result.canonical_result_hash
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
    assert tuple(attempt.family.value for attempt in enumeration.search_attempts[:3]) == (
        "LINEAR_BANDED",
        "CENTRAL_PROCESS_CORE",
        "PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
    )
    assert all(count >= 1 for _, count in enumeration.attempt_count_by_family)
    assert len(enumeration.search_attempts) <= 12
    assert enumeration.initial_family_budget == 10_000
    assert enumeration.continuation_budget == 30_000
    assert all(attempt.construction_domains for attempt in enumeration.search_attempts)
    assert all(len(attempt.role_search_funnel) == 12 for attempt in enumeration.search_attempts)
    assert all(
        domain.engineering_authority is False
        for attempt in enumeration.search_attempts
        for domain in attempt.construction_domains
    )
    peripheral_roles = {
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "changing_room",
        "office",
    }
    for attempt in enumeration.search_attempts:
        evidence = attempt.to_dict()
        assert peripheral_roles <= set(evidence["domain_derived_anchor_path_is_primary_by_role"])
        assert all(
            evidence["domain_derived_anchor_path_is_primary_by_role"][role]
            for role in peripheral_roles
        )
        assert set(evidence["generic_fallback_used_by_role"]) == set(
            evidence["generic_fallback_node_count_by_role"]
        )
        assert all(
            evidence["generic_fallback_used_by_role"][role]
            == (evidence["generic_fallback_node_count_by_role"][role] > 0)
            for role in evidence["generic_fallback_used_by_role"]
        )
    assert all(
        attempt.band_capacity_preflight_status.startswith(("PASS_TO_SEARCH", "UNKNOWN"))
        and attempt.peripheral_capacity_preflight_status.startswith(("PASS_TO_SEARCH", "UNKNOWN"))
        for attempt in enumeration.search_attempts
    )
    assert set(dict(enumeration.deepest_role_attempted_by_family)) == set(
        enumeration.family_coverage_order
    )
    assert set(dict(enumeration.deepest_role_successfully_placed_by_family)) == set(
        enumeration.family_coverage_order
    )
    assert set(dict(enumeration.best_partial_placement_witness_by_family)) == set(
        enumeration.family_coverage_order
    )
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
        f"within {application_result.placements.node_budget} nodes; deepest attempted="
        f"{dict(application_result.placements.deepest_role_attempted_by_family)}; "
        f"deepest successfully placed="
        f"{dict(application_result.placements.deepest_role_successfully_placed_by_family)}; "
        f"failures={dict(application_result.placements.failure_reason_by_family)}"
    )


def test_full_xinzhao_composition_placement_replay_is_deterministic(xinzhao_placement) -> None:
    zone_plan, p1_handoff, site_geometry, first_result = xinzhao_placement
    replay = enumerate_composition_placements(zone_plan, p1_handoff, site_geometry)
    assert replay.canonical_result_hash == first_result.canonical_result_hash
    assert [candidate.canonical_result_hash for candidate in replay.placements.candidates] == [
        candidate.canonical_result_hash for candidate in first_result.placements.candidates
    ]


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
        complete_attempt = next(
            attempt
            for attempt in application_result.placements.search_attempts
            if attempt.composition_identity == candidate.composition_identity
            and attempt.complete_layout_found
        )
        primary_domain_counts = dict(complete_attempt.domain_derived_anchor_count_by_role)
        metric = complete_attempt.metric_reservation_diagnostics
        final_certificates = metric["final_consumed"]
        # R2's verified partner hint precedes DOMAIN. A successful hint need
        # not enumerate later fallback anchors; require its actual provenance.
        assert all(
            primary_domain_counts[role] > 0
            or any(
                role in proof["roles"]
                and proof["certificate_source"] == "DIRECT_FINAL"
                and metric["by_edge"][proof["source_edge_identity"]].get("candidate_accepts", 0) > 0
                for proof in final_certificates
            )
            for role in (
                "packaging_material_storage",
                "secondary_fruit_buffer",
                "frozen_fruit_room",
                "changing_room",
                "office",
            )
        )
        assert sum(dict(complete_attempt.generic_fallback_node_count_by_role).values()) <= (
            complete_attempt.nodes_allocated // 10
        )
        assert candidate.zone_count == 12
        assert {zone.zone_code for zone in candidate.zones} == set(ZONE_CODES)
        by_role = {zone.zone_code: zone for zone in candidate.zones}
        assert len(final_certificates) == len(process_graph().must_adjacencies)
        assert all(
            tuple(by_role[role].bounds_mm for role in proof["roles"])
            == tuple(tuple(bounds) for bounds in proof["endpoint_bounds_mm"])
            for proof in final_certificates
        )
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
                validated = validate_flexible_candidate(authority, zone.width_m, zone.depth_m)
                assert validated["actual_area_m2"] >= Decimal(authority["required_area_m2"])
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


def test_domain_anchors_are_primary_faces_for_all_peripheral_roles(xinzhao_placement) -> None:
    zone_plan, p1_handoff, site_geometry, _ = xinzhao_placement
    binding = bind_layout_authority(zone_plan, p1_handoff, site_geometry)
    composition_result = build_structural_compositions(zone_plan, p1_handoff, site_geometry)
    body = site_geometry.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = tuple(
        normalize_polygon(item, allow_numeric_string=True)
        for item in body["obstacles"]["no_build_zones"]
    )
    authoritative_shapes = _authority_shapes(binding.dimension_authorities, boundary, obstacles)
    min_x, min_y = min(point[0] for point in boundary), min(point[1] for point in boundary)
    max_x, max_y = max(point[0] for point in boundary), max(point[1] for point in boundary)

    first_by_family = {}
    for handoff in composition_result.placement_handoffs:
        first_by_family.setdefault(handoff.family.value, handoff)
    assert set(first_by_family) == {
        "LINEAR_BANDED",
        "CENTRAL_PROCESS_CORE",
        "PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
    }

    roles = (
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "changing_room",
        "office",
    )
    central_face_assignments = []
    for handoff in first_by_family.values():
        bank_sign = 1
        domains = _domain_arrangement(handoff, bank_sign, boundary, binding.dimension_authorities)
        sorting_shape = _canonical_construction_shapes(
            authoritative_shapes["sorting_packaging_room"]
        )[0]
        sorting_x = min_x + (max_x - min_x - sorting_shape.world_width_mm) // 2
        sorting_y = min_y + (max_y - min_y - sorting_shape.world_depth_mm) // 2
        sorting = _rectangle("sorting_packaging_room", sorting_x, sorting_y, sorting_shape)
        placed = {"sorting_packaging_room": sorting}
        faces = _domain_faces(handoff, bank_sign)
        left, bottom, right, top = sorting.bounds_mm
        for role in roles:
            shape = _canonical_construction_shapes(authoritative_shapes[role])[0]
            origins = _domain_derived_anchors(
                role,
                shape,
                handoff,
                domains,
                bank_sign,
                placed,
                boundary,
                obstacles,
            )
            assert origins
            assert origins == _domain_derived_anchors(
                role,
                shape,
                handoff,
                domains,
                bank_sign,
                placed,
                boundary,
                obstacles,
            )
            axis, sign = faces[role]
            if axis == "X":
                expected_x = right if sign > 0 else left - shape.world_width_mm
                assert {origin[0] for origin in origins} == {expected_x}
            else:
                expected_y = top if sign > 0 else bottom - shape.world_depth_mm
                assert {origin[1] for origin in origins} == {expected_y}
            if handoff.family.value == "CENTRAL_PROCESS_CORE" and role in roles[:3]:
                central_face_assignments.append(faces[role])

    assert len(set(central_face_assignments)) == 3


def test_shipping_office_preflight_rejects_nonadjacent_seed_and_accepts_authoritative_seed(
    xinzhao_placement, monkeypatch
) -> None:
    zone_plan, p1_handoff, site_geometry, application_result = xinzhao_placement
    candidate = application_result.placements.candidates[0]
    by_role = {zone.zone_code: zone for zone in candidate.zones}
    composition_result = build_structural_compositions(zone_plan, p1_handoff, site_geometry)
    handoff = next(
        item
        for item in composition_result.placement_handoffs
        if item.composition_identity == candidate.composition_identity
    )
    binding = bind_layout_authority(zone_plan, p1_handoff, site_geometry)
    body = site_geometry.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = tuple(
        normalize_polygon(item, allow_numeric_string=True)
        for item in body["obstacles"]["no_build_zones"]
    )
    office = by_role["office"]
    office_shape = placement_domain._Shape(
        int(office.width_m * 1000), int(office.depth_m * 1000), office.rotation_deg
    )
    bank_sign = 1
    domains = _domain_arrangement(handoff, bank_sign, boundary, binding.dimension_authorities)
    placed = {role: rect for role, rect in by_role.items() if role != "office"}

    def diagnostics() -> placement_domain._SearchDiagnostics:
        result = placement_domain._SearchDiagnostics(node_limit=20_000)
        result.funnel["office"] = {
            name: 0
            for name in (
                "domain_derived_anchor_count",
                "generic_fallback_anchor_count",
                "candidate_rectangle_attempt_count",
                "site_rejection_count",
                "obstacle_rejection_count",
                "overlap_rejection_count",
                "domain_side_rejection_count",
                "must_edge_rejection_count",
            )
        }
        return result

    accepted_diagnostics = diagnostics()
    accepted = placement_domain._shipping_office_seed(
        by_role["shipping_channel"],
        placed,
        (office_shape,),
        handoff,
        domains,
        bank_sign,
        boundary,
        obstacles,
        accepted_diagnostics,
    )
    assert accepted is not None
    assert accepted_diagnostics.shipping_office_status == "PASS"
    assert placement_domain.rectangles_share_positive_edge(
        _rectangle("office", *accepted[1], accepted[0]), by_role["shipping_channel"]
    )

    shipping = by_role["shipping_channel"]
    sorting = by_role["sorting_packaging_room"]
    face_axis, face_sign = _domain_faces(handoff, bank_sign)["office"]
    legal_nonadjacent_origin = None
    for origin in placement_domain._face_anchors(
        sorting, office_shape, face_axis, face_sign, boundary, obstacles, placed
    ):
        proposed = _rectangle("office", *origin, office_shape)
        if placement_domain._candidate_rejection(
            proposed, placed, boundary, obstacles
        ) is None and not placement_domain.rectangles_share_positive_edge(proposed, shipping):
            legal_nonadjacent_origin = origin
            break
    assert legal_nonadjacent_origin is not None
    monkeypatch.setattr(
        placement_domain,
        "_domain_derived_anchors",
        lambda *args, **kwargs: (legal_nonadjacent_origin,),
    )
    monkeypatch.setattr(
        placement_domain,
        "_generic_fallback_anchors",
        lambda *args, **kwargs: (legal_nonadjacent_origin,),
    )
    rejected_diagnostics = diagnostics()
    rejected = placement_domain._shipping_office_seed(
        shipping,
        placed,
        (office_shape,),
        handoff,
        domains,
        bank_sign,
        boundary,
        obstacles,
        rejected_diagnostics,
    )
    assert rejected is None
    assert rejected_diagnostics.shipping_office_status == "NO_AUTHORITY_VALID_OFFICE_ATTACHMENT"
    assert rejected_diagnostics.funnel["office"]["must_edge_rejection_count"] == 1


def test_shipping_office_capacity_preflight_is_only_a_bounding_box_necessary_check() -> None:
    boundary = ((0, 0), (10_000, 0), (10_000, 10_000), (0, 10_000))
    possible = placement_domain._shipping_office_interface_preflight_status(
        (placement_domain._Shape(6_000, 3_000, 0),),
        (placement_domain._Shape(5_000, 2_000, 0),),
        boundary,
    )
    assert possible == "PASS_TO_SEARCH_SITE_BOUNDS_NECESSARY_CONDITION"

    impossible = placement_domain._shipping_office_interface_preflight_status(
        (placement_domain._Shape(4_000, 4_000, 0),),
        (placement_domain._Shape(4_000, 4_000, 0),),
        ((0, 0), (5_000, 0), (5_000, 5_000), (0, 5_000)),
    )
    assert impossible == "PROVABLY_NO_SHARED_EDGE_CAPACITY_IN_SITE_BOUNDS"


def test_domain_capacity_preflight_fails_only_on_proven_necessary_condition() -> None:
    boundary = ((0, 0), (10_000, 0), (10_000, 10_000), (0, 10_000))
    flexible_authority = {
        "dimension_mode": "FLEXIBLE_RECTANGLE",
        "required_area_m2": "80",
    }
    flexible_status = placement_domain._capacity_preflight_status(
        (("changing_room",),),
        {"changing_room": flexible_authority},
        {"changing_room": (placement_domain._Shape(80_000, 1_000, 0),)},
        boundary,
    )
    assert flexible_status == "PASS_TO_SEARCH_GROSS_AREA_AND_SITE_BOUNDS"

    area_status = placement_domain._capacity_preflight_status(
        (("raw_fruit_buffer", "primary_precooling_room"),),
        {
            "raw_fruit_buffer": {"dimension_mode": "FIXED", "required_area_m2": "60"},
            "primary_precooling_room": {"dimension_mode": "FIXED", "required_area_m2": "50"},
        },
        {
            "raw_fruit_buffer": (placement_domain._Shape(8_000, 7_500, 0),),
            "primary_precooling_room": (placement_domain._Shape(5_000, 10_000, 0),),
        },
        boundary,
    )
    assert area_status == "PROVABLY_EXCEEDS_BUILDABLE_SITE_AREA"


def test_s1_topology_signatures_are_unchanged() -> None:
    result = _result()
    old_signatures = [
        item["signature"] for item in json.loads(S1_EVIDENCE.read_text())["candidates"]
    ]
    replayed = [plan.to_dict()["signature"] for plan in result.compositions[:3]]
    assert replayed == old_signatures
