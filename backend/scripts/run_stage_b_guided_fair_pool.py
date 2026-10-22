"""One pinned guided fair grant; only approved TXT and evidence output arguments."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from run_stage_b_fair_pool import execute_fair_pools, fair_binding
from run_stage_b_owner_pool import dump, server_inputs

from cold_storage.bootstrap.global_composition import (
    GUIDED_FAIR_OWNER_SHA256,
    approved_stage_b_guided_fair_store,
)
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.stage_b_guided_fair_execution import (
    GUIDED_EXECUTION_CONTRACT,
)

REFERENCE_HEAD = "03b574b0428b5c4394827e87597859d671a70490"
GITHUB_REPOSITORY = "xuezhiorange-png/cold-storage-planning-agent"
FULL_CI_JOBS = frozenset(
    {
        "classify-changes",
        "backend-sqlite",
        "backend-postgresql",
        "frontend",
        "compose-config",
        "release-evidence",
        "recovery-foundation",
        "ci-gate",
    }
)
FULL_RSS_STEPS = frozenset(
    {
        "Linux physical RSS independent worker 1",
        "Linux physical RSS independent worker 2",
        "Require two real Linux RSS overlimit rejections",
        "Linux physical RSS worker isolation regressions",
    }
)


def github_admission(repo: Path) -> dict[str, Any]:
    """Only exact-head, source-bound formal PR acceptance; never fast/dispatch.

    This replaces the obsolete duplicate PR+Push CI condition only. Callers
    still verify the fixed Owner TXT, committed source, policy/dependency binding
    and the one-use durable ledger before any native execution.
    """

    def read(args: list[str]) -> str:
        return subprocess.check_output(args, cwd=repo, text=True).strip()

    def api(path: str) -> Any:
        return json.loads(read(["gh", "api", f"repos/{GITHUB_REPOSITORY}/{path}"]))

    def require(condition: bool) -> None:
        if not condition:
            raise LayoutAuthorityError("GUIDED_FAIR_EXACT_HEAD_CI_ADMISSION_BLOCKED")

    def identity(value: dict[str, Any]) -> tuple[Any, ...]:
        return (
            value["number"],
            value["state"],
            value["draft"],
            value["head"]["sha"],
            value["head"]["ref"],
            value["head"]["repo"]["id"],
            value["head"]["repo"]["full_name"],
            value["base"]["sha"],
            value["base"]["ref"],
            value["base"]["repo"]["id"],
            value["base"]["repo"]["full_name"],
        )

    try:
        head = read(["git", "rev-parse", "HEAD"])
        require(not read(["git", "diff", "HEAD", "--name-only"]))
        pr = api("pulls/307")
        require(
            pr["number"] == 307
            and pr["state"] == "open"
            and pr["draft"] is True
            and pr["head"]["sha"] == head
            and pr["head"]["repo"]["full_name"] == GITHUB_REPOSITORY
            and pr["base"]["repo"]["full_name"] == GITHUB_REPOSITORY
            and pr["base"]["ref"] == "main"
        )
        workflow = api("actions/workflows/ci.yml")
        require(workflow["path"] == ".github/workflows/ci.yml" and workflow["state"] == "active")
        runs = api(
            f"actions/workflows/{workflow['id']}/runs?event=pull_request&head_sha={head}&per_page=100"
        )["workflow_runs"]
        matching = [
            r
            for r in runs
            if r["event"] == "pull_request"
            and r["head_sha"] == head
            and r["workflow_id"] == workflow["id"]
            and r["path"] == ".github/workflows/ci.yml"
            and r["head_branch"] == pr["head"]["ref"]
            and r["head_repository"]["full_name"] == GITHUB_REPOSITORY
            and any(
                p["number"] == 307
                and p["head"]["sha"] == head
                and p["head"]["repo"]["id"] == pr["head"]["repo"]["id"]
                and p["base"]["ref"] == "main"
                and p["base"]["sha"] == pr["base"]["sha"]
                and p["base"]["repo"]["id"] == pr["base"]["repo"]["id"]
                for p in r["pull_requests"]
            )
        ]
        require(bool(matching))
        run = max(matching, key=lambda r: r["id"])
        require(run["status"] == "completed" and run["conclusion"] == "success")
        response = api(f"actions/runs/{run['id']}/jobs?per_page=100&filter=latest")
        jobs = response["jobs"]
        require(response["total_count"] == len(jobs))
        for name in FULL_CI_JOBS:
            found = [j for j in jobs if j["name"] == name]
            require(len(found) == 1)
            require(found[0]["status"] == "completed" and found[0]["conclusion"] == "success")
        sqlite = next(j for j in jobs if j["name"] == "backend-sqlite")
        for name in FULL_RSS_STEPS:
            found = [s for s in sqlite["steps"] if s["name"] == name]
            require(len(found) == 1)
            require(found[0]["status"] == "completed" and found[0]["conclusion"] == "success")
        gate = next(j for j in jobs if j["name"] == "ci-gate")
        prefix = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/check-runs/"
        require(gate["check_run_url"].startswith(prefix))
        check_id = gate["check_run_url"][len(prefix) :]
        require(check_id.isdigit())
        check = api(f"check-runs/{check_id}")
        require(
            check["name"] == "ci-gate"
            and check["status"] == "completed"
            and check["conclusion"] == "success"
            and check["app"]["id"] == 15368
            and check["app"]["slug"] == "github-actions"
            and check["check_suite"]["id"] == run["check_suite_id"]
        )
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", REFERENCE_HEAD, head], cwd=repo, check=True
        )
        # Do not admit a run if the PR moved while its jobs were being read.
        current = api("pulls/307")
        require(identity(current) == identity(pr))
        require(read(["git", "rev-parse", "HEAD"]) == head)
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise LayoutAuthorityError("GUIDED_FAIR_EXACT_HEAD_CI_ADMISSION_BLOCKED") from exc
    return dict(
        head=head,
        pr=pr,
        ci={"pull_request": run},
        formal_ci_jobs=sorted(FULL_CI_JOBS),
        acceptance="EXACT_HEAD_FULL_PULL_REQUEST_NOT_FAST_OR_DISPATCH",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-instruction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    instruction = args.owner_instruction.read_bytes()
    if hashlib.sha256(instruction).hexdigest() != GUIDED_FAIR_OWNER_SHA256:
        raise LayoutAuthorityError("POOL_OWNER_SOURCE_MISMATCH")
    repo = Path(__file__).resolve().parents[2]
    dirty = subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=repo, text=True)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "backend/src", "backend/scripts"],
        cwd=repo,
        text=True,
    )
    if dirty.strip() or untracked.strip():
        raise LayoutAuthorityError("POOL_COMMITTED_SOURCE_REQUIRED")
    admission = github_admission(repo)
    StageALedger().guard()
    store = approved_stage_b_guided_fair_store()
    # Re-entry cannot silently consume a replay or grant another MAIN. Unknown
    # claims/accounting require operator inspection, never a replacement slot.
    if (store.root / "task_ledger.json").exists() or any(store.root.glob("pool_*_claim.json")):
        raise LayoutAuthorityError("GUIDED_FAIR_EXISTING_EXECUTION_REQUIRES_INSPECTION")
    plan, p1, site = server_inputs(repo)
    binding = fair_binding(repo, plan, p1, site)
    binding["guided_execution_contract"] = dict(GUIDED_EXECUTION_CONTRACT)
    args.output.mkdir(parents=True, exist_ok=False)
    dump(args.output / "ci_admission.json", admission)
    dump(args.output / "source_binding.json", binding)
    dump(
        args.output / "server_authorities.json",
        dict(canonical_zone_plan=plan, p1_handoff=p1, typed_site=site.to_dict()),
    )
    execute_fair_pools(args.output, plan, p1, site, store, instruction, binding)


if __name__ == "__main__":
    main()
