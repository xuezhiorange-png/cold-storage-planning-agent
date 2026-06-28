"""Isolated run directory management with stale-output protection."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cold_storage.evaluation.errors import (
    RunDirectoryExistsError,
    RunIdentityMismatchError,
    RunIdentityValidationIssue,
    RunManifestMismatchError,
    RunStateError,
    RunSummaryInvalidError,
    RunSummaryNotFoundError,
    RunSummaryStatusInvalidError,
)
from cold_storage.evaluation.models import EvaluationRunSummary, RunStatus, ScenarioRunSummary

_VALID_RUN_ID_RE = re.compile(r"^[a-f0-9]{12}$")
_VALID_MANIFEST_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

# Allowed database backend values.
_VALID_DATABASE_BACKENDS: set[str | None] = {None, "sqlite", "postgresql"}

# ── Summary contract: terminal statuses only ───────────────────────
_TERMINAL_STATUSES = {RunStatus.PASSED, RunStatus.FAILED, RunStatus.ABORTED}

# ── Helper: known summary root fields ──────────────────────────────
_KNOWN_SUMMARY_FIELDS = {
    "run_id",
    "suite_id",
    "suite_revision",
    "manifest_sha256",
    "scenario_ids",
    "status",
    "completed_at",
    "code_commit_sha",
    "passed",
    "scenario_results",
}

# ── Helper: known scenario_result fields ───────────────────────────
_KNOWN_RESULT_FIELDS = {
    "scenario_id",
    "passed",
    "checks_total",
    "checks_passed",
    "checks_failed",
}


def _validate_run_id(run_id: str) -> None:
    """Validate run_id format to prevent path traversal attacks."""
    from cold_storage.evaluation.errors import EvaluationError

    if not _VALID_RUN_ID_RE.match(run_id):
        raise EvaluationError(
            code="EVAL_RUN_ID_INVALID",
            message=f"Invalid run_id format: '{run_id}' (must be 12 hex chars)",
            field="run_id",
        )


def _resolve_run_directory(base: Path, run_id: str) -> Path:
    """Resolve a run directory path and verify it stays under *base*.

    Performs, in order:
    1. Validate run ID format (12 hex chars).
    2. Resolve both *base* and the candidate run directory to absolute paths.
    3. Verify the resolved run directory is :meth:`Path.is_relative_to` *base*.

    Raises:
        EvaluationError: If run ID format is invalid or the resolved path
            escapes the base directory.
    """
    _validate_run_id(run_id)
    base_resolved = base.resolve()
    run_resolved = (base / run_id).resolve()
    if not run_resolved.is_relative_to(base_resolved):
        from cold_storage.evaluation.errors import EvaluationError

        raise EvaluationError(
            code="EVAL_RUN_ID_INVALID",
            message=(
                f"Resolved run directory '{run_resolved}' is outside "
                f"base directory '{base_resolved}'"
            ),
            field="run_id",
        )
    return run_resolved


# ────────────────────────────────────────────────────────────────
#  Shared Run Identity validation (P0-1)
# ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RunIdentityValues:
    """Canonical identity values for validation across all boundaries."""

    suite_id: str
    suite_revision: int
    manifest_sha256: str
    scenario_ids: tuple[str, ...]
    database_backend: str | None
    code_commit_sha: str | None


def _check_suite_id(suite_id: object) -> str:
    """Validate and return non-empty non-whitespace suite_id or raise."""
    if not isinstance(suite_id, str):
        raise RunIdentityValidationIssue(
            field="suite_id",
            message=f"suite_id must be a string, got {type(suite_id).__name__}",
        )
    if not suite_id.strip():
        raise RunIdentityValidationIssue(
            field="suite_id",
            message=f"suite_id must be non-empty, got {suite_id!r}",
        )
    return suite_id


def _check_suite_revision(suite_revision: object) -> int:
    """Validate and return int >= 1 suite_revision or raise."""
    if isinstance(suite_revision, bool) or not isinstance(suite_revision, int):
        raise RunIdentityValidationIssue(
            field="suite_revision",
            message=f"suite_revision must be an int, got {type(suite_revision).__name__}",
        )
    if suite_revision < 1:
        raise RunIdentityValidationIssue(
            field="suite_revision",
            message=f"suite_revision must be >= 1, got {suite_revision}",
        )
    return suite_revision


def _check_manifest_sha256(manifest_sha256: object) -> str:
    """Validate and return 64-hex-char manifest_sha256 or raise."""
    if not isinstance(manifest_sha256, str):
        raise RunIdentityValidationIssue(
            field="manifest_sha256",
            message=f"manifest_sha256 must be a string, got {type(manifest_sha256).__name__}",
        )
    if not _VALID_MANIFEST_SHA256_RE.match(manifest_sha256):
        raise RunIdentityValidationIssue(
            field="manifest_sha256",
            message=f"manifest_sha256 must be 64 lowercase hex chars, got {manifest_sha256!r}",
        )
    return manifest_sha256


def _check_scenario_ids(scenario_ids: object) -> tuple[str, ...]:
    """Validate and return non-empty unique scenario IDs from tuple/list or raise."""
    if isinstance(scenario_ids, list):
        scenario_ids = tuple(scenario_ids)
    if not isinstance(scenario_ids, tuple):
        raise RunIdentityValidationIssue(
            field="scenario_ids",
            message=f"scenario_ids must be a tuple or list, got {type(scenario_ids).__name__}",
        )
    seen: set[str] = set()
    result: list[str] = []
    for idx, sid in enumerate(scenario_ids):
        if not isinstance(sid, str):
            raise RunIdentityValidationIssue(
                field=f"scenario_ids[{idx}]",
                message=f"scenario_ids[{idx}] must be a string, got {type(sid).__name__}",
            )
        if not sid.strip():
            raise RunIdentityValidationIssue(
                field=f"scenario_ids[{idx}]",
                message=f"scenario_ids[{idx}] must be non-empty non-whitespace, got {sid!r}",
            )
        if sid in seen:
            raise RunIdentityValidationIssue(
                field=f"scenario_ids[{idx}]",
                message=f"scenario_ids[{idx}] Duplicate scenario_id: '{sid}'",
            )
        seen.add(sid)
        result.append(sid)
    return tuple(result)


def _check_database_backend(backend: object) -> str | None:
    """Validate and return database_backend or raise."""
    if backend is None:
        return None
    if not isinstance(backend, str):
        raise RunIdentityValidationIssue(
            field="database_backend",
            message=f"database_backend must be None or a string, got {type(backend).__name__}",
        )
    if backend not in {"sqlite", "postgresql"}:
        raise RunIdentityValidationIssue(
            field="database_backend",
            message=(
                f"database_backend '{backend}' is not supported "
                f"(must be None, sqlite, or postgresql)"
            ),
        )
    return backend


def _check_code_commit_sha(sha: object) -> str | None:
    """Validate and return code_commit_sha (None or non-empty non-whitespace) or raise."""
    if sha is None:
        return None
    if not isinstance(sha, str):
        raise RunIdentityValidationIssue(
            field="code_commit_sha",
            message=f"code_commit_sha must be None or a string, got {type(sha).__name__}",
        )
    if not sha.strip():
        raise RunIdentityValidationIssue(
            field="code_commit_sha",
            message=f"code_commit_sha must be non-empty non-whitespace, got {sha!r}",
        )
    return sha


def validate_run_identity_values(values: RunIdentityValues) -> None:
    """Validate all run identity fields with shared semantic rules.

    Raises ``RunIdentityValidationIssue`` with ``field`` and ``message``
    stored directly (not parsed from formatted text).
    """
    _check_suite_id(values.suite_id)
    _check_suite_revision(values.suite_revision)
    _check_manifest_sha256(values.manifest_sha256)
    _check_scenario_ids(values.scenario_ids)
    _check_database_backend(values.database_backend)
    _check_code_commit_sha(values.code_commit_sha)


def validate_run_creation_inputs(
    *,
    suite_id: str,
    suite_revision: int,
    manifest_sha256: str,
    scenario_ids: tuple[str, ...],
    database_backend: str | None = None,
    code_commit_sha: str | None = None,
) -> None:
    """Validate all run creation inputs *before* any file system side-effects.

    Delegates to the shared ``validate_run_identity_values`` and re-raises
    with ``RunInputInvalidError`` (code ``EVAL_RUN_INPUT_INVALID``).
    """
    from cold_storage.evaluation.errors import RunInputInvalidError

    try:
        validate_run_identity_values(
            RunIdentityValues(
                suite_id=suite_id,
                suite_revision=suite_revision,
                manifest_sha256=manifest_sha256,
                scenario_ids=scenario_ids,
                database_backend=database_backend,
                code_commit_sha=code_commit_sha,
            )
        )
    except RunIdentityValidationIssue as exc:
        raise RunInputInvalidError(
            code="EVAL_RUN_INPUT_INVALID",
            message=exc.message,
            field=exc.field,
        ) from exc


# ────────────────────────────────────────────────────────────────
#  Centralised summary contract validator (P0-1)
# ────────────────────────────────────────────────────────────────


def validate_run_summary(
    summary: EvaluationRunSummary,
    *,
    declared_scenario_ids: tuple[str, ...] = (),
    allow_running: bool = False,
) -> None:
    """Validate an ``EvaluationRunSummary`` against all contract invariants.

    Called by ``write_summary()``, ``_dict_to_summary_strict()``, and
    optionally ``read_verified_summary()`` so every write path enforces
    the same rules.

    Args:
        summary: The typed summary to validate.
        declared_scenario_ids: The full set of scenario IDs declared
            for this run.  Required when ``summary.status == PASSED``.
        allow_running: When True, RUNNING status is permitted (non-terminal).
            Default False — only PASSED/FAILED/ABORTED are legal final states.

    Raises:
        RunSummaryStatusInvalidError: On passed/status mismatch.
        RunSummaryInvalidError: On structural invariant violations.
    """
    # ── Terminal status only ────────────────────────────────────
    if not allow_running and summary.status not in _TERMINAL_STATUSES:
        raise RunSummaryStatusInvalidError(
            code="EVAL_RUN_SUMMARY_STATUS_INVALID",
            message=(
                "Summary status must be terminal "
                f"(PASSED/FAILED/ABORTED), got '{summary.status.value}'"
            ),
            field="status",
        )

    # ── passed/status bidirectional invariant ───────────────────
    if summary.passed and summary.status != RunStatus.PASSED:
        raise RunSummaryStatusInvalidError(
            code="EVAL_RUN_SUMMARY_STATUS_INVALID",
            message=f"passed=True but status is '{summary.status.value}'",
            field="status",
        )
    if not summary.passed and summary.status == RunStatus.PASSED:
        raise RunSummaryStatusInvalidError(
            code="EVAL_RUN_SUMMARY_STATUS_INVALID",
            message=f"status=PASSED but passed={summary.passed}",
            field="status",
        )
    # ── completed_at — terminal summaries require it ────────────
    if summary.status in _TERMINAL_STATUSES:
        if not summary.completed_at:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=(
                    f"Terminal summary '{summary.status.value}' must have non-empty completed_at"
                ),
                field="completed_at",
            )
        try:
            parsed_dt = datetime.fromisoformat(summary.completed_at)
        except (ValueError, TypeError) as exc:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Invalid completed_at format: '{summary.completed_at}': {exc}",
                field="completed_at",
            ) from exc
        if parsed_dt.tzinfo is None or parsed_dt.utcoffset() is None:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"completed_at must include timezone offset, got '{summary.completed_at}'",
                field="completed_at",
            )

    # ── Scenario result invariants ──────────────────────────────
    seen_result_ids: set[str] = set()
    for sr in summary.scenario_results:
        # scenario_id non-empty
        if not sr.scenario_id:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message="Scenario result has empty scenario_id",
                field="scenario_results",
            )

        # No duplicate
        if sr.scenario_id in seen_result_ids:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Duplicate scenario result ID: '{sr.scenario_id}'",
                field="scenario_results",
            )
        seen_result_ids.add(sr.scenario_id)

        # No undeclared ID
        if declared_scenario_ids and sr.scenario_id not in declared_scenario_ids:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Undeclared scenario result ID: '{sr.scenario_id}'",
                field="scenario_results",
            )

        # Count invariants
        if sr.checks_total < 0:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Negative checks_total for scenario '{sr.scenario_id}': {sr.checks_total}",
                field="scenario_results",
            )
        if sr.checks_passed < 0:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=(
                    f"Negative checks_passed for scenario '{sr.scenario_id}': {sr.checks_passed}"
                ),
                field="scenario_results",
            )
        if sr.checks_failed < 0:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=(
                    f"Negative checks_failed for scenario '{sr.scenario_id}': {sr.checks_failed}"
                ),
                field="scenario_results",
            )
        if sr.checks_passed + sr.checks_failed != sr.checks_total:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=(
                    f"Check counts do not close for scenario '{sr.scenario_id}': "
                    f"{sr.checks_passed} + {sr.checks_failed} != {sr.checks_total}"
                ),
                field="scenario_results",
            )
        if sr.passed != (sr.checks_failed == 0):
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=(
                    f"Scenario '{sr.scenario_id}' passed={sr.passed} "
                    f"but checks_failed={sr.checks_failed}"
                ),
                field="scenario_results",
            )

    # ── PASSED scenario completeness ────────────────────────────
    if summary.status == RunStatus.PASSED and declared_scenario_ids:
        if len(summary.scenario_results) != len(declared_scenario_ids):
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=(
                    f"PASSED summary with {len(summary.scenario_results)} "
                    f"scenario results, expected {len(declared_scenario_ids)}"
                ),
                field="scenario_results",
            )
        result_ids = {sr.scenario_id for sr in summary.scenario_results}
        for sid in declared_scenario_ids:
            if sid not in result_ids:
                raise RunSummaryInvalidError(
                    code="EVAL_RUN_SUMMARY_INVALID",
                    message=f"PASSED summary missing scenario result for '{sid}'",
                    field="scenario_results",
                )
        for sr in summary.scenario_results:
            if not sr.passed:
                raise RunSummaryInvalidError(
                    code="EVAL_RUN_SUMMARY_INVALID",
                    message=(
                        f"PASSED summary contains non-passed scenario result: '{sr.scenario_id}'"
                    ),
                    field="scenario_results",
                )
            # PASSED scenario should have at least one check
            if sr.checks_total == 0:
                raise RunSummaryInvalidError(
                    code="EVAL_RUN_SUMMARY_INVALID",
                    message=(
                        f"PASSED scenario '{sr.scenario_id}' has "
                        f"checks_total=0 (empty-pass not allowed)"
                    ),
                    field="scenario_results",
                )


# ────────────────────────────────────────────────────────────────
#  Strict run.json decoder (P0-2)
# ────────────────────────────────────────────────────────────────


def _decode_run_context_strict(value: object) -> EvaluationRunContext:
    """Strictly decode and validate a persisted ``run.json`` value.

    Accepts only a ``dict`` with exactly the known fields, proper types,
    and valid semantic content.  Rejects unknown fields, wrong types,
    and malformed values with ``RunSummaryInvalidError``.

    Raises:
        RunSummaryInvalidError: On any structural or type violation.
    """

    # Must be a dict
    if not isinstance(value, dict):
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Run.json root must be a dict, got {type(value).__name__}",
        )

    # Reject unknown root fields
    _KNOWN_RUN_FIELDS = {
        "run_id",
        "suite_id",
        "suite_revision",
        "manifest_sha256",
        "started_at",
        "status",
        "scenario_ids",
        "database_backend",
        "code_commit_sha",
    }
    extra = set(value) - _KNOWN_RUN_FIELDS
    if extra:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Unknown run.json fields: {sorted(extra)}",
        )

    def _expect_str(v: object, field: str) -> str:
        if not isinstance(v, str):
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Expected str for '{field}', got {type(v).__name__}",
            )
        return v

    def _expect_int(v: object, field: str) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Expected int for '{field}', got {type(v).__name__}",
            )
        return v

    # Required string fields
    run_id = _expect_str(value.get("run_id"), "run_id")
    suite_id = _expect_str(value.get("suite_id"), "suite_id")
    manifest_sha256 = _expect_str(value.get("manifest_sha256"), "manifest_sha256")
    started_at = _expect_str(value.get("started_at"), "started_at")
    status_str = _expect_str(value.get("status"), "status")
    suite_revision = _expect_int(value.get("suite_revision"), "suite_revision")

    # Run ID format
    if not _VALID_RUN_ID_RE.match(run_id):
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Invalid run_id format in run.json: '{run_id}'",
        )

    # Manifest SHA-256 format
    if not _VALID_MANIFEST_SHA256_RE.match(manifest_sha256):
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Invalid manifest_sha256 format in run.json: '{manifest_sha256[:16]}...'",
            field="manifest_sha256",
        )

    # Status
    try:
        status = RunStatus(status_str)
    except ValueError as exc:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Invalid run status in run.json: '{status_str}': {exc}",
        ) from exc

    # started_at ISO-8601 with timezone — must be non-empty
    if not started_at:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message="started_at must be non-empty in run.json",
        )
    try:
        parsed_dt = datetime.fromisoformat(started_at)
    except (ValueError, TypeError) as exc:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Invalid started_at in run.json: '{started_at}': {exc}",
        ) from exc
    if parsed_dt.tzinfo is None or parsed_dt.utcoffset() is None:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"started_at must include timezone offset in run.json, got '{started_at}'",
            field="started_at",
        )

    # Parse scenario_ids as tuple of strings (semantic validation via shared validator below)
    scenario_ids_raw = value.get("scenario_ids")
    if not isinstance(scenario_ids_raw, list):
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Expected list for 'scenario_ids', got {type(scenario_ids_raw).__name__}",
        )
    scenario_ids_list: list[str] = []
    for index, s_raw in enumerate(scenario_ids_raw):
        s = _expect_str(s_raw, f"scenario_ids[{index}]")
        scenario_ids_list.append(s)
    scenario_ids = tuple(scenario_ids_list)

    database_backend_raw = value.get("database_backend")
    if database_backend_raw is not None:
        database_backend_str = _expect_str(database_backend_raw, "database_backend")
        if database_backend_str not in {"sqlite", "postgresql"}:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Invalid database_backend in run.json: '{database_backend_str}'",
                field="database_backend",
            )
        database_backend = database_backend_str
    else:
        database_backend = None

    code_commit_sha_raw = value.get("code_commit_sha")
    if code_commit_sha_raw is not None:
        code_commit_sha_str = _expect_str(code_commit_sha_raw, "code_commit_sha")
        if not code_commit_sha_str.strip():
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message="'code_commit_sha' must be None or non-empty, non-whitespace string",
                field="code_commit_sha",
            )
        code_commit_sha = code_commit_sha_str
    else:
        code_commit_sha = None

    # Run shared identity validation on all typed fields
    try:
        validate_run_identity_values(
            RunIdentityValues(
                suite_id=suite_id,
                suite_revision=suite_revision,
                manifest_sha256=manifest_sha256,
                scenario_ids=scenario_ids,
                database_backend=database_backend,
                code_commit_sha=code_commit_sha,
            )
        )
    except RunIdentityValidationIssue as exc:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=exc.message,
            field=exc.field,
        ) from exc

    return EvaluationRunContext(
        run_id=run_id,
        suite_id=suite_id,
        suite_revision=suite_revision,
        manifest_sha256=manifest_sha256,
        started_at=started_at,
        status=status,
        scenario_ids=scenario_ids,
        database_backend=database_backend,
        code_commit_sha=code_commit_sha,
    )


# ────────────────────────────────────────────────────────────────
#  Load persisted run.json
# ────────────────────────────────────────────────────────────────


def _load_run_json_strict(run_dir: Path, run_id: str) -> EvaluationRunContext:
    """Read, decode and validate the ``run.json`` under *run_dir*.

    Raises:
        RunSummaryInvalidError: If the file is missing, malformed, or
            fails strict decoding.
    """
    run_json_path = run_dir / "run.json"
    try:
        raw = json.loads(run_json_path.read_text("utf-8"))
    except FileNotFoundError:
        raise RunSummaryNotFoundError(
            code="EVAL_RUN_SUMMARY_NOT_FOUND",
            message=f"Run metadata (run.json) not found for run '{run_id}'",
        ) from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Run.json is invalid for run '{run_id}': {exc}",
        ) from exc
    return _decode_run_context_strict(raw)


# ────────────────────────────────────────────────────────────────
#  EvaluationRunDirectory
# ────────────────────────────────────────────────────────────────


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

        All inputs are validated *before* any file system side-effects.
        """
        # Validate inputs first — no file system side-effects before this passes
        validate_run_creation_inputs(
            suite_id=suite_id,
            suite_revision=suite_revision,
            manifest_sha256=manifest_sha256,
            scenario_ids=scenario_ids,
            database_backend=database_backend,
            code_commit_sha=code_commit_sha,
        )

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

        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "raw").mkdir()
        (run_dir / "normalized").mkdir()

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

        Validates run ID format, path containment, and that the run
        directory and run.json already exist (and are decodable) before
        modifying state.
        """
        # Validate run ID and path containment
        run_dir = _resolve_run_directory(self._base, context.run_id)
        if not run_dir.exists():
            raise RunStateError(
                code="EVAL_RUN_STATE_INVALID",
                message=f"Run directory does not exist for run '{context.run_id}'",
            )

        # Strictly decode persisted run.json
        try:
            persisted = _load_run_json_strict(run_dir, context.run_id)
        except (RunSummaryNotFoundError, RunSummaryInvalidError) as exc:
            raise RunStateError(
                code="EVAL_RUN_STATE_INVALID",
                message=f"Run metadata is invalid for run '{context.run_id}': {exc}",
                field=getattr(exc, "field", None),
            ) from exc
        _verify_context_against_run_meta(context, _context_to_dict(persisted))

        allowed = self._allowed_transitions(context.status, new_status)
        if not allowed:
            raise RunStateError(
                code="EVAL_RUN_STATE_INVALID",
                message=f"Invalid state transition: {context.status.value} -> {new_status.value}",
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
        _atomic_write(run_dir / "run.json", _context_to_dict(updated))
        return updated

    def write_summary(
        self,
        context: EvaluationRunContext,
        summary: EvaluationRunSummary,
    ) -> None:
        """Write a typed summary.json for the run.

        The write is atomic (unique temp file + fsync + os.replace).

        Pre-conditions:
        - Run directory must exist (created by create_run).
        - ``run.json`` must exist and be valid.
        - Persisted identity in ``run.json`` must match *context*.

        Identity constraints:
        - summary.run_id must equal context.run_id
        - summary.manifest_sha256 must equal context.manifest_sha256
        - summary.suite_id must equal context.suite_id
        - summary.suite_revision must equal context.suite_revision
        - summary.scenario_ids must equal context.scenario_ids
        - summary.status must equal context.status
        """
        # Validate run ID and path containment → get resolved run_dir
        run_dir = _resolve_run_directory(self._base, context.run_id)
        summary_path = run_dir / "summary.json"

        # Fail closed: run.json must exist
        if not run_dir.exists():
            raise RunSummaryNotFoundError(
                code="EVAL_RUN_SUMMARY_NOT_FOUND",
                message=f"Run directory does not exist for run '{context.run_id}'",
            )

        # Strictly decode persisted run.json
        persisted = _load_run_json_strict(run_dir, context.run_id)
        _verify_context_against_run_meta(context, _context_to_dict(persisted))

        # Validate identity fields between summary and context
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
        # code_commit_sha must match context
        if summary.code_commit_sha != context.code_commit_sha:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(
                    f"Summary code_commit_sha '{summary.code_commit_sha}' "
                    f"does not match context '{context.code_commit_sha}'"
                ),
                field="code_commit_sha",
            )
        if summary.scenario_ids != context.scenario_ids:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message="Summary scenario_ids differ from context",
                field="scenario_ids",
            )

        # summary.status must equal context.status
        if summary.status != context.status:
            raise RunSummaryStatusInvalidError(
                code="EVAL_RUN_SUMMARY_STATUS_INVALID",
                message=(
                    f"Summary status '{summary.status.value}' does not match "
                    f"context status '{context.status.value}'"
                ),
                field="status",
            )

        # Centralised summary contract validation
        validate_run_summary(
            summary,
            declared_scenario_ids=context.scenario_ids,
            allow_running=False,
        )

        _atomic_write(summary_path, _summary_to_dict(summary))

    def read_verified_summary(
        self,
        *,
        run_id: str,
        expected_manifest_sha256: str,
        expected_suite_id: str | None = None,
        expected_suite_revision: int | None = None,
    ) -> EvaluationRunSummary:
        """Read and verify a run summary against expected identity.

        Verifies the summary against:
        - Expected manifest SHA-256
        - Expected suite ID (optional)
        - Expected suite revision (optional)
        - Persisted run.json (run ID, suite ID, suite revision, manifest hash,
          scenario IDs, status, code commit SHA, database backend)

        Raises:
            RunSummaryNotFoundError: Summary file does not exist or run.json does not exist.
            RunSummaryInvalidError: Summary JSON is malformed.
            RunIdentityMismatchError: Summary identity does not match expected.
            RunManifestMismatchError: Summary manifest hash does not match.
            RunSummaryStatusInvalidError: Summary status vs run.json inconsistency.
        """
        _validate_run_id(run_id)
        run_dir = _resolve_run_directory(self._base, run_id)
        summary_path = run_dir / "summary.json"

        if not summary_path.exists():
            raise RunSummaryNotFoundError(
                code="EVAL_RUN_SUMMARY_NOT_FOUND",
                message=f"Summary file not found for run '{run_id}'",
            )

        try:
            raw_summary: dict[str, Any] = json.loads(summary_path.read_text("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RunSummaryInvalidError(
                code="EVAL_RUN_SUMMARY_INVALID",
                message=f"Summary JSON is invalid for run '{run_id}': {exc}",
            ) from exc

        # Strict conversion to typed model (calls validate_run_summary internally)
        summary = _dict_to_summary_strict(raw_summary)

        # Validate identity against expected parameters
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

        # Verify complete identity against persisted run.json (via strict decoder)
        persisted = _load_run_json_strict(run_dir, run_id)
        _verify_summary_against_run_meta(run_id, summary, _context_to_dict(persisted))

        return summary

    def run_dir(self, run_id: str) -> Path:
        """Get the secure resolved directory path for a given run ID.

        Validates the run ID format and ensures the resolved path stays
        under the configured base directory.
        """
        return _resolve_run_directory(self._base, run_id)

    @staticmethod
    def _allowed_transitions(current: RunStatus, next_status: RunStatus) -> bool:
        transitions = {
            RunStatus.CREATED: {RunStatus.RUNNING},
            RunStatus.RUNNING: {RunStatus.PASSED, RunStatus.FAILED, RunStatus.ABORTED},
        }
        return next_status in transitions.get(current, set())


# ── Identity verification helpers ──────────────────────────────────


def _verify_context_against_run_meta(
    context: EvaluationRunContext,
    run_meta: dict[str, Any],
) -> None:
    """Verify that a context matches persisted run.json metadata.

    Checks every identity field that should be cross-referenced, including
    ``database_backend``.
    Raises:
        RunIdentityMismatchError: On any field mismatch.
    """
    fields_to_check = [
        ("run_id", context.run_id, run_meta.get("run_id", "")),
        ("suite_id", context.suite_id, run_meta.get("suite_id", "")),
        ("suite_revision", context.suite_revision, run_meta.get("suite_revision", -1)),
        ("manifest_sha256", context.manifest_sha256, run_meta.get("manifest_sha256", "")),
        ("status", context.status.value, run_meta.get("status", "")),
        ("started_at", context.started_at, run_meta.get("started_at", "")),
    ]
    for field_name, ctx_val, run_val in fields_to_check:
        if ctx_val != run_val:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(f"Context {field_name} '{ctx_val}' does not match run.json '{run_val}'"),
                field=field_name,
            )

    # Scenario IDs
    run_scenario_ids = tuple(run_meta.get("scenario_ids", []))
    if context.scenario_ids != run_scenario_ids:
        raise RunIdentityMismatchError(
            code="EVAL_RUN_IDENTITY_MISMATCH",
            message="Context scenario_ids differ from run.json",
            field="scenario_ids",
        )

    # Code commit sha — exact comparison, no or "" coercion
    if context.code_commit_sha != run_meta.get("code_commit_sha"):
        raise RunIdentityMismatchError(
            code="EVAL_RUN_IDENTITY_MISMATCH",
            message=(
                f"Context code_commit_sha '{context.code_commit_sha}' "
                f"does not match run.json '{run_meta.get('code_commit_sha')}'"
            ),
            field="code_commit_sha",
        )

    # Database backend (P0-2 addition)
    ctx_db = context.database_backend
    run_db = run_meta.get("database_backend")
    if ctx_db != run_db:
        raise RunIdentityMismatchError(
            code="EVAL_RUN_IDENTITY_MISMATCH",
            message=f"Context database_backend '{ctx_db}' does not match run.json '{run_db}'",
            field="database_backend",
        )


def _verify_summary_against_run_meta(
    run_id: str,
    summary: EvaluationRunSummary,
    run_meta: dict[str, Any],
) -> None:
    """Verify summary against persisted run.json metadata.

    Checks every identity field that can be cross-referenced.
    """
    fields_to_check = [
        ("run_id", summary.run_id, run_meta.get("run_id", "")),
        ("suite_id", summary.suite_id, run_meta.get("suite_id", "")),
        ("manifest_sha256", summary.manifest_sha256, run_meta.get("manifest_sha256", "")),
    ]
    for field_name, summary_val, run_val in fields_to_check:
        if summary_val != run_val:
            raise RunIdentityMismatchError(
                code="EVAL_RUN_IDENTITY_MISMATCH",
                message=(
                    f"Summary {field_name} '{summary_val}' does not match run.json '{run_val}'"
                ),
                field=field_name,
            )

    # Code commit sha — exact comparison, no or "" coercion
    if summary.code_commit_sha != run_meta.get("code_commit_sha"):
        raise RunIdentityMismatchError(
            code="EVAL_RUN_IDENTITY_MISMATCH",
            message=(
                f"Summary code_commit_sha '{summary.code_commit_sha}' "
                f"does not match run.json '{run_meta.get('code_commit_sha')}'"
            ),
            field="code_commit_sha",
        )

    # Suite revision
    if summary.suite_revision != run_meta.get("suite_revision"):
        raise RunIdentityMismatchError(
            code="EVAL_RUN_IDENTITY_MISMATCH",
            message=(
                f"Summary suite_revision {summary.suite_revision} "
                f"does not match run.json '{run_meta.get('suite_revision')}'"
            ),
            field="suite_revision",
        )

    # Scenario IDs
    run_scenario_ids = tuple(run_meta.get("scenario_ids", []))
    if summary.scenario_ids != run_scenario_ids:
        raise RunIdentityMismatchError(
            code="EVAL_RUN_IDENTITY_MISMATCH",
            message="Summary scenario_ids differ from run.json",
            field="scenario_ids",
        )

    # Passed consistency
    run_status_str = run_meta.get("status", "")
    if summary.status.value != run_status_str:
        raise RunSummaryStatusInvalidError(
            code="EVAL_RUN_SUMMARY_STATUS_INVALID",
            message=(
                f"Summary status '{summary.status.value}' does not match "
                f"run.json status '{run_status_str}'"
            ),
            field="status",
        )
    if summary.passed and run_status_str != "passed":
        raise RunSummaryStatusInvalidError(
            code="EVAL_RUN_SUMMARY_STATUS_INVALID",
            message=(f"Summary claims passed but run.json status is '{run_status_str}'"),
            field="status",
        )

    # Database backend is not directly accessible from summary;
    # it is validated via run.json in _load_run_json_strict and
    # _verify_context_against_run_meta during write paths.


# ── Generator, I/O, serialisation helpers ─────────────────────────


def _generate_run_id() -> str:
    """Generate a unique, compact run ID."""
    return uuid.uuid4().hex[:12]


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write data atomically to a JSON file.

    Uses open/write/flush/fsync/close + os.replace for crash safety.
    """
    tmp = path.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
    try:
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        with open(tmp, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(path))
        # fsync parent directory
        parent_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
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


def _dict_to_summary_strict(value: object) -> EvaluationRunSummary:
    """Convert a deserialized JSON value to a typed summary with strict validation.

    Accepts only a ``dict`` root.  Rejects unknown fields, wrong types,
    and structurally invalid data.
    Delegates contract invariants to ``validate_run_summary()``.
    """
    # Reject non-dict root
    if not isinstance(value, dict):
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=(f"Summary root must be a dict, got {type(value).__name__}"),
            field="$",
        )

    d: dict[str, Any] = value
    # Reject unknown root-level fields
    extra = set(d) - _KNOWN_SUMMARY_FIELDS
    if extra:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Unknown summary fields: {sorted(extra)}",
            field="$",
        )

    try:

        def _expect_string(v: object, field: str) -> str:
            if not isinstance(v, str):
                raise TypeError(f"Expected str for '{field}', got {type(v).__name__}")
            return v

        def _expect_int(v: object, field: str) -> int:
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError(f"Expected int for '{field}', got {type(v).__name__}")
            return v

        def _expect_bool(v: object, field: str) -> bool:
            if not isinstance(v, bool):
                raise TypeError(f"Expected bool for '{field}', got {type(v).__name__}")
            return v

        run_id = _expect_string(d.get("run_id"), "run_id")
        suite_id = _expect_string(d.get("suite_id"), "suite_id")
        suite_revision = _expect_int(d.get("suite_revision"), "suite_revision")
        manifest_sha256 = _expect_string(d.get("manifest_sha256"), "manifest_sha256")
        status_str = _expect_string(d.get("status"), "status")
        status = RunStatus(status_str)
        completed_at = _expect_string(d.get("completed_at", ""), "completed_at")
        passed = _expect_bool(d.get("passed"), "passed")
        code_commit_sha_raw = d.get("code_commit_sha")
        if code_commit_sha_raw is not None:
            ccs = _expect_string(code_commit_sha_raw, "code_commit_sha")
            if not ccs.strip():
                raise RunIdentityValidationIssue(
                    field="code_commit_sha",
                    message=f"code_commit_sha must be non-empty, got {ccs!r}",
                )
            code_commit_sha: str | None = ccs
        else:
            code_commit_sha = None

        scenario_ids_raw = d.get("scenario_ids", [])
        if not isinstance(scenario_ids_raw, list):
            raise TypeError(
                f"Expected list for 'scenario_ids', got {type(scenario_ids_raw).__name__}"
            )
        scenario_ids = tuple(_expect_string(s, "scenario_ids[]") for s in scenario_ids_raw)

        scenario_results_raw = d.get("scenario_results", [])
        if not isinstance(scenario_results_raw, list):
            raise TypeError(
                f"Expected list for 'scenario_results', got {type(scenario_results_raw).__name__}"
            )

        scenario_results_list: list[ScenarioRunSummary] = []
        for sr in scenario_results_raw:
            if not isinstance(sr, dict):
                raise TypeError(f"Expected dict for scenario_result, got {type(sr).__name__}")

            # Reject unknown fields inside scenario result objects
            extra_sr = set(sr) - _KNOWN_RESULT_FIELDS
            if extra_sr:
                raise ValueError(f"Unknown scenario result fields: {sorted(extra_sr)}")

            sr_id = _expect_string(sr.get("scenario_id"), "scenario_result.scenario_id")
            sr_passed = _expect_bool(sr.get("passed"), "scenario_result.passed")
            checks_total = _expect_int(sr.get("checks_total"), "scenario_result.checks_total")
            checks_passed = _expect_int(sr.get("checks_passed"), "scenario_result.checks_passed")
            checks_failed = _expect_int(sr.get("checks_failed"), "scenario_result.checks_failed")

            scenario_results_list.append(
                ScenarioRunSummary(
                    scenario_id=sr_id,
                    passed=sr_passed,
                    checks_total=checks_total,
                    checks_passed=checks_passed,
                    checks_failed=checks_failed,
                )
            )

        summary = EvaluationRunSummary(
            run_id=run_id,
            suite_id=suite_id,
            suite_revision=suite_revision,
            manifest_sha256=manifest_sha256,
            scenario_ids=scenario_ids,
            status=status,
            completed_at=completed_at,
            code_commit_sha=code_commit_sha,
            passed=passed,
            scenario_results=tuple(scenario_results_list),
        )
    except (ValueError, TypeError, KeyError, AssertionError) as exc:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=f"Summary structure is invalid: {exc}",
            field="$",
        ) from exc
    except RunIdentityValidationIssue as exc:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=exc.message,
            field=exc.field,
        ) from exc

    # Run shared identity validation on suite/scenario fields
    try:
        validate_run_identity_values(
            RunIdentityValues(
                suite_id=suite_id,
                suite_revision=suite_revision,
                manifest_sha256=manifest_sha256,
                scenario_ids=scenario_ids,
                database_backend=None,
                code_commit_sha=code_commit_sha,
            )
        )
    except RunIdentityValidationIssue as exc:
        raise RunSummaryInvalidError(
            code="EVAL_RUN_SUMMARY_INVALID",
            message=exc.message,
            field=exc.field,
        ) from exc

    # Run contract invariants via the centralised validator.
    # For read-back we allow the stored status (may be terminal only).
    validate_run_summary(summary, declared_scenario_ids=scenario_ids, allow_running=False)

    return summary
