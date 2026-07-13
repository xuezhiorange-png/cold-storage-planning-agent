"""Canonicalization authority (TASK-011C V1 — D1, D2, D3, D4).

This module is the **single** canonicalization authority for the
TASK-011C V1 evaluation framework. Per Charles binding D1:

  CANONICALIZATION_AUTHORITY=backend.src.cold_storage.evaluation.canonicalization
  SYMBOL = canonicalize_production_outputs
  SIGNATURE = (value, *, excluded_paths) -> CanonicalBytes

Contract (D1, D2, D3, D4 from `TASK-011C-remaining-evaluation-scenarios-contract.md`):

* **Single canonicalizer only.** No second TASK-011C canonicalizer
  may exist. Canonicalization is NOT performed by the CLI, manifest
  loader, tests, fixtures, comparison code, runner, or any other
  module. ALL canonicalization goes through
  :func:`canonicalize_production_outputs`.
* **Strict JSON values only.** Only JSON-serializable values are
  accepted: ``None``, ``bool``, ``int``, ``float`` (finite), ``str``,
  ``list`` of JSON values, ``dict`` with ``str`` keys and JSON
  values. Everything else fails closed.
* **No implicit coercion.** ``Decimal`` is not silently converted to
  ``str``; ``datetime`` is not silently ISO-formatted; ``tuple`` is
  not silently converted to ``list``; ``Enum`` is not silently
  mapped to ``.value`` or ``.name``; unknown objects are NOT
  converted via ``str(value)``.
* **Empty exclusion set (D3).** ``D3_V1_EXCLUDED_JSON_PATHS=[]`` is
  the V1 contract. The ``excluded_paths`` parameter is accepted for
  signature compatibility but is **forbidden to be non-empty** in
  V1; any non-empty value raises :class:`EmptyExclusionSetRequired`.
  No wildcard exclusions are permitted. No additional exact paths
  are approved.
* **Exact equality default (D4).** No global float tolerance, no
  per-field tolerance, no undeclared quantization. Decimal-valued
  governed fields MUST be deliberately represented as canonical JSON
  strings before comparison (e.g., ``"123.45"``, ``"0"``,
  ``"-12.500"``).
* **Deterministic byte serialization.** Object keys are sorted;
  arrays preserve order; UTF-8 encoding; fixed separators
  ``(",", ":")``; ``ensure_ascii=False`` (UTF-8 directly).
* **Fail closed on reject.** All rejections raise
  :class:`CanonicalizationError` with a structured ``code``
  attribute (no message-text parsing for downstream classification).
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any, Final

# Type alias for the strict-JSON value domain.
# A JSONValue is recursively: None | bool | int | float | str
#                           | list["JSONValue"]
#                           | dict[str, "JSONValue"]
JSONValue = None | bool | int | float | str | list[Any] | dict[str, Any]

# Sentinel used as the canonical-byte marker.
# The canonicalizer does not actually return a wrapper; it returns
# ``str`` (UTF-8 text). The docstring uses "CanonicalBytes" for
# clarity but the runtime type is plain ``str``.
CanonicalBytes = str

# Hard bound for nested object depth (defense-in-depth against
# pathological inputs that could otherwise overflow Python's
# recursion limit).
_MAX_DEPTH: Final[int] = 256

# Hard bound for total number of values walked (defense-in-depth
# against unbounded inputs).
_MAX_VALUES: Final[int] = 1_000_000

# Hard bound for individual string length.
_MAX_STRING_LENGTH: Final[int] = 1_000_000


class CanonicalizationError(Exception):
    """Base class for canonicalization failures.

    Every concrete subclass sets a stable, machine-readable
    ``code`` class attribute. Downstream code MUST classify via
    ``code``, NEVER by parsing ``str(exc)`` (per Phase 4 §9
    forbidden-pattern list and D1 contract rules).
    """

    code: str = "CANONICALIZATION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self._details: dict[str, Any] = dict(details) if details else {}

    @property
    def details(self) -> dict[str, Any]:
        return dict(self._details)


class EmptyExclusionSetRequired(CanonicalizationError):
    """Raised when ``excluded_paths`` is non-empty.

    Per D3 approval, V1 exclusion set is the empty set. Any
    non-empty ``excluded_paths`` is forbidden in V1.
    """

    code = "EMPTY_EXCLUSION_SET_REQUIRED"


class UnsupportedJSONValueError(CanonicalizationError):
    """Raised when the input value is not within the strict JSON value domain.

    Rejected types include (D2 contract):

    * ``NaN`` / ``Infinity`` / ``-Infinity`` (non-finite floats)
    * ``Decimal`` objects
    * ``datetime`` / ``date`` / ``time`` objects
    * ``bytes`` / ``bytearray``
    * ``set`` / ``frozenset``
    * ``tuple`` (must be ``list``, no implicit conversion)
    * custom classes
    * non-string mapping keys
    * unsupported ``Enum``
    """

    code = "UNSUPPORTED_JSON_VALUE"


class WildcardExclusionForbidden(CanonicalizationError):
    """Raised when an excluded path contains wildcard characters.

    Wildcard exclusions are forbidden by D3. Any ``*`` or
    JSONPath wildcard is rejected.
    """

    code = "WILDCARD_EXCLUSION_FORBIDDEN"


# Per Charles D1: this is the only function in the project that
# performs canonicalization. Re-exporting it is NOT a second
# canonicalizer; it is the same function reachable via a different
# import path. Tests, runner, loader, and CLI MUST call this symbol
# directly (not their own copy).
def canonicalize_production_outputs(
    value: object,
    *,
    excluded_paths: Sequence[str],
) -> CanonicalBytes:
    """Canonicalize ``value`` to deterministic UTF-8 JSON bytes.

    Parameters
    ----------
    value:
        The Python value to canonicalize. Must already be within
        the strict JSON value domain (D2). Any non-conforming
        value fails closed via :class:`UnsupportedJSONValueError`.
    excluded_paths:
        JSONPath expressions whose values would be excluded from
        canonicalization. **MUST be the empty sequence** in V1 per
        D3. Any non-empty value raises
        :class:`EmptyExclusionSetRequired`. Any value containing
        wildcard characters (``*``) raises
        :class:`WildcardExclusionForbidden`.

    Returns
    -------
    CanonicalBytes:
        Deterministic UTF-8 text serialization of ``value`` with
        sorted object keys, fixed separators ``(",", ":")``, and
        ``ensure_ascii=False``. Arrays preserve declared order.
        The returned string can be encoded to bytes via ``.encode("utf-8")``
        and SHA-256-hashed for ``content_hash`` derivation.

    Raises
    ------
    EmptyExclusionSetRequired
        If ``excluded_paths`` is non-empty. V1 forbids exclusion.
    WildcardExclusionForbidden
        If any element of ``excluded_paths`` contains ``*``.
    UnsupportedJSONValueError
        If ``value`` contains any non-JSON-domain element (D2
        rejected list, including NaN, Infinity, Decimal, datetime,
        tuple, set, custom class, non-string key, bytes, etc.).
    """
    # D3 guard: V1 exclusion set is the empty set.
    if len(excluded_paths) > 0:
        # Wildcard check first (more specific error).
        for path in excluded_paths:
            if not isinstance(path, str):
                raise UnsupportedJSONValueError(
                    "excluded_paths must be a sequence of strings; "
                    f"got element of type {type(path).__name__}.",
                    details={"field": "excluded_paths", "value": str(path)},
                )
            if "*" in path:
                raise WildcardExclusionForbidden(
                    f"wildcard exclusions are forbidden (D3); got {path!r}.",
                    details={"path": path},
                )
        raise EmptyExclusionSetRequired(
            "excluded_paths must be empty in V1 (D3 approval); "
            f"got {len(excluded_paths)} non-empty path(s).",
            details={"count": len(excluded_paths), "paths": list(excluded_paths)},
        )

    # Validate and walk the value tree, producing a fully-strict-JSON
    # representation. This is the *only* place a value is accepted
    # into the canonical form.
    walked = _walk_strict_json(value, depth=0, path="$")

    # Serialize with deterministic options.
    return json.dumps(
        walked,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,  # belt-and-braces; we already rejected NaN above
    )


def _walk_strict_json(
    value: Any,
    *,
    depth: int,
    path: str,
) -> JSONValue:
    """Recursively validate and walk ``value``, returning a strict-JSON copy.

    The returned value is always within the strict JSON value
    domain (D2). Original ``tuple``/``set``/``Decimal``/etc. are
    NEVER silently coerced; the function raises
    :class:`UnsupportedJSONValueError` instead.

    ``path`` is the JSONPath of ``value`` (used in error details).
    """
    if depth > _MAX_DEPTH:
        raise UnsupportedJSONValueError(
            f"value nesting depth exceeds {_MAX_DEPTH} at {path!r}.",
            details={"path": path, "max_depth": _MAX_DEPTH},
        )

    # None / bool
    if value is None or isinstance(value, bool):
        return value

    # Enum — FORBIDDEN unless the value is one of bool / int / str
    # (those are handled above). Real Enum subclasses (IntEnum etc.)
    # must NOT be silently mapped to .value / .name.
    # IMPORTANT: this check must come BEFORE the int / str branches
    # because IntEnum / StrEnum are subclasses of int / str in
    # Python. If the int check runs first, IntEnum instances would
    # be silently accepted as integers, which violates D2.
    try:
        from enum import Enum as _Enum

        if isinstance(value, _Enum):
            raise UnsupportedJSONValueError(
                f"Enum at {path!r} is not allowed (D2 strict JSON "
                "domain); represent as string explicitly.",
                details={
                    "path": path,
                    "type": type(value).__name__,
                    "enum_class": type(value).__name__,
                },
            )
    except ImportError:  # pragma: no cover — Enum is stdlib
        pass

    # int (must NOT be bool; we already handled bool above).
    # Note: IntEnum is intentionally handled above; if execution
    # reaches here, the value is a real int, not an Enum.
    if isinstance(value, int):
        return value

    # float — must be finite (reject NaN / +/-Inf per D2)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsupportedJSONValueError(
                f"non-finite float at {path!r}: {value!r}.",
                details={"path": path, "value": value, "type": "float"},
            )
        return value

    # str — accept any string, but enforce length cap
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise UnsupportedJSONValueError(
                f"string at {path!r} exceeds max length {_MAX_STRING_LENGTH}.",
                details={"path": path, "length": len(value)},
            )
        return value

    # list — recurse; preserve order
    if isinstance(value, list):
        return [
            _walk_strict_json(item, depth=depth + 1, path=f"{path}[{i}]")
            for i, item in enumerate(value)
        ]

    # tuple — FORBIDDEN (D2 rejects tuple-as-array)
    if isinstance(value, tuple):
        raise UnsupportedJSONValueError(
            f"tuple at {path!r} is not allowed (D2 strict JSON domain); "
            "convert to list explicitly.",
            details={"path": path, "type": "tuple"},
        )

    # dict — keys MUST be strings
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise UnsupportedJSONValueError(
                    f"non-string dict key at {path!r}: key of type {type(k).__name__}.",
                    details={
                        "path": path,
                        "key_type": type(k).__name__,
                        "key_repr": str(k)[:200],
                    },
                )
            result[k] = _walk_strict_json(v, depth=depth + 1, path=f"{path}.{k}")
        return result

    # set / frozenset — FORBIDDEN
    if isinstance(value, (set, frozenset)):
        raise UnsupportedJSONValueError(
            f"{type(value).__name__} at {path!r} is not allowed (D2 strict JSON domain).",
            details={"path": path, "type": type(value).__name__},
        )

    # bytes / bytearray — FORBIDDEN
    if isinstance(value, (bytes, bytearray)):
        raise UnsupportedJSONValueError(
            f"{type(value).__name__} at {path!r} is not allowed (D2 strict JSON domain).",
            details={"path": path, "type": type(value).__name__},
        )

    # Decimal — FORBIDDEN (no implicit stringification per D2)
    # Imported lazily to avoid forcing the dependency if never used.
    try:
        from decimal import Decimal as _Decimal

        if isinstance(value, _Decimal):
            raise UnsupportedJSONValueError(
                f"Decimal at {path!r} is not allowed (D2 strict JSON "
                "domain); represent as canonical string explicitly.",
                details={"path": path, "type": "Decimal"},
            )
    except ImportError:  # pragma: no cover — Decimal is stdlib
        pass

    # datetime / date / time — FORBIDDEN (no implicit ISO per D2)
    try:
        import datetime as _dt

        if isinstance(value, (_dt.datetime, _dt.date, _dt.time, _dt.timedelta)):
            raise UnsupportedJSONValueError(
                f"{type(value).__name__} at {path!r} is not allowed "
                "(D2 strict JSON domain); represent as ISO string "
                "explicitly if needed.",
                details={"path": path, "type": type(value).__name__},
            )
    except ImportError:  # pragma: no cover — datetime is stdlib
        pass

    # Any other type (custom class, module, function, generator, etc.)
    # is forbidden. We never call str() on it.
    raise UnsupportedJSONValueError(
        f"unsupported type {type(value).__name__} at {path!r} (D2 strict JSON domain).",
        details={"path": path, "type": type(value).__name__},
    )


__all__ = [
    "CanonicalizationError",
    "EmptyExclusionSetRequired",
    "UnsupportedJSONValueError",
    "WildcardExclusionForbidden",
    "canonicalize_production_outputs",
]
