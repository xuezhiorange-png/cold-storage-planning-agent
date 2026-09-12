"""Local stdlib tests for CI event ranges, safety priorities and final status."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CI_DIR = Path(__file__).resolve().parents[1]
ROOT = CI_DIR.parents[1]
sys.path.insert(0, str(CI_DIR))

from ci_gate import MANUAL_JOBS, gate_errors  # noqa: E402
from classify_changes import (  # noqa: E402
    REGULAR_JOBS,
    SCOPE_JOBS,
    Plan,
    classify_event,
    classify_paths,
)

BASE = "3ffb3790f85a990283ce972733c3f43b44d1e899"
PR269_PATHS = [
    "backend/tests/architecture/test_v22_p0_site_constrained_layout_contract.py",
    "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
    "docs/tasks/V2_2-P0-site-constrained-factory-layout-contract.md",
    "docs/tasks/V2_2-version-plan.md",
]


class PathTests(unittest.TestCase):
    def test_classification_matrix(self) -> None:
        cases = [
            (["docs/foo.md"], "DOCS_ARCHITECTURE_ONLY"),
            (["backend/tests/architecture/test_x.py"], "DOCS_ARCHITECTURE_ONLY"),
            (["docs/foo.md", "backend/tests/architecture/test_x.py"], "DOCS_ARCHITECTURE_ONLY"),
            (["backend/src/foo.py"], "BACKEND"),
            (["backend/tests/unit/test_x.py"], "BACKEND"),
            (["frontend/src/x.ts"], "FRONTEND"),
            (["backend/src/x.py", "frontend/src/y.ts"], "BACKEND_FRONTEND"),
            (["backend/src/x.py", "docs/foo.md"], "BACKEND"),
            (["frontend/src/x.ts", "docs/foo.md"], "FULL"),
            (["backend/alembic/versions/x.py"], "FULL"),
            ([".github/workflows/ci.yml"], "FULL"),
            (["docker-compose.production.yml"], "FULL"),
            (["unknown/new-root-file.xyz"], "FULL"),
            ([], "FULL"),
        ]
        for paths, expected in cases:
            with self.subTest(paths=paths):
                self.assertEqual(classify_paths(paths).scope, expected)

    def test_infra_and_dependencies_override_lightweight_paths(self) -> None:
        for path in (
            "Dockerfile",
            "backend/Dockerfile",
            "frontend/Dockerfile.prod",
            "deployment/prod.yml",
            "backend/pyproject.toml",
            "backend/uv.lock",
            "backend/requirements.txt",
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/pnpm-lock.yaml",
            "frontend/yarn.lock",
            "scripts/ci/classify_changes.py",
            "scripts/ci/tests/test_ci_matrix.py",
            "backend/alembic.ini",
            "backend/src/cold_storage/bootstrap/app.py",
            "backend/src/cold_storage/modules/projects/infrastructure/database.py",
            "backend/src/cold_storage/release/runner.py",
        ):
            with self.subTest(path=path):
                plan = classify_paths(["docs/foo.md", path])
                self.assertEqual(plan.scope, "FULL")
                self.assertEqual(plan.reason, "DATABASE_INFRA_FULL")

    def test_unknown_and_noncanonical_paths_cannot_downgrade(self) -> None:
        for path in (
            "",
            "../docs/foo.md",
            "/docs/foo.md",
            "docs/../backend/x.py",
            "docs//foo.md",
            "docs\\foo.md",
            "Makefile",
            ".env.example",
            "src/x.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(classify_paths([path]).scope, "FULL")

    def test_pr269_simulation_has_no_heavy_job(self) -> None:
        plan = classify_paths(PR269_PATHS)
        self.assertEqual(plan.scope, "DOCS_ARCHITECTURE_ONLY")
        self.assertEqual(SCOPE_JOBS[plan.scope], {"lightweight"})
        for flag in ("backend", "frontend", "infra", "release", "recovery"):
            self.assertEqual(plan.outputs()[flag], "false")

    def test_current_pr_self_change_forces_full(self) -> None:
        self.assertEqual(classify_paths([".github/workflows/ci.yml", *PR269_PATHS]).scope, "FULL")


class EventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ci-classifier-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "CI classifier test")
        self.git("config", "user.email", "ci-test@example.invalid")
        self.write("backend/src/original.py", "original\n")
        self.base = self.commit()
        self.write("docs/new.md", "docs\n")
        self.head = self.commit()
        self.write("frontend/src/synthetic.ts", "merge-only\n")
        self.synthetic = self.commit()

    def git(self, *args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def write(self, name: str, text: str) -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self) -> str:
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def test_pr_uses_base_and_head_not_synthetic_merge(self) -> None:
        event = {"pull_request": {"base": {"sha": self.base}, "head": {"sha": self.head}}}
        plan = classify_event("pull_request", event, self.synthetic, self.repo)
        self.assertEqual(plan.scope, "DOCS_ARCHITECTURE_ONLY")
        self.assertEqual((plan.base, plan.head), (self.base, self.head))

    def test_push_uses_before_and_github_sha(self) -> None:
        plan = classify_event("push", {"before": self.head}, self.synthetic, self.repo)
        self.assertEqual(plan.scope, "FRONTEND")
        self.assertEqual((plan.base, plan.head), (self.head, self.synthetic))

    def test_invalid_missing_empty_or_unavailable_diff_is_full(self) -> None:
        events = [
            None,
            {},
            {"before": "bad"},
            {"before": "0" * 40},
            {"before": "a" * 40},
            {"before": self.head, "created": True},
            {"before": self.head, "deleted": True},
            {"before": self.synthetic},
            {"before": self.base, "after": self.head},
        ]
        for event in events:
            with self.subTest(event=event):
                self.assertEqual(
                    classify_event("push", event, self.synthetic, self.repo).scope, "FULL"
                )
        for event in (None, {}, {"pull_request": {}}, {"pull_request": []}):
            self.assertEqual(
                classify_event("pull_request", event, self.head, self.repo).scope, "FULL"
            )
        self.assertEqual(
            classify_event("push", {"before": self.base}, "bad", self.repo).scope, "FULL"
        )

    def test_manual_and_unknown_events_default_full(self) -> None:
        for name in ("workflow_dispatch", "", "pull_request_target"):
            self.assertEqual(classify_event(name, None, self.head, self.repo).scope, "FULL")

    def test_rename_from_backend_to_docs_and_deletion_keep_backend_gate(self) -> None:
        self.git("mv", "backend/src/original.py", "docs/moved.py")
        renamed = self.commit()
        plan = classify_event("push", {"before": self.synthetic}, renamed, self.repo)
        self.assertEqual(plan.scope, "BACKEND")

    def test_nul_paths_preserve_newlines_in_filenames(self) -> None:
        self.write("docs/line\nbreak.md", "content")
        plan = classify_event("push", {"before": self.synthetic}, self.commit(), self.repo)
        self.assertEqual(plan.scope, "DOCS_ARCHITECTURE_ONLY")

    def test_tag_object_is_not_a_commit_sha(self) -> None:
        self.git("tag", "-a", "fixture", "-m", "fixture")
        tag_object = self.git("rev-parse", "fixture")
        self.assertEqual(
            classify_event("push", {"before": tag_object}, self.head, self.repo).scope, "FULL"
        )


class GateTests(unittest.TestCase):
    @staticmethod
    def needs(scope: str) -> dict:
        return {
            "classify-changes": {"result": "success", "outputs": Plan(scope, "test").outputs()},
            **{
                job: {"result": "success" if job in SCOPE_JOBS[scope] else "skipped"}
                for job in (*REGULAR_JOBS, *MANUAL_JOBS)
            },
        }

    def test_each_scope_allows_only_expected_skips(self) -> None:
        for scope in SCOPE_JOBS:
            self.assertEqual(gate_errors(self.needs(scope)), [])

    def test_every_required_job_failure_cancel_or_skip_fails_gate(self) -> None:
        for scope, required in SCOPE_JOBS.items():
            for job in required:
                for status in ("failure", "cancelled", "skipped", "", None):
                    with self.subTest(scope=scope, job=job, status=status):
                        needs = self.needs(scope)
                        needs[job]["result"] = status
                        self.assertTrue(gate_errors(needs))

    def test_classifier_failure_and_missing_output_fail_closed(self) -> None:
        self.assertTrue(gate_errors({}))
        for status in ("failure", "cancelled", "skipped"):
            needs = self.needs("FULL")
            needs["classify-changes"]["result"] = status
            self.assertTrue(gate_errors(needs))
        needs = self.needs("FULL")
        del needs["classify-changes"]["outputs"]["backend"]
        self.assertTrue(gate_errors(needs))
        needs["classify-changes"]["outputs"]["scope"] = "invented"
        self.assertTrue(gate_errors(needs))

    def test_executed_manual_failure_is_not_hidden(self) -> None:
        for job in MANUAL_JOBS:
            needs = self.needs("FULL")
            needs[job]["result"] = "failure"
            self.assertTrue(gate_errors(needs))
            needs[job]["result"] = "success"
            self.assertFalse(gate_errors(needs))


def job_blocks(text: str) -> dict[str, str]:
    starts = list(re.finditer(r"^  ([a-z][a-z0-9-]*):\n", text.split("\njobs:\n", 1)[1], re.M))
    jobs = text.split("\njobs:\n", 1)[1]
    return {
        match[1]: jobs[match.end() : starts[i + 1].start() if i + 1 < len(starts) else len(jobs)]
        for i, match in enumerate(starts)
    }


class WorkflowTests(unittest.TestCase):
    def test_manual_authorization_inputs_and_job_bodies_are_unchanged(self) -> None:
        old = subprocess.check_output(
            ["git", "show", f"{BASE}:.github/workflows/ci.yml"], cwd=ROOT, text=True
        )
        new = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertEqual(old.split("\njobs:\n")[0], new.split("\njobs:\n")[0])
        before, after = job_blocks(old), job_blocks(new)
        for name in MANUAL_JOBS:
            with self.subTest(job=name):
                self.assertEqual(before[name], after[name])

    def test_final_gate_depends_on_every_job_and_runs_always(self) -> None:
        jobs = job_blocks((ROOT / ".github/workflows/ci.yml").read_text())
        needs = set(re.findall(r"^      - ([a-z][a-z0-9-]*)$", jobs["ci-gate"], re.M))
        self.assertEqual(needs, set(jobs) - {"ci-gate"})
        self.assertIn("if: ${{ always() }}", jobs["ci-gate"])
        self.assertIn("CI_NEEDS: ${{ toJSON(needs) }}", jobs["ci-gate"])
        self.assertIn("fetch-depth: 0", jobs["classify-changes"])
        for name, flag in (
            ("backend-sqlite", "backend"),
            ("backend-postgresql", "backend"),
            ("frontend", "frontend"),
            ("compose-config", "infra"),
            ("release-evidence", "release"),
            ("recovery-foundation", "recovery"),
            ("lightweight", "lightweight"),
        ):
            self.assertIn("needs: classify-changes", jobs[name])
            self.assertIn(
                "if: ${{ needs.classify-changes.outputs." + flag + " == 'true' }}", jobs[name]
            )

    def test_lightweight_has_architecture_but_no_runtime_or_services(self) -> None:
        light = job_blocks((ROOT / ".github/workflows/ci.yml").read_text())["lightweight"]
        self.assertIn("pytest tests/architecture", light)
        self.assertIn("ruff format --check", light)
        for forbidden in ("services:", "docker", "alembic", "npm", "migrate"):
            self.assertNotIn(forbidden, light)

    def test_cli_emits_parseable_plan(self) -> None:
        output = subprocess.check_output(
            [sys.executable, str(CI_DIR / "classify_changes.py"), "--paths", *PR269_PATHS],
            cwd=ROOT,
            text=True,
            env={
                key: value
                for key, value in os.environ.items()
                if key not in {"GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"}
            },
        )
        self.assertEqual(json.loads(output)["scope"], "DOCS_ARCHITECTURE_ONLY")


if __name__ == "__main__":
    unittest.main()
