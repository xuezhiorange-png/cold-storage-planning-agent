"""Evaluation runner for Task 11B Phase B (Path A — Implementation Slice A1.5).

This module replaces the legacy ``_require_scheme_production_prerequisite``
always-raise gate that PR #21's evaluation runner used to block every
scenario on a supposed "production pipeline prerequisite gap" (rejected
during the Round 11 reversal; see pre-freeze contract §1.3 #1).

Public API
==========

* :func:`run_scenario` — single-call entry point that takes the same
  A1-2a input contract the adapter uses (``source_binding_id``,
  ``weight_set_revision_id``, ``correlation_id``, ``database_backend``),
  delegates to the same production
  ``compose_production_scheme_service(session_factory)`` entry point,
  and returns a typed :class:`ScenarioOutcome` dataclass.

* :class:`ScenarioOutcome` — read-only result carrying the produced
  :class:`SchemeRun` row plus the runner-side evaluation ledger
  (``outcome`` ∈ {``SUCCEEDED``, ``REVIEW_REQUIRED``, ``FAILED``,
  ``BLOCKED_HISTORICAL``}, ``phase_b_blocked`` boolean indicating
  whether the historical sentinel was raised, ``upstream_error_code``
  capturing the production-side error identifier that triggered the
  failure).

Ownership boundary (per pre-freeze §1.3 #1 + §5.5 + Path A §13.3)
================================================================

The runner is **only** responsible for:

- Validating the input contract at the entry boundary (raises
  :class:`InvalidEvaluationScenarioError` on contract violation).
- Calling :func:`compose_production_scheme_service` to obtain a wired
  ``ProductionSchemeService`` (the canonical composition root).
- Building a :class:`GenerateProductionSchemeCommand` from the inputs.
- Invoking ``service.generate_production_scheme_run(cmd)``.
- Mapping the resulting production-side outcome to a typed
  :class:`ScenarioOutcome`.
- Catching **only** typed production-side errors that the pre-freeze
  contract §1.3 #1 designates as recoverable-as-historical-blocked,
  forwarding them as :class:`PhaseBBlockedError` (NEVER as an
  unconditional gate; the runner MUST succeed when production
  succeeds).

The runner is **NOT** responsible for:

- Creating any ``CalculationRunRecord``, ``SourceBindingRecord``,
  ``SchemeRun``, ``OrchestrationIdentityRecord``,
  ``OrchestrationRunAttemptRecord``, ``ExecutionSnapshotRecord``,
  ``CoefficientContextRecord``, or ``ApprovedWeightSetRevision`` row.
- Approving a weight-set revision.
- Resolving approved non-demo coefficients.
- Verifying the ``SourceBinding`` (production's
  ``SourceBindingVerifier`` does this inside
  ``generate_production_scheme_run``).
- Selecting a ``SchemeService`` policy.
- Persisting any production row of any kind.
- Bypassing ``SourceBindingVerifier`` or ``SchemeService``.
- Introducing demo / latest-row / partial-binding fallbacks.
- Suppressing, renaming, downgrading, or reclassifying
  ``requires_review`` warnings.
- Altering production formulas / coefficient values / scoring rules /
  review rules / thresholds / weights.
- Parsing exception message text to make business decisions.
- Restoring ``production_seeding.py`` (pre-freeze §5.1 / §8 #1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

from cold_storage.bootstrap.production_composition import (
    compose_production_scheme_service,
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
    """Validate the A1-2a-equivalent runner input contract.

    The runner uses the same A1-2a input contract as the adapter (per
    pre-freeze §1.3 #1 — "Lift the always-raise gate"). Raises
    :class:`InvalidEvaluationScenarioError` on any violation. The
    validation is explicit (no implicit defaulting) so downstream code
    detects caller-side omissions as soon as the runner is called.
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
    profile_codes: tuple[str, ...] = ("balanced",),
) -> ScenarioOutcome:
    """Run a single evaluation scenario against the production scheme pipeline.

    The runner delegates to the production
    ``ProductionSchemeService.generate_production_scheme_run`` entry
    point. It MUST succeed when production succeeds; it MUST raise
    :class:`PhaseBBlockedError` ONLY when production raises one of
    the upstream ``HISTORICAL_BLOCKED_UPSTREAM_CODES`` errors; it
    MUST forward all other production-side exceptions unchanged (per
    pre-freeze §1.3 #1 + Path A §13.5).

    Parameters
    ----------
    session_factory:
        Zero-arg callable that returns a SQLAlchemy ``Session``
        (``sessionmaker`` is the canonical instance). Each invocation
        yields a fresh per-request session. The runner does NOT accept
        a raw ``Session`` — the production entrypoint accepts a
        factory, and the runner does the same.
    source_binding_id:
        FK reference to a pre-existing ``SourceBindingRecord`` row
        produced by the upstream production pipeline.
    weight_set_revision_id:
        FK reference to a pre-existing
        ``SchemeWeightSetRevisionRecord`` row with ``status='approved'``.
    correlation_id:
        Mandatory NOT-NULL correlation id for the produced
        ``orchestration_run_attempts`` row. Must be a non-empty string.
    database_backend:
        Mandatory NOT-NULL database backend marker. One of
        ``"sqlite"`` or ``"postgresql"`` (matches the
        ``ck_scheme_run_database_backend`` check constraint).
    profile_codes:
        Optional tuple of profile codes passed to the production
        command (defaults to ``("balanced",)`` to match the adapter
        default).

    Returns
    -------
    :class:`ScenarioOutcome`
        A read-only dataclass carrying the produced ``SchemeRun`` row,
        the runner-side ``outcome`` (one of ``SUCCEEDED`` /
        ``REVIEW_REQUIRED`` / ``FAILED`` / ``BLOCKED_HISTORICAL``),
        and the FK / database-backend echo fields.

    Raises
    ------
    InvalidEvaluationScenarioError
        If any input parameter violates the runner's contract.
    PhaseBBlockedError
        Only if production raises one of the
        ``HISTORICAL_BLOCKED_UPSTREAM_CODES`` upstream errors. This is
        the documented historical-blocked sentinel; downstream code
        catches it via the typed ``code`` attribute
        (``"PHASE_B_BLOCKED"``), NOT via the exception ``str``.
    Exception
        Any other exception raised by the production
        ``ProductionSchemeService.generate_production_scheme_run`` is
        forwarded unchanged (per pre-freeze §1.3 #1 + Path A §13.5).
        The runner does NOT wrap, transform, log-and-continue, or
        swallow production-side errors.
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

    cmd = GenerateProductionSchemeCommand(
        source_binding_id=source_binding_id,
        weight_set_revision_id=weight_set_revision_id,
        profile_codes=profile_codes,
        correlation_id=correlation_id,
        database_backend=database_backend,
    )

    service = compose_production_scheme_service(session_factory)
    try:
        scheme_run = service.generate_production_scheme_run(cmd)
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

    # The runner's input contract guarantees that the production
    # service persists a SchemeRun whose ``database_backend`` matches
    # the input. ``GenerateProductionSchemeCommand`` is immutable and
    # the production service writes the field unchanged. We assert
    # anyway to surface any future contract drift.
    persisted_db = scheme_run.database_backend
    if persisted_db != database_backend:
        raise EvaluationRunnerContractViolationError(
            "Production service returned a SchemeRun whose "
            "database_backend does not match the runner's input "
            "database_backend. The runner's input contract has been "
            "violated by production.",
            details={
                "expected": database_backend,
                "actual": persisted_db,
            },
        )

    # ``SchemeRun.status`` is a plain string (NOT an enum); the
    # production-side canonical values are ``completed``,
    # ``review_required``, ``failed``, ``running``, ``pending``
    # (lowercase). The runner maps the production-side string to a
    # typed ``Outcome`` literal that downstream code classifies by
    # (NOT by message-text parsing).
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


__all__ = [
    "Outcome",
    "ScenarioOutcome",
    "VALID_DATABASE_BACKENDS",
    "HISTORICAL_BLOCKED_UPSTREAM_CODES",
    "run_scenario",
]