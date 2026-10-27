"""R10 R2 metadata/domain/resource contracts on the complete synthetic model."""

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_entrance_coupled_spatial as r2
from cold_storage.modules.layout.infrastructure import stage_b_first_feasible_recovery as r7
from cold_storage.modules.layout.infrastructure import stage_b_frontage_joint_search as r6
from cold_storage.modules.layout.infrastructure import stage_b_functional_spatial_organization as r1
from cold_storage.modules.layout.infrastructure import stage_b_route_refinement_resources as r9
from tests.r9_full_engineering_synthetic import sources
from tests.r9_route_refinement_experiment import StrictSyntheticQuota
from tests.r10_entrance_coupled_experiment import bind_moving_process_bays, designed_translation
from tests.unit.test_v222_stage_b_functional_spatial_organization import physical_proto, prepared


def hinted():
    c, m, index = prepared()
    for role, values in (
        ("changing_room", dict(x=40000, y=20000, w=4000, d=10000)),
        ("sorting_packaging_room", dict(x=40000, y=30000, w=7600, d=14960)),
    ):
        for key, value in values.items():
            m.m.add_hint(m.rooms[role][key], value)
    ingress = next(r for r in m.routes if r["req"]["from_ref"] == "main_entrance")
    for var, value in zip(ingress["points"][0], (45750, 0), strict=True):
        m.m.add_hint(var, value)
    return c, m, index, ingress


def test_complete_domain_objective_and_current_hint_unchanged():
    c, m, index, _ = hinted()
    before = physical_proto(m.m)
    receipt = r2.apply_entrance_coupled_spatial(m, c, index)
    assert physical_proto(m.m) == before
    assert not m.m.validate()
    assert receipt["local_model_copies"] == receipt["extra_native_calls"] == 0
    assert receipt["new_variables"] == receipt["new_constraints"] == 0
    assert receipt["validated_entrance_portal_mm"] == [45750, 0]
    assert receipt["validated_tangent_centres_twice_mm"]["changing_room"] == 84000
    assert not receipt["hint_changed"] and not receipt["hard_domain_changed"]
    assert c.ledger.resource_events["R10_R2_ENTRY_POINT_READ"] == 2
    assert c.ledger.resource_events["R10_R2_COUPLED_SEARCH_METADATA"] > 0
    strategies = list(m.m.proto.search_strategy)
    assert [s.exprs[0].vars[0] for s in strategies[:2]] == [
        m.rooms["changing_room"]["y"].index,
        m.rooms["sorting_packaging_room"]["y"].index,
    ]
    assert len(receipt["variable_indices"]) == len(set(receipt["variable_indices"]))


@pytest.mark.parametrize("face", range(4))
def test_four_actual_entrance_axes_without_changing_physical_model(face):
    c, m, index, ingress = hinted()
    sx, sy, sr, st = c.sitebox
    fixed = (sx, sr, sy, st)[face]
    entry = (fixed, 45750) if face < 2 else (45750, fixed)
    c.entrances["main_entrance"] = (
        ((fixed, 45000), (fixed, 55000)) if face < 2 else ((45000, fixed), (55000, fixed))
    )
    hint = m.m.proto.solution_hint
    for var, value in zip(ingress["points"][0], entry, strict=True):
        hint.values[list(hint.vars).index(var.index)] = value
    before = physical_proto(m.m)
    receipt = r2.apply_entrance_coupled_spatial(m, c, index)
    assert receipt["preferred_entrance_face"] == ("WEST", "EAST", "SOUTH", "NORTH")[face]
    assert receipt["validated_entrance_portal_mm"] == list(entry)
    assert physical_proto(m.m) == before
    assert (
        m.m.proto.search_strategy[0].exprs[0].vars[0]
        == m.rooms["changing_room"][("x", "X", "y", "Y")[face]].index
    )


def test_actual_portal_not_segment_midpoint_controls_tangent_direction():
    c, m, index, _ = hinted()
    hint = m.m.proto.solution_hint
    # Room centre 48 m: above actual 45.750 m entry, below segment midpoint 50 m.
    hint.values[list(hint.vars).index(m.rooms["changing_room"]["x"].index)] = 46000
    r2.apply_entrance_coupled_spatial(m, c, index)
    assert m.m.proto.search_strategy[2].domain_reduction_strategy == cp_model.SELECT_MIN_VALUE


@pytest.mark.parametrize(
    "fault",
    [
        "no_hint",
        "duplicate",
        "no_entry",
        "off_boundary",
        "off_segment",
        "foreign_entry",
        "access",
        "no_sorting_hint",
    ],
)
def test_invalid_source_or_baseline_hint_fails_before_metadata_writes(fault):
    c, m, index, ingress = hinted()
    hint = m.m.proto.solution_hint
    if fault == "no_hint":
        m.m.clear_hints()
    elif fault == "duplicate":
        m.m.add_hint(m.rooms["changing_room"]["x"], 40000)
    elif fault in ("no_entry", "no_sorting_hint"):
        var = (
            ingress["points"][0][0]
            if fault == "no_entry"
            else m.rooms["sorting_packaging_room"]["x"]
        )
        at = list(hint.vars).index(var.index)
        vs, vals = list(hint.vars), list(hint.values)
        hint.vars.clear()
        hint.values.clear()
        hint.vars.extend(vs[:at] + vs[at + 1 :])
        hint.values.extend(vals[:at] + vals[at + 1 :])
    elif fault in ("off_boundary", "off_segment"):
        var = ingress["points"][0][1 if fault == "off_boundary" else 0]
        hint.values[list(hint.vars).index(var.index)] = 1 if fault == "off_boundary" else 60000
    elif fault == "foreign_entry":
        ingress["points"][0] = (
            cp_model.CpModel().new_int_var(0, 1, "foreign"),
            ingress["points"][0][1],
        )
    else:
        route = next(r for r in m.routes if r["req"]["from_ref"] == "changing_room")
        route["req"] = dict(route["req"], identity="different-authority")
    before = str(m.m.proto)
    with pytest.raises(LayoutAuthorityError):
        r2.apply_entrance_coupled_spatial(m, c, index)
    assert str(m.m.proto) == before


def test_whole_metadata_precharge_rejection_is_atomic(monkeypatch):
    c, m, index, _ = hinted()
    original = c.ledger.charge

    def charge(label, n):
        if label == "R10_R2_COUPLED_SEARCH_METADATA":
            raise LayoutAuthorityError("STAGE_A_RESOURCE_LIMIT")
        original(label, n)

    monkeypatch.setattr(c.ledger, "charge", charge)
    before = str(m.m.proto)
    with pytest.raises(LayoutAuthorityError, match="RESOURCE_LIMIT"):
        r2.apply_entrance_coupled_spatial(m, c, index)
    assert str(m.m.proto) == before and not c.ledger.attempts


def test_three_arms_have_identical_moving_first_stage_and_authorities():
    protos = []
    for cls in (
        r9.StageBResourceBoundRouteRefinementFairSolver,
        r1.StageBFunctionalSpatialOrganizationFairSolver,
        r2.StageBEntranceCoupledSpatialFairSolver,
    ):
        _, _, _, handoff, c, _, _ = sources()
        c.ledger.solver_history_verified = True
        c.ledger.execution_authorization = StrictSyntheticQuota(cls.quality_policy_hash)
        port = cls()
        port.start_handoff(c.ledger, 1)
        m = bind_moving_process_bays(r6._ReferenceAccessModel(c, handoff, True), c)
        port._final_guidance(m, c)
        protos.append(str(m.m.proto))
        assert not port.native.improving and not c.ledger.attempts
        assert not any(
            k.startswith("R10_R2_") and "SYNTHETIC" not in k for k in c.ledger.resource_events
        )
    assert protos[0] == protos[1] == protos[2]


def test_original_first_stage_hint_frontier_and_enum_mechanisms_inherited():
    cls = r2.StageBEntranceCoupledSpatialFairSolver
    for method in ("prepare_first_stage", "_run", "_hint_current_assignment"):
        assert getattr(cls.native_type, method) is getattr(r7._FirstFeasibleRecoveryNative, method)
    for method in (
        "_continuation_options",
        "observe_validated_candidate",
        "_observe_search_frontier",
        "_refresh_validated_hint",
    ):
        assert getattr(cls, method) is getattr(r7.StageBFirstFeasibleRecoveryFairSolver, method)
    assert not hasattr(cls.native_type, "refine_routes")
    *_, c, _, _ = sources()
    c.ledger.solver_history_verified = True
    c.ledger.execution_authorization = StrictSyntheticQuota(cls.quality_policy_hash)
    port = cls()
    port.start_handoff(c.ledger, 1)
    for status in ("UNKNOWN", "TOPOLOGY_REJECTED", "EXAMINED_WITNESS"):
        port.observe_validated_candidate(c, None, {}, status)
    assert port.baseline is None and not port.native.improving


@pytest.mark.parametrize("old", [None, r7.POLICY_HASH, r9.POLICY_HASH, r1.POLICY_HASH])
def test_old_policy_does_not_select_r2(old):
    *_, c, _, _ = sources()
    c.ledger.solver_history_verified = True
    c.ledger.execution_authorization = StrictSyntheticQuota(old)
    port = r2.StageBEntranceCoupledSpatialFairSolver()
    port.start_handoff(c.ledger, 1)
    with pytest.raises(LayoutAuthorityError, match="BOUND_POLICY_REQUIRED"):
        port.solutions(c, None)
    assert not c.ledger.attempts


@pytest.mark.parametrize("offset", [0, -12])
def test_independently_accepted_translated_process_fixtures(offset):
    from cold_storage.modules.layout.application.global_composition_pool import _eligible

    candidate = designed_translation(offset)
    expected = {
        r["identity"] for r in sources()[4].binding.access_requirements if r["flow_kind"] != "TRUCK"
    }
    assert _eligible(candidate, expected)
    assert candidate["stage_a_engineering_accepted"]
    assert candidate["native_independent_validation"]["pass"]
