"""V0.8 P4 controlled acceptance integration tests (PostgreSQL)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v08_sample_loader import trusted_sample_client
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from tests.integration.test_v08_p4_controlled_acceptance_sqlite import (
    MISSING_OPERATOR_KEY_CASES,
    assert_demo_catalog_leaves_remain_unverified,
    execute_missing_operator_key,
    run_p4_controlled_acceptance,
)
from tests.integration.v07_p2_consistency_evidence import assert_zero_canonical_rows
from tests.integration.v08_p3_operator_fixtures import (
    assert_reports_engine_dialect,
    configure_postgresql_env,
    isolated_process_state,
    operator_seed,
)

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "P4 PostgreSQL integration tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )


@pytest.mark.postgresql
def test_v08_p4_pg_controlled_acceptance(pg_database: str, tmp_path: Path) -> None:
    artifact_dir = tmp_path / "pg-artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_postgresql_env(pg_database, artifact_dir)
        with trusted_sample_client(pg_database, storage_dir=artifact_dir) as (client, service):
            assert_reports_engine_dialect("postgresql")
            seeded, _by_name = operator_seed(client)
            run_p4_controlled_acceptance(client, seeded, service)


@pytest.mark.postgresql
@pytest.mark.parametrize(
    "leaf_name,_label",
    MISSING_OPERATOR_KEY_CASES,
    ids=[case[1] for case in MISSING_OPERATOR_KEY_CASES],
)
def test_v08_p4_pg_missing_operator_key_fail_closed(
    pg_database: str,
    tmp_path: Path,
    leaf_name: str,
    _label: str,
) -> None:
    artifact_dir = tmp_path / "pg-missing-key-artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_postgresql_env(pg_database, artifact_dir)
        service = create_database_project_service(pg_database)
        with TestClient(create_app(project_service=service)) as client:
            assert_reports_engine_dialect("postgresql")
            created = client.post(
                "/api/v1/projects",
                json={
                    "name": f"V08-P4 pg missing key {uuid.uuid4().hex[:8]}",
                    "location": "山东",
                    "product_category": "blueberry",
                },
            )
            assert created.status_code == 200, created.text
            project_id = created.json()["id"]
            version_number = created.json()["current_version_number"]
            version_id = client.get(
                f"/api/v1/projects/{project_id}/versions/{version_number}"
            ).json()["id"]

            response = execute_missing_operator_key(
                client,
                project_id=project_id,
                version_number=version_number,
                leaf_name=leaf_name,
            )
            assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

            with sessionmaker(bind=service.engine, expire_on_commit=False)() as session:
                assert_zero_canonical_rows(session, version_id)


@pytest.mark.postgresql
def test_v08_p4_pg_demo_catalog_leaves_remain_unverified(
    pg_database: str,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "pg-demo-review-artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_postgresql_env(pg_database, artifact_dir)
        with trusted_sample_client(pg_database, storage_dir=artifact_dir) as (client, _service):
            assert_reports_engine_dialect("postgresql")
            _seeded, by_name = operator_seed(client)
            assert_demo_catalog_leaves_remain_unverified(by_name)
