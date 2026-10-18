"""Stage B's streaming port on the SAME prepared Stage-A native model engine."""

from collections.abc import Generator
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
    OrToolsGlobalCompositionSolver,
)

POLICY = "stage-b-exact-physical-multi-solution@1.0.0"


class StageBMultiSolutionSolver:
    def solutions(self, context: Any, handoff: Any) -> Generator[dict[str, Any], str | None, None]:
        audit = getattr(context.ledger.execution_authorization, "record_enumeration", None)
        if audit is None:
            raise LayoutAuthorityError("STAGE_B_MULTI_SOLUTION_POOL_LEASE_REQUIRED")
        sources = {
            "zone_plan_hash": context.binding.canonical_zone_plan_hash,
            "p1_hash": context.binding.p1_handoff_hash,
            "site_hash": context.binding.site_geometry_hash,
            "composition_hash": handoff.source_composition_hash,
        }
        return OrToolsGlobalCompositionSolver().iter_solutions(
            context, handoff, event_sink=lambda event: audit(sources, dict(event, policy=POLICY))
        )
