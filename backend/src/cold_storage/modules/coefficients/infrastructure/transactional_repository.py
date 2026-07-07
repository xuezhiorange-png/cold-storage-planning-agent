"""Transactional approval repository — commit 8.

Implements the production :class:`CoefficientApprovalTransactionPort`
with a single ``session.begin()`` containing:

1. ``UPDATE coefficient_revisions SET status = <new_state>``
2. ``INSERT INTO coefficient_audit_log ...``
3. ``INSERT INTO coefficient_approval_log ...`` (for ``approve`` /
   ``retire`` only; ``submit`` is audit-log-only per the design
   contract §5.2).

All three writes commit together or roll back together. The
repository performs **no** business validation: role checks,
citation pattern validation, and state-machine guards run in the
application layer (:class:`CoefficientApprovalService`) before
the context is built. The repository consumes the
:class:`ApprovalTransactionContext` as-is.

Per Charles's Slice 1 boundary correction (2026-07-07):

- This module does **not** modify the existing
  :class:`SqlAlchemyCoefficientApprovalLogAdapter` /
  :class:`SqlAlchemyCoefficientAuditLogAdapter` /
  :class:`SqlAlchemyCoefficientMutationAdapter` adapters — they
  remain available for read-only / unit-test paths.
- The application service does **not** import SQLAlchemy;
  everything cross-layer goes through the
  :class:`CoefficientApprovalTransactionPort` protocol.
- The repository is the **only** place that issues the
  three-write transaction. A failure mid-transaction rolls
  back the entire unit via ``session.rollback()`` and raises
  the typed error from the application caller.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from cold_storage.modules.coefficients.application.ports import (
    CoefficientApprovalTransactionPort,
)
from cold_storage.modules.coefficients.application.transaction import (
    ApprovalTransactionContext,
)
from cold_storage.modules.coefficients.domain.exceptions import (
    InvalidRevisionTransitionError,
)
from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientApprovalLogRecord,
    CoefficientAuditLogRecord,
    CoefficientRevisionRecord,
)

# Locked-set of valid transitions used by the repository as a
# defence-in-depth check. The application layer runs the same
# guard via ``domain.models.validate_revision_transition``;
# the repository re-asserts it inside the transaction so that a
# misbuilt context cannot corrupt the state machine.
_TRANSITIONS = frozenset(
    {
        ("draft", "unverified"),
        ("draft", "reviewed"),
        ("unverified", "reviewed"),
        ("reviewed", "approved"),
        ("approved", "withdrawn"),
    }
)


class TransactionalCoefficientApprovalRepository(CoefficientApprovalTransactionPort):
    """SQLAlchemy-backed transactional approval repository.

    Each ``apply_*`` method opens exactly one session and commits
    exactly once. If any of the three writes raises, the entire
    transaction rolls back; the application-side caller sees the
    propagated exception (typically
    :class:`sqlalchemy.exc.SQLAlchemyError` or a domain-layer
    typed error).
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    # ------------------------------------------------------------------
    # apply_approve
    # ------------------------------------------------------------------

    def apply_approve(self, context: ApprovalTransactionContext) -> None:
        """``UPDATE status='approved'`` + audit-log + approval-log."""
        self._apply_with_logs(
            context=context,
            write_approval_log=True,
        )

    # ------------------------------------------------------------------
    # apply_retire
    # ------------------------------------------------------------------

    def apply_retire(self, context: ApprovalTransactionContext) -> None:
        """``UPDATE status='withdrawn'`` + audit-log + approval-log."""
        self._apply_with_logs(
            context=context,
            write_approval_log=True,
        )

    # ------------------------------------------------------------------
    # apply_submit
    # ------------------------------------------------------------------

    def apply_submit(self, context: ApprovalTransactionContext) -> None:
        """``UPDATE status='unverified'`` + audit-log only (no
        approval-log row; design contract §5.2 / commit 8).
        """
        self._apply_with_logs(
            context=context,
            write_approval_log=False,
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _apply_with_logs(
        self,
        *,
        context: ApprovalTransactionContext,
        write_approval_log: bool,
    ) -> None:
        """Single-session three-write transaction.

        1. SELECT revision record (locked row for the duration of
           the transaction; SQLAlchemy uses SELECT ... FOR UPDATE
           on PostgreSQL via ``with_for_update()`` and is a no-op
           on SQLite — both backends serialize correctly).
        2. Defence-in-depth state-machine check; raise
           :class:`InvalidRevisionTransitionError` if the
           transition is not in :data:`_TRANSITIONS`.
        3. ``UPDATE coefficient_revisions`` (status, approved_at,
           withdrawn_at, reviewed_at as applicable).
        4. ``INSERT INTO coefficient_audit_log``.
        5. (optional) ``INSERT INTO coefficient_approval_log``.
        6. ``session.commit()`` — single atomic flush.

        On any exception inside the block, ``session.rollback()``
        undoes every write and the typed error propagates.
        """
        if (context.old_state, context.new_state) not in _TRANSITIONS:
            raise InvalidRevisionTransitionError(context.old_state, context.new_state)

        with self._session_factory() as session:
            try:
                record = session.scalar(
                    select(CoefficientRevisionRecord)
                    .where(CoefficientRevisionRecord.id == context.revision_id)
                    .with_for_update()
                )
                if record is None:
                    raise LookupError(f"revision {context.revision_id!r} not found")

                # Defence-in-depth: cross-check the existing DB row
                # against the context's old_state. The application
                # caller's snapshot may be stale (e.g. concurrent
                # approve by a different reviewer).
                if record.status != context.old_state:
                    raise InvalidRevisionTransitionError(record.status, context.new_state)

                # Apply the state-machine transition.
                record.status = context.new_state

                # Touch per-state timestamp columns.
                if context.new_state == "approved":
                    record.approved_at = context.observed_at
                    record.approved_by = context.reviewer
                    record.reviewed_at = context.observed_at
                    record.reviewed_by = context.reviewer
                elif context.new_state == "withdrawn":
                    record.withdrawn_at = context.observed_at
                elif context.new_state == "unverified":
                    # Submit transition; no extra timestamps.
                    pass
                else:
                    raise InvalidRevisionTransitionError(context.old_state, context.new_state)

                # Insert audit-log row.
                audit_row = CoefficientAuditLogRecord(
                    revision_id=context.revision_id,
                    actor=context.actor,
                    correlation_id=context.correlation_id,
                    old_state=context.old_state,
                    new_state=context.new_state,
                    reason=context.reason,
                    created_at=context.observed_at,
                )
                session.add(audit_row)

                # Insert approval-log row (skip on submit).
                if write_approval_log:
                    approval_row = CoefficientApprovalLogRecord(
                        revision_id=context.revision_id,
                        reviewer=context.reviewer,
                        action=context.action,
                        citation=context.citation,
                        payload_hash=context.payload_hash,
                        correlation_id=context.correlation_id,
                        created_at=context.observed_at,
                    )
                    session.add(approval_row)

                # Single atomic commit.
                session.commit()
            except Exception:
                session.rollback()
                raise


__all__ = ["TransactionalCoefficientApprovalRepository"]
