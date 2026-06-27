"""Tests for run identity validation — eighth re-review additions.

These tests verify items not already covered by the seventh-round test suite:
- P0-1: Structured RunIdentityValidationIssue (no message-text parsing for field)
- P0-2: Every invalid create_run() asserts exact class/code/field AND zero filesystem side effects
- P0-3: Public-boundary tamper tests for transition_status/write_summary/read_verified_summary
- P0-4: Direct summary decoder identity tests (_dict_to_summary_strict)
- P0-5: No broad exception class assertions at _dict_to_summary_strict boundary
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cold_storage.evaluation.errors import (
    RunIdentityValidationIssue,
    RunInputInvalidError,
    RunStateError,
    RunSummaryInvalidError,
)
from cold_storage.evaluation.models import EvaluationRunSummary, RunStatus, ScenarioRunSummary
from cold_storage.evaluation.run_directory import (
    EvaluationRunContext,
    EvaluationRunDirectory,
    RunIdentityValues,
    _dict_to_summary_strict,
    validate_run_identity_values,
)

# ── helpers ─────────────────────────────────────────────────────────


def _run_dir(tmp_path: Path) -> EvaluationRunDirectory:
    return EvaluationRunDirectory(str(tmp_path / "runs"))


def make_summary(
    context: EvaluationRunContext,
    status: RunStatus = RunStatus.PASSED,
    passed: bool = True,
) -> EvaluationRunSummary:
    scenario_results = ()
    if status == RunStatus.PASSED:
        scenario_results = tuple(
            ScenarioRunSummary(
                scenario_id=sid,
                passed=True,
                checks_total=5,
                checks_passed=5,
                checks_failed=0,
            )
            for sid in context.scenario_ids
        )
    return EvaluationRunSummary(
        run_id=context.run_id,
        suite_id=context.suite_id,
        suite_revision=context.suite_revision,
        manifest_sha256=context.manifest_sha256,
        scenario_ids=context.scenario_ids,
        status=status,
        completed_at="2026-06-27T12:00:00+00:00",
        code_commit_sha=context.code_commit_sha,
        passed=passed,
        scenario_results=scenario_results,
    )


# ── P0-1: Structured RunIdentityValidationIssue (no message parsing) ─


class TestRunIdentityValidationIssue:
    """RunIdentityValidationIssue must carry field and message separately."""

    def test_field_is_not_parsed_from_message(self) -> None:
        """field must be stored directly, not extracted from message text."""
        issue = RunIdentityValidationIssue(field="suite_revision", message="must be >= 1")
        assert issue.field == "suite_revision"
        assert issue.field not in issue.message  # field != substring of message
        assert issue.message == "must be >= 1"

    def test_validate_identity_uses_structured_issue(self) -> None:
        """validate_run_identity_values must raise RunIdentityValidationIssue with exact field."""
        with pytest.raises(RunIdentityValidationIssue) as exc_info:
            validate_run_identity_values(
                RunIdentityValues(
                    suite_id="",
                    suite_revision=1,
                    manifest_sha256="a" * 64,
                    scenario_ids=("s1",),
                    database_backend=None,
                    code_commit_sha=None,
                )
            )
        assert exc_info.value.field == "suite_id"
        assert exc_info.value.message


# ── P0-2: create_run zero-side-effect parametrized tests ─────────────


def _walk_tree(base: Path) -> set[tuple[str, bool, int | None]]:
    """Return (rel_path, is_dir, size_bytes) for every entry under *base*."""
    if not base.exists():
        return set()
    result: set[tuple[str, bool, int | None]] = set()
    for p in base.rglob("*"):
        rel = str(p.relative_to(base))
        result.add((rel, p.is_dir(), p.stat().st_size if p.is_file() else None))
    return result


_GOOD_KWARGS = {
    "suite_id": "suite-1",
    "suite_revision": 1,
    "manifest_sha256": "a" * 64,
    "scenario_ids": ("s1",),
}


@pytest.mark.parametrize(
    ("expected_field", "bad_kwargs"),
    [
        ("suite_id", {"suite_id": ""}),
        ("suite_id", {"suite_id": " "}),
        ("suite_revision", {"suite_revision": 0}),
        ("suite_revision", {"suite_revision": -1}),
        ("suite_revision", {"suite_revision": True}),
        ("manifest_sha256", {"manifest_sha256": "short"}),
        ("scenario_ids[0]", {"scenario_ids": ("",)}),
        ("scenario_ids[0]", {"scenario_ids": (" ",)}),
        ("scenario_ids[1]", {"scenario_ids": ("s1", "s1")}),
        ("database_backend", {"database_backend": "mongo"}),
        ("code_commit_sha", {"code_commit_sha": ""}),
        ("code_commit_sha", {"code_commit_sha": " "}),
    ],
)
class TestCreateRunZeroSideEffect:
    """Every invalid create_run must:
    1. Raise RunInputInvalidError with exact code/field
    2. Leave the filesystem completely unchanged
    """

    def test_invalid_input_rejected_with_zero_side_effects(
        self,
        tmp_path: Path,
        expected_field: str,
        bad_kwargs: dict,
    ) -> None:
        rd = _run_dir(tmp_path)
        base_dir = rd._base  # type: ignore[attr-defined]
        kwargs = {**_GOOD_KWARGS, **bad_kwargs}

        before = _walk_tree(base_dir)

        with pytest.raises(RunInputInvalidError) as exc_info:
            rd.create_run(**kwargs)

        after = _walk_tree(base_dir)

        assert exc_info.value.code == "EVAL_RUN_INPUT_INVALID"
        assert exc_info.value.field == expected_field
        assert after == before, (
            f"Filesystem changed despite validation failure for field={expected_field}: "
            f"before={before}, after={after}"
        )


# ── P0-3: Public-boundary tamper tests ──────────────────────────────


class TestTransitionIdentityTamper:
    """transition_status must reject tampered persisted run.json identity."""

    def _setup_tampered(
        self, tmp_path: Path, *, tamper_field: str, tamper_value: object | None
    ) -> tuple[EvaluationRunDirectory, EvaluationRunContext]:
        rd = _run_dir(tmp_path)
        ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
        ctx = rd.transition_status(ctx, RunStatus.RUNNING)
        run_dir = rd.run_dir(ctx.run_id)
        raw = json.loads((run_dir / "run.json").read_text("utf-8"))
        if tamper_value is None:
            del raw[tamper_field]
        else:
            raw[tamper_field] = tamper_value
        (run_dir / "run.json").write_text(json.dumps(raw, indent=2), "utf-8")
        return rd, ctx

    def test_transition_rejects_whitespace_suite_id(self, tmp_path: Path) -> None:
        rd, ctx = self._setup_tampered(tmp_path, tamper_field="suite_id", tamper_value=" ")
        with pytest.raises(RunStateError) as exc_info:
            rd.transition_status(ctx, RunStatus.PASSED)
        assert exc_info.value.code == "EVAL_RUN_STATE_INVALID"
        assert exc_info.value.field == "suite_id"

    def test_transition_rejects_whitespace_scenario_id(self, tmp_path: Path) -> None:
        rd, ctx = self._setup_tampered(tmp_path, tamper_field="scenario_ids", tamper_value=[" "])
        with pytest.raises(RunStateError) as exc_info:
            rd.transition_status(ctx, RunStatus.PASSED)
        assert exc_info.value.code == "EVAL_RUN_STATE_INVALID"
        assert exc_info.value.field == "scenario_ids[0]"

    def test_transition_rejects_duplicate_scenario_ids(self, tmp_path: Path) -> None:
        rd, ctx = self._setup_tampered(
            tmp_path, tamper_field="scenario_ids", tamper_value=["s1", "s1"]
        )
        with pytest.raises(RunStateError) as exc_info:
            rd.transition_status(ctx, RunStatus.PASSED)
        assert exc_info.value.code == "EVAL_RUN_STATE_INVALID"
        assert exc_info.value.field == "scenario_ids[1]"

    def test_transition_rejects_invalid_revision(self, tmp_path: Path) -> None:
        rd, ctx = self._setup_tampered(tmp_path, tamper_field="suite_revision", tamper_value=0)
        with pytest.raises(RunStateError) as exc_info:
            rd.transition_status(ctx, RunStatus.PASSED)
        assert exc_info.value.code == "EVAL_RUN_STATE_INVALID"
        assert exc_info.value.field == "suite_revision"

    def test_transition_rejects_whitespace_code_commit_sha(self, tmp_path: Path) -> None:
        rd, ctx = self._setup_tampered(tmp_path, tamper_field="code_commit_sha", tamper_value=" ")
        with pytest.raises(RunStateError) as exc_info:
            rd.transition_status(ctx, RunStatus.PASSED)
        assert exc_info.value.code == "EVAL_RUN_STATE_INVALID"
        assert exc_info.value.field == "code_commit_sha"

    def test_transition_rejects_invalid_database_backend(self, tmp_path: Path) -> None:
        rd, ctx = self._setup_tampered(
            tmp_path, tamper_field="database_backend", tamper_value="mongo"
        )
        with pytest.raises(RunStateError) as exc_info:
            rd.transition_status(ctx, RunStatus.PASSED)
        assert exc_info.value.code == "EVAL_RUN_STATE_INVALID"
        assert exc_info.value.field == "database_backend"


class TestReadVerifiedSummaryTamper:
    """read_verified_summary must reject tampered identity in run.json and summary.json."""

    def _write_baseline(self, rd: EvaluationRunDirectory, ctx: EvaluationRunContext) -> Path:
        ctx = rd.transition_status(ctx, RunStatus.RUNNING)
        ctx = rd.transition_status(ctx, RunStatus.FAILED)
        summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
        rd.write_summary(ctx, summary)
        return rd.run_dir(ctx.run_id)

    def test_run_json_tampered_whitespace_suite_id(self, tmp_path: Path) -> None:
        rd = _run_dir(tmp_path)
        ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
        run_dir = self._write_baseline(rd, ctx)
        raw = json.loads((run_dir / "run.json").read_text("utf-8"))
        raw["suite_id"] = " "
        (run_dir / "run.json").write_text(json.dumps(raw, indent=2), "utf-8")
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            rd.read_verified_summary(
                run_id=ctx.run_id,
                expected_manifest_sha256=ctx.manifest_sha256,
            )
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "suite_id"

    def test_summary_json_tampered_whitespace_suite_id(self, tmp_path: Path) -> None:
        rd = _run_dir(tmp_path)
        ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
        run_dir = self._write_baseline(rd, ctx)
        raw = json.loads((run_dir / "summary.json").read_text("utf-8"))
        raw["suite_id"] = " "
        (run_dir / "summary.json").write_text(json.dumps(raw, indent=2), "utf-8")
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            rd.read_verified_summary(
                run_id=ctx.run_id,
                expected_manifest_sha256=ctx.manifest_sha256,
            )
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "suite_id"

    def test_summary_json_tampered_duplicate_scenario_ids(self, tmp_path: Path) -> None:
        rd = _run_dir(tmp_path)
        ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
        run_dir = self._write_baseline(rd, ctx)
        raw = json.loads((run_dir / "summary.json").read_text("utf-8"))
        raw["scenario_ids"] = ["s1", "s1"]
        (run_dir / "summary.json").write_text(json.dumps(raw, indent=2), "utf-8")
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            rd.read_verified_summary(
                run_id=ctx.run_id,
                expected_manifest_sha256=ctx.manifest_sha256,
            )
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "scenario_ids[1]"

    def test_summary_json_whitespace_code_commit_sha(self, tmp_path: Path) -> None:
        rd = _run_dir(tmp_path)
        ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",), code_commit_sha="abc123")
        run_dir = self._write_baseline(rd, ctx)
        raw = json.loads((run_dir / "summary.json").read_text("utf-8"))
        raw["code_commit_sha"] = " "
        (run_dir / "summary.json").write_text(json.dumps(raw, indent=2), "utf-8")
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            rd.read_verified_summary(
                run_id=ctx.run_id,
                expected_manifest_sha256=ctx.manifest_sha256,
            )
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "code_commit_sha"


# ── P0-4: Direct summary decoder identity tests ─────────────────────


class TestDictToSummaryStrictExactContracts:
    """_dict_to_summary_strict must reject invalid identity fields with exact error."""

    BASE = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "failed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": False,
        "scenario_results": [],
    }

    def test_accepts_valid(self) -> None:
        summary = _dict_to_summary_strict(dict(self.BASE))
        assert summary.suite_id == "suite-1"

    def test_rejects_whitespace_suite_id(self) -> None:
        d = dict(self.BASE)
        d["suite_id"] = " "
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            _dict_to_summary_strict(d)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "suite_id"

    def test_rejects_empty_suite_id(self) -> None:
        d = dict(self.BASE)
        d["suite_id"] = ""
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            _dict_to_summary_strict(d)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "suite_id"

    def test_rejects_revision_zero(self) -> None:
        d = dict(self.BASE)
        d["suite_revision"] = 0
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            _dict_to_summary_strict(d)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "suite_revision"

    def test_rejects_invalid_manifest_hash(self) -> None:
        d = dict(self.BASE)
        d["manifest_sha256"] = "invalid"
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            _dict_to_summary_strict(d)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "manifest_sha256"

    def test_rejects_whitespace_scenario_id(self) -> None:
        d = dict(self.BASE)
        d["scenario_ids"] = [" "]
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            _dict_to_summary_strict(d)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "scenario_ids[0]"

    def test_rejects_duplicate_scenario_ids(self) -> None:
        d = dict(self.BASE)
        d["scenario_ids"] = ["s1", "s1"]
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            _dict_to_summary_strict(d)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "scenario_ids[1]"

    def test_rejects_whitespace_code_commit_sha(self) -> None:
        d = dict(self.BASE)
        d["code_commit_sha"] = " "
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            _dict_to_summary_strict(d)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "code_commit_sha"

    def test_rejects_empty_code_commit_sha(self) -> None:
        d = dict(self.BASE)
        d["code_commit_sha"] = ""
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            _dict_to_summary_strict(d)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "code_commit_sha"


# ── P0-2: write_summary identity tampering tests ──────────────────────


class TestWriteSummaryTamper:
    """write_summary must reject tampered identity in run.json before writing summary."""

    def _setup(
        self, tmp_path: Path, *, tamper_field: str, tamper_value: object
    ) -> tuple[EvaluationRunDirectory, EvaluationRunContext, Path]:
        rd = _run_dir(tmp_path)
        ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
        ctx = rd.transition_status(ctx, RunStatus.RUNNING)
        ctx = rd.transition_status(ctx, RunStatus.FAILED)
        run_dir = rd.run_dir(ctx.run_id)
        raw = json.loads((run_dir / "run.json").read_text("utf-8"))
        raw[tamper_field] = tamper_value
        (run_dir / "run.json").write_text(json.dumps(raw, indent=2), "utf-8")
        return rd, ctx, run_dir

    def test_write_summary_rejects_whitespace_suite_id(self, tmp_path: Path) -> None:
        """write_summary must reject whitespace suite_id in run.json."""
        rd, ctx, run_dir = self._setup(tmp_path, tamper_field="suite_id", tamper_value=" ")
        summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
        # Snapshot directory before write attempt
        before = sorted(os.listdir(run_dir))
        summary_path = run_dir / "summary.json"
        assert not summary_path.exists()
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            rd.write_summary(ctx, summary)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "suite_id"
        # Verify no summary.json was written and directory is unchanged
        assert not summary_path.exists()
        after = sorted(os.listdir(run_dir))
        assert before == after

    def test_write_summary_rejects_duplicate_scenario_ids(self, tmp_path: Path) -> None:
        """write_summary must reject duplicate scenario_ids in run.json."""
        rd, ctx, run_dir = self._setup(
            tmp_path, tamper_field="scenario_ids", tamper_value=["s1", "s1"]
        )
        summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
        before = sorted(os.listdir(run_dir))
        summary_path = run_dir / "summary.json"
        assert not summary_path.exists()
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            rd.write_summary(ctx, summary)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "scenario_ids[1]"
        # Verify no summary.json was written and directory is unchanged
        assert not summary_path.exists()
        after = sorted(os.listdir(run_dir))
        assert before == after

    def test_write_summary_rejects_whitespace_suite_id_with_existing_summary(
        self, tmp_path: Path
    ) -> None:
        """write_summary must not overwrite existing summary.json when run.json is tampered."""
        rd = _run_dir(tmp_path)
        ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
        ctx = rd.transition_status(ctx, RunStatus.RUNNING)
        ctx = rd.transition_status(ctx, RunStatus.FAILED)
        run_dir = rd.run_dir(ctx.run_id)
        # Write a valid summary first
        original_summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
        rd.write_summary(ctx, original_summary)
        summary_path = run_dir / "summary.json"
        assert summary_path.exists()
        import hashlib

        original_bytes = summary_path.read_bytes()
        original_hash = hashlib.sha256(original_bytes).hexdigest()
        # Construct a genuinely different replacement summary
        replacement_summary = EvaluationRunSummary(
            run_id=ctx.run_id,
            suite_id=ctx.suite_id,
            suite_revision=ctx.suite_revision,
            manifest_sha256=ctx.manifest_sha256,
            scenario_ids=ctx.scenario_ids,
            status=RunStatus.FAILED,
            completed_at="2026-06-27T13:00:00+00:00",
            code_commit_sha=ctx.code_commit_sha,
            passed=False,
            scenario_results=(),
        )
        assert replacement_summary.completed_at != original_summary.completed_at
        # Tamper run.json
        raw = json.loads((run_dir / "run.json").read_text("utf-8"))
        raw["suite_id"] = " "
        (run_dir / "run.json").write_text(json.dumps(raw, indent=2), "utf-8")
        # Attempt write_summary with different summary
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            rd.write_summary(ctx, replacement_summary)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "suite_id"
        # Verify existing summary.json is unchanged (both hash AND bytes)
        assert summary_path.exists()
        assert hashlib.sha256(summary_path.read_bytes()).hexdigest() == original_hash
        assert summary_path.read_bytes() == original_bytes

    def test_write_summary_rejects_duplicate_scenario_ids_with_existing_summary(
        self, tmp_path: Path
    ) -> None:
        "write_summary must not overwrite existing summary.json"
        " with duplicate scenario_ids in run.json."
        rd = _run_dir(tmp_path)
        ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
        ctx = rd.transition_status(ctx, RunStatus.RUNNING)
        ctx = rd.transition_status(ctx, RunStatus.FAILED)
        run_dir = rd.run_dir(ctx.run_id)
        # Write a valid summary first
        original_summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
        rd.write_summary(ctx, original_summary)
        summary_path = run_dir / "summary.json"
        assert summary_path.exists()
        import hashlib

        original_bytes = summary_path.read_bytes()
        original_hash = hashlib.sha256(original_bytes).hexdigest()
        # Construct a genuinely different replacement summary
        replacement_summary = EvaluationRunSummary(
            run_id=ctx.run_id,
            suite_id=ctx.suite_id,
            suite_revision=ctx.suite_revision,
            manifest_sha256=ctx.manifest_sha256,
            scenario_ids=ctx.scenario_ids,
            status=RunStatus.FAILED,
            completed_at="2026-06-27T13:00:00+00:00",
            code_commit_sha=ctx.code_commit_sha,
            passed=False,
            scenario_results=(),
        )
        assert replacement_summary.completed_at != original_summary.completed_at
        # Tamper run.json
        raw = json.loads((run_dir / "run.json").read_text("utf-8"))
        raw["scenario_ids"] = ["s1", "s1"]
        (run_dir / "run.json").write_text(json.dumps(raw, indent=2), "utf-8")
        # Attempt write_summary with different summary
        with pytest.raises(RunSummaryInvalidError) as exc_info:
            rd.write_summary(ctx, replacement_summary)
        assert exc_info.value.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc_info.value.field == "scenario_ids[1]"
        # Verify existing summary.json is unchanged (both hash AND bytes)
        assert summary_path.exists()
        assert hashlib.sha256(summary_path.read_bytes()).hexdigest() == original_hash
        assert summary_path.read_bytes() == original_bytes
