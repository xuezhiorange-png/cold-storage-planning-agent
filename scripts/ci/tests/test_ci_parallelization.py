"""Exercise fail-closed fan-in and preserve admission-facing CI contracts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from unittest.mock import patch

import test_ci_matrix as matrix
from ci_gate import BACKEND_PARALLEL_JOBS, gate_errors

ROOT = matrix.ROOT


class ParallelWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        cls.jobs = matrix.job_blocks(cls.workflow)
        baseline = subprocess.check_output(
            ["git", "show", "9c13a134b6008c8960996eedf016dc2b4754a013:.github/workflows/ci.yml"],
            cwd=ROOT,
            text=True,
        )
        cls.before = matrix.job_blocks(baseline)

    def test_every_parallel_job_is_required_and_non_success_fails_closed(self):
        for job in BACKEND_PARALLEL_JOBS:
            self.assertIn("      - " + job + "\n", self.jobs["ci-gate"])
            for status in ("failure", "cancelled", "skipped", "", None):
                with self.subTest(job=job, status=status):
                    needs = matrix.GateTests.needs("FULL")
                    needs[job]["result"] = status
                    self.assertTrue(gate_errors(needs, require_full=True))
            needs = matrix.GateTests.needs("FULL")
            del needs[job]
            self.assertTrue(gate_errors(needs, require_full=True))

    def test_actual_aggregate_programs_reject_missing_cancelled_and_skipped(self):
        for job in ("backend-sqlite", "backend-postgresql", "backend-partition-coverage"):
            body = self.jobs[job]
            self.assertIn(
                "if: ${{ always() && needs.classify-changes.outputs.backend == 'true' }}",
                body,
            )
            dependencies = re.findall(r"^      - ([a-z][a-z0-9-]*)$", body, re.M)
            program = body.split("python3 - <<'PY'\n", 1)[1].split("          PY\n", 1)[0]
            program = "\n".join(line[10:] for line in program.splitlines())
            good = {name: {"result": "success"} for name in dependencies}
            with patch.dict(os.environ, {"CI_NEEDS": json.dumps(good)}):
                exec(compile(program, "<aggregate>", "exec"), {})
            for name in dependencies:
                for status in ("failure", "cancelled", "skipped", None, "missing"):
                    needs = {key: dict(value) for key, value in good.items()}
                    if status == "missing":
                        del needs[name]
                    else:
                        needs[name]["result"] = status
                    with (
                        self.subTest(job=job, dependency=name, status=status),
                        patch.dict(os.environ, {"CI_NEEDS": json.dumps(needs)}),
                        self.assertRaises(SystemExit),
                    ):
                        exec(compile(program, "<aggregate>", "exec"), {})

    def test_partition_selectors_receipts_and_fixture_affinity(self):
        for backend in ("sqlite", "postgresql"):
            body = self.jobs[f"backend-{backend}-shards"]
            groups = "general-0, general-1, general-2, general-3"
            if backend == "sqlite":
                groups += ", composition"
            self.assertIn(f"partition: [{groups}]", body)
            self.assertIn("fail-fast: false", body)
            self.assertIn("timeout-minutes: 180", body)
            self.assertIn(f"-p tests.ci_partition --ci-backend {backend}", body)
            self.assertIn("uv run python -m pytest", body)
            self.assertIn("--ci-partition ${{ matrix.partition }}", body)
            self.assertIn(f"--ci-manifest artifacts/ci-{backend}-", body)
            self.assertIn("--durations=30 --durations-min=1", body)
            self.assertIn('-m "not physical_rss_linux"', body)
            self.assertIn("if: ${{ always() }}", body)
            self.assertIn("if-no-files-found: error", body)
            self.assertIn("fetch-depth: 0", body)
            self.assertNotIn("--ignore", body)
            self.assertNotIn("continue-on-error", body)
        self.assertIn(
            '-k "not architecture and not postgresql and not sqlite"',
            self.jobs["backend-postgresql-shards"],
        )
        architecture = self.jobs["backend-architecture"]
        self.assertIn("--ci-partition architecture", architecture)
        self.assertIn("uv run python -m pytest", architecture)
        self.assertIn('-m "not physical_rss_linux"', architecture)
        self.assertNotIn("pytest tests/architecture", architecture)
        coverage = self.jobs["backend-partition-coverage"]
        self.assertIn("verify_partitions.py artifacts/ci-partitions", coverage)
        self.assertIn("pattern: ci-partition-*\n", coverage)
        self.assertNotIn("pattern: ci-partition-*-${{ github.run_attempt }}", coverage)
        self.assertIn("merge-multiple: false", coverage)
        self.assertIn("run-id: ${{ github.run_id }}", coverage)
        self.assertIn("github-token: ${{ github.token }}", coverage)
        self.assertIn("      actions: read", coverage)
        self.assertIn("GH_TOKEN: ${{ github.token }}", coverage)
        self.assertIn("github.event.pull_request.head.sha || github.sha", coverage)
        for flag, variable in (
            ("repository", "GITHUB_REPOSITORY"),
            ("run-id", "GITHUB_RUN_ID"),
            ("attempt", "GITHUB_RUN_ATTEMPT"),
            ("head", "PARTITION_HEAD"),
        ):
            self.assertIn(f'--{flag} "${variable}"', coverage)
        self.assertNotIn("continue-on-error", coverage)
        self.assertNotIn("|| true", coverage)
        for job in ("backend-sqlite", "backend-postgresql"):
            self.assertIn("      - backend-partition-coverage\n", self.jobs[job])

    def test_cross_attempt_fix_does_not_change_other_job_contracts(self):
        baseline = subprocess.check_output(
            ["git", "show", "e9a0c98f7c4b8ad0d279427c98b60195a2f1ddbd:.github/workflows/ci.yml"],
            cwd=ROOT,
            text=True,
        )
        before = matrix.job_blocks(baseline)
        self.assertEqual(set(before), set(self.jobs))
        for name in before.keys() - {"backend-partition-coverage"}:
            with self.subTest(job=name):
                self.assertEqual(before[name], self.jobs[name])

    def test_rss_and_pg_integration_commands_preserved_verbatim(self):
        old_rss = self.before["backend-sqlite"].split("      # Fixed two runs", 1)[1]
        old_rss = old_rss.split("      - name: Backend tests", 1)[0]
        self.assertIn(old_rss, self.jobs["backend-sqlite"])
        old_pg = self.before["backend-postgresql"].split("    services:", 1)[1]
        old_pg = old_pg.split("      - name: Backend tests", 1)[0]
        self.assertIn(old_pg, self.jobs["backend-postgresql-integration"])
        self.assertIn("    services:", self.jobs["backend-postgresql-shards"])
        for name in ("backend-architecture", "backend-lint", "backend-mypy"):
            self.assertNotIn("    services:", self.jobs[name])


if __name__ == "__main__":
    unittest.main()
