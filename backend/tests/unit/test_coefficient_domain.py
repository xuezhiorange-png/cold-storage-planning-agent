"""Tests for the coefficient registry domain models.

Covers:
- CoefficientDefinition creation and validation
- CoefficientRevision state machine and immutability
- CoefficientValue and CoefficientSet immutability
- Edge cases and error conditions
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cold_storage.modules.coefficients.domain.exceptions import (
    InvalidRevisionTransitionError,
    RevisionImmutabilityError,
)
from cold_storage.modules.coefficients.domain.models import (
    ALL_REVISION_STATUSES,
    ALL_SOURCE_TYPES,
    ALL_VALUE_TYPES,
    SCHEMA_VERSION,
    CoefficientDefinition,
    CoefficientRevision,
    CoefficientSet,
    CoefficientValue,
    validate_revision_transition,
)

# ===========================================================================
# 1. CoefficientDefinition tests
# ===========================================================================


class TestCoefficientDefinition:
    def test_create_definition(self) -> None:
        d = CoefficientDefinition(
            code="area.circulation_ratio",
            name="Circulation Ratio",
            description="Test coefficient",
            category="area",
            canonical_unit="ratio",
        )
        assert d.code == "area.circulation_ratio"
        assert d.is_active is True
        assert d.value_type == "decimal"
        assert d.scope_type == "global"
        assert d.id  # auto-generated UUID

    def test_definition_custom_fields(self) -> None:
        d = CoefficientDefinition(
            code="test.code",
            name="Test",
            description="Desc",
            category="power",
            canonical_unit="kW",
            value_type="json",
            scope_type="zone",
            is_active=False,
        )
        assert d.value_type == "json"
        assert d.scope_type == "zone"
        assert d.is_active is False

    def test_definition_invalid_value_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid value_type"):
            CoefficientDefinition(
                code="test",
                name="Test",
                description="Desc",
                category="area",
                canonical_unit="m",
                value_type="invalid",
            )

    def test_definition_invalid_scope_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid scope_type"):
            CoefficientDefinition(
                code="test",
                name="Test",
                description="Desc",
                category="area",
                canonical_unit="m",
                scope_type="invalid",
            )

    def test_definition_timestamps(self) -> None:
        d = CoefficientDefinition(
            code="t", name="T", description="D", category="c", canonical_unit="u"
        )
        assert d.created_at is not None
        assert d.updated_at is not None


# ===========================================================================
# 2. CoefficientRevision state machine tests
# ===========================================================================


class TestCoefficientRevisionStateMachine:
    def _make_revision(self, status: str = "draft") -> CoefficientRevision:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            value_decimal=Decimal("1.5"),
            status="draft",
        )
        # If we want a different status, transition there
        if status == "unverified":
            rev.transition_to("unverified")
        elif status == "reviewed":
            rev.transition_to("unverified")
            rev.transition_to("reviewed")
        elif status == "approved":
            rev.transition_to("unverified")
            rev.transition_to("reviewed")
            rev.transition_to("approved")
        elif status == "withdrawn":
            rev.transition_to("unverified")
            rev.transition_to("reviewed")
            rev.transition_to("approved")
            rev.transition_to("withdrawn")
        return rev

    def test_new_revision_starts_in_draft(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
        )
        assert rev.status == "draft"

    def test_valid_transition_draft_to_unverified(self) -> None:
        rev = self._make_revision("draft")
        rev.transition_to("unverified")
        assert rev.status == "unverified"

    def test_valid_transition_draft_to_reviewed(self) -> None:
        rev = self._make_revision("draft")
        rev.transition_to("reviewed")
        assert rev.status == "reviewed"
        assert rev.reviewed_at is not None

    def test_valid_transition_unverified_to_reviewed(self) -> None:
        rev = self._make_revision("unverified")
        rev.transition_to("reviewed")
        assert rev.status == "reviewed"

    def test_valid_transition_reviewed_to_approved(self) -> None:
        rev = self._make_revision("reviewed")
        rev.transition_to("approved")
        assert rev.status == "approved"
        assert rev.approved_at is not None
        assert rev.approved_by is not None

    def test_valid_transition_approved_to_withdrawn(self) -> None:
        rev = self._make_revision("approved")
        rev.transition_to("withdrawn")
        assert rev.status == "withdrawn"
        assert rev.withdrawn_at is not None

    def test_invalid_transition_draft_to_approved(self) -> None:
        rev = self._make_revision("draft")
        with pytest.raises(InvalidRevisionTransitionError):
            rev.transition_to("approved")

    def test_invalid_transition_reviewed_to_draft(self) -> None:
        rev = self._make_revision("reviewed")
        with pytest.raises(InvalidRevisionTransitionError):
            rev.transition_to("draft")

    def test_invalid_transition_unverified_to_withdrawn(self) -> None:
        rev = self._make_revision("unverified")
        with pytest.raises(InvalidRevisionTransitionError):
            rev.transition_to("withdrawn")

    def test_invalid_transition_approved_to_reviewed(self) -> None:
        rev = self._make_revision("approved")
        with pytest.raises(RevisionImmutabilityError):
            rev.transition_to("reviewed")


# ===========================================================================
# 3. CoefficientRevision immutability tests
# ===========================================================================


class TestCoefficientRevisionImmutability:
    def test_approved_revision_is_locked(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            value_decimal=Decimal("1.5"),
            status="approved",
        )
        assert rev.is_locked is True

    def test_withdrawn_revision_is_locked(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            value_decimal=Decimal("1.5"),
            status="withdrawn",
        )
        assert rev.is_locked is True

    def test_draft_revision_is_not_locked(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            status="draft",
        )
        assert rev.is_locked is False

    def test_approved_revision_cannot_transition(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            value_decimal=Decimal("1.5"),
            status="approved",
        )
        with pytest.raises(RevisionImmutabilityError):
            rev.transition_to("draft")  # approved → draft is invalid

    def test_withdrawn_revision_cannot_transition(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            value_decimal=Decimal("1.5"),
            status="withdrawn",
        )
        with pytest.raises(RevisionImmutabilityError):
            rev.transition_to("draft")

    def test_assert_not_locked_passes_for_draft(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            status="draft",
        )
        rev.assert_not_locked("modify")  # should not raise

    def test_assert_not_locked_raises_for_approved(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            value_decimal=Decimal("1.5"),
            status="approved",
        )
        with pytest.raises(RevisionImmutabilityError):
            rev.assert_not_locked("modify")


# ===========================================================================
# 4. CoefficientRevision value access tests
# ===========================================================================


class TestCoefficientRevisionValues:
    def test_has_value_decimal(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            value_decimal=Decimal("1.5"),
        )
        assert rev.has_value() is True
        assert rev.get_decimal_value() == Decimal("1.5")

    def test_has_value_json(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            value_json={"key": "value"},
        )
        assert rev.has_value() is True
        assert rev.get_json_value() == {"key": "value"}

    def test_has_value_none(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
        )
        assert rev.has_value() is False

    def test_get_decimal_value_none_raises(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
        )
        with pytest.raises(ValueError, match="no decimal value"):
            rev.get_decimal_value()

    def test_get_json_value_none_raises(self) -> None:
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
        )
        with pytest.raises(ValueError, match="no JSON value"):
            rev.get_json_value()

    def test_json_value_is_copy(self) -> None:
        original = {"key": "value"}
        rev = CoefficientRevision(
            coefficient_definition_id="def-1",
            revision_number=1,
            unit="ratio",
            value_json=original,
        )
        returned = rev.get_json_value()
        returned["key"] = "modified"
        assert rev.value_json == original  # original not modified


# ===========================================================================
# 5. CoefficientValue and CoefficientSet tests
# ===========================================================================


class TestCoefficientValue:
    def test_create_value(self) -> None:
        v = CoefficientValue(
            code="test.code",
            revision_id="rev-1",
            revision_number=1,
            value=Decimal("1.5"),
            unit="ratio",
            status="approved",
            source_type="demo",
            source_reference=None,
            requires_review=True,
        )
        assert v.code == "test.code"
        assert v.value == Decimal("1.5")
        assert v.requires_review is True

    def test_value_is_frozen(self) -> None:
        v = CoefficientValue(
            code="test",
            revision_id="r1",
            revision_number=1,
            value=Decimal("1"),
            unit="u",
            status="approved",
            source_type="demo",
            source_reference=None,
            requires_review=False,
        )
        with pytest.raises(AttributeError):
            v.code = "modified"  # type: ignore[misc]


class TestCoefficientSet:
    def _make_set(self) -> CoefficientSet:
        items = {
            "area.ratio": CoefficientValue(
                code="area.ratio",
                revision_id="r1",
                revision_number=1,
                value=Decimal("1.15"),
                unit="ratio",
                status="approved",
                source_type="demo",
                source_reference=None,
                requires_review=True,
            ),
        }
        return CoefficientSet(items=items)

    def test_set_length(self) -> None:
        s = self._make_set()
        assert len(s) == 1

    def test_set_contains(self) -> None:
        s = self._make_set()
        assert "area.ratio" in s
        assert "missing" not in s

    def test_set_get(self) -> None:
        s = self._make_set()
        v = s.get("area.ratio")
        assert v is not None
        assert v.value == Decimal("1.15")
        assert s.get("missing") is None

    def test_set_is_frozen(self) -> None:
        s = self._make_set()
        with pytest.raises(AttributeError):
            s.items = {}  # type: ignore[misc]

    def test_set_schema_version(self) -> None:
        s = self._make_set()
        assert s.schema_version == SCHEMA_VERSION

    def test_empty_set(self) -> None:
        s = CoefficientSet(items={})
        assert len(s) == 0
        assert "any" not in s


# ===========================================================================
# 6. State machine validation function tests
# ===========================================================================


class TestValidateRevisionTransition:
    def test_valid_transitions(self) -> None:
        valid = [
            ("draft", "unverified"),
            ("draft", "reviewed"),
            ("unverified", "reviewed"),
            ("reviewed", "approved"),
            ("approved", "withdrawn"),
        ]
        for from_s, to_s in valid:
            validate_revision_transition(from_s, to_s)  # should not raise

    def test_invalid_transitions(self) -> None:
        invalid = [
            ("draft", "approved"),
            ("draft", "withdrawn"),
            ("unverified", "approved"),
            ("unverified", "draft"),
            ("reviewed", "draft"),
            ("reviewed", "unverified"),
            ("approved", "reviewed"),
            ("approved", "draft"),
            ("withdrawn", "draft"),
            ("withdrawn", "approved"),
        ]
        for from_s, to_s in invalid:
            with pytest.raises(InvalidRevisionTransitionError):
                validate_revision_transition(from_s, to_s)


# ===========================================================================
# 7. All constants validation
# ===========================================================================


class TestConstants:
    def test_all_statuses_covered(self) -> None:
        assert "draft" in ALL_REVISION_STATUSES
        assert "unverified" in ALL_REVISION_STATUSES
        assert "reviewed" in ALL_REVISION_STATUSES
        assert "approved" in ALL_REVISION_STATUSES
        assert "withdrawn" in ALL_REVISION_STATUSES
        assert len(ALL_REVISION_STATUSES) == 5

    def test_all_source_types_covered(self) -> None:
        assert "demo" in ALL_SOURCE_TYPES
        assert "standard" in ALL_SOURCE_TYPES
        assert "book" in ALL_SOURCE_TYPES
        assert "manufacturer" in ALL_SOURCE_TYPES
        assert "enterprise_standard" in ALL_SOURCE_TYPES
        assert "historical_project" in ALL_SOURCE_TYPES
        assert "engineering_judgement" in ALL_SOURCE_TYPES
        assert "unknown" in ALL_SOURCE_TYPES

    def test_value_types(self) -> None:
        assert {"decimal", "json"} == ALL_VALUE_TYPES
