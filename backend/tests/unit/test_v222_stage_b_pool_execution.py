"""Synthetic durable admission tests; never use the real Owner registry."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import PoolExecutionStore


def registry(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("unit-source")
    repo = Path(__file__).resolve().parents[3]
    instruction = b"SYNTHETIC_POOL_TEST not a real project approval"
    binding = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "repository_root": str(repo),
        "source_files": {str(source): hashlib.sha256(source.read_bytes()).hexdigest()},
        "dependency_file": str(source),
        "dependency_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
        "zone_plan_hash": "zone",
        "p1_hash": "p1",
        "site_hash": "site",
        "schedule_hash": "schedule",
        "solver_version": "synthetic-unit",
        "compositions": [
            {"identity": f"unit-{i}", "composition_hash": f"hash-{i}"} for i in range(6)
        ],
    }
    store = PoolExecutionStore(
        tmp_path / "registry", "SYNTHETIC_POOL_TEST", hashlib.sha256(instruction).hexdigest()
    )
    store.approve(instruction, binding)
    return store, binding


def admit(ledger, binding):
    lease = ledger.execution_authorization
    lease.validate_pool(
        ledger,
        {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash", "schedule_hash")},
        tuple(c["identity"] for c in binding["compositions"]),
    )
    return lease


def begin(lease, binding, i):
    lease.begin(
        {
            **{k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")},
            "composition_hash": binding["compositions"][i]["composition_hash"],
        }
    )


def test_six_ordered_compositions_two_pools_and_no_third(tmp_path):
    store, binding = registry(tmp_path)
    for mode in ("MAIN", "REPLAY"):
        ledger = store.open(mode)
        lease = admit(ledger, binding)
        for i in range(6):
            begin(lease, binding, i)
            ledger.charge("unit", 1)
            ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
        with pytest.raises(LayoutAuthorityError):
            begin(lease, binding, 0)
        lease.finish_pool()
    saved = json.loads((store.root / "task_ledger.json").read_text())
    assert saved["totals"]["composition_calls"] == 12
    assert saved["totals"]["observable_work"] == 12
    with pytest.raises(LayoutAuthorityError, match="CONSUMED"):
        store.open("MAIN")


@pytest.mark.parametrize(
    "bad", ["reordered", "changed_source", "second_admission", "duplicate", "unapproved"]
)
def test_invalid_plan_and_composition_calls_are_denied(tmp_path, bad):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    lease = ledger.execution_authorization
    if bad == "reordered":
        binding["compositions"].reverse()
    if bad == "changed_source":
        binding["site_hash"] = "forged"
    if bad in {"reordered", "changed_source"}:
        with pytest.raises(LayoutAuthorityError):
            admit(ledger, binding)
        return
    admit(ledger, binding)
    if bad == "second_admission":
        with pytest.raises(LayoutAuthorityError):
            admit(ledger, binding)
    else:
        begin(lease, binding, 0)
        ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
        with pytest.raises(LayoutAuthorityError):
            begin(lease, binding, 0 if bad == "duplicate" else 5)


def test_claim_history_and_incomplete_native_consumption_cannot_be_reset(tmp_path):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    with pytest.raises(LayoutAuthorityError, match="ACTIVE"):
        store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    ledger.native_solver_active = True
    ledger.checkpoint("CP_SAT_STARTED")
    ledger.solver_history_verified = False
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="HISTORY"):
        store.open("REPLAY")
    (store.root / "task_ledger.json").unlink()
    with pytest.raises(LayoutAuthorityError, match="HISTORY_MISSING"):
        store.open("MAIN")


def test_counter_rollback_and_fake_native_return_denied(tmp_path):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    admit(ledger, binding)
    ledger.model_work = 10
    ledger.checkpoint("UNIT")
    ledger.model_work = 9
    with pytest.raises(LayoutAuthorityError, match="ROLLBACK"):
        ledger.guard()
    ledger.model_work = 10
    ledger.native_solver_active = True
    ledger.checkpoint("CP_SAT_STARTED")
    ledger.native_solver_active = False
    with pytest.raises(LayoutAuthorityError, match="NATIVE_RETURN_UNVERIFIED"):
        ledger.checkpoint("UNIT_FAKE_RETURN")


@pytest.mark.parametrize(
    "field,value",
    [("model_work", 1_200_001), ("solver_wall", 101), ("peak_rss_bytes", 513 * 1024 * 1024)],
)
def test_real_guard_rejects_over_budget_counters(tmp_path, field, value):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    admit(ledger, binding)
    setattr(ledger, field, value)
    with pytest.raises(LayoutAuthorityError, match="RESOURCE_LIMIT"):
        ledger.guard()


def test_shared_reservations_and_elapsed_limit(tmp_path):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    ledger.solver_wall = ledger.solver_monotonic_wall = 40
    assert ledger.remaining_solver_seconds() == pytest.approx(9.9)
    ledger.checkpoint("UNIT")
    lease.finish_pool()
    replay = store.open("REPLAY")
    second = admit(replay, binding)
    assert second.totals()["native_solver_seconds"] == 40
    second.state["started_monotonic"] -= 181
    with pytest.raises(LayoutAuthorityError, match="RESOURCE_LIMIT"):
        replay.guard()


def test_missing_owner_changed_head_dependency_and_source_fail_closed(tmp_path):
    store = PoolExecutionStore(tmp_path, "SYNTHETIC_POOL_TEST", "not-approved")
    with pytest.raises(LayoutAuthorityError):
        store.open("MAIN")
    store, binding = registry(tmp_path)
    Path(binding["dependency_file"]).write_text("changed")
    with pytest.raises(LayoutAuthorityError, match="DEPENDENCY_CHANGED"):
        store.open("MAIN")


def test_actual_resident_memory_is_rejected_without_mocking_rss(tmp_path):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    admit(ledger, binding)
    pressure = bytearray(600 * 1024 * 1024)
    for i in range(0, len(pressure), 4096):
        pressure[i] = 1
    with pytest.raises(LayoutAuthorityError, match="RESOURCE_LIMIT"):
        ledger.guard()
    assert ledger.peak_rss_bytes > 512 * 1024 * 1024
    assert len(pressure) == 600 * 1024 * 1024


def test_insufficient_replay_reserve_does_not_allocate_second_claim(tmp_path):
    store, binding = registry(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    ledger.model_work = 600_001
    ledger.checkpoint("UNIT_OVER_RESERVATION_KNOWN")
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="REPLAY_NOT_EXECUTED_RESOURCE_LIMIT"):
        store.open("REPLAY")
    assert not (store.root / "pool_2_claim.json").exists()


def test_forged_head_owner_hash_and_reattachment_do_not_grant_another_pool(tmp_path):
    store, binding = registry(tmp_path)
    instruction = b"SYNTHETIC_POOL_TEST not a real project approval"
    wrong = PoolExecutionStore(
        tmp_path / "wrong", "SYNTHETIC_POOL_TEST", hashlib.sha256(instruction).hexdigest()
    )
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE"):
        wrong.approve(b"forged", binding)
    binding["head"] = "not-the-checkout"
    with pytest.raises(LayoutAuthorityError, match="HEAD_OR_DEPENDENCY"):
        wrong.approve(instruction, binding)
    binding["head"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=binding["repository_root"], text=True
    ).strip()
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    lease.finish_pool()
    reattached = PoolExecutionStore(
        tmp_path / "registry", "SYNTHETIC_POOL_TEST", hashlib.sha256(instruction).hexdigest()
    )
    reattached.approve(instruction, binding)
    with pytest.raises(LayoutAuthorityError, match="CONSUMED"):
        reattached.open("MAIN")


def test_bootstrap_admission_exposes_no_registry_or_budget_parameters():
    import inspect

    from cold_storage.bootstrap.global_composition import approved_stage_b_pool_store

    assert not inspect.signature(approved_stage_b_pool_store).parameters
