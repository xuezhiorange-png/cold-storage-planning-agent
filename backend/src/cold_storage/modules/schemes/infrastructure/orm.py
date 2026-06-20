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
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cold_storage.modules.projects.infrastructure.orm import Base


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
