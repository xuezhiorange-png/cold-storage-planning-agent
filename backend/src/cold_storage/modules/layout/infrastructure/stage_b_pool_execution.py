"""One Owner-approved pool and replay, sharing a durable non-refillable task.

Only trusted bootstrap supplies the registry and pinned Owner document digest.
Local filesystem administrators are outside the in-process authority boundary.
Stage A leases and every layout/Access rule remain unchanged.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_a_execution import CAPS as STAGE_A_CAPS
from cold_storage.modules.layout.infrastructure.stage_a_execution import _bytes, _durable

POLICY = "STAGE_B_ONE_POOL_ONE_REPLAY_SHARED_RESOURCE_V1"
CAPS = MappingProxyType(
    {
        **STAGE_A_CAPS,
        "solver_seconds": 100,
        "elapsed_seconds": 180,
        "observable_work": 1_200_000,
        "memory_mib": 512,
        "requirement_host_work": 20_000,
        "pools": 2,
        "compositions_per_pool": 6,
    }
)
# Stricter reservations, not additional Authority or a per-family refill.
POOL_SOLVER_TARGET = 49.9  # shared total still 100; leave a native-timing margin
POOL_ELAPSED_TARGET = 85.0
POOL_WORK_TARGET = 600_000
_SEAL = object()
_SCALARS = (
    "model_work",
    "native_host_work",
    "solver_wall",
    "solver_monotonic_wall",
    "checked_solutions",
    "elapsed_seconds",
    "peak_rss_bytes",
)
_LISTS = ("attempts", "native_requirements", "native_grid_searches")


class PoolExecutionStore:
    """One fixed slot per task, never a slot selected by output/run UUID."""

    def __init__(self, registry: Path, task_id: str, owner_digest: str) -> None:
        self.root = registry.resolve() / sha256(task_id.encode()).hexdigest()
        self.task_id, self.owner_digest = task_id, owner_digest
        self.approved_digest: str | None = None

    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        if (
            sha256(instruction).hexdigest() != self.owner_digest
            or self.task_id not in instruction.decode()
        ):
            raise LayoutAuthorityError("POOL_OWNER_SOURCE_MISMATCH")
        required = {
            "head",
            "repository_root",
            "dependency_file",
            "source_files",
            "dependency_hash",
            "zone_plan_hash",
            "p1_hash",
            "site_hash",
            "schedule_hash",
            "compositions",
            "solver_version",
        }
        if not required <= binding.keys() or len(binding["compositions"]) != 6:
            raise LayoutAuthorityError("POOL_BINDING_INCOMPLETE")
        identities = [c["identity"] for c in binding["compositions"]]
        hashes = [c["composition_hash"] for c in binding["compositions"]]
        if len(set(identities)) != 6 or len(set(hashes)) != 6:
            raise LayoutAuthorityError("POOL_SCHEDULE_INVALID")
        decision = dict(
            binding,
            task_id=self.task_id,
            owner_instruction_sha256=self.owner_digest,
            resource_contract=POLICY,
            caps=dict(CAPS),
            d04_rounds_reset=False,
            reserved_per_pool={
                "solver_target": POOL_SOLVER_TARGET,
                "elapsed_target": POOL_ELAPSED_TARGET,
                "work_target": POOL_WORK_TARGET,
            },
        )
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "owner_decision.json"
        if path.exists():
            if path.read_bytes() != _bytes(decision):
                raise LayoutAuthorityError("POOL_SCOPE_ALREADY_BOUND")
        else:
            _durable(
                self.root / "owner_instruction.json", {"utf8": instruction.decode()}, exclusive=True
            )
            _durable(path, decision, exclusive=True)
        self.approved_digest = sha256(path.read_bytes()).hexdigest()
        self._decision()

    def _decision(self) -> dict[str, Any]:
        path = self.root / "owner_decision.json"
        if not path.is_file() or self.approved_digest != sha256(path.read_bytes()).hexdigest():
            raise LayoutAuthorityError("POOL_OWNER_DECISION_REQUIRED_OR_CHANGED")
        body: dict[str, Any] = json.loads(path.read_text())
        if (
            body["owner_instruction_sha256"] != self.owner_digest
            or body["caps"] != CAPS
            or body["resource_contract"] != POLICY
        ):
            raise LayoutAuthorityError("POOL_OWNER_SOURCE_MISMATCH")
        owner = json.loads((self.root / "owner_instruction.json").read_text())["utf8"].encode()
        if sha256(owner).hexdigest() != self.owner_digest:
            raise LayoutAuthorityError("POOL_OWNER_SOURCE_MISMATCH")
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=body["repository_root"], text=True
        ).strip()
        if (
            head != body["head"]
            or sha256(Path(body["dependency_file"]).read_bytes()).hexdigest()
            != body["dependency_hash"]
        ):
            raise LayoutAuthorityError("POOL_HEAD_OR_DEPENDENCY_CHANGED")
        for path_string, digest in body["source_files"].items():
            if sha256(Path(path_string).read_bytes()).hexdigest() != digest:
                raise LayoutAuthorityError("POOL_SOURCE_CHANGED")
        return body

    def open(self, mode: str) -> StageALedger:
        decision = self._decision()
        if mode not in {"MAIN", "REPLAY"}:
            # No mid-composition retry: its exact accounting/continuation is not supported.
            raise LayoutAuthorityError("POOL_RESUME_DENIED_NO_SAFE_ENTRY")
        lock = self.root / "active.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError as error:
            raise LayoutAuthorityError("POOL_ACTIVE_CLAIM_EXISTS") from error
        try:
            state_path = self.root / "task_ledger.json"
            if not state_path.exists() and any(self.root.glob("pool_*_claim.json")):
                raise LayoutAuthorityError("POOL_HISTORY_MISSING")
            state: dict[str, Any] = (
                json.loads(state_path.read_text())
                if state_path.exists()
                else {
                    "decision_sha256": self.approved_digest,
                    "pools": [],
                    "started_monotonic": time.monotonic(),
                    "accounting_complete": True,
                }
            )
            if state["decision_sha256"] != self.approved_digest or not state["accounting_complete"]:
                raise LayoutAuthorityError("POOL_HISTORY_UNVERIFIED")
            number = len(state["pools"])
            if (
                number >= 2
                or (mode == "MAIN" and number != 0)
                or (
                    mode == "REPLAY" and (number != 1 or state["pools"][0]["status"] != "COMPLETED")
                )
            ):
                raise LayoutAuthorityError("POOL_GRANT_CONSUMED_OR_OUT_OF_ORDER")
            if number and time.monotonic() - state["started_monotonic"] >= 180:
                raise LayoutAuthorityError("REPLAY_NOT_EXECUTED_RESOURCE_LIMIT")
            if time.monotonic() < state["started_monotonic"]:
                raise LayoutAuthorityError("POOL_HISTORY_TIME_UNVERIFIED")
            if number:
                used = state["totals"]
                if (
                    100 - used["native_solver_seconds"] < POOL_SOLVER_TARGET
                    or used["peak_rss_bytes"] > 512 * 1024 * 1024
                    or 180 - (time.monotonic() - state["started_monotonic"]) < POOL_ELAPSED_TARGET
                    or 1_200_000 - used["observable_work"] < POOL_WORK_TARGET
                ):
                    raise LayoutAuthorityError("REPLAY_NOT_EXECUTED_RESOURCE_LIMIT")
            record: dict[str, Any] = {
                "mode": mode,
                "status": "ALLOCATED",
                "cursor": 0,
                "admitted": False,
                "composition_active": False,
                "counters": {},
            }
            _durable(
                self.root / f"pool_{number + 1}_claim.json",
                {"decision_sha256": self.approved_digest, "ordinal": number + 1},
                exclusive=True,
            )
            state["pools"].append(record)
            ledger = StageALedger(solver_history_verified=True)
            lease = PoolLease(_SEAL, self, decision, state, record, ledger)
            ledger.execution_authorization = lease
            ledger.checkpoint("POOL_ALLOCATED")
            return ledger
        except BaseException:
            lock.unlink()
            raise


class PoolLease:
    resource_policy = POLICY

    def __init__(
        self,
        seal: object,
        store: PoolExecutionStore,
        decision: dict[str, Any],
        state: dict[str, Any],
        record: dict[str, Any],
        ledger: StageALedger,
    ) -> None:
        if seal is not _SEAL:
            raise LayoutAuthorityError("POOL_LEASE_NOT_AUTHORITATIVE")
        self.store, self.decision, self.state = store, decision, state
        self.record, self.ledger, self.closed = record, ledger, False

    def validate(self, ledger: StageALedger) -> None:
        if self.closed or ledger is not self.ledger:
            raise LayoutAuthorityError("POOL_LEASE_LEDGER_MISMATCH")
        self.store._decision()
        self._monotonic(self.record["counters"], self._snapshot())

    def _snapshot(self) -> dict[str, Any]:
        return {
            **{k: getattr(self.ledger, k) for k in _SCALARS if k != "elapsed_seconds"},
            "elapsed_seconds": time.monotonic() - self.ledger.started,
            **{k: getattr(self.ledger, k) for k in _LISTS},
            "resource_events": dict(self.ledger.resource_events),
        }

    @staticmethod
    def _monotonic(old: Mapping[str, Any], new: Mapping[str, Any]) -> None:
        if any(new.get(k, 0) < old.get(k, 0) for k in _SCALARS) or any(
            len(new.get(k, [])) < len(old.get(k, [])) for k in _LISTS
        ):
            raise LayoutAuthorityError("POOL_COUNTER_ROLLBACK_DENIED")
        if any(
            new.get("resource_events", {}).get(k, 0) < count
            for k, count in old.get("resource_events", {}).items()
        ):
            raise LayoutAuthorityError("POOL_EVENT_COUNTER_ROLLBACK_DENIED")

    def validate_pool(
        self, ledger: StageALedger, sources: Mapping[str, str], plan: tuple[str, ...]
    ) -> Mapping[str, str]:
        self.validate(ledger)
        expected = tuple(c["identity"] for c in self.decision["compositions"])
        if (
            self.record["admitted"]
            or plan != expected
            or any(sources[k] != self.decision[k] for k in sources)
        ):
            raise LayoutAuthorityError("POOL_PLAN_OR_SOURCE_MISMATCH")
        self.record["admitted"] = True
        ledger.checkpoint("POOL_SCHEDULE_ADMITTED")
        return {
            "decision_sha256": str(self.store.approved_digest),
            "policy": POLICY,
            "owner_instruction_sha256": self.store.owner_digest,
            "head": self.decision["head"],
            "mode": self.record["mode"],
            "task_id": self.store.task_id,
            "source_hash": canonical_hash(self.decision["source_files"]),
        }

    def begin(self, sources: Mapping[str, str]) -> None:
        self.validate(self.ledger)
        cursor = self.record["cursor"]
        if not self.record["admitted"] or self.record["composition_active"] or cursor >= 6:
            raise LayoutAuthorityError("POOL_COMPOSITION_ADMISSION_DENIED")
        expected = self.decision["compositions"][cursor]
        required = {k: self.decision[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
        required["composition_hash"] = expected["composition_hash"]
        if dict(sources) != required:
            raise LayoutAuthorityError("POOL_COMPOSITION_OUT_OF_ORDER_OR_SOURCE_MISMATCH")
        self.record.update(cursor=cursor + 1, composition_active=True, status="RUNNING")
        self.ledger.checkpoint("POOL_COMPOSITION_STARTED")

    def totals(self) -> dict[str, Any]:
        counters = [r["counters"] for r in self.state["pools"][:-1]] + [self._snapshot()]
        return {
            "native_solver_seconds": sum(
                max(c.get("solver_wall", 0), c.get("solver_monotonic_wall", 0)) for c in counters
            ),
            "observable_work": sum(
                c.get("model_work", 0) + c.get("native_host_work", 0) for c in counters
            ),
            "elapsed_seconds": time.monotonic() - self.state["started_monotonic"],
            "peak_rss_bytes": max(c.get("peak_rss_bytes", 0) for c in counters),
            "native_calls": sum(len(c.get("attempts", [])) for c in counters),
            "composition_calls": sum(r["cursor"] for r in self.state["pools"]),
            "candidate_validation_calls": sum(
                c.get("resource_events", {}).get("STAGE_B_CANDIDATE_VALIDATION", 0)
                for c in counters
            ),
        }

    def record_enumeration(self, sources: Mapping[str, str], event: Mapping[str, Any]) -> None:
        """Compatible audit extension inside the SAME active composition claim.

        No begin(), new allowance, counter reset or resumed unknown native call.
        Full cuts/results survive interruption in the existing atomic task ledger.
        """
        self.validate(self.ledger)
        if not self.record["composition_active"] or not self.state["accounting_complete"]:
            raise LayoutAuthorityError("POOL_ENUMERATION_OUTSIDE_ACTIVE_ACCOUNTED_COMPOSITION")
        required = {k: self.decision[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
        required["composition_hash"] = self.decision["compositions"][self.record["cursor"] - 1][
            "composition_hash"
        ]
        if dict(sources) != required:
            raise LayoutAuthorityError("POOL_ENUMERATION_SOURCE_MISMATCH")
        self.ledger.charge("STAGE_B_ENUMERATION_AUDIT_RECORD", 1)
        events = self.record.setdefault("enumeration_events", [])
        entry = json.loads(_bytes(dict(event)))
        entry["sequence"] = len(events) + 1
        entry["sources"] = dict(sources)
        entry["canonical_event_hash"] = canonical_hash(entry)
        events.append(entry)
        self.ledger.checkpoint("STAGE_B_ENUMERATION_AUDIT_RECORDED")

    def remaining_solver_seconds(self, ledger: StageALedger) -> float:
        self.validate(ledger)
        local = max(ledger.solver_wall, ledger.solver_monotonic_wall)
        remaining = min(POOL_SOLVER_TARGET - local, 100 - self.totals()["native_solver_seconds"])
        if remaining <= 0:
            raise LayoutAuthorityError("STAGE_B_SOLVER_RESERVE_LIMIT")
        return float(remaining)

    def guard(self, ledger: StageALedger) -> None:
        if self.closed or ledger is not self.ledger:
            raise LayoutAuthorityError("POOL_LEASE_LEDGER_MISMATCH")
        self._monotonic(self.record["counters"], self._snapshot())
        total = self.totals()
        local_work = ledger.model_work + ledger.native_host_work
        if (
            total["elapsed_seconds"] < 0
            or total["elapsed_seconds"] > 180
            or total["native_solver_seconds"] > 100
            or total["observable_work"] > 1_200_000
            or ledger.peak_rss_bytes > 512 * 1024 * 1024
        ):
            raise LayoutAuthorityError("STAGE_B_TASK_RESOURCE_LIMIT")
        if (
            time.monotonic() - ledger.started > POOL_ELAPSED_TARGET
            or local_work > POOL_WORK_TARGET
            or max(ledger.solver_wall, ledger.solver_monotonic_wall) > 50
        ):
            raise LayoutAuthorityError("STAGE_B_REPLAY_RESERVATION_LIMIT")

    def checkpoint(self, phase: str, snapshot: Mapping[str, Any]) -> None:
        if self.closed:
            raise LayoutAuthorityError("POOL_LEASE_CLOSED")
        self._monotonic(self.record["counters"], snapshot)
        old = self.record["counters"]
        if (
            old.get("native_solver_active")
            and not snapshot["native_solver_active"]
            and (
                phase != "CP_SAT_RETURNED"
                or len(snapshot.get("attempts", [])) != len(old.get("attempts", [])) + 1
                or not self.ledger.solver_history_verified
            )
        ):
            raise LayoutAuthorityError("POOL_NATIVE_RETURN_UNVERIFIED")
        self.record["counters"] = json.loads(_bytes(snapshot))
        self.state["accounting_complete"] = (
            not snapshot["native_solver_active"] and self.ledger.solver_history_verified
        )
        if phase == "STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED":
            self.record["composition_active"] = False
        self.record["phase"] = phase
        self.state["totals"] = self.totals()
        with (self.store.root / "journal.jsonl").open("ab") as stream:
            stream.write(
                _bytes(
                    {
                        "phase": phase,
                        "pool": len(self.state["pools"]),
                        "snapshot": snapshot,
                        "totals": self.state["totals"],
                    }
                )
            )
            stream.flush()
            os.fsync(stream.fileno())
        _durable(self.store.root / "task_ledger.json", self.state)

    def finish_pool(self, result_hash: str | None = None) -> None:
        # A known bounded/resource result is complete accounting, not engineering PASS.
        self.store._decision()
        self.record["result_hash"] = result_hash
        self.record["status"] = (
            "COMPLETED" if self.state["accounting_complete"] else "INTERRUPTED_UNKNOWN"
        )
        self.ledger.checkpoint("POOL_FINISHED")
        self.closed = True
        (self.store.root / "active.lock").unlink()
