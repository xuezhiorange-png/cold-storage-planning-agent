"""R7 resource admission only. No frozen-20t Native or real authorization."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_route_refinement as routes
from cold_storage.modules.layout.infrastructure import (
    stage_b_route_refinement_resources as resources,
)
from tests.unit.test_v222_stage_b_route_refinement import local_setup


def ready():
    c, m, old, accepted = local_setup()
    port = resources.StageBResourceBoundRouteRefinementFairSolver()
    port.start_handoff(c.ledger, 1)
    n = port.native
    n.improving = True
    n._feedback_model = m.m
    n._feedback_proxy_index = old.native._feedback_proxy_index
    n._route_composition_hash = m.handoff.source_composition_hash
    return c, m, n, accepted


def record():
    return {
        "routes": [
            dict(
                from_ref="main_entrance",
                to_ref="changing_room",
                length_mm=9000,
                path_mm=[(0, 0), (0, 9000)],
            )
        ]
    }


def test_actual_unchanged_preparation_cost_is_bounded_and_not_reserved_as_fake_work():
    c, m, n, s = ready()
    before = str(m.m.proto)
    estimate = resources.preparation_work_bound(m)
    start = c.ledger.model_work
    local, length = n._build_local_model(m, s, c)
    actual = c.ledger.model_work - start - estimate["planning_work"]
    assert actual <= estimate["required_work_upper"]
    assert n._resource_local_copies == 1 and str(m.m.proto) == before
    assert c.ledger.resource_events["ROUTE_LOCAL_MODEL_COPY"] == estimate["copy_work"]
    assert c.ledger.resource_events["ROUTE_RESOURCE_PREFLIGHT_READ"] == estimate["planning_work"]
    assert actual < estimate["required_work_upper"]  # bound is not charged as actual construction.
    assert local.proto.objective.vars[0] == length.index


@pytest.mark.parametrize("kind", ["handoff_work", "global_work", "native", "elapsed", "checked"])
def test_insufficient_resource_skips_before_copy_and_native(monkeypatch, kind):
    c, m, n, s = ready()
    before = str(m.m.proto)
    calls = len(c.ledger.attempts)
    if kind == "handoff_work":
        n.work_share = 500
    elif kind == "global_work":
        c.ledger.model_work = 599500
        n.work_before = c.ledger.model_work
    elif kind == "native":
        n.native_share = 0.01
    elif kind == "elapsed":
        n.elapsed_share = 0.01
    else:
        n.checked_share = 0
    monkeypatch.setattr(routes, "_local_model", lambda *_: pytest.fail("copy must not start"))
    monkeypatch.setattr(n, "_run", lambda *_: pytest.fail("Native must not start"))
    assert list(n.refine_routes(c, m, s, record())) == []
    assert str(m.m.proto) == before and len(c.ledger.attempts) == calls
    assert "ROUTE_LOCAL_MODEL_COPY" not in c.ledger.resource_events
    assert any(
        e.get("status") == "LOCAL_REFINEMENT_SKIPPED"
        for e in c.ledger.execution_authorization.events
    )


def test_one_successful_copy_blocks_second_copy_for_different_room_geometry(monkeypatch):
    c, m, n, s = ready()
    n._build_local_model(m, s, c)
    monkeypatch.setattr(routes, "_local_model", lambda *_: pytest.fail("second copy forbidden"))
    assert list(n.refine_routes(c, m, s, record())) == []
    assert n._resource_local_copies == 1
    assert c.ledger.execution_authorization.events[-1]["reason"] == "HANDOFF_COPY_LIMIT"


def test_real_precharge_or_guard_failure_is_not_swallowed_as_skip(monkeypatch):
    c, m, n, s = ready()

    def fail(*_):
        raise LayoutAuthorityError("ACTUAL_RESOURCE_OVERRUN_TEST")

    monkeypatch.setattr(c.ledger, "guard", fail)
    with pytest.raises(LayoutAuthorityError, match="ACTUAL_RESOURCE_OVERRUN"):
        list(n.refine_routes(c, m, s, record()))
    assert not any(
        e.get("status") == "LOCAL_REFINEMENT_SKIPPED"
        for e in c.ledger.execution_authorization.events
    )


def test_enclosing_trusted_precharge_failure_remains_hard_error(monkeypatch):
    c, m, n, s = ready()

    def fail(*_):
        raise LayoutAuthorityError("ENCLOSING_TASK_RESOURCE_LIMIT")

    monkeypatch.setattr(c.ledger, "precharge_work", fail)
    with pytest.raises(LayoutAuthorityError, match="ENCLOSING_TASK_RESOURCE_LIMIT"):
        n._build_local_model(m, s, c)
    assert "ROUTE_LOCAL_MODEL_COPY" not in c.ledger.resource_events


def test_old_policy_cannot_select_resource_strategy():
    c, m, old, _ = local_setup()
    c.ledger.execution_authorization.decision = {"balanced_quality_policy_hash": routes.POLICY_HASH}
    port = resources.StageBResourceBoundRouteRefinementFairSolver()
    port.start_handoff(c.ledger, 1)
    with pytest.raises(LayoutAuthorityError, match="BOUND_POLICY_REQUIRED"):
        port.solutions(c, m.handoff)
    assert resources.POLICY_HASH != routes.POLICY_HASH
    assert port.native.prepare_first_stage.__func__ is old.native.prepare_first_stage.__func__
    assert port.native._run.__func__ is old.native._run.__func__


def test_skip_returns_to_original_room_enumeration(monkeypatch):
    from cold_storage.modules.layout.infrastructure import global_cp_sat_solver as native
    from tests.unit.test_v222_stage_b_multi_solution import native_setup

    c, lease = native_setup(monkeypatch)
    c.binding = SimpleNamespace(
        canonical_zone_plan_hash="unit-plan",
        p1_handoff_hash="unit-p1",
        site_geometry_hash="unit-site",
    )
    n = resources._ResourceBoundRouteNative(c.ledger, 1)
    h = SimpleNamespace(source_composition_hash="unit-handoff")

    def accepted(m, s):
        m.c = c
        m.handoff = h
        n.improving = True
        n._feedback_model = m.m
        return {}

    def hook(m, s, r):
        # Deliberate soft local-preparation shortage. The original tiny
        # global search still has time and is NOT cancelled by local SKIP.
        n.elapsed_share = 10**-3
        yield from n.refine_routes(c, m, s, r)

    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        c,
        h,
        accepted_model_guidance=accepted,
        before_accepted_geometry_cut=hook,
        event_sink=lease.events.append,
    )
    first = next(stream)
    repeat = stream.send("ENGINEERING_ACCEPTED")
    assert first["zones"] == repeat["zones"]
    after = stream.send("ENGINEERING_ACCEPTED")
    assert after["zones"] != first["zones"]
    assert any(e.get("status") == "LOCAL_REFINEMENT_SKIPPED" for e in lease.events)
    stream.close()


def test_same_v2_strict_comparators_are_the_original_functions():
    assert (
        resources.StageBResourceBoundRouteRefinementFairSolver.observe_validated_candidate
        is routes.StageBSameProxyRouteRefinementFairSolver.observe_validated_candidate
    )
    assert (
        resources.StageBResourceBoundRouteRefinementFairSolver._final_guidance
        is routes.StageBSameProxyRouteRefinementFairSolver._final_guidance
    )


def test_length_definition_942_work_is_actual_not_discounted():
    c, _, _, _ = ready()
    m = cp_model.CpModel()  # The real local scope is a plain, unowned model too.
    points = [[m.new_int_var(0, 20000, f"p{i}_{axis}") for axis in (0, 1)] for i in range(6)]
    start = dict(c.ledger.resource_events)
    before = c.ledger.model_work
    length = routes.exported_length_expression(m, points, c.ledger.charge)
    assert c.ledger.model_work - before == resources.LENGTH_DEFINITION_WORK == 942
    for key, expected in (("REFERENCE", 12), ("VARIABLE", 336), ("CONSTRAINT", 594)):
        label = "ROUTE_LOCAL_" + key
        assert c.ledger.resource_events[label] - start.get(label, 0) == expected
    assert m.validate() == "" and length.name == "route_exported_length_mm"


@pytest.mark.parametrize("ordinal", range(6))
def test_complete_20t_model_initial_share_skips_without_copy_or_native(monkeypatch, ordinal):
    from cold_storage.modules.layout.infrastructure.stage_b_changing_frontage_corridor import (
        apply_changing_frontage_corridor_search,
    )
    from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
        apply_frontage_joint_search,
    )
    from tests.unit.test_v222_stage_b_frontage_joint_search import complete_context
    from tests.unit.test_v222_stage_b_multi_solution import EnumerationLease

    monkeypatch.setattr(
        cp_model.CpSolver, "solve", lambda *_: pytest.fail("frozen20t Native forbidden")
    )
    monkeypatch.setattr(
        cp_model.CpSolver, "Solve", lambda *_: pytest.fail("frozen20t Native forbidden")
    )
    c, hs = complete_context()

    class ConstructionOnly(EnumerationLease):
        def remaining_solver_seconds(self, ledger):
            return 49.9

    c.ledger.solver_history_verified = True
    c.ledger.execution_authorization = ConstructionOnly()
    n = resources._ResourceBoundRouteNative(c.ledger, 6)
    h = hs[ordinal]
    m = n._new_final_model(c, h)
    n.prepare_first_stage(m, c)
    m.m.add_decision_strategy(
        [r["corridor"] for r in m.routes], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE
    )
    original = len(m.m.proto.search_strategy)
    apply_frontage_joint_search(m, c)
    strategies = m.m.proto.search_strategy
    c.ledger.charge(
        "R7_DEFERRED_STRATEGY_REORDER", len(strategies) + sum(len(s.exprs) for s in strategies)
    )
    order = [deepcopy(s) for s in strategies]
    strategies.clear()
    strategies.extend(order[original:] + order[:original])
    apply_changing_frontage_corridor_search(m, c)
    n._route_composition_hash = h.source_composition_hash
    before = str(m.m.proto)
    monkeypatch.setattr(routes, "_local_model", lambda *_: pytest.fail("full copy not affordable"))
    with pytest.raises(resources._PreparationSkip, match="HANDOFF_WORK"):
        n._build_local_model(m, None, c)  # No accepted witness is fabricated.
    assert str(m.m.proto) == before and not c.ledger.attempts
    assert "ROUTE_LOCAL_MODEL_COPY" not in c.ledger.resource_events
    assert c.ledger.resource_events["ROUTE_RESOURCE_PREFLIGHT_READ"] > 0


def test_planning_work_already_performed_is_charged_even_if_copy_skips(monkeypatch):
    c, m, n, s = ready()
    n.work_share = 500
    monkeypatch.setattr(routes, "_local_model", lambda *_: pytest.fail("copy forbidden"))
    estimate = resources.preparation_work_bound(m)
    before = c.ledger.model_work
    assert list(n.refine_routes(c, m, s, record())) == []
    assert c.ledger.resource_events["ROUTE_RESOURCE_PREFLIGHT_READ"] == estimate["planning_work"]
    assert c.ledger.model_work > before
    assert "ROUTE_LOCAL_MODEL_COPY" not in c.ledger.resource_events
