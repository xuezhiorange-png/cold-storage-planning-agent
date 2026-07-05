"""Coefficient catalog seed — infrastructure layer.

Reads the domain catalog manifest and populates the database with
``CoefficientDefinitionRecord`` and ``CoefficientRevisionRecord`` rows.
Idempotent — skips codes that already exist.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.coefficients.domain.catalog import COEFFICIENT_CATALOG


def seed_catalog(session: Session) -> None:
    """Seed the coefficient catalog into the database.

    Idempotent — skips codes that already exist.  Creates both a
    ``CoefficientDefinitionRecord`` and an initial approved
    ``CoefficientRevisionRecord`` for each catalog entry.
    """
    from cold_storage.modules.coefficients.infrastructure.orm import (
        CoefficientDefinitionRecord,
        CoefficientRevisionRecord,
    )

    for entry in COEFFICIENT_CATALOG:
        existing = session.execute(
            select(CoefficientDefinitionRecord).where(
                CoefficientDefinitionRecord.code == entry["code"]
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        defn = CoefficientDefinitionRecord(
            id=uuid.uuid4().hex,
            code=str(entry["code"]),
            name=str(entry["name"]),
            description=str(entry["description"]),
            category=str(entry["category"]),
            canonical_unit=str(entry["canonical_unit"]),
            value_type=str(entry["value_type"]),
            scope_type=str(entry["scope_type"]),
            is_active=True,
        )
        session.add(defn)
        session.flush()
        rev = CoefficientRevisionRecord(
            id=uuid.uuid4().hex,
            coefficient_definition_id=defn.id,
            revision_number=1,
            value_decimal="1.0",
            unit=str(entry["canonical_unit"]),
            status="approved",
            source_type="standard",
            approved_at=datetime.now(UTC),
        )
        session.add(rev)
    session.commit()
