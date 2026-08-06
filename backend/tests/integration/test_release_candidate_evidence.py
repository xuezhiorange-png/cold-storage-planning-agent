"""Integration test: end-to-end release-candidate evidence pipeline (S2_GAP_01–05).

Exercises :func:`collect_release_candidate_evidence` with two
reproducible synthetic builds and verifies the assembled bundle, then
verifies a synthetic promotion record against the bundle.
"""

from __future__ import annotations

from collections import OrderedDict

import pytest

from cold_storage.release.evidence_collector import (
    BuildInputs,
    BuildRunRecord,
    collect_release_candidate_evidence,
    verify_evidence_bundle,
    verify_promotion_against_bundle,
)
from cold_storage.release.provenance_schema import (
    EXPECTED_SOURCE_COMMIT_SHA,
    EXPECTED_SOURCE_REPOSITORY,
    EXPECTED_SOURCE_TREE_SHA,
)

IMAGE = "sha256:" + "a" * 64
BASE = "sha256:" + "f" * 64
LOCK = "sha256:" + "1" * 64
ATT = {
    "mechanism": "github_oidc",
    "binding": "eyJ.payload.sig",
    "issuer": "https://token.actions.githubusercontent.com",
}


def _inputs() -> BuildInputs:
    return BuildInputs(
        source_commit_sha=EXPECTED_SOURCE_COMMIT_SHA,
        source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        source_date_epoch=1234567890,
        dockerfile_digest="sha256:" + "10" * 32,
        compose_file_digest="sha256:" + "11" * 32,
        workflow_definition_digest="sha256:" + "12" * 32,
        dependency_lockset_digest=LOCK,
        migration_set_digest="sha256:" + "13" * 32,
        base_image_digest_set=[BASE],
        build_args={
            "COLD_STORAGE_BUILD_COMMIT_SHA": EXPECTED_SOURCE_COMMIT_SHA,
            "COLD_STORAGE_BUILD_VERSION": "v0.2.0",
        },
    )


def _run(digest: str = IMAGE) -> BuildRunRecord:
    return BuildRunRecord(
        build_run_id="run-1",
        build_run_attempt=1,
        build_trigger="push",
        builder_identity="runner-1.github-actions.us-east-1",
        build_started_at="2026-08-06T12:00:00Z",
        build_finished_at="2026-08-06T12:05:00Z",
        final_image_digest=digest,
        local_oci_manifest_digest=digest,
        registry_manifest_digest=digest,
        base_image_tag="python:3.12-slim",
        base_image_digest=BASE,
        lockfile_digest=LOCK,
    )


def _artifacts() -> list[OrderedDict]:
    return [
        OrderedDict(
            [("relative_path", "backend/Dockerfile"), ("size_bytes", 100), ("sha256", "x")]
        ),
        OrderedDict(
            [
                ("relative_path", "docker-compose.production.yml"),
                ("size_bytes", 200),
                ("sha256", "y"),
            ]
        ),
    ]


def test_collect_and_verify_evidence_bundle() -> None:
    bundle = collect_release_candidate_evidence(
        inputs=_inputs(),
        build_a=_run(),
        build_b=_run(),
        artifacts=_artifacts(),
        test_result_reference="https://github.com/test/run/1",
        verification_result_reference="https://github.com/test/run/2",
        attestation=ATT,
    )
    assert bundle.authoritative_image_digest == IMAGE
    assert bundle.reproducible_build_result == "PASS"
    assert bundle.provenance["source_repository"] == EXPECTED_SOURCE_REPOSITORY
    # cross-references are consistent
    assert bundle.provenance["subject_final_image_digest"] == bundle.authoritative_image_digest
    assert bundle.provenance["subject_artifact_manifest_digest"] == bundle.artifact_manifest_digest
    assert bundle.artifact_manifest["provenance_digest"] == bundle.provenance_digest
    # re-verify end-to-end
    verify_evidence_bundle(bundle)


def test_collect_rejects_non_reproducible_build() -> None:
    from cold_storage.release.canonical_serialization import ReleaseEvidenceError

    with pytest.raises(ReleaseEvidenceError) as exc:
        collect_release_candidate_evidence(
            inputs=_inputs(),
            build_a=_run(),
            build_b=_run(digest="sha256:" + "b" * 64),
            artifacts=_artifacts(),
            test_result_reference="https://github.com/test/run/1",
            verification_result_reference="https://github.com/test/run/2",
            attestation=ATT,
        )
    assert exc.value.failure_code == "RC_FINAL_IMAGE_DIGEST_MISMATCH"


def test_synthetic_promotion_evidence_against_bundle() -> None:
    """Synthetic promotion evidence (no real staging/production promotion)."""
    bundle = collect_release_candidate_evidence(
        inputs=_inputs(),
        build_a=_run(),
        build_b=_run(),
        artifacts=_artifacts(),
        test_result_reference="https://github.com/test/run/1",
        verification_result_reference="https://github.com/test/run/2",
        attestation=ATT,
    )
    promotion = OrderedDict(
        [
            ("schema_version", "cold-storage-release-candidate-promotion-record-v1"),
            ("rc_version", "v0.2.0"),
            ("source_environment", "ci"),
            ("target_environment", "staging"),
            ("final_image_digest", bundle.authoritative_image_digest),
            ("artifact_manifest_digest", bundle.artifact_manifest_digest),
            ("provenance_digest", bundle.provenance_digest),
            ("deployment_definition_digest", "sha256:" + "20" * 32),
            ("environment_config_digest", "sha256:" + "e" * 64),
            ("promoted_by", "ci-bot"),
            ("approved_by", "release-manager"),
            ("promotion_timestamp", "2026-08-06T13:00:00Z"),
            ("verification_result", "PASS"),
        ]
    )
    verify_promotion_against_bundle(bundle, promotion)
