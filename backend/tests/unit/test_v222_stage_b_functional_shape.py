"""Synthetic preference/model-only tests. No real factory or Owner grant."""

from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_construction_guidance import (
    FUNCTIONAL_SHAPE_POLICY,
    FUNCTIONAL_SHAPE_POLICY_HASH,
    FUNCTIONAL_SHAPE_ROLES,
    apply_functional_shape_guidance,
)
from cold_storage.modules.layout.infrastructure.stage_b_fair_search import (
    StageBFairSearchSolver,
    StageBFunctionalShapeFairSearchSolver,
)
from tests.unit.test_v222_stage_b_construction_guidance import model, v


def prepared():
    charges = []
    context = SimpleNamespace(
        binding=SimpleNamespace(
            p1_handoff_hash="synthetic-p1",
            canonical_zone_plan_hash="synthetic-plan",
            site_geometry_hash="synthetic-site",
            dimension_authorities={
                r: {"dimension_mode": "FLEXIBLE_RECTANGLE"} for r in FUNCTIONAL_SHAPE_ROLES
            },
        ),
        ledger=SimpleNamespace(charge=lambda k, n: charges.append((k, n))),
    )
    return SimpleNamespace(m=model(), c=context), context, charges


def search(m):
    s = cp_model.CpSolver()
    s.parameters.num_search_workers = 1
    s.parameters.random_seed = 3
    s.parameters.stop_after_first_solution = True
    s.parameters.search_branching = cp_model.PARTIAL_FIXED_SEARCH
    s.parameters.max_time_in_seconds = 1
    s.parameters.max_memory_in_mb = 512
    status = s.solve(m)
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    return s


def test_final_proxy_same_limits_repeatable_effect_not_real_quality_acceptance():
    observations = []
    for _ in range(4):
        pair = []
        for enabled in (False, True):
            final, context, charges = prepared()
            # Two finite physical shapes of equal area, no historical coordinates.
            w, d = [v(final.m, "office_physical_" + k) for k in ("w", "d")]
            final.m.add_allowed_assignments([w, d], [(2, 8), (4, 4)])
            for role in ("changing_room", "coating_room"):
                for key in ("w", "d"):
                    final.m.add(v(final.m, role + "_physical_" + key) == 4)
            final.m.add_decision_strategy([w], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE)
            if enabled:
                r = apply_functional_shape_guidance(final, context)
                assert r["phase"] == "ALL_ROOMS_ALL_ACCESS"
                assert r["functional_fit_status"] == "INPUT_REQUIRED"
                assert not r["real_layout_quality_improved"] and charges
            s = search(final.m)
            pair.append((s.value(w), s.value(d)))
        assert pair == [(2, 8), (4, 4)]
        observations.append(pair)
    assert all(row == observations[0] for row in observations)


@pytest.mark.parametrize("width,depth", [(1, 8), (8, 1), (4, 4), (8, 8)])
def test_every_old_physical_assignment_remains_feasible_no_hidden_hard(width, depth):
    final, context, _ = prepared()
    final.m.add(v(final.m, "office_physical_w") == width)
    final.m.add(v(final.m, "office_physical_d") == depth)
    before = final.m.clone()
    apply_functional_shape_guidance(final, context)
    final.m.clear_objective()
    assert str(final.m.proto) == str(before.proto)  # No auxiliary cuts or new bounds at all.
    search(final.m)


def test_authority_filter_no_caller_dimensions_and_refuse_other_objectives():
    final, context, _ = prepared()
    context.binding.dimension_authorities["coating_room"]["dimension_mode"] = "FIXED_RECTANGLE"
    r = apply_functional_shape_guidance(final, context)
    assert r["target_roles"] == ["office", "changing_room"]
    assert r["policy_hash"] == FUNCTIONAL_SHAPE_POLICY_HASH
    assert r["source_p1_handoff_hash"] == context.binding.p1_handoff_hash
    with pytest.raises(LayoutAuthorityError, match="OBJECTIVE_ALREADY_PRESENT"):
        apply_functional_shape_guidance(final, context)
    with pytest.raises(LayoutAuthorityError, match="CONTEXT_MISMATCH"):
        apply_functional_shape_guidance(final, SimpleNamespace())
    with pytest.raises(TypeError):
        apply_functional_shape_guidance(final, context, width=4000)


def test_policy_receipt_and_model_bytes_repeat_exactly():
    a, ac, _ = prepared()
    b, bc, _ = prepared()
    assert apply_functional_shape_guidance(a, ac) == apply_functional_shape_guidance(b, bc)
    assert str(a.m.proto) == str(b.m.proto)
    assert canonical_hash(FUNCTIONAL_SHAPE_POLICY) != FUNCTIONAL_SHAPE_POLICY_HASH


def test_missing_authority_refused_and_original_fair_resource_methods_not_overridden():
    final, context, _ = prepared()
    del context.binding.dimension_authorities["office"]
    with pytest.raises(LayoutAuthorityError, match="AUTHORITY_MISSING"):
        apply_functional_shape_guidance(final, context)
    assert (
        StageBFunctionalShapeFairSearchSolver.start_handoff is StageBFairSearchSolver.start_handoff
    )


def test_ordinary_fair_default_unchanged_and_explicit_strategy_reaches_final_callback():
    final, context, _ = prepared()
    final.rooms = {
        role: {
            k: v(final.m, role + suffix)
            for k, suffix in (("x", "_x"), ("y", "_y"), ("w", "_physical_w"), ("d", "_physical_d"))
        }
        for role in FUNCTIONAL_SHAPE_ROLES
    }
    before = str(final.m.proto)
    legacy = StageBFairSearchSolver()._final_guidance(final, context)
    assert legacy["policy"] == "stage-b-wall-coordinate-coherence-and-span@1.0.0"
    assert before != str(final.m.proto)
    # Inspect the inherited native hook without starting any native search.
    solver = StageBFunctionalShapeFairSearchSolver()
    context.binding.canonical_zone_plan_hash = "synthetic-plan"
    context.binding.p1_handoff_hash = "synthetic-p1"
    context.binding.site_geometry_hash = "synthetic-site"
    events = []
    context.ledger.execution_authorization = SimpleNamespace(
        decision={"functional_shape_policy_hash": FUNCTIONAL_SHAPE_POLICY_HASH},
        record_enumeration=lambda *args: events.append(args),
    )
    solver.native = SimpleNamespace(
        ledger=context.ledger, native_share=1, work_share=100, elapsed_share=1, checked_share=1
    )

    # Bind the captured model to the original server context, not a caller's dimensions.
    def capture_final(*args, **kwargs):
        assert kwargs["propagate_base_infeasible"] is True
        f, _, _ = prepared()
        f.c = context
        return kwargs["final_model_guidance"](f)

    solver.native.iter_solutions = capture_final
    r = solver.solutions(context, SimpleNamespace(source_composition_hash="synthetic-handoff"))
    assert r["policy_hash"] == FUNCTIONAL_SHAPE_POLICY_HASH
    assert events and r["target_roles"] == list(FUNCTIONAL_SHAPE_ROLES)


@pytest.mark.parametrize("decision", [{}, {"functional_shape_policy_hash": "forged"}])
def test_no_legacy_or_missing_policy_admission(decision):
    _, context, _ = prepared()
    context.ledger.execution_authorization = SimpleNamespace(decision=decision)
    with pytest.raises(LayoutAuthorityError, match="BOUND_POLICY_REQUIRED"):
        StageBFunctionalShapeFairSearchSolver().solutions(context, None)


def test_resource_charge_failure_still_propagates():
    final, context, _ = prepared()

    def exhausted(*args):
        raise LayoutAuthorityError("STAGE_A_RESOURCE_LIMIT")

    context.ledger.charge = exhausted
    with pytest.raises(LayoutAuthorityError, match="STAGE_A_RESOURCE_LIMIT"):
        apply_functional_shape_guidance(final, context)
