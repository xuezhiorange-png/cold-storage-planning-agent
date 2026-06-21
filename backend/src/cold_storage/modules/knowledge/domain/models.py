"""Knowledge domain models — pure data types, no framework or DB dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4


def _uuid() -> str:
    return str(uuid4())


# Document categories
DOCUMENT_CATEGORIES: frozenset[str] = frozenset(
    {
        "standard",
        "manual",
        "book",
        "paper",
        "manufacturer_document",
        "project_document",
        "calculation_basis",
        "spreadsheet",
        "other",
    }
)


@dataclass(frozen=True)
class KnowledgeDocument:
    """Top-level document entity representing a knowledge source."""

    id: str = field(default_factory=_uuid)
    code: str = ""
    title: str = ""
    document_category: str = "other"
    source_type: str = "upload"
    source_reference: str = ""
    owner: str = ""
    current_revision_number: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class KnowledgeRevision:
    """A single versioned revision of a document — immutable after creation."""

    id: str = field(default_factory=_uuid)
    document_id: str = ""
    revision_number: int = 1
    version_label: str = ""
    original_filename: str = ""
    safe_filename: str = ""
    mime_type: str = ""
    file_extension: str = ""
    file_size_bytes: int = 0
    content_sha256: str = ""
    storage_key: str = ""
    ingestion_status: str = "uploaded"
    review_status: str = "unverified"
    requires_ocr: bool = False
    requires_review: bool = True
    parser_name: str = ""
    parser_version: str = ""
    chunker_version: str = ""
    embedding_version: str = ""
    extracted_text_length: int = 0
    page_count: int | None = None
    sheet_count: int | None = None
    metadata_snapshot: dict[str, object] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    indexed_at: datetime | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    withdrawn_at: datetime | None = None


@dataclass(frozen=True)
class KnowledgeIngestionRun:
    """Audit record for a single ingestion pipeline execution."""

    id: str = field(default_factory=_uuid)
    revision_id: str = ""
    status: str = "pending"
    parser_name: str = ""
    parser_version: str = ""
    chunker_version: str = ""
    embedding_version: str = ""
    input_snapshot: dict[str, object] = field(default_factory=dict)
    result_snapshot: dict[str, object] = field(default_factory=dict)
    warning_messages: list[str] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


@dataclass(frozen=True)
class ParsedBlock:
    """A unit of extracted content from a parsed document."""

    text: str
    block_type: str  # paragraph, heading, table, code, list, metadata
    section_path: str = ""
    page_start: int | None = None
    page_end: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    table_index: int | None = None
    paragraph_index: int | None = None
    source_order: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeChunk:
    """A fixed-size chunk of text ready for embedding and search."""

    id: str = field(default_factory=_uuid)
    revision_id: str = ""
    chunk_index: int = 0
    text: str = ""
    text_sha256: str = ""
    character_count: int = 0
    token_count: int = 0
    section_path: str = ""
    page_start: int | None = None
    page_end: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    source_locator: str = ""
    embedding: list[float] = field(default_factory=list)
    embedding_dimension: int = 0
    embedding_version: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ChunkingConfig:
    """Configuration for the text chunker."""

    max_characters: int = 1200
    overlap_characters: int = 150
    minimum_characters: int = 80
    version: str = "chunk-v1"

    def __post_init__(self) -> None:
        if self.overlap_characters >= self.max_characters:
            raise ValueError("overlap_characters must be < max_characters")
        if self.minimum_characters < 0:
            raise ValueError("minimum_characters must be >= 0")


@dataclass(frozen=True)
class FakeEmbeddingConfig:
    """Configuration for the deterministic fake embedding provider."""

    provider: str = "fake"
    version: str = "fake-hash-v1"
    dimension: int = 64
    production_ready: bool = False
    requires_review: bool = True


@dataclass(frozen=True)
class RetrievalProfile:
    """Configuration for the hybrid retrieval scorer."""

    code: str = "hybrid-fake-v1"
    lexical_weight: Decimal = Decimal("0.65")
    semantic_weight: Decimal = Decimal("0.35")
    bm25_k1: Decimal = Decimal("1.2")
    bm25_b: Decimal = Decimal("0.75")
    embedding_config: FakeEmbeddingConfig = field(default_factory=FakeEmbeddingConfig)

    def __post_init__(self) -> None:
        total = self.lexical_weight + self.semantic_weight
        if total != Decimal("1"):
            raise ValueError(f"Weights must sum to 1, got {total}")


@dataclass(frozen=True)
class RetrievalQuery:
    """Parameters for a knowledge search request."""

    query: str = ""
    top_k: int = 10
    document_categories: list[str] = field(default_factory=list)
    include_unverified: bool = False
    include_reviewed: bool = False
    include_historical_revisions: bool = False
    document_ids: list[str] = field(default_factory=list)
    approved_only: bool = True


@dataclass(frozen=True)
class RetrievalScore:
    """Breakdown of lexical, semantic, and hybrid scores for a search hit."""

    lexical_score: Decimal = Decimal("0")
    lexical_normalized: Decimal = Decimal("0")
    semantic_raw: Decimal = Decimal("0")
    semantic_normalized: Decimal = Decimal("0")
    hybrid_score: Decimal = Decimal("0")
    retrieval_profile: str = ""
    embedding_version: str = ""


@dataclass(frozen=True)
class KnowledgeCitation:
    """Structured citation for a knowledge search result."""

    document_id: str = ""
    document_code: str = ""
    revision_id: str = ""
    revision_number: int = 0
    version_label: str = ""
    title: str = ""
    original_filename: str = ""
    content_sha256: str = ""
    chunk_id: str = ""
    chunk_index: int = 0
    section_path: str = ""
    page_start: int | None = None
    page_end: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    source_locator: str = ""
    review_status: str = ""
    requires_review: bool = True
    excerpt: str = ""


@dataclass(frozen=True)
class KnowledgeSearchResult:
    """A single search result pairing a chunk with its score and citation."""

    chunk: KnowledgeChunk = field(default_factory=KnowledgeChunk)
    score: RetrievalScore = field(default_factory=RetrievalScore)
    citation: KnowledgeCitation = field(default_factory=lambda: KnowledgeCitation())
    requires_review: bool = True
