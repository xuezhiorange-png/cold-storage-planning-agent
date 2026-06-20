"""Database-backed coefficient service implementation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from cold_storage.modules.coefficients.application.service import CoefficientService
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
from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)


class DatabaseCoefficientService(CoefficientService):
    """Database-backed coefficient service with SQLAlchemy persistence."""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine
        self.session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    # ------------------------------------------------------------------
    # Definition CRUD (override in-memory with database)
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
        """Create a new coefficient definition in the database."""
        with self.session_factory() as session:
            # Check for duplicate code
            existing = session.scalar(
                select(CoefficientDefinitionRecord).where(CoefficientDefinitionRecord.code == code)
            )
            if existing is not None:
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
            record = self._definition_to_record(definition)
            session.add(record)
            session.commit()

            # Update in-memory cache
            self._definitions[definition.id] = definition
            self._code_index[code] = definition.id
            self._revisions_by_definition[definition.id] = []
            return definition

    def list_definitions(
        self,
        category: str | None = None,
        is_active: bool | None = None,
    ) -> list[CoefficientDefinition]:
        """List definitions with optional filters from database."""
        with self.session_factory() as session:
            query = select(CoefficientDefinitionRecord).order_by(CoefficientDefinitionRecord.code)
            if category is not None:
                query = query.where(CoefficientDefinitionRecord.category == category)
            if is_active is not None:
                query = query.where(CoefficientDefinitionRecord.is_active == is_active)
            records = session.scalars(query).all()
            return [self._definition_from_record(r) for r in records]

    def get_definition(self, definition_id: str) -> CoefficientDefinition:
        """Get a definition by ID from database."""
        with self.session_factory() as session:
            record = session.get(CoefficientDefinitionRecord, definition_id)
            if record is None:
                raise CoefficientNotFoundError(definition_id)
            return self._definition_from_record(record)

    def get_definition_by_code(self, code: str) -> CoefficientDefinition:
        """Get a definition by code from database."""
        with self.session_factory() as session:
            record = session.scalar(
                select(CoefficientDefinitionRecord).where(CoefficientDefinitionRecord.code == code)
            )
            if record is None:
                raise CoefficientNotFoundError(code)
            return self._definition_from_record(record)

    # ------------------------------------------------------------------
    # Revision CRUD (override in-memory with database)
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
        """Create a new revision in the database."""
        with self.session_factory() as session:
            # Validate definition exists
            def_record = session.get(CoefficientDefinitionRecord, definition_id)
            if def_record is None:
                raise CoefficientNotFoundError(definition_id)

            if unit is None:
                unit = def_record.canonical_unit

            # Get next revision number
            existing_revisions = session.scalars(
                select(CoefficientRevisionRecord).where(
                    CoefficientRevisionRecord.coefficient_definition_id == definition_id
                )
            ).all()
            revision_number = len(existing_revisions) + 1

            # Validate supersedes
            if supersedes_revision_id is not None:
                supersedes_record = session.get(CoefficientRevisionRecord, supersedes_revision_id)
                if supersedes_record is None:
                    raise CoefficientNotFoundError(supersedes_revision_id)
                if supersedes_record.coefficient_definition_id != definition_id:
                    raise SupersedesCrossDefinitionError(
                        supersedes_revision_id,
                        definition_id,
                        supersedes_record.coefficient_definition_id,
                    )

            value_decimal_str = str(value_decimal) if value_decimal is not None else None
            value_json_str = json.dumps(value_json) if value_json is not None else None

            now = datetime.now(UTC)
            record = CoefficientRevisionRecord(
                id=str(__import__("uuid").uuid4()),
                coefficient_definition_id=definition_id,
                revision_number=revision_number,
                value_decimal=value_decimal_str,
                value_json=value_json_str,
                unit=unit,
                status="draft",
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
                created_at=now,
            )
            session.add(record)
            session.commit()

            return self._revision_from_record(record)

    def list_revisions(self, definition_id: str) -> list[CoefficientRevision]:
        """List all revisions for a definition from database."""
        with self.session_factory() as session:
            # Validate definition exists
            def_record = session.get(CoefficientDefinitionRecord, definition_id)
            if def_record is None:
                raise CoefficientNotFoundError(definition_id)

            records = session.scalars(
                select(CoefficientRevisionRecord)
                .where(CoefficientRevisionRecord.coefficient_definition_id == definition_id)
                .order_by(CoefficientRevisionRecord.revision_number)
            ).all()
            return [self._revision_from_record(r) for r in records]

    def get_revision(self, definition_id: str, revision_id: str) -> CoefficientRevision:
        """Get a specific revision from database."""
        with self.session_factory() as session:
            # Validate definition exists
            def_record = session.get(CoefficientDefinitionRecord, definition_id)
            if def_record is None:
                raise CoefficientNotFoundError(definition_id)

            record = session.get(CoefficientRevisionRecord, revision_id)
            if record is None:
                raise CoefficientNotFoundError(revision_id)
            if record.coefficient_definition_id != definition_id:
                raise CoefficientNotFoundError(revision_id)
            return self._revision_from_record(record)

    # ------------------------------------------------------------------
    # State transitions (update database)
    # ------------------------------------------------------------------

    def submit_revision_for_review(
        self, definition_id: str, revision_id: str, reviewer: str = "system"
    ) -> CoefficientRevision:
        """Submit a draft revision for review (draft → unverified)."""
        with self.session_factory() as session:
            record = self._get_revision_record(session, definition_id, revision_id)
            self._validate_not_locked(record)
            self._validate_transition(record.status, "unverified")
            record.status = "unverified"
            session.commit()
            return self._revision_from_record(record)

    def mark_revision_reviewed(
        self, definition_id: str, revision_id: str, reviewer: str = "system"
    ) -> CoefficientRevision:
        """Mark a revision as reviewed (draft/unverified → reviewed)."""
        with self.session_factory() as session:
            record = self._get_revision_record(session, definition_id, revision_id)
            self._validate_not_locked(record)
            self._validate_transition(record.status, "reviewed")
            record.status = "reviewed"
            record.reviewed_by = reviewer
            record.reviewed_at = datetime.now(UTC)
            session.commit()
            return self._revision_from_record(record)

    def approve_revision(
        self, definition_id: str, revision_id: str, approver: str = "system"
    ) -> CoefficientRevision:
        """Approve a reviewed revision (reviewed → approved)."""
        with self.session_factory() as session:
            record = self._get_revision_record(session, definition_id, revision_id)
            self._validate_not_locked(record)
            self._validate_transition(record.status, "approved")
            record.status = "approved"
            record.approved_by = approver
            record.approved_at = datetime.now(UTC)
            session.commit()
            return self._revision_from_record(record)

    def withdraw_revision(
        self, definition_id: str, revision_id: str, actor: str = "system"
    ) -> CoefficientRevision:
        """Withdraw an approved revision (approved → withdrawn)."""
        with self.session_factory() as session:
            record = self._get_revision_record(session, definition_id, revision_id)
            self._validate_not_locked(record, target_status="withdrawn")
            self._validate_transition(record.status, "withdrawn")
            record.status = "withdrawn"
            record.withdrawn_at = datetime.now(UTC)
            session.commit()
            return self._revision_from_record(record)

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
        """Resolve the latest approved values for requested coefficients."""
        with self.session_factory() as session:
            if codes is None:
                definitions = session.scalars(
                    select(CoefficientDefinitionRecord).where(
                        CoefficientDefinitionRecord.is_active == True  # noqa: E712
                    )
                ).all()
            else:
                definitions = []
                for code in codes:
                    record = session.scalar(
                        select(CoefficientDefinitionRecord).where(
                            CoefficientDefinitionRecord.code == code
                        )
                    )
                    if record is not None:
                        definitions.append(record)

            items: dict[str, CoefficientValue] = {}
            for def_record in definitions:
                revisions = session.scalars(
                    select(CoefficientRevisionRecord)
                    .where(
                        CoefficientRevisionRecord.coefficient_definition_id == def_record.id,
                        CoefficientRevisionRecord.status == "approved",
                    )
                    .order_by(CoefficientRevisionRecord.revision_number.desc())
                ).all()

                for rev_record in revisions:
                    # Check applicability filters
                    if (
                        product_type
                        and rev_record.applicable_product_type
                        and rev_record.applicable_product_type != product_type
                    ):
                        continue
                    if (
                        zone_type
                        and rev_record.applicable_zone_type
                        and rev_record.applicable_zone_type != zone_type
                    ):
                        continue
                    if (
                        process_type
                        and rev_record.applicable_process_type
                        and rev_record.applicable_process_type != process_type
                    ):
                        continue

                    if rev_record.value_decimal is not None:
                        try:
                            decimal_value = Decimal(rev_record.value_decimal)
                        except (InvalidOperation, ValueError):
                            decimal_value = Decimal("0")
                    else:
                        decimal_value = Decimal("0")

                    items[def_record.code] = CoefficientValue(
                        code=def_record.code,
                        revision_id=rev_record.id,
                        revision_number=rev_record.revision_number,
                        value=decimal_value,
                        unit=rev_record.unit,
                        status=rev_record.status,
                        source_type=rev_record.source_type,
                        source_reference=rev_record.source_reference,
                        requires_review=rev_record.source_type == "demo",
                    )
                    break  # Take the latest approved

            return CoefficientSet(items=items)

    def create_revision_from_approved(
        self,
        definition_id: str,
        value_decimal: Decimal | None = None,
        value_json: dict[str, object] | None = None,
        change_reason: str = "",
        created_by: str = "system",
    ) -> CoefficientRevision:
        """Create a new draft revision from the latest approved revision."""
        with self.session_factory() as session:
            # Find latest approved revision
            approved = session.scalars(
                select(CoefficientRevisionRecord)
                .where(
                    CoefficientRevisionRecord.coefficient_definition_id == definition_id,
                    CoefficientRevisionRecord.status == "approved",
                )
                .order_by(CoefficientRevisionRecord.revision_number.desc())
            ).all()

            if not approved:
                raise CoefficientNotFoundError(f"No approved revision for {definition_id}")

            latest = approved[0]
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
    # Seed data (database-backed)
    # ------------------------------------------------------------------

    def seed_demo_coefficients(self) -> list[CoefficientRevision]:
        """Seed the initial demo coefficients into the database."""
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
            # Move to unverified status
            self.submit_revision_for_review(definition.id, revision.id, reviewer="seed")
            created.append(revision)
        return created

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_revision_record(
        self, session: Session, definition_id: str, revision_id: str
    ) -> CoefficientRevisionRecord:
        """Get a revision record and validate it belongs to the definition."""
        record = session.get(CoefficientRevisionRecord, revision_id)
        if record is None:
            raise CoefficientNotFoundError(revision_id)
        if record.coefficient_definition_id != definition_id:
            raise CoefficientNotFoundError(revision_id)
        return record

    @staticmethod
    def _validate_not_locked(record: CoefficientRevisionRecord, target_status: str = "") -> None:
        """Validate that a revision record is not locked.

        Exception: approved → withdrawn is always allowed.
        """
        from cold_storage.modules.coefficients.domain.exceptions import (
            RevisionImmutabilityError,
        )

        if record.status in ("approved", "withdrawn") and not (
            record.status == "approved" and target_status == "withdrawn"
        ):
            raise RevisionImmutabilityError(record.id, record.status, "modify")

    @staticmethod
    def _validate_transition(from_status: str, to_status: str) -> None:
        """Validate that a state transition is allowed."""
        from cold_storage.modules.coefficients.domain.models import (
            validate_revision_transition,
        )

        validate_revision_transition(from_status, to_status)

    @staticmethod
    def _definition_to_record(definition: CoefficientDefinition) -> CoefficientDefinitionRecord:
        """Convert a domain model to an ORM record."""
        return CoefficientDefinitionRecord(
            id=definition.id,
            code=definition.code,
            name=definition.name,
            description=definition.description,
            category=definition.category,
            canonical_unit=definition.canonical_unit,
            value_type=definition.value_type,
            scope_type=definition.scope_type,
            is_active=definition.is_active,
            created_at=definition.created_at,
            updated_at=definition.updated_at,
        )

    @staticmethod
    def _definition_from_record(record: CoefficientDefinitionRecord) -> CoefficientDefinition:
        """Convert an ORM record to a domain model."""
        return CoefficientDefinition(
            id=record.id,
            code=record.code,
            name=record.name,
            description=record.description,
            category=record.category,
            canonical_unit=record.canonical_unit,
            value_type=record.value_type,
            scope_type=record.scope_type,
            is_active=record.is_active,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _revision_from_record(record: CoefficientRevisionRecord) -> CoefficientRevision:
        """Convert an ORM record to a domain model."""
        value_decimal = None
        if record.value_decimal is not None:
            try:
                value_decimal = Decimal(record.value_decimal)
            except (InvalidOperation, ValueError):
                value_decimal = None

        value_json = None
        if record.value_json is not None:
            if isinstance(record.value_json, str):
                try:
                    value_json = json.loads(record.value_json)
                except (json.JSONDecodeError, TypeError):
                    value_json = None
            else:
                value_json = record.value_json

        return CoefficientRevision(
            id=record.id,
            coefficient_definition_id=record.coefficient_definition_id,
            revision_number=record.revision_number,
            value_decimal=value_decimal,
            value_json=value_json,
            unit=record.unit,
            status=record.status,
            source_type=record.source_type,
            source_title=record.source_title,
            source_reference=record.source_reference,
            source_page=record.source_page,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            applicable_product_type=record.applicable_product_type,
            applicable_zone_type=record.applicable_zone_type,
            applicable_process_type=record.applicable_process_type,
            supersedes_revision_id=record.supersedes_revision_id,
            change_reason=record.change_reason,
            created_by=record.created_by,
            reviewed_by=record.reviewed_by,
            approved_by=record.approved_by,
            created_at=record.created_at,
            reviewed_at=record.reviewed_at,
            approved_at=record.approved_at,
            withdrawn_at=record.withdrawn_at,
        )
