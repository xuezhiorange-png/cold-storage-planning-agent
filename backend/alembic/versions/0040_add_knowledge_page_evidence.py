"""0040: persist page-scoped native/OCR evidence and chunk lineage.

Revision ID: 0040_add_knowledge_page_evidence
Revises: 0039_widen_report_export_artifact_mime_type
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0040_add_knowledge_page_evidence"
down_revision: str | Sequence[str] | None = "0039_widen_report_export_artifact_mime_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PAGE_EVIDENCE_TABLE = "knowledge_page_evidence"
CHUNKS_TABLE = "knowledge_chunks"
CHUNK_EVIDENCE_FK = "fk_knowledge_chunks_page_evidence"


def upgrade() -> None:
    """Create immutable revision/page identity and nullable chunk lineage."""
    op.create_table(
        PAGE_EVIDENCE_TABLE,
        sa.Column("source_page_evidence_id", sa.String(128), primary_key=True),
        sa.Column(
            "revision_id",
            sa.String(36),
            sa.ForeignKey("knowledge_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("extraction_method", sa.String(32), nullable=False),
        sa.Column("extraction_status", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("source_content_sha256", sa.String(64), nullable=False),
        sa.Column("source_authority", sa.String(64), nullable=False),
        sa.Column("is_derived_evidence", sa.Boolean(), nullable=False),
        sa.Column("ocr_engine", sa.String(100), nullable=False),
        sa.Column("ocr_languages", sa.String(100), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("confidence_source", sa.String(50), nullable=False),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "revision_id",
            "page_number",
            name="uq_knowledge_page_evidence_revision_page",
        ),
    )
    op.create_index(
        "ix_knowledge_page_evidence_revision_id",
        PAGE_EVIDENCE_TABLE,
        ["revision_id"],
    )
    op.create_index(
        "ix_knowledge_page_evidence_document_id",
        PAGE_EVIDENCE_TABLE,
        ["document_id"],
    )

    page_evidence_column = sa.Column(
        "source_page_evidence_id",
        sa.String(128),
        sa.ForeignKey(
            f"{PAGE_EVIDENCE_TABLE}.source_page_evidence_id",
            name=CHUNK_EVIDENCE_FK,
        ),
        nullable=True,
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(CHUNKS_TABLE, recreate="always") as batch_op:
            batch_op.add_column(page_evidence_column)
    else:
        op.add_column(CHUNKS_TABLE, page_evidence_column)

    op.create_index(
        "ix_knowledge_chunks_source_page_evidence_id",
        CHUNKS_TABLE,
        ["source_page_evidence_id"],
    )


def downgrade() -> None:
    """Remove lineage only; no derived content is silently truncated."""
    op.drop_index("ix_knowledge_chunks_source_page_evidence_id", table_name=CHUNKS_TABLE)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(CHUNKS_TABLE, recreate="always") as batch_op:
            batch_op.drop_column("source_page_evidence_id")
    else:
        op.drop_constraint(CHUNK_EVIDENCE_FK, CHUNKS_TABLE, type_="foreignkey")
        op.drop_column(CHUNKS_TABLE, "source_page_evidence_id")

    op.drop_index("ix_knowledge_page_evidence_document_id", table_name=PAGE_EVIDENCE_TABLE)
    op.drop_index("ix_knowledge_page_evidence_revision_id", table_name=PAGE_EVIDENCE_TABLE)
    op.drop_table(PAGE_EVIDENCE_TABLE)
