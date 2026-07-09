"""TASK-019 Slice 3B validation report — typed dataclass and JSON round-trip.

This module is part of the **TASK-019 Slice 3B adapter implementation**
contract. The contract is anchored at:

    docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md
    (contract merged via PR #55; merge commit 9185b766...)

The ``ValidationReport`` dataclass schema inherits the **required fields**
defined by the upstream TASK-019 Slice 3 design contract §8:

    docs/tasks/TASK-019-slice-3-validation-adapter-contract.md §8
    (contract merged via PR #52; merge commit e237a9a14288a554b0043be4117bd818794d4b63)

Field reference (verbatim from upstream §8 table):
    task_id:        string                       stable
    slice_id:       string                       stable
    case_id:        string                       stable
    status:         enum (closed set)            required
    reason:         string                       required
    implemented_fields:    list[str]
    placeholder_fields:    list[str]
    missing_fields:        list[str]
    blocked_fields:        list[str]
    source_references:     list[str]
    warnings:              list[str]

Optional fields:
    expected_output:   any      verbatim from the fixture's expected_output,
                                including the ``placeholder: True`` flag.
                                The adapter MUST NOT fill this in with a
                                production result (per §12 of the Slice 3B
                                implementation contract).
    metadata:          dict[str, Any]   opaque; the adapter does not interpret it.

JSON serialization is provided by ``ValidationReport.to_dict`` /
``ValidationReport.from_dict``; the round-trip preserves all values
verbatim including ``placeholder: True`` flags inside ``expected_output``.

The status closed set is inherited from the upstream Slice 3 §5 vocabulary:

    implemented, not_implemented, placeholder, skipped,
    requires_upstream_slice, blocked

This module does **not** import any production formula / coefficient /
pressure-drop / discount / salvage / cost-model module (forbidden by
contract §7.1). The adapter that consumes this dataclass is required by
§11 / §13 of the Slice 3B implementation contract to also be free of
those imports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Status closed set, per upstream TASK-019 Slice 3 design contract §5.
# These six strings are the only legal values for ValidationReport.status.
STATUS_IMPLEMENTED: str = "implemented"
STATUS_NOT_IMPLEMENTED: str = "not_implemented"
STATUS_PLACEHOLDER: str = "placeholder"
STATUS_SKIPPED: str = "skipped"
STATUS_REQUIRES_UPSTREAM_SLICE: str = "requires_upstream_slice"
STATUS_BLOCKED: str = "blocked"

STATUS_CLOSED_SET: frozenset[str] = frozenset(
    {
        STATUS_IMPLEMENTED,
        STATUS_NOT_IMPLEMENTED,
        STATUS_PLACEHOLDER,
        STATUS_SKIPPED,
        STATUS_REQUIRES_UPSTREAM_SLICE,
        STATUS_BLOCKED,
    }
)


def _validate_status_closed_set(status: str) -> None:
    """Raise ``ValueError`` if ``status`` is not a member of the closed set.

    Per Slice 3B contract §14, the ``status`` field of ``ValidationReport``
    is the source of truth for the case classification. A future consumer
    of the report MUST NOT treat a value outside this closed set as a
    legitimate status.
    """
    if status not in STATUS_CLOSED_SET:
        raise ValueError(
            f"ValidationReport.status must be one of {sorted(STATUS_CLOSED_SET)}; got {status!r}."
        )


@dataclass(frozen=True)
class ValidationReport:
    """TASK-019 Slice 3 validation report — typed dataclass.

    See module-level docstring for the field schema (inherited from the
    upstream TASK-019 Slice 3 design contract §8 plus Slice 3B §9/§10
    elaborations).

    The dataclass is **frozen** so that a once-constructed report is
    immutable from the perspective of downstream consumers. The adapter
    is responsible for constructing a correct report; downstream code
    MUST NOT mutate the report after the fact.
    """

    task_id: str
    slice_id: str
    case_id: str
    status: str
    reason: str
    implemented_fields: list[str] = field(default_factory=list)
    placeholder_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    blocked_fields: list[str] = field(default_factory=list)
    source_references: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Optional fields (per §8 of the upstream Slice 3 contract):
    expected_output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Status membership is verified at construction time so that an
        # invalid status never reaches a downstream consumer. This is a
        # defence-in-depth check on top of the §15.2 closed-set test.
        _validate_status_closed_set(self.status)

    # ------------------------------------------------------------------
    # JSON round-trip (per §15.2 test_validation_report_json_round_trip)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report into a JSON-safe dict.

        The serialized form preserves all field values verbatim — including
        the ``placeholder: True`` flag inside ``expected_output`` if one is
        present. The frozen dataclass is unwrapped with ``asdict``; mutable
        defaults are normalized to plain ``list`` / ``dict`` instances for
        downstream JSON consumers.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ValidationReport:
        """Construct a ``ValidationReport`` from a JSON-decoded payload.

        Unknown keys are ignored (forward-compatible). Required keys are
        read directly. ``expected_output`` is preserved verbatim including
        the ``placeholder: True`` flag if one was present in the source
        fixture.
        """
        required = (
            "task_id",
            "slice_id",
            "case_id",
            "status",
            "reason",
        )
        missing_required = [k for k in required if k not in payload]
        if missing_required:
            raise ValueError(
                f"ValidationReport.from_dict missing required keys: "
                f"{missing_required}; got keys {sorted(payload.keys())}."
            )
        return cls(
            task_id=payload["task_id"],
            slice_id=payload["slice_id"],
            case_id=payload["case_id"],
            status=payload["status"],
            reason=payload["reason"],
            implemented_fields=list(payload.get("implemented_fields") or []),
            placeholder_fields=list(payload.get("placeholder_fields") or []),
            missing_fields=list(payload.get("missing_fields") or []),
            blocked_fields=list(payload.get("blocked_fields") or []),
            source_references=list(payload.get("source_references") or []),
            warnings=list(payload.get("warnings") or []),
            expected_output=payload.get("expected_output"),
            metadata=dict(payload.get("metadata") or {}),
        )


__all__ = [
    "STATUS_IMPLEMENTED",
    "STATUS_NOT_IMPLEMENTED",
    "STATUS_PLACEHOLDER",
    "STATUS_SKIPPED",
    "STATUS_REQUIRES_UPSTREAM_SLICE",
    "STATUS_BLOCKED",
    "STATUS_CLOSED_SET",
    "ValidationReport",
]
