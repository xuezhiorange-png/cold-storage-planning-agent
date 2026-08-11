from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import create_engine, text

from cold_storage.recovery import backup_bundle
from cold_storage.recovery.backup_bundle import (
    _postgres_child_env,
    _run_postgres_tool,
    collect_artifact_inventory,
    collect_database_inventory,
    collect_database_inventory_from_connection,
)
from cold_storage.recovery.cli import main


def _database_url() -> str | None:
    value = os.environ.get("COLD_STORAGE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if value and value.startswith(("postgresql://", "postgresql+psycopg2://")):
        return value
    return None


def _replace_database(url: str, database: str) -> str:
    parsed = urlsplit(url.replace("postgresql+psycopg2://", "postgresql://", 1))
    return urlunsplit(("postgresql+psycopg2", parsed.netloc, f"/{database}", parsed.query, ""))


@pytest.mark.postgresql
def test_controlled_recovery_seed_matches_migrated_postgresql_schema_contract() -> None:
    """Exercise the controlled workflow seed against the Alembic head schema."""
    source_url = _database_url()
    if source_url is None:
        pytest.skip("PostgreSQL URL is required for the migrated-schema regression")

    engine = create_engine(source_url, future=True)
    outbox_event_id = "legacy-audit:33333333-3333-4333-8333-333333333333"
    connection = engine.connect()
    transaction = connection.begin()
    try:
        connection.execute(
            text(
                """
                INSERT INTO projects (
                    id, code, name, location, product_category, status,
                    current_version_number, created_at, updated_at
                ) VALUES (
                    '11111111-1111-4111-8111-111111111111',
                    'CONTROLLED-RECOVERY-001',
                    'Controlled Recovery Project',
                    'synthetic-location',
                    'synthetic-product',
                    'draft',
                    1,
                    TIMESTAMPTZ '2026-01-01T00:00:00Z',
                    TIMESTAMPTZ '2026-01-01T00:00:00Z'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO project_versions (
                    id, project_id, version_number, change_summary, status,
                    input_snapshot, calculation_snapshot, assumption_snapshot,
                    created_at, updated_at, created_by, parent_version_id,
                    submitted_at, reviewed_at, approved_at, approved_by, archived_at
                ) VALUES (
                    '22222222-2222-4222-8222-222222222222',
                    '11111111-1111-4111-8111-111111111111',
                    1,
                    'controlled recovery seed',
                    'draft',
                    CAST(:input_snapshot AS JSON),
                    CAST(:calculation_snapshot AS JSON),
                    CAST(:assumption_snapshot AS JSON),
                    TIMESTAMPTZ '2026-01-01T00:00:00Z',
                    TIMESTAMPTZ '2026-01-01T00:00:00Z',
                    'controlled-recovery-fixture',
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL
                )
                """
            ),
            {
                "input_snapshot": '{"source":"controlled-recovery","revision":1}',
                "calculation_snapshot": '{"result":"deterministic"}',
                "assumption_snapshot": '{"assumption":"synthetic-only"}',
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO audit_events (
                    id, actor, action, entity_type, entity_id,
                    before_snapshot, after_snapshot, event_metadata, created_at,
                    outbox_event_id
                ) VALUES (
                    '33333333-3333-4333-8333-333333333333',
                    'controlled-recovery-fixture',
                    'CONTROLLED_RECOVERY_SEED',
                    'project',
                    '11111111-1111-4111-8111-111111111111',
                    CAST(:before_snapshot AS JSON),
                    CAST(:after_snapshot AS JSON),
                    CAST(:event_metadata AS JSON),
                    TIMESTAMPTZ '2026-01-01T00:00:00Z',
                    :outbox_event_id
                )
                """
            ),
            {
                "before_snapshot": "{}",
                "after_snapshot": '{"status":"seeded"}',
                "event_metadata": '{"synthetic":true,"fixture":"TASK-012"}',
                "outbox_event_id": outbox_event_id,
            },
        )

        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM projects WHERE id='11111111-1111-4111-8111-111111111111'"
                )
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM project_versions "
                    "WHERE id='22222222-2222-4222-8222-222222222222'"
                )
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT outbox_event_id FROM audit_events "
                    "WHERE id='33333333-3333-4333-8333-333333333333'"
                )
            ).scalar_one()
            == outbox_event_id
        )
        assert (
            connection.execute(
                text(
                    "SELECT outbox_event_id IS NOT NULL FROM audit_events "
                    "WHERE id='33333333-3333-4333-8333-333333333333'"
                )
            ).scalar_one()
            is True
        )
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.mark.postgresql
def test_backup_restore_verify_preserves_source_and_isolates_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_url = _database_url()
    if source_url is None or shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        pytest.skip("PostgreSQL URL and client tools are required for recovery acceptance")
    source_engine = create_engine(source_url, future=True)
    target_database = f"task012_restore_{uuid.uuid4().hex[:12]}"
    target_url = _replace_database(source_url, target_database)
    maintenance_url = _replace_database(source_url, "postgres")
    maintenance_engine = create_engine(maintenance_url, future=True)
    source_artifacts = tmp_path / "source-artifacts"
    source_artifacts.mkdir()
    (source_artifacts / "deterministic.txt").write_text("task012\n", encoding="utf-8")
    (source_artifacts / "nested").mkdir()
    (source_artifacts / "nested" / "payload.bin").write_bytes(b"payload")
    target_artifacts = tmp_path / "target-artifacts"
    backup_root = tmp_path / "backups"
    receipt_root = tmp_path / "receipt"
    source_table = f"task012_recovery_{uuid.uuid4().hex[:8]}"
    try:
        with maintenance_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.execute(text(f'CREATE DATABASE "{target_database}"'))
        with source_engine.begin() as connection:
            connection.execute(
                text(f'CREATE TABLE "{source_table}" (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
            )
            connection.execute(
                text(f'INSERT INTO "{source_table}" (id, value) VALUES (1, :value)'),
                {"value": "deterministic"},
            )
        monkeypatch.setenv("TASK012_BACKUP_AUTHORIZED", "YES")
        monkeypatch.setenv("TASK012_ISOLATED_RESTORE_AUTHORIZED", "YES")
        monkeypatch.setenv("COLD_STORAGE_DATABASE_URL", source_url)
        monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(source_artifacts))
        monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "source-ci")
        monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "source-db-ci")
        monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "source-artifact-ci")
        monkeypatch.setenv("COLD_STORAGE_RESTORE_DATABASE_URL", target_url)
        monkeypatch.setenv("COLD_STORAGE_RESTORE_STORAGE_DIR", str(target_artifacts))
        monkeypatch.setenv("COLD_STORAGE_RESTORE_ENVIRONMENT_ID", "target-ci")
        monkeypatch.setenv("COLD_STORAGE_RESTORE_DATABASE_ENVIRONMENT_ID", "target-db-ci")
        monkeypatch.setenv("COLD_STORAGE_RESTORE_ARTIFACT_ENVIRONMENT_ID", "target-artifact-ci")
        source_before_db = collect_database_inventory(source_engine)
        source_before_artifacts = collect_artifact_inventory(
            source_artifacts,
            failure_code="BACKUP_ARTIFACT_FAILED",
        )
        assert (
            main(
                [
                    "backup",
                    "--execute-backup",
                    "--backup-root",
                    str(backup_root),
                ]
            )
            == 0
        )
        bundles = sorted(path for path in backup_root.iterdir() if path.is_dir())
        assert len(bundles) == 1
        bundle = bundles[0]
        assert (
            main(
                [
                    "restore-isolated",
                    "--execute-restore",
                    "--backup-bundle",
                    str(bundle),
                    "--output-dir",
                    str(receipt_root),
                ]
            )
            == 0
        )
        receipt = receipt_root / "restore-receipt.json"
        assert (
            main(
                [
                    "verify-restore",
                    "--backup-bundle",
                    str(bundle),
                    "--receipt",
                    str(receipt),
                ]
            )
            == 0
        )
        assert collect_database_inventory(source_engine) == source_before_db
        assert (
            collect_artifact_inventory(
                source_artifacts,
                failure_code="BACKUP_ARTIFACT_FAILED",
            )
            == source_before_artifacts
        )
        assert (target_artifacts / "deterministic.txt").read_text(encoding="utf-8") == "task012\n"
        assert (target_artifacts / "nested" / "payload.bin").read_bytes() == b"payload"
    finally:
        try:
            with source_engine.begin() as connection:
                connection.execute(text(f'DROP TABLE IF EXISTS "{source_table}"'))
        finally:
            with maintenance_engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as connection:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{target_database}"'))
            source_engine.dispose()
            maintenance_engine.dispose()


@pytest.mark.postgresql
def test_database_dump_and_inventory_share_exported_snapshot(
    tmp_path: Path,
) -> None:
    source_url = _database_url()
    if source_url is None or shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        pytest.skip("PostgreSQL URL and client tools are required for recovery acceptance")
    source_engine = create_engine(source_url, future=True)
    target_database = f"task012_snapshot_{uuid.uuid4().hex[:12]}"
    target_url = _replace_database(source_url, target_database)
    maintenance_engine = create_engine(_replace_database(source_url, "postgres"), future=True)
    source_table = f"task012_snapshot_{uuid.uuid4().hex[:8]}"
    dump_path = tmp_path / "snapshot.dump"
    try:
        with maintenance_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.execute(text(f'CREATE DATABASE "{target_database}"'))
        with source_engine.begin() as connection:
            connection.execute(
                text(f'CREATE TABLE "{source_table}" (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
            )
            connection.execute(
                text(f'INSERT INTO "{source_table}" (id, value) VALUES (1, :value)'),
                {"value": "row-a"},
            )
        source_database = _postgres_child_env(
            source_url,
            code="BACKUP_DATABASE_FAILED",
        )[1]["PGDATABASE"]
        with backup_bundle._export_database_snapshot(source_engine) as (
            snapshot_connection,
            snapshot_id,
        ):
            with source_engine.begin() as connection:
                connection.execute(
                    text(f'INSERT INTO "{source_table}" (id, value) VALUES (2, :value)'),
                    {"value": "row-b"},
                )
            snapshot_inventory = collect_database_inventory_from_connection(snapshot_connection)
            _run_postgres_tool(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--snapshot",
                    snapshot_id,
                    "--file",
                    str(dump_path),
                    "--dbname",
                    source_database,
                ],
                database_url=source_url,
                code="BACKUP_DATABASE_FAILED",
            )
        target_database_name = _postgres_child_env(
            target_url,
            code="RESTORE_DATABASE_FAILED",
        )[1]["PGDATABASE"]
        _run_postgres_tool(
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                target_database_name,
                str(dump_path),
            ],
            database_url=target_url,
            code="RESTORE_DATABASE_FAILED",
        )
        target_engine = create_engine(target_url, future=True)
        try:
            restored_inventory = collect_database_inventory(
                target_engine,
                expected_schema_head=snapshot_inventory["schema_head"],
            )
        finally:
            target_engine.dispose()
        assert restored_inventory == snapshot_inventory
    finally:
        with source_engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS "{source_table}"'))
        with maintenance_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{target_database}"'))
        source_engine.dispose()
        maintenance_engine.dispose()
