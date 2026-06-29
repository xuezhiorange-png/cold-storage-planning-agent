"""Tests for requirement metadata validation in _validate_coefficient_candidate.

Covers P0-1: requirement_hash binding + full negative test coverage for all 4
requirement metadata fields:
  1. requirement_registry_version
  2. calculator_version_vector
  3. required_codes
  4. requirement_hash (dual binding: candidate ↔ frozen)
"""

from __future__ import annotations

import pytest

from cold_storage.modules.orchestration.application.coefficient_contracts import (
    FrozenCoefficientResolutionCriteria,
)
from cold_storage.modules.orchestration.application.ports import (
    ResolvedCoefficientContextCandidate,
)
from cold_storage.modules.orchestration.application.service import (
    _AUTHORITATIVE_REQUIRED_CODES,
    _CALCULATOR_VERSION_VECTOR,
    _ORCHESTRATION_DEFINITION_VERSION,
    _REQUIREMENT_REGISTRY_VERSION,
    _compute_orchestration_fingerprint,
    _validate_coefficient_candidate,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
)
from cold_storage.modules.orchestration.domain.errors import (
    CoefficientResolutionError,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash

# Convenience aliases matching the task specification
_CV_VECTOR = _CALCULATOR_VERSION_VECTOR
_REQUIRED_CODES = _AUTHORITATIVE_REQUIRED_CODES

# ── Helpers ────────────────────────────────────────────────────────────────

_COEFFICIENTS: list[dict[str, object]] = [
    {
        "code": "area.circulation_allowance_ratio",
        "definition_id": "def-001",
        "revision_id": "rev-001",
        "revision_number": 1,
        "unit": "ratio",
        "source_type": "standard",
        "status": "approved",
        "value_decimal": "1.0",
    },
]


def _make_command(
    *,
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
) -> OrchestrationRequestCommand:
    """Create a minimal OrchestrationRequestCommand for validation tests."""
    return OrchestrationRequestCommand(
        project_id=project_id,
        project_version_id=project_version_id,
        coefficient_resolution_context={},
        actor="tester",
        correlation_id="corr-1",
    )


def _make_frozen_criteria(
    *,
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    requirement_registry_version: str = _REQUIREMENT_REGISTRY_VERSION,
    calculator_version_vector: dict[str, str] | None = None,
    required_codes: tuple[str, ...] = _REQUIRED_CODES,
    requirement_hash: str | None = None,
) -> FrozenCoefficientResolutionCriteria:
    """Create a FrozenCoefficientResolutionCriteria with authoritative defaults.

    When *requirement_hash* is ``None`` the hash is derived from the other
    three metadata fields so the criteria is always self-consistent unless
    the caller explicitly passes a wrong hash.
    """
    if calculator_version_vector is None:
        calculator_version_vector = dict(_CV_VECTOR)
    if requirement_hash is None:
        requirement_hash = result_hash(
            {
                "registry_version": requirement_registry_version,
                "calculator_version_vector": dict(calculator_version_vector),
                "required_codes": list(required_codes),
            }
        )
    return FrozenCoefficientResolutionCriteria(
        project_id=project_id,
        project_version_id=project_version_id,
        requirement_registry_version=requirement_registry_version,
        calculator_version_vector=calculator_version_vector,
        required_codes=required_codes,
        requirement_hash=requirement_hash,
    )


def _make_candidate(
    *,
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    content_override: dict[str, object] | None = None,
) -> ResolvedCoefficientContextCandidate:
    """Create a valid ResolvedCoefficientContextCandidate with all 4 requirement metadata.

    ``content_override`` is merged into the content dict **before** computing
    ``content_hash``, so the candidate is always self-consistent even when
    individual fields are intentionally wrong.
    """
    req_hash = result_hash(
        {
            "registry_version": _REQUIREMENT_REGISTRY_VERSION,
            "calculator_version_vector": dict(_CV_VECTOR),
            "required_codes": list(_REQUIRED_CODES),
        }
    )
    content: dict[str, object] = {
        "source_type": "catalog",
        "validity_status": "approved",
        "project_id": project_id,
        "project_version_id": project_version_id,
        "schema_version": "1.0.0",
        "coefficient_count": 1,
        "coefficients": list(_COEFFICIENTS),
        "requirement_registry_version": _REQUIREMENT_REGISTRY_VERSION,
        "calculator_version_vector": dict(_CV_VECTOR),
        "required_codes": list(_REQUIRED_CODES),
        "requirement_hash": req_hash,
    }
    if content_override:
        content.update(content_override)
    return ResolvedCoefficientContextCandidate(
        project_id=project_id,
        project_version_id=project_version_id,
        schema_version="1.0.0",
        content=content,
        content_hash=result_hash(content),
        approved_revision_ids=("rev-001",),
    )


def _assert_rejected(
    candidate: ResolvedCoefficientContextCandidate,
    frozen: FrozenCoefficientResolutionCriteria,
    *,
    coefficient_code: str | None = None,
    match: str | None = None,
) -> CoefficientResolutionError:
    """Assert that _validate_coefficient_candidate raises CoefficientResolutionError.

    ``coefficient_code`` checks ``err.details['coefficient_code']`` (the
    semantic sub-code such as ``'mismatch'`` or ``'criteria_integrity'``).
    ``match`` checks the full error message via ``pytest.raises(match=...)``.
    """
    command = _make_command(
        project_id=candidate.project_id,
        project_version_id=candidate.project_version_id,
    )
    with pytest.raises(CoefficientResolutionError, match=match) as exc_info:
        _validate_coefficient_candidate(candidate, command, frozen)
    err = exc_info.value
    assert err.code == "COEFF_RESOLUTION_FAILED"
    if coefficient_code is not None:
        actual = err.details.get("coefficient_code")
        assert actual == coefficient_code, (
            f"Expected coefficient_code {coefficient_code!r}, got {actual!r}"
        )
    return err


# ── 1. TestRequirementRegistryVersion ─────────────────────────────────────


class TestRequirementRegistryVersion:
    """Negative tests for requirement_registry_version in candidate content."""

    def test_field_missing(self) -> None:
        """Removing the field entirely → rejection (not a non-empty string)."""
        candidate = _make_candidate(
            content_override={"requirement_registry_version": None},
        )
        # Recompute content_hash for self-consistency (field removed → set None)
        # _make_candidate already handles this via content_override
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="requirement_registry_version")

    def test_none_value(self) -> None:
        candidate = _make_candidate(
            content_override={"requirement_registry_version": None},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="requirement_registry_version")

    def test_empty_string(self) -> None:
        candidate = _make_candidate(
            content_override={"requirement_registry_version": ""},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="requirement_registry_version")

    def test_non_string(self) -> None:
        candidate = _make_candidate(
            content_override={"requirement_registry_version": 123},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="requirement_registry_version")

    def test_wrong_version(self) -> None:
        """A valid string that doesn't match the frozen value → mismatch."""
        candidate = _make_candidate(
            content_override={"requirement_registry_version": "9.9.9"},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, coefficient_code="mismatch")


# ── 2. TestCalculatorVersionVector ────────────────────────────────────────


class TestCalculatorVersionVector:
    """Negative tests for calculator_version_vector in candidate content."""

    def test_field_missing(self) -> None:
        candidate = _make_candidate(
            content_override={"calculator_version_vector": None},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="calculator_version_vector")

    def test_none_value(self) -> None:
        candidate = _make_candidate(
            content_override={"calculator_version_vector": None},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="calculator_version_vector")

    def test_list_not_mapping(self) -> None:
        candidate = _make_candidate(
            content_override={"calculator_version_vector": ["a", "b"]},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="calculator_version_vector")

    def test_empty_key(self) -> None:
        candidate = _make_candidate(
            content_override={
                "calculator_version_vector": {"": "1.0.0"},
            },
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="calculator_version_vector")

    def test_non_string_key(self) -> None:
        candidate = _make_candidate(
            content_override={
                "calculator_version_vector": {1: "1.0.0"},
            },
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="calculator_version_vector")

    def test_empty_value(self) -> None:
        candidate = _make_candidate(
            content_override={
                "calculator_version_vector": {"zone": ""},
            },
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="calculator_version_vector")

    def test_non_string_value(self) -> None:
        candidate = _make_candidate(
            content_override={
                "calculator_version_vector": {"zone": 123},
            },
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="calculator_version_vector")

    def test_missing_calculator(self) -> None:
        """Vector missing a required calculator key → mismatch with frozen."""
        incomplete = {k: v for k, v in _CV_VECTOR.items() if k != "zone"}
        candidate = _make_candidate(
            content_override={"calculator_version_vector": incomplete},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, coefficient_code="mismatch")

    def test_extra_calculator(self) -> None:
        """Vector with an extra key → mismatch with frozen."""
        extra = dict(_CV_VECTOR, extra="1.0.0")
        candidate = _make_candidate(
            content_override={"calculator_version_vector": extra},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, coefficient_code="mismatch")

    def test_version_mismatch(self) -> None:
        """Correct keys but wrong version string → mismatch."""
        mismatched = dict(_CV_VECTOR)
        mismatched["zone"] = "2.0.0"
        candidate = _make_candidate(
            content_override={"calculator_version_vector": mismatched},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, coefficient_code="mismatch")


# ── 3. TestRequiredCodes ──────────────────────────────────────────────────


class TestRequiredCodes:
    """Negative tests for required_codes in candidate content."""

    def test_field_missing(self) -> None:
        candidate = _make_candidate(
            content_override={"required_codes": None},
        )
        frozen = _make_frozen_criteria()
        # None is not list/tuple → caught by isinstance check in _validate
        _assert_rejected(candidate, frozen, match="required_codes")

    def test_none_value(self) -> None:
        candidate = _make_candidate(
            content_override={"required_codes": None},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="required_codes")

    def test_string_not_list(self) -> None:
        candidate = _make_candidate(
            content_override={"required_codes": "not_a_list"},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="required_codes")

    def test_non_string_member(self) -> None:
        codes = list(_REQUIRED_CODES)
        codes_with_int = codes[:1] + [123]
        candidate = _make_candidate(
            content_override={"required_codes": codes_with_int},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="required_codes")

    def test_blank_member(self) -> None:
        codes = list(_REQUIRED_CODES)
        codes_with_blank = codes[:1] + [""]
        candidate = _make_candidate(
            content_override={"required_codes": codes_with_blank},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="required_codes")

    def test_duplicate_code(self) -> None:
        """Duplicate code in required_codes → rejected by validate_required_codes."""
        duped = [_REQUIRED_CODES[0], _REQUIRED_CODES[0], _REQUIRED_CODES[1]]
        candidate = _make_candidate(
            content_override={"required_codes": duped},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="duplicate")

    def test_missing_required_code(self) -> None:
        """Omit one code from the required set → mismatch with frozen."""
        incomplete = list(_REQUIRED_CODES[:-1])
        candidate = _make_candidate(
            content_override={"required_codes": incomplete},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, coefficient_code="mismatch")

    def test_extra_code(self) -> None:
        """Add an extra code → mismatch with frozen."""
        extra = list(_REQUIRED_CODES) + ["EXTRA_CODE"]
        candidate = _make_candidate(
            content_override={"required_codes": extra},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, coefficient_code="mismatch")

    def test_different_order_same_set(self) -> None:
        """Different input order but same set → ACCEPT (sorted canonical comparison)."""
        reversed_codes = list(reversed(_REQUIRED_CODES))
        candidate = _make_candidate(
            content_override={"required_codes": reversed_codes},
        )
        frozen = _make_frozen_criteria()
        command = _make_command()
        # Should NOT raise
        _validate_coefficient_candidate(candidate, command, frozen)


# ── 4. TestRequirementHash ────────────────────────────────────────────────


class TestRequirementHash:
    """Negative tests for requirement_hash in candidate content."""

    def test_field_missing(self) -> None:
        """Removing requirement_hash from content → rejection (not a non-empty string)."""
        candidate = _make_candidate(
            content_override={"requirement_hash": None},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="requirement_hash")

    def test_none_value(self) -> None:
        candidate = _make_candidate(
            content_override={"requirement_hash": None},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="requirement_hash")

    def test_empty_string(self) -> None:
        candidate = _make_candidate(
            content_override={"requirement_hash": ""},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="requirement_hash")

    def test_non_string(self) -> None:
        candidate = _make_candidate(
            content_override={"requirement_hash": 123},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, match="requirement_hash")

    def test_wrong_hash(self) -> None:
        """Valid string but doesn't match frozen → mismatch."""
        candidate = _make_candidate(
            content_override={"requirement_hash": "deadbeef"},
        )
        frozen = _make_frozen_criteria()
        _assert_rejected(candidate, frozen, coefficient_code="mismatch")

    def test_self_consistent_but_wrong_frozen_hash(self) -> None:
        """Frozen criteria has requirement_hash that doesn't match its own metadata
        → criteria_integrity error (frozen checked before candidate)."""
        candidate = _make_candidate()  # candidate is fully correct
        frozen = _make_frozen_criteria(requirement_hash="wrong_hash")
        _assert_rejected(candidate, frozen, coefficient_code="criteria_integrity")

    def test_candidate_hash_matches_wrong_frozen(self) -> None:
        """Candidate hash == frozen hash == 'wrong_hash', but frozen metadata
        produces a different hash → criteria_integrity on frozen check."""
        wrong_hash = "wrong_hash"
        candidate = _make_candidate(
            content_override={"requirement_hash": wrong_hash},
        )
        # Frozen has correct metadata but wrong hash — metadata produces != hash
        frozen = _make_frozen_criteria(requirement_hash=wrong_hash)
        _assert_rejected(candidate, frozen, coefficient_code="criteria_integrity")


# ── 5. TestRequirementHashDualBinding ─────────────────────────────────────


class TestRequirementHashDualBinding:
    """Tests for the dual-binding requirement_hash check:
    (a) frozen criteria is self-consistent (metadata → hash)
    (b) candidate content matches frozen criteria exactly
    """

    def test_valid_hash_passes(self) -> None:
        """Everything matches — no error raised."""
        candidate = _make_candidate()
        frozen = _make_frozen_criteria()
        command = _make_command()
        _validate_coefficient_candidate(candidate, command, frozen)

    def test_criteria_integrity_failure(self) -> None:
        """Frozen requirement_hash != recomputed from frozen metadata → criteria_integrity."""
        candidate = _make_candidate()
        # Build frozen with correct metadata but wrong hash
        frozen = _make_frozen_criteria(requirement_hash="tampered_hash")
        _assert_rejected(candidate, frozen, coefficient_code="criteria_integrity")

    def test_candidate_mismatch(self) -> None:
        """Candidate content hash != frozen hash (but frozen is correct) → mismatch."""
        candidate = _make_candidate(
            content_override={"requirement_hash": "different_hash"},
        )
        frozen = _make_frozen_criteria()  # correct hash
        _assert_rejected(candidate, frozen, coefficient_code="mismatch")

    def test_both_wrong(self) -> None:
        """Frozen hash wrong AND content hash wrong → criteria_integrity (frozen checked first)."""
        candidate = _make_candidate(
            content_override={"requirement_hash": "wrong_candidate"},
        )
        frozen = _make_frozen_criteria(requirement_hash="wrong_frozen")
        _assert_rejected(candidate, frozen, coefficient_code="criteria_integrity")


# ── 6. TestContextHashFingerprintProof ────────────────────────────────────


class TestContextHashFingerprintProof:
    """Prove that changes to requirement metadata in frozen criteria produce
    different coefficient context content_hash values and different
    orchestration fingerprints.

    Uses _compute_orchestration_fingerprint directly to avoid full service
    execute() calls.
    """

    @staticmethod
    def _content_hash_for_frozen(frozen: FrozenCoefficientResolutionCriteria) -> str:
        """Build a minimal candidate from frozen metadata and return its content_hash."""
        candidate = _make_candidate(
            content_override={
                "requirement_registry_version": frozen.requirement_registry_version,
                "calculator_version_vector": dict(frozen.calculator_version_vector),
                "required_codes": list(frozen.required_codes),
                "requirement_hash": frozen.requirement_hash,
            },
        )
        return candidate.content_hash

    @staticmethod
    def _fingerprint_for_context_hash(context_hash: str) -> str:
        return _compute_orchestration_fingerprint(
            execution_identity_hash="test-identity",
            coefficient_context_hash=context_hash,
            definition_version=_ORCHESTRATION_DEFINITION_VERSION,
            calculator_version_vector=dict(_CV_VECTOR),
            input_mapping_schema_version="1.0.0",
            source_snapshot_schema_version="1.0.0",
        )

    def test_registry_version_change(self) -> None:
        """Changing requirement_registry_version → different context hash + fingerprint."""
        baseline = _make_frozen_criteria()
        changed = _make_frozen_criteria(requirement_registry_version="2.0.0")

        base_hash = self._content_hash_for_frozen(baseline)
        changed_hash = self._content_hash_for_frozen(changed)
        assert base_hash != changed_hash

        base_fp = self._fingerprint_for_context_hash(base_hash)
        changed_fp = self._fingerprint_for_context_hash(changed_hash)
        assert base_fp != changed_fp

    def test_calculator_vector_change(self) -> None:
        """Changing calculator_version_vector → different context hash + fingerprint."""
        baseline = _make_frozen_criteria()
        modified_vec = dict(_CV_VECTOR)
        modified_vec["zone"] = "2.0.0"
        changed = _make_frozen_criteria(calculator_version_vector=modified_vec)

        base_hash = self._content_hash_for_frozen(baseline)
        changed_hash = self._content_hash_for_frozen(changed)
        assert base_hash != changed_hash

        base_fp = self._fingerprint_for_context_hash(base_hash)
        changed_fp = self._fingerprint_for_context_hash(changed_hash)
        assert base_fp != changed_fp

    def test_required_codes_change(self) -> None:
        """Changing required_codes → different context hash + fingerprint."""
        baseline = _make_frozen_criteria()
        extra_code = "extra.custom_code"
        changed_codes = tuple(sorted(list(_REQUIRED_CODES) + [extra_code]))
        changed = _make_frozen_criteria(required_codes=changed_codes)

        base_hash = self._content_hash_for_frozen(baseline)
        changed_hash = self._content_hash_for_frozen(changed)
        assert base_hash != changed_hash

        base_fp = self._fingerprint_for_context_hash(base_hash)
        changed_fp = self._fingerprint_for_context_hash(changed_hash)
        assert base_fp != changed_fp

    def test_requirement_hash_change(self) -> None:
        """Changing requirement_hash → different context hash + fingerprint."""
        baseline = _make_frozen_criteria()
        changed = _make_frozen_criteria(requirement_hash="different_hash_value")

        base_hash = self._content_hash_for_frozen(baseline)
        changed_hash = self._content_hash_for_frozen(changed)
        assert base_hash != changed_hash

        base_fp = self._fingerprint_for_context_hash(base_hash)
        changed_fp = self._fingerprint_for_context_hash(changed_hash)
        assert base_fp != changed_fp
