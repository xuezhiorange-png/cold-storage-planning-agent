"""Typed exception classes for the evaluation runner.

Hierarchy:

* :class:`EvaluationRunnerError` — umbrella base class for every
  runner-specific exception. Distinct from production-side
  exceptions so the evaluation harness can classify runner errors
  separately from orchestrator errors.

* :class:`PhaseBBlockedError` — historical-blocked sentinel. The
  runner raises this ONLY when production raises one of the
  upstream error codes listed in
  :data:`cold_storage.evaluation.execute.HISTORICAL_BLOCKED_UPSTREAM_CODES`.
  Per pre-freeze §1.3 #2, this class is **documented as a
  historical contract** that records the Round 11/12 reversal
  without being raised on the happy path. The runner never raises
  it on a healthy production run; the happy path always succeeds
  with ``outcome=SUCCEEDED``.

* :class:`InvalidEvaluationScenarioError` — raised when the
  runner's input contract is violated (e.g., empty FK reference,
  invalid backend marker, malformed correlation marker).

* :class:`EvaluationRunnerContractViolationError` — raised when
  the runner detects a contract violation by production (e.g.,
  the production service returns a ``SchemeRun`` whose FK
  reference does not match the input FK reference).

* :func:`is_evaluation_runner_error` — distinguishes typed runner
  errors from generic exceptions. The runner + CLI use this
  classifier to dispatch to typed error codes; they NEVER parse
  exception message text to make business decisions (Phase 4 §9
  forbidden-pattern list).

The runner stack does NOT raise ``AdapterInputError`` — the
adapter raises that internally; the runner re-validates inputs
and raises :class:`InvalidEvaluationScenarioError` instead so
the runner's input boundary is classified independently from
the adapter's.
"""

from __future__ import annotations

from typing import Any


class EvaluationRunnerError(Exception):
    """Umbrella base class for every evaluation-runner-specific error.

    Distinct from production-side exceptions so the evaluation
    harness can classify runner errors separately from orchestrator
    errors. Subclasses MUST set the ``code`` class attribute to a
    stable, machine-readable identifier; downstream code classifies
    by ``code``, NEVER by parsing the exception ``str`` (per Phase 4
    §9 forbidden-pattern list).
    """

    code: str = "EVALUATION_RUNNER_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self._details: dict[str, Any] = dict(details) if details else {}

    @property
    def details(self) -> dict[str, Any]:
        """Read-only view of structured error details."""
        return dict(self._details)


class PhaseBBlockedError(EvaluationRunnerError):
    """Historical-blocked sentinel.

    The runner raises this ONLY when production raises one of the
    upstream error codes listed in
    :data:`cold_storage.evaluation.execute.HISTORICAL_BLOCKED_UPSTREAM_CODES`.
    The class is documented as a **historical contract** that records
    the Round 11/12 reversal (per pre-freeze §1.3 #2) without being
    raised on the happy path. The happy path always succeeds with
    ``outcome=SUCCEEDED``; this class is reserved for the narrow
    set of real production-side prerequisite failures enumerated
    in the runner's ``HISTORICAL_BLOCKED_UPSTREAM_CODES`` set.

    Downstream code MUST catch this via the typed ``code`` attribute
    (``"PHASE_B_BLOCKED"``), NEVER via the exception ``str`` (Phase 4
    §9 forbidden-pattern list).
    """

    code = "PHASE_B_BLOCKED"

    def __init__(
        self,
        message: str,
        *,
        upstream_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details: dict[str, Any] = dict(details) if details else {}
        if upstream_code is not None:
            merged_details.setdefault("upstream_code", upstream_code)
        super().__init__(message, details=merged_details)
        self.upstream_code: str | None = upstream_code


class InvalidEvaluationScenarioError(EvaluationRunnerError):
    """Raised when the runner's input contract is violated.

    Examples:

    - ``source_binding_id`` is not a non-empty string.
    - ``weight_set_revision_id`` is not a non-empty string.
    - ``correlation_marker`` is empty or whitespace-only.
    - ``backend_marker`` is not one of the allowed backend markers.

    The runner raises this at the entry boundary (before any
    production invocation). Downstream code catches it via the typed
    ``code`` attribute (``"INVALID_EVALUATION_SCENARIO"``).
    """

    code = "INVALID_EVALUATION_SCENARIO"


class EvaluationRunnerContractViolationError(EvaluationRunnerError):
    """Raised when the runner detects a production-side contract violation.

    Example: the production service returns a ``SchemeRun`` whose
    FK reference does not match the input FK reference. This is a
    defense-in-depth check (the production service is the canonical
    writer; the runner only surfaces the drift).
    """

    code = "EVALUATION_RUNNER_CONTRACT_VIOLATION"


def is_evaluation_runner_error(exc: BaseException) -> bool:
    """Return True if ``exc`` is a typed evaluation-runner error.

    Used by the CLI / harness to dispatch to typed error codes
    without parsing exception message text (Phase 4 §9
    forbidden-pattern list).
    """
    return isinstance(exc, EvaluationRunnerError)


# ── C-2 typed error classes (TASK-011C runner authority) ────────────────
#
# These classes are the C-2 runner's typed error surface. Each has a
# stable ``code`` attribute; downstream code classifies by ``code``,
# NEVER by parsing ``str(exc)`` (per Phase 4 §9 forbidden-pattern
# list). All subclasses inherit ``details`` from the umbrella
# :class:`EvaluationRunnerError`.


class EvaluationManifestExecutionError(EvaluationRunnerError):
    """Raised when manifest validation OR a manifest-driven manifest
    *execution* step fails BEFORE any FS/DB side effect.

    Distinct from :class:`InvalidEvaluationScenarioError` (which is
    a per-scenario input contract violation) and from the existing
    manifest loader errors (which live in
    :mod:`cold_storage.evaluation.manifest`). This class covers the
    runner's *executive* use of the manifest (e.g. cross-scenario
    consistency checks, missing-revision detection, mismatched
    backend identity between scenario and runner).
    """

    code = "EVALUATION_MANIFEST_EXECUTION_ERROR"


class EvaluationComparisonError(EvaluationRunnerError):
    """Raised when the manifest-driven comparison executor fails
    *outside* a normal ``passed=False`` comparison result.

    Normal expected-vs-actual mismatches return
    :class:`cold_storage.evaluation.compare.ComparisonResult` with
    ``passed=False`` and a populated ``diffs`` tuple. This class
    covers the *infrastructure* failures of the comparison layer
    (e.g. undeclared path, tolerance forbidden, canonicalizer
    rejection, etc.).
    """

    code = "EVALUATION_COMPARISON_ERROR"


class EvaluationInfrastructureError(EvaluationRunnerError):
    """Raised when a downstream infrastructure operation (DB session,
    filesystem write, network) fails during a runner call.

    Distinct from production-side errors (which the runner
    forwards unchanged per the A1 ownership boundary) and from
    *expected* production exceptions (e.g.
    :class:`cold_storage.modules.orchestration.application.production_calculation.errors.InvalidProjectInputError`
    for D10). This class covers the runner's own
    infrastructure-level failures.
    """

    code = "EVALUATION_INFRASTRUCTURE_ERROR"


class StaleEvaluationArtifactsError(EvaluationRunnerError):
    """Raised when a managed artifact (per-scenario
    ``run.json`` / ``raw/<scenario_id>.json`` /
    ``normalized/<scenario_id>.json`` or the suite
    ``summary.json``) already exists at the target path BEFORE
    the runner has started writing.

    The runner NEVER silently overwrites a previous run's
    artifacts; the stale state must be inspected and resolved by
    the caller (e.g. by removing the artifact directory). This
    error is the typed signal for that inspection.
    """

    code = "STALE_EVALUATION_ARTIFACTS_ERROR"


class EvaluationArtifactWriteError(EvaluationRunnerError):
    """Raised when an atomic artifact write fails (temp sibling
    creation, flush, fsync, os.replace, etc.).

    Distinct from a stale-artifact detection (which raises
    :class:`StaleEvaluationArtifactsError` BEFORE any write
    attempt). This class covers write-side infrastructure
    failures.
    """

    code = "EVALUATION_ARTIFACT_WRITE_ERROR"


__all__ = [
    "EvaluationArtifactWriteError",
    "EvaluationComparisonError",
    "EvaluationInfrastructureError",
    "EvaluationManifestExecutionError",
    "EvaluationRunnerError",
    "EvaluationRunnerContractViolationError",
    "InvalidEvaluationScenarioError",
    "PhaseBBlockedError",
    "StaleEvaluationArtifactsError",
    "is_evaluation_runner_error",
]
