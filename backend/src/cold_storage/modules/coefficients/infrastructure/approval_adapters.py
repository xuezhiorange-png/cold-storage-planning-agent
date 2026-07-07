"""SQLAlchemy-backed adapters for the Phase 4 Slice 1 ports.

These adapters wire the application-layer protocols
(``application/ports.py``) and the application services to the
existing SQLAlchemy engine + ORM models. They live in the
infrastructure layer per the project's architecture rules
(``AGENTS.md §Architecture Rules``).

Charles's Slice 1 boundary correction (2026-07-07):

- This module does **not** modify
  :class:`cold_storage.modules.coefficients.infrastructure.database.DatabaseCoefficientService`
  or the existing :class:`CoefficientService`. It introduces a
  side path: the **production path** wires these adapters; the
  in-memory ``CoefficientService`` flow continues to work
  untouched for tests + demo seed.

- The DB read adapter (``SqlAlchemyCoefficientRevisionReadAdapter``)
  performs direct SQLAlchemy queries into ``coefficient_revisions``.
  It does **not** consult ``CoefficientService._revisions``
  in-memory cache for the production path; cache and DB state must
  agree, and the cache may be stale in long-running processes.

- The mutation adapter (``SqlAlchemyCoefficientMutationAdapter``)
  is a thin pass-through. The existing
  :class:`DatabaseCoefficientService` does not override the in-memory
  revision-mutation methods, so for Slice 1 the production path
  inherits the in-memory behavior on the revision side. This is a
  **known Slice 1 limitation**: full DB-backed revision mutation is
  deferred to a later Slice (alongside the per-definition pending
  approval log row). The two **log tables** (approval + audit) that
  Slice 1 ships are persisted durably.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from cold_storage.modules.coefficients.application.approval_service import (
    CoefficientMutationPort,
)
from cold_storage.modules.coefficients.application.ports import (
    CoefficientApprovalLogPort,
    CoefficientAuditLogPort,
    CoefficientClockPort,
    CoefficientRevisionReadPort,
    CoefficientRoleCheckPort,
)
from cold_storage.modules.coefficients.application.service import (
    CoefficientService,
)
from cold_storage.modules.coefficients.domain.models import (
    CoefficientDefinition,
    CoefficientRevision,
)
from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientApprovalLogRecord,
    CoefficientAuditLogRecord,
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)

# ---------------------------------------------------------------------------
# Record <-> dataclass conversion (inline; not exported)
# ---------------------------------------------------------------------------


def _revision_from_record(record: CoefficientRevisionRecord) -> CoefficientRevision:
    """Mirror :meth:`DatabaseCoefficientService._revision_from_record`.

    Inlined here to avoid coupling this module to private methods
    on ``DatabaseCoefficientService``. The conversion logic
    intentionally duplicates the existing helper; it does not
    change semantics. If the canonical converter changes in a
    follow-up Slice, this inline copy must be updated in lockstep.
    """
    value_decimal: Decimal | None = None
    if record.value_decimal is not None:
        try:
            value_decimal = Decimal(record.value_decimal)
        except InvalidOperation:
            value_decimal = None

    value_json: dict[str, object] | None = None
    raw_json = record.value_json
    if raw_json is not None:
        if isinstance(raw_json, dict):
            value_json = raw_json
        elif isinstance(raw_json, str) and raw_json.strip():
            try:
                value_json = json.loads(raw_json)
            except json.JSONDecodeError:
                value_json = None

    return CoefficientRevision(
        id=record.id,
        coefficient_definition_id=record.coefficient_definition_id,
        revision_number=record.revision_number,
        unit=record.unit,
        value_decimal=value_decimal,
        value_json=value_json,
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


# ---------------------------------------------------------------------------
# Read port
# ---------------------------------------------------------------------------


class SqlAlchemyCoefficientRevisionReadAdapter(CoefficientRevisionReadPort):
    """Read-only SQL access to revisions, used by the production resolver.

    The Stage / calculation_type binding maps onto the
    ``CoefficientDefinitionRecord.category`` column (which is the
    closest existing analogue to a stage slot). A strict resolver
    uses these direct SQL queries; the in-memory cache is
    intentionally bypassed on the production path.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def list_approved_revisions(
        self,
        *,
        stage_name: str,
        calculation_type: str | None,
    ) -> list[CoefficientRevision]:
        """Return all revisions whose definition's ``category == stage_name``
        and whose ``status == approved``.
        """
        with self._session_factory() as session:
            stmt = (
                select(CoefficientRevisionRecord)
                .join(
                    CoefficientDefinitionRecord,
                    CoefficientRevisionRecord.coefficient_definition_id
                    == CoefficientDefinitionRecord.id,
                )
                .where(CoefficientDefinitionRecord.category == stage_name)
                .where(CoefficientRevisionRecord.status == "approved")
                .order_by(CoefficientRevisionRecord.approved_at.desc().nullslast())
            )
            records = session.scalars(stmt).all()
            return [_revision_from_record(r) for r in records]

    def get_definition_by_code(self, code: str) -> CoefficientDefinition:
        """Look up a definition by its canonical code.

        Implementation note: delegating back to the existing
        ``CoefficientService.get_definition_by_code`` would couple
        this adapter to the in-memory cache. Slice 1 reads the
        freshest row from the DB instead.
        """
        from cold_storage.modules.coefficients.domain.exceptions import (
            CoefficientNotFoundError,
        )

        with self._session_factory() as session:
            record = session.scalar(
                select(CoefficientDefinitionRecord).where(CoefficientDefinitionRecord.code == code)
            )
            if record is None:
                raise CoefficientNotFoundError(code)
            return CoefficientDefinition(
                code=record.code,
                name=record.name,
                description=record.description,
                category=record.category,
                canonical_unit=record.canonical_unit,
                value_type=record.value_type,
                scope_type=record.scope_type,
                is_active=record.is_active,
                id=record.id,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )

    def get_revision(self, definition_id: str, revision_id: str) -> CoefficientRevision:
        from cold_storage.modules.coefficients.domain.exceptions import (
            CoefficientNotFoundError,
        )

        with self._session_factory() as session:
            record = session.scalar(
                select(CoefficientRevisionRecord).where(
                    CoefficientRevisionRecord.id == revision_id,
                    CoefficientRevisionRecord.coefficient_definition_id == definition_id,
                )
            )
            if record is None:
                raise CoefficientNotFoundError(revision_id)
            return _revision_from_record(record)


# ---------------------------------------------------------------------------
# Mutation port
# ---------------------------------------------------------------------------


class SqlAlchemyCoefficientMutationAdapter(CoefficientMutationPort):
    """Pass-through mutation adapter.

    Per Charles's Slice 1 boundary correction: this adapter does NOT
    override the existing in-memory mutation semantics. It exists
    so the production composition root can pass the
    :class:`CoefficientMutationPort` Protocol to
    :class:`CoefficientApprovalService`. The wrapped
    :class:`CoefficientService` (or its DB subclass for definition
    CRUD) retains all behavior.
    """

    def __init__(self, service: CoefficientService) -> None:
        self._service = service

    # All definitions follow the service surface verbatim. Slice 1
    # behavior intentionally matches the existing in-memory code;
    # see module docstring for the deferred DB-backed mutation.

    def create_definition(
        self,
        *,
        code: str,
        name: str,
        description: str,
        category: str,
        canonical_unit: str,
        value_type: str = "decimal",
        scope_type: str = "global",
        is_active: bool = True,
    ) -> Any:
        return self._service.create_definition(
            code=code,
            name=name,
            description=description,
            category=category,
            canonical_unit=canonical_unit,
            value_type=value_type,
            scope_type=scope_type,
            is_active=is_active,
        )

    def create_revision(
        self,
        *,
        definition_id: str,
        revision_number: int,
        unit: str,
        source_type: str = "demo",
        source_title: str | None = None,
        source_reference: str | None = None,
        source_page: str | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        value_decimal: Any = None,
        value_json: dict[str, object] | None = None,
        created_by: str = "system",
    ) -> CoefficientRevision:
        # ``create_revision`` in the existing service infers the
        # next revision number internally; we ignore the explicit
        # ``revision_number`` kwarg when delegating.
        return self._service.create_revision(
            definition_id=definition_id,
            unit=unit,
            source_type=source_type,
            source_title=source_title,
            source_reference=source_reference,
            source_page=source_page,
            valid_from=valid_from,
            valid_to=valid_to,
            value_decimal=value_decimal,
            value_json=value_json,
            created_by=created_by,
        )

    def list_revisions(self, definition_id: str) -> list[CoefficientRevision]:
        return self._service.list_revisions(definition_id)

    def list_revisions_for_stage(
        self, stage_name: str, calculation_type: str | None
    ) -> list[CoefficientRevision]:
        """Stage binding: enumerate definitions whose ``category``
        matches ``stage_name`` and return all revisions.

        Note: the existing service does not have a per-stage
        enumeration. We delegate to the read adapter in production
        and to a category-filter list_definitions here as a
        parallel fallback. Slice 1 callers (the
        :class:`CoefficientApprovalService.validate_startup_readiness`
        path) should wire the read adapter directly via the
        composition root; this fallback exists so the in-memory
        test path is functional.
        """
        definitions = self._service.list_definitions(category=stage_name)
        result: list[CoefficientRevision] = []
        for d in definitions:
            result.extend(self._service.list_revisions(d.id))
        return result

    def get_revision(self, definition_id: str, revision_id: str) -> CoefficientRevision:
        return self._service.get_revision(definition_id, revision_id)

    def mark_revision_reviewed(
        self, definition_id: str, revision_id: str, reviewer: str
    ) -> CoefficientRevision:
        return self._service.mark_revision_reviewed(definition_id, revision_id, reviewer)

    def approve_revision(
        self, definition_id: str, revision_id: str, approver: str
    ) -> CoefficientRevision:
        return self._service.approve_revision(definition_id, revision_id, approver)

    def withdraw_revision(
        self, definition_id: str, revision_id: str, actor: str
    ) -> CoefficientRevision:
        return self._service.withdraw_revision(definition_id, revision_id, actor)


# ---------------------------------------------------------------------------
# Log write ports (durable; the Slice 1 persistence boundary)
# ---------------------------------------------------------------------------


class SqlAlchemyCoefficientApprovalLogAdapter(CoefficientApprovalLogPort):
    """Persists approval log rows to ``coefficient_approval_log``."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def record(
        self,
        *,
        revision_id: str,
        reviewer: str,
        action: str,
        citation: str,
        payload_hash: str,
        correlation_id: str,
    ) -> None:
        with self._session_factory() as session:
            row = CoefficientApprovalLogRecord(
                revision_id=revision_id,
                reviewer=reviewer,
                action=action,
                citation=citation,
                payload_hash=payload_hash,
                correlation_id=correlation_id,
            )
            session.add(row)
            session.commit()


class SqlAlchemyCoefficientAuditLogAdapter(CoefficientAuditLogPort):
    """Persists audit log rows to ``coefficient_audit_log``."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def record(
        self,
        *,
        revision_id: str,
        actor: str,
        correlation_id: str,
        old_state: str,
        new_state: str,
        reason: str,
    ) -> None:
        with self._session_factory() as session:
            row = CoefficientAuditLogRecord(
                revision_id=revision_id,
                actor=actor,
                correlation_id=correlation_id,
                old_state=old_state,
                new_state=new_state,
                reason=reason,
            )
            session.add(row)
            session.commit()


# ---------------------------------------------------------------------------
# Clock + role check ports
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SystemClock(CoefficientClockPort):
    """Wall-clock adapter that returns ``datetime.now(UTC)``."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class InMemoryRoleCheckAdapter(CoefficientRoleCheckPort):
    """In-memory role lookup used by the production path until the
    transport layer populates a real ``actor_roles`` mapping.

    Slice 1 ships a deterministic mapping for the test/CI env:
    the actor named ``"coefficient.reviewer"`` (the canonical
    role-holding identity) holds the role; any other actor does
    not. The actual auth-source will be wired in a later Slice.
    """

    def __init__(self) -> None:
        # The single reviewer identity in Slice 1 fixtures.
        self._static_roles: dict[str, frozenset[str]] = {
            "coefficient.reviewer": frozenset({"coefficient.reviewer"}),
        }

    def roles_for(self, actor: str) -> frozenset[str]:
        return self._static_roles.get(actor, frozenset())


__all__ = [
    "InMemoryRoleCheckAdapter",
    "SqlAlchemyCoefficientApprovalLogAdapter",
    "SqlAlchemyCoefficientAuditLogAdapter",
    "SqlAlchemyCoefficientMutationAdapter",
    "SqlAlchemyCoefficientRevisionReadAdapter",
    "SystemClock",
]
