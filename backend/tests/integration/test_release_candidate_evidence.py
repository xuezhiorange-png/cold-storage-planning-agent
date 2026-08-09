"""Integration test: end-to-end release-candidate evidence pipeline (S2_GAP_01–05).

Exercises :func:`collect_release_candidate_evidence` with two
reproducible synthetic builds and verifies the assembled bundle, then
verifies a synthetic promotion record against the bundle.
"""

from __future__ import annotations

from collections import OrderedDict

import pytest

from cold_storage.release.canonical_serialization import ReleaseEvidenceError
from cold_storage.release.digest_verifier import compute_build_input_manifest_digest
from cold_storage.release.evidence_collector import (
    BuildInputs,
    BuildRunRecord,
    collect_release_candidate_evidence,
    verify_evidence_bundle,
    verify_promotion_against_bundle,
)
from cold_storage.release.provenance_schema import (
    EXPECTED_DOCKER_TARGET_PLATFORM,
    EXPECTED_SOURCE_COMMIT_SHA,
    EXPECTED_SOURCE_REPOSITORY,
    EXPECTED_SOURCE_TREE_SHA,
    PROMOTION_RECORD_SCHEMA_VERSION,
    RC_BUILD_ARG_MISMATCH,
    RC_FINAL_IMAGE_DIGEST_MISMATCH,
    RC_PROMOTION_REBUILD,
    RC_PROMOTION_RECORD_UNVERIFIABLE,
    RC_PROVENANCE_SUBJECT_MISMATCH,
    RC_REGISTRY_DIGEST_MISMATCH,
    RC_VERSION,
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
        oci_exporter={"type": "oci", "rewrite-timestamp": "true"},
    )


def _declared_manifest_digest(inputs: BuildInputs) -> str:
    """Compute the canonical build-input manifest digest for *inputs*.

    Test helper: in production each build run carries its own independently
    declared digest as part of its evidence.  Tests use this helper to
    produce a *correct* declared digest for the normal/passing case so the
    collector's integrity verifier accepts it.  Negative tests override
    the declared digest to a tampered value via ``declared_manifest_digest``.
    """
    return compute_build_input_manifest_digest(inputs.to_input_manifest())


def _run(
    digest: str = IMAGE,
    inputs: BuildInputs | None = None,
    declared_manifest_digest: str | None = None,
) -> BuildRunRecord:
    used_inputs = inputs if inputs is not None else _inputs()
    declared = (
        declared_manifest_digest
        if declared_manifest_digest is not None
        else _declared_manifest_digest(used_inputs)
    )
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
        build_input_manifest_digest=declared,
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
    assert _inputs().source_commit_sha == "043731fea4e60feb6b929c524c4b68e87ed67bd7"
    assert _inputs().source_tree_sha == "b456e77f07a0cef801c57d2f089a318c35c145c4"
    bundle = collect_release_candidate_evidence(
        build_a_inputs=_inputs(),
        build_b_inputs=_inputs(),
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


def test_collect_rejects_stale_source_via_public_path() -> None:
    """The public collector must reject the superseded RC source tuple."""
    stale_inputs = _inputs()
    stale_inputs.source_commit_sha = "25a88f0b65fa7662310701563e306331034d6c34"
    stale_inputs.source_tree_sha = "274e84af01bd895a30571423283838017aacd45f"
    stale_inputs.build_args = {
        **stale_inputs.build_args,
        "COLD_STORAGE_BUILD_COMMIT_SHA": stale_inputs.source_commit_sha,
    }

    with pytest.raises(ReleaseEvidenceError) as exc:
        collect_release_candidate_evidence(
            build_a_inputs=stale_inputs,
            build_b_inputs=stale_inputs,
            build_a=_run(inputs=stale_inputs),
            build_b=_run(inputs=stale_inputs),
            artifacts=_artifacts(),
            test_result_reference="https://github.com/test/run/1",
            verification_result_reference="https://github.com/test/run/2",
            attestation=ATT,
        )
    assert exc.value.failure_code == RC_PROVENANCE_SUBJECT_MISMATCH


def test_collect_rejects_non_frozen_docker_target_platform_via_public_path() -> None:
    bad_inputs = _inputs()
    bad_inputs.docker_target_platform = "linux/arm64"
    with pytest.raises(ReleaseEvidenceError) as exc:
        collect_release_candidate_evidence(
            build_a_inputs=_inputs(),
            build_b_inputs=bad_inputs,
            build_a=_run(),
            build_b=_run(inputs=bad_inputs),
            artifacts=_artifacts(),
            test_result_reference="https://github.com/test/run/1",
            verification_result_reference="https://github.com/test/run/2",
            attestation=ATT,
        )
    assert exc.value.failure_code == RC_BUILD_ARG_MISMATCH


def test_collect_positive_target_platform_is_distinct_from_build_platform() -> None:
    inputs = _inputs()
    assert inputs.docker_target_platform == EXPECTED_DOCKER_TARGET_PLATFORM
    assert inputs.build_platform == "ubuntu-latest"


def test_collect_rejects_non_reproducible_build() -> None:
    with pytest.raises(ReleaseEvidenceError) as exc:
        collect_release_candidate_evidence(
            build_a_inputs=_inputs(),
            build_b_inputs=_inputs(),
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
        build_a_inputs=_inputs(),
        build_b_inputs=_inputs(),
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
            ("rebuild_performed", False),
            ("promoted_by", "ci-bot"),
            ("approved_by", "release-manager"),
            ("promotion_timestamp", "2026-08-06T13:00:00Z"),
            ("verification_result", "PASS"),
        ]
    )
    verify_promotion_against_bundle(bundle, promotion)


# ---------------------------------------------------------------------------
# Correction R2: B2/B3/B4 end-to-end closure adversarial tests
# ---------------------------------------------------------------------------

COMMIT = EXPECTED_SOURCE_COMMIT_SHA
TREE = EXPECTED_SOURCE_TREE_SHA


def _inputs_custom(*, source_date_epoch: int = 1234567890) -> BuildInputs:
    return BuildInputs(
        source_commit_sha=COMMIT,
        source_tree_sha=TREE,
        source_date_epoch=source_date_epoch,
        dockerfile_digest="sha256:" + "10" * 32,
        compose_file_digest="sha256:" + "11" * 32,
        workflow_definition_digest="sha256:" + "12" * 32,
        dependency_lockset_digest=LOCK,
        migration_set_digest="sha256:" + "13" * 32,
        base_image_digest_set=[BASE],
        build_args={
            "COLD_STORAGE_BUILD_COMMIT_SHA": COMMIT,
            "COLD_STORAGE_BUILD_VERSION": "v0.2.0",
        },
        oci_exporter={"type": "oci", "rewrite-timestamp": "true"},
    )


# === B2: closed-schema + strict boolean enforcement ===


class TestB2ClosedSchemaAndBooleanEnforcement:
    """B2: verify_promotion must reject unknown fields and enforce strict bool."""

    def test_verify_promotion_direct_unknown_field_rejected(self) -> None:
        """Unknown field passed directly to verify_promotion → REJECTED."""
        from cold_storage.release.promotion_record import verify_promotion

        record = OrderedDict(
            [
                ("schema_version", PROMOTION_RECORD_SCHEMA_VERSION),
                ("rc_version", RC_VERSION),
                ("source_environment", "ci"),
                ("target_environment", "staging"),
                ("final_image_digest", IMAGE),
                ("artifact_manifest_digest", "sha256:" + "c" * 64),
                ("provenance_digest", "sha256:" + "d" * 64),
                ("deployment_definition_digest", "sha256:" + "20" * 32),
                ("environment_config_digest", "sha256:" + "e" * 64),
                ("promoted_by", "ci-bot"),
                ("approved_by", "release-manager"),
                ("promotion_timestamp", "2026-08-06T13:00:00Z"),
                ("verification_result", "PASS"),
                ("evil_extra_field", "malicious"),
            ]
        )
        with pytest.raises(ReleaseEvidenceError) as exc:
            verify_promotion(
                record,
                rc_image_digest=IMAGE,
                rc_artifact_manifest_digest="sha256:" + "c" * 64,
                rc_provenance_digest="sha256:" + "d" * 64,
            )
        assert exc.value.failure_code == RC_PROMOTION_RECORD_UNVERIFIABLE

    def test_verify_promotion_against_bundle_unknown_field_rejected(self) -> None:
        """Unknown field via verify_promotion_against_bundle → REJECTED."""
        bundle = collect_release_candidate_evidence(
            build_a_inputs=_inputs(),
            build_b_inputs=_inputs(),
            build_a=_run(),
            build_b=_run(),
            artifacts=_artifacts(),
            test_result_reference="https://github.com/test/run/1",
            verification_result_reference="https://github.com/test/run/2",
            attestation=ATT,
        )
        promotion = OrderedDict(
            [
                ("schema_version", PROMOTION_RECORD_SCHEMA_VERSION),
                ("rc_version", RC_VERSION),
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
                ("evil_extra_field", "malicious"),
            ]
        )
        with pytest.raises(ReleaseEvidenceError) as exc:
            verify_promotion_against_bundle(bundle, promotion)
        assert exc.value.failure_code == RC_PROMOTION_RECORD_UNVERIFIABLE

    def test_rebuild_performed_false_accepts(self) -> None:
        """rebuild_performed=False → accepted."""
        from cold_storage.release.promotion_record import verify_promotion

        record = OrderedDict(
            [
                ("schema_version", PROMOTION_RECORD_SCHEMA_VERSION),
                ("rc_version", RC_VERSION),
                ("source_environment", "ci"),
                ("target_environment", "staging"),
                ("final_image_digest", IMAGE),
                ("artifact_manifest_digest", "sha256:" + "c" * 64),
                ("provenance_digest", "sha256:" + "d" * 64),
                ("deployment_definition_digest", "sha256:" + "20" * 32),
                ("environment_config_digest", "sha256:" + "e" * 64),
                ("rebuild_performed", False),
                ("promoted_by", "ci-bot"),
                ("approved_by", "release-manager"),
                ("promotion_timestamp", "2026-08-06T13:00:00Z"),
                ("verification_result", "PASS"),
            ]
        )
        verify_promotion(
            record,
            rc_image_digest=IMAGE,
            rc_artifact_manifest_digest="sha256:" + "c" * 64,
            rc_provenance_digest="sha256:" + "d" * 64,
        )

    def test_rebuild_performed_true_rejected(self) -> None:
        """rebuild_performed=True → RC_PROMOTION_REBUILD."""
        from cold_storage.release.promotion_record import verify_promotion

        record = OrderedDict(
            [
                ("schema_version", PROMOTION_RECORD_SCHEMA_VERSION),
                ("rc_version", RC_VERSION),
                ("source_environment", "ci"),
                ("target_environment", "staging"),
                ("final_image_digest", IMAGE),
                ("artifact_manifest_digest", "sha256:" + "c" * 64),
                ("provenance_digest", "sha256:" + "d" * 64),
                ("deployment_definition_digest", "sha256:" + "20" * 32),
                ("environment_config_digest", "sha256:" + "e" * 64),
                ("rebuild_performed", True),
                ("promoted_by", "ci-bot"),
                ("approved_by", "release-manager"),
                ("promotion_timestamp", "2026-08-06T13:00:00Z"),
                ("verification_result", "PASS"),
            ]
        )
        with pytest.raises(ReleaseEvidenceError) as exc:
            verify_promotion(
                record,
                rc_image_digest=IMAGE,
                rc_artifact_manifest_digest="sha256:" + "c" * 64,
                rc_provenance_digest="sha256:" + "d" * 64,
            )
        assert exc.value.failure_code == RC_PROMOTION_REBUILD

    def test_rebuild_performed_omitted_accepts(self) -> None:
        """Omitting rebuild_performed → accepted (defaults to no-rebuild)."""
        from cold_storage.release.promotion_record import verify_promotion

        record = OrderedDict(
            [
                ("schema_version", PROMOTION_RECORD_SCHEMA_VERSION),
                ("rc_version", RC_VERSION),
                ("source_environment", "ci"),
                ("target_environment", "staging"),
                ("final_image_digest", IMAGE),
                ("artifact_manifest_digest", "sha256:" + "c" * 64),
                ("provenance_digest", "sha256:" + "d" * 64),
                ("deployment_definition_digest", "sha256:" + "20" * 32),
                ("environment_config_digest", "sha256:" + "e" * 64),
                ("promoted_by", "ci-bot"),
                ("approved_by", "release-manager"),
                ("promotion_timestamp", "2026-08-06T13:00:00Z"),
                ("verification_result", "PASS"),
            ]
        )
        verify_promotion(
            record,
            rc_image_digest=IMAGE,
            rc_artifact_manifest_digest="sha256:" + "c" * 64,
            rc_provenance_digest="sha256:" + "d" * 64,
        )

    @pytest.mark.parametrize(
        "malformed_value",
        [0, 1, "false", "true", "", [], {}, None],
        ids=[
            "int0",
            "int1",
            "str_false",
            "str_true",
            "empty_str",
            "empty_list",
            "empty_dict",
            "none",
        ],
    )
    def test_rebuild_performed_malformed_type_rejected(self, malformed_value: object) -> None:
        """Non-bool rebuild_performed → RC_PROMOTION_RECORD_UNVERIFIABLE."""
        from cold_storage.release.promotion_record import verify_promotion

        record = OrderedDict(
            [
                ("schema_version", PROMOTION_RECORD_SCHEMA_VERSION),
                ("rc_version", RC_VERSION),
                ("source_environment", "ci"),
                ("target_environment", "staging"),
                ("final_image_digest", IMAGE),
                ("artifact_manifest_digest", "sha256:" + "c" * 64),
                ("provenance_digest", "sha256:" + "d" * 64),
                ("deployment_definition_digest", "sha256:" + "20" * 32),
                ("environment_config_digest", "sha256:" + "e" * 64),
                ("rebuild_performed", malformed_value),
                ("promoted_by", "ci-bot"),
                ("approved_by", "release-manager"),
                ("promotion_timestamp", "2026-08-06T13:00:00Z"),
                ("verification_result", "PASS"),
            ]
        )
        with pytest.raises(ReleaseEvidenceError) as exc:
            verify_promotion(
                record,
                rc_image_digest=IMAGE,
                rc_artifact_manifest_digest="sha256:" + "c" * 64,
                rc_provenance_digest="sha256:" + "d" * 64,
            )
        assert exc.value.failure_code == RC_PROMOTION_RECORD_UNVERIFIABLE


# === B3: per-run build input capture ===


class TestB3PerRunBuildInputCapture:
    """B3: collector must use independent per-run build input manifests."""

    def test_identical_inputs_passes(self) -> None:
        """Build A/B identical observed manifests → collector PASS."""
        bundle = collect_release_candidate_evidence(
            build_a_inputs=_inputs(),
            build_b_inputs=_inputs(),
            build_a=_run(),
            build_b=_run(),
            artifacts=_artifacts(),
            test_result_reference="https://github.com/test/run/1",
            verification_result_reference="https://github.com/test/run/2",
            attestation=ATT,
        )
        assert bundle.authoritative_image_digest == IMAGE

    def test_collector_input_drift_source_date_epoch_fails(self) -> None:
        """A and B identical digests but different source_date_epoch → FAIL.

        Build A and B have the same final_image_digest, same source_commit_sha,
        same base image, same lockfile, same build args, same platform —
        but Build A source_date_epoch=100 and Build B source_date_epoch=200.
        Each build's declared manifest digest matches its own observed inputs
        (Layer 1 passes), but the two observed manifests differ, so the
        collector must FAIL at the manifest-comparison step (Layer 2),
        proving the builds are not actually reproducible.
        """
        inputs_a = _inputs_custom(source_date_epoch=100)
        inputs_b = _inputs_custom(source_date_epoch=200)
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=inputs_a,
                build_b_inputs=inputs_b,
                build_a=_run(inputs=inputs_a),
                build_b=_run(inputs=inputs_b),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code in (
            "RC_BUILD_ARG_MISMATCH",
            "RC_FINAL_IMAGE_DIGEST_MISMATCH",
        )

    def test_collector_input_drift_dockerfile_digest_fails(self) -> None:
        """A and B identical digests but different dockerfile_digest → FAIL."""
        inputs_a = _inputs_custom()
        inputs_b = BuildInputs(
            source_commit_sha=COMMIT,
            source_tree_sha=TREE,
            source_date_epoch=1234567890,
            dockerfile_digest="sha256:" + "99" * 32,
            compose_file_digest="sha256:" + "11" * 32,
            workflow_definition_digest="sha256:" + "12" * 32,
            dependency_lockset_digest=LOCK,
            migration_set_digest="sha256:" + "13" * 32,
            base_image_digest_set=[BASE],
            build_args={
                "COLD_STORAGE_BUILD_COMMIT_SHA": COMMIT,
                "COLD_STORAGE_BUILD_VERSION": "v0.2.0",
            },
            oci_exporter={"type": "oci", "rewrite-timestamp": "true"},
        )
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=inputs_a,
                build_b_inputs=inputs_b,
                build_a=_run(inputs=inputs_a),
                build_b=_run(inputs=inputs_b),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code in (
            "RC_BUILD_ARG_MISMATCH",
            "RC_FINAL_IMAGE_DIGEST_MISMATCH",
        )

    def test_build_a_manifest_declared_digest_matching_passes(self) -> None:
        """Build A declared manifest digest matches observed manifest → PASS.

        Renamed from ``test_build_a_manifest_declared_digest_tampered_fails``
        (R2): that test name claimed a tamper/fail but actually exercised the
        positive case with no ``pytest.raises``.  The true tamper negatives
        are now covered by ``test_collector_rejects_build_a_tampered_declared_manifest_digest``
        and ``test_collector_rejects_build_b_tampered_declared_manifest_digest``
        below, which route a BAD declared digest through the full public
        ``collect_release_candidate_evidence`` entry point.
        """
        inputs_a = _inputs_custom(source_date_epoch=100)
        bundle = collect_release_candidate_evidence(
            build_a_inputs=inputs_a,
            build_b_inputs=inputs_a,
            build_a=_run(inputs=inputs_a),
            build_b=_run(inputs=inputs_a),
            artifacts=_artifacts(),
            test_result_reference="https://github.com/test/run/1",
            verification_result_reference="https://github.com/test/run/2",
            attestation=ATT,
        )
        assert bundle.authoritative_image_digest == IMAGE

    def test_collector_rejects_build_a_tampered_declared_manifest_digest(self) -> None:
        """Build A declared digest = BAD, Build A observed manifest = GOOD → FAIL.

        R3 hard gate (Case A): Build A's declared ``build_input_manifest_digest``
        is tampered to a wrong value while its observed input manifest is
        canonical-good.  Build B is completely normal.  The public collector
        ``collect_release_candidate_evidence`` must FAIL because the declared
        digest does not match the recomputed canonical digest of Build A's
        observed inputs (Layer 1 violation).
        """
        inputs = _inputs()
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=inputs,
                build_b_inputs=inputs,
                build_a=_run(inputs=inputs, declared_manifest_digest="sha256:" + "0" * 64),
                build_b=_run(inputs=inputs),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISMATCH

    def test_collector_rejects_build_b_tampered_declared_manifest_digest(self) -> None:
        """Build B declared digest = BAD, Build B observed manifest = GOOD → FAIL.

        R3 hard gate (Case B): symmetric to Case A — Build B's declared
        ``build_input_manifest_digest`` is tampered while Build A is normal.
        The public collector must FAIL (Layer 1 violation on Build B).
        """
        inputs = _inputs()
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=inputs,
                build_b_inputs=inputs,
                build_a=_run(inputs=inputs),
                build_b=_run(inputs=inputs, declared_manifest_digest="sha256:" + "0" * 64),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISMATCH

    def test_expected_inputs_mismatch_fails(self) -> None:
        """Expected inputs differ from observed → collector FAIL (Layer 3)."""
        expected = _inputs_custom(source_date_epoch=999)
        observed = _inputs_custom(source_date_epoch=100)
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=observed,
                build_b_inputs=observed,
                build_a=_run(inputs=observed),
                build_b=_run(inputs=observed),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
                expected_inputs=expected,
            )
        assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISMATCH


# === B4: declared↔actual digest binding in collector ===


def _run_custom(
    *,
    digest: str = IMAGE,
    local_oci: str | None = None,
    registry: str | None = None,
    inputs: BuildInputs | None = None,
    declared_manifest_digest: str | None = None,
) -> BuildRunRecord:
    used_inputs = inputs if inputs is not None else _inputs()
    declared = (
        declared_manifest_digest
        if declared_manifest_digest is not None
        else _declared_manifest_digest(used_inputs)
    )
    return BuildRunRecord(
        build_run_id="run-1",
        build_run_attempt=1,
        build_trigger="push",
        builder_identity="runner-1.github-actions.us-east-1",
        build_started_at="2026-08-06T12:00:00Z",
        build_finished_at="2026-08-06T12:05:00Z",
        final_image_digest=digest,
        local_oci_manifest_digest=local_oci if local_oci is not None else digest,
        registry_manifest_digest=registry,
        base_image_tag="python:3.12-slim",
        base_image_digest=BASE,
        lockfile_digest=LOCK,
        build_input_manifest_digest=declared,
    )


class TestB4DigestBindingChainInCollector:
    """B4: collector must enforce continuous declared↔actual digest binding."""

    def test_case1_a_recorded_not_a_actual_fails(self) -> None:
        """Build A recorded digest != Build A actual → FAIL."""
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=_inputs(),
                build_b_inputs=_inputs(),
                build_a=_run_custom(digest=IMAGE, local_oci="sha256:" + "x" * 64),
                build_b=_run(),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISMATCH

    def test_case2_b_recorded_not_b_actual_fails(self) -> None:
        """Build B recorded digest != Build B actual → FAIL."""
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=_inputs(),
                build_b_inputs=_inputs(),
                build_a=_run(),
                build_b=_run_custom(digest=IMAGE, local_oci="sha256:" + "x" * 64),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISMATCH

    def test_case3_a_actual_not_b_actual_fails(self) -> None:
        """Build A actual digest != Build B actual → FAIL."""
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=_inputs(),
                build_b_inputs=_inputs(),
                build_a=_run_custom(
                    digest="sha256:" + "a" * 64,
                    local_oci="sha256:" + "a" * 64,
                ),
                build_b=_run_custom(
                    digest="sha256:" + "b" * 64,
                    local_oci="sha256:" + "b" * 64,
                ),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISMATCH

    def test_case4_a_local_not_a_registry_fails(self) -> None:
        """Build A local OCI != Build A registry → FAIL."""
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=_inputs(),
                build_b_inputs=_inputs(),
                build_a=_run_custom(
                    digest=IMAGE,
                    local_oci=IMAGE,
                    registry="sha256:" + "r" * 64,
                ),
                build_b=_run(),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code == RC_REGISTRY_DIGEST_MISMATCH

    def test_case5_b_local_not_b_registry_fails(self) -> None:
        """Build B local OCI != Build B registry → FAIL."""
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=_inputs(),
                build_b_inputs=_inputs(),
                build_a=_run(),
                build_b=_run_custom(
                    digest=IMAGE,
                    local_oci=IMAGE,
                    registry="sha256:" + "r" * 64,
                ),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code == RC_REGISTRY_DIGEST_MISMATCH

    def test_case6_all_matching_passes(self) -> None:
        """A recorded = A actual = B recorded = B actual = authoritative → PASS."""
        bundle = collect_release_candidate_evidence(
            build_a_inputs=_inputs(),
            build_b_inputs=_inputs(),
            build_a=_run(),
            build_b=_run(),
            artifacts=_artifacts(),
            test_result_reference="https://github.com/test/run/1",
            verification_result_reference="https://github.com/test/run/2",
            attestation=ATT,
        )
        assert bundle.authoritative_image_digest == IMAGE

    def test_case7_tampered_provenance_subject_fails(self) -> None:
        """Tampered provenance subject digest != authoritative → verify_evidence_bundle FAIL."""
        bundle = collect_release_candidate_evidence(
            build_a_inputs=_inputs(),
            build_b_inputs=_inputs(),
            build_a=_run(),
            build_b=_run(),
            artifacts=_artifacts(),
            test_result_reference="https://github.com/test/run/1",
            verification_result_reference="https://github.com/test/run/2",
            attestation=ATT,
        )
        # Tamper with the provenance subject digest
        bundle.provenance["subject_final_image_digest"] = "sha256:" + "x" * 64
        with pytest.raises(ReleaseEvidenceError) as exc:
            verify_evidence_bundle(bundle)
        assert exc.value.failure_code == "RC_PROVENANCE_SUBJECT_MISMATCH"

    def test_case8_promotion_digest_not_authoritative_fails(self) -> None:
        """Promotion final_image_digest != authoritative RC → FAIL."""
        bundle = collect_release_candidate_evidence(
            build_a_inputs=_inputs(),
            build_b_inputs=_inputs(),
            build_a=_run(),
            build_b=_run(),
            artifacts=_artifacts(),
            test_result_reference="https://github.com/test/run/1",
            verification_result_reference="https://github.com/test/run/2",
            attestation=ATT,
        )
        promotion = OrderedDict(
            [
                ("schema_version", PROMOTION_RECORD_SCHEMA_VERSION),
                ("rc_version", RC_VERSION),
                ("source_environment", "ci"),
                ("target_environment", "staging"),
                ("final_image_digest", "sha256:" + "z" * 64),
                ("artifact_manifest_digest", bundle.artifact_manifest_digest),
                ("provenance_digest", bundle.provenance_digest),
                ("deployment_definition_digest", "sha256:" + "20" * 32),
                ("environment_config_digest", "sha256:" + "e" * 64),
                ("rebuild_performed", False),
                ("promoted_by", "ci-bot"),
                ("approved_by", "release-manager"),
                ("promotion_timestamp", "2026-08-06T13:00:00Z"),
                ("verification_result", "PASS"),
            ]
        )
        with pytest.raises(ReleaseEvidenceError):
            verify_promotion_against_bundle(bundle, promotion)

    def test_x_y_z_collector_negative(self) -> None:
        """X=fake recorded, Y=Build A actual, Z=Build B actual (all different) → FAIL.

        Construct Build A recorded=X, Build B recorded=X, Build A actual=Y,
        Build B actual=Z, where X != Y, Y != Z.  The collector must FAIL
        because the recorded digests don't match the actual OCI digests.
        """
        x = "sha256:" + "a" * 64  # fake recorded digest
        y = "sha256:" + "b" * 64  # Build A actual
        z = "sha256:" + "c" * 64  # Build B actual
        with pytest.raises(ReleaseEvidenceError) as exc:
            collect_release_candidate_evidence(
                build_a_inputs=_inputs(),
                build_b_inputs=_inputs(),
                build_a=_run_custom(digest=x, local_oci=y),
                build_b=_run_custom(digest=x, local_oci=z),
                artifacts=_artifacts(),
                test_result_reference="https://github.com/test/run/1",
                verification_result_reference="https://github.com/test/run/2",
                attestation=ATT,
            )
        assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISMATCH
