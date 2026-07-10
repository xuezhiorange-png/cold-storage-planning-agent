"""Evaluation runner package (Task 11B Phase B Path A — Implementation Slice A1.5).

This package hosts the Task 11B Phase B evaluation runner stack, layered
on top of the production orchestrator's canonical entry point
``compose_production_scheme_service(session_factory)`` (per pre-freeze
contract §1.3 #1 + §4.1).

Public API re-exports:

* :func:`execute_scenario` — A1-2a adapter surface (ratified by
  Amendment 2 of ``docs/tasks/TASK-011B-path-a-design-ratification.md``
  §13). Reads-only FK references to pre-existing production rows plus
  the two mandatory Phase-1 input fields.

* :func:`run_scenario` — A1.5 evaluation runner surface. Same A1-2a
  input contract; delegates to the production
  ``ProductionSchemeService.generate_production_scheme_run``; returns
  a typed :class:`ScenarioOutcome`. The runner does NOT raise
  ``PhaseBBlockedError`` on the happy path.

* :class:`AdapterResult` — read-only dataclass for the A1-2a adapter.

* :class:`ScenarioOutcome` — read-only dataclass for the A1.5 runner.

* :class:`AdapterInputError` / :class:`InvalidEvaluationScenarioError` /
  :class:`EvaluationRunnerContractViolationError` /
  :class:`PhaseBBlockedError` / :class:`EvaluationRunnerError` —
  typed errors. Downstream code classifies by the ``code`` attribute
  (forbidden-pattern list: no message-text parsing).

* :class:`RunDirectory` — deterministic per-scenario run-directory
  layout helper.

* :func:`main` — CLI entry point (``cold-storage-evaluation-run``).

Forbidden behaviors (enforced by architecture tests + this module's
docstring):

- DO NOT raise any error on the happy path.
- DO NOT restore ``production_seeding.py`` (pre-freeze §5.1 / §8 #1).
- DO NOT bypass ``compose_production_scheme_service`` (pre-freeze
  §8 #6).
- DO NOT introduce demo / latest-row / partial-binding fallbacks.
- DO NOT suppress, rename, downgrade, or reclassify
  ``requires_review`` warnings.
- DO NOT alter production formulas / coefficient values / scoring
  rules / review rules / thresholds / weights.
- DO NOT parse exception message text to make business decisions
  (pre-freeze §1.5 / Phase 4 §9 forbidden-pattern list).

See :mod:`cold_storage.evaluation.adapter` for the A1-2a adapter
implementation, :mod:`cold_storage.evaluation.execute` for the A1.5
runner, :mod:`cold_storage.evaluation.errors` for the typed error
classes, :mod:`cold_storage.evaluation.run_directory` for the
per-scenario path layout, and :mod:`cold_storage.evaluation.cli` for
the CLI surface.
"""

from __future__ import annotations

from cold_storage.evaluation.adapter import (
    AdapterInputError,
    AdapterResult,
    execute_scenario,
)
from cold_storage.evaluation.cli import main as main
from cold_storage.evaluation.errors import (
    EvaluationRunnerContractViolationError,
    EvaluationRunnerError,
    InvalidEvaluationScenarioError,
    PhaseBBlockedError,
    is_evaluation_runner_error,
)
from cold_storage.evaluation.execute import (
    HISTORICAL_BLOCKED_UPSTREAM_CODES,
    Outcome,
    ScenarioOutcome,
    VALID_DATABASE_BACKENDS,
    run_scenario,
)
from cold_storage.evaluation.run_directory import (
    RunDirectory,
    execute_in_run_directory,
)

__all__ = [
    # A1-2a adapter surface (PR #49)
    "AdapterInputError",
    "AdapterResult",
    "execute_scenario",
    # A1.5 runner surface (this round)
    "Outcome",
    "ScenarioOutcome",
    "run_scenario",
    "execute_in_run_directory",
    "HISTORICAL_BLOCKED_UPSTREAM_CODES",
    "VALID_DATABASE_BACKENDS",
    "RunDirectory",
    "main",
    # Typed error surface
    "EvaluationRunnerError",
    "InvalidEvaluationScenarioError",
    "EvaluationRunnerContractViolationError",
    "PhaseBBlockedError",
    "is_evaluation_runner_error",
]