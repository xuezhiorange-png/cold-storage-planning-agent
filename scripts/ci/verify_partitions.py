"""Fail closed unless every original applicable node ran in exactly one shard."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

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


def main() -> None:
    receipts = [json.loads(path.read_text()) for path in Path(sys.argv[1]).rglob("ci-*.json")]
    print(json.dumps(verify(receipts), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
