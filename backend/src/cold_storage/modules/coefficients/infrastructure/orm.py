"""SQLAlchemy ORM models for the coefficient registry tables.

These models share the same DeclarativeBase as the projects module
so Alembic can discover all tables from a single metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cold_storage.modules.projects.infrastructure.orm import Base


class CoefficientDefinitionRecord(Base):
    """ORM model for coefficient_definitions table."""

    __tablename__ = "coefficient_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="decimal")
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False, default="global")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    revisions: Mapped[list[CoefficientRevisionRecord]] = relationship(
        back_populates="definition", order_by="CoefficientRevisionRecord.revision_number"
    )


class CoefficientRevisionRecord(Base):
    """ORM model for coefficient_revisions table."""

    __tablename__ = "coefficient_revisions"
    __table_args__ = (
        UniqueConstraint(
            "coefficient_definition_id",
            "revision_number",
            name="uq_coefficient_def_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    coefficient_definition_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coefficient_definitions.id"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    value_decimal: Mapped[str | None] = mapped_column(String(50), nullable=True)
    value_json: Mapped[dict[str, object] | None] = mapped_column(
        Text,
        nullable=True,  # stored as JSON text
    )
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="demo")
    source_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_page: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applicable_product_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    applicable_zone_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    applicable_process_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supersedes_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    definition: Mapped[CoefficientDefinitionRecord] = relationship(back_populates="revisions")


# ---------------------------------------------------------------------------
# Phase 4 Issue #35 Slice 1 — append-only log tables
# ---------------------------------------------------------------------------
# Per design contract §3.2 + §3.3 (approval log + audit log).
# Charles's Slice 1 boundary correction (2026-07-07): append only,
# no existing record class is modified, no column added to the
# coefficient_revisions table, no source_citation / governance_status
# / valid_until / NOT NULL additions to existing columns. The migration
# in 0038_phase4_slice1_coefficient_approval.py is the single source
# of schema truth for these two log tables.


class CoefficientApprovalLogRecord(Base):
    """Append-only approval-log row (design contract §3.2).

    Records a single approval transition: reviewer, timestamp, the
    validated citation, the SHA-256 hash of the revision snapshot,
    and a correlation_id for tracing. There is one row per
    ``approve`` / ``retire`` action; ``submit`` writes to the audit
    log only (see :class:`CoefficientAuditLogRecord`).
    """

    __tablename__ = "coefficient_approval_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    revision_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    citation: Mapped[str] = mapped_column(String(500), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class CoefficientAuditLogRecord(Base):
    """Append-only audit-log row (design contract §3.3).

    One row per state transition: actor, correlation_id,
    ``old_state`` / ``new_state``, the reason. The log is
    append-only at the application boundary (Slice 1 ships the
    write-only API); the schema-level
    ``UPDATE`` / ``DELETE`` rejection is a follow-up Slice together
    with archive persistence (see design contract §3.3 + §14.4).
    """

    __tablename__ = "coefficient_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    revision_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    old_state: Mapped[str] = mapped_column(String(32), nullable=False)
    new_state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
