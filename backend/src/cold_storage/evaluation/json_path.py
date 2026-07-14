"""V1 restricted JSON Path (TASK-011C C-2 comparison path authority).

This module is the single C-2 authority for parsing and evaluating
JSON Path expressions over the strict-JSON value domain. It is
intentionally narrow:

* **Allowed syntax:** ``$``, ``$.field``, ``$.nested.field``,
  ``$.array[0]`` (and combinations thereof).
* **Forbidden syntax:** wildcards (``*``), recursive descent
  (``..``), filter / script expressions (``[?(...)]``,
  ``[(...)]``), negative indexes, slices, unquoted dynamic
  expressions.

The intent is a deterministic, fail-closed, side-effect-free
lookup that the comparison executor and the run-summary
serialization can rely on. The module is **NOT** a general JSON
Path implementation; it is the V1 restricted subset that the
TASK-011C contract mandates.

Per Phase 4 §9 forbidden-pattern list, the module NEVER parses
``str(exc)`` to classify errors. Each public function raises a
typed :class:`EvaluationRunnerError` subclass with a stable
``code`` attribute.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

from cold_storage.evaluation.errors import EvaluationRunnerError

# ── Typed error classes (single-source-of-truth codes) ──────────────


class JSONPathParseError(EvaluationRunnerError):
    """Raised when a JSON Path expression fails to parse.

    The ``code`` attribute is the stable, machine-readable
    identifier ``"JSON_PATH_PARSE_ERROR"``. Downstream code
    classifies via ``code``, NEVER via ``str(exc)``.

    The error covers:

    * empty path
    * missing leading ``$``
    * wildcards (``*``)
    * recursive descent (``..``)
    * filter / script expressions (``[?(...)]`` / ``[(...)]``)
    * negative indexes (e.g. ``[-1]``)
    * slices (e.g. ``[0:3]``)
    * unquoted dynamic expressions (e.g. ``[foo]``)
    * malformed index (e.g. ``[abc]``)
    """

    code = "JSON_PATH_PARSE_ERROR"


class JSONPathLookupError(EvaluationRunnerError):
    """Raised when a parsed JSON Path fails to resolve against a value.

    The ``code`` attribute is the stable, machine-readable
    identifier ``"JSON_PATH_LOOKUP_ERROR"``. Downstream code
    classifies via ``code``, NEVER via ``str(exc)``.

    The error covers:

    * missing key on a dict
    * out-of-range index on a list
    * type mismatch (e.g. indexing a non-container, descending
      into a scalar)
    """

    code = "JSON_PATH_LOOKUP_ERROR"


# ── Parsed path representation ────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PathStep:
    """A single step in a parsed JSON Path.

    ``kind`` is one of:

    * ``"root"`` — the leading ``$`` (always at index 0; the
      path always starts with exactly one root step).
    * ``"key"`` — a ``.field`` member access.
    * ``"index"`` — a ``[N]`` index access.
    """

    kind: Literal["root", "key", "index"]
    value: str | int


# ── Parsing ───────────────────────────────────────────────────────────


# ``$.`` at the start, followed by either a ``.field`` or ``[N]``.
# A field name is one or more ``[A-Za-z0-9_]`` characters.
# An index is a non-negative integer in ``[N]``.
_STEP_RE: Final[str] = r"(?:\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\])"
_FULL_RE: Final[re.Pattern[str]] = re.compile(r"^\$" + _STEP_RE + r"*$")

# Heuristic pre-screen for forbidden syntax. We reject the entire
# expression at PARSE time (typed error, fail-closed) when any of
# these forbidden patterns appear.
_FORBIDDEN_SUBSTRINGS: Final[tuple[str, ...]] = (
    "..",  # recursive descent
    "*",  # wildcard
    "?[",  # filter expression
    "[?",  # filter expression (alternate form)
    "[(",  # script expression
    "(:",  # slice
    ":]",  # slice
)
_FORBIDDEN_NEGATIVE_INDEX: Final[re.Pattern[str]] = re.compile(r"\[-\d+\]")


def parse_path(path: str) -> list[PathStep]:
    """Parse a V1 restricted JSON Path expression.

    Parameters
    ----------
    path:
        The expression. Must start with ``$``. ``.field`` and
        ``[N]`` steps are accepted; everything else is rejected.

    Returns
    -------
    list[PathStep]
        The parsed path steps. The first step is always
        ``PathStep(kind="root", value="$")``.

    Raises
    ------
    JSONPathParseError
        On any rejection (empty input, missing leading ``$``,
        forbidden syntax, malformed index, etc.). The error
        ``code`` attribute is the stable ``"JSON_PATH_PARSE_ERROR"``.
    """
    if not isinstance(path, str) or not path:
        raise JSONPathParseError(
            "JSON Path must be a non-empty string.",
            details={"path_type": type(path).__name__},
        )
    if not path.startswith("$"):
        raise JSONPathParseError(
            "JSON Path must start with the root marker '$'.",
            details={"path_prefix": path[:1]},
        )
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        if forbidden in path:
            raise JSONPathParseError(
                f"JSON Path contains forbidden syntax {forbidden!r}; "
                "V1 only supports $.field and [N] steps.",
                details={"forbidden_token": forbidden},
            )
    if _FORBIDDEN_NEGATIVE_INDEX.search(path):
        raise JSONPathParseError(
            "JSON Path contains a negative index; V1 only supports "
            "non-negative integer indexes.",
            details={"pattern": "[-N]"},
        )
    # The remaining strict form: ``$`` followed by zero or more
    # ``.field`` / ``[N]`` steps.
    match = _FULL_RE.fullmatch(path)
    if match is None:
        raise JSONPathParseError(
            "JSON Path is not a valid V1 restricted expression; V1 "
            "only supports $.field and [N] steps (no wildcards, no "
            "slices, no scripts, no unquoted dynamic expressions).",
            details={"path_length": len(path)},
        )
    steps: list[PathStep] = [PathStep(kind="root", value="$")]
    # Iterate over the match groups. The regex has two capture
    # groups per step (``(field)`` and ``(index)``); exactly one
    # of them is non-``None`` per step.
    remainder = path[1:]  # strip the leading ``$``
    while remainder:
        if remainder.startswith("."):
            # ``.field`` — consume the leading dot.
            field_match = re.match(r"\.([A-Za-z_][A-Za-z0-9_]*)", remainder)
            if field_match is None:
                # The fullmatch guard already ensures this is
                # unreachable, but the explicit guard is
                # defense-in-depth.
                raise JSONPathParseError(
                    "JSON Path has a malformed field step; V1 only "
                    "supports [A-Za-z_][A-Za-z0-9_]* field names.",
                    details={"remainder_prefix": remainder[:8]},
                )
            steps.append(PathStep(kind="key", value=field_match.group(1)))
            remainder = remainder[field_match.end():]
        elif remainder.startswith("["):
            # ``[N]`` — consume the bracketed integer.
            index_match = re.match(r"\[(\d+)\]", remainder)
            if index_match is None:
                raise JSONPathParseError(
                    "JSON Path has a malformed index step; V1 only "
                    "supports non-negative integer indexes inside [].",
                    details={"remainder_prefix": remainder[:8]},
                )
            steps.append(PathStep(kind="index", value=int(index_match.group(1))))
            remainder = remainder[index_match.end():]
        else:
            # The fullmatch guard already ensures this is
            # unreachable.
            raise JSONPathParseError(
                "JSON Path has an unexpected character after a step.",
                details={"remainder_prefix": remainder[:8]},
            )
    return steps


# ── Lookup ────────────────────────────────────────────────────────────


def lookup(value: object, path: list[PathStep]) -> object:
    """Resolve a parsed JSON Path against ``value``.

    Parameters
    ----------
    value:
        The strict-JSON value to resolve against. ``None``,
        ``bool``, ``int``, ``float``, ``str``, ``list`` of JSON
        values, and ``dict`` with ``str`` keys are accepted.
    path:
        The parsed path steps (from :func:`parse_path`).

    Returns
    -------
    object
        The value at the path. The result is JSON-domain only;
        no implicit coercion is performed.

    Raises
    ------
    JSONPathLookupError
        On any resolution failure. The error ``code`` attribute
        is the stable ``"JSON_PATH_LOOKUP_ERROR"``.
    """
    if not isinstance(path, list) or not path:
        raise JSONPathLookupError(
            "lookup() requires a non-empty list of parsed path steps; "
            "the leading 'root' step must be present.",
            details={"path_type": type(path).__name__},
        )
    if path[0].kind != "root":
        raise JSONPathLookupError(
            "lookup() path must start with a 'root' step.",
            details={"first_step_kind": path[0].kind},
        )
    current: object = value
    for index, step in enumerate(path[1:], start=1):
        if step.kind == "key":
            if not isinstance(current, dict):
                raise JSONPathLookupError(
                    "JSON Path step requires a dict container; "
                    "got a non-dict value.",
                    details={
                        "step_index": index,
                        "step_kind": step.kind,
                        "container_type": type(current).__name__,
                    },
                )
            key = step.value
            if not isinstance(key, str) or key not in current:
                raise JSONPathLookupError(
                    "JSON Path key is missing from the dict container.",
                    details={
                        "step_index": index,
                        "step_kind": step.kind,
                        "key": key,
                    },
                )
            current = current[key]
        elif step.kind == "index":
            if not isinstance(current, list):
                raise JSONPathLookupError(
                    "JSON Path step requires a list container; "
                    "got a non-list value.",
                    details={
                        "step_index": index,
                        "step_kind": step.kind,
                        "container_type": type(current).__name__,
                    },
                )
            if not isinstance(step.value, int) or step.value < 0:
                # Defense-in-depth: parse_path already rejects
                # negative indexes.
                raise JSONPathLookupError(
                    "JSON Path index must be a non-negative integer.",
                    details={
                        "step_index": index,
                        "step_kind": step.kind,
                        "index_value": step.value,
                    },
                )
            if step.value >= len(current):
                raise JSONPathLookupError(
                    "JSON Path index is out of range for the list container.",
                    details={
                        "step_index": index,
                        "step_kind": step.kind,
                        "index_value": step.value,
                        "list_length": len(current),
                    },
                )
            current = current[step.value]
        else:
            # Defense-in-depth: parse_path only emits "key" /
            # "index" / "root" steps.
            raise JSONPathLookupError(
                "JSON Path step kind is not recognized.",
                details={
                    "step_index": index,
                    "step_kind": step.kind,
                },
            )
    return current


__all__ = [
    "JSONPathLookupError",
    "JSONPathParseError",
    "PathStep",
    "lookup",
    "parse_path",
]
