"""V0.5 P5 controlled acceptance integration matrix (SQLite)."""

from __future__ import annotations

import os

import pytest

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite V0.5 P5 controlled acceptance tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

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

pytest_plugins = ["tests.integration.v05_p5_acceptance_evidence"]


def test_p5_sqlite_sample_seed_canonical_five_with_lineage(migrated_client) -> None:
    client, _service, _engine = migrated_client
    evidence_sample_seed_canonical_five_with_lineage(client)


def test_p5_sqlite_restart_preserves_calculation_ids_and_hashes(migrated_client) -> None:
    client, service, _engine = migrated_client
    project_id, version_number, _by_name = evidence_sample_seed_canonical_five_with_lineage(client)
    evidence_restart_preserves_calculation_ids_and_hashes(
        client, service, project_id, version_number
    )


@pytest.mark.parametrize("dotted_path,_label", MISSING_KEY_CASES)
def test_p5_sqlite_missing_key_leaf_fails_closed_atomically(
    migrated_client, dotted_path: str, _label: str
) -> None:
    client, _service, engine = migrated_client
    evidence_missing_key_leaf_fails_closed_atomically(client, engine, dotted_path=dotted_path)


def test_p5_sqlite_workflow_scheme_report_consume_persisted_rows(migrated_client) -> None:
    client, service, engine = migrated_client
    project_id, version_number, _by_name = evidence_sample_seed_canonical_five_with_lineage(client)
    evidence_workflow_scheme_report_consume_persisted_installed_power(
        client, service, engine, project_id, version_number
    )


def test_p5_sqlite_demo_coefficients_remain_marked(migrated_client) -> None:
    client, _service, _engine = migrated_client
    project_id, version_number, _by_name = evidence_sample_seed_canonical_five_with_lineage(client)
    evidence_demo_coefficients_remain_marked(client, project_id, version_number)


def test_p5_sqlite_agent_assistance_not_fake_available(migrated_client) -> None:
    client, _service, _engine = migrated_client
    project_id, version_number, _by_name = evidence_sample_seed_canonical_five_with_lineage(client)
    evidence_agent_assistance_not_fake_available(client, project_id, version_number)


def test_p5_sqlite_seed_uses_five_stage_execution_only(migrated_client) -> None:
    client, _service, _engine = migrated_client
    seeded = seed_sample_project(client)
    assert seeded.five_stage_success is True
