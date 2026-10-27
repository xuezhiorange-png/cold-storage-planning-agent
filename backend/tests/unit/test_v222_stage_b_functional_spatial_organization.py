"""R10 real complete-model metadata, identity and resource contracts; no MAIN."""

from copy import deepcopy

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_changing_frontage_corridor as r9
from cold_storage.modules.layout.infrastructure import stage_b_first_feasible_recovery as r7
from cold_storage.modules.layout.infrastructure import stage_b_frontage_joint_search as r6
from cold_storage.modules.layout.infrastructure import (
    stage_b_functional_spatial_organization as r10,
)
from cold_storage.modules.layout.infrastructure.stage_b_route_refinement_resources import (
    POLICY_HASH as RESOURCE_R9_HASH,
)
from tests.r9_full_engineering_synthetic import sources
from tests.r9_route_refinement_experiment import StrictSyntheticQuota
from tests.r10_spatial_organization_experiment import bind_functional_bays


def prepared():
    _, _, _, handoff, context, _, _ = sources()
    context.ledger.solver_history_verified = True  # New synthetic ledger, no previous Solve.
    model = bind_functional_bays(r6._ReferenceAccessModel(context, handoff, True), context)
    port = r10.StageBFunctionalSpatialOrganizationFairSolver()
    context.ledger.execution_authorization = StrictSyntheticQuota(port.quality_policy_hash)
    port.start_handoff(context.ledger, 1)
    port._final_guidance(model, context)
    return context, model, port.native._feedback_proxy_index


def physical_proto(m):
    proto = deepcopy(m.proto)
    proto.search_strategy.clear()
    return str(proto)  # Includes all domains/constraints/objective AND current Hint.


def test_complete_physical_proto_objective_and_hint_identical_after_soft_reorder():
    c, m, index = prepared()
    # Current synthetic room references; no historical factory coordinates.
    for key, value in (("x", 40000), ("y", 20000), ("w", 4000), ("d", 10000)):
        m.m.add_hint(m.rooms["changing_room"][key], value)
    before = physical_proto(m.m)
    count = (len(m.m.proto.variables), len(m.m.proto.constraints))
    receipt = r10.apply_functional_spatial_organization(m, c, index)
    assert physical_proto(m.m) == before
    assert count == (len(m.m.proto.variables), len(m.m.proto.constraints))
    assert receipt["local_model_copies"] == receipt["extra_native_calls"] == 0
    assert not m.m.validate()
    assert c.ledger.resource_events["R10_AREA_REFERENCE_READ"] == 13
    assert c.ledger.resource_events["R10_ORGANIZATION_SEARCH_METADATA"] > 0
    assert receipt["required_area_m2"] == {
        "office": "60",
        "changing_room": "40",
        "coating_room": "80",
    }
    assert not receipt["furniture_layout_validated"]
    assert not receipt["real_layout_quality_improved"]


def test_all_three_strategies_build_identical_first_stage_complete_models():
    protos = []
    for cls in (
        r7.StageBFirstFeasibleRecoveryFairSolver,
        r9.StageBChangingFrontageCorridorFairSolver,
        r10.StageBFunctionalSpatialOrganizationFairSolver,
    ):
        _, _, _, handoff, c, _, _ = sources()
        c.ledger.solver_history_verified = True
        c.ledger.execution_authorization = StrictSyntheticQuota(cls.quality_policy_hash)
        port = cls()
        port.start_handoff(c.ledger, 1)
        options = port._continuation_options(c)
        assert "final_model_search" not in options
        assert "before_accepted_geometry_cut" not in options
        model = bind_functional_bays(r6._ReferenceAccessModel(c, handoff, True), c)
        port._final_guidance(model, c)
        protos.append(str(model.m.proto))
        assert not port.native.improving
        assert not any(
            k.startswith("R10_") and "SYNTHETIC" not in k for k in c.ledger.resource_events
        )
    assert protos[0] == protos[1] == protos[2]


def test_three_demand_normalized_room_choices_precede_changing_position_and_faces():
    c, m, index = prepared()
    receipt = r10.apply_functional_spatial_organization(m, c, index)
    names = [
        m.m.get_int_var_from_proto_index(s.exprs[0].vars[0]).name
        for s in list(m.m.proto.search_strategy)[:3]
    ]
    assert names == ["r5_area_" + r + "_proxy" for r in ("changing_room", "office", "coating_room")]
    assert len(receipt["variable_indices"]) == len(set(receipt["variable_indices"]))
    assert receipt["preferred_entrance_face"] == "SOUTH"


@pytest.mark.parametrize("face", range(4))
@pytest.mark.parametrize("upper", [False, True])
def test_current_site_axis_and_entrance_half_select_dynamic_soft_order(face, upper):
    c, m, index = prepared()
    sx, sy, sr, st = c.sitebox
    low, high = (120000, 122000) if upper else (2000, 4000)
    if face < 2:
        low, high = (80000, 82000) if upper else (2000, 4000)
    fixed = (sx, sr, sy, st)[face]
    c.entrances["main_entrance"] = (
        ((fixed, low), (fixed, high)) if face < 2 else ((low, fixed), (high, fixed))
    )
    before = physical_proto(m.m)
    receipt = r10.apply_functional_spatial_organization(m, c, index)
    assert receipt["preferred_entrance_face"] == ("WEST", "EAST", "SOUTH", "NORTH")[face]
    assert receipt["tangent_preference"] == ("UPPER" if upper else "LOWER")
    assert physical_proto(m.m) == before


@pytest.mark.parametrize(
    "fault", ["owner", "proxy_index", "proxy_name", "objective", "p1", "must", "route", "foreign"]
)
def test_ambiguous_or_invalid_reference_fails_before_metadata_mutation(fault):
    c, m, index = prepared()
    if fault == "owner":
        m.m.owner = object()
    elif fault == "proxy_index":
        index -= 1
    elif fault == "proxy_name":
        m.m.proto.variables[index - 1].name = "not_area_proxy"
    elif fault == "objective":
        m.m.minimize(m.rooms["office"]["w"])
    elif fault == "p1":
        c.binding.dimension_authorities["changing_room"]["required_area_m2"] = "0"
    elif fault == "must":
        m.must_choices.pop(("office", "shipping_channel"))
    elif fault == "route":
        m.routes.append(next(r for r in m.routes if r["req"]["from_ref"] == "main_entrance"))
    else:
        m.rooms["changing_room"]["w"] = cp_model.CpModel().new_int_var(1, 5, "foreign")
    before = str(m.m.proto)
    with pytest.raises(LayoutAuthorityError):
        r10.apply_functional_spatial_organization(m, c, index)
    assert str(m.m.proto) == before


def test_metadata_batch_precharge_rejection_leaves_entire_proto_unchanged(monkeypatch):
    c, m, index = prepared()
    charge = c.ledger.charge

    def refuse(label, n):
        if label == "R10_ORGANIZATION_SEARCH_METADATA":
            raise LayoutAuthorityError("STAGE_A_RESOURCE_LIMIT")
        charge(label, n)

    monkeypatch.setattr(c.ledger, "charge", refuse)
    before = str(m.m.proto)
    with pytest.raises(LayoutAuthorityError, match="RESOURCE_LIMIT"):
        r10.apply_functional_spatial_organization(m, c, index)
    assert str(m.m.proto) == before


def test_r7_first_stage_hints_frontier_baseline_and_comparators_are_inherited():
    new = r10.StageBFunctionalSpatialOrganizationFairSolver
    assert (
        new.native_type.prepare_first_stage is r7._FirstFeasibleRecoveryNative.prepare_first_stage
    )
    assert new.native_type._run is r7._FirstFeasibleRecoveryNative._run
    assert (
        new.native_type._hint_current_assignment
        is r7._FirstFeasibleRecoveryNative._hint_current_assignment
    )
    for method in (
        "observe_validated_candidate",
        "_observe_search_frontier",
        "_refresh_validated_hint",
    ):
        assert getattr(new, method) is getattr(r7.StageBFirstFeasibleRecoveryFairSolver, method)
    assert (
        new._continuation_options is r7.StageBFirstFeasibleRecoveryFairSolver._continuation_options
    )
    assert not hasattr(new.native_type, "refine_routes")


@pytest.mark.parametrize("old", [None, r7.POLICY_HASH, r9.POLICY_HASH, RESOURCE_R9_HASH])
def test_old_policy_cannot_select_r10(old):
    *_, c, _, _ = sources()
    c.ledger.solver_history_verified = True
    c.ledger.execution_authorization = StrictSyntheticQuota(old)
    port = r10.StageBFunctionalSpatialOrganizationFairSolver()
    port.start_handoff(c.ledger, 1)
    with pytest.raises(LayoutAuthorityError, match="BOUND_POLICY_REQUIRED"):
        port.solutions(c, None)
    assert c.ledger.attempts == []


def test_no_unaccepted_witness_can_activate_organization():
    *_, c, _, _ = sources()
    c.ledger.solver_history_verified = True
    port = r10.StageBFunctionalSpatialOrganizationFairSolver()
    c.ledger.execution_authorization = StrictSyntheticQuota(port.quality_policy_hash)
    port.start_handoff(c.ledger, 1)
    for feedback in ("UNKNOWN", "EXAMINED_WITNESS", "TOPOLOGY_REJECTED"):
        port.observe_validated_candidate(c, None, {}, feedback)
    assert port.baseline is None and port.search_frontier is None and not port.native.improving
    assert "R10_ORGANIZATION_SEARCH_METADATA" not in c.ledger.resource_events


def test_exhausted_share_keeps_baseline_and_never_installs_preferences():
    _, _, _, handoff, c, _, _ = sources()
    c.ledger.solver_history_verified = True
    port = r10.StageBFunctionalSpatialOrganizationFairSolver()
    c.ledger.execution_authorization = StrictSyntheticQuota(port.quality_policy_hash)
    port.start_handoff(c.ledger, 1)
    model = bind_functional_bays(r6._ReferenceAccessModel(c, handoff, True), c)
    port._final_guidance(model, c)
    port.baseline = {"retained": "synthetic-valid-baseline"}
    port.native.native_share = 0
    before = str(model.m.proto)
    with pytest.raises(LayoutAuthorityError, match="SHARE_EXHAUSTED"):
        port.native.begin_improvement(model, c, None)
    assert str(model.m.proto) == before
    assert port.baseline == {"retained": "synthetic-valid-baseline"}
    assert not port.native.improving and not c.ledger.attempts
