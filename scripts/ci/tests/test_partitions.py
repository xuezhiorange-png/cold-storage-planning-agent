"""Coverage receipts must prove execution, not merely successful collection."""

from __future__ import annotations

import copy
import hashlib
import inspect
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify_partitions as verifier  # noqa: E402
from verify_partitions import EXPECTED_JOBS, UPLOAD_STEP, verify  # noqa: E402


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
    def test_original_coverage_predicates_unchanged(self):
        self.assertEqual(
            hashlib.sha256(inspect.getsource(verify).encode()).hexdigest(),
            "6c4937feb059fe6e7504580010639cbbf3e823a41bb61ef222b2802673384382",
        )

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


class CrossAttemptTests(unittest.TestCase):
    """Official API/ZIP/log fixtures, including inherited rerun Job snapshots."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.run = dict(
            id=100,
            head_sha="a" * 40,
            repository=dict(id=1, full_name="owner/repo"),
            head_repository=dict(id=1),
            head_branch="codex/example",
            workflow_id=123,
            path=".github/workflows/ci.yml",
            event="pull_request",
            run_attempt=2,
            conclusion="failure",
        )
        self.attempts = {
            n: dict(self.run, run_attempt=n, run_started_at=f"2026-10-23T00:0{n}:00Z")
            for n in (1, 2)
        }
        self.jobs = {1: [], 2: []}
        self.artifacts = []
        self.archives = {}
        self.logs = {}
        self.rows = {(r["backend"], r["partition"]): r for r in receipts()}
        for index, group in enumerate(sorted(EXPECTED_JOBS), 1):
            first = self.job(group, 1, index)
            self.jobs[1].append(first)
            if group == ("postgresql", "general-2"):
                first["conclusion"] = "failure"
                second = self.job(group, 2, 100 + index)
                self.jobs[2].append(second)
                self.artifact(group, second)
            else:
                self.jobs[2].append(dict(copy.deepcopy(first), id=100 + index, run_attempt=2))
                self.artifact(group, first)

    def job(self, group, attempt, identifier):
        def stamp(second):
            return f"2026-10-23T00:0{attempt}:{second:02d}Z"

        return dict(
            id=identifier,
            name=EXPECTED_JOBS[group],
            run_id=self.run["id"],
            head_sha=self.run["head_sha"],
            run_attempt=attempt,
            status="completed",
            conclusion="success",
            started_at=stamp(10),
            completed_at=stamp(14),
            steps=[
                dict(
                    name=name,
                    status="completed",
                    conclusion="success",
                    started_at=stamp(start),
                    completed_at=stamp(end),
                )
                for name, start, end in (
                    (f"Backend partition ({group[0]})", 10, 11),
                    (UPLOAD_STEP, 12, 13),
                )
            ],
        )

    def artifact(self, group, job):
        backend, partition = group
        name = f"ci-partition-{backend}-{partition}-{job['run_attempt']}"
        identifier = 1000 + job["id"]
        row = dict(
            id=identifier,
            name=name,
            expired=False,
            created_at=job["steps"][-1]["started_at"],
            workflow_run=dict(
                id=self.run["id"],
                head_sha=self.run["head_sha"],
                repository_id=1,
                head_repository_id=1,
                head_branch=self.run["head_branch"],
            ),
        )
        self.artifacts.append(row)
        self.save_receipt(row, job, self.rows[group])
        return row

    def save_receipt(self, artifact, job, receipt):
        filename = f"ci-{receipt['backend']}-{receipt['partition']}.json"
        payload = json.dumps(receipt, sort_keys=True).encode()
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr(filename, payload)
        archive = buffer.getvalue()
        digest = hashlib.sha256(archive).hexdigest()
        artifact["digest"] = "sha256:" + digest
        self.archives[artifact["id"]] = archive
        directory = self.directory / artifact["name"]
        directory.mkdir(exist_ok=True)
        (directory / filename).write_bytes(payload)
        timestamp = job["steps"][-1]["started_at"].replace("Z", ".1234567Z")
        self.logs[job["id"]] = (
            f"{timestamp} SHA256 digest of uploaded artifact zip is {digest}\n"
            f"{timestamp} Artifact {artifact['name']}.zip successfully finalized. "
            f"Artifact ID {artifact['id']}\n"
        )

    def selection(self):
        return verifier.select_sources(
            self.run,
            self.attempts,
            self.jobs,
            self.artifacts,
            repository="owner/repo",
            run_id=100,
            head="a" * 40,
            attempt=2,
        )

    def verified(self):
        return verifier.verify_downloads(
            self.directory, self.selection(), self.archives.__getitem__, self.logs.__getitem__
        )

    def test_nine_original_successes_and_one_rerun_with_failed_run_preserved(self):
        result = self.verified()
        self.assertEqual(len(result["sources"]), 10)
        self.assertEqual(sum(r["producer_attempt"] == 1 for r in result["sources"]), 9)
        self.assertEqual(sum(r["producer_attempt"] == 2 for r in result["sources"]), 1)
        self.assertEqual(result["original_run_conclusion"], "failure")
        self.assertFalse(result["formal_ci_success_claimed"])
        ordered = sorted(receipts(), key=lambda r: (r["backend"], r["partition"]))
        self.assertEqual(result["coverage"], verify(ordered))

    def test_initial_attempt_still_requires_all_ten_original_producers(self):
        first = next(
            j for j in self.jobs[1] if j["name"] == "backend-postgresql-shards (general-2)"
        )
        first["conclusion"] = "success"
        self.artifact(("postgresql", "general-2"), first)
        run = dict(self.run, run_attempt=1)
        selected = verifier.select_sources(
            run,
            {1: self.attempts[1]},
            {1: self.jobs[1]},
            [a for a in self.artifacts if a["name"].endswith("-1")],
            repository="owner/repo",
            run_id=100,
            head="a" * 40,
            attempt=1,
        )["selected"]
        self.assertEqual(len(selected), 10)
        self.assertEqual({r["attempt"] for r in selected}, {1})

    def test_third_attempt_can_inherit_proven_sources_from_both_earlier_attempts(self):
        self.run["run_attempt"] = 3
        self.attempts[3] = dict(self.run, run_started_at="2026-10-23T00:03:00Z")
        self.jobs[3] = [
            dict(copy.deepcopy(j), id=j["id"] + 1000, run_attempt=3) for j in self.jobs[2]
        ]
        selection = verifier.select_sources(
            self.run,
            self.attempts,
            self.jobs,
            self.artifacts,
            repository="owner/repo",
            run_id=100,
            head="a" * 40,
            attempt=3,
        )
        result = verifier.verify_downloads(
            self.directory, selection, self.archives.__getitem__, self.logs.__getitem__
        )
        self.assertEqual(sum(r["producer_attempt"] == 1 for r in result["sources"]), 9)
        self.assertEqual(sum(r["producer_attempt"] == 2 for r in result["sources"]), 1)

    def test_every_missing_partition_and_duplicate_artifact_rejected(self):
        before = copy.deepcopy(self.artifacts)
        for index in range(10):
            self.artifacts = before[:index] + before[index + 1 :]
            with self.subTest(missing=index), self.assertRaises(ValueError):
                self.selection()
        self.artifacts = before + [copy.deepcopy(before[0])]
        with self.assertRaises(ValueError):
            self.selection()

    def test_foreign_run_head_repository_branch_and_attempt_rejected(self):
        for field, value in (
            ("id", 101),
            ("head_sha", "b" * 40),
            ("repository_id", 2),
            ("head_repository_id", 2),
            ("head_branch", "codex/foreign"),
        ):
            saved = copy.deepcopy(self.artifacts)
            self.artifacts[0]["workflow_run"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.selection()
            self.artifacts = saved
        self.artifacts[0]["name"] = self.artifacts[0]["name"].rsplit("-", 1)[0] + "-3"
        with self.assertRaises(ValueError):
            self.selection()

    def test_workflow_and_attempt_metadata_bound(self):
        for field, value in (
            ("id", 101),
            ("head_sha", "b" * 40),
            ("workflow_id", 456),
            ("path", ".github/workflows/ci-fast.yml"),
            ("event", "workflow_dispatch"),
            ("run_attempt", 2),
        ):
            saved = copy.deepcopy(self.attempts)
            self.attempts[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.selection()
            self.attempts = saved

    def test_unknown_inherited_job_and_incomplete_snapshots_rejected(self):
        self.jobs[2][0]["steps"][0]["completed_at"] = "2026-10-23T00:01:12Z"
        with self.assertRaisesRegex(ValueError, "unproven inherited"):
            self.selection()
        self.jobs[2].pop()
        with self.assertRaises(ValueError):
            self.selection()

    def test_duplicate_foreign_unfinished_jobs_rejected(self):
        saved = copy.deepcopy(self.jobs)
        for field, value in (
            ("run_id", 101),
            ("head_sha", "b" * 40),
            ("run_attempt", 1),
            ("status", "in_progress"),
        ):
            self.jobs[2][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.selection()
            self.jobs = copy.deepcopy(saved)
        self.jobs[2].append(copy.deepcopy(self.jobs[2][0]))
        with self.assertRaises(ValueError):
            self.selection()

    def test_latest_failed_or_missing_artifact_never_uses_older_success(self):
        group = ("sqlite", "general-0")
        later = self.job(group, 2, 999)
        self.jobs[2] = [j for j in self.jobs[2] if j["name"] != later["name"]] + [later]
        with self.assertRaisesRegex(ValueError, "no stale fallback"):
            self.selection()
        later["conclusion"] = "failure"
        with self.assertRaisesRegex(ValueError, "older success cannot substitute"):
            self.selection()

    def test_latest_proven_success_selected_deterministically_not_overwritten(self):
        group = ("sqlite", "general-0")
        later = self.job(group, 2, 999)
        self.jobs[2] = [j for j in self.jobs[2] if j["name"] != later["name"]] + [later]
        self.artifact(group, later)
        first = self.verified()
        self.artifacts.reverse()
        self.jobs[1].reverse()
        self.jobs[2].reverse()
        self.assertEqual(first, self.verified())
        chosen = next(
            r
            for r in first["sources"]
            if r["partition"] == "general-0" and r["backend"] == "sqlite"
        )
        self.assertEqual(chosen["producer_job_id"], 999)
        self.assertEqual(len(first["superseded_artifact_ids"]), 1)

    def test_expired_unknown_or_relabelled_inherited_artifact_rejected(self):
        saved = copy.deepcopy(self.artifacts)
        for field, value in (
            ("expired", True),
            ("name", "ci-partition-sqlite-unknown-1"),
            ("name", "ci-partition-sqlite-general-0-2"),
            ("digest", None),
            ("created_at", "2026-10-23T00:00:00Z"),
        ):
            self.artifacts[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises((ValueError, TypeError)):
                self.selection()
            self.artifacts = copy.deepcopy(saved)

    def test_unsuccessful_or_missing_upload_and_test_step_rejected(self):
        later = next(
            j for j in self.jobs[2] if j["name"] == "backend-postgresql-shards (general-2)"
        )
        saved = copy.deepcopy(later["steps"])
        for index in (0, 1):
            for status in ("failure", "skipped", "cancelled", None):
                later["steps"][index]["conclusion"] = status
                with self.subTest(index=index, status=status), self.assertRaises(ValueError):
                    self.selection()
                later["steps"] = copy.deepcopy(saved)
        later["steps"].pop()
        with self.assertRaises(ValueError):
            self.selection()

    def test_log_upload_id_digest_interval_and_duplicate_lines_bound(self):
        selected = self.selection()["selected"][0]
        job_id = selected["job"]["id"]
        saved = self.logs[job_id]
        for log in (
            "",
            saved.replace(str(selected["artifact"]["id"]), "99999"),
            saved.replace(selected["artifact"]["digest"][7:], "0" * 64),
            saved.replace("00:01:12", "00:00:12"),
            saved + saved,
        ):
            self.logs[job_id] = log
            with self.subTest(log=log), self.assertRaises(ValueError):
                self.verified()
        self.logs[job_id] = saved

    def test_zip_digest_and_local_receipt_cannot_be_forged(self):
        selected = self.selection()["selected"][0]
        identifier = selected["artifact"]["id"]
        saved = self.archives[identifier]
        self.archives[identifier] = saved + b"tampered"
        with self.assertRaisesRegex(ValueError, "ZIP digest"):
            self.verified()
        self.archives[identifier] = saved
        path = next((self.directory / selected["artifact"]["name"]).iterdir())
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "differs from source"):
            self.verified()

    def test_actual_failed_or_missing_reports_rejected_even_with_valid_provenance(self):
        selected = self.selection()["selected"][0]
        group = selected["backend"], selected["partition"]
        for reports in ([], [dict(self.rows[group]["reports"][0], outcome="failed")]):
            row = dict(copy.deepcopy(self.rows[group]), reports=reports)
            self.save_receipt(selected["artifact"], selected["job"], row)
            with self.subTest(reports=reports), self.assertRaises(ValueError):
                self.verified()

    def test_merged_extra_files_and_symlink_directories_rejected(self):
        extra = self.directory / "ci-merged.json"
        extra.write_text("{}")
        with self.assertRaises(ValueError):
            self.verified()
        extra.unlink()
        selected = self.selection()["selected"][0]
        extra = self.directory / selected["artifact"]["name"] / "duplicate.json"
        extra.write_text("{}")
        with self.assertRaises(ValueError):
            self.verified()
        extra.unlink()
        directory = extra.parent
        moved = directory.with_name("redirected")
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.verified()

    def test_paginated_api_rejects_missing_and_duplicate_pages(self):
        for pages in (
            [dict(total_count=2, jobs=[dict(id=1)])],
            [dict(total_count=2, jobs=[dict(id=1), dict(id=1)])],
            [dict(total_count=2, jobs=[dict(id=1)]), dict(total_count=3, jobs=[dict(id=2)])],
        ):
            with (
                patch.object(verifier, "github_bytes", return_value=json.dumps(pages).encode()),
                self.subTest(pages=pages),
                self.assertRaises(ValueError),
            ):
                verifier.github_collection("owner/repo", "runs/100/jobs", "jobs")
        pages = [dict(total_count=2, jobs=[dict(id=1)]), dict(total_count=2, jobs=[dict(id=2)])]
        with patch.object(verifier, "github_bytes", return_value=json.dumps(pages).encode()) as api:
            self.assertEqual(
                len(verifier.github_collection("owner/repo", "runs/100/jobs", "jobs")), 2
            )
            self.assertTrue(api.call_args.kwargs["paginate"])

    def test_cli_requires_live_source_and_rechecks_attempt_after_readback(self):
        after = dict(self.run, run_attempt=3)
        replies = [
            json.dumps(r).encode() for r in (self.run, self.attempts[1], self.attempts[2], after)
        ]
        collections = [self.jobs[1], self.jobs[2], self.artifacts]
        argv = [
            "verify_partitions.py",
            str(self.directory),
            "--repository",
            "owner/repo",
            "--run-id",
            "100",
            "--attempt",
            "2",
            "--head",
            "a" * 40,
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(verifier, "github_bytes", side_effect=replies),
            patch.object(verifier, "github_collection", side_effect=collections),
            patch.object(verifier, "verify_downloads", return_value={}),
            self.assertRaisesRegex(ValueError, "identity changed"),
        ):
            verifier.main()


if __name__ == "__main__":
    unittest.main()
