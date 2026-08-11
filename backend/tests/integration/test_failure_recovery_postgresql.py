from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from cold_storage.recovery import backup_bundle, restore_runner
from cold_storage.recovery.failure_recovery import (
    FailureState,
    RecoveryDecision,
    canonical_digest,
    classify_failure_state,
    make_migration_recovery_receipt,
    verify_migration_recovery_receipt,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def package2_pg_database(pg_database_factory, monkeypatch: pytest.MonkeyPatch) -> str:
    """Create a Package 2 database and apply Alembic to that exact URL."""
    database_url = pg_database_factory(prefix="pkg2_int")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_URL", database_url)
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    environment = os.environ.copy()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Alembic upgrade to head failed:\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"
    )
    return database_url


@pytest.fixture()
def package2_pg_engine(package2_pg_database: str):
    engine = create_engine(package2_pg_database, poolclass=NullPool)
    yield engine
    engine.dispose()


def _current_alembic_head() -> str:
    script = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, f"expected one Alembic head, got {heads}"
    return heads[0]


def _temporary_alembic_config(tmp_path: Path) -> tuple[Path, Path]:
    versions = tmp_path / "versions"
    versions.mkdir()
    source = (BACKEND_ROOT / "alembic.ini").read_text(encoding="utf-8")
    source = source.replace(
        "script_location = alembic",
        "\n".join(
            (
                f"script_location = {BACKEND_ROOT / 'alembic'}",
                "version_locations = "
                f"{BACKEND_ROOT / 'alembic' / 'versions'}{os.pathsep}{versions}",
                "path_separator = os",
            )
        ),
    )
    config = tmp_path / "alembic.ini"
    config.write_text(source, encoding="utf-8")
    return config, versions


def _write_revision(
    versions: Path,
    *,
    revision: str,
    down_revision: str,
    upgrade_body: str,
) -> Path:
    path = versions / f"{revision}.py"
    path.write_text(
        "\n".join(
            (
                '"""Temporary Package 2 failure-injection revision."""',
                "from typing import Sequence, Union",
                "",
                "from alembic import op",
                "",
                f"revision: str = {revision!r}",
                f"down_revision: Union[str, None] = {down_revision!r}",
                "branch_labels: Union[str, Sequence[str], None] = None",
                "depends_on: Union[str, Sequence[str], None] = None",
                "",
                upgrade_body.strip(),
                "",
                "def downgrade() -> None:",
                '    raise RuntimeError("TASK012_PACKAGE2_DOWNGRADE_FORBIDDEN")',
                "",
            )
        ),
        encoding="utf-8",
    )
    return path


def _migration_environment(database_url: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": database_url,
            "DATABASE_BACKEND": "postgresql",
            "COLD_STORAGE_DATABASE_URL": database_url,
            "COLD_STORAGE_DATABASE_BACKEND": "postgresql",
        }
    )
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(BACKEND_ROOT / "src"), environment.get("PYTHONPATH", "")))
    )
    return environment


def _run_migration_failure(
    *, config: Path, revision: str, database_url: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(config), "upgrade", revision],
        cwd=BACKEND_ROOT,
        env=_migration_environment(database_url),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _assert_table_absent(engine, table_name: str) -> None:
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT to_regclass(:qualified_name)"),
            {"qualified_name": f"public.{table_name}"},
        ).scalar_one()
    assert result is None, f"temporary table remained: {table_name}"


def _assert_table_present(engine, table_name: str) -> None:
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT to_regclass(:qualified_name)"),
            {"qualified_name": f"public.{table_name}"},
        ).scalar_one()
    assert result == f"{table_name}"


def _inventory_pair(engine, artifact_root: Path) -> tuple[dict[str, object], dict[str, object]]:
    return (
        backup_bundle.collect_database_inventory(engine),
        backup_bundle.collect_artifact_inventory(
            artifact_root,
            failure_code="BACKUP_ARTIFACT_FAILED",
        ),
    )


@pytest.mark.postgresql
def test_transactional_alembic_failure_is_real_and_rolls_back(
    package2_pg_database: str,
    package2_pg_engine,
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "transactional-artifacts"
    artifact_root.mkdir()
    (artifact_root / "controlled.txt").write_text("package2\n", encoding="utf-8")
    before_database, before_artifact = _inventory_pair(package2_pg_engine, artifact_root)
    config, versions = _temporary_alembic_config(tmp_path)
    revision = "task012_pkg2_transactional_failure"
    revision_path = _write_revision(
        versions,
        revision=revision,
        down_revision=_current_alembic_head(),
        upgrade_body="""
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "task012_pkg2_transactional_marker",
        sa.Column("id", sa.Integer(), nullable=False),
    )
    raise RuntimeError("TASK012_PACKAGE2_TRANSACTIONAL_MIGRATION_FAILURE_INJECTED")
""",
    )
    try:
        result = _run_migration_failure(
            config=config,
            revision=revision,
            database_url=package2_pg_database,
        )
        output = f"{result.stdout}\n{result.stderr}"
        assert result.returncode != 0
        assert "TASK012_PACKAGE2_TRANSACTIONAL_MIGRATION_FAILURE_INJECTED" in output
        _assert_table_absent(package2_pg_engine, "task012_pkg2_transactional_marker")

        after_database, after_artifact = _inventory_pair(package2_pg_engine, artifact_root)
        assessment = classify_failure_state(
            pre_deployment_schema_head=before_database["schema_head"],
            post_failure_schema_head=after_database["schema_head"],
            pre_deployment_database_inventory_digest=backup_bundle.inventory_digest(
                before_database
            ),
            post_failure_database_inventory_digest=backup_bundle.inventory_digest(after_database),
            pre_deployment_artifact_inventory_digest=backup_bundle.inventory_digest(
                before_artifact
            ),
            post_failure_artifact_inventory_digest=backup_bundle.inventory_digest(after_artifact),
        )
        assert before_database == after_database
        assert before_artifact == after_artifact
        assert assessment.failure_state is FailureState.SCHEMA_AND_DATA_UNCHANGED
        assert assessment.recovery_decision is RecoveryDecision.APP_ONLY_ROLLBACK_ALLOWED
        assert assessment.app_only_rollback_allowed is True
    finally:
        revision_path.unlink(missing_ok=True)


@pytest.mark.postgresql
def test_partial_alembic_failure_requires_isolated_recovery(
    package2_pg_database: str,
    package2_pg_engine,
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "partial-artifacts"
    artifact_root.mkdir()
    (artifact_root / "controlled.txt").write_text("package2\n", encoding="utf-8")
    before_database, before_artifact = _inventory_pair(package2_pg_engine, artifact_root)
    config, versions = _temporary_alembic_config(tmp_path)
    revision = "task012_pkg2_partial_failure"
    revision_path = _write_revision(
        versions,
        revision=revision,
        down_revision=_current_alembic_head(),
        upgrade_body="""
import os

from sqlalchemy import create_engine, text


def upgrade() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    connection = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        connection.execute(
            text("CREATE TABLE task012_pkg2_partial_marker (id INTEGER PRIMARY KEY)")
        )
    finally:
        connection.close()
        engine.dispose()
    raise RuntimeError("TASK012_PACKAGE2_PARTIAL_MIGRATION_FAILURE_INJECTED")
""",
    )
    try:
        result = _run_migration_failure(
            config=config,
            revision=revision,
            database_url=package2_pg_database,
        )
        output = f"{result.stdout}\n{result.stderr}"
        assert result.returncode != 0
        assert "TASK012_PACKAGE2_PARTIAL_MIGRATION_FAILURE_INJECTED" in output
        _assert_table_present(package2_pg_engine, "task012_pkg2_partial_marker")
        after_database, after_artifact = _inventory_pair(package2_pg_engine, artifact_root)
        assessment = classify_failure_state(
            pre_deployment_schema_head=before_database["schema_head"],
            post_failure_schema_head=after_database["schema_head"],
            pre_deployment_database_inventory_digest=backup_bundle.inventory_digest(
                before_database
            ),
            post_failure_database_inventory_digest=backup_bundle.inventory_digest(after_database),
            pre_deployment_artifact_inventory_digest=backup_bundle.inventory_digest(
                before_artifact
            ),
            post_failure_artifact_inventory_digest=backup_bundle.inventory_digest(after_artifact),
        )
        assert backup_bundle.inventory_digest(after_database) != backup_bundle.inventory_digest(
            before_database
        )
        assert assessment.app_only_rollback_allowed is False
        assert assessment.migration_recovery_required is True
        assert assessment.recovery_decision is RecoveryDecision.MIGRATION_RECOVERY_REQUIRED
    finally:
        cleanup = package2_pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            cleanup.execute(text("DROP TABLE IF EXISTS task012_pkg2_partial_marker"))
        finally:
            cleanup.close()
        revision_path.unlink(missing_ok=True)


@pytest.mark.postgresql
def test_package1_restore_and_verify_bind_real_partial_migration_recovery(
    package2_pg_database: str,
    pg_database_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        pytest.skip("PostgreSQL client tools are required for Package 1 reuse")

    source_engine = backup_bundle._create_postgres_engine(
        package2_pg_database,
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
    config, versions = _temporary_alembic_config(tmp_path)
    revision = "task012_pkg2_restore_partial_failure"
    revision_path = _write_revision(
        versions,
        revision=revision,
        down_revision=_current_alembic_head(),
        upgrade_body="""
import os

from sqlalchemy import create_engine, text


def upgrade() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    connection = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        connection.execute(
            text("CREATE TABLE task012_pkg2_restore_failure_marker (id INTEGER NOT NULL)")
        )
    finally:
        connection.close()
        engine.dispose()
    raise RuntimeError("TASK012_PACKAGE2_RESTORE_PARTIAL_MIGRATION_FAILURE_INJECTED")
""",
    )
    try:
        monkeypatch.setenv("TASK012_BACKUP_AUTHORIZED", "YES")
        monkeypatch.setenv("TASK012_ISOLATED_RESTORE_AUTHORIZED", "YES")
        monkeypatch.setenv("COLD_STORAGE_DATABASE_URL", package2_pg_database)
        monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(source_artifacts))
        monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "controlled-release-source")
        monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "controlled-release-source-db")
        monkeypatch.setenv(
            "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "controlled-release-source-artifacts"
        )

        before_database, before_artifact = _inventory_pair(source_engine, source_artifacts)
        bundle = backup_bundle.create_backup(
            backup_root=backup_root,
            execute_backup=True,
            source_environment_id="controlled-release-source",
            source_database_environment_id="controlled-release-source-db",
            source_artifact_environment_id="controlled-release-source-artifacts",
            source_artifact_root=source_artifacts,
        )
        result = _run_migration_failure(
            config=config,
            revision=revision,
            database_url=package2_pg_database,
        )
        output = f"{result.stdout}\n{result.stderr}"
        assert result.returncode != 0
        assert "TASK012_PACKAGE2_RESTORE_PARTIAL_MIGRATION_FAILURE_INJECTED" in output
        _assert_table_present(source_engine, "task012_pkg2_restore_failure_marker")

        post_failure_database, post_failure_artifact = _inventory_pair(
            source_engine, source_artifacts
        )
        assessment = classify_failure_state(
            pre_deployment_schema_head=before_database["schema_head"],
            post_failure_schema_head=post_failure_database["schema_head"],
            pre_deployment_database_inventory_digest=backup_bundle.inventory_digest(
                before_database
            ),
            post_failure_database_inventory_digest=backup_bundle.inventory_digest(
                post_failure_database
            ),
            pre_deployment_artifact_inventory_digest=backup_bundle.inventory_digest(
                before_artifact
            ),
            post_failure_artifact_inventory_digest=backup_bundle.inventory_digest(
                post_failure_artifact
            ),
        )
        assert assessment.migration_recovery_required is True

        restore_receipt = restore_runner.restore_isolated(
            bundle_root=bundle,
            output_dir=restore_receipt_root,
            execute_restore=True,
            target_database_url=target_database,
            target_artifact_root=target_artifacts,
            target_environment_id="controlled-release-recovered",
            target_database_environment_id="controlled-release-recovered-db",
            target_artifact_environment_id="controlled-release-recovered-artifacts",
        )
        restore_runner.verify_restore(
            bundle_root=bundle,
            receipt_path=restore_receipt,
            target_database_url=target_database,
            target_artifact_root=target_artifacts,
            target_environment_id="controlled-release-recovered",
            target_database_environment_id="controlled-release-recovered-db",
            target_artifact_environment_id="controlled-release-recovered-artifacts",
        )
        after_database, after_artifact = _inventory_pair(target_engine, target_artifacts)
        assert after_database == before_database
        assert after_artifact == before_artifact
        receipt = make_migration_recovery_receipt(
            backup_id=bundle.name,
            backup_manifest_digest=backup_bundle._sha256_file(bundle / "backup-manifest.json"),
            pre_migration_database_inventory_digest=backup_bundle.inventory_digest(before_database),
            pre_migration_artifact_inventory_digest=backup_bundle.inventory_digest(before_artifact),
            pre_migration_schema_head=before_database["schema_head"],
            migration_failure_class="FAILED_MIGRATION_PARTIAL_MUTATION",
            post_failure_schema_head=post_failure_database["schema_head"],
            post_failure_database_inventory_digest=backup_bundle.inventory_digest(
                post_failure_database
            ),
            post_failure_artifact_inventory_digest=backup_bundle.inventory_digest(
                post_failure_artifact
            ),
            source_environment_id="controlled-release-source",
            restore_target_environment_id="controlled-release-recovered",
            source_database_environment_id="controlled-release-source-db",
            restore_target_database_environment_id="controlled-release-recovered-db",
            source_artifact_environment_id="controlled-release-source-artifacts",
            restore_target_artifact_environment_id="controlled-release-recovered-artifacts",
            restore_backup_id=bundle.name,
            restore_receipt_digest=backup_bundle._sha256_file(restore_receipt),
            final_schema_head=after_database["schema_head"],
            final_database_inventory_digest=backup_bundle.inventory_digest(after_database),
            final_artifact_inventory_digest=backup_bundle.inventory_digest(after_artifact),
            independent_restore_verification="PASS",
            post_recovery_live_status="PASS",
            post_recovery_ready_status="PASS",
        )
        assert verify_migration_recovery_receipt(receipt)["migration_recovery_result"] == "PASS"
        assert canonical_digest(receipt).startswith("sha256:")
    finally:
        cleanup = source_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            cleanup.execute(text("DROP TABLE IF EXISTS task012_pkg2_restore_failure_marker"))
        finally:
            cleanup.close()
        target_engine.dispose()
        source_engine.dispose()
        revision_path.unlink(missing_ok=True)
