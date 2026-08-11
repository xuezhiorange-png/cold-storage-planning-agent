from __future__ import annotations

import json
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from cold_storage.recovery import backup_bundle, restore_runner
from cold_storage.recovery.backup_bundle import RecoveryError


class _FakeEngine:
    dialect = SimpleNamespace(name="postgresql")

    def dispose(self) -> None:
        pass


def _make_bundle(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, object]]:
    root = tmp_path / "bundle"
    root.mkdir()
    storage = tmp_path / "storage-source"
    storage.mkdir()
    (storage / "report.txt").write_text("report\n", encoding="utf-8")
    artifact_inventory = backup_bundle.collect_artifact_inventory(
        storage,
        failure_code="BACKUP_ARTIFACT_FAILED",
    )
    backup_bundle._write_artifact_archive(
        storage,
        root / "artifacts.tar",
        failure_code="BACKUP_ARTIFACT_FAILED",
    )
    database_inventory: dict[str, object] = {
        "schema_version": backup_bundle.DATABASE_INVENTORY_SCHEMA_VERSION,
        "schema_head": "0039_widen_report_export_artifact_mime_type",
        "table_count": 0,
        "tables": [],
    }
    backup_bundle._write_json(root / "database-inventory.json", database_inventory)
    (root / "database.dump").write_bytes(b"dump")
    now = datetime.now(UTC).replace(microsecond=0)
    manifest: dict[str, object] = {
        "schema_version": backup_bundle.BACKUP_SCHEMA_VERSION,
        "task": "TASK-012",
        "version": "V0.2",
        "backup_id": "123e4567-e89b-42d3-a456-426614174000",
        "source_environment_id": "source-ci",
        "source_database_environment_id": "source-db-ci",
        "source_artifact_environment_id": "source-artifact-ci",
        "source_schema_head": database_inventory["schema_head"],
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "retention_days": 30,
        "expires_at": (now + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        "database_dump_digest": backup_bundle._sha256_file(root / "database.dump"),
        "database_inventory_digest": backup_bundle.inventory_digest(database_inventory),
        "artifact_archive_digest": backup_bundle._sha256_file(root / "artifacts.tar"),
        "artifact_inventory_digest": backup_bundle.inventory_digest(artifact_inventory),
        "verification_result": "PASS",
    }
    backup_bundle._write_json(root / "artifact-inventory.json", artifact_inventory)
    backup_bundle._write_json(root / "backup-manifest.json", manifest)
    backup_bundle._write_checksums(root, backup_bundle.BACKUP_PAYLOAD_FILES)
    return root, database_inventory, artifact_inventory


def _set_restore_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TASK012_ISOLATED_RESTORE_AUTHORIZED", "YES")
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_URL", "postgresql+psycopg2://source:secret@localhost:5432/source"
    )
    source_root = tmp_path / "source-artifacts"
    source_root.mkdir()
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(source_root))
    monkeypatch.setenv(
        "COLD_STORAGE_RESTORE_DATABASE_URL",
        "postgresql+psycopg2://target:secret@localhost:5432/target",
    )
    monkeypatch.setenv("COLD_STORAGE_RESTORE_ENVIRONMENT_ID", "target-ci")
    monkeypatch.setenv("COLD_STORAGE_RESTORE_DATABASE_ENVIRONMENT_ID", "target-db-ci")
    monkeypatch.setenv("COLD_STORAGE_RESTORE_ARTIFACT_ENVIRONMENT_ID", "target-artifact-ci")
    monkeypatch.setenv("COLD_STORAGE_RESTORE_STORAGE_DIR", str(tmp_path / "target-artifacts"))


def _patch_mock_restore(
    monkeypatch: pytest.MonkeyPatch,
    database_inventory: dict[str, object],
    artifact_inventory: dict[str, object],
) -> None:
    monkeypatch.setattr(
        restore_runner,
        "_create_postgres_engine",
        lambda *args, **kwargs: _FakeEngine(),
    )
    monkeypatch.setattr(restore_runner, "_require_empty_database", lambda engine: None)
    monkeypatch.setattr(restore_runner, "_verify_constraints", lambda engine: None)
    monkeypatch.setattr(restore_runner, "_verify_readiness", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        restore_runner,
        "collect_database_inventory",
        lambda *args, **kwargs: database_inventory,
    )
    monkeypatch.setattr(
        restore_runner,
        "collect_artifact_inventory",
        lambda *args, **kwargs: artifact_inventory,
    )
    monkeypatch.setattr(backup_bundle, "_run_postgres_tool", lambda *args, **kwargs: None)


def test_restore_requires_both_execution_guards_before_bundle_or_target_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def fail_if_bundle_is_read(path: Path) -> backup_bundle.BackupBundle:
        nonlocal called
        called = True
        raise AssertionError("bundle must not be read without both guards")

    monkeypatch.setattr(restore_runner, "validate_backup_bundle", fail_if_bundle_is_read)
    with pytest.raises(RecoveryError, match="RESTORE_EXECUTION_NOT_AUTHORIZED"):
        restore_runner.restore_isolated(
            bundle_root=tmp_path / "missing",
            output_dir=tmp_path / "output",
            execute_restore=False,
        )
    assert called is False


def test_validate_backup_rejects_modified_database_dump(tmp_path: Path) -> None:
    root, _, _ = _make_bundle(tmp_path)
    (root / "database.dump").write_bytes(b"modified dump")
    with pytest.raises(RecoveryError, match="BACKUP_CHECKSUM_MISMATCH"):
        backup_bundle.validate_backup_bundle(root)


def test_validate_backup_rejects_modified_artifact_archive(tmp_path: Path) -> None:
    root, _, _ = _make_bundle(tmp_path)
    with (root / "artifacts.tar").open("ab") as stream:
        stream.write(b"modified")
    with pytest.raises(RecoveryError, match="BACKUP_CHECKSUM_MISMATCH"):
        backup_bundle.validate_backup_bundle(root)


def test_validate_backup_rejects_archive_inventory_mismatch(tmp_path: Path) -> None:
    root, _, _ = _make_bundle(tmp_path)
    changed_source = tmp_path / "changed-source"
    changed_source.mkdir()
    (changed_source / "report.txt").write_text("changed\n", encoding="utf-8")
    backup_bundle._write_artifact_archive(
        changed_source,
        root / "artifacts.tar",
        failure_code="BACKUP_ARTIFACT_FAILED",
    )
    manifest = backup_bundle._load_json(root / "backup-manifest.json", code="test")
    manifest["artifact_archive_digest"] = backup_bundle._sha256_file(root / "artifacts.tar")
    backup_bundle._write_json(root / "backup-manifest.json", manifest)
    backup_bundle._write_checksums(root, backup_bundle.BACKUP_PAYLOAD_FILES)
    with pytest.raises(RecoveryError, match="RESTORE_BUNDLE_INVALID"):
        backup_bundle.validate_backup_bundle(root)


def test_validate_backup_rejects_malformed_manifest(tmp_path: Path) -> None:
    root, _, _ = _make_bundle(tmp_path)
    (root / "backup-manifest.json").write_text("{}\n", encoding="utf-8")
    backup_bundle._write_checksums(root, backup_bundle.BACKUP_PAYLOAD_FILES)
    with pytest.raises(RecoveryError, match="RESTORE_BUNDLE_INVALID"):
        backup_bundle.validate_backup_bundle(root)


def test_restore_happy_path_extracts_only_after_database_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_root, database_inventory, artifact_inventory = _make_bundle(tmp_path)
    _set_restore_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        restore_runner,
        "_create_postgres_engine",
        lambda *args, **kwargs: _FakeEngine(),
    )
    monkeypatch.setattr(restore_runner, "_require_empty_database", lambda engine: None)
    monkeypatch.setattr(restore_runner, "_verify_constraints", lambda engine: None)
    monkeypatch.setattr(restore_runner, "_verify_readiness", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        restore_runner,
        "collect_database_inventory",
        lambda *args, **kwargs: database_inventory,
    )
    monkeypatch.setattr(
        restore_runner,
        "collect_artifact_inventory",
        lambda *args, **kwargs: artifact_inventory,
    )
    events: list[str] = []

    def fake_tool(argv: list[str], **kwargs: object) -> None:
        events.append("pg_restore")

    monkeypatch.setattr(backup_bundle, "_run_postgres_tool", fake_tool)
    receipt = restore_runner.restore_isolated(
        bundle_root=bundle_root,
        output_dir=tmp_path / "receipt",
        execute_restore=True,
    )
    assert events == ["pg_restore"]
    assert receipt.name == "restore-receipt.json"
    assert json.loads(receipt.read_text(encoding="utf-8"))["verification_result"] == "PASS"


def test_restore_refuses_non_empty_artifact_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_root, _, _ = _make_bundle(tmp_path)
    _set_restore_environment(monkeypatch, tmp_path)
    target = tmp_path / "target-artifacts"
    target.mkdir()
    (target / "preexisting.txt").write_text("do not overwrite", encoding="utf-8")
    monkeypatch.setattr(
        restore_runner,
        "_create_postgres_engine",
        lambda *args, **kwargs: _FakeEngine(),
    )
    monkeypatch.setattr(restore_runner, "_require_empty_database", lambda engine: None)
    with pytest.raises(RecoveryError, match="RESTORE_ARTIFACT_TARGET_NOT_EMPTY"):
        restore_runner.restore_isolated(
            bundle_root=bundle_root,
            output_dir=tmp_path / "receipt",
            execute_restore=True,
        )


@pytest.mark.parametrize(
    ("variable", "value"),
    (
        (
            "COLD_STORAGE_RESTORE_DATABASE_URL",
            "postgresql+psycopg2://target:secret@localhost:5432/source",
        ),
        ("COLD_STORAGE_RESTORE_DATABASE_ENVIRONMENT_ID", "source-db-ci"),
        ("COLD_STORAGE_RESTORE_STORAGE_DIR", "source-artifacts"),
    ),
)
def test_restore_rejects_source_target_identity_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    bundle_root, _, _ = _make_bundle(tmp_path)
    _set_restore_environment(monkeypatch, tmp_path)
    if variable == "COLD_STORAGE_RESTORE_STORAGE_DIR":
        value = str(tmp_path / value)
        (tmp_path / value).mkdir(exist_ok=True)
    monkeypatch.setenv(variable, value)
    with pytest.raises(RecoveryError, match="RESTORE_TARGET_ISOLATION_UNVERIFIED"):
        restore_runner.restore_isolated(
            bundle_root=bundle_root,
            output_dir=tmp_path / "receipt",
            execute_restore=True,
        )


@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_restore_rejects_non_exact_bundle_file_set(tmp_path: Path, mutation: str) -> None:
    bundle_root, _, _ = _make_bundle(tmp_path)
    if mutation == "missing":
        (bundle_root / "database.dump").unlink()
    else:
        (bundle_root / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(RecoveryError, match="RESTORE_BUNDLE_INVALID"):
        restore_runner.validate_backup_bundle(bundle_root)


def test_restore_rejects_database_inventory_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_root, database_inventory, artifact_inventory = _make_bundle(tmp_path)
    _set_restore_environment(monkeypatch, tmp_path)
    observed_inventory = dict(database_inventory)
    observed_inventory["table_count"] = 1
    _patch_mock_restore(monkeypatch, observed_inventory, artifact_inventory)
    with pytest.raises(RecoveryError, match="RESTORE_DATABASE_INVENTORY_MISMATCH"):
        restore_runner.restore_isolated(
            bundle_root=bundle_root,
            output_dir=tmp_path / "receipt",
            execute_restore=True,
        )


def test_restore_rejects_artifact_inventory_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_root, database_inventory, artifact_inventory = _make_bundle(tmp_path)
    _set_restore_environment(monkeypatch, tmp_path)
    observed_inventory = dict(artifact_inventory)
    observed_inventory["total_bytes"] = int(observed_inventory["total_bytes"]) + 1
    _patch_mock_restore(monkeypatch, database_inventory, observed_inventory)
    with pytest.raises(RecoveryError, match="RESTORE_ARTIFACT_INVENTORY_MISMATCH"):
        restore_runner.restore_isolated(
            bundle_root=bundle_root,
            output_dir=tmp_path / "receipt",
            execute_restore=True,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda root: (root / "report.txt").unlink(),
        lambda root: (root / "extra.txt").write_text("extra", encoding="utf-8"),
        lambda root: (root / "report.txt").write_text("tampered", encoding="utf-8"),
    ),
    ids=("missing", "extra", "hash-mismatch"),
)
def test_verify_restore_rejects_post_restore_artifact_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: object
) -> None:
    bundle_root, database_inventory, artifact_inventory = _make_bundle(tmp_path)
    _set_restore_environment(monkeypatch, tmp_path)
    _patch_mock_restore(monkeypatch, database_inventory, artifact_inventory)
    receipt = restore_runner.restore_isolated(
        bundle_root=bundle_root,
        output_dir=tmp_path / "receipt",
        execute_restore=True,
    )
    assert callable(mutation)
    mutation(tmp_path / "target-artifacts")
    monkeypatch.setattr(
        restore_runner,
        "collect_artifact_inventory",
        lambda root, **kwargs: backup_bundle.collect_artifact_inventory(
            root, failure_code="RESTORE_ARTIFACT_INVENTORY_MISMATCH"
        ),
    )
    with pytest.raises(RecoveryError, match="RESTORE_ARTIFACT_INVENTORY_MISMATCH"):
        restore_runner.verify_restore(
            bundle_root=bundle_root,
            receipt_path=receipt,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_head_expected", "forged-schema-head"),
        ("database_inventory_expected_digest", "sha256:" + "0" * 64),
        ("artifact_inventory_expected_digest", "sha256:" + "0" * 64),
        ("backup_manifest_digest", "sha256:" + "0" * 64),
        ("database_table_count", 999),
        ("artifact_file_count", 999),
        ("target_environment_id", "forged-target"),
    ),
)
def test_verify_restore_rejects_forged_receipt_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    bundle_root, database_inventory, artifact_inventory = _make_bundle(tmp_path)
    _set_restore_environment(monkeypatch, tmp_path)
    _patch_mock_restore(monkeypatch, database_inventory, artifact_inventory)
    receipt = restore_runner.restore_isolated(
        bundle_root=bundle_root,
        output_dir=tmp_path / "receipt",
        execute_restore=True,
    )
    forged = json.loads(receipt.read_text(encoding="utf-8"))
    forged[field] = value
    receipt.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(RecoveryError, match="RESTORE_RECEIPT_INVALID"):
        restore_runner.verify_restore(bundle_root=bundle_root, receipt_path=receipt)


def test_restore_rechecks_final_artifact_target_before_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_root, database_inventory, artifact_inventory = _make_bundle(tmp_path)
    _set_restore_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(
        restore_runner, "_create_postgres_engine", lambda *args, **kwargs: _FakeEngine()
    )
    monkeypatch.setattr(restore_runner, "_require_empty_database", lambda engine: None)
    monkeypatch.setattr(restore_runner, "_verify_constraints", lambda engine: None)
    monkeypatch.setattr(restore_runner, "_verify_readiness", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        restore_runner,
        "collect_database_inventory",
        lambda *args, **kwargs: database_inventory,
    )
    real_collect = backup_bundle.collect_artifact_inventory

    def collect_artifacts(root: Path, **kwargs: object) -> dict[str, object]:
        if root.name.startswith(".task012-restore-artifacts-"):
            return artifact_inventory
        return real_collect(root, **kwargs)

    monkeypatch.setattr(restore_runner, "collect_artifact_inventory", collect_artifacts)
    original_promote = restore_runner._promote_artifact_root

    def promote_with_race(staged: Path, target: Path) -> None:
        original_promote(staged, target)
        (target / "race.txt").write_text("appeared after promotion", encoding="utf-8")

    monkeypatch.setattr(restore_runner, "_promote_artifact_root", promote_with_race)
    monkeypatch.setattr(backup_bundle, "_run_postgres_tool", lambda *args, **kwargs: None)
    with pytest.raises(RecoveryError, match="RESTORE_ARTIFACT_INVENTORY_MISMATCH"):
        restore_runner.restore_isolated(
            bundle_root=bundle_root,
            output_dir=tmp_path / "receipt",
            execute_restore=True,
        )
    assert not (tmp_path / "receipt" / "restore-receipt.json").exists()


def test_restore_rejects_traversal_tar_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.tar"
    with tarfile.open(archive_path, "w") as archive:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        archive.addfile(info, __import__("io").BytesIO(b"x"))
    with pytest.raises(RecoveryError, match="RESTORE_ARTIFACT_FAILED"):
        restore_runner._safe_extract_archive(archive_path, tmp_path / "extracted")


def test_restore_rejects_forged_non_pass_receipt(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"verification_result": "PASS", "extra": True}), encoding="utf-8")
    with pytest.raises(RecoveryError, match="RESTORE_RECEIPT_INVALID"):
        restore_runner._validate_receipt({"verification_result": "PASS", "extra": True})
