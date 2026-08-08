"""Evidence collector — orchestrates the release-candidate evidence pipeline.

Ties together reproducible-build verification, artifact-manifest
generation, provenance-statement generation, and promotion-record
verification into a single :func:`collect_release_candidate_evidence`
entry point and a :func:`verify_evidence_bundle` verifier.

This round produces *code and synthetic verification* only.  Live
evidence execution (real registry push, GitHub OIDC signing, environment
approval) requires separate authorization.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from cold_storage.release.artifact_manifest import (
    build_manifest,
    compute_manifest_digest,
    verify_manifest_digest,
)
from cold_storage.release.canonical_serialization import (
    reject_secret_values,
)
from cold_storage.release.digest_verifier import (
    authoritative_image_digest,
    verify_reproducible_build,
)
from cold_storage.release.promotion_record import (
    verify_promotion,
)
from cold_storage.release.provenance_schema import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    EXPECTED_BUILD_PLATFORM,
    EXPECTED_SOURCE_REPOSITORY,
    PROVENANCE_SCHEMA_VERSION,
    RC_VERSION,
)
from cold_storage.release.provenance_statement import (
    ProvenanceError,
    build_provenance,
    compute_provenance_digest,
    verify_provenance,
)

GENERATOR_TOOL = "cold-storage.release.evidence_collector:v0.2.0-slice2-r1"


@dataclass
class BuildInputs:
    """Frozen build-input snapshot used to assemble evidence."""

    source_commit_sha: str
    source_tree_sha: str
    source_date_epoch: int
    dockerfile_digest: str
    compose_file_digest: str
    workflow_definition_digest: str
    dependency_lockset_digest: str
    migration_set_digest: str
    base_image_digest_set: list[str]
    build_args: dict[str, str]
    build_platform: str = EXPECTED_BUILD_PLATFORM
    build_target: str = "runtime"

    def to_input_manifest(self) -> OrderedDict[str, Any]:
        return OrderedDict(
            [
                ("source_commit_sha", self.source_commit_sha),
                ("source_date_epoch", self.source_date_epoch),
                ("dockerfile_digest", self.dockerfile_digest),
                ("compose_file_digest", self.compose_file_digest),
                ("workflow_definition_digest", self.workflow_definition_digest),
                ("dependency_lockset_digest", self.dependency_lockset_digest),
                ("base_image_digest_set", sorted(self.base_image_digest_set)),
                ("build_args", self.build_args),
                ("build_platform", self.build_platform),
                ("build_target", self.build_target),
            ]
        )


@dataclass
class BuildRunRecord:
    """A single build run's observable outputs."""

    build_run_id: str
    build_run_attempt: int
    build_trigger: str
    builder_identity: str
    build_started_at: str
    build_finished_at: str
    final_image_digest: str
    local_oci_manifest_digest: str
    registry_manifest_digest: str | None
    base_image_tag: str
    base_image_digest: str
    lockfile_digest: str
    reproducible_build_result: str = "PASS"


@dataclass
class EvidenceBundle:
    """The assembled, verified release-candidate evidence bundle."""

    rc_version: str
    authoritative_image_digest: str
    artifact_manifest: OrderedDict[str, Any]
    artifact_manifest_digest: str
    provenance: OrderedDict[str, Any]
    provenance_digest: str
    reproducible_build_result: str
    raw: dict[str, Any] = field(default_factory=dict)


def _build_run_to_record(run: BuildRunRecord, inputs: BuildInputs) -> OrderedDict[str, Any]:
    from cold_storage.release.digest_verifier import compute_build_input_manifest_digest

    manifest = inputs.to_input_manifest()
    manifest_digest = compute_build_input_manifest_digest(manifest)
    record: OrderedDict[str, Any] = OrderedDict()
    # Include all build input manifest fields so that
    # verify_build_input_manifest can recompute and verify integrity.
    for key, value in manifest.items():
        record[key] = value
    record["base_image_tag"] = run.base_image_tag
    record["base_image_digest"] = run.base_image_digest
    record["lockfile_digest"] = run.lockfile_digest
    record["final_image_digest"] = run.final_image_digest
    record["build_input_manifest_digest"] = manifest_digest
    return record


def collect_release_candidate_evidence(
    *,
    inputs: BuildInputs,
    build_a: BuildRunRecord,
    build_b: BuildRunRecord,
    artifacts: list[Mapping[str, Any]],
    test_result_reference: str,
    verification_result_reference: str,
    attestation: Mapping[str, Any],
) -> EvidenceBundle:
    """Assemble and verify the full RC evidence bundle.

    Raises the appropriate ``RC_*`` :class:`ReleaseEvidenceError`
    subclass on the first violation.  On success the returned bundle is
    internally consistent: the authoritative image digest, the artifact
    manifest digest, and the provenance digest all cross-reference
    correctly.
    """
    # --- S2_GAP_01: reproducible build evidence ---
    record_a = _build_run_to_record(build_a, inputs)
    record_b = _build_run_to_record(build_b, inputs)
    authoritative_digest = verify_reproducible_build(record_a, record_b)

    # --- S2_GAP_02: final image digest (authoritative) ---
    authoritative_digest = authoritative_image_digest(
        local_oci_manifest_digest=build_a.local_oci_manifest_digest,
        registry_manifest_digest=build_a.registry_manifest_digest,
    )

    # --- S2_GAP_03: artifact manifest ---
    manifest_fields: OrderedDict[str, Any] = OrderedDict(
        [
            ("schema_version", ARTIFACT_MANIFEST_SCHEMA_VERSION),
            ("rc_version", RC_VERSION),
            ("source_commit_sha", inputs.source_commit_sha),
            ("source_tree_sha", inputs.source_tree_sha),
            ("dockerfile_digest", inputs.dockerfile_digest),
            ("compose_file_digest", inputs.compose_file_digest),
            ("workflow_definition_digest", inputs.workflow_definition_digest),
            ("dependency_lockset_digest", inputs.dependency_lockset_digest),
            ("migration_set_digest", inputs.migration_set_digest),
            ("final_image_digest", authoritative_digest),
            ("sbom_digest", ""),
            ("provenance_digest", ""),  # filled after provenance digest known
            ("test_result_reference", test_result_reference),
            ("verification_result_reference", verification_result_reference),
            ("generator_tool", GENERATOR_TOOL),
            ("artifacts", list(artifacts)),
        ]
    )
    # Build manifest without provenance_digest to compute a stable base,
    # then we set provenance_digest and recompute.  The authoritative
    # artifact digest is computed over the manifest *with* the
    # provenance_digest populated.
    manifest = build_manifest(manifest_fields)

    # --- S2_GAP_04: provenance statement ---
    provenance_fields: OrderedDict[str, Any] = OrderedDict(
        [
            ("schema_version", PROVENANCE_SCHEMA_VERSION),
            ("subject_final_image_digest", authoritative_digest),
            ("subject_artifact_manifest_digest", ""),  # filled below
            ("source_repository", EXPECTED_SOURCE_REPOSITORY),
            ("source_commit_sha", inputs.source_commit_sha),
            ("source_tree_sha", inputs.source_tree_sha),
            ("build_workflow_identity", "ci"),
            ("build_workflow_ref", "refs/heads/main"),
            ("build_run_id", build_a.build_run_id),
            ("build_run_attempt", build_a.build_run_attempt),
            ("build_trigger", build_a.build_trigger),
            ("builder_identity", build_a.builder_identity),
            ("build_platform", inputs.build_platform),
            ("build_definition_digest", inputs.workflow_definition_digest),
            ("dependency_lockset_digest", inputs.dependency_lockset_digest),
            ("base_image_digest_set", sorted(inputs.base_image_digest_set)),
            ("build_input_manifest_digest", record_a["build_input_manifest_digest"]),
            ("build_started_at", build_a.build_started_at),
            ("build_finished_at", build_a.build_finished_at),
            ("reproducible_build_result", build_a.reproducible_build_result),
            ("provenance_digest", ""),  # filled below
            ("attestation", dict(attestation)),
        ]
    )
    provenance = build_provenance(provenance_fields)
    provenance_digest = compute_provenance_digest(provenance)
    provenance["provenance_digest"] = provenance_digest

    # Now populate the artifact manifest's provenance_digest and the
    # provenance's subject_artifact_manifest_digest.  Since
    # compute_provenance_digest excludes both provenance_digest and
    # subject_artifact_manifest_digest, this is a single-pass computation
    # with no circular dependency.
    manifest["provenance_digest"] = provenance_digest
    artifact_manifest_digest = compute_manifest_digest(manifest)
    provenance["subject_artifact_manifest_digest"] = artifact_manifest_digest

    # --- cross-verify everything ---
    verify_provenance(
        provenance,
        expected_image_digest=authoritative_digest,
        expected_artifact_manifest_digest=artifact_manifest_digest,
    )
    verify_manifest_digest(manifest, artifact_manifest_digest)

    return EvidenceBundle(
        rc_version=RC_VERSION,
        authoritative_image_digest=authoritative_digest,
        artifact_manifest=manifest,
        artifact_manifest_digest=artifact_manifest_digest,
        provenance=provenance,
        provenance_digest=provenance_digest,
        reproducible_build_result=build_a.reproducible_build_result,
        raw={
            "build_input_manifest": inputs.to_input_manifest(),
            "build_a_record": record_a,
            "build_b_record": record_b,
        },
    )


def verify_evidence_bundle(bundle: EvidenceBundle) -> None:
    """Re-verify an assembled evidence bundle end-to-end."""
    verify_manifest_digest(bundle.artifact_manifest, bundle.artifact_manifest_digest)
    verify_provenance(
        bundle.provenance,
        expected_image_digest=bundle.authoritative_image_digest,
        expected_artifact_manifest_digest=bundle.artifact_manifest_digest,
    )
    if bundle.provenance.get("provenance_digest") != bundle.provenance_digest:
        raise ProvenanceError(
            failure_code="RC_PROVENANCE_SUBJECT_MISMATCH",
            detail="provenance_digest field does not match bundle digest",
        )
    reject_secret_values(bundle.artifact_manifest)
    reject_secret_values(bundle.provenance)


def verify_promotion_against_bundle(
    bundle: EvidenceBundle,
    promotion_record: Mapping[str, Any],
    *,
    prior_environment_digest: str | None = None,
) -> None:
    """Verify a promotion record against a verified evidence bundle."""
    verify_promotion(
        promotion_record,
        rc_image_digest=bundle.authoritative_image_digest,
        rc_artifact_manifest_digest=bundle.artifact_manifest_digest,
        rc_provenance_digest=bundle.provenance_digest,
        prior_environment_digest=prior_environment_digest,
    )


__all__ = [
    "GENERATOR_TOOL",
    "BuildInputs",
    "BuildRunRecord",
    "EvidenceBundle",
    "collect_release_candidate_evidence",
    "verify_evidence_bundle",
    "verify_promotion_against_bundle",
]
