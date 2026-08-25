"""Session-scoped persisted calculation query for report assembly (V0.5 P3)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.application.canonical_calculation_index import (
    index_canonical_calculation_runs,
)
from cold_storage.modules.orchestration.infrastructure.orm import (
    CoefficientContextRecord,
    ProjectVersionExecutionSnapshotRecord,
)
from cold_storage.modules.projects.infrastructure.orm import (
    CalculationRunRecord,
    ProjectVersionRecord,
)
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    OrchestratedCalculationResult,
    ReportEngineeringContext,
    _assumptions_from_persisted_sources,
    _input_conditions_from_engineering_bundle,
    build_input_conditions_from_execution_snapshot_and_coefficients,
    build_orchestrated_result_from_indexed,
    detect_canonical_lineage_stale_reasons,
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
        "assumptions": record.assumptions,
        "coefficients": record.coefficients,
        "created_at": record.created_at.isoformat() if record.created_at else "",
    }
    if record.result_hash is not None:
        payload["result_hash"] = record.result_hash
    if record.provenance and isinstance(record.provenance, dict):
        upstream = record.provenance.get("upstream_calculation_ids")
        if upstream is not None:
            payload["upstream_calculation_ids"] = upstream
    if record.execution_snapshot_id is not None:
        payload["execution_snapshot_id"] = record.execution_snapshot_id
    if record.coefficient_context_id is not None:
        payload["coefficient_context_id"] = record.coefficient_context_id
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

    def get_report_engineering_context(
        self, project_id: str, project_version_id: str
    ) -> ReportEngineeringContext | None:
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
        if not indexed:
            return None

        version = self._session.scalar(
            select(ProjectVersionRecord).where(ProjectVersionRecord.id == project_version_id)
        )
        version_input_snapshot = dict(version.input_snapshot) if version is not None else {}
        version_assumption_snapshot = (
            dict(version.assumption_snapshot) if version is not None else {}
        )

        input_conditions = None
        if version_input_snapshot.get("schema_id") == "EngineeringInputBundleV1":
            input_conditions = _input_conditions_from_engineering_bundle(version_input_snapshot)

        execution_snapshot_id = next(
            (
                row.execution_snapshot_id
                for row in rows
                if row.execution_snapshot_id is not None
            ),
            None,
        )
        coefficient_context_id = next(
            (
                row.coefficient_context_id
                for row in rows
                if row.coefficient_context_id is not None
            ),
            None,
        )
        if input_conditions is None and execution_snapshot_id is not None:
            execution_record = self._session.get(
                ProjectVersionExecutionSnapshotRecord, execution_snapshot_id
            )
            coefficient_record = (
                self._session.get(CoefficientContextRecord, coefficient_context_id)
                if coefficient_context_id is not None
                else None
            )
            if execution_record is not None:
                coefficient_content = (
                    dict(coefficient_record.content)
                    if coefficient_record is not None
                    else None
                )
                input_conditions = build_input_conditions_from_execution_snapshot_and_coefficients(
                    dict(execution_record.input_snapshot),
                    coefficient_content,
                )

        assumptions = _assumptions_from_persisted_sources(
            version_assumption_snapshot=version_assumption_snapshot,
            indexed_calculations=indexed,
        )
        return ReportEngineeringContext(
            input_conditions=input_conditions,
            assumptions=assumptions,
            indexed_calculator_names=frozenset(indexed),
            stale_lineage_reasons=tuple(detect_canonical_lineage_stale_reasons(indexed)),
        )
