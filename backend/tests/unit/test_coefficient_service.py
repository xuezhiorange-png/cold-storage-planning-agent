"""Tests for the coefficient application service.

Covers:
- Definition CRUD operations
- Revision CRUD operations
- State transitions
- Conflict detection
- Resolution
- Seed data
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cold_storage.modules.coefficients.application.service import CoefficientService
from cold_storage.modules.coefficients.domain.exceptions import (
    CoefficientNotFoundError,
    DuplicateCoefficientCodeError,
    InvalidRevisionTransitionError,
    RevisionImmutabilityError,
    SupersedesCrossDefinitionError,
)


@pytest.fixture()
def service() -> CoefficientService:
    return CoefficientService()


@pytest.fixture()
def service_with_defs(service: CoefficientService) -> CoefficientService:
    """Create service with two definitions."""
    service.create_definition(
        code="area.ratio",
        name="Area Ratio",
        description="Test",
        category="area",
        canonical_unit="ratio",
    )
    service.create_definition(
        code="power.kw",
        name="Power KW",
        description="Test",
        category="power",
        canonical_unit="kW",
    )
    return service


# ===========================================================================
# 1. Definition CRUD tests
# ===========================================================================


class TestDefinitionCRUD:
    def test_create_definition(self, service: CoefficientService) -> None:
        d = service.create_definition(
            code="test.code",
            name="Test",
            description="Desc",
            category="area",
            canonical_unit="ratio",
        )
        assert d.code == "test.code"
        assert d.id

    def test_create_duplicate_code_raises(self, service_with_defs: CoefficientService) -> None:
        with pytest.raises(DuplicateCoefficientCodeError):
            service_with_defs.create_definition(
                code="area.ratio",
                name="Duplicate",
                description="Desc",
                category="area",
                canonical_unit="ratio",
            )

    def test_list_definitions(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        assert len(defs) == 2

    def test_list_definitions_filter_category(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions(category="area")
        assert len(defs) == 1
        assert defs[0].code == "area.ratio"

    def test_list_definitions_filter_active(self, service_with_defs: CoefficientService) -> None:
        # Deactivate one
        defs = service_with_defs.list_definitions()
        defs[0].is_active = False
        active = service_with_defs.list_definitions(is_active=True)
        assert len(active) == 1

    def test_get_definition(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        d = service_with_defs.get_definition(defs[0].id)
        assert d.code == defs[0].code

    def test_get_definition_not_found(self, service: CoefficientService) -> None:
        with pytest.raises(CoefficientNotFoundError):
            service.get_definition("nonexistent")

    def test_get_definition_by_code(self, service_with_defs: CoefficientService) -> None:
        d = service_with_defs.get_definition_by_code("area.ratio")
        assert d.code == "area.ratio"

    def test_get_definition_by_code_not_found(self, service: CoefficientService) -> None:
        with pytest.raises(CoefficientNotFoundError):
            service.get_definition_by_code("nonexistent")


# ===========================================================================
# 2. Revision CRUD tests
# ===========================================================================


class TestRevisionCRUD:
    def test_create_revision(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id,
            value_decimal=Decimal("1.15"),
        )
        assert rev.revision_number == 1
        assert rev.value_decimal == Decimal("1.15")
        assert rev.status == "draft"

    def test_create_revision_def_not_found(self, service: CoefficientService) -> None:
        with pytest.raises(CoefficientNotFoundError):
            service.create_revision(
                definition_id="nonexistent",
                value_decimal=Decimal("1.0"),
            )

    def test_create_multiple_revisions(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev1 = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        rev2 = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.2")
        )
        assert rev1.revision_number == 1
        assert rev2.revision_number == 2

    def test_list_revisions(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        service_with_defs.create_revision(definition_id=defs[0].id, value_decimal=Decimal("1.1"))
        revisions = service_with_defs.list_revisions(defs[0].id)
        assert len(revisions) == 1

    def test_list_revisions_not_found(self, service: CoefficientService) -> None:
        with pytest.raises(CoefficientNotFoundError):
            service.list_revisions("nonexistent")

    def test_get_revision(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        fetched = service_with_defs.get_revision(defs[0].id, rev.id)
        assert fetched.revision_number == 1

    def test_get_revision_wrong_definition(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        with pytest.raises(CoefficientNotFoundError):
            service_with_defs.get_revision(defs[1].id, rev.id)

    def test_supersedes_cross_definition_raises(
        self, service_with_defs: CoefficientService
    ) -> None:
        defs = service_with_defs.list_definitions()
        rev1 = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        with pytest.raises(SupersedesCrossDefinitionError):
            service_with_defs.create_revision(
                definition_id=defs[1].id,
                value_decimal=Decimal("1.2"),
                supersedes_revision_id=rev1.id,
            )


# ===========================================================================
# 3. State transition tests
# ===========================================================================


class TestStateTransitions:
    def test_submit_for_review(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        result = service_with_defs.submit_revision_for_review(defs[0].id, rev.id)
        assert result.status == "unverified"

    def test_mark_reviewed(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        service_with_defs.mark_revision_reviewed(defs[0].id, rev.id, reviewer="reviewer1")
        result = service_with_defs.get_revision(defs[0].id, rev.id)
        assert result.status == "reviewed"
        assert result.reviewed_by == "reviewer1"

    def test_approve(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        service_with_defs.mark_revision_reviewed(defs[0].id, rev.id)
        result = service_with_defs.approve_revision(defs[0].id, rev.id, approver="approver1")
        assert result.status == "approved"
        assert result.approved_by == "approver1"

    def test_withdraw(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        service_with_defs.mark_revision_reviewed(defs[0].id, rev.id)
        service_with_defs.approve_revision(defs[0].id, rev.id)
        result = service_with_defs.withdraw_revision(defs[0].id, rev.id)
        assert result.status == "withdrawn"

    def test_invalid_transition_raises(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        with pytest.raises(InvalidRevisionTransitionError):
            service_with_defs.approve_revision(defs[0].id, rev.id)  # draft -> approved

    def test_approved_immutable(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        service_with_defs.mark_revision_reviewed(defs[0].id, rev.id)
        service_with_defs.approve_revision(defs[0].id, rev.id)
        with pytest.raises(RevisionImmutabilityError):
            service_with_defs.submit_revision_for_review(defs[0].id, rev.id)


# ===========================================================================
# 4. Resolution tests
# ===========================================================================


class TestResolution:
    def test_resolve_empty(self, service: CoefficientService) -> None:
        result = service.resolve_coefficient_set()
        assert len(result) == 0

    def test_resolve_only_approved(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        # Create and approve one revision
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.15")
        )
        service_with_defs.mark_revision_reviewed(defs[0].id, rev.id)
        service_with_defs.approve_revision(defs[0].id, rev.id)

        result = service_with_defs.resolve_coefficient_set()
        assert len(result) == 1
        assert "area.ratio" in result

    def test_resolve_unapproved_not_included(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        service_with_defs.create_revision(definition_id=defs[0].id, value_decimal=Decimal("1.15"))
        result = service_with_defs.resolve_coefficient_set()
        assert len(result) == 0

    def test_resolve_specific_codes(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        for d in defs:
            rev = service_with_defs.create_revision(
                definition_id=d.id, value_decimal=Decimal("1.0")
            )
            service_with_defs.mark_revision_reviewed(d.id, rev.id)
            service_with_defs.approve_revision(d.id, rev.id)

        result = service_with_defs.resolve_coefficient_set(codes=["area.ratio"])
        assert len(result) == 1
        assert "area.ratio" in result
        assert "power.kw" not in result

    def test_resolve_latest_approved(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        # Create two revisions and approve both
        rev1 = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        service_with_defs.mark_revision_reviewed(defs[0].id, rev1.id)
        service_with_defs.approve_revision(defs[0].id, rev1.id)

        rev2 = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.2")
        )
        service_with_defs.mark_revision_reviewed(defs[0].id, rev2.id)
        service_with_defs.approve_revision(defs[0].id, rev2.id)

        result = service_with_defs.resolve_coefficient_set(codes=["area.ratio"])
        value = result.get("area.ratio")
        assert value is not None
        assert value.value == Decimal("1.2")
        assert value.revision_number == 2


# ===========================================================================
# 5. create_revision_from_approved tests
# ===========================================================================


class TestCreateRevisionFromApproved:
    def test_creates_new_draft(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        rev = service_with_defs.create_revision(
            definition_id=defs[0].id, value_decimal=Decimal("1.1")
        )
        service_with_defs.mark_revision_reviewed(defs[0].id, rev.id)
        service_with_defs.approve_revision(defs[0].id, rev.id)

        new_rev = service_with_defs.create_revision_from_approved(
            definition_id=defs[0].id,
            value_decimal=Decimal("1.2"),
            change_reason="Updated value",
        )
        assert new_rev.status == "draft"
        assert new_rev.value_decimal == Decimal("1.2")
        assert new_rev.supersedes_revision_id == rev.id

    def test_no_approved_raises(self, service_with_defs: CoefficientService) -> None:
        defs = service_with_defs.list_definitions()
        with pytest.raises(CoefficientNotFoundError):
            service_with_defs.create_revision_from_approved(
                definition_id=defs[0].id,
                value_decimal=Decimal("1.2"),
            )


# ===========================================================================
# 6. Seed data tests
# ===========================================================================


class TestSeedData:
    def test_seed_creates_definitions(self, service: CoefficientService) -> None:
        revisions = service.seed_demo_coefficients()
        assert len(revisions) == 10
        definitions = service.list_definitions()
        assert len(definitions) == 10

    def test_seed_coefficients_are_unverified(self, service: CoefficientService) -> None:
        service.seed_demo_coefficients()
        for definition in service.list_definitions():
            revisions = service.list_revisions(definition.id)
            assert len(revisions) == 1
            assert revisions[0].status == "unverified"
            assert revisions[0].source_type == "demo"

    def test_seed_specific_codes(self, service: CoefficientService) -> None:
        service.seed_demo_coefficients()
        d = service.get_definition_by_code("area.circulation_allowance_ratio")
        assert d.code == "area.circulation_allowance_ratio"
        revisions = service.list_revisions(d.id)
        assert revisions[0].value_decimal == Decimal("1.15")

    def test_seed_investment_coefficients(self, service: CoefficientService) -> None:
        service.seed_demo_coefficients()
        d = service.get_definition_by_code("investment.building_unit_cost")
        revisions = service.list_revisions(d.id)
        assert revisions[0].value_decimal == Decimal("900")
