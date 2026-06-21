"""Knowledge API routes — FastAPI endpoints for the knowledge module."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, NoReturn

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from cold_storage.modules.knowledge.application.service import KnowledgeService

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class DocumentCreateForm:
    """Form fields for document creation (multipart)."""

    pass


class DocumentResponse(BaseModel):
    """Response for a single document."""

    id: str
    code: str
    title: str
    document_category: str
    source_type: str
    source_reference: str
    owner: str
    current_revision_number: int
    created_at: str | None = None
    updated_at: str | None = None


class RevisionResponse(BaseModel):
    """Response for a single revision."""

    id: str
    document_id: str
    revision_number: int
    version_label: str
    original_filename: str
    mime_type: str
    file_extension: str
    file_size_bytes: int
    content_sha256: str
    ingestion_status: str
    review_status: str
    requires_ocr: bool
    requires_review: bool
    parser_name: str
    parser_version: str
    chunker_version: str
    embedding_version: str
    extracted_text_length: int
    page_count: int | None = None
    sheet_count: int | None = None
    metadata_snapshot: dict[str, Any] = Field(default_factory=dict)
    warning_messages: list[str] = Field(default_factory=list)
    created_at: str | None = None
    indexed_at: str | None = None
    reviewed_at: str | None = None
    approved_at: str | None = None
    withdrawn_at: str | None = None


class ChunkResponse(BaseModel):
    """Response for a single chunk."""

    id: str
    revision_id: str
    chunk_index: int
    text: str
    text_sha256: str
    character_count: int
    token_count: int
    section_path: str
    page_start: int | None = None
    page_end: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    source_locator: str
    embedding_dimension: int
    embedding_version: str
    created_at: str | None = None


class ReviewStatusRequest(BaseModel):
    """Request body for review status transition."""

    target_status: str


class SearchRequest(BaseModel):
    """Request body for knowledge search."""

    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    document_categories: list[str] = Field(default_factory=list)
    include_unverified: bool = False
    include_reviewed: bool = False
    include_historical_revisions: bool = False
    document_ids: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)


class SearchResultScore(BaseModel):
    """Score breakdown for a search result."""

    lexical_score: str
    lexical_normalized: str
    semantic_raw: str
    semantic_normalized: str
    hybrid_score: str
    retrieval_profile: str
    embedding_version: str


class SearchResultCitation(BaseModel):
    """Citation for a search result."""

    document_id: str
    document_code: str
    revision_id: str
    revision_number: int
    version_label: str
    title: str
    original_filename: str
    content_sha256: str
    chunk_id: str
    chunk_index: int
    section_path: str
    page_start: int | None = None
    page_end: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    source_locator: str
    review_status: str
    requires_review: bool
    excerpt: str


class SearchResult(BaseModel):
    """Single search result."""

    chunk_id: str
    chunk_index: int
    text: str
    section_path: str
    source_locator: str
    score: SearchResultScore
    citation: SearchResultCitation


class SearchResponse(BaseModel):
    """Response for knowledge search."""

    query: str
    retrieval_profile: str
    embedding_provider: str = "fake"
    production_ready: bool = False
    results: list[SearchResult]
    total_candidates: int
    total_results: int
    warnings: list[str] = Field(default_factory=list)
    requires_review: bool = True


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


def register_knowledge_routes(app: Any, get_service: Callable[[], KnowledgeService]) -> None:
    """Register knowledge-related API routes on the FastAPI app."""
    app.include_router(router)
    # Store the service factory for dependency injection
    app.state._knowledge_service_factory = get_service


def _get_service(request: Any) -> KnowledgeService:
    """Get KnowledgeService from the request app state."""
    factory: Callable[[], KnowledgeService] = request.app.state._knowledge_service_factory
    return factory()


# ---------------------------------------------------------------------------
# POST /api/v1/knowledge/documents — Create document + first revision
# ---------------------------------------------------------------------------


@router.post("/documents", status_code=201)
async def create_document(
    request: Any,
    code: str = Form(...),
    title: str = Form(""),
    document_category: str = Form("other"),
    source_type: str = Form("upload"),
    source_reference: str = Form(""),
    owner: str = Form(""),
    version_label: str = Form(""),
    file: UploadFile = File(...),  # noqa: B008
) -> dict[str, Any]:
    """Create a new knowledge document with its first revision."""
    service = _get_service(request)

    # Stream upload: compute hash + size while streaming to SpooledTemporaryFile
    import os
    import tempfile

    max_upload_bytes = int(os.environ.get("KNOWLEDGE_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    sha256_hash = hashlib.sha256()
    total_size = 0
    spooled = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)  # noqa: SIM115
    try:
        while True:
            chunk = await file.read(8192)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_upload_bytes:
                from cold_storage.modules.knowledge.domain.errors import FileTooLargeError as FTL

                raise FTL(f"File exceeds maximum upload size of {max_upload_bytes} bytes")
            sha256_hash.update(chunk)
            spooled.write(chunk)
        spooled.seek(0)
    except Exception:
        spooled.close()
        raise
    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unnamed"

    try:
        return service.create_document(
            code=code,
            title=title,
            document_category=document_category,
            source_type=source_type,
            source_reference=source_reference,
            owner=owner,
            file=spooled,
            content_sha256=sha256_hash.hexdigest(),
            file_size=total_size,
            filename=filename,
            mime_type=mime_type,
            version_label=version_label,
        )
    except Exception as exc:
        _raise_http(exc)
    finally:
        spooled.close()


# ---------------------------------------------------------------------------
# POST /api/v1/knowledge/documents/{document_id}/revisions — New revision
# ---------------------------------------------------------------------------


@router.post("/documents/{document_id}/revisions", status_code=201)
async def create_revision(
    document_id: str,
    request: Any,
    version_label: str = Form(""),
    file: UploadFile = File(...),  # noqa: B008
) -> dict[str, Any]:
    """Create a new revision for an existing document."""
    service = _get_service(request)

    # Stream upload: compute hash + size while streaming to SpooledTemporaryFile
    import os
    import tempfile

    max_upload_bytes = int(os.environ.get("KNOWLEDGE_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    sha256_hash = hashlib.sha256()
    total_size = 0
    spooled = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)  # noqa: SIM115
    try:
        while True:
            chunk = await file.read(8192)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_upload_bytes:
                from cold_storage.modules.knowledge.domain.errors import FileTooLargeError as FTL

                raise FTL(f"File exceeds maximum upload size of {max_upload_bytes} bytes")
            sha256_hash.update(chunk)
            spooled.write(chunk)
        spooled.seek(0)
    except Exception:
        spooled.close()
        raise
    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unnamed"

    try:
        return service.create_revision(
            document_id=document_id,
            file=spooled,
            content_sha256=sha256_hash.hexdigest(),
            file_size=total_size,
            filename=filename,
            mime_type=mime_type,
            version_label=version_label,
        )
    except Exception as exc:
        _raise_http(exc)
    finally:
        spooled.close()


# ---------------------------------------------------------------------------
# POST /api/v1/knowledge/documents/{id}/revisions/{num}/ingest
# ---------------------------------------------------------------------------


@router.post(
    "/documents/{document_id}/revisions/{revision_number}/ingest",
    status_code=200,
)
def ingest_revision(
    document_id: str,
    revision_number: int,
    request: Any,
) -> dict[str, Any]:
    """Trigger the ingestion pipeline for a revision."""
    service = _get_service(request)
    try:
        return service.ingest_revision(
            document_id=document_id,
            revision_number=revision_number,
        )
    except Exception as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# GET /api/v1/knowledge/documents — List all documents
# ---------------------------------------------------------------------------


@router.get("/documents")
def list_documents(request: Any) -> list[dict[str, Any]]:
    """List all knowledge documents."""
    service = _get_service(request)
    return service.list_documents()


# ---------------------------------------------------------------------------
# GET /api/v1/knowledge/documents/{document_id} — Get document
# ---------------------------------------------------------------------------


@router.get("/documents/{document_id}")
def get_document(document_id: str, request: Any) -> dict[str, Any]:
    """Get document details."""
    service = _get_service(request)
    try:
        return service.get_document(document_id)
    except Exception as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# GET /api/v1/knowledge/documents/{id}/revisions/{num} — Get revision
# ---------------------------------------------------------------------------


@router.get(
    "/documents/{document_id}/revisions/{revision_number}",
)
def get_revision(
    document_id: str,
    revision_number: int,
    request: Any,
) -> dict[str, Any]:
    """Get revision details."""
    service = _get_service(request)
    try:
        return service.get_revision(document_id, revision_number)
    except Exception as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# GET /api/v1/knowledge/documents/{id}/revisions/{num}/chunks
# ---------------------------------------------------------------------------


@router.get(
    "/documents/{document_id}/revisions/{revision_number}/chunks",
)
def list_chunks(
    document_id: str,
    revision_number: int,
    request: Any,
) -> list[dict[str, Any]]:
    """List chunks for a revision."""
    service = _get_service(request)
    try:
        return service.list_chunks(document_id, revision_number)
    except Exception as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# PATCH /api/v1/knowledge/documents/{id}/revisions/{num}/review-status
# ---------------------------------------------------------------------------


@router.patch(
    "/documents/{document_id}/revisions/{revision_number}/review-status",
)
def transition_review_status(
    document_id: str,
    revision_number: int,
    body: ReviewStatusRequest,
    request: Any,
) -> dict[str, Any]:
    """Transition the review status of a revision."""
    service = _get_service(request)
    try:
        return service.transition_review_status(
            document_id=document_id,
            revision_number=revision_number,
            target_status=body.target_status,
        )
    except Exception as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# POST /api/v1/knowledge/search — Hybrid search
# ---------------------------------------------------------------------------


@router.post("/search")
def search(body: SearchRequest, request: Any) -> dict[str, Any]:
    """Run hybrid search across indexed knowledge."""
    service = _get_service(request)
    try:
        return service.search(
            query=body.query,
            top_k=body.top_k,
            filters=body.filters,
            include_unverified=body.include_unverified,
            include_reviewed=body.include_reviewed,
            include_historical_revisions=body.include_historical_revisions,
            document_categories=body.document_categories,
            document_ids=body.document_ids,
        )
    except Exception as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# Error mapping helper
# ---------------------------------------------------------------------------


def _raise_http(exc: Exception) -> NoReturn:
    """Map domain exceptions to appropriate HTTP status codes."""
    from cold_storage.modules.knowledge.domain.errors import (
        ApprovedRevisionImmutabilityError,
        DocumentNotFoundError,
        DuplicateContentError,
        FileTooLargeError,
        IngestionFailedError,
        InvalidLifecycleTransitionError,
        RevisionNotFoundError,
        SearchQueryEmptyError,
        UnsupportedFileTypeError,
    )

    if isinstance(exc, DocumentNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, RevisionNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, DuplicateContentError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ApprovedRevisionImmutabilityError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, InvalidLifecycleTransitionError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, FileTooLargeError):
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if isinstance(exc, UnsupportedFileTypeError):
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    if isinstance(exc, IngestionFailedError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(exc, SearchQueryEmptyError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc
