"""SQLite backend runner (TASK-011C C-2 runner authority).

This module is the C-2 backend composition for the SQLite
backend. It is a thin wrapper that wires a SQLite session
factory to :func:`evaluate_manifest`. It does NOT duplicate
comparison / canonicalization / D10 / artifact logic.

The default session factory is the test-side
``a1_session_factory`` from
:mod:`tests.evaluation._seed_helpers`. The session factory
is used by the suite runner to invoke the production
adapter (which uses the A1-2a path).

Backend identity: ``DatabaseBackend.SQLITE``. Cross-backend
parity is asserted by the suite runner — the same manifest
executed against this runner and against the PostgreSQL
runner MUST produce equivalent ``RunRecord`` outcomes
(modulo backend-specific runtime metadata, which the
canonicalizer strips before normalization).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cold_storage.evaluation.errors import (
    EvaluationInfrastructureError,
    EvaluationRunnerError,
)
from cold_storage.evaluation.evaluate import SuiteRunResult, evaluate_manifest
from cold_storage.evaluation.models import Manifest


@dataclass(frozen=True, slots=True)
class SQLiteRunnerConfig:
    """Typed configuration for the SQLite backend runner.

    Attributes
    ----------
    session_factory:
        A zero-arg callable that returns a SQLAlchemy
        ``Session`` (``sessionmaker`` is the canonical
        instance). The factory is owned by the caller; the
        runner does NOT close the session.

    Notes
    -----
    The backend identity (the canonical
    :class:`DatabaseBackend` enum value) is NOT a field on
    this config: it is implied by the runner type
    (``SQLiteRunnerConfig`` always carries the SQLite
    identity). The runner enforces this invariant at the
    entry boundary.
    """

    session_factory: Callable[[], Any]


def run_sqlite_suite(
    *,
    manifest: Manifest,
    manifest_root: Path,
    root: Path,
    config: SQLiteRunnerConfig,
    commit_sha: str = "unknown",
) -> SuiteRunResult:
    """Run the V1 suite against the SQLite backend.

    The runner wires the SQLite session factory to the suite
    runner (:func:`evaluate_manifest`) and returns the typed
    :class:`SuiteRunResult`. The runner does NOT close the
    session factory; the caller is responsible for the
    session lifecycle.

    Parameters
    ----------
    manifest:
        The validated V1 manifest.
    manifest_root:
        The root directory for resolving the manifest's
        referenced files. The runner forwards the value to
        :func:`evaluate_manifest` unchanged; the runner does
        NOT default to ``Path(".")`` (per review 4693931575
        P0-3). The boundary ownership of this value lives at
        the runner layer (not the suite runner).
    root:
        The target root directory for the per-scenario
        artifacts. The runner raises
        :class:`StaleEvaluationArtifactsError` if any
        managed artifact already exists at ``root``.
    config:
        The typed SQLite runner configuration. The
        ``session_factory`` is the only required field.
    commit_sha:
        The git commit SHA that bound this run. Stored in
        the :class:`SummaryRecord` for downstream trace.

    Returns
    -------
    SuiteRunResult
        The typed suite result.

    Raises
    ------
    EvaluationRunnerError (or subclass)
        On any infrastructure / artifact / manifest failure.
    """
    if not isinstance(config, SQLiteRunnerConfig):
        raise EvaluationRunnerError(
            "run_sqlite_suite requires a SQLiteRunnerConfig instance.",
            details={"config_type": type(config).__name__},
        )
    if config.session_factory is None:
        raise EvaluationInfrastructureError(
            "run_sqlite_suite received a None session_factory.",
        )
    if not isinstance(manifest_root, Path):
        # Defense-in-depth: enforce the contract at the
        # boundary even though ``evaluate_manifest`` will
        # also enforce it.
        raise EvaluationRunnerError(
            "run_sqlite_suite requires an explicit manifest_root: Path "
            "argument; the historical Path('.') default was removed per "
            "review 4693931575 P0-3.",
            details={"manifest_root_type": type(manifest_root).__name__},
        )
    return evaluate_manifest(
        manifest=manifest,
        manifest_root=manifest_root,
        root=root,
        session_factory=config.session_factory,
        commit_sha=commit_sha,
    )


__all__ = [
    "SQLiteRunnerConfig",
    "run_sqlite_suite",
]
