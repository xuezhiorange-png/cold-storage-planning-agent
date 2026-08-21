"""Knowledge repository — INSERT-only persistence with no merge semantics."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.knowledge.domain.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionRun,
    KnowledgePageEvidence,
    KnowledgeRevision,
)
from cold_storage.modules.knowledge.infrastructure.orm import (
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    KnowledgeIngestionRunRecord,
    KnowledgePageEvidenceRecord,
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

        Approved revisions are immutable except for ``withdrawn`` transitions.
        """
        from cold_storage.modules.knowledge.domain.errors import (
            ApprovedRevisionImmutabilityError,
        )

        rec = self._session.get(KnowledgeRevisionRecord, revision_id)
        if rec is None:
            return None

        # Approved revision immutability: only allow approved → withdrawn
        # with ONLY review_status, withdrawn_at, and requires_review fields.
        if rec.review_status == "approved":
            if review_status is not None and review_status == "withdrawn":
                # Define the only fields allowed during approved→withdrawn
                _ALLOWED_FIELDS = {"review_status", "withdrawn_at", "requires_review"}
                _CONTENT_FIELDS = {
                    "ingestion_status",
                    "requires_ocr",
                    "parser_name",
                    "parser_version",
                    "chunker_version",
                    "embedding_version",
                    "extracted_text_length",
                    "page_count",
                    "sheet_count",
                    "warnings",
                    "indexed_at",
                    "reviewed_at",
                    "approved_at",
                }
                provided = _CONTENT_FIELDS & {
                    k
                    for k, v in {
                        "ingestion_status": ingestion_status,
                        "requires_ocr": requires_ocr,
                        "parser_name": parser_name,
                        "parser_version": parser_version,
                        "chunker_version": chunker_version,
                        "embedding_version": embedding_version,
                        "extracted_text_length": extracted_text_length,
                        "page_count": page_count,
                        "sheet_count": sheet_count,
                        "warnings": warnings,
                        "indexed_at": indexed_at,
                        "reviewed_at": reviewed_at,
                        "approved_at": approved_at,
                    }.items()
                    if v is not None
                }
                if provided:
                    raise ApprovedRevisionImmutabilityError(
                        f"Cannot modify content fields {provided} on approved "
                        f"revision {revision_id} during withdrawal"
                    )
            else:
                raise ApprovedRevisionImmutabilityError(
                    f"Revision {revision_id} is approved and immutable"
                )
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
    # Page evidence operations
    # ------------------------------------------------------------------

    def get_page_evidence(self, source_page_evidence_id: str) -> KnowledgePageEvidenceRecord | None:
        """Retrieve one immutable revision/page evidence slot."""
        return self._session.get(KnowledgePageEvidenceRecord, source_page_evidence_id)

    def list_page_evidence(self, revision_id: str) -> list[KnowledgePageEvidenceRecord]:
        """Retrieve page evidence in exact 1-based page order."""
        stmt = (
            select(KnowledgePageEvidenceRecord)
            .where(KnowledgePageEvidenceRecord.revision_id == revision_id)
            .order_by(KnowledgePageEvidenceRecord.page_number)
        )
        return list(self._session.execute(stmt).scalars().all())

    def save_page_evidence(self, evidence: KnowledgePageEvidence) -> KnowledgePageEvidenceRecord:
        """Insert or retry-update one non-approved page evidence slot.

        The source identity and original content hash are immutable.  A retry
        may replace a failed/empty derived result for the same revision/page,
        but it can never mutate an approved revision or point at another
        artifact.
        """
        existing = self.get_page_evidence(evidence.source_page_evidence_id)
        if existing is not None:
            if (
                existing.revision_id != evidence.revision_id
                or existing.document_id != evidence.document_id
                or existing.page_number != evidence.page_number
                or existing.source_content_sha256 != evidence.source_content_sha256
            ):
                raise ValueError("page evidence identity/source lineage mismatch")
            revision = self.get_revision(evidence.revision_id)
            if revision is not None and revision.review_status == "approved":
                from cold_storage.modules.knowledge.domain.errors import (
                    ApprovedRevisionImmutabilityError,
                )

                raise ApprovedRevisionImmutabilityError(
                    f"Revision {evidence.revision_id} is approved and page evidence is immutable"
                )
            existing.extraction_method = evidence.extraction_method
            existing.extraction_status = evidence.extraction_status
            existing.text = evidence.text
            existing.text_sha256 = evidence.text_sha256
            existing.source_authority = evidence.source_authority
            existing.is_derived_evidence = evidence.is_derived_evidence
            existing.original_filename = evidence.original_filename
            existing.ocr_engine = evidence.ocr_engine
            existing.ocr_engine_version = evidence.ocr_engine_version
            existing.ocr_languages = evidence.ocr_languages
            existing.ocr_confidence = evidence.confidence
            existing.confidence_source = evidence.confidence_source
            existing.requires_review = evidence.requires_review
            existing.review_status = evidence.review_status
            existing.warnings = list(evidence.warnings)
            existing.errors = list(evidence.errors)
            existing.ingestion_run_id = evidence.ingestion_run_id or None
            existing.ingestion_provenance = dict(evidence.ingestion_provenance)
            existing.is_complete = evidence.is_complete
            existing.error_code = evidence.error_code
            existing.error_message = evidence.error_message
            existing.updated_at = evidence.updated_at
            self._session.flush()
            return existing

        rec = KnowledgePageEvidenceRecord(
            source_page_evidence_id=evidence.source_page_evidence_id,
            revision_id=evidence.revision_id,
            document_id=evidence.document_id,
            page_number=evidence.page_number,
            extraction_method=evidence.extraction_method,
            extraction_status=evidence.extraction_status,
            text=evidence.text,
            text_sha256=evidence.text_sha256,
            source_content_sha256=evidence.source_content_sha256,
            source_authority=evidence.source_authority,
            is_derived_evidence=evidence.is_derived_evidence,
            original_filename=evidence.original_filename,
            ocr_engine=evidence.ocr_engine,
            ocr_engine_version=evidence.ocr_engine_version,
            ocr_languages=evidence.ocr_languages,
            ocr_confidence=evidence.confidence,
            confidence_source=evidence.confidence_source,
            requires_review=evidence.requires_review,
            review_status=evidence.review_status,
            warnings=list(evidence.warnings),
            errors=list(evidence.errors),
            ingestion_run_id=evidence.ingestion_run_id or None,
            ingestion_provenance=dict(evidence.ingestion_provenance),
            is_complete=evidence.is_complete,
            error_code=evidence.error_code,
            error_message=evidence.error_message,
            created_at=evidence.created_at,
            updated_at=evidence.updated_at,
        )
        self._session.add(rec)
        self._session.flush()
        return rec

    def save_page_evidences(
        self, evidences: list[KnowledgePageEvidence]
    ) -> list[KnowledgePageEvidenceRecord]:
        """Persist a deterministic page evidence set atomically."""
        return [self.save_page_evidence(evidence) for evidence in evidences]

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
                source_page_evidence_id=chunk.source_page_evidence_id or None,
                is_ocr_derived=chunk.is_ocr_derived,
                requires_review=chunk.requires_review,
                embedding=chunk.embedding,
                embedding_dimension=chunk.embedding_dimension,
                embedding_version=chunk.embedding_version,
                created_at=chunk.created_at,
            )
            self._session.add(rec)
            records.append(rec)
        self._session.flush()
        return records

    def save_chunks_idempotent(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunkRecord]:
        """Persist chunks once and verify exact equality on retry."""
        if not chunks:
            return []
        existing = self.get_chunks(chunks[0].revision_id)
        if not existing:
            return self.save_chunks(chunks)
        if len(existing) != len(chunks):
            raise ValueError("existing chunk set differs from deterministic retry")
        for record, expected in zip(existing, chunks, strict=True):
            if (
                record.id != expected.id
                or record.chunk_index != expected.chunk_index
                or record.text_sha256 != expected.text_sha256
                or (record.source_page_evidence_id or "")
                != (expected.source_page_evidence_id or "")
                or record.is_ocr_derived != expected.is_ocr_derived
                or record.requires_review != expected.requires_review
                or list(record.embedding or []) != list(expected.embedding or [])
            ):
                raise ValueError("existing chunk set does not match deterministic retry")
        return existing

    def get_chunks(self, revision_id: str) -> list[KnowledgeChunkRecord]:
        """Retrieve all chunks for a revision, ordered by chunk index."""
        stmt = (
            select(KnowledgeChunkRecord)
            .where(KnowledgeChunkRecord.revision_id == revision_id)
            .order_by(KnowledgeChunkRecord.chunk_index)
        )
        return list(self._session.execute(stmt).scalars().all())
