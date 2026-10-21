"""Fixed single MAIN admission, tightening (never replacing) the original PoolLease."""

import time
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_fair_execution import (
    FairMultiSolutionPoolExecutionStore,
    validate_fair_binding,
)
from cold_storage.modules.layout.infrastructure.stage_b_feasibility_first import POLICY_HASH
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import _SEAL, PoolLease
from cold_storage.modules.layout.infrastructure.stage_b_wall_alignment import (
    POLICY_HASH as WALL_HASH,
)

TASK = "V2_2_2_STAGE_B_FEASIBILITY_FIRST_REAL_MAIN_R1"
OWNER_SHA256 = "36002ca6be1ff4e7abf870bc3beb76e1a816f17535afe1ac0506c10c3b38b600"
CONTRACT = MappingProxyType(
    {
        "version": "stage-b-feasibility-first-single-main@1.0.0",
        "task": TASK,
        "modes": ("MAIN",),
        "main_count": 1,
        "native_seconds": 49.9,
        "elapsed_seconds": 85,
        "observable_work": 600_000,
        "memory_bytes": 512 * 1024 * 1024,
        "native_calls": 100,
        "checked_assignments": 20,
        "requirement_host_work": 20_000,
        "native_search_target": 49.8,
        "elapsed_search_target": 84,
    }
)
CONTRACT_HASH = canonical_hash(dict(CONTRACT))


def main_binding(common: Mapping[str, Any]) -> dict[str, Any]:
    return dict(
        common,
        feasibility_first_task=TASK,
        feasibility_first_policy_hash=POLICY_HASH,
        single_main_contract_hash=CONTRACT_HASH,
    )


class FeasibilityFirstMainStore(FairMultiSolutionPoolExecutionStore):
    def __init__(self, registry: Path) -> None:
        super().__init__(registry, TASK, OWNER_SHA256)

    @staticmethod
    def _validate_binding(binding: Mapping[str, Any]) -> None:
        validate_fair_binding(binding)
        if (
            binding.get("feasibility_first_task") != TASK
            or binding.get("feasibility_first_policy_hash") != POLICY_HASH
            or binding.get("single_main_contract_hash") != CONTRACT_HASH
            or not binding.get("runtime_dependency_hash")
        ):
            raise LayoutAuthorityError("FEASIBILITY_MAIN_POLICY_OR_SOURCE_BINDING_REQUIRED")

    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        self._validate_binding(binding)
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        decision = super()._decision()
        self._validate_binding(decision)
        return decision

    def open(self, mode: str) -> StageALedger:
        if mode != "MAIN":
            raise LayoutAuthorityError("FEASIBILITY_ONLY_ONE_MAIN_NO_REPLAY_OR_RESUME")
        # Parent MAIN is ordinal zero only; its exclusive durable claim and
        # missing/incomplete-history checks remain authoritative after a crash.
        return super().open(mode)

    def _make_lease(
        self,
        decision: dict[str, Any],
        state: dict[str, Any],
        record: dict[str, Any],
        ledger: StageALedger,
    ) -> PoolLease:
        return FeasibilityFirstMainLease(_SEAL, self, decision, state, record, ledger)


class FeasibilityFirstMainLease(PoolLease):
    resource_policy = "STAGE_B_FEASIBILITY_FIRST_SINGLE_MAIN_RESOURCE_V1"

    def remaining_solver_seconds(self, ledger: StageALedger) -> float:
        remaining = min(
            super().remaining_solver_seconds(ledger),
            49.8 - max(ledger.solver_wall, ledger.solver_monotonic_wall),
            84 - (time.monotonic() - ledger.started),
        )
        if remaining <= 0:
            raise LayoutAuthorityError("FEASIBILITY_MAIN_SEARCH_ALLOWANCE_LIMIT")
        return remaining

    def guard(self, ledger: StageALedger) -> None:
        super().guard(ledger)
        if (
            max(ledger.solver_wall, ledger.solver_monotonic_wall) > 49.9
            or time.monotonic() - ledger.started > 84
        ):
            raise LayoutAuthorityError("FEASIBILITY_MAIN_RESOURCE_LIMIT")

    def record_enumeration(self, sources: Mapping[str, str], event: Mapping[str, Any]) -> None:
        expected = {
            "FINAL_MODEL_GUIDANCE_APPLIED": WALL_HASH,
            "BOUNDED_IMPROVEMENT_STARTED": POLICY_HASH,
        }.get(str(event.get("kind")))
        if expected and event.get("guidance", {}).get("policy_hash") != expected:
            raise LayoutAuthorityError("FEASIBILITY_MAIN_GUIDANCE_RECEIPT_MISMATCH")
        super().record_enumeration(sources, event)
