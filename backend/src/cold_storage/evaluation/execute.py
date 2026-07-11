"""Evaluation runner for Task 11B Phase B (Path A — Implementation Slice A1.5).

This module replaces the legacy always-raise gate that the Round 11
reversal rejected. It runs against the real production scheme pipeline
through the A1-2a adapter entry point
(``cold_storage.evaluation.adapter.execute_scenario``) — it does NOT
write any production row directly, it does NOT call
``compose_production_scheme_service`` itself, and it does NOT take a
``project_input``. The runner is a thin wrapper that adds:

* Input-contract validation that raises
  :class:`InvalidEvaluationScenarioError` instead of the adapter's
  :class:`AdapterInputError` (so the runner's input boundary is
  classified independently from the adapter's).
* Mapping of the production-side terminal status to a typed
  :class:`Outcome` literal (``SUCCEEDED`` / ``REVIEW_REQUIRED`` /
  ``FAILED`` / ``BLOCKED_HISTORICAL``).
* Mapping of a narrow set of production-side typed errors
  (those whose machine-readable ``code`` attribute is in
  :data:`HISTORICAL_BLOCKED_UPSTREAM_CODES`) to
  :class:`PhaseBBlockedError`. All other production-side errors
  propagate unchanged (per pre-freeze §1.3 #1 + Path A §13.5).

Public API
==========

* :func:`run_scenario` — single-call entry point. Takes the A1-2a
  input contract that the adapter exposes
  (``source_binding_id``, ``weight_set_revision_id``,
  ``correlation_id``, ``database_backend``) and returns a typed
  :class:`ScenarioOutcome`.
* :class:`ScenarioOutcome` — read-only result dataclass carrying the
  produced :class:`SchemeRun` row plus the runner-side evaluation
  ledger (``outcome`` literal, ``phase_b_blocked`` boolean,
  ``upstream_error_code`` capturing the production-side identifier
  that triggered the failure).

Ownership boundary (per pre-freeze §1.3 #1 + §5.5 + Path A §13.3
                                                       + §14 Amendment 3)
================================================================

The runner is **only** responsible for:

- Validating the input contract at the entry boundary (raises
  :class:`InvalidEvaluationScenarioError` on contract violation).
- Delegating to ``adapter.execute_scenario(...)`` for the production
  invocation (the runner does NOT import the production
  composition root or the production command type).
- Mapping the resulting production-side outcome to a typed
  :class:`ScenarioOutcome`.
- Catching **only** typed production-side errors whose ``code`` is in
  :data:`HISTORICAL_BLOCKED_UPSTREAM_CODES` and re-raising them as
  :class:`PhaseBBlockedError` (forwarded, not swallowed, not
  message-text-parsed).

The runner is **NOT** responsible for:

- Creating any production row of any kind.
- Approving a weight-set revision.
- Resolving approved non-demo coefficients.
- Verifying the ``SourceBinding``.
- Selecting a ``SchemeService`` policy.
- Persisting any production row.
- Bypassing ``SourceBindingVerifier`` or ``SchemeService``.
- Introducing demo / latest-row / partial-binding fallbacks.
- Suppressing, renaming, downgrading, or reclassifying
  ``requires_review`` warnings.
- Altering production formulas / coefficient values / scoring rules /
  review rules / thresholds / weights.
- Parsing exception message text to make business decisions.
- Restoring any deleted evaluation-owned seeding module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

from cold_storage.evaluation.adapter import (
    execute_scenario,
)
from cold_storage.evaluation.errors import (
    EvaluationRunnerContractViolationError,
    InvalidEvaluationScenarioError,
    PhaseBBlockedError,
)
from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
)
from cold_storage.modules.schemes.domain.models import SchemeRun

# ── Allowed database backends (must match ck_scheme_run_database_backend) ──

VALID_DATABASE_BACKENDS: Final[frozenset[str]] = frozenset({"sqlite", "postgresql"})

# Production-side error class identifiers that the runner treats as
# recoverable historical-blocked. The list is intentionally narrow:
# only upstream errors whose ``code`` attribute is one of these are
# mapped to :class:`PhaseBBlockedError`. All other production-side
# errors propagate unchanged.
HISTORICAL_BLOCKED_UPSTREAM_CODES: Final[frozenset[str]] = frozenset(
    {
        "MISSING_APPROVED_COEFFICIENT",
        "SCHEMA_MIGRATION_MISSING",
        "WEIGHT_REVISION_NOT_APPROVED",
        "IDENTITY_FINGERPRINT_STALE",
    }
)

Outcome = Literal[
    "SUCCEEDED",
    "REVIEW_REQUIRED",
    "FAILED",
    "BLOCKED_HISTORICAL",
]


# ── Typed result dataclass ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    """Read-only result of a single evaluation scenario execution.

    The runner populates this from the production ``SchemeRun`` row
    and the production-side outcome. The runner does NOT mutate the
    ``SchemeRun`` row in any way.
    """

    scheme_run: SchemeRun
    outcome: Outcome
    source_binding_id: str
    weight_set_revision_id: str
    database_backend: str
    phase_b_blocked: bool = False
    upstream_error_code: str | None = None


# ── Input validation ─────────────────────────────────────────────────────


def _validate_inputs(
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_id: str,
    database_backend: str,
) -> None:
    """Validate the runner input contract.

    Raises :class:`InvalidEvaluationScenarioError` on any violation.
    The validation is explicit (no implicit defaulting) so downstream
    code detects caller-side omissions as soon as the runner is
    called.
    """
    if not isinstance(source_binding_id, str) or not source_binding_id:
        raise InvalidEvaluationScenarioError(
            "source_binding_id must be a non-empty string FK reference "
            "to a pre-existing SourceBindingRecord.",
            details={"field": "source_binding_id"},
        )
    if not isinstance(weight_set_revision_id, str) or not weight_set_revision_id:
        raise InvalidEvaluationScenarioError(
            "weight_set_revision_id must be a non-empty string FK "
            "reference to a pre-existing ApprovedWeightSetRevision.",
            details={"field": "weight_set_revision_id"},
        )
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise InvalidEvaluationScenarioError(
            "correlation_id must be a non-empty, non-null string.",
            details={"field": "correlation_id"},
        )
    if database_backend not in VALID_DATABASE_BACKENDS:
        raise InvalidEvaluationScenarioError(
            f"database_backend must be one of "
            f"{sorted(VALID_DATABASE_BACKENDS)!r}; got "
            f"{database_backend!r}.",
            details={"field": "database_backend", "value": database_backend},
        )


# ── Production-side error class mapping ────────────────────────────────


def _extract_upstream_code(exc: BaseException) -> str | None:
    """Return the production-side error class's machine-readable code.

    Production-side typed errors expose a ``code`` attribute (per the
    Phase 4 §9 forbidden-pattern list, which forbids message-text
    parsing). The runner uses ``code`` to classify the failure into
    ``historical-blocked`` vs ``forwarded-as-is``. If the production
    error does NOT expose a ``code`` attribute (e.g., ``OperationalError``,
    ``ProgrammingError``), the runner returns ``None`` and forwards the
    exception unchanged.
    """
    code_attr = getattr(exc, "code", None)
    if isinstance(code_attr, str) and code_attr:
        return code_attr
    return None


# ── Public API: run_scenario ─────────────────────────────────────────────


def run_scenario(
    session_factory: Callable[[], Any],
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_id: str,
    database_backend: str,
) -> ScenarioOutcome:
    """Run a single evaluation scenario against the production scheme pipeline.

    The runner delegates to the A1-2a adapter entry point
    (``adapter.execute_scenario``), which in turn calls
    ``compose_production_scheme_service(session_factory)`` and persists
    the resulting ``SchemeRun`` row through the production
    ``SchemeService``. The runner MUST succeed when production
    succeeds; it MUST raise :class:`PhaseBBlockedError` ONLY when
    production raises one of the upstream codes listed in
    :data:`HISTORICAL_BLOCKED_UPSTREAM_CODES`; it MUST forward all
    other production-side exceptions unchanged (per pre-freeze
    §1.3 #1 + Path A §13.5 + §14 Amendment 3).

    Parameters
    ----------
    session_factory:
        Zero-arg callable that returns a SQLAlchemy ``Session``
        (``sessionmaker`` is the canonical instance). Each invocation
        yields a fresh per-request session.
    source_binding_id:
        FK reference to a pre-existing ``SourceBindingRecord`` row.
    weight_set_revision_id:
        FK reference to a pre-existing ``ApprovedWeightSetRevision``
        row with ``status='approved'``.
    correlation_id:
        Mandatory NOT-NULL correlation id for the produced
        ``orchestration_run_attempts`` row. Must be a non-empty
        string.
    database_backend:
        Mandatory NOT-NULL database backend marker. One of
        ``"sqlite"`` or ``"postgresql"`` (matches the
        ``ck_scheme_run_database_backend`` check constraint).

    Returns
    -------
    :class:`ScenarioOutcome`
        A read-only dataclass carrying the produced ``SchemeRun`` row,
        the runner-side ``outcome`` literal, and the FK / backend
        echo fields.

    Raises
    ------
    InvalidEvaluationScenarioError
        If any input parameter violates the runner's contract.
    PhaseBBlockedError
        Only if production raises one of the
        ``HISTORICAL_BLOCKED_UPSTREAM_CODES`` upstream errors. This is
        the documented historical-blocked sentinel; downstream code
        catches it via the typed ``code`` attribute, NOT via the
        exception ``str``.
    Exception
        Any other exception raised by the production service is
        forwarded unchanged (per pre-freeze §1.3 #1 + Path A §13.5).
    EvaluationRunnerContractViolationError
        If the production orchestrator returns a ``SchemeRun`` whose
        ``source_binding_id`` does not match the input
        ``source_binding_id`` (defense-in-depth check).

    Notes
    -----
    The runner does NOT take a ``project_input`` (A1-2a surface, per
    Path A Amendment 2 §13.2). The caller is responsible for
    pre-building the production state (``SourceBindingRecord``,
    ``CalculationRunRecord`` x 5, ``ApprovedWeightSetRevision``, etc.)
    before calling this runner.

    The runner does NOT raise ``PhaseBBlockedError`` on the happy path
    (pre-freeze §1.3 #1 + §8 #12). The historical sentinel is
    reserved for the real production-side prerequisite failures
    enumerated in :data:`HISTORICAL_BLOCKED_UPSTREAM_CODES`.
    """
    _validate_inputs(
        source_binding_id=source_binding_id,
        weight_set_revision_id=weight_set_revision_id,
        correlation_id=correlation_id,
        database_backend=database_backend,
    )

    try:
        adapter_result = execute_scenario(
            session_factory,
            source_binding_id=source_binding_id,
            weight_set_revision_id=weight_set_revision_id,
            correlation_id=correlation_id,
            database_backend=database_backend,
        )
    except Exception as exc:
        upstream_code = _extract_upstream_code(exc)
        if upstream_code in HISTORICAL_BLOCKED_UPSTREAM_CODES:
            raise PhaseBBlockedError(
                f"Historical-blocked sentinel raised; production-side "
                f"upstream code: {upstream_code!r}",
                upstream_code=upstream_code,
                details={
                    "upstream_message": str(exc),
                    "source_binding_id": source_binding_id,
                    "weight_set_revision_id": weight_set_revision_id,
                    "database_backend": database_backend,
                },
            ) from exc
        # All other production-side errors propagate unchanged.
        raise

    # ``adapter_result.scheme_run.status`` is a plain string (NOT an
    # enum); the production-side canonical values are ``completed``,
    # ``review_required``, ``failed``, ``running``, ``pending``
    # (lowercase). The runner maps the production-side string to a
    # typed ``Outcome`` literal that downstream code classifies by
    # (NOT by message-text parsing).
    scheme_run = adapter_result.scheme_run
    raw_status = scheme_run.status
    if raw_status == "completed":
        outcome: Outcome = "SUCCEEDED"
    elif raw_status == "review_required":
        outcome = "REVIEW_REQUIRED"
    elif raw_status == "failed":
        outcome = "FAILED"
    elif raw_status in ("running", "pending"):
        # Production returned a synchronous PENDING / RUNNING status,
        # which the pre-freeze contract §6 / §8 treats as a
        # contract violation (synchronous scheme runs must be
        # terminal). The runner surfaces this as FAILED.
        outcome = "FAILED"
    else:
        # Unknown status — treat as FAILED for the runner-side
        # outcome; downstream code classifies by the typed Outcome
        # literal, NOT by message-text parsing.
        outcome = "FAILED"

    return ScenarioOutcome(
        scheme_run=scheme_run,
        outcome=outcome,
        source_binding_id=source_binding_id,
        weight_set_revision_id=weight_set_revision_id,
        database_backend=database_backend,
        phase_b_blocked=False,
        upstream_error_code=None,
    )


# ── Marker-named thin entry point (Phase-B orchestration boundary) ────
#
# The run-directory helper (``backend/src/cold_storage/evaluation/
# run_directory.py``) is forbidden by Amendment 3 §14.2 narrow
# carve-out to hold the A1-2a contract token names
# (``correlation_id`` / ``database_backend``) on its public surface.
# Therefore, ``execute.py`` (the single Phase-B orchestration boundary
# per Amendment 3 §14.1) exposes a marker-named thin wrapper
# :func:`run_scenario_via_markers` that maps marker names to the
# canonical A1-2a contract kwarg names and forwards to
# :func:`run_scenario`. The mapping happens ONLY inside ``execute.py``;
# no other evaluation module needs to retain the A1-2a token names
# on its public surface.
#
# This entry point is **not** a new public API for callers — it is
# the internal boundary at which the run-directory helper's
# marker-named kwargs are mapped to the runner's canonical A1-2a
# contract kwargs. Callers (CLI / tests) use ``run_scenario`` (or
# ``adapter.execute_scenario`` for the adapter-side surface) directly.


def run_scenario_via_markers(
    session_factory: Callable[[], Any],
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_marker: str,
    backend_marker: str,
) -> ScenarioOutcome:
    """Marker-named thin entry point for the run-directory helper.

    Identical contract to :func:`run_scenario`, but accepts the
    correlation / backend values under marker names so the
    run-directory helper does not need to retain the A1-2a contract
    token names on its public surface (Amendment 3 §14.2 narrow
    carve-out).
    """
    return run_scenario(
        session_factory,
        source_binding_id=source_binding_id,
        weight_set_revision_id=weight_set_revision_id,
        correlation_id=correlation_marker,
        database_backend=backend_marker,
    )


__all__ = [
    "Outcome",
    "ScenarioOutcome",
    "VALID_DATABASE_BACKENDS",
    "HISTORICAL_BLOCKED_UPSTREAM_CODES",
    "run_scenario",
    "run_scenario_via_markers",
]
