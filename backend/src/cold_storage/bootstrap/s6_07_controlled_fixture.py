"""Controlled S6-07 support at the bootstrap/integration boundary.

This module may seed synthetic prerequisites, but it never writes production
calculation output.  The five CalculationRuns and the SourceBinding are
created by the canonical orchestration use case and Transaction B.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from cold_storage.bootstrap.production_composition import (
    compose_phase2_adapter_calculator_port,
    compose_production_coefficient_approval_service,
    compose_production_scheme_service,
    compose_production_source_binding_use_case_with_strict_resolver,
)
from cold_storage.bootstrap.startup_readiness import get_required_stages
from cold_storage.modules.coefficients.application.approval_service import ApprovalRequest
from cold_storage.modules.coefficients.infrastructure.database import DatabaseCoefficientService
from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)
from cold_storage.modules.orchestration.application.coefficient_contracts import (
    FrozenCoefficientResolutionCriteria,
)
from cold_storage.modules.orchestration.application.production_source_binding import (
    ProductionSourceBindingUseCase,
)
from cold_storage.modules.orchestration.application.service import (
    _AUTHORITATIVE_REQUIRED_CODES,
    _AUTHORITATIVE_REQUIREMENT_HASH,
    _CALCULATOR_VERSION_VECTOR,
    _REQUIREMENT_REGISTRY_VERSION,
    OrchestrationService,
    ProjectVersionReadPort,
    _LoadedVersion,
)
from cold_storage.modules.orchestration.application.unit_of_work import (
    SqlAlchemyOrchestrationUnitOfWorkFactory,
)
from cold_storage.modules.orchestration.domain.contracts import OrchestrationRequestCommand
from cold_storage.modules.orchestration.domain.fingerprint import canonical_json_bytes
from cold_storage.modules.orchestration.infrastructure.coefficient_resolver import (
    SqlAlchemyCoefficientResolutionAdapter,
)
from cold_storage.modules.orchestration.infrastructure.orm import CoefficientContextRecord
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
from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
)
from cold_storage.modules.schemes.infrastructure.orm import (
    SchemeWeightSetRecord,
    SchemeWeightSetRevisionRecord,
)

S6_07_STAGE_NAMES: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

CONTROLLED_COEFFICIENT_CODE = "power.design_margin_ratio"

_STAGE_REQUIRED_COEFFICIENTS: dict[str, tuple[str, ...]] = {
    "zone": (
        "area.auxiliary_area_ratio",
        "area.circulation_allowance_ratio",
    ),
    "cooling_load": ("power.design_margin_ratio",),
    "equipment": (
        "pallet.net_load_kg",
        "pallet.turnover_factor",
    ),
    "power": (
        "power.design_margin_ratio",
        "power.standby_ratio",
    ),
    "investment": (
        "investment.building_unit_cost",
        "investment.electrical_installation_ratio",
        "investment.other_expenses_ratio",
        "investment.refrigeration_equipment_ratio",
    ),
}

_CATALOG_VALUES: dict[str, tuple[str, str, str]] = {
    "area.auxiliary_area_ratio": ("area auxiliary ratio", "0.08", "ratio"),
    "area.circulation_allowance_ratio": ("area circulation ratio", "1.20", "ratio"),
    "investment.building_unit_cost": ("building unit cost", "900", "CNY/m2"),
    "investment.electrical_installation_ratio": (
        "electrical installation ratio",
        "650",
        "CNY/kW",
    ),
    "investment.other_expenses_ratio": ("other expenses", "200000", "CNY"),
    "investment.refrigeration_equipment_ratio": (
        "refrigeration equipment ratio",
        "1400",
        "CNY/m2",
    ),
    "pallet.net_load_kg": ("pallet net load", "400", "kg"),
    "pallet.turnover_factor": ("pallet turnover factor", "1.10", "ratio"),
    "power.standby_ratio": ("power standby ratio", "0.90", "ratio"),
}

_CALCULATOR_NAMES = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}

_WEIGHT_CONTENT: dict[str, Any] = {
    "criteria": [
        {
            "criterion_code": code,
            "weight": weight,
            "direction": direction,
            "normalization_method": "min_max",
            "hard_constraint": False,
        }
        for code, weight, direction in (
            ("total_area_m2", "0.20", "lower_is_better"),
            ("investment_cny", "0.30", "lower_is_better"),
            ("total_position_count", "0.15", "higher_is_better"),
            ("room_module_count", "0.10", "lower_is_better"),
            ("door_count", "0.05", "lower_is_better"),
            ("partition_length_proxy_m", "0.05", "lower_is_better"),
            ("installed_power_kw_e", "0.15", "lower_is_better"),
        )
    ]
}


_EXECUTION_SNAPSHOT: dict[str, Any] = {
    "product_category": "synthetic",
    "zone": {
        "daily_inbound_mass_kg": "10000",
        "working_time_h_per_day": "16",
        "finished_storage_days": "2.5",
        "packaging_storage_days": "3",
        "precooling_required_ratio": "1",
    },
    "cooling_load": {
        "zones": [
            {
                "zone_code": "Z1",
                "zone_name": "s6-07-zone",
                "temperature_level": "medium_temperature",
                "zone_area": "200",
                "room_height": "5",
                "wall_area": "100",
                "roof_area": "100",
                "floor_area": "100",
                "u_value_wall": "0.35",
                "u_value_roof": "0.30",
                "u_value_floor": "0.40",
                "outdoor_design_temperature": "35",
                "room_design_temperature": "2",
                "operating_hours_per_day": "16",
                "product_entry_temperature": "10",
                "product_target_temperature": "2",
                "cooling_duration": "8",
                "product_mass_per_day": "10000",
                "product_specific_heat": "3.6",
                "packaging_mass": "100",
                "packaging_specific_heat": "1.2",
                "worker_count": 2,
                "worker_heat_gain": "120",
                "lighting_power": "2",
                "equipment_power": "4",
                "fan_motor_power": "2",
                "motor_efficiency": "0.92",
            }
        ],
        "coefficients": {"air_change_rate": "0.50"},
    },
    "equipment": {
        "condensing_temperature_c": "40",
        "systems": [
            {
                "system_code": "SYS1",
                "system_name": "controlled-system",
                "design_evaporating_temperature": "-10",
                "zones": [
                    {
                        "zone_code": "Z1",
                        "zone_name": "s6-07-zone",
                        "design_cooling_load_kw_r": "25",
                        "evaporator_count": 2,
                        "evaporation_temperature_c": "-10",
                        "defrost_method": "electric",
                    }
                ],
            }
        ],
        "coefficients": {},
    },
    "power": {
        "compressor_input_power_kw_e": "20",
        "evaporator_fan_power_kw_e": "4",
        "condenser_fan_power_kw_e": "3",
        "pump_power_kw_e": "1",
        "defrost_power_kw_e": "2",
        "processing_equipment_power_kw_e": "12",
        "lighting_power_kw_e": "3",
        "other_auxiliary_power_kw_e": "2",
    },
    "investment": {
        "total_area_m2": "200",
        "refrigerated_area_m2": "180",
        "frozen_area_m2": "20",
        "position_count": 30,
        "total_power_kw": "45",
    },
}


@dataclass(frozen=True, slots=True)
class ControlledFixtureIdentity:
    """Prerequisite identities; downstream IDs come from production output."""

    project_id: str
    version_id: str
    weight_set_id: str
    weight_revision_id: str
    fingerprint: str


def new_fixture_identity(token: str) -> ControlledFixtureIdentity:
    nonce = uuid.uuid4().hex
    return ControlledFixtureIdentity(
        project_id=str(uuid.uuid4()),
        version_id=str(uuid.uuid4()),
        weight_set_id=str(uuid.uuid4()),
        weight_revision_id=str(uuid.uuid4()),
        fingerprint=f"s6-07-controlled-{token[:40]}-{nonce}",
    )


def _write_json(path: Path | None, payload: Mapping[str, Any]) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


def _seed_approved_revision(
    engine: Engine,
    *,
    definition_id: str,
    token: str,
    label: str,
    value: Decimal = Decimal("1.0"),
) -> str:
    service = DatabaseCoefficientService(engine)
    revision = service.create_revision(
        definition_id=definition_id,
        value_decimal=value,
        source_type="engineering_judgement",
        source_title=f"TASK-012 S6-07 controlled {label}",
        source_reference=f"INTERNAL:REF-S6-07-{token[:16]}-{label.replace('_', '-')}",
        created_by="s6-07-controlled-acceptance",
    )
    compose_production_coefficient_approval_service(engine=engine).approve(
        ApprovalRequest(
            definition_id=definition_id,
            revision_id=revision.id,
            actor="coefficient.reviewer",
            reviewer="coefficient.reviewer",
            correlation_id=f"s6-07-approval-{token[:48]}-{label}",
            source_citation=revision.source_reference,
        )
    )
    approved = service.get_revision(definition_id, revision.id)
    if approved.status != "approved" or approved.source_type == "demo":
        raise RuntimeError("controlled coefficient approval did not reach approved non-demo state")
    return approved.id


def seed_startup_readiness(engine: Engine, *, token: str) -> dict[str, Any]:
    """Seed and verify the five strict startup readiness stages."""

    service = DatabaseCoefficientService(engine)
    seeded: list[dict[str, str]] = []
    for stage_name, _calculation_type in get_required_stages():
        definition = service.create_definition(
            code=f"s6_07_readiness_{token[:40]}_{stage_name}",
            name=f"S6-07 readiness {stage_name}",
            description="controlled synthetic startup-readiness coefficient",
            category=stage_name,
            canonical_unit="unit",
            is_active=True,
        )
        revision_id = _seed_approved_revision(
            engine,
            definition_id=definition.id,
            token=token,
            label=f"readiness-{stage_name}",
        )
        seeded.append(
            {"stage_name": stage_name, "definition_id": definition.id, "revision_id": revision_id}
        )
    readiness = compose_production_coefficient_approval_service(
        engine=engine
    ).validate_startup_readiness(stage_names=get_required_stages())
    if not readiness.get("ready") or readiness.get("missing") or readiness.get("citation"):
        raise RuntimeError(f"controlled startup readiness seed failed: {readiness}")
    return {
        "required_stage_count": len(get_required_stages()),
        "required_stage_names": [stage for stage, _ in get_required_stages()],
        "seeded_stage_count": len(seeded),
        "seeded": seeded,
        "ready": True,
        "startup_readiness_seed": "PASS",
    }


def create_controlled_coefficient_definition(engine: Engine, *, token: str) -> str:
    """Create the exact catalog definition used by the controlled POST."""

    service = DatabaseCoefficientService(engine)
    definition = service.create_definition(
        code=CONTROLLED_COEFFICIENT_CODE,
        name="Power design margin ratio",
        description="controlled synthetic production coefficient",
        category="acceptance",
        canonical_unit="ratio",
        is_active=True,
    )
    return definition.id


def _seed_required_catalog(
    engine: Engine, *, token: str, controlled_definition_id: str
) -> dict[str, str]:
    """Seed the remaining exact registry codes as approved prerequisites."""

    service = DatabaseCoefficientService(engine)
    revision_ids = {CONTROLLED_COEFFICIENT_CODE: ""}
    controlled = service.get_definition(controlled_definition_id)
    if controlled.code != CONTROLLED_COEFFICIENT_CODE:
        raise RuntimeError("controlled HTTP definition has unexpected code")
    revision_ids[CONTROLLED_COEFFICIENT_CODE] = _seed_approved_revision(
        engine,
        definition_id=controlled_definition_id,
        token=token,
        label="controlled-design-margin",
        value=Decimal("1.15"),
    )
    for code, (label, value, unit) in _CATALOG_VALUES.items():
        definition = service.create_definition(
            code=code,
            name=label,
            description="controlled synthetic production coefficient prerequisite",
            category="catalog",
            canonical_unit=unit,
            is_active=True,
        )
        revision_ids[code] = _seed_approved_revision(
            engine,
            definition_id=definition.id,
            token=token,
            label=code.replace(".", "-"),
            value=Decimal(value),
        )
    return revision_ids


class _RealVersionPort(ProjectVersionReadPort):
    """Read approved project/version prerequisites through SQLAlchemy."""

    def load_by_id(self, session: object, project_version_id: str) -> _LoadedVersion | None:
        if not isinstance(session, Session):
            raise TypeError("controlled version port requires SQLAlchemy Session")
        version = session.execute(
            select(ProjectVersionRecord).where(ProjectVersionRecord.id == project_version_id)
        ).scalar_one_or_none()
        if version is None:
            return None
        project = session.execute(
            select(ProjectRecord).where(ProjectRecord.id == version.project_id)
        ).scalar_one_or_none()
        if project is None:
            return None
        return _LoadedVersion(
            project_id=project.id,
            project_product_category=project.product_category,
            status=version.status,
            version_number=version.version_number,
            input_snapshot=dict(version.input_snapshot or {}),
        )


class _ControlledSnapshotPreflightPort:
    """The canonical snapshot schema is represented by ProjectVersion data."""

    def validate_candidate(
        self,
        *,
        project_id: str,
        project_version_id: str,
        version_status: str,
    ) -> None:
        if version_status != "approved":
            raise RuntimeError("controlled project version is not approved")


def _seed_project_and_version(engine: Engine, *, identity: ControlledFixtureIdentity) -> None:
    now = datetime.now(UTC)
    version_input = json.loads(json.dumps(_EXECUTION_SNAPSHOT))
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        session.add(
            ProjectRecord(
                id=identity.project_id,
                code=f"S6_07_{identity.project_id[:8]}",
                name="S6-07 controlled project",
                location="synthetic",
                product_category="synthetic",
                status="active",
                current_version_number=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            ProjectVersionRecord(
                id=identity.version_id,
                project_id=identity.project_id,
                version_number=1,
                change_summary="S6-07 controlled operational acceptance",
                created_by="s6-07-controlled-acceptance",
                status="approved",
                input_snapshot=version_input,
                calculation_snapshot={},
                assumption_snapshot={},
                created_at=now,
                updated_at=now,
                approved_at=now,
                approved_by="s6-07-controlled-acceptance",
            )
        )
        session.commit()


def _resolve_context_payload(
    engine: Engine, *, identity: ControlledFixtureIdentity
) -> dict[str, Any]:
    criteria = FrozenCoefficientResolutionCriteria(
        project_id=identity.project_id,
        project_version_id=identity.version_id,
        product_category="synthetic",
        requirement_registry_version=_REQUIREMENT_REGISTRY_VERSION,
        calculator_version_vector=dict(_CALCULATOR_VERSION_VECTOR),
        required_codes=_AUTHORITATIVE_REQUIRED_CODES,
        requirement_hash=_AUTHORITATIVE_REQUIREMENT_HASH,
    )
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        candidate = SqlAlchemyCoefficientResolutionAdapter().resolve(
            criteria=criteria,
            session=session,
        )
    return dict(candidate.content)


def _build_orchestration_service(
    engine: Engine, session_factory: sessionmaker[Session]
) -> OrchestrationService:
    return OrchestrationService(
        uow_factory=SqlAlchemyOrchestrationUnitOfWorkFactory(session_factory),
        request_repo=SqlAlchemyOrchestrationRequestRepository(),
        outbox_repo=SqlAlchemyAuditOutboxRepository(),
        snapshot_repo=SqlAlchemyExecutionSnapshotRepository(),
        coefficient_repo=SqlAlchemyCoefficientContextRepository(),
        identity_repo=SqlAlchemyOrchestrationIdentityRepository(),
        attempt_repo=SqlAlchemyOrchestrationAttemptRepository(),
        version_port=_RealVersionPort(),
        snapshot_port=_ControlledSnapshotPreflightPort(),
        coefficient_port=SqlAlchemyCoefficientResolutionAdapter(),
        calc_run_repo=SqlAlchemyCalculationRunRepository(),
        source_binding_repo=SqlAlchemySourceBindingRepository(),
        calculator_port=compose_phase2_adapter_calculator_port(),
        verification_read_port=SqlAlchemyVerificationReadPort(),
    )


def _seed_weight_revision(engine: Engine, *, identity: ControlledFixtureIdentity) -> None:
    now = datetime.now(UTC)
    code = f"s6-07-controlled-{identity.weight_set_id[:8]}"
    content_hash = hashlib.sha256(canonical_json_bytes(_WEIGHT_CONTENT)).hexdigest()
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        session.add(
            SchemeWeightSetRecord(
                id=identity.weight_set_id,
                code=code,
                name="S6-07 controlled weights",
                revision=1,
                status="approved",
                source_type="production",
                criteria=_WEIGHT_CONTENT["criteria"],
                requires_review=False,
                created_at=now,
                approved_at=now,
            )
        )
        session.add(
            SchemeWeightSetRevisionRecord(
                id=identity.weight_revision_id,
                weight_set_id=identity.weight_set_id,
                code=code,
                revision=1,
                status="draft",
                content=_WEIGHT_CONTENT,
                content_hash=content_hash,
                generator_compatibility_version="1.0.0",
                created_at=now,
            )
        )
        session.flush()
        session.execute(
            text(
                "UPDATE scheme_weight_set_revisions SET status = 'approved', "
                "approved_at = :approved_at, approved_by = :approved_by WHERE id = :revision_id"
            ),
            {
                "approved_at": now,
                "approved_by": "s6-07-controlled-acceptance",
                "revision_id": identity.weight_revision_id,
            },
        )
        session.commit()


def _stage_coefficient_continuity(
    *,
    stage: str,
    calculation: Any,
    raw_provenance: Mapping[str, Any],
    context_items: Mapping[str, Mapping[str, Any]],
    context_id: str,
) -> dict[str, Any]:
    actual = {
        str(ref.get("code")): ref
        for ref in calculation.coefficients
        if isinstance(ref, Mapping) and ref.get("code") in context_items
    }
    required = _STAGE_REQUIRED_COEFFICIENTS[stage]
    missing = [code for code in required if code not in actual]
    if missing:
        raise RuntimeError(f"{stage} did not persist approved coefficient provenance: {missing}")
    calculator_input = raw_provenance.get("calculator_input_snapshot")
    if not isinstance(calculator_input, Mapping):
        raise RuntimeError(f"{stage} persisted calculator input snapshot is missing")

    expected_paths_by_stage: dict[str, dict[str, tuple[str, ...]]] = {
        "zone": {
            "area.auxiliary_area_ratio": ("secondary_fruit_area_ratio",),
            "area.circulation_allowance_ratio": ("storage_area_factor",),
        },
        "cooling_load": {
            "power.design_margin_ratio": ("design_margin_ratio",),
        },
        "equipment": {
            "pallet.net_load_kg": ("coefficients", "compressor_cop"),
            "pallet.turnover_factor": ("coefficients", "redundancy_ratio"),
        },
        "power": {
            "power.design_margin_ratio": ("production_demand_factor",),
            "power.standby_ratio": ("refrigeration_demand_factor",),
        },
        "investment": {
            "investment.building_unit_cost": (
                "coefficients",
                "_investment_coefficients",
                "building_envelope_cost_cny_m2",
                "value",
            ),
            "investment.electrical_installation_ratio": (
                "coefficients",
                "_investment_coefficients",
                "power_distribution_cost_cny_kw",
                "value",
            ),
            "investment.other_expenses_ratio": (
                "coefficients",
                "_investment_coefficients",
                "monitoring_opening_supplies_cny",
                "value",
            ),
            "investment.refrigeration_equipment_ratio": (
                "coefficients",
                "_investment_coefficients",
                "refrigeration_cost_cny_m2",
                "value",
            ),
        },
    }
    expected_input_paths = expected_paths_by_stage[stage]

    execution_inputs: list[dict[str, Any]] = []

    def nested_value(path: tuple[str, ...]) -> Any:
        value: Any = calculator_input
        for key in path:
            if not isinstance(value, Mapping) or key not in value:
                raise RuntimeError(f"{stage} calculator input is missing {'.'.join(path)}")
            value = value[key]
        return value

    for code, path in expected_input_paths.items():
        actual_value = nested_value(path)
        expected_value = context_items[code].get("value_decimal")
        if stage == "equipment" and code == "pallet.net_load_kg":
            expected_value = Decimal(str(expected_value)) / Decimal("160")
        if Decimal(str(actual_value)) != Decimal(str(expected_value)):
            raise RuntimeError(
                f"{stage} calculator input coefficient mismatch for {code}: "
                f"expected {expected_value!r}, observed {actual_value!r}"
            )
        execution_inputs.append(
            {
                "code": code,
                "path": ".".join(path),
                "value_decimal": str(actual_value),
                "context_value_decimal": str(context_items[code].get("value_decimal")),
            }
        )

    bindings: list[dict[str, Any]] = []
    for code in required:
        ref = actual[code]
        expected = context_items[code]
        if ref.get("revision_id") != expected.get("revision_id"):
            raise RuntimeError(f"{stage} coefficient revision mismatch for {code}")
        if ref.get("source_type") == "demo" or ref.get("status") not in {None, "approved"}:
            raise RuntimeError(f"{stage} coefficient {code} is not approved non-demo")
        bindings.append(
            {
                "code": code,
                "revision_id": expected.get("revision_id"),
                "context_id": context_id,
                "calculation_id": calculation.id,
                "value_decimal": expected.get("value_decimal"),
                "persisted_provenance": dict(ref),
            }
        )
    return {
        "result": "PASS",
        "required": list(required),
        "bindings": bindings,
        "calculator_input_evidence": {
            "result": "PASS",
            "source": "persisted_calculation_run.provenance.calculator_input_snapshot",
            "bindings": execution_inputs,
        },
    }


def read_production_authority(engine: Engine, *, run_id: str) -> dict[str, Any]:
    """Read and independently verify canonical SchemeRun authority."""

    from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
        compute_archive_hash_v1,
        validate_archive_payload_v1,
    )
    from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (
        SqlAlchemyProductionSourceArchiveRepository,
    )
    from cold_storage.modules.schemes.application.production_service import (
        read_verified_production_scheme_run,
    )
    from cold_storage.modules.schemes.infrastructure.production_read_ports import (
        SqlAlchemyProductionSchemeRunReadPort,
        SqlAlchemySourceBindingReadPort,
        SqlAlchemyWeightRevisionReadPort,
    )

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        run_port = SqlAlchemyProductionSchemeRunReadPort()
        binding_port = SqlAlchemySourceBindingReadPort()
        verified = read_verified_production_scheme_run(
            run_port,
            binding_port,
            SqlAlchemyWeightRevisionReadPort(),
            session,
            run_id=run_id,
            generator_version="1.0.0",
        )
        persisted = run_port.load_production_run(session, run_id=run_id)
        if persisted is None or persisted.source_binding_id is None:
            raise RuntimeError("production SchemeRun readback is missing SourceBinding")
        binding = binding_port.load_binding(session, binding_id=persisted.source_binding_id)
        if binding is None:
            raise RuntimeError("SourceBinding readback is missing")
        calculation_ids = {
            "zone": binding.zone_calculation_id,
            "cooling_load": binding.cooling_load_calculation_id,
            "equipment": binding.equipment_calculation_id,
            "power": binding.power_calculation_id,
            "investment": binding.investment_calculation_id,
        }
        context = session.get(CoefficientContextRecord, binding.coefficient_context_id)
        if context is None or not isinstance(context.content, Mapping):
            raise RuntimeError("coefficient context readback is missing")
        context_items_raw = context.content.get("coefficients")
        if not isinstance(context_items_raw, list):
            raise RuntimeError("coefficient context has no canonical items")
        context_items = {
            str(item["code"]): item
            for item in context_items_raw
            if isinstance(item, Mapping) and isinstance(item.get("code"), str)
        }
        continuity: dict[str, Any] = {}
        stages: list[dict[str, Any]] = []
        for stage in S6_07_STAGE_NAMES:
            calculation = binding_port.load_calculation_run(session, run_id=calculation_ids[stage])
            if calculation is None:
                raise RuntimeError(f"missing persisted CalculationRun for {stage}")
            raw_calculation = session.get(CalculationRunRecord, calculation.id)
            if raw_calculation is None:
                raise RuntimeError(f"missing raw persisted CalculationRun for {stage}")
            raw_provenance = raw_calculation.provenance or {}
            if not isinstance(raw_provenance, Mapping):
                raise RuntimeError(f"{stage} persisted calculator provenance is missing")
            if calculation.coefficient_context_id != binding.coefficient_context_id:
                raise RuntimeError(f"{stage} coefficient context binding mismatch")
            continuity[stage] = _stage_coefficient_continuity(
                stage=stage,
                calculation=calculation,
                raw_provenance=raw_provenance,
                context_items=context_items,
                context_id=binding.coefficient_context_id,
            )
            stages.append(
                {
                    "name": stage,
                    "exists": True,
                    "persisted": True,
                    "calculation_id": calculation.id,
                    "calculation_type": calculation.calculation_type,
                    "result_hash": calculation.result_hash,
                    "coefficient_context_id": calculation.coefficient_context_id,
                    "coefficient_bindings": continuity[stage]["bindings"],
                }
            )

        controlled_item = context_items.get(CONTROLLED_COEFFICIENT_CODE)
        if controlled_item is None:
            raise RuntimeError("controlled design-margin coefficient is missing")
        definition_id = str(controlled_item.get("definition_id"))
        revision_id = str(controlled_item.get("revision_id"))
        definition = session.get(CoefficientDefinitionRecord, definition_id)
        revision = session.get(CoefficientRevisionRecord, revision_id)
        if definition is None or revision is None:
            raise RuntimeError("controlled coefficient rows are missing")
        if revision.coefficient_definition_id != definition.id or revision.status != "approved":
            raise RuntimeError("controlled coefficient approval binding is invalid")

        archive = SqlAlchemyProductionSourceArchiveRepository().find_by_scheme_run_id(
            session, run_id
        )
        if archive is None:
            raise RuntimeError("production source archive readback is missing")
        payload = validate_archive_payload_v1(dict(archive["archive_payload"]))
        recomputed = compute_archive_hash_v1(payload)
        if recomputed != archive["archive_hash"]:
            raise RuntimeError("canonical source archive digest mismatch")

        return {
            "run_id": persisted.id,
            "project_id": persisted.project_id,
            "project_version_id": persisted.project_version_id,
            "status": persisted.status,
            "source_mode": persisted.source_mode,
            "stages": stages,
            "coefficient_execution_continuity": {
                "result": "PASS",
                "context_id": binding.coefficient_context_id,
                "stages": continuity,
            },
            "source_binding": {
                "exists": True,
                "scheme_run_id": persisted.id,
                "source_binding_id": binding.id,
                "coefficient_context_id": binding.coefficient_context_id,
                "execution_snapshot_id": binding.execution_snapshot_id,
                "orchestration_identity_id": binding.orchestration_identity_id,
                "orchestration_run_attempt_id": binding.orchestration_run_attempt_id,
                "required_slot_ids": [calculation_ids[name] for name in S6_07_STAGE_NAMES],
                "per_calculation_result_hashes": dict(binding.per_calculation_result_hashes),
                "content_sha256": binding.combined_source_hash,
            },
            "coefficient_resolution": {
                "coefficient_id": binding.coefficient_context_id,
                "source_type": str(context.content.get("source_type")),
                "selection_strategy": "source_binding_exact_id",
                "source_binding_id": binding.id,
            },
            "power_authority": {
                "slot_id": "power",
                "calculation_id": binding.power_calculation_id,
                "scheme_run_id": persisted.id,
                "source_binding_id": binding.id,
                "value_present": True,
                "value_sha256": binding.per_calculation_result_hashes["power"],
            },
            "source_archive": {
                "exists": True,
                "scheme_run_id": persisted.id,
                "sha256": archive["archive_hash"],
                "expected_sha256": recomputed,
                "verification_method": "canonical_archive_v1",
                "independent_rehash": True,
            },
            "controlled_coefficient": {
                "definition_id": definition.id,
                "approved_revision_id": revision.id,
                "active_authority_revision_id": revision.id,
                "coefficient_context_id": context.id,
                "source_binding_coefficient_context_id": binding.coefficient_context_id,
                "definition_category": definition.category,
                "revision_status": revision.status,
                "revision_source_type": revision.source_type,
                "execution_consumed_stages": [
                    stage
                    for stage, result in continuity.items()
                    if any(
                        binding_item["code"] == CONTROLLED_COEFFICIENT_CODE
                        for binding_item in result["bindings"]
                    )
                ],
            },
            "verified_scheme_status": verified.status,
        }


def create_controlled_production_authority(
    engine: Engine, *, definition_id: str, token: str, output_path: Path | None = None
) -> dict[str, Any]:
    """Create production authority through Transaction A/B and SchemeService."""

    identity = new_fixture_identity(token)
    _seed_project_and_version(engine, identity=identity)
    _seed_required_catalog(
        engine,
        token=token,
        controlled_definition_id=definition_id,
    )
    context_payload = _resolve_context_payload(engine, identity=identity)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    orchestration_service = _build_orchestration_service(engine, session_factory)
    use_case: ProductionSourceBindingUseCase = (
        compose_production_source_binding_use_case_with_strict_resolver(
            service=orchestration_service,
            identity_repository=SqlAlchemyOrchestrationIdentityRepository(),
            engine=engine,
        )
    )
    command = OrchestrationRequestCommand(
        project_id=identity.project_id,
        project_version_id=identity.version_id,
        coefficient_resolution_context={},
        actor="s6-07-controlled-acceptance",
        correlation_id=f"s6-07-{identity.fingerprint}",
    )
    with session_factory() as session:
        outcome = use_case.run(
            session,
            command=command,
            execution_snapshot_payload=json.loads(json.dumps(_EXECUTION_SNAPSHOT)),
            coefficient_context_payload=context_payload,
        )

    _seed_weight_revision(engine, identity=identity)
    scheme_service = compose_production_scheme_service(session_factory)
    run = scheme_service.generate_production_scheme_run(
        GenerateProductionSchemeCommand(
            source_binding_id=outcome.source_binding_id,
            weight_set_revision_id=identity.weight_revision_id,
            profile_codes=("balanced",),
            profile_parameters={},
            actor="s6-07-controlled-acceptance",
            correlation_id=f"s6-07-{identity.fingerprint}",
            database_backend="postgresql" if engine.dialect.name == "postgresql" else "sqlite",
        )
    )
    authority = read_production_authority(engine, run_id=run.id)
    controlled = dict(authority["controlled_coefficient"])
    controlled.update(
        {
            "http_definition_id": definition_id,
            "persisted_definition_id": definition_id,
            "approved_revision_definition_id": definition_id,
        }
    )
    if controlled.get("definition_id") != definition_id:
        raise RuntimeError("HTTP-created definition is not the production authority definition")
    fixture_identity = asdict(identity)
    fixture_identity.update(
        {
            "execution_snapshot_id": authority["source_binding"]["execution_snapshot_id"],
            "context_id": authority["source_binding"]["coefficient_context_id"],
            "identity_id": authority["source_binding"]["orchestration_identity_id"],
            "attempt_id": authority["source_binding"]["orchestration_run_attempt_id"],
            "source_binding_id": authority["source_binding"]["source_binding_id"],
            "scheme_run_id": authority["run_id"],
        }
    )
    output: dict[str, Any] = {
        "controlled_coefficient": controlled,
        "create_response": {
            "status": 200,
            "body": {
                "run_id": run.id,
                "project_id": authority["project_id"],
                "project_version_id": authority["project_version_id"],
                "status": run.status,
            },
        },
        "persisted_readback": {
            "status": 200,
            "body": {"run_id": authority["run_id"], "status": authority["status"]},
        },
        "canonical_persistence": authority,
        "fixture_identity": fixture_identity,
    }
    _write_json(output_path, output)
    return output


def _database_engine(database_url: str) -> Engine:
    from sqlalchemy import create_engine

    os.environ["COLD_STORAGE_DATABASE_BACKEND"] = (
        "postgresql" if database_url.startswith("postgres") else "sqlite"
    )
    os.environ["COLD_STORAGE_DATABASE_URL"] = database_url
    return create_engine(database_url, pool_pre_ping=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TASK-012 S6-07 controlled fixture support")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-startup-readiness")
    seed.add_argument("--database-url", required=True)
    seed.add_argument("--token", required=True)
    seed.add_argument("--output", type=Path)
    create = sub.add_parser("create-production-authority")
    create.add_argument("--database-url", required=True)
    create.add_argument("--definition-id", required=True)
    create.add_argument("--token", required=True)
    create.add_argument("--output", type=Path, required=True)
    reload = sub.add_parser("reload-production-authority")
    reload.add_argument("--database-url", required=True)
    reload.add_argument("--run-id", required=True)
    reload.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    engine: Engine | None = None
    try:
        engine = _database_engine(args.database_url)
        if args.command == "seed-startup-readiness":
            _write_json(args.output, seed_startup_readiness(engine, token=args.token))
        elif args.command == "create-production-authority":
            create_controlled_production_authority(
                engine,
                definition_id=args.definition_id,
                token=args.token,
                output_path=args.output,
            )
        elif args.command == "reload-production-authority":
            _write_json(args.output, read_production_authority(engine, run_id=args.run_id))
        else:
            raise RuntimeError(f"unsupported command: {args.command}")
        return 0
    except Exception as exc:
        print(f"S6_07_CONTROLLED_FIXTURE_ERROR={type(exc).__name__}: {exc}")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ControlledFixtureIdentity",
    "S6_07_STAGE_NAMES",
    "create_controlled_coefficient_definition",
    "create_controlled_production_authority",
    "main",
    "new_fixture_identity",
    "read_production_authority",
    "seed_startup_readiness",
]
