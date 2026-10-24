"""R7 opt-in: defer R6 frontage branching until an engineering-valid baseline.

Keep the Reference model, objective, physical hints, independent frontier,
validators and fair shares. No new solve, physical constraint or default wiring.
"""

from copy import deepcopy
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
    POLICY_HASH as R6_POLICY_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
    StageBFrontageJointSearchFairSolver,
    _FrontageNative,
    apply_frontage_joint_search,
)

POLICY = "stage-b-r7-first-feasible-deferred-frontage@1.0.0"
POLICY_HASH = canonical_hash(
    dict(
        version=POLICY,
        parent=R6_POLICY_HASH,
        first_stage="R5_CORRIDOR_ORDER_WITH_R6_REFERENCE_PREPARATION",
        frontage="ONLY_AFTER_THIS_HANDOFF_INDEPENDENT_ENGINEERING_ACCEPTANCE",
        continuation="SAME_MODEL_PREFIX_BEFORE_ORIGINAL_CORRIDOR_STRATEGY",
        resources="UNCHANGED_CUMULATIVE_LEDGER_NO_EXTRA_NATIVE_CALL",
        quality="UNCHANGED_NINE_AND_TWELVE_METRICS_AND_VALIDATED_FRONTIER",
        activation="EXPLICIT_NEW_POLICY_NOT_HISTORICAL_GRANT_OR_DEFAULT",
    )
)


class _FirstFeasibleRecoveryNative(_FrontageNative):
    continuation_policy = POLICY
    continuation_policy_hash = POLICY_HASH

    def begin_improvement(self, model: Any, context: Any, solver: Any) -> dict[str, Any]:
        if self.improving:
            raise LayoutAuthorityError("R7_FRONTAGE_ALREADY_ACTIVATED")
        # The existing stream calls this only after persisting/yielding its
        # independently accepted baseline. Parent checks share/model/ledger,
        # installs the current-valid physical hint and reuses the same proxy.
        receipt = super().begin_improvement(model, context, solver)
        original_count = len(model.m.proto.search_strategy)
        frontage = apply_frontage_joint_search(model, context)
        # Reorder soft search metadata only. Copy work is real and charged
        # before copying or clearing anything; no learned clauses are assumed.
        strategies = model.m.proto.search_strategy
        work = len(strategies) + sum(len(s.exprs) for s in strategies)
        context.ledger.charge("R7_DEFERRED_STRATEGY_REORDER", work)
        ordered = [deepcopy(s) for s in strategies]
        strategies.clear()
        strategies.extend(ordered[original_count:] + ordered[:original_count])
        return dict(
            receipt,
            frontage_search=frontage,
            frontage_activation="AFTER_INDEPENDENT_ENGINEERING_ACCEPTANCE",
            same_model_reused=True,
            extra_native_calls=0,
            hard_domain_changed=False,
        )


class StageBFirstFeasibleRecoveryFairSolver(StageBFrontageJointSearchFairSolver):
    """Optional R7 port; existing R5/R6 runners and production stay unchanged."""

    quality_policy_hash = POLICY_HASH
    native_type = _FirstFeasibleRecoveryNative

    def _continuation_options(self, context: Any) -> dict[str, Any]:
        options = super()._continuation_options(context)
        # Crucially, no first-stage call to apply_frontage_joint_search. The
        # shared solver still adds its original corridor-MIN strategy itself.
        options.pop("final_model_search")
        return options
