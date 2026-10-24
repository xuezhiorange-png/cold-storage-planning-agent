"""Opt-in two-stage continuation, no bootstrap, quota or default activation.

The existing application stream persists/yields every independently validated
candidate before resuming us. Improvement never replaces that baseline. All
native work uses the original FairNativeSolver handoff share and StageALedger.
"""

from copy import deepcopy
from fractions import Fraction
from typing import Any, cast

from cold_storage.modules.layout.domain.construction_branch_diversity import (
    construction_branch_diversity,
)
from cold_storage.modules.layout.domain.construction_diagnostics import construction_diagnostics
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_construction_guidance import (
    FUNCTIONAL_SHAPE_POLICY_HASH,
    FUNCTIONAL_SHAPE_ROLES,
    apply_functional_shape_guidance,
)
from cold_storage.modules.layout.infrastructure.stage_b_fair_search import (
    FairNativeSolver,
    StageBFairSearchSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_wall_alignment import (
    POLICY_HASH as WALL_HASH,
)

POLICY = "stage-b-feasibility-first-bounded-functional-continuation@1.0.0"
POLICY_HASH = canonical_hash(
    {
        "version": POLICY,
        "feasibility_guidance": WALL_HASH,
        "improvement_guidance": FUNCTIONAL_SHAPE_POLICY_HASH,
        "transition": "AFTER_PERSISTED_INDEPENDENT_ENGINEERING_ACCEPTANCE",
        "hint_source": "CURRENT_INVOCATION_ACCEPTED_NATIVE_ASSIGNMENT_ONLY",
        "quality_search": "CONTINUE_OPTIMIZATION_WITHIN_ORIGINAL_HANDOFF_SHARE",
        "comparison": "EXISTING_CONSTRUCTION_FACTS_PARETO_NOT_FUNCTIONAL_APPROVAL",
        "baseline": "PRESERVE_REGARDLESS_OF_CONTINUATION_OUTCOME",
    }
)


class _FeasibilityFirstNative(FairNativeSolver):
    improving = False
    continuation_policy = POLICY
    continuation_policy_hash = POLICY_HASH

    def _apply_improvement_guidance(self, model: Any, context: Any) -> dict[str, Any]:
        return apply_functional_shape_guidance(model, context)

    def _configure_search(self, solver: Any, phase: str) -> None:
        if self.improving and phase == "ALL_ROOMS_ALL_ACCESS":
            solver.parameters.stop_after_first_solution = False

    def _hint_current_assignment(self, model: Any, context: Any, solver: Any) -> None:
        context.ledger.charge("STAGE_B_CURRENT_VALID_ASSIGNMENT_HINT", len(model.m.proto.variables))
        model.m.clear_hints()
        for index in range(len(model.m.proto.variables)):
            variable = model.m.get_int_var_from_proto_index(index)
            model.m.add_hint(variable, solver.value(variable))

    def begin_improvement(self, model: Any, context: Any, solver: Any) -> dict[str, Any]:
        self.remaining_share(context)  # No room, family or phase receives a fresh quantum.
        context.ledger.remaining_solver_seconds()
        # The same model retains every hard constraint, including total wall
        # definitions and exact invalid-witness cuts. Replace ONE soft objective.
        # Native indices/values are from this very model, not caller coordinates.
        self._hint_current_assignment(model, context, solver)
        model.m.clear_objective()
        receipt = self._apply_improvement_guidance(model, context)
        self.improving = True
        return {
            **receipt,
            "preference_policy": receipt["policy"],
            "preference_policy_hash": receipt["policy_hash"],
            "policy": self.continuation_policy,
            "policy_hash": self.continuation_policy_hash,
            "first_solution_termination_unchanged": False,
            "optimality_claimed": False,
            "hint_source": "THIS_EXECUTION_INDEPENDENTLY_ACCEPTED_NATIVE_ASSIGNMENT",
        }


def _quality_facts(candidate: dict[str, Any]) -> dict[str, Any]:
    """Consume existing fact diagnostics; do not duplicate geometry/fit validators."""
    zones, application = candidate["proposal"]["zones"], candidate["engineering_validation"]
    facts = construction_diagnostics(zones, application)
    branches = construction_branch_diversity(zones, application["access_results"])
    metrics: dict[str, Any] = {}
    for role in FUNCTIONAL_SHAPE_ROLES:
        shape = facts["room_shapes"][role]
        w, d = Fraction(shape["physical_width_m"]), Fraction(shape["physical_depth_m"])
        metrics[role + "_aspect"] = str(max(w, d) / min(w, d))
    ingress = [
        r
        for r in facts["actual_access_route_facts"]
        if r["from_ref"] == "main_entrance" and r["to_ref"] == "changing_room"
    ]
    route = ingress[0] if len(ingress) == 1 and ingress[0]["centerline"] else None
    metrics["personnel_route_m"] = route["measured_centerline_length_m"] if route else None
    metrics["personnel_route_turns"] = route["measured_heading_changes"] if route else None
    footprint = facts["footprint"]
    for key in ("area_m2", "perimeter_m", "outline_turn_count"):
        metrics["footprint_" + key] = footprint[key] if footprint else None
    return {
        "metrics": metrics,
        "construction_facts": facts,
        "functional_diversity": branches,
        "functional_fit_status": "INPUT_REQUIRED",
        "formal_quality_acceptance": False,
    }


class StageBFeasibilityFirstFairSearchSolver(StageBFairSearchSolver):
    """Explicit internal solver port; existing roots and consumed grants stay unchanged."""

    def start_handoff(self, ledger: Any, remaining_handoffs: int) -> None:
        self.native = _FeasibilityFirstNative(ledger, remaining_handoffs)
        self.baseline: dict[str, Any] | None = None

    def solutions(self, context: Any, handoff: Any) -> Any:
        decision = getattr(context.ledger.execution_authorization, "decision", {})
        if decision.get("feasibility_first_policy_hash") != POLICY_HASH:
            raise LayoutAuthorityError("STAGE_B_FEASIBILITY_FIRST_BOUND_POLICY_REQUIRED")
        return super().solutions(context, handoff)

    def _continuation_options(self, context: Any) -> dict[str, Any]:
        return {
            "accepted_model_guidance": lambda model, solver: cast(
                _FeasibilityFirstNative, self.native
            ).begin_improvement(model, context, solver)
        }

    def observe_validated_candidate(
        self, context: Any, handoff: Any, candidate: dict[str, Any], feedback: str
    ) -> None:
        if feedback != "ENGINEERING_ACCEPTED":
            return  # Never run a quality comparison on engineering failures.
        facts = _quality_facts(candidate)
        snapshot = {
            "candidate_hash": candidate["canonical_result_hash"],
            "geometry_hash": candidate["proposal"]["geometry_hash"],
            "composition_hash": handoff.source_composition_hash,
            "resource_ledger": deepcopy(candidate["resource_ledger"]),
            **facts,
        }
        if self.baseline is None:
            self.baseline = deepcopy(snapshot)
            comparison: dict[str, Any] = {
                "status": "BASE_VALID_CANDIDATE_PRESERVED",
                "baseline": snapshot,
            }
        else:
            before, after = self.baseline["metrics"], facts["metrics"]
            complete = all(v is not None for v in (*before.values(), *after.values()))
            differences = {
                k: (Fraction(str(after[k])) > Fraction(str(before[k])))
                - (Fraction(str(after[k])) < Fraction(str(before[k])))
                for k in before
                if before[k] is not None and after[k] is not None
            }
            same_organization = (
                self.baseline["functional_diversity"]["countable"]
                and facts["functional_diversity"]["countable"]
                and self.baseline["functional_diversity"]["meaningful_construction_hash"]
                == facts["functional_diversity"]["meaningful_construction_hash"]
            )
            comparison = {
                "status": "GEOMETRIC_PARETO_IMPROVEMENT"
                if complete
                and same_organization
                and max(differences.values()) <= 0
                and min(differences.values()) < 0
                else "FACTS_ONLY_OWNER_REVIEW_REQUIRED",
                "baseline_candidate_hash": self.baseline["candidate_hash"],
                "candidate": snapshot,
                "metric_directions_minus_one_better": differences,
                "all_comparison_metrics_available": complete,
                "same_meaningful_organization": same_organization,
                "baseline_retained": True,
                "overall_quality_improvement_claimed": False,
            }
        context.ledger.execution_authorization.record_enumeration(
            {
                "zone_plan_hash": context.binding.canonical_zone_plan_hash,
                "p1_hash": context.binding.p1_handoff_hash,
                "site_hash": context.binding.site_geometry_hash,
                "composition_hash": handoff.source_composition_hash,
            },
            {"kind": "FEASIBILITY_FIRST_QUALITY_FACTS", "policy_hash": POLICY_HASH, **comparison},
        )
