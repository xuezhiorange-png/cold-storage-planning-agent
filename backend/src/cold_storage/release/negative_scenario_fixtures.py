"""Negative-scenario fixtures (NR-01 … NR-20).

Each fixture returns a :class:`NegativeScenario` whose ``run`` callable
exercises a release-evidence verifier with a crafted bad input and
raises the matching ``RC_*`` :class:`ReleaseEvidenceError`.  The frozen
coverage matrix (Section 12.21) maps every NR to exactly one fixture and
one error code; no requirement is uncovered and no fixture is redundant.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cold_storage.release.artifact_manifest import (
    build_manifest,
    load_manifest_from_text,
    verify_manifest_digest,
)
from cold_storage.release.digest_verifier import (
    verify_registry_digest,
    verify_reproducible_build,
)
from cold_storage.release.promotion_record import (
    verify_promotion,
)
from cold_storage.release.provenance_schema import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    EXPECTED_SOURCE_COMMIT_SHA,
    EXPECTED_SOURCE_REPOSITORY,
    EXPECTED_SOURCE_TREE_SHA,
    PROMOTION_RECORD_SCHEMA_VERSION,
    PROVENANCE_SCHEMA_VERSION,
    RC_VERSION,
)
from cold_storage.release.provenance_statement import (
    build_provenance,
    verify_provenance,
)

IMAGE_DIGEST = "sha256:" + "a" * 64
IMAGE_DIGEST_B = "sha256:" + "b" * 64
ARTIFACT_DIGEST = "sha256:" + "c" * 64
PROVENANCE_DIGEST = "sha256:" + "d" * 64
ENV_CONFIG_DIGEST = "sha256:" + "e" * 64
BASE_DIGEST = "sha256:" + "f" * 64
LOCKFILE_DIGEST = "sha256:" + "1" * 64


def _valid_attestation() -> dict[str, str]:
    """Return a fresh copy of the valid attestation fixture."""
    return {
        "mechanism": "github_oidc",
        "binding": "eyJhbGciOiJIUzI1NiJ9.payload.signature",
        "issuer": "https://token.actions.githubusercontent.com",
    }


@dataclass
class NegativeScenario:
    """A single frozen negative scenario."""

    nr_id: str
    fixture_id: str
    expected_error_code: str
    expected_stage: str
    run: Callable[[], None]


# ---------------------------------------------------------------------------
# Valid baseline builders (mutated by individual fixtures)
# ---------------------------------------------------------------------------


def _valid_build_record(*, commit: str = EXPECTED_SOURCE_COMMIT_SHA) -> OrderedDict[str, Any]:
    from cold_storage.release.digest_verifier import compute_build_input_manifest_digest

    rec = OrderedDict(
        [
            ("source_commit_sha", commit),
            ("base_image_tag", "python:3.12-slim"),
            ("base_image_digest", BASE_DIGEST),
            ("lockfile_digest", LOCKFILE_DIGEST),
            (
                "build_args",
                {"COLD_STORAGE_BUILD_COMMIT_SHA": commit, "COLD_STORAGE_BUILD_VERSION": "v0.2.0"},
            ),
            ("build_platform", "ubuntu-latest"),
            ("final_image_digest", IMAGE_DIGEST),
            ("build_input_manifest_digest", ""),
        ]
    )
    rec["build_input_manifest_digest"] = compute_build_input_manifest_digest(rec)
    return rec


def _valid_manifest_fields() -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("schema_version", ARTIFACT_MANIFEST_SCHEMA_VERSION),
            ("rc_version", RC_VERSION),
            ("source_commit_sha", EXPECTED_SOURCE_COMMIT_SHA),
            ("source_tree_sha", EXPECTED_SOURCE_TREE_SHA),
            ("dockerfile_digest", "sha256:" + "10" * 32),
            ("compose_file_digest", "sha256:" + "11" * 32),
            ("workflow_definition_digest", "sha256:" + "12" * 32),
            ("dependency_lockset_digest", LOCKFILE_DIGEST),
            ("migration_set_digest", "sha256:" + "13" * 32),
            ("final_image_digest", IMAGE_DIGEST),
            ("sbom_digest", ""),
            ("provenance_digest", PROVENANCE_DIGEST),
            ("test_result_reference", "https://github.com/test/run/1"),
            ("verification_result_reference", "https://github.com/test/run/2"),
            ("generator_tool", "cold-storage.release.evidence_collector:v0.2.0-slice2-r1"),
            (
                "artifacts",
                [{"relative_path": "backend/Dockerfile", "size_bytes": 100, "sha256": "x"}],
            ),
        ]
    )


def _valid_provenance_fields() -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("schema_version", PROVENANCE_SCHEMA_VERSION),
            ("subject_final_image_digest", IMAGE_DIGEST),
            ("subject_artifact_manifest_digest", ARTIFACT_DIGEST),
            ("source_repository", EXPECTED_SOURCE_REPOSITORY),
            ("source_commit_sha", EXPECTED_SOURCE_COMMIT_SHA),
            ("source_tree_sha", EXPECTED_SOURCE_TREE_SHA),
            ("build_workflow_identity", "ci"),
            ("build_workflow_ref", "refs/heads/main"),
            ("build_run_id", "run-1"),
            ("build_run_attempt", 1),
            ("build_trigger", "push"),
            ("builder_identity", "runner-1.github-actions.us-east-1"),
            ("build_platform", "ubuntu-latest"),
            ("build_definition_digest", "sha256:" + "12" * 32),
            ("dependency_lockset_digest", LOCKFILE_DIGEST),
            ("base_image_digest_set", [BASE_DIGEST]),
            ("build_input_manifest_digest", "sha256:" + "0" * 64),
            ("build_started_at", "2026-08-06T12:00:00Z"),
            ("build_finished_at", "2026-08-06T12:05:00Z"),
            ("reproducible_build_result", "PASS"),
            ("provenance_digest", PROVENANCE_DIGEST),
            ("attestation", _valid_attestation()),
        ]
    )


def _valid_promotion_record() -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("schema_version", PROMOTION_RECORD_SCHEMA_VERSION),
            ("rc_version", RC_VERSION),
            ("source_environment", "ci"),
            ("target_environment", "staging"),
            ("final_image_digest", IMAGE_DIGEST),
            ("artifact_manifest_digest", ARTIFACT_DIGEST),
            ("provenance_digest", PROVENANCE_DIGEST),
            ("deployment_definition_digest", "sha256:" + "20" * 32),
            ("environment_config_digest", ENV_CONFIG_DIGEST),
            ("rebuild_performed", False),
            ("promoted_by", "ci-bot"),
            ("approved_by", "release-manager"),
            ("promotion_timestamp", "2026-08-06T13:00:00Z"),
            ("verification_result", "PASS"),
        ]
    )


# ---------------------------------------------------------------------------
# NR-01 … NR-07: build / registry stage
# ---------------------------------------------------------------------------


def _nr01() -> NegativeScenario:
    def run() -> None:
        a = _valid_build_record()
        b = _valid_build_record(commit="0" * 40)
        verify_reproducible_build(a, b)

    return NegativeScenario(
        "NR-01", "NEG-01-DIFFERENT_COMMIT", "RC_SOURCE_COMMIT_MISMATCH", "BUILD", run
    )


def _nr02() -> NegativeScenario:
    def run() -> None:
        a = _valid_build_record()
        b = _valid_build_record()
        b["base_image_digest"] = "sha256:" + "9" * 64
        verify_reproducible_build(a, b)

    return NegativeScenario(
        "NR-02", "NEG-02-BASE_IMAGE_DIGEST_DRIFT", "RC_BASE_IMAGE_DIGEST_MISMATCH", "BUILD", run
    )


def _nr03() -> NegativeScenario:
    def run() -> None:
        a = _valid_build_record()
        b = _valid_build_record()
        b["lockfile_digest"] = "sha256:" + "8" * 64
        verify_reproducible_build(a, b)

    return NegativeScenario(
        "NR-03", "NEG-03-LOCKFILE_DIGEST_MISMATCH", "RC_LOCKFILE_DIGEST_MISMATCH", "BUILD", run
    )


def _nr04() -> NegativeScenario:
    def run() -> None:
        a = _valid_build_record()
        b = _valid_build_record()
        b["build_args"] = {
            "COLD_STORAGE_BUILD_COMMIT_SHA": EXPECTED_SOURCE_COMMIT_SHA,
            "COLD_STORAGE_BUILD_VERSION": "v0.2.1",
        }
        verify_reproducible_build(a, b)

    return NegativeScenario(
        "NR-04", "NEG-04-BUILD_ARG_MISMATCH", "RC_BUILD_ARG_MISMATCH", "BUILD", run
    )


def _nr05() -> NegativeScenario:
    def run() -> None:
        a = _valid_build_record()
        b = _valid_build_record()
        b["final_image_digest"] = IMAGE_DIGEST_B
        verify_reproducible_build(a, b)

    return NegativeScenario(
        "NR-05",
        "NEG-05-FINAL_IMAGE_DIGEST_MISMATCH",
        "RC_FINAL_IMAGE_DIGEST_MISMATCH",
        "BUILD",
        run,
    )


def _nr06() -> NegativeScenario:
    def run() -> None:
        a = _valid_build_record()
        b = _valid_build_record()
        b["final_image_digest"] = None
        verify_reproducible_build(a, b)

    return NegativeScenario(
        "NR-06", "NEG-06-FINAL_IMAGE_DIGEST_MISSING", "RC_FINAL_IMAGE_DIGEST_MISSING", "BUILD", run
    )


def _nr07() -> NegativeScenario:
    def run() -> None:
        verify_registry_digest(
            local_oci_manifest_digest=IMAGE_DIGEST,
            registry_manifest_digest=IMAGE_DIGEST_B,
        )

    return NegativeScenario(
        "NR-07", "NEG-07-REGISTRY_DIGEST_MISMATCH", "RC_REGISTRY_DIGEST_MISMATCH", "REGISTRY", run
    )


# ---------------------------------------------------------------------------
# NR-08 … NR-10: artifact stage
# ---------------------------------------------------------------------------


def _nr08() -> NegativeScenario:
    def run() -> None:
        from cold_storage.release.artifact_manifest import load_manifest_from_path

        load_manifest_from_path("/nonexistent/manifest.json")

    return NegativeScenario(
        "NR-08", "NEG-08-ARTIFACT_MANIFEST_MISSING", "RC_ARTIFACT_MANIFEST_MISSING", "ARTIFACT", run
    )


def _nr09() -> NegativeScenario:
    def run() -> None:
        # Same key twice -> duplicate key rejection.
        raw = '{"schema_version":"x","schema_version":"y"}'
        load_manifest_from_text(raw)

    return NegativeScenario(
        "NR-09", "NEG-09-ARTIFACT_DUPLICATE_KEY", "RC_ARTIFACT_DUPLICATE_KEY", "ARTIFACT", run
    )


def _nr10() -> NegativeScenario:
    def run() -> None:
        manifest = build_manifest(_valid_manifest_fields())
        verify_manifest_digest(manifest, "sha256:" + "0" * 64)

    return NegativeScenario(
        "NR-10", "NEG-10-ARTIFACT_DIGEST_MISMATCH", "RC_ARTIFACT_DIGEST_MISMATCH", "ARTIFACT", run
    )


# ---------------------------------------------------------------------------
# NR-11 … NR-14: provenance stage
# ---------------------------------------------------------------------------


def _nr11() -> NegativeScenario:
    def run() -> None:
        fields = _valid_provenance_fields()
        fields["attestation"] = {}
        prov = build_provenance(fields)
        verify_provenance(
            prov,
            expected_image_digest=IMAGE_DIGEST,
            expected_artifact_manifest_digest=ARTIFACT_DIGEST,
        )

    return NegativeScenario(
        "NR-11", "NEG-11-PROVENANCE_UNSIGNED", "RC_PROVENANCE_UNSIGNED", "PROVENANCE", run
    )


def _nr12() -> NegativeScenario:
    def run() -> None:
        fields = _valid_provenance_fields()
        fields["source_repository"] = "evil/repo"
        prov = build_provenance(fields)
        verify_provenance(
            prov,
            expected_image_digest=IMAGE_DIGEST,
            expected_artifact_manifest_digest=ARTIFACT_DIGEST,
        )

    return NegativeScenario(
        "NR-12", "NEG-12-PROVENANCE_REPO_MISMATCH", "RC_PROVENANCE_REPO_MISMATCH", "PROVENANCE", run
    )


def _nr13() -> NegativeScenario:
    def run() -> None:
        fields = _valid_provenance_fields()
        fields["build_workflow_identity"] = "evil-ci"
        prov = build_provenance(fields)
        verify_provenance(
            prov,
            expected_image_digest=IMAGE_DIGEST,
            expected_artifact_manifest_digest=ARTIFACT_DIGEST,
        )

    return NegativeScenario(
        "NR-13",
        "NEG-13-PROVENANCE_WORKFLOW_MISMATCH",
        "RC_PROVENANCE_WORKFLOW_MISMATCH",
        "PROVENANCE",
        run,
    )


def _nr14() -> NegativeScenario:
    def run() -> None:
        fields = _valid_provenance_fields()
        fields["subject_final_image_digest"] = IMAGE_DIGEST_B
        prov = build_provenance(fields)
        verify_provenance(
            prov,
            expected_image_digest=IMAGE_DIGEST,
            expected_artifact_manifest_digest=ARTIFACT_DIGEST,
        )

    return NegativeScenario(
        "NR-14",
        "NEG-14-PROVENANCE_SUBJECT_MISMATCH",
        "RC_PROVENANCE_SUBJECT_MISMATCH",
        "PROVENANCE",
        run,
    )


# ---------------------------------------------------------------------------
# NR-15 … NR-20: promotion stage
# ---------------------------------------------------------------------------


def _nr15() -> NegativeScenario:
    def run() -> None:
        record = _valid_promotion_record()
        record["final_image_digest"] = "cold-storage-backend:latest"
        verify_promotion(
            record,
            rc_image_digest=IMAGE_DIGEST,
            rc_artifact_manifest_digest=ARTIFACT_DIGEST,
            rc_provenance_digest=PROVENANCE_DIGEST,
        )

    return NegativeScenario(
        "NR-15", "NEG-15-PROMOTION_MUTABLE_TAG", "RC_PROMOTION_MUTABLE_TAG", "PROMOTION", run
    )


def _nr16() -> NegativeScenario:
    def run() -> None:
        record = _valid_promotion_record()
        record["rebuild_performed"] = True
        verify_promotion(
            record,
            rc_image_digest=IMAGE_DIGEST,
            rc_artifact_manifest_digest=ARTIFACT_DIGEST,
            rc_provenance_digest=PROVENANCE_DIGEST,
        )

    return NegativeScenario(
        "NR-16", "NEG-16-PROMOTION_REBUILD", "RC_PROMOTION_REBUILD", "PROMOTION", run
    )


def _nr17() -> NegativeScenario:
    def run() -> None:
        record = _valid_promotion_record()
        record["source_environment"] = "staging"
        record["target_environment"] = "production"
        verify_promotion(
            record,
            rc_image_digest=IMAGE_DIGEST_B,  # drift vs RC identity
            rc_artifact_manifest_digest=ARTIFACT_DIGEST,
            rc_provenance_digest=PROVENANCE_DIGEST,
            prior_environment_digest=IMAGE_DIGEST_B,
        )

    return NegativeScenario(
        "NR-17", "NEG-17-PROMOTION_DIGEST_DRIFT", "RC_PROMOTION_DIGEST_DRIFT", "PROMOTION", run
    )


def _nr18() -> NegativeScenario:
    def run() -> None:
        record = _valid_promotion_record()
        record["environment_config_digest"] = ""
        verify_promotion(
            record,
            rc_image_digest=IMAGE_DIGEST,
            rc_artifact_manifest_digest=ARTIFACT_DIGEST,
            rc_provenance_digest=PROVENANCE_DIGEST,
        )

    return NegativeScenario(
        "NR-18",
        "NEG-18-ENV_CONFIG_DIGEST_MISSING",
        "RC_ENV_CONFIG_DIGEST_MISSING",
        "PROMOTION",
        run,
    )


def _nr19() -> NegativeScenario:
    def run() -> None:
        record = _valid_promotion_record()
        record["approved_by"] = "ci-bot"  # self-approval
        verify_promotion(
            record,
            rc_image_digest=IMAGE_DIGEST,
            rc_artifact_manifest_digest=ARTIFACT_DIGEST,
            rc_provenance_digest=PROVENANCE_DIGEST,
        )

    return NegativeScenario(
        "NR-19", "NEG-19-APPROVER_MISSING", "RC_APPROVER_MISSING", "PROMOTION", run
    )


def _nr20() -> NegativeScenario:
    def run() -> None:
        record = _valid_promotion_record()
        record["verification_result"] = "FAIL"
        verify_promotion(
            record,
            rc_image_digest=IMAGE_DIGEST,
            rc_artifact_manifest_digest=ARTIFACT_DIGEST,
            rc_provenance_digest=PROVENANCE_DIGEST,
        )

    return NegativeScenario(
        "NR-20",
        "NEG-20-PROMOTION_RECORD_UNVERIFIABLE",
        "RC_PROMOTION_RECORD_UNVERIFIABLE",
        "PROMOTION",
        run,
    )


_FIXTURE_BUILDERS: tuple[Callable[[], NegativeScenario], ...] = (
    _nr01,
    _nr02,
    _nr03,
    _nr04,
    _nr05,
    _nr06,
    _nr07,
    _nr08,
    _nr09,
    _nr10,
    _nr11,
    _nr12,
    _nr13,
    _nr14,
    _nr15,
    _nr16,
    _nr17,
    _nr18,
    _nr19,
    _nr20,
)


def all_negative_scenarios() -> list[NegativeScenario]:
    """Return all 20 frozen negative scenarios in NR order."""
    return [builder() for builder in _FIXTURE_BUILDERS]


__all__ = [
    "NegativeScenario",
    "all_negative_scenarios",
]
