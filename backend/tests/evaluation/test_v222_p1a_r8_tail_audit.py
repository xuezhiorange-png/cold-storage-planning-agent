"""Evidence locks and exact-origin sweep tests for the R8 read-only audit."""

from __future__ import annotations

import json
from pathlib import Path

from cold_storage.modules.layout.domain.placement import (
    _rectangle_from_mm,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
)
from tests.evaluation.v222_p1a_r8_tail_audit import (
    _closed_obstacle_forbidden_origins,
    _integer_origin_witness,
    _positive_overlap_forbidden_origins,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a"


def _load(name: str) -> dict[str, object]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_integer_origin_sweep_matches_complete_small_domain_enumeration() -> None:
    cases = (
        ((0, 0, 4, 4), []),
        ((0, 0, 4, 4), [(0, 0, 4, 4)]),
        ((0, 0, 4, 4), [(0, 0, 1, 4), (2, 0, 4, 4)]),
        ((-2, 3, 3, 7), [(-2, 3, -1, 7), (1, 3, 3, 7)]),
        ((0, 0, 5, 5), [(1, 1, 2, 2), (3, 0, 5, 4)]),
    )
    for domain, forbidden in cases:
        expected = next(
            (
                (x, y)
                for y in range(domain[1], domain[3] + 1)
                for x in range(domain[0], domain[2] + 1)
                if not any(
                    left <= x <= right and bottom <= y <= top
                    for left, bottom, right, top in forbidden
                )
            ),
            None,
        )
        assert _integer_origin_witness(domain, list(forbidden)) == expected


def test_forbidden_origin_transform_matches_exact_rectangle_predicates() -> None:
    obstacle_bounds = (3, 2, 5, 4)
    zone_bounds = (3, 2, 5, 4)
    width_mm, depth_mm = 2, 2
    obstacle = (
        (obstacle_bounds[0], obstacle_bounds[1]),
        (obstacle_bounds[2], obstacle_bounds[1]),
        (obstacle_bounds[2], obstacle_bounds[3]),
        (obstacle_bounds[0], obstacle_bounds[3]),
    )
    zone = _rectangle_from_mm("fixed_zone", *obstacle_bounds[:2], 2, 2, 0)
    obstacle_forbidden = _closed_obstacle_forbidden_origins(obstacle_bounds, width_mm, depth_mm)
    zone_forbidden = _positive_overlap_forbidden_origins(zone_bounds, width_mm, depth_mm)

    for y in range(0, 7):
        for x in range(0, 7):
            candidate = _rectangle_from_mm("candidate", x, y, width_mm, depth_mm, 0)
            closed_collision = (
                obstacle_forbidden[0] <= x <= obstacle_forbidden[2]
                and obstacle_forbidden[1] <= y <= obstacle_forbidden[3]
            )
            positive_overlap = (
                zone_forbidden[0] <= x <= zone_forbidden[2]
                and zone_forbidden[1] <= y <= zone_forbidden[3]
            )
            assert closed_collision is rectangle_intersects_closed_obstacle(candidate, obstacle)
            assert positive_overlap is rectangles_overlap(candidate, zone)


def test_956e_package_slot_conflict_is_proven_without_claiming_global_infeasibility() -> None:
    census = _load("xinzhao_p1a_r8_tail_zone_option_census.json")
    lifecycle = _load("xinzhao_p1a_r8_packaging_option_lifecycle.json")
    feasibility = _load("xinzhao_p1a_r8_tail_feasibility_search.json")

    package = census["main_skeleton_only"]["packaging_material_storage"]
    assert census["target_skeleton_hash"] == (
        "sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc"
    )
    assert (
        census["main_process_seed_provenance"]["main_process_skeleton_hash"]
        == (census["target_skeleton_hash"])
    )
    assert package["dimension_authority"]["dimension_mode"] == "DETERMINISTIC_GRID_RECTANGLE"
    assert package["dimension_authority"]["geometry"]["width_m"] == "17.3"
    assert package["dimension_authority"]["geometry"]["depth_m"] == "14.5"
    assert package["final_option_count"] == 0
    assert package["rejected_rectangle_details_complete"] is True
    assert len(package["rejected_rectangles"]) == package["raw_candidate_attempt_count"]

    exact = lifecycle["general_fallback_anchor_counterfactual"]["exact_fixed_skeleton_occupancy"]
    assert exact["dimensions_are_exhaustive"] is True
    assert exact["all_authorized_orientations_exhausted"] is True
    assert exact["status"] == "NO_AUTHORIZED_ORIENTATION_HAS_SITE_NO_BUILD_SKELETON_SLOT"
    assert all(
        row["site_only_witness_origin_mm"] is not None for row in exact["orientation_results"]
    )
    assert all(
        row["without_no_build_but_with_skeleton_witness_origin_mm"] is not None
        for row in exact["orientation_results"]
    )
    assert all(
        row["without_skeleton_but_with_no_build_witness_origin_mm"] is not None
        for row in exact["orientation_results"]
    )
    assert all(
        row["combined_site_no_build_skeleton_witness_origin_mm"] is None
        for row in exact["orientation_results"]
    )
    assert (
        feasibility["packaging_has_no_site_no_build_skeleton_slot_for_authoritative_dimensions"]
        is True
    )
    assert feasibility["infeasibility_proven"] is False
    assert feasibility["global_geometric_infeasibility_proven"] is False
    replay = feasibility["real_tool7_replay"]
    assert replay["project_layout_validated"] is True
    assert replay["p2_complete"] is True
    assert replay["zone_count"] == 12
    assert replay["access_pass_count"] == replay["access_requirement_count"] == 12
    assert replay["truck_route_validated"] is True
    assert replay["building_footprint_present"] is True


def test_tail_order_and_personnel_states_do_not_create_packaging_capacity() -> None:
    lifecycle = _load("xinzhao_p1a_r8_packaging_option_lifecycle.json")
    feasibility = _load("xinzhao_p1a_r8_tail_feasibility_search.json")
    states = lifecycle["states"]

    for state_name in (
        "STATE_A_MAIN_SKELETON_ONLY",
        "STATE_B_FIRST_RANKED_CHANGING",
        "STATE_C_FIRST_RANKED_OFFICE",
        "STATE_D_FIRST_CHANGING_AND_COMPATIBLE_OFFICE",
    ):
        state = states[state_name]
        if state_name != "STATE_A_MAIN_SKELETON_ONLY" and not state["applicable"]:
            continue
        package = state["packaging"]
        assert package["final_option_count"] == 0
        assert package["rejected_rectangle_details_complete"] is True
        assert len(package["rejected_rectangles"]) == package["raw_candidate_attempt_count"]

    alternatives = states["STATE_E_EXPLORED_CHANGING_OFFICE_ALTERNATIVES"]
    assert alternatives["explored_compatible_pairs"] == 36
    assert alternatives["search_exhausted"] is True
    assert alternatives["option_count_distribution"] == {"0": 36}
    assert all(len(pair["packaging_rejected_rectangles"]) > 0 for pair in alternatives["pairs"])

    strategies = {
        row["strategy"] + "/" + row["search_phase"]: row for row in feasibility["strategies"]
    }
    assert strategies["PERSONNEL_FIRST/STRUCTURED"]["search_exhausted"] is True
    assert strategies["PERSONNEL_FIRST/STRUCTURED"]["nodes_used"] == 43
    assert strategies["SUPPORT_FIRST/STRUCTURED"]["nodes_used"] == 1
    assert strategies["MOST_CONSTRAINED_FIRST/STRUCTURED"]["nodes_used"] == 1
    assert strategies["SUPPORT_FIRST/GENERAL_FALLBACK"]["nodes_used"] == 1
    assert all(row["p2d_reached"] is False for row in feasibility["strategies"])

    causes = feasibility["root_cause_classification"]
    assert causes["TAIL_ORDERING_STARVATION"] is False
    assert causes["PERSONNEL_BRANCH_STARVES_SUPPORT"] is False
    assert causes["TAIL_SHARE_ALLOCATION_STARVATION"] is True
    assert causes["TAIL_SHARE_IS_PRIMARY_CAUSE_OF_ZERO_PACKAGING_OPTIONS"] is False
    assert causes["TRUE_ENUMERATED_GEOMETRY_CONFLICT"] is True


def test_live_budget_accounting_discrepancy_is_explicit_and_not_rewritten() -> None:
    budget = _load("xinzhao_p1a_r8_tail_budget_accounting.json")
    assert budget["production_global_budget"] == 120
    assert budget["production_tail_node_limit_for_956e"] == 12
    assert budget["production_tail_nodes_used_for_956e"] == 12
    assert budget["production_global_node_visits"] == 104
    assert budget["production_global_nodes_unused"] == 16
    assert budget["discovery_lane_budget"] == 45
    lifecycles = budget["target_lane_skeleton_tail_lifecycles"]
    target = next(
        row
        for row in lifecycles
        if row["skeleton_hash"]
        == "sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc"
    )
    assert target["tail_node_limit"] == 12
    assert budget["target_lane_constructed_seed_count"] == len(
        budget["target_lane_constructed_seed_hashes"]
    )
    assert budget["saved_r7_metrics_global_node_visits"] == 92
    assert budget["saved_r7_metrics_global_nodes_remaining"] == 28
    assert budget["saved_vs_live_accounting_discrepancy"]["status"] == "PRESENT"
    assert budget["unused_global_nodes_recyclable_by_current_scheduler"] is False
    assert budget["tail_share_starvation_confirmed"] is True
