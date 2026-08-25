"""Session-scoped persisted calculation query for report assembly (V0.5 P3)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.application.canonical_calculation_index import (
    index_canonical_calculation_runs,
)
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    OrchestratedCalculationResult,
    build_orchestrated_result_from_indexed,
)


def _calculation_run_to_dict(record: CalculationRunRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": record.id,
        "calculation_id": record.id,
        "project_id": record.project_id,
        "project_version_id": record.project_version_id,
        "calculator_name": record.calculator_name,
        "calculator_version": record.calculator_version,
        "input_snapshot": record.input_snapshot,
        "result_snapshot": record.result_snapshot,
        "requires_review": record.requires_review,
        "created_at": record.created_at.isoformat() if record.created_at else "",
    }
    if record.result_hash is not None:
        payload["result_hash"] = record.result_hash
    if record.provenance and isinstance(record.provenance, dict):
        upstream = record.provenance.get("upstream_calculation_ids")
        if upstream is not None:
            payload["upstream_calculation_ids"] = upstream
    return payload


class SqlAlchemyPersistedCalculationQuery:
    """Read persisted canonical calculation rows for one database session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_orchestrated_result(
        self, project_id: str, project_version_id: str
    ) -> OrchestratedCalculationResult | None:
        rows = self._session.scalars(
            select(CalculationRunRecord).where(
                CalculationRunRecord.project_id == project_id,
                CalculationRunRecord.project_version_id == project_version_id,
            )
        ).all()
        calculations = [_calculation_run_to_dict(row) for row in rows]
        indexed = index_canonical_calculation_runs(
            calculations,
            project_id=project_id,
            project_version_id=project_version_id,
        )
        return build_orchestrated_result_from_indexed(indexed)
