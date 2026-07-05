from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200))
    product_category: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    current_version_number: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    versions: Mapped[list["ProjectVersionRecord"]] = relationship(back_populates="project")


class ProjectVersionRecord(Base):
    __tablename__ = "project_versions"
    __table_args__ = (UniqueConstraint("project_id", "version_number", name="uq_project_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    change_summary: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50))
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    calculation_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    assumption_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    created_by: Mapped[str] = mapped_column(String(100))
    parent_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_versions.id"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project: Mapped[ProjectRecord] = relationship(back_populates="versions")


class CalculationRunRecord(Base):
    __tablename__ = "calculation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    project_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("project_versions.id"))
    calculator_name: Mapped[str] = mapped_column(String(120))
    calculator_version: Mapped[str] = mapped_column(String(50))
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    result_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    formulas: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    coefficients: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    assumptions: Mapped[list[str]] = mapped_column(JSON)
    warnings: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    source_references: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    requires_review: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # ── Orchestration fields (all nullable — all-null for legacy, all-required for orchestrated) ──
    calculation_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    orchestration_identity_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orchestration_identities.id"), nullable=True
    )
    orchestration_run_attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orchestration_run_attempts.id"), nullable=True
    )
    execution_snapshot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orchestration_execution_snapshots.id"), nullable=True
    )
    coefficient_context_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orchestration_coefficient_contexts.id"), nullable=True
    )
    input_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provenance: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    orchestration_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "orchestration_run_attempt_id",
            "calculation_type",
            name="uq_calculation_run_attempt_type",
        ),
        CheckConstraint(
            "("
            " orchestration_identity_id IS NULL"
            " AND orchestration_run_attempt_id IS NULL"
            " AND execution_snapshot_id IS NULL"
            " AND coefficient_context_id IS NULL"
            " AND input_hash IS NULL"
            " AND result_hash IS NULL"
            " AND provenance IS NULL"
            " AND schema_version IS NULL"
            " AND calculation_type IS NULL"
            " AND orchestration_fingerprint IS NULL"
            ")"
            " OR"
            "("
            " orchestration_identity_id IS NOT NULL"
            " AND orchestration_run_attempt_id IS NOT NULL"
            " AND execution_snapshot_id IS NOT NULL"
            " AND coefficient_context_id IS NOT NULL"
            " AND input_hash IS NOT NULL"
            " AND result_hash IS NOT NULL"
            " AND provenance IS NOT NULL"
            " AND schema_version IS NOT NULL"
            " AND calculation_type IS NOT NULL"
            " AND orchestration_fingerprint IS NOT NULL"
            ")",
            name="ck_calculation_run_orchestration_nullity",
        ),
        CheckConstraint(
            "(orchestration_identity_id IS NULL"
            " AND orchestration_fingerprint IS NULL)"
            " OR (orchestration_identity_id IS NOT NULL"
            " AND orchestration_fingerprint IS NOT NULL)",
            name="ck_calculation_run_fingerprint_nullity",
        ),
    )


class EngineeringCoefficientRecord(Base):
    __tablename__ = "engineering_coefficients"
    __table_args__ = (UniqueConstraint("code", "version", name="uq_coefficient_code_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(50))
    source_reference: Mapped[str] = mapped_column(String(500))
    version: Mapped[str] = mapped_column(String(50))
    validity_status: Mapped[str] = mapped_column(String(50))
    approval_status: Mapped[str] = mapped_column(String(50))
    requires_review: Mapped[bool] = mapped_column(Boolean)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(120))
    entity_id: Mapped[str] = mapped_column(String(120))
    before_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    after_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    event_metadata: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # ── Outbox idempotency — one outbox event materializes at most one AuditEventRecord ──
    outbox_event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)


# Ensure orchestration tables are registered on Base.metadata so
# ForeignKey references from CalculationRunRecord resolve during
# metadata.create_all().
import cold_storage.modules.orchestration.infrastructure.orm  # noqa: E402, F401
