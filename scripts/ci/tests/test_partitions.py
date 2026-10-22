"""Coverage receipts must prove execution, not merely successful collection."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_partitions import verify  # noqa: E402


def receipts():
    rows = []
    composition = "tests/unit/test_v222_p1a_composition_exact_placement.py::test_real"
    for backend in ("sqlite", "postgresql"):
        groups = [f"general-{i}" for i in range(4)]
        if backend == "sqlite":
            groups += ["composition", "architecture"]
        nodes = {g: [f"tests/{g}.py::test_case"] for g in groups}
        if backend == "sqlite":
            nodes["composition"] = [composition]
        original = [n for group in nodes.values() for n in group]
        if backend == "postgresql":
            original.append(composition)
        for group in groups:
            rows.append(
                {
                    "schema": "ci-partition-v1",
                    "backend": backend,
                    "partition": group,
                    "original_nodes": original,
                    "selected_nodes": nodes[group],
                    "shared_with_sqlite": [composition] if backend == "postgresql" else [],
                    "exitstatus": 0,
                    "reports": [
                        {"nodeid": n, "when": "call", "outcome": "passed", "duration": 1}
                        for n in nodes[group]
                    ],
                }
            )
    return rows


class PartitionCoverageTests(unittest.TestCase):
    def test_complete_execution(self):
        result = verify(receipts())
        self.assertEqual(result["sqlite"]["executed_count"], 6)
        self.assertEqual(result["postgresql"]["shared_database_independent_count"], 1)

    def test_fail_closed(self):
        for kind in ("missing", "duplicate", "failed", "unexecuted", "collection", "exclusion"):
            with self.subTest(kind=kind):
                rows = copy.deepcopy(receipts())
                if kind == "missing":
                    rows.pop()
                elif kind == "duplicate":
                    rows.append(rows[0])
                elif kind == "failed":
                    rows[0]["exitstatus"] = 1
                elif kind == "unexecuted":
                    rows[0]["reports"] = []
                elif kind == "collection":
                    rows[0]["original_nodes"] = []
                else:
                    rows[-1]["shared_with_sqlite"] = ["tests/not-approved.py::test_secret"]
                with self.assertRaises(ValueError):
                    verify(rows)

    def test_failed_report_cannot_be_hidden_by_success_exit(self):
        rows = receipts()
        rows[0]["reports"][0]["outcome"] = "failed"
        with self.assertRaises(ValueError):
            verify(rows)

    def test_existing_setup_skip_is_visible(self):
        rows = receipts()
        rows[0]["reports"][0].update(when="setup", outcome="skipped")
        result = verify(rows)
        self.assertEqual(len(result["sqlite"]["skipped_reports"]), 1)

    def test_delegated_composition_requires_real_pass(self):
        for mutation in (
            {"when": "setup", "outcome": "skipped"},
            {"when": "call", "outcome": "skipped"},
            {"when": "call", "outcome": "passed", "wasxfail": "expected"},
            {"when": "call", "outcome": "passed", "wasxfail": ""},
        ):
            with self.subTest(mutation=mutation):
                rows = receipts()
                row = next(r for r in rows if r["partition"] == "composition")
                row["reports"][0].update(mutation)
                with self.assertRaises(ValueError):
                    verify(rows)


if __name__ == "__main__":
    unittest.main()
