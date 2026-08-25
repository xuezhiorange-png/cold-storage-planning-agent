"""Workbench five-stage canonical execution and persistence (V0.5 P1).

Runs the orchestration DAG through :class:`Phase2AdapterCalculatorPort` and
:class:`TransactionBExecutor`, persisting five canonical calculator identities
atomically with SourceBinding metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from cold_storage.bootstrap.production_composition import compose_phase2_adapter_calculator_port
from cold_storage.bootstrap.settings import get_settings
from cold_storage.modules.orchestration.application.service import (
    _CALCULATOR_VERSION_VECTOR,
    _COEFFICIENT_SCHEMA_VERSION,
    _ORCHESTRATION_DEFINITION_VERSION,
    _SNAPSHOT_SCHEMA_VERSION,
    _compute_orchestration_fingerprint,
)
from cold_storage.modules.orchestration.application.source_binding_assembly import (
    Phase2AdapterCalculatorPort,
)
from cold_storage.modules.orchestration.application.transaction_b import (
    SourceBindingVerifier,
    StageExecutionResult,
    TransactionBExecutor,
    TransactionBFailure,
    _stage_name_for_calculator,
)
from cold_storage.modules.orchestration.domain.contracts import (
    RequestStatus,
    StagePersistedResult,
)
from cold_storage.modules.orchestration.domain.dag import ORCHESTRATION_STAGE_ORDER
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
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
from cold_storage.modules.projects.application.engineering_input_bundle import (
    EngineeringInputBundleValidationError,
    assert_canonical_power_slot,
    bundle_payload_hash,
    coefficient_context_from_bundle,
    project_execution_snapshot_from_bundle,
    validate_engineering_input_bundle,
)
from cold_storage.modules.projects.domain.models import ProjectVersion
from cold_storage.modules.projects.infrastructure.orm import (
    WorkbenchFiveStageIdempotencyRecord,
)
from cold_storage.shared.errors import ProjectVersionLockedError


@dataclass(frozen=True, slots=True)
class FiveStageExecutionOutcome:
    source_binding_id: str
    calculation_ids: dict[str, str]
    result_hashes: dict[str, str]
    requires_review: bool
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class FiveStageExecutionError:
    code: str
    message: str
    field_path: str
    details: dict[str, Any]


class WorkbenchFiveStageExecutionService:
    """Application-owned five-stage execution for a single project version."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._settings = get_settings()

    def execute(
        self,
        *,
        project_id: str,
        version: ProjectVersion,
        bundle: Mapping[str, Any],
        idempotency_key: str | None,
        actor: str,
    ) -> FiveStageExecutionOutcome:
        if not idempotency_key or not idempotency_key.strip():
            raise FiveStageExecutionRejected(
                FiveStageExecutionError(
                    code="IDEMPOTENCY_KEY_REQUIRED",
                    message="idempotency_key is required for five-stage execution writes",
                    field_path="idempotency_key",
                    details={},
                )
            )
        lock_error = self._version_lock_error(version)
        if lock_error is not None:
            raise FiveStageExecutionRejected(lock_error)

        try:
            validate_engineering_input_bundle(bundle)
        except EngineeringInputBundleValidationError as exc:
            raise FiveStageExecutionRejected(
                FiveStageExecutionError(
                    code=exc.error.code,
                    message=exc.error.message,
                    field_path=exc.error.field_path,
                    details={},
                )
            ) from exc

        identity = bundle["project_version_identity"]
        if str(_leaf(identity, "project_id")) != project_id:
            raise FiveStageExecutionRejected(
                FiveStageExecutionError(
                    code="PROJECT_VERSION_MISMATCH",
                    message="bundle project_id does not match route project_id",
                    field_path="project_version_identity.project_id",
                    details={"project_id": project_id},
                )
            )
        if str(_leaf(identity, "project_version_id")) != version.id:
            raise FiveStageExecutionRejected(
                FiveStageExecutionError(
                    code="PROJECT_VERSION_MISMATCH",
                    message="bundle project_version_id does not match persisted version",
                    field_path="project_version_identity.project_version_id",
                    details={"project_version_id": version.id},
                )
            )
        if int(_leaf(identity, "version_number")) != version.version_number:
            raise FiveStageExecutionRejected(
                FiveStageExecutionError(
                    code="PROJECT_VERSION_MISMATCH",
                    message="bundle version_number does not match persisted version",
                    field_path="project_version_identity.version_number",
                    details={"version_number": version.version_number},
                )
            )

        payload_hash = bundle_payload_hash(bundle)
        database_backend = self._settings.database_backend
        correlation_id = str(_leaf(identity, "correlation_id"))
        actor_principal = str(_leaf(identity, "actor_principal"))

        with self._session_factory() as session:
            replay = self._check_idempotency(
                session,
                database_backend=database_backend,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
            )
            if replay is not None:
                session.commit()
                return replay

            execution_snapshot = project_execution_snapshot_from_bundle(bundle)
            coefficient_context = coefficient_context_from_bundle(bundle)
            input_group_provenance = _input_group_provenance_from_bundle(bundle)
            outcome = self._run_transaction_b(
                session,
                project_id=project_id,
                project_version_id=version.id,
                version_number=version.version_number,
                execution_snapshot=execution_snapshot,
                coefficient_context=coefficient_context,
                input_group_provenance=input_group_provenance,
                actor=actor_principal or actor,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                database_backend=database_backend,
            )
            self._persist_idempotency(
                session,
                database_backend=database_backend,
                idempotency_key=idempotency_key,
                project_version_id=version.id,
                payload_hash=payload_hash,
                outcome=outcome,
            )
            session.commit()
            return outcome

    def _run_transaction_b(
        self,
        session: Session,
        *,
        project_id: str,
        project_version_id: str,
        version_number: int,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        input_group_provenance: dict[str, str],
        actor: str,
        correlation_id: str,
        idempotency_key: str,
        database_backend: str,
    ) -> FiveStageExecutionOutcome:
        snapshot_repo = SqlAlchemyExecutionSnapshotRepository()
        coefficient_repo = SqlAlchemyCoefficientContextRepository()
        identity_repo = SqlAlchemyOrchestrationIdentityRepository()
        request_repo = SqlAlchemyOrchestrationRequestRepository()
        attempt_repo = SqlAlchemyOrchestrationAttemptRepository()
        calc_run_repo = SqlAlchemyCalculationRunRepository()
        source_binding_repo = SqlAlchemySourceBindingRepository()
        outbox_repo = SqlAlchemyAuditOutboxRepository()
        verification_read_port = SqlAlchemyVerificationReadPort()

        exec_snapshot_hash = result_hash(execution_snapshot)
        snapshot_id = snapshot_repo.get_or_create(
            session,
            project_version_id=project_version_id,
            input_snapshot_hash=exec_snapshot_hash,
            schema_version=_SNAPSHOT_SCHEMA_VERSION,
            project_id=project_id,
            version_number=version_number,
            input_snapshot=execution_snapshot,
        )
        coeff_hash = result_hash(coefficient_context)
        coefficient_id = coefficient_repo.get_or_create(
            session,
            project_version_id=project_version_id,
            content_hash=coeff_hash,
            content=coefficient_context,
            schema_version=_COEFFICIENT_SCHEMA_VERSION,
            project_id=project_id,
        )
        orchestration_fingerprint = _compute_orchestration_fingerprint(
            execution_identity_hash=exec_snapshot_hash,
            coefficient_context_hash=coeff_hash,
            definition_version=_ORCHESTRATION_DEFINITION_VERSION,
            calculator_version_vector=_CALCULATOR_VERSION_VECTOR,
            input_mapping_schema_version="1.0.0",
            source_snapshot_schema_version="1.0.0",
        )
        identity_id = identity_repo.get_or_create(
            session,
            fingerprint=orchestration_fingerprint,
            execution_snapshot_id=snapshot_id,
            coefficient_context_id=coefficient_id,
            definition_version=_ORCHESTRATION_DEFINITION_VERSION,
            calculator_version_vector=_CALCULATOR_VERSION_VECTOR,
        )

        request_id = request_repo.add(
            session,
            requested_project_id=project_id,
            requested_project_version_id=project_version_id,
            request_fingerprint=result_hash(
                {
                    "project_id": project_id,
                    "project_version_id": project_version_id,
                    "bundle_hash": exec_snapshot_hash,
                }
            ),
            actor=actor,
            correlation_id=correlation_id,
        )
        attempt_id = self._create_running_attempt(
            session,
            identity_id=identity_id,
            idempotency_key=idempotency_key,
            database_backend=database_backend,
            correlation_id=correlation_id,
        )
        request_repo.update_status(
            session,
            request_id,
            status=RequestStatus.ACCEPTED,
            resolved_project_id=project_id,
            resolved_project_version_id=project_version_id,
            resolved_identity_id=identity_id,
            resolved_attempt_id=attempt_id,
        )

        calculator_port = LineageAwareCalculatorPort(
            inner=compose_phase2_adapter_calculator_port(),
            execution_snapshot=execution_snapshot,
            input_group_provenance=input_group_provenance,
        )
        executor = TransactionBExecutor(
            calculation_run_repo=calc_run_repo,
            source_binding_repo=source_binding_repo,
            attempt_repo=attempt_repo,
            identity_repo=identity_repo,
            outbox_repo=outbox_repo,
            calculator_port=calculator_port,
            verifier=SourceBindingVerifier(read_port=verification_read_port),
        )
        try:
            result = executor.execute(
                session,
                request_id=request_id,
                project_id=project_id,
                project_version_id=project_version_id,
                execution_snapshot_id=snapshot_id,
                coefficient_context_id=coefficient_id,
                orchestration_identity_id=identity_id,
                orchestration_attempt_id=attempt_id,
                orchestration_fingerprint=orchestration_fingerprint,
                execution_snapshot=execution_snapshot,
                coefficient_context=coefficient_context,
                actor=actor,
                correlation_id=correlation_id,
                completed_at=datetime.now(UTC),
            )
        except TransactionBFailure as exc:
            session.rollback()
            raise FiveStageExecutionRejected(
                FiveStageExecutionError(
                    code=exc.code,
                    message=str(exc),
                    field_path=exc.field or "five_stage_execution",
                    details=dict(exc.details),
                )
            ) from exc

        if result.source_binding_id is None:
            session.rollback()
            raise FiveStageExecutionRejected(
                FiveStageExecutionError(
                    code="FIVE_STAGE_SOURCE_BINDING_MISSING",
                    message="five-stage execution completed without SourceBinding",
                    field_path="source_binding_id",
                    details={},
                )
            )

        calc_ids: dict[str, str] = {}
        result_hashes: dict[str, str] = {}
        for stage in result.persisted_stages:
            stage_name = _stage_name_for_calculator(stage.calculator_name)
            calc_ids[stage_name] = stage.calculation_run_id
            result_hashes[stage_name] = stage.result_hash
        if set(calc_ids) != set(ORCHESTRATION_STAGE_ORDER):
            session.rollback()
            raise FiveStageExecutionRejected(
                FiveStageExecutionError(
                    code="FIVE_STAGE_INCOMPLETE",
                    message="five-stage execution did not persist all canonical stages",
                    field_path="persisted_stages",
                    details={"persisted": sorted(calc_ids)},
                )
            )
        return FiveStageExecutionOutcome(
            source_binding_id=result.source_binding_id,
            calculation_ids=calc_ids,
            result_hashes=result_hashes,
            requires_review=bool(result.requires_review),
            idempotent_replay=False,
        )

    def _create_running_attempt(
        self,
        session: Session,
        *,
        identity_id: str,
        idempotency_key: str,
        database_backend: str,
        correlation_id: str,
    ) -> str:
        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        attempt_number = (
            SqlAlchemyOrchestrationAttemptRepository().get_max_attempt_number(session, identity_id)
            + 1
        )
        attempt_id = str(uuid4())
        session.add(
            OrchestrationRunAttemptRecord(
                id=attempt_id,
                identity_id=identity_id,
                attempt_number=attempt_number,
                status="RUNNING",
                heartbeat_at=datetime.now(UTC),
                database_backend=database_backend,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
        )
        session.flush()
        return attempt_id

    def _check_idempotency(
        self,
        session: Session,
        *,
        database_backend: str,
        idempotency_key: str,
        payload_hash: str,
    ) -> FiveStageExecutionOutcome | None:
        from sqlalchemy import select

        existing = session.scalar(
            select(WorkbenchFiveStageIdempotencyRecord).where(
                WorkbenchFiveStageIdempotencyRecord.database_backend == database_backend,
                WorkbenchFiveStageIdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            return None
        if existing.bundle_hash != payload_hash:
            raise FiveStageExecutionRejected(
                FiveStageExecutionError(
                    code="IDEMPOTENCY_PAYLOAD_CONFLICT",
                    message="idempotency_key reused with a different bundle payload",
                    field_path="idempotency_key",
                    details={
                        "idempotency_key": idempotency_key,
                        "database_backend": database_backend,
                    },
                )
            )
        outcome_payload = dict(existing.outcome_payload)
        calc_ids_raw = outcome_payload.get("calculation_ids")
        hash_raw = outcome_payload.get("result_hashes")
        if not isinstance(calc_ids_raw, dict):
            calc_ids_raw = {}
        if not isinstance(hash_raw, dict):
            hash_raw = {}
        return FiveStageExecutionOutcome(
            source_binding_id=str(outcome_payload["source_binding_id"]),
            calculation_ids={str(key): str(value) for key, value in calc_ids_raw.items()},
            result_hashes={str(key): str(value) for key, value in hash_raw.items()},
            requires_review=bool(outcome_payload.get("requires_review", True)),
            idempotent_replay=True,
        )

    def _persist_idempotency(
        self,
        session: Session,
        *,
        database_backend: str,
        idempotency_key: str,
        project_version_id: str,
        payload_hash: str,
        outcome: FiveStageExecutionOutcome,
    ) -> None:
        session.add(
            WorkbenchFiveStageIdempotencyRecord(
                id=str(uuid4()),
                database_backend=database_backend,
                idempotency_key=idempotency_key,
                project_version_id=project_version_id,
                bundle_hash=payload_hash,
                source_binding_id=outcome.source_binding_id,
                outcome_payload={
                    "source_binding_id": outcome.source_binding_id,
                    "calculation_ids": outcome.calculation_ids,
                    "result_hashes": outcome.result_hashes,
                    "requires_review": outcome.requires_review,
                },
                created_at=datetime.now(UTC),
            )
        )

    @staticmethod
    def _version_lock_error(version: ProjectVersion) -> FiveStageExecutionError | None:
        if version.status in ("approved", "archived"):
            return FiveStageExecutionError(
                code=ProjectVersionLockedError.code,
                message=f"project version {version.version_number} is locked for reruns",
                field_path="project_version_identity.version_status",
                details={"version_status": version.status},
            )
        return None


class FiveStageExecutionRejected(Exception):
    def __init__(self, error: FiveStageExecutionError) -> None:
        self.error = error
        super().__init__(error.message)


class LineageAwareCalculatorPort:
    """Bind persisted upstream results into downstream typed inputs at execution time."""

    _LINEAGE_CONFIRMED = "persisted_upstream_confirmed"

    def __init__(
        self,
        *,
        inner: Phase2AdapterCalculatorPort,
        execution_snapshot: dict[str, Any],
        input_group_provenance: Mapping[str, str],
    ) -> None:
        self._inner = inner
        self._execution_snapshot = execution_snapshot
        self._input_group_provenance = dict(input_group_provenance)
        self._stage_payloads: dict[str, dict[str, Any]] = {}
        self._cooling_zone_loads_by_code: dict[str, str] | None = None

    def execute_stage(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, StagePersistedResult],
        actor: str = "",
        correlation_id: str = "",
    ) -> StageExecutionResult:
        self._bind_lineage(
            stage_name,
            execution_snapshot=execution_snapshot,
            coefficient_context=coefficient_context,
            upstream_results=upstream_results,
            actor=actor,
            correlation_id=correlation_id,
        )
        merged_snapshot = dict(execution_snapshot)
        merged_snapshot.update(self._execution_snapshot)
        result = self._inner.execute_stage(
            stage_name=stage_name,
            execution_snapshot=merged_snapshot,
            coefficient_context=coefficient_context,
            upstream_results=upstream_results,
            actor=actor,
            correlation_id=correlation_id,
        )
        if stage_name == "power":
            try:
                assert_canonical_power_slot(result.calculator_name)
            except EngineeringInputBundleValidationError as exc:
                raise TransactionBFailure(
                    exc.error.code,
                    exc.error.message,
                    field=exc.error.field_path,
                    details={},
                ) from exc
        self._stage_payloads[stage_name] = dict(result.result_snapshot)
        return result

    def _lineage_confirmed(self, input_group: str) -> bool:
        return self._input_group_provenance.get(input_group) == self._LINEAGE_CONFIRMED

    def _bind_lineage(
        self,
        stage_name: str,
        *,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, StagePersistedResult],
        actor: str,
        correlation_id: str,
    ) -> None:
        if stage_name == "equipment" and self._lineage_confirmed("equipment_inputs"):
            self._bind_equipment_from_cooling_load(
                execution_snapshot=execution_snapshot,
                coefficient_context=coefficient_context,
            )
        if stage_name == "investment" and self._lineage_confirmed("investment_inputs"):
            self._bind_investment_from_zone_and_power()

    def _bind_equipment_from_cooling_load(
        self,
        *,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
    ) -> None:
        zone_loads = self._cooling_zone_loads_by_code
        if zone_loads is None:
            zone_loads = self._capture_cooling_zone_loads(
                execution_snapshot=execution_snapshot,
                coefficient_context=coefficient_context,
            )
        if not zone_loads:
            raise TransactionBFailure(
                "UPSTREAM_LINEAGE_BIND_FAILED",
                "equipment lineage binding requires per-zone cooling load results",
                field="equipment_inputs.systems[].zones[].design_cooling_load_kw_r",
                details={"reason": "missing_cooling_zone_loads"},
            )
        equipment_stage = self._execution_snapshot.setdefault("equipment", {})
        systems = equipment_stage.get("systems")
        if not isinstance(systems, list):
            raise TransactionBFailure(
                "UPSTREAM_LINEAGE_BIND_FAILED",
                "equipment lineage binding requires equipment systems",
                field="equipment_inputs.systems",
                details={},
            )
        for system in systems:
            if not isinstance(system, dict):
                continue
            zones = system.get("zones")
            if not isinstance(zones, list):
                continue
            for zone in zones:
                if not isinstance(zone, dict):
                    continue
                zone_code = str(zone.get("zone_code", ""))
                if not zone_code:
                    raise TransactionBFailure(
                        "UPSTREAM_LINEAGE_BIND_FAILED",
                        "equipment lineage binding requires zone_code on every zone",
                        field="equipment_inputs.systems[].zones[].zone_code",
                        details={},
                    )
                load = zone_loads.get(zone_code)
                if load is None:
                    raise TransactionBFailure(
                        "UPSTREAM_LINEAGE_BIND_FAILED",
                        (
                            "equipment lineage binding could not match cooling load "
                            f"for zone_code {zone_code!r}"
                        ),
                        field="equipment_inputs.systems[].zones[].design_cooling_load_kw_r",
                        details={
                            "zone_code": zone_code,
                            "available_zone_codes": sorted(zone_loads),
                        },
                    )
                zone["design_cooling_load_kw_r"] = load

    def _bind_investment_from_zone_and_power(self) -> None:
        investment_stage = self._execution_snapshot.setdefault("investment", {})
        zone_payload = self._stage_payloads.get("zone", {})
        total_area = zone_payload.get("total_area_m2") or zone_payload.get("total_required_area_m2")
        if total_area is not None:
            investment_stage["total_area_m2"] = _decimalize(total_area)
        position_count = _sum_position_count(zone_payload)
        if position_count is not None:
            investment_stage["position_count"] = position_count
        power_payload = self._stage_payloads.get("power", {})
        total_power = power_payload.get("total_installed_power_kw_e")
        if total_power is not None:
            investment_stage["total_power_kw"] = _decimalize(total_power)

    def _capture_cooling_zone_loads(
        self,
        *,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
    ) -> dict[str, str]:
        if self._cooling_zone_loads_by_code is not None:
            return self._cooling_zone_loads_by_code
        from dataclasses import replace

        from cold_storage.modules.calculations.application.cooling_load_api import (
            build_cooling_load_input,
        )
        from cold_storage.modules.calculations.domain.cooling_load import (
            ZoneCoolingLoadInput,
            calculate_cooling_load,
        )
        from cold_storage.modules.calculations.domain.errors import CoreCalculationError

        stage_data = execution_snapshot.get("cooling_load", {})
        if not isinstance(stage_data, dict):
            self._cooling_zone_loads_by_code = {}
            return self._cooling_zone_loads_by_code
        raw_inputs = dict(stage_data)
        try:
            typed_input = build_cooling_load_input(raw_inputs)
            coeff_data_raw: object = raw_inputs.get("coefficients", {})
            coeff_data: dict[str, object] = (
                coeff_data_raw if isinstance(coeff_data_raw, dict) else {}
            )
            worker_heat_gain: object = coeff_data.get("worker_heat_gain")
            motor_efficiency: object = coeff_data.get("motor_efficiency")
            if worker_heat_gain is not None or motor_efficiency is not None:
                new_zones: list[ZoneCoolingLoadInput] = []
                for zone in typed_input.zones:
                    new_zones.append(
                        replace(
                            zone,
                            worker_heat_gain=(
                                _decimalize(worker_heat_gain)
                                if worker_heat_gain is not None
                                else zone.worker_heat_gain
                            ),
                            motor_efficiency=(
                                _decimalize(motor_efficiency)
                                if motor_efficiency is not None
                                else zone.motor_efficiency
                            ),
                        )
                    )
                typed_input = replace(typed_input, zones=new_zones)
            result = calculate_cooling_load(typed_input)
        except (CoreCalculationError, TypeError, ValueError) as exc:
            raise TransactionBFailure(
                "UPSTREAM_LINEAGE_BIND_FAILED",
                f"could not derive per-zone cooling loads for lineage binding: {exc}",
                field="cooling_load_inputs.zones",
                details={"error": str(exc)},
            ) from exc
        del coefficient_context  # stage-local coefficients drive lineage capture
        payload = result.result
        if not isinstance(payload, Mapping) or not isinstance(payload.get("zones"), list):
            self._cooling_zone_loads_by_code = {}
            return self._cooling_zone_loads_by_code
        zone_loads: dict[str, str] = {}
        for zone in payload["zones"]:
            if not isinstance(zone, Mapping):
                continue
            zone_code = zone.get("zone_code")
            load = zone.get("subtotal_load_kw_r")
            if zone_code is None or load is None:
                continue
            zone_loads[str(zone_code)] = str(_decimalize(load))
        self._cooling_zone_loads_by_code = zone_loads
        return zone_loads


def compose_workbench_five_stage_execution_service(
    session_factory: sessionmaker[Session],
) -> WorkbenchFiveStageExecutionService:
    return WorkbenchFiveStageExecutionService(session_factory)


def _input_group_provenance_from_bundle(bundle: Mapping[str, Any]) -> dict[str, str]:
    source_metadata = bundle.get("source_metadata")
    if not isinstance(source_metadata, dict):
        return {}
    provenance = source_metadata.get("input_group_provenance")
    if not isinstance(provenance, dict):
        return {}
    return {str(key): str(value) for key, value in provenance.items()}


def _leaf(section: Mapping[str, Any], field_name: str) -> Any:
    node = section[field_name]
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node


def _decimalize(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _sum_position_count(zone_payload: dict[str, Any]) -> int | None:
    zones = zone_payload.get("zones")
    if not isinstance(zones, list):
        return None
    total = 0
    found = False
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        count = zone.get("position_count")
        if count is None:
            continue
        total += int(count)
        found = True
    return total if found else None
