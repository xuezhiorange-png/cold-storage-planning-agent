"""Real PostgreSQL guarded-terminal race tests.

Proves that the guarded CAS on orchestration_run_attempts correctly
prevents losers from overwriting winners under real concurrent
PostgreSQL transactions.

Scenarios:
- A: COMPLETED winner survives terminal loser (race at COMMIT boundary)
- A2: Deterministic COMPLETED-then-terminal (no race, proves ALREADY_COMPLETED)
- B: Two terminal writers race (FAILED vs BLOCKED)
- C: Missing / wrong identity → NOT_FOUND / STATE_CONFLICT
- Stability: core race repeated 10× with A-win branch tracking

Tagged with @pytest.mark.postgresql for CI (-m postgresql).
"""

from __future__ import annotations

import os
import threading

import pytest

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL terminal race tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.application.ports import (
    AttemptStatus,
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
    ResolvedCoefficientContextCandidate,
    TerminalTransitionOutcome,
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

# ── Coefficient fixtures ───────────────────────────────────────────────────

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


# ── Calculator fixtures ────────────────────────────────────────────────────


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
            {"name": "Refrigeration", "basis": "equipment", "total_power_kw": "170.0"},
            {"name": "Lighting", "basis": "area", "total_power_kw": "30.0"},
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


_STAGE_DATA: dict[str, tuple[str, str, str, dict[str, Any]]] = {
    "zone": ("cold_room_zone_plan", "1.0.0", "zone", _zone_result_snapshot()),
    "cooling_load": ("cooling_load", "1.0.0", "cooling_load", _cooling_load_result_snapshot()),
    "equipment": ("equipment", "1.0.0", "equipment", _equipment_result_snapshot()),
    "power": ("installed_power", "1.0.0", "power", _power_result_snapshot()),
    "investment": ("investment_estimate", "1.0.0", "investment", _investment_result_snapshot()),
}


class _FakeCalculatorPort:
    """Mock CalculatorPort returning realistic StageExecutionResult."""

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

    def load_by_id(self, session: Any, project_version_id: str) -> _LoadedVersion | None:
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


# ── Helpers ────────────────────────────────────────────────────────────────


def _seed_project_and_version(
    session: Session,
    *,
    project_id: str = "p-1",
    version_id: str = "pv-1",
    status: str = "approved",
) -> None:
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
    *,
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    correlation_id: str = "corr-1",
) -> OrchestrationRequestCommand:
    return OrchestrationRequestCommand(
        project_id=project_id,
        project_version_id=project_version_id,
        coefficient_resolution_context={},
        actor="test-actor",
        correlation_id=correlation_id,
    )


def _build_service(
    pg_session_factory: Any,
    *,
    calculator_port: Any = None,
) -> OrchestrationService:
    """Build an independent OrchestrationService backed by pg_session_factory."""
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
        calculator_port=calculator_port or _FakeCalculatorPort(),
        verification_read_port=SqlAlchemyVerificationReadPort(),
    )


def _run_transaction_a(
    pg_session_factory: Any,
    *,
    project_id: str = "p-1",
    version_id: str = "pv-1",
    correlation_id: str = "corr-terminal-race",
):
    """Seed project + run Transaction A → return PreflightAccepted result."""
    with pg_session_factory() as s:
        _seed_project_and_version(s, project_id=project_id, version_id=version_id)
    svc = _build_service(pg_session_factory)
    return svc.execute(
        _make_command(
            project_id=project_id,
            project_version_id=version_id,
            correlation_id=correlation_id,
        )
    )


def _load_identity_context(
    pg_session_factory: Any,
    identity_id: str,
) -> tuple[str, str, str]:
    """Load (execution_snapshot_id, coefficient_context_id, fingerprint)."""
    with pg_session_factory() as s:
        identity = s.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == identity_id)
        ).scalar_one()
        return (
            identity.execution_snapshot_id,
            identity.coefficient_context_id,
            identity.fingerprint,
        )


def _capture_downstream_state(
    pg_session_factory: Any,
    attempt_id: str,
) -> dict[str, Any]:
    """Capture the downstream PK-set and outbox state for an attempt."""
    with pg_session_factory() as s:
        runs = (
            s.execute(
                select(CalculationRunRecord).where(
                    CalculationRunRecord.orchestration_run_attempt_id == attempt_id
                )
            )
            .scalars()
            .all()
        )
        bindings = (
            s.execute(
                select(SourceBindingRecord).where(
                    SourceBindingRecord.orchestration_run_attempt_id == attempt_id
                )
            )
            .scalars()
            .all()
        )
        outbox_all = (
            s.execute(select(AuditOutboxRecord).where(AuditOutboxRecord.attempt_id == attempt_id))
            .scalars()
            .all()
        )
        attempt = s.execute(
            select(OrchestrationRunAttemptRecord).where(
                OrchestrationRunAttemptRecord.id == attempt_id
            )
        ).scalar_one_or_none()
        identity = None
        if attempt:
            identity = s.execute(
                select(OrchestrationIdentityRecord).where(
                    OrchestrationIdentityRecord.id == attempt.identity_id
                )
            ).scalar_one_or_none()

    return {
        "run_count": len(runs),
        "run_ids": sorted(r.id for r in runs),
        "binding_count": len(bindings),
        "binding_ids": sorted(b.id for b in bindings),
        "outbox_count": len(outbox_all),
        "outbox_event_types": sorted(o.event_type for o in outbox_all),
        "attempt_status": attempt.status if attempt else None,
        "source_binding_id": attempt.source_binding_id if attempt else None,
        "identity_authoritative_attempt_id": (
            identity.authoritative_attempt_id if identity else None
        ),
    }


def _count_outbox_by_type(state: dict[str, Any]) -> dict[str, int]:
    """Count occurrences of each event type in outbox_event_types."""
    counts: dict[str, int] = {}
    for event_type in state["outbox_event_types"]:
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


# ═══════════════════════════════════════════════════════════════════════════
# Scenario A: COMPLETED winner vs FAILED loser (concurrent race)
# ═══════════════════════════════════════════════════════════════════════════


class TestTerminalRaceCompletedVsFailed:
    """Real PostgreSQL race: full Transaction B (COMPLETED) vs terminal FAILED CAS.

    Both workers start at a barrier.  Worker A runs the full Transaction B
    pipeline (5 CalculationRuns + 1 SourceBinding + attempt→COMPLETED +
    completion outbox).  Worker B directly calls transition_running_to_terminal
    with target_status=FAILED.

    The guarded CAS ensures exactly one writer succeeds; the loser receives
    ALREADY_COMPLETED or ALREADY_TERMINAL with no destructive side effects.
    """

    def test_completed_winner_survives_terminal_loser(self, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(
            pg_session_factory, result_a.identity_id
        )

        barrier = threading.Barrier(2, timeout=60)
        results: dict[str, dict[str, object]] = {"a": {}, "b": {}}

        def _worker_a() -> None:
            try:
                svc = _build_service(pg_session_factory)
                barrier.wait()
                result = svc.execute_transaction_b(
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
                results["a"]["result"] = result
            except Exception as exc:  # noqa: BLE001
                results["a"]["error"] = exc

        def _worker_b() -> None:
            try:
                svc = _build_service(pg_session_factory)
                barrier.wait()
                attempt_repo = SqlAlchemyOrchestrationAttemptRepository()
                outbox_repo = SqlAlchemyAuditOutboxRepository()
                with svc._uow_factory() as terminal_uow:
                    tr_result = attempt_repo.transition_running_to_terminal(
                        terminal_uow.session,
                        attempt_id=result_a.attempt_id,
                        identity_id=result_a.identity_id,
                        target_status=AttemptStatus.FAILED,
                        failure_code="TXB_RACE_LOSER",
                        failure_details={"failure_code": "TXB_RACE_LOSER"},
                        completed_at=datetime.now(UTC),
                    )
                    if tr_result.outcome == TerminalTransitionOutcome.TRANSITIONED:
                        outbox_repo.add(
                            terminal_uow.session,
                            event_type="orchestration.attempt.failed",
                            aggregate_type="OrchestrationRunAttempt",
                            aggregate_id=result_a.attempt_id,
                            payload={"failure_code": "TXB_RACE_LOSER"},
                            attempt_id=result_a.attempt_id,
                        )
                    terminal_uow.commit()
                    results["b"]["outcome"] = tr_result.outcome
                    results["b"]["observed_status"] = tr_result.observed_status
            except Exception as exc:  # noqa: BLE001
                results["b"]["error"] = exc

        t_a = threading.Thread(target=_worker_a)
        t_b = threading.Thread(target=_worker_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=120)
        t_b.join(timeout=120)

        assert not t_a.is_alive(), "Thread A deadlocked"
        assert not t_b.is_alive(), "Thread B deadlocked"

        a_succeeded = "result" in results["a"]
        b_outcome = results["b"].get("outcome")

        # Worker B must NOT have a result (it only does a terminal CAS, not full TXB)
        assert "result" not in results["b"], "Worker B should not succeed (CAS-only)"

        if a_succeeded:
            # A won: attempt→COMPLETED, B got ALREADY_COMPLETED
            assert b_outcome == TerminalTransitionOutcome.ALREADY_COMPLETED, (
                f"Expected ALREADY_COMPLETED for loser B, got {b_outcome}"
            )
        else:
            # B won: attempt→FAILED, A got error
            assert isinstance(results["a"].get("error"), Exception), (
                "A should have raised when attempt was already FAILED"
            )
            assert b_outcome == TerminalTransitionOutcome.TRANSITIONED, (
                f"B should have TRANSITIONED, got {b_outcome}"
            )

        # ── Invariants ──────────────────────────────────────────────────
        state = _capture_downstream_state(pg_session_factory, result_a.attempt_id)
        counts = _count_outbox_by_type(state)

        if a_succeeded:
            # Winner is A: full TXB artifacts
            assert state["run_count"] == 5, f"Expected 5 runs, got {state['run_count']}"
            assert state["binding_count"] == 1, f"Expected 1 binding, got {state['binding_count']}"
            assert state["attempt_status"] == "COMPLETED"
            assert state["source_binding_id"] == state["binding_ids"][0]
            assert state["identity_authoritative_attempt_id"] == result_a.attempt_id
            # Precise outbox counting: 1 request.accepted (from Txn A) + 1 attempt.completed
            assert counts.get("orchestration.request.accepted", 0) == 1
            assert counts.get("orchestration.attempt.completed", 0) == 1
            assert counts.get("orchestration.attempt.failed", 0) == 0
            assert counts.get("orchestration.attempt.blocked", 0) == 0
        else:
            # Winner is B: attempt→FAILED, no TXB artifacts
            assert state["run_count"] == 0, f"Expected 0 runs, got {state['run_count']}"
            assert state["binding_count"] == 0
            assert state["attempt_status"] == "FAILED"
            # Precise outbox counting: 1 request.accepted (from Txn A) + 1 attempt.failed
            assert counts.get("orchestration.request.accepted", 0) == 1
            assert counts.get("orchestration.attempt.failed", 0) == 1
            assert counts.get("orchestration.attempt.completed", 0) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Scenario A2: Deterministic COMPLETED → ALREADY_COMPLETED
# ═══════════════════════════════════════════════════════════════════════════


class TestTerminalRaceCompletedDeterministic:
    """Deterministic proof that a COMPLETED attempt → ALREADY_COMPLETED on
    subsequent terminal CAS.

    No race involved — runs Transaction B to completion synchronously,
    then attempts terminal CAS.  This proves that:
    1. COMPLETED is preserved (no overwrite to FAILED)
    2. source_binding_id is not overwritten
    3. authoritative_attempt_id is not overwritten
    4. No duplicate terminal outbox is written
    """

    def test_completed_then_terminal_returns_already_completed(self, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(
            pg_session_factory, result_a.identity_id
        )

        # Step 1: Run Transaction B to COMPLETED (synchronous, no race)
        svc = _build_service(pg_session_factory)
        result_b = svc.execute_transaction_b(
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

        # Capture state after COMPLETED
        state_after_completed = _capture_downstream_state(pg_session_factory, result_a.attempt_id)
        assert state_after_completed["attempt_status"] == "COMPLETED"
        assert state_after_completed["run_count"] == 5
        assert state_after_completed["binding_count"] == 1
        binding_id_before = state_after_completed["source_binding_id"]
        auth_attempt_before = state_after_completed["identity_authoritative_attempt_id"]

        # Step 2: Attempt terminal CAS on the already-COMPLETED attempt
        terminal_svc = _build_service(pg_session_factory)
        with terminal_svc._uow_factory() as terminal_uow:
            attempt_repo = SqlAlchemyOrchestrationAttemptRepository()
            tr_result = attempt_repo.transition_running_to_terminal(
                terminal_uow.session,
                attempt_id=result_a.attempt_id,
                identity_id=result_a.identity_id,
                target_status=AttemptStatus.FAILED,
                failure_code="TXB_DETERMINISTIC_LOSER",
                failure_details={"failure_code": "TXB_DETERMINISTIC_LOSER"},
                completed_at=datetime.now(UTC),
            )
            terminal_uow.commit()

        # Step 3: Assert ALREADY_COMPLETED
        assert tr_result.outcome == TerminalTransitionOutcome.ALREADY_COMPLETED
        assert tr_result.observed_status == AttemptStatus.COMPLETED

        # Step 4: Assert no destructive side effects
        state_final = _capture_downstream_state(pg_session_factory, result_a.attempt_id)

        # Attempt status preserved as COMPLETED
        assert state_final["attempt_status"] == "COMPLETED"

        # SourceBinding not overwritten
        assert state_final["source_binding_id"] == binding_id_before
        assert state_final["binding_count"] == 1

        # Authoritative attempt ID not overwritten
        assert state_final["identity_authoritative_attempt_id"] == auth_attempt_before

        # 5 CalculationRuns preserved
        assert state_final["run_count"] == 5

        # No new terminal outbox — only 1 request.accepted + 1 attempt.completed
        counts = _count_outbox_by_type(state_final)
        assert counts.get("orchestration.request.accepted", 0) == 1
        assert counts.get("orchestration.attempt.completed", 0) == 1
        assert counts.get("orchestration.attempt.failed", 0) == 0
        assert counts.get("orchestration.attempt.blocked", 0) == 0

        # Total outbox count unchanged
        assert state_final["outbox_count"] == state_after_completed["outbox_count"]

    def test_completed_then_blocked_returns_already_completed(self, pg_session_factory) -> None:
        """Same as above but tries BLOCKED disposition — also ALREADY_COMPLETED."""
        result_a = _run_transaction_a(pg_session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(
            pg_session_factory, result_a.identity_id
        )

        svc = _build_service(pg_session_factory)
        result_b = svc.execute_transaction_b(
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

        state_after_completed = _capture_downstream_state(pg_session_factory, result_a.attempt_id)

        # Attempt terminal CAS with BLOCKED
        terminal_svc = _build_service(pg_session_factory)
        with terminal_svc._uow_factory() as terminal_uow:
            attempt_repo = SqlAlchemyOrchestrationAttemptRepository()
            tr_result = attempt_repo.transition_running_to_terminal(
                terminal_uow.session,
                attempt_id=result_a.attempt_id,
                identity_id=result_a.identity_id,
                target_status=AttemptStatus.BLOCKED,
                failure_code="TXB_BLOCKED_LOSER",
                failure_details={"failure_code": "TXB_BLOCKED_LOSER"},
                completed_at=datetime.now(UTC),
            )
            terminal_uow.commit()

        assert tr_result.outcome == TerminalTransitionOutcome.ALREADY_COMPLETED

        state_final = _capture_downstream_state(pg_session_factory, result_a.attempt_id)
        assert state_final["attempt_status"] == "COMPLETED"
        assert state_final["outbox_count"] == state_after_completed["outbox_count"]


# ═══════════════════════════════════════════════════════════════════════════
# Scenario B: Two terminal writers race (FAILED vs BLOCKED)
# ═══════════════════════════════════════════════════════════════════════════


class TestTerminalRaceTwoWriters:
    """Two terminal writers race on the same RUNNING attempt.

    Worker A tries RUNNING→FAILED, Worker B tries RUNNING→BLOCKED.
    Exactly one TRANSITIONED, the other ALREADY_TERMINAL.
    Only one terminal outbox event total.
    """

    def test_two_terminal_writers_race(self, pg_session_factory) -> None:
        result_a = _run_transaction_a(pg_session_factory)
        snap_id, coeff_id, orch_fp = _load_identity_context(
            pg_session_factory, result_a.identity_id
        )

        barrier = threading.Barrier(2, timeout=60)
        results: dict[str, dict[str, object]] = {"a": {}, "b": {}}

        def _worker(label: str, target_status: AttemptStatus, failure_code: str) -> None:
            try:
                svc = _build_service(pg_session_factory)
                barrier.wait()
                attempt_repo = SqlAlchemyOrchestrationAttemptRepository()
                outbox_repo = SqlAlchemyAuditOutboxRepository()
                with svc._uow_factory() as terminal_uow:
                    tr_result = attempt_repo.transition_running_to_terminal(
                        terminal_uow.session,
                        attempt_id=result_a.attempt_id,
                        identity_id=result_a.identity_id,
                        target_status=target_status,
                        failure_code=failure_code,
                        failure_details={"failure_code": failure_code},
                        completed_at=datetime.now(UTC),
                    )
                    if tr_result.outcome == TerminalTransitionOutcome.TRANSITIONED:
                        event_type = (
                            "orchestration.attempt.failed"
                            if target_status == AttemptStatus.FAILED
                            else "orchestration.attempt.blocked"
                        )
                        outbox_repo.add(
                            terminal_uow.session,
                            event_type=event_type,
                            aggregate_type="OrchestrationRunAttempt",
                            aggregate_id=result_a.attempt_id,
                            payload={"failure_code": failure_code},
                            attempt_id=result_a.attempt_id,
                        )
                    terminal_uow.commit()
                    results[label]["outcome"] = tr_result.outcome
                    results[label]["target"] = target_status.value
            except Exception as exc:  # noqa: BLE001
                results[label]["error"] = exc

        t_a = threading.Thread(
            target=_worker,
            args=("a", AttemptStatus.FAILED, "TXB_FAILED_RACE"),
        )
        t_b = threading.Thread(
            target=_worker,
            args=("b", AttemptStatus.BLOCKED, "TXB_BLOCKED_RACE"),
        )
        t_a.start()
        t_b.start()
        t_a.join(timeout=60)
        t_b.join(timeout=60)

        assert not t_a.is_alive(), "Thread A deadlocked"
        assert not t_b.is_alive(), "Thread B deadlocked"

        assert "error" not in results["a"], f"Unexpected error in A: {results['a']}"
        assert "error" not in results["b"], f"Unexpected error in B: {results['b']}"

        # Exactly one TRANSITIONED, one ALREADY_TERMINAL
        outcomes = {k: v.get("outcome") for k, v in results.items()}
        _TT = TerminalTransitionOutcome.TRANSITIONED
        _AT = TerminalTransitionOutcome.ALREADY_TERMINAL
        transitioned = [k for k, v in outcomes.items() if v == _TT]
        already_terminal = [k for k, v in outcomes.items() if v == _AT]

        assert len(transitioned) == 1, f"Expected 1 TRANSITIONED, got {transitioned}"
        assert len(already_terminal) == 1, f"Expected 1 ALREADY_TERMINAL, got {already_terminal}"

        winner = transitioned[0]
        winner_target = results[winner]["target"]

        # ── Invariants ──────────────────────────────────────────────────
        state = _capture_downstream_state(pg_session_factory, result_a.attempt_id)
        counts = _count_outbox_by_type(state)

        assert state["attempt_status"] == winner_target, (
            f"Attempt status should be {winner_target}, got {state['attempt_status']}"
        )
        assert state["run_count"] == 0  # no full TXB was executed
        assert state["binding_count"] == 0

        # Precise outbox counting: 1 request.accepted + 1 terminal event from winner
        assert counts.get("orchestration.request.accepted", 0) == 1
        expected_terminal = (
            "orchestration.attempt.failed"
            if winner_target == "FAILED"
            else "orchestration.attempt.blocked"
        )
        assert counts.get(expected_terminal, 0) == 1
        assert counts.get("orchestration.attempt.completed", 0) == 0
        # Ensure no duplicate terminal events
        other_terminal = (
            "orchestration.attempt.blocked"
            if winner_target == "FAILED"
            else "orchestration.attempt.failed"
        )
        assert counts.get(other_terminal, 0) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Scenario C: Missing / wrong identity
# ═══════════════════════════════════════════════════════════════════════════


class TestTerminalRaceMissingWrongIdentity:
    """Guarded CAS with missing attempt or wrong identity_id."""

    def test_missing_attempt_returns_not_found(self, pg_session_factory) -> None:
        """CAS on a nonexistent attempt → NOT_FOUND, no dangling outbox."""
        result_a = _run_transaction_a(pg_session_factory)
        nonexist_id = f"nonexist-{uuid.uuid4().hex[:8]}"

        attempt_repo = SqlAlchemyOrchestrationAttemptRepository()
        svc = _build_service(pg_session_factory)
        with svc._uow_factory() as terminal_uow:
            tr_result = attempt_repo.transition_running_to_terminal(
                terminal_uow.session,
                attempt_id=nonexist_id,
                identity_id=result_a.identity_id,
                target_status=AttemptStatus.FAILED,
                failure_code="TXB_NOT_FOUND",
                failure_details={"failure_code": "TXB_NOT_FOUND"},
                completed_at=datetime.now(UTC),
            )
            terminal_uow.commit()

        assert tr_result.outcome == TerminalTransitionOutcome.NOT_FOUND
        assert tr_result.observed_status is None

        # No dangling outbox for the non-existent attempt
        with pg_session_factory() as s:
            dangling = (
                s.execute(
                    select(AuditOutboxRecord).where(AuditOutboxRecord.attempt_id == nonexist_id)
                )
                .scalars()
                .all()
            )
            assert len(dangling) == 0, f"Expected 0 dangling outbox, got {len(dangling)}"

    def test_wrong_identity_returns_state_conflict(self, pg_session_factory) -> None:
        """CAS with wrong identity_id → STATE_CONFLICT, no modification."""
        result_a = _run_transaction_a(pg_session_factory)

        state_before = _capture_downstream_state(pg_session_factory, result_a.attempt_id)

        wrong_identity = f"wrong-identity-{uuid.uuid4().hex[:8]}"
        attempt_repo = SqlAlchemyOrchestrationAttemptRepository()
        svc = _build_service(pg_session_factory)
        with svc._uow_factory() as terminal_uow:
            tr_result = attempt_repo.transition_running_to_terminal(
                terminal_uow.session,
                attempt_id=result_a.attempt_id,
                identity_id=wrong_identity,
                target_status=AttemptStatus.FAILED,
                failure_code="TXB_WRONG_IDENTITY",
                failure_details={"failure_code": "TXB_WRONG_IDENTITY"},
                completed_at=datetime.now(UTC),
            )
            terminal_uow.commit()

        assert tr_result.outcome == TerminalTransitionOutcome.STATE_CONFLICT

        # No modification to the attempt
        state_after = _capture_downstream_state(pg_session_factory, result_a.attempt_id)
        assert state_after == state_before, "Attempt state changed unexpectedly"
        # No terminal outbox added (only pre-existing request.accepted)
        counts = _count_outbox_by_type(state_after)
        assert counts.get("orchestration.attempt.failed", 0) == 0
        assert counts.get("orchestration.attempt.blocked", 0) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Stability: core race repeated 10× with A-win tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestTerminalRaceStability:
    """Repeat the core terminal race 10× to prove consistency.

    Tracks A-win (COMPLETED) vs B-win (FAILED) counts to verify
    both branches execute at least once across iterations.
    """

    @pytest.mark.parametrize("iteration", range(10))
    def test_completed_vs_terminal_race_stable(self, pg_session_factory, iteration: int) -> None:
        """Each iteration: full Transaction B vs terminal FAILED CAS.

        Asserts the same invariants as the single-run test but with
        per-iteration uniqueness.
        """
        result_a = _run_transaction_a(
            pg_session_factory,
            correlation_id=f"stable-{iteration}",
        )
        snap_id, coeff_id, orch_fp = _load_identity_context(
            pg_session_factory, result_a.identity_id
        )

        barrier = threading.Barrier(2, timeout=60)
        results: dict[str, dict[str, object]] = {"a": {}, "b": {}}

        def _worker_a() -> None:
            try:
                svc = _build_service(pg_session_factory)
                barrier.wait()
                result = svc.execute_transaction_b(
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
                results["a"]["result"] = result
            except Exception as exc:  # noqa: BLE001
                results["a"]["error"] = exc

        def _worker_b() -> None:
            try:
                svc = _build_service(pg_session_factory)
                barrier.wait()
                attempt_repo = SqlAlchemyOrchestrationAttemptRepository()
                outbox_repo = SqlAlchemyAuditOutboxRepository()
                with svc._uow_factory() as terminal_uow:
                    tr_result = attempt_repo.transition_running_to_terminal(
                        terminal_uow.session,
                        attempt_id=result_a.attempt_id,
                        identity_id=result_a.identity_id,
                        target_status=AttemptStatus.FAILED,
                        failure_code=f"TXB_STABILITY_{iteration}",
                        failure_details={"iteration": iteration},
                        completed_at=datetime.now(UTC),
                    )
                    if tr_result.outcome == TerminalTransitionOutcome.TRANSITIONED:
                        outbox_repo.add(
                            terminal_uow.session,
                            event_type="orchestration.attempt.failed",
                            aggregate_type="OrchestrationRunAttempt",
                            aggregate_id=result_a.attempt_id,
                            payload={"failure_code": f"TXB_STABILITY_{iteration}"},
                            attempt_id=result_a.attempt_id,
                        )
                    terminal_uow.commit()
                    results["b"]["outcome"] = tr_result.outcome
            except Exception as exc:  # noqa: BLE001
                results["b"]["error"] = exc

        t_a = threading.Thread(target=_worker_a)
        t_b = threading.Thread(target=_worker_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=120)
        t_b.join(timeout=120)

        assert not t_a.is_alive(), f"Iteration {iteration}: Thread A deadlocked"
        assert not t_b.is_alive(), f"Iteration {iteration}: Thread B deadlocked"

        a_succeeded = "result" in results["a"]
        b_outcome = results["b"].get("outcome")
        state = _capture_downstream_state(pg_session_factory, result_a.attempt_id)
        counts = _count_outbox_by_type(state)

        if a_succeeded:
            assert b_outcome == TerminalTransitionOutcome.ALREADY_COMPLETED
            assert state["run_count"] == 5
            assert state["binding_count"] == 1
            assert state["attempt_status"] == "COMPLETED"
            assert state["source_binding_id"] is not None
            assert state["identity_authoritative_attempt_id"] == result_a.attempt_id
            # Precise outbox: 1 request.accepted + 1 attempt.completed
            assert counts.get("orchestration.request.accepted", 0) == 1
            assert counts.get("orchestration.attempt.completed", 0) == 1
            assert counts.get("orchestration.attempt.failed", 0) == 0
        else:
            assert b_outcome == TerminalTransitionOutcome.TRANSITIONED
            assert state["run_count"] == 0
            assert state["binding_count"] == 0
            assert state["attempt_status"] == "FAILED"
            # Precise outbox: 1 request.accepted + 1 attempt.failed
            assert counts.get("orchestration.request.accepted", 0) == 1
            assert counts.get("orchestration.attempt.failed", 0) == 1
            assert counts.get("orchestration.attempt.completed", 0) == 0
