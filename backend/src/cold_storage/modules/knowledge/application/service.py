"""Knowledge application service — orchestrates domain and infrastructure."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from datetime import UTC, datetime
from typing import IO, Any

from sqlalchemy.orm import Session

from cold_storage.modules.knowledge.domain.chunking import (
    CHUNKER_VERSION,
    chunk_blocks,
)
from cold_storage.modules.knowledge.domain.embedding import (
    DEFAULT_CONFIG as EMBEDDING_CONFIG,
)
from cold_storage.modules.knowledge.domain.embedding import (
    generate_embedding,
)
from cold_storage.modules.knowledge.domain.errors import (
    DocumentNotFoundError,
    DuplicateContentError,
    FileTooLargeError,
    IngestionFailedError,
    RevisionNotFoundError,
    UnsupportedFileTypeError,
)
from cold_storage.modules.knowledge.domain.lifecycle import (
    assert_not_approved,
    validate_ingestion_transition,
    validate_review_eligibility,
    validate_review_transition,
)
from cold_storage.modules.knowledge.domain.models import (
    ChunkingConfig,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionRun,
    KnowledgePageEvidence,
    KnowledgeRevision,
    ParsedBlock,
    RetrievalCandidate,
    RetrievalProfile,
    make_source_page_evidence_id,
)
from cold_storage.modules.knowledge.domain.retrieval import search_chunks
from cold_storage.modules.knowledge.infrastructure.ocr_adapter import (
    DEFAULT_OCR_LANGUAGES,
    OcrAdapter,
    OcrPageResult,
)
from cold_storage.modules.knowledge.infrastructure.parsers import (
    csv_parser,
    docx_parser,
    markdown_parser,
    pdf_parser,
    text_parser,
    xlsx_parser,
)
from cold_storage.modules.knowledge.infrastructure.parsers.base import (
    PARSER_VERSION as PARSER_VER,
)
from cold_storage.modules.knowledge.infrastructure.parsers.base import (
    get_parser_for_file,
)
from cold_storage.modules.knowledge.infrastructure.repository import (
    KnowledgeRepository,
)
from cold_storage.modules.knowledge.infrastructure.storage import (
    LocalDocumentStorage,
)
from cold_storage.modules.projects.infrastructure.orm import AuditEventRecord

# Importing the concrete parser modules is part of the application composition:
# each module registers its parser at import time. Keep the references alive so
# clean processes do not depend on another test or module importing a parser.
_PARSER_MODULES = (csv_parser, docx_parser, markdown_parser, pdf_parser, text_parser, xlsx_parser)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".txt", ".md", ".csv", ".docx", ".xlsx", ".pdf"})

KNOWLEDGE_MAX_UPLOAD_BYTES: int = int(
    os.environ.get("KNOWLEDGE_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))
)

# ZIP-based archive safety limits
_ZIP_MAX_MEMBER_COUNT: int = 200
_ZIP_MAX_DECOMPRESSED_BYTES: int = 200 * 1024 * 1024  # 200 MiB


def _sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe version of *filename*."""
    name = unicodedata.normalize("NFKC", filename)
    name = re.sub(r"[^\w.\-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:200] if name else "unnamed"


def _extract_extension(filename: str) -> str:
    """Return the lowercase extension including the dot, or empty string."""
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    return ""


def _compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest for *data*."""
    return hashlib.sha256(data).hexdigest()


def _stable_chunk_id(revision_id: str, chunk_index: int, text_sha256: str) -> str:
    """Build a retry-stable chunk identity for one immutable revision."""
    payload = f"{revision_id}:chunk:{chunk_index}:{text_sha256}".encode()
    # The existing knowledge_chunks.id column is String(36); retain a
    # deterministic 120-bit suffix without widening that frozen schema.
    return f"chunk-{hashlib.sha256(payload).hexdigest()[:30]}"


def _record_page_error(
    errors: list[dict[str, str]],
    current_code: str,
    current_message: str,
    code: str,
    message: str,
) -> tuple[str, str]:
    """Append one bounded machine-readable page error without duplicates."""
    if not current_code:
        current_code = code
    if not current_message:
        current_message = message
    if not any(item.get("code") == code for item in errors):
        errors.append({"code": code, "message": message})
    return current_code, current_message


class KnowledgeService:
    """Application service for the knowledge module.

    Orchestrates document upload, parsing, chunking, embedding, and retrieval.
    """

    def __init__(self, session: Session, ocr_adapter: OcrAdapter | None = None) -> None:
        self._session = session
        self._repo = KnowledgeRepository(session)
        self._ocr_adapter = ocr_adapter or OcrAdapter(languages=DEFAULT_OCR_LANGUAGES)
        self._storage = LocalDocumentStorage(
            base_dir=os.environ.get("KNOWLEDGE_STORAGE_DIR", "/tmp/knowledge-storage"),
            max_upload_bytes=KNOWLEDGE_MAX_UPLOAD_BYTES,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_document(
        self,
        *,
        code: str,
        title: str,
        document_category: str = "other",
        source_type: str = "upload",
        source_reference: str = "",
        owner: str = "",
        file: IO[bytes],
        content_sha256: str,
        file_size: int,
        filename: str,
        mime_type: str,
        version_label: str = "",
    ) -> dict[str, Any]:
        """Create a new knowledge document with its first revision.

        ``file`` must be a seekable binary stream. The caller computes
        ``content_sha256`` and ``file_size`` while streaming the upload.
        """
        ext = _extract_extension(filename)
        self._validate_file_type(ext, mime_type)
        self._validate_file_size(file_size)

        # Check duplicate code
        existing = self._repo.get_document_by_code(code)
        if existing is not None:
            raise DuplicateContentError(f"Document with code {code!r} already exists")

        # Create document
        doc = KnowledgeDocument(
            code=code,
            title=title,
            document_category=document_category,
            source_type=source_type,
            source_reference=source_reference,
            owner=owner,
            current_revision_number=1,
        )
        self._repo.save_document(doc)

        # Create revision 1
        revision_number = 1
        rev = KnowledgeRevision(
            document_id=doc.id,
            revision_number=revision_number,
            version_label=version_label,
            original_filename=filename,
            safe_filename=_sanitize_filename(filename),
            mime_type=mime_type,
            file_extension=ext,
            file_size_bytes=file_size,
            content_sha256=content_sha256,
            storage_key="",  # filled after save
            ingestion_status="uploaded",
            review_status="unverified",
        )

        # Save file to storage
        stored = self._storage.save(file, rev.id, content_sha256)
        rev = KnowledgeRevision(
            **{
                **rev.__dict__,
                "storage_key": stored.storage_key,
            }
        )

        try:
            self._repo.save_revision(rev)

            # Audit event
            self._audit_event(
                actor=owner or "system",
                action="document.created",
                entity_type="knowledge_document",
                entity_id=doc.id,
                before_snapshot={},
                after_snapshot={
                    "code": code,
                    "title": title,
                    "revision_number": revision_number,
                },
            )

            self._session.commit()
        except Exception:
            self._session.rollback()
            # Clean up orphan file
            try:
                self._storage.delete(stored.storage_key)
            except Exception:
                import logging

                logging.warning(f"Failed to clean up orphan file: {stored.storage_key}")
            raise

        return {
            "document_id": doc.id,
            "document_code": doc.code,
            "revision_id": rev.id,
            "revision_number": revision_number,
            "ingestion_status": rev.ingestion_status,
            "review_status": rev.review_status,
        }

    def create_revision(
        self,
        *,
        document_id: str,
        file: IO[bytes],
        content_sha256: str,
        file_size: int,
        filename: str,
        mime_type: str,
        version_label: str = "",
    ) -> dict[str, Any]:
        """Create a new revision for an existing document."""
        doc_rec = self._repo.get_document(document_id)
        if doc_rec is None:
            raise DocumentNotFoundError(f"Document {document_id!r} not found")

        ext = _extract_extension(filename)
        self._validate_file_type(ext, mime_type)
        self._validate_file_size(file_size)

        # Check duplicate content hash
        existing = self._repo.get_revision_by_hash(document_id, content_sha256)
        if existing is not None:
            raise DuplicateContentError("A revision with identical content already exists")

        next_number = doc_rec.current_revision_number + 1

        rev = KnowledgeRevision(
            document_id=document_id,
            revision_number=next_number,
            version_label=version_label,
            original_filename=filename,
            safe_filename=_sanitize_filename(filename),
            mime_type=mime_type,
            file_extension=ext,
            file_size_bytes=file_size,
            content_sha256=content_sha256,
            storage_key="",
            ingestion_status="uploaded",
            review_status="unverified",
        )

        stored = self._storage.save(file, rev.id, content_sha256)
        rev = KnowledgeRevision(
            **{
                **rev.__dict__,
                "storage_key": stored.storage_key,
            }
        )

        try:
            self._repo.save_revision(rev)

            # Update document's current revision number
            doc_rec.current_revision_number = next_number
            doc_rec.updated_at = datetime.now(UTC)
            self._session.flush()

            self._audit_event(
                actor=doc_rec.owner or "system",
                action="revision.created",
                entity_type="knowledge_document",
                entity_id=document_id,
                before_snapshot={"revision_number": doc_rec.current_revision_number - 1},
                after_snapshot={
                    "revision_number": next_number,
                    "content_sha256": content_sha256,
                },
            )

            self._session.commit()
        except Exception:
            self._session.rollback()
            # Clean up orphan file
            try:
                self._storage.delete(stored.storage_key)
            except Exception:
                import logging

                logging.warning(f"Failed to clean up orphan file: {stored.storage_key}")
            raise

        return {
            "revision_id": rev.id,
            "revision_number": next_number,
            "document_id": document_id,
            "ingestion_status": rev.ingestion_status,
            "review_status": rev.review_status,
        }

    def ingest_revision(
        self,
        *,
        document_id: str,
        revision_number: int,
    ) -> dict[str, Any]:
        """Run deterministic parse/OCR -> evidence -> chunk -> embed -> persist."""
        rev_rec = self._find_revision(document_id, revision_number)
        assert_not_approved(rev_rec.review_status)

        # An already indexed unapproved revision is a deterministic retry,
        # not permission to mint another evidence/chunk set.  Approved
        # revisions are rejected above before this idempotent readback path.
        if rev_rec.ingestion_status == "indexed":
            existing_chunks = self._repo.get_chunks(rev_rec.id)
            return {
                "document_id": document_id,
                "revision_number": revision_number,
                "ingestion_status": rev_rec.ingestion_status,
                "chunk_count": len(existing_chunks),
                "extracted_text_length": rev_rec.extracted_text_length,
            }

        if rev_rec.ingestion_status not in {"requires_ocr", "processing"}:
            validate_ingestion_transition(rev_rec.ingestion_status, "processing")

        # Create ingestion run
        run = KnowledgeIngestionRun(
            revision_id=rev_rec.id,
            status="processing",
            parser_name=rev_rec.parser_name or "",
            parser_version=PARSER_VER,
            chunker_version=CHUNKER_VERSION,
            embedding_version=EMBEDDING_CONFIG.version,
            input_snapshot={
                "revision_id": rev_rec.id,
                "document_id": document_id,
                "source_content_sha256": rev_rec.content_sha256,
            },
        )
        run_rec = self._repo.save_ingestion_run(run)

        # Update revision status
        self._repo.update_revision_status(
            rev_rec.id,
            ingestion_status="processing",
            parser_version=PARSER_VER,
            chunker_version=CHUNKER_VERSION,
            embedding_version=EMBEDDING_CONFIG.version,
        )

        warnings: list[str] = []
        selected_pages: list[int] = []

        try:
            # Read stored file
            file_content = self._storage.open(rev_rec.storage_key).read()
            actual_hash = _compute_sha256(file_content)
            if actual_hash != rev_rec.content_sha256:
                raise IngestionFailedError(
                    "stored artifact hash does not match revision content_sha256"
                )

            # Determine parser
            parser = get_parser_for_file(rev_rec.original_filename, rev_rec.mime_type)
            if parser is None:
                raise IngestionFailedError(
                    f"No parser available for extension {rev_rec.file_extension}"
                )

            # Parse — all parsers return ParseResult
            parse_result = parser.parse(file_content, rev_rec.original_filename)
            blocks = parse_result.blocks

            # Determine page/sheet counts.  PDF page_count is authoritative,
            # including pages that intentionally have no native blocks.
            page_count: int | None = parse_result.page_count
            sheet_count: int | None = None
            pages = {b.page_start for b in blocks if b.page_start is not None}
            sheets = {b.sheet_name for b in blocks if b.sheet_name is not None}
            if page_count is None and pages:
                page_count = max(pages)
            if sheets:
                sheet_count = len(sheets)

            selected_pages = list(parse_result.ocr_page_numbers)
            if selected_pages:
                if page_count is None:
                    raise IngestionFailedError("OCR page selection has no PDF page_count")
                if len(selected_pages) != len(set(selected_pages)):
                    raise IngestionFailedError("OCR page selection contains duplicates")
                if any(page < 1 or page > page_count for page in selected_pages):
                    raise IngestionFailedError("OCR page selection contains out-of-range pages")
                if rev_rec.file_extension != ".pdf":
                    raise IngestionFailedError("OCR page selection is only valid for PDF revisions")
                selected_pages = sorted(selected_pages)

            # Collect parser warnings (e.g. image-only pages)
            if parse_result.warnings:
                warnings.extend(parse_result.warnings)

            page_evidence: list[KnowledgePageEvidence] = []
            evidence_by_page: dict[int, KnowledgePageEvidence] = {}
            index_blocks = blocks
            if rev_rec.file_extension == ".pdf":
                if page_count is None:
                    raise IngestionFailedError("PDF parser did not return page_count")
                (
                    page_evidence,
                    evidence_by_page,
                    index_blocks,
                ) = self._build_pdf_page_evidence(
                    revision=rev_rec,
                    content=file_content,
                    blocks=blocks,
                    page_count=page_count,
                    selected_pages=selected_pages,
                    warnings=warnings,
                    ingestion_run_id=run.id,
                )

            # Persist evidence before chunks.  Incomplete OCR evidence is
            # durable for retry, but it never reaches the indexed chunk set.
            if page_evidence:
                self._repo.save_page_evidences(page_evidence)

            all_required_evidence_complete = all(e.is_complete for e in page_evidence)
            requires_ocr = not all_required_evidence_complete if page_evidence else False
            requires_review = True
            embedded_chunks: list[KnowledgeChunk] = []
            if not requires_ocr:
                config = ChunkingConfig()
                chunks = chunk_blocks(index_blocks, config)

                chunks_with_id: list[KnowledgeChunk] = []
                for c in chunks:
                    evidence = evidence_by_page.get(c.page_start or 0)
                    evidence_id = ""
                    is_ocr_derived = False
                    chunk_requires_review = True
                    if c.page_start is not None and c.page_start == c.page_end and evidence:
                        evidence_id = evidence.source_page_evidence_id
                        is_ocr_derived = evidence.is_derived_evidence
                        chunk_requires_review = evidence.requires_review
                    chunks_with_id.append(
                        KnowledgeChunk(
                            id=_stable_chunk_id(rev_rec.id, c.chunk_index, c.text_sha256),
                            revision_id=rev_rec.id,
                            chunk_index=c.chunk_index,
                            text=c.text,
                            text_sha256=c.text_sha256,
                            character_count=c.character_count,
                            token_count=c.token_count,
                            section_path=c.section_path,
                            page_start=c.page_start,
                            page_end=c.page_end,
                            sheet_name=c.sheet_name,
                            row_start=c.row_start,
                            row_end=c.row_end,
                            source_locator=c.source_locator,
                            source_page_evidence_id=evidence_id,
                            is_ocr_derived=is_ocr_derived,
                            requires_review=chunk_requires_review,
                        )
                    )

                for c in chunks_with_id:
                    emb = generate_embedding(c.text, EMBEDDING_CONFIG)
                    embedded_chunks.append(
                        KnowledgeChunk(
                            id=c.id,
                            revision_id=c.revision_id,
                            chunk_index=c.chunk_index,
                            text=c.text,
                            text_sha256=c.text_sha256,
                            character_count=c.character_count,
                            token_count=c.token_count,
                            section_path=c.section_path,
                            page_start=c.page_start,
                            page_end=c.page_end,
                            sheet_name=c.sheet_name,
                            row_start=c.row_start,
                            row_end=c.row_end,
                            source_locator=c.source_locator,
                            source_page_evidence_id=c.source_page_evidence_id,
                            is_ocr_derived=c.is_ocr_derived,
                            requires_review=c.requires_review,
                            embedding=emb,
                            embedding_dimension=len(emb),
                            embedding_version=EMBEDDING_CONFIG.version,
                        )
                    )

                if embedded_chunks:
                    self._repo.save_chunks_idempotent(embedded_chunks)

            final_status = "requires_ocr" if requires_ocr else "indexed"
            extracted_text_length = sum(len(e.text) for e in page_evidence)
            if not page_evidence:
                extracted_text_length = sum(len(b.text) for b in index_blocks)
            if requires_ocr:
                warnings.append(
                    "OCR evidence is incomplete; no native or OCR chunks were published"
                )

            # Update revision status
            now = datetime.now(UTC)
            self._repo.update_revision_status(
                rev_rec.id,
                ingestion_status=final_status,
                requires_ocr=requires_ocr,
                requires_review=requires_review,
                parser_name=parser.name,
                parser_version=PARSER_VER,
                chunker_version=CHUNKER_VERSION,
                embedding_version=EMBEDDING_CONFIG.version,
                extracted_text_length=extracted_text_length,
                page_count=page_count,
                sheet_count=sheet_count,
                indexed_at=now if final_status == "indexed" else None,
                warnings=warnings,
            )

            # Update ingestion run
            run_rec.status = "completed"
            run_rec.result_snapshot = {
                "chunk_count": len(embedded_chunks),
                "extracted_text_length": extracted_text_length,
                "source_page_evidence_ids": [
                    evidence.source_page_evidence_id for evidence in page_evidence
                ],
                "ocr_page_numbers": selected_pages,
                "complete": final_status == "indexed",
            }
            run_rec.completed_at = now
            self._session.flush()

            self._audit_event(
                actor=rev_rec.document.owner if rev_rec.document else "system",
                action="revision.ingested",
                entity_type="knowledge_document",
                entity_id=document_id,
                before_snapshot={"ingestion_status": "processing"},
                after_snapshot={
                    "ingestion_status": final_status,
                    "chunk_count": len(embedded_chunks),
                    "ocr_page_numbers": selected_pages,
                },
            )
            self._session.commit()

        except Exception as exc:
            self._session.rollback()
            try:
                self._repo.update_revision_status(
                    rev_rec.id,
                    ingestion_status="failed",
                    requires_ocr=bool(selected_pages),
                    requires_review=True,
                )
                failed_run = KnowledgeIngestionRun(
                    id=run.id,
                    revision_id=run.revision_id,
                    status="failed",
                    parser_name=run.parser_name,
                    parser_version=run.parser_version,
                    chunker_version=run.chunker_version,
                    embedding_version=run.embedding_version,
                    input_snapshot=run.input_snapshot,
                    result_snapshot={},
                    warning_messages=warnings,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    created_at=run.created_at,
                    completed_at=datetime.now(UTC),
                )
                self._repo.save_ingestion_run(failed_run)
                self._session.commit()
            except Exception:
                self._session.rollback()

            raise IngestionFailedError(f"Ingestion failed: {exc}") from exc

        return {
            "document_id": document_id,
            "revision_number": revision_number,
            "ingestion_status": final_status,
            "chunk_count": len(embedded_chunks),
            "extracted_text_length": extracted_text_length,
        }

    def _build_pdf_page_evidence(
        self,
        *,
        revision: Any,
        content: bytes,
        blocks: list[ParsedBlock],
        page_count: int,
        selected_pages: list[int],
        warnings: list[str],
        ingestion_run_id: str,
    ) -> tuple[list[KnowledgePageEvidence], dict[int, KnowledgePageEvidence], list[ParsedBlock]]:
        """Build one evidence slot per PDF page and OCR only selected pages."""
        now = datetime.now(UTC)
        selected = set(selected_pages)
        native_by_page: dict[int, list[ParsedBlock]] = {}
        for block in blocks:
            if block.page_start is not None and block.page_start == block.page_end:
                native_by_page.setdefault(block.page_start, []).append(block)

        evidence: list[KnowledgePageEvidence] = []
        evidence_by_page: dict[int, KnowledgePageEvidence] = {}
        for page_number in range(1, page_count + 1):
            if page_number in selected:
                continue
            page_blocks = native_by_page.get(page_number, [])
            page_text = "\n\n".join(
                block.text.strip() for block in page_blocks if block.text.strip()
            )
            page_id = make_source_page_evidence_id(revision.id, page_number)
            complete = bool(page_text)
            extraction_status = "completed" if complete else "empty"
            error_code = "" if complete else "native_text_empty"
            error_message = "" if complete else "native page text was not produced"
            item = KnowledgePageEvidence(
                source_page_evidence_id=page_id,
                revision_id=revision.id,
                document_id=revision.document_id,
                page_number=page_number,
                extraction_method="native_text",
                extraction_status=extraction_status,
                text=page_text,
                text_sha256=_compute_sha256(page_text.encode("utf-8")),
                source_content_sha256=revision.content_sha256,
                source_authority="original_artifact",
                is_derived_evidence=False,
                original_filename=revision.original_filename,
                ocr_engine="",
                ocr_engine_version="",
                ocr_languages="",
                confidence=None,
                confidence_source="unavailable",
                requires_review=False,
                review_status="unverified",
                warnings=[],
                errors=([] if complete else [{"code": error_code, "message": error_message}]),
                ingestion_run_id=ingestion_run_id,
                ingestion_provenance={
                    "source_authority": "original_artifact",
                    "original_filename": revision.original_filename,
                    "source_content_sha256": revision.content_sha256,
                    "document_id": revision.document_id,
                    "revision_id": revision.id,
                    "ingestion_run_id": ingestion_run_id,
                    "extraction_method": "native_text",
                    "page_number": page_number,
                },
                is_complete=complete,
                error_code=error_code,
                error_message=error_message,
                created_at=now,
                updated_at=now,
            )
            evidence.append(item)
            evidence_by_page[page_number] = item

        ocr_blocks: list[ParsedBlock] = []
        if selected_pages:
            try:
                ocr_results = self._ocr_adapter.ocr_pages(
                    content=content,
                    revision_id=revision.id,
                    source_content_sha256=revision.content_sha256,
                    page_numbers=selected_pages,
                    document_id=revision.document_id,
                    ingestion_run_id=ingestion_run_id,
                    original_filename=revision.original_filename,
                )
            except Exception as exc:
                ocr_results = [
                    OcrPageResult.failure(
                        page_number=page_number,
                        status="failed",
                        error_code=type(exc).__name__,
                        error_message=str(exc),
                        document_id=revision.document_id,
                        revision_id=revision.id,
                        source_content_sha256=revision.content_sha256,
                        ingestion_run_id=ingestion_run_id,
                        original_filename=revision.original_filename,
                    )
                    for page_number in selected_pages
                ]

            result_by_page: dict[int, OcrPageResult] = {}
            for result in ocr_results:
                if result.page_number not in selected or result.page_number in result_by_page:
                    continue
                result_by_page[result.page_number] = result

            for page_number in selected_pages:
                result = result_by_page.get(
                    page_number,
                    OcrPageResult.failure(
                        page_number=page_number,
                        status="failed",
                        error_code="missing_ocr_result",
                        error_message="OCR adapter did not return the required page",
                        document_id=revision.document_id,
                        revision_id=revision.id,
                        source_content_sha256=revision.content_sha256,
                        ingestion_run_id=ingestion_run_id,
                        original_filename=revision.original_filename,
                    ),
                )
                normalized_text = unicodedata.normalize("NFKC", result.text).strip()
                recomputed_hash = _compute_sha256(normalized_text.encode("utf-8"))
                status = {
                    "complete": "completed",
                    "hash_mismatch": "failed",
                    "missing_native_text": "failed",
                }.get(result.extraction_status, result.extraction_status)
                if status not in {
                    "completed",
                    "requires_ocr",
                    "unavailable",
                    "empty",
                    "failed",
                }:
                    status = "failed"
                error_code = result.error_code
                error_message = result.error_message
                page_errors = list(result.errors)
                if (error_code or error_message) and not any(
                    item.get("code") == error_code for item in page_errors
                ):
                    page_errors.append({"code": error_code, "message": error_message})

                expected_page_id = make_source_page_evidence_id(revision.id, page_number)
                if result.source_page_evidence_id != expected_page_id:
                    status = "failed"
                    error_code, error_message = _record_page_error(
                        page_errors,
                        error_code,
                        error_message,
                        "source_page_evidence_id_mismatch",
                        "OCR result does not use the stable revision/page identity",
                    )
                if result.revision_id and result.revision_id != revision.id:
                    status = "failed"
                    error_code, error_message = _record_page_error(
                        page_errors,
                        error_code,
                        error_message,
                        "revision_id_mismatch",
                        "OCR result revision does not match source",
                    )
                if result.document_id and result.document_id != revision.document_id:
                    status = "failed"
                    error_code, error_message = _record_page_error(
                        page_errors,
                        error_code,
                        error_message,
                        "document_id_mismatch",
                        "OCR result document does not match source",
                    )

                hash_matches = bool(result.text_sha256) and result.text_sha256 == recomputed_hash
                if status == "empty" or (status == "completed" and not normalized_text):
                    status = "empty"
                    error_code, error_message = _record_page_error(
                        page_errors,
                        error_code,
                        error_message,
                        "ocr_empty",
                        "OCR returned no text",
                    )
                if status == "completed" and not hash_matches:
                    status = "failed"
                    error_code, error_message = _record_page_error(
                        page_errors,
                        error_code,
                        error_message,
                        "ocr_text_hash_mismatch",
                        "OCR text hash is not reproducible",
                    )
                if status == "completed" and not result.ocr_engine_version:
                    status = "unavailable"
                    error_code, error_message = _record_page_error(
                        page_errors,
                        error_code,
                        error_message,
                        "ocr_engine_version_unavailable",
                        "OCR engine version is required for completed evidence",
                    )
                complete = status == "completed" and bool(normalized_text) and hash_matches
                page_id = expected_page_id
                provenance = dict(result.ingestion_provenance)
                provenance.update(
                    {
                        "source_authority": "original_artifact",
                        "original_filename": revision.original_filename,
                        "source_content_sha256": revision.content_sha256,
                        "document_id": revision.document_id,
                        "revision_id": revision.id,
                        "ingestion_run_id": ingestion_run_id,
                        "extraction_method": "ocr",
                        "page_number": page_number,
                    }
                )
                item = KnowledgePageEvidence(
                    source_page_evidence_id=page_id,
                    revision_id=revision.id,
                    document_id=revision.document_id,
                    page_number=page_number,
                    extraction_method="ocr",
                    extraction_status=status,
                    text=normalized_text if complete else "",
                    text_sha256=recomputed_hash,
                    source_content_sha256=revision.content_sha256,
                    source_authority="original_artifact",
                    is_derived_evidence=True,
                    original_filename=revision.original_filename,
                    ocr_engine=result.ocr_engine,
                    ocr_engine_version=result.ocr_engine_version,
                    ocr_languages=result.ocr_languages or DEFAULT_OCR_LANGUAGES,
                    confidence=result.confidence if complete else None,
                    confidence_source=result.confidence_source
                    if complete and result.confidence is not None
                    else "unavailable",
                    requires_review=True,
                    review_status="unverified",
                    warnings=list(result.warnings),
                    errors=page_errors,
                    ingestion_run_id=ingestion_run_id,
                    ingestion_provenance=provenance,
                    is_complete=complete,
                    error_code=error_code,
                    error_message=error_message,
                    created_at=now,
                    updated_at=now,
                )
                evidence.append(item)
                evidence_by_page[page_number] = item
                if complete:
                    ocr_blocks.append(
                        ParsedBlock(
                            text=normalized_text,
                            block_type="paragraph",
                            section_path=f"page:{page_number}",
                            page_start=page_number,
                            page_end=page_number,
                            source_order=page_number,
                            metadata={
                                "parser_version": PARSER_VER,
                                "page_number": page_number,
                                "extraction_method": "ocr",
                                "extraction_status": "completed",
                                "source_page_evidence_id": page_id,
                                "ocr_engine": item.ocr_engine,
                                "ocr_engine_version": item.ocr_engine_version,
                                "ocr_languages": item.ocr_languages,
                                "ocr_confidence": item.confidence,
                                "confidence_source": item.confidence_source,
                            },
                        )
                    )
                else:
                    warnings.append(f"OCR page {page_number} is not complete: {status}")

        # Parser deliberately omits native blocks for selected pages.  The
        # filter also protects against a custom parser returning duplicates.
        index_blocks = [
            block
            for block in blocks
            if block.page_start is None or block.page_start not in selected
        ] + ocr_blocks
        index_blocks.sort(key=lambda block: (block.page_start or 0, block.source_order))
        evidence.sort(key=lambda item: item.page_number)
        return evidence, evidence_by_page, index_blocks

    def get_document(self, document_id: str) -> dict[str, Any]:
        """Return document details as a dict."""
        doc_rec = self._repo.get_document(document_id)
        if doc_rec is None:
            raise DocumentNotFoundError(f"Document {document_id!r} not found")

        return {
            "id": doc_rec.id,
            "code": doc_rec.code,
            "title": doc_rec.title,
            "document_category": doc_rec.document_category,
            "source_type": doc_rec.source_type,
            "source_reference": doc_rec.source_reference,
            "owner": doc_rec.owner,
            "current_revision_number": doc_rec.current_revision_number,
            "created_at": doc_rec.created_at.isoformat() if doc_rec.created_at else None,
            "updated_at": doc_rec.updated_at.isoformat() if doc_rec.updated_at else None,
        }

    def list_documents(self) -> list[dict[str, Any]]:
        """List all knowledge documents."""
        doc_recs = self._repo.list_documents()
        return [
            {
                "id": d.id,
                "code": d.code,
                "title": d.title,
                "document_category": d.document_category,
                "source_type": d.source_type,
                "owner": d.owner,
                "current_revision_number": d.current_revision_number,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in doc_recs
        ]

    def get_revision(self, document_id: str, revision_number: int) -> dict[str, Any]:
        """Return revision details (no storage path)."""
        rev_rec = self._find_revision(document_id, revision_number)
        return {
            "id": rev_rec.id,
            "document_id": rev_rec.document_id,
            "revision_number": rev_rec.revision_number,
            "version_label": rev_rec.version_label,
            "original_filename": rev_rec.original_filename,
            "mime_type": rev_rec.mime_type,
            "file_extension": rev_rec.file_extension,
            "file_size_bytes": rev_rec.file_size_bytes,
            "content_sha256": rev_rec.content_sha256,
            "ingestion_status": rev_rec.ingestion_status,
            "review_status": rev_rec.review_status,
            "requires_ocr": rev_rec.requires_ocr,
            "requires_review": rev_rec.requires_review,
            "parser_name": rev_rec.parser_name,
            "parser_version": rev_rec.parser_version,
            "chunker_version": rev_rec.chunker_version,
            "embedding_version": rev_rec.embedding_version,
            "extracted_text_length": rev_rec.extracted_text_length,
            "page_count": rev_rec.page_count,
            "sheet_count": rev_rec.sheet_count,
            "metadata_snapshot": rev_rec.metadata_snapshot,
            "warning_messages": rev_rec.warning_messages,
            "created_at": rev_rec.created_at.isoformat() if rev_rec.created_at else None,
            "indexed_at": rev_rec.indexed_at.isoformat() if rev_rec.indexed_at else None,
            "reviewed_at": (rev_rec.reviewed_at.isoformat() if rev_rec.reviewed_at else None),
            "approved_at": (rev_rec.approved_at.isoformat() if rev_rec.approved_at else None),
            "withdrawn_at": (rev_rec.withdrawn_at.isoformat() if rev_rec.withdrawn_at else None),
        }

    def list_chunks(self, document_id: str, revision_number: int) -> list[dict[str, Any]]:
        """List all chunks for a revision."""
        rev_rec = self._find_revision(document_id, revision_number)
        chunk_recs = self._repo.get_chunks(rev_rec.id)
        return [
            {
                "id": c.id,
                "revision_id": c.revision_id,
                "chunk_index": c.chunk_index,
                "text": c.text,
                "text_sha256": c.text_sha256,
                "character_count": c.character_count,
                "token_count": c.token_count,
                "section_path": c.section_path,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "sheet_name": c.sheet_name,
                "row_start": c.row_start,
                "row_end": c.row_end,
                "source_locator": c.source_locator,
                "source_page_evidence_id": c.source_page_evidence_id or "",
                "embedding_dimension": c.embedding_dimension,
                "embedding_version": c.embedding_version,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in chunk_recs
        ]

    def transition_review_status(
        self,
        *,
        document_id: str,
        revision_number: int,
        target_status: str,
    ) -> dict[str, Any]:
        """Transition the review status of a revision."""
        rev_rec = self._find_revision(document_id, revision_number)
        # Allow approved -> withdrawn (the only permitted change on approved revisions)
        if not (rev_rec.review_status == "approved" and target_status == "withdrawn"):
            assert_not_approved(rev_rec.review_status)
        validate_review_eligibility(rev_rec.ingestion_status, target_status)
        validate_review_transition(rev_rec.review_status, target_status)

        now = datetime.now(UTC)
        update_kwargs: dict[str, Any] = {
            "review_status": target_status,
            "requires_review": target_status not in ("approved", "withdrawn"),
        }
        if target_status == "reviewed":
            update_kwargs["reviewed_at"] = now
        elif target_status == "approved":
            update_kwargs["approved_at"] = now
            update_kwargs["requires_review"] = False
        elif target_status == "withdrawn":
            update_kwargs["withdrawn_at"] = now

        self._repo.update_revision_status(rev_rec.id, **update_kwargs)

        self._audit_event(
            actor="system",
            action="revision.review_status_changed",
            entity_type="knowledge_document",
            entity_id=document_id,
            before_snapshot={"review_status": rev_rec.review_status},
            after_snapshot={"review_status": target_status},
        )

        self._session.commit()

        return {
            "document_id": document_id,
            "revision_number": revision_number,
            "review_status": target_status,
        }

    def search(
        self,
        *,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        include_unverified: bool = False,
        include_reviewed: bool = False,
        include_historical_revisions: bool = False,
        document_categories: list[str] | None = None,
        document_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run hybrid search across all indexed chunks."""
        if not query or not query.strip():
            from cold_storage.modules.knowledge.domain.errors import (
                SearchQueryEmptyError,
            )

            raise SearchQueryEmptyError("Search query is empty")

        if not (1 <= top_k <= 50):
            raise ValueError(f"top_k must be between 1 and 50, got {top_k}")

        filters = filters or {}
        doc_categories = document_categories or []
        doc_ids_filter = document_ids or []

        # Load all relevant chunks from DB
        all_doc_recs = self._repo.list_documents()
        input_candidates: list[RetrievalCandidate] = []
        total_candidates = 0

        for doc_rec in all_doc_recs:
            # Apply document-level filters
            if (
                "document_category" in filters
                and doc_rec.document_category != filters["document_category"]
            ):
                continue
            if doc_categories and doc_rec.document_category not in doc_categories:
                continue
            if doc_ids_filter and doc_rec.id not in doc_ids_filter:
                continue

            rev_recs = self._repo.list_revisions(doc_rec.id)

            # Build the set of allowed review statuses.
            # Default: only approved. Explicit flags opt-in to more.
            allowed_statuses: set[str] = {"approved"}
            if include_reviewed:
                allowed_statuses.add("reviewed")
            if include_unverified:
                allowed_statuses.add("unverified")

            # Exclude withdrawn; require ingestion_status=indexed
            # and review_status in the allowed set.
            eligible = [
                r
                for r in rev_recs
                if r.ingestion_status == "indexed"
                and r.review_status != "withdrawn"
                and r.review_status in allowed_statuses
            ]
            if not eligible:
                continue

            # When not including historical revisions, pick only the
            # newest revision.  When including, search all eligible.
            if include_historical_revisions:
                revs_to_search = eligible
            else:
                revs_to_search = [max(eligible, key=lambda r: r.revision_number)]

            for rev_rec in revs_to_search:
                chunk_recs = self._repo.get_chunks(rev_rec.id)
                total_candidates += len(chunk_recs)
                for c in chunk_recs:
                    page_evidence = (
                        self._repo.get_page_evidence(c.source_page_evidence_id)
                        if c.source_page_evidence_id
                        else None
                    )
                    chunk = KnowledgeChunk(
                        id=c.id,
                        revision_id=c.revision_id,
                        chunk_index=c.chunk_index,
                        text=c.text,
                        text_sha256=c.text_sha256,
                        character_count=c.character_count,
                        token_count=c.token_count,
                        section_path=c.section_path,
                        page_start=c.page_start,
                        page_end=c.page_end,
                        sheet_name=c.sheet_name,
                        row_start=c.row_start,
                        row_end=c.row_end,
                        source_locator=c.source_locator,
                        source_page_evidence_id=c.source_page_evidence_id or "",
                        is_ocr_derived=bool(
                            page_evidence is not None and page_evidence.is_derived_evidence
                        ),
                        requires_review=bool(
                            page_evidence is None or page_evidence.requires_review
                        ),
                        embedding=c.embedding or [],
                        embedding_dimension=c.embedding_dimension,
                        embedding_version=c.embedding_version,
                        created_at=c.created_at,
                    )
                    input_candidates.append(
                        RetrievalCandidate(
                            chunk=chunk,
                            document_code=doc_rec.code,
                            review_status=rev_rec.review_status,
                            revision_number=rev_rec.revision_number,
                        )
                    )

        profile = RetrievalProfile()
        results = search_chunks(query, input_candidates, profile, top_k=top_k)

        # Build response
        search_results = []
        warnings: list[str] = []
        any_requires_review = False
        for candidate in results:
            chunk = candidate.chunk
            score = candidate.score
            doc_code = candidate.document_code
            citation_page_evidence = (
                self._repo.get_page_evidence(chunk.source_page_evidence_id)
                if chunk.source_page_evidence_id
                else None
            )
            # Find the revision for citation info
            citation_rev = self._repo.get_revision(chunk.revision_id)
            doc_rec_obj = (
                self._repo.get_document(citation_rev.document_id) if citation_rev else None
            )

            if citation_rev and citation_rev.requires_review:
                any_requires_review = True

            search_results.append(
                {
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "section_path": chunk.section_path,
                    "source_locator": chunk.source_locator,
                    "source_page_evidence_id": chunk.source_page_evidence_id,
                    "is_ocr_derived": chunk.is_ocr_derived,
                    "score": {
                        "lexical_score": str(score.lexical_score),
                        "lexical_normalized": str(score.lexical_normalized),
                        "semantic_raw": str(score.semantic_raw),
                        "semantic_normalized": str(score.semantic_normalized),
                        "hybrid_score": str(score.hybrid_score),
                        "retrieval_profile": score.retrieval_profile,
                        "embedding_version": score.embedding_version,
                    },
                    "citation": {
                        "document_id": (citation_rev.document_id if citation_rev else ""),
                        "document_code": doc_code,
                        "revision_id": (citation_rev.id if citation_rev else ""),
                        "revision_number": (citation_rev.revision_number if citation_rev else 0),
                        "version_label": (citation_rev.version_label if citation_rev else ""),
                        "title": doc_rec_obj.title if doc_rec_obj else "",
                        "original_filename": (
                            citation_rev.original_filename if citation_rev else ""
                        ),
                        "content_sha256": (citation_rev.content_sha256 if citation_rev else ""),
                        "chunk_id": chunk.id,
                        "chunk_index": chunk.chunk_index,
                        "section_path": chunk.section_path,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "sheet_name": chunk.sheet_name,
                        "row_start": chunk.row_start,
                        "row_end": chunk.row_end,
                        "source_locator": chunk.source_locator,
                        "source_page_evidence_id": chunk.source_page_evidence_id,
                        "is_ocr_derived": chunk.is_ocr_derived,
                        "extraction_method": (
                            citation_page_evidence.extraction_method
                            if citation_page_evidence is not None
                            else ""
                        ),
                        "extraction_status": (
                            citation_page_evidence.extraction_status
                            if citation_page_evidence is not None
                            else ""
                        ),
                        "source_authority": (
                            citation_page_evidence.source_authority
                            if citation_page_evidence is not None
                            else ""
                        ),
                        "source_content_sha256": (
                            citation_page_evidence.source_content_sha256
                            if citation_page_evidence is not None
                            else (citation_rev.content_sha256 if citation_rev else "")
                        ),
                        "ocr_engine": (
                            citation_page_evidence.ocr_engine
                            if citation_page_evidence is not None
                            else ""
                        ),
                        "ocr_engine_version": (
                            citation_page_evidence.ocr_engine_version
                            if citation_page_evidence is not None
                            else ""
                        ),
                        "ocr_languages": (
                            citation_page_evidence.ocr_languages
                            if citation_page_evidence is not None
                            else ""
                        ),
                        "confidence": (
                            citation_page_evidence.confidence
                            if citation_page_evidence is not None
                            else None
                        ),
                        "ocr_confidence": (
                            citation_page_evidence.ocr_confidence
                            if citation_page_evidence is not None
                            else None
                        ),
                        "confidence_source": (
                            citation_page_evidence.confidence_source
                            if citation_page_evidence is not None
                            else "unavailable"
                        ),
                        "ocr_review_status": (
                            citation_page_evidence.review_status
                            if citation_page_evidence is not None
                            else ""
                        ),
                        "review_status": (citation_rev.review_status if citation_rev else ""),
                        "requires_review": (
                            chunk.requires_review
                            or (
                                citation_page_evidence.requires_review
                                if citation_page_evidence is not None
                                else True
                            )
                            or (citation_rev.requires_review if citation_rev else True)
                        ),
                        "excerpt": chunk.text[:200],
                    },
                }
            )

        return {
            "query": query,
            "retrieval_profile": profile.code,
            "embedding_provider": "fake",
            "production_ready": False,
            "results": search_results,
            "total_candidates": total_candidates,
            "total_results": len(search_results),
            "warnings": warnings,
            "requires_review": any_requires_review,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_revision(self, document_id: str, revision_number: int) -> Any:
        """Find a revision record or raise."""
        rev_recs = self._repo.list_revisions(document_id)
        for r in rev_recs:
            if r.revision_number == revision_number:
                return r
        raise RevisionNotFoundError(
            f"Revision {revision_number} not found for document {document_id!r}"
        )

    def _validate_file_type(self, ext: str, mime_type: str) -> None:
        """Validate file extension and MIME type."""
        if ext not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"Extension {ext!r} is not supported. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        # Check for dangerous extensions that might sneak through MIME
        dangerous_exts = {".xls", ".xlsm", ".docm", ".zip", ".rar", ".7z"}
        if ext in dangerous_exts:
            raise UnsupportedFileTypeError(f"Extension {ext!r} is not allowed")

    def _validate_file_size(self, size_bytes: int) -> None:
        """Validate file size against limit."""
        if size_bytes > KNOWLEDGE_MAX_UPLOAD_BYTES:
            raise FileTooLargeError(
                f"File size {size_bytes} exceeds limit of {KNOWLEDGE_MAX_UPLOAD_BYTES} bytes"
            )
        if size_bytes == 0:
            raise FileTooLargeError("File is empty")

    def _audit_event(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before_snapshot: dict[str, Any],
        after_snapshot: dict[str, Any],
    ) -> None:
        """Insert an audit event record."""
        import uuid

        event = AuditEventRecord(
            id=str(uuid.uuid4()),
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            event_metadata={},
            created_at=datetime.now(UTC),
            outbox_event_id=f"legacy-audit:{str(uuid.uuid4())}",
        )
        self._session.add(event)
