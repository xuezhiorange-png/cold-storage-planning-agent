"""Evaluation runner errors (Task 11B Phase B Path A — Implementation Slice A1.5).

This module defines the typed exceptions raised by the evaluation
runner (:mod:`cold_storage.evaluation.execute`). It is the successor
of the legacy ``EvaluationPrerequisiteMissingError`` class that the
pre-freeze contract §1.3 #2 designates for migration to a documented
historical contract.

Migration history
=================

The legacy ``EvaluationPrerequisiteMissingError`` was a hard
always-raise gate that PR #21's evaluation runner (the now-superseded
``codex/task-11-evaluation`` branch) used to block every evaluation
scenario on the supposed "production pipeline prerequisite gap". The
gate was rejected by the independent engineering review during the
Round 11 reversal because it fabricated a failure condition that the
production path does not actually encounter post-Issue #35.

Post-Issue #35 close
=====================

After Issue #35 closure on 2026-07-08 and the subsequent Phase 4
implementation merge, the production pipeline prerequisite that the
legacy gate claimed to be missing no longer exists. The evaluation
runner therefore MUST NOT raise ``EvaluationPrerequisiteMissingError``
on the happy path; that error class is reserved as a documented
historical contract for downstream code that explicitly wants to
distinguish the historical Phase 11B Round 12 reversal from a real
upstream prerequisite failure.

This module therefore provides:

- :class:`PhaseBBlockedError` — the documented historical contract.
  Raised ONLY when the upstream evaluation harness (or the production
  orchestrator's typed exception) explicitly flags a real upstream
  prerequisite failure that the production path cannot recover from
  in a single evaluation invocation (e.g., schema migration missing,
  identity repository unreachable, weight-set revision not approved).
  NEVER raised on the happy path.

- :class:`EvaluationRunnerError` — the umbrella typed base class for
  all evaluation-runner errors. Subclasses are typed and carry a
  machine-readable ``code`` attribute; downstream code MUST NOT parse
  exception ``str()`` text to make business decisions (pre-freeze
  §1.5 / Phase 4 §9 forbidden-pattern list).

- :func:`is_evaluation_runner_error` — helper for the test-side
  architecture-test suite to assert that a raised exception is one of
  the runner's typed errors.

Forbidden behaviors
===================

- DO NOT raise any error on the happy path. The runner delegates to
  ``compose_production_scheme_service(session_factory)``; the
  production service may itself raise a typed production-side error,
  which the runner forwards unchanged (per pre-freeze §5.5 and
  Path A §13.5).
- DO NOT parse exception message text to make business decisions.
- DO NOT introduce any class that fabricates a "blocked" outcome when
  the production service succeeded.
- DO NOT restore ``production_seeding.py`` (pre-freeze §5.1).
- DO NOT bypass ``compose_production_scheme_service`` (pre-freeze §8 #6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class EvaluationRunnerError(Exception):
    """Base class for all evaluation-runner typed errors.

    Downstream code (CLI, run-directory, test harness) MUST catch this
    base class — NOT ``Exception`` — to classify runner-side failures.

    The ``code`` attribute carries a machine-readable identifier that
    is the SINGLE contract surface for typed errors. The ``str(args)``
    representation is for humans only and is NOT part of the contract.
    """

    code: str = "EVALUATION_RUNNER_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self._message = message
        self.details: dict[str, Any] = dict(details) if details else {}

    @property
    def message(self) -> str:
        """Human-readable message (not part of the contract)."""
        return self._message


class PhaseBBlockedError(EvaluationRunnerError):
    """Documented historical contract — Round 12 reversal sentinel.

    This error class is the documented successor to the legacy
    ``EvaluationPrerequisiteMissingError`` class that PR #21's
    evaluation runner used to block every scenario. The pre-freeze
    contract §1.3 #2 mandates migrating the legacy class to a
    "documented historical contract" or removing it entirely; this
    module chooses the documented-historical-contract path because
    the existing architecture test in
    :mod:`backend.tests.architecture.test_task_011b_phase2_boundaries`
    asserts that no application file imports ``production_seeding.py``
    and a typed sentinel preserves that audit invariant.

    The runner MUST NOT raise this class on the happy path. The
    runner raises it ONLY when an explicit upstream prerequisite is
    actually missing — for example, when the upstream production
    orchestrator's ``MissingApprovedCoefficientError`` propagates
    through to the runner, or when the test harness seeds an
    explicitly-unapproved weight-set revision and asserts the runner's
    failure path.

    The error carries a ``code`` attribute that downstream code uses
    for typed classification. Downstream code MUST NOT parse the
    ``str(args)`` to decide what to do.
    """

    code = "PHASE_B_BLOCKED"

    def __init__(
        self,
        message: str,
        *,
        upstream_code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        # The upstream_code captures the production-side error class
        # identifier that triggered the historical sentinel (e.g.
        # "MISSING_APPROVED_COEFFICIENT"). It is part of the contract.
        self.upstream_code: str | None = upstream_code


class InvalidEvaluationScenarioError(EvaluationRunnerError):
    """Typed error for invalid evaluation inputs.

    Raised when the runner is asked to execute a scenario whose
    scenario_id, source_binding_id, weight_set_revision_id,
    correlation_id, or database_backend value violates the runner's
    input contract. The runner validates inputs at the entry boundary
    and raises this error before touching the session_factory or any
    production orchestrator.
    """

    code = "INVALID_EVALUATION_SCENARIO"


class EvaluationRunnerContractViolationError(EvaluationRunnerError):
    """Typed error for the runner violating its own contract.

    Raised when the runner's pre-conditions (e.g., a required
    composition root is not wired) are not satisfied. This is a
    programmer error, not a business failure; downstream code treats
    it as a hard abort.
    """

    code = "EVALUATION_RUNNER_CONTRACT_VIOLATION"


def is_evaluation_runner_error(exc: BaseException) -> bool:
    """Return True iff ``exc`` is one of the runner's typed errors.

    Architecture-test friendly: accepts any BaseException and returns
    a boolean (no exception raised). Used by the runner's own tests
    and by the forbidden-pattern architecture test.
    """
    return isinstance(exc, EvaluationRunnerError)


__all__ = [
    "EvaluationRunnerError",
    "PhaseBBlockedError",
    "InvalidEvaluationScenarioError",
    "EvaluationRunnerContractViolationError",
    "is_evaluation_runner_error",
]