"""Concrete dispatcher application service for the audit outbox.

Implements the ``AuditOutboxDispatcherService`` protocol with
per-event session management for the claim → materialize → publish cycle.

P0-12: The UoW factory is NOT used here — the service manages sessions
directly for the dispatcher pattern (short-lived per-event sessions).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from cold_storage.modules.orchestration.application.outbox_dispatcher_port import (
    ClaimedOutboxEvent,
    DispatchSummary,
)
from cold_storage.modules.orchestration.application.outbox_errors import (
    RetryableOutboxDeliveryError,
    TerminalOutboxDeliveryError,
)


class ClaimFnPG(Protocol):
    """PostgreSQL claim — uses a session + FOR UPDATE SKIP LOCKED."""

    def __call__(
        self,
        session: Any,
        *,
        worker_id: str,
        batch_size: int,
        lease_seconds: float,
        now: datetime,
    ) -> list[ClaimedOutboxEvent]: ...


class ClaimFnSQLite(Protocol):
    """SQLite claim — uses an independent engine connection + BEGIN IMMEDIATE."""

    def __call__(
        self,
        engine: Any,
        *,
        worker_id: str,
        batch_size: int,
        lease_seconds: float,
        now: datetime,
    ) -> list[ClaimedOutboxEvent]: ...


class MaterializeFn(Protocol):
    """Callable that materializes a single claimed event."""

    def __call__(
        self,
        session: Any,
        *,
        claimed: ClaimedOutboxEvent,
        worker_id: str,
        claim_token: str,
        now: datetime,
    ) -> None: ...


class MarkRetryableFn(Protocol):
    """Callable that marks an event as retryable."""

    def __call__(
        self,
        session: Any,
        *,
        event_id: str,
        worker_id: str,
        claim_token: str,
        error: Exception,
        now: datetime | None = None,
    ) -> None: ...


class MarkTerminalFn(Protocol):
    """Callable that marks an event as terminal failed."""

    def __call__(
        self,
        session: Any,
        *,
        event_id: str,
        worker_id: str,
        claim_token: str,
        error: Exception,
        now: datetime | None = None,
    ) -> None: ...


@dataclass
class _SessionFactory(Protocol):
    """Minimal protocol for session factories."""

    def __call__(self) -> Any: ...


class AuditOutboxDispatcherApplicationService:
    """Concrete dispatcher application service.

    Claims events in one transaction, then materializes each event in its own
    session. Failure handling:

    - On ``OutboxClaimLostError``: skip (no state change required).
    - On ``OutboxMaterializationMismatchError`` / ``OutboxPayloadIntegrityError``:
      rollback the materialization session, open a *fresh* failure session,
      write the terminal failure, commit, close. Failure persistence failure
      itself counts as ``unhandled_failures`` (no silent loss).
    - On any other exception: rollback the materialization session, open a
      fresh failure session, write a retryable failure, commit, close. Retryable
      persistence failure also counts as ``unhandled_failures``.
    """

    def __init__(
        self,
        *,
        engine: Any,
        claim_fn_pg: ClaimFnPG | None,
        claim_fn_sqlite: ClaimFnSQLite | None,
        materialize_fn: MaterializeFn,
        mark_retryable_fn: MarkRetryableFn,
        mark_terminal_fn: MarkTerminalFn,
        session_factory: Any,
        is_pg: bool,
    ) -> None:
        self._engine = engine
        self._claim_fn_pg = claim_fn_pg
        self._claim_fn_sqlite = claim_fn_sqlite
        self._materialize_fn = materialize_fn
        self._mark_retryable_fn = mark_retryable_fn
        self._mark_terminal_fn = mark_terminal_fn
        self._session_factory = session_factory
        self._is_pg = is_pg

    def run_cycle(
        self,
        *,
        worker_id: str,
        batch_size: int,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> DispatchSummary:
        """Execute one dispatch cycle: claim → materialize → publish."""
        from cold_storage.modules.orchestration.application.outbox_errors import (
            OutboxClaimLostError,
            OutboxMaterializationMismatchError,
            OutboxPayloadIntegrityError,
        )

        current_now = now or datetime.now(UTC)

        # ── Phase 1: Claim ────────────────────────────────────────────
        claimed: list[ClaimedOutboxEvent] = []
        if self._is_pg:
            assert self._claim_fn_pg is not None
            claim_session = self._session_factory()
            try:
                claimed = self._claim_fn_pg(
                    claim_session,
                    worker_id=worker_id,
                    batch_size=batch_size,
                    lease_seconds=lease_seconds,
                    now=current_now,
                )
                claim_session.commit()
            except Exception:
                claim_session.rollback()
                raise
            finally:
                claim_session.close()
        else:
            assert self._claim_fn_sqlite is not None
            claimed = self._claim_fn_sqlite(
                self._engine,
                worker_id=worker_id,
                batch_size=batch_size,
                lease_seconds=lease_seconds,
                now=current_now,
            )

        # ── Phase 2: Materialize each event in its own session ────────
        summary = DispatchSummary(claimed=len(claimed))
        for event in claimed:
            mat_sess = self._session_factory()
            try:
                try:
                    self._materialize_fn(
                        mat_sess,
                        claimed=event,
                        worker_id=worker_id,
                        claim_token=event.claim_token,
                        now=datetime.now(UTC),
                    )
                    mat_sess.commit()
                    summary = DispatchSummary(
                        claimed=summary.claimed,
                        published=summary.published + 1,
                        retried=summary.retried,
                        failed=summary.failed,
                        skipped=summary.skipped,
                        lost_claims=summary.lost_claims,
                        unhandled_failures=summary.unhandled_failures,
                    )
                except OutboxClaimLostError:
                    mat_sess.rollback()
                    summary = DispatchSummary(
                        claimed=summary.claimed,
                        published=summary.published,
                        retried=summary.retried,
                        failed=summary.failed,
                        skipped=summary.skipped,
                        lost_claims=summary.lost_claims + 1,
                        unhandled_failures=summary.unhandled_failures,
                    )
                except (
                    OutboxMaterializationMismatchError,
                    OutboxPayloadIntegrityError,
                ) as exc:
                    # Close materialization session before opening failure session.
                    mat_sess.rollback()
                    mat_sess.close()
                    mat_sess = None  # already closed; prevent double-close in finally
                    if self._persist_terminal_failure(
                        event=event,
                        worker_id=worker_id,
                        error=exc,
                    ):
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed + 1,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures,
                        )
                    else:
                        # Terminal persistence itself failed — count as unhandled.
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed,  # do NOT increment failed
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures + 1,
                        )
                    continue
                except TerminalOutboxDeliveryError as exc:
                    # Typed terminal failure: mark FAILED, do NOT retry.
                    mat_sess.rollback()
                    mat_sess.close()
                    mat_sess = None
                    if self._persist_terminal_failure(
                        event=event,
                        worker_id=worker_id,
                        error=exc,
                    ):
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed + 1,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures,
                        )
                    else:
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures + 1,
                        )
                    continue
                except RetryableOutboxDeliveryError as exc:
                    # Typed retryable failure: mark retryable.
                    mat_sess.rollback()
                    mat_sess.close()
                    mat_sess = None
                    if self._persist_retryable_failure(
                        event=event,
                        worker_id=worker_id,
                        error=exc,
                    ):
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried + 1,
                            failed=summary.failed,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures,
                        )
                    else:
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures + 1,
                        )
                    continue
                except Exception as exc:
                    # Unknown / untyped failure: do NOT silently retry.
                    # Persist the event as FAILED (terminal) so the system
                    # does not loop indefinitely on an unrecoverable bug.
                    # If the failure persistence itself fails, count as
                    # unhandled.
                    mat_sess.rollback()
                    mat_sess.close()
                    mat_sess = None
                    if self._persist_terminal_failure(
                        event=event,
                        worker_id=worker_id,
                        error=exc,
                    ):
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed + 1,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures,
                        )
                    else:
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures + 1,
                        )
                    continue
            finally:
                # Skip close if we've already continued past it above.
                if mat_sess is not None:
                    with contextlib.suppress(Exception):
                        mat_sess.close()

        return summary

    def _persist_terminal_failure(
        self,
        *,
        event: ClaimedOutboxEvent,
        worker_id: str,
        error: Exception,
    ) -> bool:
        """Persist a terminal failure in a fresh session. Returns False on error."""
        sess = self._session_factory()
        try:
            try:
                self._mark_terminal_fn(
                    sess,
                    event_id=event.outbox_row_id,
                    worker_id=worker_id,
                    claim_token=event.claim_token,
                    error=error,
                    now=datetime.now(UTC),
                )
                sess.commit()
                return True
            except Exception:
                sess.rollback()
                return False
        finally:
            sess.close()

    def _persist_retryable_failure(
        self,
        *,
        event: ClaimedOutboxEvent,
        worker_id: str,
        error: Exception,
    ) -> bool:
        """Persist a retryable failure in a fresh session. Returns False on error."""
        sess = self._session_factory()
        try:
            try:
                self._mark_retryable_fn(
                    sess,
                    event_id=event.outbox_row_id,
                    worker_id=worker_id,
                    claim_token=event.claim_token,
                    error=error,
                    now=datetime.now(UTC),
                )
                sess.commit()
                return True
            except Exception:
                sess.rollback()
                return False
        finally:
            sess.close()
