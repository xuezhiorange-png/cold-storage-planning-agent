"""Optional local scope, exact exported-length and bounded feedback contracts.

Small synthetic Native models only; no real input, runner or authorization store.
"""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_route_refinement as refinement
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel
from cold_storage.modules.layout.infrastructure.stage_b_changing_frontage_corridor import (
    StageBChangingFrontageCorridorFairSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_first_feasible_recovery import (
    StageBFirstFeasibleRecoveryFairSolver,
)
from tests.r9_changing_joint_synthetic import build_scene

PATHS = [
    [(0, 0), (0, 1), (0, 3), (4, 3), (4, 5), (4, 6)],
    [(0, 0), (0, 1), (4, 1), (4, 5), (5, 5), (6, 5)],
    [(0, 0), (0, 0), (0, 0), (0, 0), (0, 0), (0, 0)],
    [(0, 0), (0, 1), (0, 4), (0, 2), (0, 3), (0, 6)],
    [(0, 0), (0, 1), (0, 0), (4, 0), (2, 0), (2, 5)],
    [(1, 1), (1, 1), (1, 5), (4, 5), (4, 5), (4, 1)],
    [(0, 0), (0, 1), (5, 1), (2, 1), (2, 0), (2, 4)],
    [(0, 0), (0, 3), (0, 0), (0, 0), (0, 1), (4, 1)],
]


@pytest.mark.parametrize("path", PATHS)
def test_cp_length_matches_original_export_including_duplicates_and_backtracks(path):
    m = cp_model.CpModel()
    points = [
        [m.new_int_var(v, v, f"point{i}_{axis}") for axis, v in enumerate(p)]
        for i, p in enumerate(path)
    ]
    events = []
    length = refinement.exported_length_expression(m, points, lambda *args: events.append(args))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 3
    solver.parameters.cp_model_presolve = True
    solver.parameters.search_branching = cp_model.PARTIAL_FIXED_SEARCH
    solver.parameters.max_time_in_seconds = 0.5
    assert solver.solve(m) == cp_model.OPTIMAL
    route = dict(
        req=dict(identity="personnel", from_ref="main_entrance", to_ref="changing_room"),
        points=points,
        corridor=points[0][0],
        pw=1500,
        cw=2000,
    )
    # A thin read adapter supplies only this synthetic selector; real point
    # values and all compression/envelopes are handled by the original exporter.
    reader = SimpleNamespace(value=solver.value, boolean_value=lambda _: True)
    view = SimpleNamespace(
        routes=[route],
        c=SimpleNamespace(
            pack_req=dict(identity="pack", from_ref="p", to_ref="s"),
            profile=SimpleNamespace(
                portal_clear_width_m=Decimal("2.4"), corridor_clear_width_m=Decimal("2.5")
            ),
        ),
    )
    interface = dict(
        portal_packaging_mm=[(0, 0), (0, 0)],
        portal_sorting_mm=[(0, 0), (0, 0)],
        centerline_mm=[],
        mode="DIRECT_SHARED_EDGE",
    )
    actual = AccessModel.export_routes(view, reader, {}, interface)[0]
    assert solver.value(length) == actual["length_mm"]
    assert sum(n for _, n in events) > 0


def test_length_definition_is_total_for_original_variable_domain():
    # Several geometrically distinct paths and auxiliary choices remain possible.
    m = cp_model.CpModel()
    points = [[m.new_int_var(-2, 2, f"p{i}_{axis}") for axis in (0, 1)] for i in range(6)]
    before = [(v.name, list(v.domain)) for v in m.proto.variables]
    refinement.exported_length_expression(m, points, lambda *_: None)
    assert before == [(v.name, list(v.domain)) for v in list(m.proto.variables)[:12]]
    assert m.validate() == ""


def test_foreign_points_are_rejected():
    m = cp_model.CpModel()
    other = cp_model.CpModel()
    points = [[other.new_int_var(0, 1, f"p{i}_{axis}") for axis in (0, 1)] for i in range(6)]
    with pytest.raises(LayoutAuthorityError, match="FOREIGN_POINT"):
        refinement.exported_length_expression(m, points, lambda *_: None)


def test_first_stage_native_configuration_and_guidance_are_inherited():
    c, m = build_scene(reference=True)
    ports = [
        StageBFirstFeasibleRecoveryFairSolver(),
        StageBChangingFrontageCorridorFairSolver(),
        refinement.StageBSameProxyRouteRefinementFairSolver(),
    ]
    protos = []
    for port in ports:
        cc, mm = build_scene(reference=True)
        port.start_handoff(cc.ledger, 1)
        assert not port.native.improving
        assert "final_model_search" not in port._continuation_options(cc)
        port._final_guidance(mm, cc)
        mm.m.add_decision_strategy(
            [r["corridor"] for r in mm.routes], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE
        )
        protos.append(str(mm.m.proto))
    assert protos[0] == protos[1] == protos[2]
    assert ports[0].native._run.__func__ is ports[2].native._run.__func__
    assert "before_accepted_geometry_cut" not in ports[1]._continuation_options(c)
    assert "before_accepted_geometry_cut" in ports[2]._continuation_options(c)
    assert len({p.quality_policy_hash for p in ports}) == 3
    assert str(m.m.proto)  # untouched source fixture


@pytest.mark.parametrize("old_policy", ["old-r5", "old-r6", "old-r7", "old-r9"])
def test_old_authorization_policy_cannot_select_new_strategy(old_policy):
    c, _ = build_scene(reference=True)
    c.ledger.execution_authorization.decision = {"balanced_quality_policy_hash": old_policy}
    port = refinement.StageBSameProxyRouteRefinementFairSolver()
    port.start_handoff(c.ledger, 1)
    with pytest.raises(LayoutAuthorityError, match="BOUND_POLICY_REQUIRED"):
        port.solutions(c, SimpleNamespace())


def test_unaccepted_local_candidate_cannot_replace_baseline_or_guidance():
    port = refinement.StageBSameProxyRouteRefinementFairSolver()
    port.baseline = {"preserved": True}
    port.pending_guidance = None
    before = deepcopy(port.baseline)
    port.observe_validated_candidate(
        None, None, {"proposal": {"route_refinement": {}}}, "EXAMINED_WITNESS"
    )
    assert port.baseline == before and port.pending_guidance is None


def test_premature_hook_is_rejected_before_clone_or_solve(monkeypatch):
    c, m = build_scene(reference=True)
    port = refinement.StageBSameProxyRouteRefinementFairSolver()
    port.start_handoff(c.ledger, 1)
    monkeypatch.setattr(refinement, "_local_model", lambda *_: pytest.fail("must not clone"))
    with pytest.raises(LayoutAuthorityError, match="ACCEPTED_SECOND_STAGE_REQUIRED"):
        next(port.native.refine_routes(c, m, None, {}))


def local_setup():
    c, m = build_scene(reference=True)
    port = refinement.StageBSameProxyRouteRefinementFairSolver()
    port.start_handoff(c.ledger, 1)
    port._final_guidance(m, c)
    for row in m.rooms.values():
        row.update(nw=row["w"], nd=row["d"], rot=0)
    m.handoff.source_composition_hash = "synthetic-local-contract"
    solver, status = port.native._run(c, m.m, 0.5, "ALL_ROOMS_ALL_ACCESS")
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    # Unit protocol state only. Full 12-role acceptance is tested separately.
    port.native.improving = True
    port.native._feedback_model = m.m
    return c, m, port, solver


def test_clone_scope_never_mutates_parent_and_keeps_original_hint():
    c, m, port, solver = local_setup()
    m.m.add_hint(m.rooms["changing_room"]["x"], solver.value(m.rooms["changing_room"]["x"]))
    before = str(m.m.proto)
    local, length = refinement._local_model(m, solver, c, port.native._feedback_proxy_index)
    assert str(m.m.proto) == before
    assert str(local.proto.solution_hint) == str(m.m.proto.solution_hint)
    assert len(local.proto.variables) > len(m.m.proto.variables)
    assert local.proto.objective.vars[0] == length.index
    assert local.proto.objective.vars[0] != m.m.proto.objective.vars[0]
    local.add(length < 0)  # Deliberately impossible LOCAL condition.
    assert str(m.m.proto) == before
    assert c.ledger.resource_events["ROUTE_LOCAL_MODEL_COPY"] > 0
    assert c.ledger.resource_events["ROUTE_LOCAL_CONSTRAINT"] > 0


@pytest.mark.parametrize("status", [cp_model.UNKNOWN, cp_model.INFEASIBLE])
def test_unknown_or_no_shorter_local_route_stops_once_without_false_global_proof(
    monkeypatch, status
):
    c, m, port, accepted = local_setup()
    before = str(m.m.proto)
    calls = []

    def run(*args):
        calls.append(args)
        return SimpleNamespace(
            status_name=lambda _: cp_model.CpSolver().status_name(status)
        ), status

    monkeypatch.setattr(port.native, "_run", run)
    route = dict(
        from_ref="main_entrance",
        to_ref="changing_room",
        length_mm=9000,
        path_mm=[(0, 0), (0, 9000)],
    )
    assert list(port.native.refine_routes(c, m, accepted, {"routes": [route]})) == []
    assert len(calls) == 1
    assert str(m.m.proto) == before and port.native._route_model is None
    events = c.ledger.execution_authorization.events
    assert any(e.get("status") == cp_model.CpSolver().status_name(status) for e in events)
    assert not any(e.get("global_infeasibility_claimed") for e in events)
    assert list(port.native.refine_routes(c, m, accepted, {"routes": [route]})) == []
    assert len(calls) == 1  # Same room geometry cannot endlessly restart refinement.


def test_no_resource_does_not_clone_or_solve(monkeypatch):
    c, m, port, accepted = local_setup()
    monkeypatch.setattr(port.native, "remaining_share", lambda _: (0.01, 1))
    monkeypatch.setattr(refinement, "_local_model", lambda *_: pytest.fail("no clone allowance"))
    monkeypatch.setattr(port.native, "_run", lambda *_: pytest.fail("no Native allowance"))
    assert list(port.native.refine_routes(c, m, accepted, {})) == []


def test_original_stream_forwards_refinement_to_application_before_room_cut(monkeypatch):
    from cold_storage.modules.layout.infrastructure import global_cp_sat_solver as native
    from tests.unit.test_v222_stage_b_multi_solution import TinyModel, native_setup

    c, lease = native_setup(monkeypatch)
    seen = []

    def hook(model, solver, record):
        before = str(model.m.proto)
        seen.append("entered")
        feedback = yield dict(record, diagnostic_local_witness=True)
        seen.append(feedback)
        assert str(model.m.proto) == before

    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        c,
        None,
        accepted_model_guidance=lambda *_: {},
        before_accepted_geometry_cut=hook,
        event_sink=lease.events.append,
    )
    first = next(stream)
    repeated = stream.send("ENGINEERING_ACCEPTED")
    assert seen == [] and first["zones"] == repeated["zones"]
    local = stream.send("ENGINEERING_ACCEPTED")
    assert local["diagnostic_local_witness"] and seen == ["entered"]
    subsequent = stream.send("EXAMINED_WITNESS")
    assert seen == ["entered", "EXAMINED_WITNESS"]
    assert subsequent["zones"] != first["zones"]
    assert any(e.get("kind") == "ACCEPTED_GEOMETRY_ENUMERATION_CUT" for e in lease.events)
    assert len(TinyModel.created) == 3
    stream.close()


def test_rejected_engineering_route_never_yields_accepted_witness(monkeypatch):
    c, m, port, accepted = local_setup()
    # Fault injection exercises rejection control flow; no original engineering
    # PASS is mocked or claimed. Native generation/full oracle have a separate
    # complete 12-zone synthetic experiment.
    good_route = dict(
        from_ref="main_entrance",
        to_ref="changing_room",
        length_mm=7000,
        path_mm=[(0, 0), (0, 7000)],
        envelopes_mm=[],
    )
    monkeypatch.setattr(refinement, "validate_global_geometry", lambda *_: {"pass": False})
    m.export = lambda _: (
        {"z": SimpleNamespace(bounds_mm=(0, 0, 1000, 1000), to_dict=lambda: {})},
        {},
    )
    m.export_routes = lambda *_: [good_route]

    class Read:
        def value(self, v):
            return 7000 if v.name == "route_exported_length_mm" else accepted.value(v)

        def status_name(self, _):
            return "FEASIBLE"

    calls = []

    def run(*_):
        calls.append(1)
        return Read(), cp_model.FEASIBLE

    monkeypatch.setattr(port.native, "_run", run)
    before = str(m.m.proto)
    original = dict(good_route, length_mm=9000)
    assert list(port.native.refine_routes(c, m, accepted, {"routes": [original]})) == []
    assert len(calls) <= refinement.MAX_ROUTE_ATTEMPTS
    assert str(m.m.proto) == before
    assert port.baseline is None
    assert any(
        e.get("status") == "ORIGINAL_GEOMETRY_OR_TOPOLOGY_REJECTED"
        for e in c.ledger.execution_authorization.events
    )


def test_v2_and_twelve_comparators_remain_strict():
    from tests.unit.test_v222_stage_b_area_efficiency import area_snapshot

    before = area_snapshot()
    after = deepcopy(before)
    after["functional_diversity"]["meaningful_construction_hash"] = (
        "different-real-portal-organization"
    )
    assert (
        refinement.compare_balanced_quality(before, after)["status"] == "NOT_COMPARABLE_STRUCTURE"
    )
    assert (
        refinement.compare_area_efficient_quality(before, after)["status"]
        == "NOT_COMPARABLE_STRUCTURE"
    )


def test_actual_local_cp_model_has_no_solution_strictly_shorter_than_its_optimum():
    c, m, port, accepted = local_setup()
    before = str(m.m.proto)
    local, length = refinement._local_model(m, accepted, c, port.native._feedback_proxy_index)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 3
    solver.parameters.cp_model_presolve = True
    solver.parameters.search_branching = cp_model.PARTIAL_FIXED_SEARCH
    solver.parameters.max_time_in_seconds = 0.5
    assert solver.solve(local) == cp_model.OPTIMAL
    local.add(length < solver.value(length))
    assert solver.solve(local) == cp_model.INFEASIBLE  # This LOCAL fixed-room optimum only.
    assert str(m.m.proto) == before


def test_close_during_local_application_validation_discards_scope(monkeypatch):
    c, m, port, accepted = local_setup()
    route = dict(
        from_ref="main_entrance",
        to_ref="changing_room",
        length_mm=7000,
        path_mm=[(0, 0), (0, 7000)],
        envelopes_mm=[],
    )
    monkeypatch.setattr(
        refinement,
        "validate_global_geometry",
        lambda *_: {"pass": True, "unit_protocol_only": True},
    )
    m.export = lambda _: (
        {"z": SimpleNamespace(bounds_mm=(0, 0, 1000, 1000), to_dict=lambda: {})},
        {},
    )
    m.export_routes = lambda *_: [route]

    class Read:
        def value(self, v):
            return 7000 if v.name == "route_exported_length_mm" else accepted.value(v)

        def status_name(self, _):
            return "FEASIBLE"

    monkeypatch.setattr(port.native, "_run", lambda *_: (Read(), cp_model.FEASIBLE))
    before = str(m.m.proto)
    gen = port.native.refine_routes(c, m, accepted, {"routes": [dict(route, length_mm=9000)]})
    assert next(gen)["route_refinement"]["cp_length_mm"] == 7000
    assert port.native._route_model is not None
    gen.close()
    assert port.native._route_model is None and str(m.m.proto) == before


def test_strict_synthetic_adapter_preserves_overrun_and_refuses_precharge():
    from cold_storage.modules.layout.application.global_composition_solver import StageALedger
    from tests.r9_route_refinement_experiment import StrictSyntheticQuota

    quota = StrictSyntheticQuota("unit-policy")
    ledger = StageALedger(solver_monotonic_wall=8.001)
    with pytest.raises(LayoutAuthorityError, match="RESOURCE_FAIL"):
        quota.guard(ledger)
    assert quota.failed and ledger.solver_monotonic_wall == 8.001
    fresh = StageALedger(model_work=599999)
    with pytest.raises(LayoutAuthorityError, match="PRECHARGE_LIMIT"):
        StrictSyntheticQuota("unit-policy").precharge_work(fresh, 2)
    assert fresh.model_work == 599999


def test_refinement_audit_uses_complete_original_pool_source_contract():
    from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import PoolLease

    c, _ = build_scene(reference=True)
    expected = dict(
        zone_plan_hash=c.binding.canonical_zone_plan_hash,
        p1_hash=c.binding.p1_handoff_hash,
        site_hash=c.binding.site_geometry_hash,
        composition_hash="synthetic-active-composition",
    )
    # Exercise the original source/active-accounting/hash writer in memory.
    # Owner admission itself is not invoked, fabricated, or tested as real.
    lease = SimpleNamespace(
        validate=lambda _: None,
        ledger=c.ledger,
        record=dict(composition_active=True, cursor=1),
        state=dict(accounting_complete=True),
        decision={**expected, "compositions": [{"composition_hash": expected["composition_hash"]}]},
    )
    original = c.ledger.execution_authorization
    original.record_enumeration = lambda sources, event: PoolLease.record_enumeration(
        lease, sources, event
    )
    engine = refinement._RouteRefinementNative(c.ledger, 1)
    engine._route_composition_hash = expected["composition_hash"]
    before = c.ledger.model_work
    engine._event(c, "SYNTHETIC_CONTRACT_ONLY")
    entry = lease.record["enumeration_events"][0]
    assert entry["sources"] == expected and entry["canonical_event_hash"]
    assert c.ledger.model_work == before + 1
    with pytest.raises(LayoutAuthorityError, match="SOURCE_MISMATCH"):
        PoolLease.record_enumeration(lease, {"composition_hash": expected["composition_hash"]}, {})


def test_foreign_context_cannot_enter_local_scope(monkeypatch):
    c, m = build_scene(reference=True)
    port = refinement.StageBSameProxyRouteRefinementFairSolver()
    port.start_handoff(c.ledger, 1)
    port.native.improving = True
    port.native._feedback_model = m.m
    m.c = object()
    monkeypatch.setattr(refinement, "_local_model", lambda *_: pytest.fail("foreign context"))
    with pytest.raises(LayoutAuthorityError, match="ACCEPTED_SECOND_STAGE_REQUIRED"):
        next(port.native.refine_routes(c, m, None, {}))
