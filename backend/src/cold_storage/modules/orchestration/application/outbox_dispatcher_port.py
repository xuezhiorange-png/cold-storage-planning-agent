"""Application-layer port for the audit outbox dispatcher service.

Defines the ``AuditOutboxDispatcherService`` protocol that the CLI invokes.
The service orchestrates claim → validate → materialize → publish in
per-event short transactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ClaimedOutboxEvent:
    """Immutable DTO returned by claim operations."""

    outbox_row_id: str
    event_identity: str
    event_type: str
    event_schema_version: str
    aggregate_type: str
    aggregate_id: str
    actor: str
    correlation_id: str
    occurred_at: datetime
    payload: dict[str, Any]
    payload_hash: str
    attempt_count: int
    claim_token: str
    claim_expires_at: datetime
    # Nullable association fields
    request_id: str | None = None
    identity_id: str | None = None
    attempt_id: str | None = None
    calculation_run_id: str | None = None
    source_binding_id: str | None = None


@dataclass(frozen=True)
class DispatchSummary:
    """Structured result of a one-shot dispatch run."""

    claimed: int = 0
    published: int = 0
    retried: int = 0
    failed: int = 0
    skipped: int = 0
    lost_claims: int = 0


class AuditOutboxDispatcherService(Protocol):
    """Protocol for the outbox dispatcher service.

    The service claims events, validates claims, materializes AuditEvents,
    and publishes or retries based on the outcome.
    """

    def run_cycle(
        self,
        *,
        session: Any,
        worker_id: str,
        batch_size: int,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> DispatchSummary:
        """Execute one dispatch cycle: claim → materialize → publish.

        Returns a structured summary of the cycle's outcomes.
        """
        ...
