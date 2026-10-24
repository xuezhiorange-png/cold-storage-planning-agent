"""Fixed R6 identity on the existing trusted Store/Lease; no Grant auto-issuance."""

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import COMPARISON_POLICY
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
from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
    FRONTAGE_POLICY_HASH,
    POLICY_HASH,
    SHAPE_POLICY_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import _SEAL, PoolLease

TASK = "V2_2_2_STAGE_B_R6_REAL_MAIN_R1"
REFERENCE_HEAD = "5527df6160f1b6e257ce42556691b2b166089ede"
# UTF-8/LF public scope, not a Grant or permission to run a future commit.
OWNER_SHA256: str | None = "fffd389f7b56a2907869ae21bb7ddab20d5adde0637f26aa928dd40ca0975998"
# Scope literals must not silently follow a future imported policy revision.
BOUND_STRATEGIES = (
    "sha256:5584fd5bb8a833905bc0f441bcdc1da8d9876f619d75b7d9fd948c843a2fd95d",
    "sha256:31d228d6995aa7d2d71fd5a5fe740868aecda89b2526ff88081efb41f4fb80df",
    "sha256:ac9ce2d9b8f6d196705c12f91d28bb113b31ab31eebb4cf79aa319a030e38923",
    "sha256:1fc76233d500120f2b80f44feb6ba557fd1e3181be123b113519d93faa13ba6d",
    "sha256:4341a26ac10e7bca12f53a2a64866908dee10c8e1af516bb0b2e90ba578660a2",
)
CI_IDENTITY: Mapping[str, Any] = MappingProxyType(
    {
        "repository": "xuezhiorange-png/cold-storage-planning-agent",
        "pr_number": 312,
        "head_ref": "codex/stage-b-r6-frontage-joint-search-r1",
        "base_ref": "codex/stage-b-area-efficient-layout-r5",
        "base_sha": "f38f98c3a36346bc0837939558ee2d9936b5687b",
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
    dict(ORIGINAL_CONTRACT, version="stage-b-r6-single-main@1.0.0", task=TASK)
)
CONTRACT_HASH = canonical_hash(dict(CONTRACT))


def owner_execution_digest() -> str:
    if COMPARISON_POLICY != "same-handoff-nine-metrics-plus-three-area-allocations@1.0.0":
        raise LayoutAuthorityError("R6_SCOPE_COMPARISON_SOURCE_CHANGED")
    if (
        POLICY_HASH,
        SHAPE_POLICY_HASH,
        FRONTAGE_POLICY_HASH,
        AREA_OBJECTIVE_POLICY_HASH,
        FEEDBACK_POLICY_HASH,
    ) != BOUND_STRATEGIES:
        raise LayoutAuthorityError("R6_SCOPE_POLICY_SOURCE_CHANGED")
    if (
        not isinstance(OWNER_SHA256, str)
        or len(OWNER_SHA256) != 64
        or any(c not in "0123456789abcdef" for c in OWNER_SHA256)
    ):
        raise LayoutAuthorityError("R6_OWNER_EXECUTION_NOT_PINNED")
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
        r6_frontage_policy_hash=FRONTAGE_POLICY_HASH,
        r6_solver_class="StageBFrontageJointSearchFairSolver",
        server_input_identity="FROZEN_20T_REGRESSION_FIXTURE_NOT_XINZHAO",
        area_objective_policy_hash=AREA_OBJECTIVE_POLICY_HASH,
        single_main_contract=dict(CONTRACT),
        single_main_contract_hash=CONTRACT_HASH,
        formal_ci_identity=dict(CI_IDENTITY),
    )


class R6MainStore(FairMultiSolutionPoolExecutionStore):
    def __init__(self, registry: Path) -> None:
        super().__init__(registry, TASK, owner_execution_digest())  # Read-only constructor.

    @staticmethod
    def _validate_binding(binding: Mapping[str, Any]) -> None:
        validate_fair_binding(binding)
        expected = main_binding({})
        if any(
            canonical_hash(binding.get(k)) != canonical_hash(v) for k, v in expected.items()
        ) or not binding.get("runtime_dependency_hash"):
            raise LayoutAuthorityError("R6_MAIN_POLICY_OR_SOURCE_BINDING_REQUIRED")

    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        owner_execution_digest()
        self._validate_binding(binding)
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        owner_execution_digest()
        decision = super()._decision()
        self._validate_binding(decision)
        if decision.get("task_id") != TASK:
            raise LayoutAuthorityError("R6_MAIN_TASK_IDENTITY_MISMATCH")
        return decision

    def require_unclaimed_grant(self) -> None:
        owner_execution_digest()
        if self.root.exists() and any(
            p.name not in {"owner_decision.json", "owner_instruction.json"}
            for p in self.root.iterdir()
        ):
            raise LayoutAuthorityError("R6_EXISTING_FIXED_SLOT_REQUIRES_INSPECTION")
        path = self.root / "owner_decision.json"
        if not path.is_file():
            raise LayoutAuthorityError("R6_PREISSUED_OWNER_GRANT_REQUIRED")
        self.approved_digest = sha256(path.read_bytes()).hexdigest()
        self._decision()

    def validate_existing_binding(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        if sha256(instruction).hexdigest() != owner_execution_digest():
            raise LayoutAuthorityError("R6_OWNER_SOURCE_MISMATCH")
        self._validate_binding(binding)
        decision = self._decision()
        if any(canonical_hash(v) != canonical_hash(decision.get(k)) for k, v in binding.items()):
            raise LayoutAuthorityError("R6_PREISSUED_GRANT_BINDING_MISMATCH")

    def open(self, mode: str) -> StageALedger:
        owner_execution_digest()
        if mode != "MAIN":
            raise LayoutAuthorityError("R6_ONLY_ONE_MAIN_NO_REPLAY_OR_RESUME")
        self.require_unclaimed_grant()
        return super().open(mode)

    def _make_lease(
        self,
        decision: dict[str, Any],
        state: dict[str, Any],
        record: dict[str, Any],
        ledger: StageALedger,
    ) -> PoolLease:
        return R6MainLease(_SEAL, self, decision, state, record, ledger)


class R6MainLease(FeasibilityFirstMainLease):
    """Same cumulative guards and R3 precharge; only expected receipts differ."""

    resource_policy = "STAGE_B_R6_SINGLE_MAIN_RESOURCE_V1"

    def record_enumeration(self, sources: Mapping[str, str], event: Mapping[str, Any]) -> None:
        expected = {
            "FINAL_MODEL_GUIDANCE_APPLIED": SHAPE_POLICY_HASH,
            "BOUNDED_IMPROVEMENT_STARTED": POLICY_HASH,
            "VALIDATED_QUALITY_HINT_UPDATED": POLICY_HASH,
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
            raise LayoutAuthorityError("R6_MAIN_GUIDANCE_RECEIPT_MISMATCH")
        if event.get("kind") == "FINAL_MODEL_SEARCH_APPLIED" and (
            event.get("search", {}).get("policy_hash") != FRONTAGE_POLICY_HASH
            or event.get("search", {}).get("hard_domain_changed") is not False
        ):
            raise LayoutAuthorityError("R6_MAIN_FRONTAGE_RECEIPT_MISMATCH")
        if event.get("kind") == "VALIDATED_SEARCH_FRONTIER_UPDATED":
            previous, current = event.get("previous_proxy"), event.get("search_proxy")
            if (
                event.get("policy_hash") != POLICY_HASH
                or type(previous) is not int
                or type(current) is not int
                or not 0 < current < previous
                or not event.get("candidate_hash")
                or event.get("formal_quality_improvement") is not False
                or event.get("hard_domain_changed") is not False
            ):
                raise LayoutAuthorityError("R6_MAIN_FRONTIER_RECEIPT_MISMATCH")
        PoolLease.record_enumeration(self, sources, event)
