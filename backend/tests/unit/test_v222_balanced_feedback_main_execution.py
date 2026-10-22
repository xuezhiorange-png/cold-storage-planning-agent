"""Synthetic fixtures only: no real registry, Native solve, Owner Grant or Claim."""

import hashlib
import importlib
import inspect
import json
import shutil
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from cold_storage.bootstrap.stage_b_balanced_feedback_main import approved_balanced_main_store
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import (
    stage_b_balanced_feedback_main_execution as main,
)
from cold_storage.modules.layout.infrastructure.stage_b_feasibility_main_execution import (
    TASK as OLD_TASK,
)
from tests.unit.test_v222_multi_solution_execution import _fair_registry
from tests.unit.test_v222_stage_b_pool_execution import admit, begin


def test_new_resource_contract_tests_use_existing_independent_worker():
    from tests.stage_a_resource_process import RESOURCE_TEST_FILES

    assert Path(__file__).name in RESOURCE_TEST_FILES


def test_actual_normalized_scope_is_pinned_and_requires_future_execution_confirmation(tmp_path):
    from cold_storage.modules.layout.infrastructure.stage_b_balanced_main_execution import (
        OWNER_SHA256 as OLD_OWNER,
    )
    from cold_storage.modules.layout.infrastructure.stage_b_balanced_main_execution import (
        TASK as OLD_BALANCED_TASK,
    )

    repo = Path(__file__).resolve().parents[3]
    raw = (repo / "docs/tasks/V2_2_2-stage-b-balanced-feedback-owner-scope.txt").read_bytes()
    assert raw.endswith(b"\n") and b"\r" not in raw
    assert hashlib.sha256(raw).hexdigest() == main.owner_execution_digest() != OLD_OWNER
    assert main.TASK.encode() in raw and OLD_BALANCED_TASK.encode() not in raw
    assert b"EXECUTION_REQUIRES_SEPARATE_OWNER_EXACT_HEAD_CONFIRMATION=true\n" in raw
    assert b"PREPARATION_AUTHORIZES_GRANT_OR_CLAIM_CREATION=false\n" in raw
    assert main.POLICY_HASH == (
        "sha256:201bf90a47095fe6831ca7ea6c41b42c24fc82006cb9683a6508b3ac9d1cb06e"
    )
    assert main.FEEDBACK_POLICY_HASH == (
        "sha256:78b6566b21568cba14b4f8ef574bb6db30e3d7e381aefbdd6bf0139c8792155e"
    )
    # Original verifier, actual normalized bytes, only a temporary synthetic repo.
    _, common = _fair_registry(tmp_path)
    common["runtime_dependency_hash"] = "SYNTHETIC_NO_INSTALLED_DEPENDENCIES"
    store = main.BalancedMainStore(tmp_path / "synthetic-pinned-scope-only")
    store.approve(raw, main.main_binding(common))
    store.require_unclaimed_grant()
    store.validate_existing_binding(raw, main.main_binding(common))
    assert not (store.root / "task_ledger.json").exists()
    assert not list(store.root.glob("pool_*_claim.json"))


@pytest.mark.parametrize("bad", ["OLD_FIXED_QUANTUM_POLICY", "OLD_R1_POLICY", "APPROVED"])
def test_obsolete_or_caller_asserted_feedback_policy_refused(tmp_path, monkeypatch, bad):
    store, binding, raw = setup(tmp_path, monkeypatch)
    binding["balanced_feedback_policy_hash"] = bad
    with pytest.raises(LayoutAuthorityError, match="POLICY_OR_SOURCE"):
        store.validate_existing_binding(raw, binding)


def setup(tmp_path, monkeypatch):
    _, common = _fair_registry(tmp_path)
    raw = ("SYNTHETIC ACCOUNTING NOT OWNER EXECUTION " + main.TASK).encode()
    monkeypatch.setattr(main, "OWNER_SHA256", hashlib.sha256(raw).hexdigest())
    common["runtime_dependency_hash"] = "SYNTHETIC_INSTALLED_BYTE_HASH"
    binding = main.main_binding(common)
    store = main.BalancedMainStore(tmp_path / "isolated-registry")
    store.approve(raw, binding)
    return store, binding, raw


def runner(monkeypatch):
    # Do not leak scripts path to unrelated source-only tests.
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
        return importlib.import_module("run_stage_b_balanced_feedback_main")


def test_bootstrap_fixed_identity_hash_bound_but_no_grant_created(tmp_path):
    assert main.owner_execution_digest() == (
        "24e42afba3d23fa5ade9c44fb051e4e118ad00ab0165008629faa73a1727aa5e"
    )
    assert not inspect.signature(approved_balanced_main_store).parameters
    store = main.BalancedMainStore(tmp_path / "registry")
    assert store.task_id == main.TASK != OLD_TASK
    assert store.root.name == hashlib.sha256(main.TASK.encode()).hexdigest()
    assert not store.root.exists()
    with pytest.raises(LayoutAuthorityError, match="PREISSUED_OWNER_GRANT_REQUIRED"):
        store.require_unclaimed_grant()
    with pytest.raises(LayoutAuthorityError, match="OWNER_DECISION_REQUIRED"):
        store.open("MAIN")
    assert not store.root.exists()


def test_unarmed_entry_refuses_before_ci_inputs_or_output(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "OWNER_SHA256", None)
    entry = runner(monkeypatch)
    for name in ("github_admission", "server_inputs", "approved_balanced_main_store"):
        monkeypatch.setattr(entry, name, lambda *_: pytest.fail("unarmed execution reached gate"))
    with pytest.raises(LayoutAuthorityError, match="OWNER_EXECUTION_NOT_PINNED"):
        entry.run_main(tmp_path / "output", tmp_path / "no-execution-instruction")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("digest", ["", "APPROVED", "0" * 63, "X" * 64])
def test_caller_approval_strings_are_not_execution_digests(monkeypatch, digest):
    monkeypatch.setattr(main, "OWNER_SHA256", digest)
    with pytest.raises(LayoutAuthorityError, match="NOT_PINNED"):
        main.owner_execution_digest()


def test_correct_owner_bytes_without_grant_refuse_before_inputs(tmp_path, monkeypatch):
    entry = runner(monkeypatch)
    raw = ("SYNTHETIC " + main.TASK).encode()
    monkeypatch.setattr(main, "OWNER_SHA256", hashlib.sha256(raw).hexdigest())
    p = tmp_path / "owner.txt"
    p.write_bytes(raw)
    store = main.BalancedMainStore(tmp_path / "no-grant")
    monkeypatch.setattr(entry, "committed_source", lambda _: None)
    monkeypatch.setattr(entry, "github_admission", lambda _: {"status": "SYNTHETIC_SUCCESS"})
    monkeypatch.setattr(entry, "approved_balanced_main_store", lambda: store)
    monkeypatch.setattr(entry, "server_inputs", lambda *_: pytest.fail("inputs without Grant"))
    with pytest.raises(LayoutAuthorityError, match="PREISSUED_OWNER_GRANT_REQUIRED"):
        entry.run_main(tmp_path / "output", p)
    assert not store.root.exists() and not (tmp_path / "output").exists()


def test_preissued_grant_reopens_read_only_with_original_checks(tmp_path, monkeypatch):
    store, binding, raw = setup(tmp_path, monkeypatch)
    original = {p.name: p.read_bytes() for p in store.root.iterdir()}
    fresh = main.BalancedMainStore(store.root.parent)
    fresh.require_unclaimed_grant()
    fresh.validate_existing_binding(raw, binding)
    assert {p.name: p.read_bytes() for p in store.root.iterdir()} == original
    assert not (store.root / "task_ledger.json").exists()


@pytest.mark.parametrize("field", ["head", "zone_plan_hash", "p1_hash", "site_hash"])
def test_preissued_scope_cannot_be_rebound(tmp_path, monkeypatch, field):
    store, binding, raw = setup(tmp_path, monkeypatch)
    store.require_unclaimed_grant()
    binding[field] = "FORGED"
    with pytest.raises(LayoutAuthorityError, match="GRANT_BINDING_MISMATCH"):
        store.validate_existing_binding(raw, binding)
    assert not (store.root / "task_ledger.json").exists()


@pytest.mark.parametrize(
    "residue", ["pool_1_claim.json", "active.lock", "task_ledger.json", "journal.jsonl"]
)
def test_orphan_or_consumed_slot_never_resets(tmp_path, monkeypatch, residue):
    store, _, _ = setup(tmp_path, monkeypatch)
    p = store.root / residue
    p.write_bytes(b"SYNTHETIC CONSUMED OR INTERRUPTED")
    fresh = main.BalancedMainStore(store.root.parent)
    with pytest.raises(LayoutAuthorityError, match="EXISTING_FIXED_SLOT"):
        fresh.require_unclaimed_grant()
    assert p.read_bytes() == b"SYNTHETIC CONSUMED OR INTERRUPTED"


@pytest.mark.parametrize("field", ["task_id", "owner_instruction_sha256", "caps", "head"])
def test_reloaded_forged_or_old_decision_rejected(tmp_path, monkeypatch, field):
    store, _, _ = setup(tmp_path, monkeypatch)
    p = store.root / "owner_decision.json"
    body = json.loads(p.read_text())
    body[field] = OLD_TASK if field == "task_id" else "APPROVED"
    p.write_text(json.dumps(body))
    fresh = main.BalancedMainStore(store.root.parent)
    with pytest.raises(LayoutAuthorityError):
        fresh.require_unclaimed_grant()
    assert not (store.root / "task_ledger.json").exists()


@pytest.mark.parametrize(
    "old,new", [(b"49.9", b"50.0"), (b"600000", b"600001"), (b"false", b"true")]
)
def test_tampered_owner_budget_bytes_rejected_before_any_ci(tmp_path, monkeypatch, old, new):
    entry = runner(monkeypatch)
    raw = (
        main.TASK + "\nNATIVE_SECONDS_MAX=49.9\nWORK_MAX=600000\nREPLAY_AUTHORIZED=false\n"
    ).encode()
    monkeypatch.setattr(main, "OWNER_SHA256", hashlib.sha256(raw).hexdigest())
    p = tmp_path / "owner.txt"
    p.write_bytes(raw.replace(old, new))
    monkeypatch.setattr(entry, "github_admission", lambda *_: pytest.fail("tamper reached CI"))
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE_MISMATCH"):
        entry.run_main(tmp_path / "output", p)
    assert not (tmp_path / "output").exists()


def test_original_source_and_dependency_checks_remain_on_reload(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    Path(binding["dependency_file"]).write_bytes(b"SYNTHETIC DEPENDENCY TAMPER")
    with pytest.raises(LayoutAuthorityError, match="HEAD_OR_DEPENDENCY_CHANGED"):
        main.BalancedMainStore(store.root.parent).require_unclaimed_grant()


def test_single_use_claim_and_six_handoffs_share_one_ledger(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    assert isinstance(lease, main.BalancedMainLease)
    with pytest.raises(LayoutAuthorityError, match="ACTIVE_CLAIM"):
        store.open("MAIN")
    for i in range(6):
        begin(lease, binding, i)
        # Represent both stages on the same original cumulative ledger.
        ledger.charge("SYNTHETIC_BASELINE", 1)
        ledger.charge("SYNTHETIC_BALANCED_CONTINUATION", 2)
        ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
    assert lease.totals()["observable_work"] == 18
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="CONSUMED"):
        store.open("MAIN")
    state = json.loads((store.root / "task_ledger.json").read_text())
    assert len(state["pools"]) == len(list(store.root.glob("pool_*_claim.json"))) == 1


@pytest.mark.parametrize("mode", ["REPLAY", "RESUME", "MAIN-2", "A", "B"])
def test_no_second_mode(tmp_path, monkeypatch, mode):
    store, _, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(LayoutAuthorityError, match="ONLY_ONE_MAIN"):
        store.open(mode)
    assert not list(store.root.glob("pool_*_claim.json"))


@pytest.mark.parametrize(
    "field",
    [
        "balanced_quality_task",
        "balanced_quality_policy_hash",
        "balanced_shape_policy_hash",
        "balanced_feedback_policy_hash",
        "single_main_contract",
        "single_main_contract_hash",
        "runtime_dependency_hash",
        "schedule_hash",
        "fair_search_policy_hash",
    ],
)
def test_contract_policy_and_source_cannot_be_overridden(tmp_path, monkeypatch, field):
    store, binding, raw = setup(tmp_path, monkeypatch)
    binding[field] = "" if field == "runtime_dependency_hash" else "FORGED"
    with pytest.raises(LayoutAuthorityError):
        store.approve(raw, binding)


def test_old_authorization_bytes_and_copied_decision_fail(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE"):
        store.approve(b"old Owner authorization", binding)


def test_task_identity_tamper_in_durable_decision_is_rejected(tmp_path, monkeypatch):
    store, _, _ = setup(tmp_path, monkeypatch)
    p = store.root / "owner_decision.json"
    decision = json.loads(p.read_text())
    decision["balanced_quality_task"] = OLD_TASK
    p.write_text(json.dumps(decision))
    with pytest.raises(LayoutAuthorityError, match="DECISION_REQUIRED_OR_CHANGED"):
        store.open("MAIN")


def test_old_claim_and_decision_copied_into_new_slot_cannot_be_used(tmp_path, monkeypatch):
    old, _ = _fair_registry(tmp_path)
    raw = ("SYNTHETIC " + main.TASK).encode()
    monkeypatch.setattr(main, "OWNER_SHA256", hashlib.sha256(raw).hexdigest())
    new = main.BalancedMainStore(tmp_path / "different-registry")
    assert old.root != new.root
    shutil.copytree(old.root, new.root)
    (new.root / "pool_1_claim.json").write_text('{"ordinal":1}')
    new.approved_digest = hashlib.sha256(
        (new.root / "owner_decision.json").read_bytes()
    ).hexdigest()
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE"):
        new.open("MAIN")


@pytest.mark.parametrize(
    "field,value",
    [
        ("solver_wall", 49.91),
        ("solver_monotonic_wall", 49.91),
        ("model_work", 600001),
        ("checked_solutions", 21),
        ("peak_rss_bytes", 536870913),
    ],
)
def test_synthetic_resource_state_not_real_process_rss(tmp_path, monkeypatch, field, value):
    store, _, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    setattr(ledger, field, value)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.guard()


def test_remainder_calls_and_elapsed_not_reset_for_second_phase(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    ledger.solver_wall = ledger.solver_monotonic_wall = 20
    ledger.checkpoint("SYNTHETIC_BASELINE_RECORDED")
    assert ledger.remaining_solver_seconds() == pytest.approx(29.8)
    ledger.attempts.extend({"synthetic": i} for i in range(100))
    with pytest.raises(LayoutAuthorityError, match="NATIVE_CALL_LIMIT"):
        ledger.remaining_solver_seconds()
    from cold_storage.modules.layout.infrastructure import stage_b_feasibility_main_execution

    monkeypatch.setattr(
        stage_b_feasibility_main_execution,
        "time",
        SimpleNamespace(monotonic=lambda: ledger.started + 85.1),
    )
    with pytest.raises(LayoutAuthorityError, match="RESOURCE_LIMIT"):
        lease.guard(ledger)


def test_correct_balanced_receipts_not_old_semiperimeter(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = binding["compositions"][0]["composition_hash"]
    for kind in ("FINAL_MODEL_GUIDANCE_APPLIED", "BOUNDED_IMPROVEMENT_STARTED"):
        with pytest.raises(LayoutAuthorityError, match="GUIDANCE_RECEIPT"):
            lease.record_enumeration(sources, dict(kind=kind, guidance=dict(policy_hash="OLD")))
    lease.record_enumeration(
        sources,
        dict(kind="BOUNDED_IMPROVEMENT_STARTED", guidance=dict(policy_hash=main.POLICY_HASH)),
    )
    with pytest.raises(LayoutAuthorityError, match="GUIDANCE_RECEIPT"):
        lease.record_enumeration(sources, dict(kind="FEASIBILITY_FIRST_QUALITY_FACTS"))


def test_incomplete_native_accounting_is_not_restartable(tmp_path, monkeypatch):
    store, binding, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    ledger.native_solver_active = True
    ledger.solver_history_verified = False
    ledger.checkpoint("CP_SAT_STARTED")  # Synthetic state, no solver call.
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="UNVERIFIED"):
        store.open("MAIN")


def test_pending_full_ci_rejects_before_store_or_input_creation(tmp_path, monkeypatch):
    entry = runner(monkeypatch)
    raw = b"SYNTHETIC SOURCE ONLY"
    p = tmp_path / "owner.txt"
    p.write_bytes(raw)
    monkeypatch.setattr(entry, "owner_execution_digest", lambda: hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(entry, "committed_source", lambda _: None)

    def blocked(_):
        raise LayoutAuthorityError("EXACT_HEAD_FULL_CI_REQUIRED")

    monkeypatch.setattr(entry, "github_admission", blocked)
    monkeypatch.setattr(
        entry, "approved_balanced_main_store", lambda: pytest.fail("store before full CI")
    )
    with pytest.raises(LayoutAuthorityError, match="FULL_CI_REQUIRED"):
        entry.run_main(tmp_path / "output", p)
    assert not (tmp_path / "output").exists()


def test_real_operator_flow_with_mocked_pool_never_calls_native(tmp_path, monkeypatch):
    entry = runner(monkeypatch)
    _, common = _fair_registry(tmp_path)
    raw = ("SYNTHETIC MOCK POOL " + main.TASK).encode()
    monkeypatch.setattr(main, "OWNER_SHA256", hashlib.sha256(raw).hexdigest())
    source = tmp_path / "owner.txt"
    source.write_bytes(raw)
    store = main.BalancedMainStore(tmp_path / "new-synthetic-registry")
    site = SimpleNamespace(to_dict=lambda: {})
    monkeypatch.setattr(entry, "committed_source", lambda _: None)
    monkeypatch.setattr(entry, "github_admission", lambda _: {"head": common["head"]})
    monkeypatch.setattr(entry, "approved_balanced_main_store", lambda: store)
    monkeypatch.setattr(entry, "server_inputs", lambda _: ({}, {}, site))
    monkeypatch.setattr(entry, "runtime_dependencies", lambda: {"synthetic": "not-installed-data"})
    monkeypatch.setattr(entry, "fair_binding", lambda *_: common)
    repo = Path(entry.__file__).resolve().parents[2]
    tracked = entry.subprocess.check_output(
        [
            "git",
            "ls-files",
            "backend/src",
            "backend/scripts",
            "docs/tasks/V2_2_2-stage-b-balanced-feedback-owner-scope.txt",
        ],
        cwd=repo,
        text=True,
    ).splitlines()
    common["source_files"].update(
        {str(repo / n): hashlib.sha256((repo / n).read_bytes()).hexdigest() for n in tracked}
    )
    common["runtime_dependency_hash"] = main.canonical_hash(entry.runtime_dependencies())
    # Independent synthetic issuance in a temporary registry, BEFORE execution.
    store.approve(raw, main.main_binding(common))
    decision_bytes = (store.root / "owner_decision.json").read_bytes()
    monkeypatch.setattr(store, "approve", lambda *_: pytest.fail("runner issued a Grant"))
    monkeypatch.setattr(
        entry, "bind_layout_authority", lambda *_: SimpleNamespace(access_requirements=[])
    )
    seen = []

    def synthetic_pool(*args, solver, execution_ledger, fair_search):
        assert type(solver).__name__ == "StageBBalancedQualityFairSearchSolver"
        assert fair_search is True
        seen.append(execution_ledger)
        bound = store._decision()
        lease = admit(execution_ledger, bound)
        for i in range(6):
            begin(lease, bound, i)
            execution_ledger.charge("SYNTHETIC_NO_SOLVE", 1)
            execution_ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
        return dict(status="SYNTHETIC_NO_SOLVE", canonical_result_hash="synthetic", attempts=[])

    monkeypatch.setattr(entry, "generate_multi_solution_pool", synthetic_pool)
    out = tmp_path / "output"
    entry.run_main(out, source)
    assert len(seen) == 1
    assert (store.root / "owner_decision.json").read_bytes() == decision_bytes
    assert json.loads((out / "execution-summary.json").read_text())["task"] == main.TASK
    usage = json.loads((out / "resource-usage.json").read_text())
    assert usage["native_calls"] == usage["native_solver_seconds"] == 0
    assert usage["observable_work"] == 6
    assert usage["resource_caps_respected"]
    assert (out / "resource-ledger.json").read_bytes() == (
        store.root / "task_ledger.json"
    ).read_bytes()
    with pytest.raises(LayoutAuthorityError, match="EXISTING_FIXED_SLOT"):
        entry.run_main(tmp_path / "another-output", source)


def test_baseline_and_comparison_events_use_same_durable_lease(tmp_path, monkeypatch):
    from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
        StageBBalancedQualityFairSearchSolver,
    )
    from tests.unit.test_v222_stage_b_balanced_quality import diagnostic_candidate

    store, binding, _ = setup(tmp_path, monkeypatch)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    context = SimpleNamespace(
        ledger=ledger,
        binding=SimpleNamespace(
            canonical_zone_plan_hash=binding["zone_plan_hash"],
            p1_handoff_hash=binding["p1_hash"],
            site_geometry_hash=binding["site_hash"],
        ),
    )
    handoff = SimpleNamespace(
        source_composition_hash=binding["compositions"][0]["composition_hash"]
    )
    solver = StageBBalancedQualityFairSearchSolver()
    solver.start_handoff(ledger, 6)
    candidate = diagnostic_candidate()
    candidate["source_composition_hash"] = handoff.source_composition_hash
    before = deepcopy(candidate)
    solver.observe_validated_candidate(context, handoff, candidate, "ENGINEERING_ACCEPTED")
    baseline = deepcopy(solver.baseline)
    solver.observe_validated_candidate(context, handoff, candidate, "ENGINEERING_ACCEPTED")
    assert solver.native.ledger is ledger
    assert solver.baseline == baseline and candidate == before
    assert len(lease.record["enumeration_events"]) == 2
    assert (
        lease.record["enumeration_events"][0]["baseline"]["candidate_hash"]
        == (candidate["canonical_result_hash"])
    )


def test_operator_exposes_no_caller_policy_budget_seed_or_task(monkeypatch):
    entry = runner(monkeypatch)
    source = inspect.getsource(entry.run_main)
    assert source.count('store.open("MAIN")') == 1
    assert "StageBBalancedQualityFairSearchSolver()" in source
    assert "execution_ledger=ledger" in source
    assert "store.approve(" not in source
    assert source.index("github_admission(repo)") < source.index("store.require_unclaimed_grant()")
    assert source.index("store.require_unclaimed_grant()") < source.index("server_inputs(repo)")
    assert source.index("store.validate_existing_binding(") < source.index('store.open("MAIN")')
    assert "task=TASK" in source
    assert "--budget" not in inspect.getsource(entry.main)
    assert "--policy" not in inspect.getsource(entry.main)
    assert "--task" not in inspect.getsource(entry.main)


def test_default_bootstrap_and_original_solver_entry_not_replaced():
    from cold_storage.bootstrap import global_composition

    source = inspect.getsource(global_composition)
    assert "StageBBalancedQualityFairSearchSolver" not in source
    assert main.CONTRACT["native_seconds"] == 49.9
    assert main.CONTRACT["elapsed_seconds"] == 85
    assert main.CONTRACT["observable_work"] == 600000
    assert main.CONTRACT["memory_bytes"] == 536870912
    assert main.CONTRACT["checked_assignments"] == 20
