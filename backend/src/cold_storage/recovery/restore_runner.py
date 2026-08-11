"""Fail-closed isolated restore and post-restore verification."""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from cold_storage.recovery.backup_bundle import (
    BackupBundle,
    RecoveryError,
    _canonical_json_bytes,
    _create_postgres_engine,
    _parse_pg_url,
    _postgres_child_env,
    _read_schema_head,
    _sha256_file,
    _validate_identity,
    collect_artifact_inventory,
    collect_database_inventory,
    inventory_digest,
    validate_backup_bundle,
    validate_tar_member_name,
)

RESTORE_RECEIPT_FIELDS: tuple[str, ...] = (
    "schema_version",
    "task",
    "version",
    "backup_id",
    "backup_manifest_digest",
    "source_environment_id",
    "target_environment_id",
    "source_database_environment_id",
    "target_database_environment_id",
    "source_artifact_environment_id",
    "target_artifact_environment_id",
    "schema_head_expected",
    "schema_head_actual",
    "database_table_count",
    "database_inventory_expected_digest",
    "database_inventory_actual_digest",
    "artifact_file_count",
    "artifact_inventory_expected_digest",
    "artifact_inventory_actual_digest",
    "database_restore_status",
    "artifact_restore_status",
    "database_verification_status",
    "artifact_verification_status",
    "constraint_verification_status",
    "readiness_verification_status",
    "verified_at",
    "verification_result",
)


@dataclass(frozen=True)
class RestoreTarget:
    database_url: str
    artifact_root: Path
    environment_id: str
    database_environment_id: str
    artifact_environment_id: str


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_bytes(_canonical_json_bytes(value))


def _load_object(path: Path, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(code, "JSON document is unreadable or malformed") from exc
    if not isinstance(value, dict):
        raise RecoveryError(code, "JSON document must be an object")
    return value


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise json.JSONDecodeError("duplicate key", key, 0)
        result[key] = value
    return result


def _resolve_target(
    *,
    target_database_url: str | None,
    target_artifact_root: Path | None,
    target_environment_id: str | None,
    target_database_environment_id: str | None,
    target_artifact_environment_id: str | None,
) -> RestoreTarget:
    database_url = target_database_url or os.environ.get("COLD_STORAGE_RESTORE_DATABASE_URL")
    artifact_root_value = target_artifact_root or Path(
        os.environ.get("COLD_STORAGE_RESTORE_STORAGE_DIR", "")
    )
    if not database_url:
        raise RecoveryError("RESTORE_TARGET_ISOLATION_UNVERIFIED", "restore database is missing")
    if not str(artifact_root_value) or str(artifact_root_value) == ".":
        raise RecoveryError(
            "RESTORE_TARGET_ISOLATION_UNVERIFIED", "restore artifact root is missing"
        )
    return RestoreTarget(
        database_url=database_url,
        artifact_root=artifact_root_value.resolve(),
        environment_id=_resolve_identity(
            target_environment_id,
            "COLD_STORAGE_RESTORE_ENVIRONMENT_ID",
        ),
        database_environment_id=_resolve_identity(
            target_database_environment_id,
            "COLD_STORAGE_RESTORE_DATABASE_ENVIRONMENT_ID",
        ),
        artifact_environment_id=_resolve_identity(
            target_artifact_environment_id,
            "COLD_STORAGE_RESTORE_ARTIFACT_ENVIRONMENT_ID",
        ),
    )


def _resolve_identity(explicit: str | None, env_name: str) -> str:
    value = explicit if explicit not in (None, "") else os.environ.get(env_name)
    return _validate_identity(value, code="RESTORE_TARGET_ISOLATION_UNVERIFIED")


def _ensure_target_identities_are_distinct(bundle: BackupBundle, target: RestoreTarget) -> None:
    pairs = (
        (bundle.manifest["source_environment_id"], target.environment_id),
        (
            bundle.manifest["source_database_environment_id"],
            target.database_environment_id,
        ),
        (
            bundle.manifest["source_artifact_environment_id"],
            target.artifact_environment_id,
        ),
    )
    if any(source == destination for source, destination in pairs):
        raise RecoveryError(
            "RESTORE_TARGET_ISOLATION_UNVERIFIED",
            "source and target environment identities are not distinct",
        )


def _ensure_connection_identity_is_distinct(bundle: BackupBundle, target: RestoreTarget) -> None:
    source_url = os.environ.get("COLD_STORAGE_DATABASE_URL")
    if not source_url:
        raise RecoveryError("RESTORE_TARGET_ISOLATION_UNVERIFIED", "source database is missing")
    source_identity, _ = _parse_pg_url(
        source_url,
        code="RESTORE_TARGET_ISOLATION_UNVERIFIED",
    )
    target_identity, _ = _parse_pg_url(
        target.database_url,
        code="RESTORE_TARGET_ISOLATION_UNVERIFIED",
    )
    if (
        source_identity.host == target_identity.host
        and source_identity.port == target_identity.port
        and source_identity.database == target_identity.database
    ):
        raise RecoveryError(
            "RESTORE_TARGET_ISOLATION_UNVERIFIED",
            "source and target database identities are not distinct",
        )
    if bundle.manifest["source_database_environment_id"] == target.database_environment_id:
        raise RecoveryError(
            "RESTORE_TARGET_ISOLATION_UNVERIFIED",
            "source and target database environment identities are equal",
        )


def _ensure_artifact_root_is_distinct(target: RestoreTarget) -> None:
    source_root_value = os.environ.get("COLD_STORAGE_STORAGE_DIR")
    if not source_root_value:
        raise RecoveryError(
            "RESTORE_TARGET_ISOLATION_UNVERIFIED", "source artifact root is missing"
        )
    source_root = Path(source_root_value).resolve()
    if (
        source_root == target.artifact_root
        or source_root.is_relative_to(target.artifact_root)
        or target.artifact_root.is_relative_to(source_root)
    ):
        raise RecoveryError(
            "RESTORE_TARGET_ISOLATION_UNVERIFIED",
            "source and target artifact roots are not distinct",
        )


def _require_empty_database(engine: Engine) -> None:
    try:
        tables = []
        inspector = inspect(engine)
        for schema in sorted(inspector.get_schema_names()):
            if schema in {"information_schema", "pg_catalog"} or schema.startswith("pg_"):
                continue
            tables.extend(inspector.get_table_names(schema=schema))
    except Exception as exc:
        raise RecoveryError(
            "RESTORE_TARGET_ISOLATION_UNVERIFIED",
            "target database emptiness could not be verified",
        ) from exc
    if tables:
        raise RecoveryError("RESTORE_TARGET_NOT_EMPTY")


def _require_empty_artifact_root(root: Path) -> None:
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise RecoveryError("RESTORE_ARTIFACT_TARGET_NOT_EMPTY")
        try:
            if any(root.iterdir()):
                raise RecoveryError("RESTORE_ARTIFACT_TARGET_NOT_EMPTY")
        except OSError as exc:
            raise RecoveryError("RESTORE_ARTIFACT_TARGET_NOT_EMPTY") from exc
    else:
        try:
            root.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RecoveryError("RESTORE_ARTIFACT_TARGET_NOT_EMPTY") from exc


def _safe_extract_archive(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    seen: set[str] = set()
    try:
        with tarfile.open(archive_path, mode="r:") as archive:
            members = archive.getmembers()
            for member in members:
                parts = validate_tar_member_name(member.name)
                normalized = "/".join(parts)
                if normalized in seen:
                    raise RecoveryError("RESTORE_ARTIFACT_FAILED", "duplicate archive path")
                seen.add(normalized)
                if (
                    member.issym()
                    or member.islnk()
                    or member.isdev()
                    or not (member.isdir() or member.isreg())
                ):
                    raise RecoveryError(
                        "RESTORE_ARTIFACT_FAILED", "archive special entry is forbidden"
                    )
                candidate = destination.joinpath(*parts)
                parent = candidate.parent
                parent.mkdir(parents=True, exist_ok=True)
                current = destination
                for component in parts[:-1]:
                    current = current / component
                    if current.is_symlink():
                        raise RecoveryError(
                            "RESTORE_ARTIFACT_FAILED", "archive path crosses symlink"
                        )
                if member.isdir():
                    if candidate.exists() and not candidate.is_dir():
                        raise RecoveryError("RESTORE_ARTIFACT_FAILED", "archive path collision")
                    candidate.mkdir(parents=True, exist_ok=True)
                    continue
                if candidate.exists() or candidate.is_symlink():
                    raise RecoveryError("RESTORE_ARTIFACT_FAILED", "archive path collision")
                stream = archive.extractfile(member)
                if stream is None:
                    raise RecoveryError("RESTORE_ARTIFACT_FAILED", "archive file cannot be read")
                written = 0
                with stream, candidate.open("xb") as output:
                    for chunk in iter(stream.read, b""):
                        output.write(chunk)
                        written += len(chunk)
                if written != member.size:
                    raise RecoveryError("RESTORE_ARTIFACT_FAILED", "archive file size changed")
    except RecoveryError:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    except (OSError, tarfile.TarError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise RecoveryError("RESTORE_ARTIFACT_FAILED", "archive extraction failed") from exc


def _promote_artifact_root(staged: Path, target: Path) -> None:
    try:
        if not target.exists():
            staged.rename(target)
            return
        for child in sorted(staged.iterdir(), key=lambda path: path.name):
            destination = target / child.name
            if destination.exists() or destination.is_symlink():
                raise RecoveryError(
                    "RESTORE_ARTIFACT_FAILED", "artifact target changed during restore"
                )
            child.rename(destination)
        staged.rmdir()
    except RecoveryError:
        raise
    except OSError as exc:
        raise RecoveryError(
            "RESTORE_ARTIFACT_FAILED", "artifact target publication failed"
        ) from exc


def _verify_constraints(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        raise RecoveryError("RESTORE_CONSTRAINT_VERIFICATION_FAILED", "PostgreSQL is required")
    query = text(
        "SELECT n.nspname, c.conname "
        "FROM pg_constraint AS c "
        "JOIN pg_namespace AS n ON n.oid = c.connamespace "
        "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
        "AND NOT c.convalidated"
    )
    try:
        with engine.connect() as connection:
            rows = connection.execute(query).all()
    except Exception as exc:
        raise RecoveryError(
            "RESTORE_CONSTRAINT_VERIFICATION_FAILED",
            "database constraints could not be verified",
        ) from exc
    if rows:
        raise RecoveryError(
            "RESTORE_CONSTRAINT_VERIFICATION_FAILED",
            "database contains unvalidated application constraints",
        )


def _verify_readiness(engine: Engine, artifact_root: Path, *, expected_schema_head: str) -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        _read_schema_head(
            engine,
            expected=expected_schema_head,
            code="RESTORE_READINESS_FAILED",
        )
        if not artifact_root.is_dir() or artifact_root.is_symlink():
            raise RecoveryError(
                "RESTORE_READINESS_FAILED", "restored artifact storage is unavailable"
            )
        probe = artifact_root / ".task012-recovery-readiness-probe"
        probe.write_bytes(b"ok")
        probe.unlink()
    except RecoveryError:
        raise
    except OSError as exc:
        raise RecoveryError(
            "RESTORE_READINESS_FAILED", "restored artifact storage is not writable"
        ) from exc
    except Exception as exc:
        raise RecoveryError("RESTORE_READINESS_FAILED", "restored database is not ready") from exc


def _receipt_for(
    bundle: BackupBundle,
    target: RestoreTarget,
    *,
    schema_head_actual: str,
    database_actual: Mapping[str, Any],
    artifact_actual: Mapping[str, Any],
    verified_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "cold-storage-restore-receipt-v1",
        "task": "TASK-012",
        "version": "V0.2",
        "backup_id": bundle.backup_id,
        "backup_manifest_digest": _sha256_file(bundle.root / "backup-manifest.json"),
        "source_environment_id": bundle.manifest["source_environment_id"],
        "target_environment_id": target.environment_id,
        "source_database_environment_id": bundle.manifest["source_database_environment_id"],
        "target_database_environment_id": target.database_environment_id,
        "source_artifact_environment_id": bundle.manifest["source_artifact_environment_id"],
        "target_artifact_environment_id": target.artifact_environment_id,
        "schema_head_expected": bundle.manifest["source_schema_head"],
        "schema_head_actual": schema_head_actual,
        "database_table_count": database_actual["table_count"],
        "database_inventory_expected_digest": bundle.manifest["database_inventory_digest"],
        "database_inventory_actual_digest": inventory_digest(database_actual),
        "artifact_file_count": artifact_actual["file_count"],
        "artifact_inventory_expected_digest": bundle.manifest["artifact_inventory_digest"],
        "artifact_inventory_actual_digest": inventory_digest(artifact_actual),
        "database_restore_status": "PASS",
        "artifact_restore_status": "PASS",
        "database_verification_status": "PASS",
        "artifact_verification_status": "PASS",
        "constraint_verification_status": "PASS",
        "readiness_verification_status": "PASS",
        "verified_at": verified_at,
        "verification_result": "PASS",
    }


def restore_isolated(
    *,
    bundle_root: Path,
    output_dir: Path,
    execute_restore: bool,
    target_database_url: str | None = None,
    target_artifact_root: Path | None = None,
    target_environment_id: str | None = None,
    target_database_environment_id: str | None = None,
    target_artifact_environment_id: str | None = None,
) -> Path:
    """Restore one complete backup to a new, empty, independently identified target."""
    if not execute_restore or os.environ.get("TASK012_ISOLATED_RESTORE_AUTHORIZED") != "YES":
        raise RecoveryError("RESTORE_EXECUTION_NOT_AUTHORIZED")
    bundle = validate_backup_bundle(bundle_root)
    target = _resolve_target(
        target_database_url=target_database_url,
        target_artifact_root=target_artifact_root,
        target_environment_id=target_environment_id,
        target_database_environment_id=target_database_environment_id,
        target_artifact_environment_id=target_artifact_environment_id,
    )
    _ensure_target_identities_are_distinct(bundle, target)
    _ensure_connection_identity_is_distinct(bundle, target)
    _ensure_artifact_root_is_distinct(target)
    engine = _create_postgres_engine(
        target.database_url,
        code="RESTORE_TARGET_ISOLATION_UNVERIFIED",
    )
    staged: Path | None = None
    try:
        _require_empty_database(engine)
        _require_empty_artifact_root(target.artifact_root)
        _identity, child_env = _postgres_child_env(
            target.database_url,
            code="RESTORE_TARGET_ISOLATION_UNVERIFIED",
        )
        _run_restore_command = [
            "pg_restore",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            child_env["PGDATABASE"],
            str(bundle.root / "database.dump"),
        ]
        from cold_storage.recovery.backup_bundle import _run_postgres_tool

        _run_postgres_tool(
            _run_restore_command,
            database_url=target.database_url,
            code="RESTORE_DATABASE_FAILED",
        )
        staged = Path(
            tempfile.mkdtemp(prefix=".task012-restore-artifacts-", dir=target.artifact_root.parent)
        )
        # mkdtemp creates the staging directory; the extractor requires an
        # absent destination so it can own the complete tree.
        staged.rmdir()
        _safe_extract_archive(bundle.root / "artifacts.tar", staged)
        actual_artifact_inventory = collect_artifact_inventory(
            staged,
            failure_code="RESTORE_ARTIFACT_FAILED",
        )
        if actual_artifact_inventory != bundle.artifact_inventory:
            raise RecoveryError("RESTORE_ARTIFACT_INVENTORY_MISMATCH")
        _promote_artifact_root(staged, target.artifact_root)
        staged = None
        final_artifact_inventory = collect_artifact_inventory(
            target.artifact_root,
            failure_code="RESTORE_ARTIFACT_INVENTORY_MISMATCH",
        )
        if final_artifact_inventory != bundle.artifact_inventory:
            raise RecoveryError("RESTORE_ARTIFACT_INVENTORY_MISMATCH")
        actual_database_inventory = collect_database_inventory(
            engine,
            expected_schema_head=bundle.manifest["source_schema_head"],
            failure_code="RESTORE_SCHEMA_MISMATCH",
        )
        if actual_database_inventory != bundle.database_inventory:
            raise RecoveryError("RESTORE_DATABASE_INVENTORY_MISMATCH")
        _verify_constraints(engine)
        _verify_readiness(
            engine,
            target.artifact_root,
            expected_schema_head=bundle.manifest["source_schema_head"],
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        receipt = _receipt_for(
            bundle,
            target,
            schema_head_actual=actual_database_inventory["schema_head"],
            database_actual=actual_database_inventory,
            artifact_actual=final_artifact_inventory,
            verified_at=_utc_now(),
        )
        receipt_path = output_dir / "restore-receipt.json"
        _write_json(receipt_path, receipt)
        return receipt_path
    except RecoveryError:
        raise
    finally:
        engine.dispose()
        if staged is not None:
            shutil.rmtree(staged, ignore_errors=True)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_receipt_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RecoveryError("RESTORE_RECEIPT_INVALID", "receipt timestamp is not UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryError("RESTORE_RECEIPT_INVALID", "receipt timestamp is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecoveryError("RESTORE_RECEIPT_INVALID", "receipt timestamp is not timezone-aware")
    if parsed.microsecond != 0:
        raise RecoveryError("RESTORE_RECEIPT_INVALID", "receipt timestamp precision is invalid")
    return value


def _validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if set(receipt) != set(RESTORE_RECEIPT_FIELDS):
        raise RecoveryError("RESTORE_RECEIPT_INVALID", "restore receipt schema is not closed")
    for key, value in receipt.items():
        lowered = key.lower()
        if any(secret in lowered for secret in ("password", "database_url", "dsn", "token")):
            raise RecoveryError(
                "RESTORE_RECEIPT_INVALID", "restore receipt contains secret material"
            )
        if isinstance(value, str) and ("://" in value or value.startswith("/")):
            raise RecoveryError(
                "RESTORE_RECEIPT_INVALID", "restore receipt contains an unsafe path or URL"
            )
    if receipt.get("verification_result") != "PASS":
        raise RecoveryError("RESTORE_RECEIPT_INVALID", "restore receipt is not a PASS receipt")
    _validate_receipt_timestamp(receipt.get("verified_at"))
    return dict(receipt)


def verify_restore(
    *,
    bundle_root: Path,
    receipt_path: Path,
    target_database_url: str | None = None,
    target_artifact_root: Path | None = None,
    target_environment_id: str | None = None,
    target_database_environment_id: str | None = None,
    target_artifact_environment_id: str | None = None,
) -> Path:
    """Recompute restore evidence; never trusts the receipt's PASS alone."""
    bundle = validate_backup_bundle(bundle_root)
    receipt = _validate_receipt(_load_object(receipt_path, code="RESTORE_RECEIPT_INVALID"))
    if receipt.get("backup_id") != bundle.backup_id:
        raise RecoveryError("RESTORE_RECEIPT_INVALID", "receipt backup identity differs")
    target = _resolve_target(
        target_database_url=target_database_url,
        target_artifact_root=target_artifact_root,
        target_environment_id=target_environment_id,
        target_database_environment_id=target_database_environment_id,
        target_artifact_environment_id=target_artifact_environment_id,
    )
    _ensure_target_identities_are_distinct(bundle, target)
    _ensure_connection_identity_is_distinct(bundle, target)
    _ensure_artifact_root_is_distinct(target)
    receipt_identity_pairs = (
        ("source_environment_id", bundle.manifest["source_environment_id"]),
        (
            "source_database_environment_id",
            bundle.manifest["source_database_environment_id"],
        ),
        ("source_artifact_environment_id", bundle.manifest["source_artifact_environment_id"]),
        ("target_environment_id", target.environment_id),
        ("target_database_environment_id", target.database_environment_id),
        ("target_artifact_environment_id", target.artifact_environment_id),
    )
    for key, expected in receipt_identity_pairs:
        if receipt.get(key) != expected:
            raise RecoveryError("RESTORE_RECEIPT_INVALID", "restore receipt identity differs")
    engine = _create_postgres_engine(
        target.database_url,
        code="RESTORE_TARGET_ISOLATION_UNVERIFIED",
    )
    try:
        actual_database_inventory = collect_database_inventory(
            engine,
            expected_schema_head=bundle.manifest["source_schema_head"],
            failure_code="RESTORE_SCHEMA_MISMATCH",
        )
        actual_artifact_inventory = collect_artifact_inventory(
            target.artifact_root,
            failure_code="RESTORE_ARTIFACT_INVENTORY_MISMATCH",
        )
        if actual_database_inventory != bundle.database_inventory:
            raise RecoveryError("RESTORE_DATABASE_INVENTORY_MISMATCH")
        if actual_artifact_inventory != bundle.artifact_inventory:
            raise RecoveryError("RESTORE_ARTIFACT_INVENTORY_MISMATCH")
        _verify_constraints(engine)
        _verify_readiness(
            engine,
            target.artifact_root,
            expected_schema_head=bundle.manifest["source_schema_head"],
        )
        expected = _receipt_for(
            bundle,
            target,
            schema_head_actual=actual_database_inventory["schema_head"],
            database_actual=actual_database_inventory,
            artifact_actual=actual_artifact_inventory,
            verified_at=str(receipt["verified_at"]),
        )
        for key, value in expected.items():
            if receipt.get(key) != value:
                raise RecoveryError(
                    "RESTORE_RECEIPT_INVALID", "restore receipt is not independently verified"
                )
        return receipt_path
    finally:
        engine.dispose()


__all__ = [
    "RESTORE_RECEIPT_FIELDS",
    "RestoreTarget",
    "restore_isolated",
    "verify_restore",
]
