"""Fixture-contract tests for the TASK-019 Slice 3A placeholder fixtures.

This test module is part of the **TASK-019 Slice 3A placeholder fixture
contract**. It validates **fixture shape only**. It does **NOT**:

- call the validation adapter (the adapter is not authorized in this round);
- call the production calculation path;
- open a database session;
- snapshot or assert against any real expected output;
- generate any report artifact.

The discipline is dictated by the source contract:

    docs/tasks/TASK-019-slice-3-validation-adapter-contract.md
    (merged via PR #52; merge commit e237a9a14288a554b0043be4117bd818794d4b63)

and the Slice 3A fixture contract:

    docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md

**No production modules are imported.** No SQLAlchemy session is opened.
No adapter code is exercised. This module is shape-only.
"""

from __future__ import annotations

import pytest

from ._task_019_slice_3_placeholder_fixtures import (
    EXPECTED_STATUS_CLOSED_SET,
    STATUS_BLOCKED,
    STATUS_IMPLEMENTED,
    STATUS_NOT_IMPLEMENTED,
    STATUS_PLACEHOLDER,
    STATUS_REQUIRES_UPSTREAM_SLICE,
    STATUS_SKIPPED,
    TASK_019_SLICE_3_PLACEHOLDER_CASES,
    get_case_by_id,
    iter_cases,
)

# ---------------------------------------------------------------------------
# Shape-level invariants
# ---------------------------------------------------------------------------


def test_case_id_uniqueness() -> None:
    """Every case must have a unique ``case_id``."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for case in TASK_019_SLICE_3_PLACEHOLDER_CASES:
        case_id = case["case_id"]
        if case_id in seen:
            duplicates.add(case_id)
        seen.add(case_id)
    assert not duplicates, f"duplicate case_id(s): {sorted(duplicates)}"


def test_minimum_case_count() -> None:
    """The fixture contract requires at least 3 placeholder cases."""
    assert len(TASK_019_SLICE_3_PLACEHOLDER_CASES) >= 3, (
        f"expected at least 3 placeholder cases; got {len(TASK_019_SLICE_3_PLACEHOLDER_CASES)}"
    )


@pytest.mark.parametrize(
    "case",
    list(TASK_019_SLICE_3_PLACEHOLDER_CASES),
    ids=lambda case: case["case_id"],
)
def test_task_id_is_fixed(case: dict) -> None:
    """Every case must have ``task_id == "TASK-019"``."""
    assert case["task_id"] == "TASK-019", case["case_id"]


@pytest.mark.parametrize(
    "case",
    list(TASK_019_SLICE_3_PLACEHOLDER_CASES),
    ids=lambda case: case["case_id"],
)
def test_slice_id_is_fixed(case: dict) -> None:
    """Every case must have ``slice_id == "slice-3"``."""
    assert case["slice_id"] == "slice-3", case["case_id"]


@pytest.mark.parametrize(
    "case",
    list(TASK_019_SLICE_3_PLACEHOLDER_CASES),
    ids=lambda case: case["case_id"],
)
def test_required_fields_present(case: dict) -> None:
    """Every case must carry all required fields per the contract §6/§8."""
    required = (
        "case_id",
        "task_id",
        "slice_id",
        "inputs",
        "expected_output",
        "expected_status",
        "placeholder_fields",
        "reason",
        "source_references",
    )
    missing = [k for k in required if k not in case]
    assert not missing, f"{case['case_id']}: missing fields {missing}"


@pytest.mark.parametrize(
    "case",
    list(TASK_019_SLICE_3_PLACEHOLDER_CASES),
    ids=lambda case: case["case_id"],
)
def test_expected_status_in_closed_set(case: dict) -> None:
    """``expected_status`` must be in the closed set defined by §5."""
    status = case["expected_status"]
    assert status in EXPECTED_STATUS_CLOSED_SET, (
        f"{case['case_id']}: expected_status {status!r} "
        f"is not in the closed set {sorted(EXPECTED_STATUS_CLOSED_SET)}"
    )


# ---------------------------------------------------------------------------
# Placeholder semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    list(TASK_019_SLICE_3_PLACEHOLDER_CASES),
    ids=lambda case: case["case_id"],
)
def test_placeholder_case_has_placeholder_fields(case: dict) -> None:
    """A placeholder case must list at least one field in
    ``placeholder_fields``."""
    assert case["placeholder_fields"], (
        f"{case['case_id']}: placeholder case must list at least one "
        f"placeholder field in 'placeholder_fields'"
    )


@pytest.mark.parametrize(
    "case",
    list(TASK_019_SLICE_3_PLACEHOLDER_CASES),
    ids=lambda case: case["case_id"],
)
def test_placeholder_expected_output_must_not_be_implemented(case: dict) -> None:
    """If ``expected_output.placeholder is True``, ``expected_status`` MUST
    NOT be ``implemented``. The future adapter is forbidden from
    reclassifying a placeholder case as success."""
    expected_output = case.get("expected_output") or {}
    if expected_output.get("placeholder") is True:
        assert case["expected_status"] != STATUS_IMPLEMENTED, (
            f"{case['case_id']}: expected_output is placeholder; "
            f"expected_status MUST NOT be 'implemented'"
        )


@pytest.mark.parametrize(
    "case",
    list(TASK_019_SLICE_3_PLACEHOLDER_CASES),
    ids=lambda case: case["case_id"],
)
def test_requires_slice_implies_requires_upstream_slice_status(case: dict) -> None:
    """If ``requires_slice`` is non-null, ``expected_status`` MUST be
    ``requires_upstream_slice``. The future adapter is forbidden from
    reclassifying such a case as ``placeholder`` or as ``failure``."""
    if case.get("requires_slice"):
        assert case["expected_status"] == STATUS_REQUIRES_UPSTREAM_SLICE, (
            f"{case['case_id']}: requires_slice is set "
            f"(={case['requires_slice']!r}); expected_status MUST be "
            f"'requires_upstream_slice' (got {case['expected_status']!r})"
        )


# ---------------------------------------------------------------------------
# Source-references invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    list(TASK_019_SLICE_3_PLACEHOLDER_CASES),
    ids=lambda case: case["case_id"],
)
def test_source_references_include_source_contract(case: dict) -> None:
    """Every case must reference the source design contract (PR #52)."""
    expected = "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md"
    assert expected in case["source_references"], (
        f"{case['case_id']}: source_references must include {expected!r}; "
        f"got {case['source_references']!r}"
    )


# ---------------------------------------------------------------------------
# No-real-expected-output invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    list(TASK_019_SLICE_3_PLACEHOLDER_CASES),
    ids=lambda case: case["case_id"],
)
def test_no_real_expected_output_invented(case: dict) -> None:
    """``expected_output`` must NOT contain any value that looks like a
    real expected value (e.g. a numeric value, a kW / m^2 / CNY field, a
    formula). The Slice 3A contract forbids inventing real expected
    outputs.

    The only allowed content of ``expected_output`` is the
    ``placeholder: True`` flag and a human-readable ``reason``.
    """
    expected_output = case.get("expected_output") or {}
    forbidden_keys = (
        "value",
        "kW",
        "m2",
        "m^2",
        "CNY",
        "formula",
        "expected_kw",
        "expected_cny",
        "expected_m2",
    )
    found = [k for k in forbidden_keys if k in expected_output]
    assert not found, (
        f"{case['case_id']}: expected_output contains forbidden "
        f"real-value keys {found}; placeholder cases must not invent "
        f"real expected outputs"
    )


# ---------------------------------------------------------------------------
# Closed-set sanity (defensive)
# ---------------------------------------------------------------------------


def test_status_constants_match_closed_set() -> None:
    """The exported status constants are exactly the closed-set members."""
    assert STATUS_IMPLEMENTED in EXPECTED_STATUS_CLOSED_SET
    assert STATUS_NOT_IMPLEMENTED in EXPECTED_STATUS_CLOSED_SET
    assert STATUS_PLACEHOLDER in EXPECTED_STATUS_CLOSED_SET
    assert STATUS_SKIPPED in EXPECTED_STATUS_CLOSED_SET
    assert STATUS_REQUIRES_UPSTREAM_SLICE in EXPECTED_STATUS_CLOSED_SET
    assert STATUS_BLOCKED in EXPECTED_STATUS_CLOSED_SET
    assert len(EXPECTED_STATUS_CLOSED_SET) == 6


def test_get_case_by_id_round_trip() -> None:
    """get_case_by_id must return the same case for every known case_id."""
    for case in TASK_019_SLICE_3_PLACEHOLDER_CASES:
        retrieved = get_case_by_id(case["case_id"])
        assert retrieved is case  # identity check; tuple is stable


def test_iter_cases_is_immutable_view() -> None:
    """iter_cases must return the same tuple object every call."""
    assert iter_cases() is iter_cases()
    assert iter_cases() is TASK_019_SLICE_3_PLACEHOLDER_CASES
