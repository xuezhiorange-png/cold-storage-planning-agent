"""Explicit Stage-B search restrictions, never a budget or engineering relaxation."""

import time
from collections.abc import Generator
from typing import Any

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.application.stage_b_search_policy import POLICY_HASH
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
    OrToolsGlobalCompositionSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import (
    POOL_ELAPSED_TARGET,
    POOL_WORK_TARGET,
)

SHARE_STOP = "STAGE_B_HANDOFF_SHARE_EXHAUSTED"


def union_input_variables(model: Any, solver: Any) -> list[Any]:
    """Equal values imply equal *exported* rectangle union, not equal model bbox.

    Physical room boxes determine interface faces. Packaging's selected case
    fixes side/corridor/axis and, when corridor, its centre fixes its envelope.
    Other active corridors retain ALL six points, hence the exact same path
    simplification and strips/corners. All activation flags remain fixed.
    Direct Portal centres add no area; neither they nor nominal rotation may
    rescue this union. A different active path/room/case is NEVER excluded.
    """
    variables = [r[k] for r in model.rooms.values() for k in ("x", "y", "w", "d")]
    for interface in model.interfaces:
        variables.append(interface["active"])
        if solver.boolean_value(interface["active"]) and interface["corridor"]:
            variables.append(interface["center"])
    for route in model.routes:
        variables.append(route["corridor"])
        if solver.boolean_value(route["corridor"]):
            variables.extend(v for point in route["points"] for v in point)
    return list({v.index: v for v in variables if not isinstance(v, int)}.values())


class FairNativeSolver(OrToolsGlobalCompositionSolver):
    def __init__(self, ledger: StageALedger, remaining_handoffs: int) -> None:
        self.ledger = ledger
        self.started = time.monotonic()
        self.native_before = max(ledger.solver_wall, ledger.solver_monotonic_wall)
        self.work_before = ledger.model_work + ledger.native_host_work
        self.checked_before = ledger.checked_solutions
        self.native_share = ledger.remaining_solver_seconds() / remaining_handoffs
        self.work_share = max(0, POOL_WORK_TARGET - self.work_before) / remaining_handoffs
        self.elapsed_share = (
            max(0, POOL_ELAPSED_TARGET - (self.started - ledger.started)) / remaining_handoffs
        )
        remaining_checked = max(0, 20 - ledger.checked_solutions)
        self.checked_share = (
            max(1, remaining_checked // remaining_handoffs) if remaining_checked else 0
        )

    def _run(self, context: Any, model: Any, seconds: float, phase: str) -> Any:
        ledger = context.ledger
        ledger.guard()
        remaining = self.native_share - (
            max(ledger.solver_wall, ledger.solver_monotonic_wall) - self.native_before
        )
        elapsed = self.elapsed_share - (time.monotonic() - self.started)
        if (
            remaining <= 0
            or elapsed <= 0
            or ledger.model_work + ledger.native_host_work - self.work_before >= self.work_share
            or ledger.checked_solutions - self.checked_before >= self.checked_share
        ):
            raise LayoutAuthorityError(SHARE_STOP)
        cap = (
            remaining if phase == "ALL_ROOMS_ALL_ACCESS" else min(remaining, self.native_share / 8)
        )
        return super()._run(context, model, min(seconds, cap, elapsed), phase)


class StageBFairSearchSolver:
    """One preparation/begin per handoff; unused shares carry forward only.

    Local limits are scheduling quanta checked between native calls, not new
    Authority caps. Preprocessing/oracles stay charged to the shared ledger and
    can overrun a local work/time quantum; global protection still fails closed.
    """

    policy_hash = POLICY_HASH

    def start_handoff(self, ledger: StageALedger, remaining_handoffs: int) -> None:
        self.native = FairNativeSolver(ledger, remaining_handoffs)

    def solutions(self, context: Any, handoff: Any) -> Generator[dict[str, Any], str | None, None]:
        audit = getattr(context.ledger.execution_authorization, "record_enumeration", None)
        if audit is None or not hasattr(self, "native") or self.native.ledger is not context.ledger:
            raise LayoutAuthorityError("STAGE_B_FAIR_BOUND_POOL_REQUIRED")
        sources = {
            "zone_plan_hash": context.binding.canonical_zone_plan_hash,
            "p1_hash": context.binding.p1_handoff_hash,
            "site_hash": context.binding.site_geometry_hash,
            "composition_hash": handoff.source_composition_hash,
        }
        audit(
            sources,
            {
                "kind": "HANDOFF_SHARE_STARTED",
                "policy_hash": POLICY_HASH,
                "native_share": self.native.native_share,
                "work_share": self.native.work_share,
                "elapsed_share": self.native.elapsed_share,
                "checked_share": self.native.checked_share,
            },
        )
        return self.native.iter_solutions(
            context,
            handoff,
            event_sink=lambda e: audit(sources, dict(e, policy_hash=POLICY_HASH)),
            topology_variables=union_input_variables,
            propagate_base_infeasible=True,
        )
