"""Deterministic text chunking — splits parsed blocks into fixed-size chunks."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from cold_storage.modules.knowledge.domain.models import (
    ChunkingConfig,
    KnowledgeChunk,
    ParsedBlock,
)

CHUNKER_VERSION: str = "chunk-v1"


def chunk_blocks(
    blocks: list[ParsedBlock],
    config: ChunkingConfig,
) -> list[KnowledgeChunk]:
    """Split parsed blocks into fixed-size knowledge chunks.

    Rules:
    1.  Prefer block boundaries for chunk splits.
    2.  Do not cross PDF page boundaries unless a block already spans pages.
    3.  Do not cross XLSX sheet boundaries.
    4.  Try not to split table rows — keep entire rows together when possible.
    5.  Oversized single blocks split by sentence/character boundaries.
    6.  Overlap only within the same source context (same page/sheet).
    7.  Chunk order is deterministic — same blocks + config always produce the same output.
    8.  Empty or whitespace-only blocks produce no chunks.
    9.  overlap_characters < max_characters (enforced by ChunkingConfig).
    10. Unicode NFKC normalization on all text.
    11. Each chunk records a full human-readable source_locator.
    """
    chunks: list[KnowledgeChunk] = []
    chunk_index = 0

    for block in blocks:
        normalized = _normalize_text(block.text)
        # Skip empty blocks
        if not normalized.strip():
            continue

        locator = _compute_source_locator(block)
        section = block.section_path

        # If the block fits in one chunk, emit it directly
        if len(normalized) <= config.max_characters:
            chunk = _make_chunk(
                revision_id="",
                chunk_index=chunk_index,
                text=normalized,
                section_path=section,
                block=block,
                locator=locator,
            )
            chunks.append(chunk)
            chunk_index += 1
            continue

        # Oversized block — split into sub-chunks with overlap
        pieces = _split_text_with_overlap(normalized, config)
        for piece in pieces:
            if not piece.strip():
                continue
            chunk = _make_chunk(
                revision_id="",
                chunk_index=chunk_index,
                text=piece,
                section_path=section,
                block=block,
                locator=locator,
            )
            chunks.append(chunk)
            chunk_index += 1

    return chunks


def _normalize_text(text: str) -> str:
    """Apply Unicode NFKC normalization."""
    return unicodedata.normalize("NFKC", text)


def _split_text_with_overlap(text: str, config: ChunkingConfig) -> list[str]:
    """Split text into overlapping chunks respecting sentence boundaries where possible."""
    if len(text) <= config.max_characters:
        return [text]

    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + config.max_characters, len(text))
        chunk_text = text[start:end]

        # Try to split at a sentence boundary if we're not at the end
        if end < len(text):
            split_point = _find_sentence_boundary(chunk_text)
            if split_point > config.minimum_characters:
                chunk_text = text[start : start + split_point]
                end = start + split_point

        pieces.append(chunk_text)

        # Advance with overlap
        if end >= len(text):
            break
        start = end - config.overlap_characters
        if start <= 0:
            start = end

    return pieces


def _find_sentence_boundary(text: str) -> int:
    """Find the last sentence boundary position in text (prior to the end)."""
    # Look for sentence-ending punctuation followed by space or newline
    matches = list(re.finditer(r"[.!?。！？]\s", text))
    if matches:
        return matches[-1].end()
    # Fall back to newline
    matches = list(re.finditer(r"\n", text))
    if matches:
        return matches[-1].end()
    return len(text)


def _make_chunk(
    revision_id: str,
    chunk_index: int,
    text: str,
    section_path: str,
    block: ParsedBlock,
    locator: str,
) -> KnowledgeChunk:
    """Create a KnowledgeChunk with computed hashes and counts."""
    text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return KnowledgeChunk(
        revision_id=revision_id,
        chunk_index=chunk_index,
        text=text,
        text_sha256=text_sha256,
        character_count=len(text),
        token_count=len(text.split()),
        section_path=section_path,
        page_start=block.page_start,
        page_end=block.page_end,
        sheet_name=block.sheet_name,
        row_start=block.row_start,
        row_end=block.row_end,
        source_locator=locator,
    )


def _compute_source_locator(block: ParsedBlock) -> str:
    """Build a human-readable source locator string from a parsed block."""
    parts: list[str] = []
    if block.section_path:
        parts.append(block.section_path)
    if block.page_start is not None:
        if block.page_end is not None and block.page_end != block.page_start:
            parts.append(f"p.{block.page_start}-{block.page_end}")
        else:
            parts.append(f"p.{block.page_start}")
    if block.sheet_name:
        parts.append(f"sheet:{block.sheet_name}")
    if block.row_start is not None:
        if block.row_end is not None and block.row_end != block.row_start:
            parts.append(f"rows:{block.row_start}-{block.row_end}")
        else:
            parts.append(f"row:{block.row_start}")
    if block.table_index is not None:
        parts.append(f"table:{block.table_index}")
    return " | ".join(parts) if parts else f"block:{block.source_order}"
