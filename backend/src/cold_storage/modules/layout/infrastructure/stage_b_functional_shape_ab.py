"""Fixed two-MAIN A/B admission. No replay, replacement slots or transferable reserves.

Reuse the fair store, sealed PoolLease and original counters. The extra shared
file links exactly two single-use claims; incomplete writes/interruption never
permit another invocation. Filesystem administrators remain outside this trust
boundary, as in the original durable store.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_a_execution import _durable
from cold_storage.modules.layout.infrastructure.stage_b_construction_guidance import (
    FUNCTIONAL_SHAPE_POLICY,
    FUNCTIONAL_SHAPE_POLICY_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_fair_execution import (
    FairMultiSolutionPoolExecutionStore,
    validate_fair_binding,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import _SEAL, PoolLease
from cold_storage.modules.layout.infrastructure.stage_b_wall_alignment import POLICY, POLICY_HASH

TASK = "V2_2_2_STAGE_B_FUNCTIONAL_SHAPE_REAL_AB_MAIN_R1"
OWNER_SHA256 = "a50cf6d8493bd5788e9ff8b92c69edc317c7c647bfc09b62eb24a72ee2a87c31"
SLOTS = MappingProxyType({arm: f"V2_2_2_STAGE_B_AB_R1_ARM_{arm}_MAIN" for arm in ("A", "B")})
ARM_POLICIES = MappingProxyType(
    {
        "A": (POLICY, POLICY_HASH),
        "B": (FUNCTIONAL_SHAPE_POLICY, FUNCTIONAL_SHAPE_POLICY_HASH),
    }
)
CONTRACT = MappingProxyType(
    {
        "version": "stage-b-functional-shape-two-main-ab@1.0.0",
        "order": ("A", "B"),
        "modes": ("MAIN",),
        "native_seconds": 100,
        "elapsed_seconds": 180,
        "work": 1_200_000,
        "memory_bytes": 512 * 1024 * 1024,
        "native_calls": 100,
        "per_arm_native_seconds": 49.9,
        "native_search_target": 49.8,  # identical 0.1s instrumentation margin for both arms
        "elapsed_search_target": 84,
        "per_arm_elapsed_seconds": 85,
        "per_arm_work": 600_000,
        "per_arm_checked_assignments": 20,
        "requirement_host_work": 20_000,
        "reserves_transferable": False,
    }
)
CONTRACT_HASH = canonical_hash(CONTRACT)


def arm_binding(common: Mapping[str, Any], arm: str) -> dict[str, Any]:
    policy, digest = ARM_POLICIES[arm]
    result = dict(
        common,
        ab_experiment=TASK,
        ab_contract_hash=CONTRACT_HASH,
        ab_common_binding_hash=canonical_hash(common),
        ab_arm=arm,
        final_guidance_policy=policy,
        final_guidance_policy_hash=digest,
    )
    if arm == "B":
        result["functional_shape_policy_hash"] = digest
    return result


class FunctionalShapeABStore(FairMultiSolutionPoolExecutionStore):
    def __init__(self, registry: Path, arm: str) -> None:
        if arm not in SLOTS:
            raise LayoutAuthorityError("AB_ARM_NOT_AUTHORIZED")
        self.arm = arm
        self.registry = registry.resolve()
        self.shared_root = self.registry / sha256(TASK.encode()).hexdigest()
        self._shared_cache: dict[str, Any] | None = None
        self._shared_digest: str | None = None
        super().__init__(registry, SLOTS[arm], OWNER_SHA256)

    def _validate_binding(self, binding: Mapping[str, Any]) -> None:
        validate_fair_binding(binding)
        if (
            binding.get("ab_experiment") != TASK
            or binding.get("ab_contract_hash") != CONTRACT_HASH
            or binding.get("ab_arm") != self.arm
            or binding.get("final_guidance_policy") != ARM_POLICIES[self.arm][0]
            or binding.get("final_guidance_policy_hash") != ARM_POLICIES[self.arm][1]
            or not isinstance(binding.get("runtime_dependency_hash"), str)
            or (self.arm == "A" and "functional_shape_policy_hash" in binding)
            or (
                self.arm == "B"
                and binding.get("functional_shape_policy_hash") != FUNCTIONAL_SHAPE_POLICY_HASH
            )
        ):
            raise LayoutAuthorityError("AB_POLICY_OR_BINDING_MISMATCH")
        common = {
            k: v
            for k, v in binding.items()
            if k
            not in {
                "ab_experiment",
                "ab_contract_hash",
                "ab_common_binding_hash",
                "ab_arm",
                "final_guidance_policy",
                "final_guidance_policy_hash",
                "functional_shape_policy_hash",
                "task_id",
                "owner_instruction_sha256",
                "resource_contract",
                "caps",
                "d04_rounds_reset",
                "reserved_per_pool",
            }
        }
        if canonical_hash(common) != binding.get("ab_common_binding_hash"):
            raise LayoutAuthorityError("AB_COMMON_SOURCE_BINDING_CHANGED")

    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        self._validate_binding(binding)
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        result = super()._decision()
        self._validate_binding(result)
        return result

    def shared_state(self) -> dict[str, Any]:
        path = self.shared_root / "shared-resource-ledger.json"
        if not path.is_file():
            raise LayoutAuthorityError("AB_SHARED_HISTORY_REQUIRED")
        raw = path.read_bytes()
        if self._shared_cache is not None:
            if (
                sha256(raw).hexdigest() != self._shared_digest
                or time.monotonic() < self._shared_cache["last_monotonic"]
            ):
                raise LayoutAuthorityError("AB_SHARED_HISTORY_CHANGED")
            return self._shared_cache
        state: dict[str, Any] = json.loads(raw)
        if (
            state["contract_hash"] != CONTRACT_HASH
            or state["owner_sha256"] != OWNER_SHA256
            or state["common_binding_hash"] != self._decision()["ab_common_binding_hash"]
            or time.monotonic() < state["last_monotonic"]
        ):
            raise LayoutAuthorityError("AB_SHARED_HISTORY_UNVERIFIED")
        for arm, digest in state["decisions"].items():
            folder = self.registry / sha256(SLOTS[arm].encode()).hexdigest()
            if sha256((folder / "owner_decision.json").read_bytes()).hexdigest() != digest:
                raise LayoutAuthorityError("AB_PEER_DECISION_CHANGED")
        for arm, row in state["arms"].items():
            if arm == self.arm:
                continue
            folder = self.registry / sha256(SLOTS[arm].encode()).hexdigest()
            peer = json.loads((folder / "task_ledger.json").read_text())
            record = peer["pools"][0]
            counters = record["counters"]
            expected_totals = {
                "native_solver_seconds": max(
                    counters["solver_wall"], counters["solver_monotonic_wall"]
                ),
                "observable_work": counters["model_work"] + counters["native_host_work"],
                "peak_rss_bytes": counters["peak_rss_bytes"],
                "native_calls": len(counters["attempts"]),
                "composition_calls": record["cursor"],
                "candidate_validation_calls": counters["resource_events"].get(
                    "STAGE_B_CANDIDATE_VALIDATION", 0
                ),
            }
            if (
                not peer["accounting_complete"]
                or not row["accounting_complete"]
                or row["counters_hash"] != canonical_hash(counters)
                or record["status"] != row["status"]
                or record["status"] != "COMPLETED"
                or any(row["totals"].get(k) != v for k, v in expected_totals.items())
            ):
                raise LayoutAuthorityError("AB_PEER_CONSUMPTION_UNVERIFIED")
        self._shared_cache = state
        self._shared_digest = sha256(raw).hexdigest()
        return state

    def _save_shared(self, state: dict[str, Any]) -> None:
        path = self.shared_root / "shared-resource-ledger.json"
        _durable(path, state)
        self._shared_cache = state
        self._shared_digest = sha256(path.read_bytes()).hexdigest()

    def open(self, mode: str) -> StageALedger:
        if mode != "MAIN":
            raise LayoutAuthorityError("AB_ONLY_ONE_MAIN_NO_REPLAY")
        decision = self._decision()
        self.shared_root.mkdir(parents=True, exist_ok=True)
        lock = self.shared_root / "active.lock"
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        except FileExistsError as error:
            raise LayoutAuthorityError("AB_EXCLUSIVE_CLAIM_EXISTS") from error
        try:
            state_path = self.shared_root / "shared-resource-ledger.json"
            if not state_path.exists():
                if self.arm != "A" or any(
                    (
                        self.registry / sha256(slot.encode()).hexdigest() / "task_ledger.json"
                    ).exists()
                    or list(
                        (self.registry / sha256(slot.encode()).hexdigest()).glob(
                            "pool_*_claim.json"
                        )
                    )
                    for slot in SLOTS.values()
                ):
                    raise LayoutAuthorityError("AB_SHARED_HISTORY_MISSING_OR_ORDER_INVALID")
                decisions = {}
                for arm, slot in SLOTS.items():
                    path = self.registry / sha256(slot.encode()).hexdigest() / "owner_decision.json"
                    peer = json.loads(path.read_text())
                    if peer["ab_common_binding_hash"] != decision["ab_common_binding_hash"]:
                        raise LayoutAuthorityError("AB_DIFFERENT_PLAN_OR_SOURCE")
                    decisions[arm] = sha256(path.read_bytes()).hexdigest()
                now = time.monotonic()
                _durable(
                    state_path,
                    {
                        "contract_hash": CONTRACT_HASH,
                        "owner_sha256": OWNER_SHA256,
                        "common_binding_hash": decision["ab_common_binding_hash"],
                        "decisions": decisions,
                        "started_monotonic": now,
                        "last_monotonic": now,
                        "arms": {},
                    },
                    exclusive=True,
                )
            shared = self.shared_state()
            if self.arm in shared["arms"] or (
                self.arm == "B" and shared["arms"].get("A", {}).get("status") != "COMPLETED"
            ):
                raise LayoutAuthorityError("AB_SLOT_CONSUMED_OR_OUT_OF_ORDER")
            if self.arm == "B":
                a = shared["arms"]["A"]["totals"]
                if (
                    100 - a["native_solver_seconds"] < 49.9
                    or 180 - (time.monotonic() - shared["started_monotonic"]) < 85
                    or 1_200_000 - a["observable_work"] < 600_000
                    or a["native_calls"] >= 100
                    or a["peak_rss_bytes"] > 512 * 1024 * 1024
                ):
                    raise LayoutAuthorityError("AB_B_NOT_EXECUTED_RESOURCE_LIMIT")
            return super().open("MAIN")
        except BaseException:
            lock.unlink()
            raise

    def _make_lease(
        self,
        decision: dict[str, Any],
        state: dict[str, Any],
        record: dict[str, Any],
        ledger: StageALedger,
    ) -> PoolLease:
        return FunctionalShapeABLease(_SEAL, self, decision, state, record, ledger)


class FunctionalShapeABLease(PoolLease):
    store: FunctionalShapeABStore

    def record_enumeration(self, sources: Mapping[str, str], event: Mapping[str, Any]) -> None:
        if event.get("kind") == "FINAL_MODEL_GUIDANCE_APPLIED":
            receipt = event.get("guidance", {})
            if (
                receipt.get("policy") != self.decision["final_guidance_policy"]
                or receipt.get("policy_hash") != self.decision["final_guidance_policy_hash"]
            ):
                raise LayoutAuthorityError("AB_ARM_FINAL_GUIDANCE_RECEIPT_MISMATCH")
        super().record_enumeration(sources, event)

    def totals(self) -> dict[str, Any]:
        local = super().totals()
        shared = self.store.shared_state()
        for arm, row in shared["arms"].items():
            if arm == self.store.arm:
                continue
            for k, value in row["totals"].items():
                if k == "peak_rss_bytes":
                    local[k] = max(local[k], value)
                elif k != "elapsed_seconds":
                    local[k] += value
        local["elapsed_seconds"] = time.monotonic() - shared["started_monotonic"]
        return local

    def remaining_solver_seconds(self, ledger: StageALedger) -> float:
        remaining = min(
            super().remaining_solver_seconds(ledger),
            49.8 - max(ledger.solver_wall, ledger.solver_monotonic_wall),
            84 - (time.monotonic() - ledger.started),
        )
        if remaining <= 0:
            raise LayoutAuthorityError("AB_ARM_SEARCH_ALLOWANCE_EXHAUSTED")
        return remaining

    def guard(self, ledger: StageALedger) -> None:
        super().guard(ledger)
        if max(ledger.solver_wall, ledger.solver_monotonic_wall) > 49.9:
            raise LayoutAuthorityError("AB_ARM_NATIVE_RESOURCE_LIMIT")
        if time.monotonic() - ledger.started > 84:
            raise LayoutAuthorityError("AB_ARM_ELAPSED_SEARCH_LIMIT")

    def checkpoint(self, phase: str, snapshot: Mapping[str, Any]) -> None:
        super().checkpoint(phase, snapshot)
        shared = self.store.shared_state()
        shared["arms"][self.store.arm] = {
            "status": self.record["status"],
            "accounting_complete": self.state["accounting_complete"],
            "counters_hash": canonical_hash(self.record["counters"]),
            "totals": super().totals(),
        }
        shared["last_monotonic"] = time.monotonic()
        shared["totals"] = self.totals()
        self.store._save_shared(shared)

    def finish_pool(self, result_hash: str | None = None) -> None:
        super().finish_pool(result_hash)
        (self.store.shared_root / "active.lock").unlink()
