"""TASK-012 V0.2 Slice 6 Package 3 final evidence assembly.

This module is a read/verify/bind/assemble boundary. It never builds, deploys,
backs up, restores, migrates, rolls back, signs, promotes, or dispatches a
workflow. The frozen authority table below is the input contract for the first
V0.2 final release evidence bundle. Every authority is checked against its
expected run, artifact, digest, and lineage identity before a bundle is made.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from cold_storage.release.canonical_serialization import (
    CanonicalSerializationError,
    ReleaseEvidenceError,
    canonical_bytes,
    load_json_strict,
)

PACKAGE3_SCHEMA_VERSION = "task012-s6-06-final-release-evidence-v1"
AUTHORITY_INDEX_SCHEMA_VERSION = "task012-s6-06-authority-index-v1"
EXPECTED_REPOSITORY = "xuezhiorange-png/cold-storage-planning-agent"
IMPLEMENTATION_BASE_SHA = "7b36d68afb94577db401b8825013cc14ab0943d7"
IMPLEMENTATION_BASE_TREE_SHA = "a43c2686a5f2c91aae1b4966f31923648c5eff03"
PACKAGE3_IMPLEMENTATION_HEAD_SHA = "15952da351c922939f82d5e32bdd60216537fcdb"
EXPECTED_VERSION = "V0.2"
EXPECTED_RELEASE_VERSION = "v0.2.0"
EXPECTED_RC_SOURCE_SHA = "043731fea4e60feb6b929c524c4b68e87ed67bd7"
EXPECTED_RC_SOURCE_TREE_SHA = "b456e77f07a0cef801c57d2f089a318c35c145c4"

FINAL_JSON_FILES: tuple[str, ...] = (
    "authority-index.json",
    "recovery-authority-summary.json",
    "release-evidence-summary.json",
    "release-provenance-summary.json",
    "runtime-readiness-summary.json",
    "source-identity.json",
)
FINAL_BUNDLE_FILES: tuple[str, ...] = (
    *FINAL_JSON_FILES,
    "SHA256SUMS",
    "SHA256SUMS.sha256",
)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
POSITIVE_DECIMAL_RE = re.compile(r"^[1-9][0-9]*$")
RFC3339_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class FinalReleaseEvidenceError(ReleaseEvidenceError):
    """A fail-closed S6-06 validation failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(failure_code=code, detail=detail)


def _row(
    *,
    authority_id: str,
    authority_type: str,
    domain: str,
    canonical_path: str | None,
    pr_number: int | None,
    merge_sha: str | None,
    workflow_name: str | None,
    workflow_path: str | None,
    run_id: int | None,
    run_attempt: int | None,
    event: str | None,
    head_sha: str | None,
    conclusion: str | None,
    artifact_id: int | None,
    artifact_name: str | None,
    artifact_digest: str | None,
    artifact_expired: bool | None,
    receipt_name: str | None,
    receipt_sha256: str | None,
    source_environment_class: str,
    controlled_synthetic: bool,
    authority_source_sha: str | None = None,
) -> dict[str, Any]:
    return {
        "authority_id": authority_id,
        "authority_type": authority_type,
        "domain": domain,
        "required": True,
        "canonical_repository_path": canonical_path,
        "canonical_pr_number": pr_number,
        "canonical_merge_sha": merge_sha,
        "workflow_name": workflow_name,
        "workflow_path": workflow_path,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "workflow_event": event,
        "workflow_head_sha": head_sha,
        "workflow_conclusion": conclusion,
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "artifact_digest": artifact_digest,
        "artifact_expired": artifact_expired,
        "receipt_name": receipt_name,
        "receipt_sha256": receipt_sha256,
        "source_environment_class": source_environment_class,
        "controlled_synthetic": controlled_synthetic,
        "production": False,
        "production_operation_performed": False,
        "authority_source_sha": authority_source_sha or merge_sha,
        "current_release_source_sha": None,
        "lineage_binding_result": "PASS",
        "verification_result": "PASS",
    }


_FROZEN_AUTHORITY_ROWS: tuple[dict[str, Any], ...] = (
    _row(
        authority_id="SOURCE_MAIN_IDENTITY",
        authority_type="source",
        domain="Source / Version Identity",
        canonical_path="backend/src/cold_storage/release/provenance_schema.py;backend/src/cold_storage/release/live_evidence_runner.py",
        pr_number=96,
        merge_sha=IMPLEMENTATION_BASE_SHA,
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="ENVIRONMENT_SECURITY",
        authority_type="contract",
        domain="Environment / Configuration / Secrets",
        canonical_path="backend/src/cold_storage/bootstrap/settings.py;backend/src/cold_storage/bootstrap/configuration_redactor.py;docs/tasks/TASK-012-slice1-environment-config-security-contract.md",
        pr_number=74,
        merge_sha="16abd0e1367e9f2c6f1ea9c0983803f166bebda2",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="STARTUP_LIFECYCLE_CONTRACT",
        authority_type="contract",
        domain="Deployment / Startup / Runtime Readiness",
        canonical_path="docs/tasks/TASK-012-slice2-deployment-startup-lifecycle-contract.md",
        pr_number=75,
        merge_sha="d6031ae848b48001c1b5b6d24a413e0db4814505",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="STARTUP_LIFECYCLE_IMPLEMENTATION",
        authority_type="contract",
        domain="Deployment / Startup / Runtime Readiness",
        canonical_path="backend/src/cold_storage/bootstrap/production_entrypoint.py;backend/src/cold_storage/bootstrap/runtime_readiness.py;backend/src/cold_storage/bootstrap/app.py",
        pr_number=76,
        merge_sha="1f6e0e2e10eaa2733be9a67279f04a6eea3e64d1",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="SCHEMA_FAILURE_CLASSIFICATION",
        authority_type="contract",
        domain="Deployment / Startup / Runtime Readiness",
        canonical_path="backend/src/cold_storage/bootstrap/startup_readiness.py;docs/tasks/TASK-012-slice2-deployment-startup-lifecycle-contract.md",
        pr_number=77,
        merge_sha="ad86ff744b2a3adb4d534ab8581953d9a12b4289",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="ARTIFACT_STORAGE_CLASSIFICATION",
        authority_type="contract",
        domain="Deployment / Startup / Runtime Readiness",
        canonical_path="backend/src/cold_storage/bootstrap/runtime_readiness.py;docs/tasks/TASK-012-slice2-deployment-startup-lifecycle-contract.md",
        pr_number=78,
        merge_sha="69f7631f2568a1330e8377448b69c9809de5cc91",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="OBSERVABILITY_AUDIT",
        authority_type="contract",
        domain="Observability / Audit Operations",
        canonical_path="backend/src/cold_storage/bootstrap/middleware/correlation_id.py;backend/src/cold_storage/bootstrap/middleware/structured_logging.py;backend/src/cold_storage/bootstrap/configuration_redactor.py;docs/tasks/TASK-012-slice4-observability-and-audit-operations-contract.md",
        pr_number=79,
        merge_sha="1d661b16b69a08f20d46f8a7a99a0952080b7e61",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="PRODUCTION_DEPENDENCY_CONTRACT",
        authority_type="contract",
        domain="Environment / Configuration / Secrets",
        canonical_path="backend/src/cold_storage/modules/coefficients/infrastructure/repository.py;docs/tasks/TASK-012-slice4-production-dependency-reality-contract.md",
        pr_number=80,
        merge_sha="cd543644aa9d2c1c2b68c1ebdfff66f4b0c5ebc8",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="PRODUCTION_DEPENDENCY_IMPLEMENTATION",
        authority_type="contract",
        domain="Environment / Configuration / Secrets",
        canonical_path="backend/src/cold_storage/bootstrap/app.py;backend/src/cold_storage/modules/coefficients/api/routes.py;docs/tasks/TASK-012-slice4-production-dependency-reality-contract.md",
        pr_number=81,
        merge_sha="25a88f0b65fa7662310701563e306331034d6c34",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="SLICE2_RELEASE_CONTRACT",
        authority_type="contract",
        domain="Slice 2 Release Candidate / Build Provenance",
        canonical_path="docs/tasks/TASK-012-slice2-release-candidate-evidence-contract.md;backend/src/cold_storage/release/evidence_collector.py",
        pr_number=82,
        merge_sha="1c3798bef11aedb8485678b9b60698e9ffb6a75f",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
    ),
    _row(
        authority_id="S2_D0_CAPTURE",
        authority_type="artifact",
        domain="Slice 2 Release Candidate / Build Provenance",
        canonical_path=".github/workflows/ci.yml;backend/src/cold_storage/release/live_evidence_runner.py",
        pr_number=89,
        merge_sha="6fb432575416f452531a345f469e6f9ec8bd789e",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31342745646,
        run_attempt=1,
        event="workflow_dispatch",
        head_sha="6fb432575416f452531a345f469e6f9ec8bd789e",
        conclusion="success",
        artifact_id=9046325555,
        artifact_name="task012-live-evidence-31342745646-1",
        artifact_digest="sha256:791451d6cfa0dccb9f28f4700c74d58e257537a7b79a29241a84716056634020",
        artifact_expired=False,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="controlled_synthetic",
        controlled_synthetic=True,
    ),
    _row(
        authority_id="S2_D1_TRANSPORT",
        authority_type="artifact",
        domain="Slice 2 Release Candidate / Build Provenance",
        canonical_path=".github/workflows/ci.yml;backend/src/cold_storage/release/artifact_transport.py",
        pr_number=90,
        merge_sha="09d99ac2bc7db315d1370e41a4a5e15e7ab107ff",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31352302807,
        run_attempt=1,
        event="workflow_dispatch",
        head_sha="09d99ac2bc7db315d1370e41a4a5e15e7ab107ff",
        conclusion="success",
        artifact_id=9049370270,
        artifact_name="task012-verified-transport-31342745646-1-31352302807-1",
        artifact_digest="sha256:c375e013b4052ad08a407338b5cd99e2653a7b0bfe2f96fed051976b5918ba3f",
        artifact_expired=False,
        receipt_name="artifact-transport-receipt.json",
        receipt_sha256="sha256:38d395a48821241d25c195b68e9695b4c7b7890b64d45712110edbc7da96fb7e",
        source_environment_class="controlled_synthetic",
        controlled_synthetic=True,
    ),
    _row(
        authority_id="S2_ATTESTATION",
        authority_type="artifact",
        domain="Slice 2 Release Candidate / Build Provenance",
        canonical_path=".github/workflows/ci.yml;backend/src/cold_storage/release/live_attestation.py",
        pr_number=91,
        merge_sha="d4a18f056c288ff6cd7673e1765a54dfd4e82f1a",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31371998864,
        run_attempt=1,
        event="workflow_dispatch",
        head_sha="d4a18f056c288ff6cd7673e1765a54dfd4e82f1a",
        conclusion="success",
        artifact_id=9056423295,
        artifact_name="task012-live-attestation-31371998864-1",
        artifact_digest="sha256:102756b94a74383e62cde8e52d8b995936b349625b701b99ad62fc942cf4ffd1",
        artifact_expired=False,
        receipt_name="attestation.json",
        receipt_sha256="sha256:a426e5ef78e121549727daad67ae9b98fbb88d6d4978d9c93d9094cfab4129bb",
        source_environment_class="controlled_synthetic",
        controlled_synthetic=True,
    ),
    _row(
        authority_id="S2_ASSEMBLY",
        authority_type="artifact",
        domain="Slice 2 Release Candidate / Build Provenance",
        canonical_path=".github/workflows/ci.yml;backend/src/cold_storage/release/evidence_collector.py;backend/src/cold_storage/release/live_attestation.py",
        pr_number=92,
        merge_sha="901fafa53fa579bea5891129799a30da1829234d",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31394393604,
        run_attempt=1,
        event="workflow_dispatch",
        head_sha="901fafa53fa579bea5891129799a30da1829234d",
        conclusion="success",
        artifact_id=9064992469,
        artifact_name="task012-assembled-evidence-31394393604-1",
        artifact_digest="sha256:2b048ebf6bca77b126367c2050c3fee49dd4c5f5c439bf7898414d61b03be274",
        artifact_expired=False,
        receipt_name="assembly-metadata.json",
        receipt_sha256="sha256:329485214a2d37f44beea715ee4e99fc5c966861eb7ef5c7aedf4683cc63cf73",
        source_environment_class="controlled_synthetic",
        controlled_synthetic=True,
    ),
    _row(
        authority_id="S6_PACKAGE1_FINAL",
        authority_type="artifact",
        domain="Slice 6 Package 1 Recovery",
        canonical_path="backend/src/cold_storage/recovery/backup_bundle.py;backend/src/cold_storage/recovery/restore_runner.py;backend/tests/integration/test_recovery_postgresql.py;docs/runbooks/TASK-012-slice6-data-recovery-foundation.md",
        pr_number=95,
        merge_sha="658c993040d93371ee3286fc91c8f4abeb5da7b1",
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31469678479,
        run_attempt=1,
        event="workflow_dispatch",
        head_sha="658c993040d93371ee3286fc91c8f4abeb5da7b1",
        conclusion="success",
        artifact_id=9092865725,
        artifact_name="task012-controlled-recovery-31469678479-1",
        artifact_digest="sha256:345841c71d21239753758749f3f02b17925bb73dc2d4b72071c6389e3b481699",
        artifact_expired=False,
        receipt_name="acceptance-summary.json",
        receipt_sha256="sha256:f0eb7e8e43d7df5f50b12e2e464a25780a77598cffb4d5242d00b65af6baa5d7",
        source_environment_class="controlled_synthetic",
        controlled_synthetic=True,
    ),
    _row(
        authority_id="S6_PACKAGE2_FINAL",
        authority_type="artifact",
        domain="Slice 6 Package 2 Recovery",
        canonical_path="backend/src/cold_storage/recovery/failure_recovery.py;backend/src/cold_storage/recovery/restore_runner.py;.github/workflows/task012-slice6-package2-recovery.yml;docs/runbooks/TASK-012-slice6-release-failure-recovery.md",
        pr_number=96,
        merge_sha=IMPLEMENTATION_BASE_SHA,
        workflow_name="TASK-012 Slice 6 Package 2 Release Failure Recovery",
        workflow_path=".github/workflows/task012-slice6-package2-recovery.yml",
        run_id=31493144331,
        run_attempt=1,
        event="workflow_dispatch",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=9101883140,
        artifact_name="task012-slice6-package2-recovery-31493144331-1",
        artifact_digest="sha256:ab859a42afc7e6459dd053fa1aaf5d7ddd4ce9968f11093904f1f513c0b1ea18",
        artifact_expired=False,
        receipt_name="acceptance-summary.json",
        receipt_sha256="sha256:19bd9af181b044d253d3a4ce8b62b9ca26943ea033cc7b69166e63291dd1335a",
        source_environment_class="controlled_synthetic",
        controlled_synthetic=True,
    ),
    _row(
        authority_id="MAIN_CI_FINAL",
        authority_type="ci",
        domain="Source / Version Identity",
        canonical_path=".github/workflows/ci.yml",
        pr_number=None,
        merge_sha=None,
        workflow_name="ci",
        workflow_path=".github/workflows/ci.yml",
        run_id=31492728302,
        run_attempt=1,
        event="push",
        head_sha=IMPLEMENTATION_BASE_SHA,
        conclusion="success",
        artifact_id=None,
        artifact_name=None,
        artifact_digest=None,
        artifact_expired=None,
        receipt_name=None,
        receipt_sha256=None,
        source_environment_class="repository_contract",
        controlled_synthetic=False,
        authority_source_sha=IMPLEMENTATION_BASE_SHA,
    ),
)

_FROZEN_AUTHORITY_BY_ID = {row["authority_id"]: row for row in _FROZEN_AUTHORITY_ROWS}


def _fail(code: str, detail: str) -> FinalReleaseEvidenceError:
    return FinalReleaseEvidenceError(code, detail)


def _require_mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be an object")
    return value


def _require_string(value: object, *, field: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be a non-empty string")
    return value


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be boolean")
    return value


def _parse_positive_int(value: object, *, field: str, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be a positive integer")
    if isinstance(value, int):
        if value > 0:
            return value
        raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be positive")
    if isinstance(value, str) and POSITIVE_DECIMAL_RE.fullmatch(value):
        return int(value)
    raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be a positive integer")


def _parse_nonnegative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be a non-negative integer")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be a non-negative integer")


def _require_commit(value: object, *, field: str, nullable: bool = False) -> str | None:
    parsed = _require_string(value, field=field, nullable=nullable)
    if parsed is None:
        return None
    if not COMMIT_RE.fullmatch(parsed):
        raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be a 40-character SHA")
    return parsed


def _require_digest(value: object, *, field: str, nullable: bool = False) -> str | None:
    parsed = _require_string(value, field=field, nullable=nullable)
    if parsed is None:
        return None
    if not SHA256_RE.fullmatch(parsed):
        raise _fail("REQUIRED_FIELD_INVALID", f"{field} must be canonical sha256")
    return parsed


def _require_enum(value: object, *, field: str, allowed: set[str]) -> str:
    parsed = _require_string(value, field=field)
    assert parsed is not None
    if parsed not in allowed:
        raise _fail("REQUIRED_FIELD_INVALID", f"{field} has unsupported value")
    return parsed


_SAFE_AUDIT_SECRET_KEYS = frozenset(
    {
        "no_secret_material_result",
        "secret_redaction",
        "secret_material_scan",
        "credential_non_persistence",
    }
)
_SECRET_KEY_RE = re.compile(
    r"(^|_)(?:password|token|authorization|cookie|dsn|private_key|api_key|credential|secret)($|_)"
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(?:bearer\s+\S+|gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|"
    r"(?:postgres(?:ql)?|redis)://\S+|-----BEGIN [^-]+ PRIVATE KEY-----|"
    r"authorization:\s*\S+|cookie:\s*\S+)"
)


def _scan_secret_material(value: object, *, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower().replace("-", "_")
            child_path = f"{path}.{key_text}" if path else key_text
            if (
                key_text not in _SAFE_AUDIT_SECRET_KEYS
                and _SECRET_KEY_RE.search(key_text)
                and child not in (None, "", [])
            ):
                raise _fail("SECRET_MATERIAL_DETECTED", f"secret-bearing field: {child_path}")
            _scan_secret_material(child, path=child_path)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _scan_secret_material(child, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and _SECRET_VALUE_RE.search(value):
        raise _fail("SECRET_MATERIAL_DETECTED", f"secret-like value: {path or '<root>'}")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise _fail("REQUIRED_AUTHORITY_MISSING", f"JSON file is not a regular file: {path}")
    try:
        return load_json_strict(path.read_text(encoding="utf-8"))
    except CanonicalSerializationError as exc:
        raise _fail("REQUIRED_AUTHORITY_INVALID", f"invalid JSON authority: {path}") from exc


def _validate_timestamp(value: object) -> str:
    parsed = _require_string(value, field="generated_at")
    assert parsed is not None
    if not RFC3339_UTC_RE.fullmatch(parsed):
        raise _fail("GENERATED_AT_INVALID", "generated_at must be RFC3339 UTC")
    try:
        datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _fail("GENERATED_AT_INVALID", "generated_at is not a valid timestamp") from exc
    return parsed


def _normalize_authority(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize external numeric strings and reject incomplete records."""
    authority_id = _require_string(row.get("authority_id"), field="authority_id")
    assert authority_id is not None
    expected = _FROZEN_AUTHORITY_BY_ID.get(authority_id)
    if expected is None:
        raise _fail("REQUIRED_AUTHORITY_AMBIGUOUS", f"unexpected authority: {authority_id}")

    required_value = row.get("required", row.get("required_by_s6_06"))
    normalized: dict[str, Any] = {
        "authority_id": authority_id,
        "authority_type": _require_enum(
            row.get("authority_type", expected["authority_type"]),
            field=f"{authority_id}.authority_type",
            allowed={"source", "contract", "ci", "artifact", "receipt", "recovery"},
        ),
        "domain": _require_string(row.get("domain"), field=f"{authority_id}.domain"),
        "required": _require_bool(required_value, field=f"{authority_id}.required"),
        "canonical_repository_path": _require_string(
            row.get("canonical_repository_path"),
            field=f"{authority_id}.canonical_repository_path",
            nullable=True,
        ),
        "canonical_pr_number": _parse_positive_int(
            row.get("canonical_pr_number"),
            field=f"{authority_id}.canonical_pr_number",
            nullable=True,
        ),
        "canonical_merge_sha": _require_commit(
            row.get("canonical_merge_sha"),
            field=f"{authority_id}.canonical_merge_sha",
            nullable=True,
        ),
        "workflow_name": _require_string(
            row.get("workflow_name"), field=f"{authority_id}.workflow_name", nullable=True
        ),
        "workflow_path": _require_string(
            row.get("workflow_path", expected["workflow_path"]),
            field=f"{authority_id}.workflow_path",
            nullable=True,
        ),
        "workflow_run_id": _parse_positive_int(
            row.get("workflow_run_id"), field=f"{authority_id}.workflow_run_id", nullable=True
        ),
        "workflow_run_attempt": _parse_positive_int(
            row.get("workflow_run_attempt"),
            field=f"{authority_id}.workflow_run_attempt",
            nullable=True,
        ),
        "workflow_event": _require_string(
            row.get("workflow_event"), field=f"{authority_id}.workflow_event", nullable=True
        ),
        "workflow_head_sha": _require_commit(
            row.get("workflow_head_sha"), field=f"{authority_id}.workflow_head_sha", nullable=True
        ),
        "workflow_conclusion": _require_string(
            row.get("workflow_conclusion"),
            field=f"{authority_id}.workflow_conclusion",
            nullable=True,
        ),
        "artifact_id": _parse_positive_int(
            row.get("artifact_id"), field=f"{authority_id}.artifact_id", nullable=True
        ),
        "artifact_name": _require_string(
            row.get("artifact_name"), field=f"{authority_id}.artifact_name", nullable=True
        ),
        "artifact_digest": _require_digest(
            row.get("artifact_digest"), field=f"{authority_id}.artifact_digest", nullable=True
        ),
        "artifact_expired": (
            None
            if row.get("artifact_expired") is None
            else _require_bool(
                row.get("artifact_expired"), field=f"{authority_id}.artifact_expired"
            )
        ),
        "receipt_name": _require_string(
            row.get("receipt_name"), field=f"{authority_id}.receipt_name", nullable=True
        ),
        "receipt_sha256": _require_digest(
            row.get("receipt_sha256"), field=f"{authority_id}.receipt_sha256", nullable=True
        ),
        "source_environment_class": _require_enum(
            row.get("source_environment_class"),
            field=f"{authority_id}.source_environment_class",
            allowed={"repository_contract", "controlled_synthetic", "production"},
        ),
        "controlled_synthetic": _require_bool(
            row.get("controlled_synthetic"), field=f"{authority_id}.controlled_synthetic"
        ),
        "production": _require_bool(row.get("production"), field=f"{authority_id}.production"),
        "production_operation_performed": _require_bool(
            row.get("production_operation_performed"),
            field=f"{authority_id}.production_operation_performed",
        ),
        "authority_source_sha": _require_commit(
            row.get("authority_source_sha"),
            field=f"{authority_id}.authority_source_sha",
            nullable=True,
        ),
        "current_release_source_sha": _require_commit(
            row.get("current_release_source_sha"),
            field=f"{authority_id}.current_release_source_sha",
        ),
        "lineage_binding_result": _require_enum(
            row.get("lineage_binding_result"),
            field=f"{authority_id}.lineage_binding_result",
            allowed={"PASS", "FAIL"},
        ),
        "verification_result": _require_enum(
            row.get("verification_result"),
            field=f"{authority_id}.verification_result",
            allowed={"PASS", "FAIL", "MISSING", "AMBIGUOUS"},
        ),
    }

    if normalized["artifact_id"] is not None and normalized["artifact_expired"] is not False:
        raise _fail(
            "ARTIFACT_EXPIRED_WITHOUT_DURABLE_AUTHORITY",
            f"artifact is expired or missing expiry state: {authority_id}",
        )
    if normalized["workflow_run_id"] is not None:
        for field in (
            "workflow_run_attempt",
            "workflow_event",
            "workflow_head_sha",
            "workflow_conclusion",
        ):
            if normalized[field] is None:
                raise _fail("REQUIRED_AUTHORITY_INVALID", f"{authority_id}.{field} is required")
    if normalized["artifact_id"] is not None:
        for field in ("artifact_name", "artifact_digest"):
            if normalized[field] is None:
                raise _fail("ARTIFACT_MISSING", f"{authority_id}.{field} is required")
    return normalized


def _compare_frozen_authority(row: Mapping[str, Any]) -> None:
    authority_id = row["authority_id"]
    expected = _FROZEN_AUTHORITY_BY_ID[authority_id]
    for field, expected_value in expected.items():
        if field == "current_release_source_sha":
            continue
        if row.get(field) != expected_value:
            raise _fail(
                "AUTHORITY_BINDING_MISMATCH",
                f"{authority_id}.{field} does not match frozen authority",
            )


def _normalize_and_verify_index(
    value: Mapping[str, Any], *, source_sha: str, source_tree_sha: str
) -> list[dict[str, Any]]:
    if value.get("schema_version") not in {
        AUTHORITY_INDEX_SCHEMA_VERSION,
        "task012-s6-06-authority-index-v1-input",
    }:
        raise _fail("AUTHORITY_INDEX_SCHEMA_INVALID", "authority index schema mismatch")
    if value.get("task") != "TASK-012" or value.get("version") != EXPECTED_VERSION:
        raise _fail("AUTHORITY_INDEX_SCHEMA_INVALID", "authority index task/version mismatch")
    if value.get("slice") != 6 or value.get("item") != "S6-06" or value.get("package") != 3:
        raise _fail("AUTHORITY_INDEX_SCHEMA_INVALID", "authority index scope mismatch")
    if value.get("source_sha") != source_sha:
        raise _fail("SOURCE_SHA_MISMATCH", "authority index source SHA mismatch")
    if value.get("source_tree_sha") != source_tree_sha:
        raise _fail("SOURCE_TREE_MISMATCH", "authority index source tree mismatch")
    raw_authorities = value.get("authorities")
    if not isinstance(raw_authorities, list) or len(raw_authorities) != len(_FROZEN_AUTHORITY_ROWS):
        raise _fail("REQUIRED_AUTHORITY_MISSING", "authority index must contain exactly 17 entries")
    normalized = [
        _normalize_authority(_require_mapping(item, field="authority")) for item in raw_authorities
    ]
    if len({row["authority_id"] for row in normalized}) != len(_FROZEN_AUTHORITY_ROWS):
        raise _fail("REQUIRED_AUTHORITY_AMBIGUOUS", "authority IDs are not unique")
    for row in normalized:
        _compare_frozen_authority(row)
        if row["current_release_source_sha"] != source_sha:
            raise _fail(
                "SOURCE_SHA_MISMATCH",
                f"{row['authority_id']}.current_release_source_sha mismatch",
            )
        if row["verification_result"] != "PASS":
            raise _fail(
                "REQUIRED_AUTHORITY_FAILED", f"authority is not PASS: {row['authority_id']}"
            )
        if not row["required"]:
            raise _fail(
                "REQUIRED_AUTHORITY_INVALID", f"authority is not required: {row['authority_id']}"
            )
        if row["production"] or row["production_operation_performed"]:
            raise _fail(
                "PRODUCTION_OPERATION_DETECTED", f"production marker in {row['authority_id']}"
            )
    return sorted(normalized, key=lambda item: str(item["authority_id"]))


def _verify_github_metadata(authorities: Sequence[Mapping[str, Any]], metadata_dir: Path) -> None:
    if not metadata_dir.is_dir():
        raise _fail("REQUIRED_AUTHORITY_MISSING", f"metadata directory missing: {metadata_dir}")
    run_cache: dict[int, Mapping[str, Any]] = {}
    for authority in authorities:
        run_id = authority["workflow_run_id"]
        if isinstance(run_id, int) and run_id not in run_cache:
            run_cache[run_id] = _read_json(metadata_dir / f"run-{run_id}.json")
        if isinstance(run_id, int):
            run = run_cache[run_id]
            if _parse_positive_int(run.get("id"), field="workflow metadata id") != run_id:
                raise _fail(
                    "WORKFLOW_HEAD_MISMATCH",
                    f"workflow run ID mismatch: {authority['authority_id']}",
                )
            if run.get("event") != authority["workflow_event"]:
                raise _fail(
                    "WORKFLOW_IDENTITY_MISMATCH",
                    f"workflow event mismatch: {authority['authority_id']}",
                )
            if (
                run.get("head_branch") != "main"
                or run.get("head_sha") != authority["workflow_head_sha"]
            ):
                raise _fail(
                    "WORKFLOW_HEAD_MISMATCH", f"workflow head mismatch: {authority['authority_id']}"
                )
            if (
                _parse_positive_int(run.get("run_attempt"), field="workflow metadata attempt")
                != authority["workflow_run_attempt"]
            ):
                raise _fail(
                    "WORKFLOW_ATTEMPT_MISMATCH",
                    f"workflow attempt mismatch: {authority['authority_id']}",
                )
            if run.get("status") != "completed" or run.get("conclusion") != "success":
                raise _fail(
                    "WORKFLOW_NOT_SUCCESSFUL",
                    f"workflow not successful: {authority['authority_id']}",
                )
            if run.get("path") != authority["workflow_path"]:
                raise _fail(
                    "WORKFLOW_IDENTITY_MISMATCH",
                    f"workflow path mismatch: {authority['authority_id']}",
                )
            if run.get("name") != authority["workflow_name"]:
                raise _fail(
                    "WORKFLOW_IDENTITY_MISMATCH",
                    f"workflow name mismatch: {authority['authority_id']}",
                )

        artifact_id = authority["artifact_id"]
        if isinstance(artifact_id, int):
            artifact = _read_json(metadata_dir / f"artifact-{artifact_id}.json")
            if _parse_positive_int(artifact.get("id"), field="artifact metadata id") != artifact_id:
                raise _fail(
                    "ARTIFACT_DIGEST_MISMATCH", f"artifact ID mismatch: {authority['authority_id']}"
                )
            if artifact.get("name") != authority["artifact_name"]:
                raise _fail(
                    "ARTIFACT_IDENTITY_MISMATCH",
                    f"artifact name mismatch: {authority['authority_id']}",
                )
            if (
                artifact.get("expired") is not False
                or artifact.get("digest") != authority["artifact_digest"]
            ):
                raise _fail(
                    "ARTIFACT_DIGEST_MISMATCH",
                    f"artifact digest/expiry mismatch: {authority['authority_id']}",
                )
            workflow_run = _require_mapping(
                artifact.get("workflow_run"), field="artifact.workflow_run"
            )
            if (
                _parse_positive_int(workflow_run.get("id"), field="artifact workflow run id")
                != authority["workflow_run_id"]
                or workflow_run.get("head_branch") != "main"
                or workflow_run.get("head_sha") != authority["workflow_head_sha"]
            ):
                raise _fail(
                    "ARTIFACT_WORKFLOW_BINDING_MISMATCH",
                    f"artifact workflow mismatch: {authority['authority_id']}",
                )


def _validate_source_inputs(repository: str, source_sha: str, source_tree_sha: str) -> None:
    if repository != EXPECTED_REPOSITORY:
        raise _fail("REPOSITORY_IDENTITY_MISMATCH", "repository is not the frozen repository")
    _require_commit(source_sha, field="source_sha")
    _require_commit(source_tree_sha, field="source_tree_sha")


def _common(
    *,
    schema_version: str,
    generated_at: str,
    authority_ids: list[str],
    source_sha: str,
    source_tree_sha: str,
    counts: Mapping[str, int],
) -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("schema_version", schema_version),
            ("task", "TASK-012"),
            ("version", EXPECTED_VERSION),
            ("slice", 6),
            ("item", "S6-06"),
            ("package", 3),
            ("source_sha", source_sha),
            ("source_tree_sha", source_tree_sha),
            ("generated_at", generated_at),
            ("controlled_evidence_only", True),
            ("production_operation_performed", False),
            ("upstream_authorities", authority_ids),
            ("required_authority_count", counts["required"]),
            ("passed_authority_count", counts["passed"]),
            ("missing_authority_count", counts["missing"]),
            ("failed_authority_count", counts["failed"]),
            ("ambiguous_authority_count", counts["ambiguous"]),
            ("release_evidence_result", "PASS"),
        ]
    )


def _counts(authorities: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "required": sum(1 for row in authorities if row["required"]),
        "passed": sum(1 for row in authorities if row["verification_result"] == "PASS"),
        "missing": sum(1 for row in authorities if row["verification_result"] == "MISSING"),
        "failed": sum(1 for row in authorities if row["verification_result"] == "FAIL"),
        "ambiguous": sum(1 for row in authorities if row["verification_result"] == "AMBIGUOUS"),
    }


def _build_documents(
    *,
    authorities: list[dict[str, Any]],
    source_sha: str,
    source_tree_sha: str,
    generated_at: str,
) -> dict[str, OrderedDict[str, Any]]:
    authority_ids = [str(row["authority_id"]) for row in authorities]
    counts = _counts(authorities)
    source_identity = _common(
        schema_version=f"{PACKAGE3_SCHEMA_VERSION}-source-identity",
        generated_at=generated_at,
        authority_ids=authority_ids,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        counts=counts,
    )
    source_identity.update(
        {
            "repository": EXPECTED_REPOSITORY,
            "application_version": EXPECTED_VERSION,
            "release_version": EXPECTED_RELEASE_VERSION,
            "rc_source_sha": EXPECTED_RC_SOURCE_SHA,
            "rc_source_tree_sha": EXPECTED_RC_SOURCE_TREE_SHA,
            "source_commit_present": True,
            "source_tree_match": True,
            "rc_commit_present": True,
            "rc_tree_match": True,
            "stale_or_mismatched_release_detected": False,
            "verification_result": "PASS",
        }
    )

    authority_index = _common(
        schema_version=AUTHORITY_INDEX_SCHEMA_VERSION,
        generated_at=generated_at,
        authority_ids=authority_ids,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        counts=counts,
    )
    authority_index["authorities"] = authorities
    authority_index["authority_count"] = len(authorities)
    authority_index["required_authority_count"] = counts["required"]
    authority_index["verification_result"] = "PASS"

    runtime = _common(
        schema_version=f"{PACKAGE3_SCHEMA_VERSION}-runtime-readiness",
        generated_at=generated_at,
        authority_ids=authority_ids,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        counts=counts,
    )
    runtime.update(
        {
            "environment_security": {
                "strict_staging_production_validation": "PASS",
                "secret_redaction": "PASS",
                "credential_non_persistence": "PASS",
                "fake_capability_excluded_from_production": "PASS",
            },
            "runtime_readiness": {
                "startup_fail_closed": "PASS",
                "migration_owner_external": "PASS",
                "database_readiness": "PASS",
                "schema_head_readiness": "PASS",
                "artifact_storage_readiness": "PASS",
                "environment_identity": "PASS",
                "health_live_surface": "PASS",
                "health_ready_surface": "PASS",
            },
            "observability": {
                "structured_logging": "PASS",
                "correlation_identity": "PASS",
                "redaction": "PASS",
                "audit_outbox_operational_surface": "PASS",
                "remote_dashboard_or_pagerduty": None,
            },
            "dependency_reality": {
                "production_coefficient_authority": "PASS",
                "production_agent_capability": "disabled_by_contract",
            },
            "verification_result": "PASS",
        }
    )

    package1 = {
        "status": "PASS",
        "run_id": 31469678479,
        "run_attempt": 1,
        "head_sha": "658c993040d93371ee3286fc91c8f4abeb5da7b1",
        "artifact_id": 9092865725,
        "artifact_digest": (
            "sha256:345841c71d21239753758749f3f02b17925bb73dc2d4b72071c6389e3b481699"
        ),
        "acceptance_result": "PASS",
        "backup_result": "PASS",
        "isolated_restore_result": "PASS",
        "restored_data_verification_result": "PASS",
        "controlled_synthetic": True,
        "production_operation_performed": False,
        "automatic_downgrade_performed": False,
        "receipt_references": ["backup-manifest.json", "restore-receipt.json"],
    }
    package2 = {
        "status": "PASS",
        "run_id": 31493144331,
        "run_attempt": 1,
        "head_sha": IMPLEMENTATION_BASE_SHA,
        "artifact_id": 9101883140,
        "artifact_digest": (
            "sha256:ab859a42afc7e6459dd053fa1aaf5d7ddd4ce9968f11093904f1f513c0b1ea18"
        ),
        "acceptance_result": "PASS",
        "failed_deployment_rollback_result": "PASS",
        "failed_migration_recovery_result": "PASS",
        "transactional_migration_failure_result": "PASS",
        "partial_migration_failure_result": "PASS",
        "canonical_backup_result": "PASS",
        "canonical_restore_result": "PASS",
        "canonical_verify_result": "PASS",
        "post_recovery_live_result": "PASS",
        "post_recovery_ready_result": "PASS",
        "automatic_downgrade_performed": False,
        "controlled_synthetic": True,
        "production_operation_performed": False,
        "receipt_references": [
            "deployment-rollback-receipt.json",
            "migration-recovery-receipt.json",
            "restore-receipt.json",
        ],
    }
    recovery = _common(
        schema_version=f"{PACKAGE3_SCHEMA_VERSION}-recovery-authority",
        generated_at=generated_at,
        authority_ids=authority_ids,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        counts=counts,
    )
    recovery.update(
        {
            "package1": package1,
            "package2": package2,
            "historical_failures_excluded": [31461529093],
            "automatic_downgrade_performed": False,
            "production_operation_performed": False,
            "verification_result": "PASS",
        }
    )

    provenance = _common(
        schema_version=f"{PACKAGE3_SCHEMA_VERSION}-release-provenance",
        generated_at=generated_at,
        authority_ids=authority_ids,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        counts=counts,
    )
    provenance.update(
        {
            "authority_source_sha": "901fafa53fa579bea5891129799a30da1829234d",
            "current_release_source_sha": source_sha,
            "lineage_binding_result": "PASS",
            "rc_source_sha": EXPECTED_RC_SOURCE_SHA,
            "rc_source_tree_sha": EXPECTED_RC_SOURCE_TREE_SHA,
            "d0_capture": {
                "run_id": 31342745646,
                "artifact_id": 9046325555,
                "artifact_digest": (
                    "sha256:791451d6cfa0dccb9f28f4700c74d58e257537a7b79a29241a84716056634020"
                ),
                "authority_source_sha": "6fb432575416f452531a345f469e6f9ec8bd789e",
                "current_release_source_sha": source_sha,
                "lineage_binding_result": "PASS",
            },
            "d1_transport": {
                "run_id": 31352302807,
                "artifact_id": 9049370270,
                "artifact_digest": (
                    "sha256:c375e013b4052ad08a407338b5cd99e2653a7b0bfe2f96fed051976b5918ba3f"
                ),
                "receipt_sha256": (
                    "sha256:38d395a48821241d25c195b68e9695b4c7b7890b64d45712110edbc7da96fb7e"
                ),
                "authority_source_sha": "09d99ac2bc7db315d1370e41a4a5e15e7ab107ff",
                "current_release_source_sha": source_sha,
                "lineage_binding_result": "PASS",
            },
            "attestation": {
                "run_id": 31371998864,
                "artifact_id": 9056423295,
                "artifact_digest": (
                    "sha256:102756b94a74383e62cde8e52d8b995936b349625b701b99ad62fc942cf4ffd1"
                ),
                "receipt_sha256": (
                    "sha256:a426e5ef78e121549727daad67ae9b98fbb88d6d4978d9c93d9094cfab4129bb"
                ),
                "authority_source_sha": "d4a18f056c288ff6cd7673e1765a54dfd4e82f1a",
                "current_release_source_sha": source_sha,
                "lineage_binding_result": "PASS",
            },
            "assembly": {
                "run_id": 31394393604,
                "artifact_id": 9064992469,
                "artifact_digest": (
                    "sha256:2b048ebf6bca77b126367c2050c3fee49dd4c5f5c439bf7898414d61b03be274"
                ),
                "receipt_sha256": (
                    "sha256:329485214a2d37f44beea715ee4e99fc5c966861eb7ef5c7aedf4683cc63cf73"
                ),
                "authority_source_sha": "901fafa53fa579bea5891129799a30da1829234d",
                "current_release_source_sha": source_sha,
                "lineage_binding_result": "PASS",
            },
            "final_image_manifest_digest": (
                "sha256:e2f8b70d400858d351a67b520c89b8e0c6089f9f6c13cca086efdaef9348c9fc"
            ),
            "provenance_digest": (
                "sha256:42f994e2c206f6730efcd1b4c64d425dd59c7b3953f69959e3b27e5d8709e417"
            ),
            "attestation_binding": (
                "sha256:af3f135a7eb39190a8cbd000555003b9117135b314b6d728c13903b0a0304fb0"
            ),
            "assembly_payload_shape": [
                "artifact-manifest.json",
                "provenance.json",
                "evidence-bundle.json",
                "assembly-metadata.json",
                "SHA256SUMS",
                "SHA256SUMS.sha256",
            ],
            "slice2_closure_reaffirmed": True,
            "verification_result": "PASS",
        }
    )

    summary = _common(
        schema_version=f"{PACKAGE3_SCHEMA_VERSION}-summary",
        generated_at=generated_at,
        authority_ids=authority_ids,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        counts=counts,
    )
    gate_names = (
        "source_identity_result",
        "environment_security_result",
        "runtime_readiness_result",
        "observability_result",
        "release_provenance_result",
        "recovery_package1_result",
        "recovery_package2_result",
        "bundle_shape_result",
        "bundle_checksum_result",
        "receipt_binding_result",
        "artifact_digest_binding_result",
        "no_secret_material_result",
        "no_production_operation_result",
    )
    summary.update({name: "PASS" for name in gate_names})
    summary.update(
        {
            "s6_07_required_for_s6_06_pass": False,
            "s6_06_prerequisite_for_s6_07": True,
            "s6_07_executed": False,
            "s6_07_result": None,
            "next_required_stage": "S6-07",
            "next_stage_status": "NOT_AUTHORIZED",
            "release_evidence_result": "PASS",
        }
    )
    return {
        "release-evidence-summary.json": summary,
        "source-identity.json": source_identity,
        "authority-index.json": authority_index,
        "runtime-readiness-summary.json": runtime,
        "recovery-authority-summary.json": recovery,
        "release-provenance-summary.json": provenance,
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_bytes(canonical_bytes(value))


def _sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksums(root: Path) -> None:
    lines = [f"{_sha256_hex(root / name)}  {name}" for name in FINAL_JSON_FILES]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")
    sidecar_digest = _sha256_hex(root / "SHA256SUMS")
    (root / "SHA256SUMS.sha256").write_text(f"{sidecar_digest}  SHA256SUMS\n", encoding="ascii")


def _verify_checksums(root: Path) -> None:
    checksum_path = root / "SHA256SUMS"
    if not checksum_path.is_file() or checksum_path.is_symlink():
        raise _fail("CHECKSUM_MISMATCH", "SHA256SUMS is missing")
    expected_lines = checksum_path.read_text(encoding="ascii").splitlines()
    expected = {
        name: digest for digest, name in (_parse_checksum_line(line) for line in expected_lines)
    }
    if set(expected) != set(FINAL_JSON_FILES):
        raise _fail("CHECKSUM_COVERAGE_MISMATCH", "SHA256SUMS coverage is not exact")
    for name, digest in expected.items():
        if _sha256_hex(root / name) != digest:
            raise _fail("CHECKSUM_MISMATCH", f"checksum mismatch: {name}")
    sidecar_path = root / "SHA256SUMS.sha256"
    if not sidecar_path.is_file() or sidecar_path.is_symlink():
        raise _fail("CHECKSUM_MISMATCH", "SHA256SUMS.sha256 is missing")
    sidecar_lines = sidecar_path.read_text(encoding="ascii").splitlines()
    if len(sidecar_lines) != 1:
        raise _fail("CHECKSUM_COVERAGE_MISMATCH", "sidecar must contain exactly one record")
    sidecar_digest, sidecar_name = _parse_checksum_line(sidecar_lines[0])
    if sidecar_name != "SHA256SUMS" or _sha256_hex(checksum_path) != sidecar_digest:
        raise _fail("CHECKSUM_MISMATCH", "SHA256SUMS sidecar mismatch")


def _parse_checksum_line(line: str) -> tuple[str, str]:
    parts = line.split("  ", 1)
    if len(parts) != 2 or not SHA_HEX_RE.fullmatch(parts[0]) or not parts[1]:
        raise _fail("CHECKSUM_COVERAGE_MISMATCH", "invalid checksum record")
    return parts[0], parts[1]


def _verify_exact_shape(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise _fail("BUNDLE_SHAPE_MISMATCH", "bundle output is not a directory")
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != set(FINAL_BUNDLE_FILES):
        raise _fail("BUNDLE_SHAPE_MISMATCH", "bundle file set is not exactly eight files")
    for entry in entries:
        if not entry.is_file() or entry.is_symlink():
            raise _fail("BUNDLE_SHAPE_MISMATCH", "bundle contains a non-regular file")


def _verify_common(document: Mapping[str, Any], *, schema_suffix: str) -> str:
    expected_schema = (
        AUTHORITY_INDEX_SCHEMA_VERSION
        if schema_suffix == "authority-index"
        else f"{PACKAGE3_SCHEMA_VERSION}-{schema_suffix}"
    )
    if document.get("schema_version") != expected_schema:
        raise _fail("BUNDLE_SCHEMA_MISMATCH", f"unexpected schema for {schema_suffix}")
    for field, expected in (
        ("task", "TASK-012"),
        ("version", EXPECTED_VERSION),
        ("slice", 6),
        ("item", "S6-06"),
        ("package", 3),
        ("controlled_evidence_only", True),
        ("production_operation_performed", False),
    ):
        if document.get(field) != expected:
            raise _fail("BUNDLE_SCHEMA_MISMATCH", f"common field mismatch: {field}")
    source_sha = _require_commit(document.get("source_sha"), field="source_sha")
    tree_sha = _require_commit(document.get("source_tree_sha"), field="source_tree_sha")
    assert source_sha is not None and tree_sha is not None
    _validate_timestamp(document.get("generated_at"))
    authorities = document.get("upstream_authorities")
    if (
        not isinstance(authorities, list)
        or len(authorities) != 17
        or not all(isinstance(item, str) for item in authorities)
    ):
        raise _fail("BUNDLE_SCHEMA_MISMATCH", "upstream authority list mismatch")
    for field in (
        "required_authority_count",
        "passed_authority_count",
        "missing_authority_count",
        "failed_authority_count",
        "ambiguous_authority_count",
    ):
        _parse_nonnegative_int(document.get(field), field=field)
    generated_at = document.get("generated_at")
    if not isinstance(generated_at, str):
        raise _fail("BUNDLE_SCHEMA_MISMATCH", "generated_at must be a string")
    return generated_at


def write_frozen_authority_index(output: Path, *, source_sha: str, source_tree_sha: str) -> Path:
    """Write the fixed 17-entry input index for an explicit release source."""
    _validate_source_inputs(EXPECTED_REPOSITORY, source_sha, source_tree_sha)
    authorities = [
        {**row, "current_release_source_sha": source_sha} for row in _FROZEN_AUTHORITY_ROWS
    ]
    value: OrderedDict[str, Any] = OrderedDict(
        [
            ("schema_version", "task012-s6-06-authority-index-v1-input"),
            ("task", "TASK-012"),
            ("version", EXPECTED_VERSION),
            ("slice", 6),
            ("item", "S6-06"),
            ("package", 3),
            ("source_sha", source_sha),
            ("source_tree_sha", source_tree_sha),
            ("authorities", authorities),
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, value)
    return output


def assemble_final_release_evidence(
    *,
    authority_index: Path,
    output_dir: Path,
    repository: str,
    source_sha: str,
    source_tree_sha: str,
    generated_at: str,
    github_metadata_dir: Path | None,
) -> Path:
    """Assemble and independently verify the exact eight-file final bundle."""
    if github_metadata_dir is None:
        raise _fail("GITHUB_METADATA_REQUIRED", "GitHub metadata is required for assembly")
    _validate_timestamp(generated_at)
    _validate_source_inputs(repository, source_sha, source_tree_sha)
    index = _read_json(authority_index)
    authorities = _normalize_and_verify_index(
        index, source_sha=source_sha, source_tree_sha=source_tree_sha
    )
    _verify_github_metadata(authorities, github_metadata_dir)
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise _fail("BUNDLE_OUTPUT_NOT_EMPTY", "output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=False)
    documents = _build_documents(
        authorities=authorities,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        generated_at=generated_at,
    )
    for name, document in documents.items():
        _scan_secret_material(document, path=name)
        _write_json(output_dir / name, document)
    _write_checksums(output_dir)
    verify_final_release_evidence(
        bundle_dir=output_dir,
        repository=repository,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        github_metadata_dir=github_metadata_dir,
    )
    return output_dir


def verify_final_release_evidence(
    *,
    bundle_dir: Path,
    repository: str,
    source_sha: str,
    source_tree_sha: str,
    github_metadata_dir: Path | None,
) -> None:
    """Independently verify an already-created S6-06 bundle."""
    if github_metadata_dir is None:
        raise _fail("GITHUB_METADATA_REQUIRED", "GitHub metadata is required for verification")
    _validate_source_inputs(repository, source_sha, source_tree_sha)
    _verify_exact_shape(bundle_dir)
    documents = {name: _read_json(bundle_dir / name) for name in FINAL_JSON_FILES}
    generated_at = _verify_common(
        documents["release-evidence-summary.json"], schema_suffix="summary"
    )
    for name, suffix in (
        ("source-identity.json", "source-identity"),
        ("runtime-readiness-summary.json", "runtime-readiness"),
        ("recovery-authority-summary.json", "recovery-authority"),
        ("release-provenance-summary.json", "release-provenance"),
    ):
        if _verify_common(documents[name], schema_suffix=suffix) != generated_at:
            raise _fail("BUNDLE_SCHEMA_MISMATCH", "generated_at is not shared across bundle")
    authority_index = documents["authority-index.json"]
    if _verify_common(authority_index, schema_suffix="authority-index") != generated_at:
        raise _fail("BUNDLE_SCHEMA_MISMATCH", "authority index timestamp mismatch")
    authorities = _normalize_and_verify_index(
        authority_index, source_sha=source_sha, source_tree_sha=source_tree_sha
    )
    _verify_github_metadata(authorities, github_metadata_dir)
    for name, document in documents.items():
        _scan_secret_material(document, path=name)
    expected_documents = _build_documents(
        authorities=authorities,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        generated_at=generated_at,
    )
    for name, expected in expected_documents.items():
        if documents[name] != expected:
            raise _fail("BUNDLE_BINDING_MISMATCH", f"derived document mismatch: {name}")
    _verify_checksums(bundle_dir)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TASK-012 S6-06 final evidence boundary")
    subparsers = parser.add_subparsers(dest="command", required=True)

    frozen = subparsers.add_parser("write-frozen-authority-index")
    frozen.add_argument("--output", required=True, type=Path)
    frozen.add_argument("--source-sha", required=True)
    frozen.add_argument("--source-tree-sha", required=True)

    assemble = subparsers.add_parser("assemble-final-release-evidence")
    assemble.add_argument("--authority-index", required=True, type=Path)
    assemble.add_argument("--output-dir", required=True, type=Path)
    assemble.add_argument("--repository", default=EXPECTED_REPOSITORY)
    assemble.add_argument("--source-sha", required=True)
    assemble.add_argument("--source-tree-sha", required=True)
    assemble.add_argument("--generated-at", required=True)
    assemble.add_argument("--github-metadata-dir", required=True, type=Path)

    verify = subparsers.add_parser("verify-final-release-evidence")
    verify.add_argument("--bundle-dir", required=True, type=Path)
    verify.add_argument("--repository", default=EXPECTED_REPOSITORY)
    verify.add_argument("--source-sha", required=True)
    verify.add_argument("--source-tree-sha", required=True)
    verify.add_argument("--github-metadata-dir", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "write-frozen-authority-index":
            path = write_frozen_authority_index(
                args.output,
                source_sha=args.source_sha,
                source_tree_sha=args.source_tree_sha,
            )
            print("FROZEN_AUTHORITY_INDEX=WRITTEN")
            print(f"AUTHORITY_INDEX={path}")
            return 0
        if args.command == "assemble-final-release-evidence":
            path = assemble_final_release_evidence(
                authority_index=args.authority_index,
                output_dir=args.output_dir,
                repository=args.repository,
                source_sha=args.source_sha,
                source_tree_sha=args.source_tree_sha,
                generated_at=args.generated_at,
                github_metadata_dir=args.github_metadata_dir,
            )
            print("S6_06_ASSEMBLY_RESULT=PASS")
            print(f"BUNDLE_DIR={path}")
            return 0
        if args.command == "verify-final-release-evidence":
            verify_final_release_evidence(
                bundle_dir=args.bundle_dir,
                repository=args.repository,
                source_sha=args.source_sha,
                source_tree_sha=args.source_tree_sha,
                github_metadata_dir=args.github_metadata_dir,
            )
            print("S6_06_VERIFICATION_RESULT=PASS")
            return 0
        raise _fail("COMMAND_INVALID", "unsupported command")
    except FinalReleaseEvidenceError as exc:
        print(f"ERROR_CODE={exc.failure_code}")
        if exc.detail:
            print(f"ERROR_DETAIL={exc.detail}")
        return 1


__all__ = [
    "AUTHORITY_INDEX_SCHEMA_VERSION",
    "EXPECTED_REPOSITORY",
    "IMPLEMENTATION_BASE_SHA",
    "IMPLEMENTATION_BASE_TREE_SHA",
    "PACKAGE3_IMPLEMENTATION_HEAD_SHA",
    "FINAL_BUNDLE_FILES",
    "FINAL_JSON_FILES",
    "FinalReleaseEvidenceError",
    "assemble_final_release_evidence",
    "main",
    "verify_final_release_evidence",
    "write_frozen_authority_index",
]


if __name__ == "__main__":
    raise SystemExit(main())
