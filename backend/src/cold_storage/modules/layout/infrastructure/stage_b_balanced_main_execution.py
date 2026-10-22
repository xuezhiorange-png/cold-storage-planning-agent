"""Hash-bound fixed balanced MAIN adapter; execution requires a preissued Grant."""

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    POLICY_HASH,
    SHAPE_POLICY_HASH,
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
from cold_storage.modules.layout.infrastructure.stage_b_wall_alignment import (
    POLICY_HASH as WALL_HASH,
)

TASK = "V2_2_2_STAGE_B_BALANCED_LAYOUT_REAL_VALIDATION_R1"
# Actual private UTF-8 instruction bytes, pinned under the Owner hash-binding
# task. This digest is NOT Grant issuance or permission to execute this commit.
# Separate final Owner confirmation and exact-head formal PR CI remain required.
OWNER_SHA256: str | None = "83ef14b7f0c62e685cbf3cc8556348616d1645207d027bc16042dd88dc7bb055"
CONTRACT: Mapping[str, Any] = MappingProxyType(
    dict(ORIGINAL_CONTRACT, version="stage-b-balanced-single-main@1.0.0", task=TASK)
)
CONTRACT_HASH = canonical_hash(dict(CONTRACT))


def owner_execution_digest() -> str:
    if (
        not isinstance(OWNER_SHA256, str)
        or len(OWNER_SHA256) != 64
        or any(c not in "0123456789abcdef" for c in OWNER_SHA256)
    ):
        raise LayoutAuthorityError("BALANCED_OWNER_EXECUTION_NOT_PINNED")
    return OWNER_SHA256


def main_binding(common: Mapping[str, Any]) -> dict[str, Any]:
    return dict(
        common,
        balanced_quality_task=TASK,
        balanced_quality_policy_hash=POLICY_HASH,
        balanced_shape_policy_hash=SHAPE_POLICY_HASH,
        single_main_contract=dict(CONTRACT),
        single_main_contract_hash=CONTRACT_HASH,
    )


class BalancedMainStore(FairMultiSolutionPoolExecutionStore):
    def __init__(self, registry: Path) -> None:
        # Constructor is read-only; absent execution authorization cannot approve
        # or open even if a caller copies historical files into the new path.
        super().__init__(registry, TASK, OWNER_SHA256 or "UNISSUED_EXECUTION_AUTHORIZATION")

    @staticmethod
    def _validate_binding(binding: Mapping[str, Any]) -> None:
        validate_fair_binding(binding)
        if (
            binding.get("balanced_quality_task") != TASK
            or binding.get("balanced_quality_policy_hash") != POLICY_HASH
            or binding.get("balanced_shape_policy_hash") != SHAPE_POLICY_HASH
            or binding.get("single_main_contract_hash") != CONTRACT_HASH
            or canonical_hash(binding.get("single_main_contract")) != CONTRACT_HASH
            or not binding.get("runtime_dependency_hash")
        ):
            raise LayoutAuthorityError("BALANCED_MAIN_POLICY_OR_SOURCE_BINDING_REQUIRED")

    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        owner_execution_digest()
        self._validate_binding(binding)
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        owner_execution_digest()
        decision = super()._decision()
        self._validate_binding(decision)
        if decision.get("task_id") != TASK:
            raise LayoutAuthorityError("BALANCED_MAIN_TASK_IDENTITY_MISMATCH")
        return decision

    def require_unclaimed_grant(self) -> None:
        """Read the fixed trusted registry, never issue a Grant from runner input.

        Use the existing filesystem-admin trust boundary and original decision
        verifier (Owner bytes, caps, source HEAD/files/dependencies). Any execution
        residue requires inspection, not a new slot or a reset.
        """
        owner_execution_digest()
        if self.root.exists() and any(
            p.name not in {"owner_decision.json", "owner_instruction.json"}
            for p in self.root.iterdir()
        ):
            raise LayoutAuthorityError("BALANCED_EXISTING_FIXED_SLOT_REQUIRES_INSPECTION")
        path = self.root / "owner_decision.json"
        if not path.is_file():
            raise LayoutAuthorityError("BALANCED_PREISSUED_OWNER_GRANT_REQUIRED")
        self.approved_digest = sha256(path.read_bytes()).hexdigest()
        self._decision()

    def validate_existing_binding(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        """Fresh server-derived binding must equal the previously issued scope."""
        if sha256(instruction).hexdigest() != owner_execution_digest():
            raise LayoutAuthorityError("BALANCED_OWNER_SOURCE_MISMATCH")
        self._validate_binding(binding)
        decision = self._decision()
        if any(
            key not in decision or canonical_hash(value) != canonical_hash(decision[key])
            for key, value in binding.items()
        ):
            raise LayoutAuthorityError("BALANCED_PREISSUED_GRANT_BINDING_MISMATCH")

    def open(self, mode: str) -> StageALedger:
        owner_execution_digest()
        if mode != "MAIN":
            raise LayoutAuthorityError("BALANCED_ONLY_ONE_MAIN_NO_REPLAY_OR_RESUME")
        return super().open(mode)

    def _make_lease(
        self,
        decision: dict[str, Any],
        state: dict[str, Any],
        record: dict[str, Any],
        ledger: StageALedger,
    ) -> PoolLease:
        return BalancedMainLease(_SEAL, self, decision, state, record, ledger)


class BalancedMainLease(FeasibilityFirstMainLease):
    """Reuse the tighter one-MAIN guards, not the old strategy's receipt hash."""

    resource_policy = "STAGE_B_BALANCED_SINGLE_MAIN_RESOURCE_V1"

    def record_enumeration(self, sources: Mapping[str, str], event: Mapping[str, Any]) -> None:
        expected = {
            "FINAL_MODEL_GUIDANCE_APPLIED": WALL_HASH,
            "BOUNDED_IMPROVEMENT_STARTED": POLICY_HASH,
        }.get(str(event.get("kind")))
        if (
            expected
            and event.get("guidance", {}).get("policy_hash") != expected
            or event.get("kind") == "FEASIBILITY_FIRST_QUALITY_FACTS"
            and event.get("policy_hash") != POLICY_HASH
        ):
            raise LayoutAuthorityError("BALANCED_MAIN_GUIDANCE_RECEIPT_MISMATCH")
        PoolLease.record_enumeration(self, sources, event)
