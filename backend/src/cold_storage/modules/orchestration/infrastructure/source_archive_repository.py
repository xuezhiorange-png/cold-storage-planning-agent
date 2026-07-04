"""Infrastructure adapter for ``production_source_archives`` table.

The application layer (orchestration.application.source_archive_builder)
and (orchestration.application.historical_source_resolver) consume
``ProductionSourceArchiveWritePort`` / ``ProductionSourceArchiveReadPort``
protocols defined in ``application/ports.py``.  This module is the
single concrete implementation of both protocols, scoped to the
SQLAlchemy ORM model ``ProductionSourceArchiveRecord``.

Architecture rule: this module MAY import SQLAlchemy.  It MUST NOT be
imported by any module under ``cold_storage.modules.orchestration.application``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from cold_storage.modules.orchestration.infrastructure.orm import (
    ProductionSourceArchiveRecord,
)


class SqlAlchemyProductionSourceArchiveRepository:
    """Concrete SQLAlchemy adapter for archive writes and reads.

    Methods:
        add_archive(session, **fields) -> None
            Inserts a new row.  Does NOT commit.  The caller's UoW owns
            the transaction boundary.

        find_by_scheme_run_id(session, scheme_run_id) -> Mapping | None
            Returns the archive row as a Mapping snapshot, or None.

    Both methods accept a ``session: Any`` because the application ports
    type session as Any to keep their module free of SQLAlchemy imports.
    At runtime we expect a SQLAlchemy ``Session`` (or compatible).
    """

    def add_archive(
        self,
        session: Any,
        *,
        archive_id: str,
        scheme_run_id: str,
        source_binding_id: str | None,
        source_contract_version: str,
        archive_schema_version: str,
        archive_payload: Mapping[str, Any],
        archive_hash: str,
        combined_source_hash: str | None,
        weight_set_revision_id: str | None,
        weight_set_content_hash: str | None,
        binding_schema_version: str | None,
        execution_snapshot_id: str | None,
        coefficient_context_id: str | None,
        orchestration_identity_id: str | None,
        authoritative_attempt_id: str | None,
        orchestration_fingerprint: str | None,
        created_at: datetime,
        created_by: str,
        reason: str,
    ) -> None:
        """Insert a row.  NO commit, NO flush, NO rollback.

        The application builder calls this inside its UoW; the UoW owns
        flush/commit.  We DO call ``session.add(record)`` which stages
        the row for the UoW's eventual flush.
        """
        record = ProductionSourceArchiveRecord(
            id=archive_id,
            scheme_run_id=scheme_run_id,
            source_binding_id=source_binding_id,
            source_contract_version=source_contract_version,
            archive_schema_version=archive_schema_version,
            archive_payload=dict(archive_payload),
            archive_hash=archive_hash,
            combined_source_hash=combined_source_hash,
            weight_set_revision_id=weight_set_revision_id,
            weight_set_content_hash=weight_set_content_hash,
            binding_schema_version=binding_schema_version,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            authoritative_attempt_id=authoritative_attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
            created_at=created_at,
            created_by=created_by,
            reason=reason,
        )
        session.add(record)

    def find_by_scheme_run_id(
        self,
        session: Any,
        scheme_run_id: str,
    ) -> Mapping[str, Any] | None:
        """Return the archive row as a Mapping snapshot, or None.

        The Mapping shape matches what the historical source resolver
        expects (so its downstream field accesses all work).  Raises
        AttributeError if the session is not a SQLAlchemy Session or
        compatible — the application layer wraps this in try/except
        and converts it to a domain error.
        """
        record = (
            session.query(ProductionSourceArchiveRecord)
            .filter(ProductionSourceArchiveRecord.scheme_run_id == scheme_run_id)
            .one_or_none()
        )
        if record is None:
            return None

        return _snapshot(record)


def _snapshot(record: ProductionSourceArchiveRecord) -> Mapping[str, Any]:
    """Convert ORM record to a Mapping snapshot for resolver use."""
    payload_obj = record.archive_payload
    payload_dict: dict[str, object] = dict(payload_obj) if isinstance(payload_obj, dict) else {}
    slots_obj = payload_dict.get("source_slots", {})
    source_slots: dict[str, dict[str, str]] = (
        {k: dict(v) for k, v in slots_obj.items()} if isinstance(slots_obj, dict) else {}
    )
    return {
        "id": record.id,
        "scheme_run_id": record.scheme_run_id,
        "source_binding_id": record.source_binding_id,
        "source_contract_version": record.source_contract_version,
        "archive_schema_version": record.archive_schema_version,
        "archive_payload": payload_dict,
        "archive_hash": record.archive_hash,
        "combined_source_hash": record.combined_source_hash,
        "weight_set_revision_id": record.weight_set_revision_id,
        "weight_set_content_hash": record.weight_set_content_hash,
        "binding_schema_version": record.binding_schema_version,
        "execution_snapshot_id": record.execution_snapshot_id,
        "coefficient_context_id": record.coefficient_context_id,
        "orchestration_identity_id": record.orchestration_identity_id,
        "authoritative_attempt_id": record.authoritative_attempt_id,
        "orchestration_fingerprint": record.orchestration_fingerprint,
        "created_at": record.created_at,
        "created_by": record.created_by,
        "reason": record.reason,
        "source_slots": source_slots,
    }
