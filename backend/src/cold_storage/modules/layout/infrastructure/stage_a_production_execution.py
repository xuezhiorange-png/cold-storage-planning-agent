"""Owner-bound two-request task accounting, not a new placement algorithm.

Original work counters remain exactly StageALedger.model_work and
StageALedger.native_host_work: their existing observable-work guard is retained.
Native solver seconds, deterministic time, branches and conflicts stay separate.
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
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.stage_a_execution import (
    CAPS,
    OwnerExecutionStore,
    _bytes,
    _durable,
)

RESOURCE_POLICY = "V2_2_2_STAGE_A_CP_SAT_PRODUCTION_RESOURCE_V1"
REQUEST_SECONDS = 100
REPLAY_SECONDS = 90
TASK_SECONDS = 180
TASK_WORK = 1_200_000


class ProductionReplayStore(OwnerExecutionStore):
    """Fixed approved ceilings; callers cannot pass budgets or allocation counts."""

    maximum_instances = 2
    resource_policy = RESOURCE_POLICY
    production_mapping = RESOURCE_POLICY
    approval_caps = MappingProxyType(
        dict(
            CAPS,
            request_solver_seconds=100,
            replay_solver_seconds=90,
            task_solver_seconds=180,
            task_original_work_units=1_200_000,
            max_requests=2,
        )
    )

    def open(self, mode: str, *, historical: Mapping[str, Any] | None = None) -> StageALedger:
        if historical is not None:
            raise LayoutAuthorityError("RESUME_DENIED_UNVERIFIED_HISTORICAL_EXECUTION")
        decision_path = self.root / "owner_decision.json"
        if not decision_path.is_file():
            raise LayoutAuthorityError("EXECUTION_OWNER_DECISION_REQUIRED")
        decision = json.loads(decision_path.read_text())
        if (
            decision.get("owner_instruction_sha256") != self.owner_digest
            or sha256(decision_path.read_bytes()).hexdigest() != self.approved_digest
        ):
            raise LayoutAuthorityError("EXECUTION_OWNER_SOURCE_MISMATCH")
        lock = self.root / "production_active.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError as error:
            raise LayoutAuthorityError("RESUME_DENIED_ACTIVE_EXECUTION") from error
        try:
            path = self.root / "task_resource_ledger.json"
            if not path.exists() and any(self.root.glob("production_claim_*.json")):
                raise LayoutAuthorityError("RESUME_DENIED_LEDGER_MISSING")
            state: dict[str, Any] = (
                json.loads(path.read_text())
                if path.exists()
                else dict(
                    policy=RESOURCE_POLICY,
                    decision_sha256=self.approved_digest,
                    request_count=0,
                    requests=[],
                    accounting_complete=True,
                    active_request=None,
                )
            )
            if state["decision_sha256"] != self.approved_digest:
                raise LayoutAuthorityError("EXECUTION_OWNER_SOURCE_MISMATCH")
            if not state["accounting_complete"]:
                raise LayoutAuthorityError("RESUME_DENIED_NATIVE_COUNTERS_INCOMPLETE")
            ledger = StageALedger()
            if mode == "NEW":
                if state["active_request"] is not None or any(
                    r["status"] != "COMPLETED" for r in state["requests"]
                ):
                    raise LayoutAuthorityError("EXECUTION_PREVIOUS_REQUEST_NOT_COMPLETE")
                if state["request_count"] >= self.maximum_instances:
                    raise LayoutAuthorityError("EXECUTION_NEW_INSTANCE_ALREADY_CONSUMED")
                state["request_count"] += 1
                try:
                    _durable(
                        self.root / f"production_claim_{state['request_count']}.json",
                        {"decision_sha256": self.approved_digest},
                        exclusive=True,
                    )
                except FileExistsError as error:
                    raise LayoutAuthorityError("EXECUTION_NEW_INSTANCE_ALREADY_CONSUMED") from error
                request = dict(
                    identity=f"{self.approved_digest}:{state['request_count']}",
                    status="ALLOCATED",
                    main_invocation_count=0,
                    counters={},
                )
                state["requests"].append(request)
                state["active_request"] = state["request_count"] - 1
            elif mode == "RESUME":
                index = state["active_request"]
                if index is None:
                    raise LayoutAuthorityError("RESUME_DENIED_LEDGER_MISSING")
                request = state["requests"][index]
                saved = request["counters"]
                if request["status"] != "PAUSED" or saved.get("native_solver_active"):
                    raise LayoutAuthorityError("RESUME_DENIED_INCOMPLETE_OR_TERMINAL_EXECUTION")
                for key in (
                    "model_work",
                    "native_host_work",
                    "solver_wall",
                    "solver_monotonic_wall",
                    "attempts",
                    "checked_solutions",
                    "native_requirements",
                    "native_grid_searches",
                    "resource_events",
                    "peak_rss_bytes",
                ):
                    if key in saved:
                        setattr(ledger, key, saved[key])
                ledger.started -= saved["elapsed_seconds"]
            else:
                raise LayoutAuthorityError("EXECUTION_MODE_INVALID")
            lease = _ProductionLease(self, decision, state, request, ledger)
            ledger.execution_authorization = lease
            ledger.solver_history_verified = True
            lease.guard(ledger)
            ledger.checkpoint("EXECUTION_" + mode + "_ADMITTED")
            return ledger
        except BaseException:
            lock.unlink()
            raise


class _ProductionLease:
    resource_policy = RESOURCE_POLICY

    def __init__(
        self,
        store: ProductionReplayStore,
        decision: dict[str, Any],
        state: dict[str, Any],
        request: dict[str, Any],
        ledger: StageALedger,
    ) -> None:
        self.store, self.decision, self.state = store, decision, state
        self.request, self.ledger = request, ledger
        self.closed = False
        previous = state["requests"][:-1]
        self.previous_seconds = sum(self.seconds(r["counters"]) for r in previous)
        self.previous_work = sum(self.work(r["counters"]) for r in previous)

    @staticmethod
    def seconds(counters: Mapping[str, Any]) -> float:
        return float(max(counters.get("solver_wall", 0), counters.get("solver_monotonic_wall", 0)))

    @staticmethod
    def work(counters: Mapping[str, Any]) -> int:
        return int(counters.get("model_work", 0) + counters.get("native_host_work", 0))

    def validate(self, ledger: StageALedger) -> None:
        if ledger is not self.ledger or self.closed:
            raise LayoutAuthorityError("EXECUTION_LEASE_LEDGER_MISMATCH")
        path = self.store.root / "owner_decision.json"
        if sha256(path.read_bytes()).hexdigest() != self.store.approved_digest:
            raise LayoutAuthorityError("EXECUTION_OWNER_SCOPE_CHANGED")
        for path_string, expected in self.decision["source_files"].items():
            if sha256(Path(path_string).read_bytes()).hexdigest() != expected:
                raise LayoutAuthorityError("EXECUTION_SOURCE_FINGERPRINT_CHANGED")
        saved = self.request["counters"]
        for key in ("model_work", "native_host_work", "solver_wall", "solver_monotonic_wall"):
            if getattr(ledger, key) < saved.get(key, 0):
                raise LayoutAuthorityError("EXECUTION_COUNTER_ROLLBACK_DENIED")

    def remaining_solver_seconds(self, ledger: StageALedger) -> float:
        used = max(ledger.solver_wall, ledger.solver_monotonic_wall)
        remaining = min(
            REQUEST_SECONDS - used,
            REPLAY_SECONDS - used,
            TASK_SECONDS - self.previous_seconds - used,
        )
        if remaining <= 0:
            raise LayoutAuthorityError("CP_SAT_CUMULATIVE_ALLOWANCE_EXHAUSTED")
        return remaining

    def precharge_work(self, ledger: StageALedger, n: int) -> None:
        if self.closed or ledger is not self.ledger:
            raise LayoutAuthorityError("EXECUTION_LEASE_LEDGER_MISMATCH")
        if self.previous_work + ledger.model_work + ledger.native_host_work + n > TASK_WORK:
            raise LayoutAuthorityError("STAGE_A_TASK_WORK_LIMIT")

    def guard(self, ledger: StageALedger) -> None:
        if max(ledger.solver_wall, ledger.solver_monotonic_wall) > REPLAY_SECONDS:
            raise LayoutAuthorityError("STAGE_A_REQUEST_SOLVER_LIMIT")
        if self.previous_work + ledger.model_work + ledger.native_host_work > TASK_WORK:
            raise LayoutAuthorityError("STAGE_A_TASK_WORK_LIMIT")
        if (
            self.previous_seconds + max(ledger.solver_wall, ledger.solver_monotonic_wall)
            > TASK_SECONDS
        ):
            raise LayoutAuthorityError("STAGE_A_TASK_SOLVER_LIMIT")

    def begin(self, sources: Mapping[str, str]) -> None:
        self.validate(self.ledger)
        if any(sources[k] != self.decision[k] for k in sources):
            raise LayoutAuthorityError("EXECUTION_AUTHORITY_IDENTITY_MISMATCH")
        if self.request["main_invocation_count"]:
            raise LayoutAuthorityError("EXECUTION_MAIN_INVOCATION_ALREADY_CONSUMED")
        self.request["main_invocation_count"] = 1
        self.request["status"] = "RUNNING"
        self.ledger.checkpoint("MAIN_INVOCATION_STARTED")

    def checkpoint(self, phase: str, snapshot: Mapping[str, Any]) -> None:
        if self.closed:
            raise LayoutAuthorityError("EXECUTION_LEASE_CLOSED")
        old = self.request["counters"]
        for key in (
            "model_work",
            "native_host_work",
            "solver_wall",
            "solver_monotonic_wall",
            "elapsed_seconds",
            "checked_solutions",
        ):
            if snapshot.get(key, 0) < old.get(key, 0):
                raise LayoutAuthorityError("EXECUTION_COUNTER_ROLLBACK_DENIED")
        for key in ("attempts", "native_requirements", "native_grid_searches"):
            if len(snapshot.get(key, [])) < len(old.get(key, [])):
                raise LayoutAuthorityError("EXECUTION_COUNTER_ROLLBACK_DENIED")
        self.request["counters"] = json.loads(_bytes(snapshot))
        self.request["phase"] = phase
        self.state["accounting_complete"] = not snapshot["native_solver_active"]
        self.state["solver_wall_seconds"] = sum(
            self.seconds(r["counters"]) for r in self.state["requests"]
        )
        self.state["original_work_units"] = sum(
            self.work(r["counters"]) for r in self.state["requests"]
        )
        self.state["native_call_count"] = sum(
            len(r["counters"].get("attempts", [])) for r in self.state["requests"]
        )
        self.state["recorded_monotonic"] = time.monotonic()
        with (self.store.root / "task_journal.jsonl").open("ab") as stream:
            stream.write(_bytes(self.state))
            stream.flush()
            os.fsync(stream.fileno())
        _durable(self.store.root / "task_resource_ledger.json", self.state)

    def finish(self, status: str) -> None:
        self.request["status"] = status
        if status != "PAUSED":
            self.state["active_request"] = None
        self.ledger.checkpoint("EXECUTION_" + status)
        self.closed = True
        (self.store.root / "production_active.lock").unlink()

    def pause(self) -> None:
        if self.ledger.native_solver_active:
            raise LayoutAuthorityError("RESUME_DENIED_NATIVE_COUNTERS_INCOMPLETE")
        self.finish("PAUSED")
