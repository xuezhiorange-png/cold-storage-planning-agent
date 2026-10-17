"""Controlled global backend: authority, exact geometry and CP-SAT regressions."""

from __future__ import annotations

import inspect
from decimal import Decimal
from typing import Any

import pytest
from ortools.sat.python import cp_model

from cold_storage.bootstrap.global_composition import generate_controlled_global_layout
from cold_storage.modules.layout.application.global_composition_solver import (
    RESOURCE_SCOPE,
    _overlap,
    _route_geometry_errors,
    generate_global_composition_candidate,
    rectangular_scope,
    validate_native_access_geometry,
    zone_geometry_hash,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import (
    AccessModel,
    disjoint,
    envelopes,
    touch,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context


def test_controlled_entry_accepts_neither_coordinates_nor_handoff() -> None:
    assert set(inspect.signature(generate_controlled_global_layout).parameters) == {
        "canonical_zone_plan",
        "p1_handoff",
        "site_geometry",
        "composition_identity",
        "execution_ledger",
    }
    assert "NOT_MAPPED_TO_P3_DFS" in RESOURCE_SCOPE


def test_server_replay_is_consumed_and_unknown_not_relabelled() -> None:
    class InspectSolver:
        def solve(self, context: Any, handoff: Any) -> dict[str, Any]:
            assert len(context.binding.dimension_authorities) == 12
            assert len(context.must) == 7
            assert len(context.binding.access_requirements) == 12
            assert handoff.source_site_geometry_hash == context.site.canonical_result_hash
            assert handoff.source_p1_handoff_hash == context.binding.p1_handoff_hash
            assert not hasattr(context, "seed")
            return {"solver_status": "UNKNOWN"}

    plan, p1, site = _context()
    result = generate_global_composition_candidate(plan, p1.to_dict(), site, solver=InspectSolver())
    assert result["proposal"]["solver_status"] == "UNKNOWN"
    assert result["p3_complete"] is False
    assert result["p2_complete"] is False
    assert result["historical_candidate_injected"] is False
    assert "engineering_validation" not in result


def test_mutated_authority_or_fake_composition_cannot_reach_solver() -> None:
    class NeverSolver:
        def solve(self, context: Any, handoff: Any) -> dict[str, Any]:
            raise AssertionError("invalid sources reached backend")

    plan, p1, site = _context()
    with pytest.raises(LayoutAuthorityError):
        generate_global_composition_candidate(
            plan, p1.to_dict(), site, solver=NeverSolver(), composition_identity="caller-created"
        )
    bad = p1.to_dict()
    bad["source_zone_plan_hash"] = "sha256:" + "0" * 64
    with pytest.raises(LayoutAuthorityError):
        generate_global_composition_candidate(plan, bad, site, solver=NeverSolver())


def test_nonrectangular_site_and_concave_obstacles_not_bbox_substituted() -> None:
    assert rectangular_scope(((0, 0), (10, 0), (10, 10), (0, 10))) == (0, 0, 10, 10)
    with pytest.raises(LayoutAuthorityError, match="RECTANGULAR_SCOPE"):
        rectangular_scope(((0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)))


@pytest.mark.parametrize(
    "second,accepted",
    [
        ({"x": 10, "y": 0, "X": 20, "Y": 10}, True),
        ({"x": 10, "y": 10, "X": 20, "Y": 20}, False),
        ({"x": 9, "y": 0, "X": 20, "Y": 10}, False),
    ],
)
def test_exact_must_positive_shared_edge_not_corner(second: dict[str, int], accepted: bool) -> None:
    model = cp_model.CpModel()
    touch(model, {"x": 0, "y": 0, "X": 10, "Y": 10}, second, "must")
    assert (cp_model.CpSolver().solve(model) == cp_model.OPTIMAL) is accepted


def test_closed_obstacle_contact_rejected_but_room_contact_allowed() -> None:
    first = {"x": 0, "y": 0, "X": 10, "Y": 10}
    second = {"x": 10, "y": 0, "X": 20, "Y": 10}
    for closed in (False, True):
        model = cp_model.CpModel()
        disjoint(model, first, second, "touch", closed=closed)
        assert (cp_model.CpSolver().solve(model) == cp_model.OPTIMAL) is (not closed)
    assert not _overlap((0, 0, 10, 10), (10, 0, 20, 10))
    assert _overlap((0, 0, 10, 10), (10, 0, 20, 10), closed=True)


def test_rotated_footprint_and_full_turn_envelope() -> None:
    r = PlacedRectangleV1("office", Decimal(0), Decimal(0), Decimal(2), Decimal(4), 90)
    assert rectangular_scope(r.polygon_mm) == (0, 0, 4000, 2000)
    boxes = envelopes([(0, 0), (5000, 0), (5000, 5000)], 2000)
    assert boxes == [(0, -1000, 5000, 1000), (4000, 0, 6000, 5000), (4000, -1000, 6000, 1000)]
    with pytest.raises(LayoutAuthorityError):
        envelopes([(0, 0), (1, 1)], 2000)


def test_real_authorities_build_one_twelve_room_eleven_access_model() -> None:
    class ModelInspector:
        def solve(self, context: Any, handoff: Any) -> dict[str, Any]:
            model = AccessModel(context, handoff, True)
            assert len(model.rooms) == 12
            assert len(model.routes) + 1 == 11
            assert len(handoff.mandatory_interface_reservations) == 7
            assert model.m.validate() == ""
            assert len(model.m.proto.solution_hint.vars) == 0
            for room in model.rooms.values():
                # 9.15 pybind repeated fields do not implement Python negative
                # indexing; inspect the complete native domain as a real list.
                assert list(room["x"].proto.domain)[0] < list(room["x"].proto.domain)[-1]
                assert list(room["y"].proto.domain)[0] < list(room["y"].proto.domain)[-1]
            return {"solver_status": "NOT_SOLVED_MODEL_INSPECTION_ONLY"}

    plan, p1, site = _context()
    generate_global_composition_candidate(plan, p1.to_dict(), site, solver=ModelInspector())


def test_route_oracle_rejects_omitted_turn_and_false_length() -> None:
    route = dict(
        topology="CORRIDOR_MEDIATED",
        path_mm=[(0, 0), (5000, 0), (5000, 5000)],
        portal_from_center_mm=(0, 0),
        portal_to_center_mm=(5000, 5000),
        width_mm=2000,
        envelopes_mm=[(0, -1000, 5000, 1000), (4000, 0, 6000, 5000), (4000, -1000, 6000, 1000)],
        length_mm=10000,
        turn_count=1,
    )
    assert _route_geometry_errors(route) == []
    missing = dict(route, envelopes_mm=route["envelopes_mm"][:2])
    assert "INCOMPLETE_CORRIDOR_ENVELOPE" in _route_geometry_errors(missing)
    assert "ROUTE_LENGTH_OR_TURNS" in _route_geometry_errors(dict(route, length_mm=1))


def test_geometry_hash_excludes_runtime_but_detects_coordinate_change() -> None:
    first = [{"zone_code": "a", "x": "0"}, {"zone_code": "b", "x": "1"}]
    assert zone_geometry_hash(first) == zone_geometry_hash(list(reversed(first)))
    assert zone_geometry_hash(first) != zone_geometry_hash([first[0], dict(first[1], x="2")])


def test_small_cp_sat_replay_has_identical_exact_assignment() -> None:
    outcomes = []
    for _ in range(2):
        model = cp_model.CpModel()
        x = model.new_int_var(0, 10, "x")
        model.add(x == 7)
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 3
        assert solver.solve(model) == cp_model.OPTIMAL
        outcomes.append(solver.value(x))
    assert outcomes == [7, 7]


def test_native_oracle_checks_actual_application_corridors_not_solver_flags() -> None:
    from cold_storage.modules.layout.application.access_routing import route_site_placement
    from tests.unit.test_v22_p2d_access_routing import rebuilt_access_context

    captured: list[Any] = []

    class CaptureContext:
        def solve(self, context: Any, handoff: Any) -> dict[str, Any]:
            captured.append(context)
            return {"solver_status": "UNKNOWN"}

    plan, p1, site, placement, _, zones, *_rest = rebuilt_access_context()
    generate_global_composition_candidate(plan, p1.to_dict(), site, solver=CaptureContext())
    application = route_site_placement(plan, p1, site, placement, None).to_dict()
    check = validate_native_access_geometry(captured[0], zones, application)
    assert check["pass"], check
    assert check["pass_count"] == 11
    assert check["coexistence"] is True
    assert check["source"] == "ACTUAL_NATIVE_APPLICATION_CORRIDORS"
