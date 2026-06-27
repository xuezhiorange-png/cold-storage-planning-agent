"""Isolated run directory management with stale-output protection."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cold_storage.evaluation.errors import (
    RunDirectoryExistsError,
    RunStateError,
)
from cold_storage.evaluation.models import RunStatus


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
    ) -> EvaluationRunContext:
        """Create a new unique run directory.

        Returns the run context.  Raises ``RunDirectoryError`` if the
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
        )
        _atomic_write(self._base / context.run_id / "run.json", _context_to_dict(updated))
        return updated

    def write_summary(
        self,
        context: EvaluationRunContext,
        summary: dict[str, Any],
    ) -> None:
        """Write a final summary.json for the run.

        The write is atomic (temp file + rename).  Only allowed when
        the run status is ``RUNNING``, ``PASSED``, or ``FAILED``.
        """
        if context.status not in (RunStatus.RUNNING, RunStatus.PASSED, RunStatus.FAILED):
            raise RunStateError(
                code="EVAL_RUN_STATE_INVALID",
                message=f"Cannot write summary in status '{context.status.value}'",
            )
        _atomic_write(self._base / context.run_id / "summary.json", summary)

    def read_summary(self, run_id: str) -> dict[str, Any] | None:
        """Read summary.json for a given run ID.

        Returns ``None`` if the file does not exist.
        """
        path = self._base / run_id / "summary.json"
        if not path.exists():
            return None
        result: Any = json.loads(path.read_text("utf-8"))
        return cast("dict[str, Any]", result)

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
    """Write data atomically to a JSON file."""
    tmp = path.with_suffix(".tmp")
    content = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    tmp.write_bytes(content)
    tmp.rename(path)


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
    }
