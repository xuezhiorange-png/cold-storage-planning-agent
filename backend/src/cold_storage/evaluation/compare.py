"""Manifest-driven comparison executor (TASK-011C C-2 — D4 numeric-exact).

This module is the single C-2 authority for comparing the
actual normalized output (produced by
:func:`cold_storage.evaluation.canonicalization.canonicalize_production_outputs`)
against the expected normalized output (loaded from the manifest's
``expected_output.path`` file). It is **NOT** a second canonicalizer;
it consumes already-canonicalized bytes and walks them.

Per the D4 contract:

* **Default = EXACT.** No global float tolerance. No per-field
  tolerance. No undeclared tolerance. No quantize invention.
* **V1 only emits EXACT and DECIMAL kinds.** The ``EXCLUDED`` kind
  was removed by review 4689545688 P0-3.
* **Empty exclusion set (D3).** No wildcards in the policy. The
  comparison executor is fail-closed on undeclared paths and on
  forbidden tolerance declarations.

Per the C-2 contract:

* **Decimal inputs are canonical strings.** The runner MUST convert
  decimal-valued production outputs to canonical JSON strings
  (``"123.45"``, ``"0"``, ``"-12.500"``) before they reach this
  module. The comparison module treats decimal leaves as exact
  string equality — no float conversion, no quantize
  reinvention.
* **Diffs are structured.** The comparison result is a
  :class:`ComparisonResult` carrying a tuple of
  :class:`ComparisonDiffEntry` records. Downstream code classifies
  the result by ``result.passed`` and by the diff ``kind`` enum;
  it NEVER parses the diff ``reason`` text.

Per Phase 4 §9 forbidden-pattern list, this module NEVER parses
exception message text to classify errors. The infrastructure
errors raised here are typed ``EvaluationComparisonError`` with a
stable ``code`` attribute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from cold_storage.evaluation.canonicalization import (
    canonicalize_production_outputs,
)
from cold_storage.evaluation.errors import (
    EvaluationComparisonError,
    EvaluationRunnerError,
)
from cold_storage.evaluation.models import (
    ComparisonKind,
    ComparisonPolicy,
    ComparisonPolicyLeaf,
)

# ── Typed diff representation ─────────────────────────────────────────


DiffKind = Literal[
    "missing",
    "type_mismatch",
    "value_mismatch",
    "tolerance_violation",
    "unexpected",
]


@dataclass(frozen=True, slots=True)
class ComparisonDiffEntry:
    """A single structured diff entry.

    The ``path`` is the JSON Path (V1 restricted subset) of the
    leaf where the diff was found. The ``kind`` is one of:

    * ``"missing"`` — the expected leaf has no counterpart in
      actual (or vice versa, when ``unexpected``).
    * ``"type_mismatch"`` — the expected and actual values have
      different JSON-domain types.
    * ``"value_mismatch"`` — both leaves are present and same
      type but the values differ.
    * ``"tolerance_violation"`` — the policy declared a tolerance
      but V1 forbids tolerance (defense-in-depth; the policy
      schema is closed to ``{"exact", "decimal"}``).
    * ``"unexpected"`` — actual has a leaf that expected does
      not (only reported when there is no declared policy leaf
      for the path; otherwise the leaf is compared).

    The ``expected`` and ``actual`` fields carry the leaf values
    (JSON-domain only) for direct comparison. They are NEVER
    stringified via ``str(value)`` / ``repr(value)`` /
    ``format(value)``; the diff consumer renders them as needed.
    """

    path: str
    kind: DiffKind
    expected: object | None
    actual: object | None
    reason: str


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """The result of a single comparison invocation.

    ``passed`` is True iff the diff tuple is empty. A non-empty
    diff tuple means the comparison failed for at least one
    declared leaf.
    """

    passed: bool
    diffs: tuple[ComparisonDiffEntry, ...] = ()


# ── Comparison entry point ───────────────────────────────────────────


def compare_outputs(
    *,
    expected: object,
    actual: object,
    policy: ComparisonPolicy,
) -> ComparisonResult:
    """Compare ``expected`` against ``actual`` per ``policy``.

    Parameters
    ----------
    expected:
        The expected normalized value (loaded from the manifest's
        ``expected_output.path`` file). Must already be in the
        strict-JSON value domain.
    actual:
        The actual normalized value (produced by the runner
        from the production calculator output). Must already be
        in the strict-JSON value domain.
    policy:
        The manifest's comparison policy. The ``leaves`` tuple
        drives per-leaf comparison kind (EXACT / DECIMAL).
        Per the D3 contract, the policy MUST NOT carry any
        tolerance fields, exclusion fields, or wildcards.

    Returns
    -------
    ComparisonResult
        ``passed=True`` if every declared leaf matched;
        ``passed=False`` with a populated ``diffs`` tuple
        otherwise.

    Raises
    ------
    EvaluationComparisonError
        On an infrastructure-level failure (undeclared path,
        forbidden tolerance, canonicalizer rejection of the
        inputs, etc.). The error ``code`` attribute is the
        stable ``"EVALUATION_COMPARISON_ERROR"`` or one of its
        typed subtypes via ``details``.
    """
    if not isinstance(policy, ComparisonPolicy):
        raise EvaluationComparisonError(
            "compare_outputs requires a ComparisonPolicy instance.",
            details={"policy_type": type(policy).__name__},
        )
    # The strict-JSON canonicalizer validates that both expected
    # and actual are in the D2 strict-JSON value domain. If
    # either is malformed, we surface a typed ComparisonError.
    try:
        canonicalize_production_outputs(expected, excluded_paths=())
        canonicalize_production_outputs(actual, excluded_paths=())
    except Exception as exc:
        # Map the canonicalizer's typed error to a typed
        # runner error. We classify by ``code`` when available.
        code = getattr(exc, "code", "CANONICALIZATION_ERROR")
        raise EvaluationComparisonError(
            "compare_outputs received a value that is not in the "
            "strict-JSON value domain; the D1 canonicalizer "
            "rejected it.",
            details={
                "canonicalizer_code": str(code),
                "expected_type": type(expected).__name__,
                "actual_type": type(actual).__name__,
            },
        ) from exc

    diffs: list[ComparisonDiffEntry] = []
    declared_paths: set[str] = set()
    declared_leaves: list[ComparisonPolicyLeaf] = list(policy.leaves)
    if not declared_leaves:
        # Default = EXACT on the WHOLE structure when the policy
        # carries no declared leaves. We compare the two
        # canonical-form trees as scalars.
        if not _exact_equal(expected, actual):
            diffs.append(
                ComparisonDiffEntry(
                    path="$",
                    kind="value_mismatch",
                    expected=expected,
                    actual=actual,
                    reason="default EXACT comparison failed at root",
                )
            )
    else:
        for leaf in declared_leaves:
            declared_paths.add(leaf.path)
            expected_value = _resolve_path(expected, leaf.path)
            actual_value = _resolve_path(actual, leaf.path)
            if expected_value is _MISSING:
                diffs.append(
                    ComparisonDiffEntry(
                        path=leaf.path,
                        kind="missing",
                        expected=None,
                        actual=actual_value if actual_value is not _MISSING else None,
                        reason="expected value is missing at declared path",
                    )
                )
                continue
            if actual_value is _MISSING:
                diffs.append(
                    ComparisonDiffEntry(
                        path=leaf.path,
                        kind="missing",
                        expected=expected_value,
                        actual=None,
                        reason="actual value is missing at declared path",
                    )
                )
                continue
            if not _same_json_type(expected_value, actual_value):
                diffs.append(
                    ComparisonDiffEntry(
                        path=leaf.path,
                        kind="type_mismatch",
                        expected=expected_value,
                        actual=actual_value,
                        reason=(
                            f"expected type {type(expected_value).__name__!s} "
                            f"!= actual type {type(actual_value).__name__!s}"
                        ),
                    )
                )
                continue
            # Per-kind comparison.
            if leaf.kind == ComparisonKind.EXACT:
                if not _exact_equal(expected_value, actual_value):
                    diffs.append(
                        ComparisonDiffEntry(
                            path=leaf.path,
                            kind="value_mismatch",
                            expected=expected_value,
                            actual=actual_value,
                            reason="EXACT comparison failed",
                        )
                    )
            elif leaf.kind == ComparisonKind.DECIMAL:
                # Both sides are required to be canonical decimal
                # strings. We compare exact string equality.
                if not (
                    isinstance(expected_value, str)
                    and isinstance(actual_value, str)
                ):
                    diffs.append(
                        ComparisonDiffEntry(
                            path=leaf.path,
                            kind="type_mismatch",
                            expected=expected_value,
                            actual=actual_value,
                            reason=(
                                "DECIMAL comparison requires both sides to "
                                "be canonical decimal strings; got "
                                f"{type(expected_value).__name__!s} vs "
                                f"{type(actual_value).__name__!s}"
                            ),
                        )
                    )
                    continue
                if expected_value != actual_value:
                    diffs.append(
                        ComparisonDiffEntry(
                            path=leaf.path,
                            kind="value_mismatch",
                            expected=expected_value,
                            actual=actual_value,
                            reason=(
                                "DECIMAL canonical-string comparison failed "
                                "(no tolerance, no quantize invention)"
                            ),
                        )
                    )
            else:  # pragma: no cover — schema is closed to {exact, decimal}
                # Defense-in-depth: the schema forbids this but
                # if it ever changes we must fail closed.
                raise EvaluationComparisonError(
                    f"DECLARED COMPARISON KIND FORBIDDEN: {leaf.kind!s}",
                    details={"path": leaf.path, "kind": str(leaf.kind)},
                )

    # Detect unexpected actual leaves that are not covered by
    # any declared policy leaf. We do this ONLY when the policy
    # is non-empty (a declared policy means "compare exactly
    # these leaves and nothing else"). When the policy is
    # empty, the whole-structure comparison already captured
    # every difference.
    if declared_leaves and isinstance(actual, Mapping):
        for actual_key in actual.keys():
            if not isinstance(actual_key, str):
                # Untyped key (numeric, tuple, etc.) is a
                # canonicalizer rejection upstream, but we
                # surface a typed error here.
                raise EvaluationComparisonError(
                    "compare_outputs received an actual value with a "
                    "non-string dict key; the D1 canonicalizer should "
                    "have rejected it.",
                    details={"key_type": type(actual_key).__name__},
                )
            candidate = f"$.{actual_key}"
            if candidate not in declared_paths and not _has_subpath_match(
                declared_paths, candidate
            ):
                diffs.append(
                    ComparisonDiffEntry(
                        path=candidate,
                        kind="unexpected",
                        expected=None,
                        actual=actual[actual_key],
                        reason=(
                            "actual value has a leaf that is not "
                            "covered by the declared policy"
                        ),
                    )
                )

    return ComparisonResult(
        passed=len(diffs) == 0,
        diffs=tuple(diffs),
    )


# ── Internal helpers ────────────────────────────────────────────────


# Sentinel for "path not found" — distinct from None, which is a
# legitimate JSON value.
class _MissingSentinel:
    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING: Any = _MissingSentinel()


def _resolve_path(value: object, path: str) -> object:
    """Resolve ``path`` against ``value`` using the V1 JSON Path.

    Raises :class:`EvaluationComparisonError` (with code
    ``"UNDECLARED_PATH"``) when ``path`` cannot be resolved.
    The error NEVER parses path text to classify; it relies on
    the typed ``JSONPathLookupError`` from the V1 path module.
    """
    # Imported here to avoid a top-level circular import.
    from cold_storage.evaluation.json_path import (
        JSONPathLookupError,
        lookup,
        parse_path,
    )

    try:
        steps = parse_path(path)
    except Exception as exc:  # JSONPathParseError, subclass of EvaluationRunnerError
        code = getattr(exc, "code", "JSON_PATH_PARSE_ERROR")
        raise EvaluationComparisonError(
            "compare_outputs received a path that fails the V1 JSON Path parser.",
            details={"path": path, "parser_code": str(code)},
        ) from exc
    try:
        return lookup(value, steps)
    except JSONPathLookupError as exc:
        return _MISSING


def _same_json_type(a: object, b: object) -> bool:
    """Return True iff ``a`` and ``b`` are the same JSON-domain type.

    The strict-JSON value domain is
    ``None | bool | int | float | str | list | dict``. Booleans
    are NOT interchangeable with ints (D4 explicit, V1 contract).
    """
    if type(a) is not type(b):
        return False
    return True


def _exact_equal(a: object, b: object) -> bool:
    """Recursive EXACT equality over the strict-JSON value domain.

    Booleans are NOT interchangeable with ints. Lists preserve
    order. Dicts require exact key sets.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_exact_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_exact_equal(a[k], b[k]) for k in a)
    return a == b


def _has_subpath_match(declared_paths: set[str], candidate: str) -> bool:
    """Return True iff any declared path is a strict subpath of
    ``candidate``.

    Example: if the declared paths are ``{"$.a.b"}`` and the
    candidate is ``"$.a"``, the candidate has a subpath match
    and is therefore not reported as unexpected.
    """
    for declared in declared_paths:
        # declared starts with candidate + "." (i.e. declared is
        # deeper than candidate).
        if declared.startswith(candidate + "."):
            return True
    return False


__all__ = [
    "ComparisonDiffEntry",
    "ComparisonResult",
    "DiffKind",
    "compare_outputs",
]
