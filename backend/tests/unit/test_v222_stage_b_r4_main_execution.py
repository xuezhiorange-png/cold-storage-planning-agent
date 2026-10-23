"""Temporary synthetic registries and mocked pool only. Native calls forbidden."""

import hashlib
import importlib
import inspect
import json
import shutil
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from ortools.sat.python import cp_model

from cold_storage.bootstrap.stage_b_r4_main import approved_r4_main_store
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_r4_main_execution as main
from cold_storage.modules.layout.infrastructure.stage_b_balanced_feedback_main_execution import (
    TASK as OLD_TASK,
)
from tests.unit.test_v222_multi_solution_execution import _fair_registry
from tests.unit.test_v222_stage_b_pool_execution import admit, begin

SCOPE = "docs/tasks/V2_2_2-stage-b-r4-owner-scope.txt"


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda *_: pytest.fail("Native forbidden"))


def owner_bytes():
    return (Path(__file__).resolve().parents[3] / SCOPE).read_bytes()


def setup(tmp_path):
    _, common = _fair_registry(tmp_path)
    common["runtime_dependency_hash"] = "SYNTHETIC_NOT_REAL_RUNTIME"
    binding = main.main_binding(common)
    store = main.R4MainStore(tmp_path / "r4-synthetic-registry")
    store.approve(owner_bytes(), binding)  # Temporary Fixture issuance, never real registry.
    return store, binding


def runner():
    with pytest.MonkeyPatch.context() as p:
        p.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
        return importlib.import_module("run_stage_b_r4_main")


def test_r4_fixed_scope_hash_bootstrap_and_unused_identity(tmp_path):
    from tests.stage_a_resource_process import RESOURCE_TEST_FILES

    raw = owner_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert hashlib.sha256(raw).hexdigest() == main.owner_execution_digest()
    fields = dict(line.split("=", 1) for line in raw.decode().splitlines())
    for field, key in (
        ("PR_NUMBER", "pr_number"),
        ("PR_HEAD_REF", "head_ref"),
        ("PR_BASE_REF", "base_ref"),
        ("PR_BASE_SHA", "base_sha"),
    ):
        assert fields[field] == str(main.CI_IDENTITY[key])
    assert (
        tuple(
            fields[k]
            for k in (
                "POLICY_HASH",
                "FIRST_STAGE_POLICY_HASH",
                "SHAPE_POLICY_HASH",
                "FEEDBACK_POLICY_HASH",
            )
        )
        == main.BOUND_STRATEGIES
    )
    for field, key in (
        ("NATIVE_SECONDS_MAX", "native_seconds"),
        ("ELAPSED_SECONDS_MAX", "elapsed_seconds"),
        ("WORK_MAX", "observable_work"),
        ("NATIVE_CALLS_MAX", "native_calls"),
        ("COMPLETE_ASSIGNMENT_CHECKS_MAX", "checked_assignments"),
    ):
        assert float(fields[field]) == main.CONTRACT[key]
    assert int(fields["RSS_MAX_MIB"]) * 1024**2 == main.CONTRACT["memory_bytes"]
    assert main.TASK != OLD_TASK and main.TASK.encode() in raw
    assert (
        main.POLICY_HASH
        == "sha256:fad41d6d4be18248b9a5ee93e299a591876e40e2422ac0ed5aa3924c2e2e5156"
    )
    assert (
        main.FIRST_STAGE_POLICY_HASH
        == "sha256:ce5fd7a398ecfc93ed98ccc9108209fe011402d4dd81b697da9e8b70886fb940"
    )
    assert b"PREPARATION_AUTHORIZES_GRANT_OR_CLAIM_CREATION=false\n" in raw
    assert b"EXECUTION_REQUIRES_SEPARATE_OWNER_EXACT_HEAD_CONFIRMATION=true\n" in raw
    assert not inspect.signature(approved_r4_main_store).parameters
    assert Path(__file__).name in RESOURCE_TEST_FILES
    store = main.R4MainStore(tmp_path / "no-grant")
    assert store.root.name == hashlib.sha256(main.TASK.encode()).hexdigest()
    with pytest.raises(LayoutAuthorityError, match="PREISSUED_OWNER_GRANT_REQUIRED"):
        store.require_unclaimed_grant()
    with pytest.raises(LayoutAuthorityError, match="OWNER_DECISION_REQUIRED"):
        store.open("MAIN")
    assert not store.root.exists()


@pytest.mark.parametrize(
    "old,new", [(b"49.9", b"50.0"), (b"600000", b"600001"), (b"false", b"true")]
)
def test_r4_tampered_instruction_refused_before_ci(tmp_path, monkeypatch, old, new):
    entry = runner()
    p = tmp_path / "scope"
    p.write_bytes(owner_bytes().replace(old, new))
    monkeypatch.setattr(entry, "github_admission", lambda *_: pytest.fail("tamper reached CI"))
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE_MISMATCH"):
        entry.run_main(tmp_path / "output", p)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("digest", [None, "APPROVED", "x" * 64, "0" * 63])
def test_r4_unpinned_owner_refused(monkeypatch, digest):
    monkeypatch.setattr(main, "OWNER_SHA256", digest)
    with pytest.raises(LayoutAuthorityError, match="OWNER_EXECUTION_NOT_PINNED"):
        main.owner_execution_digest()


@pytest.mark.parametrize(
    "field", ["POLICY_HASH", "FIRST_STAGE_POLICY_HASH", "SHAPE_POLICY_HASH", "FEEDBACK_POLICY_HASH"]
)
def test_r4_owner_scope_cannot_silently_follow_a_future_policy(monkeypatch, tmp_path, field):
    monkeypatch.setattr(main, field, "OLD_OR_FUTURE_POLICY")
    with pytest.raises(LayoutAuthorityError, match="SCOPE_POLICY_SOURCE_CHANGED"):
        main.R4MainStore(tmp_path / "no-grant")
    assert not (tmp_path / "no-grant").exists()


def test_r4_pending_formal_ci_blocks_before_registry_or_inputs(tmp_path, monkeypatch):
    entry = runner()
    p = tmp_path / "scope"
    p.write_bytes(owner_bytes())
    monkeypatch.setattr(entry, "committed_source", lambda *_: None)

    def blocked(_):
        raise LayoutAuthorityError("EXACT_HEAD_FULL_CI_REQUIRED")

    monkeypatch.setattr(entry, "github_admission", blocked)
    monkeypatch.setattr(entry, "approved_r4_main_store", lambda: pytest.fail("registry before CI"))
    with pytest.raises(LayoutAuthorityError, match="FULL_CI_REQUIRED"):
        entry.run_main(tmp_path / "output", p)
    assert not (tmp_path / "output").exists()


def test_r4_correct_hash_without_grant_cannot_generate_inputs_or_claim(tmp_path, monkeypatch):
    entry = runner()
    p = tmp_path / "scope"
    p.write_bytes(owner_bytes())
    store = main.R4MainStore(tmp_path / "empty-registry")
    monkeypatch.setattr(entry, "committed_source", lambda *_: None)
    monkeypatch.setattr(entry, "github_admission", lambda _: {"head": "SYNTHETIC"})
    monkeypatch.setattr(entry, "approved_r4_main_store", lambda: store)
    monkeypatch.setattr(entry, "server_inputs", lambda *_: pytest.fail("inputs without Grant"))
    with pytest.raises(LayoutAuthorityError, match="PREISSUED_OWNER_GRANT_REQUIRED"):
        entry.run_main(tmp_path / "output", p)
    assert not store.root.exists() and not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "field",
    [
        "balanced_quality_task",
        "balanced_quality_policy_hash",
        "balanced_first_stage_policy_hash",
        "balanced_shape_policy_hash",
        "balanced_feedback_policy_hash",
        "single_main_contract",
        "single_main_contract_hash",
        "formal_ci_identity",
        "runtime_dependency_hash",
    ],
)
def test_r4_changed_binding_or_budget_refused(tmp_path, field):
    store, binding = setup(tmp_path)
    binding[field] = "" if field == "runtime_dependency_hash" else "OLD_OR_TAMPERED"
    with pytest.raises(LayoutAuthorityError, match="POLICY_OR_SOURCE"):
        store.validate_existing_binding(owner_bytes(), binding)
    assert not (store.root / "task_ledger.json").exists()


@pytest.mark.parametrize("field", ["pr_number", "base_ref", "base_sha", "head_ref"])
def test_r4_ci_binding_cannot_be_replaced_with_pr307_or_another_base(tmp_path, field):
    store, binding = setup(tmp_path)
    binding["formal_ci_identity"][field] = 307 if field == "pr_number" else "OLD"
    with pytest.raises(LayoutAuthorityError, match="POLICY_OR_SOURCE"):
        store.validate_existing_binding(owner_bytes(), binding)


@pytest.mark.parametrize("field", ["head", "zone_plan_hash", "p1_hash", "site_hash"])
def test_r4_fresh_server_scope_cannot_rebind_preissued_sources(tmp_path, field):
    store, binding = setup(tmp_path)
    binding[field] = "FORGED"
    with pytest.raises(LayoutAuthorityError, match="GRANT_BINDING_MISMATCH"):
        store.validate_existing_binding(owner_bytes(), binding)
    assert not (store.root / "task_ledger.json").exists()


def test_r4_original_dependency_and_source_verifier_still_runs(tmp_path):
    store, binding = setup(tmp_path)
    Path(binding["dependency_file"]).write_bytes(b"SYNTHETIC TAMPER")
    with pytest.raises(LayoutAuthorityError, match="HEAD_OR_DEPENDENCY_CHANGED"):
        main.R4MainStore(store.root.parent).require_unclaimed_grant()
    assert not (store.root / "task_ledger.json").exists()


@pytest.mark.parametrize(
    "residue", ["pool_1_claim.json", "task_ledger.json", "journal.jsonl", "active.lock"]
)
def test_r4_existing_or_consumed_slot_never_resets(tmp_path, residue):
    store, _ = setup(tmp_path)
    p = store.root / residue
    p.write_bytes(b"PRESERVE SYNTHETIC HISTORY")
    with pytest.raises(LayoutAuthorityError, match="EXISTING_FIXED_SLOT"):
        main.R4MainStore(store.root.parent).require_unclaimed_grant()
    assert p.read_bytes() == b"PRESERVE SYNTHETIC HISTORY"


def test_r4_old_owner_and_copied_historical_decision_rejected(tmp_path):
    old, _ = _fair_registry(tmp_path)
    new = main.R4MainStore(tmp_path / "new-registry")
    shutil.copytree(old.root, new.root)
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE"):
        new.require_unclaimed_grant()
    assert not (new.root / "task_ledger.json").exists()


@pytest.mark.parametrize("mode", ["REPLAY", "RESUME", "MAIN-2"])
def test_r4_only_main_mode(tmp_path, mode):
    store, _ = setup(tmp_path)
    with pytest.raises(LayoutAuthorityError, match="ONLY_ONE_MAIN"):
        store.open(mode)
    assert not list(store.root.glob("pool_*_claim.json"))


def test_r4_single_consumption_six_handoffs_share_budget_and_no_batch_overrun(tmp_path):
    store, binding = setup(tmp_path)
    store.require_unclaimed_grant()
    store.validate_existing_binding(owner_bytes(), binding)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    assert isinstance(lease, main.R4MainLease)
    with pytest.raises(LayoutAuthorityError, match="ACTIVE_CLAIM"):
        store.open("MAIN")
    for i in range(6):
        begin(lease, binding, i)
        ledger.charge("SYNTHETIC_BASELINE", 1)
        ledger.charge("SYNTHETIC_R4_CONTINUATION", 2)
        ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
    assert lease.totals()["observable_work"] == 18
    ledger.model_work = 599999  # SYNTHETIC_RESOURCE_STATE_TEST, not real RSS.
    before = deepcopy(ledger.resource_events)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.charge("SYNTHETIC_BATCH", 2)
    assert ledger.model_work == 599999 and ledger.resource_events == before
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="CONSUMED"):
        store.open("MAIN")
    assert len(list(store.root.glob("pool_*_claim.json"))) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("solver_wall", 49.91),
        ("model_work", 600001),
        ("peak_rss_bytes", 536870913),
        ("checked_solutions", 21),
    ],
)
def test_r4_cumulative_limit_rejection_uses_original_guards(tmp_path, field, value):
    store, _ = setup(tmp_path)
    ledger = store.open("MAIN")
    setattr(ledger, field, value)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.guard()


@pytest.mark.parametrize(
    "kind",
    [
        "FINAL_MODEL_GUIDANCE_APPLIED",
        "BOUNDED_IMPROVEMENT_STARTED",
        "VALIDATED_QUALITY_HINT_UPDATED",
        "FEASIBILITY_FIRST_QUALITY_FACTS",
    ],
)
def test_r4_receipts_match_real_nested_hint_and_top_level_quality_events(tmp_path, kind):
    store, binding = setup(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = binding["compositions"][0]["composition_hash"]
    expected = (
        main.FIRST_STAGE_POLICY_HASH if kind == "FINAL_MODEL_GUIDANCE_APPLIED" else main.POLICY_HASH
    )

    def event(h):
        return dict(
            kind=kind,
            **(
                {"policy_hash": h}
                if kind == "FEASIBILITY_FIRST_QUALITY_FACTS"
                else {"guidance": {"policy_hash": h}}
            ),
        )

    with pytest.raises(LayoutAuthorityError, match="GUIDANCE_RECEIPT"):
        lease.record_enumeration(sources, event("OLD"))
    lease.record_enumeration(sources, event(expected))


def test_r4_baseline_and_quality_receipts_stay_on_same_durable_lease(tmp_path):
    from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
        StageBFirstStageBalancedQualityFairSearchSolver,
    )
    from tests.unit.test_v222_stage_b_balanced_quality import diagnostic_candidate

    store, binding = setup(tmp_path)
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
    port = StageBFirstStageBalancedQualityFairSearchSolver()
    port.start_handoff(ledger, 6)
    candidate = diagnostic_candidate()
    candidate["source_composition_hash"] = handoff.source_composition_hash
    original = deepcopy(candidate)
    port.observe_validated_candidate(context, handoff, candidate, "ENGINEERING_ACCEPTED")
    baseline = deepcopy(port.baseline)
    port.observe_validated_candidate(context, handoff, candidate, "ENGINEERING_ACCEPTED")
    assert port.native.ledger is ledger and port.baseline == baseline and candidate == original
    assert len(lease.record["enumeration_events"]) == 2
    assert all(e["policy_hash"] == main.POLICY_HASH for e in lease.record["enumeration_events"])


def test_r4_mocked_operator_exports_existing_evidence_with_zero_native_calls(tmp_path, monkeypatch):
    from tests.unit.test_v222_github_full_ci_admission import r4_responses

    entry, ci = r4_responses()
    _, common = _fair_registry(tmp_path)
    store = main.R4MainStore(tmp_path / "new-r4-registry")
    scope = tmp_path / "scope"
    scope.write_bytes(owner_bytes())
    monkeypatch.setattr(entry, "committed_source", lambda _: None)
    monkeypatch.setattr(
        entry, "github_admission", lambda _: {"head": common["head"], "pr": ci["pr"]}
    )
    monkeypatch.setattr(entry, "approved_r4_main_store", lambda: store)
    monkeypatch.setattr(entry, "runtime_dependencies", lambda: {"synthetic": "dependency bytes"})
    monkeypatch.setattr(
        entry, "server_inputs", lambda _: ({}, {}, SimpleNamespace(to_dict=lambda: {}))
    )
    monkeypatch.setattr(entry, "fair_binding", lambda *_: common)
    repo = Path(entry.__file__).resolve().parents[2]
    tracked = entry.subprocess.check_output(
        ["git", "ls-files", "backend/src", "backend/scripts", entry.OWNER_SCOPE_PATH],
        cwd=repo,
        text=True,
    ).splitlines()
    common["source_files"].update(
        {str(repo / n): hashlib.sha256((repo / n).read_bytes()).hexdigest() for n in tracked}
    )
    common["runtime_dependency_hash"] = main.canonical_hash(entry.runtime_dependencies())
    store.approve(owner_bytes(), main.main_binding(common))
    original = (store.root / "owner_decision.json").read_bytes()
    monkeypatch.setattr(store, "approve", lambda *_: pytest.fail("runner issued Grant"))
    monkeypatch.setattr(
        entry, "bind_layout_authority", lambda *_: SimpleNamespace(access_requirements=[])
    )

    def pool(*args, solver, execution_ledger, fair_search):
        assert (
            type(solver).__name__ == "StageBFirstStageBalancedQualityFairSearchSolver"
            and fair_search
        )
        bound = store._decision()
        lease = admit(execution_ledger, bound)
        for i in range(6):
            begin(lease, bound, i)
            execution_ledger.charge("SYNTHETIC_NO_NATIVE", 1)
            execution_ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
        return dict(status="SYNTHETIC_NO_SOLVE", canonical_result_hash="synthetic", attempts=[])

    monkeypatch.setattr(entry, "generate_multi_solution_pool", pool)
    out = tmp_path / "output"
    entry.run_main(out, scope)
    assert (store.root / "owner_decision.json").read_bytes() == original
    usage = json.loads((out / "resource-usage.json").read_text())
    assert usage["native_calls"] == usage["native_solver_seconds"] == 0
    assert usage["observable_work"] == 6 and usage["resource_caps_respected"]
    assert (out / "resource-ledger.json").read_bytes() == (
        store.root / "task_ledger.json"
    ).read_bytes()
    assert json.loads((out / "execution-summary.json").read_text())["task"] == main.TASK
    with pytest.raises(LayoutAuthorityError, match="EXISTING_FIXED_SLOT"):
        entry.run_main(tmp_path / "second", scope)


def test_r4_runner_no_policy_budget_pr_or_registry_cli_and_no_auto_issuance():
    entry = runner()
    source = inspect.getsource(entry.run_main)
    assert source.count('store.open("MAIN")') == 1 and "store.approve(" not in source
    assert source.index("github_admission(repo)") < source.index("store.require_unclaimed_grant()")
    assert source.index("store.require_unclaimed_grant()") < source.index("server_inputs(repo)")
    assert source.index("store.validate_existing_binding(") < source.index('store.open("MAIN")')
    cli = inspect.getsource(entry.main)
    assert cli.count("parser.add_argument(") == 2
    for name in ("--budget", "--pr", "--task", "--policy", "--grant", "--registry"):
        assert name not in cli
