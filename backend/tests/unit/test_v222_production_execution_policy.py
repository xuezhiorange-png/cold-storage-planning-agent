"""Synthetic accounting tests; no real-project generation and no budget refill."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.stage_a_production_execution import (
    ProductionReplayStore,
)


def store(tmp_path: Path) -> ProductionReplayStore:
    instruction = b"UNIT_PRODUCTION_POLICY owner two replays"
    source = tmp_path / "source.txt"
    source.write_text("fixed")
    binding: dict[str, Any] = dict(
        head="unit",
        worktree_fingerprint="unit",
        source_files={str(source): hashlib.sha256(source.read_bytes()).hexdigest()},
        fixture_sha256="unit",
        zone_plan_hash="zone",
        p1_hash="p1",
        site_hash="site",
        composition_hash="composition",
        solver_version="unit",
        structural_version="unit",
        resource_contract_version="V2_2_2_STAGE_A_CP_SAT_PRODUCTION_RESOURCE_V1",
        max_new_instances=2,
    )
    result = ProductionReplayStore(
        tmp_path, "UNIT_PRODUCTION_POLICY", hashlib.sha256(instruction).hexdigest()
    )
    result.approve(instruction, binding)
    return result


def test_two_requests_cumulative_native_calls_and_no_third(tmp_path: Path) -> None:
    registry = store(tmp_path)
    for _ in range(2):
        ledger = registry.open("NEW")
        assert ledger.remaining_solver_seconds() == 90
        lease = ledger.execution_authorization
        assert lease is not None
        lease.begin({"p1_hash": "p1"})
        for i in range(7):
            ledger.solver_wall += 8
            ledger.solver_monotonic_wall += 8.01
            ledger.attempts.append({"wall_time": 8, "branches": i, "conflicts": i})
            ledger.checkpoint("UNIT_NATIVE_CALL_RETURNED")
        assert ledger.remaining_solver_seconds() == pytest.approx(33.93)
        lease.finish("COMPLETED")  # type: ignore[attr-defined]
    saved = json.loads((registry.root / "task_resource_ledger.json").read_text())
    assert saved["native_call_count"] == 14
    assert saved["solver_wall_seconds"] == pytest.approx(112.14)
    with pytest.raises(LayoutAuthorityError, match="ALREADY_CONSUMED"):
        registry.open("NEW")


def test_original_work_counters_share_task_limit(tmp_path: Path) -> None:
    registry = store(tmp_path)
    first = registry.open("NEW")
    first.model_work, first.native_host_work = 500_000, 100_000
    assert first.execution_authorization is not None
    first.execution_authorization.finish("COMPLETED")  # type: ignore[attr-defined]
    second = registry.open("NEW")
    second.model_work, second.native_host_work = 500_000, 100_000
    second.guard()
    with pytest.raises(LayoutAuthorityError, match="TASK_WORK_LIMIT"):
        second.charge("EXISTING_COUNTER_INCREMENT")
    assert second.model_work == 500_000 and second.native_host_work == 100_000
    assert "EXISTING_COUNTER_INCREMENT" not in second.resource_events


def test_request_and_task_native_limits_not_dfs(tmp_path: Path) -> None:
    registry = store(tmp_path)
    ledger = registry.open("NEW")
    ledger.solver_wall = 90
    with pytest.raises(LayoutAuthorityError, match="ALLOWANCE_EXHAUSTED"):
        ledger.remaining_solver_seconds()
    ledger.solver_wall = 100.1
    with pytest.raises(LayoutAuthorityError, match="REQUEST_SOLVER_LIMIT"):
        ledger.guard()
    ledger.solver_wall = 89
    assert ledger.execution_authorization is not None
    # Same native bound at task level, independently of branches/conflicts.
    ledger.execution_authorization.previous_seconds = 92  # type: ignore[attr-defined]
    with pytest.raises(LayoutAuthorityError, match="ALLOWANCE_EXHAUSTED"):
        ledger.remaining_solver_seconds()


def test_unknown_native_interruption_missing_ledger_and_uuid_denied(tmp_path: Path) -> None:
    registry = store(tmp_path)
    ledger = registry.open("NEW")
    ledger.native_solver_active = True
    ledger.checkpoint("UNIT_INTERRUPTED_NATIVE_CALL")
    assert ledger.execution_authorization is not None
    ledger.execution_authorization.finish("FAILED")  # type: ignore[attr-defined]
    with pytest.raises(LayoutAuthorityError, match="COUNTERS_INCOMPLETE"):
        registry.open("NEW")
    (registry.root / "task_resource_ledger.json").unlink()
    with pytest.raises(LayoutAuthorityError, match="LEDGER_MISSING"):
        registry.open("NEW")


def test_verified_pause_restores_counters_and_no_refill(tmp_path: Path) -> None:
    registry = store(tmp_path)
    ledger = registry.open("NEW")
    ledger.solver_wall, ledger.solver_monotonic_wall = 12, 12.5
    ledger.model_work = 75
    assert ledger.execution_authorization is not None
    ledger.execution_authorization.pause()  # type: ignore[attr-defined]
    resumed = registry.open("RESUME")
    assert resumed.remaining_solver_seconds() == 77.5
    assert resumed.model_work == 75
    resumed.model_work = 0
    with pytest.raises(LayoutAuthorityError, match="ROLLBACK"):
        resumed.remaining_solver_seconds()


def test_historical_scope_and_source_tamper_rejected(tmp_path: Path) -> None:
    registry = store(tmp_path)
    with pytest.raises(LayoutAuthorityError, match="UNVERIFIED_HISTORICAL"):
        registry.open("RESUME", historical={})
    ledger = registry.open("NEW")
    (tmp_path / "source.txt").write_text("changed")
    with pytest.raises(LayoutAuthorityError, match="FINGERPRINT_CHANGED"):
        ledger.remaining_solver_seconds()
