"""Scheme ORM models — SQLAlchemy records for persistence.

Key decisions:
- ``total_score`` uses ``Numeric`` (not ``Float``) for exact Decimal round-trip.
- ``score_breakdown_snapshot`` and ``constraint_results`` are stored as JSON.
- ``SchemeRunRecord`` carries a ``status`` column to enforce immutability at
  the repository layer (completed runs cannot be overwritten).
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Ensure orchestration tables are registered on Base.metadata so
# ForeignKey references (source_binding_id, weight_set_revision_id)
# resolve during metadata.create_all().
import cold_storage.modules.orchestration.infrastructure.orm  # noqa: F401
from cold_storage.modules.projects.infrastructure.orm import Base


class SchemeWeightSetRevisionRecord(Base):
    """Immutable approved weight-set revision — minimal Phase 1 skeleton.

    Full governance (seeds, resolvers, audit) belongs to later phases.
    This table only establishes the schema and FK target so
    ``scheme_runs.weight_set_revision_id`` is never a dangling reference.
    """

    __tablename__ = "scheme_weight_set_revisions"
    __table_args__ = (
        UniqueConstraint("code", "revision", name="uq_scheme_weight_set_revision_code_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    weight_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scheme_weight_sets.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    content: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    generator_compatibility_version: Mapped[str] = mapped_column(String(50), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class SchemeWeightSetRecord(Base):
    __tablename__ = "scheme_weight_sets"
    __table_args__ = (UniqueConstraint("code", "revision", name="uq_weight_set_code_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    source_type: Mapped[str] = mapped_column(String(50), default="system")
    criteria: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SchemeRunRecord(Base):
    __tablename__ = "scheme_runs"
    __table_args__ = (
        CheckConstraint(
            "("
            " source_mode = 'legacy'"
            " AND source_binding_id IS NULL"
            " AND source_contract_version IS NULL"
            " AND weight_set_revision_id IS NULL"
            " AND weight_set_content_hash IS NULL"
            " AND weight_set_generator_compatibility_version IS NULL"
            " AND combined_source_hash IS NULL"
            ")"
            " OR"
            "("
            " source_mode = 'production'"
            " AND source_binding_id IS NOT NULL"
            " AND source_contract_version IS NOT NULL"
            " AND weight_set_revision_id IS NOT NULL"
            " AND weight_set_content_hash IS NOT NULL"
            " AND weight_set_generator_compatibility_version IS NOT NULL"
            " AND combined_source_hash IS NOT NULL"
            ")",
            name="ck_scheme_run_source_mode_nullity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"))
    project_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("project_versions.id"))
    weight_set_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    generator_version: Mapped[str] = mapped_column(String(50))
    source_snapshot_hash: Mapped[str] = mapped_column(String(128))
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    assumption_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    comparison_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    candidates_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True)
    recommended_scheme_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    warning_messages: Mapped[list[object]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ── Production source identity (all null for legacy, all required for production) ──
    source_mode: Mapped[str] = mapped_column(String(50), default="legacy")
    source_binding_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("orchestration_source_bindings.id"),
        nullable=True,
    )
    source_contract_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weight_set_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("scheme_weight_set_revisions.id"),
        nullable=True,
    )
    weight_set_content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    weight_set_generator_compatibility_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    combined_source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    candidates: Mapped[list["SchemeCandidateRecord"]] = relationship(back_populates="scheme_run")


class SchemeCandidateRecord(Base):
    __tablename__ = "scheme_candidates"
    __table_args__ = (UniqueConstraint("scheme_run_id", "scheme_code", name="uq_run_scheme"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scheme_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("scheme_runs.id"))
    scheme_code: Mapped[str] = mapped_column(String(120))
    profile_code: Mapped[str] = mapped_column(String(120))
    feasible: Mapped[bool] = mapped_column(Boolean, default=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_score: Mapped[object | None] = mapped_column(Numeric(12, 3), nullable=True)
    score_breakdown_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    constraint_results: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    result_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    scheme_run: Mapped["SchemeRunRecord"] = relationship(back_populates="candidates")
