"""Knowledge repository — INSERT-only persistence with no merge semantics."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.knowledge.domain.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionRun,
    KnowledgeRevision,
)
from cold_storage.modules.knowledge.infrastructure.orm import (
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    KnowledgeIngestionRunRecord,
    KnowledgeRevisionRecord,
)


class KnowledgeRepository:
    """Repository for knowledge domain entities.

    All writes are INSERT-only — existing records are never merged or updated
    except for explicit status transitions via ``update_revision_status``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Document operations
    # ------------------------------------------------------------------

    def save_document(self, doc: KnowledgeDocument) -> KnowledgeDocumentRecord:
        """Persist a new knowledge document."""
        rec = KnowledgeDocumentRecord(
            id=doc.id,
            code=doc.code,
            title=doc.title,
            document_category=doc.document_category,
            source_type=doc.source_type,
            source_reference=doc.source_reference,
            owner=doc.owner,
            current_revision_number=doc.current_revision_number,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        self._session.add(rec)
        self._session.flush()
        return rec

    def get_document(self, document_id: str) -> KnowledgeDocumentRecord | None:
        """Retrieve a document by ID."""
        return self._session.get(KnowledgeDocumentRecord, document_id)

    def get_document_by_code(self, code: str) -> KnowledgeDocumentRecord | None:
        """Retrieve a document by its unique code."""
        stmt = select(KnowledgeDocumentRecord).where(KnowledgeDocumentRecord.code == code)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_documents(self) -> list[KnowledgeDocumentRecord]:
        """List all knowledge documents."""
        stmt = select(KnowledgeDocumentRecord).order_by(KnowledgeDocumentRecord.created_at)
        return list(self._session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Revision operations
    # ------------------------------------------------------------------

    def save_revision(self, rev: KnowledgeRevision) -> KnowledgeRevisionRecord:
        """Persist a new document revision."""
        rec = KnowledgeRevisionRecord(
            id=rev.id,
            document_id=rev.document_id,
            revision_number=rev.revision_number,
            version_label=rev.version_label,
            original_filename=rev.original_filename,
            safe_filename=rev.safe_filename,
            mime_type=rev.mime_type,
            file_extension=rev.file_extension,
            file_size_bytes=rev.file_size_bytes,
            content_sha256=rev.content_sha256,
            storage_key=rev.storage_key,
            ingestion_status=rev.ingestion_status,
            review_status=rev.review_status,
            requires_ocr=rev.requires_ocr,
            requires_review=rev.requires_review,
            parser_name=rev.parser_name,
            parser_version=rev.parser_version,
            chunker_version=rev.chunker_version,
            embedding_version=rev.embedding_version,
            extracted_text_length=rev.extracted_text_length,
            page_count=rev.page_count,
            sheet_count=rev.sheet_count,
            metadata_snapshot=rev.metadata_snapshot,
            warning_messages=rev.warnings,
            created_at=rev.created_at,
            indexed_at=rev.indexed_at,
            reviewed_at=rev.reviewed_at,
            approved_at=rev.approved_at,
            withdrawn_at=rev.withdrawn_at,
        )
        self._session.add(rec)
        self._session.flush()
        return rec

    def get_revision(self, revision_id: str) -> KnowledgeRevisionRecord | None:
        """Retrieve a revision by ID."""
        return self._session.get(KnowledgeRevisionRecord, revision_id)

    def list_revisions(self, document_id: str) -> list[KnowledgeRevisionRecord]:
        """List all revisions for a document, ordered by revision number."""
        stmt = (
            select(KnowledgeRevisionRecord)
            .where(KnowledgeRevisionRecord.document_id == document_id)
            .order_by(KnowledgeRevisionRecord.revision_number)
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_revision_by_hash(
        self, document_id: str, content_sha256: str
    ) -> KnowledgeRevisionRecord | None:
        """Retrieve a revision by document ID and content hash."""
        stmt = select(KnowledgeRevisionRecord).where(
            KnowledgeRevisionRecord.document_id == document_id,
            KnowledgeRevisionRecord.content_sha256 == content_sha256,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def update_revision_status(
        self,
        revision_id: str,
        *,
        ingestion_status: str | None = None,
        review_status: str | None = None,
        requires_ocr: bool | None = None,
        requires_review: bool | None = None,
        parser_name: str | None = None,
        parser_version: str | None = None,
        chunker_version: str | None = None,
        embedding_version: str | None = None,
        extracted_text_length: int | None = None,
        page_count: int | None = None,
        sheet_count: int | None = None,
        warnings: list[str] | None = None,
        indexed_at: datetime | None = None,
        reviewed_at: datetime | None = None,
        approved_at: datetime | None = None,
        withdrawn_at: datetime | None = None,
    ) -> KnowledgeRevisionRecord | None:
        """Update specific fields on a revision (status transitions).

        Only non-None fields are updated. This is the only mutation method
        for revisions — all other writes are INSERT-only.
        """
        rec = self._session.get(KnowledgeRevisionRecord, revision_id)
        if rec is None:
            return None
        if ingestion_status is not None:
            rec.ingestion_status = ingestion_status
        if review_status is not None:
            rec.review_status = review_status
        if requires_ocr is not None:
            rec.requires_ocr = requires_ocr
        if requires_review is not None:
            rec.requires_review = requires_review
        if parser_name is not None:
            rec.parser_name = parser_name
        if parser_version is not None:
            rec.parser_version = parser_version
        if chunker_version is not None:
            rec.chunker_version = chunker_version
        if embedding_version is not None:
            rec.embedding_version = embedding_version
        if extracted_text_length is not None:
            rec.extracted_text_length = extracted_text_length
        if page_count is not None:
            rec.page_count = page_count
        if sheet_count is not None:
            rec.sheet_count = sheet_count
        if warnings is not None:
            rec.warning_messages = list(warnings)
        if indexed_at is not None:
            rec.indexed_at = indexed_at
        if reviewed_at is not None:
            rec.reviewed_at = reviewed_at
        if approved_at is not None:
            rec.approved_at = approved_at
        if withdrawn_at is not None:
            rec.withdrawn_at = withdrawn_at
        self._session.flush()
        return rec

    # ------------------------------------------------------------------
    # Ingestion run operations
    # ------------------------------------------------------------------

    def save_ingestion_run(self, run: KnowledgeIngestionRun) -> KnowledgeIngestionRunRecord:
        """Persist a new ingestion run record."""
        rec = KnowledgeIngestionRunRecord(
            id=run.id,
            revision_id=run.revision_id,
            status=run.status,
            parser_name=run.parser_name,
            parser_version=run.parser_version,
            chunker_version=run.chunker_version,
            embedding_version=run.embedding_version,
            input_snapshot=run.input_snapshot,
            result_snapshot=run.result_snapshot,
            warning_messages=run.warning_messages,
            error_code=run.error_code,
            error_message=run.error_message,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )
        self._session.add(rec)
        self._session.flush()
        return rec

    # ------------------------------------------------------------------
    # Chunk operations
    # ------------------------------------------------------------------

    def save_chunks(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunkRecord]:
        """Batch-insert knowledge chunks."""
        records: list[KnowledgeChunkRecord] = []
        for chunk in chunks:
            rec = KnowledgeChunkRecord(
                id=chunk.id,
                revision_id=chunk.revision_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                text_sha256=chunk.text_sha256,
                character_count=chunk.character_count,
                token_count=chunk.token_count,
                section_path=chunk.section_path,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                sheet_name=chunk.sheet_name,
                row_start=chunk.row_start,
                row_end=chunk.row_end,
                source_locator=chunk.source_locator,
                embedding=chunk.embedding,
                embedding_dimension=chunk.embedding_dimension,
                embedding_version=chunk.embedding_version,
                created_at=chunk.created_at,
            )
            self._session.add(rec)
            records.append(rec)
        self._session.flush()
        return records

    def get_chunks(self, revision_id: str) -> list[KnowledgeChunkRecord]:
        """Retrieve all chunks for a revision, ordered by chunk index."""
        stmt = (
            select(KnowledgeChunkRecord)
            .where(KnowledgeChunkRecord.revision_id == revision_id)
            .order_by(KnowledgeChunkRecord.chunk_index)
        )
        return list(self._session.execute(stmt).scalars().all())
