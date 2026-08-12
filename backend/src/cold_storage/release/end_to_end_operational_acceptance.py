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
S6_07_RAW_OBSERVATION_SCHEMA = "task012-s6-07-operational-observation-v2"
S6_07_ACCEPTANCE_TYPE = "controlled_end_to_end_operational_acceptance"

S6_07_STAGE_NAMES: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

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


def _require_pass_fields(
    payload: Mapping[str, Any], expected: Mapping[str, object], *, code: str
) -> None:
    for field, expected_value in expected.items():
        _eq(payload.get(field), expected_value, field=field, code=code)


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


def _require_int(value: object, *, field: str, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(code, f"{field} must be an integer raw observation")
    return value


def _require_sha256(value: object, *, field: str, code: str) -> str:
    result = _string(value, field=field)
    if not HEX_RE.fullmatch(result):
        raise _fail(code, f"{field} must be a SHA-256 hex digest")
    return result


def _response(section: Mapping[str, Any], *, field: str, code: str) -> Mapping[str, Any]:
    response = _mapping(section.get(field), field=field)
    _require_int(response.get("status"), field=f"{field}.status", code=code)
    return response


def _response_body(response: Mapping[str, Any], *, field: str, code: str) -> Mapping[str, Any]:
    return _mapping(response.get("body"), field=f"{field}.body")


def _require_response_status(
    response: Mapping[str, Any], *, expected: int, field: str, code: str
) -> Mapping[str, Any]:
    if response.get("status") != expected:
        raise _fail(code, f"{field} returned unexpected HTTP status")
    return response


def _find_capability(body: Mapping[str, Any], *, name: str) -> Mapping[str, Any]:
    capabilities = body.get("capabilities")
    if not isinstance(capabilities, list):
        raise _fail("S6_07_RUNTIME_STARTUP_FAILED", "readiness capabilities are missing")
    for capability in capabilities:
        if isinstance(capability, Mapping) and capability.get("name") == name:
            return capability
    raise _fail("S6_07_RUNTIME_STARTUP_FAILED", f"missing capability: {name}")


def _derive_assertions(
    observations: Mapping[str, Any], *, source_sha: str, source_tree_sha: str
) -> dict[str, str]:
    """Derive acceptance results exclusively from raw runtime observations."""

    _commit(source_tree_sha, field="source_tree_sha")
    runtime = _mapping(observations.get("runtime_lifecycle"), field="runtime_lifecycle")
    identity = _mapping(runtime.get("build_identity"), field="runtime_lifecycle.build_identity")
    if identity.get("file_present") is not True:
        raise _fail("S6_07_RUNTIME_STARTUP_FAILED", "build identity file was not observed")
    _eq(
        identity.get("commit_sha"),
        source_sha,
        field="build identity commit",
        code="S6_07_SOURCE_SHA_MISMATCH",
    )
    _eq(
        identity.get("version"),
        EXPECTED_RELEASE_VERSION,
        field="build identity version",
        code="S6_07_RUNTIME_STARTUP_FAILED",
    )

    migration = _mapping(runtime.get("migration"), field="runtime_lifecycle.migration")
    if (
        _require_int(
            migration.get("exit_code"), field="migration.exit_code", code="S6_07_MIGRATION_FAILED"
        )
        != 0
    ):
        raise _fail("S6_07_MIGRATION_FAILED", "migration command failed")
    migration_output = _string(migration.get("current_output"), field="migration.current_output")
    if "(head)" not in migration_output:
        raise _fail("S6_07_MIGRATION_FAILED", "alembic current did not report the exact head")

    container = _mapping(runtime.get("container"), field="runtime_lifecycle.container")
    if container.get("running") is not True or container.get("status") != "running":
        raise _fail("S6_07_RUNTIME_STARTUP_FAILED", "backend container state is not running")

    live_response = _require_response_status(
        _response(runtime, field="liveness", code="S6_07_READINESS_FAILED"),
        expected=200,
        field="liveness",
        code="S6_07_READINESS_FAILED",
    )
    if (
        _response_body(live_response, field="liveness", code="S6_07_READINESS_FAILED").get("status")
        != "live"
    ):
        raise _fail("S6_07_READINESS_FAILED", "liveness body is not live")

    ready_response = _require_response_status(
        _response(runtime, field="readiness", code="S6_07_READINESS_FAILED"),
        expected=200,
        field="readiness",
        code="S6_07_READINESS_FAILED",
    )
    ready_body = _response_body(ready_response, field="readiness", code="S6_07_READINESS_FAILED")
    if ready_body.get("status") != "ready":
        raise _fail("S6_07_READINESS_FAILED", "readiness body is not ready")
    capability = _find_capability(ready_body, name="model_backed_agent")
    if capability.get("status") != "disabled" or capability.get("code") != (
        "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE"
    ):
        raise _fail("S6_07_FAKE_AGENT_REACHABLE", "strict capability projection is not disabled")

    database = _mapping(runtime.get("database"), field="runtime_lifecycle.database")
    if database.get("backend") != "postgresql":
        raise _fail("S6_07_COEFFICIENT_AUTHORITY_INVALID", "runtime database is not PostgreSQL")
    if database.get("service_class") != "DatabaseCoefficientService":
        raise _fail(
            "S6_07_COEFFICIENT_AUTHORITY_INVALID",
            "canonical coefficient service was not observed",
        )
    storage = _mapping(runtime.get("artifact_storage"), field="runtime_lifecycle.artifact_storage")
    if storage.get("probe_exists") is not True:
        raise _fail("S6_07_RUNTIME_STARTUP_FAILED", "artifact storage probe was not observed")
    _require_sha256(
        storage.get("probe_sha256"),
        field="artifact_storage.probe_sha256",
        code="S6_07_RUNTIME_STARTUP_FAILED",
    )

    http_scope = _mapping(observations.get("production_http_scope"), field="production_http_scope")
    coefficient = _mapping(http_scope.get("coefficient"), field="production_http_scope.coefficient")
    created = _require_response_status(
        _response(coefficient, field="created", code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED"),
        expected=200,
        field="coefficient.created",
        code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
    )
    readback = _require_response_status(
        _response(coefficient, field="readback", code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED"),
        expected=200,
        field="coefficient.readback",
        code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
    )
    created_body = _response_body(
        created, field="coefficient.created", code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED"
    )
    readback_body = _response_body(
        readback, field="coefficient.readback", code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED"
    )
    coefficient_id = _string(created_body.get("id"), field="coefficient.created.body.id")
    _eq(
        readback_body.get("id"),
        coefficient_id,
        field="coefficient readback id",
        code="S6_07_COEFFICIENT_AUTHORITY_INVALID",
    )
    if coefficient.get("persisted_row_id") != coefficient_id:
        raise _fail("S6_07_COEFFICIENT_AUTHORITY_INVALID", "persisted coefficient row differs")

    agent = _mapping(http_scope.get("planning_agent"), field="production_http_scope.planning_agent")
    agent_response = _require_response_status(
        _response(agent, field="response", code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED"),
        expected=503,
        field="planning_agent.response",
        code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
    )
    agent_body = _response_body(
        agent_response, field="planning_agent.response", code="S6_07_PRODUCTION_HTTP_SCOPE_FAILED"
    )
    error = _mapping(agent_body.get("error"), field="planning_agent.error")
    if error.get("code") != "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE":
        raise _fail("S6_07_FAKE_AGENT_REACHABLE", "agent did not return the strict disabled code")
    details = _mapping(error.get("details"), field="planning_agent.error.details")
    if details.get("retryable") is not False:
        raise _fail("S6_07_PRODUCTION_HTTP_SCOPE_FAILED", "disabled agent is incorrectly retryable")

    persistence = _mapping(observations.get("persistence_e2e"), field="persistence_e2e")
    scheme = _mapping(persistence.get("scheme"), field="persistence_e2e.scheme")
    scheme_response = _response(scheme, field="response", code="S6_07_PERSISTENCE_FAILED")
    _require_response_status(
        scheme_response,
        expected=200,
        field="scheme.response",
        code="S6_07_PERSISTENCE_FAILED",
    )
    persisted = _mapping(scheme.get("persisted"), field="persistence_e2e.scheme.persisted")
    run_id = _string(persisted.get("run_id"), field="persisted.run_id")
    if persisted.get("status") != "completed":
        raise _fail("S6_07_PERSISTENCE_FAILED", "persisted scheme run is not completed")
    stages = persisted.get("stages")
    if not isinstance(stages, list) or len(stages) != len(S6_07_STAGE_NAMES):
        raise _fail("S6_07_PERSISTENCE_FAILED", "persisted stage evidence is incomplete")
    observed_stage_names: list[str] = []
    for stage in stages:
        stage_mapping = _mapping(stage, field="persistence_e2e.scheme.persisted.stages[]")
        stage_name = _string(stage_mapping.get("name"), field="stage.name")
        if stage_name in observed_stage_names or stage_name not in S6_07_STAGE_NAMES:
            raise _fail("S6_07_PERSISTENCE_FAILED", "persisted stage names are ambiguous")
        if stage_mapping.get("status") != "completed":
            raise _fail("S6_07_PERSISTENCE_FAILED", f"stage did not complete: {stage_name}")
        observed_stage_names.append(stage_name)
    if set(observed_stage_names) != set(S6_07_STAGE_NAMES):
        raise _fail("S6_07_PERSISTENCE_FAILED", "not all five stages were observed")

    if not isinstance(persisted.get("source_binding"), Mapping):
        raise _fail("S6_07_PERSISTENCE_FAILED", "SourceBinding observation is missing")
    binding = cast(Mapping[str, Any], persisted["source_binding"])
    if binding.get("exists") is not True or binding.get("run_id") != run_id:
        raise _fail(
            "S6_07_PERSISTENCE_FAILED", "SourceBinding is missing or belongs to another run"
        )
    slot_ids = binding.get("required_slot_ids")
    if not isinstance(slot_ids, list) or set(slot_ids) != set(S6_07_STAGE_NAMES):
        raise _fail("S6_07_PERSISTENCE_FAILED", "SourceBinding slots are incomplete")
    _require_sha256(
        binding.get("content_sha256"),
        field="source_binding.content_sha256",
        code="S6_07_PERSISTENCE_FAILED",
    )

    resolution = _mapping(
        persisted.get("coefficient_resolution"), field="persisted.coefficient_resolution"
    )
    if resolution.get("coefficient_id") != coefficient_id:
        raise _fail("S6_07_PERSISTENCE_FAILED", "scheme did not use the persisted coefficient")
    if resolution.get("source_type") in (None, "demo"):
        raise _fail("S6_07_PERSISTENCE_FAILED", "demo coefficient source was used")
    if resolution.get("selection_strategy") != "explicit_id":
        raise _fail("S6_07_PERSISTENCE_FAILED", "coefficient selection was not explicit")

    if not isinstance(persisted.get("power_authority"), Mapping):
        raise _fail("S6_07_PERSISTENCE_FAILED", "power authority observation is missing")
    power = cast(Mapping[str, Any], persisted["power_authority"])
    if power.get("slot_id") != "power" or power.get("value_present") is not True:
        raise _fail("S6_07_PERSISTENCE_FAILED", "power authority was not persisted")
    _require_sha256(
        power.get("value_sha256"),
        field="power_authority.value_sha256",
        code="S6_07_PERSISTENCE_FAILED",
    )
    archive = _mapping(persisted.get("source_archive"), field="persisted.source_archive")
    if archive.get("exists") is not True or archive.get("run_id") != run_id:
        raise _fail("S6_07_PERSISTENCE_FAILED", "source archive is missing or unbound")
    archive_digest = _require_sha256(
        archive.get("sha256"),
        field="source_archive.sha256",
        code="S6_07_PERSISTENCE_FAILED",
    )
    if archive.get("expected_sha256") != archive_digest:
        raise _fail("S6_07_PERSISTENCE_FAILED", "source archive digest mismatch")

    restart = _mapping(persistence.get("restart"), field="persistence_e2e.restart")
    if restart.get("performed") is not True:
        raise _fail("S6_07_PERSISTENCE_FAILED", "restart was not observed")
    restart_ready = _require_response_status(
        _response(restart, field="readiness", code="S6_07_PERSISTENCE_FAILED"),
        expected=200,
        field="restart.readiness",
        code="S6_07_PERSISTENCE_FAILED",
    )
    if (
        _response_body(
            restart_ready, field="restart.readiness", code="S6_07_PERSISTENCE_FAILED"
        ).get("status")
        != "ready"
    ):
        raise _fail("S6_07_PERSISTENCE_FAILED", "readiness after restart did not pass")
    restart_coeff = _mapping(
        restart.get("coefficient_readback"), field="restart.coefficient_readback"
    )
    if restart_coeff.get("id") != coefficient_id:
        raise _fail("S6_07_PERSISTENCE_FAILED", "coefficient did not survive restart")
    restart_binding = _mapping(restart.get("source_binding"), field="restart.source_binding")
    if restart_binding.get("exists") is not True or restart_binding.get("run_id") != run_id:
        raise _fail("S6_07_PERSISTENCE_FAILED", "SourceBinding did not survive restart")
    artifact_probe = _mapping(restart.get("artifact_probe"), field="restart.artifact_probe")
    if artifact_probe.get("exists") is not True:
        raise _fail("S6_07_PERSISTENCE_FAILED", "artifact volume probe did not survive restart")
    _require_sha256(
        artifact_probe.get("sha256"),
        field="restart.artifact_probe.sha256",
        code="S6_07_PERSISTENCE_FAILED",
    )

    observability = _mapping(
        observations.get("observability_security"), field="observability_security"
    )
    correlation = _mapping(observability.get("correlation"), field="observability.correlation")
    if correlation.get("header_present") is not True or correlation.get(
        "expected"
    ) != correlation.get("observed"):
        raise _fail("S6_07_OBSERVABILITY_FAILED", "correlation identity was not observed")
    structured = _mapping(
        observability.get("structured_logging"), field="observability.structured_logging"
    )
    count = _require_int(
        structured.get("record_count"),
        field="structured_logging.record_count",
        code="S6_07_OBSERVABILITY_FAILED",
    )
    parsed = _require_int(
        structured.get("parseable_record_count"),
        field="structured_logging.parseable_record_count",
        code="S6_07_OBSERVABILITY_FAILED",
    )
    matched = _require_int(
        structured.get("correlation_match_count"),
        field="structured_logging.correlation_match_count",
        code="S6_07_OBSERVABILITY_FAILED",
    )
    if count <= 0 or parsed != count or matched <= 0:
        raise _fail("S6_07_OBSERVABILITY_FAILED", "structured log observations are incomplete")
    redaction = _mapping(observability.get("redaction"), field="observability.redaction")
    for field in ("password_occurrences", "database_url_occurrences", "token_occurrences"):
        if (
            _require_int(
                redaction.get(field),
                field=f"redaction.{field}",
                code="S6_07_OBSERVABILITY_FAILED",
            )
            != 0
        ):
            raise _fail("S6_07_SECRET_MATERIAL_DETECTED", f"secret marker observed: {field}")

    return {
        "runtime_lifecycle": "PASS",
        "production_http_scope": "PASS",
        "persistence_e2e": "PASS",
        "observability_security": "PASS",
    }


def _validate_observations(
    observations: Mapping[str, Any], *, source_sha: str, source_tree_sha: str
) -> dict[str, dict[str, Any]]:
    """Validate raw observations and return only raw evidence sections."""
    _eq(
        observations.get("schema_version"),
        S6_07_RAW_OBSERVATION_SCHEMA,
        field="observations.schema_version",
        code="S6_07_EVIDENCE_BUNDLE_INVALID",
    )
    _eq(
        observations.get("observation_type"),
        "raw",
        field="observations.observation_type",
        code="S6_07_EVIDENCE_BUNDLE_INVALID",
    )
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
    if (
        observations.get("controlled_synthetic") is not True
        or observations.get("real_production_data") is not False
        or observations.get("real_production_operation") is not False
    ):
        raise _fail("S6_07_PRODUCTION_HTTP_SCOPE_FAILED", "unsafe evidence scope marker")
    sections = {
        name: dict(_mapping(observations.get(name), field=name))
        for name in (
            "runtime_lifecycle",
            "production_http_scope",
            "persistence_e2e",
            "observability_security",
        )
    }
    _derive_assertions(observations, source_sha=source_sha, source_tree_sha=source_tree_sha)
    return sections


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
    assertions: Mapping[str, str],
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
        "runtime_lifecycle_result": assertions["runtime_lifecycle"],
        "production_http_scope_result": assertions["production_http_scope"],
        "persistence_e2e_result": assertions["persistence_e2e"],
        "observability_security_result": assertions["observability_security"],
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
    runtime = {
        **common,
        "observation_type": "raw",
        **observations["runtime_lifecycle"],
    }
    http_scope = {
        **common,
        "observation_type": "raw",
        **observations["production_http_scope"],
    }
    persistence = {
        **common,
        "observation_type": "raw",
        **observations["persistence_e2e"],
    }
    security = {
        **common,
        "observation_type": "raw",
        **observations["observability_security"],
    }
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
    assertions = _derive_assertions(
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
        assertions=assertions,
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
    for name in (
        "runtime-lifecycle-observations.json",
        "production-http-scope-observations.json",
        "persistence-e2e-observations.json",
        "observability-security-observations.json",
    ):
        _eq(
            documents[name].get("observation_type"),
            "raw",
            field=f"{name}.observation_type",
            code="S6_07_EVIDENCE_BUNDLE_INVALID",
        )
    raw_observations = {
        "schema_version": S6_07_RAW_OBSERVATION_SCHEMA,
        "observation_type": "raw",
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
    }
    assertions = _derive_assertions(
        raw_observations, source_sha=source_sha, source_tree_sha=source_tree_sha
    )
    _validate_observations(
        raw_observations,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
    )
    for field, expected in {
        "runtime_lifecycle_result": assertions["runtime_lifecycle"],
        "production_http_scope_result": assertions["production_http_scope"],
        "persistence_e2e_result": assertions["persistence_e2e"],
        "observability_security_result": assertions["observability_security"],
        "acceptance_result": "PASS",
    }.items():
        _eq(
            summary.get(field),
            expected,
            field=field,
            code="S6_07_EVIDENCE_BUNDLE_INVALID",
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
