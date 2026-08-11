from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

from cold_storage.recovery import backup_bundle, restore_runner
from cold_storage.recovery.failure_recovery import (
    FailureState,
    canonical_digest,
    classify_failure_state,
    make_migration_recovery_receipt,
    verify_migration_recovery_receipt,
)


@pytest.mark.postgresql
def test_transactional_migration_failure_classifies_schema_and_data_unchanged(
    pg_engine,
) -> None:
    before = backup_bundle.collect_database_inventory(pg_engine)
    connection = pg_engine.connect()
    transaction = connection.begin()
    try:
        connection.execute(
            text(
                "CREATE TABLE task012_pkg2_transaction_marker "
                "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
        transaction.rollback()
    finally:
        connection.close()

    after = backup_bundle.collect_database_inventory(pg_engine)
    assessment = classify_failure_state(
        pre_deployment_schema_head=before["schema_head"],
        post_failure_schema_head=after["schema_head"],
        pre_deployment_database_inventory_digest=backup_bundle.inventory_digest(before),
        post_failure_database_inventory_digest=backup_bundle.inventory_digest(after),
    )
    assert before == after
    assert assessment.failure_state is FailureState.SCHEMA_AND_DATA_UNCHANGED
    assert assessment.app_only_rollback_allowed is True
    assert assessment.migration_recovery_required is False


@pytest.mark.postgresql
def test_partial_migration_mutation_requires_isolated_recovery(pg_engine) -> None:
    before = backup_bundle.collect_database_inventory(pg_engine)
    connection = pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        connection.execute(
            text(
                "CREATE TABLE task012_pkg2_partial_marker "
                "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
    finally:
        connection.close()

    try:
        after = backup_bundle.collect_database_inventory(pg_engine)
        assessment = classify_failure_state(
            pre_deployment_schema_head=before["schema_head"],
            post_failure_schema_head=after["schema_head"],
            pre_deployment_database_inventory_digest=backup_bundle.inventory_digest(before),
            post_failure_database_inventory_digest=backup_bundle.inventory_digest(after),
        )
        assert assessment.failure_state is FailureState.DATA_CHANGED
        assert assessment.app_only_rollback_allowed is False
        assert assessment.migration_recovery_required is True
    finally:
        cleanup = pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            cleanup.execute(text("DROP TABLE IF EXISTS task012_pkg2_partial_marker"))
        finally:
            cleanup.close()


@pytest.mark.postgresql
def test_package1_backup_restore_verify_binds_migration_recovery_to_isolated_target(
    pg_database: str,
    pg_database_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        pytest.skip("PostgreSQL client tools are required for Package 1 reuse")

    source_engine = backup_bundle._create_postgres_engine(
        pg_database,
        code="BACKUP_DATABASE_FAILED",
    )
    target_database = pg_database_factory(prefix="pkg2_recovered")
    target_engine = backup_bundle._create_postgres_engine(
        target_database,
        code="RESTORE_DATABASE_FAILED",
    )
    source_artifacts = tmp_path / "source-artifacts"
    source_artifacts.mkdir()
    (source_artifacts / "controlled.txt").write_text("package2\n", encoding="utf-8")
    target_artifacts = tmp_path / "recovered-artifacts"
    backup_root = tmp_path / "backups"
    restore_receipt_root = tmp_path / "restore-receipt"
    try:
        monkeypatch.setenv("TASK012_BACKUP_AUTHORIZED", "YES")
        monkeypatch.setenv("TASK012_ISOLATED_RESTORE_AUTHORIZED", "YES")
        monkeypatch.setenv("COLD_STORAGE_DATABASE_URL", pg_database)
        monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(source_artifacts))
        monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "controlled-release-source")
        monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "controlled-release-source-db")
        monkeypatch.setenv(
            "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "controlled-release-source-artifacts"
        )

        before_database = backup_bundle.collect_database_inventory(source_engine)
        before_artifact = backup_bundle.collect_artifact_inventory(
            source_artifacts,
            failure_code="BACKUP_ARTIFACT_FAILED",
        )
        bundle = backup_bundle.create_backup(
            backup_root=backup_root,
            execute_backup=True,
            source_environment_id="controlled-release-source",
            source_database_environment_id="controlled-release-source-db",
            source_artifact_environment_id="controlled-release-source-artifacts",
            source_artifact_root=source_artifacts,
        )
        restore_receipt = restore_runner.restore_isolated(
            bundle_root=bundle.root,
            output_dir=restore_receipt_root,
            execute_restore=True,
            target_database_url=target_database,
            target_artifact_root=target_artifacts,
            target_environment_id="controlled-release-recovered",
            target_database_environment_id="controlled-release-recovered-db",
            target_artifact_environment_id="controlled-release-recovered-artifacts",
        )
        restore_runner.verify_restore(
            bundle_root=bundle.root,
            receipt_path=restore_receipt,
            target_database_url=target_database,
            target_artifact_root=target_artifacts,
            target_environment_id="controlled-release-recovered",
            target_database_environment_id="controlled-release-recovered-db",
            target_artifact_environment_id="controlled-release-recovered-artifacts",
        )
        after_database = backup_bundle.collect_database_inventory(target_engine)
        after_artifact = backup_bundle.collect_artifact_inventory(
            target_artifacts,
            failure_code="RESTORE_ARTIFACT_INVENTORY_MISMATCH",
        )
        receipt = make_migration_recovery_receipt(
            backup_id=bundle.backup_id,
            backup_manifest_digest=backup_bundle._sha256_file(bundle.root / "backup-manifest.json"),
            pre_migration_database_inventory_digest=backup_bundle.inventory_digest(before_database),
            pre_migration_artifact_inventory_digest=backup_bundle.inventory_digest(before_artifact),
            pre_migration_schema_head=before_database["schema_head"],
            migration_failure_class="FAILED_MIGRATION_PARTIAL_MUTATION",
            post_failure_schema_head=before_database["schema_head"],
            post_failure_database_inventory_digest=backup_bundle.inventory_digest(before_database),
            post_failure_artifact_inventory_digest=backup_bundle.inventory_digest(before_artifact),
            source_environment_id="controlled-release-source",
            restore_target_environment_id="controlled-release-recovered",
            source_database_environment_id="controlled-release-source-db",
            restore_target_database_environment_id="controlled-release-recovered-db",
            source_artifact_environment_id="controlled-release-source-artifacts",
            restore_target_artifact_environment_id="controlled-release-recovered-artifacts",
            restore_backup_id=bundle.backup_id,
            restore_receipt_digest=backup_bundle._sha256_file(restore_receipt),
            final_schema_head=after_database["schema_head"],
            final_database_inventory_digest=backup_bundle.inventory_digest(after_database),
            final_artifact_inventory_digest=backup_bundle.inventory_digest(after_artifact),
        )
        assert verify_migration_recovery_receipt(receipt)["migration_recovery_result"] == "PASS"
        assert canonical_digest(receipt).startswith("sha256:")
    finally:
        target_engine.dispose()
        source_engine.dispose()
