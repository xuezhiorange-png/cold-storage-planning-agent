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

from cold_storage.bootstrap.stage_b_r6_main import approved_r6_main_store
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_r6_main_execution as main
from cold_storage.modules.layout.infrastructure.stage_b_r5_main_execution import (
    TASK as OLD_TASK,
)
from tests.unit.test_v222_multi_solution_execution import _fair_registry
from tests.unit.test_v222_stage_b_pool_execution import admit, begin

SCOPE = "docs/tasks/V2_2_2-stage-b-r6-owner-scope.txt"


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda *_: pytest.fail("Native forbidden"))


def owner_bytes():
    return (Path(__file__).resolve().parents[3] / SCOPE).read_bytes()


def setup(tmp_path):
    _, common = _fair_registry(tmp_path)
    common["runtime_dependency_hash"] = "SYNTHETIC_NOT_REAL_RUNTIME"
    binding = main.main_binding(common)
    store = main.R6MainStore(tmp_path / "r6-synthetic-registry")
    store.approve(owner_bytes(), binding)  # Temporary Fixture issuance, never real registry.
    return store, binding


def runner():
    with pytest.MonkeyPatch.context() as p:
        p.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
        return importlib.import_module("run_stage_b_r6_main")


def test_r6_fixed_scope_hash_bootstrap_and_unused_identity(tmp_path):
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
                "SHAPE_POLICY_HASH",
                "FRONTAGE_POLICY_HASH",
                "AREA_OBJECTIVE_POLICY_HASH",
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
        == "sha256:5584fd5bb8a833905bc0f441bcdc1da8d9876f619d75b7d9fd948c843a2fd95d"
    )
    assert (
        main.SHAPE_POLICY_HASH
        == "sha256:31d228d6995aa7d2d71fd5a5fe740868aecda89b2526ff88081efb41f4fb80df"
    )
    assert b"PREPARATION_AUTHORIZES_GRANT_OR_CLAIM_CREATION=false\n" in raw
    assert b"EXECUTION_REQUIRES_SEPARATE_OWNER_EXACT_HEAD_CONFIRMATION=true\n" in raw
    assert not inspect.signature(approved_r6_main_store).parameters
    assert Path(__file__).name in RESOURCE_TEST_FILES
    store = main.R6MainStore(tmp_path / "no-grant")
    assert store.root.name == hashlib.sha256(main.TASK.encode()).hexdigest()
    with pytest.raises(LayoutAuthorityError, match="PREISSUED_OWNER_GRANT_REQUIRED"):
        store.require_unclaimed_grant()
    with pytest.raises(LayoutAuthorityError, match="PREISSUED_OWNER_GRANT_REQUIRED"):
        store.open("MAIN")
    assert not store.root.exists()


@pytest.mark.parametrize(
    "old,new", [(b"49.9", b"50.0"), (b"600000", b"600001"), (b"false", b"true")]
)
def test_r6_tampered_instruction_refused_before_ci(tmp_path, monkeypatch, old, new):
    entry = runner()
    p = tmp_path / "scope"
    p.write_bytes(owner_bytes().replace(old, new))
    monkeypatch.setattr(entry, "github_admission", lambda *_: pytest.fail("tamper reached CI"))
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE_MISMATCH"):
        entry.run_main(tmp_path / "output", p)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("digest", [None, "APPROVED", "x" * 64, "0" * 63])
def test_r6_unpinned_owner_refused(monkeypatch, digest):
    monkeypatch.setattr(main, "OWNER_SHA256", digest)
    with pytest.raises(LayoutAuthorityError, match="OWNER_EXECUTION_NOT_PINNED"):
        main.owner_execution_digest()


@pytest.mark.parametrize(
    "field",
    [
        "POLICY_HASH",
        "SHAPE_POLICY_HASH",
        "FRONTAGE_POLICY_HASH",
        "AREA_OBJECTIVE_POLICY_HASH",
        "FEEDBACK_POLICY_HASH",
    ],
)
def test_r6_owner_scope_cannot_silently_follow_a_future_policy(monkeypatch, tmp_path, field):
    monkeypatch.setattr(main, field, "OLD_OR_FUTURE_POLICY")
    with pytest.raises(LayoutAuthorityError, match="SCOPE_POLICY_SOURCE_CHANGED"):
        main.R6MainStore(tmp_path / "no-grant")
    assert not (tmp_path / "no-grant").exists()


def test_r6_pending_formal_ci_blocks_before_registry_or_inputs(tmp_path, monkeypatch):
    entry = runner()
    p = tmp_path / "scope"
    p.write_bytes(owner_bytes())
    monkeypatch.setattr(entry, "committed_source", lambda *_: None)

    def blocked(_):
        raise LayoutAuthorityError("EXACT_HEAD_FULL_CI_REQUIRED")

    monkeypatch.setattr(entry, "github_admission", blocked)
    monkeypatch.setattr(entry, "approved_r6_main_store", lambda: pytest.fail("registry before CI"))
    with pytest.raises(LayoutAuthorityError, match="FULL_CI_REQUIRED"):
        entry.run_main(tmp_path / "output", p)
    assert not (tmp_path / "output").exists()


def test_r6_correct_hash_without_grant_cannot_generate_inputs_or_claim(tmp_path, monkeypatch):
    entry = runner()
    p = tmp_path / "scope"
    p.write_bytes(owner_bytes())
    store = main.R6MainStore(tmp_path / "empty-registry")
    monkeypatch.setattr(entry, "committed_source", lambda *_: None)
    monkeypatch.setattr(entry, "github_admission", lambda _: {"head": "SYNTHETIC"})
    monkeypatch.setattr(entry, "approved_r6_main_store", lambda: store)
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
        "area_comparison_policy",
        "r6_frontage_policy_hash",
        "r6_solver_class",
        "server_input_identity",
        "area_objective_policy_hash",
        "single_main_contract",
        "single_main_contract_hash",
        "formal_ci_identity",
        "runtime_dependency_hash",
    ],
)
def test_r6_changed_binding_or_budget_refused(tmp_path, field):
    store, binding = setup(tmp_path)
    binding[field] = "" if field == "runtime_dependency_hash" else "OLD_OR_TAMPERED"
    with pytest.raises(LayoutAuthorityError, match="POLICY_OR_SOURCE"):
        store.validate_existing_binding(owner_bytes(), binding)
    assert not (store.root / "task_ledger.json").exists()


@pytest.mark.parametrize("field", ["pr_number", "base_ref", "base_sha", "head_ref"])
def test_r6_ci_binding_cannot_be_replaced_with_pr307_or_another_base(tmp_path, field):
    store, binding = setup(tmp_path)
    binding["formal_ci_identity"][field] = 307 if field == "pr_number" else "OLD"
    with pytest.raises(LayoutAuthorityError, match="POLICY_OR_SOURCE"):
        store.validate_existing_binding(owner_bytes(), binding)


@pytest.mark.parametrize("field", ["head", "zone_plan_hash", "p1_hash", "site_hash"])
def test_r6_fresh_server_scope_cannot_rebind_preissued_sources(tmp_path, field):
    store, binding = setup(tmp_path)
    binding[field] = "FORGED"
    with pytest.raises(LayoutAuthorityError, match="GRANT_BINDING_MISMATCH"):
        store.validate_existing_binding(owner_bytes(), binding)
    assert not (store.root / "task_ledger.json").exists()


def test_r6_original_dependency_and_source_verifier_still_runs(tmp_path):
    store, binding = setup(tmp_path)
    Path(binding["dependency_file"]).write_bytes(b"SYNTHETIC TAMPER")
    with pytest.raises(LayoutAuthorityError, match="HEAD_OR_DEPENDENCY_CHANGED"):
        main.R6MainStore(store.root.parent).require_unclaimed_grant()
    assert not (store.root / "task_ledger.json").exists()


@pytest.mark.parametrize(
    "residue", ["pool_1_claim.json", "task_ledger.json", "journal.jsonl", "active.lock"]
)
def test_r6_existing_or_consumed_slot_never_resets(tmp_path, residue):
    store, _ = setup(tmp_path)
    p = store.root / residue
    p.write_bytes(b"PRESERVE SYNTHETIC HISTORY")
    with pytest.raises(LayoutAuthorityError, match="EXISTING_FIXED_SLOT"):
        main.R6MainStore(store.root.parent).require_unclaimed_grant()
    assert p.read_bytes() == b"PRESERVE SYNTHETIC HISTORY"


def test_r6_old_owner_and_copied_historical_decision_rejected(tmp_path):
    old, _ = _fair_registry(tmp_path)
    new = main.R6MainStore(tmp_path / "new-registry")
    shutil.copytree(old.root, new.root)
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE"):
        new.require_unclaimed_grant()
    assert not (new.root / "task_ledger.json").exists()


@pytest.mark.parametrize(
    "scope",
    [
        "V2_2_2-stage-b-r5-owner-scope.txt",
        "V2_2_2-stage-b-r4-owner-scope.txt",
        "V2_2_2-stage-b-balanced-feedback-owner-scope.txt",
    ],
)
def test_r6_historical_owner_bytes_cannot_issue_new_task(tmp_path, scope):
    _, common = _fair_registry(tmp_path)
    common["runtime_dependency_hash"] = "SYNTHETIC"
    store = main.R6MainStore(tmp_path / "new")
    path = Path(__file__).resolve().parents[3] / "docs/tasks" / scope
    with pytest.raises(LayoutAuthorityError, match="OWNER"):
        store.approve(path.read_bytes(), main.main_binding(common))
    assert not store.root.exists()


@pytest.mark.parametrize("mode", ["REPLAY", "RESUME", "MAIN-2"])
def test_r6_only_main_mode(tmp_path, mode):
    store, _ = setup(tmp_path)
    with pytest.raises(LayoutAuthorityError, match="ONLY_ONE_MAIN"):
        store.open(mode)
    assert not list(store.root.glob("pool_*_claim.json"))


def test_r6_single_consumption_six_handoffs_share_budget_and_no_batch_overrun(tmp_path):
    store, binding = setup(tmp_path)
    store.require_unclaimed_grant()
    store.validate_existing_binding(owner_bytes(), binding)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    assert isinstance(lease, main.R6MainLease)
    with pytest.raises(LayoutAuthorityError, match="EXISTING_FIXED_SLOT"):
        store.open("MAIN")
    for i in range(6):
        begin(lease, binding, i)
        ledger.charge("SYNTHETIC_BASELINE", 1)
        ledger.charge("SYNTHETIC_R6_CONTINUATION", 2)
        ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
    assert lease.totals()["observable_work"] == 18
    ledger.model_work = 599999  # SYNTHETIC_RESOURCE_STATE_TEST, not real RSS.
    before = deepcopy(ledger.resource_events)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.charge("SYNTHETIC_BATCH", 2)
    assert ledger.model_work == 599999 and ledger.resource_events == before
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="EXISTING_FIXED_SLOT"):
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
def test_r6_cumulative_limit_rejection_uses_original_guards(tmp_path, field, value):
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
def test_r6_receipts_match_real_nested_hint_and_top_level_quality_events(tmp_path, kind):
    store, binding = setup(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = binding["compositions"][0]["composition_hash"]
    expected = (
        main.SHAPE_POLICY_HASH if kind == "FINAL_MODEL_GUIDANCE_APPLIED" else main.POLICY_HASH
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


def test_r6_baseline_and_quality_receipts_stay_on_same_durable_lease(tmp_path):
    from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
        StageBFrontageJointSearchFairSolver,
    )
    from tests.unit.test_v222_stage_b_area_efficiency import requirements
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
    context.binding.dimension_authorities = {
        r: {"dimension_mode": "FLEXIBLE_RECTANGLE"}
        for r in ("office", "changing_room", "coating_room")
    }
    requirements(context, "1")
    port = StageBFrontageJointSearchFairSolver()
    port.start_handoff(ledger, 6)
    candidate = diagnostic_candidate()
    candidate["source_composition_hash"] = handoff.source_composition_hash
    candidate.update(
        source_p1_handoff_hash=binding["p1_hash"],
        source_zone_plan_hash=binding["zone_plan_hash"],
        source_site_geometry_hash=binding["site_hash"],
    )
    original = deepcopy(candidate)
    port.observe_validated_candidate(context, handoff, candidate, "ENGINEERING_ACCEPTED")
    baseline = deepcopy(port.baseline)
    port.observe_validated_candidate(context, handoff, candidate, "ENGINEERING_ACCEPTED")
    assert port.native.ledger is ledger and port.baseline == baseline and candidate == original
    assert len(lease.record["enumeration_events"]) == 2
    assert all(e["policy_hash"] == main.POLICY_HASH for e in lease.record["enumeration_events"])


def test_r6_mocked_operator_exports_existing_evidence_with_zero_native_calls(tmp_path, monkeypatch):
    entry, ci = r6_responses()
    _, common = _fair_registry(tmp_path)
    store = main.R6MainStore(tmp_path / "new-r6-registry")
    scope = tmp_path / "scope"
    scope.write_bytes(owner_bytes())
    monkeypatch.setattr(entry, "committed_source", lambda _: None)
    monkeypatch.setattr(
        entry, "github_admission", lambda _: {"head": common["head"], "pr": ci["pr"]}
    )
    monkeypatch.setattr(entry, "approved_r6_main_store", lambda: store)
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
        assert type(solver).__name__ == "StageBFrontageJointSearchFairSolver" and fair_search
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


def test_r6_runner_no_policy_budget_pr_or_registry_cli_and_no_auto_issuance():
    entry = runner()
    source = inspect.getsource(entry.run_main)
    assert source.count('store.open("MAIN")') == 1 and "store.approve(" not in source
    assert source.index("github_admission(repo)") < source.index("store.require_unclaimed_grant()")
    assert source.index("store.require_unclaimed_grant()") < source.index("server_binding(repo)")
    assert source.index("store.validate_existing_binding(") < source.index('store.open("MAIN")')
    cli = inspect.getsource(entry.main)
    assert cli.count("parser.add_argument(") == 2
    for name in ("--budget", "--pr", "--task", "--policy", "--grant", "--registry"):
        assert name not in cli


def r6_responses():
    from tests.unit.test_v222_github_full_ci_admission import r4_responses

    _, data = r4_responses()
    entry = runner()
    data["pr"]["number"] = 312
    data["pr"]["base"].update(ref=main.CI_IDENTITY["base_ref"], sha=main.CI_IDENTITY["base_sha"])
    data["pr"]["head"]["ref"] = main.CI_IDENTITY["head_ref"]
    run = data["runs"]["workflow_runs"][0]
    run["head_branch"] = main.CI_IDENTITY["head_ref"]
    run["pull_requests"] = [
        dict(number=312, head=deepcopy(data["pr"]["head"]), base=deepcopy(data["pr"]["base"]))
    ]
    return entry, data


def install_ci(monkeypatch, data, *, moved=False):
    from tests.unit.test_v222_github_full_ci_admission import HEAD

    shared = importlib.import_module("run_stage_b_guided_fair_pool")
    calls = []

    def read(args, **kwargs):
        calls.append(args)
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return HEAD
        if args[:2] == ["git", "diff"]:
            return ""
        assert args[:2] == ["gh", "api"]
        path = args[2]
        if path.endswith("pulls/312"):
            result = deepcopy(data["pr"])
            if moved and sum(c[0] == "gh" and c[2].endswith("pulls/312") for c in calls) > 1:
                result["base"]["sha"] = "d" * 40
        elif path.endswith("actions/workflows/ci.yml"):
            result = data["workflow"]
        elif "/workflows/20/runs?" in path:
            assert f"event=pull_request&head_sha={HEAD}" in path
            result = data["runs"]
        elif "/jobs?" in path:
            result = data["jobs"]
        elif path.endswith("check-runs/88"):
            result = data["check"]
        else:
            raise AssertionError(f"unexpected R6 API call {args}")
        return json.dumps(result)

    def ancestry(args, **kwargs):
        assert args[:4] == ["git", "merge-base", "--is-ancestor", main.REFERENCE_HEAD]
        return shared.subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(shared.subprocess, "check_output", read)
    monkeypatch.setattr(shared.subprocess, "run", ancestry)
    return calls


def test_r6_actual_pr312_base_partition_and_original_rss_admission(tmp_path, monkeypatch):
    from tests.unit.test_v222_github_full_ci_admission import HEAD

    entry, data = r6_responses()
    calls = install_ci(monkeypatch, data)
    result = entry.github_admission(tmp_path)
    assert result["pr"]["number"] == 312 and result["head"] == HEAD
    assert "backend-partition-coverage" in result["formal_ci_jobs"]
    assert all("pulls/310" not in str(c) and "pulls/307" not in str(c) for c in calls)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "fault",
    [
        "pr311",
        "base",
        "base_sha",
        "head",
        "fast",
        "dispatch",
        "push",
        "pending",
        "failed",
        "coverage",
        "sqlite",
        "postgresql",
        "rss1",
        "rss2",
        "rss_receipt",
        "gate",
        "app",
        "moved",
    ],
)
def test_r6_ci_fail_closed_without_formal_same_head_all_jobs_and_both_rss(
    tmp_path, monkeypatch, fault
):
    entry, data = r6_responses()
    run = data["runs"]["workflow_runs"][0]
    jobs = data["jobs"]["jobs"]
    if fault == "pr311":
        data["pr"]["number"] = 311
    elif fault == "base":
        data["pr"]["base"]["ref"] = "main"
    elif fault == "base_sha":
        data["pr"]["base"]["sha"] = "d" * 40
    elif fault == "head":
        run["head_sha"] = "d" * 40
    elif fault == "fast":
        run["path"] = ".github/workflows/ci-fast.yml"
    elif fault in ("dispatch", "push"):
        run["event"] = "workflow_dispatch" if fault == "dispatch" else "push"
    elif fault == "pending":
        run.update(status="in_progress", conclusion=None)
    elif fault == "failed":
        run["conclusion"] = "failure"
    elif fault in ("coverage", "sqlite", "postgresql", "gate"):
        name = {
            "coverage": "backend-partition-coverage",
            "sqlite": "backend-sqlite",
            "postgresql": "backend-postgresql",
            "gate": "ci-gate",
        }[fault]
        next(j for j in jobs if j["name"] == name)["conclusion"] = "skipped"
    elif fault.startswith("rss"):
        steps = next(j for j in jobs if j["name"] == "backend-sqlite")["steps"]
        steps[{"rss1": 0, "rss2": 1, "rss_receipt": 2}[fault]]["conclusion"] = "skipped"
    elif fault == "app":
        data["check"]["app"]["id"] = 999
    install_ci(monkeypatch, data, moved=fault == "moved")
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        entry.github_admission(tmp_path)
    assert not list(tmp_path.iterdir())


def test_r6_twelve_metric_event_cannot_silently_use_nine_comparator(tmp_path):
    store, binding = setup(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = binding["compositions"][0]["composition_hash"]
    with pytest.raises(LayoutAuthorityError, match="GUIDANCE_RECEIPT"):
        lease.record_enumeration(
            sources,
            dict(
                kind="FEASIBILITY_FIRST_QUALITY_FACTS",
                policy_hash=main.POLICY_HASH,
                candidate={},
                comparison_policy="OLD_NINE",
            ),
        )


def test_r6_quality_export_separates_old_nine_and_twelve_preserves_unknown_topology(monkeypatch):
    from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
        compare_area_efficient_quality,
    )
    from tests.unit.test_v222_stage_b_area_efficiency import area_snapshot

    entry = runner()
    before = area_snapshot("2")
    after = area_snapshot("3", office_aspect="3", footprint_perimeter_m="90")
    before["candidate_hash"], after["candidate_hash"] = "base", "new"
    candidates = [
        dict(canonical_result_hash="base", source_composition_hash="h"),
        dict(canonical_result_hash="new", source_composition_hash="h"),
    ]
    facts = {"base": before, "new": after}
    monkeypatch.setattr(
        importlib.import_module(entry.quality_evidence.__module__),
        "area_efficiency_snapshot",
        lambda c, *_: deepcopy(facts[c["canonical_result_hash"]]),
    )
    comparison = compare_area_efficient_quality(before, after)
    events = [dict(kind="FEASIBILITY_FIRST_QUALITY_FACTS", candidate=after, **comparison)]
    original = deepcopy((candidates, events))
    report = entry.quality_evidence(candidates, object(), events)
    assert report["comparisons"][0]["original_nine"]["status"] == "GEOMETRIC_PARETO_IMPROVEMENT"
    assert report["comparisons"][0]["twelve"]["status"] == "QUALITY_TRADEOFF"
    assert (candidates, events) == original
    assert entry.canonical_hash(report) == entry.canonical_hash(
        entry.quality_evidence(candidates, object(), events)
    )
    events[0]["status"] = "GEOMETRIC_PARETO_IMPROVEMENT"
    with pytest.raises(LayoutAuthorityError, match="COMPARISON_RECEIPT_MISMATCH"):
        entry.quality_evidence(candidates, object(), events)


def test_r6_unpaired_or_other_structure_never_assumed_pareto(monkeypatch):
    from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
        compare_area_efficient_quality,
    )
    from tests.unit.test_v222_stage_b_area_efficiency import area_snapshot

    entry = runner()
    b, a = area_snapshot(), area_snapshot(office_aspect="3")
    b["candidate_hash"], a["candidate_hash"] = "base", "new"
    a["composition_hash"] = "other"
    facts = {"base": b, "new": a}
    monkeypatch.setattr(
        importlib.import_module(entry.quality_evidence.__module__),
        "area_efficiency_snapshot",
        lambda c, *_: deepcopy(facts[c["canonical_result_hash"]]),
    )
    candidates = [dict(canonical_result_hash=k, source_composition_hash="h") for k in facts]
    event = dict(
        kind="FEASIBILITY_FIRST_QUALITY_FACTS", candidate=a, **compare_area_efficient_quality(b, a)
    )
    assert (
        entry.quality_evidence(candidates, None, [event])["comparisons"][0]["twelve"]["status"]
        == "NOT_COMPARABLE_STRUCTURE"
    )
    assert entry.quality_evidence(candidates[1:], None, [event])["comparisons"] == [
        dict(status="NOT_EVALUATED", original_event=event)
    ]
    assert entry.quality_evidence([], None, [])["all_valid_proposal_facts"] == []


def test_r6_export_adds_reports_without_changing_unknown_certificates_or_native(
    tmp_path, monkeypatch
):
    entry = runner()
    topology = dict(
        kind="TOPOLOGY_REJECTED_WITNESS_CUT",
        certificate={
            "status": "SINGULAR_POINT_CONTACT",
            "hole_count": None,
        },
    )
    events = [topology, dict(kind="OTHER_REJECTION", certificate={"hole_count": 4})]
    original = deepcopy(events)

    def original_export(output, *args, **kwargs):
        entry.dump(output / "candidate-index.json", [])
        entry.dump(output / "execution-summary.json", {"main_status": "SYNTHETIC_NO_SOLVE"})
        (output / "results.md").write_text("Original report\n")

    monkeypatch.setattr(entry, "export_base_evidence", original_export)
    lease = SimpleNamespace(
        record={
            "enumeration_events": events,
            "counters": dict(
                resource_events={},
                model_work=0,
                native_host_work=0,
                solver_wall=0,
                solver_monotonic_wall=0,
                attempts=[],
                checked_solutions=0,
            ),
        }
    )
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for out in (first, second):
        entry.export_r6_evidence(out, None, lease, None, set(), None)
        assert json.loads((out / "topology-rejections.json").read_text()) == [topology]
        assert (
            json.loads((out / "execution-summary.json").read_text())["comparison_policy"]
            == main.COMPARISON_POLICY
        )
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }
    assert events == original


def test_r6_report_facts_use_original_physical_geometry_and_bound_p1(monkeypatch):
    from tests.unit.test_v222_stage_b_area_efficiency import setup as model_setup
    from tests.unit.test_v222_stage_b_balanced_quality import diagnostic_candidate

    context, _, _ = model_setup(area="1")
    candidate = diagnostic_candidate()
    candidate.update(
        source_p1_handoff_hash=context.binding.p1_handoff_hash,
        source_zone_plan_hash=context.binding.canonical_zone_plan_hash,
        source_site_geometry_hash=context.binding.site_geometry_hash,
        source_composition_hash="synthetic-handoff",
    )
    candidate["canonical_result_hash"] = main.canonical_hash(
        {k: v for k, v in candidate.items() if k != "canonical_result_hash"}
    )
    original = deepcopy(candidate)
    actual = runner().quality_evidence([candidate], context.binding, [])
    room = actual["all_valid_proposal_facts"][0]["area_efficiency"]["rooms"]["office"]
    assert room["required_area_m2"] == "1" and room["actual_area_m2"] == "8"
    assert room["area_overallocation_ratio"] == "7"
    assert candidate == original


def test_r6_actual_r5_grant_and_consumed_history_cannot_authorize_r6(tmp_path):
    from tests.unit.test_v222_stage_b_r5_main_execution import setup as old_setup

    old, _ = old_setup(tmp_path)
    new = main.R6MainStore(tmp_path / "isolated-r6")
    assert old.root.name != new.root.name and old.owner_digest != new.owner_digest
    shutil.copytree(old.root, new.root)
    before = {p.name: p.read_bytes() for p in new.root.iterdir()}
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE"):
        new.require_unclaimed_grant()
    assert before == {p.name: p.read_bytes() for p in new.root.iterdir()}
    assert not list(new.root.glob("pool_*_claim.json"))


@pytest.mark.parametrize(
    "kind", ["FINAL_MODEL_SEARCH_APPLIED", "VALIDATED_SEARCH_FRONTIER_UPDATED"]
)
def test_r6_new_frontage_and_frontier_receipts_are_on_original_durable_lease(tmp_path, kind):
    store, binding = setup(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = binding["compositions"][0]["composition_hash"]
    event = (
        dict(
            kind=kind, search=dict(policy_hash=main.FRONTAGE_POLICY_HASH, hard_domain_changed=False)
        )
        if kind == "FINAL_MODEL_SEARCH_APPLIED"
        else dict(
            kind=kind,
            policy_hash=main.POLICY_HASH,
            previous_proxy=5772,
            search_proxy=5469,
            candidate_hash="SYNTHETIC_ACCEPTED_TRADEOFF",
            formal_quality_improvement=False,
            hard_domain_changed=False,
        )
    )
    original = deepcopy(event)
    lease.record_enumeration(sources, event)
    assert event == original and lease.record["enumeration_events"][-1]["kind"] == kind
    archived = json.loads((store.root / "task_ledger.json").read_text())["pools"][0]
    assert archived["enumeration_events"][-1]["sources"] == sources
    assert ledger.execution_authorization is lease


@pytest.mark.parametrize(
    "field,value",
    [
        ("policy_hash", "OLD_R5"),
        ("previous_proxy", None),
        ("search_proxy", 5772),
        ("search_proxy", 5800),
        ("search_proxy", True),
        ("candidate_hash", ""),
        ("formal_quality_improvement", True),
        ("hard_domain_changed", True),
    ],
)
def test_r6_invalid_frontier_receipts_do_not_consume_work_or_record_progress(
    tmp_path, field, value
):
    store, binding = setup(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = binding["compositions"][0]["composition_hash"]
    event = dict(
        kind="VALIDATED_SEARCH_FRONTIER_UPDATED",
        policy_hash=main.POLICY_HASH,
        previous_proxy=5772,
        search_proxy=5469,
        candidate_hash="SYNTHETIC_ACCEPTED",
        formal_quality_improvement=False,
        hard_domain_changed=False,
    )
    event[field] = value
    before = ledger.model_work
    with pytest.raises(LayoutAuthorityError, match="FRONTIER_RECEIPT"):
        lease.record_enumeration(sources, event)
    assert not lease.record.get("enumeration_events") and ledger.model_work == before


def test_r6_work_export_uses_actual_raw_counters_and_preserves_unattributed_values():
    entry = runner()
    labels = dict(
        MODEL_ROLE_VARIABLES=5,
        R6_CREATED_DOMAIN_FACT=7,
        R6_FRONTAGE_STRATEGY_WRITE=3,
        R6_PHYSICAL_HINT_REFERENCE=2,
        R6_CURRENT_VALID_PHYSICAL_HINT=4,
        R6_VALIDATED_PROXY_FACTS=10,
        STAGE_B_CANDIDATE_VALIDATION=1,
        EXACT_UNION_PRIMITIVE=6,
        NEW_UNKNOWN_LABEL=8,
    )
    lease = SimpleNamespace(
        record={
            "counters": dict(
                resource_events=labels,
                model_work=sum(labels.values()),
                native_host_work=17,
                solver_wall=0.1,
                solver_monotonic_wall=0.2,
                attempts=[{}],
                checked_solutions=1,
            )
        }
    )
    before = deepcopy(lease.record)
    report = entry.work_evidence(lease)
    assert report["groups"]["model_preparation"]["work"] == 15
    assert report["groups"]["physical_hint"]["work"] == 6
    assert report["groups"]["search_feedback"]["work"] == 10
    assert report["groups"]["validation_and_export"]["work"] == 1
    assert report["groups"]["topology_and_cuts"]["work"] == 6
    assert report["groups"]["other_model_work"]["work"] == 8
    assert report["observable_work"] == sum(labels.values()) + 17
    assert report["labels_reconcile_to_model_work"] and report["native_solver_seconds"] == 0.2
    assert lease.record == before
    lease.record["counters"]["model_work"] += 2  # SYNTHETIC missing labels are not hidden.
    report = entry.work_evidence(lease)
    assert report["unlabelled_model_work"] == 2 and not report["labels_reconcile_to_model_work"]


@pytest.mark.parametrize(
    "fault", ["dirty", "inputs", "head", "runtime", "source", "base", "history", "output_exists"]
)
def test_r6_preclaim_chain_rejects_changed_evidence_without_creating_a_claim(
    tmp_path, monkeypatch, fault
):
    entry, ci = r6_responses()
    _, common = _fair_registry(tmp_path)
    deps = {"SYNTHETIC": "runtime"}
    common["runtime_dependency_hash"] = main.canonical_hash(deps)
    binding = main.main_binding(common)
    store = main.R6MainStore(tmp_path / "preclaim-only")
    store.approve(owner_bytes(), binding)
    scope, output = tmp_path / "scope", tmp_path / "output"
    scope.write_bytes(owner_bytes())
    monkeypatch.setattr(entry, "committed_source", lambda _: None)
    monkeypatch.setattr(
        entry, "github_admission", lambda _: dict(head=common["head"], pr=deepcopy(ci["pr"]))
    )
    monkeypatch.setattr(entry, "approved_r6_main_store", lambda: store)
    monkeypatch.setattr(
        entry,
        "server_binding",
        lambda _: ({}, {}, SimpleNamespace(to_dict=lambda: {}), deps, binding),
    )
    monkeypatch.setattr(entry, "runtime_dependencies", lambda: deps)
    monkeypatch.setattr(store, "open", lambda *_: pytest.fail("Claim before complete admission"))
    monkeypatch.setattr(
        entry,
        "generate_multi_solution_pool",
        lambda *_a, **_k: pytest.fail("Native/pool forbidden"),
    )
    if fault == "dirty":

        def dirty(_):
            raise LayoutAuthorityError("SYNTHETIC_DIRTY_SOURCE")

        monkeypatch.setattr(entry, "committed_source", dirty)
    elif fault == "inputs":

        def invalid(_):
            raise LayoutAuthorityError("SYNTHETIC_P1_SITE_INPUT_INVALID")

        monkeypatch.setattr(entry, "server_binding", invalid)
    elif fault == "head":
        monkeypatch.setattr(
            entry, "github_admission", lambda _: dict(head="DIFFERENT_HEAD", pr=ci["pr"])
        )
    elif fault == "runtime":
        monkeypatch.setattr(entry, "runtime_dependencies", lambda: {"CHANGED": "dependency"})
    elif fault == "source":
        Path(next(iter(common["source_files"]))).write_bytes(b"SYNTHETIC_SOURCE_CHANGED")
    elif fault == "base":
        responses = [deepcopy(ci["pr"]), deepcopy(ci["pr"])]
        responses[1]["base"]["sha"] = "0" * 40
        monkeypatch.setattr(
            entry, "github_admission", lambda _: dict(head=common["head"], pr=responses.pop(0))
        )
    elif fault == "history":
        (store.root / "journal.jsonl").write_text("SYNTHETIC_UNKNOWN_HISTORY")
    else:
        output.mkdir()
    with pytest.raises((LayoutAuthorityError, FileExistsError)):
        entry.run_main(output, scope)
    assert (
        not list(store.root.glob("pool_*_claim.json")) and not (store.root / "active.lock").exists()
    )
    assert not (store.root / "task_ledger.json").exists()
    if fault != "output_exists":
        assert not output.exists()


def test_r6_uses_production_presolve_and_partial_fixed_search_without_native(monkeypatch):
    from cold_storage.modules.layout.infrastructure import global_cp_sat_solver as shared
    from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
        _FrontageNative,
    )
    from tests.unit.test_v222_stage_b_area_efficiency import setup as model_setup

    context, model, _ = model_setup()
    engine = _FrontageNative(context.ledger, 1)
    parameters = cp_model.CpSolver().parameters
    probe = SimpleNamespace(
        parameters=parameters,
        wall_time=0,
        num_branches=0,
        num_conflicts=0,
        response_proto=SimpleNamespace(deterministic_time=0),
        status_name=lambda _: "UNKNOWN",
        response_stats=lambda: "SYNTHETIC_NO_NATIVE",
    )
    monkeypatch.setattr(shared.cp_model, "CpSolver", lambda: probe)
    monkeypatch.setattr(engine, "_solve_with_feedback", lambda *_: (cp_model.UNKNOWN, None))
    engine._run(context, model.m, 0.01, "ALL_ROOMS_ALL_ACCESS")
    assert parameters.cp_model_presolve is True
    assert parameters.search_branching == cp_model.PARTIAL_FIXED_SEARCH
    assert parameters.stop_after_first_solution is True and parameters.num_search_workers == 1
    engine.improving = True
    engine._run(context, model.m, 0.01, "ALL_ROOMS_ALL_ACCESS")
    assert parameters.cp_model_presolve is True and not parameters.stop_after_first_solution
    assert parameters.search_branching == cp_model.PARTIAL_FIXED_SEARCH
    assert all(a["solver_status"] == "UNKNOWN" for a in context.ledger.attempts)


def test_r6_native_calls_and_checked_assignments_are_single_pool_limits(tmp_path):
    store, binding = setup(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    ledger.attempts.extend(dict(SYNTHETIC_RESOURCE_STATE_TEST=i) for i in range(100))
    with pytest.raises(LayoutAuthorityError, match="NATIVE_CALL_LIMIT"):
        ledger.remaining_solver_seconds()
    assert len(ledger.attempts) == 100
    ledger.checked_solutions = 20  # Synthetic counters, no actual assignments or Native calls.
    ledger.guard()
    ledger.checked_solutions = 21
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.guard()
    assert main.CONTRACT["requirement_host_work"] == 20000


def test_r6_counter_rollback_and_unknown_native_history_cannot_be_restarted(tmp_path):
    store, binding = setup(tmp_path)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    begin(lease, binding, 0)
    ledger.charge("SYNTHETIC_BASELINE", 3)
    ledger.checkpoint("SYNTHETIC_COUNTED")
    ledger.model_work -= 1  # SYNTHETIC_RESOURCE_STATE_TEST: prove rollback is rejected.
    with pytest.raises(LayoutAuthorityError, match="ROLLBACK"):
        ledger.checkpoint("SYNTHETIC_FORGED_ROLLBACK")
    original = (store.root / "pool_1_claim.json").read_bytes()
    with pytest.raises(LayoutAuthorityError, match="EXISTING_FIXED_SLOT"):
        main.R6MainStore(store.root.parent).open("MAIN")
    assert (store.root / "pool_1_claim.json").read_bytes() == original


def test_r6_wrapper_exports_search_progress_without_promoting_tradeoff(tmp_path, monkeypatch):
    from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
        compare_area_efficient_quality,
    )
    from tests.unit.test_v222_stage_b_area_efficiency import area_snapshot

    entry = runner()
    before = area_snapshot("2")
    after = area_snapshot("3", office_aspect="3", footprint_perimeter_m="90")
    before["candidate_hash"], after["candidate_hash"] = "base", "new"
    for snapshot in (before, after):
        snapshot["functional_diversity"].update(
            countable=True, meaningful_construction_hash="same-v2"
        )
    comparison = compare_area_efficient_quality(before, after)
    frontier = dict(
        kind="VALIDATED_SEARCH_FRONTIER_UPDATED",
        policy_hash=main.POLICY_HASH,
        previous_proxy=5772,
        search_proxy=5469,
        candidate_hash="new",
        formal_quality_improvement=False,
        hard_domain_changed=False,
    )
    events = [dict(kind="FEASIBILITY_FIRST_QUALITY_FACTS", candidate=after, **comparison), frontier]
    labels = {"R6_VALIDATED_PROXY_FACTS": 10}
    lease = SimpleNamespace(
        record=dict(
            enumeration_events=deepcopy(events),
            counters=dict(
                resource_events=labels,
                model_work=10,
                native_host_work=0,
                solver_wall=0,
                solver_monotonic_wall=0,
                attempts=[],
                checked_solutions=0,
            ),
        )
    )
    facts = {"base": before, "new": after}
    monkeypatch.setattr(
        importlib.import_module(entry.quality_evidence.__module__),
        "area_efficiency_snapshot",
        lambda c, *_: facts[c["canonical_result_hash"]],
    )

    def base_export(out, *_args, **kwargs):
        assert kwargs["task"] == main.TASK
        rows = []
        for i, h in enumerate(("base", "new")):
            folder = out / f"synthetic-{i}"
            folder.mkdir()
            entry.dump(
                folder / "candidate.json",
                dict(canonical_result_hash=h, source_composition_hash="h"),
            )
            rows.append(dict(svg=f"synthetic-{i}/layout.svg", geometry_hash=f"geometry-{i}"))
        entry.dump(out / "candidate-index.json", rows)
        entry.dump(out / "execution-summary.json", {"main_status": "SYNTHETIC_NO_SOLVE"})
        (out / "results.md").write_text("Original exporter preserved\n")

    monkeypatch.setattr(entry, "export_base_evidence", base_export)
    output = tmp_path / "report-only"
    output.mkdir()
    original = deepcopy(lease.record)
    entry.export_r6_evidence(output, None, lease, None, set(), None)
    summary = json.loads((output / "execution-summary.json").read_text())
    assert summary["distinct_valid_geometry_count"] == 2
    assert summary["distinct_valid_v2_organization_count"] == 1
    assert (
        summary["independent_comparison_counts"]["original_nine"]["GEOMETRIC_PARETO_IMPROVEMENT"]
        == 1
    )
    assert summary["independent_comparison_counts"]["twelve"]["QUALITY_TRADEOFF"] == 1
    assert not summary["search_progress_is_formal_quality_improvement"]
    assert json.loads((output / "r6-search-feedback.json").read_text()) == events
    assert lease.record == original
