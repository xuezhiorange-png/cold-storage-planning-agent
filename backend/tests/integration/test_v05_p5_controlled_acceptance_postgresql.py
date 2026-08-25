"""V0.5 P5 controlled acceptance integration matrix (PostgreSQL)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL V0.5 P5 controlled acceptance tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from tests.integration.v05_p5_acceptance_evidence import (
    MISSING_KEY_CASES,
    evidence_agent_assistance_not_fake_available,
    evidence_demo_coefficients_remain_marked,
    evidence_missing_key_leaf_fails_closed_atomically,
    evidence_restart_preserves_calculation_ids_and_hashes,
    evidence_sample_seed_canonical_five_with_lineage,
    evidence_workflow_scheme_report_consume_persisted_installed_power,
    seed_sample_project,
)


@pytest.fixture()
def pg_client(pg_engine):
    service = DatabaseProjectService(pg_engine)
    client = TestClient(create_app(project_service=service))
    return client, service, pg_engine


def test_p5_pg_sample_seed_canonical_five_with_lineage(pg_client) -> None:
    client, _service, _engine = pg_client
    evidence_sample_seed_canonical_five_with_lineage(client)


def test_p5_pg_restart_preserves_calculation_ids_and_hashes(pg_client) -> None:
    client, service, _engine = pg_client
    project_id, version_number, _by_name = evidence_sample_seed_canonical_five_with_lineage(client)
    evidence_restart_preserves_calculation_ids_and_hashes(
        client, service, project_id, version_number
    )


@pytest.mark.parametrize("dotted_path,_label", MISSING_KEY_CASES)
def test_p5_pg_missing_key_leaf_fails_closed_atomically(
    pg_client, dotted_path: str, _label: str
) -> None:
    client, _service, engine = pg_client
    evidence_missing_key_leaf_fails_closed_atomically(client, engine, dotted_path=dotted_path)


def test_p5_pg_workflow_scheme_report_consume_persisted_rows(pg_client) -> None:
    client, service, engine = pg_client
    project_id, version_number, _by_name = evidence_sample_seed_canonical_five_with_lineage(client)
    evidence_workflow_scheme_report_consume_persisted_installed_power(
        client, service, engine, project_id, version_number
    )


def test_p5_pg_demo_coefficients_remain_marked(pg_client) -> None:
    client, _service, _engine = pg_client
    project_id, version_number, _by_name = evidence_sample_seed_canonical_five_with_lineage(client)
    evidence_demo_coefficients_remain_marked(client, project_id, version_number)


def test_p5_pg_agent_assistance_not_fake_available(pg_client) -> None:
    client, _service, _engine = pg_client
    project_id, version_number, _by_name = evidence_sample_seed_canonical_five_with_lineage(client)
    evidence_agent_assistance_not_fake_available(client, project_id, version_number)


def test_p5_pg_seed_uses_five_stage_execution_only(pg_client) -> None:
    client, _service, _engine = pg_client
    seeded = seed_sample_project(client)
    assert seeded.five_stage_success is True
