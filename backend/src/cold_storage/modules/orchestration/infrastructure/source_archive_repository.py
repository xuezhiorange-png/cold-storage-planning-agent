"""Infrastructure adapter for ``production_source_archives`` table.

The application layer (orchestration.application.source_archive_builder)
and (orchestration.application.historical_source_resolver) consume
``ProductionSourceArchiveWritePort`` / ``ProductionSourceArchiveReadPort``
protocols defined in ``application/ports.py``.  This module is the
single concrete implementation of both protocols, scoped to the
SQLAlchemy ORM model ``ProductionSourceArchiveRecord``.

Architecture rule: this module MAY import SQLAlchemy.  It MUST NOT be
imported from the application layer (see ``application/ports.py`` for
the constraint).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.infrastructure.orm import (
    ProductionSourceArchiveRecord,
)


class SqlAlchemyProductionSourceArchiveRepository:
    """Concrete SQLAlchemy adapter for archive writes and reads."""

    def __init__(self, session: Session | None = None) -> None:
        # ``session`` is OPTIONAL on read paths so legacy call sites
        # that supply no session can still construct the repository and
        # call ``find_by_scheme_run_id`` with a session passed in.  On
        # write paths the application builder must provide the live
        # ``session`` so the INSERT participates in the caller's UoW.
        self._session = session

    # ── Write port ──────────────────────────────────────────────────────

    def add_archive(
        self,
        session: Session,
        *,
        archive_id: str,
        scheme_run_id: str,
        source_binding_id: str,
        source_contract_version: str,
        archive_schema_version: str,
        archive_payload: Mapping[str, Any],
        archive_hash: str,
        combined_source_hash: str,
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
    ) -> str:
        """Add a new ``production_source_archives`` row to ``session``.

        The caller (production SchemeRun UoW) owns the transaction;
        this method performs ``session.add`` and returns the row's id
        for the UoW's eventual flush.
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
        return archive_id

    # ── Read port ───────────────────────────────────────────────────────

    def find_by_scheme_run_id(
        self,
        session: Session,
        scheme_run_id: str,
    ) -> Mapping[str, Any] | None:
        """Return the unique archive row for ``scheme_run_id`` as a snapshot mapping."""
        record = (
            session.query(ProductionSourceArchiveRecord)
            .filter(ProductionSourceArchiveRecord.scheme_run_id == scheme_run_id)
            .one_or_none()
        )
        if record is None:
            return None
        return _snapshot(record)


def _snapshot(record: ProductionSourceArchiveRecord) -> Mapping[str, Any]:
    """Convert ORM record to a Mapping snapshot for resolver use.

    The ``source_slots`` sub-document is forwarded verbatim from
    ``archive_payload``.  In v1 it MUST be an ordered list of
    ``[slot_name, slot_payload]`` pairs in
    ``SOURCE_SLOT_ORDER_V1`` order; the resolver converts the list to
    a lookup map after recomputing the archive_hash.  Legacy v0 rows
    (no archive_hash binding to slot order) are accepted only in
    defensive read paths.
    """
    payload_obj = record.archive_payload
    payload_dict: dict[str, object] = dict(payload_obj) if isinstance(payload_obj, dict) else {}
    slots_obj = payload_dict.get("source_slots", [])

    if isinstance(slots_obj, list):
        # Preserve slot order verbatim from the JSON column.  Each
        # list element is ``[name, payload_dict]``; we rebuild a clean
        # ``[name, payload_dict]`` so callers (resolver) see the same
        # shape across SQLite and PostgreSQL.
        ordered_slots: list[Any] = []
        for entry in slots_obj:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                slot_name = entry[0]
                slot_payload = entry[1]
                clean_payload = dict(slot_payload) if isinstance(slot_payload, dict) else slot_payload
                ordered_slots.append([slot_name, clean_payload])
            else:
                # Forward unknown entry shapes unchanged; the resolver
                # raises ``SchemeSourceArchiveIntegrityError`` on the
                # malformed list element.
                ordered_slots.append(entry)
        source_slots: Any = ordered_slots
    elif isinstance(slots_obj, dict):
        # Legacy v0 dict payload shape — forwarded as-is so a defensive
        # read path can recognise it.
        source_slots = {
            k: dict(v) if isinstance(v, dict) else v for k, v in slots_obj.items()
        }
    else:
        source_slots = []

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


__all__ = ["SqlAlchemyProductionSourceArchiveRepository"]
