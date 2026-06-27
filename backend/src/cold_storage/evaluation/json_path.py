"""Shared JSONPath parsing, rendering, and path construction for evaluation comparison.

All modules (canonicalizer, comparator, manifest validator) use the same
path representation to ensure consistency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cold_storage.evaluation.errors import JsonPathInvalidError


@dataclass(frozen=True, slots=True)
class ObjectKeySegment:
    """Access an object key by name."""

    key: str


@dataclass(frozen=True, slots=True)
class ArrayIndexSegment:
    """Access an array element by integer index."""

    index: int


@dataclass(frozen=True, slots=True)
class ParsedJsonPath:
    """A parsed JSONPath expression for simple lookup operations.

    ``raw`` always holds the canonical form produced by ``render_json_path``.
    """

    raw: str
    segments: tuple[ObjectKeySegment | ArrayIndexSegment, ...]


# Object key grammar: [a-zA-Z_][a-zA-Z0-9_]*
_OBJECT_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def parse_json_path(path_str: str) -> ParsedJsonPath:
    """Parse a simple JSONPath expression.

    Supports the grammar:
      $                 root (no segments)
      $.field           object key access
      $[0]              array index access
      $.items[0]        chained access
      $.matrix[0][1]    repeated array index

    Object keys must match the identifier grammar ``[a-zA-Z_][a-zA-Z0-9_]*``.

    Does NOT support:
      wildcards, recursive descent, filters, negative indexes, slices,
      quoted property expressions, or root arrays as entry point.

    Raises:
        JsonPathInvalidError: If the path uses unsupported syntax.
    """
    if not path_str:
        raise JsonPathInvalidError(
            code="EVAL_JSON_PATH_INVALID",
            message="Empty JSONPath is not allowed",
            field=path_str,
        )
    if path_str == "$":
        return ParsedJsonPath(raw=path_str, segments=())

    if not path_str.startswith("$"):
        raise JsonPathInvalidError(
            code="EVAL_JSON_PATH_INVALID",
            message=f"JSONPath must start with '$': '{path_str}'",
            field=path_str,
        )

    remainder = path_str[1:]  # strip leading $
    segments: list[ObjectKeySegment | ArrayIndexSegment] = []

    idx = 0
    while idx < len(remainder):
        ch = remainder[idx]
        if ch == ".":
            # Object key: .field_name
            idx += 1
            start = idx
            while idx < len(remainder) and remainder[idx] not in ("[", "."):
                idx += 1
            key = remainder[start:idx]
            if not key:
                raise JsonPathInvalidError(
                    code="EVAL_JSON_PATH_INVALID",
                    message=f"Empty object key in JSONPath: '{path_str}'",
                    field=path_str,
                )
            # Enforce identifier grammar
            if not _OBJECT_KEY_RE.match(key):
                raise JsonPathInvalidError(
                    code="EVAL_JSON_PATH_INVALID",
                    message=f"Invalid object key '{key}' in JSONPath: '{path_str}' "
                    f"(must match [a-zA-Z_][a-zA-Z0-9_]*)",
                    field=path_str,
                )
            segments.append(ObjectKeySegment(key=key))
        elif ch == "[":
            # Array index: [digits]
            idx += 1
            start = idx
            while idx < len(remainder) and remainder[idx] != "]":
                idx += 1
            if idx >= len(remainder) or remainder[idx] != "]":
                raise JsonPathInvalidError(
                    code="EVAL_JSON_PATH_INVALID",
                    message=f"Unclosed bracket in JSONPath: '{path_str}'",
                    field=path_str,
                )
            idx_str = remainder[start:idx]
            if not idx_str:
                raise JsonPathInvalidError(
                    code="EVAL_JSON_PATH_INVALID",
                    message=f"Empty array index in JSONPath: '{path_str}'",
                    field=path_str,
                )
            try:
                index = int(idx_str)
            except ValueError:
                raise JsonPathInvalidError(
                    code="EVAL_JSON_PATH_INVALID",
                    message=f"Invalid array index '{idx_str}' in JSONPath: '{path_str}'",
                    field=path_str,
                ) from None
            if index < 0:
                raise JsonPathInvalidError(
                    code="EVAL_JSON_PATH_INVALID",
                    message=f"Negative array index not allowed in JSONPath: '{path_str}'",
                    field=path_str,
                )
            segments.append(ArrayIndexSegment(index=index))
            idx += 1  # skip closing ]
        else:
            raise JsonPathInvalidError(
                code="EVAL_JSON_PATH_INVALID",
                message=f"Unexpected character '{ch}' in JSONPath: '{path_str}'",
                field=path_str,
            )

    return ParsedJsonPath(raw=path_str, segments=tuple(segments))


def render_json_path(parsed: ParsedJsonPath) -> str:
    """Render a ParsedJsonPath back to its canonical string form.

    Always produces paths in ``$.field`` / ``$.field[0]`` format.
    """
    parts = ["$"]
    for seg in parsed.segments:
        if isinstance(seg, ObjectKeySegment):
            parts.append(f".{seg.key}")
        elif isinstance(seg, ArrayIndexSegment):
            parts.append(f"[{seg.index}]")
    return "".join(parts)


def resolve_json_path(
    obj: Any,
    parsed: ParsedJsonPath,
) -> tuple[Any, bool]:
    """Resolve a parsed JSONPath against a JSON value.

    Returns (value, found) where found is True if the path exists.
    """
    current = obj
    for seg in parsed.segments:
        if isinstance(seg, ObjectKeySegment):
            if not isinstance(current, dict):
                return None, False
            if seg.key not in current:
                return None, False
            current = current[seg.key]
        elif isinstance(seg, ArrayIndexSegment):
            if not isinstance(current, (list, tuple)):
                return None, False
            if seg.index < 0 or seg.index >= len(current):
                return None, False
            current = current[seg.index]
    return current, True


def append_object_key(parent_path: str, key: str) -> str:
    """Build a child JSONPath string by appending an object key.

    ``append_object_key("$", "area")`` → ``"$.area"``
    ``append_object_key("$.obj", "field")`` → ``"$.obj.field"``
    """
    if parent_path == "$":
        return f"$.{key}"
    return f"{parent_path}.{key}"


def append_array_index(parent_path: str, index: int) -> str:
    """Build a child JSONPath string by appending an array index.

    ``append_array_index("$", 0)`` → ``"$[0]"``
    ``append_array_index("$.items", 1)`` → ``"$.items[1]"``
    """
    return f"{parent_path}[{index}]"
