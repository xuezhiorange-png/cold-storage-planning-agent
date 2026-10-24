"""R7 synthetic native/phase tests and six-Handoff construction, never MAIN."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_area_efficiency as r5
from cold_storage.modules.layout.infrastructure import stage_b_first_feasible_recovery as r7
from cold_storage.modules.layout.infrastructure import stage_b_frontage_joint_search as r6
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel
from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
    OrToolsGlobalCompositionSolver,
)
from tests.r6_frontage_synthetic import build_scene
from tests.r7_search_ablation import prepare, run, validate_scene
from tests.unit.test_v222_stage_b_frontage_joint_search import (
    complete_context,
    frontier_snapshot,
    reference_setup,
)


@pytest.mark.parametrize("repeat", range(3))
def test_production_configuration_recovers_first_witness_search(repeat):
    results = [run(arm) for arm in "ABC"]
    recovered = run("C", delayed=True)
    a, b, c = results
    for result in [*results, recovered]:
        assert result["status"] in {"FEASIBLE", "OPTIMAL"}
        assert result["first"] and result["geometry"]["valid"]
        assert result["geometry"]["topology"]["hole_count"] == 0
        assert result["geometry"]["topology"]["connected_component_count"] == 1
        assert result["geometry"]["route_errors"] == []
        assert "cp_model_presolve: true" in result["parameters"]
        assert "search_branching: PARTIAL_FIXED_SEARCH" in result["parameters"]
    assert a["first"]["objective"] == b["first"]["objective"] == c["first"]["objective"]
    assert a["first"]["branches"] == b["first"]["branches"] == recovered["first"]["branches"]
    assert c["first"]["branches"] > recovered["first"]["branches"]
    assert c["first"]["conflicts"] > recovered["first"]["conflicts"]
    assert c["deterministic_seconds"] > recovered["deterministic_seconds"]
    # Wall-clock improvements are measured evidence, never a flaky time assertion.


def test_original_scene_is_a_negative_control_under_production_presolve():
    rows = [run(arm, packing=False) for arm in "ABC"]
    assert all(row["first"]["branches"] == 0 and row["geometry"]["valid"] for row in rows)


def test_keep_original_no_presolve_comparison_separate_from_production_evidence():
    a, c = [run(arm, packing=False, production=False) for arm in ("A", "C")]
    assert a["geometry"]["valid"] and c["geometry"]["valid"]
    assert a["geometry"]["route_length_mm"] == 12000
    assert c["geometry"]["route_length_mm"] == 9000
    assert not a["production"] and not c["production"]


@pytest.mark.parametrize("group", [0, 1, 7, 11])
def test_isolated_frontage_groups_distinguish_branching_cost(group):
    base = run("B")
    isolated = run("C", drop_groups=tuple(i for i in range(12) if i != group))
    assert isolated["geometry"]["valid"]
    if group in (0, 11):
        assert isolated["first"]["conflicts"] > base["first"]["conflicts"]
    else:
        assert isolated["first"]["branches"] == base["first"]["branches"]


def test_first_stage_is_exact_r5_proto_with_reference_preparation():
    _, a = prepare("A", packing=False)
    _, b = prepare("B", packing=False)
    assert str(a.m.proto) == str(b.m.proto)
    context, model = build_scene(reference=True)
    port = r7.StageBFirstFeasibleRecoveryFairSolver()
    port.start_handoff(context.ledger, 1)
    options = port._continuation_options(context)
    assert "final_model_search" not in options
    assert "accepted_model_guidance" in options and "accepted_continuation_guidance" in options
    port._final_guidance(model, context)
    model.m.add_decision_strategy(
        [r["corridor"] for r in model.routes], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE
    )
    assert str(model.m.proto) == str(a.m.proto)
    assert "R6_FRONTAGE_REFERENCE_READ" not in context.ledger.resource_events


def test_accepted_transition_uses_same_model_ledger_share_and_no_extra_solve(monkeypatch):
    context, model = build_scene(reference=True)
    port = r7.StageBFirstFeasibleRecoveryFairSolver()
    port.start_handoff(context.ledger, 1)
    engine = port.native
    port._final_guidance(model, context)
    model.m.add_decision_strategy(
        [r["corridor"] for r in model.routes], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE
    )
    original = (
        [str(v) for v in model.m.proto.variables],
        [str(c) for c in model.m.proto.constraints],
    )
    shares = (engine.native_share, engine.work_share, engine.checked_share)
    first, status = engine._run(context, model.m, 2, "ALL_ROOMS_ALL_ACCESS")
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL) and validate_scene(model, first)["valid"]
    assert len(model.m.proto.search_strategy) == 1 and not engine.improving
    monkeypatch.setattr(r5, "area_efficiency_snapshot", lambda candidate, *_: candidate)
    baseline = frontier_snapshot("4", "4")
    port.observe_validated_candidate(
        context,
        SimpleNamespace(source_composition_hash="synthetic-handoff"),
        baseline,
        "ENGINEERING_ACCEPTED",
    )
    baseline_copy = deepcopy(port.baseline)
    calls = len(context.ledger.attempts)
    with monkeypatch.context() as patch:
        patch.setattr(
            cp_model.CpSolver, "solve", lambda *_: pytest.fail("transition must not Solve")
        )
        patch.setattr(
            cp_model.CpModel, "clone", lambda *_: pytest.fail("transition must not clone")
        )
        receipt = port._continuation_options(context)["accepted_model_guidance"](model, first)
    assert receipt["frontage_activation"] == "AFTER_INDEPENDENT_ENGINEERING_ACCEPTANCE"
    assert receipt["extra_native_calls"] == 0 and len(context.ledger.attempts) == calls
    assert model.m is engine._feedback_model is engine._area_model
    assert len(model.m.proto.search_strategy) == 13
    assert model.m.proto.search_strategy[0].exprs[0].vars[0] == model.routes[0]["to_faces"][1].index
    assert original == (
        [str(v) for v in model.m.proto.variables],
        [str(c) for c in model.m.proto.constraints],
    )
    assert context.ledger.resource_events["R7_DEFERRED_STRATEGY_REORDER"] > 0
    assert engine.ledger is context.ledger and shares == (
        engine.native_share,
        engine.work_share,
        engine.checked_share,
    )
    _, status = engine._run(context, model.m, 2, "ALL_ROOMS_ALL_ACCESS")
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    assert len(context.ledger.attempts) == calls + 1
    assert port.baseline == baseline_copy and not model.m.validate()
    current = str(model.m.proto)
    with pytest.raises(LayoutAuthorityError, match="ALREADY_ACTIVATED"):
        engine.begin_improvement(model, context, first)
    assert str(model.m.proto) == current
    _, status = engine._run(context, model.m, 1e-9, "ALL_ROOMS_ALL_ACCESS")
    assert status == cp_model.UNKNOWN and port.baseline == baseline_copy
    assert len(context.ledger.attempts) == calls + 2


@pytest.mark.parametrize("accepted", ["EXAMINED_WITNESS", "UNKNOWN", "TOPOLOGY_REJECTED"])
def test_unaccepted_feedback_does_not_create_baseline_or_advance_frontier(accepted):
    context, model = build_scene(reference=True)
    port = r7.StageBFirstFeasibleRecoveryFairSolver()
    port.start_handoff(context.ledger, 1)
    port._final_guidance(model, context)
    port.observe_validated_candidate(context, None, {}, accepted)
    assert port.baseline is None and port.search_frontier is None
    assert not model.m.proto.search_strategy and not port.native.improving


def test_no_remaining_share_refuses_frontage_before_any_mutation():
    context, model = build_scene(reference=True)
    port = r7.StageBFirstFeasibleRecoveryFairSolver()
    port.start_handoff(context.ledger, 1)
    port._final_guidance(model, context)
    port.baseline = frontier_snapshot("4", "4")
    saved_baseline = deepcopy(port.baseline)
    port.native.native_share = 0
    before = str(model.m.proto)
    with pytest.raises(LayoutAuthorityError, match="SHARE_EXHAUSTED"):
        port.native.begin_improvement(model, context, None)
    assert str(model.m.proto) == before and not context.ledger.attempts
    assert port.baseline == saved_baseline


def test_unknown_first_call_stops_without_frontage_or_wrong_infeasibility():
    context, model = build_scene(reference=True)
    port = r7.StageBFirstFeasibleRecoveryFairSolver()
    port.start_handoff(context.ledger, 1)
    port._final_guidance(model, context)
    _, status = port.native._run(context, model.m, 1e-9, "ALL_ROOMS_ALL_ACCESS")
    assert status == cp_model.UNKNOWN
    assert context.ledger.attempts[-1]["solver_status"] == "UNKNOWN"
    assert len(context.ledger.attempts) == 1 and not port.native.improving
    assert not model.m.proto.search_strategy and port.baseline is None


@pytest.mark.parametrize("old", [None, r5.POLICY_HASH, r6.POLICY_HASH])
def test_old_authorization_cannot_select_new_strategy(old):
    context, _ = build_scene(reference=True)
    context.ledger.execution_authorization.decision = {"balanced_quality_policy_hash": old}
    port = r7.StageBFirstFeasibleRecoveryFairSolver()
    port.start_handoff(context.ledger, 1)
    with pytest.raises(LayoutAuthorityError, match="BOUND_POLICY_REQUIRED"):
        port.solutions(context, None)
    assert not context.ledger.attempts


def test_six_full_handoff_models_preserve_original_hard_model_without_solving(monkeypatch):
    import gc

    from tests.unit.test_v222_stage_b_multi_solution import EnumerationLease

    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda *_: pytest.fail("20t Solve forbidden"))
    for ordinal in range(6):
        context, handoffs = complete_context()
        context.ledger.solver_history_verified = True
        context.ledger.execution_authorization = EnumerationLease()
        original = AccessModel(context, handoffs[ordinal], True)
        engine = r7._FirstFeasibleRecoveryNative(context.ledger, 6 - ordinal)
        reference = engine._new_final_model(context, handoffs[ordinal])
        assert str(original.m.proto) == str(reference.m.proto)
        r5.apply_area_efficient_guidance(original, context)
        engine.prepare_first_stage(reference, context)
        assert str(original.m.proto) == str(reference.m.proto)
        assert not reference.m.validate()
        del original, reference, context, engine
        gc.collect()


def test_no_default_wiring_and_original_validators_and_comparators_are_inherited():
    from pathlib import Path

    assert (
        r7._FirstFeasibleRecoveryNative.iter_solutions
        is OrToolsGlobalCompositionSolver.iter_solutions
    )
    assert (
        r7.StageBFirstFeasibleRecoveryFairSolver.observe_validated_candidate
        is r6.StageBFrontageJointSearchFairSolver.observe_validated_candidate
    )
    assert (
        r7.StageBFirstFeasibleRecoveryFairSolver._refresh_validated_hint
        is r6.StageBFrontageJointSearchFairSolver._refresh_validated_hint
    )
    assert r5.COMPARISON_POLICY == "same-handoff-nine-metrics-plus-three-area-allocations@1.0.0"
    root = Path(__file__).resolve().parents[2]
    for directory in (root / "src/cold_storage/bootstrap", root / "scripts"):
        assert all(
            "stage_b_first_feasible_recovery" not in p.read_text() for p in directory.rglob("*.py")
        )


def test_all_729_original_physical_assignments_remain_extendable():
    from itertools import product

    context, model, _ = reference_setup([((1, 3), (1, 3))] * 3)
    engine = r7._FirstFeasibleRecoveryNative(context.ledger, 1)
    engine.prepare_first_stage(model, context)
    model.m.clear_objective()
    found = []

    class Collect(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            found.append(
                tuple(self.value(model.m.get_int_var_from_proto_index(i)) for i in range(6))
            )

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = 3
    solver.parameters.enumerate_all_solutions = True
    assert solver.solve(model.m, Collect()) == cp_model.OPTIMAL
    assert len(found) == 729 and set(found) == set(product(range(1, 4), repeat=6))


@pytest.mark.parametrize("choice", [0, 1])
def test_delayed_frontage_keeps_both_original_portal_geometries(choice):
    context, model = build_scene(reference=True)
    engine = r7._FirstFeasibleRecoveryNative(context.ledger, 1)
    engine.prepare_first_stage(model, context)
    first, status = engine._run(context, model.m, 2, "ALL_ROOMS_ALL_ACCESS")
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    engine.begin_improvement(model, context, first)
    model.m.clear_hints()
    model.m.add_hint(model.choice, choice)
    projection = cp_model.CpSolver()
    projection.parameters.num_search_workers = 1
    projection.parameters.max_time_in_seconds = 2
    # Test-only projection query, never used by R7 or the production benchmark.
    projection.parameters.fix_variables_to_their_hinted_value = True
    assert projection.solve(model.m) == cp_model.OPTIMAL
    assert projection.value(model.choice) == choice
    assert validate_scene(model, projection)["valid"]


def test_existing_exact_hole_cut_rejects_ring_and_retains_open_geometry(monkeypatch):
    from cold_storage.modules.layout.infrastructure import global_cp_sat_solver as native
    from cold_storage.modules.layout.infrastructure.stage_b_fair_search import union_input_variables
    from tests.unit.test_v222_stage_b_multi_solution import TinyModel, native_setup, rooms

    context, lease = native_setup(monkeypatch)

    class Ring(TinyModel):
        @staticmethod
        def layouts():
            ring = rooms()
            positions = [
                (0, 0),
                (1, 0),
                (2, 0),
                (2, 1),
                (2, 2),
                (1, 2),
                (0, 2),
                (0, 1),
                (0, -1),
                (1, -1),
                (2, -1),
                (3, -1),
            ]
            for room, (x, y) in zip(ring, positions, strict=True):
                room.update(x=x, y=y)
            opened = deepcopy(ring)
            opened[5].update(x=3, y=0)
            return [ring, opened]

        def __init__(self, *args):
            super().__init__(*args)
            self.interfaces[0]["corridor"] = False

    monkeypatch.setattr(native, "GlobalModel", Ring)
    monkeypatch.setattr(native, "AccessModel", Ring)
    engine = r7._FirstFeasibleRecoveryNative(context.ledger, 1)
    # Isolate the inherited exact-cut path; factory itself is a synthetic model.
    monkeypatch.setattr(engine, "_new_final_model", lambda c, h: Ring(c, h, True))
    stream = engine.iter_solutions(
        context, None, event_sink=lease.events.append, topology_variables=union_input_variables
    )
    first = next(stream)
    assert first["model_witness_topology"]["valid"]
    assert context.ledger.checked_solutions == 2
    cut = next(e for e in lease.events if e["kind"] == "TOPOLOGY_REJECTED_WITNESS_CUT")
    assert cut["certificate"]["hole_count"] == 1
    assert first["topology_refinement_cuts"][0]["scope"] == "EXACT_EXPORTED_UNION_INPUT_EQUIVALENCE"
    stream.close()
