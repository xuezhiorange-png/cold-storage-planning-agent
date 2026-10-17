"""Resource admission only: these tests never call a real CP-SAT/layout solve."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.stage_a_execution import OwnerExecutionStore


def approved_store(tmp_path: Path) -> tuple[OwnerExecutionStore, dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    instruction = b"SYNTHETIC_RESOURCE_UNIT_TASK owner approves one NEW scope"
    source = tmp_path / "source.txt"
    source.write_text("fixed unit source")
    binding: dict[str, Any] = dict(
        head="unit-head",
        worktree_fingerprint="unit-fingerprint",
        source_files={str(source): hashlib.sha256(source.read_bytes()).hexdigest()},
        fixture_sha256="fixture",
        zone_plan_hash="zone",
        p1_hash="p1",
        site_hash="site",
        composition_hash="composition",
        solver_version="test-no-solve",
        structural_version="test",
        resource_contract_version="unchanged-test",
        max_new_instances=1,
    )
    store = OwnerExecutionStore(
        tmp_path / "registry",
        "SYNTHETIC_RESOURCE_UNIT_TASK",
        hashlib.sha256(instruction).hexdigest(),
    )
    store.approve(instruction, binding)
    return store, binding


def test_bare_verified_boolean_does_not_grant_budget() -> None:
    with pytest.raises(LayoutAuthorityError, match="EXECUTION_IDENTITY_REQUIRED"):
        StageALedger(solver_history_verified=True).remaining_solver_seconds()


def test_single_new_bound_to_task_not_output_or_request_id(tmp_path: Path) -> None:
    store, _ = approved_store(tmp_path)
    ledger = store.open("NEW")
    assert ledger.remaining_solver_seconds() == 100
    for _new_output_or_uuid in ("directory-b", "different-uuid"):
        with pytest.raises(LayoutAuthorityError, match="ALREADY_CONSUMED"):
            store.open("NEW")
    assert ledger.execution_authorization is not None
    ledger.execution_authorization.finish("FAILED")  # type: ignore[attr-defined]
    with pytest.raises(LayoutAuthorityError, match="ALREADY_CONSUMED"):
        store.open("NEW")


def test_resume_restores_all_counters_without_refill(tmp_path: Path) -> None:
    store, _ = approved_store(tmp_path)
    ledger = store.open("NEW")
    ledger.solver_wall = 12.5
    ledger.model_work = 120
    ledger.native_host_work = 300
    ledger.checked_solutions = 2
    ledger.started -= 3
    assert ledger.execution_authorization is not None
    ledger.execution_authorization.pause()  # type: ignore[attr-defined]
    restored = store.open("RESUME")
    assert restored.remaining_solver_seconds() == 87.5
    assert (restored.model_work, restored.native_host_work, restored.checked_solutions) == (
        120,
        300,
        2,
    )
    assert restored.started < ledger.started + 1


def test_missing_historical_and_unfinished_resume_fail_closed(tmp_path: Path) -> None:
    store, _ = approved_store(tmp_path)
    with pytest.raises(LayoutAuthorityError, match="UNVERIFIED_HISTORICAL"):
        store.open("RESUME", historical={"accounting_complete": False})
    with pytest.raises(LayoutAuthorityError, match="LEDGER_MISSING"):
        store.open("RESUME")
    ledger = store.open("NEW")
    ledger.native_solver_active = True
    ledger.checkpoint("NATIVE_STARTED")
    with pytest.raises(LayoutAuthorityError, match="INCOMPLETE_OR_TERMINAL"):
        store.open("RESUME")


def test_sources_and_authorities_cannot_be_swapped(tmp_path: Path) -> None:
    store, binding = approved_store(tmp_path)
    ledger = store.open("NEW")
    lease = ledger.execution_authorization
    assert lease is not None
    with pytest.raises(LayoutAuthorityError, match="AUTHORITY_IDENTITY_MISMATCH"):
        lease.begin({"p1_hash": "different"})
    source = Path(next(iter(binding["source_files"])))
    source.write_text("changed")
    with pytest.raises(LayoutAuthorityError, match="FINGERPRINT_CHANGED"):
        ledger.remaining_solver_seconds()


def test_ledger_rollback_and_repeated_main_invocation_denied(tmp_path: Path) -> None:
    store, _ = approved_store(tmp_path)
    ledger = store.open("NEW")
    assert ledger.execution_authorization is not None
    ledger.execution_authorization.begin({"site_hash": "site"})
    with pytest.raises(LayoutAuthorityError, match="MAIN_INVOCATION_ALREADY_CONSUMED"):
        ledger.execution_authorization.begin({"site_hash": "site"})
    ledger.model_work = 10
    ledger.checkpoint("COUNTED")
    ledger.model_work = 0
    with pytest.raises(LayoutAuthorityError, match="COUNTER_ROLLBACK"):
        ledger.remaining_solver_seconds()
    with pytest.raises(LayoutAuthorityError, match="COUNTER_ROLLBACK"):
        ledger.checkpoint("CANNOT_LAUNDER_RESET_THROUGH_CHECKPOINT")


def test_owner_document_or_decision_tamper_rejected(tmp_path: Path) -> None:
    store, binding = approved_store(tmp_path)
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE_MISMATCH"):
        store.approve(b"unapproved", binding)
    path = store.root / "owner_decision.json"
    decision = json.loads(path.read_text())
    decision["max_new_instances"] = 2
    path.write_text(json.dumps(decision))
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE_MISMATCH"):
        store.open("NEW")


def test_unchanged_limits_zero_and_native_active_fail_closed(tmp_path: Path) -> None:
    store, _ = approved_store(tmp_path)
    ledger = store.open("NEW")
    ledger.solver_wall = 100
    with pytest.raises(LayoutAuthorityError, match="ALLOWANCE_EXHAUSTED"):
        ledger.remaining_solver_seconds()
    ledger.native_solver_active = True
    with pytest.raises(LayoutAuthorityError, match="HISTORY_UNVERIFIED"):
        ledger.remaining_solver_seconds()
