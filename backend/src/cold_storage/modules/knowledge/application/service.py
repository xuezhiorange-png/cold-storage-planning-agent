"""Knowledge application service — orchestrates domain and infrastructure."""

from __future__ import annotations

import hashlib
import io
import os
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

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
    KnowledgeRevision,
    RetrievalProfile,
)
from cold_storage.modules.knowledge.domain.retrieval import search_chunks
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


class KnowledgeService:
    """Application service for the knowledge module.

    Orchestrates document upload, parsing, chunking, embedding, and retrieval.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = KnowledgeRepository(session)
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
        file_content: bytes,
        filename: str,
        mime_type: str,
        version_label: str = "",
    ) -> dict[str, Any]:
        """Create a new knowledge document with its first revision."""
        ext = _extract_extension(filename)
        self._validate_file_type(ext, mime_type)
        self._validate_file_size(len(file_content))

        # Check duplicate code
        existing = self._repo.get_document_by_code(code)
        if existing is not None:
            raise DuplicateContentError(f"Document with code {code!r} already exists")

        content_sha256 = _compute_sha256(file_content)

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
            file_size_bytes=len(file_content),
            content_sha256=content_sha256,
            storage_key="",  # filled after save
            ingestion_status="uploaded",
            review_status="unverified",
        )

        # Save file to storage
        stored = self._storage.save(io.BytesIO(file_content), rev.id, content_sha256)
        rev = KnowledgeRevision(
            **{
                **rev.__dict__,
                "storage_key": stored.storage_key,
            }
        )
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
        file_content: bytes,
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
        self._validate_file_size(len(file_content))

        content_sha256 = _compute_sha256(file_content)

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
            file_size_bytes=len(file_content),
            content_sha256=content_sha256,
            storage_key="",
            ingestion_status="uploaded",
            review_status="unverified",
        )

        stored = self._storage.save(io.BytesIO(file_content), rev.id, content_sha256)
        rev = KnowledgeRevision(
            **{
                **rev.__dict__,
                "storage_key": stored.storage_key,
            }
        )
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
        """Run the ingestion pipeline: parse -> chunk -> embed -> persist."""
        rev_rec = self._find_revision(document_id, revision_number)
        assert_not_approved(rev_rec.review_status)
        validate_ingestion_transition(rev_rec.ingestion_status, "processing")

        # Create ingestion run
        run = KnowledgeIngestionRun(
            revision_id=rev_rec.id,
            status="processing",
            parser_name=rev_rec.parser_name or "",
            parser_version=PARSER_VER,
            chunker_version=CHUNKER_VERSION,
            embedding_version=EMBEDDING_CONFIG.version,
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

        try:
            # Read stored file
            file_content = self._storage.open(rev_rec.storage_key).read()

            # Determine parser
            parser = get_parser_for_file(rev_rec.original_filename, rev_rec.mime_type)
            if parser is None:
                raise IngestionFailedError(
                    f"No parser available for extension {rev_rec.file_extension}"
                )

            # Parse
            blocks = parser.parse(file_content, rev_rec.original_filename)
            extracted_text_length = sum(len(b.text) for b in blocks)

            # Determine page/sheet counts from blocks
            page_count: int | None = None
            sheet_count: int | None = None
            pages = {b.page_start for b in blocks if b.page_start is not None}
            sheets = {b.sheet_name for b in blocks if b.sheet_name is not None}
            if pages:
                page_count = max(pages)
            if sheets:
                sheet_count = len(sheets)

            # Chunk
            config = ChunkingConfig()
            chunks = chunk_blocks(blocks, config)

            # Assign revision_id to all chunks
            chunks_with_id: list[KnowledgeChunk] = []
            for c in chunks:
                new_chunk = KnowledgeChunk(
                    id=c.id,
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
                )
                chunks_with_id.append(new_chunk)

            # Embed
            embedded_chunks: list[KnowledgeChunk] = []
            for c in chunks_with_id:
                emb = generate_embedding(c.text, EMBEDDING_CONFIG)
                embedded = KnowledgeChunk(
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
                    embedding=emb,
                    embedding_dimension=len(emb),
                    embedding_version=EMBEDDING_CONFIG.version,
                )
                embedded_chunks.append(embedded)

            # Persist chunks
            self._repo.save_chunks(embedded_chunks)

            # Update revision status
            now = datetime.now(UTC)
            self._repo.update_revision_status(
                rev_rec.id,
                ingestion_status="indexed",
                requires_ocr=False,
                requires_review=True,
                parser_name=parser.name,
                parser_version=PARSER_VER,
                chunker_version=CHUNKER_VERSION,
                embedding_version=EMBEDDING_CONFIG.version,
                extracted_text_length=extracted_text_length,
                page_count=page_count,
                sheet_count=sheet_count,
                indexed_at=now,
                warnings=warnings,
            )

            # Update ingestion run
            run_rec.status = "completed"
            run_rec.result_snapshot = {
                "chunk_count": len(embedded_chunks),
                "extracted_text_length": extracted_text_length,
            }
            run_rec.completed_at = now
            self._session.flush()

        except Exception as exc:
            self._repo.update_revision_status(
                rev_rec.id,
                ingestion_status="failed",
            )
            run_rec.status = "failed"
            run_rec.error_code = type(exc).__name__
            run_rec.error_message = str(exc)
            run_rec.completed_at = datetime.now(UTC)
            self._session.flush()

            self._session.commit()

            raise IngestionFailedError(f"Ingestion failed: {exc}") from exc

        self._audit_event(
            actor=rev_rec.document.owner if rev_rec.document else "system",
            action="revision.ingested",
            entity_type="knowledge_document",
            entity_id=document_id,
            before_snapshot={"ingestion_status": "processing"},
            after_snapshot={
                "ingestion_status": "indexed",
                "chunk_count": len(embedded_chunks),
            },
        )

        self._session.commit()

        return {
            "document_id": document_id,
            "revision_number": revision_number,
            "ingestion_status": "indexed",
            "chunk_count": len(embedded_chunks),
            "extracted_text_length": extracted_text_length,
        }

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
    ) -> dict[str, Any]:
        """Run hybrid search across all indexed chunks."""
        if not query or not query.strip():
            from cold_storage.modules.knowledge.domain.errors import (
                SearchQueryEmptyError,
            )

            raise SearchQueryEmptyError("Search query is empty")

        filters = filters or {}

        # Load all relevant chunks from DB
        all_doc_recs = self._repo.list_documents()
        chunk_doc_pairs: list[tuple[KnowledgeChunk, str]] = []

        for doc_rec in all_doc_recs:
            # Apply document-level filters
            if (
                "document_category" in filters
                and doc_rec.document_category != filters["document_category"]
            ):
                continue

            rev_recs = self._repo.list_revisions(doc_rec.id)
            for rev_rec in rev_recs:
                # Only search indexed revisions
                if rev_rec.ingestion_status != "indexed":
                    continue

                # Review status filter
                approved_only = filters.get("approved_only", True)
                if approved_only and rev_rec.review_status != "approved":
                    continue

                chunk_recs = self._repo.get_chunks(rev_rec.id)
                for c in chunk_recs:
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
                        embedding=c.embedding or [],
                        embedding_dimension=c.embedding_dimension,
                        embedding_version=c.embedding_version,
                        created_at=c.created_at,
                    )
                    chunk_doc_pairs.append((chunk, doc_rec.code))

        profile = RetrievalProfile()
        results = search_chunks(query, chunk_doc_pairs, profile, top_k=top_k)

        # Build response
        search_results = []
        for chunk, score, doc_code in results:
            # Find the revision for citation info
            citation_rev = self._repo.get_revision(chunk.revision_id)
            doc_rec_obj = (
                self._repo.get_document(citation_rev.document_id) if citation_rev else None
            )

            search_results.append(
                {
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "section_path": chunk.section_path,
                    "source_locator": chunk.source_locator,
                    "score": {
                        "hybrid_score": str(score.hybrid_score),
                        "lexical_score": str(score.lexical_score),
                        "semantic_raw": str(score.semantic_raw),
                    },
                    "citation": {
                        "document_code": doc_code,
                        "document_id": (citation_rev.document_id if citation_rev else ""),
                        "revision_number": (citation_rev.revision_number if citation_rev else 0),
                        "title": doc_rec_obj.title if doc_rec_obj else "",
                        "original_filename": (
                            citation_rev.original_filename if citation_rev else ""
                        ),
                        "chunk_id": chunk.id,
                        "section_path": chunk.section_path,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "review_status": (citation_rev.review_status if citation_rev else ""),
                        "excerpt": chunk.text[:200],
                    },
                }
            )

        return {
            "query": query,
            "total_results": len(search_results),
            "results": search_results,
            "retrieval_profile": profile.code,
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
        )
        self._session.add(event)
