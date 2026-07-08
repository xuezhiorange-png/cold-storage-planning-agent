"""Evaluation adapter for production scheme generation — Implementation Slice A1.

This module implements the A1-2a adapter surface ratified by Amendment 2
of the Path A design contract
(``docs/tasks/TASK-011B-path-a-design-ratification.md`` §13).

Contract reference: A1-2a (Amendment 2 §13.2 / §13.3 / §13.4).

Public API
==========

* :func:`execute_scenario` — single-call entry point that wraps the
  production ``ProductionSchemeService.generate_production_scheme_run``
  call. Takes only FK references to pre-existing production rows plus
  mandatory ``correlation_id`` and ``database_backend`` metadata. Does
  NOT take a ``project_input`` or a ``scenario_id``.

* :class:`AdapterResult` — read-only result dataclass carrying the
  production ``SchemeRun`` row and the lineage fields extracted from
  it. Does NOT carry ``calculation_run_ids`` (the adapter no longer
  observes the 5 ``CalculationRunRecord`` rows directly; the
  evaluation harness reads them via the production read ports if it
  needs to assert the §4.3 strict row counts).

Ownership boundary (per §13.3)
===============================

The adapter is **only** responsible for:

* Calling :func:`compose_production_scheme_service` to obtain a wired
  ``ProductionSchemeService``.
* Building a :class:`GenerateProductionSchemeCommand` from the
  inputs.
* Invoking ``service.generate_production_scheme_run(cmd)``.
* Reading the persisted ``SchemeRunRecord`` to extract the read-only
  lineage fields (``source_binding_id``, ``weight_set_revision_id``,
  ``combined_source_hash``, ``requires_review``, ``warning_messages``).
* Constructing the :class:`AdapterResult` typed dataclass.
* Forwarding any production exception unchanged to the caller.

The adapter is **NOT** responsible for:

* Creating a ``ProjectVersion`` row.
* Creating a ``OrchestrationIdentityRecord`` row.
* Creating a ``OrchestrationRunAttemptRecord`` row.
* Creating any ``CalculationRunRecord`` rows (the 5 stage calculations).
* Creating an ``OrchestrationExecutionSnapshotRecord`` row.
* Creating an ``OrchestrationCoefficientContextRecord`` row.
* Creating a ``SourceBindingRecord`` row.
* Creating an ``ApprovedWeightSetRevision`` row (or any weight-set row).
* Approving a weight-set revision.
* Resolving approved non-demo coefficients.
* Verifying the ``SourceBinding`` (production's ``SourceBindingVerifier``
  does this inside ``generate_production_scheme_run``).
* Selecting a ``SchemeService`` policy.
* Persisting any production row of any kind.

This ownership boundary is **enforced by the adapter's API surface**:
the adapter accepts only FK references to pre-existing production rows
plus the ``correlation_id`` and ``database_backend`` metadata. The
adapter has no constructor parameters other than the typed fields. The
the module is forbidden (per the architecture boundary tests in
``backend/tests/architecture/test_task_011b_phase2_boundaries.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cold_storage.bootstrap.production_composition import (
    compose_production_scheme_service,
)
from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
)
from cold_storage.modules.schemes.domain.models import SchemeRun

# ── Adapter error class ──────────────────────────────────────────────────


class AdapterInputError(ValueError):
    """Raised when the adapter's input contract is violated.

    Distinct from production-side errors so the evaluation harness can
    classify adapter input failures separately from production
    orchestrator failures.
    """


# ── AdapterResult ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """Read-only result of a single evaluation scenario execution.

    The adapter populates this from the production ``SchemeRun`` row
    and the persisted ``SchemeRunRecord``; the evaluation harness
    writes it to the evaluation artifact (raw / normalized JSON). The
    adapter does NOT mutate the ``SchemeRun`` row in any way.

    The ``calculation_run_ids`` field is intentionally absent: the
    adapter no longer observes the 5 ``CalculationRunRecord`` rows
    directly. The evaluation harness can read them via the production
    read ports (e.g. ``SqlAlchemySourceBindingReadPort``) if it needs
    to assert the §4.3 strict row counts.
    """

    scheme_run: SchemeRun
    source_binding_id: str
    weight_set_revision_id: str
    combined_source_hash: str | None
    review_required: bool
    review_reasons: tuple[str, ...] = field(default_factory=tuple)


# ── Input validation ──────────────────────────────────────────────────────


_VALID_DATABASE_BACKENDS: frozenset[str] = frozenset({"sqlite", "postgresql"})


def _validate_inputs(
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_id: str,
    database_backend: str,
) -> None:
    """Validate the A1-2a input contract.

    Raises :class:`AdapterInputError` on any violation. The validation
    is intentionally explicit (no implicit defaulting) so the
    evaluation harness can detect caller-side omissions as soon as the
    adapter is called, not later inside the production orchestrator.
    """
    if not isinstance(source_binding_id, str) or not source_binding_id:
        raise AdapterInputError(
            "source_binding_id must be a non-empty string FK reference "
            "to a pre-existing SourceBindingRecord."
        )
    if not isinstance(weight_set_revision_id, str) or not weight_set_revision_id:
        raise AdapterInputError(
            "weight_set_revision_id must be a non-empty string FK reference "
            "to a pre-existing ApprovedWeightSetRevision."
        )
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise AdapterInputError(
            "correlation_id must be a non-empty, non-null string "
            "(whitespace-only is rejected). "
            "Phase 1 (Task 11B) made scheme_runs.database_backend and "
            "orchestration_run_attempts.correlation_id NOT NULL with no "
            "column-level server_default; the adapter must reject empty "
            "values at the input boundary."
        )
    if database_backend not in _VALID_DATABASE_BACKENDS:
        raise AdapterInputError(
            f"database_backend must be one of {sorted(_VALID_DATABASE_BACKENDS)!r}; "
            f"got {database_backend!r}. Phase 1 (Task 11B) added a CHECK "
            "constraint ck_scheme_run_database_backend on the scheme_runs "
            "table that rejects any other value at the database layer."
        )


# ── Public API: execute_scenario ──────────────────────────────────────────


def execute_scenario(
    session_factory: Callable[[], Any],
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_id: str,
    database_backend: str,
) -> AdapterResult:
    """Run a single evaluation scenario against the production scheme pipeline.

    Parameters
    ----------
    session_factory:
        Zero-arg callable that returns a SQLAlchemy ``Session``
        (``sessionmaker`` is the canonical instance). Each invocation
        yields a fresh per-request session.
    source_binding_id:
        FK reference to a pre-existing ``SourceBindingRecord`` row
        produced by the upstream production pipeline
        (via ``ProductionSourceBindingUseCase.run``).
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

    Returns
    -------
    :class:`AdapterResult`
        A read-only dataclass carrying the production ``SchemeRun`` row
        and the lineage fields extracted from the persisted
        ``SchemeRunRecord``.

    Raises
    ------
    AdapterInputError
        If any input parameter violates the A1-2a input contract.
    Exception
        Any exception raised by the production
        ``ProductionSchemeService.generate_production_scheme_run`` is
        forwarded unchanged. Per §13.5, the adapter does not wrap or
        re-raise production errors.

    Notes
    -----
    The adapter does NOT take a ``project_input`` (forbidden by A1-2a)
    or a ``scenario_id`` (removed by Amendment 2). The caller is
    responsible for pre-building the production state
    (``SourceBindingRecord``, ``CalculationRunRecord`` x 5,
    ``ApprovedWeightSetRevision``, etc.) before calling this adapter.
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
        profile_codes=("balanced",),
        correlation_id=correlation_id,
        database_backend=database_backend,
    )

    service = compose_production_scheme_service(session_factory)
    scheme_run = service.generate_production_scheme_run(cmd)

    # Read-only lineage extraction: a fresh session to read the
    # persisted SchemeRunRecord. The production service has already
    # committed the row inside its own UoW.
    with session_factory() as session:
        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeRunRecord,
        )

        record = session.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == scheme_run.id)
        ).scalar_one_or_none()

        if record is None:
            # Production service returned a domain SchemeRun that has
            # no corresponding persisted record. Per §13.5 the adapter
            # forwards production's exception shape; raise a clear
            # readback failure so the harness can classify it.
            raise AdapterInputError(
                f"Production service returned SchemeRun id={scheme_run.id!r} "
                "but no persisted SchemeRunRecord was found. The adapter "
                "requires the production service to commit the SchemeRun row "
                "before returning."
            )

        # All three lineage FK / hash fields are NOT NULL on a
        # production-source SchemeRunRecord (enforced by the
        # ck_scheme_run_source_mode_nullity check constraint). They
        # are typed Optional[None] on the ORM column to match the
        # legacy nullability, so we read them through Optional access.
        persisted_source_binding_id = record.source_binding_id
        persisted_weight_set_revision_id = record.weight_set_revision_id
        persisted_combined_source_hash = record.combined_source_hash
        persisted_requires_review = record.requires_review
        persisted_warning_messages = tuple(record.warning_messages or ())

    return AdapterResult(
        scheme_run=scheme_run,
        source_binding_id=persisted_source_binding_id
        if persisted_source_binding_id is not None
        else source_binding_id,
        weight_set_revision_id=persisted_weight_set_revision_id
        if persisted_weight_set_revision_id is not None
        else weight_set_revision_id,
        combined_source_hash=persisted_combined_source_hash,
        review_required=persisted_requires_review,
        review_reasons=persisted_warning_messages,
    )


__all__ = [
    "AdapterInputError",
    "AdapterResult",
    "execute_scenario",
]
