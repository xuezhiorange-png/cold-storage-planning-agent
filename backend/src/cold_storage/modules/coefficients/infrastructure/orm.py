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
