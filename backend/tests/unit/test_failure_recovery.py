from __future__ import annotations

import json
from pathlib import Path

import pytest

from cold_storage.recovery.failure_recovery import (
    FailureRecoveryError,
    FailureState,
    RecoveryDecision,
    classify_failure_state,
    make_deployment_rollback_receipt,
    make_migration_recovery_receipt,
    validate_pre_failure_state,
    verify_deployment_rollback_receipt,
    verify_migration_recovery_receipt,
)


def _digest(letter: str) -> str:
    return f"sha256:{letter * 64}"


def _state() -> dict[str, str]:
    return {
        "schema_version": "cold-storage-release-failure-state-v1",
        "previous_image_digest": _digest("a"),
        "previous_build_commit_sha": "1" * 40,
        "previous_build_version": "pkg2-prev-1",
        "previous_deployment_id": "deployment-prev-1",
        "candidate_image_digest": _digest("b"),
        "candidate_build_commit_sha": "2" * 40,
        "candidate_build_version": "pkg2-candidate-1",
        "candidate_deployment_id": "deployment-candidate-1",
        "database_environment_id": "controlled-release-db",
        "artifact_environment_id": "controlled-release-artifacts",
        "pre_deployment_schema_head": "0039_widen_report_export_artifact_mime_type",
        "pre_deployment_database_inventory_digest": _digest("c"),
        "pre_deployment_artifact_inventory_digest": _digest("d"),
        "backup_id": "backup-001",
        "backup_manifest_digest": _digest("e"),
    }


def _validated_state():
    return validate_pre_failure_state(_state())


def test_unchanged_state_allows_app_only_rollback() -> None:
    assessment = classify_failure_state(
        pre_deployment_schema_head="head",
        post_failure_schema_head="head",
        pre_deployment_database_inventory_digest=_digest("a"),
        post_failure_database_inventory_digest=_digest("a"),
        pre_deployment_artifact_inventory_digest=_digest("b"),
        post_failure_artifact_inventory_digest=_digest("b"),
    )
    assert assessment.failure_state is FailureState.SCHEMA_AND_DATA_UNCHANGED
    assert assessment.recovery_decision is RecoveryDecision.APP_ONLY_ROLLBACK_ALLOWED
    assert assessment.app_only_rollback_allowed is True
    assert assessment.migration_recovery_required is False


@pytest.mark.parametrize(
    ("post_schema", "post_database", "expected"),
    (
        ("next-head", _digest("a"), FailureState.SCHEMA_CHANGED),
        ("head", _digest("b"), FailureState.DATA_CHANGED),
        ("next-head", _digest("b"), FailureState.SCHEMA_AND_DATA_CHANGED),
    ),
)
def test_changed_state_requires_migration_recovery(
    post_schema: str, post_database: str, expected: FailureState
) -> None:
    assessment = classify_failure_state(
        pre_deployment_schema_head="head",
        post_failure_schema_head=post_schema,
        pre_deployment_database_inventory_digest=_digest("a"),
        post_failure_database_inventory_digest=post_database,
    )
    assert assessment.failure_state is expected
    assert assessment.app_only_rollback_allowed is False
    assert assessment.migration_recovery_required is True
    assert assessment.recovery_decision is RecoveryDecision.MIGRATION_RECOVERY_REQUIRED


@pytest.mark.parametrize(
    ("schema", "database"),
    ((None, _digest("a")), (["head-a", "head-b"], _digest("a")), ("head", "not-a-digest")),
)
def test_ambiguous_state_requires_fail_closed_recovery(schema: object, database: object) -> None:
    assessment = classify_failure_state(
        pre_deployment_schema_head="head",
        post_failure_schema_head=schema,
        pre_deployment_database_inventory_digest=_digest("a"),
        post_failure_database_inventory_digest=database,
    )
    assert assessment.failure_state is FailureState.STATE_AMBIGUOUS
    assert assessment.app_only_rollback_allowed is False
    assert assessment.migration_recovery_required is True


def test_pre_failure_state_rejects_same_release_identity() -> None:
    payload = _state()
    payload["candidate_image_digest"] = payload["previous_image_digest"]
    with pytest.raises(FailureRecoveryError, match="identities must differ"):
        validate_pre_failure_state(payload)


def test_deployment_rollback_receipt_requires_known_good_identity() -> None:
    state = _validated_state()
    receipt = make_deployment_rollback_receipt(
        state,
        post_failure_schema_head=state.pre_deployment_schema_head,
        post_failure_database_inventory_digest=state.pre_deployment_database_inventory_digest,
        post_failure_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
        rollback_image_digest=state.previous_image_digest,
        rollback_build_commit_sha=state.previous_build_commit_sha,
        rollback_build_version=state.previous_build_version,
        rollback_deployment_id=state.previous_deployment_id,
        post_rollback_live_status="PASS",
        post_rollback_ready_status="PASS",
    )
    assert verify_deployment_rollback_receipt(receipt)["rollback_result"] == "PASS"

    tampered = dict(receipt)
    tampered["rollback_image_digest"] = _digest("f")
    with pytest.raises(FailureRecoveryError, match="rollback identity mismatch"):
        verify_deployment_rollback_receipt(tampered)


def test_app_only_receipt_is_rejected_when_database_changed() -> None:
    state = _validated_state()
    with pytest.raises(FailureRecoveryError, match="APP_ONLY_ROLLBACK_PROHIBITED"):
        make_deployment_rollback_receipt(
            state,
            post_failure_schema_head=state.pre_deployment_schema_head,
            post_failure_database_inventory_digest=_digest("f"),
            post_failure_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
            rollback_image_digest=state.previous_image_digest,
            rollback_build_commit_sha=state.previous_build_commit_sha,
            rollback_build_version=state.previous_build_version,
            rollback_deployment_id=state.previous_deployment_id,
            post_rollback_live_status="PASS",
            post_rollback_ready_status="PASS",
        )


def test_migration_receipt_requires_isolated_verified_recovery() -> None:
    state = _validated_state()
    receipt = make_migration_recovery_receipt(
        backup_id=state.backup_id,
        backup_manifest_digest=state.backup_manifest_digest,
        pre_migration_database_inventory_digest=state.pre_deployment_database_inventory_digest,
        pre_migration_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
        pre_migration_schema_head=state.pre_deployment_schema_head,
        migration_failure_class="FAILED_MIGRATION_PARTIAL_MUTATION",
        post_failure_schema_head="temporary-failure-head",
        post_failure_database_inventory_digest=_digest("f"),
        post_failure_artifact_inventory_digest=_digest("f"),
        source_environment_id="controlled-release-source",
        restore_target_environment_id="controlled-release-recovered",
        source_database_environment_id="controlled-release-source-db",
        restore_target_database_environment_id="controlled-release-recovered-db",
        source_artifact_environment_id="controlled-release-source-artifacts",
        restore_target_artifact_environment_id="controlled-release-recovered-artifacts",
        restore_backup_id=state.backup_id,
        restore_receipt_digest=_digest("1"),
        final_schema_head=state.pre_deployment_schema_head,
        final_database_inventory_digest=state.pre_deployment_database_inventory_digest,
        final_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
    )
    assert verify_migration_recovery_receipt(receipt)["automatic_downgrade_performed"] is False

    tampered = dict(receipt)
    tampered["automatic_downgrade_performed"] = True
    with pytest.raises(FailureRecoveryError, match="AUTOMATIC_DOWNGRADE_PROHIBITED"):
        verify_migration_recovery_receipt(tampered)


def test_migration_receipt_rejects_restore_backup_mismatch() -> None:
    state = _validated_state()
    receipt = make_migration_recovery_receipt(
        backup_id=state.backup_id,
        backup_manifest_digest=state.backup_manifest_digest,
        pre_migration_database_inventory_digest=state.pre_deployment_database_inventory_digest,
        pre_migration_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
        pre_migration_schema_head=state.pre_deployment_schema_head,
        migration_failure_class="FAILED_MIGRATION_PARTIAL_MUTATION",
        post_failure_schema_head=state.pre_deployment_schema_head,
        post_failure_database_inventory_digest=_digest("f"),
        post_failure_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
        source_environment_id="controlled-release-source",
        restore_target_environment_id="controlled-release-recovered",
        source_database_environment_id="controlled-release-source-db",
        restore_target_database_environment_id="controlled-release-recovered-db",
        source_artifact_environment_id="controlled-release-source-artifacts",
        restore_target_artifact_environment_id="controlled-release-recovered-artifacts",
        restore_backup_id=state.backup_id,
        restore_receipt_digest=_digest("1"),
        final_schema_head=state.pre_deployment_schema_head,
        final_database_inventory_digest=state.pre_deployment_database_inventory_digest,
        final_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
    )
    receipt["restore_backup_id"] = "backup-other"
    with pytest.raises(FailureRecoveryError, match="backup identity mismatch"):
        verify_migration_recovery_receipt(receipt)


def test_migration_receipt_rejects_source_target_collision() -> None:
    state = _validated_state()
    with pytest.raises(FailureRecoveryError, match="restore target is not isolated"):
        make_migration_recovery_receipt(
            backup_id=state.backup_id,
            backup_manifest_digest=state.backup_manifest_digest,
            pre_migration_database_inventory_digest=state.pre_deployment_database_inventory_digest,
            pre_migration_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
            pre_migration_schema_head=state.pre_deployment_schema_head,
            migration_failure_class="FAILED_MIGRATION_TRANSACTION_ROLLBACK",
            post_failure_schema_head=state.pre_deployment_schema_head,
            post_failure_database_inventory_digest=state.pre_deployment_database_inventory_digest,
            post_failure_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
            source_environment_id="same",
            restore_target_environment_id="same",
            source_database_environment_id="source-db",
            restore_target_database_environment_id="target-db",
            source_artifact_environment_id="source-artifacts",
            restore_target_artifact_environment_id="target-artifacts",
            restore_backup_id=state.backup_id,
            restore_receipt_digest=_digest("1"),
            final_schema_head=state.pre_deployment_schema_head,
            final_database_inventory_digest=state.pre_deployment_database_inventory_digest,
            final_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
        )


def test_receipt_validator_rejects_secret_and_unknown_fields(tmp_path: Path) -> None:
    state = _validated_state()
    receipt = make_deployment_rollback_receipt(
        state,
        post_failure_schema_head=state.pre_deployment_schema_head,
        post_failure_database_inventory_digest=state.pre_deployment_database_inventory_digest,
        post_failure_artifact_inventory_digest=state.pre_deployment_artifact_inventory_digest,
        rollback_image_digest=state.previous_image_digest,
        rollback_build_commit_sha=state.previous_build_commit_sha,
        rollback_build_version=state.previous_build_version,
        rollback_deployment_id=state.previous_deployment_id,
        post_rollback_live_status="PASS",
        post_rollback_ready_status="PASS",
    )
    receipt["unexpected"] = "nope"
    receipt["password"] = "secret"
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(FailureRecoveryError, match="receipt schema is not closed"):
        verify_deployment_rollback_receipt(receipt)
