"""Explicit R5 preference: demand-normalized compactness, not an area Authority.

For physical sides w,d and P1 demand A, (w+d)^2/(4*A) equals allocation
ratio times (aspect+2+1/aspect)/4. It penalizes both oversized squares and
slender rooms without inventing weights or changing physical feasibility.
"""

from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction
from typing import Any, cast

from cold_storage.modules.layout.domain.dimensioning import (
    REPORTED_AREA_SOURCE,
    LayoutAuthorityError,
    canonical_hash,
)
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    FEEDBACK_POLICY_HASH,
    StageBBalancedQualityFairSearchSolver,
    _BalancedNative,
    balanced_quality_snapshot,
    compare_balanced_quality,
)
from cold_storage.modules.layout.infrastructure.stage_b_construction_guidance import (
    FUNCTIONAL_SHAPE_ROLES,
)
from cold_storage.modules.layout.infrastructure.stage_b_feasibility_first import (
    _FeasibilityFirstNative,
)

SCALE = 1000  # Representation precision, not an engineering acceptance threshold.
SHAPE_POLICY = "stage-b-demand-normalized-semiperimeter-square@1.0.0"
SHAPE_POLICY_HASH = canonical_hash(
    dict(
        version=SHAPE_POLICY,
        roles=FUNCTIONAL_SHAPE_ROLES,
        objective="MAX_CEIL_1000_TIMES_PHYSICAL_SEMIPERIMETER_SQUARED_DIV_4_P1_AREA_MM2",
        demand="SERVER_BOUND_FLEXIBLE_P1_REQUIRED_AREA_CEIL_MM2_AS_EXISTING_MODEL",
        definitions="TOTAL_EXACT_INTEGER_DEFINITIONS_NO_PHYSICAL_CUT",
        weighting="NONE_DEMAND_NORMALIZATION_ONLY",
        scale=SCALE,
    )
)
COMPARISON_POLICY = "same-handoff-nine-metrics-plus-three-area-allocations@1.0.0"
POLICY = "stage-b-area-efficient-first-stage-and-feedback@1.0.0"
POLICY_HASH = canonical_hash(
    dict(
        version=POLICY,
        first_stage=SHAPE_POLICY_HASH,
        continuation="REUSE_SAME_PROXY_MODEL_AND_LEDGER",
        feedback=FEEDBACK_POLICY_HASH,
        comparison=COMPARISON_POLICY,
        hint="ONLY_THIS_EXECUTION_VALIDATED_TWELVE_METRIC_PARETO",
        baseline="PERSIST_BEFORE_TRANSITION_NEVER_REPLACE",
        resources="ORIGINAL_FAIR_SHARE_NO_EXTRA_SOLVE_OR_QUOTA",
        activation="INDEPENDENT_BOUND_POLICY_NO_DEFAULT_OR_RUNNER_CHANGE",
    )
)


def _positive(value: Any) -> Fraction:
    if value is None or isinstance(value, (bool, float)):
        raise LayoutAuthorityError("R5_EXACT_POSITIVE_VALUE_REQUIRED")
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise LayoutAuthorityError("R5_EXACT_POSITIVE_VALUE_REQUIRED") from error
    if result <= 0:
        raise LayoutAuthorityError("R5_EXACT_POSITIVE_VALUE_REQUIRED")
    return result


def _demands(binding: Any) -> dict[str, Fraction]:
    result = {}
    for role in FUNCTIONAL_SHAPE_ROLES:
        auth = binding.dimension_authorities.get(role, {})
        area = auth.get("area_requirement", {})
        if (
            not isinstance(area, Mapping)
            or auth.get("dimension_mode") != "FLEXIBLE_RECTANGLE"
            or auth.get("status") != "FLEXIBLE_AUTHORIZED"
            or auth.get("p2_may_change_required_area") is not False
            or auth.get("p2_may_select_width_depth") is not True
            or area.get("reported_area_source_identity") != REPORTED_AREA_SOURCE
        ):
            raise LayoutAuthorityError("R5_BOUND_FLEXIBLE_P1_REQUIRED")
        required = _positive(auth.get("required_area_m2"))
        if required != _positive(area.get("reported_required_area_m2")):
            raise LayoutAuthorityError("R5_P1_AREA_SOURCE_MISMATCH")
        result[role] = required
    return result


def apply_area_efficient_guidance(model: Any, context: Any) -> dict[str, Any]:
    """Add only total definitions; clear the objective to recover every assignment.

    P1's existing ceil-to-integer-mm2 demand is reused, never redefined. All
    domains are derived from original variables. Unsupported int64 arithmetic
    fails closed before model mutation rather than clamping a physical domain.
    """
    if model.c is not context or model.m.has_objective():
        raise LayoutAuthorityError("R5_CONTEXT_OR_OBJECTIVE_MISMATCH")
    demands = _demands(context.binding)
    m = model.m
    context.ledger.charge("R5_MODEL_FACTS_READ", 3 * len(m.proto.variables) + 3)
    index: dict[str, list[int]] = {}
    magnitude = 0
    for i, var in enumerate(m.proto.variables):
        index.setdefault(var.name, []).append(i)
        magnitude += max(abs(var.domain[0]), abs(var.domain[len(var.domain) - 1]))
    if any(n.startswith("r5_area_") for n in index):
        raise LayoutAuthorityError("R5_DEFINITIONS_ALREADY_PRESENT")
    specs = []
    for role, demand in demands.items():
        names = [role + "_physical_" + side for side in ("w", "d")]
        if any(len(index.get(n, [])) != 1 for n in names):
            raise LayoutAuthorityError("R5_ORIGINAL_PHYSICAL_VARIABLE_REQUIRED")
        w, d = [m.get_int_var_from_proto_index(index[n][0]) for n in names]
        if any(model.rooms[role][s].index != v.index for s, v in (("w", w), ("d", d))):
            raise LayoutAuthorityError("R5_ORIGINAL_PHYSICAL_VARIABLE_REQUIRED")
        wl, wu = w.proto.domain[0], w.proto.domain[len(w.proto.domain) - 1]
        dl, du = d.proto.domain[0], d.proto.domain[len(d.proto.domain) - 1]
        if min(wl, dl) <= 0:
            raise LayoutAuthorityError("R5_POSITIVE_PHYSICAL_DOMAIN_REQUIRED")
        minimum_mm2 = -(-(demand * 1_000_000).numerator // (demand * 1_000_000).denominator)
        denominator = 4 * minimum_mm2
        lo, hi = wl + dl, wu + du
        numerator = SCALE * hi * hi + denominator - 1
        upper = numerator // denominator
        magnitude += hi + hi * hi + numerator + upper
        if max(4 * magnitude, upper * denominator, denominator) > (1 << 63) - 1:
            raise LayoutAuthorityError("R5_INT64_OVERFLOW")
        specs.append((role, w, d, lo, hi, denominator, numerator, upper))
    # Precharge the entire definitional batch before changing the model.
    context.ledger.charge("R5_TOTAL_DEFINITIONS", 27)
    proxies = []
    for role, w, d, lo, hi, denominator, numerator, upper in specs:
        half = m.new_int_var(lo, hi, "r5_area_" + role + "_semiperimeter")
        square = m.new_int_var(lo * lo, hi * hi, "r5_area_" + role + "_square")
        n = m.new_int_var(SCALE * lo * lo + denominator - 1, numerator, "r5_area_" + role + "_n")
        q = m.new_int_var(1, upper, "r5_area_" + role + "_proxy")
        m.add(half == w + d)
        m.add_multiplication_equality(square, [half, half])
        m.add(n == SCALE * square + denominator - 1)
        m.add_division_equality(q, n, denominator)
        proxies.append(q)
    worst = m.new_int_var(1, max(s[-1] for s in specs), "r5_area_worst")
    m.add_max_equality(worst, proxies)
    m.minimize(worst)
    return dict(
        policy=SHAPE_POLICY,
        policy_hash=SHAPE_POLICY_HASH,
        proxy="MAX_DEMAND_NORMALIZED_SEMIPERIMETER_SQUARED",
        source_p1_handoff_hash=context.binding.p1_handoff_hash,
        required_area_m2={r: str(v) for r, v in demands.items()},
        demand_rounding="UNCHANGED_EXISTING_MODEL_CEIL_MM2",
        changes_engineering_feasible_domain=False,
        area_upper_bound_added=False,
        first_solution_termination_unchanged=True,
        optimality_claimed=False,
        topology_pruning=False,
        functional_fit_status="INPUT_REQUIRED",
        real_layout_quality_improved=False,
    )


def area_efficiency_snapshot(
    candidate: dict[str, Any], composition_hash: str, binding: Any
) -> dict[str, Any]:
    """Extend original physical diagnostics with exact, separately visible area facts."""
    if any(
        candidate.get(key) != value
        for key, value in (
            ("source_p1_handoff_hash", binding.p1_handoff_hash),
            ("source_zone_plan_hash", binding.canonical_zone_plan_hash),
            ("source_site_geometry_hash", binding.site_geometry_hash),
        )
    ):
        raise LayoutAuthorityError("R5_CANDIDATE_AUTHORITY_MISMATCH")
    demands = _demands(binding)
    result = balanced_quality_snapshot(candidate, composition_hash)
    rows = {}
    for role, demand in demands.items():
        shape = result["construction_facts"]["room_shapes"][role]
        w, d = (_positive(shape[k]) for k in ("physical_width_m", "physical_depth_m"))
        actual = w * d
        rows[role] = dict(
            required_area_m2=str(demand),
            actual_area_m2=str(actual),
            area_allocation_ratio=str(actual / demand),
            area_overallocation_ratio=str(max(Fraction(0), actual / demand - 1)),
            area_shortfall_m2=str(max(Fraction(0), demand - actual)),
            physical_width_m=str(w),
            physical_depth_m=str(d),
            exact_compactness_proxy=str((w + d) ** 2 / (4 * demand)),
        )
    return dict(
        result,
        area_efficiency=dict(
            source_p1_handoff_hash=binding.p1_handoff_hash,
            area_source=REPORTED_AREA_SOURCE,
            rooms=rows,
            diagnostic_only=True,
            coating_process="PACKAGING_BOX_FILM_SEALING",
        ),
    )


def compare_area_efficient_quality(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Versioned twelve-metric order; original nine-metric comparator is untouched."""
    original = compare_balanced_quality(before, after)
    directions = dict(original["metric_directions_minus_one_better"])
    valid = True
    try:
        for role in FUNCTIONAL_SHAPE_ROLES:
            b, a = (row["area_efficiency"]["rooms"][role] for row in (before, after))
            demand = _positive(b["required_area_m2"])
            if demand != _positive(a["required_area_m2"]):
                valid = False
            ratios = [_positive(row["area_allocation_ratio"]) for row in (b, a)]
            if any(
                ratio < 1 or ratio != _positive(row["actual_area_m2"]) / demand
                for row, ratio in zip((b, a), ratios, strict=True)
            ):
                valid = False
            directions[role + "_area_allocation_ratio"] = (ratios[1] > ratios[0]) - (
                ratios[1] < ratios[0]
            )
        for row in (before, after):
            if (
                row["area_efficiency"].get("area_source") != REPORTED_AREA_SOURCE
                or row["area_efficiency"]["source_p1_handoff_hash"]
                != row["authority_hashes"]["source_p1_handoff_hash"]
            ):
                valid = False
    except (KeyError, TypeError, LayoutAuthorityError):
        valid = False
    if original["status"] in {"INCOMPLETE_EVIDENCE", "NOT_COMPARABLE_STRUCTURE"}:
        status = original["status"]
    elif not valid:
        status = "INCOMPLETE_EVIDENCE"
    elif max(directions.values()) <= 0 and min(directions.values()) < 0:
        status = "GEOMETRIC_PARETO_IMPROVEMENT"
    elif min(directions.values()) < 0 < max(directions.values()):
        status = "QUALITY_TRADEOFF"
    else:
        status = "NO_MEASURABLE_IMPROVEMENT"
    return {
        **original,
        "status": status,
        "comparison_policy": COMPARISON_POLICY,
        "original_nine_metric_comparison": original,
        "metric_directions_minus_one_better": directions,
        "area_evidence_complete": valid,
        "formal_quality_acceptance": False,
    }


class _AreaEfficientNative(_BalancedNative):
    continuation_policy = POLICY
    continuation_policy_hash = POLICY_HASH

    def prepare_first_stage(self, model: Any, context: Any) -> dict[str, Any]:
        receipt = apply_area_efficient_guidance(model, context)
        self._area_model = model.m
        self._feedback_proxy_index = len(model.m.proto.variables) - 1
        self._area_receipt = deepcopy(receipt)
        return receipt

    def _apply_improvement_guidance(self, model: Any, context: Any) -> dict[str, Any]:
        if model.c is not context or model.m is not self._area_model:
            raise LayoutAuthorityError("R5_CONTINUATION_MODEL_MISMATCH")
        proxy = model.m.get_int_var_from_proto_index(self._feedback_proxy_index)
        if proxy.name != "r5_area_worst":
            raise LayoutAuthorityError("R5_CONTINUATION_PROXY_MISMATCH")
        context.ledger.charge("R5_PROXY_REUSE", 1)
        model.m.minimize(proxy)
        return {**self._area_receipt, "definitions_reused": True}

    def begin_improvement(self, model: Any, context: Any, solver: Any) -> dict[str, Any]:
        if model.c is not context or model.m is not self._area_model:
            raise LayoutAuthorityError("R5_CONTINUATION_MODEL_MISMATCH")
        self.remaining_share(context)
        context.ledger.remaining_solver_seconds()
        context.ledger.charge("R5_FEEDBACK_BASELINE", 1)
        proxy = model.m.get_int_var_from_proto_index(self._feedback_proxy_index)
        baseline = solver.value(proxy)
        receipt = _FeasibilityFirstNative.begin_improvement(self, model, context, solver)
        self._feedback_model, self._baseline_proxy = model.m, baseline
        return {
            **receipt,
            "native_feedback_policy_hash": FEEDBACK_POLICY_HASH,
            "baseline_proxy": baseline,
            "unknown_ends_stream_without_retry": True,
            "cross_solve_learning_preserved": False,
        }


class StageBAreaEfficientQualityFairSearchSolver(StageBBalancedQualityFairSearchSolver):
    """R5 opt-in only: old grants/runners/defaults cannot activate this policy."""

    quality_policy_hash = POLICY_HASH
    native_type = _AreaEfficientNative

    def _final_guidance(self, model: Any, context: Any) -> dict[str, Any]:
        return cast(_AreaEfficientNative, self.native).prepare_first_stage(model, context)

    def observe_validated_candidate(
        self, context: Any, handoff: Any, candidate: dict[str, Any], feedback: str
    ) -> None:
        if feedback != "ENGINEERING_ACCEPTED":
            return
        snapshot = area_efficiency_snapshot(
            candidate, handoff.source_composition_hash, context.binding
        )
        if self.baseline is None:
            self.baseline = deepcopy(snapshot)
            self.guidance_incumbent = deepcopy(snapshot)
            comparison = {"status": "BASE_VALID_CANDIDATE_PRESERVED", "baseline": snapshot}
        else:
            comparison = {
                **compare_area_efficient_quality(self.baseline, snapshot),
                "candidate": snapshot,
            }
        if self.guidance_incumbent is not None and (
            compare_area_efficient_quality(self.guidance_incumbent, snapshot)["status"]
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
