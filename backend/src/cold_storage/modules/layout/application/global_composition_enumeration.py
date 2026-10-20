"""Multiple proposals, one original authority/context admission and one oracle.

The pool owns counting. Rejected/duplicate proposals never become new accepted
quota; every native attempt and every validation still consumes the same ledger.
"""

from collections.abc import Generator, Mapping
from copy import deepcopy
from typing import Any, Protocol

from cold_storage.modules.layout.application.global_composition_pool import _eligible
from cold_storage.modules.layout.application.global_composition_solver import (
    GlobalGenerationContext,
    StageALedger,
    generate_global_composition_candidate,
    validate_generated_global_proposal,
)
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.domain.composition_handoff import (
    StructuralCompositionPlacementHandoffV1,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError


class MultiSolutionSolver(Protocol):
    def solutions(
        self, context: GlobalGenerationContext, handoff: StructuralCompositionPlacementHandoffV1
    ) -> Generator[dict[str, Any], str | None, None]: ...


def resource_interrupted(result: Mapping[str, Any]) -> bool:
    error = result.get("engineering_validation_error", {}).get("code", "")
    codes = [error, *result.get("proposal", {}).get("codes", [])]
    if any(
        word in code for code in codes for word in ("LIMIT", "RESOURCE", "HISTORY", "ALLOWANCE")
    ):
        return True
    return any(
        row.get("status") == "RESOURCE_INTERRUPTED"
        for row in result.get("engineering_validation", {}).get("access_results", [])
        if row.get("flow_kind") != "TRUCK"
    )


def generate_global_composition_candidates(
    plan: Mapping[str, Any],
    p1: Mapping[str, Any],
    site: ValidatedSiteGeometryV1,
    *,
    solver: MultiSolutionSolver,
    composition_identity: str,
    execution_ledger: StageALedger,
) -> Generator[dict[str, Any], None, None]:
    ledger = execution_ledger
    audit = getattr(ledger.execution_authorization, "record_enumeration", None)
    if audit is None:
        raise LayoutAuthorityError("STAGE_B_MULTI_SOLUTION_POOL_LEASE_REQUIRED")

    class Capture:
        stream: Generator[dict[str, Any], str | None, None] | None = None
        context: GlobalGenerationContext
        handoff: StructuralCompositionPlacementHandoffV1

        def solve(self, context: GlobalGenerationContext, handoff: Any) -> dict[str, Any]:
            self.context, self.handoff = context, handoff
            self.stream = solver.solutions(context, handoff)
            proposal = next(self.stream)
            if proposal.get("zones"):
                ledger.charge("STAGE_B_CANDIDATE_VALIDATION", 1)
                ledger.checkpoint("STAGE_B_CANDIDATE_VALIDATION_STARTED")
            return proposal

    capture = Capture()
    try:
        # Sole begin(): trusted source binding and context creation are unchanged.
        current = generate_global_composition_candidate(
            plan,
            p1,
            site,
            solver=capture,
            composition_identity=composition_identity,
            execution_ledger=ledger,
        )
        while True:
            frozen = deepcopy(current)
            sources = {
                "zone_plan_hash": current["source_zone_plan_hash"],
                "p1_hash": current["source_p1_handoff_hash"],
                "site_hash": current["source_site_geometry_hash"],
                "composition_hash": current["source_composition_hash"],
            }
            audit(sources, {"kind": "VALIDATION_RESULT", "candidate_result": frozen})
            yield frozen
            # Resource/unknown native facts may not be cut or blindly retried.
            if resource_interrupted(current) or not current["proposal"].get("zones"):
                return
            assert capture.stream is not None
            identities = {
                r["identity"]
                for r in capture.context.binding.access_requirements
                if r["flow_kind"] != "TRUCK"
            }
            feedback = (
                "ENGINEERING_ACCEPTED" if _eligible(current, identities) else "EXAMINED_WITNESS"
            )
            # Optional internal diagnostics run AFTER the immutable validation
            # result was audited/yielded, never instead of the engineering oracle.
            observe = getattr(solver, "observe_validated_candidate", None)
            if callable(observe):
                observe(capture.context, capture.handoff, deepcopy(current), feedback)
            try:
                proposal = capture.stream.send(feedback)
            except StopIteration:
                return
            if proposal.get("zones"):
                ledger.charge("STAGE_B_CANDIDATE_VALIDATION", 1)
                ledger.checkpoint("STAGE_B_CANDIDATE_VALIDATION_STARTED")
            current = validate_generated_global_proposal(
                plan, p1, site, capture.context, capture.handoff, proposal
            )
    finally:
        if capture.stream is not None:
            capture.stream.close()
        ledger.checkpoint("STAGE_B_ENUMERATION_RETURNED_OR_INTERRUPTED")
