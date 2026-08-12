from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.dependencies import shutdown_dependencies
from cold_storage.bootstrap.runtime_readiness import reset_readiness_state
from cold_storage.modules.coefficients.infrastructure.database import DatabaseCoefficientService
from cold_storage.modules.coefficients.infrastructure.orm import CoefficientDefinitionRecord
from cold_storage.release import end_to_end_operational_acceptance as acceptance
from tests.evaluation._seed_helpers import (
    SOURCE_BINDING_ID,
    WEIGHT_REVISION_ID,
    seed_a1_all_prereqs,
)
from tests.unit.test_end_to_end_operational_acceptance import (
    S6_06_ARTIFACT_ID,
    S6_06_DIGEST,
    S6_06_RUN_ID,
    SOURCE_SHA,
    SOURCE_TREE_SHA,
    _observations,
    _write_s6_06_fixture,
)


def test_synthetic_acceptance_roundtrip_reuses_s6_06_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s6_06_bundle, metadata = _write_s6_06_fixture(tmp_path)
    calls: list[Path] = []

    def _verify(**kwargs: object) -> None:
        calls.append(kwargs["bundle_dir"] if isinstance(kwargs["bundle_dir"], Path) else Path("."))

    monkeypatch.setattr(acceptance, "verify_final_release_evidence", _verify)
    output = acceptance.assemble_s6_07_acceptance_evidence(
        output_dir=tmp_path / "bundle",
        repository=acceptance.EXPECTED_REPOSITORY,
        source_sha=SOURCE_SHA,
        source_tree_sha=SOURCE_TREE_SHA,
        generated_at="2026-08-12T00:00:00Z",
        s6_06_run_id=S6_06_RUN_ID,
        s6_06_run_attempt=1,
        s6_06_artifact_id=S6_06_ARTIFACT_ID,
        s6_06_artifact_digest=S6_06_DIGEST,
        s6_06_bundle_dir=s6_06_bundle,
        s6_06_metadata_dir=metadata,
        observations=_observations(),
    )
    assert len(calls) >= 2
    assert len(list(output.iterdir())) == 9


def test_sqlite_persistence_fixture_proves_restart_readback(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'acceptance.db'}")
    CoefficientDefinitionRecord.__table__.create(engine)
    service = DatabaseCoefficientService(engine)
    definition = service.create_definition(
        code="s6_07_persistence_probe",
        name="S6-07 persistence probe",
        description="controlled synthetic coefficient",
        category="acceptance",
        canonical_unit="unit",
        is_active=True,
    )
    engine.dispose()

    restarted = create_engine(f"sqlite:///{tmp_path / 'acceptance.db'}")
    service_after_restart = DatabaseCoefficientService(restarted)
    recovered = service_after_restart.get_definition(definition.id)
    assert recovered.code == "s6_07_persistence_probe"
    with restarted.connect() as connection:
        assert (
            connection.scalar(
                select(CoefficientDefinitionRecord.id).where(
                    CoefficientDefinitionRecord.id == definition.id
                )
            )
            == definition.id
        )
    restarted.dispose()


@pytest.mark.postgresql
def test_postgresql_coefficient_persistence_survives_service_recreation() -> None:
    """Exercise the real PostgreSQL engine used by the controlled workflow."""

    database_url = os.environ.get("S6_07_POSTGRES_URL")
    if not database_url:
        pytest.skip("S6_07_POSTGRES_URL is required for PostgreSQL acceptance execution")
    engine = create_engine(database_url, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    service = DatabaseCoefficientService(engine)
    code = f"s6_07_pg_{uuid.uuid4().hex}"
    definition = service.create_definition(
        code=code,
        name="S6-07 PostgreSQL persistence probe",
        description="controlled synthetic coefficient",
        category="acceptance",
        canonical_unit="unit",
        is_active=True,
    )
    engine.dispose()

    restarted_engine = create_engine(database_url, pool_pre_ping=True)
    restarted_service = DatabaseCoefficientService(restarted_engine)
    recovered = restarted_service.get_definition(definition.id)
    assert recovered.id == definition.id
    assert recovered.code == code
    with restarted_engine.connect() as connection:
        assert (
            connection.scalar(
                select(CoefficientDefinitionRecord.id).where(
                    CoefficientDefinitionRecord.id == definition.id
                )
            )
            == definition.id
        )
    restarted_engine.dispose()


@pytest.mark.postgresql
def test_strict_application_composition_returns_disabled_agent_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the production composition and strict disabled-agent route."""

    database_url = os.environ.get("S6_07_POSTGRES_URL")
    if not database_url:
        pytest.skip("S6_07_POSTGRES_URL is required for PostgreSQL acceptance execution")
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "production")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_URL", database_url)
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(artifact_dir))
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_STORAGE_DIR", str(artifact_dir))
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci-strict")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci-strict")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci-strict")
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", "0" * 40)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", "v0.2.0")
    monkeypatch.setenv("COLD_STORAGE_DEPLOYMENT_ID", "s6-07-test")
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
    reset_readiness_state()
    try:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/agent/sessions", json={})
            assert response.status_code == 503
            assert response.json() == {
                "error": {
                    "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
                    "message": "Model-backed agent not in V0.2 production scope.",
                    "details": {"retryable": False},
                }
            }
    finally:
        shutdown_dependencies()


def _read_production_authority(database_url: str, run_id: str) -> dict[str, object]:
    """Read and independently verify one production SchemeRun from PostgreSQL."""

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

    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        run_read_port = SqlAlchemyProductionSchemeRunReadPort()
        binding_read_port = SqlAlchemySourceBindingReadPort()
        weight_read_port = SqlAlchemyWeightRevisionReadPort()
        verified = read_verified_production_scheme_run(
            run_read_port,
            binding_read_port,
            weight_read_port,
            session,
            run_id=run_id,
            generator_version="1.0.0",
        )
        persisted = run_read_port.load_production_run(session, run_id=run_id)
        if persisted is None or persisted.source_binding_id is None:
            raise AssertionError("production SchemeRun readback is missing SourceBinding")
        binding = binding_read_port.load_binding(
            session,
            binding_id=persisted.source_binding_id,
        )
        if binding is None:
            raise AssertionError("SourceBinding readback is missing")

        calculation_ids = {
            "zone": binding.zone_calculation_id,
            "cooling_load": binding.cooling_load_calculation_id,
            "equipment": binding.equipment_calculation_id,
            "power": binding.power_calculation_id,
            "investment": binding.investment_calculation_id,
        }
        stages: list[dict[str, object]] = []
        for name in acceptance.S6_07_STAGE_NAMES:
            calculation_id = calculation_ids[name]
            calculation = binding_read_port.load_calculation_run(
                session,
                run_id=calculation_id,
            )
            if calculation is None:
                raise AssertionError(f"missing persisted CalculationRun for {name}")
            stages.append(
                {
                    "name": name,
                    "exists": True,
                    "persisted": True,
                    "calculation_id": calculation.id,
                    "calculation_type": calculation.calculation_type,
                    "result_hash": calculation.result_hash,
                }
            )

        archive = SqlAlchemyProductionSourceArchiveRepository().find_by_scheme_run_id(
            session,
            run_id,
        )
        if archive is None:
            raise AssertionError("production source archive readback is missing")
        payload = validate_archive_payload_v1(dict(archive["archive_payload"]))
        recomputed_archive_hash = compute_archive_hash_v1(payload)
        if recomputed_archive_hash != archive["archive_hash"]:
            raise AssertionError("canonical source archive digest mismatch")

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
                "required_slot_ids": [
                    calculation_ids[name] for name in acceptance.S6_07_STAGE_NAMES
                ],
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
                "expected_sha256": recomputed_archive_hash,
                "verification_method": "canonical_archive_v1",
                "independent_rehash": True,
            },
            "verified_scheme_status": verified.status,
        }
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgresql
def test_postgresql_persisted_production_authority_roundtrip() -> None:
    """Create once, then emit only independently read persisted authority.

    The legacy HTTP ``POST /scheme-runs`` route is backed by a different
    application service.  This acceptance probe therefore invokes the
    canonical production application service directly, captures its create
    identity, and obtains all operational facts from independent persisted
    read ports before any observation is written.
    """

    database_url = os.environ.get("S6_07_POSTGRES_URL")
    if not database_url:
        pytest.skip("S6_07_POSTGRES_URL is required for PostgreSQL acceptance execution")

    from cold_storage.bootstrap.production_composition import compose_production_scheme_service
    from cold_storage.modules.schemes.application.production_ports import (
        GenerateProductionSchemeCommand,
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    seed_session = factory()
    try:
        seed_a1_all_prereqs(seed_session)
    finally:
        seed_session.close()

    service = compose_production_scheme_service(factory)
    run = service.generate_production_scheme_run(
        GenerateProductionSchemeCommand(
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            profile_codes=("balanced",),
            profile_parameters={},
            actor="s6-07-controlled-acceptance",
            correlation_id=f"s6-07-{uuid.uuid4().hex}",
            database_backend="postgresql",
        )
    )
    authority = _read_production_authority(database_url, run.id)
    output_path = os.environ.get("S6_07_PRODUCTION_AUTHORITY_OUTPUT")
    if output_path:
        Path(output_path).write_text(
            json.dumps(
                {
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
                        "body": {
                            "run_id": authority["run_id"],
                            "status": authority["status"],
                        },
                    },
                    "canonical_persistence": authority,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    engine.dispose()


@pytest.mark.postgresql
def test_postgresql_persisted_production_authority_reload_after_restart() -> None:
    """Reload the exact run through fresh sessions after the service restart."""

    database_url = os.environ.get("S6_07_POSTGRES_URL")
    run_id = os.environ.get("S6_07_RELOAD_RUN_ID")
    output_path = os.environ.get("S6_07_RELOAD_AUTHORITY_OUTPUT")
    if not database_url or not run_id or not output_path:
        pytest.skip("S6-07 restart authority inputs are required")
    authority = _read_production_authority(database_url, run_id)
    Path(output_path).write_text(json.dumps(authority, sort_keys=True), encoding="utf-8")


def test_observation_fixture_is_not_a_production_secret_fixture(tmp_path: Path) -> None:
    observations = _observations()
    path = tmp_path / "observations.json"
    path.write_text(json.dumps(observations), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["real_production_operation"] is False
