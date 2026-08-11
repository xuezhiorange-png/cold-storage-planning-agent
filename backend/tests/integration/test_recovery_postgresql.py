from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import create_engine, text

from cold_storage.recovery.backup_bundle import (
    collect_artifact_inventory,
    collect_database_inventory,
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
