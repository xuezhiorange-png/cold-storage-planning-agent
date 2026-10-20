"""Synthetic fixed-slot accounting only; never touch the actual Owner registry."""

import hashlib
import importlib
import inspect
import json
from pathlib import Path

import pytest

from cold_storage.bootstrap.stage_b_functional_shape_ab import approved_functional_shape_ab_stores
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_functional_shape_ab as ab
from tests.unit.test_v222_multi_solution_execution import _fair_registry
from tests.unit.test_v222_stage_b_pool_execution import admit, begin


def setup(tmp_path, monkeypatch):
    _, common = _fair_registry(tmp_path)
    raw = ("SYNTHETIC ACCOUNTING ONLY " + " ".join(ab.SLOTS.values())).encode()
    monkeypatch.setattr(ab, "OWNER_SHA256", hashlib.sha256(raw).hexdigest())
    common["runtime_dependency_hash"] = "synthetic-runtime-byte-fingerprint"
    stores = [ab.FunctionalShapeABStore(tmp_path / "ab", arm) for arm in ("A", "B")]
    bindings = [ab.arm_binding(common, arm) for arm in ("A", "B")]
    for s, b in zip(stores, bindings, strict=True):
        s.approve(raw, b)
    return stores, bindings, raw


def test_bootstrap_fixed_slots_cannot_alias_old_grants():
    assert not inspect.signature(approved_functional_shape_ab_stores).parameters
    a, b = approved_functional_shape_ab_stores()
    assert a.task_id == "V2_2_2_STAGE_B_AB_R1_ARM_A_MAIN"
    assert b.task_id == "V2_2_2_STAGE_B_AB_R1_ARM_B_MAIN"
    assert a.root != b.root and a.shared_root == b.shared_root
    assert a.owner_digest == b.owner_digest == ab.OWNER_SHA256


def test_two_sequential_main_only_no_replay_or_reallocation(tmp_path, monkeypatch):
    stores, bindings, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(LayoutAuthorityError):
        stores[1].open("MAIN")
    for s, binding in zip(stores, bindings, strict=True):
        with pytest.raises(LayoutAuthorityError, match="NO_REPLAY"):
            s.open("REPLAY")
        ledger = s.open("MAIN")
        lease = admit(ledger, binding)
        with pytest.raises(LayoutAuthorityError, match="EXCLUSIVE"):
            stores[1].open("MAIN")
        for i in range(6):
            begin(lease, binding, i)
            ledger.charge("SYNTHETIC_ACCOUNTING", 1)
            ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
        lease.finish_pool()
    assert stores[1].shared_state()["totals"]["observable_work"] == 12
    for s in stores:
        with pytest.raises(LayoutAuthorityError):
            s.open("MAIN")


@pytest.mark.parametrize(
    "arm,key",
    [
        (a, k)
        for a in (0, 1)
        for k in (
            "ab_arm",
            "ab_contract_hash",
            "final_guidance_policy_hash",
            "ab_common_binding_hash",
            "zone_plan_hash",
            "schedule_hash",
            "runtime_dependency_hash",
        )
    ],
)
def test_policy_source_arm_or_budget_binding_tamper_denied(tmp_path, monkeypatch, arm, key):
    stores, bindings, raw = setup(tmp_path, monkeypatch)
    bindings[arm][key] = "caller-forged"
    with pytest.raises(LayoutAuthorityError):
        stores[arm].approve(raw, bindings[arm])


def test_two_arms_share_native_counters_but_not_reserved_seconds(tmp_path, monkeypatch):
    stores, bindings, _ = setup(tmp_path, monkeypatch)
    a = stores[0].open("MAIN")
    lease = admit(a, bindings[0])
    begin(lease, bindings[0], 0)
    a.solver_wall = a.solver_monotonic_wall = 40
    a.attempts.extend({"synthetic": i} for i in range(60))
    a.checkpoint("SYNTHETIC_ACCOUNTED")
    assert a.remaining_solver_seconds() == pytest.approx(9.8)
    lease.finish_pool()
    b = stores[1].open("MAIN")
    second = admit(b, bindings[1])
    begin(second, bindings[1], 0)
    assert b.remaining_solver_seconds() == pytest.approx(49.8)  # unused A time does not transfer
    b.attempts.extend({"synthetic": i} for i in range(40))
    b.checkpoint("SYNTHETIC_ACCOUNTED")
    assert second.totals()["native_solver_seconds"] == 40
    assert second.totals()["native_calls"] == 100
    with pytest.raises(LayoutAuthorityError, match="NATIVE_CALL_LIMIT"):
        b.remaining_solver_seconds()
    second.finish_pool()


@pytest.mark.parametrize(
    "field,value",
    [("solver_wall", 49.91), ("model_work", 600001), ("peak_rss_bytes", 513 * 1024 * 1024)],
)
def test_original_and_stricter_arm_guards_fail_closed(tmp_path, monkeypatch, field, value):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    setattr(ledger, field, value)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.guard()


def test_unknown_native_interruption_prevents_b_and_restart(tmp_path, monkeypatch):
    stores, bindings, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    lease = admit(ledger, bindings[0])
    begin(lease, bindings[0], 0)
    ledger.native_solver_active = True
    ledger.checkpoint("CP_SAT_STARTED")
    ledger.solver_history_verified = False
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="UNVERIFIED"):
        stores[1].open("MAIN")
    with pytest.raises(LayoutAuthorityError):
        stores[0].open("MAIN")


def test_shared_file_tamper_and_counter_rollback_rejected(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.charge("SYNTHETIC", 5)
    ledger.checkpoint("SYNTHETIC_ACCOUNTED")
    ledger.model_work = 4
    with pytest.raises(LayoutAuthorityError, match="ROLLBACK"):
        ledger.guard()
    ledger.model_work = 5
    file = stores[0].shared_root / "shared-resource-ledger.json"
    file.write_text(file.read_text() + " ")
    with pytest.raises(LayoutAuthorityError, match="SHARED_HISTORY_CHANGED"):
        ledger.guard()


def test_insufficient_remaining_wall_time_denies_b_reserve(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.execution_authorization.finish_pool()
    file = stores[0].shared_root / "shared-resource-ledger.json"
    state = json.loads(file.read_text())
    state["started_monotonic"] -= 100
    file.write_text(json.dumps(state))
    with pytest.raises(LayoutAuthorityError, match="NOT_EXECUTED_RESOURCE_LIMIT"):
        stores[1].open("MAIN")


def test_operator_ci_gate_precedes_any_approval_and_exposes_no_budget(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("run_stage_b_functional_shape_ab")
    source = tmp_path / "owner.txt"
    source.write_bytes(b"synthetic-owner-instruction")
    monkeypatch.setattr(module, "OWNER_SHA256", hashlib.sha256(source.read_bytes()).hexdigest())
    monkeypatch.setattr(module, "committed_source", lambda *_: None)

    def blocked(*args):
        raise LayoutAuthorityError("GUIDED_FAIR_EXACT_HEAD_CI_ADMISSION_BLOCKED")

    monkeypatch.setattr(module, "github_admission", blocked)
    monkeypatch.setattr(
        module, "execute", lambda *a: pytest.fail("CI-blocked must never approve/open")
    )
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["entry", "--owner-instruction", str(source), "--output", str(tmp_path / "out")],
    )
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        module.main()
    assert not (tmp_path / "out").exists()


def test_missing_shared_history_cannot_recreate_consumed_allowance(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.execution_authorization.finish_pool()
    (stores[0].shared_root / "shared-resource-ledger.json").unlink()
    with pytest.raises(LayoutAuthorityError, match="HISTORY"):
        stores[1].open("MAIN")


def test_exhausted_target_is_resource_not_infeasible(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.solver_wall = ledger.solver_monotonic_wall = 49.8
    ledger.checkpoint("SYNTHETIC_ACCOUNTED")
    with pytest.raises(LayoutAuthorityError, match="ALLOWANCE_EXHAUSTED"):
        ledger.remaining_solver_seconds()


@pytest.mark.parametrize("arm", [0, 1])
def test_declared_arm_rejects_other_arm_actual_final_guidance_receipt(tmp_path, monkeypatch, arm):
    stores, bindings, _ = setup(tmp_path, monkeypatch)
    first = stores[0].open("MAIN")
    if arm:
        first.execution_authorization.finish_pool()
        ledger = stores[1].open("MAIN")
    else:
        ledger = first
    lease = admit(ledger, bindings[arm])
    begin(lease, bindings[arm], 0)
    sources = {
        **{k: bindings[arm][k] for k in ("zone_plan_hash", "p1_hash", "site_hash")},
        "composition_hash": bindings[arm]["compositions"][0]["composition_hash"],
    }
    wrong = ab.ARM_POLICIES["A" if arm else "B"]
    with pytest.raises(LayoutAuthorityError, match="GUIDANCE_RECEIPT_MISMATCH"):
        lease.record_enumeration(
            sources,
            {
                "kind": "FINAL_MODEL_GUIDANCE_APPLIED",
                "guidance": {"policy": wrong[0], "policy_hash": wrong[1]},
            },
        )
    expected = ab.ARM_POLICIES["B" if arm else "A"]
    lease.record_enumeration(
        sources,
        {
            "kind": "FINAL_MODEL_GUIDANCE_APPLIED",
            "guidance": {"policy": expected[0], "policy_hash": expected[1]},
        },
    )
    assert len(lease.record["enumeration_events"]) == 1


def test_peer_summary_cannot_erase_verified_consumption(tmp_path, monkeypatch):
    stores, _, _ = setup(tmp_path, monkeypatch)
    ledger = stores[0].open("MAIN")
    ledger.charge("SYNTHETIC_ACCOUNTED_WORK", 50)
    ledger.checkpoint("SYNTHETIC_ACCOUNTED")
    ledger.execution_authorization.finish_pool()
    path = stores[0].shared_root / "shared-resource-ledger.json"
    state = json.loads(path.read_text())
    state["arms"]["A"]["totals"]["observable_work"] = 0
    path.write_text(json.dumps(state))
    with pytest.raises(LayoutAuthorityError, match="CONSUMPTION_UNVERIFIED"):
        stores[1].open("MAIN")


def test_no_candidates_report_is_deterministic_and_inconclusive(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    module = importlib.import_module("analyze_stage_b_functional_shape_ab")
    output = tmp_path / "analysis"
    output.mkdir()
    (output / "source-admission.json").write_text(json.dumps({"head": "synthetic"}))
    for arm in ("a", "b"):
        root = output / ("arm-" + arm)
        root.mkdir()
        (root / "pool.json").write_text(
            json.dumps(
                {
                    "status": "RESOURCE_LIMITED_NOT_PROJECT_INFEASIBLE",
                    "distinct_physical_geometry_count": 0,
                    "distinct_meaningful_construction_count": 0,
                    "major_structural_family_count": 0,
                    "compositions": [],
                }
            )
        )
        (root / "resource-ledger.json").write_text(
            json.dumps(
                {
                    "pools": [
                        {
                            "counters": {"checked_solutions": 0, "attempts": []},
                        }
                    ]
                }
            )
        )
    repo = Path(__file__).resolve().parents[3]
    module.analyze(output, repo)
    first = (output / "candidate-quality-comparison.json").read_bytes()
    module.analyze(output, repo)
    assert first == (output / "candidate-quality-comparison.json").read_bytes()
    receipt = json.loads((output / "ab-conclusion.json").read_text())
    assert receipt["conclusion"] == "INCONCLUSIVE"
    assert receipt["real_replay_determinism"] == "NOT_EVALUATED"
