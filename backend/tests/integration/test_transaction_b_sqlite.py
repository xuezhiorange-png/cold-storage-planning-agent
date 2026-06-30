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
    TransactionBFailure,
    VerificationReadPort,
)
from cold_storage.modules.orchestration.application.unit_of_work import (
    SqlAlchemyOrchestrationUnitOfWorkFactory,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
)
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
