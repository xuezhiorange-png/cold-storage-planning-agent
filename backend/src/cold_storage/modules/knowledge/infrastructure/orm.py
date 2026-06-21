"""Knowledge ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
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


class KnowledgeDocumentRecord(Base):
    """ORM record for a knowledge document."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("code", name="uq_knowledge_doc_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    document_category: Mapped[str] = mapped_column(String(50), default="other")
    source_type: Mapped[str] = mapped_column(String(50), default="upload")
    source_reference: Mapped[str] = mapped_column(String(500), default="")
    owner: Mapped[str] = mapped_column(String(100), default="")
    current_revision_number: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    revisions: Mapped[list[KnowledgeRevisionRecord]] = relationship(
        back_populates="document",
        order_by="KnowledgeRevisionRecord.revision_number",
    )


class KnowledgeRevisionRecord(Base):
    """ORM record for a single document revision."""

    __tablename__ = "knowledge_revisions"
    __table_args__ = (
        UniqueConstraint("document_id", "revision_number", name="uq_knowledge_rev_num"),
        UniqueConstraint("document_id", "content_sha256", name="uq_knowledge_rev_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_documents.id"))
    revision_number: Mapped[int] = mapped_column(Integer)
    version_label: Mapped[str] = mapped_column(String(100), default="")
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    safe_filename: Mapped[str] = mapped_column(String(255), default="")
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    file_extension: Mapped[str] = mapped_column(String(20), default="")
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_sha256: Mapped[str] = mapped_column(String(64), default="")
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    ingestion_status: Mapped[str] = mapped_column(String(50), default="uploaded")
    review_status: Mapped[str] = mapped_column(String(50), default="unverified")
    requires_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True)
    parser_name: Mapped[str] = mapped_column(String(50), default="")
    parser_version: Mapped[str] = mapped_column(String(50), default="")
    chunker_version: Mapped[str] = mapped_column(String(50), default="")
    embedding_version: Mapped[str] = mapped_column(String(50), default="")
    extracted_text_length: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    warning_messages: Mapped[list[object]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped[KnowledgeDocumentRecord] = relationship(back_populates="revisions")
    ingestion_runs: Mapped[list[KnowledgeIngestionRunRecord]] = relationship(
        back_populates="revision",
        order_by="KnowledgeIngestionRunRecord.created_at",
    )
    chunks: Mapped[list[KnowledgeChunkRecord]] = relationship(
        back_populates="revision",
        order_by="KnowledgeChunkRecord.chunk_index",
    )


class KnowledgeIngestionRunRecord(Base):
    """ORM record for an ingestion pipeline execution."""

    __tablename__ = "knowledge_ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_revisions.id"))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    parser_name: Mapped[str] = mapped_column(String(50), default="")
    parser_version: Mapped[str] = mapped_column(String(50), default="")
    chunker_version: Mapped[str] = mapped_column(String(50), default="")
    embedding_version: Mapped[str] = mapped_column(String(50), default="")
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    result_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    warning_messages: Mapped[list[object]] = mapped_column(JSON, default=list)
    error_code: Mapped[str] = mapped_column(String(100), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    revision: Mapped[KnowledgeRevisionRecord] = relationship(back_populates="ingestion_runs")


class KnowledgeChunkRecord(Base):
    """ORM record for an embedded text chunk."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("revision_id", "chunk_index", name="uq_knowledge_chunk_idx"),
        UniqueConstraint(
            "revision_id",
            "text_sha256",
            "chunk_index",
            name="uq_knowledge_chunk_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_revisions.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    text_sha256: Mapped[str] = mapped_column(String(64), default="")
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    section_path: Mapped[str] = mapped_column(String(500), default="")
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    row_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_locator: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list)
    embedding_dimension: Mapped[int] = mapped_column(Integer, default=0)
    embedding_version: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    revision: Mapped[KnowledgeRevisionRecord] = relationship(back_populates="chunks")
