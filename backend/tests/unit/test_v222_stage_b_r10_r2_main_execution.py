"""R10 R2 preparation: temporary synthetic grants; both Native APIs forbidden."""

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

from cold_storage.bootstrap.stage_b_r10_r2_main import approved_r10_r2_main_store
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure import stage_b_r10_r2_main_execution as main
from cold_storage.modules.layout.infrastructure.stage_b_entrance_coupled_spatial import (
    StageBEntranceCoupledSpatialFairSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_feasibility_main_execution import (
    FeasibilityFirstMainLease,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import PoolLease
from tests.unit.test_v222_multi_solution_execution import _fair_registry
from tests.unit.test_v222_stage_b_pool_execution import admit, begin

SCOPE = "docs/tasks/V2_2_2-stage-b-r10-r2-owner-scope.txt"
REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    monkeypatch.setattr(
        cp_model.CpSolver, "solve", lambda *_a, **_k: pytest.fail("Native forbidden")
    )
    monkeypatch.setattr(
        cp_model.CpSolver, "Solve", lambda *_a, **_k: pytest.fail("Native forbidden")
    )


def owner_bytes():
    return (REPO / SCOPE).read_bytes()


def runner():
    with pytest.MonkeyPatch.context() as p:
        p.syspath_prepend(str(REPO / "backend/scripts"))
        return importlib.import_module("run_stage_b_r10_r2_main")


def setup(tmp_path):
    _, common = _fair_registry(tmp_path)
    common["runtime_dependency_hash"] = "SYNTHETIC_NOT_REAL_RUNTIME"
    binding = main.main_binding(common)
    store = main.R10R2MainStore(tmp_path / "r10-r2-synthetic-registry")
    store.approve(owner_bytes(), binding)
    return store, binding


def saved(lease, binding):
    sources = {k: binding[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    sources["composition_hash"] = binding["compositions"][0]["composition_hash"]
    lease.record_enumeration(
        sources,
        dict(
            kind="FEASIBILITY_FIRST_QUALITY_FACTS",
            policy_hash=main.POLICY_HASH,
            status="BASE_VALID_CANDIDATE_PRESERVED",
            baseline=dict(
                candidate_hash="SYNTHETIC_ACCEPTED_BASE",
                composition_hash=sources["composition_hash"],
            ),
        ),
    )
    return sources


def guidance():
    return dict(
        policy_hash=main.POLICY_HASH,
        frontage_search=dict(policy_hash=main.FRONTAGE_POLICY_HASH, hard_domain_changed=False),
        frontage_activation="AFTER_INDEPENDENT_ENGINEERING_ACCEPTANCE",
        same_model_reused=True,
        extra_native_calls=0,
        hard_domain_changed=False,
        entrance_coupled_search=dict(
            policy_hash=main.POLICY_HASH,
            hard_domain_changed=False,
            objective_changed=False,
            hint_changed=False,
            local_model_copies=0,
            extra_native_calls=0,
            new_variables=0,
            new_constraints=0,
            preferred_entrance_face="EAST",
            validated_entrance_portal_mm=[75000, 25000],
            validated_tangent_centres_twice_mm=dict(
                changing_room=48000, sorting_packaging_room=36000
            ),
        ),
    )


def test_scope_actual_pr_hash_caps_and_readonly_bootstrap(tmp_path, monkeypatch):
    from tests.stage_a_resource_process import RESOURCE_TEST_FILES

    assert Path(__file__).name in RESOURCE_TEST_FILES
    assert hashlib.sha256(owner_bytes()).hexdigest() == main.owner_execution_digest()
    fields = dict(line.split("=", 1) for line in owner_bytes().decode().splitlines())
    assert fields["EXPERIMENT_ID"] == main.TASK
    for field, key in [
        ("PR_NUMBER", "pr_number"),
        ("PR_HEAD_REF", "head_ref"),
        ("PR_BASE_REF", "base_ref"),
        ("PR_BASE_SHA", "base_sha"),
    ]:
        assert fields[field] == str(main.CI_IDENTITY[key])
    assert (
        main.CI_IDENTITY["pr_number"] == 320
        and main.CI_IDENTITY["base_sha"] == "0cf97f6d4a4ba48947bc9bfdef25e97968eb9832"
    )
    assert (
        fields["POLICY_HASH"]
        == main.POLICY_HASH
        == StageBEntranceCoupledSpatialFairSolver.quality_policy_hash
    )
    assert (
        tuple(
            fields[f]
            for f in [
                "POLICY_HASH",
                "R1_REFERENCE_POLICY_HASH",
                "FIRST_FEASIBLE_POLICY_HASH",
                "PARENT_SEARCH_POLICY_HASH",
                "SHAPE_POLICY_HASH",
                "FRONTAGE_POLICY_HASH",
                "AREA_OBJECTIVE_POLICY_HASH",
                "FEEDBACK_POLICY_HASH",
            ]
        )
        == main.BOUND_STRATEGIES
    )
    for field, key in [
        ("NATIVE_SECONDS_MAX", "native_seconds"),
        ("ELAPSED_SECONDS_MAX", "elapsed_seconds"),
        ("WORK_MAX", "observable_work"),
        ("NATIVE_CALLS_MAX", "native_calls"),
        ("CHECKED_ASSIGNMENTS_MAX", "checked_assignments"),
        ("PER_REQUIREMENT_HOST_WORK_MAX", "requirement_host_work"),
    ]:
        assert float(fields[field]) == main.CONTRACT[key]
    assert fields["MAX_LOCAL_COPIES_PER_HANDOFF"] == "0"
    assert b"PREPARATION_AUTHORIZES_GRANT_OR_CLAIM_CREATION=false\n" in owner_bytes()
    assert not inspect.signature(approved_r10_r2_main_store).parameters
    monkeypatch.setattr(Path, "home", classmethod(lambda _: tmp_path))
    store = approved_r10_r2_main_store()
    assert (
        not store.root.exists()
        and store.root.name == hashlib.sha256(main.TASK.encode()).hexdigest()
    )
    with pytest.raises(LayoutAuthorityError, match="PREISSUED_OWNER_GRANT_REQUIRED"):
        store.open("MAIN")
    assert not list(tmp_path.iterdir())
    assert main.R10R2MainLease.guard is FeasibilityFirstMainLease.guard
    assert main.R10R2MainLease.precharge_work is PoolLease.precharge_work


@pytest.mark.parametrize(
    "field",
    [
        "POLICY_HASH",
        "R1_REFERENCE_POLICY_HASH",
        "FIRST_FEASIBLE_POLICY_HASH",
        "PARENT_SEARCH_POLICY_HASH",
        "SHAPE_POLICY_HASH",
        "FRONTAGE_POLICY_HASH",
        "AREA_OBJECTIVE_POLICY_HASH",
        "FEEDBACK_POLICY_HASH",
    ],
)
def test_changed_policy_source_cannot_silently_follow_scope(monkeypatch, field):
    monkeypatch.setattr(main, field, "DIFFERENT")
    with pytest.raises(LayoutAuthorityError, match="SCOPE_POLICY_SOURCE_CHANGED"):
        main.owner_execution_digest()


@pytest.mark.parametrize("digest", [None, "", "x" * 64, "0" * 63])
def test_no_placeholder_owner_hash(monkeypatch, digest):
    monkeypatch.setattr(main, "OWNER_SHA256", digest)
    with pytest.raises(LayoutAuthorityError, match="NOT_PINNED"):
        main.owner_execution_digest()


@pytest.mark.parametrize("mode", ["REPLAY", "RESUME", "retry", "MAIN2"])
def test_only_one_main_mode(tmp_path, mode):
    s, _ = setup(tmp_path)
    with pytest.raises(LayoutAuthorityError, match="ONLY_ONE_MAIN"):
        s.open(mode)


@pytest.mark.parametrize("scope", ["r5", "r6", "r7", "r9"])
def test_old_owner_and_task_cannot_issue_new_grant(tmp_path, scope):
    _, common = _fair_registry(tmp_path)
    common["runtime_dependency_hash"] = "SYNTHETIC"
    s = main.R10R2MainStore(tmp_path / "new")
    with pytest.raises(LayoutAuthorityError):
        s.approve(
            (REPO / f"docs/tasks/V2_2_2-stage-b-{scope}-owner-scope.txt").read_bytes(),
            main.main_binding(common),
        )
    assert not s.root.exists()


@pytest.mark.parametrize(
    "field",
    [
        "balanced_quality_task",
        "balanced_quality_policy_hash",
        "r10_r2_solver_class",
        "r10_r2_first_feasible_policy_hash",
        "r10_r2_r1_reference_policy_hash",
        "single_main_contract",
        "single_main_contract_hash",
        "formal_ci_identity",
        "runtime_dependency_hash",
        "local_model_copy_enabled",
        "local_refinement_max_copies",
    ],
)
def test_binding_or_budget_tamper_rejected_before_claim(tmp_path, field):
    s, b = setup(tmp_path)
    changed = deepcopy(b)
    changed[field] = "TAMPERED"
    with pytest.raises(LayoutAuthorityError):
        s.validate_existing_binding(owner_bytes(), changed)
    assert not list(s.root.glob("pool_*_claim.json"))


@pytest.mark.parametrize(
    "residue",
    ["pool_1_claim.json", "task_ledger.json", "active.lock", "journal.jsonl", "unknown-file"],
)
def test_unknown_or_consumed_slot_never_reset(tmp_path, residue):
    s, _ = setup(tmp_path)
    (s.root / residue).write_text("SYNTHETIC_HISTORICAL_STATE")
    before = {p.name: p.read_bytes() for p in s.root.iterdir()}
    with pytest.raises(LayoutAuthorityError, match="FIXED_SLOT"):
        s.open("MAIN")
    assert before == {p.name: p.read_bytes() for p in s.root.iterdir()}


def test_copied_old_r9_synthetic_grant_is_rejected(tmp_path):
    from tests.unit.test_v222_stage_b_r9_main_execution import setup as old_setup

    (tmp_path / "old-fixture").mkdir()
    old, _ = old_setup(tmp_path / "old-fixture")
    new = main.R10R2MainStore(tmp_path / "new-fixture")
    new.root.mkdir(parents=True)
    for p in old.root.iterdir():
        shutil.copyfile(p, new.root / p.name)
    with pytest.raises(LayoutAuthorityError):
        new.open("MAIN")
    assert not list(new.root.glob("pool_*_claim.json"))


def test_one_claim_six_handoffs_and_whole_work_precharge(tmp_path):
    s, b = setup(tmp_path)
    ledger = s.open("MAIN")
    lease = admit(ledger, b)
    assert isinstance(lease, main.R10R2MainLease)
    for i in range(6):
        begin(lease, b, i)
        ledger.charge("SYNTHETIC_BASELINE_AND_CONTINUATION", 2)
        ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
    assert lease.totals()["observable_work"] == 12
    ledger.model_work = 599999
    before = deepcopy(ledger.resource_events)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.charge("SYNTHETIC_BATCH", 2)
    assert ledger.model_work == 599999 and before == ledger.resource_events
    lease.finish_pool()
    with pytest.raises(LayoutAuthorityError, match="FIXED_SLOT"):
        s.open("MAIN")
    assert len(list(s.root.glob("pool_*_claim.json"))) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("solver_wall", 49.91),
        ("solver_monotonic_wall", 49.91),
        ("model_work", 600001),
        ("peak_rss_bytes", 536870913),
        ("checked_solutions", 21),
    ],
)
def test_original_cumulative_guards_unchanged(tmp_path, field, value):
    s, b = setup(tmp_path)
    ledger = s.open("MAIN")
    lease = admit(ledger, b)
    begin(lease, b, 0)
    setattr(ledger, field, value)
    with pytest.raises(LayoutAuthorityError, match="LIMIT"):
        ledger.guard()


@pytest.mark.parametrize(
    "fault",
    [
        "no_baseline",
        "policy",
        "frontage",
        "domain",
        "hint",
        "copy",
        "bool_count",
        "portal",
        "centres",
        "phase",
    ],
)
def test_second_stage_requires_original_baseline_and_exact_r10_receipt(tmp_path, fault):
    s, b = setup(tmp_path)
    ledger = s.open("MAIN")
    lease = admit(ledger, b)
    begin(lease, b, 0)
    source = {k: b[k] for k in ("zone_plan_hash", "p1_hash", "site_hash")}
    source["composition_hash"] = b["compositions"][0]["composition_hash"]
    if fault != "no_baseline":
        source = saved(lease, b)
    g = guidance()
    j = g["entrance_coupled_search"]
    if fault == "policy":
        g["policy_hash"] = "OLD"
    elif fault == "frontage":
        g["frontage_search"]["policy_hash"] = "OLD"
    elif fault == "domain":
        j["hard_domain_changed"] = True
    elif fault == "hint":
        j["hint_changed"] = True
    elif fault == "copy":
        j["local_model_copies"] = 1
    elif fault == "bool_count":
        j["extra_native_calls"] = False
    elif fault == "portal":
        j["validated_entrance_portal_mm"] = [1]
    elif fault == "centres":
        j["validated_tangent_centres_twice_mm"] = {}
    elif fault == "phase":
        g["frontage_activation"] = "FIRST_STAGE"
    original = deepcopy(lease.record)
    work = ledger.model_work
    with pytest.raises(LayoutAuthorityError):
        lease.record_enumeration(source, dict(kind="BOUNDED_IMPROVEMENT_STARTED", guidance=g))
    assert lease.record == original and ledger.model_work == work


def test_current_hint_and_organization_receipt_are_recorded_on_same_lease(tmp_path):
    s, b = setup(tmp_path)
    ledger = s.open("MAIN")
    lease = admit(ledger, b)
    begin(lease, b, 0)
    source = saved(lease, b)
    lease.record_enumeration(source, dict(kind="BOUNDED_IMPROVEMENT_STARTED", guidance=guidance()))
    assert lease.record["enumeration_events"][-1]["guidance"]["entrance_coupled_search"][
        "validated_entrance_portal_mm"
    ] == [75000, 25000]
    with pytest.raises(LayoutAuthorityError, match="LOCAL_ROUTE_REFINEMENT_FORBIDDEN"):
        lease.record_enumeration(
            source, dict(kind="SAME_PROXY_ROUTE_REFINEMENT", status="LOCAL_PREPARATION_ADMITTED")
        )
    assert lease.record["enumeration_events"][-1]["kind"] == "BOUNDED_IMPROVEMENT_STARTED"


def responses():
    from tests.unit.test_v222_stage_b_r9_main_execution import r9_responses

    _, d = r9_responses()
    d["pr"]["number"] = 320
    d["pr"]["base"].update(ref=main.CI_IDENTITY["base_ref"], sha=main.CI_IDENTITY["base_sha"])
    d["pr"]["head"]["ref"] = main.CI_IDENTITY["head_ref"]
    run = d["runs"]["workflow_runs"][0]
    run["head_branch"] = main.CI_IDENTITY["head_ref"]
    run["pull_requests"] = [
        dict(number=320, head=deepcopy(d["pr"]["head"]), base=deepcopy(d["pr"]["base"]))
    ]
    template = next(j for j in d["jobs"]["jobs"] if j["name"] == "frontend")
    for i, name in enumerate(["backend-architecture", "backend-lint", "backend-mypy"]):
        j = deepcopy(template)
        j.update(id=2000 + i, name=name)
        d["jobs"]["jobs"].append(j)
    d["jobs"]["total_count"] = len(d["jobs"]["jobs"])
    return runner(), d


def install_ci(monkeypatch, d, moved=False):
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
        if path.endswith("pulls/320"):
            answer = deepcopy(d["pr"])
            if moved and sum(x[0] == "gh" and x[2].endswith("pulls/320") for x in calls) > 1:
                answer["base"]["sha"] = "d" * 40
        elif path.endswith("actions/workflows/ci.yml"):
            answer = d["workflow"]
        elif "/workflows/20/runs?" in path:
            assert f"event=pull_request&head_sha={HEAD}" in path
            answer = d["runs"]
        elif "/jobs?" in path:
            answer = d["jobs"]
        elif path.endswith("check-runs/88"):
            answer = d["check"]
        else:
            raise AssertionError(args)
        return json.dumps(answer)

    monkeypatch.setattr(shared.subprocess, "check_output", read)
    monkeypatch.setattr(
        shared.subprocess, "run", lambda args, **kw: shared.subprocess.CompletedProcess(args, 0)
    )
    return calls


def test_exact_pr320_base319_full_jobs_partition_and_two_rss(tmp_path, monkeypatch):
    e, d = responses()
    calls = install_ci(monkeypatch, d)
    a = e.github_admission(tmp_path)
    assert a["pr"]["number"] == 320 and "backend-partition-coverage" in a["formal_ci_jobs"]
    assert set(main.CI_IDENTITY["required_jobs"]) <= set(a["formal_ci_jobs"])
    assert not any(str(x).find("pulls/317") >= 0 for x in calls)


@pytest.mark.parametrize(
    "fault",
    [
        "old_pr",
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
        "postgres",
        "architecture",
        "lint",
        "mypy",
        "rss1",
        "rss2",
        "rss_receipt",
        "gate",
        "app",
        "moved",
    ],
)
def test_full_ci_fails_closed(tmp_path, monkeypatch, fault):
    e, d = responses()
    run = d["runs"]["workflow_runs"][0]
    if fault == "old_pr":
        d["pr"]["number"] = 319
    elif fault == "base":
        d["pr"]["base"]["ref"] = "main"
    elif fault == "base_sha":
        d["pr"]["base"]["sha"] = "0" * 40
    elif fault == "head":
        d["pr"]["head"]["sha"] = "0" * 40
    elif fault == "fast":
        run["path"] = ".github/workflows/ci-fast.yml"
    elif fault in ["dispatch", "push"]:
        run["event"] = "workflow_dispatch" if fault == "dispatch" else "push"
    elif fault == "pending":
        run["status"] = "in_progress"
        run["conclusion"] = None
    elif fault == "failed":
        run["conclusion"] = "failure"
    elif fault in ["rss1", "rss2", "rss_receipt"]:
        job = next(j for j in d["jobs"]["jobs"] if j["name"] == "backend-sqlite")
        step = job["steps"][{"rss1": 0, "rss2": 1, "rss_receipt": 2}[fault]]
        step["conclusion"] = "skipped"
    elif fault == "app":
        d["check"]["app"]["id"] = 1
    elif fault not in ["moved"]:
        name = {
            "coverage": "backend-partition-coverage",
            "sqlite": "backend-sqlite",
            "postgres": "backend-postgresql",
            "architecture": "backend-architecture",
            "lint": "backend-lint",
            "mypy": "backend-mypy",
            "gate": "ci-gate",
        }[fault]
        next(j for j in d["jobs"]["jobs"] if j["name"] == name)["conclusion"] = "failure"
    install_ci(monkeypatch, d, moved=fault == "moved")
    with pytest.raises(LayoutAuthorityError):
        e.github_admission(tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "fault",
    [
        "dirty",
        "ci",
        "missing_grant",
        "inputs",
        "head",
        "runtime",
        "source",
        "base",
        "history",
        "output_exists",
    ],
)
def test_preclaim_chain_never_opens_on_bad_evidence(tmp_path, monkeypatch, fault):
    e, ci = responses()
    _, common = _fair_registry(tmp_path)
    deps = {"SYNTHETIC": "runtime"}
    common["runtime_dependency_hash"] = canonical_hash(deps)
    b = main.main_binding(common)
    s = main.R10R2MainStore(tmp_path / "preclaim")
    if fault != "missing_grant":
        s.approve(owner_bytes(), b)
    owner, out = tmp_path / "owner", tmp_path / "output"
    owner.write_bytes(owner_bytes())
    monkeypatch.setattr(e, "committed_source", lambda _: None)
    monkeypatch.setattr(
        e, "github_admission", lambda _: dict(head=common["head"], pr=deepcopy(ci["pr"]))
    )
    monkeypatch.setattr(e, "approved_r10_r2_main_store", lambda: s)
    monkeypatch.setattr(
        e, "server_binding", lambda _: ({}, {}, SimpleNamespace(to_dict=lambda: {}), deps, b)
    )
    monkeypatch.setattr(e, "runtime_dependencies", lambda: deps)
    monkeypatch.setattr(s, "open", lambda *_: pytest.fail("Claim before full admission"))
    monkeypatch.setattr(
        e, "generate_multi_solution_pool", lambda *_a, **_k: pytest.fail("Pool forbidden")
    )

    def fail(*_):
        raise LayoutAuthorityError("SYNTHETIC_ADMISSION_REJECTED")

    if fault == "dirty":
        monkeypatch.setattr(e, "committed_source", fail)
    elif fault == "ci":
        monkeypatch.setattr(e, "github_admission", fail)
    elif fault == "inputs":
        monkeypatch.setattr(e, "server_binding", fail)
    elif fault == "head":
        monkeypatch.setattr(e, "github_admission", lambda _: dict(head="DIFFERENT", pr=ci["pr"]))
    elif fault == "runtime":
        monkeypatch.setattr(e, "runtime_dependencies", lambda: {"CHANGED": "runtime"})
    elif fault == "source":
        Path(next(iter(common["source_files"]))).write_bytes(b"SYNTHETIC_CHANGED_SOURCE")
    elif fault == "base":
        pr = [deepcopy(ci["pr"]), deepcopy(ci["pr"])]
        pr[1]["base"]["sha"] = "0" * 40
        monkeypatch.setattr(
            e, "github_admission", lambda _: dict(head=common["head"], pr=pr.pop(0))
        )
    elif fault == "history":
        (s.root / "journal.jsonl").write_text("SYNTHETIC_UNKNOWN_HISTORY")
    elif fault == "output_exists":
        out.mkdir()
    with pytest.raises((LayoutAuthorityError, FileExistsError)):
        e.run_main(out, owner)
    assert not list(s.root.glob("pool_*_claim.json")) and not (s.root / "task_ledger.json").exists()


def test_owner_tamper_refused_before_ci(tmp_path, monkeypatch):
    e = runner()
    p = tmp_path / "tampered"
    p.write_bytes(owner_bytes().replace(b"WORK_MAX=600000", b"WORK_MAX=600001"))
    monkeypatch.setattr(e, "github_admission", lambda *_: pytest.fail("CI before Scope rejection"))
    with pytest.raises(LayoutAuthorityError, match="OWNER_SOURCE"):
        e.run_main(tmp_path / "out", p)


def test_runner_has_fixed_cli_and_never_approves():
    e = runner()
    s = inspect.getsource(e)
    assert ".approve(" not in s and "StageBResourceBoundRouteRefinementFairSolver" not in s
    assert (
        s.index("github_admission(repo)")
        < s.index("store.require_unclaimed_grant()")
        < s.index("server_binding(repo)")
        < s.index('store.open("MAIN")')
    )
    assert s.count('store.open("MAIN")') == 1
    assert e.StageBEntranceCoupledSpatialFairSolver is StageBEntranceCoupledSpatialFairSolver


def test_six_frozen20t_models_use_real_binding_without_native_or_store():
    from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
        _ReferenceAccessModel,
        apply_reference_area_guidance,
    )
    from tests.unit.test_v222_stage_b_frontage_joint_search import complete_context

    e = runner()
    _, _, _, deps, b = e.server_binding(REPO)
    c, hs = complete_context()
    assert (
        c.binding.canonical_zone_plan_hash == b["zone_plan_hash"]
        and c.binding.p1_handoff_hash == b["p1_hash"]
        and c.binding.site_geometry_hash == b["site_hash"]
    )
    assert {h.source_composition_hash for h in hs} == {
        r["composition_hash"] for r in b["compositions"]
    }
    assert (
        len(hs) == 6
        and deps
        and b["r10_r2_solver_class"] == "StageBEntranceCoupledSpatialFairSolver"
    )
    for h in hs:
        c, _ = complete_context()
        m = _ReferenceAccessModel(c, h, True)
        apply_reference_area_guidance(m, c)
        assert not m.m.validate() and len(m.rooms) == 12
        assert {r["req"]["identity"] for r in m.routes} | {c.pack_req["identity"]} == {
            r["identity"] for r in c.binding.access_requirements if r["flow_kind"] != "TRUCK"
        }
        assert not c.ledger.attempts and c.ledger.execution_authorization is None
        assert not m.m.proto.has_solution_hint()


@pytest.mark.parametrize("profile_overrun", [False, True])
def test_mocked_operator_exports_six_rows_and_original_caps(tmp_path, monkeypatch, profile_overrun):
    e, ci = responses()
    _, common = _fair_registry(tmp_path)
    s = main.R10R2MainStore(tmp_path / "synthetic-operator")
    scope = tmp_path / "scope"
    scope.write_bytes(owner_bytes())
    monkeypatch.setattr(e, "committed_source", lambda _: None)
    monkeypatch.setattr(e, "github_admission", lambda _: dict(head=common["head"], pr=ci["pr"]))
    monkeypatch.setattr(e, "approved_r10_r2_main_store", lambda: s)
    monkeypatch.setattr(e, "runtime_dependencies", lambda: {"SYNTHETIC": "runtime"})
    monkeypatch.setattr(e, "server_inputs", lambda _: ({}, {}, SimpleNamespace(to_dict=lambda: {})))
    monkeypatch.setattr(e, "fair_binding", lambda *_: common)
    tracked = e.subprocess.check_output(
        ["git", "ls-files", "backend/src", "backend/scripts", SCOPE], cwd=REPO, text=True
    ).splitlines()
    common["source_files"].update(
        {str(REPO / n): hashlib.sha256((REPO / n).read_bytes()).hexdigest() for n in tracked}
    )
    common["source_files"][str(REPO / SCOPE)] = hashlib.sha256(owner_bytes()).hexdigest()
    common["runtime_dependency_hash"] = canonical_hash(e.runtime_dependencies())
    s.approve(owner_bytes(), main.main_binding(common))
    before = (s.root / "owner_decision.json").read_bytes()
    monkeypatch.setattr(s, "approve", lambda *_: pytest.fail("Runner issued Grant"))
    monkeypatch.setattr(
        e, "bind_layout_authority", lambda *_: SimpleNamespace(access_requirements=[])
    )

    def pool(*_a, solver, execution_ledger, fair_search):
        assert type(solver) is StageBEntranceCoupledSpatialFairSolver and fair_search
        lease = admit(execution_ledger, s._decision())
        for i in range(6):
            begin(lease, common, i)
            execution_ledger.charge("SYNTHETIC_NO_NATIVE", 1)
            execution_ledger.checkpoint("STAGE_B_CANDIDATE_RETURNED_OR_INTERRUPTED")
        if profile_overrun:
            execution_ledger.native_requirements.append(
                dict(
                    identity="SYNTHETIC_PROFILE_STATE",
                    host_work=20001,
                    status="SYNTHETIC_COUNTER_ONLY",
                )
            )
        return dict(status="SYNTHETIC_NO_SOLVE", canonical_result_hash="synthetic", attempts=[])

    monkeypatch.setattr(e, "generate_multi_solution_pool", pool)
    out = tmp_path / "output"
    if profile_overrun:
        with pytest.raises(LayoutAuthorityError, match="RESOURCE_CAPS_EXCEEDED"):
            e.run_main(out, scope)
    else:
        e.run_main(out, scope)
    usage = json.loads((out / "resource-usage.json").read_text())
    report = json.loads((out / "r10-r2-organization-report.json").read_text())
    assert (
        usage["native_calls"] == usage["native_solver_seconds"] == 0
        and usage["observable_work"] == 6
    )
    assert usage["resource_caps_respected"] is (not profile_overrun)
    assert len(report["per_handoff"]) == 6 and report["local_model_copy_work"] == 0
    assert all(r["consumption"]["observable_work"] == 1 for r in report["per_handoff"])
    assert all(r["first_valid_baseline"] == "NOT_EVALUATED" for r in report["per_handoff"])
    assert (s.root / "owner_decision.json").read_bytes() == before
    assert (out / "resource-ledger.json").read_bytes() == (s.root / "task_ledger.json").read_bytes()
    assert json.loads((out / "execution-summary.json").read_text())["task"] == main.TASK
    with pytest.raises(LayoutAuthorityError, match="FIXED_SLOT"):
        e.run_main(tmp_path / "second", scope)


@pytest.mark.parametrize("mode", ["native_count", "native_active", "rollback"])
def test_shared_calls_and_history_cannot_be_refilled(tmp_path, mode):
    s, b = setup(tmp_path)
    ledger = s.open("MAIN")
    lease = admit(ledger, b)
    begin(lease, b, 0)
    if mode == "native_count":
        ledger.attempts.extend(dict(synthetic_counter_test=i) for i in range(100))
        ledger.checkpoint("SYNTHETIC_COUNTERS")
        with pytest.raises(LayoutAuthorityError, match="LIMIT"):
            ledger.remaining_solver_seconds()
    elif mode == "native_active":
        ledger.native_solver_active = True
        with pytest.raises(LayoutAuthorityError, match="HISTORY_UNVERIFIED"):
            ledger.remaining_solver_seconds()
    else:
        ledger.charge("SYNTHETIC_COUNTERS", 5)
        ledger.checkpoint("SYNTHETIC_COUNTERS")
        ledger.model_work -= 1
        with pytest.raises(LayoutAuthorityError):
            ledger.guard()


def test_engineering_output_has_real_room_route_and_independent_quality_sources(tmp_path):
    from cold_storage.modules.layout.infrastructure.stage_b_r10_r2_main_evidence import (
        organization_evidence,
    )
    from tests.r9_full_engineering_synthetic import sources
    from tests.r10_entrance_coupled_experiment import designed_translation

    c = designed_translation(0)
    *_, context, _, _ = sources()
    e = runner()
    # Original full synthetic engineering oracle, no Native candidate claimed.
    facts = e.quality_evidence([c], context.binding, [])
    decision = dict(
        zone_plan_hash=context.binding.canonical_zone_plan_hash,
        p1_hash=context.binding.p1_handoff_hash,
        site_hash=context.binding.site_geometry_hash,
        compositions=[
            dict(identity="synthetic-fixture", composition_hash=c["source_composition_hash"])
        ],
    )
    lease = SimpleNamespace(
        decision=decision,
        record=dict(enumeration_events=[], counters=dict(resource_events={}), cursor=0),
    )
    ids = {r["identity"] for r in context.binding.access_requirements if r["flow_kind"] != "TRUCK"}
    report = organization_evidence(
        tmp_path, None, lease, [c], facts, dict(per_handoff_baselines=[]), ids
    )
    row = report["valid_candidates"][0]
    assert row["room_dimensions_and_areas"]["changing_room"]["required_area_m2"] == "40"
    assert len(row["sorting_changing_positions"]) == 2 and row["metrics"]["personnel_route_m"]
    assert row["cp_sat_personnel_portal_and_route"]["from_ref"] == "main_entrance"
    assert row["independently_validated_application_personnel"]["status"] == "PASS"
    assert report["per_handoff"][0]["consumption"] == "NOT_EVALUATED"
    assert not report["historical_r9_p04_used_as_formal_frontier"] and not report["p2d_full_pass"]
    bad = deepcopy(c)
    bad["source_site_geometry_hash"] = "OTHER"
    with pytest.raises(LayoutAuthorityError, match="AUTHORITY_MISMATCH"):
        organization_evidence(
            tmp_path, None, lease, [bad], facts, dict(per_handoff_baselines=[]), ids
        )
    lease.record["counters"]["resource_events"]["ROUTE_LOCAL_MODEL_COPY"] = 1
    with pytest.raises(LayoutAuthorityError, match="LOCAL_COPY"):
        organization_evidence(
            tmp_path, None, lease, [c], facts, dict(per_handoff_baselines=[]), ids
        )


def test_first_stage_and_r10_search_implementation_are_inherited_without_copy():
    from cold_storage.modules.layout.infrastructure.stage_b_entrance_coupled_spatial import (
        POLICY_HASH,
    )
    from cold_storage.modules.layout.infrastructure.stage_b_first_feasible_recovery import (
        StageBFirstFeasibleRecoveryFairSolver,
    )

    cls = StageBEntranceCoupledSpatialFairSolver
    assert (
        cls.native_type.prepare_first_stage
        is StageBFirstFeasibleRecoveryFairSolver.native_type.prepare_first_stage
    )
    assert cls.native_type._run is StageBFirstFeasibleRecoveryFairSolver.native_type._run
    assert not hasattr(cls.native_type, "refine_routes")
    assert main.POLICY_HASH == POLICY_HASH and not main.main_binding({})["local_model_copy_enabled"]


def test_work_projection_keeps_exact_labels_and_unattributed_work():
    ledger = dict(
        resource_events={"R10_R2_COUPLED_SEARCH_METADATA": 218, "MODEL_ORIGINAL": 100},
        model_work=320,
        native_host_work=7,
        solver_wall=0,
        solver_monotonic_wall=0,
        attempts=[],
        checked_solutions=0,
    )
    e = runner()
    r = e.work_evidence(SimpleNamespace(record=dict(counters=ledger)))
    assert r["observable_work"] == 327 and r["unlabelled_model_work"] == 2
    assert r["groups"]["entrance_coupled_organization"]["work"] == 218
    assert sum(g["work"] for g in r["groups"].values()) == 318
    assert r["original_resource_events"] == ledger["resource_events"]


def test_unknown_termination_uses_original_attempt_not_infeasible(tmp_path):
    from cold_storage.modules.layout.infrastructure.stage_b_r10_r2_main_evidence import (
        organization_evidence,
    )

    lease = SimpleNamespace(
        decision=dict(compositions=[dict(identity="fixture-H1", composition_hash="fixture-c")]),
        record=dict(cursor=1, enumeration_events=[], counters=dict(resource_events={})),
    )
    result = dict(
        compositions=[dict(composition_identity="fixture-H1")],
        attempts=[
            dict(
                composition_identity="fixture-H1",
                solver_status="UNKNOWN",
                status="NATIVE_NO_COMPLETE_MODEL_CANDIDATE",
            )
        ],
    )
    r = organization_evidence(
        tmp_path,
        result,
        lease,
        [],
        dict(all_valid_proposal_facts=[], comparisons=[]),
        dict(per_handoff_baselines=[]),
        set(),
    )
    assert r["per_handoff"][0]["last_native_solver_status"] == "UNKNOWN"
    assert (
        r["per_handoff"][0]["termination_reason"]["status"] == "NATIVE_NO_COMPLETE_MODEL_CANDIDATE"
    )
    assert r["per_handoff"][0]["consumption"] == "NOT_EVALUATED" and not r["unknown_is_infeasible"]
