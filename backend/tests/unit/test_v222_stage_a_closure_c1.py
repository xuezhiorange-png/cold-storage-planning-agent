"""C1 exact topology, native portal mapping and no-reset resource safety."""

from __future__ import annotations

from typing import Any

import pytest
from ortools.sat.python import cp_model

from cold_storage.bootstrap.global_composition import generate_controlled_global_layout
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain import access_routing as native
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import (
    bind_native_portal_positions,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context


@pytest.mark.parametrize(
    "boxes,components,holes,valid",
    [
        ([(0, 0, 10, 10)], 1, 0, True),
        ([(0, 0, 10, 10), (20, 0, 30, 10)], 2, 0, False),
        ([(0, 0, 10, 30), (10, 0, 30, 10)], 1, 0, True),
        ([(0, 0, 30, 10), (0, 20, 30, 30), (0, 10, 10, 20), (20, 10, 30, 20)], 1, 1, False),
    ],
)
def test_exact_topology(boxes: Any, components: int, holes: int, valid: bool) -> None:
    row = inspect_rectangular_union(boxes)
    assert row["connected_component_count"] == components
    assert row["hole_count"] == holes
    assert row["valid"] is valid


def test_point_touch_and_nonpositive_rectangles_fail_closed() -> None:
    row = inspect_rectangular_union([(0, 0, 10, 10), (10, 10, 20, 20)])
    assert row["connected_component_count"] == 2
    assert row["singular_points_mm"] == [(10, 10)]
    assert row["valid"] is False
    assert inspect_rectangular_union([(0, 0, 0, 10)])["valid"] is False


@pytest.mark.parametrize("length,width", [(2, 2), (3, 2), (8, 2), (9, 2), (9, 3), (2, 3)])
def test_portal_mapping_exactly_matches_frozen_native_offsets(length: int, width: int) -> None:
    model = cp_model.CpModel()
    pos = model.new_int_var(0, 20, "position")
    active = model.new_bool_var("active")
    model.add(active == 1)
    bind_native_portal_positions(model, pos, 0, length, width, active, 20, "test")
    found = set()

    class Collect(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self) -> None:
            found.add(self.value(pos))

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.enumerate_all_solutions = True
    status = solver.solve(model, Collect())
    expected = {
        native._portal_center(r["segment_mm"])[0]
        for r in native._portal_candidates(
            ((0, 0), (length, 0)), edge_class="LONG_EDGE", clear_width_mm=width
        )
    }
    assert found == expected
    assert (status == cp_model.INFEASIBLE) is (not expected)


def test_inactive_short_face_does_not_reject_room_dimension() -> None:
    model = cp_model.CpModel()
    pos = model.new_int_var(0, 20, "position")
    active = model.new_bool_var("active")
    model.add(active == 0)
    bind_native_portal_positions(model, pos, 0, 1, 4, active, 20, "inactive")
    assert cp_model.CpSolver().solve(model) == cp_model.OPTIMAL


def test_unknown_history_and_zero_remaining_do_not_grant_one_millisecond(tmp_path: Any) -> None:
    from tests.unit.test_v222_execution_scope import approved_store

    with pytest.raises(LayoutAuthorityError, match="HISTORY_UNVERIFIED"):
        StageALedger(solver_wall=24.694611).remaining_solver_seconds()
    for consumed in (100, 101):
        store, _ = approved_store(tmp_path / str(consumed))
        ledger = store.open("NEW")
        ledger.solver_wall = consumed
        with pytest.raises(LayoutAuthorityError, match="ALLOWANCE_EXHAUSTED"):
            ledger.remaining_solver_seconds()
    store, _ = approved_store(tmp_path / "remaining")
    ledger = store.open("NEW")
    ledger.solver_wall = 99.5
    assert ledger.remaining_solver_seconds() == 0.5
    ledger.native_solver_active = True
    with pytest.raises(LayoutAuthorityError, match="HISTORY_UNVERIFIED"):
        ledger.remaining_solver_seconds()


def test_actual_server_entry_blocks_unverified_continuation_before_any_solve(
    monkeypatch: Any,
) -> None:
    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Native solver must not start on unknown historical usage")

    monkeypatch.setattr(cp_model.CpSolver, "solve", never)
    events = []
    ledger = StageALedger(solver_wall=24.694611, audit_sink=events.append)
    plan, p1, site = _context()
    result = generate_controlled_global_layout(plan, p1.to_dict(), site, execution_ledger=ledger)
    assert result["proposal"]["solver_status"] == "NOT_STARTED"
    assert result["proposal"]["codes"] == ["CP_SAT_CUMULATIVE_HISTORY_UNVERIFIED"]
    assert result["stage_a_engineering_accepted"] is False
    assert result["server_owned_generation"] is False
    assert result["resource_ledger"]["solver_wall_seconds"] == 24.694611
    assert result["resource_ledger"]["attempts"] == []
    assert len(events) >= 2


def test_b0_positive_native_application_union_remains_valid() -> None:
    from cold_storage.modules.layout.application.access_routing import route_site_placement
    from tests.unit.test_v22_p2d_access_routing import rebuilt_access_context

    plan, p1, site, placement, _, zones, *_rest = rebuilt_access_context()
    app = route_site_placement(plan, p1, site, placement, None).to_dict()
    assert (
        sum(r["status"] == "PASS" and r["flow_kind"] != "TRUCK" for r in app["access_results"])
        == 11
    )
    assert app["building_footprint"]
    boxes = [r.bounds_mm for r in zones.values()]
    for route in app["corridors"]:
        for raw in route["envelope"]:
            poly = native.normalize_polygon(raw, allow_numeric_string=True)
            boxes.append(
                (
                    min(x for x, _ in poly),
                    min(y for _, y in poly),
                    max(x for x, _ in poly),
                    max(y for _, y in poly),
                )
            )
    topology = inspect_rectangular_union(boxes)
    assert topology["valid"] is True
    assert topology["hole_count"] == 0


def test_exact_assignment_cut_preserves_another_route_for_same_rooms() -> None:
    from types import SimpleNamespace

    from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
        physical_assignment_variables,
    )

    model = cp_model.CpModel()
    room_x = model.new_int_var(0, 1, "room_x")
    route_x = model.new_int_var(0, 1, "route_x")
    zero = model.new_int_var(0, 0, "zero")
    active = model.new_bool_var("corridor")
    model.add(active == 1)
    auxiliary = model.new_int_var(0, 1, "unused_nonphysical")
    wrapper = SimpleNamespace(
        rooms={"role": dict(x=room_x, y=0, nw=1, nd=1, rot=0)},
        interfaces=[],
        routes=[dict(corridor=active, points=[(route_x, zero)])],
    )
    initial = model.clone()
    initial.add(room_x == 0)
    initial.add(route_x == 0)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    assert solver.solve(initial) == cp_model.OPTIMAL
    variables = physical_assignment_variables(wrapper, solver)
    assert auxiliary.index not in {v.index for v in variables}
    model.add_forbidden_assignments(variables, [[solver.value(v) for v in variables]])
    same_rooms = model.clone()
    same_rooms.add(room_x == 0)
    same_rooms.add(route_x == 1)
    assert solver.solve(same_rooms) == cp_model.OPTIMAL
    same_invalid_geometry = model.clone()
    same_invalid_geometry.add(room_x == 0)
    same_invalid_geometry.add(route_x == 0)
    same_invalid_geometry.add(auxiliary == 1)
    assert solver.solve(same_invalid_geometry) == cp_model.INFEASIBLE
