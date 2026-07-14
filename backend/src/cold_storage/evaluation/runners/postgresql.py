"""PostgreSQL backend runner (TASK-011C C-2 runner authority).

This module is the C-2 backend composition for the PostgreSQL
backend. It mirrors :mod:`.sqlite` exactly, with a
PostgreSQL-typed session factory. The runner does NOT
duplicate comparison / canonicalization / D10 / artifact
logic.

Backend identity: ``DatabaseBackend.POSTGRESQL``. The runner
emits the same typed cross-backend parity contract as the
SQLite runner — the same manifest executed against this
runner and against the SQLite runner MUST produce
equivalent ``RunRecord`` outcomes (modulo backend-specific
runtime metadata, which the canonicalizer strips before
normalization).
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
class PostgreSQLRunnerConfig:
    """Typed configuration for the PostgreSQL backend runner.

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
    (``PostgreSQLRunnerConfig`` always carries the
    PostgreSQL identity). The runner enforces this
    invariant at the entry boundary.
    """

    session_factory: Callable[[], Any]


def run_postgresql_suite(
    *,
    manifest: Manifest,
    root: Path,
    config: PostgreSQLRunnerConfig,
    commit_sha: str = "unknown",
) -> SuiteRunResult:
    """Run the V1 suite against the PostgreSQL backend.

    The runner wires the PostgreSQL session factory to the
    suite runner (:func:`evaluate_manifest`) and returns the
    typed :class:`SuiteRunResult`. The runner does NOT
    close the session factory; the caller is responsible
    for the session lifecycle.

    Parameters
    ----------
    manifest:
        The validated V1 manifest.
    root:
        The target root directory for the per-scenario
        artifacts. The runner raises
        :class:`StaleEvaluationArtifactsError` if any
        managed artifact already exists at ``root``.
    config:
        The typed PostgreSQL runner configuration. The
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
    if not isinstance(config, PostgreSQLRunnerConfig):
        raise EvaluationRunnerError(
            "run_postgresql_suite requires a PostgreSQLRunnerConfig instance.",
            details={"config_type": type(config).__name__},
        )
    if config.session_factory is None:
        raise EvaluationInfrastructureError(
            "run_postgresql_suite received a None session_factory.",
        )
    return evaluate_manifest(
        manifest=manifest,
        root=root,
        session_factory=config.session_factory,
        commit_sha=commit_sha,
    )


__all__ = [
    "PostgreSQLRunnerConfig",
    "run_postgresql_suite",
]
