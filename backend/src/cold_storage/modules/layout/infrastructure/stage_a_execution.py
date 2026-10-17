"""Durable one-grant execution scope. No layout or engineering rules live here.

The store and approval digest are trusted bootstrap configuration, not request
parameters. Filesystem administrators remain outside this in-process trust model.
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

POLICY = "OWNER_APPROVED_INDEPENDENT_EXECUTION_V1"
_SEAL = object()
CAPS = MappingProxyType(
    {
        "solver_seconds": 100,
        "experiment_seconds": 180,
        "workers": 1,
        "memory_mib": 512,
        "observable_work": 1_200_000,
        "requirement_host_work": 20_000,
        "checked_solutions": 20,
        "placement_nodes": 60_000,
        "access_route_nodes": 20_000,
        "truck_nodes": 20_000,
        "joint_evaluations": 256,
        "joint_events": 1024,
        "joint_work": 8192,
    }
)


def _bytes(body: Mapping[str, Any]) -> bytes:
    return (json.dumps(body, sort_keys=True, default=str, ensure_ascii=False) + "\n").encode()


def _durable(path: Path, body: Mapping[str, Any], *, exclusive: bool = False) -> None:
    payload = _bytes(body)
    if exclusive:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        temporary = path.with_suffix(".pending")
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class OwnerExecutionStore:
    """A single trusted registry slot per Owner task, independent of output/run ID."""

    maximum_instances = 1
    resource_policy = POLICY
    production_mapping = "NOT_APPROVED"
    approval_caps = CAPS

    def __init__(self, registry: Path, task_id: str, owner_digest: str) -> None:
        self.root = registry.resolve() / sha256(task_id.encode()).hexdigest()
        self.task_id = task_id
        self.owner_digest = owner_digest
        self.approved_digest: str | None = None

    def approve(self, instruction: bytes, binding: dict[str, Any]) -> dict[str, Any]:
        if sha256(instruction).hexdigest() != self.owner_digest:
            raise LayoutAuthorityError("EXECUTION_OWNER_SOURCE_MISMATCH")
        if (
            self.task_id not in instruction.decode()
            or binding.get("max_new_instances") != self.maximum_instances
        ):
            raise LayoutAuthorityError("EXECUTION_OWNER_SCOPE_INVALID")
        required = {
            "head",
            "worktree_fingerprint",
            "source_files",
            "fixture_sha256",
            "zone_plan_hash",
            "p1_hash",
            "site_hash",
            "composition_hash",
            "solver_version",
            "structural_version",
            "resource_contract_version",
        }
        if not required <= binding.keys() or any(not binding[k] for k in required):
            raise LayoutAuthorityError("EXECUTION_IDENTITY_INCOMPLETE")
        decision = dict(
            binding,
            task_id=self.task_id,
            policy=self.resource_policy,
            owner_instruction_sha256=self.owner_digest,
            registry_root=str(self.root),
            caps=dict(self.approval_caps),
            historical_resume_allowed=False,
            d04_rounds_reset=False,
            production_resource_mapping=self.production_mapping,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "owner_decision.json"
        if path.exists():
            if path.read_bytes() != _bytes(decision):
                raise LayoutAuthorityError("EXECUTION_OWNER_SCOPE_ALREADY_BOUND")
        else:
            _durable(path, decision, exclusive=True)
        self.approved_digest = sha256(path.read_bytes()).hexdigest()
        return decision

    def open(self, mode: str, *, historical: Mapping[str, Any] | None = None) -> StageALedger:
        if mode == "RESUME" and historical is not None:
            # Legacy R16/C1 has no complete, bound checkpoint; never create an allowance.
            raise LayoutAuthorityError("RESUME_DENIED_UNVERIFIED_HISTORICAL_EXECUTION")
        decision_path = self.root / "owner_decision.json"
        if not decision_path.exists():
            raise LayoutAuthorityError("EXECUTION_OWNER_DECISION_REQUIRED")
        decision = json.loads(decision_path.read_text())
        if (
            decision["owner_instruction_sha256"] != self.owner_digest
            or self.approved_digest != sha256(decision_path.read_bytes()).hexdigest()
        ):
            raise LayoutAuthorityError("EXECUTION_OWNER_SOURCE_MISMATCH")
        state_path = self.root / "execution_resource_ledger.json"
        if mode == "NEW":
            initial: dict[str, Any] = dict(
                execution_identity=sha256(decision_path.read_bytes()).hexdigest(),
                decision_sha256=sha256(decision_path.read_bytes()).hexdigest(),
                state="ALLOCATED",
                new_instance_count=1,
                main_invocation_count=0,
                accounting_complete=True,
                native_solver_active=False,
                counters={},
            )
            try:
                _durable(self.root / "new_allocation_claim.json", initial, exclusive=True)
            except FileExistsError as error:
                raise LayoutAuthorityError("EXECUTION_NEW_INSTANCE_ALREADY_CONSUMED") from error
            _durable(state_path, initial)
        elif mode == "RESUME":
            if not state_path.exists():
                raise LayoutAuthorityError("RESUME_DENIED_LEDGER_MISSING")
            initial = json.loads(state_path.read_text())
            if (
                initial.get("state") != "PAUSED"
                or not initial.get("accounting_complete")
                or initial.get("native_solver_active")
                or initial.get("decision_sha256") != sha256(decision_path.read_bytes()).hexdigest()
            ):
                raise LayoutAuthorityError("RESUME_DENIED_INCOMPLETE_OR_TERMINAL_EXECUTION")
        else:
            raise LayoutAuthorityError("EXECUTION_MODE_INVALID")
        try:
            lock = os.open(self.root / "active.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(lock)
        except FileExistsError as error:
            raise LayoutAuthorityError("RESUME_DENIED_ACTIVE_EXECUTION") from error
        saved = initial.get("counters", {})
        ledger = StageALedger()
        for key in (
            "model_work",
            "native_host_work",
            "solver_wall",
            "attempts",
            "checked_solutions",
            "native_requirements",
            "native_grid_searches",
            "resource_events",
            "peak_rss_bytes",
        ):
            if key in saved:
                setattr(ledger, key, saved[key])
        ledger.started -= saved.get("elapsed_seconds", 0)
        lease = _ExecutionLease(_SEAL, self.root, decision, initial, ledger)
        ledger.execution_authorization = lease
        ledger.solver_history_verified = True  # Derived only after durable scope admission.
        ledger.checkpoint("EXECUTION_" + mode + "_ADMITTED")
        return ledger


class _ExecutionLease:
    def __init__(
        self,
        seal: object,
        root: Path,
        decision: dict[str, Any],
        state: dict[str, Any],
        ledger: StageALedger,
    ) -> None:
        if seal is not _SEAL:
            raise LayoutAuthorityError("EXECUTION_LEASE_NOT_AUTHORITATIVE")
        self.root, self.decision, self.state, self.ledger = root, decision, state, ledger
        self.closed = False
        self.decision_bytes = (root / "owner_decision.json").read_bytes()
        self.io_seconds = 0.0
        self.io_bytes = 0

    def validate(self, ledger: StageALedger) -> None:
        if self.closed or ledger is not self.ledger:
            raise LayoutAuthorityError("EXECUTION_LEASE_LEDGER_MISMATCH")
        if (self.root / "owner_decision.json").read_bytes() != self.decision_bytes:
            raise LayoutAuthorityError("EXECUTION_OWNER_SCOPE_CHANGED")
        for path, expected in self.decision["source_files"].items():
            if sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise LayoutAuthorityError("EXECUTION_SOURCE_FINGERPRINT_CHANGED")
        saved = self.state.get("counters", {})
        for key in ("model_work", "native_host_work", "solver_wall", "checked_solutions"):
            if getattr(ledger, key) < saved.get(key, 0):
                raise LayoutAuthorityError("EXECUTION_COUNTER_ROLLBACK_DENIED")

    def begin(self, sources: Mapping[str, str]) -> None:
        self.validate(self.ledger)
        if any(sources[key] != self.decision[key] for key in sources):
            raise LayoutAuthorityError("EXECUTION_AUTHORITY_IDENTITY_MISMATCH")
        if self.state["main_invocation_count"] >= 1:
            raise LayoutAuthorityError("EXECUTION_MAIN_INVOCATION_ALREADY_CONSUMED")
        self.state["main_invocation_count"] += 1
        self.state["state"] = "RUNNING"
        self.ledger.checkpoint("MAIN_INVOCATION_STARTED")

    def checkpoint(self, phase: str, snapshot: Mapping[str, Any]) -> None:
        started = time.monotonic()
        if self.closed:
            raise LayoutAuthorityError("EXECUTION_LEASE_CLOSED")
        previous = self.state.get("counters", {})
        for key in (
            "model_work",
            "native_host_work",
            "solver_wall",
            "checked_solutions",
            "elapsed_seconds",
        ):
            if snapshot.get(key, 0) < previous.get(key, 0):
                raise LayoutAuthorityError("EXECUTION_COUNTER_ROLLBACK_DENIED")
        for key in ("attempts", "native_requirements", "native_grid_searches"):
            if len(snapshot.get(key, [])) < len(previous.get(key, [])):
                raise LayoutAuthorityError("EXECUTION_COUNTER_ROLLBACK_DENIED")
        self.state.update(
            phase=phase,
            counters=json.loads(_bytes(snapshot)),
            native_solver_active=snapshot["native_solver_active"],
            accounting_complete=not snapshot["native_solver_active"],
            io_seconds_observed=self.io_seconds,
            io_bytes_observed=self.io_bytes,
        )
        payload = _bytes(self.state)
        with (self.root / "journal.jsonl").open("ab") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _durable(self.root / "execution_resource_ledger.json", self.state)
        self.io_bytes += len(payload) * 2
        self.io_seconds += time.monotonic() - started

    def finish(self, state: str) -> None:
        self.state["state"] = state
        self.ledger.checkpoint("EXECUTION_" + state)
        self.closed = True
        (self.root / "active.lock").unlink()

    def pause(self) -> None:
        if self.ledger.native_solver_active:
            raise LayoutAuthorityError("RESUME_DENIED_NATIVE_COUNTERS_INCOMPLETE")
        self.finish("PAUSED")
