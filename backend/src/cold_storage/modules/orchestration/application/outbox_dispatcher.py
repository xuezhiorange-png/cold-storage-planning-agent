"""Concrete dispatcher application service for the audit outbox.

Implements the ``AuditOutboxDispatcherService`` protocol with
per-event session management for the claim → materialize → publish cycle.

P0-12: The UoW factory is NOT used here — the service manages sessions
directly for the dispatcher pattern (short-lived per-event sessions).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from cold_storage.modules.orchestration.application.outbox_dispatcher_port import (
    ClaimedOutboxEvent,
    DispatchSummary,
)


class ClaimFn(Protocol):
    """Callable that claims events in a session."""

    def __call__(
        self,
        session: Any,
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

    Claims events in one session, then materializes each event in its own
    session for atomicity. Error classification matches the CLI logic.
    """

    def __init__(
        self,
        *,
        claim_fn: ClaimFn,
        materialize_fn: MaterializeFn,
        mark_retryable_fn: MarkRetryableFn,
        mark_terminal_fn: MarkTerminalFn,
        session_factory: Any,
        is_pg: bool,
    ) -> None:
        self._claim_fn = claim_fn
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
        """Execute one dispatch cycle: claim → materialize → publish.

        1. Claim events in one session.
        2. For each claimed event, create a fresh session and attempt
           materialization.
        3. Classify errors and retry or fail as appropriate.
        """
        from cold_storage.modules.orchestration.application.outbox_errors import (
            OutboxClaimLostError,
            OutboxMaterializationMismatchError,
            OutboxPayloadIntegrityError,
        )

        current_now = now or datetime.now(UTC)

        # ── Phase 1: Claim in a single session ────────────────────────
        claimed: list[ClaimedOutboxEvent] = []
        claim_session = self._session_factory()
        try:
            claimed = self._claim_fn(
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

        # ── Phase 2: Materialize each event in its own session ────────
        summary = DispatchSummary(claimed=len(claimed))
        for event in claimed:
            sess = self._session_factory()
            try:
                try:
                    self._materialize_fn(
                        sess,
                        claimed=event,
                        worker_id=worker_id,
                        claim_token=event.claim_token,
                        now=datetime.now(UTC),
                    )
                    sess.commit()
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
                    try:
                        self._mark_terminal_fn(
                            sess,
                            event_id=event.outbox_row_id,
                            worker_id=worker_id,
                            claim_token=event.claim_token,
                            error=exc,
                            now=datetime.now(UTC),
                        )
                        sess.commit()
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed + 1,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures,
                        )
                    except Exception:
                        sess.rollback()
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed + 1,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures,
                        )
                except Exception as exc:
                    try:
                        self._mark_retryable_fn(
                            sess,
                            event_id=event.outbox_row_id,
                            worker_id=worker_id,
                            claim_token=event.claim_token,
                            error=exc,
                            now=datetime.now(UTC),
                        )
                        sess.commit()
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried + 1,
                            failed=summary.failed,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures,
                        )
                    except Exception:
                        sess.rollback()
                        summary = DispatchSummary(
                            claimed=summary.claimed,
                            published=summary.published,
                            retried=summary.retried,
                            failed=summary.failed,
                            skipped=summary.skipped,
                            lost_claims=summary.lost_claims,
                            unhandled_failures=summary.unhandled_failures + 1,
                        )
            finally:
                sess.close()

        return summary
