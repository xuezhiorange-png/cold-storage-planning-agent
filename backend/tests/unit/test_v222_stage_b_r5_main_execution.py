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

from cold_storage.bootstrap.stage_b_r5_main import approved_r5_main_store
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import stage_b_r5_main_execution as main
from cold_storage.modules.layout.infrastructure.stage_b_r4_main_execution import (
    TASK as OLD_TASK,
)
from tests.unit.test_v222_multi_solution_execution import _fair_registry
from tests.unit.test_v222_stage_b_pool_execution import admit, begin

SCOPE = "docs/tasks/V2_2_2-stage-b-r5-owner-scope.txt"


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda *_: pytest.fail("Native forbidden"))


def owner_bytes():
    return (Path(__file__).resolve().parents[3] / SCOPE).read_bytes()


def setup(tmp_path):
    _, common = _fair_registry(tmp_path)
    common["runtime_dependency_hash"] = "SYNTHETIC_NOT_REAL_RUNTIME"
    binding = main.main_binding(common)
    store = main.R5MainStore(tmp_path / "r5-synthetic-registry")
    store.approve(owner_bytes(), binding)  # Temporary Fixture issuance, never real registry.
    return store, binding


def runner():
    with pytest.MonkeyPatch.context() as p:
        p.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
        return importlib.import_module("run_stage_b_r5_main")


def test_r5_fixed_scope_hash_bootstrap_and_unused_identity(tmp_path):
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
        == "sha256:ddccb804958e52c169ad1d1c0c2c6ecc259271e350e23207dba0b1a5e71db0a4"
    )
    assert (
        main.SHAPE_POLICY_HASH
        == "sha256:1fc76233d500120f2b80f44feb6ba557fd1e3181be123b113519d93faa13ba6d"
    )
    assert b"PREPARATION_AUTHORIZES_GRANT_OR_CLAIM_CREATION=false\n" in raw
    assert b"EXECUTION_REQUIRES_SEPARATE_OWNER_EXACT_HEAD_CONFIRMATION=true\n" in raw
    assert not inspect.signature(approved_r5_main_store).parameters
    assert Path(__file__).name in RESOURCE_TEST_FILES
    store = main.R5MainStore(tmp_path / "no-grant")
    assert store.root.name == hashlib.sha256(main.TASK.encode()).hexdigest()
    with pytest.raises(LayoutAuthorityError, match="PREISSUED_OWNER_GRANT_REQUIRED"):
        store.require_unclaimed_grant()
    with pytest.raises(LayoutAuthorityError, match="OWNER_DECISION_REQUIRED"):
        store.open("MAIN")
    assert not store.root.exists()


@pytest.mark.parametrize(
    "old,new", [(b"49.9", b"50.0"), (b"600000", b"600001"), (b"false", b"true")]
)
def test_r5_tampered_instruction_refused_before_ci(tmp_path, monkeypatch, old, new):
    entry = runner()
    p = tmp_path / "scope"
    p.write_bytes(owner_bytes().replace(old, new))
    monkeypatch.setattr(entry, "github_admission", lambda *_: pytest.fail("tamper reached CI"))
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE_MISMATCH"):
        entry.run_main(tmp_path / "output", p)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("digest", [None, "APPROVED", "x" * 64, "0" * 63])
def test_r5_unpinned_owner_refused(monkeypatch, digest):
    monkeypatch.setattr(main, "OWNER_SHA256", digest)
    with pytest.raises(LayoutAuthorityError, match="OWNER_EXECUTION_NOT_PINNED"):
        main.owner_execution_digest()


@pytest.mark.parametrize("field", ["POLICY_HASH", "SHAPE_POLICY_HASH", "FEEDBACK_POLICY_HASH"])
def test_r5_owner_scope_cannot_silently_follow_a_future_policy(monkeypatch, tmp_path, field):
    monkeypatch.setattr(main, field, "OLD_OR_FUTURE_POLICY")
    with pytest.raises(LayoutAuthorityError, match="SCOPE_POLICY_SOURCE_CHANGED"):
        main.R5MainStore(tmp_path / "no-grant")
    assert not (tmp_path / "no-grant").exists()


def test_r5_pending_formal_ci_blocks_before_registry_or_inputs(tmp_path, monkeypatch):
    entry = runner()
    p = tmp_path / "scope"
    p.write_bytes(owner_bytes())
    monkeypatch.setattr(entry, "committed_source", lambda *_: None)

    def blocked(_):
        raise LayoutAuthorityError("EXACT_HEAD_FULL_CI_REQUIRED")

    monkeypatch.setattr(entry, "github_admission", blocked)
    monkeypatch.setattr(entry, "approved_r5_main_store", lambda: pytest.fail("registry before CI"))
    with pytest.raises(LayoutAuthorityError, match="FULL_CI_REQUIRED"):
        entry.run_main(tmp_path / "output", p)
    assert not (tmp_path / "output").exists()


def test_r5_correct_hash_without_grant_cannot_generate_inputs_or_claim(tmp_path, monkeypatch):
    entry = runner()
    p = tmp_path / "scope"
    p.write_bytes(owner_bytes())
    store = main.R5MainStore(tmp_path / "empty-registry")
    monkeypatch.setattr(entry, "committed_source", lambda *_: None)
    monkeypatch.setattr(entry, "github_admission", lambda _: {"head": "SYNTHETIC"})
    monkeypatch.setattr(entry, "approved_r5_main_store", lambda: store)
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
        "single_main_contract",
        "single_main_contract_hash",
        "formal_ci_identity",
        "runtime_dependency_hash",
    ],
)
def test_r5_changed_binding_or_budget_refused(tmp_path, field):
    store, binding = setup(tmp_path)
    binding[field] = "" if field == "runtime_dependency_hash" else "OLD_OR_TAMPERED"
    with pytest.raises(LayoutAuthorityError, match="POLICY_OR_SOURCE"):
        store.validate_existing_binding(owner_bytes(), binding)
    assert not (store.root / "task_ledger.json").exists()


@pytest.mark.parametrize("field", ["pr_number", "base_ref", "base_sha", "head_ref"])
def test_r5_ci_binding_cannot_be_replaced_with_pr307_or_another_base(tmp_path, field):
    store, binding = setup(tmp_path)
    binding["formal_ci_identity"][field] = 307 if field == "pr_number" else "OLD"
    with pytest.raises(LayoutAuthorityError, match="POLICY_OR_SOURCE"):
        store.validate_existing_binding(owner_bytes(), binding)


@pytest.mark.parametrize("field", ["head", "zone_plan_hash", "p1_hash", "site_hash"])
def test_r5_fresh_server_scope_cannot_rebind_preissued_sources(tmp_path, field):
    store, binding = setup(tmp_path)
    binding[field] = "FORGED"
    with pytest.raises(LayoutAuthorityError, match="GRANT_BINDING_MISMATCH"):
        store.validate_existing_binding(owner_bytes(), binding)
    assert not (store.root / "task_ledger.json").exists()


def test_r5_original_dependency_and_source_verifier_still_runs(tmp_path):
    store, binding = setup(tmp_path)
    Path(binding["dependency_file"]).write_bytes(b"SYNTHETIC TAMPER")
    with pytest.raises(LayoutAuthorityError, match="HEAD_OR_DEPENDENCY_CHANGED"):
        main.R5MainStore(store.root.parent).require_unclaimed_grant()
    assert not (store.root / "task_ledger.json").exists()


@pytest.mark.parametrize(
    "residue", ["pool_1_claim.json", "task_ledger.json", "journal.jsonl", "active.lock"]
)
def test_r5_existing_or_consumed_slot_never_resets(tmp_path, residue):
    store, _ = setup(tmp_path)
    p = store.root / residue
    p.write_bytes(b"PRESERVE SYNTHETIC HISTORY")
    with pytest.raises(LayoutAuthorityError, match="EXISTING_FIXED_SLOT"):
        main.R5MainStore(store.root.parent).require_unclaimed_grant()
    assert p.read_bytes() == b"PRESERVE SYNTHETIC HISTORY"


def test_r5_old_owner_and_copied_historical_decision_rejected(tmp_path):
    old, _ = _fair_registry(tmp_path)
    new = main.R5MainStore(tmp_path / "new-registry")
    shutil.copytree(old.root, new.root)
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE"):
        new.require_unclaimed_grant()
    assert not (new.root / "task_ledger.json").exists()


@pytest.mark.parametrize(
    "scope",
    [
        "V2_2_2-stage-b-r4-owner-scope.txt",
        "V2_2_2-stage-b-balanced-feedback-owner-scope.txt",
    ],
)
def test_r5_historical_owner_bytes_cannot_issue_new_task(tmp_path, scope):
    _, common = _fair_registry(tmp_path)
    common["runtime_dependency_hash"] = "SYNTHETIC"
    store = main.R5MainStore(tmp_path / "new")
    path = Path(__file__).resolve().parents[3] / "docs/tasks" / scope
    with pytest.raises(LayoutAuthorityError, match="OWNER"):
        store.approve(path.read_bytes(), main.main_binding(common))
    assert not store.root.exists()


@pytest.mark.parametrize("mode", ["REPLAY", "RESUME", "MAIN-2"])
def test_r5_only_main_mode(tmp_path, mode):
    store, _ = setup(tmp_path)
    with pytest.raises(LayoutAuthorityError, match="ONLY_ONE_MAIN"):
        store.open(mode)
    assert not list(store.root.glob("pool_*_claim.json"))


def test_r5_single_consumption_six_handoffs_share_budget_and_no_batch_overrun(tmp_path):
    store, binding = setup(tmp_path)
    store.require_unclaimed_grant()
    store.validate_existing_binding(owner_bytes(), binding)
    ledger = store.open("MAIN")
    lease = admit(ledger, binding)
    assert isinstance(lease, main.R5MainLease)
    with pytest.raises(LayoutAuthorityError, match="ACTIVE_CLAIM"):
        store.open("MAIN")
    for i in range(6):
        begin(lease, binding, i)
        ledger.charge("SYNTHETIC_BASELINE", 1)
        ledger.charge("SYNTHETIC_R5_CONTINUATION", 2)
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
def test_r5_cumulative_limit_rejection_uses_original_guards(tmp_path, field, value):
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
def test_r5_receipts_match_real_nested_hint_and_top_level_quality_events(tmp_path, kind):
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


def test_r5_baseline_and_quality_receipts_stay_on_same_durable_lease(tmp_path):
    from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
        StageBAreaEfficientQualityFairSearchSolver,
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
    port = StageBAreaEfficientQualityFairSearchSolver()
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


def test_r5_mocked_operator_exports_existing_evidence_with_zero_native_calls(tmp_path, monkeypatch):
    entry, ci = r5_responses()
    _, common = _fair_registry(tmp_path)
    store = main.R5MainStore(tmp_path / "new-r5-registry")
    scope = tmp_path / "scope"
    scope.write_bytes(owner_bytes())
    monkeypatch.setattr(entry, "committed_source", lambda _: None)
    monkeypatch.setattr(
        entry, "github_admission", lambda _: {"head": common["head"], "pr": ci["pr"]}
    )
    monkeypatch.setattr(entry, "approved_r5_main_store", lambda: store)
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
        assert type(solver).__name__ == "StageBAreaEfficientQualityFairSearchSolver" and fair_search
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


def test_r5_runner_no_policy_budget_pr_or_registry_cli_and_no_auto_issuance():
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


def r5_responses():
    from tests.unit.test_v222_github_full_ci_admission import r4_responses

    _, data = r4_responses()
    entry = runner()
    data["pr"]["number"] = 311
    data["pr"]["base"].update(ref=main.CI_IDENTITY["base_ref"], sha=main.CI_IDENTITY["base_sha"])
    data["pr"]["head"]["ref"] = main.CI_IDENTITY["head_ref"]
    run = data["runs"]["workflow_runs"][0]
    run["head_branch"] = main.CI_IDENTITY["head_ref"]
    run["pull_requests"] = [
        dict(number=311, head=deepcopy(data["pr"]["head"]), base=deepcopy(data["pr"]["base"]))
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
        if path.endswith("pulls/311"):
            result = deepcopy(data["pr"])
            if moved and sum(c[0] == "gh" and c[2].endswith("pulls/311") for c in calls) > 1:
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
            raise AssertionError(f"unexpected R5 API call {args}")
        return json.dumps(result)

    def ancestry(args, **kwargs):
        assert args[:4] == ["git", "merge-base", "--is-ancestor", main.REFERENCE_HEAD]
        return shared.subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(shared.subprocess, "check_output", read)
    monkeypatch.setattr(shared.subprocess, "run", ancestry)
    return calls


def test_r5_actual_pr311_base_partition_and_original_rss_admission(tmp_path, monkeypatch):
    from tests.unit.test_v222_github_full_ci_admission import HEAD

    entry, data = r5_responses()
    calls = install_ci(monkeypatch, data)
    result = entry.github_admission(tmp_path)
    assert result["pr"]["number"] == 311 and result["head"] == HEAD
    assert "backend-partition-coverage" in result["formal_ci_jobs"]
    assert all("pulls/310" not in str(c) and "pulls/307" not in str(c) for c in calls)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "fault",
    [
        "pr310",
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
def test_r5_ci_fail_closed_without_formal_same_head_all_jobs_and_both_rss(
    tmp_path, monkeypatch, fault
):
    entry, data = r5_responses()
    run = data["runs"]["workflow_runs"][0]
    jobs = data["jobs"]["jobs"]
    if fault == "pr310":
        data["pr"]["number"] = 310
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


def test_r5_twelve_metric_event_cannot_silently_use_nine_comparator(tmp_path):
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


def test_r5_quality_export_separates_old_nine_and_twelve_preserves_unknown_topology(monkeypatch):
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
        entry, "area_efficiency_snapshot", lambda c, *_: deepcopy(facts[c["canonical_result_hash"]])
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


def test_r5_unpaired_or_other_structure_never_assumed_pareto(monkeypatch):
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
        entry, "area_efficiency_snapshot", lambda c, *_: deepcopy(facts[c["canonical_result_hash"]])
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


def test_r5_export_adds_reports_without_changing_unknown_certificates_or_native(
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
    lease = SimpleNamespace(record={"enumeration_events": events})
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for out in (first, second):
        entry.export_r5_evidence(out, None, lease, None, set(), None)
        assert json.loads((out / "topology-rejections.json").read_text()) == [topology]
        assert (
            json.loads((out / "execution-summary.json").read_text())["comparison_policy"]
            == main.COMPARISON_POLICY
        )
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }
    assert events == original


def test_r5_report_facts_use_original_physical_geometry_and_bound_p1(monkeypatch):
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
