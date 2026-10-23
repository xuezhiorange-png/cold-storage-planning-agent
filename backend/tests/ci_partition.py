"""Explicit CI partitions with collection and actual execution receipts.

No default selection changes: this plugin must be explicitly loaded by CI.
Resource workers do not load it and retain their original isolated semantics.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pytest

COMPOSITION_FILES = frozenset(
    {
        "tests/unit/test_v222_p1a_composition_exact_placement.py",
        "tests/unit/test_v222_p1a_composition_candidate_validation.py",
    }
)
GROUPS = tuple(f"general-{index}" for index in range(4))


def partition(nodeid: str) -> str:
    """Keep expensive shared fixtures together; spread other test functions."""
    path = nodeid.split("::", 1)[0]
    if path in COMPOSITION_FILES:
        return "composition"
    if path.startswith("tests/architecture/"):
        return "architecture"
    # Preserve module-scoped setup for the remainder. The known dominant
    # composition dependency graph has its own lane and session baseline;
    # hashing individual nodes here would multiply other expensive fixtures.
    return GROUPS[int(hashlib.sha256(path.encode()).hexdigest(), 16) % len(GROUPS)]


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("audited-ci-partition")
    group.addoption("--ci-partition", choices=(*GROUPS, "composition", "architecture"))
    group.addoption("--ci-backend", choices=("sqlite", "postgresql"))
    group.addoption("--ci-manifest")


class Receipt:
    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.data: dict[str, Any] = {
            "schema": "ci-partition-v1",
            "backend": config.getoption("--ci-backend"),
            "partition": config.getoption("--ci-partition"),
            "reports": [],
            "fixture_timings": [],
        }

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        self.data["original_nodes"] = sorted(item.nodeid for item in items)
        self.data["shared_with_sqlite"] = sorted(
            item.nodeid
            for item in items
            if self.data["backend"] == "postgresql"
            and item.nodeid.split("::", 1)[0] in COMPOSITION_FILES
        )
        selected, excluded = [], []
        for item in items:
            target = partition(item.nodeid)
            if (
                target == self.data["partition"]
                and item.nodeid not in self.data["shared_with_sqlite"]
            ):
                selected.append(item)
            else:
                excluded.append(item)
        self.data["selected_nodes"] = sorted(item.nodeid for item in selected)
        self.data["fixtures"] = {
            item.nodeid: sorted(getattr(item, "fixturenames", [])) for item in selected
        }
        items[:] = selected
        self.config.hook.pytest_deselected(items=excluded)

    @pytest.hookimpl(wrapper=True)
    def pytest_fixture_setup(self, fixturedef: Any, request: pytest.FixtureRequest) -> Any:
        started = time.perf_counter()
        try:
            return (yield)
        finally:
            self.data["fixture_timings"].append(
                {
                    "fixture": fixturedef.argname,
                    "scope": fixturedef.scope,
                    "nodeid": request.node.nodeid,
                    "duration": time.perf_counter() - started,
                }
            )

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.data["reports"].append(
            {
                "nodeid": report.nodeid,
                "when": report.when,
                "outcome": report.outcome,
                "duration": report.duration,
                "wasxfail": getattr(report, "wasxfail", None),
            }
        )

    def pytest_sessionfinish(self, exitstatus: int) -> None:
        self.data["exitstatus"] = int(exitstatus)
        destination = Path(self.config.getoption("--ci-manifest"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")


def pytest_configure(config: pytest.Config) -> None:
    supplied = [
        config.getoption(key) for key in ("--ci-partition", "--ci-backend", "--ci-manifest")
    ]
    if not any(supplied):
        return
    if not all(supplied):
        raise pytest.UsageError("CI partition, backend and manifest must be supplied together")
    config.pluginmanager.register(Receipt(config), "ci-partition-receipt")
