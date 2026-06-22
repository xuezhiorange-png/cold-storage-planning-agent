"""Report domain errors."""

from __future__ import annotations


class ReportError(Exception):
    """Base error for the reports module."""


class ReportNotFoundError(ReportError):
    def __init__(self, report_id: str) -> None:
        super().__init__(f"Report not found: {report_id}")
        self.report_id = report_id


class InvalidStatusTransitionError(ReportError):
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(f"Cannot transition from {from_status} to {to_status}")
        self.from_status = from_status
        self.to_status = to_status


class RevisionImmutableError(ReportError):
    def __init__(self, revision_id: str, status: str) -> None:
        super().__init__(f"Revision {revision_id} is immutable (status={status})")


class QualityBlockerError(ReportError):
    def __init__(self, blockers: list[dict[str, object]]) -> None:
        super().__init__(f"Quality blockers present: {len(blockers)}")
        self.blockers = blockers


class ConcurrentRevisionError(ReportError):
    def __init__(self, report_id: str) -> None:
        super().__init__(f"Concurrent revision creation for {report_id}")


class ConcurrencyConflictError(ReportError):
    """Raised when CAS update fails due to version mismatch."""

    def __init__(self, report_id: str) -> None:
        super().__init__(f"Concurrent update conflict for {report_id}")
        self.report_id = report_id


class ReportAccessDeniedError(ReportError):
    def __init__(self, report_id: str, actor: str) -> None:
        super().__init__(f"Actor {actor} denied access to report {report_id}")


class SchemaValidationError(ReportError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"Schema validation failed: {len(errors)} errors")
        self.errors = errors


class IdempotencyClaimError(ReportError):
    """Raised when another concurrent request holds the idempotency key."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Idempotency key '{key}' is already claimed by a concurrent request")
        self.key = key


class IdempotencyPayloadConflictError(ReportError):
    """Raised when the same idempotency key is used with different parameters."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Idempotency key '{key}' used with different request parameters")
        self.key = key
