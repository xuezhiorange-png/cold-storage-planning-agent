"""Controlled synthetic fixtures for TASK-012 S6-07 acceptance.

This module is the shared non-production support boundary used by the focused
PostgreSQL tests and by the explicitly dispatched S6-07 workflow.  It creates
run-scoped synthetic rows through the same approved coefficient and production
scheme services that the application uses, then reads the result through the
canonical production read ports.  It is intentionally not imported by the
application bootstrap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.production_composition import (
    compose_production_coefficient_approval_service,
    compose_production_scheme_service,
)
from cold_storage.bootstrap.startup_readiness import get_required_stages
from cold_storage.modules.coefficients.application.approval_service import ApprovalRequest
from cold_storage.modules.coefficients.infrastructure.database import DatabaseCoefficientService
from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)
from cold_storage.modules.orchestration.domain.fingerprint import (
    canonical_json_bytes,
    result_hash,
)
from cold_storage.modules.orchestration.domain.snapshots import build_source_snapshot_content_v1
from cold_storage.modules.orchestration.infrastructure.orm import (
    CoefficientContextRecord,
    OrchestrationIdentityRecord,
    OrchestrationRunAttemptRecord,
    ProjectVersionExecutionSnapshotRecord,
    SourceBindingRecord,
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

_CALCULATOR_NAMES: dict[str, str] = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}
_UPSTREAM_STAGES: dict[str, tuple[str, ...]] = {
    "zone": (),
    "cooling_load": ("zone",),
    "equipment": ("cooling_load",),
    "power": ("equipment",),
    "investment": ("zone", "power"),
}
_RESULTS: dict[str, dict[str, Any]] = {
    "zone": {
        "daily_inbound_mass_kg": 10000,
        "design_daily_mass_kg": 10000,
        "total_required_area_m2": "200.0",
        "total_area_m2": "200.0",
        "planning_parameters": {"pallet_weight_kg": 500, "working_hours_per_day": 8},
        "zones": [
            {
                "zone_code": "Z1",
                "zone_name": "s6-07-zone",
                "daily_throughput_kg_day": 10000,
                "required_area_m2": "200.0",
                "design_storage_mass_kg": "15000.0",
                "position_count": 30,
                "temperature_band": "0~4C",
                "function": "storage",
                "process_compatibility": "blueberry",
                "hygiene_zone": "food_grade",
            }
        ],
    },
    "cooling_load": {
        "total_cooling_load_kw": "25.0",
        "safety_margin_load_kw": "2.5",
        "envelope_heat_transfer_load_kw": "3.0",
        "product_sensible_heat_load_kw": "18.0",
        "packaging_load_kw": "1.0",
        "infiltration_load_kw": "3.0",
        "personnel_load_kw": "0.5",
        "lighting_load_kw": "0.3",
        "evaporator_fan_load_kw": "1.2",
        "defrost_additional_load_kw": "0.4",
        "other_configuration_load_kw": "0.1",
        "latent_load_kw": "0.0",
    },
    "equipment": {
        "evaporator_total_cooling_capacity_kw": "30.0",
        "evaporator_quantity": 2,
        "single_evaporator_capacity_kw": "15.0",
        "compressor_operating_capacity_kw": "22.0",
        "compressor_installed_capacity_kw": "25.0",
        "standby_capacity_kw": "8.0",
        "condenser_heat_rejection_capacity_kw": "30.0",
        "evaporation_temperature_c": "-5.0",
        "condensing_temperature_c": "40.0",
        "defrost_method": "electric",
        "review_requirement": "",
    },
    "power": {
        "total_installed_power_kw_e": "200.0",
        "total_estimated_demand_kw": "160.0",
        "equipment_rows": [],
        "summary_rows": [],
        "items": [],
        "assumptions": [],
    },
    "investment": {
        "total_investment_cny": "6000000.0",
        "items": [
            {"item_name": "building", "amount_cny": "3000000.0"},
            {"item_name": "equipment", "amount_cny": "2000000.0"},
            {"item_name": "other", "amount_cny": "1000000.0"},
        ],
    },
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


@dataclass(frozen=True, slots=True)
class ControlledFixtureIdentity:
    """All mutable fixture identities for one controlled run."""

    project_id: str
    version_id: str
    execution_snapshot_id: str
    context_id: str
    identity_id: str
    attempt_id: str
    source_binding_id: str
    weight_set_id: str
    weight_revision_id: str
    fingerprint: str
    calculation_ids: dict[str, str]


def new_fixture_identity(token: str) -> ControlledFixtureIdentity:
    """Return a unique, run-scoped identity set."""

    nonce = uuid.uuid4().hex

    def _id() -> str:
        return str(uuid.uuid4())

    return ControlledFixtureIdentity(
        project_id=_id(),
        version_id=_id(),
        execution_snapshot_id=_id(),
        context_id=_id(),
        identity_id=_id(),
        attempt_id=_id(),
        source_binding_id=_id(),
        weight_set_id=_id(),
        weight_revision_id=_id(),
        fingerprint=f"s6-07-controlled-{token[:40]}-{nonce}",
        calculation_ids={stage: _id() for stage in S6_07_STAGE_NAMES},
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
        source_reference=f"INTERNAL:REF-S6-07-{token[:28]}-{label.replace('_', '-')}",
        created_by="s6-07-controlled-acceptance",
    )
    approval = compose_production_coefficient_approval_service(engine=engine)
    approval.approve(
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
    """Seed and verify the five canonical startup readiness stages."""

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
            {
                "stage_name": stage_name,
                "definition_id": definition.id,
                "revision_id": revision_id,
            }
        )

    readiness = compose_production_coefficient_approval_service(
        engine=engine
    ).validate_startup_readiness(stage_names=get_required_stages())
    if not readiness.get("ready") or readiness.get("missing") or readiness.get("citation"):
        raise RuntimeError(f"controlled startup readiness seed failed: {readiness}")
    payload: dict[str, Any] = {
        "required_stage_count": len(get_required_stages()),
        "required_stage_names": [stage for stage, _ in get_required_stages()],
        "seeded_stage_count": len(seeded),
        "seeded": seeded,
        "ready": True,
        "startup_readiness_seed": "PASS",
    }
    return payload


def create_controlled_coefficient_definition(engine: Engine, *, token: str) -> str:
    """Create the definition identity equivalent to the controlled HTTP POST."""

    service = DatabaseCoefficientService(engine)
    definition = service.create_definition(
        code=f"s6_07_controlled_coefficient_{token[:40]}",
        name="S6-07 controlled coefficient",
        description="synthetic acceptance coefficient",
        category="acceptance",
        canonical_unit="unit",
        is_active=True,
    )
    return definition.id


def _stage_snapshot(stage: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(_RESULTS[stage])))


def _domain_hash(identity: ControlledFixtureIdentity, stage: str) -> str:
    slot_ids = identity.calculation_ids
    content = build_source_snapshot_content_v1(
        schema_version="1.0.0",
        calculation_type=stage,
        calculator_name=_CALCULATOR_NAMES[stage],
        calculator_version="1.0.0",
        project_id=identity.project_id,
        project_version_id=identity.version_id,
        execution_snapshot_id=identity.execution_snapshot_id,
        coefficient_context_id=identity.context_id,
        orchestration_identity_id=identity.identity_id,
        orchestration_run_attempt_id=identity.attempt_id,
        input_hash=f"s6-07-input-{stage}",
        requires_review=False,
        payload=_stage_snapshot(stage),
        upstream_calculation_ids={name: slot_ids[name] for name in _UPSTREAM_STAGES[stage]},
    )
    return result_hash(content)


def _combined_hash(identity: ControlledFixtureIdentity, hashes: Mapping[str, str]) -> str:
    from cold_storage.modules.schemes.application.source_binding_verifier import (
        _compute_combined_source_hash,
    )

    return _compute_combined_source_hash(
        binding_schema_version="1.0.0",
        project_id=identity.project_id,
        project_version_id=identity.version_id,
        execution_snapshot_id=identity.execution_snapshot_id,
        coefficient_context_id=identity.context_id,
        orchestration_identity_id=identity.identity_id,
        orchestration_attempt_id=identity.attempt_id,
        orchestration_fingerprint=identity.fingerprint,
        slot_ids=identity.calculation_ids,
        result_hashes=hashes,
        requires_reviews={stage: False for stage in S6_07_STAGE_NAMES},
    )


def _seed_production_context(
    engine: Engine,
    *,
    identity: ControlledFixtureIdentity,
    definition_id: str,
    approved_revision_id: str,
) -> None:
    now = datetime.now(UTC)
    input_snapshot = {"throughput_t": "25.0", "controlled": True}
    input_snapshot_hash = hashlib.sha256(canonical_json_bytes(input_snapshot)).hexdigest()
    context_content: dict[str, Any] = {
        "schema_version": "s6-07-controlled-coefficient-context-v1",
        "context_id": identity.context_id,
        "controlled_coefficient": {
            "definition_id": definition_id,
            "approved_revision_id": approved_revision_id,
            "active_authority_revision_id": approved_revision_id,
        },
        "source_type": "production_persisted_context",
        "controlled_synthetic": True,
    }
    context_hash = hashlib.sha256(canonical_json_bytes(context_content)).hexdigest()
    hashes = {stage: _domain_hash(identity, stage) for stage in S6_07_STAGE_NAMES}
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
        session.add(
            ProjectVersionRecord(
                id=identity.version_id,
                project_id=identity.project_id,
                version_number=1,
                change_summary="S6-07 controlled operational acceptance",
                created_by="s6-07-controlled-acceptance",
                status="approved",
                input_snapshot=input_snapshot,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            ProjectVersionExecutionSnapshotRecord(
                id=identity.execution_snapshot_id,
                project_id=identity.project_id,
                project_version_id=identity.version_id,
                version_number=1,
                input_snapshot=input_snapshot,
                input_snapshot_hash=input_snapshot_hash,
                schema_version="1.0.0",
                captured_status="approved",
                captured_source_revision=approved_revision_id,
                captured_at=now,
            )
        )
        session.add(
            CoefficientContextRecord(
                id=identity.context_id,
                project_id=identity.project_id,
                project_version_id=identity.version_id,
                content=context_content,
                content_hash=context_hash,
                schema_version="s6-07-controlled-coefficient-context-v1",
                captured_at=now,
            )
        )
        session.add(
            OrchestrationIdentityRecord(
                id=identity.identity_id,
                fingerprint=identity.fingerprint,
                execution_snapshot_id=identity.execution_snapshot_id,
                coefficient_context_id=identity.context_id,
                definition_version="1.0.0",
                calculator_version_vector={stage: "1.0.0" for stage in S6_07_STAGE_NAMES},
                status="ACTIVE",
                created_at=now,
            )
        )
        session.add(
            OrchestrationRunAttemptRecord(
                id=identity.attempt_id,
                identity_id=identity.identity_id,
                attempt_number=1,
                status="COMPLETED",
                heartbeat_at=now,
                started_at=now,
                completed_at=now,
                database_backend="postgresql" if engine.dialect.name == "postgresql" else "sqlite",
                correlation_id=f"s6-07-{identity.attempt_id}",
            )
        )
        for stage in S6_07_STAGE_NAMES:
            upstream = {name: identity.calculation_ids[name] for name in _UPSTREAM_STAGES[stage]}
            session.add(
                CalculationRunRecord(
                    id=identity.calculation_ids[stage],
                    project_id=identity.project_id,
                    project_version_id=identity.version_id,
                    calculator_name=_CALCULATOR_NAMES[stage],
                    calculator_version="1.0.0",
                    input_snapshot={},
                    result_snapshot=_stage_snapshot(stage),
                    formulas=[],
                    coefficients=[],
                    assumptions=[],
                    warnings=[],
                    source_references=[],
                    requires_review=False,
                    calculation_type=stage,
                    orchestration_identity_id=identity.identity_id,
                    orchestration_run_attempt_id=identity.attempt_id,
                    execution_snapshot_id=identity.execution_snapshot_id,
                    coefficient_context_id=identity.context_id,
                    input_hash=f"s6-07-input-{stage}",
                    result_hash=hashes[stage],
                    provenance={"stage": stage, "upstream_calculation_ids": upstream},
                    schema_version="1.0.0",
                    orchestration_fingerprint=identity.fingerprint,
                    created_at=now,
                )
            )
        session.add(
            SourceBindingRecord(
                id=identity.source_binding_id,
                project_id=identity.project_id,
                project_version_id=identity.version_id,
                execution_snapshot_id=identity.execution_snapshot_id,
                coefficient_context_id=identity.context_id,
                orchestration_identity_id=identity.identity_id,
                orchestration_run_attempt_id=identity.attempt_id,
                orchestration_fingerprint=identity.fingerprint,
                zone_calculation_id=identity.calculation_ids["zone"],
                cooling_load_calculation_id=identity.calculation_ids["cooling_load"],
                equipment_calculation_id=identity.calculation_ids["equipment"],
                power_calculation_id=identity.calculation_ids["power"],
                investment_calculation_id=identity.calculation_ids["investment"],
                per_calculation_result_hashes=hashes,
                combined_source_hash=_combined_hash(identity, hashes),
                schema_version="1.0.0",
                created_at=now,
            )
        )
        session.flush()
        attempt = session.get(OrchestrationRunAttemptRecord, identity.attempt_id)
        if attempt is None:
            raise RuntimeError("controlled attempt was not persisted")
        attempt.source_binding_id = identity.source_binding_id
        session.flush()
        orchestration_identity = session.get(OrchestrationIdentityRecord, identity.identity_id)
        if orchestration_identity is None:
            raise RuntimeError("controlled orchestration identity was not persisted")
        orchestration_identity.authoritative_attempt_id = identity.attempt_id
        session.commit()

    _seed_weight_revision(engine, identity=identity)


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


def read_production_authority(engine: Engine, *, run_id: str) -> dict[str, Any]:
    """Read one persisted SchemeRun through the canonical read ports."""

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

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        run_port = SqlAlchemyProductionSchemeRunReadPort()
        binding_port = SqlAlchemySourceBindingReadPort()
        weight_port = SqlAlchemyWeightRevisionReadPort()
        verified = read_verified_production_scheme_run(
            run_port,
            binding_port,
            weight_port,
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
        stages: list[dict[str, Any]] = []
        for stage in S6_07_STAGE_NAMES:
            calculation = binding_port.load_calculation_run(session, run_id=calculation_ids[stage])
            if calculation is None:
                raise RuntimeError(f"missing persisted CalculationRun for {stage}")
            stages.append(
                {
                    "name": stage,
                    "exists": True,
                    "persisted": True,
                    "calculation_id": calculation.id,
                    "calculation_type": calculation.calculation_type,
                    "result_hash": calculation.result_hash,
                }
            )
        archive = SqlAlchemyProductionSourceArchiveRepository().find_by_scheme_run_id(
            session, run_id
        )
        if archive is None:
            raise RuntimeError("production source archive readback is missing")
        payload = validate_archive_payload_v1(dict(archive["archive_payload"]))
        recomputed = compute_archive_hash_v1(payload)
        if recomputed != archive["archive_hash"]:
            raise RuntimeError("canonical source archive digest mismatch")
        context = session.get(CoefficientContextRecord, binding.coefficient_context_id)
        if context is None:
            raise RuntimeError("coefficient context readback is missing")
        controlled = context.content.get("controlled_coefficient")
        if not isinstance(controlled, Mapping):
            raise RuntimeError("controlled coefficient mapping is missing from context")
        definition_id = str(controlled.get("definition_id"))
        revision_id = str(controlled.get("approved_revision_id"))
        definition = session.get(CoefficientDefinitionRecord, definition_id)
        revision = session.get(CoefficientRevisionRecord, revision_id)
        if definition is None or revision is None:
            raise RuntimeError("controlled coefficient rows are missing")
        active_revision_id = str(controlled.get("active_authority_revision_id"))
        if revision.coefficient_definition_id != definition.id or revision.status != "approved":
            raise RuntimeError("controlled coefficient approval binding is invalid")
        if active_revision_id != revision.id:
            raise RuntimeError("controlled active authority revision is invalid")
        return {
            "run_id": persisted.id,
            "project_id": persisted.project_id,
            "project_version_id": persisted.project_version_id,
            "status": persisted.status,
            "source_mode": persisted.source_mode,
            "stages": stages,
            "source_binding": {
                "exists": True,
                "scheme_run_id": persisted.id,
                "source_binding_id": binding.id,
                "coefficient_context_id": binding.coefficient_context_id,
                "required_slot_ids": [calculation_ids[name] for name in S6_07_STAGE_NAMES],
                "per_calculation_result_hashes": dict(binding.per_calculation_result_hashes),
                "content_sha256": binding.combined_source_hash,
            },
            "coefficient_resolution": {
                "coefficient_id": binding.coefficient_context_id,
                "source_type": "production_persisted_context",
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
                "active_authority_revision_id": active_revision_id,
                "coefficient_context_id": context.id,
                "source_binding_coefficient_context_id": binding.coefficient_context_id,
                "definition_category": definition.category,
                "revision_status": revision.status,
                "revision_source_type": revision.source_type,
            },
            "verified_scheme_status": verified.status,
        }


def create_controlled_production_authority(
    engine: Engine, *, definition_id: str, token: str, output_path: Path | None = None
) -> dict[str, Any]:
    """Bind an HTTP-created definition to the canonical production scheme."""

    approved_revision_id = _seed_approved_revision(
        engine,
        definition_id=definition_id,
        token=token,
        label="http-controlled",
    )
    identity = new_fixture_identity(token)
    _seed_production_context(
        engine,
        identity=identity,
        definition_id=definition_id,
        approved_revision_id=approved_revision_id,
    )
    service = compose_production_scheme_service(sessionmaker(bind=engine, expire_on_commit=False))
    run = service.generate_production_scheme_run(
        GenerateProductionSchemeCommand(
            source_binding_id=identity.source_binding_id,
            weight_set_revision_id=identity.weight_revision_id,
            profile_codes=("balanced",),
            profile_parameters={},
            actor="s6-07-controlled-acceptance",
            correlation_id=f"s6-07-{identity.attempt_id}",
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
    if not isinstance(controlled, Mapping) or controlled.get("definition_id") != definition_id:
        raise RuntimeError("HTTP-created definition is not the production authority definition")
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
        "fixture_identity": asdict(identity),
    }
    _write_json(output_path, output)
    return output


def _database_engine(database_url: str) -> Engine:
    from sqlalchemy import create_engine

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
            _write_json(
                args.output,
                read_production_authority(engine, run_id=args.run_id),
            )
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
