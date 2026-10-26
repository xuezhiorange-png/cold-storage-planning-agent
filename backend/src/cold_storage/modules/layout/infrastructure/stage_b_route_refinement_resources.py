"""Optional R7 admission and one local copy per Handoff; unchanged route math.

Only predicted insufficient *remaining* resources become SKIP. Ledger/Lease guard
or precharge failures are never caught: genuine overruns/identity faults remain
fail-closed errors. Reservations are estimates, not billed or newly granted Work.
"""

import time
from collections.abc import Generator
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import (
    POOL_ELAPSED_TARGET,
    POOL_WORK_TARGET,
)
from cold_storage.modules.layout.infrastructure.stage_b_route_refinement import (
    MIN_ROUTE_SECONDS,
    StageBSameProxyRouteRefinementFairSolver,
    _personnel_route,
    _RouteRefinementNative,
)
from cold_storage.modules.layout.infrastructure.stage_b_route_refinement import (
    POLICY_HASH as PARENT_HASH,
)

# Exact operation count of the unchanged six-point total length definition:
# 12 reference visits + 336 variable writes + 594 constraint writes. Checked
# against actual metering for all six complete 20t models (without Native Solve).
LENGTH_DEFINITION_WORK = 942
MAX_COPIES_PER_HANDOFF = 1
PREPARATION_ELAPSED_RESERVE = 0.1
POLICY = "stage-b-r9-route-refinement-resource-admission@1.0.0"
POLICY_HASH = canonical_hash(
    dict(
        version=POLICY,
        parent=PARENT_HASH,
        copies_per_handoff=MAX_COPIES_PER_HANDOFF,
        preflight="COPY_PLUS_KNOWN_DEFINITIONS_AND_SCOPE_UPPER_BOUND",
        length_definition_work=LENGTH_DEFINITION_WORK,
        elapsed_preparation_reserve=PREPARATION_ELAPSED_RESERVE,
        shares="ORIGINAL_NATIVE_ELAPSED_WORK_CHECKED_REMAINING",
        global_limits="ORIGINAL_LEASE_AND_POOL_GUARDS",
        skipped="RETURN_TO_ORIGINAL_ROOM_ENUMERATION",
        failure="NEVER_CONVERT_LEDGER_FAILURE_TO_SKIP",
        route_algorithm="UNCHANGED_PARENT_COPY_MODEL_AND_EXPORTED_LENGTH",
    )
)


class _PreparationSkip(Exception):
    def __init__(self, reason: str, facts: dict[str, Any]) -> None:
        super().__init__(reason)
        self.reason, self.facts = reason, facts


def preparation_work_bound(model: Any, charge: Any = None) -> dict[str, int]:
    """Meter each actual metadata read; no proto-variable scan or solution read.

    The conservative builder bound is NOT charged as construction. A caller may
    stop the planning walk itself when its remaining share cannot pay a read.
    """
    planning = 0

    def read(n: int = 1) -> None:
        nonlocal planning
        if charge is not None:
            charge("ROUTE_RESOURCE_PREFLIGHT_READ", n)
        planning += n

    m = model.m
    read(len(model.routes))
    personnel = _personnel_route(model)
    read(1 + len(personnel["points"]))
    if len(personnel["points"]) != 6 or any(len(p) != 2 for p in personnel["points"]):
        raise LayoutAuthorityError("ROUTE_REFINEMENT_FIVE_SEGMENT_REQUIRED")
    metadata = 0
    for strategy in m.proto.search_strategy:
        read()
        metadata += len(strategy.exprs) + 1
    read(3)
    hints = len(m.proto.solution_hint.vars) if m.proto.has_solution_hint() else 0
    copy_work = len(m.proto.variables) + len(m.proto.constraints) + hints + metadata
    groups = [
        *personnel["points"],
        personnel["from_faces"],
        personnel["to_faces"],
        *personnel["from_offsets"],
        *personnel["to_offsets"],
    ]
    read(len(groups))
    free = 1 + sum(len(group) for group in groups)
    read(3)
    selectors = len(model.interfaces) + len(model.routes)
    enumeration = 5 * len(model.rooms) + 2 * len(model.interfaces)
    for route in model.routes:
        read(2 + len(route["points"]))
        selectors += len(route["direct"])
        enumeration += 1 + max(sum(len(p) for p in route["points"]), len(route["direct"]) + 1)
    references = enumeration + 4 * len(model.rooms)
    scope = free + selectors + enumeration + 2 * references + 1
    return dict(
        copy_work=copy_work,
        scope_work_upper=scope,
        length_definition_work=LENGTH_DEFINITION_WORK,
        objective_work=1,
        required_work_upper=copy_work + scope + LENGTH_DEFINITION_WORK + 1,
        planning_work=planning,
    )


class _ResourceBoundRouteNative(_RouteRefinementNative):
    continuation_policy = POLICY
    continuation_policy_hash = POLICY_HASH

    def _remaining_resources(self, context: Any) -> dict[str, float]:
        ledger = context.ledger
        ledger.guard()  # Genuine overrun/identity/accounting failure propagates.
        global_native = ledger.remaining_solver_seconds()
        used_work = ledger.model_work + ledger.native_host_work
        return dict(
            handoff_work=self.work_share - (used_work - self.work_before),
            global_work=POOL_WORK_TARGET - used_work,
            handoff_native=self.native_share
            - (max(ledger.solver_wall, ledger.solver_monotonic_wall) - self.native_before),
            global_native=global_native,
            handoff_elapsed=self.elapsed_share - (time.monotonic() - self.started),
            global_elapsed=POOL_ELAPSED_TARGET - (time.monotonic() - ledger.started),
            handoff_checked=self.checked_share - (ledger.checked_solutions - self.checked_before),
            global_checked=20 - ledger.checked_solutions,
        )

    def _admit(self, context: Any, required: int = 0) -> dict[str, float]:
        available = self._remaining_resources(context)
        for key in ("handoff_work", "global_work"):
            if available[key] < required:
                raise _PreparationSkip("INSUFFICIENT_" + key.upper(), available)
        for key in ("handoff_checked", "global_checked"):
            if available[key] < 1:
                raise _PreparationSkip("INSUFFICIENT_" + key.upper(), available)
        for key in ("handoff_native", "global_native"):
            if available[key] <= MIN_ROUTE_SECONDS:
                raise _PreparationSkip("INSUFFICIENT_" + key.upper(), available)
        for key in ("handoff_elapsed", "global_elapsed"):
            if available[key] <= PREPARATION_ELAPSED_RESERVE + MIN_ROUTE_SECONDS:
                raise _PreparationSkip("INSUFFICIENT_" + key.upper(), available)
        return available

    def _build_local_model(self, model: Any, solver: Any, context: Any) -> tuple[Any, Any]:
        def planning_charge(label: str, work: int) -> None:
            self._admit(context, work)
            context.ledger.charge(label, work)

        estimate = preparation_work_bound(model, planning_charge)
        available = self._admit(context, estimate["required_work_upper"])
        # Existing trusted global/task precharge still validates hidden enclosing
        # reservations. It bills nothing and errors are not converted to SKIP.
        context.ledger.precharge_work(estimate["required_work_upper"])
        self._event(
            context,
            "LOCAL_PREPARATION_ADMITTED",
            estimate=estimate,
            available=available,
            resource_policy_hash=POLICY_HASH,
        )
        # Audit itself can consume resources; recheck immediately before copy_from.
        self._admit(context, estimate["required_work_upper"])
        before = context.ledger.model_work + context.ledger.native_host_work
        self._resource_local_sessions = 1
        local, length = super()._build_local_model(model, solver, context)
        actual = context.ledger.model_work + context.ledger.native_host_work - before
        if actual > estimate["required_work_upper"]:
            raise LayoutAuthorityError("ROUTE_PREPARATION_ESTIMATE_UNDERRUN")
        self._resource_local_copies = getattr(self, "_resource_local_copies", 0) + 1
        self._event(
            context,
            "LOCAL_PREPARATION_COMPLETE",
            copy_count=self._resource_local_copies,
            actual_work=actual,
            estimate=estimate,
            resource_policy_hash=POLICY_HASH,
        )
        return local, length

    def refine_routes(
        self, context: Any, model: Any, accepted_solver: Any, record: dict[str, Any]
    ) -> Generator[dict[str, Any], str | None, None]:
        if (
            not self.improving
            or model.m is not self._feedback_model
            or model.c is not context
            or context.ledger is not self.ledger
        ):
            raise LayoutAuthorityError("ROUTE_REFINEMENT_ACCEPTED_SECOND_STAGE_REQUIRED")
        self._route_composition_hash = model.handoff.source_composition_hash
        context.ledger.guard()
        if getattr(self, "_resource_local_sessions", 0) >= MAX_COPIES_PER_HANDOFF:
            self._event(
                context,
                "LOCAL_REFINEMENT_SKIPPED",
                reason="HANDOFF_COPY_LIMIT",
                resource_policy_hash=POLICY_HASH,
            )
            return
        try:
            # The unchanged parent reads/bills four room coordinates before
            # planning the copy. Admit that real operation too, not just copy.
            self._admit(context, 4 * len(model.rooms))
            yield from super().refine_routes(context, model, accepted_solver, record)
        except _PreparationSkip as skip:
            self._event(
                context,
                "LOCAL_REFINEMENT_SKIPPED",
                reason=skip.reason,
                available=skip.facts,
                resource_policy_hash=POLICY_HASH,
            )


class StageBResourceBoundRouteRefinementFairSolver(StageBSameProxyRouteRefinementFairSolver):
    """Explicit new identity; no old Runner, authorization or default is changed."""

    quality_policy_hash = POLICY_HASH
    native_type = _ResourceBoundRouteNative
