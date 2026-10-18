"""Opt-in construction search preferences, not engineering/quality acceptance.

Definitions extend a model without removing any original physical assignment.
Each phase has ONE declared proxy objective; there is no candidate ranking or
arbitrary weighted quality sum. Inherited first-solution termination remains;
an objective is guidance, not an optimality or real-layout-improvement claim.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import combinations
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.adjacency import PROCESS_FLOW, ZONE_CODES
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
    OrToolsGlobalCompositionSolver,
)

POLICY = "stage-b-phase-construction-guidance@1.0.0"


def apply_construction_guidance(
    model: cp_model.CpModel,
    *,
    phase: str,
    axis: str,
    direction: str,
    flexible_roles: Sequence[str],
    bands: Sequence[Sequence[str]],
    charge: Callable[[str, int], None],
) -> dict[str, Any]:
    """Only definitional variables/constraints and a soft objective are added.

    Bounds are derived from actual variable domains, not room aspect/area caps.
    All preprocessing/definitions are charged to the original model-work ledger.
    Missing model facts fail closed, never silently fall back to a new policy.
    """
    if axis not in ("X", "Y") or direction not in ("POSITIVE", "NEGATIVE"):
        raise LayoutAuthorityError("STAGE_B_GUIDANCE_ORIENTATION_INVALID")
    index: dict[str, list[int]] = {}
    for i, v in enumerate(model.proto.variables):
        index.setdefault(v.name, []).append(i)
    charge("STAGE_B_GUIDANCE_VARIABLE_INDEX", len(model.proto.variables))

    def var(name: str) -> Any:
        if len(index.get(name, [])) != 1:
            raise LayoutAuthorityError("STAGE_B_GUIDANCE_MODEL_FACT_MISSING", name=name)
        return model.get_int_var_from_proto_index(index[name][0])

    # Every base variable has finite authoritative/model bounds. Sum of absolute
    # domain extrema safely bounds the differences/sums below, even at negative origins.
    bound = 1 + sum(max(abs(v.domain[0]), abs(v.domain[-1])) for v in model.proto.variables)
    terms: list[Any] = []

    def absolute(expr: Any) -> None:
        p = model.new_int_var(0, bound, "stage_b_proxy_" + str(len(terms)))
        model.add_abs_equality(p, expr)
        terms.append(p)
        charge("STAGE_B_GUIDANCE_DEFINITIONS", 2)

    if phase == "ALL_ROOM_GEOMETRY_HINT":
        metric = "FLEXIBLE_PHYSICAL_SEMIPERIMETER_MM_NOT_ASPECT_GATE"
        for role in flexible_roles:
            # For a given required area this prefers economical, balanced sides;
            # unlike |w-d| alone it never rewards an arbitrarily enlarged square.
            terms.append(var(role + "_physical_w") + var(role + "_physical_d"))
    elif phase == "ALL_ROOM_MUST_HINT":
        metric = "REVERSE_CENTER_PROGRESS_PROXY_DOUBLED_MM_NOT_BACKTRACK_COUNT"
        sign = 1 if direction == "POSITIVE" else -1
        for a, b in zip(PROCESS_FLOW[:-1], PROCESS_FLOW[1:], strict=True):
            lo, hi = ("_x", "_right") if axis == "X" else ("_y", "_top")
            p = model.new_int_var(0, bound, "stage_b_reverse_" + str(len(terms)))
            model.add_max_equality(
                p, [0, sign * (var(a + lo) + var(a + hi) - var(b + lo) - var(b + hi))]
            )
            terms.append(p)
            charge("STAGE_B_GUIDANCE_DEFINITIONS", 2)
    elif phase == "COMPOSITION_PACKAGING_HINT":
        metric = "HANDOFF_BAND_CROSS_AXIS_LIMIT_MISMATCH_MM_NOT_DEPTH_GATE"
        near, far = ("_y", "_top") if axis == "X" else ("_x", "_right")
        for band in bands:
            for a, b in combinations(band, 2):
                absolute(var(a + near) - var(b + near))
                absolute(var(a + far) - var(b + far))
    elif phase == "ALL_ACCESS_FRESH_HINT_ONLY":
        metric = "MODELED_CORRIDOR_CENTERLINE_LENGTH_MM_NOT_UNION_AREA"
        # Reuse unique, exact min/max endpoint variables of the existing five
        # segments. Inactive routes contribute zero; their unused coordinates
        # do not acquire new restrictions. Packaging's straight gap is separate.
        for name in sorted(index):
            if name.startswith("route") and name.endswith("corridor"):
                ri = name[len("route") : -len("corridor")]
                if not ri.isdigit():
                    continue
                active = var(name)
                p = model.new_int_var(0, bound, "stage_b_length_" + ri)
                length = sum(
                    var(f"r{ri}s{j}high{ax}") - var(f"r{ri}s{j}low{ax}")
                    for j in range(5)
                    for ax in ("x", "y")
                )
                model.add(p == length).only_enforce_if(active)
                model.add(p == 0).only_enforce_if(active.Not())
                terms.append(p)
                charge("STAGE_B_GUIDANCE_DEFINITIONS", 3)
    elif phase == "ALL_ROOMS_ALL_ACCESS":
        metric = "ROOM_ENCLOSING_AXIS_SPAN_MM_NOT_BUILDING_FOOTPRINT"
        for near, far in (("_x", "_right"), ("_y", "_top")):
            low = model.new_int_var(-bound, bound, "stage_b_low" + near)
            high = model.new_int_var(-bound, bound, "stage_b_high" + far)
            model.add_min_equality(low, [var(r + near) for r in ZONE_CODES])
            model.add_max_equality(high, [var(r + far) for r in ZONE_CODES])
            terms.append(high - low)
            charge("STAGE_B_GUIDANCE_DEFINITIONS", 4)
    else:
        raise LayoutAuthorityError("STAGE_B_GUIDANCE_PHASE_UNSUPPORTED", phase=phase)
    model.minimize(sum(terms))
    charge("STAGE_B_GUIDANCE_OBJECTIVE", 1)
    return {
        "policy": POLICY,
        "phase": phase,
        "proxy": metric,
        "term_count": len(terms),
        "preference_status": "ACTIVE_PROXY" if terms else "NOT_APPLICABLE_NO_BOUND_TERMS",
        "changes_engineering_feasible_domain": False,
        "first_solution_termination_unchanged": True,
        "formal_quality_gate": False,
        "process_flow_validated": False,
        "layout_regularity_validated": False,
    }


class _GuidedInvocation(OrToolsGlobalCompositionSolver):
    def __init__(self, handoff: Any) -> None:
        self.handoff = handoff
        self.receipts: list[dict[str, Any]] = []

    def _run(self, context: Any, model: Any, seconds: float, phase: str) -> tuple[Any, Any]:
        guided = model.clone()
        receipt = apply_construction_guidance(
            guided,
            phase=phase,
            axis=self.handoff.process_axis.value,
            direction=self.handoff.process_direction.value,
            flexible_roles=tuple(
                r
                for r, a in context.binding.dimension_authorities.items()
                if a["dimension_mode"] == "FLEXIBLE_RECTANGLE"
            ),
            bands=tuple(
                b.zone_roles
                for b in self.handoff.principal_band_intents
                if b.axis_relation == "ALONG_PROCESS_AXIS"
            ),
            charge=context.ledger.charge,
        )
        self.receipts.append(receipt)
        solver, status = super()._run(context, guided, seconds, phase)
        receipt["solver_status"] = solver.status_name(status)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            receipt["proxy_value"] = solver.objective_value
        return solver, status


class StageBGuidedConstructionSolver:
    """Explicit opt-in solver port; no grant creation, scheduler or Stage-A edits."""

    def solve(self, context: Any, handoff: Any) -> dict[str, Any]:
        invocation = _GuidedInvocation(handoff)
        result = invocation.solve(context, handoff)
        result["construction_guidance"] = {
            "policy": POLICY,
            "phases": invocation.receipts,
            "real_quality_improvement_verified": False,
        }
        return result
