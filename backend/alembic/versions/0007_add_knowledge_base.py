"""Add knowledge base tables.

Revision ID: 0007_add_knowledge_base
Revises: 0006_scheme_candidate_details
Create Date: 2026-06-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_add_knowledge_base"
down_revision: str | None = "0006_scheme_candidate_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. knowledge_documents
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(120), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("document_category", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_reference", sa.String(500), nullable=False),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("current_revision_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_documents_code", "knowledge_documents", ["code"])

    # 2. knowledge_revisions
    op.create_table(
        "knowledge_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(200), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("safe_filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_extension", sa.String(20), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("ingestion_status", sa.String(50), nullable=False),
        sa.Column("review_status", sa.String(50), nullable=False),
        sa.Column("requires_ocr", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("requires_review", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("parser_name", sa.String(50), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("chunker_version", sa.String(50), nullable=False),
        sa.Column("embedding_version", sa.String(50), nullable=False),
        sa.Column("extracted_text_length", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("sheet_count", sa.Integer(), nullable=True),
        sa.Column("metadata_snapshot", sa.JSON(), nullable=False),
        sa.Column("warning_messages", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_id", "revision_number", name="uq_knowledge_rev_num"),
        sa.UniqueConstraint("document_id", "content_sha256", name="uq_knowledge_rev_hash"),
    )
    op.create_index(
        "ix_knowledge_revisions_document_id",
        "knowledge_revisions",
        ["document_id"],
    )
    op.create_index(
        "ix_knowledge_revisions_review_status",
        "knowledge_revisions",
        ["review_status"],
    )
    op.create_index(
        "ix_knowledge_revisions_ingestion_status",
        "knowledge_revisions",
        ["ingestion_status"],
    )
    op.create_index(
        "ix_knowledge_revisions_content_sha256",
        "knowledge_revisions",
        ["content_sha256"],
    )

    # 3. knowledge_ingestion_runs
    op.create_table(
        "knowledge_ingestion_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id",
            sa.String(36),
            sa.ForeignKey("knowledge_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("parser_name", sa.String(50), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("chunker_version", sa.String(50), nullable=False),
        sa.Column("embedding_version", sa.String(50), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("warning_messages", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 4. knowledge_chunks
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "revision_id",
            sa.String(36),
            sa.ForeignKey("knowledge_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.String(500), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.String(200), nullable=True),
        sa.Column("row_start", sa.Integer(), nullable=True),
        sa.Column("row_end", sa.Integer(), nullable=True),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("embedding_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("revision_id", "chunk_index", name="uq_knowledge_chunk_idx"),
        sa.UniqueConstraint(
            "revision_id",
            "text_sha256",
            "chunk_index",
            name="uq_knowledge_chunk_hash",
        ),
    )
    op.create_index("ix_knowledge_chunks_revision_id", "knowledge_chunks", ["revision_id"])
    op.create_index("ix_knowledge_chunks_text_sha256", "knowledge_chunks", ["text_sha256"])


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_ingestion_runs")
    op.drop_table("knowledge_revisions")
    op.drop_table("knowledge_documents")
