"""Tiny native models and exact facts only; no factory solve or Owner registry."""

from copy import deepcopy
from fractions import Fraction
from itertools import product
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure import global_cp_sat_solver as native
from cold_storage.modules.layout.infrastructure import stage_b_balanced_quality as balanced
from cold_storage.modules.layout.infrastructure import stage_b_feasibility_first as old
from cold_storage.modules.layout.infrastructure.stage_b_fair_search import FairNativeSolver
from tests.unit.test_v222_stage_b_multi_solution import (
    EnumerationLease,
    TinyModel,
    feasibility_context,
    rooms,
    synthetic_quality_candidate,
)


def context_and_model(ranges=None):
    lease = EnumerationLease()
    ledger = StageALedger(solver_history_verified=True, execution_authorization=lease)
    context = SimpleNamespace(
        ledger=ledger,
        binding=SimpleNamespace(
            p1_handoff_hash="synthetic-p1",
            canonical_zone_plan_hash="synthetic-plan",
            site_geometry_hash="synthetic-site",
            dimension_authorities={
                r: {"dimension_mode": "FLEXIBLE_RECTANGLE"} for r in old.FUNCTIONAL_SHAPE_ROLES
            },
        ),
    )
    m = cp_model.CpModel()
    rooms = {}
    for i, role in enumerate(old.FUNCTIONAL_SHAPE_ROLES):
        w, d = ranges[i] if ranges else ((1, 4), (1, 4))
        rooms[role] = {
            "w": m.new_int_var(*w, role + "_physical_w"),
            "d": m.new_int_var(*d, role + "_physical_d"),
        }
    return context, SimpleNamespace(m=m, c=context, rooms=rooms), lease


def variable(model, name):
    return next(
        model.get_int_var_from_proto_index(i)
        for i, v in enumerate(model.proto.variables)
        if v.name == name
    )


def solve(model):
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 3
    solver.parameters.max_time_in_seconds = 3
    assert not model.validate()
    assert solver.solve(model) == cp_model.OPTIMAL
    return solver


def snapshot(**updates):
    metrics = {
        "office_aspect": "4",
        "changing_room_aspect": "3",
        "coating_room_aspect": "2",
        "worst_room_aspect": "4",
        "personnel_route_m": "10",
        "personnel_route_turns": 2,
        "footprint_perimeter_m": "100",
        "footprint_outline_turn_count": 8,
        "footprint_reflex_corner_count": 2,
        "footprint_area_m2": "500",
    }
    metrics.update(updates)
    return {
        "candidate_hash": canonical_hash(metrics),
        "composition_hash": "synthetic-handoff",
        "functional_diversity": {"countable": True, "meaningful_construction_hash": "synthetic-v2"},
        "authority_hashes": {
            k: "SYNTHETIC:" + k
            for k in (
                "source_zone_plan_hash",
                "source_p1_handoff_hash",
                "source_site_geometry_hash",
            )
        },
        "metrics": metrics,
    }


def diagnostic_candidate(office=(1, 8), route_length=3):
    candidate = synthetic_quality_candidate(office, route_length)
    candidate.update(snapshot()["authority_hashes"])
    candidate["source_composition_hash"] = "synthetic-handoff"
    candidate["canonical_result_hash"] = canonical_hash(
        {k: v for k, v in candidate.items() if k != "canonical_result_hash"}
    )
    return candidate


def test_minimax_prioritizes_worst_room_not_semiperimeter_sum():
    context, wrapper, _ = context_and_model([((1, 8), (1, 8))] * 3)
    m = wrapper.m
    variables = [m.get_int_var_from_proto_index(i) for i in range(6)]
    # Both alternatives are legal synthetic input assignments. A is cheaper in
    # total spans (29 < 38), but B fixes the worst aspect (8 -> 2).
    a, b = (1, 8, 5, 5, 5, 5), (2, 4, 8, 8, 8, 8)
    m.add_allowed_assignments(variables, [a, b])
    legacy = m.clone()
    legacy.minimize(sum(legacy.get_int_var_from_proto_index(i) for i in range(6)))
    original = solve(legacy)
    assert tuple(original.value(legacy.get_int_var_from_proto_index(i)) for i in range(6)) == a
    receipt = balanced.apply_balanced_shape_guidance(wrapper, context)
    chosen = solve(m)
    assert tuple(chosen.value(v) for v in variables) == b
    assert chosen.value(variable(m, "balanced_shape_worst")) == 2000
    assert receipt["strategy"] == "BALANCED_FUNCTIONAL_SHAPE"
    assert not receipt["changes_engineering_feasible_domain"]
    assert context.ledger.model_work > 0  # Definitions are not free work.


def test_every_original_physical_assignment_has_unique_extension_without_objective():
    context, wrapper, _ = context_and_model([((1, 3), (1, 3))] * 3)
    balanced.apply_balanced_shape_guidance(wrapper, context)
    wrapper.m.clear_objective()
    assignments = []

    class Collect(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            assignments.append(
                tuple(self.value(wrapper.m.get_int_var_from_proto_index(i)) for i in range(6))
            )

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.enumerate_all_solutions = True
    assert solver.solve(wrapper.m, Collect()) == cp_model.OPTIMAL
    assert set(assignments) == set(product(range(1, 4), repeat=6))
    assert len(assignments) == 3**6  # No ambiguous or extra auxiliary assignments.


@pytest.mark.parametrize(
    "width,depth",
    [(1, 1), (1, 100000), (100000, 1), (1000000, 999999), (7, 3), (3, 7)],
)
def test_proxy_bounds_positive_rotation_and_ceil_error(width, depth):
    context, wrapper, _ = context_and_model([((width, width), (depth, depth))] * 3)
    balanced.apply_balanced_shape_guidance(wrapper, context)
    solver = solve(wrapper.m)
    value = solver.value(variable(wrapper.m, "balanced_shape_worst"))
    exact = Fraction(max(width, depth), min(width, depth))
    assert value == (1000 * max(width, depth) + min(width, depth) - 1) // min(width, depth)
    assert 0 <= Fraction(value, 1000) - exact < Fraction(1, 1000)


@pytest.mark.parametrize("fault", ["zero", "negative", "overflow", "missing", "duplicate"])
def test_unsupported_arithmetic_rejected_without_clamping_or_partial_definitions(fault):
    ranges = [((1, 4), (1, 4))] * 3
    if fault in ("zero", "negative", "overflow"):
        ranges[0] = (
            (
                0 if fault == "zero" else -1 if fault == "negative" else 1,
                1 << 62 if fault == "overflow" else 4,
            ),
            (1, 4),
        )
    context, wrapper, _ = context_and_model(ranges)
    if fault == "missing":
        wrapper.m.proto.variables[0].name = "missing-role"
    elif fault == "duplicate":
        wrapper.m.new_int_var(1, 4, "office_physical_w")
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError):
        balanced.apply_balanced_shape_guidance(wrapper, context)
    assert str(wrapper.m.proto) == before


def test_context_authority_and_existing_objective_are_not_silently_overwritten():
    context, wrapper, _ = context_and_model()
    with pytest.raises(LayoutAuthorityError, match="CONTEXT_MISMATCH"):
        balanced.apply_balanced_shape_guidance(wrapper, SimpleNamespace())
    context.binding.dimension_authorities["office"]["dimension_mode"] = "FIXED_RECTANGLE"
    with pytest.raises(LayoutAuthorityError, match="FLEXIBLE_AUTHORITY_REQUIRED"):
        balanced.apply_balanced_shape_guidance(wrapper, context)
    context.binding.dimension_authorities["office"]["dimension_mode"] = "FLEXIBLE_RECTANGLE"
    wrapper.m.minimize(variable(wrapper.m, "office_physical_w"))
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError, match="OBJECTIVE_ALREADY_PRESENT"):
        balanced.apply_balanced_shape_guidance(wrapper, context)
    assert str(wrapper.m.proto) == before


def test_proxy_ties_do_not_become_exact_aspect_ties():
    proxies = []
    for width in (10001, 10002):
        context, wrapper, _ = context_and_model([((width, width), (10000, 10000))] * 3)
        balanced.apply_balanced_shape_guidance(wrapper, context)
        proxies.append(solve(wrapper.m).value(variable(wrapper.m, "balanced_shape_worst")))
    assert proxies == [1001, 1001]
    before = snapshot(
        office_aspect="10002/10000",
        changing_room_aspect="1",
        coating_room_aspect="1",
        worst_room_aspect="10002/10000",
    )
    after = snapshot(
        office_aspect="10001/10000",
        changing_room_aspect="1",
        coating_room_aspect="1",
        worst_room_aspect="10001/10000",
    )
    assert balanced.compare_balanced_quality(before, after)["status"] == (
        "GEOMETRIC_PARETO_IMPROVEMENT"
    )


@pytest.mark.parametrize(
    "metric,value",
    [
        ("personnel_route_m", "11"),
        ("personnel_route_turns", 3),
        ("footprint_perimeter_m", "101"),
        ("footprint_outline_turn_count", 10),
        ("footprint_reflex_corner_count", 3),
        ("changing_room_aspect", "7"),
    ],
)
def test_shape_gain_cannot_hide_route_building_or_other_room_worsening(metric, value):
    before = snapshot()
    after = snapshot(office_aspect="2", worst_room_aspect="3", **{metric: value})
    if metric == "changing_room_aspect":
        after["metrics"]["worst_room_aspect"] = "7"
    result = balanced.compare_balanced_quality(before, after)
    assert result["status"] == "QUALITY_TRADEOFF"
    assert result["metric_directions_minus_one_better"][metric] == 1
    assert not result["automatic_production_selection"]


@pytest.mark.parametrize("metric", balanced.COMPARISON_METRICS)
@pytest.mark.parametrize("value", [None, "UNAVAILABLE"])
def test_missing_metrics_never_become_zero_or_improvement(metric, value):
    before, after = snapshot(), snapshot(office_aspect="2", worst_room_aspect="3")
    after["metrics"][metric] = value
    result = balanced.compare_balanced_quality(before, after)
    assert result["status"] == "INCOMPLETE_EVIDENCE"
    assert metric in result["missing_or_invalid_metrics"]
    assert after["metrics"][metric] == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("personnel_route_turns", "1/2"),
        ("footprint_perimeter_m", "0"),
        ("office_aspect", "0.5"),
        ("office_aspect", 1.23),
        ("worst_room_aspect", "2"),
        ("personnel_route_m", True),
    ],
)
def test_invalid_exact_metrics_and_inconsistent_worst_are_incomplete(field, value):
    assert balanced.compare_balanced_quality(snapshot(), snapshot(**{field: value}))["status"] == (
        "INCOMPLETE_EVIDENCE"
    )


@pytest.mark.parametrize("difference", ["handoff", "organization", "authority"])
def test_different_structure_or_authority_not_a_paired_improvement(difference):
    after = snapshot(office_aspect="2", worst_room_aspect="3")
    if difference == "handoff":
        after["composition_hash"] = "other-handoff"
    elif difference == "organization":
        after["functional_diversity"]["meaningful_construction_hash"] = "other-v2"
    else:
        after["authority_hashes"]["source_p1_handoff_hash"] = "other-p1"
    assert balanced.compare_balanced_quality(snapshot(), after)["status"] == (
        "NOT_COMPARABLE_STRUCTURE"
    )


def test_area_is_fact_only_no_gain_or_loss_without_engineering_calibration():
    for area in ("1", "1000000", None):
        result = balanced.compare_balanced_quality(snapshot(), snapshot(footprint_area_m2=area))
        assert result["status"] == "NO_MEASURABLE_IMPROVEMENT"
        assert "footprint_area_m2" not in result["metric_directions_minus_one_better"]
        assert result["footprint_area_facts_only"]["candidate_m2"] == area


def test_real_diagnostic_route_and_footprint_not_straight_line_or_bbox_substitutes():
    candidate = diagnostic_candidate()
    row = next(
        r
        for r in candidate["engineering_validation"]["access_results"]
        if r["from_ref"] == "main_entrance"
    )
    row.update(centerline=[dict(x=0, y=0), dict(x=0, y=2), dict(x=3, y=2)], route_length_m=5)
    candidate["engineering_validation"]["building_footprint"]["footprint"]["points"] = [
        dict(x=x, y=y) for x, y in ((0, 0), (6, 0), (6, 6), (4, 6), (4, 2), (2, 2), (2, 6), (0, 6))
    ]
    facts = balanced.balanced_quality_snapshot(candidate, "synthetic-handoff")
    assert facts["metrics"]["personnel_route_m"] == "5"
    assert facts["metrics"]["personnel_route_turns"] == 1
    assert facts["metrics"]["footprint_outline_turn_count"] == 8
    assert facts["metrics"]["footprint_reflex_corner_count"] == 2
    assert facts["metrics"]["footprint_area_m2"] == "28"
    assert facts["metrics"]["footprint_perimeter_m"] == "32"  # Bbox perimeter would be 24.
    assert facts["construction_facts"]["footprint"]["bounding_rectangle_area_m2"] == "36"
    row["status"] = "UNKNOWN"
    assert (
        balanced.balanced_quality_snapshot(candidate, "synthetic-handoff")["metrics"][
            "personnel_route_m"
        ]
        is None
    )
    candidate["engineering_validation"].pop("building_footprint")
    unknown = balanced.balanced_quality_snapshot(candidate, "synthetic-handoff")
    assert unknown["metrics"]["footprint_reflex_corner_count"] is None


def test_baseline_and_original_hash_preserved_after_real_diagnostic_tradeoff():
    context, _, lease = context_and_model()
    port = balanced.StageBBalancedQualityFairSearchSolver()
    port.start_handoff(context.ledger, 6)
    h = SimpleNamespace(source_composition_hash="synthetic-handoff")
    before = diagnostic_candidate()
    original = deepcopy(before)
    port.observe_validated_candidate(context, h, before, "ENGINEERING_ACCEPTED")
    baseline = deepcopy(port.baseline)
    worse_route = diagnostic_candidate((2, 4), route_length=5)
    port.observe_validated_candidate(context, h, worse_route, "EXAMINED_WITNESS")
    assert len(lease.events) == 1
    port.observe_validated_candidate(context, h, worse_route, "ENGINEERING_ACCEPTED")
    assert lease.events[-1]["status"] == "QUALITY_TRADEOFF"
    assert port.baseline == baseline and before == original
    assert port.baseline["candidate_hash"] == before["canonical_result_hash"]
    port.start_handoff(context.ledger, 5)
    assert port.baseline is None and not port.native.improving


@pytest.mark.parametrize("exhaustion", ["native", "elapsed", "work", "checked", "global"])
def test_resource_exhaustion_does_not_switch_or_refill(exhaustion):
    context, model, _ = context_and_model()
    engine = balanced._BalancedNative(context.ledger, 6)
    if exhaustion == "native":
        context.ledger.solver_monotonic_wall = engine.native_share
    elif exhaustion == "elapsed":
        engine.elapsed_share = 0
    elif exhaustion == "work":
        context.ledger.model_work = int(engine.work_share) + 1
    elif exhaustion == "checked":
        context.ledger.checked_solutions = engine.checked_share
    else:
        context.ledger.model_work = 1_200_001
    before = str(model.m.proto)
    with pytest.raises(LayoutAuthorityError):
        engine.begin_improvement(model, context, None)
    assert str(model.m.proto) == before and not engine.improving
    assert not context.ledger.attempts


def test_native_transition_uses_same_ledger_partial_hints_and_unknown_retains_baseline():
    context, wrapper, _ = context_and_model()
    engine = balanced._BalancedNative(context.ledger, 1)
    shares = (engine.native_share, engine.work_share, engine.checked_share)
    first, _ = engine._run(context, wrapper.m, 1, "ALL_ROOMS_ALL_ACCESS")
    assert "search_feedback" not in context.ledger.attempts[-1]
    incumbent = tuple(first.value(wrapper.m.get_int_var_from_proto_index(i)) for i in range(6))
    receipt = engine.begin_improvement(wrapper, context, first)
    assert receipt["policy_hash"] == balanced.POLICY_HASH
    assert receipt["preference_policy_hash"] == balanced.SHAPE_POLICY_HASH
    assert len(wrapper.m.proto.solution_hint.vars) == 6  # No old/historical coordinates.
    assert shares == (engine.native_share, engine.work_share, engine.checked_share)
    assert engine.ledger is context.ledger
    _, status = engine._run(context, wrapper.m, 1e-9, "ALL_ROOMS_ALL_ACCESS")
    assert status == cp_model.UNKNOWN
    assert incumbent == tuple(
        first.value(wrapper.m.get_int_var_from_proto_index(i)) for i in range(6)
    )
    assert len(context.ledger.attempts) == 2 and context.ledger.solver_monotonic_wall > 0


def test_objective_switch_failure_cannot_mutate_saved_baseline_or_invent_native_result():
    context, wrapper, lease = context_and_model()
    port = balanced.StageBBalancedQualityFairSearchSolver()
    port.start_handoff(context.ledger, 1)
    h = SimpleNamespace(source_composition_hash="synthetic-handoff")
    port.observe_validated_candidate(context, h, diagnostic_candidate(), "ENGINEERING_ACCEPTED")
    baseline = deepcopy(port.baseline)
    first, _ = port.native._run(context, wrapper.m, 1, "ALL_ROOMS_ALL_ACCESS")
    context.binding.dimension_authorities = {}
    with pytest.raises(LayoutAuthorityError, match="FLEXIBLE_AUTHORITY_REQUIRED"):
        port.native.begin_improvement(wrapper, context, first)
    assert port.baseline == baseline and not port.native.improving
    assert len(context.ledger.attempts) == 1 and len(lease.events) == 1


@pytest.mark.parametrize(
    "decision",
    [
        {},
        {"feasibility_first_policy_hash": old.POLICY_HASH},
        {"balanced_quality_policy_hash": "forged"},
    ],
)
def test_old_or_unbound_grant_cannot_authorize_new_strategy(decision):
    context, _, lease = context_and_model()
    lease.decision = decision
    port = balanced.StageBBalancedQualityFairSearchSolver()
    port.start_handoff(context.ledger, 6)
    with pytest.raises(LayoutAuthorityError, match="BALANCED_BOUND_POLICY_REQUIRED"):
        port.solutions(context, None)
    assert not context.ledger.attempts


def test_old_policy_hash_default_native_and_comparator_determinism_unchanged():
    assert (
        old.POLICY_HASH == "sha256:2a2db1361e71b6872eea1a536a890ababcaf835070dcd67833c598a651bcc092"
    )
    assert balanced.POLICY_HASH != old.POLICY_HASH
    context, _, _ = context_and_model()
    original = old._FeasibilityFirstNative(context.ledger, 1)
    assert original.continuation_policy_hash == old.POLICY_HASH
    assert (
        original._apply_improvement_guidance.__func__
        is old._FeasibilityFirstNative._apply_improvement_guidance
    )
    inputs = (snapshot(), snapshot(office_aspect="2", worst_room_aspect="3"))
    saved = deepcopy(inputs)
    assert balanced.compare_balanced_quality(*inputs) == balanced.compare_balanced_quality(*inputs)
    assert inputs == saved


@pytest.mark.parametrize("field", ["metrics", "authority_hashes", "functional_diversity"])
@pytest.mark.parametrize("value", [None, "UNKNOWN", []])
def test_malformed_evidence_containers_fail_closed(field, value):
    after = snapshot()
    after[field] = value
    assert balanced.compare_balanced_quality(snapshot(), after)["status"] == "INCOMPLETE_EVIDENCE"


def test_snapshot_cannot_relabel_another_handoff_and_missing_identity_is_not_invented():
    candidate = diagnostic_candidate()
    with pytest.raises(LayoutAuthorityError, match="CANDIDATE_SOURCE_MISMATCH"):
        balanced.balanced_quality_snapshot(candidate, "other-handoff")
    del candidate["source_composition_hash"]
    result = balanced.balanced_quality_snapshot(candidate, "synthetic-handoff")
    assert result["composition_hash"] is None
    assert balanced.compare_balanced_quality(result, result)["status"] == "INCOMPLETE_EVIDENCE"


def test_balanced_stream_retains_wall_first_stage_model_and_original_handoff_quantum(monkeypatch):
    # Existing synthetic protocol harness: real native tiny variables, not a
    # factory engineering PASS or mocked quality comparison.
    context, lease = feasibility_context(monkeypatch)
    lease.decision = {"balanced_quality_policy_hash": balanced.POLICY_HASH}

    class NamedTinyModel(TinyModel):
        def __init__(self, *args):
            super().__init__(*args)
            self.c = args[0]
            for role, row in self.rooms.items():
                for side in ("w", "d"):
                    row[side].proto.name = role + "_physical_" + side

    monkeypatch.setattr(native, "GlobalModel", NamedTinyModel)
    monkeypatch.setattr(native, "AccessModel", NamedTinyModel)
    port = balanced.StageBBalancedQualityFairSearchSolver()
    port.start_handoff(context.ledger, 6)
    engine = port.native
    shares = (engine.native_share, engine.work_share, engine.checked_share)
    stream = port.solutions(context, SimpleNamespace(source_composition_hash="synthetic-handoff"))
    first = deepcopy(next(stream))
    assert first["construction_guidance"]["policy"].startswith("stage-b-wall-coordinate")
    final = TinyModel.created[-1]
    original_constraints = [str(c) for c in final.m.proto.constraints]
    second = stream.send("ENGINEERING_ACCEPTED")
    assert second["construction_guidance"]["policy_hash"] == balanced.POLICY_HASH
    assert second["construction_guidance"]["preference_policy_hash"] == balanced.SHAPE_POLICY_HASH
    assert second["search_stage"] == "BOUNDED_QUALITY_IMPROVEMENT"
    assert [
        str(c) for c in list(final.m.proto.constraints)[: len(original_constraints)]
    ] == original_constraints
    assert len(TinyModel.created) == 3 and port.native is engine
    assert shares == (engine.native_share, engine.work_share, engine.checked_share)
    assert engine.ledger is context.ledger and len(context.ledger.attempts) == 6
    assert first["search_stage"] == "FEASIBILITY_FIRST"
    assert len([e for e in lease.events if e["kind"] == "BOUNDED_IMPROVEMENT_STARTED"]) == 1
    stream.close()


@pytest.mark.parametrize(
    "requested,remaining,elapsed,global_remaining,expected",
    [
        (30, 30, 30, 30, 30),
        (3, 30, 30, 30, 3),
        (30, 3, 30, 30, 3),
        (30, 30, 1, 30, 1),
        (30, 30, 30, 0.2, 0.2),
    ],
)
def test_feedback_waits_for_witness_within_every_original_time_allowance(
    monkeypatch, requested, remaining, elapsed, global_remaining, expected
):
    context, wrapper, _ = context_and_model()
    engine = balanced._BalancedNative(context.ledger, 1)
    engine.improving = True
    engine._feedback_model = wrapper.m
    engine._feedback_proxy_index = 0
    engine._baseline_proxy = 10  # Synthetic scalar observer, not factory approval.
    monkeypatch.setattr(engine, "remaining_share", lambda _: (remaining, elapsed))
    monkeypatch.setattr(context.ledger, "remaining_solver_seconds", lambda: global_remaining)
    calls = []
    original = balanced._BalancedNative._solve_with_feedback

    def observe(self, ctx, solver, model, phase):
        calls.append(solver.parameters.max_time_in_seconds)
        return original(self, ctx, solver, model, phase)

    monkeypatch.setattr(balanced._BalancedNative, "_solve_with_feedback", observe)
    _, status = engine._run(context, wrapper.m, requested, "ALL_ROOMS_ALL_ACCESS")
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    assert calls == [expected]


@pytest.mark.parametrize(
    "improving,phase",
    [
        (False, "ALL_ROOMS_ALL_ACCESS"),
        (False, "GLOBAL_GEOMETRY"),
        (True, "ALL_ACCESS_FRESH_HINT_ONLY"),
    ],
)
def test_quanta_do_not_change_first_stage_or_warmup_call(monkeypatch, improving, phase):
    context, wrapper, _ = context_and_model()
    engine = balanced._BalancedNative(context.ledger, 6)
    engine.improving = improving
    monkeypatch.setattr(FairNativeSolver, "_run", lambda self, ctx, m, seconds, p: (m, seconds, p))
    assert engine._run(context, wrapper.m, 17, phase) == (wrapper.m, 17, phase)


@pytest.mark.parametrize("exhaustion", ["native", "elapsed", "work", "checked", "global"])
def test_improvement_quanta_cannot_refill_exhausted_resources(monkeypatch, exhaustion):
    context, wrapper, _ = context_and_model()
    engine = balanced._BalancedNative(context.ledger, 6)
    engine.improving = True
    if exhaustion == "native":
        context.ledger.solver_monotonic_wall = engine.native_share
    elif exhaustion == "elapsed":
        engine.elapsed_share = 0
    elif exhaustion == "work":
        context.ledger.model_work = int(engine.work_share) + 1
    elif exhaustion == "checked":
        context.ledger.checked_solutions = engine.checked_share
    else:
        context.ledger.model_work = 1_200_001
    calls = []
    monkeypatch.setattr(
        native.OrToolsGlobalCompositionSolver, "_run", lambda *args: calls.append(args)
    )
    with pytest.raises(LayoutAuthorityError):
        engine._run(context, wrapper.m, 30, "ALL_ROOMS_ALL_ACCESS")
    assert not calls and not context.ledger.attempts


@pytest.mark.parametrize("bounded", [False, True])
def test_real_synthetic_hole_cuts_survive_quanta_without_model_rebuild_or_repeat(
    monkeypatch, bounded, record_property
):
    # Real union validator and CP-SAT on a tiny finite domain; NOT a factory solve.
    context, lease = feasibility_context(monkeypatch)

    class HoleModel(TinyModel):
        @staticmethod
        def layouts():
            hole = rooms()
            positions = (
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
            )
            for row, (x, y) in zip(hole, positions, strict=True):
                row.update(x=x, y=y)
            opened = deepcopy(hole)
            opened[5].update(x=3, y=0)
            return [hole, opened]

    monkeypatch.setattr(native, "GlobalModel", HoleModel)
    monkeypatch.setattr(native, "AccessModel", HoleModel)

    class FixedTwoSecondNative(old._FeasibilityFirstNative):
        def _run(self, ctx, model, seconds, phase):
            if self.improving and phase == "ALL_ROOMS_ALL_ACCESS":
                remaining, elapsed = self.remaining_share(ctx)
                seconds = min(
                    2, min(seconds, remaining, elapsed, ctx.ledger.remaining_solver_seconds()) / 2
                )
            return super()._run(ctx, model, seconds, phase)

    engine = (balanced._BalancedNative if bounded else FixedTwoSecondNative)(context.ledger, 1)
    engine.improving = True  # Isolate second-stage scheduling, no grant or MAIN.
    calls = []
    parent = native.OrToolsGlobalCompositionSolver._run

    def measured(self, ctx, model, seconds, phase):
        calls.append((id(model), seconds, phase))
        return parent(self, ctx, model, seconds, phase)

    monkeypatch.setattr(native.OrToolsGlobalCompositionSolver, "_run", measured)

    def prefer_hole(model):
        model.m.minimize(variable(model.m, "organization"))
        if bounded:
            engine._feedback_model = model.m
            engine._feedback_proxy_index = variable(model.m, "organization").index
            engine._baseline_proxy = 2  # Both alternative witnesses qualify in this toy model.
        return {"synthetic_only": True}

    stream = engine.iter_solutions(
        context, None, event_sink=lease.events.append, final_model_guidance=prefer_hole
    )
    result = next(stream)
    stream.close()
    cuts = [e for e in lease.events if e["kind"] == "TOPOLOGY_REJECTED_WITNESS_CUT"]
    assert cuts and all(e["certificate"]["hole_count"] == 1 for e in cuts)
    # The two portal witnesses may share geometry; neither exact witness repeats.
    assert len({tuple(e["values"]) for e in cuts}) == len(cuts)
    assert result["model_witness_topology"]["valid"]
    final_calls = [c for c in calls if c[2] == "ALL_ROOMS_ALL_ACCESS"]
    assert len(final_calls) == len(cuts) + 1
    assert len({c[0] for c in final_calls}) == 1
    assert all(0 < c[1] <= engine.native_share for c in final_calls)
    assert len(TinyModel.created) == 3  # No repeated warmup/model preparation.
    assert len(context.ledger.attempts) == len(calls)
    assert context.ledger.solver_monotonic_wall < engine.native_share
    record_property("SYNTHETIC_ONLY_feedback_enabled", bounded)
    record_property("SYNTHETIC_ONLY_final_native_calls", len(final_calls))
    record_property("SYNTHETIC_ONLY_exact_hole_cuts", len(cuts))
    record_property("SYNTHETIC_ONLY_native_seconds", context.ledger.solver_monotonic_wall)
    record_property("SYNTHETIC_ONLY_branches", sum(a["branches"] for a in context.ledger.attempts))
    # This finite domain needs at most both invalid portal witnesses + one valid
    # solve. More restarts would reduce candidate efficiency, not prove progress.
    assert len(final_calls) <= 3


def test_quantum_repeated_calls_debit_existing_share_not_fresh_budget(monkeypatch):
    context, wrapper, _ = context_and_model()
    engine = balanced._BalancedNative(context.ledger, 1)
    engine.improving = True
    engine.native_share = 6
    caps = []

    def consume(self, ctx, model, seconds, phase):
        caps.append(seconds)
        ctx.ledger.solver_monotonic_wall += min(seconds, 2)
        return None, cp_model.FEASIBLE

    monkeypatch.setattr(native.OrToolsGlobalCompositionSolver, "_run", consume)
    for _ in range(3):
        engine._run(context, wrapper.m, 100, "ALL_ROOMS_ALL_ACCESS")
    with pytest.raises(LayoutAuthorityError, match="SHARE_EXHAUSTED"):
        engine._run(context, wrapper.m, 100, "ALL_ROOMS_ALL_ACCESS")
    assert caps == [6, 4, 2]
    assert context.ledger.solver_monotonic_wall == 6
    assert engine.native_share == 6 and engine.ledger is context.ledger


@pytest.mark.parametrize("status", [cp_model.UNKNOWN, cp_model.FEASIBLE, cp_model.OPTIMAL])
def test_quantum_status_is_not_reinterpreted_or_retried_and_baseline_is_preserved(
    monkeypatch, status
):
    context, lease = feasibility_context(monkeypatch)
    lease.decision = {"balanced_quality_policy_hash": balanced.POLICY_HASH}

    class NamedModel(TinyModel):
        def __init__(self, *args):
            super().__init__(*args)
            self.c = args[0]
            for role, row in self.rooms.items():
                for side in ("w", "d"):
                    row[side].proto.name = role + "_physical_" + side

    monkeypatch.setattr(native, "GlobalModel", NamedModel)
    monkeypatch.setattr(native, "AccessModel", NamedModel)
    parent = native.OrToolsGlobalCompositionSolver._run
    improvement_calls = []

    def controlled(self, ctx, model, seconds, phase):
        solver, actual = parent(self, ctx, model, seconds, phase)
        if self.improving and phase == "ALL_ROOMS_ALL_ACCESS":
            improvement_calls.append(seconds)
            return solver, status  # Explicit synthetic protocol outcome injection.
        return solver, actual

    monkeypatch.setattr(native.OrToolsGlobalCompositionSolver, "_run", controlled)
    port = balanced.StageBBalancedQualityFairSearchSolver()
    port.start_handoff(context.ledger, 1)
    handoff = SimpleNamespace(source_composition_hash="synthetic-handoff")
    stream = port.solutions(context, handoff)
    first = deepcopy(next(stream))
    port.observe_validated_candidate(
        context, handoff, diagnostic_candidate(), "ENGINEERING_ACCEPTED"
    )
    saved = deepcopy(port.baseline)
    result = stream.send("ENGINEERING_ACCEPTED")
    assert result["solver_status"] == cp_model.CpSolver().status_name(status)
    assert port.baseline == saved and first["search_stage"] == "FEASIBILITY_FIRST"
    assert len(improvement_calls) == 1
    if status == cp_model.UNKNOWN:
        assert not result["global_infeasibility_claimed"] and "zones" not in result
        with pytest.raises(StopIteration):
            next(stream)
        assert not any("CUT" in e["kind"] for e in lease.events)
    else:
        assert result["model_witness_topology"]["valid"]
    stream.close()


def test_quanta_policy_rejects_r1_binding_without_changing_shape_or_comparator():
    assert (
        balanced.POLICY_HASH
        != "sha256:7eade090fb1f173473dd050f8a5cbfba9ab66c0c3a8180bdf8a1becf6d8ac3ed"
    )
    assert (
        balanced.SHAPE_POLICY_HASH
        == "sha256:4f03968760711b1ab090fbcabc2d45ea367428065ec23a47d6986671b7c3ddb0"
    )
    context, _, lease = context_and_model()
    r1_hash = "sha256:7eade090fb1f173473dd050f8a5cbfba9ab66c0c3a8180bdf8a1becf6d8ac3ed"
    lease.decision = {"balanced_quality_policy_hash": r1_hash}
    port = balanced.StageBBalancedQualityFairSearchSolver()
    port.start_handoff(context.ledger, 1)
    with pytest.raises(LayoutAuthorityError, match="BALANCED_BOUND_POLICY_REQUIRED"):
        port.solutions(context, None)
    assert (
        balanced.compare_balanced_quality(snapshot(), snapshot())["status"]
        == "NO_MEASURABLE_IMPROVEMENT"
    )
    assert not context.ledger.attempts


def test_real_callback_skips_baseline_then_returns_first_gain_before_timeout(record_property):
    # Tiny actual CP-SAT: ascending improvement sequence forced by fixed search.
    model = cp_model.CpModel()
    proxy = model.new_int_var(0, 10, "synthetic_proxy")
    model.minimize(proxy)
    model.add_decision_strategy([proxy], cp_model.CHOOSE_FIRST, cp_model.SELECT_MAX_VALUE)
    charges = []
    callback = balanced._FirstImprovingWitness(proxy, 10, lambda *x: charges.append(x))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.cp_model_presolve = False
    solver.parameters.search_branching = cp_model.FIXED_SEARCH
    solver.parameters.max_time_in_seconds = 2
    status = solver.solve(model, callback)
    assert status == cp_model.FEASIBLE  # Stop did not prove optimum (which is 0).
    assert solver.value(proxy) == 9
    receipt = callback.receipt()
    assert receipt["solution_count"] == 2  # Baseline 10 was not a stop condition.
    assert receipt["feedback_proxy"] == 9 and receipt["stop_requested"]
    assert 0 <= receipt["first_solution_seconds"] <= receipt["feedback_seconds"] < 2
    assert not receipt["engineering_validated"]
    assert len(charges) == 2
    record_property("ACTUAL_TINY_CP_feedback_seconds", receipt["feedback_seconds"])
    record_property("ACTUAL_TINY_CP_status", solver.status_name(status))


@pytest.mark.parametrize("baseline", [0, 10, 11])
def test_callback_without_strict_gain_does_not_force_stop_or_claim_engineering(baseline):
    model = cp_model.CpModel()
    proxy = model.new_int_var(10, 10, "constant_proxy")
    model.minimize(proxy)
    callback = balanced._FirstImprovingWitness(proxy, baseline, lambda *_: None)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    assert solver.solve(model, callback) == cp_model.OPTIMAL
    receipt = callback.receipt()
    assert receipt["stop_requested"] == (baseline > 10)
    assert (receipt["feedback_proxy"] is not None) == (baseline > 10)
    assert not receipt["engineering_validated"]


def test_no_solution_feedback_keeps_unknown_and_charges_actual_single_call():
    context, wrapper, _ = context_and_model()
    engine = balanced._BalancedNative(context.ledger, 1)
    first, _ = engine._run(context, wrapper.m, 1, "ALL_ROOMS_ALL_ACCESS")
    engine.begin_improvement(wrapper, context, first)
    _, status = engine._run(context, wrapper.m, 1e-9, "ALL_ROOMS_ALL_ACCESS")
    assert status == cp_model.UNKNOWN
    receipt = context.ledger.attempts[-1]["search_feedback"]
    assert receipt["solution_count"] == 0
    assert receipt["first_solution_seconds"] is None and receipt["feedback_seconds"] is None
    assert not receipt["stop_requested"] and len(context.ledger.attempts) == 2


@pytest.mark.parametrize("phase", ["ALL_ROOMS_ALL_ACCESS", "ALL_ACCESS_FRESH_HINT_ONLY"])
def test_shared_hook_and_first_stage_delegate_original_signature_without_feedback(phase):
    context, wrapper, _ = context_and_model()
    calls = []
    solver = SimpleNamespace(solve=lambda *args: calls.append(args) or cp_model.FEASIBLE)
    engine = balanced._BalancedNative(context.ledger, 1)
    assert engine._solve_with_feedback(context, solver, wrapper.m, phase) == (
        cp_model.FEASIBLE,
        None,
    )
    assert calls == [(wrapper.m,)]


def test_callback_budget_exception_marks_native_history_unverified_not_success():
    context, wrapper, _ = context_and_model()
    engine = balanced._BalancedNative(context.ledger, 1)
    engine.improving = True
    engine._feedback_model = wrapper.m
    engine._feedback_proxy_index = 0
    engine._baseline_proxy = 10
    # A synthetic ledger boundary, NOT a real RSS overlimit test.
    context.ledger.model_work = 1_200_000
    engine.work_share = 1_200_001
    with pytest.raises(LayoutAuthorityError, match="STAGE_A_RESOURCE_LIMIT"):
        engine._run(context, wrapper.m, 1, "ALL_ROOMS_ALL_ACCESS")
    assert not context.ledger.solver_history_verified and not context.ledger.attempts
    with pytest.raises(LayoutAuthorityError, match="HISTORY_UNVERIFIED"):
        context.ledger.remaining_solver_seconds()


def test_delayed_witness_protocol_fixed_two_second_cutoff_vs_feedback(record_property):
    # Deterministic simulated Native kernel. 3 seconds is scenario data, NOT
    # a measured factory witness latency or a claim of performance improvement.
    context, wrapper, _ = context_and_model()

    class Callback(balanced._FirstImprovingWitness):
        @property
        def wall_time(self):
            return 3.0

        def value(self, _):
            return 9

        def stop_search(self):
            self.stopped = True

    class Kernel:
        def __init__(self, allowance):
            self.allowance = allowance
            self.calls = 0

        def solve(self, model, callback=None):
            self.calls += 1
            if self.allowance < 3:
                return cp_model.UNKNOWN
            if callback is not None:
                callback.on_solution_callback()
            return cp_model.FEASIBLE

    old_kernel, feedback_kernel = Kernel(2), Kernel(6)
    original_status, original_feedback = (
        native.OrToolsGlobalCompositionSolver()._solve_with_feedback(
            context, old_kernel, wrapper.m, "ALL_ROOMS_ALL_ACCESS"
        )
    )
    assert original_status == cp_model.UNKNOWN and original_feedback is None
    callback = Callback(variable(wrapper.m, "office_physical_w"), 10, context.ledger.charge)
    corrected_status = feedback_kernel.solve(wrapper.m, callback)
    assert corrected_status == cp_model.FEASIBLE and callback.stopped
    assert callback.receipt()["feedback_seconds"] == 3
    assert old_kernel.calls == feedback_kernel.calls == 1
    assert not callback.receipt()["engineering_validated"]
    record_property("SIMULATED_KERNEL_NOT_MEASURED_witness_time", 3)


@pytest.mark.parametrize(
    "old_hash",
    [
        "sha256:7eade090fb1f173473dd050f8a5cbfba9ab66c0c3a8180bdf8a1becf6d8ac3ed",
        "sha256:c1aed0b63d610538ce0c66f3e6bf88e9811d7f6d7f350b9d77c38e7aa2db6911",
    ],
)
def test_feedback_strategy_rejects_both_previous_policy_bindings(old_hash):
    context, _, lease = context_and_model()
    lease.decision = {"balanced_quality_policy_hash": old_hash}
    port = balanced.StageBBalancedQualityFairSearchSolver()
    port.start_handoff(context.ledger, 1)
    with pytest.raises(LayoutAuthorityError, match="BALANCED_BOUND_POLICY_REQUIRED"):
        port.solutions(context, None)
    assert not context.ledger.attempts


def test_feedback_cannot_rebind_another_model_or_learn_invalid_witness_threshold():
    context, wrapper, _ = context_and_model()
    engine = balanced._BalancedNative(context.ledger, 1)
    first, _ = engine._run(context, wrapper.m, 1, "ALL_ROOMS_ALL_ACCESS")
    engine.begin_improvement(wrapper, context, first)
    saved = engine._baseline_proxy
    with pytest.raises(LayoutAuthorityError, match="FEEDBACK_MODEL_MISMATCH"):
        engine._solve_with_feedback(
            context, cp_model.CpSolver(), wrapper.m.clone(), "ALL_ROOMS_ALL_ACCESS"
        )
    engine._run(context, wrapper.m, 1, "ALL_ROOMS_ALL_ACCESS")
    assert engine._baseline_proxy == saved  # Never tighten using an unvalidated incumbent.


def test_real_minimax_feedback_uses_same_model_and_accounts_callback_work_and_native_once():
    context, wrapper, _ = context_and_model([((1, 8), (1, 8))] * 3)
    m = wrapper.m
    original_vars = [m.get_int_var_from_proto_index(i) for i in range(6)]
    baseline = (1, 8, 5, 5, 5, 5)
    m.add_allowed_assignments(original_vars, [baseline, (2, 4, 8, 8, 8, 8), (4, 4, 8, 8, 8, 8)])
    m.minimize(original_vars[0])
    engine = balanced._BalancedNative(context.ledger, 1)
    first, _ = engine._run(context, m, 1, "ALL_ROOMS_ALL_ACCESS")
    assert tuple(first.value(v) for v in original_vars) == baseline
    share = (engine.native_share, engine.work_share, engine.checked_share)
    receipt = engine.begin_improvement(wrapper, context, first)
    assert receipt["baseline_proxy"] == 8000
    constraints = [str(c) for c in m.proto.constraints]
    second, status = engine._run(context, m, 1, "ALL_ROOMS_ALL_ACCESS")
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    feedback = context.ledger.attempts[-1]["search_feedback"]
    assert feedback["stop_requested"] and feedback["feedback_proxy"] < 8000
    assert feedback["feedback_proxy"] == second.value(variable(m, "balanced_shape_worst"))
    assert (
        context.ledger.resource_events["STAGE_B_BALANCED_FEEDBACK_OBSERVATION"]
        == feedback["solution_count"]
    )
    assert len(context.ledger.attempts) == 2
    assert context.ledger.solver_wall == sum(a["wall_time"] for a in context.ledger.attempts)
    assert engine.ledger is context.ledger and [str(c) for c in m.proto.constraints] == constraints
    assert share == (engine.native_share, engine.work_share, engine.checked_share)
    assert tuple(first.value(v) for v in original_vars) == baseline
