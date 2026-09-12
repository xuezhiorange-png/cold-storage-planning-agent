"""Repository-owned, fail-safe CI planning. No third-party runtime dependencies."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

REGULAR_JOBS = (
    "lightweight",
    "backend-sqlite",
    "backend-postgresql",
    "frontend",
    "compose-config",
    "release-evidence",
    "recovery-foundation",
)
SCOPE_JOBS: dict[str, frozenset[str]] = {
    "DOCS_ARCHITECTURE_ONLY": frozenset({"lightweight"}),
    "BACKEND": frozenset(
        {
            "backend-sqlite",
            "backend-postgresql",
            "compose-config",
            "release-evidence",
            "recovery-foundation",
        }
    ),
    "FRONTEND": frozenset({"frontend", "release-evidence"}),
    "BACKEND_FRONTEND": frozenset(set(REGULAR_JOBS) - {"lightweight"}),
    "FULL": frozenset(set(REGULAR_JOBS) - {"lightweight"}),
}
OUTPUT_JOBS = {
    "lightweight": "lightweight",
    "backend": "backend-sqlite",
    "frontend": "frontend",
    "infra": "compose-config",
    "release": "release-evidence",
    "recovery": "recovery-foundation",
}
# These take precedence over language scopes, including frontend dependencies.
FULL_PREFIXES = (
    ".github/",
    "scripts/ci/",
    "backend/alembic/",
    "deployment/",
    "backend/src/cold_storage/bootstrap/",
    "backend/src/cold_storage/release/",
)
MANIFEST_NAMES = {
    "pyproject.toml",
    "package.json",
    "Pipfile",
    "Pipfile.lock",
    "uv.lock",
    "poetry.lock",
    "pdm.lock",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "bun.lockb",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Gemfile",
    "Gemfile.lock",
    ".python-version",
    ".node-version",
    ".nvmrc",
    ".npmrc",
}
SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


@dataclass(frozen=True)
class Plan:
    scope: str
    reason: str
    base: str = ""
    head: str = ""

    def outputs(self) -> dict[str, str]:
        jobs = SCOPE_JOBS[self.scope]
        return {
            "scope": self.scope,
            "reason": self.reason,
            "base": self.base,
            "head": self.head,
            **{key: str(job in jobs).lower() for key, job in OUTPUT_JOBS.items()},
        }


def classify_paths(paths: Sequence[str]) -> Plan:
    if not paths:
        return Plan("FULL", "EMPTY_CHANGE_SET")
    kinds: set[str] = set()
    for raw in paths:
        if (
            not raw
            or raw.startswith("/")
            or "\\" in raw
            or any(part in {"", ".", ".."} for part in raw.split("/"))
        ):
            return Plan("FULL", "UNKNOWN_FAIL_SAFE")
        path = PurePosixPath(raw)
        name = path.name
        if (
            raw.startswith(FULL_PREFIXES)
            or name in MANIFEST_NAMES
            or name.endswith(".lock")
            or name.startswith("requirements")
            and name.endswith((".txt", ".in"))
            or name == "Dockerfile"
            or name.startswith("Dockerfile.")
            or name.startswith(("docker-compose", "compose"))
            and name.endswith((".yml", ".yaml"))
            or raw == "backend/alembic.ini"
            or raw.startswith("backend/src/")
            and (
                "infrastructure" in path.parts
                or name in {"config.py", "settings.py", "entrypoint.py"}
            )
        ):
            return Plan("FULL", "DATABASE_INFRA_FULL")
        if raw.startswith(("docs/", "backend/tests/architecture/")):
            kinds.add("docs")
        elif raw.startswith(("backend/src/", "backend/tests/")):
            kinds.add("backend")
        elif raw.startswith("frontend/"):
            kinds.add("frontend")
        else:
            return Plan("FULL", "UNKNOWN_FAIL_SAFE")
    if kinds == {"docs"}:
        return Plan("DOCS_ARCHITECTURE_ONLY", "ONLY_DOCS_AND_ARCHITECTURE")
    if {"backend", "frontend"} <= kinds:
        return Plan("BACKEND_FRONTEND", "BACKEND_AND_FRONTEND")
    if "backend" in kinds:
        return Plan("BACKEND", "BACKEND_CHANGED")
    # Mixed frontend+docs must still run architecture/contract checks.
    if "docs" in kinds:
        return Plan("FULL", "MIXED_FRONTEND_AND_CONTRACT")
    return Plan("FRONTEND", "FRONTEND_CHANGED")


def _commit(repo: Path, value: object) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value) or int(value, 16) == 0:
        raise ValueError("invalid or zero commit SHA")
    kind = subprocess.check_output(
        ["git", "cat-file", "-t", value],
        cwd=repo,
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()
    if kind != "commit":
        raise ValueError("SHA does not identify a commit")
    return value.lower()


def classify_event(event_name: str, event: object, github_sha: str, repo: Path) -> Plan:
    if event_name == "workflow_dispatch":
        return Plan("FULL", "MANUAL_DEFAULT_FULL")
    try:
        if not isinstance(event, Mapping):
            raise ValueError("missing event")
        if event_name == "pull_request":
            # Never use GITHUB_SHA: it may be the synthetic merge commit.
            pr = event["pull_request"]
            base = _commit(repo, pr["base"]["sha"])
            head = _commit(repo, pr["head"]["sha"])
        elif event_name == "push":
            if event.get("created") or event.get("deleted"):
                return Plan("FULL", "PUSH_REF_LIFECYCLE")
            base = _commit(repo, event["before"])
            head = _commit(repo, github_sha)
            if "after" in event and event["after"] != head:
                raise ValueError("push event SHA disagreement")
        else:
            return Plan("FULL", "UNSUPPORTED_EVENT")
        # Disable rename detection so both old and new paths are classified.
        raw = subprocess.check_output(
            ["git", "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", base, head],
            cwd=repo,
            stderr=subprocess.DEVNULL,
        )
        paths = [part.decode("utf-8", errors="strict") for part in raw.split(b"\0") if part]
        plan = classify_paths(paths)
        return Plan(plan.scope, plan.reason, base, head)
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError):
        return Plan("FULL", "INVALID_OR_UNAVAILABLE_DIFF")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", nargs="*", help="local simulation; bypass event loading")
    args = parser.parse_args()
    if args.paths is not None:
        plan = classify_paths(args.paths)
    else:
        try:
            event: Any = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        except (KeyError, ValueError, OSError):
            event = None
        plan = classify_event(
            os.environ.get("GITHUB_EVENT_NAME", ""),
            event,
            os.environ.get("GITHUB_SHA", ""),
            Path.cwd(),
        )
    outputs = plan.outputs()
    print(json.dumps(outputs, sort_keys=True))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in outputs.items()))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(f"CI scope: **{plan.scope}** ({plan.reason})\n")
            stream.write("Required jobs: " + ", ".join(sorted(SCOPE_JOBS[plan.scope])) + "\n")


if __name__ == "__main__":
    main()
