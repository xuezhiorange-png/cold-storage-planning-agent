"""TASK-012 V0.2 Slice 6 S6-07 operational acceptance boundary.

This module verifies observations collected by a separately controlled,
synthetic runtime exercise.  It does not start services, run migrations,
execute business calculations, or mutate production resources.  The controlled
workflow owns those actions and writes a redacted observation document; this
module binds that document to the exact release identity and the already
verified S6-06 authority, then creates and independently verifies a compact
nine-file evidence bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import stat
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

from cold_storage.release.canonical_serialization import (
    ReleaseEvidenceError,
    canonical_bytes,
    load_json_strict,
)
from cold_storage.release.final_release_evidence import (
    verify_final_release_evidence,
)

EXPECTED_REPOSITORY = "xuezhiorange-png/cold-storage-planning-agent"
EXPECTED_TASK = "TASK-012"
EXPECTED_VERSION = "V0.2"
EXPECTED_RELEASE_VERSION = "v0.2.0"
S6_06_WORKFLOW_PATH = ".github/workflows/task012-slice6-package3-release-evidence.yml"
S6_06_WORKFLOW_NAME = "task012-slice6-package3-release-evidence"
S6_07_WORKFLOW_PATH = ".github/workflows/task012-slice6-s7-e2e-operational-acceptance.yml"

S6_07_SCHEMA_VERSION = "task012-s6-07-operational-acceptance-v1"
S6_07_ACCEPTANCE_TYPE = "controlled_end_to_end_operational_acceptance"

S6_07_JSON_FILES: tuple[str, ...] = (
    "acceptance-summary.json",
    "source-identity.json",
    "s6-06-authority.json",
    "runtime-lifecycle-observations.json",
    "production-http-scope-observations.json",
    "persistence-e2e-observations.json",
    "observability-security-observations.json",
)
S6_07_BUNDLE_FILES: tuple[str, ...] = (*S6_07_JSON_FILES, "SHA256SUMS", "SHA256SUMS.sha256")

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")

S6_07_FAILURE_CODES: tuple[str, ...] = (
    "S6_07_EXECUTION_NOT_AUTHORIZED",
    "S6_07_SOURCE_SHA_MISMATCH",
    "S6_07_SOURCE_TREE_INVALID",
    "S6_07_S6_06_AUTHORITY_MISSING",
    "S6_07_S6_06_AUTHORITY_MISMATCH",
    "S6_07_S6_06_ARTIFACT_EXPIRED",
    "S6_07_S6_06_DIGEST_MISMATCH",
    "S6_07_S6_06_VERIFICATION_FAILED",
    "S6_07_RUNTIME_STARTUP_FAILED",
    "S6_07_MIGRATION_FAILED",
    "S6_07_READINESS_FAILED",
    "S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
    "S6_07_FAKE_AGENT_REACHABLE",
    "S6_07_COEFFICIENT_AUTHORITY_INVALID",
    "S6_07_PERSISTENCE_FAILED",
    "S6_07_OBSERVABILITY_FAILED",
    "S6_07_SECRET_MATERIAL_DETECTED",
    "S6_07_EVIDENCE_BUNDLE_INVALID",
    "S6_07_CHECKSUM_MISMATCH",
)


class S607AcceptanceError(ReleaseEvidenceError):
    """A fail-closed S6-07 acceptance failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in S6_07_FAILURE_CODES:
            raise ValueError(f"unsupported S6-07 failure code: {code}")
        super().__init__(failure_code=code, detail=detail)


def _fail(code: str, detail: str) -> S607AcceptanceError:
    return S607AcceptanceError(code, detail)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return load_json_strict(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise _fail("S6_07_S6_06_AUTHORITY_MISSING", f"missing JSON input: {path.name}") from exc
    except (OSError, UnicodeError, ReleaseEvidenceError) as exc:
        raise _fail("S6_07_EVIDENCE_BUNDLE_INVALID", f"invalid JSON input: {path.name}") from exc


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail("S6_07_EVIDENCE_BUNDLE_INVALID", f"{field} must be an object")
    return cast(Mapping[str, Any], value)


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _fail("S6_07_EVIDENCE_BUNDLE_INVALID", f"{field} must be a non-empty string")
    return value


def _commit(value: object, *, field: str) -> str:
    result = _string(value, field=field)
    if not COMMIT_RE.fullmatch(result):
        raise _fail("S6_07_SOURCE_TREE_INVALID", f"{field} is not a 40-character SHA")
    return result


def _digest(value: object, *, field: str) -> str:
    result = _string(value, field=field)
    if not DIGEST_RE.fullmatch(result):
        raise _fail("S6_07_S6_06_DIGEST_MISMATCH", f"{field} is not a sha256 digest")
    return result


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _fail("S6_07_S6_06_AUTHORITY_MISMATCH", f"{field} must be positive")
    return value


def _eq(value: object, expected: object, *, field: str, code: str) -> None:
    if value != expected:
        raise _fail(code, f"{field} does not match the controlled contract")


def _validate_source(*, repository: str, source_sha: str, source_tree_sha: str) -> None:
    _eq(repository, EXPECTED_REPOSITORY, field="repository", code="S6_07_SOURCE_SHA_MISMATCH")
    _commit(source_sha, field="source_sha")
    _commit(source_tree_sha, field="source_tree_sha")


def _safe_secret_scan(value: object, *, path: str = "") -> None:
    """Reject secret-bearing values while allowing redaction gate names."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower().replace("-", "_")
            gate_key = key_text.endswith(("_not_emitted", "_redacted", "_excluded"))
            forbidden = {
                "password",
                "postgres_password",
                "database_url",
                "redis_url",
                "dsn",
                "token",
                "authorization",
                "cookie",
                "private_key",
                "secret",
            }
            if key_text in forbidden and not gate_key:
                raise _fail("S6_07_SECRET_MATERIAL_DETECTED", f"secret-like field: {path}.{key}")
            _safe_secret_scan(child, path=f"{path}.{key}" if path else str(key))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _safe_secret_scan(child, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        lowered = value.lower()
        unsafe_markers = (
            "postgresql://",
            "postgres://",
            "redis://",
            "bearer ",
            "github_pat_",
            "ghp_",
            "-----begin ",
        )
        if any(marker in lowered for marker in unsafe_markers):
            raise _fail("S6_07_SECRET_MATERIAL_DETECTED", f"secret-like value at {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_checksum(line: str) -> tuple[str, str]:
    parts = line.split("  ", 1)
    if len(parts) != 2 or not HEX_RE.fullmatch(parts[0]) or not parts[1]:
        raise _fail("S6_07_CHECKSUM_MISMATCH", "invalid checksum record")
    return parts[0], parts[1]


def verify_s6_07_checksums(bundle_dir: Path) -> None:
    """Verify checksums using paths relative to the downloaded bundle root."""

    sums = bundle_dir / "SHA256SUMS"
    sidecar = bundle_dir / "SHA256SUMS.sha256"
    if not sums.is_file() or not sidecar.is_file():
        raise _fail("S6_07_CHECKSUM_MISMATCH", "checksum files are missing")
    records = [_parse_checksum(line) for line in sums.read_text(encoding="ascii").splitlines()]
    if {name for _, name in records} != set(S6_07_JSON_FILES) or len(records) != len(
        S6_07_JSON_FILES
    ):
        raise _fail(
            "S6_07_CHECKSUM_MISMATCH", "SHA256SUMS coverage is not exactly seven JSON files"
        )
    for expected, name in records:
        if _sha256(bundle_dir / name) != expected:
            raise _fail("S6_07_CHECKSUM_MISMATCH", f"checksum mismatch: {name}")
    sidecar_records = [
        _parse_checksum(line) for line in sidecar.read_text(encoding="ascii").splitlines()
    ]
    if sidecar_records != [(_sha256(sums), "SHA256SUMS")]:
        raise _fail("S6_07_CHECKSUM_MISMATCH", "SHA256SUMS sidecar mismatch")


def _verify_exact_shape(bundle_dir: Path) -> None:
    if not bundle_dir.is_dir() or bundle_dir.is_symlink():
        raise _fail("S6_07_EVIDENCE_BUNDLE_INVALID", "bundle root is not a directory")
    entries = list(bundle_dir.iterdir())
    if {entry.name for entry in entries} != set(S6_07_BUNDLE_FILES):
        raise _fail("S6_07_EVIDENCE_BUNDLE_INVALID", "bundle must contain exactly nine files")
    if any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise _fail("S6_07_EVIDENCE_BUNDLE_INVALID", "bundle entries must be regular files")


def _read_observations(observations: Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(observations, Path):
        return _read_json(observations)
    return dict(_mapping(observations, field="observations"))


def _require_pass_fields(
    section: Mapping[str, Any],
    required: Mapping[str, object],
    *,
    code: str,
) -> None:
    for field, expected in required.items():
        if field not in section:
            raise _fail(code, f"missing observation: {field}")
        if section[field] != expected:
            raise _fail(code, f"observation mismatch: {field}")


def _validate_observations(
    observations: Mapping[str, Any], *, source_sha: str, source_tree_sha: str
) -> dict[str, dict[str, Any]]:
    _eq(
        observations.get("task"),
        EXPECTED_TASK,
        field="observations.task",
        code="S6_07_EVIDENCE_BUNDLE_INVALID",
    )
    _eq(
        observations.get("version"),
        EXPECTED_VERSION,
        field="observations.version",
        code="S6_07_EVIDENCE_BUNDLE_INVALID",
    )
    _eq(
        observations.get("slice"),
        6,
        field="observations.slice",
        code="S6_07_EVIDENCE_BUNDLE_INVALID",
    )
    _eq(
        observations.get("item"),
        "S6-07",
        field="observations.item",
        code="S6_07_EVIDENCE_BUNDLE_INVALID",
    )
    _eq(
        observations.get("source_sha"),
        source_sha,
        field="observations.source_sha",
        code="S6_07_SOURCE_SHA_MISMATCH",
    )
    _eq(
        observations.get("source_tree_sha"),
        source_tree_sha,
        field="observations.source_tree_sha",
        code="S6_07_SOURCE_TREE_INVALID",
    )
    _require_pass_fields(
        observations,
        {
            "controlled_synthetic": True,
            "real_production_data": False,
            "real_production_operation": False,
        },
        code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
    )

    runtime = dict(_mapping(observations.get("runtime_lifecycle"), field="runtime_lifecycle"))
    _require_pass_fields(
        runtime,
        {
            "image_build": "PASS",
            "build_identity_file": "PASS",
            "build_commit_sha_match": "PASS",
            "build_version": EXPECTED_RELEASE_VERSION,
            "migration_service": "PASS",
            "alembic_exact_head": "PASS",
            "backend_startup": "PASS",
            "liveness": "PASS",
            "readiness": "PASS",
            "canonical_database_engine": "PASS",
            "canonical_artifact_storage": "PASS",
            "strict_capability_audit": "PASS",
        },
        code="S6_07_RUNTIME_STARTUP_FAILED",
    )

    http_scope = dict(
        _mapping(observations.get("production_http_scope"), field="production_http_scope")
    )
    _require_pass_fields(
        http_scope,
        {
            "coefficient_routes_mounted": True,
            "coefficient_backend": "DatabaseCoefficientService",
            "coefficient_engine_is_canonical_engine": True,
            "database_failure_fallback_to_in_memory": False,
            "coefficient_lifecycle_readback": "PASS",
            "planning_agent_route_mounted": True,
            "planning_agent_backend": "DISABLED",
            "planning_agent_http_status": 503,
            "planning_agent_error_code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
            "planning_agent_retryable": False,
            "fake_agent_gateway_constructed_in_strict_mode": False,
            "fake_agent_result_returned": False,
        },
        code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
    )

    persistence = dict(_mapping(observations.get("persistence_e2e"), field="persistence_e2e"))
    _require_pass_fields(
        persistence,
        {
            "zone_stage": "PASS",
            "cooling_load_stage": "PASS",
            "equipment_stage": "PASS",
            "power_stage": "PASS",
            "investment_stage": "PASS",
            "source_binding": "VERIFIED",
            "scheme_run": "PASS",
            "no_demo_coefficient_used": True,
            "no_latest_row_fallback": True,
            "no_partial_source_binding": True,
            "power_authority_binding": "PASS",
            "source_archive_verification": "PASS",
            "restart_performed": True,
            "readiness_after_restart": "PASS",
            "database_state_persisted": "PASS",
            "coefficient_state_persisted": "PASS",
            "source_binding_state_persisted": "PASS",
            "artifact_state_persisted": "PASS",
        },
        code="S6_07_PERSISTENCE_FAILED",
    )

    observability = dict(
        _mapping(observations.get("observability_security"), field="observability_security")
    )
    _require_pass_fields(
        observability,
        {
            "correlation_id": "PASS",
            "structured_logging": "PASS",
            "sensitive_value_redaction": "PASS",
            "database_url_not_emitted": "PASS",
            "password_not_emitted": "PASS",
            "token_not_emitted": "PASS",
            "production_disabled_capability_observable": "PASS",
        },
        code="S6_07_OBSERVABILITY_FAILED",
    )
    return {
        "runtime_lifecycle": runtime,
        "production_http_scope": http_scope,
        "persistence_e2e": persistence,
        "observability_security": observability,
    }


def _verify_s6_06_run_metadata(
    metadata_dir: Path,
    *,
    run_id: int,
    run_attempt: int,
    source_sha: str,
) -> Mapping[str, Any]:
    run = _read_json(metadata_dir / f"run-{run_id}.json")
    _eq(
        _positive_int(run.get("id"), field="s6-06 run id"),
        run_id,
        field="s6-06 run id",
        code="S6_07_S6_06_AUTHORITY_MISMATCH",
    )
    _require_pass_fields(
        run,
        {
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": source_sha,
            "run_attempt": run_attempt,
            "status": "completed",
            "conclusion": "success",
            "path": S6_06_WORKFLOW_PATH,
            "name": S6_06_WORKFLOW_NAME,
        },
        code="S6_07_S6_06_AUTHORITY_MISMATCH",
    )
    return run


def _verify_s6_06_artifact_metadata(
    metadata_dir: Path,
    *,
    run_id: int,
    run_attempt: int,
    artifact_id: int,
    artifact_digest: str,
    source_sha: str,
) -> Mapping[str, Any]:
    artifact = _read_json(metadata_dir / f"artifact-{artifact_id}.json")
    _eq(
        _positive_int(artifact.get("id"), field="s6-06 artifact id"),
        artifact_id,
        field="s6-06 artifact id",
        code="S6_07_S6_06_AUTHORITY_MISMATCH",
    )
    if artifact.get("expired") is True:
        raise _fail("S6_07_S6_06_ARTIFACT_EXPIRED", "S6-06 artifact is expired")
    if artifact.get("expired") is not False:
        raise _fail("S6_07_S6_06_ARTIFACT_EXPIRED", "S6-06 artifact expiry state is missing")
    _eq(
        artifact.get("digest"),
        artifact_digest,
        field="s6-06 artifact digest",
        code="S6_07_S6_06_DIGEST_MISMATCH",
    )
    expected_name = f"task012-s6-06-final-release-evidence-{run_id}-{run_attempt}"
    _eq(
        artifact.get("name"),
        expected_name,
        field="s6-06 artifact name",
        code="S6_07_S6_06_AUTHORITY_MISMATCH",
    )
    workflow_run = _mapping(artifact.get("workflow_run"), field="artifact.workflow_run")
    _require_pass_fields(
        workflow_run,
        {"id": run_id, "head_branch": "main", "head_sha": source_sha},
        code="S6_07_S6_06_AUTHORITY_MISMATCH",
    )
    return artifact


def _verify_s6_06_bundle_identity(
    bundle_dir: Path, *, source_sha: str, source_tree_sha: str
) -> None:
    source = _read_json(bundle_dir / "source-identity.json")
    _eq(
        source.get("source_sha"),
        source_sha,
        field="S6-06 source SHA",
        code="S6_07_S6_06_AUTHORITY_MISMATCH",
    )
    _eq(
        source.get("source_tree_sha"),
        source_tree_sha,
        field="S6-06 source tree",
        code="S6_07_S6_06_AUTHORITY_MISMATCH",
    )
    _eq(
        source.get("verification_result"),
        "PASS",
        field="S6-06 source verification",
        code="S6_07_S6_06_VERIFICATION_FAILED",
    )


def verify_s6_06_prerequisite(
    *,
    repository: str,
    source_sha: str,
    source_tree_sha: str,
    s6_06_run_id: int,
    s6_06_run_attempt: int,
    s6_06_artifact_id: int,
    s6_06_artifact_digest: str,
    s6_06_bundle_dir: Path,
    s6_06_metadata_dir: Path,
) -> None:
    """Verify the exact refreshed S6-06 authority before S6-07 assembly."""

    _validate_source(repository=repository, source_sha=source_sha, source_tree_sha=source_tree_sha)
    _positive_int(s6_06_run_id, field="s6_06_run_id")
    _positive_int(s6_06_run_attempt, field="s6_06_run_attempt")
    _positive_int(s6_06_artifact_id, field="s6_06_artifact_id")
    _digest(s6_06_artifact_digest, field="s6_06_artifact_digest")
    if not s6_06_metadata_dir.is_dir() or not s6_06_bundle_dir.is_dir():
        raise _fail(
            "S6_07_S6_06_AUTHORITY_MISSING", "S6-06 metadata or bundle directory is missing"
        )
    _verify_s6_06_run_metadata(
        s6_06_metadata_dir,
        run_id=s6_06_run_id,
        run_attempt=s6_06_run_attempt,
        source_sha=source_sha,
    )
    _verify_s6_06_artifact_metadata(
        s6_06_metadata_dir,
        run_id=s6_06_run_id,
        run_attempt=s6_06_run_attempt,
        artifact_id=s6_06_artifact_id,
        artifact_digest=s6_06_artifact_digest,
        source_sha=source_sha,
    )
    try:
        _verify_s6_06_bundle_identity(
            s6_06_bundle_dir,
            source_sha=source_sha,
            source_tree_sha=source_tree_sha,
        )
        verify_final_release_evidence(
            bundle_dir=s6_06_bundle_dir,
            repository=repository,
            source_sha=source_sha,
            source_tree_sha=source_tree_sha,
            github_metadata_dir=s6_06_metadata_dir,
        )
    except S607AcceptanceError:
        raise
    except Exception as exc:
        raise _fail("S6_07_S6_06_VERIFICATION_FAILED", "S6-06 canonical verifier failed") from exc


def _safe_zip_name(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise _fail("S6_07_S6_06_VERIFICATION_FAILED", "unsafe archive path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise _fail("S6_07_S6_06_VERIFICATION_FAILED", "archive path traversal")
    return path


def extract_s6_06_artifact_archive(archive: Path, output_dir: Path) -> Path:
    """Safely extract a downloaded S6-06 ZIP into a fresh directory."""

    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise _fail(
                "S6_07_S6_06_VERIFICATION_FAILED", "S6-06 extraction directory is not empty"
            )
    else:
        output_dir.mkdir(parents=True)
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(archive) as source:
            for info in source.infolist():
                relative = _safe_zip_name(info.filename)
                if info.is_dir():
                    continue
                if str(relative) in seen:
                    raise _fail("S6_07_S6_06_VERIFICATION_FAILED", "duplicate archive path")
                seen.add(str(relative))
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK or mode not in (0, stat.S_IFREG):
                    raise _fail("S6_07_S6_06_VERIFICATION_FAILED", "archive contains special file")
                target = output_dir.joinpath(*relative.parts)
                resolved = target.resolve()
                if output_dir.resolve() not in resolved.parents:
                    raise _fail(
                        "S6_07_S6_06_VERIFICATION_FAILED", "archive escapes extraction root"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(info))
    except S607AcceptanceError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise _fail("S6_07_S6_06_VERIFICATION_FAILED", "S6-06 archive extraction failed") from exc
    return output_dir


def _s6_06_document(
    *,
    source_sha: str,
    source_tree_sha: str,
    generated_at: str,
    run_id: int,
    run_attempt: int,
    artifact_id: int,
    artifact_digest: str,
) -> dict[str, Any]:
    return {
        "schema_version": f"{S6_07_SCHEMA_VERSION}-s6-06-authority",
        "task": EXPECTED_TASK,
        "version": EXPECTED_VERSION,
        "slice": 6,
        "item": "S6-07",
        "source_sha": source_sha,
        "source_tree_sha": source_tree_sha,
        "generated_at": generated_at,
        "controlled_synthetic": True,
        "real_production_data": False,
        "real_production_operation": False,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "artifact_id": artifact_id,
        "artifact_name": f"task012-s6-06-final-release-evidence-{run_id}-{run_attempt}",
        "artifact_digest": artifact_digest,
        "verification_result": "PASS",
        "authority_reused": True,
        "s6_07_does_not_rerun_s6_06": True,
    }


def _build_documents(
    *,
    source_sha: str,
    source_tree_sha: str,
    generated_at: str,
    s6_06: Mapping[str, Any],
    observations: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    common = {
        "schema_version": S6_07_SCHEMA_VERSION,
        "task": EXPECTED_TASK,
        "version": EXPECTED_VERSION,
        "slice": 6,
        "item": "S6-07",
        "source_sha": source_sha,
        "source_tree_sha": source_tree_sha,
        "generated_at": generated_at,
        "controlled_synthetic": True,
        "real_production_data": False,
        "real_production_operation": False,
    }
    summary = {
        **common,
        "acceptance_type": S6_07_ACCEPTANCE_TYPE,
        "s6_06_run_id": s6_06["run_id"],
        "s6_06_artifact_id": s6_06["artifact_id"],
        "s6_06_artifact_digest": s6_06["artifact_digest"],
        "s6_06_verification_result": "PASS",
        "runtime_lifecycle_result": "PASS",
        "production_http_scope_result": "PASS",
        "persistence_e2e_result": "PASS",
        "observability_security_result": "PASS",
        "production_promotion": False,
        "required_gate_count": 6,
        "passed_gate_count": 6,
        "missing_gate_count": 0,
        "failed_gate_count": 0,
        "acceptance_result": "PASS",
        "next_required_stage": "S6-07_INDEPENDENT_REVIEW",
        "next_stage_status": "NOT_AUTHORIZED",
    }
    source = {
        **common,
        "repository": EXPECTED_REPOSITORY,
        "application_version": EXPECTED_VERSION,
        "release_version": EXPECTED_RELEASE_VERSION,
        "source_commit_present": True,
        "source_tree_valid": True,
        "s6_06_source_binding_required": True,
        "verification_result": "PASS",
    }
    runtime = {**common, **observations["runtime_lifecycle"], "verification_result": "PASS"}
    http_scope = {**common, **observations["production_http_scope"], "verification_result": "PASS"}
    persistence = {**common, **observations["persistence_e2e"], "verification_result": "PASS"}
    security = {**common, **observations["observability_security"], "verification_result": "PASS"}
    return {
        "acceptance-summary.json": summary,
        "source-identity.json": source,
        "s6-06-authority.json": dict(s6_06),
        "runtime-lifecycle-observations.json": runtime,
        "production-http-scope-observations.json": http_scope,
        "persistence-e2e-observations.json": persistence,
        "observability-security-observations.json": security,
    }


def _write_documents(output_dir: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    for name, document in documents.items():
        _safe_secret_scan(document, path=name)
        (output_dir / name).write_bytes(canonical_bytes(document))
    sums = "".join(f"{_sha256(output_dir / name)}  {name}\n" for name in S6_07_JSON_FILES)
    (output_dir / "SHA256SUMS").write_text(sums, encoding="ascii")
    (output_dir / "SHA256SUMS.sha256").write_text(
        f"{_sha256(output_dir / 'SHA256SUMS')}  SHA256SUMS\n", encoding="ascii"
    )


def assemble_s6_07_acceptance_evidence(
    *,
    output_dir: Path,
    repository: str,
    source_sha: str,
    source_tree_sha: str,
    generated_at: str,
    s6_06_run_id: int,
    s6_06_run_attempt: int,
    s6_06_artifact_id: int,
    s6_06_artifact_digest: str,
    s6_06_bundle_dir: Path,
    s6_06_metadata_dir: Path,
    observations: Path | Mapping[str, Any],
) -> Path:
    """Verify all controlled observations and assemble the exact nine files."""

    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise _fail("S6_07_EVIDENCE_BUNDLE_INVALID", "output directory must be empty")
    _validate_source(repository=repository, source_sha=source_sha, source_tree_sha=source_tree_sha)
    observation_data = _read_observations(observations)
    validated = _validate_observations(
        observation_data, source_sha=source_sha, source_tree_sha=source_tree_sha
    )
    s6_06 = _s6_06_document(
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        generated_at=generated_at,
        run_id=s6_06_run_id,
        run_attempt=s6_06_run_attempt,
        artifact_id=s6_06_artifact_id,
        artifact_digest=s6_06_artifact_digest,
    )
    verify_s6_06_prerequisite(
        repository=repository,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        s6_06_run_id=s6_06_run_id,
        s6_06_run_attempt=s6_06_run_attempt,
        s6_06_artifact_id=s6_06_artifact_id,
        s6_06_artifact_digest=s6_06_artifact_digest,
        s6_06_bundle_dir=s6_06_bundle_dir,
        s6_06_metadata_dir=s6_06_metadata_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    documents = _build_documents(
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        generated_at=generated_at,
        s6_06=s6_06,
        observations=validated,
    )
    _write_documents(output_dir, documents)
    verify_s6_07_acceptance_evidence(
        bundle_dir=output_dir,
        repository=repository,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        s6_06_run_id=s6_06_run_id,
        s6_06_run_attempt=s6_06_run_attempt,
        s6_06_artifact_id=s6_06_artifact_id,
        s6_06_artifact_digest=s6_06_artifact_digest,
        s6_06_bundle_dir=s6_06_bundle_dir,
        s6_06_metadata_dir=s6_06_metadata_dir,
    )
    return output_dir


def verify_s6_07_acceptance_evidence(
    *,
    bundle_dir: Path,
    repository: str,
    source_sha: str,
    source_tree_sha: str,
    s6_06_run_id: int,
    s6_06_run_attempt: int,
    s6_06_artifact_id: int,
    s6_06_artifact_digest: str,
    s6_06_bundle_dir: Path,
    s6_06_metadata_dir: Path,
) -> None:
    """Independently verify S6-07 without trusting the recorded PASS fields."""

    _validate_source(repository=repository, source_sha=source_sha, source_tree_sha=source_tree_sha)
    _verify_exact_shape(bundle_dir)
    verify_s6_07_checksums(bundle_dir)
    documents = {name: _read_json(bundle_dir / name) for name in S6_07_JSON_FILES}
    for name, document in documents.items():
        _safe_secret_scan(document, path=name)
        _eq(
            document.get("source_sha"),
            source_sha,
            field=f"{name}.source_sha",
            code="S6_07_SOURCE_SHA_MISMATCH",
        )
        _eq(
            document.get("source_tree_sha"),
            source_tree_sha,
            field=f"{name}.source_tree_sha",
            code="S6_07_SOURCE_TREE_INVALID",
        )
        _eq(
            document.get("controlled_synthetic"),
            True,
            field=f"{name}.controlled_synthetic",
            code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
        )
        _eq(
            document.get("real_production_operation"),
            False,
            field=f"{name}.real_production_operation",
            code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
        )
    summary = documents["acceptance-summary.json"]
    _eq(
        summary.get("acceptance_type"),
        S6_07_ACCEPTANCE_TYPE,
        field="acceptance_type",
        code="S6_07_EVIDENCE_BUNDLE_INVALID",
    )
    _eq(
        summary.get("acceptance_result"),
        "PASS",
        field="acceptance_result",
        code="S6_07_EVIDENCE_BUNDLE_INVALID",
    )
    _eq(
        summary.get("next_stage_status"),
        "NOT_AUTHORIZED",
        field="next_stage_status",
        code="S6_07_EVIDENCE_BUNDLE_INVALID",
    )
    authority = documents["s6-06-authority.json"]
    _eq(
        authority.get("run_id"),
        s6_06_run_id,
        field="s6-06 run id",
        code="S6_07_S6_06_AUTHORITY_MISMATCH",
    )
    _eq(
        authority.get("artifact_id"),
        s6_06_artifact_id,
        field="s6-06 artifact id",
        code="S6_07_S6_06_AUTHORITY_MISMATCH",
    )
    _eq(
        authority.get("artifact_digest"),
        s6_06_artifact_digest,
        field="s6-06 digest",
        code="S6_07_S6_06_DIGEST_MISMATCH",
    )
    _validate_observations(
        {
            "task": EXPECTED_TASK,
            "version": EXPECTED_VERSION,
            "slice": 6,
            "item": "S6-07",
            "source_sha": source_sha,
            "source_tree_sha": source_tree_sha,
            "controlled_synthetic": True,
            "real_production_data": False,
            "real_production_operation": False,
            "runtime_lifecycle": documents["runtime-lifecycle-observations.json"],
            "production_http_scope": documents["production-http-scope-observations.json"],
            "persistence_e2e": documents["persistence-e2e-observations.json"],
            "observability_security": documents["observability-security-observations.json"],
        },
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
    )
    verify_s6_06_prerequisite(
        repository=repository,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        s6_06_run_id=s6_06_run_id,
        s6_06_run_attempt=s6_06_run_attempt,
        s6_06_artifact_id=s6_06_artifact_id,
        s6_06_artifact_digest=s6_06_artifact_digest,
        s6_06_bundle_dir=s6_06_bundle_dir,
        s6_06_metadata_dir=s6_06_metadata_dir,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TASK-012 S6-07 operational acceptance boundary")
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract-s6-06-artifact")
    extract.add_argument("--archive", required=True, type=Path)
    extract.add_argument("--output-dir", required=True, type=Path)

    prerequisite = sub.add_parser("verify-s6-06-prerequisite")
    prerequisite.add_argument("--repository", default=EXPECTED_REPOSITORY)
    prerequisite.add_argument("--source-sha", required=True)
    prerequisite.add_argument("--source-tree-sha", required=True)
    prerequisite.add_argument("--s6-06-run-id", required=True, type=int)
    prerequisite.add_argument("--s6-06-run-attempt", required=True, type=int)
    prerequisite.add_argument("--s6-06-artifact-id", required=True, type=int)
    prerequisite.add_argument("--s6-06-artifact-digest", required=True)
    prerequisite.add_argument("--s6-06-bundle-dir", required=True, type=Path)
    prerequisite.add_argument("--s6-06-metadata-dir", required=True, type=Path)

    for name in ("assemble-s6-07-acceptance-evidence", "verify-s6-07-acceptance-evidence"):
        command = sub.add_parser(name)
        command.add_argument("--repository", default=EXPECTED_REPOSITORY)
        command.add_argument("--source-sha", required=True)
        command.add_argument("--source-tree-sha", required=True)
        command.add_argument("--s6-06-run-id", required=True, type=int)
        command.add_argument("--s6-06-run-attempt", required=True, type=int)
        command.add_argument("--s6-06-artifact-id", required=True, type=int)
        command.add_argument("--s6-06-artifact-digest", required=True)
        command.add_argument("--s6-06-bundle-dir", required=True, type=Path)
        command.add_argument("--s6-06-metadata-dir", required=True, type=Path)
        if name.startswith("assemble"):
            command.add_argument("--output-dir", required=True, type=Path)
            command.add_argument("--observations", required=True, type=Path)
            command.add_argument("--generated-at", required=True)
        else:
            command.add_argument("--bundle-dir", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "extract-s6-06-artifact":
            extract_s6_06_artifact_archive(args.archive, args.output_dir)
            print("S6_06_EXTRACTION=PASS")
            return 0
        if args.command == "verify-s6-06-prerequisite":
            verify_s6_06_prerequisite(
                repository=args.repository,
                source_sha=args.source_sha,
                source_tree_sha=args.source_tree_sha,
                s6_06_run_id=args.s6_06_run_id,
                s6_06_run_attempt=args.s6_06_run_attempt,
                s6_06_artifact_id=args.s6_06_artifact_id,
                s6_06_artifact_digest=args.s6_06_artifact_digest,
                s6_06_bundle_dir=args.s6_06_bundle_dir,
                s6_06_metadata_dir=args.s6_06_metadata_dir,
            )
            print("S6_06_VERIFICATION_RESULT=PASS")
            return 0
        common = {
            "repository": args.repository,
            "source_sha": args.source_sha,
            "source_tree_sha": args.source_tree_sha,
            "s6_06_run_id": args.s6_06_run_id,
            "s6_06_run_attempt": args.s6_06_run_attempt,
            "s6_06_artifact_id": args.s6_06_artifact_id,
            "s6_06_artifact_digest": args.s6_06_artifact_digest,
            "s6_06_bundle_dir": args.s6_06_bundle_dir,
            "s6_06_metadata_dir": args.s6_06_metadata_dir,
        }
        if args.command == "assemble-s6-07-acceptance-evidence":
            path = assemble_s6_07_acceptance_evidence(
                output_dir=args.output_dir,
                generated_at=args.generated_at,
                observations=args.observations,
                **common,
            )
            print("S6_07_ASSEMBLY_RESULT=PASS")
            print(f"BUNDLE_DIR={path}")
            return 0
        if args.command == "verify-s6-07-acceptance-evidence":
            verify_s6_07_acceptance_evidence(bundle_dir=args.bundle_dir, **common)
            print("S6_07_VERIFICATION_RESULT=PASS")
            return 0
        raise _fail("S6_07_EVIDENCE_BUNDLE_INVALID", "unsupported command")
    except S607AcceptanceError as exc:
        print(f"ERROR_CODE={exc.failure_code}")
        return 1


__all__ = [
    "EXPECTED_REPOSITORY",
    "S6_07_BUNDLE_FILES",
    "S6_07_FAILURE_CODES",
    "S6_07_JSON_FILES",
    "S607AcceptanceError",
    "assemble_s6_07_acceptance_evidence",
    "extract_s6_06_artifact_archive",
    "main",
    "verify_s6_06_prerequisite",
    "verify_s6_07_acceptance_evidence",
    "verify_s6_07_checksums",
]


if __name__ == "__main__":
    raise SystemExit(main())
