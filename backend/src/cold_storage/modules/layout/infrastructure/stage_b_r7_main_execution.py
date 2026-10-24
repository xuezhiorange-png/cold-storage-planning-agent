"""Fixed R7 identity on the existing trusted Store/Lease; no Grant auto-issuance."""

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    COMPARISON_POLICY as COMPARISON_POLICY,
)
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    SHAPE_POLICY_HASH as AREA_OBJECTIVE_POLICY_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import FEEDBACK_POLICY_HASH
from cold_storage.modules.layout.infrastructure.stage_b_fair_execution import (
    FairMultiSolutionPoolExecutionStore,
    validate_fair_binding,
)
from cold_storage.modules.layout.infrastructure.stage_b_feasibility_main_execution import (
    CONTRACT as ORIGINAL_CONTRACT,
)
from cold_storage.modules.layout.infrastructure.stage_b_feasibility_main_execution import (
    FeasibilityFirstMainLease,
)
from cold_storage.modules.layout.infrastructure.stage_b_first_feasible_recovery import POLICY_HASH
from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
    FRONTAGE_POLICY_HASH,
    SHAPE_POLICY_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
    POLICY_HASH as PARENT_SEARCH_POLICY_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import _SEAL, PoolLease

TASK = "V2_2_2_STAGE_B_R7_REAL_MAIN_R1"
REFERENCE_HEAD = "aab1bb8dce8acf06379809a4ea15b5b4cea19b06"
# UTF-8/LF public scope, not a Grant or permission to run a future commit.
OWNER_SHA256: str | None = "11aa91474ff6fbafcf2baac6042421abe126bce2d54b97e29a5caf4eca299788"
# Scope literals must not silently follow a future imported policy revision.
BOUND_STRATEGIES = (
    "sha256:e669e1a82f2e59cfa8cda122cda45596ba812e816aec673d4a67b7717e63e458",
    "sha256:5584fd5bb8a833905bc0f441bcdc1da8d9876f619d75b7d9fd948c843a2fd95d",
    "sha256:31d228d6995aa7d2d71fd5a5fe740868aecda89b2526ff88081efb41f4fb80df",
    "sha256:ac9ce2d9b8f6d196705c12f91d28bb113b31ab31eebb4cf79aa319a030e38923",
    "sha256:1fc76233d500120f2b80f44feb6ba557fd1e3181be123b113519d93faa13ba6d",
    "sha256:4341a26ac10e7bca12f53a2a64866908dee10c8e1af516bb0b2e90ba578660a2",
)
CI_IDENTITY: Mapping[str, Any] = MappingProxyType(
    {
        "repository": "xuezhiorange-png/cold-storage-planning-agent",
        "pr_number": 313,
        "head_ref": "codex/stage-b-r7-first-feasible-search-r1",
        "base_ref": "codex/stage-b-r6-frontage-joint-search-r1",
        "base_sha": "83e044686a8cbe180807c1478869207d908f7755",
        "workflow": ".github/workflows/ci.yml",
        "event": "pull_request",
        "required_jobs": (
            "classify-changes",
            "backend-sqlite",
            "backend-postgresql",
            "backend-partition-coverage",
            "frontend",
            "compose-config",
            "release-evidence",
            "recovery-foundation",
            "ci-gate",
        ),
    }
)
CONTRACT: Mapping[str, Any] = MappingProxyType(
    dict(ORIGINAL_CONTRACT, version="stage-b-r7-single-main@1.0.0", task=TASK)
)
CONTRACT_HASH = canonical_hash(dict(CONTRACT))


def owner_execution_digest() -> str:
    if COMPARISON_POLICY != "same-handoff-nine-metrics-plus-three-area-allocations@1.0.0":
        raise LayoutAuthorityError("R7_SCOPE_COMPARISON_SOURCE_CHANGED")
    if (
        POLICY_HASH,
        PARENT_SEARCH_POLICY_HASH,
        SHAPE_POLICY_HASH,
        FRONTAGE_POLICY_HASH,
        AREA_OBJECTIVE_POLICY_HASH,
        FEEDBACK_POLICY_HASH,
    ) != BOUND_STRATEGIES:
        raise LayoutAuthorityError("R7_SCOPE_POLICY_SOURCE_CHANGED")
    if (
        not isinstance(OWNER_SHA256, str)
        or len(OWNER_SHA256) != 64
        or any(c not in "0123456789abcdef" for c in OWNER_SHA256)
    ):
        raise LayoutAuthorityError("R7_OWNER_EXECUTION_NOT_PINNED")
    return OWNER_SHA256


def main_binding(common: Mapping[str, Any]) -> dict[str, Any]:
    return dict(
        common,
        balanced_quality_task=TASK,
        balanced_quality_policy_hash=POLICY_HASH,
        balanced_first_stage_policy_hash=SHAPE_POLICY_HASH,
        balanced_shape_policy_hash=SHAPE_POLICY_HASH,
        balanced_feedback_policy_hash=FEEDBACK_POLICY_HASH,
        area_comparison_policy=COMPARISON_POLICY,
        r7_frontage_policy_hash=FRONTAGE_POLICY_HASH,
        r7_solver_class="StageBFirstFeasibleRecoveryFairSolver",
        r7_parent_search_policy_hash=PARENT_SEARCH_POLICY_HASH,
        server_input_identity="FROZEN_20T_REGRESSION_FIXTURE_NOT_XINZHAO",
        area_objective_policy_hash=AREA_OBJECTIVE_POLICY_HASH,
        single_main_contract=dict(CONTRACT),
        single_main_contract_hash=CONTRACT_HASH,
        formal_ci_identity=dict(CI_IDENTITY),
    )


class R7MainStore(FairMultiSolutionPoolExecutionStore):
    def __init__(self, registry: Path) -> None:
        super().__init__(registry, TASK, owner_execution_digest())  # Read-only constructor.

    @staticmethod
    def _validate_binding(binding: Mapping[str, Any]) -> None:
        validate_fair_binding(binding)
        expected = main_binding({})
        if any(
            canonical_hash(binding.get(k)) != canonical_hash(v) for k, v in expected.items()
        ) or not binding.get("runtime_dependency_hash"):
            raise LayoutAuthorityError("R7_MAIN_POLICY_OR_SOURCE_BINDING_REQUIRED")

    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        owner_execution_digest()
        self._validate_binding(binding)
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        owner_execution_digest()
        decision = super()._decision()
        self._validate_binding(decision)
        if decision.get("task_id") != TASK:
            raise LayoutAuthorityError("R7_MAIN_TASK_IDENTITY_MISMATCH")
        return decision

    def require_unclaimed_grant(self) -> None:
        owner_execution_digest()
        if self.root.exists() and any(
            p.name not in {"owner_decision.json", "owner_instruction.json"}
            for p in self.root.iterdir()
        ):
            raise LayoutAuthorityError("R7_EXISTING_FIXED_SLOT_REQUIRES_INSPECTION")
        path = self.root / "owner_decision.json"
        if not path.is_file():
            raise LayoutAuthorityError("R7_PREISSUED_OWNER_GRANT_REQUIRED")
        self.approved_digest = sha256(path.read_bytes()).hexdigest()
        self._decision()

    def validate_existing_binding(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        if sha256(instruction).hexdigest() != owner_execution_digest():
            raise LayoutAuthorityError("R7_OWNER_SOURCE_MISMATCH")
        self._validate_binding(binding)
        decision = self._decision()
        if any(canonical_hash(v) != canonical_hash(decision.get(k)) for k, v in binding.items()):
            raise LayoutAuthorityError("R7_PREISSUED_GRANT_BINDING_MISMATCH")

    def open(self, mode: str) -> StageALedger:
        owner_execution_digest()
        if mode != "MAIN":
            raise LayoutAuthorityError("R7_ONLY_ONE_MAIN_NO_REPLAY_OR_RESUME")
        self.require_unclaimed_grant()
        return super().open(mode)

    def _make_lease(
        self,
        decision: dict[str, Any],
        state: dict[str, Any],
        record: dict[str, Any],
        ledger: StageALedger,
    ) -> PoolLease:
        return R7MainLease(_SEAL, self, decision, state, record, ledger)


class R7MainLease(FeasibilityFirstMainLease):
    """Same cumulative guards and R3 precharge; only expected receipts differ."""

    resource_policy = "STAGE_B_R7_SINGLE_MAIN_RESOURCE_V1"

    def record_enumeration(self, sources: Mapping[str, str], event: Mapping[str, Any]) -> None:
        expected = {
            "FINAL_MODEL_GUIDANCE_APPLIED": SHAPE_POLICY_HASH,
            "BOUNDED_IMPROVEMENT_STARTED": POLICY_HASH,
            "VALIDATED_QUALITY_HINT_UPDATED": PARENT_SEARCH_POLICY_HASH,
        }.get(str(event.get("kind")))
        if (
            expected
            and event.get("guidance", {}).get("policy_hash") != expected
            or event.get("kind") == "FEASIBILITY_FIRST_QUALITY_FACTS"
            and (
                event.get("policy_hash") != POLICY_HASH
                or "candidate" in event
                and event.get("comparison_policy") != COMPARISON_POLICY
            )
        ):
            raise LayoutAuthorityError("R7_MAIN_GUIDANCE_RECEIPT_MISMATCH")
        if event.get("kind") == "FINAL_MODEL_SEARCH_APPLIED":
            raise LayoutAuthorityError("R7_FIRST_STAGE_FRONTAGE_FORBIDDEN")
        if event.get("kind") == "BOUNDED_IMPROVEMENT_STARTED":
            guidance = event.get("guidance", {})
            frontage = guidance.get("frontage_search", {})
            saved = any(
                e.get("kind") == "FEASIBILITY_FIRST_QUALITY_FACTS"
                and e.get("status") == "BASE_VALID_CANDIDATE_PRESERVED"
                and e.get("sources") == dict(sources)
                and e.get("baseline", {}).get("candidate_hash")
                for e in self.record.get("enumeration_events", [])
            )
            if (
                not saved
                or frontage.get("policy_hash") != FRONTAGE_POLICY_HASH
                or frontage.get("hard_domain_changed") is not False
                or guidance.get("frontage_activation") != "AFTER_INDEPENDENT_ENGINEERING_ACCEPTANCE"
                or guidance.get("same_model_reused") is not True
                or type(guidance.get("extra_native_calls")) is not int
                or guidance["extra_native_calls"] != 0
                or guidance.get("hard_domain_changed") is not False
            ):
                raise LayoutAuthorityError("R7_MAIN_DEFERRED_FRONTAGE_RECEIPT_MISMATCH")
        if event.get("kind") == "VALIDATED_SEARCH_FRONTIER_UPDATED":
            previous, current = event.get("previous_proxy"), event.get("search_proxy")
            if (
                event.get("policy_hash") != PARENT_SEARCH_POLICY_HASH
                or type(previous) is not int
                or type(current) is not int
                or not 0 < current < previous
                or not event.get("candidate_hash")
                or event.get("formal_quality_improvement") is not False
                or event.get("hard_domain_changed") is not False
            ):
                raise LayoutAuthorityError("R7_MAIN_FRONTIER_RECEIPT_MISMATCH")
        PoolLease.record_enumeration(self, sources, event)
