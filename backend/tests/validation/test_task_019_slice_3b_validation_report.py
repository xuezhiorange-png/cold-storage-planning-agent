"""TASK-019 Slice 3B validation report tests — §15.2 required tests.

This module is part of the **TASK-019 Slice 3B adapter implementation**
contract. The contract is anchored at:

    docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md

These tests verify the ``ValidationReport`` dataclass that lives in
``cold_storage.modules.reports.application.validation_report``
(see §6.2 of the contract for the allowed-files list).

The tests are deliberately **structure-only** — they do NOT invoke the
production path, do NOT call the validation adapter, and do NOT open
a database session. They validate the dataclass schema, the JSON
round-trip property, and the closed-set enforcement of the ``status``
field.

Required tests (per the contract §15.2):

    * ``test_validation_report_required_fields``
    * ``test_validation_report_json_round_trip``
    * ``test_validation_report_status_closed_set``

No production modules are imported. No SQLAlchemy session is opened.
"""

from __future__ import annotations

import json

import pytest

from cold_storage.modules.reports.application.validation_report import (
    STATUS_BLOCKED,
    STATUS_CLOSED_SET,
    STATUS_IMPLEMENTED,
    STATUS_NOT_IMPLEMENTED,
    STATUS_PLACEHOLDER,
    STATUS_REQUIRES_UPSTREAM_SLICE,
    STATUS_SKIPPED,
    ValidationReport,
)


def _build_sample_report(**overrides: object) -> ValidationReport:
    """Build a sample ``ValidationReport`` with all §8 fields populated.

    Used as a fixture for the round-trip + required-fields tests. Any
    override keyword argument replaces the default for the named field.
    """
    defaults: dict[str, object] = {
        "task_id": "TASK-019",
        "slice_id": "slice-3",
        "case_id": "case_01_smoke_placeholder",
        "status": STATUS_PLACEHOLDER,
        "reason": "expected output is placeholder; no assertion possible",
        "implemented_fields": ["case_id", "slice_id"],
        "placeholder_fields": ["expected_output", "inputs"],
        "missing_fields": [],
        "blocked_fields": [],
        "source_references": [
            "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md",
            "docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md",
        ],
        "warnings": [
            "case is intentionally a placeholder; do not assert against expected_output",
        ],
        "expected_output": {
            "placeholder": True,
            "reason": "No real expected output authorized for this case.",
        },
        "metadata": {"design_base_sha": "9185b766de877c32557a355a6c6ce30d444154c0"},
    }
    defaults.update(overrides)
    return ValidationReport(**defaults)  # type: ignore[arg-type]


def test_validation_report_required_fields() -> None:
    """Verify the §8 required fields are present and typed correctly.

    This test constructs a sample ``ValidationReport`` and asserts that
    every required field (per the upstream Slice 3 §8 schema) is
    populated and that the optional fields default sensibly when omitted.
    """
    report = _build_sample_report()

    # Required fields — access via attribute, not via __dict__ keys, so
    # this test stays type-checkable.
    assert report.task_id == "TASK-019"
    assert report.slice_id == "slice-3"
    assert report.case_id == "case_01_smoke_placeholder"
    assert report.status == STATUS_PLACEHOLDER
    assert report.reason.startswith("expected output is placeholder")

    # Required list fields are list[str] instances (per §8 of upstream).
    assert isinstance(report.implemented_fields, list)
    assert all(isinstance(item, str) for item in report.implemented_fields)
    assert isinstance(report.placeholder_fields, list)
    assert all(isinstance(item, str) for item in report.placeholder_fields)
    assert isinstance(report.missing_fields, list)
    assert isinstance(report.blocked_fields, list)
    assert isinstance(report.source_references, list)
    assert isinstance(report.warnings, list)

    # Optional fields preserve their payload verbatim.
    assert report.expected_output == {
        "placeholder": True,
        "reason": "No real expected output authorized for this case.",
    }
    assert report.metadata == {
        "design_base_sha": "9185b766de877c32557a355a6c6ce30d444154c0",
    }

    # Defaults: a report constructed with only the required fields has
    # empty lists and an empty metadata dict.
    minimal = ValidationReport(
        task_id="TASK-019",
        slice_id="slice-3",
        case_id="case_03_malformed_or_blocked_placeholder",
        status=STATUS_BLOCKED,
        reason="Intentionally malformed to exercise the blocked status path.",
    )
    assert minimal.implemented_fields == []
    assert minimal.placeholder_fields == []
    assert minimal.missing_fields == []
    assert minimal.blocked_fields == []
    assert minimal.source_references == []
    assert minimal.warnings == []
    assert minimal.expected_output is None
    assert minimal.metadata == {}


def test_validation_report_json_round_trip() -> None:
    """Verify JSON serialize -> deserialize preserves all field values.

    Required by §15.2: "serialize a ValidationReport to JSON; deserialize
    back; assert all field values are preserved verbatim (including the
    ``placeholder: True`` flag in ``expected_output``, if present)".
    """
    original = _build_sample_report()

    # Serialize — round-trip through ``dict`` then ``json`` to exercise
    # the actual JSON serializer (not just ``asdict``).
    serialized_dict = original.to_dict()
    payload = json.loads(json.dumps(serialized_dict))
    assert isinstance(payload, dict)

    # Deserialize.
    restored = ValidationReport.from_dict(payload)

    # Field-by-field equality.
    assert restored.task_id == original.task_id
    assert restored.slice_id == original.slice_id
    assert restored.case_id == original.case_id
    assert restored.status == original.status
    assert restored.reason == original.reason
    assert restored.implemented_fields == original.implemented_fields
    assert restored.placeholder_fields == original.placeholder_fields
    assert restored.missing_fields == original.missing_fields
    assert restored.blocked_fields == original.blocked_fields
    assert restored.source_references == original.source_references
    assert restored.warnings == original.warnings

    # The ``placeholder: True`` flag in ``expected_output`` is preserved
    # verbatim — this is the canonical proof of the round-trip property.
    assert restored.expected_output == {
        "placeholder": True,
        "reason": "No real expected output authorized for this case.",
    }
    assert restored.expected_output is not None
    assert restored.expected_output.get("placeholder") is True

    # metadata is preserved verbatim.
    assert restored.metadata == original.metadata


def test_validation_report_status_closed_set() -> None:
    """Verify the ``status`` field accepts only the §5 closed set.

    Required by §15.2: "assert that the ``status`` field, when set, is one
    of the Slice 3 §5 values (``implemented``, ``not_implemented``,
    ``placeholder``, ``skipped``, ``requires_upstream_slice``,
    ``blocked``)".
    """
    # Closed set contains exactly the six §5 statuses.
    assert (
        frozenset(
            {
                STATUS_IMPLEMENTED,
                STATUS_NOT_IMPLEMENTED,
                STATUS_PLACEHOLDER,
                STATUS_SKIPPED,
                STATUS_REQUIRES_UPSTREAM_SLICE,
                STATUS_BLOCKED,
            }
        )
        == STATUS_CLOSED_SET
    )

    # Each closed-set value is constructible.
    for status in STATUS_CLOSED_SET:
        report = _build_sample_report(status=status)
        assert report.status == status

    # Construction with a status outside the closed set raises
    # ``ValueError`` (defence-in-depth on top of the assertion above).
    with pytest.raises(ValueError) as exc_info:
        _build_sample_report(status="not-in-closed-set")
    assert "ValidationReport.status must be one of" in str(exc_info.value)

    # ``from_dict`` also refuses an out-of-closed-set status because the
    # constructor's ``__post_init__`` runs on every construction path.
    bad_payload = {
        "task_id": "TASK-019",
        "slice_id": "slice-3",
        "case_id": "case_01_smoke_placeholder",
        "status": "arbitrary-string",
        "reason": "should fail closed-set validation",
    }
    with pytest.raises(ValueError) as exc_info:
        ValidationReport.from_dict(bad_payload)
    assert "ValidationReport.status must be one of" in str(exc_info.value)
