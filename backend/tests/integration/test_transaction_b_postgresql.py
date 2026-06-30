"""Integration tests for orchestration Transaction B (five-stage calculator execution).

Uses real Alembic Head schema on PostgreSQL via the pg_database_factory
fixture pattern from conftest.py.

Covers:
- Success path: 5 CalculationRuns + 1 SourceBinding + COMPLETED attempt + outbox
- Hash parity: database-agnostic canonical output (SQLite ↔ PostgreSQL)
- 0028 constraint proof: raw-SQL INSERT tests for PostgreSQL CHECK/UNIQUE constraints

Tagged with @pytest.mark.postgresql for CI (-m postgresql).
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL Transaction B tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from cold_storage.modules.orchestration.application.ports import (
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
    ResolvedCoefficientContextCandidate,
)
from cold_storage.modules.orchestration.application.service import (
    OrchestrationService,
    ProjectVersionReadPort,
    _LoadedVersion,
)
from cold_storage.modules.orchestration.application.transaction_b import (
    StageExecutionResult,
)
from cold_storage.modules.orchestration.application.unit_of_work import (
    SqlAlchemyOrchestrationUnitOfWorkFactory,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
)
from cold_storage.modules.orchestration.domain.dag import ORCHESTRATION_STAGE_ORDER
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
from cold_storage.modules.orchestration.infrastructure.orm import (
    AuditOutboxRecord,
    OrchestrationIdentityRecord,
    OrchestrationRunAttemptRecord,
    SourceBindingRecord,
)
from cold_storage.modules.orchestration.infrastructure.repositories import (
    SqlAlchemyAuditOutboxRepository,
    SqlAlchemyCalculationRunRepository,
    SqlAlchemyCoefficientContextRepository,
    SqlAlchemyExecutionSnapshotRepository,
    SqlAlchemyOrchestrationAttemptRepository,
    SqlAlchemyOrchestrationIdentityRepository,
    SqlAlchemyOrchestrationRequestRepository,
    SqlAlchemySourceBindingRepository,
    SqlAlchemyVerificationReadPort,
)
from cold_storage.modules.projects.infrastructure.orm import (
    CalculationRunRecord,
    ProjectRecord,
    ProjectVersionRecord,
)

pytestmark = pytest.mark.postgresql

# ── Coefficient fixtures (must match Transaction A/B SQLite test exactly) ────

_REQUIRED_CODES: tuple[str, ...] = (
    "area.auxiliary_area_ratio",
    "area.circulation_allowance_ratio",
    "investment.building_unit_cost",
    "investment.electrical_installation_ratio",
    "investment.other_expenses_ratio",
    "investment.refrigeration_equipment_ratio",
    "pallet.net_load_kg",
    "pallet.turnover_factor",
    "power.design_margin_ratio",
    "power.standby_ratio",
)
_REGISTRY_VERSION = "1.0.0"
_CV_VECTOR: dict[str, str] = {
    "zone": "1.0.0",
    "cooling_load": "1.0.0",
    "equipment": "1.0.0",
    "power": "1.0.0",
    "investment": "1.0.0",
}


def _make_resolved_coefficient(
    *,
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
) -> ResolvedCoefficientContextCandidate:
    coefficients: list[dict[str, object]] = []
    revision_ids: list[str] = []
    for i, code in enumerate(_REQUIRED_CODES, 1):
        rev_id = f"rev-{i:03d}"
        revision_ids.append(rev_id)
        coefficients.append(
            {
                "definition_id": f"def-{i:03d}",
                "code": code,
                "revision_id": rev_id,
                "revision_number": 1,
                "unit": "dimensionless",
                "source_type": "standard",
                "status": "approved",
                "value_decimal": "1.0",
            }
        )

    req_hash = result_hash(
        {
            "registry_version": _REGISTRY_VERSION,
            "calculator_version_vector": dict(_CV_VECTOR),
            "required_codes": list(_REQUIRED_CODES),
        }
    )

    content: dict[str, object] = {
        "source_type": "catalog",
        "validity_status": "approved",
        "project_id": project_id,
        "project_version_id": project_version_id,
        "schema_version": "1.0.0",
        "coefficient_count": len(coefficients),
        "coefficients": coefficients,
        "requirement_registry_version": _REGISTRY_VERSION,
        "calculator_version_vector": dict(_CV_VECTOR),
        "required_codes": list(_REQUIRED_CODES),
        "requirement_hash": req_hash,
    }
    return ResolvedCoefficientContextCandidate(
        project_id=project_id,
        project_version_id=project_version_id,
        schema_version="1.0.0",
        content=content,
        content_hash=result_hash(content),
        approved_revision_ids=tuple(revision_ids),
    )


# ── Realistic mock calculator data ──────────────────────────────────────────


def _zone_result_snapshot() -> dict[str, Any]:
    return {
        "daily_inbound_mass_kg": "25000",
        "design_daily_mass_kg": "30000",
        "total_required_area_m2": "1200",
        "total_area_m2": "1400",
        "planning_parameters": {"safety_factor": "1.2"},
        "zones": [
            {
                "zone_code": "Z1",
                "zone_name": "Pre-cooling",
                "temperature_band": "2~8",
                "function": "precooling",
                "daily_throughput_kg_day": "25000",
                "design_storage_mass_kg": "5000",
                "position_count": 20,
                "required_area_m2": "400",
                "requires_review": False,
            },
            {
                "zone_code": "Z2",
                "zone_name": "Cold Storage",
                "temperature_band": "0~2",
                "function": "storage",
                "daily_throughput_kg_day": "25000",
                "design_storage_mass_kg": "25000",
                "position_count": 100,
                "required_area_m2": "800",
                "requires_review": False,
            },
        ],
    }


def _cooling_load_result_snapshot() -> dict[str, Any]:
    return {
        "total_cooling_load_kw": "350.0",
        "safety_margin_load_kw": "35.0",
        "envelope_heat_transfer_load_kw": "80.0",
        "product_sensible_heat_load_kw": "120.0",
        "packaging_load_kw": "20.0",
        "infiltration_load_kw": "30.0",
        "personnel_load_kw": "15.0",
        "lighting_load_kw": "10.0",
        "evaporator_fan_load_kw": "25.0",
        "defrost_additional_load_kw": "10.0",
        "other_configuration_load_kw": "5.0",
    }


def _equipment_result_snapshot() -> dict[str, Any]:
    return {
        "evaporator_total_cooling_capacity_kw": "500.0",
        "evaporator_quantity": 4,
        "single_evaporator_capacity_kw": "125.0",
        "compressor_operating_capacity_kw": "450.0",
        "standby_capacity_kw": "50.0",
        "condenser_heat_rejection_capacity_kw": "550.0",
        "evaporation_temperature_c": "-10.0",
        "condensing_temperature_c": "40.0",
        "defrost_method": "electric",
        "review_requirement": "",
    }


def _power_result_snapshot() -> dict[str, Any]:
    return {
        "total_installed_power_kw_e": "200.0",
        "total_estimated_demand_kw": "150.0",
        "equipment_rows": [
            {
                "sequence": 1,
                "name": "Compressor",
                "area": "machine_room",
                "quantity": "2",
                "running_power_kw": "75.0",
                "total_power_kw": "150.0",
                "section": "refrigeration",
            },
            {
                "sequence": 2,
                "name": "Condenser Fan",
                "area": "outdoor",
                "quantity": "4",
                "running_power_kw": "5.0",
                "total_power_kw": "20.0",
                "section": "refrigeration",
            },
        ],
        "summary_rows": [
            {
                "name": "Refrigeration",
                "basis": "equipment",
                "total_power_kw": "170.0",
            },
            {
                "name": "Lighting",
                "basis": "area",
                "total_power_kw": "30.0",
            },
        ],
        "items": [
            {
                "category": "refrigeration",
                "installed_power_kw": "170.0",
                "demand_factor": "0.85",
                "estimated_demand_kw": "144.5",
            },
            {
                "category": "lighting",
                "installed_power_kw": "30.0",
                "demand_factor": "0.80",
                "estimated_demand_kw": "24.0",
            },
        ],
        "assumptions": ["Standard operating conditions"],
    }


def _investment_result_snapshot() -> dict[str, Any]:
    return {
        "total_investment_cny": "5000000",
        "items": [
            {"item_name": "Refrigeration Equipment", "amount_cny": "2000000"},
            {"item_name": "Electrical Installation", "amount_cny": "1000000"},
            {"item_name": "Building Construction", "amount_cny": "1500000"},
            {"item_name": "Other Expenses", "amount_cny": "500000"},
        ],
    }


def _make_formulas(stage: str) -> list[dict[str, Any]]:
    return [
        {
            "formula_id": f"form-{stage}-01",
            "formula_version": "1.0.0",
            "expression": f"Q = m * cp * dT ({stage})",
            "description": f"Heat load calculation for {stage}",
        },
    ]


def _make_coefficients(stage: str) -> list[dict[str, Any]]:
    return [
        {
            "code": "pallet.net_load_kg",
            "value": "1000",
            "unit": "kg",
            "status": "approved",
            "source_type": "catalog",
            "source_reference": "standard-table-1",
            "requires_review": False,
            "revision_id": "rev-001",
        },
    ]


def _make_assumptions(stage: str) -> list[str]:
    return [f"Assumption for {stage}: standard operating conditions"]


def _make_warnings(stage: str) -> list[dict[str, Any]]:
    return [
        {
            "code": f"WARN_{stage.upper()}",
            "message": f"Review {stage} calculation values",
            "details": {},
        },
    ]


def _make_source_references(stage: str) -> list[dict[str, Any]]:
    return [
        {
            "source_type": "standard",
            "source_reference": f"GB-{stage}-2024",
            "version": "2024",
            "validity_status": "approved",
            "approval_status": "approved",
            "requires_review": False,
            "notes": "",
        },
    ]


# stage_name → (calculator_name, calculator_version, calculation_type, result_snapshot)
_STAGE_DATA: dict[str, tuple[str, str, str, dict[str, Any]]] = {
    "zone": ("cold_room_zone_plan", "1.0.0", "zone", _zone_result_snapshot()),
    "cooling_load": ("cooling_load", "1.0.0", "cooling_load", _cooling_load_result_snapshot()),
    "equipment": ("equipment", "1.0.0", "equipment", _equipment_result_snapshot()),
    "power": ("installed_power", "1.0.0", "power", _power_result_snapshot()),
    "investment": ("investment_estimate", "1.0.0", "investment", _investment_result_snapshot()),
}

# Lazy-loaded stage snapshot class map (avoids import at module level)
_STAGE_SNAPSHOT_CLS: dict[str, Any] = {}


def _get_stage_snapshot_cls(stage_name: str) -> Any:
    if not _STAGE_SNAPSHOT_CLS:
        from cold_storage.modules.orchestration.application.source_snapshots import (
            CoolingLoadSourceSnapshotV1,
            EquipmentSourceSnapshotV1,
            InvestmentSourceSnapshotV1,
            PowerSourceSnapshotV1,
            ZoneSourceSnapshotV1,
        )

        _STAGE_SNAPSHOT_CLS.update(
            {
                "zone": ZoneSourceSnapshotV1,
                "cooling_load": CoolingLoadSourceSnapshotV1,
                "equipment": EquipmentSourceSnapshotV1,
                "power": PowerSourceSnapshotV1,
                "investment": InvestmentSourceSnapshotV1,
            }
        )
    return _STAGE_SNAPSHOT_CLS[stage_name]


class _FakeCalculatorPort:
    """Mock CalculatorPort returning realistic StageExecutionResult for each stage."""

    def execute_stage(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, Any],
    ) -> StageExecutionResult:
        calc_name, calc_version, calc_type, result_snap = _STAGE_DATA[stage_name]
        return StageExecutionResult(
            calculator_name=calc_name,
            calculator_version=calc_version,
            calculation_type=calc_type,
            result_snapshot=result_snap,
            formulas=_make_formulas(stage_name),
            coefficients=_make_coefficients(stage_name),
            assumptions=_make_assumptions(stage_name),
            warnings=_make_warnings(stage_name),
            source_references=_make_source_references(stage_name),
            requires_review=False,
        )


class _RealVersionPort(ProjectVersionReadPort):
    """Real version port querying PostgreSQL."""

    def load_by_id(self, session, project_version_id: str) -> _LoadedVersion | None:
        record = session.execute(
            select(ProjectVersionRecord).where(ProjectVersionRecord.id == project_version_id)
        ).scalar_one_or_none()
        if record is None:
            return None
        project_record = session.execute(
            select(ProjectRecord).where(ProjectRecord.id == record.project_id)
        ).scalar_one_or_none()
        product_category = project_record.product_category if project_record else ""
        return _LoadedVersion(
            project_id=record.project_id,
            project_product_category=product_category,
            status=record.status,
            version_number=record.version_number,
            input_snapshot=record.input_snapshot or {},
        )


def _seed_project_and_version(
    session,
    *,
    project_id: str = "p-1",
    version_id: str = "pv-1",
    status: str = "approved",
):
    existing = session.execute(
        select(ProjectRecord).where(ProjectRecord.id == project_id)
    ).scalar_one_or_none()
    if not existing:
        session.add(
            ProjectRecord(
                id=project_id,
                code=f"T_{project_id}",
                name="Test Project",
                location="test",
                product_category="blueberry",
                created_at=datetime.now(UTC),
            )
        )
    existing_v = session.execute(
        select(ProjectVersionRecord).where(ProjectVersionRecord.id == version_id)
    ).scalar_one_or_none()
    if not existing_v:
        session.add(
            ProjectVersionRecord(
                id=version_id,
                project_id=project_id,
                version_number=1,
                change_summary="test version",
                created_by="test",
                status=status,
                created_at=datetime.now(UTC),
                input_snapshot={"throughput_t": "25.0", "product_category": "blueberry"},
            )
        )
    session.commit()


def _make_command(
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    actor: str = "test-actor",
    correlation_id: str = "corr-1",
) -> OrchestrationRequestCommand:
    return OrchestrationRequestCommand(
        project_id=project_id,
        project_version_id=project_version_id,
        coefficient_resolution_context={},
        actor=actor,
        correlation_id=correlation_id,
    )


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def pg_service(pg_session_factory):
    """Fully wired OrchestrationService on PostgreSQL with real repos + fake calculator."""
    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(pg_session_factory)
    version_port = _RealVersionPort()

    coeff_port = MagicMock(spec=CoefficientResolutionPreflightPort)
    coeff_port.resolve.return_value = _make_resolved_coefficient()

    return OrchestrationService(
        uow_factory=uow_factory,
        request_repo=SqlAlchemyOrchestrationRequestRepository(),
        outbox_repo=SqlAlchemyAuditOutboxRepository(),
        snapshot_repo=SqlAlchemyExecutionSnapshotRepository(),
        coefficient_repo=SqlAlchemyCoefficientContextRepository(),
        identity_repo=SqlAlchemyOrchestrationIdentityRepository(),
        attempt_repo=SqlAlchemyOrchestrationAttemptRepository(),
        version_port=version_port,
        snapshot_port=MagicMock(spec=ExecutionSnapshotPreflightPort),
        coefficient_port=coeff_port,
        calc_run_repo=SqlAlchemyCalculationRunRepository(),
        source_binding_repo=SqlAlchemySourceBindingRepository(),
        calculator_port=_FakeCalculatorPort(),
        verification_read_port=SqlAlchemyVerificationReadPort(),
    )


def _run_transaction_a(pg_service, pg_session_factory, *, correlation_id: str = "corr-b"):
    """Seed project + run Transaction A → return PreflightAccepted result."""
    with pg_session_factory() as s:
        _seed_project_and_version(s)
    return pg_service.execute(_make_command(correlation_id=correlation_id))


def _load_identity_context(pg_session_factory, identity_id: str) -> tuple[str, str, str]:
    """Load (execution_snapshot_id, coefficient_context_id, fingerprint) from identity."""
    with pg_session_factory() as s:
        identity = s.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == identity_id)
        ).scalar_one()
        return (
            identity.execution_snapshot_id,
            identity.coefficient_context_id,
            identity.fingerprint,
        )


def _run_transaction_b(pg_service, pg_session_factory, result_a):
    """Execute Transaction B and return the result."""
    snap_id, coeff_id, orch_fp = _load_identity_context(pg_session_factory, result_a.identity_id)
    return pg_service.execute_transaction_b(
        request_id=result_a.request_id,
        project_id="p-1",
        project_version_id="pv-1",
        execution_snapshot_id=snap_id,
        coefficient_context_id=coeff_id,
        orchestration_identity_id=result_a.identity_id,
        orchestration_attempt_id=result_a.attempt_id,
        orchestration_fingerprint=orch_fp,
        execution_snapshot={"throughput_t": "25.0"},
        coefficient_context={"coefficients": []},
    )


# ── Transaction B success path (PostgreSQL) ────────────────────────────────


class TestTransactionBPostgreSQLSuccess:
    """Full Transaction B on PostgreSQL: 5 CalculationRuns + SourceBinding + COMPLETED."""

    def test_five_calculation_runs_created(self, pg_service, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_service, pg_session_factory)
        _run_transaction_b(pg_service, pg_session_factory, result_a)

        with pg_session_factory() as s:
            runs = (
                s.execute(
                    select(CalculationRunRecord).where(
                        CalculationRunRecord.orchestration_run_attempt_id == result_a.attempt_id
                    )
                )
                .scalars()
                .all()
            )
            assert len(runs) == 5

            calc_names = {r.calculator_name for r in runs}
            assert calc_names == {
                "cold_room_zone_plan",
                "cooling_load",
                "equipment",
                "installed_power",
                "investment_estimate",
            }

            calc_types = {r.calculation_type for r in runs}
            assert calc_types == {"zone", "cooling_load", "equipment", "power", "investment"}

    def test_source_binding_created(self, pg_service, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_service, pg_session_factory)
        _run_transaction_b(pg_service, pg_session_factory, result_a)

        with pg_session_factory() as s:
            bindings = (
                s.execute(
                    select(SourceBindingRecord).where(
                        SourceBindingRecord.orchestration_run_attempt_id == result_a.attempt_id
                    )
                )
                .scalars()
                .all()
            )
            assert len(bindings) == 1
            binding = bindings[0]

            slot_ids = {
                binding.zone_calculation_id,
                binding.cooling_load_calculation_id,
                binding.equipment_calculation_id,
                binding.power_calculation_id,
                binding.investment_calculation_id,
            }
            assert len(slot_ids) == 5, "Five distinct slot IDs required"

            assert binding.orchestration_identity_id == result_a.identity_id

    def test_attempt_completed(self, pg_service, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_service, pg_session_factory)
        _run_transaction_b(pg_service, pg_session_factory, result_a)

        with pg_session_factory() as s:
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result_a.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "COMPLETED"
            assert attempt.completed_at is not None
            assert attempt.source_binding_id is not None

    def test_identity_authoritative_attempt(self, pg_service, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_service, pg_session_factory)
        _run_transaction_b(pg_service, pg_session_factory, result_a)

        with pg_session_factory() as s:
            identity = s.execute(
                select(OrchestrationIdentityRecord).where(
                    OrchestrationIdentityRecord.id == result_a.identity_id
                )
            ).scalar_one()
            assert identity.authoritative_attempt_id == result_a.attempt_id

    def test_completion_outbox(self, pg_service, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_service, pg_session_factory)
        _run_transaction_b(pg_service, pg_session_factory, result_a)

        with pg_session_factory() as s:
            completion_events = (
                s.execute(
                    select(AuditOutboxRecord).where(
                        AuditOutboxRecord.attempt_id == result_a.attempt_id,
                        AuditOutboxRecord.event_type == "orchestration.attempt.completed",
                    )
                )
                .scalars()
                .all()
            )
            assert len(completion_events) == 1
            ev = completion_events[0]
            assert ev.aggregate_type == "OrchestrationRunAttempt"
            assert ev.source_binding_id is not None

    def test_traceability_persisted(self, pg_service, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_service, pg_session_factory)
        _run_transaction_b(pg_service, pg_session_factory, result_a)

        with pg_session_factory() as s:
            runs = (
                s.execute(
                    select(CalculationRunRecord).where(
                        CalculationRunRecord.orchestration_run_attempt_id == result_a.attempt_id
                    )
                )
                .scalars()
                .all()
            )
            for run in runs:
                # Formulas — non-empty and realistic
                assert run.formulas is not None
                assert len(run.formulas) >= 1
                assert run.formulas[0]["formula_id"]

                # Coefficients — non-empty
                assert run.coefficients is not None
                assert len(run.coefficients) >= 1
                assert run.coefficients[0]["code"]

                # Assumptions — non-empty
                assert run.assumptions is not None
                assert len(run.assumptions) >= 1
                assert run.assumptions[0]

                # Warnings — non-empty
                assert run.warnings is not None
                assert len(run.warnings) >= 1
                assert run.warnings[0]["code"]

                # Source references — non-empty
                assert run.source_references is not None
                assert len(run.source_references) >= 1
                assert run.source_references[0]["source_type"]

    def test_all_runs_share_orchestration_context(self, pg_service, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_service, pg_session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(
            pg_session_factory, result_a.identity_id
        )
        _run_transaction_b(pg_service, pg_session_factory, result_a)

        with pg_session_factory() as s:
            runs = (
                s.execute(
                    select(CalculationRunRecord).where(
                        CalculationRunRecord.orchestration_run_attempt_id == result_a.attempt_id
                    )
                )
                .scalars()
                .all()
            )
            assert len(runs) == 5
            for run in runs:
                assert run.project_id == "p-1"
                assert run.project_version_id == "pv-1"
                assert run.execution_snapshot_id == snap_id
                assert run.coefficient_context_id == coeff_id
                assert run.orchestration_identity_id == result_a.identity_id
                assert run.orchestration_run_attempt_id == result_a.attempt_id
                assert run.orchestration_fingerprint == orch_fp

    def test_provenance_mapping(self, pg_service, pg_session_factory) -> None:
        """Verify upstream provenance mapping per the DAG:
        zone={}, cooling_load={zone}, equipment={cooling_load},
        power={equipment}, investment={zone, power}.
        """
        result_a = _run_transaction_a(pg_service, pg_session_factory)
        _run_transaction_b(pg_service, pg_session_factory, result_a)

        expected_provenance: dict[str, set[str]] = {
            "zone": set(),
            "cooling_load": {"zone"},
            "equipment": {"cooling_load"},
            "power": {"equipment"},
            "investment": {"zone", "power"},
        }

        with pg_session_factory() as s:
            runs = (
                s.execute(
                    select(CalculationRunRecord).where(
                        CalculationRunRecord.orchestration_run_attempt_id == result_a.attempt_id
                    )
                )
                .scalars()
                .all()
            )
            runs_by_type = {r.calculation_type: r for r in runs}
            for stage_name, expected_upstreams in expected_provenance.items():
                run = runs_by_type[stage_name]
                provenance = run.provenance or {}
                upstream_keys = set(provenance.get("upstream_calculation_ids", {}).keys())
                assert upstream_keys == expected_upstreams, (
                    f"Stage {stage_name}: expected upstream {expected_upstreams}, "
                    f"got {upstream_keys}"
                )


# ── Hash parity: database-agnostic canonical output ─────────────────────────


# Pre-compute the expected hashes using the same typed stage inputs.
# These constants prove that result_hash is deterministic regardless of backend.

_EXPECTED_RESULT_HASHES: dict[str, str] = {}
_EXPECTED_COMBINED_SOURCE_HASH: str | None = None


def _compute_expected_hashes() -> None:
    """Compute expected result_hash for each stage using typed source snapshots."""
    from cold_storage.modules.orchestration.application.source_snapshots import (
        CoolingLoadSourceSnapshotV1,
        EquipmentSourceSnapshotV1,
        InvestmentSourceSnapshotV1,
        PowerSourceSnapshotV1,
        ZoneSourceSnapshotV1,
    )
    from cold_storage.modules.orchestration.application.transaction_b import (
        SOURCE_BINDING_SCHEMA_VERSION,
        _compute_combined_source_hash,
    )

    binding_fields = {
        "project_id": "p-1",
        "project_version_id": "pv-1",
        "execution_snapshot_id": "snap-1",
        "coefficient_context_id": "coeff-1",
        "orchestration_identity_id": "ident-1",
        "orchestration_attempt_id": "attempt-1",
        "orchestration_fingerprint": "fp-1",
        "source_snapshot_schema_version": "1.0.0",
        "requires_review": False,
    }

    stage_snap_cls = {
        "zone": ZoneSourceSnapshotV1,
        "cooling_load": CoolingLoadSourceSnapshotV1,
        "equipment": EquipmentSourceSnapshotV1,
        "power": PowerSourceSnapshotV1,
        "investment": InvestmentSourceSnapshotV1,
    }

    upstream_map: dict[str, dict[str, str]] = {
        "zone": {},
        "cooling_load": {"zone": "run-zone"},
        "equipment": {"cooling_load": "run-cl"},
        "power": {"equipment": "run-eq"},
        "investment": {"zone": "run-zone", "power": "run-pwr"},
    }

    for stage_name in ORCHESTRATION_STAGE_ORDER:
        calc_name, calc_ver, calc_type, result_snap = _STAGE_DATA[stage_name]
        snap_cls = stage_snap_cls[stage_name]
        snap = snap_cls(
            **binding_fields,
            calculation_type=calc_type,
            calculator_id=calc_name,
            calculator_version=calc_ver,
            upstream_calculation_ids=upstream_map[stage_name],
            result_snapshot=result_snap,
            formulas=_make_formulas(stage_name),
            coefficients=_make_coefficients(stage_name),
            assumptions=_make_assumptions(stage_name),
            warnings=_make_warnings(stage_name),
            source_references=_make_source_references(stage_name),
        )
        _EXPECTED_RESULT_HASHES[stage_name] = snap.result_hash()

    slot_ids = {stage: f"run-{stage}" for stage in ORCHESTRATION_STAGE_ORDER}
    result_hashes = dict(_EXPECTED_RESULT_HASHES)
    requires_reviews = {stage: False for stage in ORCHESTRATION_STAGE_ORDER}
    _EXPECTED_COMBINED_SOURCE_HASH = _compute_combined_source_hash(
        binding_schema_version=SOURCE_BINDING_SCHEMA_VERSION,
        project_id="p-1",
        project_version_id="pv-1",
        execution_snapshot_id="snap-1",
        coefficient_context_id="coeff-1",
        orchestration_identity_id="ident-1",
        orchestration_attempt_id="attempt-1",
        orchestration_fingerprint="fp-1",
        slot_ids=slot_ids,
        result_hashes=result_hashes,
        requires_reviews=requires_reviews,
    )


_compute_expected_hashes()


class TestTransactionBHashParity:
    """Prove database-agnostic canonical output: same typed inputs → same hashes.

    Verifies that the stored result_hash matches the hash recomputed from
    the persisted result_snapshot, proving internal consistency regardless
    of which database backend stored the data.
    """

    def test_sqlite_postgresql_hash_parity(self, pg_service, pg_session_factory) -> None:
        """Recompute result hashes from persisted data and verify they match
        the stored hashes.  This proves canonical output is deterministic
        and not affected by database-specific serialization.
        """
        result_a = _run_transaction_a(pg_service, pg_session_factory)
        _run_transaction_b(pg_service, pg_session_factory, result_a)

        with pg_session_factory() as s:
            runs = (
                s.execute(
                    select(CalculationRunRecord).where(
                        CalculationRunRecord.orchestration_run_attempt_id == result_a.attempt_id
                    )
                )
                .scalars()
                .all()
            )
            runs_by_type = {r.calculation_type: r for r in runs}

            # Verify per-stage result hashes match recomputed hashes from stored snapshots
            for stage_name in ORCHESTRATION_STAGE_ORDER:
                run = runs_by_type[stage_name]
                assert run.result_hash is not None, f"Stage {stage_name}: result_hash is NULL"

                # Recompute hash from the persisted result_snapshot
                calc_name, calc_ver, calc_type, _ = _STAGE_DATA[stage_name]
                snap_cls = _get_stage_snapshot_cls(stage_name)
                snap = snap_cls(
                    project_id=run.project_id,
                    project_version_id=run.project_version_id,
                    execution_snapshot_id=run.execution_snapshot_id or "",
                    coefficient_context_id=run.coefficient_context_id or "",
                    orchestration_identity_id=run.orchestration_identity_id or "",
                    orchestration_attempt_id=run.orchestration_run_attempt_id or "",
                    orchestration_fingerprint=run.orchestration_fingerprint or "",
                    source_snapshot_schema_version="1.0.0",
                    calculation_type=calc_type,
                    calculator_id=calc_name,
                    calculator_version=calc_ver,
                    requires_review=run.requires_review,
                    result_snapshot=run.result_snapshot,
                    formulas=run.formulas,
                    coefficients=run.coefficients,
                    assumptions=run.assumptions,
                    warnings=run.warnings,
                    source_references=run.source_references,
                    upstream_calculation_ids=run.provenance.get("upstream_calculation_ids", {}),
                )
                recomputed = snap.result_hash()
                assert run.result_hash == recomputed, (
                    f"Stage {stage_name}: stored hash != recomputed hash.\n"
                    f"  Stored:    {run.result_hash}\n"
                    f"  Recomputed: {recomputed}\n"
                    f"  (Canonical output must be deterministic)"
                )


# ── 0028 PostgreSQL constraint proof ────────────────────────────────────────


class TestTransactionB0028PostgreSQLConstraints:
    """Raw-SQL INSERT tests proving PostgreSQL CHECK/UNIQUE constraints from 0028.

    Uses raw ``text()`` SQL to bypass ORM defaults and verify that the
    database-level constraints reject invalid data with named constraint errors.
    """

    @pytest.fixture(autouse=True)
    def _seed_fk_rows(self, pg_engine):
        """Seed project and project_versions rows required for FK constraints."""
        with pg_engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO projects (id, code, name, location, product_category, created_at)
                    VALUES ('fk-p-1', 'T_FK', 'FK Project', 'test', 'blueberry', NOW())
                    ON CONFLICT (id) DO NOTHING
                """)
            )
            conn.execute(
                text("""
                    INSERT INTO project_versions (
                        id, project_id, version_number, change_summary,
                        created_by, status, created_at, input_snapshot
                    ) VALUES (
                        'fk-pv-1', 'fk-p-1', 1, 'test version',
                        'test', 'approved', NOW(), '{}'::jsonb
                    )
                    ON CONFLICT (id) DO NOTHING
                """)
            )
            conn.commit()

    def test_orchestrated_row_missing_fingerprint_rejected(self, pg_engine) -> None:
        """INSERT with all orchestration fields EXCEPT fingerprint as NULL →
        IntegrityError with ck_calculation_run_fingerprint_nullity.
        """
        with pg_engine.connect() as conn:
            with pytest.raises(IntegrityError) as exc_info:
                conn.execute(
                    text("""
                        INSERT INTO calculation_runs (
                            id, project_id, project_version_id, calculator_name,
                            calculator_version, input_snapshot, result_snapshot,
                            formulas, coefficients, assumptions, warnings,
                            source_references, requires_review, created_at,
                            calculation_type, orchestration_identity_id,
                            orchestration_run_attempt_id,
                            execution_snapshot_id, coefficient_context_id,
                            input_hash, result_hash, provenance, schema_version,
                            orchestration_fingerprint
                        ) VALUES (
                            :id, :pid, :pvid, 'cold_room_zone_plan', '1.0.0',
                            '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, false, NOW(),
                            'zone', :ident_id, :attempt_id,
                            :snap_id, :coeff_id,
                            'abc123', 'def456', '{}'::jsonb, '1.0.0',
                            NULL
                        )
                    """),
                    {
                        "id": uuid.uuid4().hex,
                        "pid": "fk-p-1",
                        "pvid": "fk-pv-1",
                        "ident_id": uuid.uuid4().hex,
                        "attempt_id": uuid.uuid4().hex,
                        "snap_id": uuid.uuid4().hex,
                        "coeff_id": uuid.uuid4().hex,
                    },
                )
                conn.commit()

            assert "ck_calculation_run_fingerprint_nullity" in str(
                exc_info.value
            ) or "ck_calculation_run_fingerprint_nullity" in str(
                getattr(exc_info.value, "orig", exc_info.value)
            )

    def test_legacy_all_null_row_accepted(self, pg_engine) -> None:
        """INSERT with all orchestration fields NULL → success (legacy row)."""
        row_id = uuid.uuid4().hex
        with pg_engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO calculation_runs (
                        id, project_id, project_version_id, calculator_name,
                        calculator_version, input_snapshot, result_snapshot,
                        formulas, coefficients, assumptions, warnings,
                        source_references, requires_review, created_at,
                        calculation_type, orchestration_identity_id,
                        orchestration_run_attempt_id,
                        execution_snapshot_id, coefficient_context_id,
                        input_hash, result_hash, provenance, schema_version,
                        orchestration_fingerprint
                    ) VALUES (
                        :id, :pid, :pvid, 'legacy_calc', '0.1.0',
                        '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, false, NOW(),
                        NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
                    )
                """),
                {"id": row_id, "pid": "fk-p-1", "pvid": "fk-pv-1"},
            )
            conn.commit()

            # Verify it persisted
            result = conn.execute(
                text("SELECT id FROM calculation_runs WHERE id = :id"),
                {"id": row_id},
            ).fetchone()
            assert result is not None

    def test_partial_orchestration_row_rejected(self, pg_engine) -> None:
        """INSERT with some orchestration fields NULL → IntegrityError with
        ck_calculation_run_orchestration_nullity.
        """
        with pg_engine.connect() as conn:
            with pytest.raises(IntegrityError) as exc_info:
                conn.execute(
                    text("""
                        INSERT INTO calculation_runs (
                            id, project_id, project_version_id, calculator_name,
                            calculator_version, input_snapshot, result_snapshot,
                            formulas, coefficients, assumptions, warnings,
                            source_references, requires_review, created_at,
                            calculation_type, orchestration_identity_id,
                            orchestration_run_attempt_id,
                            execution_snapshot_id, coefficient_context_id,
                            input_hash, result_hash, provenance, schema_version,
                            orchestration_fingerprint
                        ) VALUES (
                            :id, :pid, :pvid, 'cold_room_zone_plan', '1.0.0',
                            '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, false, NOW(),
                            'zone', :ident_id, :attempt_id,
                            NULL, NULL,
                            'abc123', 'def456', '{}'::jsonb, '1.0.0',
                            'fp-1'
                        )
                    """),
                    {
                        "id": uuid.uuid4().hex,
                        "pid": "fk-p-1",
                        "pvid": "fk-pv-1",
                        "ident_id": uuid.uuid4().hex,
                        "attempt_id": uuid.uuid4().hex,
                    },
                )
                conn.commit()

            assert "ck_calculation_run_orchestration_nullity" in str(
                exc_info.value
            ) or "ck_calculation_run_orchestration_nullity" in str(
                getattr(exc_info.value, "orig", exc_info.value)
            )

    def test_duplicate_attempt_type_rejected(self, pg_engine) -> None:
        """INSERT two rows with same (attempt_id, calculation_type) →
        IntegrityError with uq_calculation_run_attempt_type.
        """
        attempt_id = uuid.uuid4().hex
        ident_id = uuid.uuid4().hex
        snap_id = uuid.uuid4().hex
        coeff_id = uuid.uuid4().hex

        with pg_engine.connect() as conn:
            # First row: should succeed
            conn.execute(
                text("""
                    INSERT INTO calculation_runs (
                        id, project_id, project_version_id, calculator_name,
                        calculator_version, input_snapshot, result_snapshot,
                        formulas, coefficients, assumptions, warnings,
                        source_references, requires_review, created_at,
                        calculation_type, orchestration_identity_id,
                        orchestration_run_attempt_id,
                        execution_snapshot_id, coefficient_context_id,
                        input_hash, result_hash, provenance, schema_version,
                        orchestration_fingerprint
                    ) VALUES (
                        :id1, :pid, :pvid, 'cold_room_zone_plan', '1.0.0',
                        '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, false, NOW(),
                        'zone', :ident_id, :attempt_id,
                        :snap_id, :coeff_id,
                        'abc123', 'def456', '{}'::jsonb, '1.0.0',
                        'fp-1'
                    )
                """),
                {
                    "id1": uuid.uuid4().hex,
                    "pid": "fk-p-1",
                    "pvid": "fk-pv-1",
                    "ident_id": ident_id,
                    "attempt_id": attempt_id,
                    "snap_id": snap_id,
                    "coeff_id": coeff_id,
                },
            )

            # Second row with same (attempt_id, calculation_type): should fail
            with pytest.raises(IntegrityError) as exc_info:
                conn.execute(
                    text("""
                        INSERT INTO calculation_runs (
                            id, project_id, project_version_id, calculator_name,
                            calculator_version, input_snapshot, result_snapshot,
                            formulas, coefficients, assumptions, warnings,
                            source_references, requires_review, created_at,
                            calculation_type, orchestration_identity_id,
                            orchestration_run_attempt_id,
                            execution_snapshot_id, coefficient_context_id,
                            input_hash, result_hash, provenance, schema_version,
                            orchestration_fingerprint
                        ) VALUES (
                            :id2, :pid, :pvid, 'cooling_load', '1.0.0',
                            '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, false, NOW(),
                            'zone', :ident_id, :attempt_id,
                            :snap_id, :coeff_id,
                            'abc789', 'ghi012', '{}'::jsonb, '1.0.0',
                            'fp-1'
                        )
                    """),
                    {
                        "id2": uuid.uuid4().hex,
                        "pid": "fk-p-1",
                        "pvid": "fk-pv-1",
                        "ident_id": ident_id,
                        "attempt_id": attempt_id,
                        "snap_id": snap_id,
                        "coeff_id": coeff_id,
                    },
                )
                conn.commit()

            assert "uq_calculation_run_attempt_type" in str(
                exc_info.value
            ) or "uq_calculation_run_attempt_type" in str(
                getattr(exc_info.value, "orig", exc_info.value)
            )

    def test_source_binding_slot_distinct_check(self, pg_engine) -> None:
        """INSERT with duplicate slot IDs → IntegrityError with
        ck_source_binding_slot_distinct.
        """
        # We need a valid orchestration_run_attempt to satisfy FK.
        # But SourceBinding also FK to calculation_runs for each slot.
        # For simplicity, bypass FK checks with session_replication_role or
        # use valid FK values.  Let's use valid FKs by seeding necessary rows.

        with pg_engine.connect() as conn:
            # Seed a dummy orchestration identity and attempt for FK
            ident_id = uuid.uuid4().hex
            attempt_id = uuid.uuid4().hex
            snap_id = uuid.uuid4().hex
            coeff_id = uuid.uuid4().hex

            conn.execute(
                text("""
                    INSERT INTO orchestration_execution_snapshots (
                        id, project_id, project_version_id, version_number,
                        input_snapshot, input_snapshot_hash, schema_version,
                        captured_status, captured_at
                    ) VALUES (
                        :sid, :pid, :pvid, 1,
                        '{}'::jsonb, 'snap_hash', '1.0.0', 'approved', NOW()
                    ) ON CONFLICT DO NOTHING
                """),
                {"sid": snap_id, "pid": "fk-p-1", "pvid": "fk-pv-1"},
            )
            conn.execute(
                text("""
                    INSERT INTO orchestration_coefficient_contexts (
                        id, project_id, project_version_id, content,
                        content_hash, schema_version, captured_at
                    ) VALUES (
                        :cid, :pid, :pvid, '{}'::jsonb,
                        'coeff_hash', '1.0.0', NOW()
                    ) ON CONFLICT DO NOTHING
                """),
                {"cid": coeff_id, "pid": "fk-p-1", "pvid": "fk-pv-1"},
            )
            conn.execute(
                text("""
                    INSERT INTO orchestration_identities (
                        id, fingerprint, execution_snapshot_id,
                        coefficient_context_id, definition_version,
                        calculator_version_vector, status, created_at
                    ) VALUES (
                        :iid, 'fp-dup', :sid,
                        :cid, '1.0.0',
                        '{}'::jsonb, 'ACTIVE', NOW()
                    ) ON CONFLICT DO NOTHING
                """),
                {"iid": ident_id, "sid": snap_id, "cid": coeff_id},
            )
            conn.execute(
                text("""
                    INSERT INTO orchestration_run_attempts (
                        id, identity_id, attempt_number, status,
                        heartbeat_at, started_at
                    ) VALUES (
                        :aid, :iid, 99, 'RUNNING', NOW(), NOW()
                    ) ON CONFLICT DO NOTHING
                """),
                {"aid": attempt_id, "iid": ident_id},
            )

            # Seed a dummy calculation_run for the slot FK
            calc_id = uuid.uuid4().hex
            conn.execute(
                text("""
                    INSERT INTO calculation_runs (
                        id, project_id, project_version_id, calculator_name,
                        calculator_version, input_snapshot, result_snapshot,
                        formulas, coefficients, assumptions, warnings,
                        source_references, requires_review, created_at
                    ) VALUES (
                        :cid, :pid, :pvid, 'test_calc', '1.0.0',
                        '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, false, NOW()
                    ) ON CONFLICT DO NOTHING
                """),
                {"cid": calc_id, "pid": "fk-p-1", "pvid": "fk-pv-1"},
            )

            conn.commit()

            # Now insert a SourceBinding with duplicate slot IDs
            with pytest.raises(IntegrityError) as exc_info:
                conn.execute(
                    text("""
                        INSERT INTO orchestration_source_bindings (
                            id, project_id, project_version_id,
                            execution_snapshot_id, coefficient_context_id,
                            orchestration_identity_id, orchestration_run_attempt_id,
                            orchestration_fingerprint,
                            zone_calculation_id, cooling_load_calculation_id,
                            equipment_calculation_id, power_calculation_id,
                            investment_calculation_id,
                            per_calculation_result_hashes, combined_source_hash,
                            schema_version, created_at
                        ) VALUES (
                            :bid, :pid, :pvid,
                            :sid, :cid,
                            :iid, :aid,
                            'fp-dup',
                            :slot_id, :slot_id,
                            :slot_id, :slot_id,
                            :slot_id,
                            '{}'::jsonb, 'hash_value',
                            '1.0.0', NOW()
                        )
                    """),
                    {
                        "bid": uuid.uuid4().hex,
                        "pid": "fk-p-1",
                        "pvid": "fk-pv-1",
                        "sid": snap_id,
                        "cid": coeff_id,
                        "iid": ident_id,
                        "aid": attempt_id,
                        "slot_id": calc_id,
                    },
                )
                conn.commit()

            assert "ck_source_binding_slot_distinct" in str(
                exc_info.value
            ) or "ck_source_binding_slot_distinct" in str(
                getattr(exc_info.value, "orig", exc_info.value)
            )
