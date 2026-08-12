from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.dependencies import shutdown_dependencies
from cold_storage.bootstrap.runtime_readiness import reset_readiness_state
from cold_storage.bootstrap.s6_07_controlled_fixture import (
    _CATALOG_VALUES,
    _seed_approved_revision,
    _seed_required_catalog,
    create_controlled_coefficient_definition,
    create_controlled_production_authority,
    read_production_authority,
    seed_startup_readiness,
)
from cold_storage.modules.coefficients.infrastructure.database import DatabaseCoefficientService
from cold_storage.modules.coefficients.infrastructure.orm import CoefficientDefinitionRecord
from cold_storage.modules.orchestration.domain.errors import AmbiguousCoefficientError
from cold_storage.modules.projects.infrastructure.orm import Base
from cold_storage.release import end_to_end_operational_acceptance as acceptance
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
    identity_path = tmp_path / "build-identity.json"
    identity_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "commit_sha": "0" * 40,
                "version": "v0.2.0",
            }
        ),
        encoding="utf-8",
    )
    from cold_storage.bootstrap import deployment_identity

    load_runtime_identity = deployment_identity.load_runtime_identity

    def load_test_identity(
        *,
        env: Mapping[str, str],
        path: Path | str = deployment_identity.DEFAULT_BUILD_IDENTITY_PATH,
    ) -> tuple[deployment_identity.BuildIdentityRecord, str]:
        return load_runtime_identity(env=env, path=identity_path)

    monkeypatch.setattr(deployment_identity, "load_runtime_identity", load_test_identity)
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", "1")
    monkeypatch.setenv("COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS", "30")
    reset_readiness_state()
    readiness_engine = create_engine(database_url, pool_pre_ping=True)
    seed_startup_readiness(readiness_engine, token=f"strict-{uuid.uuid4().hex}")
    readiness_engine.dispose()
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
    """Read persisted authority through the formal acceptance support boundary."""

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        return read_production_authority(engine, run_id=run_id)
    finally:
        engine.dispose()


def test_sqlite_canonical_production_authority_roundtrip(tmp_path: Path) -> None:
    """Exercise the same canonical five-stage producer used by PG acceptance."""

    engine = create_engine(f"sqlite:///{tmp_path / 'canonical-authority.db'}")
    Base.metadata.create_all(engine)
    try:
        seed_startup_readiness(engine, token=f"sqlite-{uuid.uuid4().hex}")
        definition_id = create_controlled_coefficient_definition(
            engine, token=f"sqlite-{uuid.uuid4().hex}"
        )
        document = create_controlled_production_authority(
            engine,
            definition_id=definition_id,
            token=f"sqlite-{uuid.uuid4().hex}",
        )
        authority = document["canonical_persistence"]
        assert isinstance(authority, dict)
        assert [stage["name"] for stage in authority["stages"]] == [
            "zone",
            "cooling_load",
            "equipment",
            "power",
            "investment",
        ]
        assert authority["source_binding"]["exists"] is True
        assert authority["source_archive"]["independent_rehash"] is True
        assert (
            authority["coefficient_execution_continuity"]["result"]
            == "NOT_REQUIRED_BY_V0_2_OPERATIONAL_ACCEPTANCE"
        )
        assert authority["coefficient_execution_continuity"]["available"] is False
        assert all(stage["persisted"] for stage in authority["stages"])
    finally:
        engine.dispose()


def test_sqlite_controlled_catalog_seed_reuses_valid_authority(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog-seed.db'}")
    Base.metadata.create_all(engine)
    try:
        definition_id = create_controlled_coefficient_definition(
            engine, token=f"catalog-{uuid.uuid4().hex}"
        )
        first = _seed_required_catalog(
            engine,
            token=f"first-{uuid.uuid4().hex}",
            controlled_definition_id=definition_id,
        )
        second = _seed_required_catalog(
            engine,
            token=f"second-{uuid.uuid4().hex}",
            controlled_definition_id=definition_id,
        )
        assert first == second
        service = DatabaseCoefficientService(engine)
        assert len(service.list_revisions(definition_id)) == 1
        for code in _CATALOG_VALUES:
            definition = service.get_definition_by_code(code)
            assert len(service.list_revisions(definition.id)) == 1
    finally:
        engine.dispose()


def test_sqlite_controlled_catalog_seed_rejects_value_drift(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog-value-drift.db'}")
    Base.metadata.create_all(engine)
    try:
        controlled_definition_id = create_controlled_coefficient_definition(
            engine, token=f"value-drift-{uuid.uuid4().hex}"
        )
        service = DatabaseCoefficientService(engine)
        definition = service.create_definition(
            code="area.auxiliary_area_ratio",
            name="area auxiliary ratio",
            description="invalid controlled fixture value",
            category="catalog",
            canonical_unit="ratio",
            is_active=True,
        )
        _seed_approved_revision(
            engine,
            definition_id=definition.id,
            token=f"value-drift-{uuid.uuid4().hex}",
            label="area-auxiliary-ratio",
            value=Decimal("0.09"),
        )
        with pytest.raises(RuntimeError, match="value mismatch"):
            _seed_required_catalog(
                engine,
                token=f"value-drift-{uuid.uuid4().hex}",
                controlled_definition_id=controlled_definition_id,
            )
    finally:
        engine.dispose()


def test_sqlite_controlled_catalog_seed_rejects_ambiguous_heads(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog-ambiguous.db'}")
    Base.metadata.create_all(engine)
    try:
        controlled_definition_id = create_controlled_coefficient_definition(
            engine, token=f"ambiguous-{uuid.uuid4().hex}"
        )
        service = DatabaseCoefficientService(engine)
        definition = service.create_definition(
            code="area.auxiliary_area_ratio",
            name="area auxiliary ratio",
            description="invalid controlled fixture ambiguity",
            category="catalog",
            canonical_unit="ratio",
            is_active=True,
        )
        _seed_approved_revision(
            engine,
            definition_id=definition.id,
            token=f"ambiguous-one-{uuid.uuid4().hex}",
            label="area-auxiliary-ratio-one",
            value=Decimal("0.08"),
        )
        _seed_approved_revision(
            engine,
            definition_id=definition.id,
            token=f"ambiguous-two-{uuid.uuid4().hex}",
            label="area-auxiliary-ratio-two",
            value=Decimal("0.08"),
        )
        with pytest.raises(AmbiguousCoefficientError, match="ambiguous_revisions"):
            _seed_required_catalog(
                engine,
                token=f"ambiguous-{uuid.uuid4().hex}",
                controlled_definition_id=controlled_definition_id,
            )
    finally:
        engine.dispose()


def test_sqlite_controlled_catalog_seed_rejects_unit_drift(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog-unit-drift.db'}")
    Base.metadata.create_all(engine)
    try:
        controlled_definition_id = create_controlled_coefficient_definition(
            engine, token=f"unit-drift-{uuid.uuid4().hex}"
        )
        service = DatabaseCoefficientService(engine)
        definition = service.create_definition(
            code="area.auxiliary_area_ratio",
            name="area auxiliary ratio",
            description="invalid controlled fixture unit",
            category="catalog",
            canonical_unit="bad-unit",
            is_active=True,
        )
        _seed_approved_revision(
            engine,
            definition_id=definition.id,
            token=f"unit-drift-{uuid.uuid4().hex}",
            label="area-auxiliary-ratio",
            value=Decimal("0.08"),
        )
        with pytest.raises(RuntimeError, match="unit mismatch"):
            _seed_required_catalog(
                engine,
                token=f"unit-drift-{uuid.uuid4().hex}",
                controlled_definition_id=controlled_definition_id,
            )
    finally:
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

    engine = create_engine(database_url, pool_pre_ping=True)
    definition_id = create_controlled_coefficient_definition(
        engine, token=f"roundtrip-{uuid.uuid4().hex}"
    )
    output_path = os.environ.get("S6_07_PRODUCTION_AUTHORITY_OUTPUT")
    authority_document = create_controlled_production_authority(
        engine,
        definition_id=definition_id,
        token=f"roundtrip-{uuid.uuid4().hex}",
        output_path=Path(output_path) if output_path else None,
    )
    authority = authority_document["canonical_persistence"]
    assert isinstance(authority, dict)
    output_path = os.environ.get("S6_07_PRODUCTION_AUTHORITY_OUTPUT")
    assert output_path is None or Path(output_path).is_file()
    engine.dispose()


@pytest.mark.postgresql
def test_postgresql_production_authority_survives_fresh_engine_reload() -> None:
    """Repeat authority creation, then reload the second result from a new engine."""

    database_url = os.environ.get("S6_07_POSTGRES_URL")
    if not database_url:
        pytest.skip("S6_07_POSTGRES_URL is required for PostgreSQL acceptance execution")
    engine = create_engine(database_url, pool_pre_ping=True)
    first_definition_id = create_controlled_coefficient_definition(
        engine, token=f"repeat-first-{uuid.uuid4().hex}"
    )
    first = create_controlled_production_authority(
        engine,
        definition_id=first_definition_id,
        token=f"repeat-first-{uuid.uuid4().hex}",
    )
    service = DatabaseCoefficientService(engine)
    catalog_revision_ids_after_first = {
        code: tuple(
            revision.id
            for revision in service.list_revisions(service.get_definition_by_code(code).id)
        )
        for code in _CATALOG_VALUES
    }
    second_definition_id = create_controlled_coefficient_definition(
        engine, token=f"repeat-second-{uuid.uuid4().hex}"
    )
    second = create_controlled_production_authority(
        engine,
        definition_id=second_definition_id,
        token=f"repeat-second-{uuid.uuid4().hex}",
    )
    catalog_revision_ids_after_second = {
        code: tuple(
            revision.id
            for revision in service.list_revisions(service.get_definition_by_code(code).id)
        )
        for code in _CATALOG_VALUES
    }
    assert catalog_revision_ids_after_second == catalog_revision_ids_after_first
    canonical_first = first["canonical_persistence"]
    canonical_second = second["canonical_persistence"]
    assert isinstance(canonical_first, dict)
    assert isinstance(canonical_second, dict)
    assert canonical_first["run_id"] != canonical_second["run_id"]
    assert len(canonical_second["stages"]) == 5
    run_id = str(canonical_second["run_id"])
    engine.dispose()

    restarted_engine = create_engine(database_url, pool_pre_ping=True)
    try:
        after = read_production_authority(
            restarted_engine,
            run_id=run_id,
            controlled_definition_id=second_definition_id,
        )
        assert after["run_id"] == canonical_second["run_id"]
        assert after["source_binding"] == canonical_second["source_binding"]
        assert after["stages"] == canonical_second["stages"]
        assert after["source_archive"] == canonical_second["source_archive"]
        assert after["controlled_coefficient"] == canonical_second["controlled_coefficient"]
        assert after["source_archive"]["independent_rehash"] is True
    finally:
        restarted_engine.dispose()


def test_observation_fixture_is_not_a_production_secret_fixture(tmp_path: Path) -> None:
    observations = _observations()
    path = tmp_path / "observations.json"
    path.write_text(json.dumps(observations), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["real_production_operation"] is False
