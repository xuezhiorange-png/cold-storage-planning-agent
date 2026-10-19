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


def github_admission(repo: Path) -> dict[str, Any]:
    def read(args: list[str]) -> str:
        return subprocess.check_output(args, cwd=repo, text=True).strip()

    head = read(["git", "rev-parse", "HEAD"])
    pr = json.loads(read(["gh", "pr", "view", "307", "--json", "headRefOid,isDraft,state"]))
    runs = json.loads(
        read(
            [
                "gh",
                "run",
                "list",
                "--commit",
                head,
                "--workflow",
                "ci.yml",
                "--json",
                "databaseId,event,status,conclusion,headSha",
                "--limit",
                "30",
            ]
        )
    )
    latest = {}
    for event in ("pull_request", "push"):
        matching = [r for r in runs if r["event"] == event and r["headSha"] == head]
        latest[event] = max(matching, key=lambda r: r["databaseId"]) if matching else None
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", REFERENCE_HEAD, head], cwd=repo, check=True
    )
    if pr != {"headRefOid": head, "isDraft": True, "state": "OPEN"} or any(
        not r or r["status"] != "completed" or r["conclusion"] != "success" for r in latest.values()
    ):
        raise LayoutAuthorityError("GUIDED_FAIR_EXACT_HEAD_CI_ADMISSION_BLOCKED")
    return dict(head=head, pr=pr, ci=latest)


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
