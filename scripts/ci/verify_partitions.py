"""Fail closed unless every original applicable node ran in exactly one shard."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zipfile import ZipFile

GENERAL = {f"general-{index}" for index in range(4)}
COMPOSITION_FILES = {
    "tests/unit/test_v222_p1a_composition_exact_placement.py",
    "tests/unit/test_v222_p1a_composition_candidate_validation.py",
}


def verify(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    sqlite_nodes: set[str] = set()
    for backend in ("sqlite", "postgresql"):
        rows = [row for row in receipts if row.get("backend") == backend]
        groups = GENERAL | ({"composition", "architecture"} if backend == "sqlite" else set())
        if Counter(row.get("partition") for row in rows) != Counter(dict.fromkeys(groups, 1)):
            raise ValueError(f"{backend}: missing, unknown or duplicate partition")
        original = set(rows[0]["original_nodes"])
        selected: list[str] = []
        shared = set(rows[0]["shared_with_sqlite"])
        for row in rows:
            if row.get("schema") != "ci-partition-v1" or row.get("exitstatus") != 0:
                raise ValueError(f"{backend}: unsuccessful or malformed receipt")
            if set(row["original_nodes"]) != original or set(row["shared_with_sqlite"]) != shared:
                raise ValueError(f"{backend}: inconsistent original collection")
            nodes = row["selected_nodes"]
            if len(set(nodes)) != len(nodes):
                raise ValueError("duplicate node inside partition")
            selected.extend(nodes)
            reports = row["reports"]
            if any(r["outcome"] == "failed" for r in reports):
                raise ValueError("failed execution report")
            completed = [
                r["nodeid"]
                for r in reports
                if r["when"] == "call" or r["when"] == "setup" and r["outcome"] == "skipped"
            ]
            if Counter(completed) != Counter(nodes):
                raise ValueError("collection does not match actual execution")
        if Counter(selected) != Counter(dict.fromkeys(original - shared, 1)):
            raise ValueError(f"{backend}: missing or duplicated applicable test")
        if backend == "sqlite":
            if shared:
                raise ValueError("SQLite must not delegate tests")
            sqlite_nodes = {
                r["nodeid"]
                for row in rows
                for r in row["reports"]
                if r["when"] == "call" and r["outcome"] == "passed" and r.get("wasxfail") is None
            }
        elif shared != {n for n in original if n.split("::", 1)[0] in COMPOSITION_FILES}:
            raise ValueError("unapproved PostgreSQL exclusion")
        elif not shared <= sqlite_nodes:
            raise ValueError("database-independent tests did not execute in SQLite suite")
        summary[backend] = {
            "original_count": len(original),
            "executed_count": len(selected),
            "shared_database_independent_count": len(shared),
            "skipped_reports": [
                r for row in rows for r in row["reports"] if r["outcome"] == "skipped"
            ],
            "slowest_reports": sorted(
                [r for row in rows for r in row["reports"]],
                key=lambda r: r["duration"],
                reverse=True,
            )[:30],
        }
    return summary


EXPECTED_JOBS = {
    (backend, group): (
        "backend-architecture" if group == "architecture" else f"backend-{backend}-shards ({group})"
    )
    for backend in ("sqlite", "postgresql")
    for group in sorted(
        GENERAL | ({"composition", "architecture"} if backend == "sqlite" else set())
    )
}
ARTIFACT_NAME = re.compile(
    r"ci-partition-(sqlite|postgresql)-(general-[0-3]|composition|architecture)-([1-9][0-9]*)"
)
UPLOAD_STEP = "Preserve partition execution manifest"


def _time(value: Any) -> datetime:
    # GitHub logs use seven fractional digits; Python 3.9 accepts at most six.
    stamp = re.sub(r"(\.\d{6})\d+(?=[+-]\d\d:\d\d$)", r"\1", str(value).replace("Z", "+00:00"))
    result = datetime.fromisoformat(stamp)
    if result.tzinfo is None:
        raise ValueError("missing GitHub timestamp timezone")
    return result


def _identity(run: dict[str, Any]) -> tuple[Any, ...]:
    return (
        run["id"],
        run["head_sha"],
        run["repository"]["id"],
        run["head_repository"]["id"],
        run["head_branch"],
        run["workflow_id"],
        run["path"],
        run["event"],
    )


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [s for s in job["steps"] if s["name"] == name]
    if (
        len(matches) != 1
        or matches[0]["status"] != "completed"
        or matches[0]["conclusion"] != "success"
    ):
        raise ValueError(f"missing or unsuccessful producer step: {name}")
    return dict(matches[0])


def select_sources(
    run: dict[str, Any],
    attempts: dict[int, dict[str, Any]],
    jobs: dict[int, list[dict[str, Any]]],
    artifacts: list[dict[str, Any]],
    *,
    repository: str,
    run_id: int,
    head: str,
    attempt: int,
) -> dict[str, Any]:
    """Bind immutable artifacts to actual executions, not inherited rerun snapshots.

    A later jobs API response can clone an earlier successful execution under a
    new job ID/run_attempt. Only an identical execution fingerprint AND earlier
    execution timestamps may inherit its original upload. A newer failed job
    can never fall back to an older successful artifact.
    """
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or not re.fullmatch(r"[0-9a-f]{40}", head)
        or type(run_id) is not int
        or run_id <= 0
        or type(attempt) is not int
        or attempt <= 0
        or run["id"] != run_id
        or run["head_sha"] != head
        or run["repository"]["full_name"] != repository
        or run["run_attempt"] != attempt
        or run["path"].split("@", 1)[0] != ".github/workflows/ci.yml"
        or run["event"] not in {"pull_request", "push", "workflow_dispatch"}
        or set(attempts) != set(range(1, attempt + 1))
        or set(jobs) != set(attempts)
    ):
        raise ValueError("workflow Run/HEAD/Attempt identity mismatch")
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    origins: dict[str, dict[str, Any]] = {}
    observed: dict[tuple[int, tuple[str, str]], dict[str, Any]] = {}
    for number in range(1, attempt + 1):
        meta = attempts[number]
        if _identity(meta) != _identity(run) or meta["run_attempt"] != number:
            raise ValueError("foreign or missing attempt metadata")
        start = _time(meta["run_started_at"])
        seen: set[tuple[str, str]] = set()
        for job in jobs[number]:
            groups = [g for g, name in EXPECTED_JOBS.items() if name == job["name"]]
            if not groups:
                continue
            group = groups[0]
            if (
                group in seen
                or job["run_id"] != run_id
                or job["head_sha"] != head
                or job["run_attempt"] != number
                or type(job["id"]) is not int
                or job["id"] <= 0
                or job["status"] != "completed"
            ):
                raise ValueError("duplicate, foreign or unfinished producer Job")
            seen.add(group)
            began, ended = _time(job["started_at"]), _time(job["completed_at"])
            if ended < began:
                raise ValueError("invalid producer execution interval")
            fingerprint = json.dumps(
                {
                    k: job[k]
                    for k in (
                        "name",
                        "run_id",
                        "head_sha",
                        "status",
                        "conclusion",
                        "started_at",
                        "completed_at",
                        "steps",
                    )
                },
                sort_keys=True,
            )
            if fingerprint in origins:
                if began >= start:
                    raise ValueError("ambiguous repeated execution identity")
                origin = origins[fingerprint]
            else:
                if began < start or (
                    number < attempt and ended > _time(attempts[number + 1]["run_started_at"])
                ):
                    raise ValueError("unproven inherited Job or overlapping attempts")
                origin = dict(attempt=number, job=job)
                origins[fingerprint] = origin
            observed[number, group] = origin
            latest[group] = origin
        if seen != set(EXPECTED_JOBS):
            raise ValueError("incomplete attempt producer Job collection")
    if set(latest) != set(EXPECTED_JOBS):
        raise ValueError("missing expected producer Job")
    by_group: dict[tuple[int, tuple[str, str]], dict[str, Any]] = {}
    names: set[str] = set()
    ids: set[int] = set()
    for artifact in artifacts:
        if not artifact["name"].startswith("ci-partition-"):
            continue
        match = ARTIFACT_NAME.fullmatch(artifact["name"])
        if match is None:
            raise ValueError("unknown partition artifact name")
        backend, partition, n = match.groups()
        key = int(n), (backend, partition)
        source = artifact["workflow_run"]
        if (
            key not in observed
            or observed[key]["attempt"] != int(n)
            or (backend, partition) not in EXPECTED_JOBS
            or artifact["name"] in names
            or type(artifact["id"]) is not int
            or artifact["id"] <= 0
            or artifact["id"] in ids
            or key in by_group
            or artifact["expired"] is not False
            or source["id"] != run_id
            or source["head_sha"] != head
            or source["repository_id"] != run["repository"]["id"]
            or source["head_repository_id"] != run["head_repository"]["id"]
            or source["head_branch"] != run["head_branch"]
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["digest"])
        ):
            raise ValueError("duplicate or unproven artifact Run/HEAD/Attempt source")
        names.add(artifact["name"])
        ids.add(artifact["id"])
        by_group[key] = artifact
    selected = []
    for group, origin in sorted(latest.items()):
        job = origin["job"]
        if job["conclusion"] != "success":
            raise ValueError("latest producer failed; older success cannot substitute")
        _step(job, f"Backend partition ({group[0]})")
        upload = _step(job, UPLOAD_STEP)
        key = origin["attempt"], group
        if key not in by_group:
            raise ValueError("latest execution artifact missing; no stale fallback")
        artifact = by_group[key]
        if (
            not _time(upload["started_at"])
            <= _time(artifact["created_at"])
            <= _time(upload["completed_at"])
        ):
            raise ValueError("artifact outside producer upload interval")
        selected.append(dict(backend=group[0], partition=group[1], **origin, artifact=artifact))
    return dict(
        run_id=run_id,
        head=head,
        attempt=attempt,
        run_conclusion=run.get("conclusion"),
        selected=selected,
        artifact_names=sorted(names),
        superseded_artifact_ids=sorted(ids - {s["artifact"]["id"] for s in selected}),
    )


def verify_downloads(
    directory: Path,
    selection: dict[str, Any],
    read_archive: Callable[[int], bytes],
    read_log: Callable[[int], str],
) -> dict[str, Any]:
    """Require official ZIP digest/upload receipts and unchanged per-artifact files."""
    children = list(directory.iterdir())
    if {p.name for p in children} != set(selection["artifact_names"]) or any(
        not p.is_dir() or p.is_symlink() for p in children
    ):
        raise ValueError("missing, extra or merged artifact directories")
    receipts = []
    sources = []
    for selected in selection["selected"]:
        artifact, job = selected["artifact"], selected["job"]
        upload = _step(job, UPLOAD_STEP)
        log = read_log(job["id"])
        # Job step timestamps have second resolution; raw log timestamps have fractions.
        start, stop = (
            _time(upload["started_at"]),
            _time(upload["completed_at"]) + timedelta(seconds=1),
        )
        digest_rows = re.findall(
            r"(?m)^(\S+) SHA256 digest of uploaded artifact zip is ([0-9a-f]{64})\s*$", log
        )
        id_rows = re.findall(
            r"(?m)^(\S+) Artifact "
            + re.escape(artifact["name"])
            + r"\.zip successfully finalized\. Artifact ID ([0-9]+)\s*$",
            log,
        )
        digests = [d for t, d in digest_rows if start <= _time(t) < stop]
        identifiers = [int(i) for t, i in id_rows if start <= _time(t) < stop]
        digest = artifact["digest"].removeprefix("sha256:")
        if digests != [digest] or identifiers != [artifact["id"]]:
            raise ValueError("producer log does not prove unique artifact ID/digest upload")
        archive = read_archive(artifact["id"])
        if hashlib.sha256(archive).hexdigest() != digest:
            raise ValueError("official artifact ZIP digest mismatch")
        filename = f"ci-{selected['backend']}-{selected['partition']}.json"
        path = directory / artifact["name"] / filename
        if path.is_symlink() or set(p.name for p in path.parent.iterdir()) != {filename}:
            raise ValueError("extra, redirected or duplicate partition file")
        with ZipFile(io.BytesIO(archive)) as zip_file:
            if zip_file.namelist() != [filename] or zip_file.read(filename) != path.read_bytes():
                raise ValueError("local receipt differs from source artifact ZIP")
        row = json.loads(path.read_text())
        if (
            row.get("backend") != selected["backend"]
            or row.get("partition") != selected["partition"]
        ):
            raise ValueError("receipt backend/partition conflicts with artifact source")
        receipts.append(row)
        sources.append(
            dict(
                backend=selected["backend"],
                partition=selected["partition"],
                producer_attempt=selected["attempt"],
                producer_job_id=job["id"],
                artifact_id=artifact["id"],
                artifact_name=artifact["name"],
                digest=artifact["digest"],
            )
        )
    return dict(
        coverage=verify(receipts),
        sources=sources,
        run_id=selection["run_id"],
        head=selection["head"],
        attempt=selection["attempt"],
        superseded_artifact_ids=selection["superseded_artifact_ids"],
        original_run_conclusion=selection["run_conclusion"],
        formal_ci_success_claimed=False,
    )


def github_bytes(repository: str, path: str, *, paginate: bool = False) -> bytes:
    args = ["gh", "api", f"repos/{repository}/actions/{path}"]
    if paginate:
        args += ["--paginate", "--slurp"]
    return subprocess.check_output(args)


def github_collection(repository: str, path: str, key: str) -> list[dict[str, Any]]:
    pages = json.loads(github_bytes(repository, path + "?per_page=100", paginate=True))
    total = pages[0]["total_count"]
    rows = [row for page in pages for row in page[key]]
    if (
        any(page["total_count"] != total for page in pages)
        or len(rows) != total
        or len({r["id"] for r in rows}) != total
    ):
        raise ValueError("incomplete or duplicate GitHub API collection")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository)
        or args.run_id <= 0
        or args.attempt <= 0
    ):
        parser.error("invalid GitHub source identity")
    base = f"runs/{args.run_id}"
    run = json.loads(github_bytes(args.repository, base))
    attempts = {
        n: json.loads(github_bytes(args.repository, f"{base}/attempts/{n}"))
        for n in range(1, args.attempt + 1)
    }
    jobs = {
        n: github_collection(args.repository, f"{base}/attempts/{n}/jobs", "jobs") for n in attempts
    }
    artifacts = github_collection(args.repository, f"{base}/artifacts", "artifacts")
    selection = select_sources(
        run,
        attempts,
        jobs,
        artifacts,
        repository=args.repository,
        run_id=args.run_id,
        head=args.head,
        attempt=args.attempt,
    )
    result = verify_downloads(
        args.directory,
        selection,
        lambda identifier: github_bytes(args.repository, f"artifacts/{identifier}/zip"),
        lambda identifier: github_bytes(args.repository, f"jobs/{identifier}/logs").decode(),
    )
    after = json.loads(github_bytes(args.repository, base))
    if _identity(after) != _identity(run) or after["run_attempt"] != args.attempt:
        raise ValueError("Run identity changed during coverage verification")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
