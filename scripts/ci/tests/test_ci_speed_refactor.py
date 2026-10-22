"""Fast feedback never supplies formal merge or native-execution authority."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

CI = Path(__file__).resolve().parents[1]
ROOT = CI.parents[1]
sys.path.insert(0, str(CI))

import test_ci_matrix as matrix  # noqa: E402
from ci_gate import development_gate_errors, gate_errors  # noqa: E402
from classify_changes import STAGE_B_FAST_PATHS, classify_paths  # noqa: E402


class FastScopeTests(unittest.TestCase):
    def test_only_complete_exact_allowlist_is_stage_b_fast(self):
        for path in STAGE_B_FAST_PATHS:
            self.assertEqual(classify_paths([path], development=True).scope, "STAGE_B_FAST")
            self.assertNotEqual(classify_paths([path]).scope, "STAGE_B_FAST")
        self.assertEqual(
            classify_paths(sorted(STAGE_B_FAST_PATHS), development=True).scope, "STAGE_B_FAST"
        )

    def test_unknown_or_high_risk_mixed_change_is_not_stage_b_fast(self):
        safe = next(iter(STAGE_B_FAST_PATHS))
        for bad in (
            "backend/src/cold_storage/modules/layout/infrastructure/global_cp_sat_model.py",
            "backend/src/cold_storage/modules/layout/infrastructure/stage_b_feasibility_first.py",
            "backend/scripts/run_stage_b_guided_fair_pool.py",
            "backend/tests/stage_a_resource_process.py",
            "backend/src/cold_storage/modules/layout/domain/access.py",
            "backend/src/cold_storage/modules/layout/application/sorting_dimension_authority.py",
            "backend/alembic/versions/migration.py",
            "backend/uv.lock",
            "backend/pyproject.toml",
            ".github/workflows/ci-fast.yml",
            "scripts/ci/classify_changes.py",
            "backend/src/unknown.py",
            "../outside.py",
            "/absolute.py",
            "backend//unsafe.py",
        ):
            with self.subTest(path=bad):
                self.assertNotEqual(
                    classify_paths([safe, bad], development=True).scope, "STAGE_B_FAST"
                )
        self.assertEqual(classify_paths([], development=True).scope, "FULL")

    def test_full_cli_overrides_safe_or_document_only_scope(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}
        for path in (*STAGE_B_FAST_PATHS, "docs/only.md"):
            output = subprocess.check_output(
                [sys.executable, str(CI / "classify_changes.py"), "--full", "--paths", path],
                cwd=ROOT,
                text=True,
                env=env,
            )
            self.assertEqual(json.loads(output)["scope"], "FULL")


class AcceptanceBoundaryTests(unittest.TestCase):
    def test_fast_or_partial_cannot_satisfy_formal_gate(self):
        self.assertTrue(gate_errors(matrix.GateTests.needs("STAGE_B_FAST")))
        self.assertTrue(gate_errors(matrix.GateTests.needs("BACKEND"), require_full=True))
        self.assertEqual(gate_errors(matrix.GateTests.needs("FULL"), require_full=True), [])

    def test_fast_job_must_actually_succeed(self):
        for status in ("skipped", "failure", "cancelled", "", None):
            self.assertTrue(
                development_gate_errors(
                    {"fast-checks": {"result": status, "outputs": {"scope": "FULL"}}}
                )
            )
        self.assertTrue(development_gate_errors({}))
        self.assertTrue(development_gate_errors({"fast-checks": {"result": "success"}}))
        for scope in ("STAGE_B_FAST", "FULL"):
            self.assertEqual(
                development_gate_errors(
                    {"fast-checks": {"result": "success", "outputs": {"scope": scope}}}
                ),
                [],
            )

    def test_triggers_names_and_cancellation_domains_are_disjoint(self):
        full = (ROOT / ".github/workflows/ci.yml").read_text()
        fast = (ROOT / ".github/workflows/ci-fast.yml").read_text()
        self.assertIn("push:\n    branches: [main]", full)
        self.assertIn("pull_request:\n    types: [labeled]", full)
        self.assertIn("workflow_dispatch:", full)
        self.assertNotIn("concurrency:", full)
        self.assertIn("types: [opened, synchronize, reopened]", fast)
        self.assertIn("ci-fast-pr-${{ github.event.pull_request.number }}", fast)
        self.assertIn("cancel-in-progress: true", fast)
        for prohibited in ("workflow_dispatch:", "pull_request_target:", "  push:", "ci-gate:\n"):
            # Match full gate name only; fast-ci-gate is intentionally distinct.
            if prohibited == "ci-gate:\n":
                self.assertNotIn("  ci-gate:\n", fast)
            else:
                self.assertNotIn(prohibited, fast)
        self.assertIn("  fast-ci-gate:\n", fast)
        self.assertIn("CI_GATE_KIND: DEVELOPMENT", fast)
        self.assertIn("contents: read", fast)
        self.assertIn("fonts-wqy-zenhei", fast)
        self.assertLess(fast.index("fonts-wqy-zenhei"), fast.index("Stage B, geometry"))
        self.assertNotIn("secrets.", fast)
        self.assertNotIn("continue-on-error", fast)
        jobs = matrix.job_blocks(full)
        self.assertIn("classify_changes.py --full", jobs["classify-changes"])
        self.assertIn('CI_FULL_REQUIRED: "true"', jobs["ci-gate"])
        self.assertIn("if: ${{ always() }}", jobs["ci-gate"])
        self.assertIn("ci_gate.py", jobs["ci-gate"])
        self.assertIn("physical RSS independent worker 1", jobs["backend-sqlite"])
        self.assertIn("physical RSS independent worker 2", jobs["backend-sqlite"])


if __name__ == "__main__":
    unittest.main()
