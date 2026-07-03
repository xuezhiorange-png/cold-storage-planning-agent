"""Integration tests for orchestration Transaction B (five-stage calculator execution).

Uses real Alembic Head schema via ``alembic upgrade head`` for SQLite.

Covers:
- Success path: 5 CalculationRuns + 1 SourceBinding + COMPLETED attempt + outbox
- Rollback: calculator failure → rolled back, attempt → FAILED via terminal UoW
- Rollback: verifier failure → rolled back, attempt → FAILED via terminal UoW
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite Transaction B tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
    TransactionBBlocked,
    TransactionBFailure,
    VerificationReadPort,
)
from cold_storage.modules.orchestration.application.unit_of_work import (
    SqlAlchemyOrchestrationUnitOfWorkFactory,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
)
from cold_storage.modules.orchestration.domain.dag import ORCHESTRATION_STAGE_ORDER
from cold_storage.modules.orchestration.domain.errors import OrchestrationDomainError
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

BACKEND_DIR = Path(__file__).resolve().parents[2]

# ── Coefficient fixtures (must match Transaction A test exactly) ─────────────

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


class _FailingCalculatorPort:
    """CalculatorPort that raises on the first stage to trigger rollback."""

    def execute_stage(self, **kwargs: Any) -> StageExecutionResult:
        raise RuntimeError("Simulated calculator failure")


class _RealVersionPort(ProjectVersionReadPort):
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
                code="T001",
                name="Test Project",
                location="test",
                product_category="blueberry",
                status="active",
                current_version_number=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
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
def engine():
    """Create a SQLite DB and run Alembic upgrade head."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)

    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        db_path.unlink(missing_ok=True)
        pytest.fail(f"Alembic upgrade failed:\n{r.stderr}\n{r.stdout}")

    e = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(e, "connect")
    def _pragma(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    yield e
    e.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def calculator_port():
    """Default calculator port returning realistic results."""
    return _FakeCalculatorPort()


@pytest.fixture()
def service(session_factory, calculator_port):
    """Fully wired OrchestrationService with real repos + fake calculator."""
    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(session_factory)
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
        calculator_port=calculator_port,
        verification_read_port=SqlAlchemyVerificationReadPort(),
    )


def _run_transaction_a(service, session_factory, *, correlation_id: str = "corr-b"):
    """Seed project + run Transaction A → return PreflightAccepted result."""
    with session_factory() as s:
        _seed_project_and_version(s)
    return service.execute(_make_command(correlation_id=correlation_id))


def _load_identity_context(session_factory, identity_id: str) -> tuple[str, str, str]:
    """Load (execution_snapshot_id, coefficient_context_id, fingerprint) from identity record."""
    with session_factory() as s:
        identity = s.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == identity_id)
        ).scalar_one()
        return identity.execution_snapshot_id, identity.coefficient_context_id, identity.fingerprint


# ── Transaction B success path ──────────────────────────────────────────────


class TestTransactionBSuccessPath:
    """Full Transaction B: 5 CalculationRuns + SourceBinding + COMPLETED."""

    def test_five_calculation_runs_created(self, service, session_factory) -> None:
        result_a = _run_transaction_a(service, session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        result_b = service.execute_transaction_b(
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

        assert result_b.status == "COMPLETED"
        assert len(result_b.persisted_stages) == 5

        with session_factory() as s:
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

            for run in runs:
                assert run.orchestration_identity_id == result_a.identity_id
                assert run.orchestration_run_attempt_id == result_a.attempt_id
                assert run.execution_snapshot_id is not None
                assert run.coefficient_context_id is not None

    def test_source_binding_created(self, service, session_factory) -> None:
        result_a = _run_transaction_a(service, session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        service.execute_transaction_b(
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

        with session_factory() as s:
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
            assert binding.orchestration_fingerprint == orch_fp

    def test_attempt_transitioned_to_completed(self, service, session_factory) -> None:
        result_a = _run_transaction_a(service, session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        service.execute_transaction_b(
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

        with session_factory() as s:
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result_a.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "COMPLETED"
            assert attempt.completed_at is not None
            assert attempt.source_binding_id is not None

    def test_identity_authoritative_attempt_set(self, service, session_factory) -> None:
        result_a = _run_transaction_a(service, session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        service.execute_transaction_b(
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

        with session_factory() as s:
            identity = s.execute(
                select(OrchestrationIdentityRecord).where(
                    OrchestrationIdentityRecord.id == result_a.identity_id
                )
            ).scalar_one()
            assert identity.authoritative_attempt_id == result_a.attempt_id

    def test_completion_outbox_emitted(self, service, session_factory) -> None:
        result_a = _run_transaction_a(service, session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        service.execute_transaction_b(
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

        with session_factory() as s:
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

    def test_result_hashes_match(self, service, session_factory) -> None:
        """Verify stored result_hash matches the typed snapshot hash.

        The SourceBindingVerifier re-computes result hashes by re-parsing
        the typed snapshot from persisted data.  If verification passes,
        hashes are consistent.  We also verify non-null directly.
        """
        result_a = _run_transaction_a(service, session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        service.execute_transaction_b(
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

        with session_factory() as s:
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
                assert run.result_hash is not None
                assert len(run.result_hash) == 64, "SHA-256 hex digest length"
                assert run.input_hash is not None
                assert len(run.input_hash) == 64

    def test_orchestration_fingerprint_stored(self, service, session_factory) -> None:
        result_a = _run_transaction_a(service, session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        service.execute_transaction_b(
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

        with session_factory() as s:
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
                assert run.orchestration_fingerprint is not None
                assert run.orchestration_fingerprint == orch_fp

    def test_traceability_data_stored(self, service, session_factory) -> None:
        result_a = _run_transaction_a(service, session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        service.execute_transaction_b(
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

        with session_factory() as s:
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
                assert run.formulas[0]["formula_id"]  # has a real formula_id

                # Coefficients — non-empty
                assert run.coefficients is not None
                assert len(run.coefficients) >= 1
                assert run.coefficients[0]["code"]  # has a real code

                # Assumptions — non-empty
                assert run.assumptions is not None
                assert len(run.assumptions) >= 1
                assert run.assumptions[0]  # non-empty string

                # Warnings — non-empty
                assert run.warnings is not None
                assert len(run.warnings) >= 1
                assert run.warnings[0]["code"]  # has a real code

                # Source references — non-empty
                assert run.source_references is not None
                assert len(run.source_references) >= 1
                assert run.source_references[0]["source_type"]  # has a real type


# ── Transaction B rollback ──────────────────────────────────────────────────


class TestTransactionBRollback:
    """Calculator and verifier failures roll back Transaction B."""

    def test_calculator_failure_rolls_back(self, session_factory, engine) -> None:
        """CalculatorPort raises → primary UoW rolled back, attempt → FAILED."""
        # Build service with a failing calculator port
        uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(session_factory)
        coeff_port = MagicMock(spec=CoefficientResolutionPreflightPort)
        coeff_port.resolve.return_value = _make_resolved_coefficient()

        svc = OrchestrationService(
            uow_factory=uow_factory,
            request_repo=SqlAlchemyOrchestrationRequestRepository(),
            outbox_repo=SqlAlchemyAuditOutboxRepository(),
            snapshot_repo=SqlAlchemyExecutionSnapshotRepository(),
            coefficient_repo=SqlAlchemyCoefficientContextRepository(),
            identity_repo=SqlAlchemyOrchestrationIdentityRepository(),
            attempt_repo=SqlAlchemyOrchestrationAttemptRepository(),
            version_port=_RealVersionPort(),
            snapshot_port=MagicMock(spec=ExecutionSnapshotPreflightPort),
            coefficient_port=coeff_port,
            calc_run_repo=SqlAlchemyCalculationRunRepository(),
            source_binding_repo=SqlAlchemySourceBindingRepository(),
            calculator_port=_FailingCalculatorPort(),
            verification_read_port=SqlAlchemyVerificationReadPort(),
        )

        # Run Transaction A to get a valid RUNNING attempt
        with session_factory() as s:
            _seed_project_and_version(s)
        result_a = svc.execute(_make_command(correlation_id="calc-fail"))
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        # Transaction B should fail
        with pytest.raises((TransactionBFailure, RuntimeError)):
            svc.execute_transaction_b(
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

        with session_factory() as s:
            # Zero CalculationRuns (primary UoW rolled back)
            calc_count = (
                s.execute(
                    select(func.count())
                    .select_from(CalculationRunRecord)
                    .where(CalculationRunRecord.orchestration_run_attempt_id == result_a.attempt_id)
                )
            ).scalar()
            assert calc_count == 0

            # Zero SourceBindings
            binding_count = (
                s.execute(
                    select(func.count())
                    .select_from(SourceBindingRecord)
                    .where(SourceBindingRecord.orchestration_run_attempt_id == result_a.attempt_id)
                )
            ).scalar()
            assert binding_count == 0

            # Attempt transitioned to FAILED via terminal UoW
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result_a.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "FAILED"

            # Terminal outbox event emitted
            failed_events = (
                s.execute(
                    select(AuditOutboxRecord).where(
                        AuditOutboxRecord.attempt_id == result_a.attempt_id,
                        AuditOutboxRecord.event_type == "orchestration.attempt.failed",
                    )
                )
                .scalars()
                .all()
            )
            assert len(failed_events) == 1

    def test_verifier_failure_rolls_back(self, session_factory, engine) -> None:
        """VerificationReadPort raises during verification → rolled back."""
        # Build service with a verification port that raises
        uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(session_factory)
        coeff_port = MagicMock(spec=CoefficientResolutionPreflightPort)
        coeff_port.resolve.return_value = _make_resolved_coefficient()

        failing_verifier = MagicMock(spec=VerificationReadPort)
        failing_verifier.load_verification_state.side_effect = RuntimeError(
            "Simulated verification read failure"
        )

        svc = OrchestrationService(
            uow_factory=uow_factory,
            request_repo=SqlAlchemyOrchestrationRequestRepository(),
            outbox_repo=SqlAlchemyAuditOutboxRepository(),
            snapshot_repo=SqlAlchemyExecutionSnapshotRepository(),
            coefficient_repo=SqlAlchemyCoefficientContextRepository(),
            identity_repo=SqlAlchemyOrchestrationIdentityRepository(),
            attempt_repo=SqlAlchemyOrchestrationAttemptRepository(),
            version_port=_RealVersionPort(),
            snapshot_port=MagicMock(spec=ExecutionSnapshotPreflightPort),
            coefficient_port=coeff_port,
            calc_run_repo=SqlAlchemyCalculationRunRepository(),
            source_binding_repo=SqlAlchemySourceBindingRepository(),
            calculator_port=_FakeCalculatorPort(),
            verification_read_port=failing_verifier,
        )

        # Run Transaction A to get a valid RUNNING attempt
        with session_factory() as s:
            _seed_project_and_version(s)
        result_a = svc.execute(_make_command(correlation_id="ver-fail"))
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        # Transaction B should fail
        with pytest.raises((TransactionBFailure, RuntimeError)):
            svc.execute_transaction_b(
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

        with session_factory() as s:
            # Primary UoW rolled back → zero CalculationRuns
            calc_count = (
                s.execute(
                    select(func.count())
                    .select_from(CalculationRunRecord)
                    .where(CalculationRunRecord.orchestration_run_attempt_id == result_a.attempt_id)
                )
            ).scalar()
            assert calc_count == 0

            # Zero SourceBindings
            binding_count = (
                s.execute(
                    select(func.count())
                    .select_from(SourceBindingRecord)
                    .where(SourceBindingRecord.orchestration_run_attempt_id == result_a.attempt_id)
                )
            ).scalar()
            assert binding_count == 0

            # Attempt transitioned to FAILED via terminal UoW
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result_a.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "FAILED"


# ========================================================================
# Stage-level failure injection with PK-set zero-delta proof
# and terminal transaction atomicity tests
# ========================================================================


# ── Failure injection components ──────────────────────────────────────────


class _FailAfterStageCalculatorPort:
    """Executes stages up to and including *fail_after_stage* normally,
    raises ``RuntimeError`` on the **next** stage in the DAG order."""

    def __init__(self, fail_after_stage: str) -> None:
        self._fail_after_stage = fail_after_stage
        self._real = _FakeCalculatorPort()
        self._stages = list(ORCHESTRATION_STAGE_ORDER)

    def execute_stage(self, *, stage_name: str, **kwargs: Any) -> StageExecutionResult:
        current_idx = self._stages.index(stage_name)
        fail_idx = self._stages.index(self._fail_after_stage)
        if current_idx > fail_idx:
            raise RuntimeError(f"Simulated failure after stage {self._fail_after_stage!r}")
        return self._real.execute_stage(stage_name=stage_name, **kwargs)


class _FailingCalculationRunRepository:
    """Wraps real repo, raises after the *fail_after_n*-th ``add()`` call."""

    def __init__(
        self,
        real: SqlAlchemyCalculationRunRepository,
        *,
        fail_after_n: int = 0,
    ) -> None:
        self._real = real
        self._fail_after_n = fail_after_n
        self._add_count = 0

    def add(self, session: Any, /, **kwargs: Any) -> str:
        if self._add_count >= self._fail_after_n:
            raise RuntimeError("Simulated CalculationRun add failure")
        self._add_count += 1
        return self._real.add(session, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _FailingSourceBindingRepository:
    """Wraps real repo, raises ``TransactionBFailure`` on ``add()``."""

    def __init__(self, real: SqlAlchemySourceBindingRepository) -> None:
        self._real = real

    def add(self, session: Any, /, **kwargs: Any) -> str:
        raise TransactionBFailure(
            "TXB_SOURCE_BINDING_FAILED",
            "Simulated source binding failure",
            field="source_binding",
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _FailingAttemptCompletionRepository:
    """Wraps real repo, raises ``TransactionBFailure`` on ``complete_attempt_cas()``."""

    def __init__(self, real: SqlAlchemyOrchestrationAttemptRepository) -> None:
        self._real = real

    def complete_attempt_cas(self, session: Any, /, **kwargs: Any) -> bool:
        raise TransactionBFailure(
            "TXB_CAS_FAILED",
            "Simulated attempt CAS failure",
            field="attempt_status",
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _FailingIdentityAuthorityRepository:
    """Wraps real repo, raises ``TransactionBFailure`` on ``set_authoritative_attempt()``."""

    def __init__(self, real: SqlAlchemyOrchestrationIdentityRepository) -> None:
        self._real = real

    def set_authoritative_attempt(self, session: Any, /, **kwargs: Any) -> bool:
        raise TransactionBFailure(
            "TXB_CAS_IDENTITY_FAILED",
            "Simulated identity CAS failure",
            field="identity_authoritative_attempt",
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _FailingCompletionOutboxRepository:
    """Wraps real repo, raises ``TransactionBFailure`` on ``add()`` for completion events only."""

    def __init__(self, real: SqlAlchemyAuditOutboxRepository) -> None:
        self._real = real

    def add(self, session: Any, /, *, event_type: str, **kwargs: Any) -> str:
        if event_type == "orchestration.attempt.completed":
            raise TransactionBFailure(
                "TXB_OUTBOX_FAILED",
                "Simulated completion outbox failure",
                field="outbox",
            )
        return self._real.add(session, event_type=event_type, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _DomainErrorCalculatorPort:
    """Calculator that raises TransactionBBlocked (engineering domain blocker) on every stage."""

    def execute_stage(self, **kwargs: Any) -> StageExecutionResult:
        raise TransactionBBlocked(
            "DOMAIN_BLOCKER",
            "Engineering domain blocker: missing required parameter",
            field="execution_snapshot",
            details={"missing_key": "throughput_t"},
        )


# ── PK-set capture helpers ────────────────────────────────────────────────


def _capture_calc_run_pks(session_factory: Any) -> set[str]:
    """Capture the set of all CalculationRunRecord primary keys."""
    with session_factory() as s:
        return set(s.execute(select(CalculationRunRecord.id)).scalars().all())


def _capture_source_binding_pks(session_factory: Any) -> set[str]:
    """Capture the set of all SourceBindingRecord primary keys."""
    with session_factory() as s:
        return set(s.execute(select(SourceBindingRecord.id)).scalars().all())


def _capture_outbox_pks(session_factory: Any) -> set[str]:
    """Capture the set of all AuditOutboxRecord primary keys."""
    with session_factory() as s:
        return set(s.execute(select(AuditOutboxRecord.id)).scalars().all())


# ── Service builder helper ────────────────────────────────────────────────


def _make_txb_service(
    session_factory: Any,
    *,
    calculator_port: Any = None,
    source_binding_repo: Any = None,
    attempt_repo: Any = None,
    identity_repo: Any = None,
    outbox_repo: Any = None,
    verification_read_port: Any = None,
) -> OrchestrationService:
    """Build an ``OrchestrationService`` with optional repo/port overrides."""
    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(session_factory)
    coeff_port = MagicMock(spec=CoefficientResolutionPreflightPort)
    coeff_port.resolve.return_value = _make_resolved_coefficient()

    return OrchestrationService(
        uow_factory=uow_factory,
        request_repo=SqlAlchemyOrchestrationRequestRepository(),
        outbox_repo=outbox_repo or SqlAlchemyAuditOutboxRepository(),
        snapshot_repo=SqlAlchemyExecutionSnapshotRepository(),
        coefficient_repo=SqlAlchemyCoefficientContextRepository(),
        identity_repo=identity_repo or SqlAlchemyOrchestrationIdentityRepository(),
        attempt_repo=attempt_repo or SqlAlchemyOrchestrationAttemptRepository(),
        version_port=_RealVersionPort(),
        snapshot_port=MagicMock(spec=ExecutionSnapshotPreflightPort),
        coefficient_port=coeff_port,
        calc_run_repo=SqlAlchemyCalculationRunRepository(),
        source_binding_repo=source_binding_repo or SqlAlchemySourceBindingRepository(),
        calculator_port=calculator_port or _FakeCalculatorPort(),
        verification_read_port=verification_read_port or SqlAlchemyVerificationReadPort(),
    )


# ── Historical data seeder ────────────────────────────────────────────────


def _seed_historical_and_prepare_test(
    session_factory: Any,
) -> tuple[Any, str, str, str]:
    """Seed historical data via successful Transaction B, then prepare a new attempt.

    Returns ``(result_a_test, snap_id, coeff_id, orch_fp)`` for the failing test.
    """
    svc = _make_txb_service(session_factory)

    with session_factory() as s:
        _seed_project_and_version(s)

    # Historical: Transaction A + B (succeeds)
    result_a_hist = svc.execute(_make_command(correlation_id="hist"))
    snap_id_hist, coeff_id_hist, orch_fp_hist = _load_identity_context(
        session_factory, result_a_hist.identity_id
    )
    svc.execute_transaction_b(
        request_id=result_a_hist.request_id,
        project_id="p-1",
        project_version_id="pv-1",
        execution_snapshot_id=snap_id_hist,
        coefficient_context_id=coeff_id_hist,
        orchestration_identity_id=result_a_hist.identity_id,
        orchestration_attempt_id=result_a_hist.attempt_id,
        orchestration_fingerprint=orch_fp_hist,
        execution_snapshot={"throughput_t": "25.0"},
        coefficient_context={"coefficients": []},
    )

    # Prepare test attempt: Transaction A only
    result_a_test = svc.execute(_make_command(correlation_id="fail"))
    snap_id_test, coeff_id_test, orch_fp_test = _load_identity_context(
        session_factory, result_a_test.identity_id
    )

    return result_a_test, snap_id_test, coeff_id_test, orch_fp_test


# ── Test class 1: PK-set zero-delta proof ─────────────────────────────────


class TestTransactionBStageFailureRollbackPKSet:
    """Stage-level failure injection with PK-set zero-delta proof.

    For each test:
    - Seed historical data (successful Transaction B)
    - Capture PK sets before the failing call
    - Run failing Transaction B
    - Capture PK sets after
    - Assert: calc and binding PK sets unchanged
    - Assert: only new outbox is the terminal failure event
    - Assert: historical data untouched
    """

    def _run_failing_txb(
        self,
        session_factory: Any,
        svc: OrchestrationService,
        result_a: Any,
        snap_id: str,
        coeff_id: str,
        orch_fp: str,
    ) -> tuple[set[str], set[str], set[str], set[str], set[str], set[str]]:
        """Run failing Transaction B and return PK sets before/after."""
        calc_pks_before = _capture_calc_run_pks(session_factory)
        binding_pks_before = _capture_source_binding_pks(session_factory)
        outbox_pks_before = _capture_outbox_pks(session_factory)

        with pytest.raises((TransactionBFailure, RuntimeError, OrchestrationDomainError)):
            svc.execute_transaction_b(
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

        calc_pks_after = _capture_calc_run_pks(session_factory)
        binding_pks_after = _capture_source_binding_pks(session_factory)
        outbox_pks_after = _capture_outbox_pks(session_factory)

        return (
            calc_pks_before,
            calc_pks_after,
            binding_pks_before,
            binding_pks_after,
            outbox_pks_before,
            outbox_pks_after,
        )

    def _assert_pk_set_unchanged(
        self,
        calc_before: set[str],
        calc_after: set[str],
        binding_before: set[str],
        binding_after: set[str],
        outbox_before: set[str],
        outbox_after: set[str],
    ) -> None:
        """Assert PK-set zero-delta for calc/binding; only terminal failure outbox added."""
        assert calc_after == calc_before, "CalculationRun PK set must be unchanged"
        assert binding_after == binding_before, "SourceBinding PK set must be unchanged"
        new_outbox = outbox_after - outbox_before
        assert len(new_outbox) == 1, (
            f"Expected exactly 1 new outbox event (terminal failure), got {len(new_outbox)}"
        )

    # ── Tests 1-6: Calculator stage failures ──────────────────────────────

    def test_failure_before_zone_execution(self, session_factory, engine) -> None:
        """Calculator raises on zone -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(session_factory, calculator_port=_FailingCalculatorPort())

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    def test_failure_after_zone_persisted(self, session_factory, engine) -> None:
        """Fail after zone, before cooling_load -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            calculator_port=_FailAfterStageCalculatorPort("zone"),
        )

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    def test_failure_after_cooling_load_persisted(self, session_factory, engine) -> None:
        """Fail after cooling_load, before equipment -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            calculator_port=_FailAfterStageCalculatorPort("cooling_load"),
        )

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    def test_failure_after_equipment_persisted(self, session_factory, engine) -> None:
        """Fail after equipment, before power -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            calculator_port=_FailAfterStageCalculatorPort("equipment"),
        )

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    def test_failure_after_power_persisted(self, session_factory, engine) -> None:
        """Fail after power, before investment -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            calculator_port=_FailAfterStageCalculatorPort("power"),
        )

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    def test_failure_after_investment_persisted(self, session_factory, engine) -> None:
        """All 5 stages succeed, verifier fails -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        failing_verifier = MagicMock(spec=VerificationReadPort)
        failing_verifier.load_verification_state.side_effect = RuntimeError(
            "Simulated verification failure after investment"
        )
        svc = _make_txb_service(session_factory, verification_read_port=failing_verifier)

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    # ── Tests 7-10: Repository failures ───────────────────────────────────

    def test_failure_before_source_binding_insert(self, session_factory, engine) -> None:
        """SourceBinding repo raises on add() -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            source_binding_repo=_FailingSourceBindingRepository(
                SqlAlchemySourceBindingRepository()
            ),
        )

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    def test_failure_on_attempt_cas(self, session_factory, engine) -> None:
        """Attempt CAS fails -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            attempt_repo=_FailingAttemptCompletionRepository(
                SqlAlchemyOrchestrationAttemptRepository()
            ),
        )

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    def test_failure_on_identity_cas(self, session_factory, engine) -> None:
        """Identity CAS fails -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            identity_repo=_FailingIdentityAuthorityRepository(
                SqlAlchemyOrchestrationIdentityRepository()
            ),
        )

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    def test_failure_on_completion_outbox(self, session_factory, engine) -> None:
        """Completion outbox add fails -> PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            outbox_repo=_FailingCompletionOutboxRepository(SqlAlchemyAuditOutboxRepository()),
        )

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)

    # ── Test 11: Historical data preservation ─────────────────────────────

    def test_failure_preserves_historical_data(self, session_factory, engine) -> None:
        """Seed historical data, fail, verify historical data untouched."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)

        # Capture historical data
        hist_calc_pks = _capture_calc_run_pks(session_factory)
        hist_binding_pks = _capture_source_binding_pks(session_factory)
        hist_outbox_pks = _capture_outbox_pks(session_factory)

        assert len(hist_calc_pks) >= 5, "Historical 5 CalculationRuns expected"
        assert len(hist_binding_pks) >= 1, "Historical 1 SourceBinding expected"
        assert len(hist_outbox_pks) >= 1, "Historical outbox event expected"

        # Run failing Transaction B
        svc = _make_txb_service(
            session_factory,
            source_binding_repo=_FailingSourceBindingRepository(
                SqlAlchemySourceBindingRepository()
            ),
        )

        cb, ca, bb, ba, ob, oa = self._run_failing_txb(
            session_factory, svc, result_a, snap_id, coeff_id, orch_fp
        )

        # Assert historical data untouched
        assert hist_calc_pks.issubset(ca), "Historical CalculationRuns must be preserved"
        assert hist_binding_pks.issubset(ba), "Historical SourceBindings must be preserved"
        assert hist_outbox_pks.issubset(oa), "Historical outbox events must be preserved"

        # Assert PK-set zero-delta
        self._assert_pk_set_unchanged(cb, ca, bb, ba, ob, oa)


# ── Test class 2: Terminal atomicity ──────────────────────────────────────


class TestTransactionBTerminalAtomicity:
    """Terminal transaction atomicity tests."""

    def test_domain_blocker_produces_blocked_status(self, session_factory, engine) -> None:
        """Engineering domain error (TransactionBBlocked) -> attempt.status=BLOCKED,
        failure_code set, terminal outbox with orchestration.attempt.blocked."""
        svc = _make_txb_service(session_factory)

        with session_factory() as s:
            _seed_project_and_version(s)
        result_a = svc.execute(_make_command(correlation_id="domain-blocker"))
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        svc_fail = _make_txb_service(session_factory, calculator_port=_DomainErrorCalculatorPort())

        with pytest.raises(TransactionBBlocked):
            svc_fail.execute_transaction_b(
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

        with session_factory() as s:
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result_a.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "BLOCKED"
            assert attempt.failure_code is not None

            terminal_events = (
                s.execute(
                    select(AuditOutboxRecord).where(
                        AuditOutboxRecord.attempt_id == result_a.attempt_id,
                        AuditOutboxRecord.event_type == "orchestration.attempt.blocked",
                    )
                )
                .scalars()
                .all()
            )
            assert len(terminal_events) == 1

    def test_unexpected_calculator_failure_produces_failed(self, session_factory, engine) -> None:
        """RuntimeError from calculator -> attempt.status=FAILED."""
        svc = _make_txb_service(session_factory)

        with session_factory() as s:
            _seed_project_and_version(s)
        result_a = svc.execute(_make_command(correlation_id="unexpected-fail"))
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        svc_fail = _make_txb_service(session_factory, calculator_port=_FailingCalculatorPort())

        with pytest.raises(TransactionBFailure):
            svc_fail.execute_transaction_b(
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

        with session_factory() as s:
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result_a.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "FAILED"

    def test_verification_integrity_failure_produces_failed(self, session_factory, engine) -> None:
        """Verifier raises -> attempt.status=FAILED."""
        svc = _make_txb_service(session_factory)

        with session_factory() as s:
            _seed_project_and_version(s)
        result_a = svc.execute(_make_command(correlation_id="verifier-integrity-fail"))
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        failing_verifier = MagicMock(spec=VerificationReadPort)
        failing_verifier.load_verification_state.side_effect = RuntimeError(
            "Simulated verification integrity failure"
        )
        svc_fail = _make_txb_service(session_factory, verification_read_port=failing_verifier)

        with pytest.raises(TransactionBFailure):
            svc_fail.execute_transaction_b(
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

        with session_factory() as s:
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result_a.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "FAILED"

    def test_attempt_update_succeeds_but_outbox_flush_fails(self, session_factory, engine) -> None:
        """Completion outbox fails, terminal outbox succeeds -> attempt=FAILED."""
        svc = _make_txb_service(session_factory)

        with session_factory() as s:
            _seed_project_and_version(s)
        result_a = svc.execute(_make_command(correlation_id="outbox-flush-fail"))
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        # _FailingCompletionOutboxRepository: fails on completion, succeeds on failure
        real_outbox = SqlAlchemyAuditOutboxRepository()
        svc_fail = _make_txb_service(
            session_factory,
            outbox_repo=_FailingCompletionOutboxRepository(real_outbox),
        )

        with pytest.raises(TransactionBFailure):
            svc_fail.execute_transaction_b(
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

        with session_factory() as s:
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result_a.attempt_id
                )
            ).scalar_one()
            # Terminal state must be consistent: attempt is FAILED
            assert attempt.status == "FAILED"
            assert attempt.failure_code is not None

            # Terminal failure outbox event is emitted
            terminal_events = (
                s.execute(
                    select(AuditOutboxRecord).where(
                        AuditOutboxRecord.attempt_id == result_a.attempt_id,
                        AuditOutboxRecord.event_type == "orchestration.attempt.failed",
                    )
                )
                .scalars()
                .all()
            )
            assert len(terminal_events) == 1

    def test_attempt_row_missing(self, session_factory, engine) -> None:
        """attempt_id doesn't exist -> handled gracefully (exception raised, no crash)."""
        from sqlalchemy.exc import IntegrityError

        svc = _make_txb_service(session_factory)

        with session_factory() as s:
            _seed_project_and_version(s)
        result_a = svc.execute(_make_command(correlation_id="missing-attempt"))
        snap_id, coeff_id, orch_fp = _load_identity_context(session_factory, result_a.identity_id)

        fake_attempt_id = "non-existent-attempt-id"

        # The attempt check fails (not RUNNING), terminal UoW starts,
        # but outbox FK constraint fails for missing attempt row.
        # The important thing is that the error is raised (not swallowed)
        # and no crash occurs.
        with pytest.raises((TransactionBFailure, RuntimeError, IntegrityError)):
            svc.execute_transaction_b(
                request_id=result_a.request_id,
                project_id="p-1",
                project_version_id="pv-1",
                execution_snapshot_id=snap_id,
                coefficient_context_id=coeff_id,
                orchestration_identity_id=result_a.identity_id,
                orchestration_attempt_id=fake_attempt_id,
                orchestration_fingerprint=orch_fp,
                execution_snapshot={"throughput_t": "25.0"},
                coefficient_context={"coefficients": []},
            )

        # No crash — the exception was raised gracefully


# ========================================================================
# Stage-level rollback tests with PK-set zero-delta proof
# (enhanced: rejection outbox request_id match + count assertions)
#
# Each test covers one of the 10 canonical failure points:
#   1. after zone persisted
#   2. after cooling_load persisted
#   3. after equipment persisted
#   4. after power persisted
#   5. after investment persisted
#   6. before SourceBinding insert
#   7. after SourceBinding flush / before commit (CAS returns False)
#   8. attempt completion CAS failure (CAS raises)
#   9. identity authoritative CAS failure
#  10. completion outbox failure
#
# For every failure point the test:
#   - Seeds historical data (one successful Transaction A+B)
#   - Captures PK sets BEFORE the failing call
#   - Triggers the failure
#   - Captures PK sets AFTER
#   - Asserts after == before (zero delta) for CalculationRun, SourceBinding
#   - Asserts exactly 1 new outbox event (the rejection outbox)
#   - Asserts the rejection outbox event_type == "orchestration.attempt.failed"
#   - Asserts the rejection outbox request_id matches the command request_id
#   - Asserts the attempt status == FAILED
# ========================================================================


# ── Additional failure injection: CAS returns False (not raises) ────────


class _CasFalseAttemptRepository:
    """Wraps real repo, returns ``False`` from ``complete_attempt_cas()``.

    This exercises the ``if not cas_ok`` branch inside
    :meth:`TransactionBExecutor.execute` (step 6), which is reached
    **after** the SourceBinding has been flushed but **before** the
    primary UoW commits.
    """

    def __init__(self, real: SqlAlchemyOrchestrationAttemptRepository) -> None:
        self._real = real

    def complete_attempt_cas(self, session: Any, /, **kwargs: Any) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


# ── Outbox inspection helper ────────────────────────────────────────────


def _load_rejection_outbox_events(
    session_factory: Any,
    attempt_id: str,
) -> list[AuditOutboxRecord]:
    """Return all ``orchestration.attempt.failed`` outbox rows for *attempt_id*."""
    with session_factory() as s:
        return (
            s.execute(
                select(AuditOutboxRecord).where(
                    AuditOutboxRecord.attempt_id == attempt_id,
                    AuditOutboxRecord.event_type == "orchestration.attempt.failed",
                )
            )
            .scalars()
            .all()
        )


# ── New test class ──────────────────────────────────────────────────────


class TestTransactionBStageRollbackZeroDeltaProof:
    """Enhanced stage-level rollback tests with PK-set zero-delta proof.

    Each test covers one of the 10 canonical failure points and asserts:

    1. CalculationRun PK set unchanged (zero delta)
    2. SourceBinding PK set unchanged (zero delta)
    3. Exactly 1 new outbox event (the rejection outbox)
    4. Rejection outbox event_type == ``"orchestration.attempt.failed"``
    5. Rejection outbox ``request_id`` matches the command ``request_id``
    6. Attempt status == ``FAILED``
    """

    # ── Shared helper ───────────────────────────────────────────────

    def _run_and_assert(
        self,
        session_factory: Any,
        svc: OrchestrationService,
        result_a: Any,
        snap_id: str,
        coeff_id: str,
        orch_fp: str,
    ) -> None:
        """Run failing Transaction B, then assert PK-set zero-delta + outbox."""
        request_id = result_a.request_id

        # ── Capture PK sets BEFORE ──────────────────────────────────
        calc_pks_before = _capture_calc_run_pks(session_factory)
        binding_pks_before = _capture_source_binding_pks(session_factory)
        outbox_pks_before = _capture_outbox_pks(session_factory)

        # ── Trigger failure ─────────────────────────────────────────
        with pytest.raises((TransactionBFailure, RuntimeError, OrchestrationDomainError)):
            svc.execute_transaction_b(
                request_id=request_id,
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

        # ── Capture PK sets AFTER ───────────────────────────────────
        calc_pks_after = _capture_calc_run_pks(session_factory)
        binding_pks_after = _capture_source_binding_pks(session_factory)
        outbox_pks_after = _capture_outbox_pks(session_factory)

        # ── Assert: CalculationRun PK set zero delta ────────────────
        assert calc_pks_after == calc_pks_before, (
            "CalculationRun PK set must be unchanged after rollback"
        )

        # ── Assert: SourceBinding PK set zero delta ─────────────────
        assert binding_pks_after == binding_pks_before, (
            "SourceBinding PK set must be unchanged after rollback"
        )

        # ── Assert: exactly 1 new outbox event ──────────────────────
        new_outbox_pks = outbox_pks_after - outbox_pks_before
        assert len(new_outbox_pks) == 1, (
            f"Expected exactly 1 new outbox event (rejection), got {len(new_outbox_pks)}"
        )

        # ── Assert: rejection outbox event details ──────────────────
        rejection_events = _load_rejection_outbox_events(session_factory, result_a.attempt_id)
        assert len(rejection_events) == 1, (
            f"Expected 1 rejection outbox for attempt, got {len(rejection_events)}"
        )
        rejection = rejection_events[0]
        assert rejection.event_type == "orchestration.attempt.failed"
        assert rejection.request_id == request_id, (
            f"Rejection outbox request_id {rejection.request_id!r} "
            f"must match command request_id {request_id!r}"
        )
        assert rejection.attempt_id == result_a.attempt_id

        # ── Assert: attempt status is FAILED ────────────────────────
        with session_factory() as s:
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result_a.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "FAILED"

    # ── 1. Failure after zone persisted ─────────────────────────────

    def test_01_failure_after_zone_pk_set_proof(self, session_factory, engine) -> None:
        """Failure after zone stage → PK-set unchanged, rejection outbox verified."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            calculator_port=_FailAfterStageCalculatorPort("zone"),
        )
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)

    # ── 2. Failure after cooling_load persisted ─────────────────────

    def test_02_failure_after_cooling_load_pk_set_proof(self, session_factory, engine) -> None:
        """Failure after cooling_load stage → PK-set unchanged, rejection outbox verified."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            calculator_port=_FailAfterStageCalculatorPort("cooling_load"),
        )
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)

    # ── 3. Failure after equipment persisted ────────────────────────

    def test_03_failure_after_equipment_pk_set_proof(self, session_factory, engine) -> None:
        """Failure after equipment stage → PK-set unchanged, rejection outbox verified."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            calculator_port=_FailAfterStageCalculatorPort("equipment"),
        )
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)

    # ── 4. Failure after power persisted ────────────────────────────

    def test_04_failure_after_power_pk_set_proof(self, session_factory, engine) -> None:
        """Failure after power stage → PK-set unchanged, rejection outbox verified."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            calculator_port=_FailAfterStageCalculatorPort("power"),
        )
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)

    # ── 5. Failure after investment persisted ───────────────────────

    def test_05_failure_after_investment_pk_set_proof(self, session_factory, engine) -> None:
        """Failure after investment stage (verifier fails) → PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        failing_verifier = MagicMock(spec=VerificationReadPort)
        failing_verifier.load_verification_state.side_effect = RuntimeError(
            "Simulated verification failure after investment"
        )
        svc = _make_txb_service(session_factory, verification_read_port=failing_verifier)
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)

    # ── 6. Before SourceBinding insert ──────────────────────────────

    def test_06_failure_before_source_binding_insert_pk_set_proof(
        self, session_factory, engine
    ) -> None:
        """SourceBinding add() raises → PK-set unchanged, rejection outbox verified."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            source_binding_repo=_FailingSourceBindingRepository(
                SqlAlchemySourceBindingRepository()
            ),
        )
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)

    # ── 7. After SourceBinding flush / before commit (CAS returns False) ──

    def test_07_failure_after_source_binding_flush_pk_set_proof(
        self, session_factory, engine
    ) -> None:
        """SourceBinding flushed, attempt CAS returns False → PK-set unchanged.

        The SourceBinding ``add()`` + ``flush()`` succeed inside the primary
        UoW, but ``complete_attempt_cas()`` returns ``False`` (CAS mismatch),
        causing the executor to raise ``TransactionBFailure``.  The entire
        primary UoW is rolled back, so no new CalculationRun, SourceBinding,
        or outbox rows persist.
        """
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            attempt_repo=_CasFalseAttemptRepository(SqlAlchemyOrchestrationAttemptRepository()),
        )
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)

    # ── 8. Attempt completion CAS failure (raises) ──────────────────

    def test_08_failure_on_attempt_cas_pk_set_proof(self, session_factory, engine) -> None:
        """Attempt CAS raises TransactionBFailure → PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            attempt_repo=_FailingAttemptCompletionRepository(
                SqlAlchemyOrchestrationAttemptRepository()
            ),
        )
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)

    # ── 9. Identity authoritative CAS failure ───────────────────────

    def test_09_failure_on_identity_cas_pk_set_proof(self, session_factory, engine) -> None:
        """Identity CAS raises TransactionBFailure → PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            identity_repo=_FailingIdentityAuthorityRepository(
                SqlAlchemyOrchestrationIdentityRepository()
            ),
        )
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)

    # ── 10. Completion outbox failure ───────────────────────────────

    def test_10_failure_on_completion_outbox_pk_set_proof(self, session_factory, engine) -> None:
        """Completion outbox add fails → PK-set unchanged."""
        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)
        svc = _make_txb_service(
            session_factory,
            outbox_repo=_FailingCompletionOutboxRepository(SqlAlchemyAuditOutboxRepository()),
        )
        self._run_and_assert(session_factory, svc, result_a, snap_id, coeff_id, orch_fp)


# ═════════════════════════════════════════════════════════════════════════════
# P0-2: AttemptTerminalDisposition enum authority tests
# ═════════════════════════════════════════════════════════════════════════════


class TestTerminalDispositionEnumAuthority:
    """Verify that AttemptTerminalDisposition is the sole authority for
    terminal status and event type mapping."""

    def test_blocked_disposition_maps_to_blocked_status_and_event(
        self, session_factory, engine
    ) -> None:
        """TransactionBBlocked.terminal_disposition == BLOCKED maps to
        BLOCKED status and orchestration.attempt.blocked event."""
        from cold_storage.modules.orchestration.domain.errors import (
            AttemptTerminalDisposition,
        )

        svc = _make_txb_service(session_factory)
        assert (
            svc._TERMINAL_STATUS_BY_DISPOSITION[AttemptTerminalDisposition.BLOCKED].value
            == "BLOCKED"
        )
        assert (
            svc._TERMINAL_EVENT_BY_DISPOSITION[AttemptTerminalDisposition.BLOCKED]
            == "orchestration.attempt.blocked"
        )

    def test_failed_disposition_maps_to_failed_status_and_event(
        self, session_factory, engine
    ) -> None:
        """AttemptTerminalDisposition.FAILED maps to FAILED status and
        orchestration.attempt.failed event."""
        from cold_storage.modules.orchestration.domain.errors import (
            AttemptTerminalDisposition,
        )

        svc = _make_txb_service(session_factory)
        assert (
            svc._TERMINAL_STATUS_BY_DISPOSITION[AttemptTerminalDisposition.FAILED].value == "FAILED"
        )
        assert (
            svc._TERMINAL_EVENT_BY_DISPOSITION[AttemptTerminalDisposition.FAILED]
            == "orchestration.attempt.failed"
        )

    def test_terminal_method_rejects_raw_string_disposition(self, session_factory, engine) -> None:
        """_transaction_b_terminal raises TypeError for raw string."""
        svc = _make_txb_service(session_factory)
        exc = TransactionBFailure("TEST_CODE", "test", field="test")
        with pytest.raises(TypeError, match="AttemptTerminalDisposition"):
            svc._transaction_b_terminal(
                attempt_id="x",
                request_id="x",
                identity_id="x",
                exc=exc,
                disposition="BLOCKED",  # type: ignore[arg-type]
                actor="test-actor",
                correlation_id="test-corr",
                occurred_at=datetime.now(UTC),
            )

    def test_transaction_b_blocked_exposes_enum_disposition(self) -> None:
        """TransactionBBlocked.terminal_disposition is the BLOCKED enum."""
        from cold_storage.modules.orchestration.domain.errors import (
            AttemptTerminalDisposition,
        )

        exc = TransactionBBlocked("BLOCKER", "blocked", field="test")
        assert exc.terminal_disposition is AttemptTerminalDisposition.BLOCKED

    def test_transaction_b_failure_exposes_enum_disposition(self) -> None:
        """TransactionBFailure.terminal_disposition is the FAILED enum."""
        from cold_storage.modules.orchestration.domain.errors import (
            AttemptTerminalDisposition,
        )

        exc = TransactionBFailure("FAIL", "failed", field="test")
        assert exc.terminal_disposition is AttemptTerminalDisposition.FAILED

    def test_terminal_event_type_cannot_diverge_from_status(self, session_factory, engine) -> None:
        """Exhaustive mapping ensures event_type and status always agree."""
        from cold_storage.modules.orchestration.domain.contracts import (
            AttemptStatus,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            AttemptTerminalDisposition,
        )

        svc = _make_txb_service(session_factory)
        expected_events = {
            AttemptTerminalDisposition.BLOCKED: "orchestration.attempt.blocked",
            AttemptTerminalDisposition.FAILED: "orchestration.attempt.failed",
        }
        expected_statuses = {
            AttemptTerminalDisposition.BLOCKED: AttemptStatus.BLOCKED,
            AttemptTerminalDisposition.FAILED: AttemptStatus.FAILED,
        }
        for d in AttemptTerminalDisposition:
            assert svc._TERMINAL_EVENT_BY_DISPOSITION[d] == expected_events[d]
            assert svc._TERMINAL_STATUS_BY_DISPOSITION[d] == expected_statuses[d]


# ═════════════════════════════════════════════════════════════════════════════
# P0-1: Guarded terminal CAS tests (SQLite)
# ═════════════════════════════════════════════════════════════════════════════


class TestGuardedTerminalCAS:
    """Verify the guarded terminal CAS in SqlAlchemyAttemptRepository."""

    def test_transitioned_on_running_attempt(self, session_factory, engine) -> None:
        """CAS transition of RUNNING attempt returns TRANSITIONED."""
        from cold_storage.modules.orchestration.application.ports import (
            TerminalTransitionOutcome,
        )
        from cold_storage.modules.orchestration.domain.contracts import (
            AttemptStatus,
        )

        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)

        with session_factory() as session:
            row = session.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.identity_id == result_a.identity_id,
                    OrchestrationRunAttemptRecord.status == "RUNNING",
                )
            ).scalar_one_or_none()
            attempt_id = row.id

            repo = SqlAlchemyOrchestrationAttemptRepository()
            result = repo.transition_running_to_terminal(
                session,
                attempt_id=attempt_id,
                identity_id=result_a.identity_id,
                target_status=AttemptStatus.FAILED,
                failure_code="TEST",
                failure_details={"test": True},
                completed_at=datetime.now(UTC),
            )
            assert result.outcome == TerminalTransitionOutcome.TRANSITIONED
            session.commit()

    def test_already_completed_on_winner(self, session_factory, engine) -> None:
        """CAS on already-COMPLETED attempt returns ALREADY_COMPLETED."""
        from cold_storage.modules.orchestration.application.ports import (
            TerminalTransitionOutcome,
        )
        from cold_storage.modules.orchestration.domain.contracts import (
            AttemptStatus,
        )

        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)

        with session_factory() as session:
            row = session.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.identity_id == result_a.identity_id,
                    OrchestrationRunAttemptRecord.status == "RUNNING",
                )
            ).scalar_one_or_none()
            attempt_id = row.id
            identity_id = result_a.identity_id

            repo = SqlAlchemyOrchestrationAttemptRepository()
            repo.update_status(
                session,
                attempt_id,
                status=AttemptStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            session.commit()

            result = repo.transition_running_to_terminal(
                session,
                attempt_id=attempt_id,
                identity_id=identity_id,
                target_status=AttemptStatus.FAILED,
                failure_code="LOSER",
                failure_details={},
                completed_at=datetime.now(UTC),
            )
            assert result.outcome == TerminalTransitionOutcome.ALREADY_COMPLETED
            assert result.observed_status == AttemptStatus.COMPLETED

    def test_already_terminal_on_blocked(self, session_factory, engine) -> None:
        """CAS on already-BLOCKED attempt returns ALREADY_TERMINAL."""
        from cold_storage.modules.orchestration.application.ports import (
            TerminalTransitionOutcome,
        )
        from cold_storage.modules.orchestration.domain.contracts import (
            AttemptStatus,
        )

        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)

        with session_factory() as session:
            row = session.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.identity_id == result_a.identity_id,
                    OrchestrationRunAttemptRecord.status == "RUNNING",
                )
            ).scalar_one_or_none()
            attempt_id = row.id

            repo = SqlAlchemyOrchestrationAttemptRepository()
            repo.update_status(
                session,
                attempt_id,
                status=AttemptStatus.BLOCKED,
                failure_code="FIRST",
                failure_details={},
            )
            session.commit()

            result = repo.transition_running_to_terminal(
                session,
                attempt_id=attempt_id,
                identity_id=result_a.identity_id,
                target_status=AttemptStatus.FAILED,
                failure_code="SECOND",
                failure_details={},
                completed_at=datetime.now(UTC),
            )
            assert result.outcome == TerminalTransitionOutcome.ALREADY_TERMINAL
            assert result.observed_status == AttemptStatus.BLOCKED

    def test_not_found_for_missing_attempt(self, session_factory, engine) -> None:
        """CAS on non-existent attempt returns NOT_FOUND."""
        from cold_storage.modules.orchestration.application.ports import (
            TerminalTransitionOutcome,
        )
        from cold_storage.modules.orchestration.domain.contracts import (
            AttemptStatus,
        )

        with session_factory() as session:
            repo = SqlAlchemyOrchestrationAttemptRepository()
            result = repo.transition_running_to_terminal(
                session,
                attempt_id="nonexistent-id",
                identity_id="nonexistent-identity",
                target_status=AttemptStatus.FAILED,
                failure_code="TEST",
                failure_details={},
                completed_at=datetime.now(UTC),
            )
            assert result.outcome == TerminalTransitionOutcome.NOT_FOUND

    def test_state_conflict_on_identity_mismatch(self, session_factory, engine) -> None:
        """CAS with wrong identity_id returns STATE_CONFLICT."""
        from cold_storage.modules.orchestration.application.ports import (
            TerminalTransitionOutcome,
        )
        from cold_storage.modules.orchestration.domain.contracts import (
            AttemptStatus,
        )

        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)

        with session_factory() as session:
            row = session.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.identity_id == result_a.identity_id,
                    OrchestrationRunAttemptRecord.status == "RUNNING",
                )
            ).scalar_one_or_none()
            attempt_id = row.id

            repo = SqlAlchemyOrchestrationAttemptRepository()
            result = repo.transition_running_to_terminal(
                session,
                attempt_id=attempt_id,
                identity_id="wrong-identity",
                target_status=AttemptStatus.FAILED,
                failure_code="TEST",
                failure_details={},
                completed_at=datetime.now(UTC),
            )
            assert result.outcome == TerminalTransitionOutcome.STATE_CONFLICT
            assert result.observed_status == AttemptStatus.RUNNING

    def test_no_outbox_on_already_completed(self, session_factory, engine) -> None:
        """Terminal CAS on ALREADY_COMPLETED must not write outbox."""
        from cold_storage.modules.orchestration.domain.contracts import (
            AttemptStatus,
        )

        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)

        with session_factory() as session:
            row = session.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.identity_id == result_a.identity_id,
                    OrchestrationRunAttemptRecord.status == "RUNNING",
                )
            ).scalar_one_or_none()
            attempt_id = row.id

            repo = SqlAlchemyOrchestrationAttemptRepository()
            repo.update_status(
                session,
                attempt_id,
                status=AttemptStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            session.commit()

            before_count = session.execute(
                select(func.count()).select_from(AuditOutboxRecord)
            ).scalar()

            repo.transition_running_to_terminal(
                session,
                attempt_id=attempt_id,
                identity_id=result_a.identity_id,
                target_status=AttemptStatus.FAILED,
                failure_code="LOSER",
                failure_details={},
                completed_at=datetime.now(UTC),
            )
            session.flush()

            after_count = session.execute(
                select(func.count()).select_from(AuditOutboxRecord)
            ).scalar()
            assert after_count == before_count

    def test_terminal_loser_cannot_overwrite_completed_winner(
        self, session_factory, engine
    ) -> None:
        """Winner completes, loser fails.  Loser CAS returns ALREADY_COMPLETED.
        Attempt stays COMPLETED with winner's source_binding_id."""
        from cold_storage.modules.orchestration.application.ports import (
            TerminalTransitionOutcome,
        )
        from cold_storage.modules.orchestration.domain.contracts import (
            AttemptStatus,
        )

        result_a, snap_id, coeff_id, orch_fp = _seed_historical_and_prepare_test(session_factory)

        with session_factory() as session:
            row = session.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.identity_id == result_a.identity_id,
                    OrchestrationRunAttemptRecord.status == "RUNNING",
                )
            ).scalar_one_or_none()
            attempt_id = row.id

            repo = SqlAlchemyOrchestrationAttemptRepository()
            # Complete the attempt (no source_binding_id since the binding
            # doesn't actually exist in the test DB)
            repo.update_status(
                session,
                attempt_id,
                status=AttemptStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )
            session.commit()

            result = repo.transition_running_to_terminal(
                session,
                attempt_id=attempt_id,
                identity_id=result_a.identity_id,
                target_status=AttemptStatus.FAILED,
                failure_code="LOSER_FAILED",
                failure_details={"reason": "integrity"},
                completed_at=datetime.now(UTC),
            )
            assert result.outcome == TerminalTransitionOutcome.ALREADY_COMPLETED

            final = session.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == attempt_id
                )
            ).scalar_one()
            assert final.status == "COMPLETED"
            assert final.source_binding_id is None
            assert final.failure_code is None
