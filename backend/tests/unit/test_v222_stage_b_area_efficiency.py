"""R5 tiny synthetic CP-SAT/fact tests; never a factory MAIN or real Grant."""

from copy import deepcopy
from fractions import Fraction
from itertools import product
from pathlib import Path
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import (
    REPORTED_AREA_SOURCE,
    LayoutAuthorityError,
    canonical_hash,
)
from cold_storage.modules.layout.infrastructure import global_cp_sat_solver as native
from cold_storage.modules.layout.infrastructure import stage_b_area_efficiency as r5
from cold_storage.modules.layout.infrastructure import stage_b_balanced_quality as r4
from tests.unit.test_v222_stage_b_balanced_quality import (
    context_and_model,
    diagnostic_candidate,
    snapshot,
    solve,
    variable,
)
from tests.unit.test_v222_stage_b_multi_solution import TinyModel, feasibility_context, rooms
from tests.unit.test_v222_stage_b_pool_execution import admit, registry


def requirements(context, area="0.000001"):
    for auth in context.binding.dimension_authorities.values():
        auth.update(
            status="FLEXIBLE_AUTHORIZED",
            p2_may_change_required_area=False,
            p2_may_select_width_depth=True,
            required_area_m2=area,
            area_requirement=dict(
                reported_required_area_m2=area,
                reported_area_source_identity=REPORTED_AREA_SOURCE,
            ),
        )


def setup(ranges=None, area="0.000001"):
    context, wrapper, lease = context_and_model(ranges)
    requirements(context, area)
    return context, wrapper, lease


def area_snapshot(allocation="2", **metrics):
    result = snapshot(**metrics)
    result["metrics"]["worst_room_aspect"] = str(
        max(Fraction(result["metrics"][r + "_aspect"]) for r in r5.FUNCTIONAL_SHAPE_ROLES)
    )
    result["area_efficiency"] = dict(
        source_p1_handoff_hash=result["authority_hashes"]["source_p1_handoff_hash"],
        area_source=REPORTED_AREA_SOURCE,
        rooms={
            r: dict(
                required_area_m2="1", actual_area_m2=allocation, area_allocation_ratio=allocation
            )
            for r in r5.FUNCTIONAL_SHAPE_ROLES
        },
    )
    return result


def test_all_729_physical_assignments_have_one_extension_without_objective():
    context, wrapper, _ = setup([((1, 3), (1, 3))] * 3)
    r5.apply_area_efficient_guidance(wrapper, context)
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
    assert len(assignments) == 729
    assert set(assignments) == set(product(range(1, 4), repeat=6))


def test_r5_prefers_demand_sized_compact_geometry_not_r4_oversized_square():
    context, wrapper, _ = setup([((1000, 10000), (1000, 10000))] * 3, area="8")
    # All choices satisfy 8 m² in this small model; no topology/project claim.
    for room in wrapper.rooms.values():
        wrapper.m.add_allowed_assignments(
            [room["w"], room["d"]], [(1000, 8000), (2000, 4000), (10000, 10000)]
        )
    old = wrapper.m.clone()
    old_wrapper = SimpleNamespace(m=old, c=context)
    r4.apply_balanced_shape_guidance(old_wrapper, context)
    legacy = solve(old)
    assert legacy.value(variable(old, "office_physical_w")) == 10000
    r5.apply_area_efficient_guidance(wrapper, context)
    chosen = solve(wrapper.m)
    assert [
        (chosen.value(room["w"]), chosen.value(room["d"])) for room in wrapper.rooms.values()
    ] == [(2000, 4000)] * 3
    assert chosen.value(variable(wrapper.m, "r5_area_worst")) == 1125


@pytest.mark.parametrize("side", [1000, 2000, 8000])
def test_uniform_square_expansion_cannot_reduce_area_proxy(side):
    context, wrapper, _ = setup([((side, side), (side, side))] * 3, area="1")
    receipt = r5.apply_area_efficient_guidance(wrapper, context)
    solver = solve(wrapper.m)
    assert solver.value(variable(wrapper.m, "r5_area_worst")) == side * side // 1000
    assert receipt["area_upper_bound_added"] is False
    assert receipt["real_layout_quality_improved"] is False


@pytest.mark.parametrize("demand", ["0.000001", "0.0000011", "0.0000009"])
def test_exact_proxy_reuses_existing_mm2_demand_rounding(demand):
    context, wrapper, _ = setup([((3, 3), (5, 5))] * 3, demand)
    r5.apply_area_efficient_guidance(wrapper, context)
    solver = solve(wrapper.m)
    area = Fraction(demand) * 1_000_000
    ceil_area = -(-area.numerator // area.denominator)
    assert solver.value(variable(wrapper.m, "r5_area_worst")) == (
        1000 * 64 + 4 * ceil_area - 1
    ) // (4 * ceil_area)


@pytest.mark.parametrize("bad", [None, True, 1.0, "0", "-1", "NaN", "invalid"])
def test_invalid_or_missing_p1_area_rejected_before_model_changes(bad):
    context, wrapper, _ = setup()
    context.binding.dimension_authorities["office"]["required_area_m2"] = bad
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError):
        r5.apply_area_efficient_guidance(wrapper, context)
    assert str(wrapper.m.proto) == before


@pytest.mark.parametrize("fault", ["fixed", "change_area", "wrong_source", "mismatch"])
def test_no_caller_area_authority_override(fault):
    context, wrapper, _ = setup()
    auth = context.binding.dimension_authorities["office"]
    if fault == "fixed":
        auth["dimension_mode"] = "FIXED"
    elif fault == "change_area":
        auth["p2_may_change_required_area"] = True
    elif fault == "wrong_source":
        auth["area_requirement"]["reported_area_source_identity"] = "caller"
    else:
        auth["area_requirement"]["reported_required_area_m2"] = "20"
    with pytest.raises(LayoutAuthorityError):
        r5.apply_area_efficient_guidance(wrapper, context)
    assert not wrapper.m.has_objective()


@pytest.mark.parametrize("fault", ["objective", "context", "variable", "nonpositive", "overflow"])
def test_bad_models_fail_closed_without_partial_definitions(fault):
    context, wrapper, _ = setup()
    if fault == "objective":
        wrapper.m.minimize(wrapper.rooms["office"]["w"])
    elif fault == "context":
        wrapper.c = object()
    elif fault == "variable":
        wrapper.rooms["office"]["w"] = wrapper.rooms["coating_room"]["w"]
    elif fault == "nonpositive":
        wrapper.rooms["office"]["w"].proto.domain[0] = 0
    else:
        wrapper.rooms["coating_room"]["d"].proto.domain[1] = 10**10
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError):
        r5.apply_area_efficient_guidance(wrapper, context)
    assert str(wrapper.m.proto) == before


def test_whole_definition_work_batch_is_precharged_before_mutation():
    context, wrapper, _ = setup()
    # SYNTHETIC_RESOURCE_STATE_TEST. Original StageALedger/guard remains real.
    context.ledger.model_work = 1_200_000 - (3 * len(wrapper.m.proto.variables) + 3) - 26
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError, match="STAGE_A_RESOURCE_LIMIT"):
        r5.apply_area_efficient_guidance(wrapper, context)
    assert str(wrapper.m.proto) == before
    assert context.ledger.model_work == 1_200_000 - 26
    assert "R5_TOTAL_DEFINITIONS" not in context.ledger.resource_events


def test_original_pool_600000_cap_precharges_entire_r5_definition_batch(tmp_path):
    # Original Store/Lease in a SYNTHETIC temporary registry, not an Owner Grant.
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    context, wrapper, _ = setup()
    context.ledger = ledger
    read_cost = 3 * len(wrapper.m.proto.variables) + 3
    ledger.model_work = 600_000 - read_cost - 26
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError, match="REPLAY_RESERVATION_LIMIT"):
        r5.apply_area_efficient_guidance(wrapper, context)
    assert str(wrapper.m.proto) == before
    assert ledger.model_work == 600_000 - 26
    assert "R5_TOTAL_DEFINITIONS" not in ledger.resource_events
    lease.finish_pool()


def test_area_diagnostics_use_original_geometry_p1_and_preserve_candidate_hash():
    context, _, _ = setup(area="1")
    candidate = diagnostic_candidate()
    candidate.update(
        source_p1_handoff_hash=context.binding.p1_handoff_hash,
        source_zone_plan_hash=context.binding.canonical_zone_plan_hash,
        source_site_geometry_hash=context.binding.site_geometry_hash,
    )
    candidate["canonical_result_hash"] = canonical_hash(
        {k: v for k, v in candidate.items() if k != "canonical_result_hash"}
    )
    before = deepcopy(candidate)
    result = r5.area_efficiency_snapshot(candidate, "synthetic-handoff", context.binding)
    office = result["area_efficiency"]["rooms"]["office"]
    assert office["actual_area_m2"] == "8"
    assert office["area_allocation_ratio"] == "8"
    assert office["area_overallocation_ratio"] == "7"
    assert candidate == before
    assert result["functional_fit_status"] == "INPUT_REQUIRED"
    assert result["area_efficiency"]["coating_process"] == "PACKAGING_BOX_FILM_SEALING"
    assert canonical_hash(result) == canonical_hash(
        r5.area_efficiency_snapshot(candidate, "synthetic-handoff", context.binding)
    )
    candidate["source_p1_handoff_hash"] = "other-p1"
    with pytest.raises(LayoutAuthorityError, match="AUTHORITY_MISMATCH"):
        r5.area_efficiency_snapshot(candidate, "synthetic-handoff", context.binding)


def test_original_nine_metric_pareto_is_not_silently_redefined():
    before = area_snapshot("2")
    after = area_snapshot("3", office_aspect="3", footprint_perimeter_m="90")
    assert r4.compare_balanced_quality(before, after)["status"] == "GEOMETRIC_PARETO_IMPROVEMENT"
    actual = r5.compare_area_efficient_quality(before, after)
    assert actual["status"] == "QUALITY_TRADEOFF"
    assert actual["comparison_policy"] == r5.COMPARISON_POLICY != r4.COMPARISON_POLICY
    assert len(actual["metric_directions_minus_one_better"]) == 12
    assert actual["formal_quality_acceptance"] is False


@pytest.mark.parametrize(
    "fault", ["missing_area", "wrong_demand", "shortfall", "route", "structure", "p1"]
)
def test_missing_or_incomparable_area_evidence_never_pareto(fault):
    before, after = area_snapshot(), area_snapshot("1", office_aspect="3")
    if fault == "missing_area":
        del after["area_efficiency"]["rooms"]["office"]
    elif fault == "wrong_demand":
        after["area_efficiency"]["rooms"]["office"]["required_area_m2"] = "2"
    elif fault == "shortfall":
        after["area_efficiency"]["rooms"]["office"].update(
            actual_area_m2="1/2", area_allocation_ratio="1/2"
        )
    elif fault == "route":
        after["metrics"]["personnel_route_m"] = None
    elif fault == "p1":
        after["area_efficiency"]["source_p1_handoff_hash"] = "other"
    else:
        after["functional_diversity"]["meaningful_construction_hash"] = "other"
    assert r5.compare_area_efficient_quality(before, after)["status"] in {
        "INCOMPLETE_EVIDENCE",
        "NOT_COMPARABLE_STRUCTURE",
    }


def test_only_twelve_metric_pareto_updates_hint_and_keeps_baseline(monkeypatch):
    context, _, lease = setup()
    port = r5.StageBAreaEfficientQualityFairSearchSolver()
    port.start_handoff(context.ledger, 1)
    monkeypatch.setattr(r5, "area_efficiency_snapshot", lambda candidate, *_: candidate)
    handoff = SimpleNamespace(source_composition_hash="synthetic-handoff")
    first = area_snapshot()
    port.observe_validated_candidate(context, handoff, first, "ENGINEERING_ACCEPTED")
    bad = area_snapshot("3", office_aspect="3", footprint_perimeter_m="90")
    port.observe_validated_candidate(context, handoff, bad, "ENGINEERING_ACCEPTED")
    assert port.pending_guidance is None
    assert lease.events[-1]["status"] == "QUALITY_TRADEOFF"
    good = area_snapshot("1", office_aspect="3", footprint_perimeter_m="90")
    port.observe_validated_candidate(context, handoff, good, "ENGINEERING_REJECTED")
    assert port.pending_guidance is None
    port.observe_validated_candidate(context, handoff, good, "ENGINEERING_ACCEPTED")
    assert port.guidance_incumbent == good and port.pending_guidance == good
    assert port.baseline == first


@pytest.mark.parametrize(
    "old_hash", [None, "forged", r4.POLICY_HASH, r4.FIRST_STAGE_QUALITY_POLICY_HASH]
)
def test_old_grants_cannot_activate_r5(old_hash):
    context, _, lease = setup()
    lease.decision = {"balanced_quality_policy_hash": old_hash}
    port = r5.StageBAreaEfficientQualityFairSearchSolver()
    port.start_handoff(context.ledger, 6)
    with pytest.raises(LayoutAuthorityError, match="BOUND_POLICY_REQUIRED"):
        port.solutions(context, None)
    assert not context.ledger.attempts and not lease.events


def test_two_stages_reuse_model_proxy_ledger_and_unknown_is_not_infeasible():
    context, wrapper, _ = setup()
    engine = r5._AreaEfficientNative(context.ledger, 1)
    engine.prepare_first_stage(wrapper, context)
    shares = (engine.native_share, engine.work_share, engine.checked_share)
    first, status = engine._run(context, wrapper.m, 1, "ALL_ROOMS_ALL_ACCESS")
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    count = len(wrapper.m.proto.variables)
    receipt = engine.begin_improvement(wrapper, context, first)
    assert receipt["definitions_reused"] and receipt["policy_hash"] == r5.POLICY_HASH
    assert engine._baseline_proxy == first.value(variable(wrapper.m, "r5_area_worst"))
    assert engine.ledger is context.ledger
    assert shares == (engine.native_share, engine.work_share, engine.checked_share)
    constraints = [str(c) for c in wrapper.m.proto.constraints]
    _, status = engine._run(context, wrapper.m, 1e-9, "ALL_ROOMS_ALL_ACCESS")
    assert status == cp_model.UNKNOWN
    assert [str(c) for c in wrapper.m.proto.constraints] == constraints
    assert len(wrapper.m.proto.variables) == count
    assert len(context.ledger.attempts) == 2


def test_exhausted_share_cannot_start_improvement_or_drop_baseline(monkeypatch):
    context, wrapper, _ = setup()
    port = r5.StageBAreaEfficientQualityFairSearchSolver()
    port.start_handoff(context.ledger, 1)
    monkeypatch.setattr(r5, "area_efficiency_snapshot", lambda candidate, *_: candidate)
    first = area_snapshot()
    port.observe_validated_candidate(
        context,
        SimpleNamespace(source_composition_hash="synthetic-handoff"),
        first,
        "ENGINEERING_ACCEPTED",
    )
    port.native.prepare_first_stage(wrapper, context)
    port.native.native_share = 0
    before = str(wrapper.m.proto)
    with pytest.raises(LayoutAuthorityError):
        port.native.begin_improvement(wrapper, context, None)
    assert port.baseline == first and str(wrapper.m.proto) == before
    assert not context.ledger.attempts


def test_r5_rejects_hole_witnesses_with_original_exact_topology_cut(monkeypatch):
    context, lease = feasibility_context(monkeypatch)
    requirements(context)
    lease.decision = {"balanced_quality_policy_hash": r5.POLICY_HASH}

    class HoleModel(TinyModel):
        @staticmethod
        def layouts():
            hole = rooms()
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
            for row, (x, y) in zip(hole, positions, strict=True):
                row.update(x=x, y=y)
            return [hole, deepcopy(hole)]

        def __init__(self, *args):
            super().__init__(*args)
            self.c = args[0]
            self.interfaces[0]["corridor"] = False
            for role, room in self.rooms.items():
                for side in ("w", "d"):
                    room[side].proto.name = role + "_physical_" + side

    monkeypatch.setattr(native, "GlobalModel", HoleModel)
    monkeypatch.setattr(native, "AccessModel", HoleModel)
    port = r5.StageBAreaEfficientQualityFairSearchSolver()
    port.start_handoff(context.ledger, 1)
    stream = port.solutions(context, SimpleNamespace(source_composition_hash="synthetic-handoff"))
    terminal = next(stream)
    cuts = [e for e in lease.events if e["kind"] == "TOPOLOGY_REJECTED_WITNESS_CUT"]
    assert len(cuts) == 1 and cuts[0]["certificate"]["hole_count"] == 1
    assert "portal-position" not in cuts[0]["variable_names"]
    assert (
        terminal["solver_status"] == "INFEASIBLE" and not terminal["global_infeasibility_claimed"]
    )
    assert port.baseline is None
    stream.close()


def test_r5_default_is_not_wired_into_production_or_historical_runners():
    backend = Path(__file__).resolve().parents[2]
    for root in [backend / "scripts", backend / "src/cold_storage/bootstrap"]:
        assert all("stage_b_area_efficiency" not in file.read_text() for file in root.rglob("*.py"))
    assert (
        r4.FIRST_STAGE_QUALITY_POLICY_HASH
        == "sha256:fad41d6d4be18248b9a5ee93e299a591876e40e2422ac0ed5aa3924c2e2e5156"
    )
    assert r5.POLICY_HASH != r4.FIRST_STAGE_QUALITY_POLICY_HASH
    root = backend.parent
    assert Path(__file__).name in (root / ".github/workflows/ci-fast.yml").read_text()
    assert Path(__file__).name in (backend / "tests/stage_a_resource_process.py").read_text()


def test_proxy_sublevel_bounds_area_without_adding_an_area_cap():
    context, wrapper, _ = setup([((1, 4), (1, 4))] * 3)
    r5.apply_area_efficient_guidance(wrapper, context)
    # AM-GM is a diagnostic identity, not a new constraint or area permission.
    for w, d in product(range(1, 5), repeat=2):
        q = (1000 * (w + d) ** 2 + 3) // 4
        assert Fraction(w * d, 1) <= Fraction(q, 1000)
    assert all("area_cap" not in v.name for v in wrapper.m.proto.variables)


def test_same_solve_feedback_uses_area_proxy_not_old_aspect_baseline():
    context, wrapper, _ = setup()
    engine = r5._AreaEfficientNative(context.ledger, 1)
    engine.prepare_first_stage(wrapper, context)
    # Obtain a deliberately poor but legal tiny witness in the SAME model.
    # This fixture-only solver parameter is never used by the implementation.
    for room in wrapper.rooms.values():
        wrapper.m.add_hint(room["w"], 4)
        wrapper.m.add_hint(room["d"], 4)
    first = cp_model.CpSolver()
    first.parameters.fix_variables_to_their_hinted_value = True
    first.parameters.num_search_workers = 1
    assert first.solve(wrapper.m) == cp_model.OPTIMAL
    engine.begin_improvement(wrapper, context, first)
    assert engine._baseline_proxy == 16000  # Square aspect is 1, not 16.
    before = [str(c) for c in wrapper.m.proto.constraints]
    _, status = engine._run(context, wrapper.m, 1, "ALL_ROOMS_ALL_ACCESS")
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    feedback = context.ledger.attempts[-1]["search_feedback"]
    assert feedback["stop_requested"] and feedback["feedback_proxy"] < 16000
    assert not feedback["engineering_validated"]
    assert [str(c) for c in wrapper.m.proto.constraints] == before


def test_valid_stream_reuses_same_area_proxy_and_keeps_first_proposal(monkeypatch):
    context, lease = feasibility_context(monkeypatch)
    requirements(context)
    lease.decision = {"balanced_quality_policy_hash": r5.POLICY_HASH}

    class NamedModel(TinyModel):
        def __init__(self, *args):
            super().__init__(*args)
            self.c = args[0]
            for role, room in self.rooms.items():
                for side in ("w", "d"):
                    room[side].proto.name = role + "_physical_" + side

    monkeypatch.setattr(native, "GlobalModel", NamedModel)
    monkeypatch.setattr(native, "AccessModel", NamedModel)
    port = r5.StageBAreaEfficientQualityFairSearchSolver()
    port.start_handoff(context.ledger, 6)
    stream = port.solutions(context, SimpleNamespace(source_composition_hash="synthetic-handoff"))
    first = deepcopy(next(stream))
    original_hash = canonical_hash(first)
    second = stream.send("ENGINEERING_ACCEPTED")
    assert canonical_hash(first) == original_hash
    assert first["search_stage"] == "FEASIBILITY_FIRST"
    assert second["search_stage"] == "BOUNDED_QUALITY_IMPROVEMENT"
    assert second["construction_guidance"]["definitions_reused"]
    assert first["model_witness_topology"]["valid"] and second["model_witness_topology"]["valid"]
    assert sum(v.name == "r5_area_worst" for v in TinyModel.created[-1].m.proto.variables) == 1
    assert port.native.ledger is context.ledger
    stream.close()
