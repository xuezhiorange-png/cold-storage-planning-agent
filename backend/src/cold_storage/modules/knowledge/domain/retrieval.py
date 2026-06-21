"""Retrieval — BM25 lexical search + cosine similarity hybrid scoring."""

from __future__ import annotations

import math
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from cold_storage.modules.knowledge.domain.models import (
    RetrievalCandidate,
    RetrievalProfile,
    RetrievalScore,
)


def tokenize(text: str) -> list[str]:
    """Deterministic tokenization matching the embedding tokenizer.

    Produces English words, numbers, Chinese unigrams + bigrams, and unit strings.
    """
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    # Priority: unit strings first (kW(r), kW(e), kWh, m², kg, ℃), then words, numbers, CJK
    token_pattern = r"kw\([re]\)|kwh|m[²2]|kg|℃|[a-z]+|[0-9]+(?:\.[0-9]+)?"
    for m in re.finditer(token_pattern, normalized):
        tokens.append(m.group(0))
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    for ch in cjk_chars:
        tokens.append(ch)
    for i in range(len(cjk_chars) - 1):
        tokens.append(cjk_chars[i] + cjk_chars[i + 1])
    return tokens


def bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    avg_dl: float,
    idf: dict[str, float],
    k1: float = 1.2,
    b: float = 0.75,
) -> float:
    """Compute BM25 score for a query against a document.

    Parameters
    ----------
    query_tokens : list[str]
        Tokens from the query.
    doc_tokens : list[str]
        Tokens from the document.
    avg_dl : float
        Average document length (in tokens) across the corpus.
    idf : dict[str, float]
        Inverse document frequency for each vocabulary token.
    k1, b : float
        BM25 tuning parameters.
    """
    dl = len(doc_tokens)
    # Term frequency map
    tf_map: dict[str, int] = {}
    for t in doc_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1

    score = 0.0
    for qt in query_tokens:
        if qt not in idf:
            continue
        tf = tf_map.get(qt, 0)
        if tf == 0:
            continue
        idf_val = idf[qt]
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * dl / max(avg_dl, 1.0))
        score += idf_val * (numerator / denominator)
    return score


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def hybrid_score(
    lexical_score: float,
    max_lexical_score: float,
    query_embedding: list[float],
    chunk_embedding: list[float],
    profile: RetrievalProfile,
) -> RetrievalScore:
    """Compute hybrid score combining BM25 lexical and cosine semantic scores.

    Normalizes both scores to [0, 1] before applying the profile weights.
    """
    # Normalize lexical score
    if max_lexical_score > 0:
        lexical_normalized = Decimal(str(lexical_score / max_lexical_score))
    else:
        lexical_normalized = Decimal("0")
    lexical_normalized = lexical_normalized.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # Semantic score
    semantic_raw = cosine_similarity(query_embedding, chunk_embedding)
    # Normalize cosine from [-1, 1] → [0, 1]
    raw_plus_one = Decimal(str(semantic_raw)) + Decimal("1")
    semantic_normalized = raw_plus_one / Decimal("2")
    semantic_normalized = max(Decimal("0"), min(Decimal("1"), semantic_normalized))
    semantic_normalized = semantic_normalized.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # Weighted hybrid
    hybrid = (
        profile.lexical_weight * lexical_normalized + profile.semantic_weight * semantic_normalized
    )
    hybrid = hybrid.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    return RetrievalScore(
        lexical_score=Decimal(str(lexical_score)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        ),
        lexical_normalized=lexical_normalized,
        semantic_raw=Decimal(str(semantic_raw)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        ),
        semantic_normalized=semantic_normalized,
        hybrid_score=hybrid,
        retrieval_profile=profile.code,
        embedding_version=profile.embedding_config.version,
    )


def _compute_idf(corpus_tokens: list[list[str]]) -> dict[str, float]:
    """Compute IDF for all tokens in the corpus using BM25 formula."""
    n_docs = len(corpus_tokens)
    if n_docs == 0:
        return {}
    # Count document frequency
    df: dict[str, int] = {}
    for tokens in corpus_tokens:
        unique = set(tokens)
        for t in unique:
            df[t] = df.get(t, 0) + 1
    # BM25 IDF: log((N - df + 0.5) / (df + 0.5) + 1)
    idf: dict[str, float] = {}
    for t, freq in df.items():
        idf[t] = math.log((n_docs - freq + 0.5) / (freq + 0.5) + 1)
    return idf


def search_chunks(
    query: str,
    candidates: list[RetrievalCandidate],
    profile: RetrievalProfile,
    top_k: int = 10,
) -> list[RetrievalCandidate]:
    """Full hybrid search pipeline.

    Parameters
    ----------
    query : str
        The search query text.
    candidates : list[RetrievalCandidate]
        Pre-built candidates with chunk, document_code, review_status,
        and revision_number already populated by the caller.
    profile : RetrievalProfile
        Retrieval configuration with BM25 params and weights.
    top_k : int
        Maximum number of results to return.
    """
    if not candidates:
        return []

    # Tokenize query
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    # Tokenize all documents and compute corpus stats
    doc_token_lists = [tokenize(c.chunk.text) for c in candidates]
    n_docs = len(doc_token_lists)
    total_tokens = sum(len(toks) for toks in doc_token_lists)
    avg_dl = total_tokens / max(n_docs, 1)

    idf = _compute_idf(doc_token_lists)

    # Score each chunk
    raw_lexical_scores: list[float] = []

    for _candidate, doc_tokens in zip(candidates, doc_token_lists, strict=True):
        lex_score = bm25_score(
            query_tokens,
            doc_tokens,
            avg_dl,
            idf,
            k1=float(profile.bm25_k1),
            b=float(profile.bm25_b),
        )
        raw_lexical_scores.append(lex_score)

    max_lex = max(raw_lexical_scores) if raw_lexical_scores else 0.0

    # Generate query embedding
    from cold_storage.modules.knowledge.domain.embedding import generate_embedding

    query_embedding = generate_embedding(query, profile.embedding_config)

    scored: list[RetrievalCandidate] = []
    for candidate, lex_score in zip(candidates, raw_lexical_scores, strict=True):
        chunk = candidate.chunk
        chunk_embedding = chunk.embedding if chunk.embedding else []
        score = hybrid_score(lex_score, max_lex, query_embedding, chunk_embedding, profile)
        # Create a new candidate with the score filled in, preserving metadata
        scored.append(
            RetrievalCandidate(
                chunk=chunk,
                score=score,
                document_code=candidate.document_code,
                review_status=candidate.review_status,
                revision_number=candidate.revision_number,
            )
        )

    # Sort by full tie-break chain:
    # 1. hybrid_score DESC
    # 2. lexical_normalized DESC
    # 3. semantic_normalized DESC
    # 4. review_status priority: approved > reviewed > unverified
    # 5. document code ASC
    # 6. revision_number DESC
    # 7. chunk_index ASC
    # 8. chunk_id ASC (dictionary order)
    _REVIEW_PRIORITY = {"approved": 0, "reviewed": 1, "unverified": 2, "withdrawn": 3}

    def _sort_key(
        c: RetrievalCandidate,
    ) -> tuple[  # noqa: B023
        Decimal, Decimal, Decimal, int, str, int, int, str
    ]:
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

    scored.sort(key=_sort_key)
    return scored[:top_k]
