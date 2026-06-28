"""Orchestration domain — immutable enums, DTOs, errors, DAG, canonical hashing.

All domain types are frozen (``@dataclass(frozen=True, slots=True)``) and
carry no database session, ORM references, or mutable state.
"""

from enum import StrEnum


# ── Request status ──────────────────────────────────────────────────────────

class RequestStatus(StrEnum):
    """Orchestration request lifecycle status."""

    PENDING = "PENDING"
    PREFLIGHT_REJECTED = "PREFLIGHT_REJECTED"
    ACCEPTED = "ACCEPTED"


# ── Identity / attempt statuses ─────────────────────────────────────────────

class IdentityStatus(StrEnum):
    """OrchestrationIdentityRecord lifecycle status."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class AttemptStatus(StrEnum):
    """OrchestrationRunAttemptRecord lifecycle status."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"


# ── Stage execution status ──────────────────────────────────────────────────

class StageExecutionStatus(StrEnum):
    """Per-stage calculator execution outcome."""

    PASSED = "passed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Outbox status ───────────────────────────────────────────────────────────

class OutboxStatus(StrEnum):
    """Audit outbox event dispatch status."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PUBLISHED = "PUBLISHED"


# ── SchemeRun source mode ───────────────────────────────────────────────────

class SourceMode(StrEnum):
    """SchemeRun source identity mode."""

    LEGACY = "legacy"
    PRODUCTION = "production"
