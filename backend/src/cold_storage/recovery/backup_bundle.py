"""Authoritative PostgreSQL and artifact-storage backup bundles.

This package is deliberately independent from the release-evidence package.
It owns the operator-facing data recovery boundary only: a PostgreSQL custom
dump, a deterministic artifact archive, inventories, and a closed manifest.
The command layer never places a database URL or a credential in a manifest,
receipt, subprocess argument, or user-facing error.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import Connection, Engine

BACKUP_SCHEMA_VERSION = "cold-storage-operational-backup-v1"
DATABASE_INVENTORY_SCHEMA_VERSION = "cold-storage-database-inventory-v1"
ARTIFACT_INVENTORY_SCHEMA_VERSION = "cold-storage-artifact-inventory-v1"
BACKUP_PAYLOAD_FILES: tuple[str, ...] = (
    "backup-manifest.json",
    "database.dump",
    "database-inventory.json",
    "artifacts.tar",
    "artifact-inventory.json",
)
BACKUP_FILES = frozenset((*BACKUP_PAYLOAD_FILES, "SHA256SUMS", "SHA256SUMS.sha256"))
MANIFEST_FIELDS: tuple[str, ...] = (
    "schema_version",
    "task",
    "version",
    "backup_id",
    "source_environment_id",
    "source_database_environment_id",
    "source_artifact_environment_id",
    "source_schema_head",
    "created_at",
    "retention_days",
    "expires_at",
    "database_dump_digest",
    "database_inventory_digest",
    "artifact_archive_digest",
    "artifact_inventory_digest",
    "verification_result",
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BACKUP_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_CHECKSUM_LINE_RE = re.compile(r"^([0-9a-f]{64})  ([^\r\n]+)$")
_EXCLUDED_SCHEMAS = frozenset({"information_schema", "pg_catalog"})


class RecoveryError(Exception):
    """A safe, machine-readable recovery failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class BackupBundle:
    """A validated backup bundle and its parsed evidence documents."""

    root: Path
    manifest: dict[str, Any]
    database_inventory: dict[str, Any]
    artifact_inventory: dict[str, Any]

    @property
    def backup_id(self) -> str:
        return str(self.manifest["backup_id"])


@dataclass(frozen=True)
class PostgresConnectionIdentity:
    """Non-secret identity used to prove source/target separation."""

    host: str
    port: int
    database: str
    user: str


def _canonical_json_bytes(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise RecoveryError("BACKUP_BUNDLE_INCOMPLETE", "non-canonical JSON value") from exc
    return (encoded + "\n").encode("utf-8")


def _load_json(path: Path, *, code: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(code, "JSON document is unreadable or malformed") from exc
    if not isinstance(value, dict):
        raise RecoveryError(code, "JSON document must be an object")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise json.JSONDecodeError("duplicate key", key, 0)
        result[key] = value
    return result


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_bytes(_canonical_json_bytes(value))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RecoveryError("BACKUP_BUNDLE_INCOMPLETE", "required file is unreadable") from exc
    return f"sha256:{digest.hexdigest()}"


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _validate_digest(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise RecoveryError(code, "digest is not canonical SHA-256")
    return value


def _validate_identity(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _IDENTITY_RE.fullmatch(value) is None:
        raise RecoveryError(code, "environment identity is missing or malformed")
    if value.lower() in {"unknown", "unset", "none", "null"}:
        raise RecoveryError(code, "environment identity is not authoritative")
    return value


def _resolve_identity(explicit: str | None, env_name: str, *, code: str) -> str:
    value = explicit if explicit not in (None, "") else os.environ.get(env_name)
    return _validate_identity(value, code=code)


def _parse_positive_bounded_int(value: object, *, code: str) -> int:
    if isinstance(value, bool):
        raise RecoveryError(code, "integer value is malformed")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        result = int(value)
    else:
        raise RecoveryError(code, "integer value is malformed")
    if not 1 <= result <= 3650:
        raise RecoveryError(code, "integer value is outside the bounded range")
    return result


def _parse_pg_url(url: str, *, code: str) -> tuple[PostgresConnectionIdentity, dict[str, str]]:
    if not isinstance(url, str) or not url:
        raise RecoveryError(code, "PostgreSQL connection is missing")
    normalized = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RecoveryError(code, "PostgreSQL connection scheme is unsupported")
    try:
        host = parsed.hostname
        port = parsed.port or 5432
    except ValueError as exc:
        raise RecoveryError(code, "PostgreSQL connection authority is malformed") from exc
    database = unquote(parsed.path.lstrip("/"))
    user = unquote(parsed.username or "")
    password = unquote(parsed.password) if parsed.password is not None else None
    if not host or not database or not user or parsed.fragment:
        raise RecoveryError(code, "PostgreSQL connection identity is incomplete")
    if parsed.query:
        # Query parameters such as sslmode remain in the Python SQLAlchemy URL,
        # but are not copied to the subprocess argv. The identity is unaffected.
        pass
    identity = PostgresConnectionIdentity(host.lower(), port, database, user)
    child_env: dict[str, str] = {
        "PGHOST": host,
        "PGPORT": str(port),
        "PGDATABASE": database,
        "PGUSER": user,
    }
    if password is not None:
        child_env["PGPASSWORD"] = password
    return identity, child_env


def _postgres_child_env(
    url: str, *, code: str
) -> tuple[PostgresConnectionIdentity, dict[str, str]]:
    identity, values = _parse_pg_url(url, code=code)
    child_env = dict(os.environ)
    child_env.update(values)
    # Never let a service-file setting silently redirect the operation.
    child_env.pop("PGSERVICE", None)
    child_env.pop("PGSERVICEFILE", None)
    return identity, child_env


def _create_postgres_engine(url: str, *, code: str) -> Engine:
    _parse_pg_url(url, code=code)
    try:
        return create_engine(url, future=True, pool_pre_ping=True)
    except Exception as exc:  # pragma: no cover - dialect construction varies
        raise RecoveryError(code, "PostgreSQL engine could not be created") from exc


@contextmanager
def _export_database_snapshot(engine: Engine) -> Iterator[tuple[Connection, str]]:
    """Keep one PostgreSQL MVCC snapshot open for dump and inventory reads."""
    connection = engine.connect().execution_options(isolation_level="REPEATABLE READ")
    transaction = None
    try:
        transaction = connection.begin()
        connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        snapshot = connection.execute(text("SELECT pg_export_snapshot()"))
        snapshot_id = snapshot.scalar_one()
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise RecoveryError("BACKUP_DATABASE_FAILED", "PostgreSQL snapshot identity is invalid")
        yield connection, snapshot_id
        transaction.commit()
    except RecoveryError:
        if transaction is not None:
            transaction.rollback()
        raise
    except Exception as exc:
        if transaction is not None:
            transaction.rollback()
        raise RecoveryError(
            "BACKUP_DATABASE_FAILED", "PostgreSQL snapshot transaction failed"
        ) from exc
    finally:
        connection.close()


def _run_postgres_tool(
    argv: Sequence[str],
    *,
    database_url: str,
    code: str,
) -> None:
    _identity, child_env = _postgres_child_env(database_url, code=code)
    try:
        subprocess.run(
            list(argv),
            check=True,
            capture_output=True,
            text=True,
            env=child_env,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RecoveryError(code, "PostgreSQL recovery command failed") from exc


def _packaged_schema_head() -> str:
    # The existing runtime readiness loader is the schema-graph authority.
    # Recovery consumes its validated result instead of creating a second
    # migration graph parser.
    from cold_storage.bootstrap.runtime_readiness import _load_packaged_alembic_head

    head, reason = _load_packaged_alembic_head()
    if head is None:
        raise RecoveryError("BACKUP_SCHEMA_IDENTITY_INVALID", reason or "schema head unavailable")
    return head


def _read_schema_head_connection(connection: Connection, *, expected: str | None, code: str) -> str:
    packaged = _packaged_schema_head()
    if expected is not None and expected != packaged:
        raise RecoveryError(code, "expected schema identity is not the packaged head")
    try:
        rows = connection.execute(text("SELECT version_num FROM alembic_version")).all()
    except Exception as exc:
        raise RecoveryError(code, "schema identity could not be read") from exc
    if len(rows) != 1 or not isinstance(rows[0][0], str) or not rows[0][0].strip():
        raise RecoveryError(code, "schema identity is missing or not unique")
    actual = rows[0][0].strip()
    if actual != packaged or (expected is not None and actual != expected):
        raise RecoveryError(code, "schema head does not match the packaged identity")
    return actual


def _read_schema_head(
    engine_or_connection: Engine | Connection, *, expected: str | None, code: str
) -> str:
    if isinstance(engine_or_connection, Engine):
        with engine_or_connection.connect() as connection:
            return _read_schema_head_connection(connection, expected=expected, code=code)
    return _read_schema_head_connection(engine_or_connection, expected=expected, code=code)


def _normalize_scalar(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RecoveryError("BACKUP_DATABASE_FAILED", "non-finite database value")
        return {"type": "float", "value": format(value, ".17g")}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": format(value, "f")}
    if isinstance(value, (datetime, date, time)):
        return {"type": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, bytes):
        return {"type": "bytes", "value": value.hex()}
    if isinstance(value, uuid.UUID):
        return {"type": "uuid", "value": str(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_scalar(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_scalar(item) for item in value]
    # PostgreSQL extension values such as inet are rendered through their
    # stable textual adapter representation, never repr() or object address.
    return {"type": type(value).__name__, "value": str(value)}


def _table_rows(
    connection: Connection, *, schema: str, table_name: str
) -> tuple[list[str], list[dict[str, object]]]:
    metadata = MetaData()
    table = Table(
        table_name,
        metadata,
        schema=None if schema == "public" else schema,
        autoload_with=connection,
    )
    columns = [column.name for column in table.columns]
    rows = connection.execute(select(table)).all()
    normalized: list[dict[str, object]] = []
    for row in rows:
        normalized.append({column: _normalize_scalar(row._mapping[column]) for column in columns})
    primary_keys = [column.name for column in table.primary_key.columns]
    if primary_keys:
        normalized.sort(
            key=lambda item: _canonical_json_bytes({key: item[key] for key in primary_keys})
        )
    else:
        normalized.sort(key=_canonical_json_bytes)
    return columns, normalized


def _application_table_names(connection: Connection) -> list[tuple[str, str]]:
    inspector = inspect(connection)
    names: list[tuple[str, str]] = []
    for schema in sorted(inspector.get_schema_names()):
        if schema in _EXCLUDED_SCHEMAS or schema.startswith("pg_"):
            continue
        for table_name in sorted(inspector.get_table_names(schema=schema)):
            names.append((schema, table_name))
    return names


def collect_database_inventory_from_connection(
    connection: Connection,
    *,
    expected_schema_head: str | None = None,
    failure_code: str = "BACKUP_DATABASE_FAILED",
) -> dict[str, Any]:
    schema_head = _read_schema_head_connection(
        connection, expected=expected_schema_head, code=failure_code
    )
    tables: list[dict[str, Any]] = []
    try:
        for schema, table_name in _application_table_names(connection):
            columns, rows = _table_rows(connection, schema=schema, table_name=table_name)
            logical_payload = {
                "schema": schema,
                "table": table_name,
                "columns": columns,
                "rows": rows,
            }
            tables.append(
                {
                    "schema": schema,
                    "table": table_name,
                    "row_count": len(rows),
                    "logical_digest": _sha256_bytes(_canonical_json_bytes(logical_payload)),
                }
            )
    except RecoveryError:
        raise
    except Exception as exc:
        raise RecoveryError(failure_code, "database inventory could not be collected") from exc
    return {
        "schema_version": DATABASE_INVENTORY_SCHEMA_VERSION,
        "schema_head": schema_head,
        "table_count": len(tables),
        "tables": tables,
    }


def collect_database_inventory(
    engine: Engine,
    *,
    expected_schema_head: str | None = None,
    failure_code: str = "BACKUP_DATABASE_FAILED",
) -> dict[str, Any]:
    """Collect inventory using one connection; snapshot callers pass theirs directly."""
    try:
        with engine.connect() as connection:
            return collect_database_inventory_from_connection(
                connection,
                expected_schema_head=expected_schema_head,
                failure_code=failure_code,
            )
    except RecoveryError:
        raise
    except Exception as exc:
        raise RecoveryError(failure_code, "database inventory could not be collected") from exc


def inventory_digest(inventory: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical_json_bytes(inventory))


def _artifact_entries(root: Path, *, failure_code: str) -> list[tuple[str, Path, bool]]:
    resolved = root.resolve()
    if not resolved.is_dir() or resolved.is_symlink():
        raise RecoveryError(failure_code, "artifact storage root is not a directory")
    entries: list[tuple[str, Path, bool]] = []

    def visit(directory: Path, relative: PurePosixPath) -> None:
        try:
            children = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise RecoveryError(failure_code, "artifact storage cannot be read") from exc
        for entry in children:
            if "\\" in entry.name or entry.name in {"", ".", ".."}:
                raise RecoveryError(failure_code, "artifact path is not canonical")
            child_relative = relative / entry.name
            child_path = directory / entry.name
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                raise RecoveryError(failure_code, "artifact entry cannot be inspected") from exc
            if stat.S_ISLNK(mode):
                raise RecoveryError(failure_code, "artifact symlink is forbidden")
            if stat.S_ISDIR(mode):
                entries.append((child_relative.as_posix(), child_path, True))
                visit(child_path, child_relative)
            elif stat.S_ISREG(mode):
                if entry.stat(follow_symlinks=False).st_nlink != 1:
                    raise RecoveryError(failure_code, "artifact hardlink is forbidden")
                entries.append((child_relative.as_posix(), child_path, False))
            else:
                raise RecoveryError(failure_code, "artifact special file is forbidden")

    visit(resolved, PurePosixPath())
    entries.sort(key=lambda item: item[0])
    return entries


def collect_artifact_inventory(root: Path, *, failure_code: str) -> dict[str, Any]:
    entries = _artifact_entries(root, failure_code=failure_code)
    files: list[dict[str, Any]] = []
    for relative_path, path, is_directory in entries:
        if is_directory:
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise RecoveryError(failure_code, "artifact file cannot be read") from exc
        files.append(
            {
                "relative_path": relative_path,
                "size_bytes": size,
                "sha256": _sha256_file(path),
            }
        )
    return {
        "schema_version": ARTIFACT_INVENTORY_SCHEMA_VERSION,
        "file_count": len(files),
        "total_bytes": sum(int(item["size_bytes"]) for item in files),
        "files": files,
    }


def _write_artifact_archive(source_root: Path, destination: Path, *, failure_code: str) -> None:
    entries = _artifact_entries(source_root, failure_code=failure_code)
    try:
        with tarfile.open(destination, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for relative_path, path, is_directory in entries:
                info = tarfile.TarInfo(relative_path + ("/" if is_directory else ""))
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                if is_directory:
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    archive.addfile(info)
                else:
                    info.type = tarfile.REGTYPE
                    info.mode = 0o644
                    info.size = path.stat().st_size
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
    except RecoveryError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise RecoveryError(failure_code, "artifact archive could not be created") from exc


def collect_artifact_inventory_from_archive(
    archive_path: Path, *, failure_code: str
) -> dict[str, Any]:
    """Derive artifact inventory from the immutable archive payload itself."""
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        with tarfile.open(archive_path, mode="r:") as archive:
            for member in archive.getmembers():
                try:
                    parts = validate_tar_member_name(member.name)
                except RecoveryError as exc:
                    raise RecoveryError(failure_code, exc.detail) from exc
                relative_path = "/".join(parts)
                if relative_path in seen:
                    raise RecoveryError(failure_code, "artifact archive contains duplicate paths")
                seen.add(relative_path)
                if (
                    member.issym()
                    or member.islnk()
                    or member.isdev()
                    or not (member.isdir() or member.isreg())
                ):
                    raise RecoveryError(failure_code, "artifact archive contains unsafe entries")
                if member.isdir():
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    raise RecoveryError(failure_code, "artifact archive file cannot be read")
                digest = hashlib.sha256()
                size = 0
                with stream:
                    for chunk in iter(stream.read, b""):
                        digest.update(chunk)
                        size += len(chunk)
                if size != member.size:
                    raise RecoveryError(failure_code, "artifact archive file size changed")
                files.append(
                    {
                        "relative_path": relative_path,
                        "size_bytes": size,
                        "sha256": f"sha256:{digest.hexdigest()}",
                    }
                )
    except RecoveryError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise RecoveryError(failure_code, "artifact archive could not be read") from exc
    files.sort(key=lambda item: str(item["relative_path"]))
    return {
        "schema_version": ARTIFACT_INVENTORY_SCHEMA_VERSION,
        "file_count": len(files),
        "total_bytes": sum(int(item["size_bytes"]) for item in files),
        "files": files,
    }


def _write_checksums(root: Path, payload_files: Sequence[str]) -> None:
    lines: list[str] = []
    for relative in sorted(payload_files):
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise RecoveryError("BACKUP_BUNDLE_INCOMPLETE", "checksum payload is missing")
        lines.append(f"{_sha256_file(path)[7:]}  {relative}")
    manifest = ("\n".join(lines) + "\n").encode("ascii")
    (root / "SHA256SUMS").write_bytes(manifest)
    (root / "SHA256SUMS.sha256").write_bytes(
        hashlib.sha256(manifest).hexdigest().encode("ascii") + b"\n"
    )


def _validate_checksum_files(root: Path, *, code: str) -> None:
    manifest_path = root / "SHA256SUMS"
    sidecar_path = root / "SHA256SUMS.sha256"
    try:
        sidecar = sidecar_path.read_bytes()
        sums = manifest_path.read_bytes()
    except OSError as exc:
        raise RecoveryError(code, "checksum files are missing") from exc
    if not re.fullmatch(rb"[0-9a-f]{64}\n", sidecar):
        raise RecoveryError(code, "checksum sidecar is malformed")
    if sidecar[:-1].decode("ascii") != hashlib.sha256(sums).hexdigest():
        raise RecoveryError(code, "checksum sidecar does not match SHA256SUMS")
    try:
        text_value = sums.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RecoveryError(code, "checksum manifest is not ASCII") from exc
    if not text_value.endswith("\n") or "\r" in text_value:
        raise RecoveryError(code, "checksum manifest line endings are invalid")
    listed: dict[str, str] = {}
    for line in text_value[:-1].split("\n"):
        match = _CHECKSUM_LINE_RE.fullmatch(line)
        if match is None:
            raise RecoveryError(code, "checksum manifest entry is malformed")
        digest, relative = match.groups()
        pure = PurePosixPath(relative)
        if (
            relative in listed
            or not relative
            or "\\" in relative
            or relative.startswith("/")
            or re.match(r"^[A-Za-z]:", relative) is not None
            or relative != pure.as_posix()
            or ".." in pure.parts
            or relative not in BACKUP_PAYLOAD_FILES
        ):
            raise RecoveryError(code, "checksum manifest coverage is invalid")
        listed[relative] = digest
    if set(listed) != set(BACKUP_PAYLOAD_FILES):
        raise RecoveryError(code, "checksum manifest does not cover the exact payload")
    for relative, digest in listed.items():
        path = root / relative
        if not path.is_file() or path.is_symlink() or _sha256_file(path)[7:] != digest:
            raise RecoveryError(code, "backup checksum mismatch")


def _parse_timestamp(value: object, *, code: str) -> datetime:
    if not isinstance(value, str):
        raise RecoveryError(code, "timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryError(code, "timestamp is malformed") from exc
    if parsed.tzinfo is None:
        raise RecoveryError(code, "timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if set(manifest) != set(MANIFEST_FIELDS):
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup manifest schema is not closed")
    if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup manifest schema is unsupported")
    if manifest.get("task") != "TASK-012" or manifest.get("version") != "V0.2":
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup manifest task identity is invalid")
    backup_id = manifest.get("backup_id")
    if not isinstance(backup_id, str) or _BACKUP_ID_RE.fullmatch(backup_id) is None:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup id is malformed")
    for key in (
        "source_environment_id",
        "source_database_environment_id",
        "source_artifact_environment_id",
    ):
        _validate_identity(manifest.get(key), code="RESTORE_BUNDLE_INVALID")
    source_head = manifest.get("source_schema_head")
    if not isinstance(source_head, str) or not source_head:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "source schema head is missing")
    created_at = _parse_timestamp(manifest.get("created_at"), code="RESTORE_BUNDLE_INVALID")
    expires_at = _parse_timestamp(manifest.get("expires_at"), code="RESTORE_BUNDLE_INVALID")
    retention = _parse_positive_bounded_int(
        manifest.get("retention_days"), code="RESTORE_BUNDLE_INVALID"
    )
    if expires_at <= created_at or expires_at > created_at + timedelta(days=retention, seconds=1):
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup retention metadata is invalid")
    if manifest.get("verification_result") != "PASS":
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup was not verified")
    for key in (
        "database_dump_digest",
        "database_inventory_digest",
        "artifact_archive_digest",
        "artifact_inventory_digest",
    ):
        _validate_digest(manifest.get(key), code="RESTORE_BUNDLE_INVALID")
    return dict(manifest)


def _validate_inventory_documents(
    database_inventory: Mapping[str, Any], artifact_inventory: Mapping[str, Any]
) -> None:
    if database_inventory.get("schema_version") != DATABASE_INVENTORY_SCHEMA_VERSION:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "database inventory schema is unsupported")
    if artifact_inventory.get("schema_version") != ARTIFACT_INVENTORY_SCHEMA_VERSION:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "artifact inventory schema is unsupported")
    tables = database_inventory.get("tables")
    if (
        not isinstance(tables, list)
        or database_inventory.get("table_count") != len(tables)
        or any(not isinstance(item, dict) for item in tables)
    ):
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "database inventory shape is invalid")
    table_keys: list[tuple[object, object]] = []
    for item in tables:
        schema = item.get("schema")
        table = item.get("table")
        if not isinstance(schema, str) or not isinstance(table, str):
            raise RecoveryError(
                "RESTORE_BUNDLE_INVALID", "database inventory table identity is invalid"
            )
        if not isinstance(item.get("row_count"), int) or item["row_count"] < 0:
            raise RecoveryError("RESTORE_BUNDLE_INVALID", "database inventory row count is invalid")
        _validate_digest(item.get("logical_digest"), code="RESTORE_BUNDLE_INVALID")
        table_keys.append((schema, table))
    if table_keys != sorted(table_keys) or len(table_keys) != len(set(table_keys)):
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "database inventory table order is invalid")
    files = artifact_inventory.get("files")
    if (
        not isinstance(files, list)
        or artifact_inventory.get("file_count") != len(files)
        or any(not isinstance(item, dict) for item in files)
    ):
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "artifact inventory shape is invalid")
    paths = [item.get("relative_path") for item in files]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "artifact inventory paths are not canonical")
    for item in files:
        relative = item.get("relative_path")
        if (
            not isinstance(relative, str)
            or "\\" in relative
            or relative.startswith("/")
            or ".." in PurePosixPath(relative).parts
            or relative != PurePosixPath(relative).as_posix()
        ):
            raise RecoveryError("RESTORE_BUNDLE_INVALID", "artifact inventory path is unsafe")
        if type(item.get("size_bytes")) is not int or item["size_bytes"] < 0:
            raise RecoveryError("RESTORE_BUNDLE_INVALID", "artifact inventory size is invalid")
        _validate_digest(item.get("sha256"), code="RESTORE_BUNDLE_INVALID")
    if artifact_inventory.get("total_bytes") != sum(int(item["size_bytes"]) for item in files):
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "artifact inventory total is invalid")


def validate_backup_bundle(bundle_root: Path) -> BackupBundle:
    """Validate a complete bundle before any restore target mutation."""
    root = bundle_root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup bundle root is not a directory")
    actual_files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink() or path.is_dir():
            raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup bundle contains unsafe entries")
        relative = path.relative_to(root).as_posix()
        if "/" in relative or relative not in BACKUP_FILES:
            raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup bundle file set is not exact")
        actual_files.add(relative)
    if actual_files != BACKUP_FILES:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "backup bundle file set is incomplete")
    _validate_checksum_files(root, code="BACKUP_CHECKSUM_MISMATCH")
    manifest = _validate_manifest(
        _load_json(root / "backup-manifest.json", code="RESTORE_BUNDLE_INVALID")
    )
    database_inventory = _load_json(root / "database-inventory.json", code="RESTORE_BUNDLE_INVALID")
    artifact_inventory = _load_json(root / "artifact-inventory.json", code="RESTORE_BUNDLE_INVALID")
    _validate_inventory_documents(database_inventory, artifact_inventory)
    if database_inventory.get("schema_head") != manifest["source_schema_head"]:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "database inventory schema head disagrees")
    if _sha256_file(root / "database.dump") != manifest["database_dump_digest"]:
        raise RecoveryError(
            "RESTORE_BUNDLE_INVALID", "database dump digest disagrees with manifest"
        )
    if inventory_digest(database_inventory) != manifest["database_inventory_digest"]:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "database inventory digest disagrees")
    if _sha256_file(root / "artifacts.tar") != manifest["artifact_archive_digest"]:
        raise RecoveryError(
            "RESTORE_BUNDLE_INVALID", "artifact archive digest disagrees with manifest"
        )
    if inventory_digest(artifact_inventory) != manifest["artifact_inventory_digest"]:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "artifact inventory digest disagrees")
    archive_inventory = collect_artifact_inventory_from_archive(
        root / "artifacts.tar",
        failure_code="RESTORE_BUNDLE_INVALID",
    )
    if archive_inventory != artifact_inventory:
        raise RecoveryError("RESTORE_BUNDLE_INVALID", "artifact archive and inventory disagree")
    return BackupBundle(root, manifest, database_inventory, artifact_inventory)


def create_backup(
    *,
    backup_root: Path,
    execute_backup: bool,
    retention_days: int = 30,
    source_environment_id: str | None = None,
    source_database_environment_id: str | None = None,
    source_artifact_environment_id: str | None = None,
    source_artifact_root: Path | None = None,
    database_url: str | None = None,
) -> Path:
    """Create and atomically publish one fully verified backup bundle."""
    if not execute_backup or os.environ.get("TASK012_BACKUP_AUTHORIZED") != "YES":
        raise RecoveryError("BACKUP_EXECUTION_NOT_AUTHORIZED")
    retention = _parse_positive_bounded_int(retention_days, code="BACKUP_BUNDLE_INCOMPLETE")
    source_env = _resolve_identity(
        source_environment_id, "COLD_STORAGE_ENVIRONMENT_ID", code="BACKUP_BUNDLE_INCOMPLETE"
    )
    source_db_env = _resolve_identity(
        source_database_environment_id,
        "COLD_STORAGE_DATABASE_ENVIRONMENT_ID",
        code="BACKUP_BUNDLE_INCOMPLETE",
    )
    source_artifact_env = _resolve_identity(
        source_artifact_environment_id,
        "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID",
        code="BACKUP_BUNDLE_INCOMPLETE",
    )
    url = database_url or os.environ.get("COLD_STORAGE_DATABASE_URL")
    if not url:
        raise RecoveryError("BACKUP_BUNDLE_INCOMPLETE", "source PostgreSQL connection is missing")
    artifact_root_value = source_artifact_root or os.environ.get("COLD_STORAGE_STORAGE_DIR")
    if not artifact_root_value:
        raise RecoveryError("BACKUP_ARTIFACT_FAILED", "source artifact storage is missing")
    source_root = Path(artifact_root_value).resolve()
    destination_root = backup_root.resolve()
    if destination_root == source_root or destination_root.is_relative_to(source_root):
        raise RecoveryError(
            "BACKUP_ARTIFACT_FAILED", "backup root overlaps source artifact storage"
        )
    destination_root.mkdir(parents=True, exist_ok=True)
    backup_id = str(uuid.uuid4())
    final_root = destination_root / backup_id
    temp_root = Path(tempfile.mkdtemp(prefix=f".{backup_id}.", dir=destination_root))
    published = False
    engine: Engine | None = None
    now = datetime.now(UTC).replace(microsecond=0)
    expires = now + timedelta(days=retention)
    try:
        engine = _create_postgres_engine(url, code="BACKUP_DATABASE_FAILED")
        _identity, child_env = _postgres_child_env(url, code="BACKUP_DATABASE_FAILED")
        database_name = child_env["PGDATABASE"]
        with _export_database_snapshot(engine) as (snapshot_connection, snapshot_id):
            _run_postgres_tool(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--snapshot",
                    snapshot_id,
                    "--file",
                    str(temp_root / "database.dump"),
                    "--dbname",
                    database_name,
                ],
                database_url=url,
                code="BACKUP_DATABASE_FAILED",
            )
            database_inventory = collect_database_inventory_from_connection(snapshot_connection)
        _write_artifact_archive(
            source_root,
            temp_root / "artifacts.tar",
            failure_code="BACKUP_ARTIFACT_FAILED",
        )
        artifact_inventory = collect_artifact_inventory_from_archive(
            temp_root / "artifacts.tar",
            failure_code="BACKUP_ARTIFACT_FAILED",
        )
        _write_json(temp_root / "database-inventory.json", database_inventory)
        _write_json(temp_root / "artifact-inventory.json", artifact_inventory)
        manifest: dict[str, Any] = {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "task": "TASK-012",
            "version": "V0.2",
            "backup_id": backup_id,
            "source_environment_id": source_env,
            "source_database_environment_id": source_db_env,
            "source_artifact_environment_id": source_artifact_env,
            "source_schema_head": database_inventory["schema_head"],
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "retention_days": retention,
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
            "database_dump_digest": _sha256_file(temp_root / "database.dump"),
            "database_inventory_digest": inventory_digest(database_inventory),
            "artifact_archive_digest": _sha256_file(temp_root / "artifacts.tar"),
            "artifact_inventory_digest": inventory_digest(artifact_inventory),
            "verification_result": "PASS",
        }
        _write_json(temp_root / "backup-manifest.json", manifest)
        _write_checksums(temp_root, BACKUP_PAYLOAD_FILES)
        validate_backup_bundle(temp_root)
        if final_root.exists():
            raise RecoveryError("BACKUP_BUNDLE_INCOMPLETE", "backup id already exists")
        temp_root.rename(final_root)
        published = True
        return final_root
    except RecoveryError:
        raise
    except (OSError, ValueError) as exc:
        raise RecoveryError("BACKUP_BUNDLE_INCOMPLETE", "backup bundle publication failed") from exc
    finally:
        if engine is not None:
            engine.dispose()
        if not published:
            shutil.rmtree(temp_root, ignore_errors=True)


def validate_tar_member_name(name: str) -> tuple[str, ...]:
    """Return safe path components for a storage-root-relative tar member."""
    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or re.match(r"^[A-Za-z]:", name) is not None
    ):
        raise RecoveryError("RESTORE_ARTIFACT_FAILED", "artifact archive path is unsafe")
    normalized = name.rstrip("/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or normalized != pure.as_posix()
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise RecoveryError("RESTORE_ARTIFACT_FAILED", "artifact archive path is unsafe")
    return pure.parts


__all__ = [
    "ARTIFACT_INVENTORY_SCHEMA_VERSION",
    "BACKUP_FILES",
    "BACKUP_PAYLOAD_FILES",
    "BACKUP_SCHEMA_VERSION",
    "BackupBundle",
    "RecoveryError",
    "collect_artifact_inventory",
    "collect_artifact_inventory_from_archive",
    "collect_database_inventory",
    "collect_database_inventory_from_connection",
    "create_backup",
    "inventory_digest",
    "validate_backup_bundle",
    "validate_tar_member_name",
]
