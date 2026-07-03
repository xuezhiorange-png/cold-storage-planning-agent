"""Typed errors for the audit outbox dispatcher subsystem.

These errors represent distinct failure modes during claim, materialization,
and retry operations. Each carries a machine-readable code for structured
logging and monitoring.
"""

from __future__ import annotations


class OutboxClaimLostError(Exception):
    """Raised when a claimed event no longer belongs to this worker."""

    def __init__(self, event_id: str, worker_id: str, claim_token: str) -> None:
        super().__init__(
            f"Claim lost for event {event_id!r}: "
            f"expected worker={worker_id!r}, claim_token={claim_token!r}"
        )
        self.event_id = event_id
        self.worker_id = worker_id
        self.claim_token = claim_token


class OutboxIdempotencyMismatchError(Exception):
    """Raised when the same event_identity has a different envelope."""

    def __init__(
        self,
        event_identity: str,
        mismatched_fields: list[str],
        *,
        existing_payload_hash: str = "",
        new_payload_hash: str = "",
    ) -> None:
        super().__init__(
            f"Idempotency mismatch for event_identity {event_identity!r}: "
            f"fields differ: {', '.join(sorted(mismatched_fields))}"
        )
        self.event_identity = event_identity
        self.mismatched_fields = mismatched_fields
        self.existing_payload_hash = existing_payload_hash
        self.new_payload_hash = new_payload_hash


class OutboxPayloadIntegrityError(Exception):
    """Raised when payload hash verification fails during materialization."""

    def __init__(
        self,
        event_id: str,
        expected_hash: str,
        actual_hash: str,
    ) -> None:
        super().__init__(
            f"Payload integrity error for event {event_id!r}: "
            f"expected hash={expected_hash!r}, actual={actual_hash!r}"
        )
        self.event_id = event_id
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


class OutboxMaterializationMismatchError(Exception):
    """Raised when a duplicate AuditEvent has non-matching fields."""

    def __init__(
        self,
        event_identity: str,
        mismatched_fields: list[str],
    ) -> None:
        super().__init__(
            f"Materialization mismatch for event_identity {event_identity!r}: "
            f"fields differ: {', '.join(sorted(mismatched_fields))}"
        )
        self.event_identity = event_identity
        self.mismatched_fields = mismatched_fields


class RetryableOutboxDeliveryError(Exception):
    """Transient failure that can be retried after backoff."""

    def __init__(self, event_id: str, reason: str) -> None:
        super().__init__(f"Retryable delivery error for event {event_id!r}: {reason}")
        self.event_id = event_id
        self.reason = reason


class TerminalOutboxDeliveryError(Exception):
    """Permanent failure that cannot be retried."""

    def __init__(self, event_id: str, reason: str) -> None:
        super().__init__(f"Terminal delivery error for event {event_id!r}: {reason}")
        self.event_id = event_id
        self.reason = reason
