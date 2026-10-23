"""Optional balanced continuation; no bootstrap, grant, quota or selector change.

Integer proxies guide search only. Exact physical facts decide geometric Pareto
relations; neither the proxy nor a Pareto relation approves functional room fit.
"""

from copy import deepcopy
from fractions import Fraction
from typing import Any, cast

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.global_composition_solver import (
    GlobalGenerationContext,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_construction_guidance import (
    FUNCTIONAL_SHAPE_ROLES,
)
from cold_storage.modules.layout.infrastructure.stage_b_fair_search import (
    StageBFairSearchSolver,
    union_input_variables,
)
from cold_storage.modules.layout.infrastructure.stage_b_feasibility_first import (
    StageBFeasibilityFirstFairSearchSolver,
    _FeasibilityFirstNative,
    _quality_facts,
)
from cold_storage.modules.layout.infrastructure.stage_b_wall_alignment import (
    POLICY_HASH as WALL_HASH,
)

RATIO_SCALE = 1000  # Representation precision, NOT an engineering acceptance limit.
SHAPE_POLICY = "stage-b-balanced-functional-shape-minimax@1.0.0"
SHAPE_POLICY_HASH = canonical_hash(
    {
        "version": SHAPE_POLICY,
        "roles": FUNCTIONAL_SHAPE_ROLES,
        "dimension_mode": "FLEXIBLE_RECTANGLE",
        "objective": "MIN_MAX_CEIL_SCALE_LONG_SIDE_DIV_SHORT_SIDE",
        "scale": RATIO_SCALE,
        "definitions": "TOTAL_POSITIVE_INTEGER_DEFINITIONS_NO_PHYSICAL_CUT",
        "tie_breaking": "NONE_NO_WEIGHTED_SUM",
    }
)
COMPARISON_POLICY = "same-handoff-exact-nine-metric-pareto@1.0.0"
COMPARISON_METRICS = (
    "office_aspect",
    "changing_room_aspect",
    "coating_room_aspect",
    "worst_room_aspect",
    "personnel_route_m",
    "personnel_route_turns",
    "footprint_perimeter_m",
    "footprint_outline_turn_count",
    "footprint_reflex_corner_count",
)
FEEDBACK_POLICY = "stage-b-balanced-first-improving-witness-feedback@1.1.0"
FEEDBACK_POLICY_HASH = canonical_hash(
    {
        "version": FEEDBACK_POLICY,
        "stop": "FIRST_PROXY_STRICTLY_BELOW_PERSISTED_BASELINE",
        "baseline": "SAME_HANDOFF_VALIDATED_PARETO_INCUMBENT_OR_FIRST_BASELINE",
        "hint_refresh": "CURRENT_ACCEPTED_UNION_INPUTS_ONLY_AFTER_EXACT_NINE_METRIC_PARETO",
        "allowance": "ORIGINAL_REMAINING_SHARE_NO_FIXED_TWO_SECOND_CAP",
        "scope": "IMPROVING_ALL_ROOMS_ALL_ACCESS_ONLY",
        "unknown": "END_CURRENT_STREAM_WITHOUT_CUT_OR_RETRY",
        "continuation": "EXISTING_EXACT_WITNESS_CUT_SAME_MODEL_SAME_LEDGER",
        "learning": "NOT_PRESERVED_BETWEEN_SOLVES",
    }
)
POLICY = "stage-b-feasibility-first-balanced-quality@2.2.0"
POLICY_HASH = canonical_hash(
    {
        "version": POLICY,
        "first_stage": WALL_HASH,
        "continuation": SHAPE_POLICY_HASH,
        "native_feedback": FEEDBACK_POLICY_HASH,
        "comparison": COMPARISON_POLICY,
        "metrics": COMPARISON_METRICS,
        "area": "FACT_ONLY_NOT_MINIMIZED_BY_COMPARATOR",
        "baseline": "PERSIST_BEFORE_TRANSITION_NEVER_REPLACED",
        "resources": "SAME_HANDOFF_SAME_MODEL_SAME_LEDGER_NO_REFILL",
    }
)


def apply_balanced_shape_guidance(model: Any, context: Any) -> dict[str, Any]:
    """Every positive physical assignment has one extension to these auxiliaries.

    For s=min(w,d)>0, l=max(w,d), q=(1000*l+s-1)//s=ceil(1000*l/s).
    The objective is max(q), not a hard ratio cap. Each q overestimates the
    exact scaled ratio by <1; proxy ties must be compared using exact facts.
    Unsupported arithmetic domains are rejected BEFORE definitions are added,
    never clamped into a smaller physical domain.
    """
    if model.c is not context:
        raise LayoutAuthorityError("STAGE_B_BALANCED_CONTEXT_MISMATCH")
    m = model.m
    if m.has_objective():
        raise LayoutAuthorityError("STAGE_B_BALANCED_OBJECTIVE_ALREADY_PRESENT")
    authorities = context.binding.dimension_authorities
    if any(
        authorities.get(r, {}).get("dimension_mode") != "FLEXIBLE_RECTANGLE"
        for r in FUNCTIONAL_SHAPE_ROLES
    ):
        raise LayoutAuthorityError("STAGE_B_BALANCED_FLEXIBLE_AUTHORITY_REQUIRED")
    index: dict[str, list[int]] = {}
    for i, var in enumerate(m.proto.variables):
        index.setdefault(var.name, []).append(i)
    context.ledger.charge("STAGE_B_BALANCED_VARIABLE_INDEX", len(m.proto.variables))
    context.ledger.charge(
        "STAGE_B_BALANCED_DOMAIN_BOUNDS", sum(len(v.domain) for v in m.proto.variables)
    )
    if any(n.startswith("balanced_shape_") for n in index):
        raise LayoutAuthorityError("STAGE_B_BALANCED_DEFINITIONS_ALREADY_PRESENT")
    specs = []
    for role in FUNCTIONAL_SHAPE_ROLES:
        names = [role + "_physical_" + side for side in ("w", "d")]
        if any(len(index.get(n, [])) != 1 for n in names):
            raise LayoutAuthorityError("STAGE_B_BALANCED_MODEL_FACT_REQUIRED")
        w, d = [m.get_int_var_from_proto_index(index[n][0]) for n in names]
        # Materialize before negative indexing: the locked OR-Tools pybind
        # repeated-field wrapper is not a Python list ([-1] can return zero).
        wb, db = list(w.proto.domain), list(d.proto.domain)
        wl, wu = wb[0], wb[-1]
        dl, du = db[0], db[-1]
        if min(wl, dl) <= 0:
            raise LayoutAuthorityError("STAGE_B_BALANCED_POSITIVE_DOMAIN_REQUIRED")
        sl, su, ll, lu = min(wl, dl), min(wu, du), max(wl, dl), max(wu, du)
        nu = RATIO_SCALE * lu + su - 1
        qu = (RATIO_SCALE * lu + sl - 1) // sl
        specs.append((role, w, d, sl, su, ll, lu, nu, qu))
    # Conservative int64 admission: covers variable-domain sums, linear
    # activities AND division's q*s range, including unsupported huge domains.
    magnitude = sum(max(abs(x) for x in v.domain) for v in m.proto.variables)
    magnitude += sum(su + lu + nu + qu for _, _, _, _, su, _, lu, nu, qu in specs)
    magnitude += max(s[-1] for s in specs)
    activities = [4 * nu for *_, nu, qu in specs] + [
        qu * su for _, _, _, _, su, _, _, _, qu in specs
    ]
    if max([4 * magnitude, *activities]) > (1 << 63) - 1:
        raise LayoutAuthorityError("STAGE_B_BALANCED_INT64_OVERFLOW")
    context.ledger.charge("STAGE_B_BALANCED_DEFINITIONS", 3 * 8 + 3)
    ratios = []
    for role, w, d, sl, su, ll, lu, nu, qu in specs:
        short = m.new_int_var(sl, su, "balanced_shape_" + role + "_short")
        long = m.new_int_var(ll, lu, "balanced_shape_" + role + "_long")
        numerator = m.new_int_var(
            RATIO_SCALE * ll + sl - 1, nu, "balanced_shape_" + role + "_numerator"
        )
        ratio = m.new_int_var(RATIO_SCALE, qu, "balanced_shape_" + role + "_ceil_ratio")
        m.add_min_equality(short, [w, d])
        m.add_max_equality(long, [w, d])
        m.add(numerator == RATIO_SCALE * long + short - 1)
        m.add_division_equality(ratio, numerator, short)
        ratios.append(ratio)
    worst = m.new_int_var(RATIO_SCALE, max(s[-1] for s in specs), "balanced_shape_worst")
    m.add_max_equality(worst, ratios)
    m.minimize(worst)
    return {
        "policy": SHAPE_POLICY,
        "policy_hash": SHAPE_POLICY_HASH,
        "strategy": "BALANCED_FUNCTIONAL_SHAPE",
        "proxy": "MAX_CEIL_1000_TIMES_PHYSICAL_ASPECT",
        "ratio_scale": RATIO_SCALE,
        "ratio_error_strict_upper_bound": "1/1000",
        "target_roles": list(FUNCTIONAL_SHAPE_ROLES),
        "source_p1_handoff_hash": context.binding.p1_handoff_hash,
        "changes_engineering_feasible_domain": False,
        "individual_nonworsening_guaranteed_by_objective": False,
        "exact_comparison_required": True,
        "coating_process": "PACKAGING_BOX_FILM_SEALING",
        "functional_fit_status": "INPUT_REQUIRED",
        "real_layout_quality_improved": False,
    }


def balanced_quality_snapshot(candidate: dict[str, Any], composition_hash: str) -> dict[str, Any]:
    """Read the original diagnostic geometry/routes; do not create another validator."""
    actual_composition = candidate.get("source_composition_hash")
    if actual_composition is not None and actual_composition != composition_hash:
        raise LayoutAuthorityError("STAGE_B_BALANCED_CANDIDATE_SOURCE_MISMATCH")
    facts = _quality_facts(candidate)
    metrics = facts["metrics"]
    metrics["worst_room_aspect"] = str(
        max(Fraction(metrics[r + "_aspect"]) for r in FUNCTIONAL_SHAPE_ROLES)
    )
    footprint = facts["construction_facts"]["footprint"]
    metrics["footprint_reflex_corner_count"] = (
        footprint["reflex_corner_count"] if footprint else None
    )
    ingress = [
        r
        for r in facts["construction_facts"]["actual_access_route_facts"]
        if r["from_ref"] == "main_entrance" and r["to_ref"] == "changing_room"
    ]
    if (
        len(ingress) != 1
        or ingress[0]["status"] != "PASS"
        or not ingress[0]["reported_route_length_matches"]
        or not ingress[0]["centerline"]
    ):
        metrics["personnel_route_m"] = metrics["personnel_route_turns"] = None
    return {
        "candidate_hash": candidate["canonical_result_hash"],
        "geometry_hash": candidate["proposal"]["geometry_hash"],
        "composition_hash": actual_composition,
        "authority_hashes": {
            k: candidate.get(k)
            for k in (
                "source_zone_plan_hash",
                "source_p1_handoff_hash",
                "source_site_geometry_hash",
            )
        },
        "resource_ledger": deepcopy(candidate["resource_ledger"]),
        **facts,
    }


def _metric(value: Any, name: str) -> Fraction | None:
    if value is None or isinstance(value, (bool, float)):
        return None
    try:
        exact = Fraction(str(value))
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    if exact < 0 or (name.endswith("aspect") and exact < 1):
        return None
    if name.endswith(("count", "turns")) and exact.denominator != 1:
        return None
    if name == "footprint_perimeter_m" and exact == 0:
        return None
    return exact


def compare_balanced_quality(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Exact nine-metric partial order, not a score, selector or engineering approval."""
    metrics = [
        row["metrics"] if isinstance(row.get("metrics"), dict) else {} for row in (before, after)
    ]
    parsed = [{k: _metric(row.get(k), k) for k in COMPARISON_METRICS} for row in metrics]
    missing = sorted(k for k in COMPARISON_METRICS if any(row[k] is None for row in parsed))
    for row in parsed:
        aspects = [row[r + "_aspect"] for r in FUNCTIONAL_SHAPE_ROLES]
        known = [v for v in aspects if v is not None]
        if len(known) == len(aspects) and row["worst_room_aspect"] != max(known):
            missing.append("worst_room_aspect")
    organizations = [
        row["functional_diversity"] if isinstance(row.get("functional_diversity"), dict) else {}
        for row in (before, after)
    ]
    identities = [before.get("composition_hash"), after.get("composition_hash")]
    authority = [
        row["authority_hashes"] if isinstance(row.get("authority_hashes"), dict) else {}
        for row in (before, after)
    ]
    identity_complete = all(isinstance(v, str) and v for v in identities) and all(
        row.get("countable") is True
        and isinstance(row.get("meaningful_construction_hash"), str)
        and row["meaningful_construction_hash"]
        for row in organizations
    )
    authority_complete = all(
        all(
            isinstance(row.get(k), str) and row[k]
            for k in (
                "source_zone_plan_hash",
                "source_p1_handoff_hash",
                "source_site_geometry_hash",
            )
        )
        for row in authority
    )
    same_structure = (
        identities[0] == identities[1]
        and organizations[0].get("meaningful_construction_hash")
        == organizations[1].get("meaningful_construction_hash")
        and authority[0] == authority[1]
    )
    directions = {}
    for key in COMPARISON_METRICS:
        baseline, candidate = parsed[0][key], parsed[1][key]
        if baseline is not None and candidate is not None:
            directions[key] = (candidate > baseline) - (candidate < baseline)
    status = (
        "INCOMPLETE_EVIDENCE"
        if not identity_complete or not authority_complete
        else "NOT_COMPARABLE_STRUCTURE"
        if not same_structure
        else "INCOMPLETE_EVIDENCE"
        if missing
        else "GEOMETRIC_PARETO_IMPROVEMENT"
        if max(directions.values()) <= 0 and min(directions.values()) < 0
        else "QUALITY_TRADEOFF"
        if min(directions.values()) < 0 < max(directions.values())
        else "NO_MEASURABLE_IMPROVEMENT"
    )
    return {
        "status": status,
        "comparison_policy": COMPARISON_POLICY,
        "baseline_candidate_hash": before.get("candidate_hash"),
        "candidate_hash": after.get("candidate_hash"),
        "metric_directions_minus_one_better": directions,
        "missing_or_invalid_metrics": sorted(set(missing)),
        "same_handoff_and_meaningful_organization": bool(same_structure and identity_complete),
        "footprint_area_facts_only": {
            "baseline_m2": metrics[0].get("footprint_area_m2"),
            "candidate_m2": metrics[1].get("footprint_area_m2"),
        },
        "baseline_retained": True,
        "overall_quality_improvement_claimed": False,
        "formal_quality_acceptance": False,
        "automatic_production_selection": False,
    }


class _FirstImprovingWitness(cp_model.CpSolverSolutionCallback):
    """Scalar search observation only; no export, cuts or engineering acceptance."""

    def __init__(self, proxy: Any, baseline: int, charge: Any) -> None:
        super().__init__()
        self.proxy, self.baseline, self.charge = proxy, baseline, charge
        self.solution_count = 0
        self.first_solution_seconds: float | None = None
        self.feedback_seconds: float | None = None
        self.feedback_proxy: int | None = None

    def on_solution_callback(self) -> None:
        self.solution_count += 1
        self.charge("STAGE_B_BALANCED_FEEDBACK_OBSERVATION", 1)
        if self.first_solution_seconds is None:
            self.first_solution_seconds = self.wall_time
        value = self.value(self.proxy)
        if value < self.baseline:
            self.feedback_seconds, self.feedback_proxy = self.wall_time, value
            self.stop_search()  # Return through normal Solve accounting/validators.

    def receipt(self) -> dict[str, Any]:
        return {
            "policy_hash": FEEDBACK_POLICY_HASH,
            "baseline_proxy": self.baseline,
            "solution_count": self.solution_count,
            "first_solution_seconds": self.first_solution_seconds,
            "feedback_seconds": self.feedback_seconds,
            "feedback_proxy": self.feedback_proxy,
            "stop_requested": self.feedback_proxy is not None,
            "engineering_validated": False,
        }


class _BalancedNative(_FeasibilityFirstNative):
    continuation_policy = POLICY
    continuation_policy_hash = POLICY_HASH

    def _solve_with_feedback(
        self,
        context: GlobalGenerationContext,
        solver: cp_model.CpSolver,
        model: cp_model.CpModel,
        phase: str,
    ) -> tuple[Any, dict[str, Any] | None]:
        if not self.improving or phase != "ALL_ROOMS_ALL_ACCESS":
            return super()._solve_with_feedback(context, solver, model, phase)
        if model is not getattr(self, "_feedback_model", None):
            raise LayoutAuthorityError("STAGE_B_BALANCED_FEEDBACK_MODEL_MISMATCH")
        proxy = model.get_int_var_from_proto_index(self._feedback_proxy_index)
        callback = _FirstImprovingWitness(proxy, self._baseline_proxy, context.ledger.charge)
        status = solver.solve(model, callback)
        return status, callback.receipt()  # Never rewrite FEASIBLE/OPTIMAL/UNKNOWN.

    def begin_improvement(self, model: Any, context: Any, solver: Any) -> dict[str, Any]:
        # Capture exact incumbent dimensions before adding proxy variables.
        # This is a callback stop preference, NEVER a new feasibility cut.
        self.remaining_share(context)
        context.ledger.remaining_solver_seconds()
        context.ledger.charge("STAGE_B_BALANCED_FEEDBACK_BASELINE", 6)
        ratios = []
        for role in FUNCTIONAL_SHAPE_ROLES:
            dimensions = [model.rooms[role][side] for side in ("w", "d")]
            if [v.name for v in dimensions] != [role + "_physical_" + s for s in ("w", "d")]:
                raise LayoutAuthorityError("STAGE_B_BALANCED_FEEDBACK_DIMENSION_MISMATCH")
            w, d = (solver.value(v) for v in dimensions)
            if min(w, d) <= 0:
                raise LayoutAuthorityError("STAGE_B_BALANCED_FEEDBACK_INVALID_BASELINE")
            ratios.append((RATIO_SCALE * max(w, d) + min(w, d) - 1) // min(w, d))
        receipt = super().begin_improvement(model, context, solver)
        self._feedback_model = model.m
        self._baseline_proxy = max(ratios)
        self._feedback_proxy_index = len(model.m.proto.variables) - 1
        if model.m.proto.variables[self._feedback_proxy_index].name != "balanced_shape_worst":
            raise LayoutAuthorityError("STAGE_B_BALANCED_FEEDBACK_PROXY_MISMATCH")
        return {
            **receipt,
            "native_feedback_policy": FEEDBACK_POLICY,
            "native_feedback_policy_hash": FEEDBACK_POLICY_HASH,
            "baseline_proxy": self._baseline_proxy,
            "unknown_ends_stream_without_retry": True,
            "cross_solve_learning_preserved": False,
        }

    def _apply_improvement_guidance(self, model: Any, context: Any) -> dict[str, Any]:
        return apply_balanced_shape_guidance(model, context)

    def refresh_validated_hint(self, model: Any, context: Any, solver: Any) -> dict[str, Any]:
        """Only the stream's independently accepted current assignment may guide us."""
        if not self.improving or model.m is not self._feedback_model:
            raise LayoutAuthorityError("STAGE_B_BALANCED_FEEDBACK_MODEL_MISMATCH")
        variables = union_input_variables(model, solver)
        values = [solver.value(v) for v in variables]
        proxy = model.m.get_int_var_from_proto_index(self._feedback_proxy_index)
        incumbent = solver.value(proxy)
        context.ledger.charge("STAGE_B_VALIDATED_PARETO_HINT", len(variables) + 1)
        model.m.clear_hints()
        for variable, value in zip(variables, values, strict=True):
            model.m.add_hint(variable, value)
        previous = self._baseline_proxy
        self._baseline_proxy = incumbent
        return {
            "policy_hash": POLICY_HASH,
            "hint_source": "CURRENT_EXECUTION_INDEPENDENTLY_VALIDATED_PARETO_INCUMBENT",
            "hint_variables": len(variables),
            "previous_feedback_proxy": previous,
            "feedback_proxy": incumbent,
            "hard_domain_changed": False,
            "original_baseline_preserved": True,
        }


class StageBBalancedQualityFairSearchSolver(StageBFeasibilityFirstFairSearchSolver):
    """Only a future independently bound decision can authorize this strategy."""

    def start_handoff(self, ledger: Any, remaining_handoffs: int) -> None:
        self.native = _BalancedNative(ledger, remaining_handoffs)
        self.baseline = None
        self.guidance_incumbent: dict[str, Any] | None = None
        self.pending_guidance: dict[str, Any] | None = None

    def _continuation_options(self, context: Any) -> dict[str, Any]:
        return {
            **super()._continuation_options(context),
            "accepted_continuation_guidance": lambda model, solver: self._refresh_validated_hint(
                model, context, solver
            ),
        }

    def _refresh_validated_hint(
        self, model: Any, context: Any, solver: Any
    ) -> dict[str, Any] | None:
        if self.pending_guidance is None:
            return None
        receipt = cast(_BalancedNative, self.native).refresh_validated_hint(model, context, solver)
        receipt["candidate_hash"] = self.pending_guidance["candidate_hash"]
        self.pending_guidance = None
        return receipt

    def solutions(self, context: Any, handoff: Any) -> Any:
        decision = getattr(context.ledger.execution_authorization, "decision", {})
        if decision.get("balanced_quality_policy_hash") != POLICY_HASH:
            raise LayoutAuthorityError("STAGE_B_BALANCED_BOUND_POLICY_REQUIRED")
        return StageBFairSearchSolver.solutions(self, context, handoff)

    def observe_validated_candidate(
        self, context: Any, handoff: Any, candidate: dict[str, Any], feedback: str
    ) -> None:
        if feedback != "ENGINEERING_ACCEPTED":
            return
        snapshot = balanced_quality_snapshot(candidate, handoff.source_composition_hash)
        if self.baseline is None:
            self.baseline = deepcopy(snapshot)
            self.guidance_incumbent = deepcopy(snapshot)
            comparison = {"status": "BASE_VALID_CANDIDATE_PRESERVED", "baseline": snapshot}
        else:
            comparison = {
                **compare_balanced_quality(self.baseline, snapshot),
                "candidate": snapshot,
            }
        if self.guidance_incumbent is not None and (
            compare_balanced_quality(self.guidance_incumbent, snapshot)["status"]
            == "GEOMETRIC_PARETO_IMPROVEMENT"
        ):
            self.guidance_incumbent = deepcopy(snapshot)
            self.pending_guidance = deepcopy(snapshot)
        context.ledger.execution_authorization.record_enumeration(
            {
                "zone_plan_hash": context.binding.canonical_zone_plan_hash,
                "p1_hash": context.binding.p1_handoff_hash,
                "site_hash": context.binding.site_geometry_hash,
                "composition_hash": handoff.source_composition_hash,
            },
            {"kind": "FEASIBILITY_FIRST_QUALITY_FACTS", "policy_hash": POLICY_HASH, **comparison},
        )
