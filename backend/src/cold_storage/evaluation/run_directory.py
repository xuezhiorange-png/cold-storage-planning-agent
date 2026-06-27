"""Isolated run directory management with stale-output protection."""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cold_storage.evaluation.errors import (
    RunDirectoryExistsError,
    RunIdentityMismatchError,
    RunManifestMismatchError,
    RunStateError,
    RunSummaryInvalidError,
    RunSummaryNotFoundError,
    RunSummaryStatusInvalidError,
)
from cold_storage.evaluation.models import (
    EvaluationRunSummary,
    RunStatus,
    ScenarioRunSummary,
)


@dataclass(frozen=True, slots=True)
class EvaluationRunContext:
    """Metadata for a single evaluation run."""

    run_id: str
    suite_id: str
    suite_revision: int
    manifest_sha256: str
    started_at: str
    status: RunStatus
    scenario_ids: tuple[str, ...]
    database_backend: str | None = None
    code_commit_sha: str | None = None


class EvaluationRunDirectory:
    """Manages a unique, isolated evaluation run directory.

    Each run gets a unique ID and directory under ``evaluation/runs/<run-id>/``.
    The directory structure is::

        runs/<run-id>/
        ├── run.json       # Run metadata
        ├── raw/           # Raw outputs before canonicalization
        ├── normalized/    # Canonicalized comparison outputs
        └── summary.json   # Final result (written atomically)
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)

    def create_run(
        self,
        suite_id: str,
        suite_revision: int,
        manifest_sha256: str,
        scenario_ids: tuple[str, ...],
        *,
        database_backend: str | None = None,
        code_commit_sha: str | None = None,
    ) -> EvaluationRunContext:
        """Create a new unique run directory.

        Returns the run context.  Raises ``RunDirectoryExistsError`` if the
        directory already exists (UUID collision) or cannot be created.
        """
        run_id = _generate_run_id()
        run_dir = self._base / run_id

        if run_dir.exists():
            raise RunDirectoryExistsError(
                code="EVAL_RUN_DIRECTORY_EXISTS",
                message=f"Run directory already exists: '{run_dir}'",
            )

        started_at = datetime.now(UTC).isoformat()
        context = EvaluationRunContext(
            run_id=run_id,
            suite_id=suite_id,
            suite_revision=suite_revision,
            manifest_sha256=manifest_sha256,
            started_at=started_at,
            status=RunStatus.CREATED,
            scenario_ids=scenario_ids,
            database_backend=database_backend,
            code_commit_sha=code_commit_sha,
        )

        # Create directory structure
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "raw").mkdir()
        (run_dir / "normalized").mkdir()

        # Write run.json atomically
        _atomic_write(run_dir / "run.json", _context_to_dict(context))

        return context

    def transition_status(
        self,
        context: EvaluationRunContext,
        new_status: RunStatus,
    ) -> EvaluationRunContext:
        """Transition run status and persist update.

        Valid transitions:
        - created -> running
        - running -> passed | failed | aborted
        """
        allowed = self._allowed_transitions(context.status, new_status)
        if not allowed:
            raise RunStateError(
                code="EVAL_RUN_STATE_INVALID",
                message=(f"Invalid state transition: {context.status.value} -> {new_status.value}"),
            )

        updated = EvaluationRunContext(
            run_id=context.run_id,
            suite_id=context.suite_id,
            suite_revision=context.suite_revision,
            manifest_sha256=context.manifest_sha256,
            started_at=context.started_at,
            status=new_status,
            scenario_ids=context.scenario_ids,
            database_backend=context.database_backend,
            code_commit_sha=context.code_commit_sha,
        )
        _atomic_write(self._base / context.run_id / "run.json", _context_to_dict(updated))
        return updated

    def write_summary(
        self,
        context: EvaluationRunContext,
        summary: EvaluationRunSummary,
    ) -> None:
        """Write a typed summary.json for the run.

        The write is atomic (unique temp file + fsync + os.replace).
        Only allowed when the run status is ``RUNNING``, ``PASSED``, or ``FAILED``.

        Validates identity constraints:
        - summary.run_id must equal context.run_id
        - summary.manifest_sha256 must equal context.manifest_sha256
        - summary.suite_id must equal context.suite_id
        - summary.suite_revision must equal context.suite_revision
        - summary.scenario_ids must equal context.scenario_ids
        - passed=True requires summary.status == PASSED
        """
        if context.status not in (RunStatus.RUNNING, RunStatus.PASSED, RunStatus.FAILED):
            raise RunStateError(
                code="EVAL_RUN_STATE_INVALID",
                message=f"Cannot write summary in status '{context.status.value}'",
            )

        # Validate identity
        if summary.run_id != context.run_id:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(
                    f"Summary run_id '{summary.run_id}' does not match "
                    f"context run_id '{context.run_id}'"
                ),
                field="run_id",
            )
        if summary.manifest_sha256 != context.manifest_sha256:
            raise RunManifestMismatchError(
                code="EVAL_RUN_MANIFEST_MISMATCH",
                message=(
                    f"Summary manifest_sha256 '{summary.manifest_sha256[:16]}...' "
                    f"does not match context '{context.manifest_sha256[:16]}...'"
                ),
                field="manifest_sha256",
            )
        if summary.suite_id != context.suite_id:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(
                    f"Summary suite_id '{summary.suite_id}' "
                    f"does not match context '{context.suite_id}'"
                ),
                field="suite_id",
            )
        if summary.suite_revision != context.suite_revision:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(
                    f"Summary suite_revision {summary.suite_revision} "
                    f"does not match context {context.suite_revision}"
                ),
                field="suite_revision",
            )
        if summary.scenario_ids != context.scenario_ids:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=("Summary scenario_ids differ from context"),
                field="scenario_ids",
            )
        if summary.passed and summary.status != RunStatus.PASSED:
            raise RunSummaryStatusInvalidError(
                code="EVAL_RUN_SUMMARY_STATUS_INVALID",
                message=(f"Summary claims passed=True but status is '{summary.status.value}'"),
                field="status",
            )

        _atomic_write(
            self._base / context.run_id / "summary.json",
            _summary_to_dict(summary),
        )

    def read_summary(self, run_id: str) -> dict[str, Any] | None:
        """Read summary.json for a given run ID.

        Returns ``None`` if the file does not exist.
        """
        path = self._base / run_id / "summary.json"
        if not path.exists():
            return None
        result: Any = json.loads(path.read_text("utf-8"))
        return cast("dict[str, Any]", result)

    def read_verified_summary(
        self,
        *,
        run_id: str,
        expected_manifest_sha256: str,
        expected_suite_id: str | None = None,
        expected_suite_revision: int | None = None,
    ) -> EvaluationRunSummary:
        """Read and verify a run summary against expected identity.

        Raises:
            RunSummaryNotFoundError: Summary file does not exist or run.json does not exist.
            RunSummaryInvalidError: Summary JSON is malformed.
            RunIdentityMismatchError: Summary identity does not match expected.
            RunManifestMismatchError: Summary manifest hash does not match.
            RunSummaryStatusInvalidError: Summary status vs run.json inconsistency.
        """
        run_dir = self._base / run_id
        summary_path = run_dir / "summary.json"
        run_json_path = run_dir / "run.json"

        if not summary_path.exists():
            raise RunSummaryNotFoundError(
                code="EVAL_RUN_SUMMARY_NOT_FOUND",
                message=f"Summary file not found for run '{run_id}'",
            )
        if not run_json_path.exists():
            raise RunSummaryNotFoundError(
                code="EVAL_RUN_SUMMARY_NOT_FOUND",
                message=f"Run metadata not found for run '{run_id}'",
            )

        try:
            raw_summary: dict[str, Any] = json.loads(summary_path.read_text("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Summary JSON is invalid for run '{run_id}': {exc}",
            ) from exc

        # Convert to typed model
        try:
            summary = _dict_to_summary(raw_summary)
        except (KeyError, TypeError, ValueError) as exc:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Summary structure is invalid for run '{run_id}': {exc}",
            ) from exc

        # Validate identity
        if summary.run_id != run_id:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(
                    f"Summary run_id '{summary.run_id}' does not match directory name '{run_id}'"
                ),
                field="run_id",
            )

        if summary.manifest_sha256 != expected_manifest_sha256:
            raise RunManifestMismatchError(
                code="EVAL_RUN_MANIFEST_MISMATCH",
                message=(
                    f"Summary manifest hash '{summary.manifest_sha256[:16]}...' "
                    f"does not match expected '{expected_manifest_sha256[:16]}...'"
                ),
                field="manifest_sha256",
            )

        if expected_suite_id is not None and summary.suite_id != expected_suite_id:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(
                    f"Summary suite_id '{summary.suite_id}' "
                    f"does not match expected '{expected_suite_id}'"
                ),
                field="suite_id",
            )

        if (
            expected_suite_revision is not None
            and summary.suite_revision != expected_suite_revision
        ):
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(
                    f"Summary suite_revision {summary.suite_revision} "
                    f"does not match expected {expected_suite_revision}"
                ),
                field="suite_revision",
            )

        # Verify against run.json
        try:
            run_meta: dict[str, Any] = json.loads(run_json_path.read_text("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Run.json is invalid for run '{run_id}': {exc}",
            ) from exc

        if summary.run_id != run_meta.get("run_id", ""):
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(
                    f"Summary run_id '{summary.run_id}' does not match "
                    f"run.json run_id '{run_meta.get('run_id')}'"
                ),
                field="run_id",
            )
        if summary.manifest_sha256 != run_meta.get("manifest_sha256", ""):
            raise RunManifestMismatchError(
                code="EVAL_RUN_MANIFEST_MISMATCH",
                message="Summary manifest hash does not match run.json",
                field="manifest_sha256",
            )
        if summary.passed and run_meta.get("status") != "passed":
            raise RunSummaryStatusInvalidError(
                code="EVAL_RUN_SUMMARY_STATUS_INVALID",
                message=(
                    f"Summary claims passed but run.json status is '{run_meta.get('status')}'"
                ),
                field="status",
            )

        return summary

    def run_dir(self, run_id: str) -> Path:
        """Get the directory path for a given run ID."""
        return self._base / run_id

    @staticmethod
    def _allowed_transitions(current: RunStatus, next_status: RunStatus) -> bool:
        transitions = {
            RunStatus.CREATED: {RunStatus.RUNNING},
            RunStatus.RUNNING: {RunStatus.PASSED, RunStatus.FAILED, RunStatus.ABORTED},
        }
        return next_status in transitions.get(current, set())


def _generate_run_id() -> str:
    """Generate a unique, compact run ID."""
    return uuid.uuid4().hex[:12]


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write data atomically to a JSON file.

    Uses a unique temp filename + flush + fsync + os.replace for crash safety.
    """
    tmp = path.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
    try:
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        tmp.write_bytes(content)
        # Flush and fsync for durability
        with open(tmp, "rb") as f:
            fcntl.fsync(f.fileno())
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _context_to_dict(ctx: EvaluationRunContext) -> dict[str, Any]:
    return {
        "run_id": ctx.run_id,
        "suite_id": ctx.suite_id,
        "suite_revision": ctx.suite_revision,
        "manifest_sha256": ctx.manifest_sha256,
        "started_at": ctx.started_at,
        "status": ctx.status.value,
        "scenario_ids": list(ctx.scenario_ids),
        "database_backend": ctx.database_backend,
        "code_commit_sha": ctx.code_commit_sha,
    }


def _summary_to_dict(summary: EvaluationRunSummary) -> dict[str, Any]:
    return {
        "run_id": summary.run_id,
        "suite_id": summary.suite_id,
        "suite_revision": summary.suite_revision,
        "manifest_sha256": summary.manifest_sha256,
        "scenario_ids": list(summary.scenario_ids),
        "status": summary.status.value,
        "completed_at": summary.completed_at,
        "code_commit_sha": summary.code_commit_sha,
        "passed": summary.passed,
        "scenario_results": [
            {
                "scenario_id": sr.scenario_id,
                "passed": sr.passed,
                "checks_total": sr.checks_total,
                "checks_passed": sr.checks_passed,
                "checks_failed": sr.checks_failed,
            }
            for sr in summary.scenario_results
        ],
    }


def _dict_to_summary(d: dict[str, Any]) -> EvaluationRunSummary:
    """Convert a deserialized dict to a typed summary."""
    scenario_results = tuple(
        ScenarioRunSummary(
            scenario_id=sr["scenario_id"],
            passed=sr["passed"],
            checks_total=sr["checks_total"],
            checks_passed=sr["checks_passed"],
            checks_failed=sr["checks_failed"],
        )
        for sr in d.get("scenario_results", [])
    )
    return EvaluationRunSummary(
        run_id=d["run_id"],
        suite_id=d["suite_id"],
        suite_revision=d["suite_revision"],
        manifest_sha256=d["manifest_sha256"],
        scenario_ids=tuple(d.get("scenario_ids", [])),
        status=RunStatus(d["status"]),
        completed_at=d.get("completed_at", ""),
        code_commit_sha=d.get("code_commit_sha"),
        passed=d["passed"],
        scenario_results=scenario_results,
    )
