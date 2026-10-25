"""R9 synthetic geometry, soft domain and accepted-baseline transition contracts."""

from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
from cold_storage.modules.layout.infrastructure import stage_b_area_efficiency as r5
from cold_storage.modules.layout.infrastructure import stage_b_changing_frontage_corridor as r9
from cold_storage.modules.layout.infrastructure import stage_b_first_feasible_recovery as r7
from cold_storage.modules.layout.infrastructure import stage_b_frontage_joint_search as r6
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import (
    bind_native_portal_positions,
)
from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
    OrToolsGlobalCompositionSolver,
)
from tests.r9_changing_joint_synthetic import build_scene, solve_scene
from tests.unit.test_v222_stage_b_frontage_joint_search import complete_context, frontier_snapshot


def hard_proto(model):
    proto = deepcopy(model.m.proto)
    proto.search_strategy.clear()
    proto.clear_solution_hint()  # Accepted-baseline hints are soft metadata, not constraints.
    return str(proto)


@pytest.mark.parametrize("production", [True, False])
def test_joint_position_changes_real_route_with_identical_physical_domain(production):
    old, new = [solve_scene(j, production=production) for j in (False, True)]
    for result in (old, new):
        assert result["status"] in {"FEASIBLE", "OPTIMAL"}
        assert result["topology"]["valid"] and result["topology"]["hole_count"] == 0
        assert result["topology"]["connected_component_count"] == 1
        assert result["route_errors"] == [] and all(result["must_contacts"].values())
        assert result["independent_access"]["status"] == "PASS"
        assert result["independent_access"]["route_length_m"] * 1000 == result["route"]["length_mm"]
        assert result["changing_face"] == "EAST"
        assert result["objective"] == old["objective"]
    assert old["boxes"]["changing_room"] == (4000, 4000, 8000, 6000)
    assert new["boxes"]["changing_room"] == (6000, 4000, 10000, 6000)
    assert old["route"]["length_mm"] == 9000 and new["route"]["length_mm"] == 7000
    assert new["route"]["turn_count"] == old["route"]["turn_count"] == 2
    assert new["work"] > old["work"]  # New real metadata work is billed, not hidden.


def test_r9_metadata_has_no_definitions_constraints_objective_or_hint_changes():
    c, m = build_scene(reference=True)
    r6.apply_reference_area_guidance(m, c)
    r6.apply_frontage_joint_search(m, c)
    before = hard_proto(m)
    receipt = r9.apply_changing_frontage_corridor_search(m, c)
    assert hard_proto(m) == before and not m.m.validate()
    assert receipt["new_variables"] == receipt["new_constraints"] == 0
    assert receipt["portal_width_mm"] == 1500
    assert c.ledger.resource_events["R9_PHYSICAL_REFERENCE_READ"] == 20
    assert c.ledger.resource_events["R9_JOINT_STRATEGY_METADATA"] > 0
    assert len(receipt["variable_indices"]) == len(set(receipt["variable_indices"]))


@pytest.mark.parametrize("position", [0, 1])
@pytest.mark.parametrize("face", [0, 1])
def test_every_original_physical_and_portal_assignment_remains_feasible(position, face):
    for joint in (False, True):
        c, m = build_scene(reference=True)
        m.m.add(m.position == position)
        m.m.add(m.choice == face)
        before = hard_proto(m)
        if joint:
            r9.apply_changing_frontage_corridor_search(m, c)
        assert hard_proto(m) == before
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.max_time_in_seconds = 2
        assert solver.solve(m.m) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


@pytest.mark.parametrize("face", range(4))
def test_boundary_direction_is_derived_from_current_site_not_historical_coordinates(face):
    c, m = build_scene(reference=True)
    c.entrances["main_entrance"] = [
        ((0, 5000), (0, 7000)),
        ((16000, 5000), (16000, 7000)),
        ((5000, 0), (7000, 0)),
        ((5000, 14000), (7000, 14000)),
    ][face]
    receipt = r9.apply_changing_frontage_corridor_search(m, c)
    assert receipt["physical_edge"] == ("x", "X", "y", "Y")[face]
    assert m.m.proto.search_strategy[0].exprs[0].vars[0] == m.routes[0]["to_faces"][face].index


@pytest.mark.parametrize(
    "fault",
    ["context", "duplicate", "authority", "profile", "width", "points", "foreign", "missing"],
)
def test_bad_references_refuse_before_metadata_mutation(fault):
    c, m = build_scene(reference=True)
    if fault == "context":
        m.c = object()
    elif fault == "duplicate":
        m.routes.append(m.routes[0])
    elif fault == "authority":
        m.routes[0]["req"] = dict(m.routes[0]["req"], identity="foreign")
    elif fault == "profile":
        c.binding.access_requirements[0]["profile_identity"] = "not-approved"
    elif fault == "width":
        m.routes[0]["pw"] = 1000
    elif fault == "points":
        m.routes[0]["points"].pop()
    elif fault == "foreign":
        m.rooms["changing_room"]["X"] = cp_model.CpModel().new_int_var(0, 10, "foreign")
    else:
        m.routes = []
    before = str(m.m.proto)
    with pytest.raises((LayoutAuthorityError, KeyError)):
        r9.apply_changing_frontage_corridor_search(m, c)
    assert str(m.m.proto) == before


def test_metadata_precharge_failure_does_not_partially_reorder(monkeypatch):
    c, m = build_scene(reference=True)
    original = c.ledger.charge

    def charge(kind, work):
        if kind == "R9_JOINT_STRATEGY_METADATA":
            raise LayoutAuthorityError("STAGE_A_RESOURCE_LIMIT")
        return original(kind, work)

    monkeypatch.setattr(c.ledger, "charge", charge)
    before = str(m.m.proto)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        r9.apply_changing_frontage_corridor_search(m, c)
    assert str(m.m.proto) == before


def test_p07_short_edge_cannot_fit_original_door_and_recorded_path_backtracks():
    # Immutable R8 P07 facts, mm; these are mechanism tests, not a new factory layout.
    m = cp_model.CpModel()
    active = m.new_bool_var("east")
    pos = m.new_int_var(23650, 24658, "door")
    bind_native_portal_positions(m, pos, 23650, 24658, 1500, active, 80000, "p07")
    m.add(active == 1)
    assert cp_model.CpSolver().solve(m) == cp_model.INFEASIBLE  # this fixed face only
    path = [(75460, 25275), (58897, 25275), (58897, 25658), (57147, 25658), (57147, 24658)]
    length = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(path, path[1:], strict=False))
    direct = abs(path[-1][0] - path[0][0]) + abs(path[-1][1] - path[0][1])
    assert length == 19696 and length - direct == 766
    assert Fraction(39683, 1008) > 39


def test_p03_p06_room_shortening_retreats_door_and_lengthens_actual_route():
    for xmax, length in ((41031, 35054), (39719, 36366)):
        path = [(75460, 25275), (74460, 25275), (74460, 24650), (xmax, 24650)]
        assert (
            sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(path, path[1:], strict=False))
            == length
            == 76085 - xmax
        )
    assert 36366 - 35054 == 41031 - 39719


def test_hole_witness_still_fails_original_exact_union():
    ring = [
        (0, 0, 6000, 1000),
        (0, 5000, 6000, 6000),
        (0, 1000, 1000, 5000),
        (5000, 1000, 6000, 5000),
    ]
    result = inspect_rectangular_union(ring)
    assert not result["valid"] and result["hole_count"] == 1


def test_first_stage_options_preparation_and_engine_are_identical_to_r7():
    c, m = build_scene(reference=True)
    r7port = r7.StageBFirstFeasibleRecoveryFairSolver()
    r9port = r9.StageBChangingFrontageCorridorFairSolver()
    for port in (r7port, r9port):
        port.start_handoff(c.ledger, 1)
        assert "final_model_search" not in port._continuation_options(c)
        assert not port.native.improving
    assert r9port.native.prepare_first_stage.__func__ is r7port.native.prepare_first_stage.__func__
    assert r9port.native._run.__func__ is r7port.native._run.__func__
    assert not m.m.proto.search_strategy


def test_accepted_transition_keeps_model_budget_baseline_and_no_solve(monkeypatch):
    c, m = build_scene(reference=True)
    port = r9.StageBChangingFrontageCorridorFairSolver()
    port.start_handoff(c.ledger, 1)
    port._final_guidance(m, c)
    solver, status = port.native._run(c, m.m, 2, "ALL_ROOMS_ALL_ACCESS")
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    monkeypatch.setattr(r5, "area_efficiency_snapshot", lambda candidate, *_: candidate)
    baseline = frontier_snapshot("4", "4")
    port.observe_validated_candidate(
        c,
        SimpleNamespace(source_composition_hash="synthetic-handoff"),
        baseline,
        "ENGINEERING_ACCEPTED",
    )
    saved = deepcopy(port.baseline)
    before = hard_proto(m)
    calls = len(c.ledger.attempts)
    shares = (port.native.native_share, port.native.work_share, port.native.checked_share)
    with monkeypatch.context() as patch:
        patch.setattr(
            cp_model.CpSolver, "solve", lambda *_: pytest.fail("transition must not Solve")
        )
        patch.setattr(cp_model.CpModel, "clone", lambda *_: pytest.fail("same model required"))
        receipt = port._continuation_options(c)["accepted_model_guidance"](m, solver)
    assert hard_proto(m) == before and port.baseline == saved
    assert receipt["changing_joint_search"]["extra_native_calls"] == 0
    assert len(c.ledger.attempts) == calls and port.native._feedback_model is m.m
    assert shares == (port.native.native_share, port.native.work_share, port.native.checked_share)
    assert m.m.proto.search_strategy[0].exprs[0].vars[0] == m.routes[0]["to_faces"][1].index
    # Fixed proxy + a valid current Hint is an explicit negative control:
    # metadata cannot promise a new quality witness or override acceptance.
    again, again_status = port.native._run(c, m.m, 2, "ALL_ROOMS_ALL_ACCESS")
    assert again_status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert again.value(m.position) == solver.value(m.position)
    assert port.baseline == saved
    with pytest.raises(LayoutAuthorityError, match="ALREADY_ACTIVATED"):
        port.native.begin_improvement(m, c, solver)
    _, status = port.native._run(c, m.m, 1e-9, "ALL_ROOMS_ALL_ACCESS")
    assert status == cp_model.UNKNOWN and port.baseline == saved


@pytest.mark.parametrize("status", ["TOPOLOGY_REJECTED", "UNKNOWN", "EXAMINED_WITNESS"])
def test_unaccepted_witness_never_activates_joint_search(status):
    c, m = build_scene(reference=True)
    port = r9.StageBChangingFrontageCorridorFairSolver()
    port.start_handoff(c.ledger, 1)
    port.observe_validated_candidate(c, None, {}, status)
    assert port.baseline is None and port.search_frontier is None and not port.native.improving
    assert not m.m.proto.search_strategy


@pytest.mark.parametrize("old", [None, r7.POLICY_HASH, r6.POLICY_HASH])
def test_old_policy_cannot_authorize_r9(old):
    c, m = build_scene(reference=True)
    c.ledger.execution_authorization.decision = {"balanced_quality_policy_hash": old}
    port = r9.StageBChangingFrontageCorridorFairSolver()
    port.start_handoff(c.ledger, 1)
    with pytest.raises(LayoutAuthorityError, match="BOUND_POLICY_REQUIRED"):
        port.solutions(c, None)
    assert not c.ledger.attempts


def test_original_validators_frontier_hint_and_both_comparators_are_inherited():
    assert (
        r9._ChangingFrontageCorridorNative.iter_solutions
        is OrToolsGlobalCompositionSolver.iter_solutions
    )
    for name in (
        "observe_validated_candidate",
        "_refresh_validated_hint",
        "_observe_search_frontier",
    ):
        assert getattr(r9.StageBChangingFrontageCorridorFairSolver, name) is getattr(
            r7.StageBFirstFeasibleRecoveryFairSolver, name
        )
    assert r5.COMPARISON_POLICY == "same-handoff-nine-metrics-plus-three-area-allocations@1.0.0"


@pytest.mark.parametrize("ordinal", range(6))
def test_all_six_handoff_models_have_identical_hard_first_stage_and_postbaseline_domain(
    ordinal, monkeypatch
):
    from tests.unit.test_v222_stage_b_multi_solution import EnumerationLease

    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda *_: pytest.fail("20t Native forbidden"))
    c, handoffs = complete_context()
    c.ledger.solver_history_verified = True
    c.ledger.execution_authorization = EnumerationLease()
    old = r7._FirstFeasibleRecoveryNative(c.ledger, 6 - ordinal)
    new = r9._ChangingFrontageCorridorNative(c.ledger, 6 - ordinal)
    a = old._new_final_model(c, handoffs[ordinal])
    b = new._new_final_model(c, handoffs[ordinal])
    assert str(a.m.proto) == str(b.m.proto)
    old.prepare_first_stage(a, c)
    new.prepare_first_stage(b, c)
    assert str(a.m.proto) == str(b.m.proto)
    r6.apply_frontage_joint_search(b, c)
    before = hard_proto(b)
    r9.apply_changing_frontage_corridor_search(b, c)
    assert hard_proto(b) == before and not b.m.validate()


def test_different_v2_organization_is_not_promoted_to_formal_pareto():
    from tests.unit.test_v222_stage_b_area_efficiency import area_snapshot

    before = area_snapshot()
    after = deepcopy(before)
    after["functional_diversity"]["meaningful_construction_hash"] = "other-v2"
    assert r5.compare_area_efficient_quality(before, after)["status"] == "NOT_COMPARABLE_STRUCTURE"


def test_exhausted_share_cannot_start_joint_phase_or_lose_baseline():
    c, m = build_scene(reference=True)
    port = r9.StageBChangingFrontageCorridorFairSolver()
    port.start_handoff(c.ledger, 1)
    port._final_guidance(m, c)
    port.baseline = frontier_snapshot("4", "4")
    saved = deepcopy(port.baseline)
    port.native.native_share = 0
    before = str(m.m.proto)
    with pytest.raises(LayoutAuthorityError, match="SHARE_EXHAUSTED"):
        port.native.begin_improvement(m, c, None)
    assert str(m.m.proto) == before and port.baseline == saved
    assert not c.ledger.attempts and not port.native.improving
