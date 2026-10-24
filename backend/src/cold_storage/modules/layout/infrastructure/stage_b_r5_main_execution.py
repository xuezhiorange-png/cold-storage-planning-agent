"""Fixed R5 identity on the existing trusted Store/Lease; no Grant auto-issuance."""

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    COMPARISON_POLICY,
    POLICY_HASH,
    SHAPE_POLICY_HASH,
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
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import _SEAL, PoolLease

TASK = "V2_2_2_STAGE_B_R5_REAL_MAIN_R1"
REFERENCE_HEAD = "5097afc9b5d2910333036c518f4e91f1755b3693"
# UTF-8/LF public scope, not a Grant or permission to run a future commit.
OWNER_SHA256: str | None = "574701eece1f41db140e58c832403f1a7b23f6f8bfdb0302ab903864d6d36448"
# Scope literals must not silently follow a future imported policy revision.
BOUND_STRATEGIES = (
    "sha256:ddccb804958e52c169ad1d1c0c2c6ecc259271e350e23207dba0b1a5e71db0a4",
    "sha256:1fc76233d500120f2b80f44feb6ba557fd1e3181be123b113519d93faa13ba6d",
    "sha256:4341a26ac10e7bca12f53a2a64866908dee10c8e1af516bb0b2e90ba578660a2",
)
CI_IDENTITY: Mapping[str, Any] = MappingProxyType(
    {
        "repository": "xuezhiorange-png/cold-storage-planning-agent",
        "pr_number": 311,
        "head_ref": "codex/stage-b-area-efficient-layout-r5",
        "base_ref": "codex/stage-b-first-stage-quality-r4",
        "base_sha": "4529144b187241702b82eb384887da15aa359aac",
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
    dict(ORIGINAL_CONTRACT, version="stage-b-r5-single-main@1.0.0", task=TASK)
)
CONTRACT_HASH = canonical_hash(dict(CONTRACT))


def owner_execution_digest() -> str:
    if COMPARISON_POLICY != "same-handoff-nine-metrics-plus-three-area-allocations@1.0.0":
        raise LayoutAuthorityError("R5_SCOPE_COMPARISON_SOURCE_CHANGED")
    if (
        POLICY_HASH,
        SHAPE_POLICY_HASH,
        FEEDBACK_POLICY_HASH,
    ) != BOUND_STRATEGIES:
        raise LayoutAuthorityError("R5_SCOPE_POLICY_SOURCE_CHANGED")
    if (
        not isinstance(OWNER_SHA256, str)
        or len(OWNER_SHA256) != 64
        or any(c not in "0123456789abcdef" for c in OWNER_SHA256)
    ):
        raise LayoutAuthorityError("R5_OWNER_EXECUTION_NOT_PINNED")
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
        single_main_contract=dict(CONTRACT),
        single_main_contract_hash=CONTRACT_HASH,
        formal_ci_identity=dict(CI_IDENTITY),
    )


class R5MainStore(FairMultiSolutionPoolExecutionStore):
    def __init__(self, registry: Path) -> None:
        super().__init__(registry, TASK, owner_execution_digest())  # Read-only constructor.

    @staticmethod
    def _validate_binding(binding: Mapping[str, Any]) -> None:
        validate_fair_binding(binding)
        expected = main_binding({})
        if any(
            canonical_hash(binding.get(k)) != canonical_hash(v) for k, v in expected.items()
        ) or not binding.get("runtime_dependency_hash"):
            raise LayoutAuthorityError("R5_MAIN_POLICY_OR_SOURCE_BINDING_REQUIRED")

    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        owner_execution_digest()
        self._validate_binding(binding)
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        owner_execution_digest()
        decision = super()._decision()
        self._validate_binding(decision)
        if decision.get("task_id") != TASK:
            raise LayoutAuthorityError("R5_MAIN_TASK_IDENTITY_MISMATCH")
        return decision

    def require_unclaimed_grant(self) -> None:
        owner_execution_digest()
        if self.root.exists() and any(
            p.name not in {"owner_decision.json", "owner_instruction.json"}
            for p in self.root.iterdir()
        ):
            raise LayoutAuthorityError("R5_EXISTING_FIXED_SLOT_REQUIRES_INSPECTION")
        path = self.root / "owner_decision.json"
        if not path.is_file():
            raise LayoutAuthorityError("R5_PREISSUED_OWNER_GRANT_REQUIRED")
        self.approved_digest = sha256(path.read_bytes()).hexdigest()
        self._decision()

    def validate_existing_binding(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        if sha256(instruction).hexdigest() != owner_execution_digest():
            raise LayoutAuthorityError("R5_OWNER_SOURCE_MISMATCH")
        self._validate_binding(binding)
        decision = self._decision()
        if any(canonical_hash(v) != canonical_hash(decision.get(k)) for k, v in binding.items()):
            raise LayoutAuthorityError("R5_PREISSUED_GRANT_BINDING_MISMATCH")

    def open(self, mode: str) -> StageALedger:
        owner_execution_digest()
        if mode != "MAIN":
            raise LayoutAuthorityError("R5_ONLY_ONE_MAIN_NO_REPLAY_OR_RESUME")
        return super().open(mode)

    def _make_lease(
        self,
        decision: dict[str, Any],
        state: dict[str, Any],
        record: dict[str, Any],
        ledger: StageALedger,
    ) -> PoolLease:
        return R5MainLease(_SEAL, self, decision, state, record, ledger)


class R5MainLease(FeasibilityFirstMainLease):
    """Same cumulative guards and R3 precharge; only expected receipts differ."""

    resource_policy = "STAGE_B_R5_SINGLE_MAIN_RESOURCE_V1"

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
            raise LayoutAuthorityError("R5_MAIN_GUIDANCE_RECEIPT_MISMATCH")
        PoolLease.record_enumeration(self, sources, event)
