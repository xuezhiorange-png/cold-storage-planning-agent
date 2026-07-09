"""TASK-019 Slice 3A placeholder fixture cases.

This module is part of the **TASK-019 Slice 3A placeholder fixture contract**.
It is **NOT** an implementation. It does **NOT** import any production code,
does **NOT** call any production path, and does **NOT** contain any real
expected output.

Each entry in :data:`TASK_019_SLICE_3_PLACEHOLDER_CASES` is a **placeholder
case** for a future validation-adapter implementation round. The placeholder
shape is dictated by the source contract:

    docs/tasks/TASK-019-slice-3-validation-adapter-contract.md
    (merged via PR #52; merge commit e237a9a14288a554b0043be4117bd818794d4b63)

The fixture contract is documented in:

    docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md

**No production modules are imported.** No database sessions are opened.
No calculations are performed. This module is a **shape-only contract** for
a future adapter implementation.

**Discipline (per the source contract §4 forbidden scope)**:
- No production formula / coefficient / threshold / weight / scoring rule
  is referenced.
- No pressure-drop implementation is referenced (none exists in the repo).
- No `production_seeding.py` is restored.
- No `cold_storage.modules.*` or `cold_storage.evaluation.*` is imported.
- No SQLAlchemy session is opened.
- No `ValidationReport` production model is created.
"""

from __future__ import annotations

# The single source of truth for the fixture contract: the design contract
# (PR #52 / merge commit e237a9a14288a554b0043be4117bd818794d4b63).
_SOURCE_CONTRACT_PATH = "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md"
_FIXTURE_CONTRACT_PATH = "docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md"

# Status closed set, per the source contract §5. Kept in sync with the
# design contract; fixture cases reference these strings only.
STATUS_IMPLEMENTED = "implemented"
STATUS_NOT_IMPLEMENTED = "not_implemented"
STATUS_PLACEHOLDER = "placeholder"
STATUS_SKIPPED = "skipped"
STATUS_REQUIRES_UPSTREAM_SLICE = "requires_upstream_slice"
STATUS_BLOCKED = "blocked"

EXPECTED_STATUS_CLOSED_SET = frozenset(
    {
        STATUS_IMPLEMENTED,
        STATUS_NOT_IMPLEMENTED,
        STATUS_PLACEHOLDER,
        STATUS_SKIPPED,
        STATUS_REQUIRES_UPSTREAM_SLICE,
        STATUS_BLOCKED,
    }
)


def _placeholder_inputs(reason: str) -> dict:
    """Build a placeholder ``inputs`` payload.

    The payload is intentionally non-computational. It contains only a
    ``placeholder`` flag and a human-readable ``reason``; no engineering
    numbers, no engineering units, no engineering formulas.
    """
    return {
        "placeholder": True,
        "reason": reason,
    }


def _placeholder_expected_output(reason: str) -> dict:
    """Build a placeholder ``expected_output`` payload.

    The payload is intentionally non-assertable: it does **not** contain
    any value against which a future adapter could make a numerical
    assertion. The ``placeholder: True`` flag is the source of truth.
    """
    return {
        "placeholder": True,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Placeholder cases
# ---------------------------------------------------------------------------
# Each case is a self-contained dict. The shape follows the source
# contract §6 (Fixture contract) and §8 (Validation report schema),
# with the additional `expected_status` field per the Slice 3A contract.
# ---------------------------------------------------------------------------

_CASE_01_SMOKE_PLACEHOLDER: dict = {
    "task_id": "TASK-019",
    "slice_id": "slice-3",
    "case_id": "case_01_smoke_placeholder",
    "inputs": _placeholder_inputs(
        "TBD-by-Slice-3A fixture contract only; smoke-test the placeholder shape."
    ),
    "expected_output": _placeholder_expected_output(
        "No real expected output authorized for this case."
    ),
    "requires_slice": None,
    "expected_status": STATUS_PLACEHOLDER,
    "placeholder_fields": ["inputs", "expected_output"],
    "reason": (
        "Smoke case used to verify the placeholder shape is well-formed. "
        "Both inputs and expected_output are explicitly placeholder; no "
        "real expected value is asserted."
    ),
    "source_references": [
        _SOURCE_CONTRACT_PATH,
        _FIXTURE_CONTRACT_PATH,
    ],
}

_CASE_02_REQUIRES_UPSTREAM_SLICE: dict = {
    "task_id": "TASK-019",
    "slice_id": "slice-3",
    "case_id": "case_02_requires_upstream_slice",
    "inputs": _placeholder_inputs(
        "TBD-by-Slice-3A; this case requires an upstream TASK-019 slice "
        "(e.g., Slice 1 or Slice 2) that has not yet been authored."
    ),
    "expected_output": _placeholder_expected_output(
        "Cannot be produced until the upstream slice completes; not a real "
        "expected value, and not a failure."
    ),
    "requires_slice": "slice-1",  # upstream slice identifier, per §6
    "expected_status": STATUS_REQUIRES_UPSTREAM_SLICE,
    "placeholder_fields": ["inputs", "expected_output"],
    "reason": (
        "Case requires an upstream TASK-019 slice that has not been "
        "authored. The case is intentionally a placeholder; the future "
        "adapter must classify it as `requires_upstream_slice`, not as "
        "`implemented` and not as `failure`."
    ),
    "source_references": [
        _SOURCE_CONTRACT_PATH,
        _FIXTURE_CONTRACT_PATH,
    ],
}

_CASE_03_MALFORMED_OR_BLOCKED_PLACEHOLDER: dict = {
    "task_id": "TASK-019",
    "slice_id": "slice-3",
    "case_id": "case_03_malformed_or_blocked_placeholder",
    "inputs": {
        # Intentionally NOT a placeholder shape: the inputs themselves are
        # structurally invalid (missing required fields) to exercise the
        # `blocked` status path. This is the ONLY way `blocked` is allowed.
        "placeholder": False,
        "missing_required_field": "intentionally_absent",
        "reason": (
            "Intentionally malformed to exercise the `blocked` status path. "
            "This case is not a real fixture; it is a shape-validation probe."
        ),
    },
    "expected_output": _placeholder_expected_output(
        "Cannot be produced; inputs are structurally invalid. "
        "The future adapter must classify this case as `blocked`, not as "
        "`placeholder` and not as `implemented`."
    ),
    "requires_slice": None,
    "expected_status": STATUS_BLOCKED,
    "placeholder_fields": ["expected_output"],
    "reason": (
        "Intentionally malformed to exercise the `blocked` status path per "
        "the source contract §5. The `blocked` status is reserved for "
        "cases where the contract or the inputs are not executable; it is "
        "neither success nor ordinary skip. This is the only kind of case "
        "the future adapter is allowed to classify as `blocked`."
    ),
    "source_references": [
        _SOURCE_CONTRACT_PATH,
        _FIXTURE_CONTRACT_PATH,
    ],
}

# The single tuple-like collection. Order is significant for documentation
# purposes only; the test that validates case_id uniqueness is order-agnostic.
TASK_019_SLICE_3_PLACEHOLDER_CASES: tuple[dict, ...] = (
    _CASE_01_SMOKE_PLACEHOLDER,
    _CASE_02_REQUIRES_UPSTREAM_SLICE,
    _CASE_03_MALFORMED_OR_BLOCKED_PLACEHOLDER,
)


# Public lookup helpers (read-only; the test module consumes these).
def get_case_by_id(case_id: str) -> dict:
    """Return the placeholder case whose ``case_id`` matches.

    Raises:
        KeyError: if no case with that case_id is found. This is a
            defensive lookup; the contract test is expected to verify
            uniqueness separately.
    """
    for case in TASK_019_SLICE_3_PLACEHOLDER_CASES:
        if case["case_id"] == case_id:
            return case
    raise KeyError(case_id)


def iter_cases() -> tuple[dict, ...]:
    """Return the tuple of all placeholder cases (immutable view)."""
    return TASK_019_SLICE_3_PLACEHOLDER_CASES


__all__ = [
    "STATUS_IMPLEMENTED",
    "STATUS_NOT_IMPLEMENTED",
    "STATUS_PLACEHOLDER",
    "STATUS_SKIPPED",
    "STATUS_REQUIRES_UPSTREAM_SLICE",
    "STATUS_BLOCKED",
    "EXPECTED_STATUS_CLOSED_SET",
    "TASK_019_SLICE_3_PLACEHOLDER_CASES",
    "get_case_by_id",
    "iter_cases",
]
