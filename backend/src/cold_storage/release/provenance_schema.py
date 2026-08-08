"""Frozen schema constants and trust boundaries for release-candidate evidence.

This module owns the single source of truth for the schema version strings,
the allowed repository / workflow / ref / issuer values, and the full
``RC_*`` error-code table frozen in the Slice 2 R1 contract.  Every other
release module imports these constants so that there is exactly one
definition of each frozen value.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Schema version strings (frozen)
# ---------------------------------------------------------------------------

ARTIFACT_MANIFEST_SCHEMA_VERSION = "cold-storage-release-candidate-artifact-manifest-v1"
PROVENANCE_SCHEMA_VERSION = "cold-storage-release-candidate-provenance-v1"
PROMOTION_RECORD_SCHEMA_VERSION = "cold-storage-release-candidate-promotion-record-v1"

# ---------------------------------------------------------------------------
# RC identity tuple (frozen)
# ---------------------------------------------------------------------------

RC_VERSION = "v0.2.0"
EXPECTED_SOURCE_REPOSITORY = "xuezhiorange-png/cold-storage-planning-agent"
EXPECTED_SOURCE_COMMIT_SHA = "25a88f0b65fa7662310701563e306331034d6c34"
EXPECTED_SOURCE_TREE_SHA = "274e84af01bd895a30571423283838017aacd45f"

EXPECTED_WORKFLOW_IDENTITY = "ci"
# push-triggered RC must originate from main; PR-merge refs are NOT acceptable
# for an RC.
ALLOWED_WORKFLOW_REFS = frozenset({"refs/heads/main"})
EXPECTED_BUILD_PLATFORM = "ubuntu-latest"
EXPECTED_OIDC_ISSUER = "https://token.actions.githubusercontent.com"

#: Allowed promotion environment sequence edges.
ALLOWED_PROMOTION_EDGES = frozenset(
    {
        ("ci", "staging"),
        ("staging", "production"),
    }
)
ALLOWED_ENVIRONMENTS = frozenset({"ci", "staging", "production"})

# ---------------------------------------------------------------------------
# Error code table (Section 11.2 of the frozen contract)
# ---------------------------------------------------------------------------

RC_SOURCE_COMMIT_MISMATCH = "RC_SOURCE_COMMIT_MISMATCH"
RC_BASE_IMAGE_DIGEST_MISMATCH = "RC_BASE_IMAGE_DIGEST_MISMATCH"
RC_LOCKFILE_DIGEST_MISMATCH = "RC_LOCKFILE_DIGEST_MISMATCH"
RC_BUILD_ARG_MISMATCH = "RC_BUILD_ARG_MISMATCH"
RC_FINAL_IMAGE_DIGEST_MISMATCH = "RC_FINAL_IMAGE_DIGEST_MISMATCH"
RC_FINAL_IMAGE_DIGEST_MISSING = "RC_FINAL_IMAGE_DIGEST_MISSING"
RC_REGISTRY_DIGEST_MISMATCH = "RC_REGISTRY_DIGEST_MISMATCH"
RC_ARTIFACT_MANIFEST_MISSING = "RC_ARTIFACT_MANIFEST_MISSING"
RC_ARTIFACT_DUPLICATE_KEY = "RC_ARTIFACT_DUPLICATE_KEY"
RC_ARTIFACT_DIGEST_MISMATCH = "RC_ARTIFACT_DIGEST_MISMATCH"
RC_PROVENANCE_UNSIGNED = "RC_PROVENANCE_UNSIGNED"
RC_PROVENANCE_REPO_MISMATCH = "RC_PROVENANCE_REPO_MISMATCH"
RC_PROVENANCE_WORKFLOW_MISMATCH = "RC_PROVENANCE_WORKFLOW_MISMATCH"
RC_PROVENANCE_SUBJECT_MISMATCH = "RC_PROVENANCE_SUBJECT_MISMATCH"
RC_PROMOTION_MUTABLE_TAG = "RC_PROMOTION_MUTABLE_TAG"
RC_PROMOTION_REBUILD = "RC_PROMOTION_REBUILD"
RC_PROMOTION_DIGEST_DRIFT = "RC_PROMOTION_DIGEST_DRIFT"
RC_ENV_CONFIG_DIGEST_MISSING = "RC_ENV_CONFIG_DIGEST_MISSING"
RC_APPROVER_MISSING = "RC_APPROVER_MISSING"
RC_PROMOTION_RECORD_UNVERIFIABLE = "RC_PROMOTION_RECORD_UNVERIFIABLE"

#: All 20 frozen error codes — used by the architecture test to assert that
#: every code is exercised by exactly one negative-scenario fixture.
ALL_ERROR_CODES: tuple[str, ...] = (
    RC_SOURCE_COMMIT_MISMATCH,
    RC_BASE_IMAGE_DIGEST_MISMATCH,
    RC_LOCKFILE_DIGEST_MISMATCH,
    RC_BUILD_ARG_MISMATCH,
    RC_FINAL_IMAGE_DIGEST_MISMATCH,
    RC_FINAL_IMAGE_DIGEST_MISSING,
    RC_REGISTRY_DIGEST_MISMATCH,
    RC_ARTIFACT_MANIFEST_MISSING,
    RC_ARTIFACT_DUPLICATE_KEY,
    RC_ARTIFACT_DIGEST_MISMATCH,
    RC_PROVENANCE_UNSIGNED,
    RC_PROVENANCE_REPO_MISMATCH,
    RC_PROVENANCE_WORKFLOW_MISMATCH,
    RC_PROVENANCE_SUBJECT_MISMATCH,
    RC_PROMOTION_MUTABLE_TAG,
    RC_PROMOTION_REBUILD,
    RC_PROMOTION_DIGEST_DRIFT,
    RC_ENV_CONFIG_DIGEST_MISSING,
    RC_APPROVER_MISSING,
    RC_PROMOTION_RECORD_UNVERIFIABLE,
)

# ---------------------------------------------------------------------------
# Deterministic field orders (frozen)
# ---------------------------------------------------------------------------

ARTIFACT_MANIFEST_FIELD_ORDER: tuple[str, ...] = (
    "schema_version",
    "rc_version",
    "source_commit_sha",
    "source_tree_sha",
    "dockerfile_digest",
    "compose_file_digest",
    "workflow_definition_digest",
    "dependency_lockset_digest",
    "migration_set_digest",
    "final_image_digest",
    "sbom_digest",
    "provenance_digest",
    "test_result_reference",
    "verification_result_reference",
    "generator_tool",
    "artifacts",
)

PROVENANCE_FIELD_ORDER: tuple[str, ...] = (
    "schema_version",
    "subject_final_image_digest",
    "subject_artifact_manifest_digest",
    "source_repository",
    "source_commit_sha",
    "source_tree_sha",
    "build_workflow_identity",
    "build_workflow_ref",
    "build_run_id",
    "build_run_attempt",
    "build_trigger",
    "builder_identity",
    "build_platform",
    "build_definition_digest",
    "dependency_lockset_digest",
    "base_image_digest_set",
    "build_input_manifest_digest",
    "build_started_at",
    "build_finished_at",
    "reproducible_build_result",
    "provenance_digest",
    "attestation",
)

PROMOTION_RECORD_FIELD_ORDER: tuple[str, ...] = (
    "schema_version",
    "rc_version",
    "source_environment",
    "target_environment",
    "final_image_digest",
    "artifact_manifest_digest",
    "provenance_digest",
    "deployment_definition_digest",
    "environment_config_digest",
    "rebuild_performed",
    "promoted_by",
    "approved_by",
    "promotion_timestamp",
    "verification_result",
)


class ProvenanceSchemaError(Exception):
    """Raised for schema-level trust-boundary violations.

    Kept separate from :class:`canonical_serialization.ReleaseEvidenceError`
    so that callers that only need constants do not pull in the error
    hierarchy; concrete verifiers re-raise as ``RC_*`` codes.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail or code)
