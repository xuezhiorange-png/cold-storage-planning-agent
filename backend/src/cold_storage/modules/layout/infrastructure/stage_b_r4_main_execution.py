"""Fixed R4 identity on the existing trusted Store/Lease; no Grant auto-issuance."""

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    FEEDBACK_POLICY_HASH,
    FIRST_STAGE_POLICY_HASH,
    SHAPE_POLICY_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    FIRST_STAGE_QUALITY_POLICY_HASH as POLICY_HASH,
)
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

TASK = "V2_2_2_STAGE_B_R4_REAL_MAIN_R1"
REFERENCE_HEAD = "6b114ac3cda934b07e7d8fbe00d95904e7aa996a"
# UTF-8/LF public scope, not a Grant or permission to run a future commit.
OWNER_SHA256: str | None = "c9c080ed9a9226de4632cec0513a5842c844a3d8621d332a25a78b10224209fd"
# Scope literals must not silently follow a future imported policy revision.
BOUND_STRATEGIES = (
    "sha256:fad41d6d4be18248b9a5ee93e299a591876e40e2422ac0ed5aa3924c2e2e5156",
    "sha256:ce5fd7a398ecfc93ed98ccc9108209fe011402d4dd81b697da9e8b70886fb940",
    "sha256:4f03968760711b1ab090fbcabc2d45ea367428065ec23a47d6986671b7c3ddb0",
    "sha256:4341a26ac10e7bca12f53a2a64866908dee10c8e1af516bb0b2e90ba578660a2",
)
CI_IDENTITY: Mapping[str, Any] = MappingProxyType(
    {
        "repository": "xuezhiorange-png/cold-storage-planning-agent",
        "pr_number": 310,
        "head_ref": "codex/stage-b-first-stage-quality-r4",
        "base_ref": "codex/v2.2.2-p1a-structural-hard-interface-reservation-p0",
        "base_sha": "9c13a134b6008c8960996eedf016dc2b4754a013",
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
    dict(ORIGINAL_CONTRACT, version="stage-b-r4-single-main@1.0.0", task=TASK)
)
CONTRACT_HASH = canonical_hash(dict(CONTRACT))


def owner_execution_digest() -> str:
    if (
        POLICY_HASH,
        FIRST_STAGE_POLICY_HASH,
        SHAPE_POLICY_HASH,
        FEEDBACK_POLICY_HASH,
    ) != BOUND_STRATEGIES:
        raise LayoutAuthorityError("R4_SCOPE_POLICY_SOURCE_CHANGED")
    if (
        not isinstance(OWNER_SHA256, str)
        or len(OWNER_SHA256) != 64
        or any(c not in "0123456789abcdef" for c in OWNER_SHA256)
    ):
        raise LayoutAuthorityError("R4_OWNER_EXECUTION_NOT_PINNED")
    return OWNER_SHA256


def main_binding(common: Mapping[str, Any]) -> dict[str, Any]:
    return dict(
        common,
        balanced_quality_task=TASK,
        balanced_quality_policy_hash=POLICY_HASH,
        balanced_first_stage_policy_hash=FIRST_STAGE_POLICY_HASH,
        balanced_shape_policy_hash=SHAPE_POLICY_HASH,
        balanced_feedback_policy_hash=FEEDBACK_POLICY_HASH,
        single_main_contract=dict(CONTRACT),
        single_main_contract_hash=CONTRACT_HASH,
        formal_ci_identity=dict(CI_IDENTITY),
    )


class R4MainStore(FairMultiSolutionPoolExecutionStore):
    def __init__(self, registry: Path) -> None:
        super().__init__(registry, TASK, owner_execution_digest())  # Read-only constructor.

    @staticmethod
    def _validate_binding(binding: Mapping[str, Any]) -> None:
        validate_fair_binding(binding)
        expected = main_binding({})
        if any(
            canonical_hash(binding.get(k)) != canonical_hash(v) for k, v in expected.items()
        ) or not binding.get("runtime_dependency_hash"):
            raise LayoutAuthorityError("R4_MAIN_POLICY_OR_SOURCE_BINDING_REQUIRED")

    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        owner_execution_digest()
        self._validate_binding(binding)
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        owner_execution_digest()
        decision = super()._decision()
        self._validate_binding(decision)
        if decision.get("task_id") != TASK:
            raise LayoutAuthorityError("R4_MAIN_TASK_IDENTITY_MISMATCH")
        return decision

    def require_unclaimed_grant(self) -> None:
        owner_execution_digest()
        if self.root.exists() and any(
            p.name not in {"owner_decision.json", "owner_instruction.json"}
            for p in self.root.iterdir()
        ):
            raise LayoutAuthorityError("R4_EXISTING_FIXED_SLOT_REQUIRES_INSPECTION")
        path = self.root / "owner_decision.json"
        if not path.is_file():
            raise LayoutAuthorityError("R4_PREISSUED_OWNER_GRANT_REQUIRED")
        self.approved_digest = sha256(path.read_bytes()).hexdigest()
        self._decision()

    def validate_existing_binding(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        if sha256(instruction).hexdigest() != owner_execution_digest():
            raise LayoutAuthorityError("R4_OWNER_SOURCE_MISMATCH")
        self._validate_binding(binding)
        decision = self._decision()
        if any(canonical_hash(v) != canonical_hash(decision.get(k)) for k, v in binding.items()):
            raise LayoutAuthorityError("R4_PREISSUED_GRANT_BINDING_MISMATCH")

    def open(self, mode: str) -> StageALedger:
        owner_execution_digest()
        if mode != "MAIN":
            raise LayoutAuthorityError("R4_ONLY_ONE_MAIN_NO_REPLAY_OR_RESUME")
        return super().open(mode)

    def _make_lease(
        self,
        decision: dict[str, Any],
        state: dict[str, Any],
        record: dict[str, Any],
        ledger: StageALedger,
    ) -> PoolLease:
        return R4MainLease(_SEAL, self, decision, state, record, ledger)


class R4MainLease(FeasibilityFirstMainLease):
    """Same cumulative guards and R3 precharge; only expected receipts differ."""

    resource_policy = "STAGE_B_R4_SINGLE_MAIN_RESOURCE_V1"

    def record_enumeration(self, sources: Mapping[str, str], event: Mapping[str, Any]) -> None:
        expected = {
            "FINAL_MODEL_GUIDANCE_APPLIED": FIRST_STAGE_POLICY_HASH,
            "BOUNDED_IMPROVEMENT_STARTED": POLICY_HASH,
            "VALIDATED_QUALITY_HINT_UPDATED": POLICY_HASH,
        }.get(str(event.get("kind")))
        if (
            expected
            and event.get("guidance", {}).get("policy_hash") != expected
            or event.get("kind") == "FEASIBILITY_FIRST_QUALITY_FACTS"
            and event.get("policy_hash") != POLICY_HASH
        ):
            raise LayoutAuthorityError("R4_MAIN_GUIDANCE_RECEIPT_MISMATCH")
        PoolLease.record_enumeration(self, sources, event)
