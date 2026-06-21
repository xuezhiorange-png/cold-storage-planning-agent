"""Fake embedding provider — deterministic, cross-platform, no ML dependencies."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from cold_storage.modules.knowledge.domain.models import FakeEmbeddingConfig

DEFAULT_CONFIG = FakeEmbeddingConfig()


def generate_embedding(
    text: str,
    config: FakeEmbeddingConfig | None = None,
) -> list[float]:
    """Generate a deterministic fake embedding from text.

    Algorithm:
    1.  Unicode NFKC normalization, lowercase.
    2.  Tokenize: English words, numbers, Chinese unigrams + bigrams, unit strings.
    3.  Each token → SHA-256 → (dimension_index, sign).
    4.  Accumulate into a vector, L2-normalize.
    5.  Empty text → zero vector.
    6.  Cross-process and cross-machine deterministic.
    """
    if config is None:
        config = DEFAULT_CONFIG

    dim = config.dimension
    if not text or not text.strip():
        return [0.0] * dim

    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens = _tokenize(normalized)

    if not tokens:
        return [0.0] * dim

    # Accumulate contributions from each token
    vector = [0.0] * dim
    for token in tokens:
        token_hash = hashlib.sha256(token.encode("utf-8")).digest()
        # Use first 4 bytes for index, next byte for sign
        idx = int.from_bytes(token_hash[:4], "big") % dim
        sign = 1.0 if (token_hash[4] & 0x80) == 0 else -1.0
        # Use a float derived from the hash for magnitude
        magnitude = int.from_bytes(token_hash[5:9], "big") / (2**32)
        contribution = sign * (1.0 + magnitude)
        vector[idx] += contribution

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]

    # Round to 6 decimal places for determinism
    vector = [
        float(Decimal(str(v)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)) for v in vector
    ]
    return vector


def _tokenize(text: str) -> list[str]:
    """Tokenize text into English words, numbers, Chinese unigrams+bigrams, and unit strings."""
    tokens: list[str] = []

    # Match English words, numbers, and common units
    for m in re.finditer(r"[a-z]+|[0-9]+(?:\.[0-9]+)?|[a-z0-9]+(?:\([^)]*\))?", text):
        tokens.append(m.group(0))

    # Extract CJK characters for unigrams and bigrams
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    for ch in cjk_chars:
        tokens.append(ch)
    for i in range(len(cjk_chars) - 1):
        tokens.append(cjk_chars[i] + cjk_chars[i + 1])

    return tokens
