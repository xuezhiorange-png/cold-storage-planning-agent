"""Coefficient application service — CRUD, state transitions, and resolution.

This service owns the business logic for coefficient definitions and revisions.
Infrastructure implementations (database) extend this with persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from cold_storage.modules.coefficients.domain.exceptions import (
    CoefficientNotFoundError,
    DuplicateCoefficientCodeError,
    SupersedesCrossDefinitionError,
)
from cold_storage.modules.coefficients.domain.models import (
    CoefficientDefinition,
    CoefficientRevision,
    CoefficientSet,
    CoefficientValue,
)


@dataclass
class CoefficientService:
    """In-memory coefficient service with full CRUD and state machine."""

    def __init__(self) -> None:
        self._definitions: dict[str, CoefficientDefinition] = {}
        self._code_index: dict[str, str] = {}  # code -> definition_id
        self._revisions: dict[str, CoefficientRevision] = {}  # revision_id -> revision
        self._revisions_by_definition: dict[str, list[str]] = {}  # def_id -> [rev_ids]

    # ------------------------------------------------------------------
    # Definition CRUD
    # ------------------------------------------------------------------

    def create_definition(
        self,
        code: str,
        name: str,
        description: str,
        category: str,
        canonical_unit: str,
        value_type: str = "decimal",
        scope_type: str = "global",
        is_active: bool = True,
    ) -> CoefficientDefinition:
        """Create a new coefficient definition.

        Raises:
            DuplicateCoefficientCodeError: If code already exists.
        """
        if code in self._code_index:
            raise DuplicateCoefficientCodeError(code)
        definition = CoefficientDefinition(
            code=code,
            name=name,
            description=description,
            category=category,
            canonical_unit=canonical_unit,
            value_type=value_type,
            scope_type=scope_type,
            is_active=is_active,
        )
        self._definitions[definition.id] = definition
        self._code_index[code] = definition.id
        self._revisions_by_definition[definition.id] = []
        return definition

    def list_definitions(
        self,
        category: str | None = None,
        is_active: bool | None = None,
    ) -> list[CoefficientDefinition]:
        """List definitions with optional filters."""
        results = list(self._definitions.values())
        if category is not None:
            results = [d for d in results if d.category == category]
        if is_active is not None:
            results = [d for d in results if d.is_active == is_active]
        return results

    def get_definition(self, definition_id: str) -> CoefficientDefinition:
        """Get a definition by ID.

        Raises:
            CoefficientNotFoundError: If not found.
        """
        if definition_id not in self._definitions:
            raise CoefficientNotFoundError(definition_id)
        return self._definitions[definition_id]

    def get_definition_by_code(self, code: str) -> CoefficientDefinition:
        """Get a definition by code.

        Raises:
            CoefficientNotFoundError: If not found.
        """
        definition_id = self._code_index.get(code)
        if definition_id is None:
            raise CoefficientNotFoundError(code)
        return self._definitions[definition_id]

    # ------------------------------------------------------------------
    # Revision CRUD
    # ------------------------------------------------------------------

    def create_revision(
        self,
        definition_id: str,
        value_decimal: Decimal | None = None,
        value_json: dict[str, object] | None = None,
        unit: str | None = None,
        source_type: str = "demo",
        source_title: str | None = None,
        source_reference: str | None = None,
        source_page: str | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        applicable_product_type: str | None = None,
        applicable_zone_type: str | None = None,
        applicable_process_type: str | None = None,
        supersedes_revision_id: str | None = None,
        change_reason: str | None = None,
        created_by: str = "system",
    ) -> CoefficientRevision:
        """Create a new revision for a coefficient definition.

        Raises:
            CoefficientNotFoundError: If definition_id not found.
            SupersedesCrossDefinitionError: If supersedes_revision_id belongs
                to a different definition.
        """
        definition = self.get_definition(definition_id)
        if unit is None:
            unit = definition.canonical_unit

        # Determine next revision number
        existing = self._revisions_by_definition.get(definition_id, [])
        revision_number = len(existing) + 1

        # Validate supersedes crosses definition boundaries
        if supersedes_revision_id is not None:
            supersedes_rev = self._revisions.get(supersedes_revision_id)
            if supersedes_rev is None:
                raise CoefficientNotFoundError(supersedes_revision_id)
            if supersedes_rev.coefficient_definition_id != definition_id:
                raise SupersedesCrossDefinitionError(
                    supersedes_revision_id,
                    definition_id,
                    supersedes_rev.coefficient_definition_id,
                )

        revision = CoefficientRevision(
            coefficient_definition_id=definition_id,
            revision_number=revision_number,
            unit=unit,
            value_decimal=value_decimal,
            value_json=value_json,
            source_type=source_type,
            source_title=source_title,
            source_reference=source_reference,
            source_page=source_page,
            valid_from=valid_from,
            valid_to=valid_to,
            applicable_product_type=applicable_product_type,
            applicable_zone_type=applicable_zone_type,
            applicable_process_type=applicable_process_type,
            supersedes_revision_id=supersedes_revision_id,
            change_reason=change_reason,
            created_by=created_by,
        )
        self._revisions[revision.id] = revision
        self._revisions_by_definition[definition_id].append(revision.id)
        return revision

    def list_revisions(self, definition_id: str) -> list[CoefficientRevision]:
        """List all revisions for a definition.

        Raises:
            CoefficientNotFoundError: If definition_id not found.
        """
        self.get_definition(definition_id)  # validate exists
        revision_ids = self._revisions_by_definition.get(definition_id, [])
        return [self._revisions[rid] for rid in revision_ids]

    def get_revision(self, definition_id: str, revision_id: str) -> CoefficientRevision:
        """Get a specific revision.

        Raises:
            CoefficientNotFoundError: If not found or doesn't belong to definition.
        """
        self.get_definition(definition_id)  # validate definition exists
        revision = self._revisions.get(revision_id)
        if revision is None:
            raise CoefficientNotFoundError(revision_id)
        if revision.coefficient_definition_id != definition_id:
            raise CoefficientNotFoundError(revision_id)
        return revision

    # ------------------------------------------------------------------
    # State machine transitions
    # ------------------------------------------------------------------

    def submit_revision_for_review(
        self, definition_id: str, revision_id: str, reviewer: str = "system"
    ) -> CoefficientRevision:
        """Submit a draft revision for review (draft → unverified).

        Also transitions draft → reviewed if reviewer is specified.
        """
        revision = self.get_revision(definition_id, revision_id)
        revision.transition_to("unverified")
        return revision

    def mark_revision_reviewed(
        self, definition_id: str, revision_id: str, reviewer: str = "system"
    ) -> CoefficientRevision:
        """Mark a revision as reviewed (draft/unverified → reviewed)."""
        revision = self.get_revision(definition_id, revision_id)
        revision.reviewed_by = reviewer
        revision.transition_to("reviewed")
        return revision

    def approve_revision(
        self, definition_id: str, revision_id: str, approver: str = "system"
    ) -> CoefficientRevision:
        """Approve a reviewed revision (reviewed → approved)."""
        revision = self.get_revision(definition_id, revision_id)
        revision.approved_by = approver
        revision.transition_to("approved")
        return revision

    def withdraw_revision(
        self, definition_id: str, revision_id: str, actor: str = "system"
    ) -> CoefficientRevision:
        """Withdraw an approved revision (approved → withdrawn)."""
        revision = self.get_revision(definition_id, revision_id)
        revision.transition_to("withdrawn")
        return revision

    # ------------------------------------------------------------------
    # Resolution (for calculations)
    # ------------------------------------------------------------------

    def resolve_coefficient_set(
        self,
        codes: list[str] | None = None,
        product_type: str | None = None,
        zone_type: str | None = None,
        process_type: str | None = None,
    ) -> CoefficientSet:
        """Resolve the latest approved values for requested coefficients.

        If codes is None, resolve all active definitions.
        Only approved revisions are included.
        """
        if codes is None:
            definitions = [d for d in self._definitions.values() if d.is_active]
            codes = [d.code for d in definitions]
        else:
            definitions = []
            for code in codes:
                def_id = self._code_index.get(code)
                if def_id is not None:
                    definitions.append(self._definitions[def_id])

        items: dict[str, CoefficientValue] = {}
        for definition in definitions:
            value = self._resolve_single(
                definition,
                product_type=product_type,
                zone_type=zone_type,
                process_type=process_type,
            )
            if value is not None:
                items[definition.code] = value

        return CoefficientSet(items=items)

    def _resolve_single(
        self,
        definition: CoefficientDefinition,
        product_type: str | None = None,
        zone_type: str | None = None,
        process_type: str | None = None,
    ) -> CoefficientValue | None:
        """Resolve the latest approved value for a single definition."""
        revision_ids = self._revisions_by_definition.get(definition.id, [])
        # Find the latest approved revision, preferring higher revision numbers
        approved_revisions = []
        for rid in revision_ids:
            rev = self._revisions[rid]
            if rev.status == "approved" and rev.has_value():
                # Check applicability filters
                if (
                    product_type
                    and rev.applicable_product_type
                    and rev.applicable_product_type != product_type
                ):
                    continue
                if zone_type and rev.applicable_zone_type and rev.applicable_zone_type != zone_type:
                    continue
                if (
                    process_type
                    and rev.applicable_process_type
                    and rev.applicable_process_type != process_type
                ):
                    continue
                approved_revisions.append(rev)

        if not approved_revisions:
            return None

        # Get the latest approved revision
        latest = max(approved_revisions, key=lambda r: r.revision_number)

        decimal_value = latest.value_decimal if latest.value_decimal is not None else Decimal("0")

        return CoefficientValue(
            code=definition.code,
            revision_id=latest.id,
            revision_number=latest.revision_number,
            value=decimal_value,
            unit=latest.unit,
            status=latest.status,
            source_type=latest.source_type,
            source_reference=latest.source_reference,
            requires_review=latest.source_type == "demo",
        )

    def create_revision_from_approved(
        self,
        definition_id: str,
        value_decimal: Decimal | None = None,
        value_json: dict[str, object] | None = None,
        change_reason: str = "",
        created_by: str = "system",
    ) -> CoefficientRevision:
        """Create a new draft revision from the latest approved revision.

        Finds the latest approved revision and creates a new draft
        that supersedes it.
        """
        revision_ids = self._revisions_by_definition.get(definition_id, [])
        approved = [
            self._revisions[rid]
            for rid in revision_ids
            if self._revisions[rid].status == "approved"
        ]
        if not approved:
            raise CoefficientNotFoundError(f"No approved revision for {definition_id}")

        latest = max(approved, key=lambda r: r.revision_number)
        return self.create_revision(
            definition_id=definition_id,
            value_decimal=value_decimal,
            value_json=value_json,
            source_type=latest.source_type,
            source_title=latest.source_title,
            source_reference=latest.source_reference,
            source_page=latest.source_page,
            valid_from=latest.valid_from,
            valid_to=latest.valid_to,
            applicable_product_type=latest.applicable_product_type,
            applicable_zone_type=latest.applicable_zone_type,
            applicable_process_type=latest.applicable_process_type,
            supersedes_revision_id=latest.id,
            change_reason=change_reason,
            created_by=created_by,
        )

    # ------------------------------------------------------------------
    # Seed data helper
    # ------------------------------------------------------------------

    def seed_demo_coefficients(self) -> list[CoefficientRevision]:
        """Seed the initial demo coefficients from the inventory."""
        seed_data = [
            (
                "area.circulation_allowance_ratio",
                "Circulation Allowance Ratio",
                "1.15",
                "ratio",
                "area",
            ),
            ("area.auxiliary_area_ratio", "Auxiliary Area Ratio", "1.10", "ratio", "area"),
            ("pallet.net_load_kg", "Net Pallet Load", "400", "kg", "pallet"),
            ("pallet.turnover_factor", "Pallet Turnover Factor", "1.2", "ratio", "pallet"),
            ("power.design_margin_ratio", "Design Margin Ratio", "1.15", "ratio", "power"),
            ("power.standby_ratio", "Standby Ratio", "1.10", "ratio", "power"),
            ("investment.building_unit_cost", "Building Unit Cost", "900", "CNY/m²", "investment"),
            (
                "investment.refrigeration_equipment_ratio",
                "Refrigeration Equipment Ratio",
                "1400",
                "CNY/m²",
                "investment",
            ),
            (
                "investment.electrical_installation_ratio",
                "Electrical Installation Ratio",
                "650",
                "CNY/m²",
                "investment",
            ),
            (
                "investment.other_expenses_ratio",
                "Other Expenses Ratio",
                "0.05",
                "ratio",
                "investment",
            ),
        ]

        created: list[CoefficientRevision] = []
        for code, name, value, unit, category in seed_data:
            definition = self.create_definition(
                code=code,
                name=name,
                description=f"Demo coefficient: {name}",
                category=category,
                canonical_unit=unit,
            )
            revision = self.create_revision(
                definition_id=definition.id,
                value_decimal=Decimal(value),
                unit=unit,
                source_type="demo",
                source_title="Demo seed data",
                source_reference="Initial seed from coefficient inventory",
                created_by="seed",
            )
            # Move to unverified status to match requirements
            revision.transition_to("unverified")
            created.append(revision)
        return created
