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

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from cold_storage.evaluation.canonicalization import (
    canonicalize_production_outputs,
)
from cold_storage.evaluation.errors import (
    EvaluationComparisonError,
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
                if not (isinstance(expected_value, str) and isinstance(actual_value, str)):
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

    # P0-4 of review 4693931575: detect unexpected actual
    # leaves RECURSIVELY (the historical top-level-key scan
    # missed ``$.outer.extra`` when only ``$.outer.inner``
    # was declared). The contract:
    #
    #   * every actual leaf MUST be either a declared
    #     comparison path OR strictly inside a declared
    #     container path;
    #   * having a declared descendant does NOT cover the
    #     whole parent — the parent must still be declared
    #     explicitly for the recursive walk to consider it
    #     covered.
    #
    # The structured unexpected diff carries the V1 JSON
    # Path of the offending leaf (e.g. ``$.outer.extra`` or
    # ``$.items[1].id``), so downstream code classifies by
    # the diff ``kind`` enum (NEVER by ``reason`` text).
    if declared_leaves and (isinstance(actual, (Mapping, list)) or _is_scalar(actual)):
        actual_leaves = _enumerate_actual_leaves(actual)
        # A declared path is a "container" iff its target
        # is a dict / list under V1 semantics. The helper
        # decides: a path ending in ``.key`` / ``[N]`` is
        # NOT itself a container (it points to a scalar
        # inside a container); a path WITHOUT a trailing
        # step IS a container (e.g. ``$.outer`` /
        # ``$.items`` / ``$.items[0]`` / ``$``). We walk
        # the actual tree and only treat a path as
        # "covering a subtree" if it actually points to a
        # container in the actual value.
        declared_container_paths: set[str] = set()
        for declared in declared_paths:
            target = _resolve_path(actual, declared)
            if isinstance(target, (Mapping, list)):
                declared_container_paths.add(declared)
        for leaf_path, leaf_value in actual_leaves:
            if leaf_path in declared_paths:
                continue
            if _path_is_under_container(leaf_path, declared_container_paths):
                continue
            diffs.append(
                ComparisonDiffEntry(
                    path=leaf_path,
                    kind="unexpected",
                    expected=None,
                    actual=leaf_value,
                    reason=(
                        "actual value has a leaf that is not covered by the "
                        "declared policy (recursive undeclared-leaf detection "
                        "per review 4693931575 P0-4)"
                    ),
                )
            )

    return ComparisonResult(
        passed=len(diffs) == 0,
        diffs=tuple(diffs),
    )


def _is_scalar(value: object) -> bool:
    """Return True iff ``value`` is a strict-JSON scalar (None /
    bool / int / float / str)."""
    return isinstance(value, (type(None), bool, int, float, str))


def _enumerate_actual_leaves(
    value: object,
) -> list[tuple[str, object]]:
    """Recursively enumerate every JSON-domain node in ``value``.

    The implementation is the in-module counterpart to the
    ``enumerate_leaves`` helper in
    :mod:`cold_storage.evaluation.json_path` (which is
    intentionally NOT touched in this corrective round per
    the path-precise authority of review 4694841112). The
    output format is identical: a list of
    ``(path, leaf_value)`` tuples with V1 restricted JSON
    Path strings (e.g. ``"$.outer.inner"`` /
    ``"$.items[0].id"``).

    The function is depth-first and preserves list order
    (V1 contract is order-exact). Dicts are walked in
    insertion order (Python 3.7+ invariant). The function
    raises :class:`EvaluationComparisonError` on a non-JSON
    value (defense-in-depth; the canonicalizer rejects
    non-JSON values upstream).

    P0-4 of review 4694841112: empty ``{}`` / ``[]`` are
    emitted as terminal coverage nodes (the node ITSELF is
    the leaf, with the empty container as the value). This
    ensures that an undeclared empty ``{}`` / ``[]`` in the
    actual value is surfaced as a structured ``unexpected``
    diff instead of being silently absent from the leaf
    enumeration.
    """
    leaves: list[tuple[str, object]] = []
    _walk_leaves(value, parent_path="$", out=leaves)
    return leaves


def _walk_leaves(value: object, *, parent_path: str, out: list[tuple[str, object]]) -> None:
    if isinstance(value, Mapping):
        if not value:
            # P0-4 of review 4694841112: an EMPTY mapping is
            # itself a terminal coverage node. The diff is
            # ``kind=unexpected`` if the policy did NOT
            # declare the container path; the diff is
            # skipped (covered) if the policy declared the
            # container path.
            out.append((parent_path, value))
            return
        for key, sub in value.items():
            if not isinstance(key, str):
                raise EvaluationComparisonError(
                    "_enumerate_actual_leaves received a dict with a "
                    "non-string key; the value is not in the strict-JSON "
                    "domain.",
                    details={
                        "parent_path": parent_path,
                        "non_str_key_type": type(key).__name__,
                    },
                )
            child_path = f"{parent_path}.{key}"
            # P0-4 of review 4694841112: an empty
            # ``Mapping`` or ``list`` is a terminal coverage
            # node; recursion stops and the empty container
            # itself is emitted as the leaf (so the
            # comparison layer can detect undeclared
            # ``{}`` / ``[]`` as a structured
            # ``unexpected`` diff).
            if isinstance(sub, (Mapping, list)) and sub:
                _walk_leaves(sub, parent_path=child_path, out=out)
            else:
                out.append((child_path, sub))
    elif isinstance(value, list):
        if not value:
            # P0-4 of review 4694841112: an EMPTY list is
            # itself a terminal coverage node (same
            # rationale as the empty-mapping case above).
            out.append((parent_path, value))
            return
        for index, sub in enumerate(value):
            child_path = f"{parent_path}[{index}]"
            if isinstance(sub, (Mapping, list)) and sub:
                _walk_leaves(sub, parent_path=child_path, out=out)
            else:
                out.append((child_path, sub))
    else:
        # Scalar (None / bool / int / float / str).
        out.append((parent_path, value))


def _path_is_under_container(path: str, container_paths: set[str]) -> bool:
    """Return True iff ``path`` is strictly under any container in
    ``container_paths`` (i.e. one of the container paths is a strict
    ancestor of ``path``).
    """
    for container in container_paths:
        if not container:
            continue
        # ``path`` is under ``container`` iff ``path`` starts
        # with ``container + "."`` (a key-step descendant) or
        # ``container + "["`` (an index-step descendant).
        if path.startswith(container + ".") or path.startswith(container + "["):
            return True
    return False


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
    except JSONPathLookupError:
        return _MISSING


def _same_json_type(a: object, b: object) -> bool:
    """Return True iff ``a`` and ``b`` are the same JSON-domain type.

    The strict-JSON value domain is
    ``None | bool | int | float | str | list | dict``. Booleans
    are NOT interchangeable with ints (D4 explicit, V1 contract).
    """
    if type(a) is not type(b):  # noqa: SIM103
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
        a_list = cast(list[object], a)
        b_list = cast(list[object], b)
        if len(a_list) != len(b_list):
            return False
        return all(
            _exact_equal(x, y)
            for x, y in zip(a_list, b_list)  # noqa: B905
        )
    if isinstance(a, dict):
        a_dict = cast(dict[object, object], a)
        b_dict = cast(dict[object, object], b)
        if set(a_dict.keys()) != set(b_dict.keys()):
            return False
        return all(_exact_equal(a_dict[k], b_dict[k]) for k in a_dict)
    return a == b


def _has_subpath_match(declared_paths: set[str], candidate: str) -> bool:
    """Deprecated.

    The P0-4 recursive undeclared-leaf detection uses
    :func:`_path_is_under_container` instead. This helper is
    kept as a thin wrapper for any external test that may
    import it (the public ``compare_outputs`` no longer
    references it). It MUST NOT be used inside the
    comparison executor.
    """
    return any(declared.startswith(candidate + ".") for declared in declared_paths)


__all__ = [
    "ComparisonDiffEntry",
    "ComparisonResult",
    "DiffKind",
    "compare_outputs",
]
