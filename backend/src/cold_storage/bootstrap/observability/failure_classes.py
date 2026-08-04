"""Stable failure class enumeration for observability metrics.

These are the 10 frozen failure classes from OBSERVABILITY_CONTRACT.md §13.
No dynamic failure class labels are permitted.
"""

from __future__ import annotations

from enum import StrEnum


class AlertableFailureClass(StrEnum):
    """10 stable failure classes for alertable failure metrics."""

    DATABASE_UNREACHABLE = "DATABASE_UNREACHABLE"
    MIGRATION_HEAD_INVALID = "MIGRATION_HEAD_INVALID"
    REDIS_UNREACHABLE = "REDIS_UNREACHABLE"
    ARTIFACT_STORAGE_AUTH_FAILED = "ARTIFACT_STORAGE_AUTH_FAILED"
    OUTBOX_RETRY_EXHAUSTED = "OUTBOX_RETRY_EXHAUSTED"
    OUTBOX_POISON_MESSAGE = "OUTBOX_POISON_MESSAGE"
    READINESS_CHECK_TIMEOUT = "READINESS_CHECK_TIMEOUT"
    STARTUP_LIVENESS_STALL = "STARTUP_LIVENESS_STALL"
    STRICT_ENVIRONMENT_VIOLATION = "STRICT_ENVIRONMENT_VIOLATION"
    SECRET_PRESENT_IN_REDACTED_OUTPUT = "SECRET_PRESENT_IN_REDACTED_OUTPUT"


ALERTABLE_FAILURE_CLASSES: frozenset[str] = frozenset({fc.value for fc in AlertableFailureClass})
