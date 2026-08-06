"""Provenance statement unit tests (S2_GAP_04)."""

from __future__ import annotations

from collections import OrderedDict

import pytest

from cold_storage.release.canonical_serialization import ReleaseEvidenceError
from cold_storage.release.provenance_schema import (
    PROVENANCE_SCHEMA_VERSION,
    RC_PROVENANCE_REPO_MISMATCH,
    RC_PROVENANCE_SUBJECT_MISMATCH,
    RC_PROVENANCE_UNSIGNED,
    RC_PROVENANCE_WORKFLOW_MISMATCH,
)
from cold_storage.release.provenance_statement import (
    ProvenanceError,
    build_provenance,
    compute_provenance_digest,
    verify_provenance,
)

IMAGE = "sha256:" + "a" * 64
IMAGE_B = "sha256:" + "b" * 64
ARTIFACT = "sha256:" + "c" * 64
ATT = {
    "mechanism": "github_oidc",
    "binding": "eyJ.payload.sig",
    "issuer": "https://token.actions.githubusercontent.com",
}


def _fields() -> OrderedDict:
    return OrderedDict(
        [
            ("schema_version", PROVENANCE_SCHEMA_VERSION),
            ("subject_final_image_digest", IMAGE),
            ("subject_artifact_manifest_digest", ARTIFACT),
            ("source_repository", "xuezhiorange-png/cold-storage-planning-agent"),
            ("source_commit_sha", "25a88f0b65fa7662310701563e306331034d6c34"),
            ("source_tree_sha", "274e84af01bd895a30571423283838017aacd45f"),
            ("build_workflow_identity", "ci"),
            ("build_workflow_ref", "refs/heads/main"),
            ("build_run_id", "run-1"),
            ("build_run_attempt", 1),
            ("build_trigger", "push"),
            ("builder_identity", "runner-1.github-actions.us-east-1"),
            ("build_platform", "ubuntu-latest"),
            ("build_definition_digest", "sha256:" + "12" * 32),
            ("dependency_lockset_digest", "sha256:" + "1" * 64),
            ("base_image_digest_set", ["sha256:" + "f" * 64]),
            ("build_input_manifest_digest", "sha256:" + "0" * 64),
            ("build_started_at", "2026-08-06T12:00:00Z"),
            ("build_finished_at", "2026-08-06T12:05:00Z"),
            ("reproducible_build_result", "PASS"),
            ("provenance_digest", ""),
            ("attestation", dict(ATT)),
        ]
    )


def test_verify_provenance_passes_for_valid_statement() -> None:
    prov = build_provenance(_fields())
    verify_provenance(prov, expected_image_digest=IMAGE, expected_artifact_manifest_digest=ARTIFACT)


def test_provenance_rejects_unsigned() -> None:
    fields = _fields()
    fields["attestation"] = {}
    prov = build_provenance(fields)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_provenance(
            prov, expected_image_digest=IMAGE, expected_artifact_manifest_digest=ARTIFACT
        )
    assert exc.value.failure_code == RC_PROVENANCE_UNSIGNED


def test_provenance_rejects_repo_mismatch() -> None:
    fields = _fields()
    fields["source_repository"] = "evil/repo"
    prov = build_provenance(fields)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_provenance(
            prov, expected_image_digest=IMAGE, expected_artifact_manifest_digest=ARTIFACT
        )
    assert exc.value.failure_code == RC_PROVENANCE_REPO_MISMATCH


def test_provenance_rejects_workflow_mismatch() -> None:
    fields = _fields()
    fields["build_workflow_identity"] = "evil-ci"
    prov = build_provenance(fields)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_provenance(
            prov, expected_image_digest=IMAGE, expected_artifact_manifest_digest=ARTIFACT
        )
    assert exc.value.failure_code == RC_PROVENANCE_WORKFLOW_MISMATCH


def test_provenance_rejects_pr_ref_for_rc() -> None:
    fields = _fields()
    fields["build_workflow_ref"] = "refs/pull/99/merge"
    prov = build_provenance(fields)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_provenance(
            prov, expected_image_digest=IMAGE, expected_artifact_manifest_digest=ARTIFACT
        )
    assert exc.value.failure_code == RC_PROVENANCE_WORKFLOW_MISMATCH


def test_provenance_rejects_subject_image_mismatch() -> None:
    fields = _fields()
    fields["subject_final_image_digest"] = IMAGE_B
    prov = build_provenance(fields)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_provenance(
            prov, expected_image_digest=IMAGE, expected_artifact_manifest_digest=ARTIFACT
        )
    assert exc.value.failure_code == RC_PROVENANCE_SUBJECT_MISMATCH


def test_provenance_rejects_subject_artifact_mismatch() -> None:
    fields = _fields()
    prov = build_provenance(fields)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_provenance(
            prov,
            expected_image_digest=IMAGE,
            expected_artifact_manifest_digest="sha256:" + "z" * 64,
        )
    assert exc.value.failure_code == RC_PROVENANCE_SUBJECT_MISMATCH


def test_provenance_rejects_unknown_schema_version() -> None:
    fields = _fields()
    fields["schema_version"] = "unknown-v2"
    with pytest.raises(ProvenanceError):
        build_provenance(fields)


def test_provenance_rejects_reproducible_build_not_pass() -> None:
    fields = _fields()
    fields["reproducible_build_result"] = "FAIL"
    prov = build_provenance(fields)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_provenance(
            prov, expected_image_digest=IMAGE, expected_artifact_manifest_digest=ARTIFACT
        )
    assert exc.value.failure_code == RC_PROVENANCE_UNSIGNED


def test_provenance_rejects_wrong_oidc_issuer() -> None:
    fields = _fields()
    fields["attestation"] = {
        "mechanism": "github_oidc",
        "binding": "x",
        "issuer": "https://evil.example",
    }
    prov = build_provenance(fields)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_provenance(
            prov, expected_image_digest=IMAGE, expected_artifact_manifest_digest=ARTIFACT
        )
    assert exc.value.failure_code == RC_PROVENANCE_UNSIGNED


def test_provenance_digest_is_stable_excluding_self_and_attestation() -> None:
    prov = build_provenance(_fields())
    d1 = compute_provenance_digest(prov)
    prov["provenance_digest"] = "sha256:" + "0" * 64
    prov["attestation"] = {"mechanism": "cosign", "binding": "other"}
    d2 = compute_provenance_digest(prov)
    assert d1 == d2


def test_provenance_subject_binds_both_digests() -> None:
    """A provenance binding only one subject digest is incomplete (9.10)."""
    fields = _fields()
    fields["subject_artifact_manifest_digest"] = ""
    prov = build_provenance(fields)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_provenance(
            prov, expected_image_digest=IMAGE, expected_artifact_manifest_digest=ARTIFACT
        )
    assert exc.value.failure_code == RC_PROVENANCE_SUBJECT_MISMATCH
