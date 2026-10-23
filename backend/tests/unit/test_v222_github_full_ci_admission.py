"""Synthetic GitHub responses only: no Owner grant, native solve or network."""

from __future__ import annotations

import copy
import importlib
import json
import subprocess
from pathlib import Path

import pytest

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError

with pytest.MonkeyPatch.context() as importer:
    importer.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    runner = importlib.import_module("run_stage_b_guided_fair_pool")

HEAD = "a" * 40
BASE = "b" * 40


def responses():
    repository = {"id": 123, "full_name": runner.GITHUB_REPOSITORY}
    pr = {
        "number": 307,
        "state": "open",
        "draft": True,
        "head": {"sha": HEAD, "ref": "codex/test", "repo": repository},
        "base": {"sha": BASE, "ref": "main", "repo": repository},
    }
    run = {
        "id": 10,
        "event": "pull_request",
        "head_sha": HEAD,
        "workflow_id": 20,
        "path": ".github/workflows/ci.yml",
        "head_branch": "codex/test",
        "head_repository": repository,
        "pull_requests": [{"number": 307, "head": pr["head"], "base": pr["base"]}],
        "status": "completed",
        "conclusion": "success",
        "check_suite_id": 30,
    }
    jobs = [
        {
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "steps": [],
            "check_run_url": f"https://api.github.com/repos/{runner.GITHUB_REPOSITORY}/check-runs/88",
        }
        for name in sorted(runner.FULL_CI_JOBS)
    ]
    next(j for j in jobs if j["name"] == "backend-sqlite")["steps"] = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in sorted(runner.FULL_RSS_STEPS)
    ]
    return {
        "pr": copy.deepcopy(pr),
        "workflow": {"id": 20, "state": "active", "path": ".github/workflows/ci.yml"},
        "runs": {"workflow_runs": [copy.deepcopy(run)]},
        "jobs": {"total_count": len(jobs), "jobs": jobs},
        "check": {
            "name": "ci-gate",
            "status": "completed",
            "conclusion": "success",
            "app": {"id": 15368, "slug": "github-actions"},
            "check_suite": {"id": 30},
        },
    }


def install(monkeypatch, data, *, dirty=False, moved=False):
    calls = []

    def read(args, **kwargs):
        calls.append(args)
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return HEAD
        if args[:2] == ["git", "diff"]:
            return "changed.py" if dirty else ""
        assert args[:2] == ["gh", "api"]
        path = args[2]
        if path.endswith("pulls/307"):
            result = copy.deepcopy(data["pr"])
            if moved and sum(c[0] == "gh" and c[2].endswith("pulls/307") for c in calls) > 1:
                result["head"]["sha"] = "c" * 40
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
            raise AssertionError(f"unexpected external operation {args}")
        return json.dumps(result)

    def ancestry(args, **kwargs):
        assert args[:3] == ["git", "merge-base", "--is-ancestor"]
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(runner.subprocess, "check_output", read)
    monkeypatch.setattr(runner.subprocess, "run", ancestry)
    return calls


def test_exact_head_formal_pr_full_jobs_pass_without_push_or_new_grant(tmp_path, monkeypatch):
    install(monkeypatch, responses())
    result = runner.github_admission(tmp_path)
    assert set(result["ci"]) == {"pull_request"}
    assert result["head"] == HEAD
    assert result["acceptance"] == "EXACT_HEAD_FULL_PULL_REQUEST_NOT_FAST_OR_DISPATCH"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "fault",
    [
        "fast_workflow",
        "dispatch",
        "push",
        "wrong_head",
        "wrong_branch",
        "wrong_repo",
        "wrong_pr",
        "missing_pr",
        "stale_base",
        "pending",
        "failed",
        "cancelled",
        "workflow_disabled",
        "missing_job",
        "skipped_job",
        "cancelled_job",
        "duplicate_job",
        "missing_rss",
        "skipped_rss",
        "forged_app",
        "wrong_check_suite",
        "wrong_check_name",
        "incomplete_jobs_page",
        "closed_pr",
        "ready_pr",
        "fork_pr",
        "pr_head_mismatch",
    ],
)
def test_nonformal_stale_incomplete_or_forged_ci_fails_closed(tmp_path, monkeypatch, fault):
    data = responses()
    run = data["runs"]["workflow_runs"][0]
    jobs = data["jobs"]["jobs"]
    if fault == "fast_workflow":
        run["path"] = ".github/workflows/ci-fast.yml"
    elif fault in {"dispatch", "push"}:
        run["event"] = "workflow_dispatch" if fault == "dispatch" else "push"
    elif fault == "wrong_head":
        run["head_sha"] = "c" * 40
    elif fault == "wrong_branch":
        run["head_branch"] = "unrelated"
    elif fault == "wrong_repo":
        run["head_repository"]["full_name"] = "other/repository"
    elif fault == "wrong_pr":
        run["pull_requests"][0]["number"] = 999
    elif fault == "missing_pr":
        run["pull_requests"] = []
    elif fault == "stale_base":
        run["pull_requests"][0]["base"]["sha"] = "c" * 40
    elif fault == "pending":
        run["status"] = "in_progress"
    elif fault in {"failed", "cancelled"}:
        run["conclusion"] = "failure" if fault == "failed" else "cancelled"
    elif fault == "workflow_disabled":
        data["workflow"]["state"] = "disabled_manually"
    elif fault == "missing_job":
        jobs.pop()
        data["jobs"]["total_count"] -= 1
    elif fault in {"skipped_job", "cancelled_job"}:
        jobs[0]["conclusion"] = "skipped" if fault == "skipped_job" else "cancelled"
    elif fault == "duplicate_job":
        jobs.append(copy.deepcopy(jobs[0]))
        data["jobs"]["total_count"] += 1
    elif fault == "incomplete_jobs_page":
        data["jobs"]["total_count"] += 1
    elif fault in {"missing_rss", "skipped_rss"}:
        steps = next(j for j in jobs if j["name"] == "backend-sqlite")["steps"]
        if fault == "missing_rss":
            steps.pop()
        else:
            steps[0]["conclusion"] = "skipped"
    elif fault == "forged_app":
        data["check"]["app"]["id"] = 999
    elif fault == "wrong_check_suite":
        data["check"]["check_suite"]["id"] = 999
    elif fault == "wrong_check_name":
        data["check"]["name"] = "fast-ci-gate"
    elif fault == "closed_pr":
        data["pr"]["state"] = "closed"
    elif fault == "ready_pr":
        data["pr"]["draft"] = False
    elif fault == "fork_pr":
        data["pr"]["head"]["repo"]["full_name"] = "fork/repository"
    elif fault == "pr_head_mismatch":
        data["pr"]["head"]["sha"] = "c" * 40
    install(monkeypatch, data)
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        runner.github_admission(tmp_path)
    assert not list(tmp_path.iterdir())


def test_new_pending_formal_run_cannot_reuse_older_success(tmp_path, monkeypatch):
    data = responses()
    latest = copy.deepcopy(data["runs"]["workflow_runs"][0])
    latest.update(id=11, status="in_progress", conclusion=None)
    data["runs"]["workflow_runs"].append(latest)
    install(monkeypatch, data)
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        runner.github_admission(tmp_path)


@pytest.mark.parametrize("flag", ["dirty", "moved"])
def test_mutating_source_or_pr_identity_is_refused(tmp_path, monkeypatch, flag):
    install(monkeypatch, responses(), **{flag: True})
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        runner.github_admission(tmp_path)


def r4_responses():
    with pytest.MonkeyPatch.context() as importer:
        importer.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
        entry = importlib.import_module("run_stage_b_r4_main")
    data = responses()
    data["pr"].update(number=310)
    data["pr"]["base"].update(ref=entry.CI_IDENTITY["base_ref"], sha=entry.CI_IDENTITY["base_sha"])
    data["pr"]["head"]["ref"] = entry.CI_IDENTITY["head_ref"]
    run = data["runs"]["workflow_runs"][0]
    run["head_branch"] = entry.CI_IDENTITY["head_ref"]
    run["pull_requests"] = [
        {
            "number": 310,
            "head": copy.deepcopy(data["pr"]["head"]),
            "base": copy.deepcopy(data["pr"]["base"]),
        }
    ]
    coverage = copy.deepcopy(data["jobs"]["jobs"][0])
    coverage.update(name="backend-partition-coverage")
    data["jobs"]["jobs"].append(coverage)
    data["jobs"]["total_count"] += 1
    return entry, data


def install_r4(monkeypatch, data, *, moved=None):
    calls = []

    def read(args, **kwargs):
        calls.append(args)
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return HEAD
        if args[:2] == ["git", "diff"]:
            return ""
        assert args[:2] == ["gh", "api"]
        path = args[2]
        if path.endswith("pulls/310"):
            result = copy.deepcopy(data["pr"])
            if moved and sum(c[0] == "gh" and c[2].endswith("pulls/310") for c in calls) > 1:
                result[moved]["sha"] = "d" * 40
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
            raise AssertionError(f"unexpected R4 external call {args}")
        return json.dumps(result)

    monkeypatch.setattr(runner.subprocess, "check_output", read)

    def ancestry(args, **kwargs):
        assert args[:3] == ["git", "merge-base", "--is-ancestor"]
        assert args[3] == "6b114ac3cda934b07e7d8fbe00d95904e7aa996a"
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(runner.subprocess, "run", ancestry)
    return calls


def test_r4_exact_head_stacked_pr_requires_partition_coverage_and_original_rss(
    tmp_path, monkeypatch
):
    entry, data = r4_responses()
    calls = install_r4(monkeypatch, data)
    result = entry.github_admission(tmp_path)
    assert result["pr"]["number"] == 310 and result["head"] == HEAD
    assert set(result["formal_ci_jobs"]) == runner.FULL_CI_JOBS | {"backend-partition-coverage"}
    assert not any("pulls/307" in str(c) for c in calls)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "fault",
    [
        "pr307",
        "base_main",
        "base_sha",
        "head_ref",
        "run_pr307",
        "run_base_main",
        "run_stale_base",
        "fast",
        "dispatch",
        "push",
        "old_head",
        "workflow_id",
        "coverage_missing",
        "coverage_failed",
        "coverage_skipped",
        "coverage_cancelled",
        "rss1_missing",
        "rss2_skipped",
        "rss_verify_failed",
        "rss_isolation_skipped",
        "gate_wrong_app",
        "gate_wrong_suite",
        "gate_skipped",
        "incomplete_jobs",
        "pending",
        "cancelled",
        "failed",
        "empty_runs",
        "fork",
        "ready",
        "closed",
    ],
)
def test_r4_rejects_wrong_identity_incomplete_or_nonformal_ci(tmp_path, monkeypatch, fault):
    entry, data = r4_responses()
    run = data["runs"]["workflow_runs"][0]
    if fault == "pr307":
        data["pr"]["number"] = 307
    elif fault == "base_main":
        data["pr"]["base"]["ref"] = "main"
    elif fault == "base_sha":
        data["pr"]["base"]["sha"] = BASE
    elif fault == "head_ref":
        data["pr"]["head"]["ref"] = "codex/other"
    elif fault == "run_pr307":
        run["pull_requests"][0]["number"] = 307
    elif fault == "run_base_main":
        run["pull_requests"][0]["base"]["ref"] = "main"
    elif fault == "run_stale_base":
        run["pull_requests"][0]["base"]["sha"] = BASE
    elif fault == "fast":
        run["path"] = ".github/workflows/ci-fast.yml"
    elif fault == "dispatch":
        run["event"] = "workflow_dispatch"
    elif fault == "push":
        run["event"] = "push"
    elif fault == "old_head":
        run["head_sha"] = "c" * 40
    elif fault == "workflow_id":
        run["workflow_id"] = 99
    elif fault.startswith("coverage"):
        jobs = data["jobs"]["jobs"]
        coverage = next(j for j in jobs if j["name"] == "backend-partition-coverage")
        if fault == "coverage_missing":
            jobs.remove(coverage)
            data["jobs"]["total_count"] -= 1
        else:
            coverage["conclusion"] = fault.split("_")[1].replace("failed", "failure")
    elif fault.startswith("rss"):
        steps = next(j for j in data["jobs"]["jobs"] if j["name"] == "backend-sqlite")["steps"]
        name = {
            "rss1_missing": "Linux physical RSS independent worker 1",
            "rss2_skipped": "Linux physical RSS independent worker 2",
            "rss_verify_failed": "Require two real Linux RSS overlimit rejections",
            "rss_isolation_skipped": "Linux physical RSS worker isolation regressions",
        }[fault]
        step = next(s for s in steps if s["name"] == name)
        if fault == "rss1_missing":
            steps.remove(step)
        else:
            step["conclusion"] = "failure" if fault.endswith("failed") else "skipped"
    elif fault == "gate_wrong_app":
        data["check"]["app"]["id"] = 999
    elif fault == "gate_wrong_suite":
        data["check"]["check_suite"]["id"] = 999
    elif fault == "gate_skipped":
        data["check"]["conclusion"] = "skipped"
    elif fault == "incomplete_jobs":
        data["jobs"]["total_count"] += 1
    elif fault == "pending":
        run["status"] = "in_progress"
    elif fault in {"cancelled", "failed"}:
        run["conclusion"] = "failure" if fault == "failed" else fault
    elif fault == "empty_runs":
        data["runs"]["workflow_runs"] = []
    elif fault == "fork":
        data["pr"]["head"]["repo"]["full_name"] = "fork/repo"
    elif fault == "ready":
        data["pr"]["draft"] = False
    elif fault == "closed":
        data["pr"]["state"] = "closed"
    install_r4(monkeypatch, data)
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        entry.github_admission(tmp_path)


@pytest.mark.parametrize("moved", ["head", "base"])
def test_r4_head_or_base_moving_during_admission_is_refused(tmp_path, monkeypatch, moved):
    entry, data = r4_responses()
    install_r4(monkeypatch, data, moved=moved)
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        entry.github_admission(tmp_path)


def test_r4_new_pending_formal_run_does_not_reuse_previous_success(tmp_path, monkeypatch):
    entry, data = r4_responses()
    latest = copy.deepcopy(data["runs"]["workflow_runs"][0])
    latest.update(id=11, status="in_progress", conclusion=None)
    data["runs"]["workflow_runs"].append(latest)
    install_r4(monkeypatch, data)
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        entry.github_admission(tmp_path)


def test_original_pr307_entry_does_not_accept_r4_identity(tmp_path, monkeypatch):
    _, data = r4_responses()
    install(monkeypatch, data)
    with pytest.raises(LayoutAuthorityError, match="CI_ADMISSION_BLOCKED"):
        runner.github_admission(tmp_path)
