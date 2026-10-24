"""R6 bounded synthetic CP-SAT and source-owned construction tests; no MAIN."""

from copy import copy, deepcopy
from fractions import Fraction
from itertools import product
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_area_efficiency as r5
from cold_storage.modules.layout.infrastructure import stage_b_frontage_joint_search as r6
from cold_storage.modules.layout.infrastructure.stage_b_model_references import ReferenceCpModel
from tests.unit.test_v222_stage_b_area_efficiency import area_snapshot, setup
from tests.unit.test_v222_stage_b_balanced_quality import solve, variable
from tests.unit.test_v222_stage_b_pool_execution import admit, registry


def reference_setup(ranges=None, area="0.000001", auxiliary=0, positions=False, ledger=None):
    context, _, lease = setup(area=area)
    if ledger is not None:
        context.ledger = ledger
    model = ReferenceCpModel(context.ledger.charge)
    rooms = {}
    for i, role in enumerate(r5.FUNCTIONAL_SHAPE_ROLES):
        w, d = ranges[i] if ranges else ((1, 4), (1, 4))
        rooms[role] = dict(
            w=model.new_int_var(*w, role + "_physical_w"),
            d=model.new_int_var(*d, role + "_physical_d"),
        )
        if positions:
            rooms[role].update(x=model.new_constant(0), y=model.new_constant(0))
    for i in range(auxiliary):
        model.new_int_var(0, 10, f"unused_aux_{i}")
    wrapper = SimpleNamespace(m=model, c=context, rooms=rooms, interfaces=[], routes=[])
    model.seal(wrapper)
    return context, wrapper, lease


def test_reference_definitions_preserve_all_729_assignments_and_exact_extensions():
    context, wrapper, _ = reference_setup([((1, 3), (1, 3))] * 3)
    r6.apply_reference_area_guidance(wrapper, context)
    wrapper.m.clear_objective()
    found = []

    class Collect(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            found.append(
                tuple(self.value(wrapper.m.get_int_var_from_proto_index(i)) for i in range(6))
            )

    engine = cp_model.CpSolver()
    engine.parameters.num_search_workers = 1
    engine.parameters.max_time_in_seconds = 3
    engine.parameters.enumerate_all_solutions = True
    assert engine.solve(wrapper.m, Collect()) == cp_model.OPTIMAL
    assert len(found) == 729 and set(found) == set(product(range(1, 4), repeat=6))


@pytest.mark.parametrize("auxiliary", [0, 10, 1000])
def test_same_proxy_proto_and_real_work_reduction_with_creation_cost_included(auxiliary):
    old_context, old, _ = setup()
    for i in range(auxiliary):
        old.m.new_int_var(0, 10, f"unused_aux_{i}")
    context, new, _ = reference_setup(auxiliary=auxiliary)
    assert str(old.m.proto) == str(new.m.proto)
    r5.apply_area_efficient_guidance(old, old_context)
    receipt = r6.apply_reference_area_guidance(new, context)
    assert str(old.m.proto) == str(new.m.proto)
    assert old_context.ledger.model_work == 3 * (6 + auxiliary) + 30
    assert context.ledger.model_work == (6 + auxiliary) + 61
    assert context.ledger.resource_events["R6_CREATED_DOMAIN_FACT"] == 6 + auxiliary + 13
    assert context.ledger.resource_events["R6_PHYSICAL_FACTS_READ"] == 21
    assert "R5_MODEL_FACTS_READ" not in context.ledger.resource_events
    assert new.m.implicit_reads == 0 and receipt["full_proto_scan"] is False
    if auxiliary >= 10:
        assert context.ledger.model_work < old_context.ledger.model_work


def test_native_implicit_constants_and_interleaving_are_counted_once():
    ledger = StageALedger()
    m = ReferenceCpModel(ledger.charge)
    a = m.new_int_var(0, 3, "a")
    m.add_bool_or([True])  # C++ creates a constant without Python new_constant.
    b = m.new_bool_var("b")
    first = m.new_constant(7)
    second = m.new_constant(7)
    owner = SimpleNamespace(m=m)
    m.seal(owner)
    assert a.index == 0 and b.index > a.index and first.index == second.index
    assert m.recorded == len(m.proto.variables) == 4
    assert m.magnitude == 3 + 1 + 1 + 7
    assert m.implicit_reads == 2
    assert ledger.resource_events["R6_CREATED_DOMAIN_FACT"] == 4
    assert ledger.resource_events["R6_IMPLICIT_CONSTANT_READ"] == 6


@pytest.mark.parametrize(
    "fault",
    [
        "foreign",
        "renamed",
        "domain",
        "empty",
        "untracked",
        "copy",
        "clone",
        "repeat",
        "positive",
        "overflow",
        "context",
        "objective",
    ],
)
def test_reference_model_faults_fail_before_target_mutation(fault):
    context, wrapper, _ = reference_setup()
    if fault == "foreign":
        wrapper.rooms["office"]["w"] = cp_model.CpModel().new_int_var(1, 4, "office_physical_w")
    elif fault == "renamed":
        wrapper.rooms["office"]["w"].proto.name = "other"
    elif fault == "domain":
        wrapper.rooms["office"]["w"].proto.domain[1] = 5
    elif fault == "empty":
        wrapper.rooms["office"]["w"].proto.domain.clear()
    elif fault == "untracked":
        wrapper.m.proto.variables.add().name = "untracked"
    elif fault == "copy":
        with pytest.raises(LayoutAuthorityError, match="COPY_UNSUPPORTED"):
            copy(wrapper.m)
        return
    elif fault == "clone":
        wrapper.m = wrapper.m.clone()
    elif fault == "repeat":
        r6.apply_reference_area_guidance(wrapper, context)
    elif fault == "positive":
        context, wrapper, _ = reference_setup([((0, 4), (1, 4))] * 3)
    elif fault == "overflow":
        context, wrapper, _ = reference_setup([((1, 10**10), (1, 10**10))] * 3)
    elif fault == "context":
        wrapper.c = object()
    else:
        wrapper.m.minimize(wrapper.rooms["office"]["w"])
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError):
        r6.apply_reference_area_guidance(wrapper, context)
    assert str(wrapper.m.proto) == before


def test_auxiliary_bounds_are_in_global_overflow_protection_without_second_scan():
    context, _, _ = setup()
    m = ReferenceCpModel(context.ledger.charge)
    rooms = {
        r: {s: m.new_int_var(1, 4, r + "_physical_" + s) for s in ("w", "d")}
        for r in r5.FUNCTIONAL_SHAPE_ROLES
    }
    m.new_int_var(0, 3_000_000_000_000_000_000, "large_auxiliary")
    wrapper = SimpleNamespace(m=m, c=context, rooms=rooms)
    m.seal(wrapper)
    before = str(m.proto)
    with pytest.raises(LayoutAuthorityError, match="INT64_OVERFLOW"):
        r6.apply_reference_area_guidance(wrapper, context)
    assert str(m.proto) == before


def test_duplicate_reserved_names_and_non_interval_or_post_seal_creation_rejected():
    context, _, _ = setup()
    m = ReferenceCpModel(context.ledger.charge)
    rooms = {
        r: {s: m.new_int_var(1, 4, r + "_physical_" + s) for s in ("w", "d")}
        for r in r5.FUNCTIONAL_SHAPE_ROLES
    }
    m.new_int_var(1, 4, "office_physical_w")
    wrapper = SimpleNamespace(m=m, c=context, rooms=rooms)
    m.seal(wrapper)
    with pytest.raises(LayoutAuthorityError, match="REFERENCE_CHANGED"):
        r6.apply_reference_area_guidance(wrapper, context)
    with pytest.raises(LayoutAuthorityError, match="SEALED"):
        m.new_bool_var("after_seal")
    with pytest.raises(LayoutAuthorityError, match="NON_INTERVAL"):
        m.new_int_var_from_domain(cp_model.Domain.from_values([1, 3]), "domain")


@pytest.mark.parametrize("cap", [600000, 1200000])
def test_whole_definition_and_metadata_batch_admitted_before_any_target_changes(tmp_path, cap):
    if cap == 600000:
        store, binding = registry(tmp_path)
        ledger = store.open("MAIN")  # SYNTHETIC temporary registry only.
        lease = admit(ledger, binding)
    else:
        ledger, lease = StageALedger(), None
    context, wrapper, _ = reference_setup(ledger=ledger)
    ledger.model_work = cap - 21 - 39  # SYNTHETIC_RESOURCE_STATE_TEST.
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        r6.apply_reference_area_guidance(wrapper, context)
    assert str(wrapper.m.proto) == before
    assert ledger.model_work == cap - 39
    assert "R5_TOTAL_DEFINITIONS" not in ledger.resource_events
    if lease:
        lease.finish_pool()


@pytest.mark.parametrize("demand", [None, "0", "-1", True, 1.0])
def test_bad_p1_sources_do_not_mutate_model(demand):
    context, wrapper, _ = reference_setup()
    context.binding.dimension_authorities["office"]["required_area_m2"] = demand
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError):
        r6.apply_reference_area_guidance(wrapper, context)
    assert str(wrapper.m.proto) == before


def test_physical_hint_writes_real_small_set_and_omits_unused_auxiliaries():
    context, wrapper, _ = reference_setup(auxiliary=1000, positions=True)
    solver = solve(wrapper.m)
    before = [str(c) for c in wrapper.m.proto.constraints]
    work = context.ledger.model_work
    receipt = r6.install_physical_hint(wrapper, context, solver)
    assert receipt["hint_variable_count"] == 7  # Six sizes + one shared zero position.
    assert len(wrapper.m.proto.solution_hint.vars) == 7
    assert context.ledger.model_work - work == 12 + 7
    assert all(
        wrapper.m.get_int_var_from_proto_index(i).name != "unused_aux_0"
        for i in wrapper.m.proto.solution_hint.vars
    )
    assert before == [str(c) for c in wrapper.m.proto.constraints]


def test_hint_budget_failure_keeps_previous_hint_and_constraints():
    context, wrapper, _ = reference_setup(positions=True)
    solver = solve(wrapper.m)
    wrapper.m.add_hint(wrapper.rooms["office"]["w"], 1)
    before = str(wrapper.m.proto)
    context.ledger.model_work = 1_200_000 - 12 - 6
    with pytest.raises(LayoutAuthorityError):
        r6.install_physical_hint(wrapper, context, solver)
    assert str(wrapper.m.proto) == before


def frontier_snapshot(w, d, **metrics):
    area = Fraction(w) * Fraction(d)
    result = area_snapshot(str(area), **metrics)
    for room in result["area_efficiency"]["rooms"].values():
        room.update(physical_width_m=str(w), physical_depth_m=str(d))
    return result


def test_validated_tradeoff_advances_search_not_formal_pareto_and_equal_proxy_no_advance(
    monkeypatch,
):
    context, _, lease = setup(area="1")
    port = r6.StageBFrontageJointSearchFairSolver()
    port.start_handoff(context.ledger, 1)
    monkeypatch.setattr(r5, "area_efficiency_snapshot", lambda candidate, *_: candidate)
    handoff = SimpleNamespace(source_composition_hash="synthetic-handoff")
    first = frontier_snapshot("1", "4")
    port.observe_validated_candidate(context, handoff, first, "ENGINEERING_ACCEPTED")
    assert context.ledger.resource_events["R6_VALIDATED_PROXY_FACTS"] == 10
    improved = frontier_snapshot(
        "2", "2.1", office_aspect="1.05", changing_room_aspect="1.05", coating_room_aspect="1.05"
    )
    port.observe_validated_candidate(context, handoff, improved, "EXAMINED_WITNESS")
    assert port.search_frontier == 6250 and port.pending_frontier is None
    assert context.ledger.resource_events["R6_VALIDATED_PROXY_FACTS"] == 10
    port.observe_validated_candidate(context, handoff, improved, "ENGINEERING_ACCEPTED")
    assert port.search_frontier == 4203 and port.pending_frontier[0] == 4203
    assert lease.events[-1]["status"] == "QUALITY_TRADEOFF" and port.pending_guidance is None
    assert port.baseline == first
    port.pending_frontier = None
    port.observe_validated_candidate(context, handoff, deepcopy(improved), "ENGINEERING_ACCEPTED")
    assert port.pending_frontier is None and port.search_frontier == 4203
    assert r5.compare_area_efficient_quality(first, improved)["status"] == "QUALITY_TRADEOFF"


@pytest.mark.parametrize("old_hash", [None, r5.POLICY_HASH, "old-r4", "forged"])
def test_r5_or_missing_binding_cannot_activate_r6(old_hash):
    context, _, lease = setup()
    lease.decision = dict(balanced_quality_policy_hash=old_hash)
    port = r6.StageBFrontageJointSearchFairSolver()
    port.start_handoff(context.ledger, 6)
    with pytest.raises(LayoutAuthorityError, match="BOUND_POLICY_REQUIRED"):
        port.solutions(context, None)
    assert not context.ledger.attempts and not lease.events


def test_r6_reuses_same_model_and_ledger_and_unknown_is_not_infeasible():
    context, wrapper, _ = reference_setup(
        area="1", ranges=[((1000, 4000), (1000, 4000))] * 3, positions=True
    )
    engine = r6._FrontageNative(context.ledger, 1)
    engine.prepare_first_stage(wrapper, context)
    first, _ = engine._run(context, wrapper.m, 1, "ALL_ROOMS_ALL_ACCESS")
    original = [str(c) for c in wrapper.m.proto.constraints]
    shares = (engine.native_share, engine.work_share, engine.checked_share)
    engine.begin_improvement(wrapper, context, first)
    _, status = engine._run(context, wrapper.m, 1e-9, "ALL_ROOMS_ALL_ACCESS")
    assert status == cp_model.UNKNOWN
    assert [str(c) for c in wrapper.m.proto.constraints] == original
    assert len(context.ledger.attempts) == 2 and shares == (
        engine.native_share,
        engine.work_share,
        engine.checked_share,
    )
    assert engine.ledger is context.ledger and engine.last_hint_receipt["hint_variable_count"] == 7


def run_scene(use_r6):
    from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
    from cold_storage.modules.layout.infrastructure.global_cp_sat_model import envelopes
    from tests.r6_frontage_synthetic import BOXES, build_scene

    context, model = build_scene(reference=use_r6)
    if use_r6:
        r6.apply_frontage_joint_search(model, context)
        r6.apply_reference_area_guidance(model, context)
    else:
        r5.apply_area_efficient_guidance(model, context)
    model.m.add_decision_strategy([model.choice], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 3
    solver.parameters.max_time_in_seconds = 2
    solver.parameters.search_branching = cp_model.FIXED_SEARCH
    # Both sides use the SAME test-only settings to expose decision-order
    # semantics rather than presolve's arbitrary removal of an objective tie.
    solver.parameters.cp_model_presolve = False
    solver.parameters.stop_after_first_solution = True
    status = solver.solve(model.m)
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    path = [tuple(solver.value(v) for v in point) for point in model.routes[0]["points"]]
    boxes = list(BOXES.values()) + envelopes(path, 2000)
    topology = inspect_rectangular_union(boxes)
    assert (
        topology["valid"]
        and topology["hole_count"] == 0
        and topology["connected_component_count"] == 1
    )
    headings = [
        (int(b[0] > a[0]) - int(b[0] < a[0]), int(b[1] > a[1]) - int(b[1] < a[1]))
        for a, b in zip(path, path[1:], strict=False)
        if a != b
    ]
    result = dict(
        choice=solver.value(model.choice),
        route_length_mm=sum(
            abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(path, path[1:], strict=False)
        ),
        turns=sum(a != b for a, b in zip(headings, headings[1:], strict=False)),
        path_mm=path,
        topology=topology,
        proxy=solver.value(variable(model.m, "r5_area_worst")),
        work=context.ledger.model_work,
    )
    return result, context, model, solver


def test_nontrivial_synthetic_actual_portal_choice_route_and_topology_difference():
    old, _, _, _ = run_scene(False)
    new, _, _, _ = run_scene(True)
    assert (old["choice"], new["choice"]) == (0, 1)
    assert old["proxy"] == new["proxy"] == 1125
    assert (old["route_length_mm"], new["route_length_mm"]) == (12000, 9000)
    assert (old["turns"], new["turns"]) == (3, 2)


def test_frontage_prefix_is_reproducible_and_has_no_physical_cut_or_new_variables():
    from tests.r6_frontage_synthetic import build_scene

    receipts = []
    for _ in range(2):
        context, model = build_scene(reference=True)
        before = model.m.clone()
        receipt = r6.apply_frontage_joint_search(model, context)
        after = model.m.clone()
        after.proto.search_strategy.clear()
        assert str(before.proto) == str(after.proto)
        receipts.append(receipt)
    assert receipts[0] == receipts[1]
    assert receipts[0]["new_variables"] == receipts[0]["new_constraints"] == 0


@pytest.mark.parametrize("fault", ["authority", "entrance", "must", "literal", "budget"])
def test_frontage_failures_leave_strategies_and_original_constraints_untouched(fault):
    from tests.r6_frontage_synthetic import build_scene

    context, model = build_scene(reference=True)
    if fault == "authority":
        context.binding.access_requirements = ()
    elif fault == "entrance":
        context.entrances["main_entrance"] = ((8000, 4000), (8000, 6000))
    elif fault == "must":
        model.must_choices.pop(("office", "shipping_channel"))
    elif fault == "literal":
        model.routes[0]["to_faces"][1] = cp_model.CpModel().new_bool_var("foreign")
    else:
        context.ledger.model_work = 1_200_000 - 1
    before = str(model.m.proto)
    with pytest.raises(LayoutAuthorityError):
        r6.apply_frontage_joint_search(model, context)
    assert str(model.m.proto) == before


def test_physical_hint_on_synthetic_scene_selects_actual_ports_and_route_choices():
    _, context, model, solver = run_scene(True)
    receipt = r6.install_physical_hint(model, context, solver)
    indices = set(model.m.proto.solution_hint.vars)
    assert model.routes[0]["to_faces"][1].index in indices
    assert model.interfaces[0]["active"].index in indices
    assert all(v.index in indices for v in model.routes[0]["points"][-1])
    assert receipt["hint_variable_count"] < len(model.m.proto.variables) // 2


def test_synthetic_choice_and_actual_route_repeat_under_identical_configuration():
    for active in (False, True):
        first, *_ = run_scene(active)
        second, *_ = run_scene(active)
        for key in ("choice", "route_length_mm", "turns", "path_mm", "topology", "proxy", "work"):
            assert first[key] == second[key]


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("choice", [0, 1])
def test_both_original_physical_portal_assignments_remain_extendable(active, choice):
    from tests.r6_frontage_synthetic import build_scene

    context, model = build_scene(reference=active)
    if active:
        r6.apply_frontage_joint_search(model, context)
        r6.apply_reference_area_guidance(model, context)
    else:
        r5.apply_area_efficient_guidance(model, context)
    model.m.add_hint(model.choice, choice)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = 2
    solver.parameters.fix_variables_to_their_hinted_value = True  # Test-only projection query.
    assert solver.solve(model.m) == cp_model.OPTIMAL
    assert solver.value(model.choice) == choice


def test_tradeoff_frontier_reaches_native_callback_without_hint_promotion(monkeypatch):
    context, model, lease = reference_setup(
        ranges=[((1000, 4000), (1000, 4000))] * 3, area="1", positions=True
    )
    for room in model.rooms.values():
        model.m.add_allowed_assignments([room["w"], room["d"]], [(1000, 4000), (2000, 2100)])
    port = r6.StageBFrontageJointSearchFairSolver()
    port.start_handoff(context.ledger, 1)
    engine = port.native
    engine.prepare_first_stage(model, context)

    def witness(w, d):
        model.m.clear_hints()
        for room in model.rooms.values():
            model.m.add_hint(room["w"], w)
            model.m.add_hint(room["d"], d)
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.max_time_in_seconds = 2
        solver.parameters.fix_variables_to_their_hinted_value = True
        assert solver.solve(model.m) == cp_model.OPTIMAL
        return solver

    original = witness(1000, 4000)
    monkeypatch.setattr(r5, "area_efficiency_snapshot", lambda candidate, *_: candidate)
    handoff = SimpleNamespace(source_composition_hash="synthetic-handoff")
    baseline = frontier_snapshot("1", "4")
    port.observe_validated_candidate(context, handoff, baseline, "ENGINEERING_ACCEPTED")
    engine.begin_improvement(model, context, original)
    improved = witness(2000, 2100)
    tradeoff = frontier_snapshot(
        "2", "2.1", office_aspect="1.05", changing_room_aspect="1.05", coating_room_aspect="1.05"
    )
    port.observe_validated_candidate(context, handoff, tradeoff, "ENGINEERING_ACCEPTED")
    constraints = [str(c) for c in model.m.proto.constraints]
    assert port.pending_guidance is None
    assert port._refresh_validated_hint(model, context, improved) is None
    assert engine._baseline_proxy == 4203 and port.search_frontier == 4203
    assert lease.events[-1]["kind"] == "VALIDATED_SEARCH_FRONTIER_UPDATED"
    assert lease.events[-1]["formal_quality_improvement"] is False
    # Both allowed geometries now have proxy >= the VALIDATED frontier.
    # Equal proxy is no longer early-stopped as progress against stale 6250.
    _, status = engine._run(context, model.m, 1, "ALL_ROOMS_ALL_ACCESS")
    assert status == cp_model.OPTIMAL
    assert context.ledger.attempts[-1]["search_feedback"]["stop_requested"] is False
    assert [str(c) for c in model.m.proto.constraints] == constraints
    assert port.baseline == baseline


def test_no_remaining_share_preserves_initial_engineering_baseline(monkeypatch):
    context, model, _ = reference_setup(positions=True)
    port = r6.StageBFrontageJointSearchFairSolver()
    port.start_handoff(context.ledger, 1)
    monkeypatch.setattr(r5, "area_efficiency_snapshot", lambda candidate, *_: candidate)
    first = frontier_snapshot("1", "4")
    port.observe_validated_candidate(
        context,
        SimpleNamespace(source_composition_hash="synthetic-handoff"),
        first,
        "ENGINEERING_ACCEPTED",
    )
    port.native.prepare_first_stage(model, context)
    port.native.native_share = 0
    before = str(model.m.proto)
    with pytest.raises(LayoutAuthorityError):
        port.native.begin_improvement(model, context, None)
    assert port.baseline == first and str(model.m.proto) == before


def test_changed_ledger_cannot_reuse_creation_facts():
    context, wrapper, _ = reference_setup()
    context.ledger = StageALedger()
    with pytest.raises(LayoutAuthorityError, match="LEDGER_MISMATCH"):
        r6.apply_reference_area_guidance(wrapper, context)


def complete_context():
    """Build existing model inputs only. NEVER solve the 20t fixture."""
    from cold_storage.modules.layout.application.global_composition_solver import (
        GlobalGenerationContext,
        rectangular_scope,
    )
    from cold_storage.modules.layout.application.layout_authority_binding import (
        bind_layout_authority,
    )
    from cold_storage.modules.layout.application.structural_composition import (
        build_structural_compositions,
    )
    from cold_storage.modules.layout.domain.access_authority import resolve_access_profile
    from cold_storage.modules.layout.domain.access_routing import _segment_from_mapping
    from cold_storage.modules.layout.domain.adjacency import process_graph
    from cold_storage.modules.layout.domain.site_geometry import normalize_polygon
    from cold_storage.modules.layout.domain.validated_site_obstacles import (
        validated_hard_obstacle_polygons,
    )
    from tests.unit.test_v222_p1a_composition_authority_handoff import _context

    plan, p1, site = _context()
    binding = bind_layout_authority(plan, p1.to_dict(), site)
    body = site.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = validated_hard_obstacle_polygons(body)
    pack = next(r for r in binding.access_requirements if r["flow_kind"] == "PACKAGING")
    context = GlobalGenerationContext(
        binding,
        site,
        boundary,
        obstacles,
        rectangular_scope(boundary),
        tuple(rectangular_scope(p) for p in obstacles),
        {
            k: _segment_from_mapping(v, field=k)
            for k, v in body["entrances"].items()
            if k in ("main_entrance", "truck_entrance")
        },
        tuple(process_graph().must_adjacencies),
        pack,
        resolve_access_profile(pack["profile_identity"]),
        StageALedger(),
    )
    return context, build_structural_compositions(plan, p1.to_dict(), site).placement_handoffs


def test_six_handoff_reference_builds_exactly_match_domains_constraints_and_indices(monkeypatch):
    """Construction/validation only; forbid every native Solve explicitly."""
    import gc

    from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel

    monkeypatch.setattr(
        cp_model.CpSolver, "solve", lambda *_: pytest.fail("20t Native solve forbidden")
    )
    for ordinal in range(6):
        context, handoffs = complete_context()
        original = AccessModel(context, handoffs[ordinal], True)
        reference = r6._ReferenceAccessModel(context, handoffs[ordinal], True)
        assert str(original.m.proto) == str(reference.m.proto)
        r5.apply_area_efficient_guidance(original, context)
        r6.apply_reference_area_guidance(reference, context)
        assert str(original.m.proto) == str(reference.m.proto)
        assert not reference.m.validate()
        before = reference.m.clone()
        r6.apply_frontage_joint_search(reference, context)
        after = reference.m.clone()
        after.proto.search_strategy.clear()
        assert str(before.proto) == str(after.proto)
        assert not reference.m.validate()
        del original, reference, before, after
        gc.collect()


def test_r6_only_hook_and_default_factory_preserve_original_warmup_sequence():
    import inspect

    from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel
    from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
        OrToolsGlobalCompositionSolver,
    )

    context, handoffs = complete_context()
    default = OrToolsGlobalCompositionSolver()._new_final_model(context, handoffs[0])
    assert type(default) is AccessModel and type(default.m) is cp_model.CpModel
    source = inspect.getsource(OrToolsGlobalCompositionSolver.iter_solutions)
    assert source.count("global_model.m.clone()") == 1  # Three iterations of this call site.
    assert all(
        name in source
        for name in (
            "ALL_ROOM_GEOMETRY_HINT",
            "ALL_ROOM_MUST_HINT",
            "COMPOSITION_PACKAGING_HINT",
            "ALL_ACCESS_FRESH_HINT_ONLY",
        )
    )
    assert source.index("search_receipt = final_model_search(model)") < source.index(
        "model.m.add_decision_strategy("
    )


def test_r5_policy_and_original_comparison_versions_are_not_replaced():
    from pathlib import Path

    from cold_storage.modules.layout.infrastructure import stage_b_balanced_quality as original

    assert (
        r5.POLICY_HASH == "sha256:ddccb804958e52c169ad1d1c0c2c6ecc259271e350e23207dba0b1a5e71db0a4"
    )
    assert r6.POLICY_HASH != r5.POLICY_HASH
    assert r5.COMPARISON_POLICY == "same-handoff-nine-metrics-plus-three-area-allocations@1.0.0"
    assert original.COMPARISON_POLICY == "same-handoff-exact-nine-metric-pareto@1.0.0"
    backend = Path(__file__).resolve().parents[2]
    assert all(
        "stage_b_frontage_joint_search" not in p.read_text()
        for root in ("src/cold_storage/bootstrap", "scripts")
        for p in (backend / root).rglob("*.py")
    )
    assert Path(__file__).name in (backend / "tests/stage_a_resource_process.py").read_text()
    assert Path(__file__).name in (backend.parent / ".github/workflows/ci-fast.yml").read_text()
