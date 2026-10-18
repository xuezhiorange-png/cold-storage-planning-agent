"""Synthetic native enumeration, not an Owner-bound factory execution."""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.bootstrap.global_composition import generate_multi_solution_global_layout_pool
from cold_storage.modules.layout.application import global_composition_enumeration as enumeration
from cold_storage.modules.layout.application import global_composition_solver as application
from cold_storage.modules.layout.application import global_multi_solution_pool as pool
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.construction_diversity import construction_diversity
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.infrastructure import global_cp_sat_solver as native
from cold_storage.modules.layout.infrastructure import stage_b_fair_search as fair
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel, GlobalModel
from cold_storage.modules.layout.infrastructure.stage_b_multi_solution import (
    StageBMultiSolutionSolver,
)
from tests.unit.test_v222_construction_diversity import rooms
from tests.unit.test_v222_global_composition_pool import SyntheticLease, setup_ports
from tests.unit.test_v222_p1a_composition_authority_handoff import _context
from tests.unit.test_v222_stage_b_pool_execution import admit, begin, registry


class EnumerationLease(SyntheticLease):
    def __init__(self):
        super().__init__()
        self.begins = []
        self.events = []

    def begin(self, sources):
        self.begins.append(sources)

    def record_enumeration(self, sources, event):
        self.events.append(deepcopy(event))


def test_no_grant_or_stage_a_lease_cannot_start_enumeration(monkeypatch):
    plan, p1, site = _context()
    monkeypatch.setattr(
        native.OrToolsGlobalCompositionSolver,
        "iter_solutions",
        lambda *_: pytest.fail("unauthorized"),
    )
    for ledger in (None, StageALedger(execution_authorization=SyntheticLease())):
        result = generate_multi_solution_global_layout_pool(
            plan, p1.to_dict(), site, execution_ledger=ledger
        )
        assert result["construction_candidate_count"] == 0
        assert "QUOTA_REQUIRED" in result["status"]


class TinyModel:
    """Two connected square-room organizations, real CP-SAT variables/cuts."""

    created = []

    @staticmethod
    def layouts():
        layouts = [rooms(p) for p in ("EEEEEE", "EEENNN")]
        for layout in layouts:
            # Connect the five non-process rooms without enclosing any void.
            support = [
                r
                for r in layout
                if r["zone_code"] not in {z["zone_code"] for z in layout if z["y"] >= 0}
            ]
            for row, pos in zip(support, ((0, 1), (1, 1), (2, 1), (0, 2), (1, 2)), strict=True):
                row.update(x=pos[0], y=pos[1])
        return layouts

    def __init__(self, *args):
        self.m = cp_model.CpModel()
        self.rooms = {}
        layouts = self.layouts()
        choice = self.m.new_bool_var("organization")
        for a, b in zip(*layouts, strict=True):
            code = a["zone_code"]
            x, y = (self.m.new_int_var(-10000, 10000, code + k) for k in ("x", "y"))
            self.m.add_allowed_assignments(
                [choice, x, y],
                [(i, int(r["x"] * 1000), int(r["y"] * 1000)) for i, r in enumerate((a, b))],
            )
            w = self.m.new_int_var(1000, 1000, code + "w")
            d = self.m.new_int_var(1000, 1000, code + "d")
            rot = self.m.new_int_var(0, 0, code + "rot")
            self.rooms[code] = dict(x=x, y=y, nw=w, nd=d, w=w, d=d, rot=rot)
        witness = self.m.new_int_var(0, 1, "portal-position")
        self.interfaces = [{"active": self.m.new_constant(1), "center": witness}]
        self.routes = []
        self.geometry_constraint_count = self.must_constraint_count = len(self.m.proto.constraints)
        self.created.append(self)

    def export(self, solver):
        return {
            k: PlacedRectangleV1(
                k,
                Decimal(solver.value(r["x"])) / 1000,
                Decimal(solver.value(r["y"])) / 1000,
                Decimal(1),
                Decimal(1),
                0,
            )
            for k, r in self.rooms.items()
        }, {}

    def export_routes(self, *args):
        return []


def native_setup(monkeypatch):
    TinyModel.created = []
    monkeypatch.setattr(native, "GlobalModel", TinyModel)
    monkeypatch.setattr(native, "AccessModel", TinyModel)
    # Synthetic dimension authority is intentionally not the real factory's.
    monkeypatch.setattr(
        native, "validate_global_geometry", lambda *_: {"pass": True, "synthetic_test_only": True}
    )
    monkeypatch.setattr(native, "validate_building_footprint_against_site", lambda *_: None)
    lease = EnumerationLease()
    ledger = StageALedger(solver_history_verified=True, execution_authorization=lease)
    return SimpleNamespace(ledger=ledger, must=tuple(range(7)), site=None), lease


def test_one_preparation_two_actual_native_organizations_and_no_extra_witnesses(monkeypatch):
    context, lease = native_setup(monkeypatch)
    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        context, None, event_sink=lease.events.append
    )
    first = next(stream)
    second = stream.send("ENGINEERING_ACCEPTED")
    terminal = stream.send("ENGINEERING_ACCEPTED")
    assert first["model_witness_topology"]["valid"]
    assert second["model_witness_topology"]["valid"]
    a, b = (construction_diversity(r["zones"]) for r in (first, second))
    assert a["symmetry_invariant_geometry_hash"] != b["symmetry_invariant_geometry_hash"]
    assert a["major_organization_hash"] != b["major_organization_hash"]
    assert terminal["solver_status"] == "INFEASIBLE"
    assert terminal["global_infeasibility_claimed"] is False
    assert len(TinyModel.created) == 3  # Global + hint Access + ONE final Access.
    phases = [a["phase"] for a in context.ledger.attempts]
    assert phases.count("ALL_ROOMS_ALL_ACCESS") == 3
    assert len(phases) == 7
    assert context.ledger.checked_solutions == 2
    assert len([e for e in lease.events if e["kind"] == "ACCEPTED_GEOMETRY_ENUMERATION_CUT"]) == 2
    assert context.ledger.solver_wall > 0
    stream.close()


def test_rejected_physical_witness_preserves_other_portal_for_same_rooms(monkeypatch):
    context, lease = native_setup(monkeypatch)
    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        context, None, event_sink=lease.events.append
    )
    first = next(stream)
    # Force the next assignment to the same geometry, leaving its other Portal free.
    model = TinyModel.created[-1]
    for row in first["zones"]:
        for k in ("x", "y"):
            model.m.add(model.rooms[row["zone_code"]][k] == int(Decimal(row[k]) * 1000))
    second = stream.send("EXAMINED_WITNESS")
    assert first["zones"] == second["zones"]
    cut = next(e for e in lease.events if e["kind"] == "EXAMINED_WITNESS_ENUMERATION_CUT")
    assert "portal-position" in cut["variable_names"]
    assert cut["engineering_infeasibility_claimed"] is False
    stream.close()


def test_topology_cut_is_exact_witness_and_does_not_delete_valid_alternative(monkeypatch):
    context, lease = native_setup(monkeypatch)
    original = native.inspect_rectangular_union
    calls = []

    def reject_once(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        return (
            {**result, "valid": False, "synthetic_rejection": True} if len(calls) == 1 else result
        )

    monkeypatch.setattr(native, "inspect_rectangular_union", reject_once)
    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        context, None, event_sink=lease.events.append
    )
    accepted = next(stream)
    assert accepted["model_witness_topology"]["valid"]
    assert context.ledger.checked_solutions == 2
    cut = next(e for e in lease.events if e["kind"] == "TOPOLOGY_REJECTED_WITNESS_CUT")
    assert "portal-position" in cut["variable_names"]
    assert cut["certificate"]["synthetic_rejection"]
    stream.close()


def test_stage_a_takes_first_only_without_continuation_cut(monkeypatch):
    context, _ = native_setup(monkeypatch)
    result = native.OrToolsGlobalCompositionSolver().solve(context, None)
    assert result["zones"]
    assert len(context.ledger.attempts) == 5
    assert "STAGE_B_PHYSICAL_ENUMERATION_CUT" not in context.ledger.resource_events


class InfeasibleBase(TinyModel):
    """The first two hint slices are SAT; the complete base is genuinely UNSAT."""

    def __init__(self, *args):
        super().__init__(*args)
        self.m.add_bool_or([])


def test_proven_complete_base_infeasible_skips_access_and_retains_native_proof(monkeypatch):
    context, lease = native_setup(monkeypatch)
    monkeypatch.setattr(native, "GlobalModel", InfeasibleBase)

    def forbidden_access(*args):
        pytest.fail("A supermodel of the proven UNSAT base must not be constructed")

    monkeypatch.setattr(native, "AccessModel", forbidden_access)
    proposals = list(
        native.OrToolsGlobalCompositionSolver().iter_solutions(
            context, None, event_sink=lease.events.append, propagate_base_infeasible=True
        )
    )
    assert len(proposals) == 1
    result = proposals[0]
    assert result["solver_status"] == "INFEASIBLE"
    assert result["base_model_proof"] == context.ledger.attempts[-1]
    assert result["base_model_proof"]["phase"] == "COMPOSITION_PACKAGING_HINT"
    assert "status: INFEASIBLE" in result["base_model_proof"]["response_stats"]
    assert result["skipped_phases"] == ["ALL_ACCESS_FRESH_HINT_ONLY", "ALL_ROOMS_ALL_ACCESS"]
    assert result["candidate_generated"] is False
    assert result["global_infeasibility_claimed"] is False
    assert "zones" not in result
    assert len(context.ledger.attempts) == 3
    assert context.ledger.checked_solutions == 0
    assert context.ledger.solver_wall > 0
    assert len(lease.events) == 1
    assert lease.events[0]["kind"] == "PROVEN_BASE_INFEASIBLE_SHORT_CIRCUIT"
    assert lease.events[0]["proposal"] == result


def test_stage_a_default_does_not_propagate_base_infeasibility(monkeypatch):
    context, lease = native_setup(monkeypatch)
    monkeypatch.setattr(native, "GlobalModel", InfeasibleBase)
    monkeypatch.setattr(native, "AccessModel", InfeasibleBase)
    result = native.OrToolsGlobalCompositionSolver().solve(context, None)
    assert result["solver_status"] == "INFEASIBLE"
    assert len(context.ledger.attempts) == 5
    assert context.ledger.attempts[-1]["phase"] == "ALL_ROOMS_ALL_ACCESS"
    assert "base_model_proof" not in result
    assert not lease.events


@pytest.mark.parametrize("base_status", [cp_model.FEASIBLE, cp_model.OPTIMAL, cp_model.UNKNOWN])
def test_unproven_or_feasible_base_continues_original_access_flow(monkeypatch, base_status):
    context, lease = native_setup(monkeypatch)
    original = native.OrToolsGlobalCompositionSolver._run

    def base_response(self, ctx, model, seconds, phase):
        # Exercise actual bounded native accounting. The SAT witness is reused
        # only to test the response-status branch, never as engineering evidence.
        solver, status = original(self, ctx, model, seconds, phase)
        return solver, base_status if phase == "COMPOSITION_PACKAGING_HINT" else status

    monkeypatch.setattr(native.OrToolsGlobalCompositionSolver, "_run", base_response)
    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        context, None, event_sink=lease.events.append, propagate_base_infeasible=True
    )
    result = next(stream)
    stream.close()
    assert result["zones"]
    assert len(TinyModel.created) == 3
    assert [a["phase"] for a in context.ledger.attempts][-2:] == [
        "ALL_ACCESS_FRESH_HINT_ONLY",
        "ALL_ROOMS_ALL_ACCESS",
    ]
    assert not any(e["kind"] == "PROVEN_BASE_INFEASIBLE_SHORT_CIRCUIT" for e in lease.events)


def test_model_invalid_is_not_promoted_to_infeasible(monkeypatch):
    context, lease = native_setup(monkeypatch)
    original = native.OrToolsGlobalCompositionSolver._run

    def invalid_complete_base(self, ctx, model, seconds, phase):
        if phase == "COMPOSITION_PACKAGING_HINT":
            # MODEL_INVALID is returned by CP-SAT itself, not relabelled UNSAT.
            model.proto.variables[0].domain.clear()
            solver = cp_model.CpSolver()
            status = solver.solve(model)
            assert status == cp_model.MODEL_INVALID
            return solver, status
        return original(self, ctx, model, seconds, phase)

    monkeypatch.setattr(native.OrToolsGlobalCompositionSolver, "_run", invalid_complete_base)
    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        context, None, event_sink=lease.events.append, propagate_base_infeasible=True
    )
    result = next(stream)
    stream.close()
    assert result["zones"]  # Original behavior; invalid hint never proves UNSAT.
    assert not any(e["kind"] == "PROVEN_BASE_INFEASIBLE_SHORT_CIRCUIT" for e in lease.events)


@pytest.mark.parametrize("phase", ["ALL_ROOM_GEOMETRY_HINT", "ALL_ROOM_MUST_HINT"])
def test_partial_hint_infeasible_does_not_enter_complete_base_short_circuit(monkeypatch, phase):
    context, lease = native_setup(monkeypatch)
    original = native.OrToolsGlobalCompositionSolver._run

    def partial_response(self, ctx, model, seconds, current_phase):
        solver, status = original(self, ctx, model, seconds, current_phase)
        return solver, cp_model.INFEASIBLE if current_phase == phase else status

    monkeypatch.setattr(native.OrToolsGlobalCompositionSolver, "_run", partial_response)
    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        context, None, event_sink=lease.events.append, propagate_base_infeasible=True
    )
    result = next(stream)
    stream.close()
    assert result["zones"]
    assert len(context.ledger.attempts) == 5
    assert not any(e["kind"] == "PROVEN_BASE_INFEASIBLE_SHORT_CIRCUIT" for e in lease.events)


def test_post_native_guard_failure_prevents_infeasible_short_circuit(monkeypatch):
    context, lease = native_setup(monkeypatch)
    monkeypatch.setattr(native, "GlobalModel", InfeasibleBase)
    original = context.ledger.guard
    error = LayoutAuthorityError("STAGE_A_RESOURCE_LIMIT")

    def post_native_guard():
        original()
        if context.ledger.attempts and context.ledger.attempts[-1]["phase"] == (
            "COMPOSITION_PACKAGING_HINT"
        ):
            raise error

    monkeypatch.setattr(context.ledger, "guard", post_native_guard)
    with pytest.raises(LayoutAuthorityError) as caught:
        next(
            native.OrToolsGlobalCompositionSolver().iter_solutions(
                context, None, event_sink=lease.events.append, propagate_base_infeasible=True
            )
        )
    assert caught.value is error
    assert context.ledger.attempts[-1]["solver_status"] == "INFEASIBLE"
    assert not lease.events


@pytest.mark.parametrize(
    "error",
    [
        LayoutAuthorityError("STAGE_A_RESOURCE_LIMIT"),
        LayoutAuthorityError("STAGE_A_REQUIREMENT_HOST_LIMIT"),
        LayoutAuthorityError(fair.SHARE_STOP),
        RuntimeError("synthetic native interruption"),
    ],
)
def test_resource_or_native_exception_is_not_converted_to_infeasible(monkeypatch, error):
    context, lease = native_setup(monkeypatch)
    original = native.OrToolsGlobalCompositionSolver._run

    def interrupt(self, ctx, model, seconds, phase):
        if phase == "COMPOSITION_PACKAGING_HINT":
            raise error
        return original(self, ctx, model, seconds, phase)

    monkeypatch.setattr(native.OrToolsGlobalCompositionSolver, "_run", interrupt)
    with pytest.raises(type(error)) as caught:
        next(
            native.OrToolsGlobalCompositionSolver().iter_solutions(
                context, None, event_sink=lease.events.append, propagate_base_infeasible=True
            )
        )
    assert caught.value is error
    assert len(context.ledger.attempts) == 2
    assert not lease.events


@pytest.mark.parametrize("fair_entry", [False, True])
def test_only_stage_b_streaming_ports_opt_in(monkeypatch, fair_entry):
    context, lease = native_setup(monkeypatch)
    context.binding = SimpleNamespace(
        canonical_zone_plan_hash="synthetic-plan",
        p1_handoff_hash="synthetic-p1",
        site_geometry_hash="synthetic-site",
    )
    handoff = SimpleNamespace(source_composition_hash="synthetic-composition")
    calls = []

    def capture(self, *args, **kwargs):
        calls.append(kwargs)
        yield {"solver_status": "UNKNOWN"}

    monkeypatch.setattr(native.OrToolsGlobalCompositionSolver, "iter_solutions", capture)
    port = fair.StageBFairSearchSolver() if fair_entry else StageBMultiSolutionSolver()
    if fair_entry:
        port.start_handoff(context.ledger, 6)
    assert list(port.solutions(context, handoff)) == [{"solver_status": "UNKNOWN"}]
    assert len(calls) == 1 and calls[0]["propagate_base_infeasible"] is True


def test_actual_access_model_keeps_complete_base_constraint_prefix_without_solving():
    # Actual production model builders and bound synthetic server context, not
    # TinyModel. Inspection only: no native factory solve and no Owner grant.
    class InspectSuperset:
        def solve(self, context, handoff):
            base = GlobalModel(context, handoff)
            extension = AccessModel(context, handoff, True)
            nvars = len(base.m.proto.variables)
            ncons = len(base.m.proto.constraints)
            assert len(extension.m.proto.variables) > nvars
            assert len(extension.m.proto.constraints) > ncons
            assert all(
                str(v) == str(extension.m.proto.variables[i])
                for i, v in enumerate(base.m.proto.variables)
            )
            assert all(
                str(c) == str(extension.m.proto.constraints[i])
                for i, c in enumerate(base.m.proto.constraints)
            )
            return {"solver_status": "MODEL_INSPECTION_ONLY_NOT_SOLVED"}

    plan, p1, site = _context()
    handoffs = application.build_structural_compositions(
        plan, p1.to_dict(), site
    ).placement_handoffs
    assert len(handoffs) == 6
    for handoff in handoffs:
        result = application.generate_global_composition_candidate(
            plan,
            p1.to_dict(),
            site,
            solver=InspectSuperset(),
            composition_identity=handoff.composition_identity,
        )
        assert result["proposal"]["solver_status"] == "MODEL_INSPECTION_ONLY_NOT_SOLVED"


def test_unknown_creates_no_cut_and_keeps_accounting(monkeypatch):
    context, lease = native_setup(monkeypatch)
    original = native.OrToolsGlobalCompositionSolver._run

    def unknown(self, ctx, model, seconds, phase):
        if phase != "ALL_ROOMS_ALL_ACCESS":
            return original(self, ctx, model, seconds, phase)
        return original(self, ctx, model, 1e-9, phase)

    monkeypatch.setattr(native.OrToolsGlobalCompositionSolver, "_run", unknown)
    results = list(
        native.OrToolsGlobalCompositionSolver().iter_solutions(
            context, None, event_sink=lease.events.append
        )
    )
    assert len(results) == 1 and results[0]["solver_status"] == "UNKNOWN"
    assert not any("CUT" in e["kind"] for e in lease.events)
    assert len(context.ledger.attempts) == 5
    assert context.ledger.attempts[-1]["solver_status"] == "UNKNOWN"


def test_durable_enumeration_does_not_begin_again_or_refresh_budget(tmp_path):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = "hash-0"
    with pytest.raises(LayoutAuthorityError):
        lease.record_enumeration(sources, {"kind": "NOT_ACTIVE"})
    begin(lease, binding, 0)
    for i in range(2):
        ledger.charge("STAGE_B_CANDIDATE_VALIDATION", 1)
        lease.record_enumeration(sources, {"kind": "VALIDATION_RESULT", "index": i})
    assert lease.record["cursor"] == 1
    assert lease.totals()["candidate_validation_calls"] == 2
    assert len(lease.record["enumeration_events"]) == 2
    with pytest.raises(LayoutAuthorityError):
        lease.record_enumeration({**sources, "composition_hash": "hash-1"}, {})
    ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
    with pytest.raises(LayoutAuthorityError):
        lease.record_enumeration(sources, {})
    lease.finish_pool()


def test_one_handoff_pool_continues_and_rejects_duplicates_and_failed_engineering(monkeypatch):
    counts = []

    def candidates(*args, **kwargs):
        counts.append(kwargs["composition_identity"])
        for i, path in enumerate(("EEEEEE", "EEEEEE", "EEENNN", "EENNWW", "ENENEN", "EEEENN")):
            body = original(*args, **kwargs)
            body["proposal"]["zones"] = rooms(path)
            if i == 3:
                body["native_independent_validation"]["pass"] = False
            body["canonical_result_hash"] = canonical_hash(
                {k: v for k, v in body.items() if k != "canonical_result_hash"}
            )
            yield body

    # Each original synthetic port call uses an outcome; enough for all 6 handoffs.
    plan, p1, site, ledger, _, _ = setup_ports(monkeypatch, ["EEEEEE"] * 36)
    ledger.execution_authorization = EnumerationLease()
    import cold_storage.modules.layout.application.global_composition_pool as original_pool

    original = original_pool.generate_global_composition_candidate
    monkeypatch.setattr(pool, "generate_global_composition_candidates", candidates)
    result = pool.generate_multi_solution_pool(plan, p1, site, solver=None, execution_ledger=ledger)
    assert result["construction_candidate_count"] == 4
    assert len(counts) == 6
    assert result["major_structural_family_count"] == 3
    statuses = [a["status"] for a in result["attempts"]]
    assert "DUPLICATE_GEOMETRY_NOT_COUNTED" in statuses
    assert "ENGINEERING_INCOMPLETE_NOT_COUNTED" in statuses
    assert result["p2d_full_pass_count"] == 0


def test_application_binds_and_begins_once_validates_each_proposal(monkeypatch):
    plan, p1, site = _context()
    lease = EnumerationLease()
    ledger = StageALedger(solver_history_verified=True, execution_authorization=lease)
    validated = []

    def oracle(plan, p1, site, context, handoff, proposal):
        validated.append(proposal["synthetic_sequence"])
        return dict(
            proposal=proposal,
            stage_a_engineering_accepted=True,
            independent_validation={"pass": True},
            native_independent_validation={"pass": True, "coexistence": True},
            engineering_validation={
                "building_footprint": {"synthetic": True},
                "access_results": [
                    {
                        "requirement_identity": r["identity"],
                        "flow_kind": r["flow_kind"],
                        "status": "PASS",
                    }
                    for r in context.binding.access_requirements
                    if r["flow_kind"] != "TRUCK"
                ],
            },
            source_zone_plan_hash=context.binding.canonical_zone_plan_hash,
            source_p1_handoff_hash=context.binding.p1_handoff_hash,
            source_site_geometry_hash=context.binding.site_geometry_hash,
            source_composition_hash=handoff.source_composition_hash,
        )

    monkeypatch.setattr(application, "validate_generated_global_proposal", oracle)
    monkeypatch.setattr(enumeration, "validate_generated_global_proposal", oracle)
    feedbacks = []

    class Port:
        def solutions(self, *args):
            for i in range(2):
                feedbacks.append((yield {"zones": ["synthetic-only"], "synthetic_sequence": i}))

    h = application.build_structural_compositions(plan, p1.to_dict(), site).placement_handoffs[0]
    results = list(
        enumeration.generate_global_composition_candidates(
            plan,
            p1.to_dict(),
            site,
            solver=Port(),
            composition_identity=h.composition_identity,
            execution_ledger=ledger,
        )
    )
    assert len(lease.begins) == 1
    assert validated == [0, 1]
    assert feedbacks == ["ENGINEERING_ACCEPTED", "ENGINEERING_ACCEPTED"]
    assert ledger.resource_events["STAGE_B_CANDIDATE_VALIDATION"] == 2
    assert [r["proposal"]["synthetic_sequence"] for r in results] == [0, 1]


def test_real_hole_certificate_cut_then_valid_concave_union(monkeypatch):
    context, lease = native_setup(monkeypatch)

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
            opened = deepcopy(hole)
            opened[5].update(x=3, y=0)  # Actual open notch, not a filled void.
            return [hole, opened]

    monkeypatch.setattr(native, "GlobalModel", HoleModel)
    monkeypatch.setattr(native, "AccessModel", HoleModel)
    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        context, None, event_sink=lease.events.append
    )
    result = next(stream)
    assert result["model_witness_topology"]["valid"]
    cuts = [e for e in lease.events if e["kind"] == "TOPOLOGY_REJECTED_WITNESS_CUT"]
    assert cuts
    assert all(e["certificate"]["hole_count"] == 1 for e in cuts)
    assert all("portal-position" in e["variable_names"] for e in cuts)
    stream.close()


def test_native_enumeration_deterministic_geometry_and_cut_values(monkeypatch):
    snapshots = []
    for _ in range(2):
        context, lease = native_setup(monkeypatch)
        stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
            context, None, event_sink=lease.events.append
        )
        results = [next(stream), stream.send("ENGINEERING_ACCEPTED")]
        snapshots.append(
            ([r["zones"] for r in results], [e for e in lease.events if "CUT" in e["kind"]])
        )
        stream.close()
    assert snapshots[0] == snapshots[1]


def test_interruption_after_first_keeps_candidate_and_never_refills(monkeypatch):
    context, lease = native_setup(monkeypatch)
    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        context, None, event_sink=lease.events.append
    )
    first = next(stream)
    work = context.ledger.model_work
    context.ledger.model_work = 1_200_001
    with pytest.raises(LayoutAuthorityError, match="STAGE_A_RESOURCE_LIMIT"):
        stream.send("ENGINEERING_ACCEPTED")
    assert first["zones"]
    assert context.ledger.model_work > work
    assert len(context.ledger.attempts) == 5
    stream.close()


def test_enumeration_event_counter_rollback_and_unknown_history_denied(tmp_path):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = "hash-0"
    ledger.charge("STAGE_B_CANDIDATE_VALIDATION", 1)
    lease.record_enumeration(sources, {"kind": "VALIDATION_RESULT"})
    ledger.resource_events["STAGE_B_CANDIDATE_VALIDATION"] = 0
    with pytest.raises(LayoutAuthorityError, match="ROLLBACK"):
        lease.record_enumeration(sources, {})
    ledger.resource_events["STAGE_B_CANDIDATE_VALIDATION"] = 1
    ledger.native_solver_active = True
    ledger.checkpoint("CP_SAT_STARTED")
    ledger.solver_history_verified = False
    with pytest.raises(LayoutAuthorityError):
        lease.record_enumeration(sources, {})
    lease.finish_pool()


@pytest.mark.parametrize(
    "outcome", ["UNKNOWN", "BOUNDED_TOPOLOGY_REFINEMENT_LIMIT", "HOST_INTERRUPTED", "BAD_SOURCE"]
)
def test_pool_terminal_status_and_source_failure_never_count_or_refill(monkeypatch, outcome):
    plan, p1, site, ledger, _, _ = setup_ports(monkeypatch, ["EEEEEE"] * 6)
    ledger.execution_authorization = EnumerationLease()
    from cold_storage.modules.layout.application import global_composition_pool as original_pool

    generate = original_pool.generate_global_composition_candidate
    calls = []

    def candidates(*args, **kwargs):
        calls.append(kwargs["composition_identity"])
        body = generate(*args, **kwargs)
        if outcome == "BAD_SOURCE":
            body["source_zone_plan_hash"] = "forged"
        elif outcome == "HOST_INTERRUPTED":
            body["engineering_validation"]["access_results"][0]["status"] = "RESOURCE_INTERRUPTED"
        else:
            body["proposal"] = {"solver_status": outcome}
            body["stage_a_engineering_accepted"] = False
        body["canonical_result_hash"] = canonical_hash(
            {k: v for k, v in body.items() if k != "canonical_result_hash"}
        )
        yield body

    monkeypatch.setattr(pool, "generate_global_composition_candidates", candidates)
    result = pool.generate_multi_solution_pool(plan, p1, site, solver=None, execution_ledger=ledger)
    assert result["construction_candidate_count"] == 0
    assert result["project_infeasible_proven"] is False
    assert len(calls) == (6 if outcome == "UNKNOWN" else 1)
    if outcome == "UNKNOWN":
        assert all(a["status"] == "SEARCH_UNKNOWN_NOT_ACCEPTED" for a in result["attempts"])
