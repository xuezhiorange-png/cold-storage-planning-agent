"""Infrastructure adapters for production scheme generation.

Implements SourceBindingReadPort and WeightRevisionReadPort using
SQLAlchemy ORM.  Repositories MUST NOT commit/rollback/close/create sessions.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.infrastructure.orm import (
    OrchestrationRunAttemptRecord,
    SourceBindingRecord,
)
from cold_storage.modules.projects.infrastructure.orm import (
    CalculationRunRecord,
)
from cold_storage.modules.schemes.application.production_ports import (
    AttemptSnapshot,
    CalculationRunSnapshot,
    SourceBindingSnapshot,
    WeightSetRevisionSnapshot,
)
from cold_storage.modules.schemes.infrastructure.orm import (
    SchemeWeightSetRevisionRecord,
)

# ── SourceBindingReadPort adapter ──────────────────────────────────────────


class SqlAlchemySourceBindingReadPort:
    """Read-only adapter for SourceBinding and CalculationRun loading."""

    def load_binding(self, session: Session, /, *, binding_id: str) -> SourceBindingSnapshot | None:
        record = session.execute(
            select(SourceBindingRecord).where(SourceBindingRecord.id == binding_id)
        ).scalar_one_or_none()
        if record is None:
            return None
        return SourceBindingSnapshot(
            id=record.id,
            project_id=record.project_id,
            project_version_id=record.project_version_id,
            execution_snapshot_id=record.execution_snapshot_id,
            coefficient_context_id=record.coefficient_context_id,
            orchestration_identity_id=record.orchestration_identity_id,
            orchestration_run_attempt_id=record.orchestration_run_attempt_id,
            orchestration_fingerprint=record.orchestration_fingerprint,
            zone_calculation_id=record.zone_calculation_id,
            cooling_load_calculation_id=record.cooling_load_calculation_id,
            equipment_calculation_id=record.equipment_calculation_id,
            power_calculation_id=record.power_calculation_id,
            investment_calculation_id=record.investment_calculation_id,
            per_calculation_result_hashes=record.per_calculation_result_hashes or {},
            combined_source_hash=record.combined_source_hash,
            schema_version=record.schema_version,
        )

    def load_calculation_run(
        self, session: Session, /, *, run_id: str
    ) -> CalculationRunSnapshot | None:
        record = session.execute(
            select(CalculationRunRecord).where(CalculationRunRecord.id == run_id)
        ).scalar_one_or_none()
        if record is None:
            return None
        return CalculationRunSnapshot(
            id=record.id,
            project_id=record.project_id,
            project_version_id=record.project_version_id,
            orchestration_identity_id=record.orchestration_identity_id or "",
            orchestration_run_attempt_id=record.orchestration_run_attempt_id or "",
            orchestration_fingerprint=record.orchestration_fingerprint,
            calculator_name=record.calculator_name,
            calculator_version=record.calculator_version,
            calculation_type=record.calculation_type or "",
            result_snapshot=record.result_snapshot or {},
            result_hash=record.result_hash or "",
            schema_version=record.schema_version,
            formulas=record.formulas or [],
            coefficients=record.coefficients or [],
            assumptions=record.assumptions or [],
            warnings=record.warnings or [],
            source_references=record.source_references or [],
            upstream_calculation_ids=getattr(record, "upstream_calculation_ids", None) or {},
            requires_review=record.requires_review or False,
        )

    def load_attempt(self, session: Session, /, *, attempt_id: str) -> AttemptSnapshot | None:
        record = session.execute(
            select(OrchestrationRunAttemptRecord).where(
                OrchestrationRunAttemptRecord.id == attempt_id
            )
        ).scalar_one_or_none()
        if record is None:
            return None
        return AttemptSnapshot(
            id=record.id,
            identity_id=record.identity_id,
            status=record.status,
            source_binding_id=record.source_binding_id,
        )


# ── WeightRevisionReadPort adapter ────────────────────────────────────────


class SqlAlchemyWeightRevisionReadPort:
    """Read-only adapter for weight-set revision loading."""

    def load_approved_revision(
        self, session: Session, /, *, revision_id: str
    ) -> WeightSetRevisionSnapshot | None:
        record = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == revision_id
            )
        ).scalar_one_or_none()
        if record is None:
            return None

        # Parse criteria from content
        from cold_storage.modules.schemes.application.weight_revision_governance import (
            _parse_criteria,
        )

        raw_criteria = record.content.get("criteria", [])
        criteria = _parse_criteria(raw_criteria) if raw_criteria else ()

        return WeightSetRevisionSnapshot(
            id=record.id,
            weight_set_id=record.weight_set_id,
            code=record.code,
            revision=record.revision,
            status=record.status,
            content=record.content or {},
            content_hash=record.content_hash,
            generator_compatibility_version=record.generator_compatibility_version,
            approved_at=record.approved_at,
            approved_by=record.approved_by or "",
            criteria=criteria,
        )
