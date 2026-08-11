from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from cold_storage.recovery import backup_bundle
from cold_storage.recovery.backup_bundle import RecoveryError


class _FakeEngine:
    def dispose(self) -> None:
        pass


def _set_backup_environment(monkeypatch: pytest.MonkeyPatch, artifact_root: Path) -> None:
    monkeypatch.setenv("TASK012_BACKUP_AUTHORIZED", "YES")
    monkeypatch.setenv(
        "COLD_STORAGE_DATABASE_URL", "postgresql+psycopg2://backup:secret@localhost:5432/source"
    )
    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "source-ci")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "source-db-ci")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "source-artifact-ci")
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(artifact_root))


def test_backup_requires_both_execution_guards_before_database_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def fail_if_database_is_open(*args: object, **kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("database must not be opened without both guards")

    monkeypatch.setattr(backup_bundle, "_create_postgres_engine", fail_if_database_is_open)
    with pytest.raises(RecoveryError, match="BACKUP_EXECUTION_NOT_AUTHORIZED"):
        backup_bundle.create_backup(
            backup_root=tmp_path / "backups",
            execute_backup=False,
        )
    assert called is False


def test_backup_publishes_exact_verified_bundle_without_secret_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_root = tmp_path / "source-artifacts"
    (artifact_root / "nested").mkdir(parents=True)
    (artifact_root / "nested" / "one.txt").write_text("one\n", encoding="utf-8")
    (artifact_root / "two.txt").write_text("two\n", encoding="utf-8")
    _set_backup_environment(monkeypatch, artifact_root)
    monkeypatch.setattr(
        backup_bundle,
        "_create_postgres_engine",
        lambda *args, **kwargs: _FakeEngine(),
    )
    monkeypatch.setattr(
        backup_bundle,
        "collect_database_inventory",
        lambda engine: {
            "schema_version": backup_bundle.DATABASE_INVENTORY_SCHEMA_VERSION,
            "schema_head": "0039_widen_report_export_artifact_mime_type",
            "table_count": 0,
            "tables": [],
        },
    )

    def fake_dump(argv: list[str], **_: object) -> None:
        dump_path = Path(argv[argv.index("--file") + 1])
        dump_path.write_bytes(b"synthetic custom-format dump")

    monkeypatch.setattr(backup_bundle, "_run_postgres_tool", fake_dump)
    bundle = backup_bundle.create_backup(
        backup_root=tmp_path / "backups",
        execute_backup=True,
        retention_days=30,
    )
    assert set(path.name for path in bundle.iterdir()) == backup_bundle.BACKUP_FILES
    validated = backup_bundle.validate_backup_bundle(bundle)
    assert validated.manifest["verification_result"] == "PASS"
    assert validated.manifest["retention_days"] == 30
    assert validated.artifact_inventory["file_count"] == 2
    text_value = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in bundle.rglob("*")
    )
    assert "backup:secret" not in text_value
    assert "postgresql" not in text_value


def test_artifact_inventory_rejects_symlink(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(RecoveryError, match="BACKUP_ARTIFACT_FAILED"):
        backup_bundle.collect_artifact_inventory(root, failure_code="BACKUP_ARTIFACT_FAILED")


def test_database_logical_digest_is_order_independent() -> None:
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)"))
        connection.execute(
            text(
                "INSERT INTO alembic_version(version_num) "
                "VALUES ('0039_widen_report_export_artifact_mime_type')"
            )
        )
        connection.execute(
            text("CREATE TABLE values_table (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        )
        connection.execute(text("INSERT INTO values_table(id, value) VALUES (2, 'b'), (1, 'a')"))
    first = backup_bundle.collect_database_inventory(engine)
    second = backup_bundle.collect_database_inventory(engine)
    assert first == second
    assert first["tables"][0]["logical_digest"].startswith("sha256:")
    engine.dispose()


def test_postgres_tool_uses_environment_credentials_and_shell_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        calls.append({"args": args, "kwargs": kwargs})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(backup_bundle.subprocess, "run", fake_run)
    backup_bundle._run_postgres_tool(
        ["pg_dump", "--dbname", "source"],
        database_url="postgresql+psycopg2://user:secret@localhost:5432/source",
        code="BACKUP_DATABASE_FAILED",
    )
    assert calls
    assert calls[0]["kwargs"]["shell"] is False
    argv = calls[0]["args"][0]
    assert "secret" not in argv
    env = calls[0]["kwargs"]["env"]
    assert env["PGPASSWORD"] == "secret"
