"""Shared tokenizer for knowledge retrieval and embedding.

Both the BM25 lexical scorer and the fake embedding provider
must use the same tokenization to ensure retrieval consistency.
"""

from __future__ import annotations

import re
import unicodedata


def tokenize(text: str) -> list[str]:
    """Deterministic tokenization matching the embedding tokenizer.

    Produces English words, numbers, Chinese unigrams + bigrams, and unit strings.
    Unit strings (kw(r), kw(e), kw(th), kwh, m², kg, ℃) are matched as single
    tokens before generic word patterns, and the text is already NFKC-normalized
    and lowercased by the caller.
    """
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    # Priority: compound unit strings first, then words, numbers, CJK
    token_pattern = r"kw\([re]\)|kw\(th\)|kwh|m[²2]|kg|℃|[a-z]+|[0-9]+(?:\.[0-9]+)?"
    for m in re.finditer(token_pattern, normalized):
        tokens.append(m.group(0))
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    for ch in cjk_chars:
        tokens.append(ch)
    for i in range(len(cjk_chars) - 1):
        tokens.append(cjk_chars[i] + cjk_chars[i + 1])
    return tokens
