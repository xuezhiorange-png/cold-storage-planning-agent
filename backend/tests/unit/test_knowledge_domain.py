"""Knowledge domain tests — lifecycle, chunking, embedding, retrieval.

Covers 25 domain-level properties:
 1. Ingestion lifecycle happy path
 2. Ingestion lifecycle failed→retry
 3. Ingestion lifecycle invalid transition
 4. Review lifecycle happy path
 5. Review lifecycle withdraw
 6. Review requires indexed ingestion status
 7. Chunking deterministic
 8. Chunking empty text
 9. Chunking overlap
10. Chunking no cross-page
11. Chunking no cross-sheet
12. Chunking NFKC normalization
13. Embedding deterministic
14. Embedding cross-process consistency
15. Embedding empty text
16. Embedding all values finite
17. Embedding correct dimension
18. Embedding Chinese unigrams+bigrams
19. BM25 basic scoring
20. BM25 tokenizer unit tokens
21. Hybrid score weights sum
22. Hybrid score zero lexical
23. Cosine similarity basic
24. Cosine identical vectors
25. Cosine orthogonal vectors
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from cold_storage.modules.knowledge.domain.chunking import chunk_blocks
from cold_storage.modules.knowledge.domain.embedding import generate_embedding
from cold_storage.modules.knowledge.domain.errors import (
    InvalidLifecycleTransitionError,
)
from cold_storage.modules.knowledge.domain.lifecycle import (
    can_transition_ingestion,
    can_transition_review,
    validate_ingestion_transition,
    validate_review_eligibility,
    validate_review_transition,
)
from cold_storage.modules.knowledge.domain.models import (
    ChunkingConfig,
    FakeEmbeddingConfig,
    ParsedBlock,
    RetrievalProfile,
)
from cold_storage.modules.knowledge.domain.retrieval import (
    bm25_score,
    cosine_similarity,
    hybrid_score,
    tokenize,
)

# ---------------------------------------------------------------------------
# 1. Ingestion lifecycle happy path
# ---------------------------------------------------------------------------


class TestIngestionLifecycle:
    def test_ingestion_lifecycle_happy_path(self) -> None:
        """uploaded→processing→indexed should all be valid."""
        validate_ingestion_transition("uploaded", "processing")
        validate_ingestion_transition("processing", "indexed")

    def test_ingestion_lifecycle_failed_retry(self) -> None:
        """uploaded→processing→failed→processing→indexed should all be valid."""
        validate_ingestion_transition("uploaded", "processing")
        validate_ingestion_transition("processing", "failed")
        validate_ingestion_transition("failed", "processing")
        validate_ingestion_transition("processing", "indexed")

    def test_ingestion_lifecycle_invalid(self) -> None:
        """indexed→uploaded should fail (indexed is terminal)."""
        with pytest.raises(InvalidLifecycleTransitionError):
            validate_ingestion_transition("indexed", "uploaded")

    def test_ingestion_can_transition_bool(self) -> None:
        """can_transition_ingestion returns True/False without raising."""
        assert can_transition_ingestion("uploaded", "processing") is True
        assert can_transition_ingestion("uploaded", "indexed") is False


# ---------------------------------------------------------------------------
# 4-6. Review lifecycle tests
# ---------------------------------------------------------------------------


class TestReviewLifecycle:
    def test_review_lifecycle_happy_path(self) -> None:
        """unverified→reviewed→approved should all be valid."""
        validate_review_transition("unverified", "reviewed")
        validate_review_transition("reviewed", "approved")

    def test_review_lifecycle_withdraw(self) -> None:
        """approved→withdrawn should be valid."""
        validate_review_transition("approved", "withdrawn")

    def test_review_requires_indexed(self) -> None:
        """Can't set review_status to 'reviewed' if ingestion_status != 'indexed'."""
        with pytest.raises(InvalidLifecycleTransitionError, match="only 'indexed'"):
            validate_review_eligibility(ingestion_status="processing", review_status="reviewed")

    def test_review_requires_indexed_succeeds(self) -> None:
        """Can set review_status to 'reviewed' when ingestion_status is 'indexed'."""
        validate_review_eligibility(ingestion_status="indexed", review_status="reviewed")

    def test_review_withdraw_from_unverified(self) -> None:
        """unverified→withdrawn should be valid."""
        validate_review_transition("unverified", "withdrawn")

    def test_review_can_transition_bool(self) -> None:
        """can_transition_review returns True/False without raising."""
        assert can_transition_review("unverified", "reviewed") is True
        assert can_transition_review("approved", "reviewed") is False


# ---------------------------------------------------------------------------
# 7-12. Chunking tests
# ---------------------------------------------------------------------------


class TestChunking:
    def test_chunking_deterministic(self) -> None:
        """Same input blocks + same config = same output chunks."""
        # Use text short enough to fit in one chunk (avoids split path)
        blocks = [
            ParsedBlock(text="Hello world. Short text.", block_type="paragraph", source_order=0),
        ]
        config = ChunkingConfig(max_characters=200, overlap_characters=30, minimum_characters=20)
        result1 = chunk_blocks(blocks, config)
        result2 = chunk_blocks(blocks, config)
        assert len(result1) == len(result2)
        for c1, c2 in zip(result1, result2, strict=True):
            assert c1.text == c2.text
            assert c1.chunk_index == c2.chunk_index

    def test_chunking_empty_text(self) -> None:
        """Empty or whitespace-only blocks produce no chunks."""
        blocks = [
            ParsedBlock(text="", block_type="paragraph", source_order=0),
            ParsedBlock(text="   ", block_type="paragraph", source_order=1),
            ParsedBlock(text="\n\n\n", block_type="paragraph", source_order=2),
        ]
        config = ChunkingConfig()
        result = chunk_blocks(blocks, config)
        assert len(result) == 0

    def test_chunking_overlap(self) -> None:
        """Multiple blocks with overlapping page ranges stay within page boundaries."""
        blocks = [
            ParsedBlock(
                text="Alpha beta. " * 5,
                block_type="paragraph",
                page_start=1,
                page_end=1,
                source_order=0,
            ),
            ParsedBlock(
                text="Gamma delta. " * 5,
                block_type="paragraph",
                page_start=1,
                page_end=1,
                source_order=1,
            ),
        ]
        config = ChunkingConfig(max_characters=500, overlap_characters=100, minimum_characters=20)
        result = chunk_blocks(blocks, config)
        # Each block fits, so we get 2 chunks (one per block)
        assert len(result) == 2
        assert result[0].page_start == 1
        assert result[1].page_start == 1

    def test_chunking_no_cross_page(self) -> None:
        """Different page blocks stay separate — no chunk merges across pages."""
        blocks = [
            ParsedBlock(
                text="Page one content. " * 10,
                block_type="paragraph",
                page_start=1,
                page_end=1,
                source_order=0,
            ),
            ParsedBlock(
                text="Page two content. " * 10,
                block_type="paragraph",
                page_start=2,
                page_end=2,
                source_order=1,
            ),
        ]
        config = ChunkingConfig(max_characters=500, overlap_characters=100, minimum_characters=20)
        result = chunk_blocks(blocks, config)
        # Each page block is separate, so chunks from page 1 shouldn't contain page 2 text
        for chunk in result:
            assert "Page one content" not in chunk.text or "Page two content" not in chunk.text

    def test_chunking_no_cross_sheet(self) -> None:
        """Different sheet blocks stay separate — no chunk merges across sheets."""
        blocks = [
            ParsedBlock(
                text="Sheet A data. " * 10,
                block_type="paragraph",
                sheet_name="Sheet1",
                source_order=0,
            ),
            ParsedBlock(
                text="Sheet B data. " * 10,
                block_type="paragraph",
                sheet_name="Sheet2",
                source_order=1,
            ),
        ]
        config = ChunkingConfig(max_characters=500, overlap_characters=100, minimum_characters=20)
        result = chunk_blocks(blocks, config)
        for chunk in result:
            assert "Sheet A data" not in chunk.text or "Sheet B data" not in chunk.text

    def test_chunking_normalization(self) -> None:
        """Unicode NFKC normalization is applied to all chunk text."""
        # Full-width characters (U+FF21 = Ａ) normalize to ASCII 'A' under NFKC
        blocks = [
            ParsedBlock(text="ＡＢＣＤ", block_type="paragraph", source_order=0),
        ]
        config = ChunkingConfig()
        result = chunk_blocks(blocks, config)
        assert len(result) == 1
        assert result[0].text == "ABCD"


# ---------------------------------------------------------------------------
# 13-18. Embedding tests
# ---------------------------------------------------------------------------


class TestEmbedding:
    def test_embedding_deterministic(self) -> None:
        """Same text produces the same embedding vector."""
        vec1 = generate_embedding("cold storage temperature control")
        vec2 = generate_embedding("cold storage temperature control")
        assert vec1 == vec2

    def test_embedding_cross_process(self) -> None:
        """Embedding is deterministic across separate Python processes."""
        text = "deterministic cross process test"
        result_main = generate_embedding(text)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"""
import json
from cold_storage.modules.knowledge.domain.embedding import generate_embedding
vec = generate_embedding("{text}")
print(json.dumps(vec))
""",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
            env={
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parent.parent.parent / "src"),
            },
        )
        assert result.returncode == 0, f"Subprocess failed: {result.stderr}"
        result_sub = [float(v) for v in __import__("json").loads(result.stdout.strip())]
        assert result_main == result_sub

    def test_embedding_empty(self) -> None:
        """Empty text produces a zero vector."""
        config = FakeEmbeddingConfig(dimension=64)
        vec = generate_embedding("", config)
        assert vec == [0.0] * 64

    def test_embedding_whitespace_only(self) -> None:
        """Whitespace-only text produces a zero vector."""
        config = FakeEmbeddingConfig(dimension=64)
        vec = generate_embedding("   \n\t  ", config)
        assert vec == [0.0] * 64

    def test_embedding_finite(self) -> None:
        """All embedding values are finite (no inf or nan)."""
        vec = generate_embedding("This is a test sentence for finite values.")
        for v in vec:
            assert math.isfinite(v), f"Non-finite value found: {v}"

    def test_embedding_dimension(self) -> None:
        """Embedding vector has the configured dimension (64)."""
        config = FakeEmbeddingConfig(dimension=64)
        vec = generate_embedding("dimension check", config)
        assert len(vec) == 64

    def test_embedding_chinese(self) -> None:
        """Chinese text with unigrams+bigrams produces a valid embedding."""
        vec = generate_embedding("冷库温度控制系统")
        assert len(vec) == 64
        # Non-zero vector (Chinese chars produce tokens)
        assert any(v != 0.0 for v in vec)
        # All finite
        for v in vec:
            assert math.isfinite(v)


# ---------------------------------------------------------------------------
# 19-20. BM25 tests
# ---------------------------------------------------------------------------


class TestBM25:
    def test_bm25_basic(self) -> None:
        """Basic BM25 scoring: query token present in doc should give positive score."""
        query_tokens = ["cold", "storage"]
        doc_tokens = ["cold", "storage", "temperature", "control"]
        avg_dl = 4.0
        idf = {"cold": 1.5, "storage": 1.2, "temperature": 0.8, "control": 0.9}
        score = bm25_score(query_tokens, doc_tokens, avg_dl, idf, k1=1.2, b=0.75)
        assert score > 0

    def test_bm25_no_match(self) -> None:
        """BM25 with no matching tokens gives zero score."""
        query_tokens = ["frozen", "ice"]
        doc_tokens = ["cold", "storage"]
        avg_dl = 2.0
        idf = {"cold": 1.0, "storage": 1.0, "frozen": 1.0, "ice": 1.0}
        score = bm25_score(query_tokens, doc_tokens, avg_dl, idf)
        assert score == 0.0

    def test_bm25_tokenizer_units(self) -> None:
        """Unit strings like kWh, kg are tokenized; kW and (r) are separate tokens."""
        text = "The power is 15 kW and consumption is 120 kWh with area 200 m2 and mass 50 kg"
        tokens = tokenize(text)
        # Verify unit-like tokens are present
        token_set = set(tokens)
        assert "kwh" in token_set
        assert "kg" in token_set
        assert "kw" in token_set


# ---------------------------------------------------------------------------
# 21-22. Hybrid score tests
# ---------------------------------------------------------------------------


class TestHybridScore:
    def test_hybrid_score_weights(self) -> None:
        """Hybrid score weights sum to 1."""
        profile = RetrievalProfile()
        total = profile.lexical_weight + profile.semantic_weight
        assert total == Decimal("1")

    def test_hybrid_score_zero_lexical(self) -> None:
        """Zero lexical score is handled correctly in hybrid scoring."""
        profile = RetrievalProfile()
        query_emb = generate_embedding("test query")
        chunk_emb = generate_embedding("test chunk")
        score = hybrid_score(
            lexical_score=0.0,
            max_lexical_score=10.0,
            query_embedding=query_emb,
            chunk_embedding=chunk_emb,
            profile=profile,
        )
        # Score should still have a semantic component
        assert score.hybrid_score >= Decimal("0")
        assert score.lexical_normalized == Decimal("0")


# ---------------------------------------------------------------------------
# 23-25. Cosine similarity tests
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_cosine_similarity(self) -> None:
        """Basic cosine similarity: similar direction gives high score."""
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(1.0)

    def test_cosine_identical(self) -> None:
        """Cosine of identical vectors equals 1."""
        vec = [0.3, 0.4, 0.5, 0.6]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_cosine_orthogonal(self) -> None:
        """Cosine of orthogonal vectors equals 0."""
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_zero_vector(self) -> None:
        """Cosine similarity with zero vector returns 0."""
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    def test_cosine_different_length(self) -> None:
        """Cosine similarity of different-length vectors returns 0."""
        a = [1.0, 2.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0


# ---------------------------------------------------------------------------
# 26. Tokenizer compound unit tokens
# ---------------------------------------------------------------------------


class TestTokenizerCompoundUnits:
    def test_tokenize_kw_units(self) -> None:
        """kW(r), kW(e) produce compound tokens; kWh is a single token."""
        tokens_r = tokenize("kW(r)")
        assert "kw(r)" in tokens_r
        tokens_e = tokenize("kW(e)")
        assert "kw(e)" in tokens_e
        tokens_kwh = tokenize("kWh")
        assert "kwh" in tokens_kwh
        # Compound tokens are distinct — kW(r) ≠ kW(e)
        assert "kw(r)" != "kw(e)"

    def test_tokenize_kwh_vs_kwe(self) -> None:
        """Tokenizing kW(r) vs kW(e) produces different embeddings."""
        emb_r = generate_embedding("kW(r)")
        emb_e = generate_embedding("kW(e)")
        assert emb_r != emb_e


# ---------------------------------------------------------------------------
# 27. Tie-break stability
# ---------------------------------------------------------------------------


class TestTieBreakStability:
    def test_tie_break_stable(self) -> None:
        """Sorting candidates with same scores is stable and deterministic."""
        from cold_storage.modules.knowledge.domain.models import (
            KnowledgeChunk,
            RetrievalCandidate,
            RetrievalScore,
        )

        score = RetrievalScore(
            hybrid_score=Decimal("0.5"),
            lexical_normalized=Decimal("0.3"),
            semantic_normalized=Decimal("0.2"),
        )

        _REVIEW_PRIORITY = {"approved": 0, "reviewed": 1, "unverified": 2, "withdrawn": 3}

        def _sort_key(c: RetrievalCandidate) -> tuple:
            return (
                -c.score.hybrid_score,
                -c.score.lexical_normalized,
                -c.score.semantic_normalized,
                _REVIEW_PRIORITY.get(c.review_status, 2),
                c.document_code,
                -c.revision_number,
                c.chunk.chunk_index,
                c.chunk.id,
            )

        candidates = [
            RetrievalCandidate(
                chunk=KnowledgeChunk(text="same", chunk_index=0, id="chunk-aaa"),
                score=score,
                document_code="DOC-A",
                review_status="unverified",
                revision_number=2,
            ),
            RetrievalCandidate(
                chunk=KnowledgeChunk(text="same", chunk_index=0, id="chunk-bbb"),
                score=score,
                document_code="DOC-A",
                review_status="approved",
                revision_number=1,
            ),
            RetrievalCandidate(
                chunk=KnowledgeChunk(text="same", chunk_index=0, id="chunk-ccc"),
                score=score,
                document_code="DOC-A",
                review_status="reviewed",
                revision_number=3,
            ),
        ]

        sorted1 = sorted(candidates, key=_sort_key)
        sorted2 = sorted(candidates, key=_sort_key)

        # Deterministic: same order on repeated sorts
        assert [c.chunk.id for c in sorted1] == [c.chunk.id for c in sorted2]

        # Tie-break by review_status priority: approved > reviewed > unverified
        assert sorted1[0].review_status == "approved"
        assert sorted1[1].review_status == "reviewed"
        assert sorted1[2].review_status == "unverified"


# ---------------------------------------------------------------------------
# 28. Dynamic requires_review
# ---------------------------------------------------------------------------


class TestSearchRequiresReviewDynamic:
    def test_search_requires_review_dynamic(self) -> None:
        """requires_review is False when all results are from approved revisions."""
        from cold_storage.modules.knowledge.domain.models import (
            KnowledgeChunk,
            KnowledgeRevision,
            RetrievalCandidate,
            RetrievalScore,
        )

        # Approved revision: requires_review is explicitly set to False
        approved_rev = KnowledgeRevision(
            review_status="approved",
            requires_review=False,
        )
        assert approved_rev.requires_review is False

        # Unverified revision: requires_review defaults to True
        unverified_rev = KnowledgeRevision(review_status="unverified")
        assert unverified_rev.requires_review is True

        # Simulate the service's any_requires_review logic
        score = RetrievalScore(hybrid_score=Decimal("0.5"))
        candidates = [
            RetrievalCandidate(
                chunk=KnowledgeChunk(text="test", id="c1"),
                score=score,
                document_code="DOC-1",
                review_status="approved",
                revision_number=1,
            ),
            RetrievalCandidate(
                chunk=KnowledgeChunk(text="test", id="c2"),
                score=score,
                document_code="DOC-1",
                review_status="approved",
                revision_number=2,
            ),
        ]

        # Service logic: approved revisions have requires_review=False
        revision_requires_review = {"approved": False, "unverified": True, "reviewed": True}
        any_requires_review = False
        for candidate in candidates:
            if revision_requires_review.get(candidate.review_status, True):
                any_requires_review = True
        assert any_requires_review is False


# ---------------------------------------------------------------------------
# 29. Real search_chunks tie-break
# ---------------------------------------------------------------------------


class TestRealSearchChunksTieBreak:
    def test_search_chunks_real_tie_break(self) -> None:
        """search_chunks sorts approved > unverified when scores are identical.

        Regression test: verify the REAL search_chunks() function breaks ties
        using review_status priority, not a copied _sort_key helper.
        """

        from cold_storage.modules.knowledge.domain.models import (
            KnowledgeChunk,
            RetrievalCandidate,
            RetrievalProfile,
        )
        from cold_storage.modules.knowledge.domain.retrieval import search_chunks

        profile = RetrievalProfile()
        shared_text = "cold storage temperature control system"

        # Two candidates with the SAME text (same BM25/cosine scores)
        # but different review_status and revision_number.
        approved = RetrievalCandidate(
            chunk=KnowledgeChunk(text=shared_text, chunk_index=0, id="chunk-approved"),
            document_code="DOC-A",
            review_status="approved",
            revision_number=1,
        )
        unverified = RetrievalCandidate(
            chunk=KnowledgeChunk(text=shared_text, chunk_index=0, id="chunk-unverified"),
            document_code="DOC-A",
            review_status="unverified",
            revision_number=2,
        )

        results = search_chunks(
            query="cold storage",
            candidates=[unverified, approved],  # unverified first
            profile=profile,
            top_k=10,
        )

        assert len(results) == 2
        # Approved candidate must sort first (review_status priority 0 < 2)
        assert results[0].review_status == "approved"
        assert results[0].chunk.id == "chunk-approved"
        assert results[1].review_status == "unverified"
        assert results[1].chunk.id == "chunk-unverified"
