"""Fail-closed release failure classification and recovery receipts.

This module owns the decision boundary between an application-only rollback
and a migration recovery.  It deliberately does not start processes, call a
cloud provider, or mutate a database.  Package 2's controlled workflow and
operator tooling provide observations to these pure validators and reuse the
Package 1 backup/restore commands for data recovery.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from cold_storage.recovery.backup_bundle import RecoveryError

_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,255}$")
_SCHEMA_HEAD_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

PRE_FAILURE_STATE_FIELDS: tuple[str, ...] = (
    "schema_version",
    "previous_image_digest",
    "previous_build_commit_sha",
    "previous_build_version",
    "previous_deployment_id",
    "candidate_image_digest",
    "candidate_build_commit_sha",
    "candidate_build_version",
    "candidate_deployment_id",
    "database_environment_id",
    "artifact_environment_id",
    "pre_deployment_schema_head",
    "pre_deployment_database_inventory_digest",
    "pre_deployment_artifact_inventory_digest",
    "backup_id",
    "backup_manifest_digest",
)

DEPLOYMENT_ROLLBACK_RECEIPT_FIELDS: tuple[str, ...] = (
    "schema_version",
    "task",
    "version",
    "slice",
    "package",
    "controlled_synthetic",
    "database_environment_id",
    "artifact_environment_id",
    "backup_id",
    "backup_manifest_digest",
    "previous_image_digest",
    "failed_candidate_image_digest",
    "previous_build_commit_sha",
    "failed_candidate_build_commit_sha",
    "previous_build_version",
    "failed_candidate_build_version",
    "previous_deployment_id",
    "failed_candidate_deployment_id",
    "pre_failure_schema_head",
    "post_failure_schema_head",
    "pre_failure_database_inventory_digest",
    "post_failure_database_inventory_digest",
    "pre_failure_artifact_inventory_digest",
    "post_failure_artifact_inventory_digest",
    "failure_classification",
    "recovery_decision",
    "rollback_image_digest",
    "rollback_build_commit_sha",
    "rollback_build_version",
    "rollback_deployment_id",
    "post_rollback_live_status",
    "post_rollback_ready_status",
    "rollback_result",
)

MIGRATION_RECOVERY_RECEIPT_FIELDS: tuple[str, ...] = (
    "schema_version",
    "task",
    "version",
    "slice",
    "package",
    "controlled_synthetic",
    "backup_id",
    "backup_manifest_digest",
    "pre_migration_database_inventory_digest",
    "pre_migration_artifact_inventory_digest",
    "pre_migration_schema_head",
    "migration_attempt_result",
    "migration_failure_class",
    "post_failure_schema_head",
    "post_failure_database_inventory_digest",
    "post_failure_artifact_inventory_digest",
    "failure_state_classification",
    "automatic_downgrade_performed",
    "recovery_required",
    "source_environment_id",
    "restore_target_environment_id",
    "source_database_environment_id",
    "restore_target_database_environment_id",
    "source_artifact_environment_id",
    "restore_target_artifact_environment_id",
    "restore_backup_id",
    "restore_receipt_digest",
    "final_schema_head",
    "final_database_inventory_digest",
    "final_artifact_inventory_digest",
    "independent_restore_verification",
    "post_recovery_live_status",
    "post_recovery_ready_status",
    "readiness_verification",
    "migration_recovery_result",
)


class FailureState(StrEnum):
    """Closed classification of the observed post-failure state."""

    SCHEMA_AND_DATA_UNCHANGED = "SCHEMA_AND_DATA_UNCHANGED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    DATA_CHANGED = "DATA_CHANGED"
    SCHEMA_AND_DATA_CHANGED = "SCHEMA_AND_DATA_CHANGED"
    STATE_AMBIGUOUS = "STATE_AMBIGUOUS"


class RecoveryDecision(StrEnum):
    """Closed action decision exposed to operators and automation."""

    APP_ONLY_ROLLBACK_ALLOWED = "APP_ONLY_ROLLBACK_ALLOWED"
    MIGRATION_RECOVERY_REQUIRED = "MIGRATION_RECOVERY_REQUIRED"
    FAIL_CLOSED = "FAIL_CLOSED"


class FailureRecoveryError(RecoveryError):
    """Stable failure for malformed or unsafe Package 2 evidence."""


@dataclass(frozen=True)
class FailureAssessment:
    """The result of comparing pre-failure and post-failure observations."""

    failure_state: FailureState
    recovery_decision: RecoveryDecision
    app_only_rollback_allowed: bool
    migration_recovery_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "cold-storage-release-failure-classification-v1",
            "failure_state_classification": self.failure_state.value,
            "recovery_decision": self.recovery_decision.value,
            "app_only_rollback_allowed": self.app_only_rollback_allowed,
            "migration_recovery_required": self.migration_recovery_required,
        }


@dataclass(frozen=True)
class PreFailureState:
    """Validated immutable identities captured before a release attempt."""

    schema_version: str
    previous_image_digest: str
    previous_build_commit_sha: str
    previous_build_version: str
    previous_deployment_id: str
    candidate_image_digest: str
    candidate_build_commit_sha: str
    candidate_build_version: str
    candidate_deployment_id: str
    database_environment_id: str
    artifact_environment_id: str
    pre_deployment_schema_head: str
    pre_deployment_database_inventory_digest: str
    pre_deployment_artifact_inventory_digest: str
    backup_id: str
    backup_manifest_digest: str

    def as_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in PRE_FAILURE_STATE_FIELDS}


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def canonical_digest(value: object) -> str:
    """Return the digest used when binding a receipt to a JSON document."""

    return f"sha256:{hashlib.sha256(_canonical_json_bytes(value)).hexdigest()}"


def _reject_secret_or_path(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise FailureRecoveryError("FAILURE_RECOVERY_INPUT_INVALID", f"{field} is invalid")
    if (
        "://" in value
        or value.startswith(("/", "\\"))
        or "\\" in value
        or any(character.isspace() for character in value)
    ):
        raise FailureRecoveryError("FAILURE_RECOVERY_INPUT_INVALID", f"{field} is unsafe")
    if not _TOKEN_PATTERN.fullmatch(value):
        raise FailureRecoveryError("FAILURE_RECOVERY_INPUT_INVALID", f"{field} is malformed")
    return value


def _validate_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise FailureRecoveryError(
            "FAILURE_RECOVERY_INPUT_INVALID", f"{field} is not a SHA-256 digest"
        )
    return value


def _validate_commit(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _COMMIT_PATTERN.fullmatch(value) is None:
        raise FailureRecoveryError("FAILURE_RECOVERY_INPUT_INVALID", f"{field} is not a commit SHA")
    return value


def _validate_schema_head(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SCHEMA_HEAD_PATTERN.fullmatch(value) is None:
        raise FailureRecoveryError("FAILURE_RECOVERY_INPUT_INVALID", f"{field} is malformed")
    return value


def _validate_closed_mapping(
    value: Mapping[str, Any], fields: tuple[str, ...], *, code: str
) -> dict[str, Any]:
    if set(value) != set(fields):
        raise FailureRecoveryError(code, "receipt schema is not closed")
    for key, item in value.items():
        if "secret" in key.lower() or "password" in key.lower() or "token" in key.lower():
            raise FailureRecoveryError(code, "receipt contains secret material")
        if isinstance(item, str) and ("://" in item or item.startswith(("/", "\\"))):
            raise FailureRecoveryError(code, "receipt contains a path or URL")
    return dict(value)


def _optional_observation_digest(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) else None


def _optional_schema_head(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) and _SCHEMA_HEAD_PATTERN.fullmatch(value) else None


def classify_failure_state(
    *,
    pre_deployment_schema_head: object,
    post_failure_schema_head: object,
    pre_deployment_database_inventory_digest: object,
    post_failure_database_inventory_digest: object,
    pre_deployment_artifact_inventory_digest: object | None = None,
    post_failure_artifact_inventory_digest: object | None = None,
) -> FailureAssessment:
    """Classify failure state and fail closed for incomplete observations.

    The application-only path is allowed only when every supplied authority
    is present, well-formed, and equal. Missing, malformed, multi-head, or
    otherwise ambiguous observations require migration recovery.
    """

    pre_schema = _optional_schema_head(pre_deployment_schema_head)
    post_schema = _optional_schema_head(post_failure_schema_head)
    pre_database = _optional_observation_digest(pre_deployment_database_inventory_digest)
    post_database = _optional_observation_digest(post_failure_database_inventory_digest)
    pre_artifact = _optional_observation_digest(pre_deployment_artifact_inventory_digest)
    post_artifact = _optional_observation_digest(post_failure_artifact_inventory_digest)

    if (
        pre_schema is None
        or post_schema is None
        or pre_database is None
        or post_database is None
        or pre_artifact is None
        or post_artifact is None
    ):
        return FailureAssessment(
            FailureState.STATE_AMBIGUOUS,
            RecoveryDecision.MIGRATION_RECOVERY_REQUIRED,
            False,
            True,
        )

    schema_changed = pre_schema != post_schema
    data_changed = pre_database != post_database or (
        pre_artifact is not None and post_artifact is not None and pre_artifact != post_artifact
    )
    if not schema_changed and not data_changed:
        return FailureAssessment(
            FailureState.SCHEMA_AND_DATA_UNCHANGED,
            RecoveryDecision.APP_ONLY_ROLLBACK_ALLOWED,
            True,
            False,
        )
    if schema_changed and data_changed:
        state = FailureState.SCHEMA_AND_DATA_CHANGED
    elif schema_changed:
        state = FailureState.SCHEMA_CHANGED
    else:
        state = FailureState.DATA_CHANGED
    return FailureAssessment(state, RecoveryDecision.MIGRATION_RECOVERY_REQUIRED, False, True)


def validate_pre_failure_state(value: Mapping[str, Any]) -> PreFailureState:
    """Validate the closed pre-failure identity document."""

    payload = _validate_closed_mapping(
        value, PRE_FAILURE_STATE_FIELDS, code="PRE_FAILURE_STATE_INVALID"
    )
    if payload["schema_version"] != "cold-storage-release-failure-state-v1":
        raise FailureRecoveryError("PRE_FAILURE_STATE_INVALID", "unsupported state schema")
    result = PreFailureState(
        schema_version=str(payload["schema_version"]),
        previous_image_digest=_validate_digest(
            payload["previous_image_digest"], field="previous_image_digest"
        ),
        previous_build_commit_sha=_validate_commit(
            payload["previous_build_commit_sha"], field="previous_build_commit_sha"
        ),
        previous_build_version=_reject_secret_or_path(
            payload["previous_build_version"], field="previous_build_version"
        ),
        previous_deployment_id=_reject_secret_or_path(
            payload["previous_deployment_id"], field="previous_deployment_id"
        ),
        candidate_image_digest=_validate_digest(
            payload["candidate_image_digest"], field="candidate_image_digest"
        ),
        candidate_build_commit_sha=_validate_commit(
            payload["candidate_build_commit_sha"], field="candidate_build_commit_sha"
        ),
        candidate_build_version=_reject_secret_or_path(
            payload["candidate_build_version"], field="candidate_build_version"
        ),
        candidate_deployment_id=_reject_secret_or_path(
            payload["candidate_deployment_id"], field="candidate_deployment_id"
        ),
        database_environment_id=_reject_secret_or_path(
            payload["database_environment_id"], field="database_environment_id"
        ),
        artifact_environment_id=_reject_secret_or_path(
            payload["artifact_environment_id"], field="artifact_environment_id"
        ),
        pre_deployment_schema_head=_validate_schema_head(
            payload["pre_deployment_schema_head"], field="pre_deployment_schema_head"
        ),
        pre_deployment_database_inventory_digest=_validate_digest(
            payload["pre_deployment_database_inventory_digest"],
            field="pre_deployment_database_inventory_digest",
        ),
        pre_deployment_artifact_inventory_digest=_validate_digest(
            payload["pre_deployment_artifact_inventory_digest"],
            field="pre_deployment_artifact_inventory_digest",
        ),
        backup_id=_reject_secret_or_path(payload["backup_id"], field="backup_id"),
        backup_manifest_digest=_validate_digest(
            payload["backup_manifest_digest"], field="backup_manifest_digest"
        ),
    )
    if result.previous_image_digest == result.candidate_image_digest:
        raise FailureRecoveryError(
            "PRE_FAILURE_STATE_INVALID", "release image identities must differ"
        )
    if result.previous_deployment_id == result.candidate_deployment_id:
        raise FailureRecoveryError("PRE_FAILURE_STATE_INVALID", "deployment identities must differ")
    if result.database_environment_id == result.artifact_environment_id:
        raise FailureRecoveryError(
            "PRE_FAILURE_STATE_INVALID", "database and artifact identities must differ"
        )
    return result


def _validated_post_observation(
    state: PreFailureState,
    *,
    post_schema_head: object,
    post_database_inventory_digest: object,
    post_artifact_inventory_digest: object,
) -> tuple[str, str, str, FailureAssessment]:
    schema = _validate_schema_head(post_schema_head, field="post_failure_schema_head")
    database = _validate_digest(
        post_database_inventory_digest, field="post_failure_database_inventory_digest"
    )
    artifact = _validate_digest(
        post_artifact_inventory_digest, field="post_failure_artifact_inventory_digest"
    )
    assessment = classify_failure_state(
        pre_deployment_schema_head=state.pre_deployment_schema_head,
        post_failure_schema_head=schema,
        pre_deployment_database_inventory_digest=state.pre_deployment_database_inventory_digest,
        post_failure_database_inventory_digest=database,
        pre_deployment_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
        post_failure_artifact_inventory_digest=artifact,
    )
    return schema, database, artifact, assessment


def make_deployment_rollback_receipt(
    state: PreFailureState,
    *,
    post_failure_schema_head: object,
    post_failure_database_inventory_digest: object,
    post_failure_artifact_inventory_digest: object,
    rollback_image_digest: object,
    rollback_build_commit_sha: object,
    rollback_build_version: object,
    rollback_deployment_id: object,
    post_rollback_live_status: object,
    post_rollback_ready_status: object,
) -> dict[str, Any]:
    """Create a PASS receipt only after an app-only rollback is authorized."""

    schema, database, artifact, assessment = _validated_post_observation(
        state,
        post_schema_head=post_failure_schema_head,
        post_database_inventory_digest=post_failure_database_inventory_digest,
        post_artifact_inventory_digest=post_failure_artifact_inventory_digest,
    )
    if not assessment.app_only_rollback_allowed:
        raise FailureRecoveryError(
            "APP_ONLY_ROLLBACK_PROHIBITED", "database or schema state changed or is ambiguous"
        )
    rollback_digest = _validate_digest(rollback_image_digest, field="rollback_image_digest")
    rollback_commit = _validate_commit(rollback_build_commit_sha, field="rollback_build_commit_sha")
    rollback_version = _reject_secret_or_path(
        rollback_build_version, field="rollback_build_version"
    )
    rollback_deployment = _reject_secret_or_path(
        rollback_deployment_id, field="rollback_deployment_id"
    )
    if (
        rollback_digest != state.previous_image_digest
        or rollback_commit != state.previous_build_commit_sha
        or rollback_version != state.previous_build_version
        or rollback_deployment != state.previous_deployment_id
    ):
        raise FailureRecoveryError(
            "ROLLBACK_IDENTITY_MISMATCH", "rollback did not restore previous known-good identity"
        )
    if post_rollback_live_status != "PASS" or post_rollback_ready_status != "PASS":
        raise FailureRecoveryError("ROLLBACK_READINESS_FAILED", "rollback readiness did not pass")
    return {
        "schema_version": "cold-storage-deployment-rollback-receipt-v1",
        "task": "TASK-012",
        "version": "V0.2",
        "slice": 6,
        "package": 2,
        "controlled_synthetic": True,
        "database_environment_id": state.database_environment_id,
        "artifact_environment_id": state.artifact_environment_id,
        "backup_id": state.backup_id,
        "backup_manifest_digest": state.backup_manifest_digest,
        "previous_image_digest": state.previous_image_digest,
        "failed_candidate_image_digest": state.candidate_image_digest,
        "previous_build_commit_sha": state.previous_build_commit_sha,
        "failed_candidate_build_commit_sha": state.candidate_build_commit_sha,
        "previous_build_version": state.previous_build_version,
        "failed_candidate_build_version": state.candidate_build_version,
        "previous_deployment_id": state.previous_deployment_id,
        "failed_candidate_deployment_id": state.candidate_deployment_id,
        "pre_failure_schema_head": state.pre_deployment_schema_head,
        "post_failure_schema_head": schema,
        "pre_failure_database_inventory_digest": state.pre_deployment_database_inventory_digest,
        "post_failure_database_inventory_digest": database,
        "pre_failure_artifact_inventory_digest": state.pre_deployment_artifact_inventory_digest,
        "post_failure_artifact_inventory_digest": artifact,
        "failure_classification": assessment.failure_state.value,
        "recovery_decision": assessment.recovery_decision.value,
        "rollback_image_digest": rollback_digest,
        "rollback_build_commit_sha": rollback_commit,
        "rollback_build_version": rollback_version,
        "rollback_deployment_id": rollback_deployment,
        "post_rollback_live_status": "PASS",
        "post_rollback_ready_status": "PASS",
        "rollback_result": "PASS",
    }


def verify_deployment_rollback_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a closed deployment rollback receipt without trusting PASS alone."""

    receipt = _validate_closed_mapping(
        value, DEPLOYMENT_ROLLBACK_RECEIPT_FIELDS, code="DEPLOYMENT_ROLLBACK_RECEIPT_INVALID"
    )
    state_payload = {
        "schema_version": "cold-storage-release-failure-state-v1",
        "previous_image_digest": receipt["previous_image_digest"],
        "previous_build_commit_sha": receipt["previous_build_commit_sha"],
        "previous_build_version": receipt["previous_build_version"],
        "previous_deployment_id": receipt["previous_deployment_id"],
        "candidate_image_digest": receipt["failed_candidate_image_digest"],
        "candidate_build_commit_sha": receipt["failed_candidate_build_commit_sha"],
        "candidate_build_version": receipt["failed_candidate_build_version"],
        "candidate_deployment_id": receipt["failed_candidate_deployment_id"],
        "database_environment_id": receipt["database_environment_id"],
        "artifact_environment_id": receipt["artifact_environment_id"],
        "pre_deployment_schema_head": receipt["pre_failure_schema_head"],
        "pre_deployment_database_inventory_digest": receipt[
            "pre_failure_database_inventory_digest"
        ],
        "pre_deployment_artifact_inventory_digest": receipt[
            "pre_failure_artifact_inventory_digest"
        ],
        "backup_id": receipt["backup_id"],
        "backup_manifest_digest": receipt["backup_manifest_digest"],
    }
    state = validate_pre_failure_state(state_payload)
    if receipt["schema_version"] != "cold-storage-deployment-rollback-receipt-v1":
        raise FailureRecoveryError(
            "DEPLOYMENT_ROLLBACK_RECEIPT_INVALID", "unsupported receipt schema"
        )
    if (
        receipt["task"],
        receipt["version"],
        receipt["slice"],
        receipt["package"],
        receipt["controlled_synthetic"],
    ) != ("TASK-012", "V0.2", 6, 2, True):
        raise FailureRecoveryError(
            "DEPLOYMENT_ROLLBACK_RECEIPT_INVALID", "receipt identity mismatch"
        )
    _, _, _, assessment = _validated_post_observation(
        state,
        post_schema_head=receipt["post_failure_schema_head"],
        post_database_inventory_digest=receipt["post_failure_database_inventory_digest"],
        post_artifact_inventory_digest=receipt["post_failure_artifact_inventory_digest"],
    )
    if assessment.failure_state != FailureState.SCHEMA_AND_DATA_UNCHANGED:
        raise FailureRecoveryError(
            "DEPLOYMENT_ROLLBACK_RECEIPT_INVALID", "rollback state was not unchanged"
        )
    if receipt["failure_classification"] != assessment.failure_state.value:
        raise FailureRecoveryError("DEPLOYMENT_ROLLBACK_RECEIPT_INVALID", "classification mismatch")
    if receipt["recovery_decision"] != RecoveryDecision.APP_ONLY_ROLLBACK_ALLOWED.value:
        raise FailureRecoveryError(
            "DEPLOYMENT_ROLLBACK_RECEIPT_INVALID", "unsafe recovery decision"
        )
    if receipt["rollback_result"] != "PASS":
        raise FailureRecoveryError("DEPLOYMENT_ROLLBACK_RECEIPT_INVALID", "rollback did not pass")
    expected = {
        "rollback_image_digest": state.previous_image_digest,
        "rollback_build_commit_sha": state.previous_build_commit_sha,
        "rollback_build_version": state.previous_build_version,
        "rollback_deployment_id": state.previous_deployment_id,
        "post_rollback_live_status": "PASS",
        "post_rollback_ready_status": "PASS",
    }
    if any(receipt[key] != expected_value for key, expected_value in expected.items()):
        raise FailureRecoveryError(
            "DEPLOYMENT_ROLLBACK_RECEIPT_INVALID", "rollback identity mismatch"
        )
    return receipt


def make_migration_recovery_receipt(
    *,
    backup_id: object,
    backup_manifest_digest: object,
    pre_migration_database_inventory_digest: object,
    pre_migration_artifact_inventory_digest: object,
    pre_migration_schema_head: object,
    migration_failure_class: object,
    post_failure_schema_head: object,
    post_failure_database_inventory_digest: object,
    post_failure_artifact_inventory_digest: object,
    source_environment_id: object,
    restore_target_environment_id: object,
    source_database_environment_id: object,
    restore_target_database_environment_id: object,
    source_artifact_environment_id: object,
    restore_target_artifact_environment_id: object,
    restore_backup_id: object,
    restore_receipt_digest: object,
    final_schema_head: object,
    final_database_inventory_digest: object,
    final_artifact_inventory_digest: object,
    independent_restore_verification: object,
    post_recovery_live_status: object,
    post_recovery_ready_status: object,
) -> dict[str, Any]:
    """Create a PASS migration-recovery receipt after isolated verification."""

    pre_database = _validate_digest(
        pre_migration_database_inventory_digest,
        field="pre_migration_database_inventory_digest",
    )
    pre_artifact = _validate_digest(
        pre_migration_artifact_inventory_digest,
        field="pre_migration_artifact_inventory_digest",
    )
    pre_schema = _validate_schema_head(pre_migration_schema_head, field="pre_migration_schema_head")
    post_schema = _validate_schema_head(post_failure_schema_head, field="post_failure_schema_head")
    final_schema = _validate_schema_head(final_schema_head, field="final_schema_head")
    backup_id_value = _reject_secret_or_path(backup_id, field="backup_id")
    backup_digest = _validate_digest(backup_manifest_digest, field="backup_manifest_digest")
    failure_class = _reject_secret_or_path(migration_failure_class, field="migration_failure_class")
    post_db = _validate_digest(
        post_failure_database_inventory_digest, field="post_failure_database_inventory_digest"
    )
    post_artifact = _validate_digest(
        post_failure_artifact_inventory_digest, field="post_failure_artifact_inventory_digest"
    )
    receipt_digest = _validate_digest(restore_receipt_digest, field="restore_receipt_digest")
    restore_backup_id_value = _reject_secret_or_path(restore_backup_id, field="restore_backup_id")
    if restore_backup_id_value != backup_id_value:
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "restore receipt backup identity mismatch"
        )
    final_db = _validate_digest(
        final_database_inventory_digest, field="final_database_inventory_digest"
    )
    final_artifact = _validate_digest(
        final_artifact_inventory_digest, field="final_artifact_inventory_digest"
    )
    restore_verification = independent_restore_verification
    live_status = post_recovery_live_status
    ready_status = post_recovery_ready_status
    if restore_verification != "PASS":
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID",
            "independent restore verification did not pass",
        )
    if live_status != "PASS":
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID",
            "post-recovery live status did not pass",
        )
    if ready_status != "PASS":
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID",
            "post-recovery ready status did not pass",
        )
    identities = {
        "source_environment_id": _reject_secret_or_path(
            source_environment_id, field="source_environment_id"
        ),
        "restore_target_environment_id": _reject_secret_or_path(
            restore_target_environment_id, field="restore_target_environment_id"
        ),
        "source_database_environment_id": _reject_secret_or_path(
            source_database_environment_id, field="source_database_environment_id"
        ),
        "restore_target_database_environment_id": _reject_secret_or_path(
            restore_target_database_environment_id, field="restore_target_database_environment_id"
        ),
        "source_artifact_environment_id": _reject_secret_or_path(
            source_artifact_environment_id, field="source_artifact_environment_id"
        ),
        "restore_target_artifact_environment_id": _reject_secret_or_path(
            restore_target_artifact_environment_id, field="restore_target_artifact_environment_id"
        ),
    }
    if any(
        identities[source] == identities[target]
        for source, target in (
            ("source_environment_id", "restore_target_environment_id"),
            ("source_database_environment_id", "restore_target_database_environment_id"),
            ("source_artifact_environment_id", "restore_target_artifact_environment_id"),
        )
    ):
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "restore target is not isolated"
        )
    if final_schema != pre_schema or final_db != pre_database or final_artifact != pre_artifact:
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "final recovery state mismatch"
        )
    classification = classify_failure_state(
        pre_deployment_schema_head=pre_schema,
        post_failure_schema_head=post_schema,
        pre_deployment_database_inventory_digest=pre_database,
        post_failure_database_inventory_digest=post_db,
        pre_deployment_artifact_inventory_digest=pre_artifact,
        post_failure_artifact_inventory_digest=post_artifact,
    )
    if not classification.migration_recovery_required:
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID",
            "unchanged failure state does not require migration recovery",
        )
    return {
        "schema_version": "cold-storage-migration-recovery-receipt-v2",
        "task": "TASK-012",
        "version": "V0.2",
        "slice": 6,
        "package": 2,
        "controlled_synthetic": True,
        "backup_id": backup_id_value,
        "backup_manifest_digest": backup_digest,
        "pre_migration_database_inventory_digest": pre_database,
        "pre_migration_artifact_inventory_digest": pre_artifact,
        "pre_migration_schema_head": pre_schema,
        "migration_attempt_result": "FAILURE",
        "migration_failure_class": failure_class,
        "post_failure_schema_head": post_schema,
        "post_failure_database_inventory_digest": post_db,
        "post_failure_artifact_inventory_digest": post_artifact,
        "failure_state_classification": classification.failure_state.value,
        "automatic_downgrade_performed": False,
        "recovery_required": True,
        **identities,
        "restore_backup_id": restore_backup_id_value,
        "restore_receipt_digest": receipt_digest,
        "final_schema_head": final_schema,
        "final_database_inventory_digest": final_db,
        "final_artifact_inventory_digest": final_artifact,
        "independent_restore_verification": restore_verification,
        "post_recovery_live_status": live_status,
        "post_recovery_ready_status": ready_status,
        "readiness_verification": "PASS",
        "migration_recovery_result": "PASS",
    }


def verify_migration_recovery_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the closed migration recovery receipt and its safety gates."""

    receipt = _validate_closed_mapping(
        value, MIGRATION_RECOVERY_RECEIPT_FIELDS, code="MIGRATION_RECOVERY_RECEIPT_INVALID"
    )
    if (
        receipt["schema_version"],
        receipt["task"],
        receipt["version"],
        receipt["slice"],
        receipt["package"],
        receipt["controlled_synthetic"],
    ) != ("cold-storage-migration-recovery-receipt-v2", "TASK-012", "V0.2", 6, 2, True):
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "receipt identity mismatch"
        )
    if receipt["automatic_downgrade_performed"] is not False:
        raise FailureRecoveryError(
            "AUTOMATIC_DOWNGRADE_PROHIBITED", "automatic downgrade is forbidden"
        )
    if receipt["recovery_required"] is not True:
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "recovery requirement is missing"
        )
    if receipt["migration_attempt_result"] != "FAILURE":
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "migration failure is missing"
        )
    _reject_secret_or_path(receipt["backup_id"], field="backup_id")
    _reject_secret_or_path(receipt["restore_backup_id"], field="restore_backup_id")
    if receipt["restore_backup_id"] != receipt["backup_id"]:
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "restore receipt backup identity mismatch"
        )
    _reject_secret_or_path(receipt["migration_failure_class"], field="migration_failure_class")
    for key in (
        "backup_manifest_digest",
        "pre_migration_database_inventory_digest",
        "pre_migration_artifact_inventory_digest",
        "post_failure_database_inventory_digest",
        "post_failure_artifact_inventory_digest",
        "restore_receipt_digest",
        "final_database_inventory_digest",
        "final_artifact_inventory_digest",
    ):
        _validate_digest(receipt[key], field=key)
    for key in (
        "pre_migration_schema_head",
        "post_failure_schema_head",
        "final_schema_head",
    ):
        _validate_schema_head(receipt[key], field=key)
    classification = classify_failure_state(
        pre_deployment_schema_head=receipt["pre_migration_schema_head"],
        post_failure_schema_head=receipt["post_failure_schema_head"],
        pre_deployment_database_inventory_digest=receipt["pre_migration_database_inventory_digest"],
        post_failure_database_inventory_digest=receipt["post_failure_database_inventory_digest"],
        pre_deployment_artifact_inventory_digest=receipt["pre_migration_artifact_inventory_digest"],
        post_failure_artifact_inventory_digest=receipt["post_failure_artifact_inventory_digest"],
    )
    if (
        receipt["failure_state_classification"] != classification.failure_state.value
        or not classification.migration_recovery_required
    ):
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID",
            "migration failure classification is not fail-closed",
        )
    if receipt["final_schema_head"] != receipt["pre_migration_schema_head"]:
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "final schema head mismatch"
        )
    if (
        receipt["final_database_inventory_digest"]
        != receipt["pre_migration_database_inventory_digest"]
    ):
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "final database digest mismatch"
        )
    if (
        receipt["final_artifact_inventory_digest"]
        != receipt["pre_migration_artifact_inventory_digest"]
    ):
        raise FailureRecoveryError(
            "MIGRATION_RECOVERY_RECEIPT_INVALID", "final artifact digest mismatch"
        )
    for source, target in (
        ("source_environment_id", "restore_target_environment_id"),
        ("source_database_environment_id", "restore_target_database_environment_id"),
        ("source_artifact_environment_id", "restore_target_artifact_environment_id"),
    ):
        _reject_secret_or_path(receipt[source], field=source)
        _reject_secret_or_path(receipt[target], field=target)
        if receipt[source] == receipt[target]:
            raise FailureRecoveryError(
                "MIGRATION_RECOVERY_RECEIPT_INVALID", "restore target is not isolated"
            )
    for key in (
        "independent_restore_verification",
        "post_recovery_live_status",
        "post_recovery_ready_status",
        "readiness_verification",
        "migration_recovery_result",
    ):
        if receipt[key] != "PASS":
            raise FailureRecoveryError("MIGRATION_RECOVERY_RECEIPT_INVALID", f"{key} did not pass")
    return receipt


def load_json_object(path: Path) -> dict[str, Any]:
    """Read one non-secret JSON object for the canonical CLI."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FailureRecoveryError(
            "FAILURE_RECOVERY_INPUT_INVALID", "JSON input is unreadable"
        ) from exc
    if not isinstance(value, dict):
        raise FailureRecoveryError("FAILURE_RECOVERY_INPUT_INVALID", "JSON input must be an object")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write canonical JSON to an operator-selected evidence path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(value) + b"\n")


__all__ = [
    "DEPLOYMENT_ROLLBACK_RECEIPT_FIELDS",
    "FailureAssessment",
    "FailureRecoveryError",
    "FailureState",
    "MIGRATION_RECOVERY_RECEIPT_FIELDS",
    "PRE_FAILURE_STATE_FIELDS",
    "PreFailureState",
    "RecoveryDecision",
    "canonical_digest",
    "classify_failure_state",
    "load_json_object",
    "make_deployment_rollback_receipt",
    "make_migration_recovery_receipt",
    "validate_pre_failure_state",
    "verify_deployment_rollback_receipt",
    "verify_migration_recovery_receipt",
    "write_json",
]
