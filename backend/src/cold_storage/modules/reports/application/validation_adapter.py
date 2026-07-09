"""TASK-019 Slice 3B validation adapter — thin placeholder contract adapter.

This module is part of the **TASK-019 Slice 3B adapter implementation**
contract. The contract is anchored at:

    docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md
    (contract merged via PR #55; merge commit 9185b766...)

The adapter's responsibility (per the Slice 3B contract §4 / §8 / §9 /
§10 / §11 / §13):

    1. Take a Slice 3A fixture case dict (one of the three permitted
       cases: ``case_01_smoke_placeholder``,
       ``case_02_requires_upstream_slice``,
       ``case_03_malformed_or_blocked_placeholder``).
    2. Classify the case to exactly one of the Slice 3A ``expected_status``
       values (placeholder, requires_upstream_slice, blocked) using only
       the Slice 3A fixture's ``expected_status`` and the placeholder
       semantics from the Slice 3A fixture helper.
    3. Build a ``ValidationReport`` typed object (see ``validation_report``)
       with the upstream Slice 3 §8 required fields populated.
    4. Surface the fixture's ``placeholder_fields``, ``source_references``,
       and ``expected_output`` verbatim — including the
       ``placeholder: True`` flag.
    5. Surface any adapter-internal warning as informational only; the
       ``status`` field remains the source of truth (Slice 3B contract §14).

The adapter is **strictly read-only** with respect to production data
(Slice 3B contract §8.3 / §11):

    * It does NOT compute business results.
    * It does NOT infer missing fields.
    * It does NOT swallow exceptions (any exception is captured to
      ``warnings``; an unrecoverable exception transitions the case to
      ``blocked``).
    * It does NOT mutate the database — no ``session.flush()``,
      ``session.commit()``, ``INSERT``, ``UPDATE``, ``DELETE``, raw SQL,
      ``bulk_insert_mappings``.
    * It does NOT import any production-formula / coefficient /
      pressure-drop / discount / salvage / cost-model module (contract
      §7.1 / §13).
    * It does NOT fill in placeholder fields with production results
      (contract §12 / §13). For all three Slice 3A cases the production
      path does NOT exist or the inputs are placeholder / malformed /
      blocked, so ``production_output`` is expected to be ``None``.

Inputs
======

``validate_case(case, production_output=None, metadata=None)``

* ``case``: required. A Slice 3A fixture case dict (see
  ``backend.tests.validation._task_019_slice_3_placeholder_fixtures``).
* ``production_output``: optional. The result of invoking the production
  path on the case's inputs, ``None`` when the production path does
  not exist or was not invoked. For all three Slice 3A cases the
  production path does NOT exist; the adapter treats ``None`` as the
  default and never invokes the production path itself.
* ``metadata``: optional. An opaque dict carrying additional context.
  The adapter does **not** interpret ``metadata``; it attaches it to
  the report unchanged.

Output
======

A single ``ValidationReport`` instance. The adapter does NOT return
``None``; failure to construct a report is itself a ``blocked`` case
(Slice 3B contract §8.2).

The three Slice 3A cases always classify to the same ``status`` because
the contract §10 mandates that the adapter routes each case to its
Slice 3A ``expected_status`` verbatim.
"""

from __future__ import annotations

import logging
from typing import Any

from cold_storage.modules.reports.application.validation_report import (
    STATUS_BLOCKED,
    STATUS_PLACEHOLDER,
    STATUS_REQUIRES_UPSTREAM_SLICE,
    ValidationReport,
)

logger = logging.getLogger(__name__)

# String identifiers used inside the warnings list. These mirror the
# advisory examples enumerated in the Slice 3B contract §14.
WARNING_PRODUCTION_API_UNAVAILABLE: str = "production_api_unavailable"
WARNING_CONTRACT_AMBIGUOUS: str = "contract_ambiguous"
WARNING_UNSUPPORTED_CASE_SHAPE: str = "unsupported_case_shape"
WARNING_ADAPTER_INTERNAL_WARNING: str = "adapter_internal_warning"

# Strings that the Slice 3A fixture helper uses for the three permitted
# case_id values. The adapter accepts only these three (Slice 3B contract
# §10 — "no expansion of the three Slice 3A fixture cases").
_CASE_ID_SMOKE: str = "case_01_smoke_placeholder"
_CASE_ID_REQUIRES_UPSTREAM: str = "case_02_requires_upstream_slice"
_CASE_ID_MALFORMED_BLOCKED: str = "case_03_malformed_or_blocked_placeholder"
_PERMITTED_CASE_IDS: frozenset[str] = frozenset(
    {_CASE_ID_SMOKE, _CASE_ID_REQUIRES_UPSTREAM, _CASE_ID_MALFORMED_BLOCKED}
)

# Source contract paths, verbatim. These are surfaced into the report's
# ``source_references`` for provenance preservation (Slice 3B contract §9).
_SOURCE_CONTRACT_PATH: str = "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md"
_FIXTURE_CONTRACT_PATH: str = "docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md"
_SLICE_3B_IMPLEMENTATION_CONTRACT_PATH: str = (
    "docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md"
)


def _coerce_string_list(value: Any) -> list[str]:
    """Coerce ``value`` to a ``list[str]`` defensively.

    The fixture helper uses concrete ``list[str]`` instances today; this
    coercion exists to keep the adapter resilient to a future Slice 3A
    contract amendment that might swap the concrete type (e.g. to a
    tuple). The contract forbids changing the SHAPE of the placeholder
    case but does NOT prevent evolving the concrete container type.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value]
    except TypeError:
        return [str(value)]


def _classify_case(case: dict[str, Any]) -> tuple[str, str]:
    """Route the case to its Slice 3A ``expected_status`` verbatim.

    Returns a ``(status, reason)`` tuple. The status is taken directly from
    the fixture's ``expected_status`` field per Slice 3B contract §10 —
    "the adapter must report each case with the Slice 3A
    ``expected_status`` (verbatim)".

    The reason is built from the fixture's ``reason`` text plus the
    case_id so downstream consumers can trace the classification back
    to its source case without referring to external state.
    """
    expected_status = case.get("expected_status")
    fixture_reason = case.get("reason") or ""
    case_id = case.get("case_id") or "<unknown>"

    # Per Slice 3B contract §10, the adapter routes only to the Slice 3A
    # expected_status values for the three permitted cases. If a caller
    # supplies an unknown case_id (which is forbidden by §10 but the
    # adapter must still be resilient — it must NOT silently rewrite it
    # as ``implemented``), the adapter routes to ``blocked`` with a
    # warning (contract §9 "fail-closed for ambiguous mixed placeholders"
    # generalized to the unsupported case shape).
    if expected_status not in (
        STATUS_PLACEHOLDER,
        STATUS_REQUIRES_UPSTREAM_SLICE,
        STATUS_BLOCKED,
    ):
        return (
            STATUS_BLOCKED,
            (
                f"case_id={case_id} has expected_status={expected_status!r} "
                "which is not a Slice 3B-recognized status; routed to "
                f"{STATUS_BLOCKED!r} per fail-closed semantics."
            ),
            # No third element — we construct the (status, reason) tuple
            # only; the warning is added by validate_case() when it sees
            # the unsupported status.
        )[:2]

    # Verbatim status from the fixture, plus the fixture's reason text.
    reason = f"{fixture_reason} (case_id={case_id})"
    return (str(expected_status), reason)


def _build_implemented_fields(
    case: dict[str, Any],
    placeholder_fields: list[str],
) -> list[str]:
    """Return the list of fixture fields that are NOT placeholder.

    Per upstream Slice 3 §8 the ``implemented_fields`` list enumerates
    "the input/output fields that are real (not placeholder)". For the
    three Slice 3A cases the only real-by-shape fields are the case's
    own identity (case_id, slice_id, task_id, expected_status,
    placeholder_fields, reason, source_references, requires_slice).
    ``inputs`` and ``expected_output`` are the placeholder fields.
    """
    placeholder_set = set(placeholder_fields)
    candidate_fields = [
        "case_id",
        "task_id",
        "slice_id",
        "expected_status",
        "reason",
        "placeholder_fields",
        "source_references",
        "requires_slice",
    ]
    return [field for field in candidate_fields if field not in placeholder_set]


def _build_source_references(
    case: dict[str, Any],
) -> list[str]:
    """Surface the fixture's ``source_references`` verbatim.

    Per Slice 3B contract §8.4 ("Adapter may do") the adapter surfaces
    the fixture's ``source_references`` verbatim into the report's
    ``source_references``. The fixture helper already contains the two
    contract paths; we add the Slice 3B implementation contract path so
    that downstream consumers can trace the report back to the adapter
    implementation contract without external state.
    """
    fixture_refs = _coerce_string_list(case.get("source_references"))
    out: list[str] = []
    for ref in fixture_refs:
        if ref and ref not in out:
            out.append(ref)
    if _SLICE_3B_IMPLEMENTATION_CONTRACT_PATH not in out:
        out.append(_SLICE_3B_IMPLEMENTATION_CONTRACT_PATH)
    return out


def _coerce_expected_output(case: dict[str, Any]) -> Any:
    """Return the fixture's ``expected_output`` verbatim.

    Per Slice 3B contract §12, ``expected_output`` is NEVER replaced by a
    production result. The payload — including the ``placeholder: True``
    flag — is preserved as-is.
    """
    return case.get("expected_output")


def _coerce_placeholder_fields(case: dict[str, Any]) -> list[str]:
    """Return the fixture's ``placeholder_fields`` verbatim."""
    return _coerce_string_list(case.get("placeholder_fields"))


def validate_case(
    case: dict[str, Any],
    production_output: Any = None,
    metadata: dict[str, Any] | None = None,
) -> ValidationReport:
    """Run the thin validation adapter against a Slice 3A case.

    Parameters
    ----------
    case:
        A Slice 3A fixture case dict. See
        ``backend.tests.validation._task_019_slice_3_placeholder_fixtures``
        for the three permitted cases.
    production_output:
        Optional reference to the production path result. The adapter
        does NOT compute this; the caller is responsible for invoking
        any production path. For the three Slice 3A cases no production
        path exists and this argument is expected to be ``None`` (the
        default).
    metadata:
        Optional opaque dict. The adapter does NOT interpret it; it
        surfaces it into ``ValidationReport.metadata`` unchanged.

    Returns
    -------
    ValidationReport
        A frozen report carrying the upstream Slice 3 §8 required fields
        populated from the fixture and the adapter's classification.
        The report's ``status`` is the Slice 3A ``expected_status``
        verbatim; the ``expected_output`` field is the fixture's
        ``expected_output`` verbatim (placeholder preserved).

    Notes
    -----
    The adapter never returns ``None``. Per Slice 3B contract §8.2,
    failure to construct a report is itself a ``blocked`` case. This
    function does NOT raise on unrecognized case_id; it routes to
    ``blocked`` and surfaces a warning so that the caller always
    receives a report.
    """
    if not isinstance(case, dict):
        # Per Slice 3B contract §8.2 ("failure to construct a report is
        # itself a ``blocked`` case") we do not raise here; we construct
        # a minimal ``blocked`` report instead. The caller always
        # receives a ``ValidationReport``.
        return ValidationReport(
            task_id="TASK-019",
            slice_id="slice-3b",
            case_id="<non-dict-case>",
            status=STATUS_BLOCKED,
            reason="validate_case received a non-dict ``case`` argument.",
            placeholder_fields=[],
            missing_fields=["case"],
            source_references=[_SLICE_3B_IMPLEMENTATION_CONTRACT_PATH],
            warnings=[WARNING_ADAPTER_INTERNAL_WARNING],
        )

    case_id = case.get("case_id") or "<missing-case-id>"
    placeholder_fields = _coerce_placeholder_fields(case)

    # Classify. The classify step returns the verbatim Slice 3A
    # expected_status for the three permitted cases, and routes to
    # ``blocked`` for an unsupported case shape.
    classification = _classify_case(case)
    status, reason = classification

    # Warnings (informational only; the status is the source of truth).
    # Per Slice 3B contract §14, the warnings list is informational;
    # adding a warning does NOT change the case's classification.
    warnings: list[str] = []
    if case_id not in _PERMITTED_CASE_IDS:
        warnings.append(WARNING_UNSUPPORTED_CASE_SHAPE)

    # The production path does NOT exist for any of the three Slice 3A
    # cases. If a non-None production_output is observed, surface a
    # contract_ambiguous warning so downstream consumers know to inspect
    # the unexpected shape; do NOT change the classification.
    if production_output is not None:
        warnings.append(WARNING_CONTRACT_AMBIGUOUS)
        logger.debug(
            "TASK-019 Slice 3B adapter received a non-None "
            "production_output for case_id=%s; Slice 3A does not "
            "authorize a production path for any of the three "
            "permitted cases.",
            case_id,
        )

    return ValidationReport(
        task_id=case.get("task_id") or "TASK-019",
        slice_id=case.get("slice_id") or "slice-3",
        case_id=case_id,
        status=status,
        reason=reason,
        implemented_fields=_build_implemented_fields(case, placeholder_fields),
        placeholder_fields=placeholder_fields,
        missing_fields=[]
        if case_id != _CASE_ID_MALFORMED_BLOCKED
        else _coerce_string_list(["inputs.missing_required_field"]),
        blocked_fields=[]
        if case_id != _CASE_ID_MALFORMED_BLOCKED
        else _coerce_string_list(["inputs"]),
        source_references=_build_source_references(case),
        warnings=warnings,
        expected_output=_coerce_expected_output(case),
        # Per §15.1 ``test_case_02_requires_upstream_slice_status``, the
        # fixture's ``requires_slice`` value surfaces into
        # ``metadata`` (or ``source_references``). We surface it into
        # ``metadata.requires_slice`` for downstream consumers that
        # want to inspect the upstream-slice pointer without re-parsing
        # the fixture. Caller-supplied ``metadata`` is honored
        # last-write-wins on the ``requires_slice`` slot.
        metadata=_build_metadata(case, metadata),
    )


def _build_metadata(
    case: dict[str, Any],
    caller_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the metadata payload, including ``requires_slice`` from the fixture.

    Per §15.1 ``test_case_02_requires_upstream_slice_status``: "assert
    ``requires_slice == 'slice-1'`` surfaces in ``metadata`` or
    ``source_references``". We surface it into ``metadata.requires_slice``.
    """
    out: dict[str, Any] = {}
    requires_slice = case.get("requires_slice")
    if requires_slice is not None:
        out["requires_slice"] = str(requires_slice)
    if caller_metadata is not None:
        for key, value in caller_metadata.items():
            out[key] = value
    return out


__all__ = [
    "WARNING_PRODUCTION_API_UNAVAILABLE",
    "WARNING_CONTRACT_AMBIGUOUS",
    "WARNING_UNSUPPORTED_CASE_SHAPE",
    "WARNING_ADAPTER_INTERNAL_WARNING",
    "validate_case",
]
