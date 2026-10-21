"""Synthetic accounting only. Never allocate the actual Owner slot or solve a factory."""

import hashlib
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cold_storage.bootstrap.stage_b_feasibility_main import approved_feasibility_first_main_store
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure import stage_b_feasibility_main_execution as main
from tests.unit.test_v222_multi_solution_execution import _fair_registry
from tests.unit.test_v222_stage_b_pool_execution import admit, begin


def setup(tmp_path, monkeypatch):
    _, common = _fair_registry(tmp_path)
    raw = ("SYNTHETIC ACCOUNTING ONLY " + main.TASK).encode()
    monkeypatch.setattr(main, "OWNER_SHA256", hashlib.sha256(raw).hexdigest())
    common["runtime_dependency_hash"] = "SYNTHETIC_RUNTIME_FINGERPRINT"
    binding = main.main_binding(common)
    store = main.FeasibilityFirstMainStore(tmp_path / "isolated-registry")
    store.approve(raw, binding)
    return store, binding, raw


def test_bootstrap_fixed_task_and_owner_digest_no_caller_slot_or_budget():
    assert not inspect.signature(approved_feasibility_first_main_store).parameters
    store = approved_feasibility_first_main_store()  # Constructor performs no write/open.
    assert store.task_id == "V2_2_2_STAGE_B_FEASIBILITY_FIRST_REAL_MAIN_R1"
    assert store.owner_digest == main.OWNER_SHA256
    assert store.root.name == hashlib.sha256(main.TASK.encode()).hexdigest()


def test_single_main_exclusive_and_consumed_after_finish(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    with pytest.raises(LayoutAuthorityError, match="ACTIVE_CLAIM"):
        store.open("MAIN")
    for i in range(6):
        begin(lease, binding, i)
        ledger.charge("SYNTHETIC_WORK", 1)
        ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
    assert lease.totals()["observable_work"] == 6
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="CONSUMED"):
        store.open("MAIN")


@pytest.mark.parametrize("mode", ["REPLAY", "RESUME", "NEW", "B", "MAIN-2"])
def test_unauthorized_modes_rejected_without_claim(tmp_path, monkeypatch, mode):
    store, _, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(LayoutAuthorityError, match="ONLY_ONE_MAIN"):
        store.open(mode)
    assert not list(store.root.glob("pool_*_claim.json"))


@pytest.mark.parametrize(
    "field",
    [
        "feasibility_first_task",
        "feasibility_first_policy_hash",
        "single_main_contract_hash",
        "runtime_dependency_hash",
        "schedule_hash",
        "fair_search_policy_hash",
    ],
)
def test_policy_source_or_contract_tamper_refused(tmp_path, monkeypatch, field):
    store, binding, raw = setup(tmp_path, monkeypatch)
    binding[field] = "" if field == "runtime_dependency_hash" else "FORGED"
    with pytest.raises(LayoutAuthorityError):
        store.approve(raw, binding)


def test_wrong_instruction_bytes_rejected(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE"):
        store.approve(b"caller APPROVED=true", binding)


@pytest.mark.parametrize(
    "field,value",
    [
        ("solver_wall", 49.91),
        ("model_work", 600001),
        ("checked_solutions", 21),
        ("peak_rss_bytes", 513 * 1024 * 1024),
    ],
)
def test_single_main_caps_are_real_guards(tmp_path, monkeypatch, field, value):
    store, _, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    setattr(ledger, field, value)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.guard()


def test_elapsed_and_native_remainder_not_refilled_per_composition(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    ledger.solver_wall = ledger.solver_monotonic_wall = 20
    ledger.checkpoint("SYNTHETIC_COUNTERS")
    ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
    begin(lease, binding, 1)
    assert ledger.remaining_solver_seconds() == pytest.approx(29.8)
    ledger.attempts.extend({"synthetic": i} for i in range(100))
    with pytest.raises(LayoutAuthorityError, match="NATIVE_CALL_LIMIT"):
        ledger.remaining_solver_seconds()
    monkeypatch.setattr(main, "time", SimpleNamespace(monotonic=lambda: ledger.started + 85.1))
    with pytest.raises(LayoutAuthorityError, match="RESOURCE_LIMIT"):
        lease.guard(ledger)


def test_unknown_interruption_and_deleted_ledger_cannot_restart(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    ledger.native_solver_active = True
    ledger.checkpoint("CP_SAT_STARTED")
    ledger.solver_history_verified = False
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="UNVERIFIED"):
        store.open("MAIN")
    (store.root / "task_ledger.json").unlink()  # Synthetic isolated corruption case only.
    with pytest.raises(LayoutAuthorityError, match="HISTORY_MISSING"):
        store.open("MAIN")


def test_wrong_final_or_improvement_guidance_rejected(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = binding["compositions"][0]["composition_hash"]
    for kind in ("FINAL_MODEL_GUIDANCE_APPLIED", "BOUNDED_IMPROVEMENT_STARTED"):
        with pytest.raises(LayoutAuthorityError, match="GUIDANCE_RECEIPT"):
            lease.record_enumeration(sources, {"kind": kind, "guidance": {"policy_hash": "fake"}})


def test_real_entry_ci_block_prevents_even_store_approval(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    runner = importlib.import_module("run_stage_b_feasibility_first_main")
    raw = b"SYNTHETIC CI ADMISSION TEST"
    source = tmp_path / "instruction.txt"
    source.write_bytes(raw)
    monkeypatch.setattr(runner, "OWNER_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(runner, "committed_source", lambda *_: None)

    def blocked(*args):
        raise LayoutAuthorityError("EXACT_HEAD_CI_PENDING")

    monkeypatch.setattr(runner, "github_admission", blocked)
    monkeypatch.setattr(
        runner,
        "approved_feasibility_first_main_store",
        lambda: pytest.fail("Must not allocate before CI admission"),
    )
    with pytest.raises(LayoutAuthorityError, match="CI_PENDING"):
        runner.run_main(tmp_path / "output", source)
    assert not (tmp_path / "output").exists()


def test_entry_only_exposes_owner_bytes_and_output_no_replay_or_seed(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    runner = importlib.import_module("run_stage_b_feasibility_first_main")
    source = inspect.getsource(runner.run_main)
    assert source.count('store.open("MAIN")') == 1
    assert 'store.open("REPLAY")' not in source
    assert "StageBFeasibilityFirstFairSearchSolver()" in source
    assert source.index("github_admission(repo)") < source.index("store.approve(")
    assert source.index("store.approve(") < source.index('store.open("MAIN")')


def test_export_keeps_baseline_and_same_geometry_route_variant_separate(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    runner = importlib.import_module("run_stage_b_feasibility_first_main")
    monkeypatch.setattr(runner, "_eligible", lambda *_: True)
    monkeypatch.setattr(runner, "_quality_facts", lambda c: {"synthetic": True})

    def render(folder, result, site, ids):
        folder = folder / "candidate-01"
        folder.mkdir(parents=True)
        candidate = result["attempts"][0]["candidate_result"]
        (folder / "candidate.json").write_text(json.dumps(candidate))
        (folder / "layout.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><text>SYNTHETIC_TEST_ONLY</text></svg>'
        )

    monkeypatch.setattr(runner, "export_fair_pool", render)
    attempts, events = [], []
    for stage in ("FEASIBILITY_FIRST", "BOUNDED_QUALITY_IMPROVEMENT"):
        candidate = {
            "proposal": {"geometry_hash": "same-room-geometry", "search_stage": stage},
            "source_composition_hash": "same-synthetic-handoff",
        }
        candidate["canonical_result_hash"] = canonical_hash(candidate)
        attempts.append({"candidate_result": candidate, "status": "SYNTHETIC_NOT_COUNTED"})
        events.append({"kind": "VALIDATION_RESULT", "candidate_result": candidate})
    events.append({"kind": "BOUNDED_IMPROVEMENT_STARTED"})
    lease = SimpleNamespace(record={"enumeration_events": events, "cursor": 1})
    runner.export_evidence(tmp_path, {"attempts": attempts}, lease, None, set())
    rows = json.loads((tmp_path / "candidate-index.json").read_text())
    assert len(rows) == 2 and rows[0]["svg"] != rows[1]["svg"]
    assert {r["candidate_hash"] for r in rows} == {
        c["candidate_result"]["canonical_result_hash"] for c in attempts
    }
    summary = json.loads((tmp_path / "execution-summary.json").read_text())
    assert summary["baseline_preserved"] and summary["baseline_hashes_unchanged"]
    assert summary["improvement_new_geometry_count"] == 0
    assert summary["real_two_stage_result"] == "INCONCLUSIVE"  # No comparison receipt; don't guess.
    assert summary["p2d_full_pass_count"] == 0


def test_no_candidate_export_does_not_fabricate_baseline_or_svg(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    runner = importlib.import_module("run_stage_b_feasibility_first_main")
    lease = SimpleNamespace(record={"enumeration_events": [], "cursor": 6})
    runner.export_evidence(tmp_path, {"attempts": []}, lease, None, set())
    summary = json.loads((tmp_path / "execution-summary.json").read_text())
    assert summary["real_two_stage_result"] == "INCONCLUSIVE"
    assert summary["baseline_preserved"] == "NOT_APPLICABLE_NO_VALID_BASELINE"
    assert not list(tmp_path.rglob("*.svg"))
