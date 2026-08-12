from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

from cold_storage.modules.coefficients.infrastructure.database import DatabaseCoefficientService
from cold_storage.modules.coefficients.infrastructure.orm import CoefficientDefinitionRecord
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
def test_postgresql_controlled_acceptance_requires_explicit_database_authority() -> None:
    """The real S6-07 workflow supplies this authority; local runs never guess it."""

    database_url = __import__("os").environ.get("S6_07_POSTGRES_URL")
    if not database_url:
        pytest.skip("S6_07_POSTGRES_URL is required for PostgreSQL acceptance execution")
    assert database_url.startswith(("postgresql://", "postgresql+psycopg2://"))


def test_observation_fixture_is_not_a_production_secret_fixture(tmp_path: Path) -> None:
    observations = _observations()
    path = tmp_path / "observations.json"
    path.write_text(json.dumps(observations), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["real_production_operation"] is False
