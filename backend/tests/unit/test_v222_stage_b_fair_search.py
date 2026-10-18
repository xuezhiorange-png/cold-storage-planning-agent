"""Synthetic policy/cut tests only; no real Owner grant or factory execution."""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.bootstrap.global_composition import (
    generate_fair_multi_solution_global_layout_pool,
)
from cold_storage.modules.layout.application import global_multi_solution_pool as pool
from cold_storage.modules.layout.application.stage_b_search_policy import POLICY_HASH, schedule_hash
from cold_storage.modules.layout.domain.adjacency import PROCESS_FLOW
from cold_storage.modules.layout.domain.construction_branch_diversity import (
    construction_branch_diversity,
)
from cold_storage.modules.layout.domain.construction_diversity import physical_boxes
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
from cold_storage.modules.layout.infrastructure import global_cp_sat_solver as native
from cold_storage.modules.layout.infrastructure import stage_b_fair_search as fair
from tests.unit.test_v222_construction_diversity import rooms
from tests.unit.test_v222_global_composition_pool import setup_ports
from tests.unit.test_v222_p1a_composition_authority_handoff import _context
from tests.unit.test_v222_stage_b_multi_solution import EnumerationLease, TinyModel, native_setup
from tests.unit.test_v222_stage_b_pool_execution import registry


def branch_case(north=False):
    zones = rooms("EEENNN")
    sorting = physical_boxes(zones)["sorting_packaging_room"]
    x, y = sorting[0] / 1000, sorting[1] / 1000
    changing = next(z for z in zones if z["zone_code"] == "changing_room")
    changing.update(x=x, y=y + 1 if north else y - 1)

    def portal(ax, ay, bx, by):
        return {
            "segment": {
                "start": dict(x=f"{ax:.3f}", y=f"{ay:.3f}"),
                "end": dict(x=f"{bx:.3f}", y=f"{by:.3f}"),
            }
        }

    joint = portal(x + 0.2, y + 1 if north else y, x + 0.8, y + 1 if north else y)
    entrance = portal(x, changing["y"] + 0.2, x, changing["y"] + 0.8)
    rows = [
        dict(
            from_ref="main_entrance",
            to_ref="changing_room",
            status="PASS",
            topology="CORRIDOR_MEDIATED",
            portal_to=entrance,
        ),
        dict(
            from_ref="changing_room",
            to_ref="sorting_packaging_room",
            status="PASS",
            topology="DIRECT_SHARED_EDGE",
            portal_from=deepcopy(joint),
            portal_to=deepcopy(joint),
        ),
    ]
    return zones, rows


def test_meaningful_branch_and_major_family_are_independent():
    a, b = [construction_branch_diversity(*branch_case(n)) for n in (False, True)]
    assert a["countable"] and b["countable"]
    assert a["major_family_hash"] == b["major_family_hash"]
    assert a["meaningful_construction_hash"] != b["meaningful_construction_hash"]
    assert a["legacy"]["major_organization_hash"] == b["legacy"]["major_organization_hash"]


@pytest.mark.parametrize(
    "swap,sx,sy", [(a, b, c) for a in (False, True) for b in (-1, 1) for c in (-1, 1)]
)
def test_joint_symmetry_translation_and_portal_microshift_do_not_count(swap, sx, sy):
    zones, rows = branch_case()
    before = construction_branch_diversity(zones, rows)
    boxes = physical_boxes(zones)

    def transform(x, y):
        return (sx * y + 20, sy * x + 30) if swap else (sx * x + 20, sy * y + 30)

    for row in zones:
        x, y, r, t = [v / 1000 for v in boxes[row["zone_code"]]]
        points = [transform(x, y), transform(r, t)]
        row.update(
            x=min(p[0] for p in points),
            y=min(p[1] for p in points),
            width_m=abs(points[1][0] - points[0][0]),
            depth_m=abs(points[1][1] - points[0][1]),
            rotation_deg=0,
        )
    for row in rows:
        for key in ("portal_from", "portal_to"):
            if key not in row:
                continue
            for p in row[key]["segment"].values():
                # Decimal arithmetic avoids introducing non-mm floats.
                x, y = transform(Decimal(str(p["x"])), Decimal(str(p["y"])))
                p.update(x=str(x), y=str(y))
    after = construction_branch_diversity(zones, rows)
    assert after["meaningful_construction_hash"] == before["meaningful_construction_hash"]
    original_zones, original_rows = branch_case()
    point = original_rows[0]["portal_to"]["segment"]["start"]
    point["y"] = str(Decimal(point["y"]) + Decimal("0.001"))
    assert (
        construction_branch_diversity(original_zones, original_rows)["meaningful_construction_hash"]
        == before["meaningful_construction_hash"]
    )


@pytest.mark.parametrize("defect", ["missing", "failed", "forged_face"])
def test_incomplete_branch_abstains(defect):
    zones, rows = branch_case()
    if defect == "missing":
        rows.pop()
    elif defect == "failed":
        rows[0]["status"] = "FAIL"
    else:
        rows[1]["portal_to"]["segment"]["start"]["y"] = "0.01"
    assert not construction_branch_diversity(zones, rows)["countable"]


def test_union_cut_removes_redundant_direct_portal_but_keeps_path_filling_hole():
    m = cp_model.CpModel()
    room = {k: m.new_constant(v) for k, v in dict(x=0, y=0, w=1, d=1).items()}
    corridor = m.new_bool_var("corridor")
    direct_center = m.new_int_var(0, 1, "direct_center")
    model = SimpleNamespace(
        m=m,
        rooms={"synthetic": room},
        interfaces=[],
        routes=[
            dict(
                corridor=corridor,
                points=[(m.new_constant(1), m.new_constant(1))],
                direct=[dict(active=corridor.Not(), center=direct_center)],
            )
        ],
    )
    m.add_hint(corridor, 0)
    solver = cp_model.CpSolver()
    assert solver.solve(m) in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    # Force and evaluate the actual invalid assignment before learning its cut.
    m.add(corridor == 0)
    assert solver.solve(m) == cp_model.OPTIMAL
    ring = [(0, 0, 3, 1), (0, 2, 3, 3), (0, 1, 1, 2), (2, 1, 3, 2)]
    assert inspect_rectangular_union(ring)["hole_count"] == 1
    variables = fair.union_input_variables(model, solver)
    assert direct_center.index not in {v.index for v in variables}
    values = [solver.value(v) for v in variables]
    # Clone before the test-only restriction; build the two residual domains.
    residual = cp_model.CpModel()
    residual.proto.copy_from(m.proto)
    residual.proto.constraints[-1].copy_from(cp_model.CpModel().proto.constraints.add())
    residual.add_forbidden_assignments(
        [residual.get_int_var_from_proto_index(v.index) for v in variables], [values]
    )
    assert solver.solve(residual) == cp_model.OPTIMAL
    assert solver.value(residual.get_int_var_from_proto_index(corridor.index)) == 1
    assert inspect_rectangular_union(ring + [(1, 1, 2, 2)])["valid"]
    # An alternative portal with unchanged invalid union remains excluded.
    residual.add(residual.get_int_var_from_proto_index(corridor.index) == 0)
    assert solver.solve(residual) == cp_model.INFEASIBLE


def test_active_corridor_alternative_points_are_not_excluded():
    m = cp_model.CpModel()
    p = m.new_int_var(0, 2, "actual-path-x")
    room = {k: m.new_constant(v) for k, v in dict(x=0, y=0, w=1, d=1).items()}
    model = SimpleNamespace(
        rooms={"synthetic": room},
        interfaces=[],
        routes=[dict(corridor=m.new_constant(1), points=[(p, m.new_constant(1))])],
    )
    s = cp_model.CpSolver()
    assert s.solve(m) == cp_model.OPTIMAL
    before = s.value(p)
    variables = fair.union_input_variables(model, s)
    assert p.index in {v.index for v in variables}
    m.add_forbidden_assignments(variables, [[s.value(v) for v in variables]])
    assert s.solve(m) == cp_model.OPTIMAL
    assert s.value(p) != before


def test_actual_durable_lease_rejects_old_schedule_for_new_policy(tmp_path):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    lease = ledger.execution_authorization
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash", "schedule_hash")}
    sources["schedule_hash"] = schedule_hash(sources["schedule_hash"])
    try:
        with pytest.raises(LayoutAuthorityError, match="POOL_PLAN_OR_SOURCE_MISMATCH"):
            lease.validate_pool(
                ledger, sources, tuple(c["identity"] for c in binding["compositions"])
            )
        assert lease.record["cursor"] == 0
        assert not lease.record["admitted"]
        assert ledger.attempts == []
    finally:
        lease.finish_pool()


def test_opt_in_native_hook_rejects_real_ring_and_retains_open_notch(monkeypatch):
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
            for r, (x, y) in zip(ring, positions, strict=True):
                r.update(x=x, y=y)
            opened = deepcopy(ring)
            opened[5].update(x=3, y=0)
            return [ring, opened]

        def __init__(self, *args):
            super().__init__(*args)
            self.interfaces[0]["corridor"] = False

    monkeypatch.setattr(native, "GlobalModel", Ring)
    monkeypatch.setattr(native, "AccessModel", Ring)
    stream = native.OrToolsGlobalCompositionSolver().iter_solutions(
        context, None, event_sink=lease.events.append, topology_variables=fair.union_input_variables
    )
    first = next(stream)
    assert first["model_witness_topology"]["valid"]
    assert context.ledger.checked_solutions == 2
    cut = next(e for e in lease.events if e["kind"] == "TOPOLOGY_REJECTED_WITNESS_CUT")
    assert cut["certificate"]["hole_count"] == 1
    assert "portal-position" not in cut["variable_names"]
    assert first["topology_refinement_cuts"][0]["scope"] == "EXACT_EXPORTED_UNION_INPUT_EQUIVALENCE"
    stream.close()


def test_native_share_caps_hints_and_still_allows_two_solutions(monkeypatch):
    context, _ = native_setup(monkeypatch)
    # Exercise original native solve/accounting through the additional quantum.
    engine = fair.FairNativeSolver(context.ledger, 6)
    stream = engine.iter_solutions(context, None)
    first = next(stream)
    second = stream.send("ENGINEERING_ACCEPTED")
    assert first["zones"] != second["zones"]
    assert context.ledger.checked_solutions == 2
    stream.close()


def test_share_is_additional_bound_not_refill_and_reserves_other_handoffs(monkeypatch):
    context, _ = native_setup(monkeypatch)
    context.ledger.solver_wall = 12
    context.ledger.solver_monotonic_wall = 12
    context.ledger.model_work = 120
    engine = fair.FairNativeSolver(context.ledger, 6)
    assert engine.checked_share == 3
    assert engine.native_share == pytest.approx((100 - 12) / 6)  # synthetic lease only
    context.ledger.checked_solutions = 3
    with pytest.raises(LayoutAuthorityError, match=fair.SHARE_STOP):
        engine._run(context, cp_model.CpModel(), 1, "ALL_ROOMS_ALL_ACCESS")
    assert context.ledger.solver_wall == 12
    assert context.ledger.model_work == 120
    context.ledger.model_work = 1_200_001
    with pytest.raises(LayoutAuthorityError, match="STAGE_A_RESOURCE_LIMIT"):
        engine._run(context, cp_model.CpModel(), 1, "ALL_ROOMS_ALL_ACCESS")


def test_new_entry_has_no_grant_and_old_hash_cannot_admit_new_policy(monkeypatch):
    plan, p1, site = _context()
    result = generate_fair_multi_solution_global_layout_pool(plan, p1.to_dict(), site)
    assert "QUOTA_REQUIRED" in result["status"]
    assert result["attempts"] == []
    assert schedule_hash("old") != "old"
    plan, p1, site, ledger, _, _ = setup_ports(monkeypatch, ["EEENNN"] * 6)

    class OldLease(EnumerationLease):
        def validate_pool(self, ledger, sources, plan):
            raise LayoutAuthorityError("POOL_PLAN_OR_SOURCE_MISMATCH")

    ledger.execution_authorization = OldLease()
    with pytest.raises(LayoutAuthorityError, match="SOURCE_MISMATCH"):
        generate_fair_multi_solution_global_layout_pool(plan, p1, site, execution_ledger=ledger)


def test_fair_pool_keeps_candidates_covers_six_and_separates_counts(monkeypatch):
    plan, p1, site, ledger, _, _ = setup_ports(monkeypatch, ["EEENNN"] * 6)
    ledger.execution_authorization = EnumerationLease()
    shares = []

    class Port:
        policy_hash = POLICY_HASH

        def start_handoff(self, ledger, remaining):
            shares.append(remaining)

    import cold_storage.modules.layout.application.global_composition_pool as original

    generate = original.generate_global_composition_candidate
    calls = []

    def candidates(*args, **kwargs):
        calls.append(kwargs["composition_identity"])
        body = generate(*args, **kwargs)
        zones, branches = branch_case(len(calls) % 2 == 0)
        body["proposal"]["zones"] = zones
        for branch in branches:
            # Replace the two synthetic result rows without changing exact identities.
            target = next(
                r
                for r in body["engineering_validation"]["access_results"]
                if r["requirement_identity"]
                == f"access:{branch['from_ref']}->{branch['to_ref']}@1.0.0"
            )
            target.update(branch)
        body["canonical_result_hash"] = canonical_hash(
            {k: v for k, v in body.items() if k != "canonical_result_hash"}
        )
        yield deepcopy(body)
        # A local share exhaustion advances, not global stop/INFEASIBLE.
        raise LayoutAuthorityError(fair.SHARE_STOP)

    monkeypatch.setattr(pool, "generate_global_composition_candidates", candidates)
    result = pool.generate_multi_solution_pool(
        plan, p1, site, solver=Port(), execution_ledger=ledger, fair_search=True
    )
    assert shares == [6, 5, 4, 3, 2, 1]
    assert result["distinct_physical_geometry_count"] == 2
    assert result["distinct_meaningful_construction_count"] == 2
    assert (
        result["major_structural_family_count"] == result["legacy_distinct_organization_count"] == 1
    )
    assert len(result["candidates"]) == 2
    assert result["p2d_full_pass_count"] == 0
    assert all(c["error"]["code"] == fair.SHARE_STOP for c in result["compositions"])


def _family_proposal(path="EEENNN", *, north=False, east=False, defect=None):
    zones, branches = branch_case(north)
    before = physical_boxes(zones)["sorting_packaging_room"]
    main = {r["zone_code"]: r for r in rooms(path)}
    for row in zones:
        if row["zone_code"] in PROCESS_FLOW:
            row.update(main[row["zone_code"]])
    after = physical_boxes(zones)["sorting_packaging_room"]
    dx, dy = ((after[i] - before[i]) / 1000 for i in (0, 1))
    changing = next(r for r in zones if r["zone_code"] == "changing_room")
    changing.update(x=changing["x"] + dx, y=changing["y"] + dy)
    for branch in branches:
        for key in ("portal_from", "portal_to"):
            if key in branch:
                for point in branch[key]["segment"].values():
                    point.update(
                        x=str(Decimal(point["x"]) + Decimal(str(dx))),
                        y=str(Decimal(point["y"]) + Decimal(str(dy))),
                    )
    if east:
        changing["width_m"] = 2
        right = physical_boxes(zones)["changing_room"][2]
        for point in branches[0]["portal_to"]["segment"].values():
            point["x"] = str(Decimal(right) / 1000)
    if defect == "microshift":
        office = next(r for r in zones if r["zone_code"] == "office")
        office["x"] = str(Decimal(str(office["x"])) + Decimal("0.001"))
    return dict(zones=zones, branches=branches, defect=defect)


def _collect_families(monkeypatch, proposals):
    plan, p1, site, ledger, _, _ = setup_ports(monkeypatch, ["EEENNN"] * len(proposals))
    ledger.execution_authorization = EnumerationLease()
    from cold_storage.modules.layout.application import global_composition_pool as original

    generate = original.generate_global_composition_candidate
    emitted = []

    class Port:
        policy_hash = POLICY_HASH

        def start_handoff(self, ledger, remaining):
            pass

    def candidates(*args, **kwargs):
        # Only first handoff has these synthetic proposals; other streams end.
        if emitted:
            return
        emitted.append(kwargs["composition_identity"])
        for data in proposals:
            body = generate(*args, **kwargs)
            body["proposal"]["zones"] = deepcopy(data["zones"])
            for branch in data["branches"]:
                row = next(
                    r
                    for r in body["engineering_validation"]["access_results"]
                    if r["requirement_identity"]
                    == f"access:{branch['from_ref']}->{branch['to_ref']}@1.0.0"
                )
                row.update(deepcopy(branch))
            if data["defect"] == "missing_branch":
                # Identities/PASS alone are insufficient: actual Portal evidence missing.
                del body["engineering_validation"]["access_results"][0]["portal_to"]
            if data["defect"] == "engineering_failure":
                body["native_independent_validation"]["pass"] = False
            if data["defect"] == "unknown":
                body["proposal"] = {"solver_status": "UNKNOWN"}
                body["stage_a_engineering_accepted"] = False
            if data["defect"] == "resource_interrupt":
                body["engineering_validation"]["access_results"][0]["status"] = (
                    "RESOURCE_INTERRUPTED"
                )
            body["canonical_result_hash"] = canonical_hash(
                {k: v for k, v in body.items() if k != "canonical_result_hash"}
            )
            yield body

    monkeypatch.setattr(pool, "generate_global_composition_candidates", candidates)
    result = pool.generate_multi_solution_pool(
        plan, p1, site, solver=Port(), execution_ledger=ledger, fair_search=True
    )
    accepted_families = {c["diversity"]["major_family_hash"] for c in result["candidates"]}
    assert result["major_structural_family_count"] == len(accepted_families)
    assert result["construction_candidate_count"] == len(result["candidates"])
    assert result["p2d_full_pass_count"] == 0
    return result


def test_a_new_family_missing_branch_does_not_count(monkeypatch):
    result = _collect_families(monkeypatch, [_family_proposal(defect="missing_branch")])
    assert result["distinct_physical_geometry_count"] == 1
    assert result["construction_candidate_count"] == result["major_structural_family_count"] == 0


def test_b_duplicate_geometry_does_not_add_candidate_or_family(monkeypatch):
    data = _family_proposal()
    result = _collect_families(monkeypatch, [data, deepcopy(data)])
    assert result["distinct_physical_geometry_count"] == 1
    assert result["construction_candidate_count"] == result["major_structural_family_count"] == 1
    assert result["attempts"][1]["status"] == "DUPLICATE_GEOMETRY_NOT_COUNTED"


def test_c_same_functional_organization_does_not_add_family(monkeypatch):
    result = _collect_families(
        monkeypatch, [_family_proposal(), _family_proposal(defect="microshift")]
    )
    assert result["distinct_physical_geometry_count"] == 2
    assert result["construction_candidate_count"] == result["major_structural_family_count"] == 1
    assert result["attempts"][1]["status"] == "SAME_FUNCTIONAL_ORGANIZATION_NOT_COUNTED"


def test_d_two_constructions_one_actual_family(monkeypatch):
    result = _collect_families(monkeypatch, [_family_proposal(), _family_proposal(north=True)])
    assert result["construction_candidate_count"] == 2
    assert result["major_structural_family_count"] == 1


def test_e_two_accepted_constructions_two_actual_families(monkeypatch):
    result = _collect_families(monkeypatch, [_family_proposal(), _family_proposal("EEEEEE")])
    assert result["construction_candidate_count"] == 2
    assert result["major_structural_family_count"] == 2


def test_f_rejected_third_family_cannot_complete_five_three_target(monkeypatch):
    proposals = [_family_proposal("ENENEN", defect="missing_branch")]
    proposals.extend(
        _family_proposal(north=n, east=e)
        for n, e in ((False, False), (True, False), (False, True), (True, True))
    )
    proposals.append(_family_proposal("EENNWW"))
    result = _collect_families(monkeypatch, proposals)
    assert result["construction_candidate_count"] == 5
    assert result["major_structural_family_count"] == 2
    assert result["status"] != "CONSTRUCTION_TARGETS_MET_NOT_P2D"


@pytest.mark.parametrize("defect", ["engineering_failure", "unknown", "resource_interrupt"])
def test_nonaccepted_outcomes_never_add_families(monkeypatch, defect):
    result = _collect_families(monkeypatch, [_family_proposal(defect=defect)])
    assert result["construction_candidate_count"] == result["major_structural_family_count"] == 0
