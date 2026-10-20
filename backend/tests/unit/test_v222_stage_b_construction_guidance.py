"""Tiny SYNTHETIC models only; no real factory invocation or Owner registry."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.bootstrap import global_composition as bootstrap
from cold_storage.modules.layout.domain.adjacency import PROCESS_FLOW, ZONE_CODES
from cold_storage.modules.layout.domain.construction_diagnostics import construction_diagnostics
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
    OrToolsGlobalCompositionSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_construction_guidance import (
    StageBGuidedConstructionSolver,
    _GuidedInvocation,
    apply_construction_guidance,
)
from tests.unit.test_v222_construction_diversity import rooms
from tests.unit.test_v222_p1a_composition_authority_handoff import _context


def model():
    m = cp_model.CpModel()
    for r in ZONE_CODES:
        x = m.new_int_var(0, 20, r + "_x")
        y = m.new_int_var(0, 20, r + "_y")
        w = m.new_int_var(1, 8, r + "_physical_w")
        d = m.new_int_var(1, 8, r + "_physical_d")
        right = m.new_int_var(1, 28, r + "_right")
        top = m.new_int_var(1, 28, r + "_top")
        m.add(right == x + w)
        m.add(top == y + d)
    return m


def v(m, name):
    return next(
        m.get_int_var_from_proto_index(i) for i, p in enumerate(m.proto.variables) if p.name == name
    )


def guide(m, phase, **kwargs):
    work = []
    receipt = apply_construction_guidance(
        m,
        phase=phase,
        axis=kwargs.get("axis", "X"),
        direction=kwargs.get("direction", "POSITIVE"),
        flexible_roles=("office",),
        bands=(("raw_fruit_buffer", "primary_precooling_room"),),
        charge=lambda label, n: work.append((label, n)),
    )
    assert work and all(n > 0 for _, n in work)
    assert not receipt["formal_quality_gate"]
    assert not receipt["changes_engineering_feasible_domain"]
    assert not receipt["process_flow_validated"]
    return receipt


def solve(m):
    s = cp_model.CpSolver()
    s.parameters.num_search_workers = 1
    s.parameters.max_time_in_seconds = 2
    status = s.solve(m)
    assert status == cp_model.OPTIMAL
    return s


def test_semiperimeter_objective_balances_shape_without_rewarding_large_square():
    m = model()
    w, d = v(m, "office_physical_w"), v(m, "office_physical_d")
    area = m.new_int_var(1, 64, "synthetic_area")
    m.add_multiplication_equality(area, [w, d])
    m.add(area >= 16)
    guide(m, "ALL_ROOM_GEOMETRY_HINT")
    s = solve(m)
    assert s.value(w) == s.value(d) == 4
    assert s.objective_value == 8


@pytest.mark.parametrize(
    "phase",
    [
        "ALL_ROOM_GEOMETRY_HINT",
        "ALL_ROOM_MUST_HINT",
        "COMPOSITION_PACKAGING_HINT",
        "ALL_ROOMS_ALL_ACCESS",
    ],
)
def test_every_small_original_assignment_extends_even_if_visually_unfavorable(phase):
    for width, depth in ((1, 8), (8, 1), (4, 4), (8, 8)):
        m = model()
        m.add(v(m, "office_physical_w") == width)
        m.add(v(m, "office_physical_d") == depth)
        # Include reversed main progress and misaligned bands; neither is cut.
        for i, r in enumerate(PROCESS_FLOW):
            m.add(v(m, r + "_x") == 12 - i)
        guide(m, phase)
        solve(m)


@pytest.mark.parametrize("axis,direction", [("X", "POSITIVE"), ("Y", "NEGATIVE")])
def test_progress_is_a_direction_bound_center_proxy_not_formal_backtracking(axis, direction):
    m = model()
    for i, r in enumerate(PROCESS_FLOW):
        m.add(v(m, r + ("_x" if axis == "X" else "_y")) == i)
        m.add(v(m, r + ("_physical_w" if axis == "X" else "_physical_d")) == 1)
    receipt = guide(m, "ALL_ROOM_MUST_HINT", axis=axis, direction=direction)
    assert "NOT_BACKTRACK_COUNT" in receipt["proxy"]
    assert solve(m).objective_value == (0 if direction == "POSITIVE" else 12)


@pytest.mark.parametrize("active", [0, 1])
def test_actual_segment_length_and_inactive_routes_not_unused_coordinates(active):
    m = model()
    flag = m.new_bool_var("route0corridor")
    m.add(flag == active)
    for j in range(5):
        for suffix, number in (("lowx", 1), ("highx", 4), ("lowy", 2), ("highy", 2)):
            m.new_int_var(number, number, f"r0s{j}" + suffix)
    receipt = guide(m, "ALL_ACCESS_FRESH_HINT_ONLY")
    assert receipt["term_count"] == 1
    assert solve(m).objective_value == 15 * active


def test_missing_model_facts_and_invalid_strategy_fail_closed():
    with pytest.raises(LayoutAuthorityError, match="MODEL_FACT_MISSING"):
        guide(cp_model.CpModel(), "ALL_ROOM_GEOMETRY_HINT")
    with pytest.raises(LayoutAuthorityError, match="PHASE_UNSUPPORTED"):
        guide(model(), "fabricated")
    with pytest.raises(LayoutAuthorityError, match="ORIENTATION_INVALID"):
        guide(model(), "ALL_ROOM_MUST_HINT", axis="Z")


def test_same_input_constructs_identical_guided_proto_without_search():
    a, b = model(), model()
    assert guide(a, "COMPOSITION_PACKAGING_HINT") == guide(b, "COMPOSITION_PACKAGING_HINT")
    assert str(a.proto) == str(b.proto)


def test_stage_a_model_is_unmodified_and_inherited_run_keeps_its_resource_mechanism(monkeypatch):
    m = model()
    before = str(m.proto)
    called = []

    def run(self, context, prepared, seconds, phase):
        called.append((prepared, seconds, phase))
        assert prepared is not m and prepared.has_objective()
        return SimpleNamespace(status_name=lambda _: "UNKNOWN"), cp_model.UNKNOWN

    monkeypatch.setattr(OrToolsGlobalCompositionSolver, "_run", run)
    h = SimpleNamespace(
        process_axis=SimpleNamespace(value="X"),
        process_direction=SimpleNamespace(value="POSITIVE"),
        principal_band_intents=[],
    )
    c = SimpleNamespace(
        binding=SimpleNamespace(
            dimension_authorities={"office": {"dimension_mode": "FLEXIBLE_RECTANGLE"}}
        ),
        ledger=SimpleNamespace(charge=lambda *args: None),
    )
    guided = _GuidedInvocation(h)
    guided._run(c, m, 1.25, "ALL_ROOM_GEOMETRY_HINT")
    assert called[0][1:] == (1.25, "ALL_ROOM_GEOMETRY_HINT")
    assert str(m.proto) == before and not m.has_objective()
    assert guided.receipts[0]["solver_status"] == "UNKNOWN"
    h.principal_band_intents = [
        SimpleNamespace(
            zone_roles=("office", "changing_room"), axis_relation="PERIPHERAL_OR_CORE_FACE"
        )
    ]
    guided._run(c, m, 1.25, "COMPOSITION_PACKAGING_HINT")
    assert guided.receipts[1]["term_count"] == 0
    assert guided.receipts[1]["preference_status"] == "NOT_APPLICABLE_NO_BOUND_TERMS"
    assert str(m.proto) == before


def test_bootstrap_is_explicit_default_unchanged_and_no_quota_not_a_solve(monkeypatch):
    plan, p1, site = _context()
    captured = []
    original = bootstrap.generate_global_composition_pool

    def capture(*args, **kwargs):
        captured.append(type(kwargs["solver"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(bootstrap, "generate_global_composition_pool", capture)
    for entry in (
        bootstrap.generate_controlled_global_layout_pool,
        bootstrap.generate_guided_global_layout_pool,
    ):
        result = entry(plan, p1.to_dict(), site)
        assert result["status"] == "OWNER_POOL_EXECUTION_QUOTA_REQUIRED"
        assert result["attempts"] == []
    assert captured == [OrToolsGlobalCompositionSolver, StageBGuidedConstructionSolver]
    with pytest.raises(TypeError):
        bootstrap.generate_guided_global_layout_pool(
            plan, p1.to_dict(), site, construction_strategy="caller-invented"
        )


def test_diagnostics_do_not_confuse_attachment_reversal_and_formal_route_backtracking():
    d = construction_diagnostics(rooms("EENNWW"), {})
    assert d["adjacency_directions"] == list("EENNWW")
    assert d["adjacency_direction_changes"] == 2
    assert d["main_flow_backtrack_count"] is None
    assert d["main_flow_turn_count"] is None
    assert d["formal_main_flow_status"].startswith("UNAVAILABLE")
    assert not d["grid_numeric_gate_applied"]
    assert d["process_flow_validated"] is not True


def test_diagnostics_rotation_real_centerline_length_and_concave_outline():
    rows = rooms()
    next(r for r in rows if r["zone_code"] == "office").update(
        width_m=2, depth_m=9, rotation_deg=90
    )
    app = {
        "access_results": [
            {
                "requirement_identity": "synthetic",
                "from_ref": "main_entrance",
                "to_ref": "changing_room",
                "flow_kind": "PEOPLE",
                "status": "PASS",
                "topology": "CORRIDOR_MEDIATED",
                "route_length_m": "5",
                "centerline": [
                    {"x": 0, "y": 0},
                    {"x": 0, "y": 0},
                    {"x": 3, "y": 0},
                    {"x": 3, "y": 2},
                ],
            }
        ],
        "building_footprint": {
            "footprint": {
                "points": [
                    {"x": x, "y": y} for x, y in [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
                ]
            }
        },
    }
    original = deepcopy((rows, app))
    d = construction_diagnostics(rows, app)
    assert (rows, app) == original
    assert d["room_shapes"]["office"]["physical_width_m"] == "9"
    assert d["room_shapes"]["office"]["aspect_ratio"] == "4.5"
    assert d["actual_access_route_facts"][0]["measured_centerline_length_m"] == "5"
    assert d["actual_access_route_facts"][0]["measured_heading_changes"] == 1
    assert d["footprint"]["area_m2"] == "3"
    assert d["footprint"]["reflex_corner_count"] == 1


def test_missing_shared_edge_is_unavailable_not_synthetic_direction_count():
    rows = rooms()
    next(r for r in rows if r["zone_code"] == "sorting_packaging_room")["y"] += 100
    d = construction_diagnostics(rows, {})
    assert d["adjacency_direction_changes"] is None
    assert d["adjacent_opposite_directions"] is None


def test_real_model_variable_contract_all_phases_without_any_native_search(monkeypatch):
    from cold_storage.modules.layout.application.global_composition_solver import (
        generate_global_composition_candidate,
    )
    from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel

    def forbidden(*args, **kwargs):
        raise AssertionError("Model-only test must never start native search")

    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)

    class ModelOnlyProbe:
        def solve(self, context, handoff):
            base = AccessModel(context, handoff)
            for phase in (
                "ALL_ROOM_GEOMETRY_HINT",
                "ALL_ROOM_MUST_HINT",
                "COMPOSITION_PACKAGING_HINT",
                "ALL_ACCESS_FRESH_HINT_ONLY",
                "ALL_ROOMS_ALL_ACCESS",
            ):
                clone = base.m.clone()
                apply_construction_guidance(
                    clone,
                    phase=phase,
                    axis=handoff.process_axis.value,
                    direction=handoff.process_direction.value,
                    flexible_roles=tuple(
                        r
                        for r, a in context.binding.dimension_authorities.items()
                        if a["dimension_mode"] == "FLEXIBLE_RECTANGLE"
                    ),
                    bands=tuple(
                        b.zone_roles
                        for b in handoff.principal_band_intents
                        if b.axis_relation == "ALONG_PROCESS_AXIS"
                    ),
                    charge=context.ledger.charge,
                )
                assert not clone.validate()
                assert not base.m.has_objective()
            return {"solver_status": "UNKNOWN", "candidate_generated": False}

    plan, p1, site = _context()
    result = generate_global_composition_candidate(
        plan, p1.to_dict(), site, solver=ModelOnlyProbe()
    )
    assert not result["stage_a_engineering_accepted"]
    assert result["proposal"]["solver_status"] == "UNKNOWN"


def test_six_handoffs_final_functional_shape_preserves_original_model_without_search(monkeypatch):
    # This file uses the existing process-lifetime resource-test isolation.
    from cold_storage.modules.layout.application import global_composition_solver as generation
    from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel
    from cold_storage.modules.layout.infrastructure.stage_b_construction_guidance import (
        FUNCTIONAL_SHAPE_ROLES,
        apply_functional_shape_guidance,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Real factory search is not authorized")

    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)

    class Inspect:
        def solve(self, context, handoff):
            final = AccessModel(context, handoff, True)
            before = str(final.m.proto)
            receipt = apply_functional_shape_guidance(final, context)
            assert receipt["target_roles"] == list(FUNCTIONAL_SHAPE_ROLES)
            assert final.m.validate() == ""
            final.m.clear_objective()
            assert str(final.m.proto) == before
            return {"solver_status": "MODEL_INSPECTION_ONLY"}

    plan, p1, site = _context()
    handoffs = generation.build_structural_compositions(plan, p1.to_dict(), site).placement_handoffs
    assert len(handoffs) == 6
    for handoff in handoffs:
        result = generation.generate_global_composition_candidate(
            plan,
            p1.to_dict(),
            site,
            solver=Inspect(),
            composition_identity=handoff.composition_identity,
        )
        assert result["proposal"]["solver_status"] == "MODEL_INSPECTION_ONLY"
