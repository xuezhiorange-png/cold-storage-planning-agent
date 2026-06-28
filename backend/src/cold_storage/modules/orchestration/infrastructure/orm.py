"""Orchestration ORM models — persistence entities for the orchestration module.

Extends the existing ``Base`` from ``projects.infrastructure.orm``.
Follows existing convention: String(36) PKs, DateTime(timezone=True) timestamps,
JSON columns for snapshots, and UniqueConstraint for business uniqueness.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from cold_storage.modules.projects.infrastructure.orm import Base

# ── Orchestration Request ───────────────────────────────────────────────────


class OrchestrationRequestRecord(Base):
    """Mutable persisted request lifecycle entity."""

    __tablename__ = "orchestration_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    project_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_versions.id"), nullable=False
    )
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    resolved_identity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_field: Mapped[str | None] = mapped_column(String(200), nullable=True)
    failure_details: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Execution Snapshot ──────────────────────────────────────────────────────


class ProjectVersionExecutionSnapshotRecord(Base):
    """Immutable execution snapshot — created once per unique (version, hash, schema)."""

    __tablename__ = "orchestration_execution_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "project_version_id",
            "input_snapshot_hash",
            "schema_version",
            name="uq_exec_snapshot_version_hash_schema",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    project_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_versions.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    input_snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    captured_status: Mapped[str] = mapped_column(String(50), nullable=False)
    captured_source_revision: Mapped[str | None] = mapped_column(String(200), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


# ── Coefficient Context ─────────────────────────────────────────────────────


class CoefficientContextRecord(Base):
    """Immutable materialized coefficient resolution context."""

    __tablename__ = "orchestration_coefficient_contexts"
    __table_args__ = (
        UniqueConstraint(
            "project_version_id",
            "content_hash",
            name="uq_coeff_context_version_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    project_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_versions.id"), nullable=False
    )
    content: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


# ── Orchestration Identity ──────────────────────────────────────────────────


class OrchestrationIdentityRecord(Base):
    """Immutable orchestration identity keyed by fingerprint."""

    __tablename__ = "orchestration_identities"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_orch_identity_fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    execution_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orchestration_execution_snapshots.id"), nullable=False
    )
    coefficient_context_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orchestration_coefficient_contexts.id"), nullable=False
    )
    definition_version: Mapped[str] = mapped_column(String(50), nullable=False)
    calculator_version_vector: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    authoritative_attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


# ── Orchestration Run Attempt ───────────────────────────────────────────────


class OrchestrationRunAttemptRecord(Base):
    """Mutable attempt lifecycle entity. Exactly one RUNNING per identity."""

    __tablename__ = "orchestration_run_attempts"
    __table_args__ = (
        UniqueConstraint("identity_id", "attempt_number", name="uq_attempt_identity_number"),
        # PostgreSQL partial index; SQLite equivalent enforced via application + constraint test
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orchestration_identities.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="RUNNING")
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_binding_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_details: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Source Binding ──────────────────────────────────────────────────────────


class SourceBindingRecord(Base):
    """Immutable binding of exactly five CalculationRunRecords."""

    __tablename__ = "orchestration_source_bindings"
    __table_args__ = (
        UniqueConstraint(
            "orchestration_identity_id",
            "orchestration_run_attempt_id",
            name="uq_source_binding_identity_attempt",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    project_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_versions.id"), nullable=False
    )
    execution_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orchestration_execution_snapshots.id"), nullable=False
    )
    coefficient_context_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orchestration_coefficient_contexts.id"), nullable=False
    )
    orchestration_identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orchestration_identities.id"), nullable=False
    )
    orchestration_run_attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orchestration_run_attempts.id"), nullable=False
    )
    orchestration_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)

    # Five calculation slots — all NOT NULL
    zone_calculation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("calculation_runs.id"), nullable=False
    )
    cooling_load_calculation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("calculation_runs.id"), nullable=False
    )
    equipment_calculation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("calculation_runs.id"), nullable=False
    )
    power_calculation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("calculation_runs.id"), nullable=False
    )
    investment_calculation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("calculation_runs.id"), nullable=False
    )

    per_calculation_result_hashes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    combined_source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


# ── Audit Outbox ────────────────────────────────────────────────────────────


class AuditOutboxRecord(Base):
    """Transactional outbox for audit events."""

    __tablename__ = "orchestration_audit_outbox"
    __table_args__ = (UniqueConstraint("event_identity", name="uq_outbox_event_identity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    identity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    calculation_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_binding_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    claimed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_details: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
