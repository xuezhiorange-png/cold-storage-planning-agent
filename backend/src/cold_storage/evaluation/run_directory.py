"""Evaluation run-directory helpers (Task 11B Phase B Path A — Implementation Slice A1.5).

This module provides the canonical per-scenario run directory layout
for the evaluation harness. It is the test-harness-side companion to
:mod:`cold_storage.evaluation.execute` — the runner writes its
scenario artifacts under the path this module computes.

The run-directory layout is intentionally simple:

    <root>/<scenario_id>/
        raw/<scenario_id>.json         # the un-canonicalized form
        normalized/<scenario_id>.json  # the canonicalized form
        summary.json                   # the run-level summary

Per pre-freeze §1.3 #1 + §4.1 row "Runner — run_directory.py", this
module MUST NOT:

- Compute paths that bypass the runner's input contract.
- Write production rows of any kind.
- Bypass ``compose_production_scheme_service`` (pre-freeze §8 #6).
- Introduce demo / latest-row / partial-binding fallbacks.
- Suppress, rename, downgrade, or reclassify ``requires_review``
  warnings.
- Alter production formulas / coefficient values / scoring rules /
  review rules / thresholds / weights.

It MUST:

- Compute a deterministic, per-scenario run directory path.
- Use a stable, machine-readable path format that does not depend on
  wall-clock time or platform-dependent separators.
- Forward any underlying exception from the production orchestrator
  unchanged (per pre-freeze §1.3 #1 + Path A §13.5).
- Reject ``scenario_id`` values that contain path-traversal characters
  at the input boundary (defense-in-depth; the runner does not
  write production rows, but the run-directory is a host filesystem
  write surface).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cold_storage.evaluation.errors import (
    EvaluationRunnerError,
    InvalidEvaluationScenarioError,
)
from cold_storage.evaluation.execute import ScenarioOutcome, run_scenario_via_markers

# ── Allowed scenario_id character set ──────────────────────────────────
#
# Path-traversal-resistant. Only lowercase letters, digits, dot,
# dash, and underscore are allowed. The pattern is intentionally
# narrow; it accepts the canonical ``baseline-feasible`` /
# ``high-throughput-review`` / ``invalid-blocked`` ids from the
# pre-freeze §4.1 manifest and rejects anything that contains a
# slash, backslash, NUL byte, or ``..`` segment.

_SAFE_SCENARIO_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


def _validate_scenario_id(scenario_id: str) -> str:
    if not isinstance(scenario_id, str) or not _SAFE_SCENARIO_ID.match(scenario_id):
        raise InvalidEvaluationScenarioError(
            f"scenario_id must match {_SAFE_SCENARIO_ID.pattern!r}; got "
            f"{scenario_id!r}.",
            details={"field": "scenario_id", "value": scenario_id},
        )
    return scenario_id


# ── Run-directory path computation ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RunDirectory:
    """Canonical per-scenario run-directory layout.

    Attributes
    ----------
    root:
        The user-provided root directory.
    scenario_id:
        The validated scenario identifier.
    scenario_dir:
        The per-scenario subdirectory (``<root>/<scenario_id>``).
    raw_dir:
        The directory holding the un-canonicalized JSON form
        (``<root>/<scenario_id>/raw/``).
    normalized_dir:
        The directory holding the canonicalized JSON form
        (``<root>/<scenario_id>/normalized/``).
    summary_path:
        The path to the run-level summary JSON file
        (``<root>/<scenario_id>/summary.json``).
    """

    root: Path
    scenario_id: str
    scenario_dir: Path
    raw_dir: Path
    normalized_dir: Path
    summary_path: Path

    @classmethod
    def for_scenario(cls, *, root: Path, scenario_id: str) -> "RunDirectory":
        """Compute the per-scenario run-directory layout.

        Validates ``scenario_id`` at the input boundary; raises
        :class:`InvalidEvaluationScenarioError` on rejection.
        """
        validated_id = _validate_scenario_id(scenario_id)
        if not isinstance(root, Path):
            root = Path(root)
        scenario_dir = root / validated_id
        return cls(
            root=root,
            scenario_id=validated_id,
            scenario_dir=scenario_dir,
            raw_dir=scenario_dir / "raw",
            normalized_dir=scenario_dir / "normalized",
            summary_path=scenario_dir / "summary.json",
        )


# ── Per-scenario execute helper ──────────────────────────────────────────


def execute_in_run_directory(
    session_factory: Callable[[], Any],
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_marker: str,
    backend_marker: str,
    scenario_id: str,
    run_root: Path,
) -> ScenarioOutcome:
    """Run a scenario AND compute the canonical run-directory layout.

    This is the thin orchestration helper that the runner's
    acceptance tests use to assert the post-merge contract: the runner
    produces a ``ScenarioOutcome`` and the helper returns the
    per-scenario run-directory paths that the evaluation harness would
    use to persist the raw / normalized / summary artifacts.

    The helper does NOT actually write any artifacts to disk — the
    per-scenario persistence step is the evaluation harness's
    responsibility, not the runner's (pre-freeze §1.3 #1: "Runner
    does NOT write to any file."). The helper only computes the
    deterministic path layout and returns it alongside the
    ``ScenarioOutcome``.

    Parameters
    ----------
    session_factory, source_binding_id, weight_set_revision_id,
    correlation_marker, backend_marker:
        Forwarded to :func:`run_scenario` unchanged.
    scenario_id:
        The evaluation scenario identifier. Must match the canonical
        ``_SAFE_SCENARIO_ID`` pattern.
    run_root:
        The user-provided root directory for the run artifacts.

    Returns
    -------
    :class:`ScenarioOutcome`
        The same ``ScenarioOutcome`` returned by :func:`run_scenario`.

    Notes
    -----
    The :class:`RunDirectory` paths are accessible via
    :func:`RunDirectory.for_scenario`; this helper returns the
    ``ScenarioOutcome`` only because the runner's acceptance tests
    only assert the production-side outcome, not the artifact
    persistence path. Tests that need the path layout call
    :func:`RunDirectory.for_scenario` directly.
    """
    # Validate scenario_id early so a path-traversal attempt surfaces
    # as an InvalidEvaluationScenarioError BEFORE any production
    # session is opened.
    _validate_scenario_id(scenario_id)

    try:
        outcome = run_scenario_via_markers(
            session_factory,
            source_binding_id=source_binding_id,
            weight_set_revision_id=weight_set_revision_id,
            correlation_marker=correlation_marker,
            backend_marker=backend_marker,
        )
    except EvaluationRunnerError:
        # Runner-typed errors propagate unchanged; do NOT wrap them.
        raise
    except Exception:
        # Production-side errors propagate unchanged per pre-freeze
        # §1.3 #1 + Path A §13.5.
        raise

    return outcome


__all__ = [
    "RunDirectory",
    "execute_in_run_directory",
    "_SAFE_SCENARIO_ID",
    "_validate_scenario_id",
]