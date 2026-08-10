"""Evidence collector — orchestrates the release-candidate evidence pipeline.

Ties together reproducible-build verification, artifact-manifest
generation, provenance-statement generation, and promotion-record
verification into a single :func:`collect_release_candidate_evidence`
entry point and a :func:`verify_evidence_bundle` verifier.

This round produces *code and synthetic verification* only.  Live
evidence execution (real registry push, GitHub OIDC signing, environment
approval) requires separate authorization.

B3 (Correction R2): Build A and Build B each carry their own independent
build-input manifest.  The collector no longer shares a single
``BuildInputs`` across both builds — each run's manifest is independently
canonicalized, digested, and integrity-verified before comparison.

B3 (Correction R3): The per-build ``build_input_manifest_digest`` is now
an *independently declared* field carried by each ``BuildRunRecord`` — it
is the digest the build run's own evidence declares, **not** a value the
collector computes and then verifies against itself (which was a circular
proof).  ``_build_run_to_record`` copies the run's declared digest into
the record verbatim; the existing ``verify_build_input_manifest`` then
recomputes the canonical digest of the run's *observed* inputs and
rejects any drift between declared and recomputed.  This establishes the
real trust relationship: declared digest (from per-build evidence) ↔
recomputed canonical digest (of the observed input manifest).

B4 (Correction R2): The authoritative RC digest is established through a
single continuous binding chain — Build A recorded ↔ Build A actual OCI ↔
Build B recorded ↔ Build B actual OCI ↔ authoritative RC ↔ registry (if
present).  No variable overwrite is permitted after the chain is
established.
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
    ReproducibleBuildError,
    normalize_oci_exporter_policy,
    validate_oci_exporter_policy,
    verify_reproducible_build,
)
from cold_storage.release.promotion_record import (
    verify_promotion,
)
from cold_storage.release.provenance_schema import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    EXPECTED_BUILD_PLATFORM,
    EXPECTED_DOCKER_TARGET_PLATFORM,
    EXPECTED_SOURCE_REPOSITORY,
    PROVENANCE_SCHEMA_VERSION,
    RC_BUILD_ARG_MISMATCH,
    RC_FINAL_IMAGE_DIGEST_MISMATCH,
    RC_REGISTRY_DIGEST_MISMATCH,
    RC_VERSION,
)
from cold_storage.release.provenance_statement import (
    LIVE_ATTESTATION_SUBJECT_SCHEMA,
    ProvenanceError,
    build_pre_attestation_provenance,
    build_provenance,
    compute_live_attestation_subject_digest,
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
    oci_exporter: dict[str, str]
    docker_target_platform: str = EXPECTED_DOCKER_TARGET_PLATFORM
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
                ("oci_exporter", normalize_oci_exporter_policy(self.oci_exporter)),
                ("docker_target_platform", self.docker_target_platform),
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
    # B3 (R3): independently declared build-input manifest digest carried by
    # this run's own evidence.  The collector does NOT compute this — it is
    # an external declaration that verify_build_input_manifest checks
    # against the recomputed canonical digest of the observed inputs.
    build_input_manifest_digest: str = ""
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


@dataclass(frozen=True)
class PreparedReleaseEvidence:
    """Evidence prepared before an attestation is created or consumed."""

    rc_version: str
    authoritative_image_digest: str
    artifact_manifest: OrderedDict[str, Any]
    artifact_manifest_digest: str
    pre_attestation_provenance: OrderedDict[str, Any]
    provenance_digest: str
    attestation_subject: OrderedDict[str, Any]
    attestation_subject_digest: str
    reproducible_build_result: str
    raw: dict[str, Any] = field(default_factory=dict)
    build_a_inputs: BuildInputs | None = None
    build_b_inputs: BuildInputs | None = None
    build_a: BuildRunRecord | None = None
    build_b: BuildRunRecord | None = None
    artifacts: list[Mapping[str, Any]] = field(default_factory=list)
    test_result_reference: str = ""
    verification_result_reference: str = ""


def _build_run_to_record(run: BuildRunRecord, inputs: BuildInputs) -> OrderedDict[str, Any]:
    """Build a per-run evidence record from the run's own build inputs.

    B3 (R2): Each build run now carries its own independent ``BuildInputs``.
    The manifest is generated from *this run's* inputs, canonicalized,
    and digested independently — not shared with the other build.

    B3 (R3): The ``build_input_manifest_digest`` placed into the record is
    the run's *independently declared* digest (``run.build_input_manifest_digest``),
    **not** a digest computed here by the collector.  Computing it here and
    then verifying it would be a circular proof.  The downstream
    ``verify_build_input_manifest`` recomputes the canonical digest from
    the observed inputs and rejects any drift from this declared value.
    """
    manifest = inputs.to_input_manifest()
    record: OrderedDict[str, Any] = OrderedDict()
    # Include all build input manifest fields so that
    # verify_build_input_manifest can recompute and verify integrity.
    for key, value in manifest.items():
        record[key] = value
    record["base_image_tag"] = run.base_image_tag
    record["base_image_digest"] = run.base_image_digest
    record["lockfile_digest"] = run.lockfile_digest
    record["final_image_digest"] = run.final_image_digest
    record["build_input_manifest_digest"] = run.build_input_manifest_digest
    return record


def _verify_digest_binding_chain(
    *,
    build_a: BuildRunRecord,
    build_b: BuildRunRecord,
    reproducible_digest: str,
) -> str:
    """Verify the continuous declared↔actual digest binding chain (B4).

    Establishes a single machine-verifiable chain:
    Build A recorded final_image_digest ↔ Build A actual local OCI digest ↔
    Build B recorded final_image_digest ↔ Build B actual local OCI digest ↔
    authoritative RC digest ↔ registry digest (if present).

    No variable is overwritten after the chain is established.  The
    returned digest is the authoritative RC digest, derived solely from
    the cross-checked chain.

    Raises :class:`ReproducibleBuildError` on any mismatch.
    """
    # 1. Build A: recorded final_image_digest == actual local OCI digest
    if build_a.final_image_digest != build_a.local_oci_manifest_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail=("Build A final_image_digest does not match its local OCI manifest digest"),
        )

    # 2. Build B: recorded final_image_digest == actual local OCI digest
    if build_b.final_image_digest != build_b.local_oci_manifest_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail=("Build B final_image_digest does not match its local OCI manifest digest"),
        )

    # 3. Build A local OCI digest == Build B local OCI digest
    if build_a.local_oci_manifest_digest != build_b.local_oci_manifest_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail=("Build A and Build B local OCI manifest digests differ"),
        )

    # 4. If Build A registry digest exists: must match local OCI digest
    if (
        build_a.registry_manifest_digest is not None
        and build_a.registry_manifest_digest != ""
        and build_a.registry_manifest_digest != build_a.local_oci_manifest_digest
    ):
        raise ReproducibleBuildError(
            failure_code=RC_REGISTRY_DIGEST_MISMATCH,
            detail=("Build A registry manifest digest differs from local OCI manifest digest"),
        )

    # 5. If Build B registry digest exists: must match local OCI digest
    if (
        build_b.registry_manifest_digest is not None
        and build_b.registry_manifest_digest != ""
        and build_b.registry_manifest_digest != build_b.local_oci_manifest_digest
    ):
        raise ReproducibleBuildError(
            failure_code=RC_REGISTRY_DIGEST_MISMATCH,
            detail=("Build B registry manifest digest differs from local OCI manifest digest"),
        )

    # 6. Authoritative RC digest = the cross-checked unique digest.
    #    No second assignment — the chain has proven all digests are
    #    identical, so the Build A local OCI digest IS the authoritative
    #    digest.  We also cross-check against the reproducible build
    #    verdict to ensure consistency.
    authoritative_digest = build_a.local_oci_manifest_digest
    if reproducible_digest != authoritative_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail=(
                "reproducible build digest does not match the authoritative binding chain digest"
            ),
        )

    return authoritative_digest


def prepare_pre_attestation_evidence(
    *,
    build_a_inputs: BuildInputs,
    build_b_inputs: BuildInputs,
    build_a: BuildRunRecord,
    build_b: BuildRunRecord,
    artifacts: list[Mapping[str, Any]],
    test_result_reference: str,
    verification_result_reference: str,
    expected_inputs: BuildInputs | None = None,
) -> PreparedReleaseEvidence:
    """Prepare the authoritative P/M evidence before attestation exists.

    B3: ``build_a_inputs`` and ``build_b_inputs`` are separate, allowing
    the collector to detect when Build A's observed inputs differ from
    Build B's observed inputs.  If ``expected_inputs`` is provided, each
    build's observed inputs are also verified against the expected/frozen
    RC input definition.

    B4: The authoritative RC digest is established through a single
    continuous binding chain — no variable overwrite after the chain is
    established.

    The function is intentionally the only observation-to-provenance
    preparation path.  It does not create, accept, or upload an attestation.
    """
    for label, inputs in (("Build A", build_a_inputs), ("Build B", build_b_inputs)):
        validate_oci_exporter_policy(inputs.oci_exporter)
        if inputs.docker_target_platform != EXPECTED_DOCKER_TARGET_PLATFORM:
            raise ReproducibleBuildError(
                failure_code=RC_BUILD_ARG_MISMATCH,
                detail=(
                    f"{label} docker target platform is "
                    f"{inputs.docker_target_platform!r}, expected "
                    f"{EXPECTED_DOCKER_TARGET_PLATFORM!r}"
                ),
            )

    # --- B3: per-run build input evidence ---
    # Each build carries its own observed build-input manifest.  The
    # records are built independently from each run's own inputs.
    record_a = _build_run_to_record(build_a, build_a_inputs)
    record_b = _build_run_to_record(build_b, build_b_inputs)

    # --- B3: optional expected-inputs cross-check ---
    # If a frozen/expected RC input definition is provided, verify that
    # each build's observed inputs match it.  This prevents a build from
    # silently using different inputs than expected while still producing
    # the same digest.
    if expected_inputs is not None:
        manifest_a = build_a_inputs.to_input_manifest()
        manifest_b = build_b_inputs.to_input_manifest()
        manifest_expected = expected_inputs.to_input_manifest()
        if manifest_a != manifest_expected:
            raise ReproducibleBuildError(
                failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
                detail="Build A observed inputs do not match expected inputs",
            )
        if manifest_b != manifest_expected:
            raise ReproducibleBuildError(
                failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
                detail="Build B observed inputs do not match expected inputs",
            )

    # --- S2_GAP_01: reproducible build evidence ---
    # verify_reproducible_build includes per-run manifest integrity
    # verification (verify_build_input_manifest) and manifest comparison.
    reproducible_digest = verify_reproducible_build(record_a, record_b)

    # --- B4: continuous digest binding chain ---
    # The authoritative RC digest is established through a single
    # continuous chain.  No variable overwrite is permitted.
    authoritative_digest = _verify_digest_binding_chain(
        build_a=build_a,
        build_b=build_b,
        reproducible_digest=reproducible_digest,
    )

    # --- S2_GAP_03: artifact manifest ---
    manifest_fields: OrderedDict[str, Any] = OrderedDict(
        [
            ("schema_version", ARTIFACT_MANIFEST_SCHEMA_VERSION),
            ("rc_version", RC_VERSION),
            ("source_commit_sha", build_a_inputs.source_commit_sha),
            ("source_tree_sha", build_a_inputs.source_tree_sha),
            ("dockerfile_digest", build_a_inputs.dockerfile_digest),
            ("compose_file_digest", build_a_inputs.compose_file_digest),
            ("workflow_definition_digest", build_a_inputs.workflow_definition_digest),
            ("dependency_lockset_digest", build_a_inputs.dependency_lockset_digest),
            ("migration_set_digest", build_a_inputs.migration_set_digest),
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

    # --- S2_GAP_04: pre-attestation provenance statement ---
    provenance_fields: OrderedDict[str, Any] = OrderedDict(
        [
            ("schema_version", PROVENANCE_SCHEMA_VERSION),
            ("subject_final_image_digest", authoritative_digest),
            ("subject_artifact_manifest_digest", ""),  # filled below
            ("source_repository", EXPECTED_SOURCE_REPOSITORY),
            ("source_commit_sha", build_a_inputs.source_commit_sha),
            ("source_tree_sha", build_a_inputs.source_tree_sha),
            ("build_workflow_identity", "ci"),
            ("build_workflow_ref", "refs/heads/main"),
            ("build_run_id", build_a.build_run_id),
            ("build_run_attempt", build_a.build_run_attempt),
            ("build_trigger", build_a.build_trigger),
            ("builder_identity", build_a.builder_identity),
            ("build_platform", build_a_inputs.build_platform),
            ("build_definition_digest", build_a_inputs.workflow_definition_digest),
            ("dependency_lockset_digest", build_a_inputs.dependency_lockset_digest),
            ("base_image_digest_set", sorted(build_a_inputs.base_image_digest_set)),
            ("build_input_manifest_digest", record_a["build_input_manifest_digest"]),
            ("build_started_at", build_a.build_started_at),
            ("build_finished_at", build_a.build_finished_at),
            ("reproducible_build_result", build_a.reproducible_build_result),
            ("provenance_digest", ""),  # filled below
        ]
    )
    provenance = build_pre_attestation_provenance(provenance_fields)
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
    verify_manifest_digest(manifest, artifact_manifest_digest)

    attestation_subject = OrderedDict(
        [
            ("schema_version", LIVE_ATTESTATION_SUBJECT_SCHEMA),
            ("provenance_digest", provenance_digest),
            ("artifact_manifest_digest", artifact_manifest_digest),
        ]
    )
    attestation_subject_digest = compute_live_attestation_subject_digest(
        provenance_digest, artifact_manifest_digest
    )

    return PreparedReleaseEvidence(
        rc_version=RC_VERSION,
        authoritative_image_digest=authoritative_digest,
        artifact_manifest=manifest,
        artifact_manifest_digest=artifact_manifest_digest,
        pre_attestation_provenance=provenance,
        provenance_digest=provenance_digest,
        attestation_subject=attestation_subject,
        attestation_subject_digest=attestation_subject_digest,
        reproducible_build_result=build_a.reproducible_build_result,
        raw={
            "build_a_input_manifest": build_a_inputs.to_input_manifest(),
            "build_b_input_manifest": build_b_inputs.to_input_manifest(),
            "build_a_record": record_a,
            "build_b_record": record_b,
        },
        build_a_inputs=build_a_inputs,
        build_b_inputs=build_b_inputs,
        build_a=build_a,
        build_b=build_b,
        artifacts=list(artifacts),
        test_result_reference=test_result_reference,
        verification_result_reference=verification_result_reference,
    )


def finalize_prepared_release_evidence(
    prepared: PreparedReleaseEvidence,
    attestation: Mapping[str, Any],
    *,
    live_attestation: bool = False,
) -> EvidenceBundle:
    """Attach an explicit attestation and finalize the verified bundle."""
    provenance = OrderedDict(prepared.pre_attestation_provenance)
    provenance["attestation"] = dict(attestation)
    provenance = build_provenance(provenance)
    provenance["provenance_digest"] = prepared.provenance_digest
    provenance["subject_artifact_manifest_digest"] = prepared.artifact_manifest_digest
    verify_provenance(
        provenance,
        expected_image_digest=prepared.authoritative_image_digest,
        expected_artifact_manifest_digest=prepared.artifact_manifest_digest,
        require_live_attestation=live_attestation,
    )
    verify_manifest_digest(prepared.artifact_manifest, prepared.artifact_manifest_digest)
    return EvidenceBundle(
        rc_version=prepared.rc_version,
        authoritative_image_digest=prepared.authoritative_image_digest,
        artifact_manifest=prepared.artifact_manifest,
        artifact_manifest_digest=prepared.artifact_manifest_digest,
        provenance=provenance,
        provenance_digest=prepared.provenance_digest,
        reproducible_build_result=prepared.reproducible_build_result,
        raw={**prepared.raw, "attestation_subject": prepared.attestation_subject},
    )


def collect_release_candidate_evidence(
    *,
    build_a_inputs: BuildInputs,
    build_b_inputs: BuildInputs,
    build_a: BuildRunRecord,
    build_b: BuildRunRecord,
    artifacts: list[Mapping[str, Any]],
    test_result_reference: str,
    verification_result_reference: str,
    attestation: Mapping[str, Any],
    expected_inputs: BuildInputs | None = None,
    live_attestation: bool = False,
) -> EvidenceBundle:
    """Prepare, attest, and verify a release-candidate evidence bundle.

    Existing synthetic callers retain the historical default.  The live
    Assembly path opts into the exact Slice 2 attestation contract.
    """
    prepared = prepare_pre_attestation_evidence(
        build_a_inputs=build_a_inputs,
        build_b_inputs=build_b_inputs,
        build_a=build_a,
        build_b=build_b,
        artifacts=artifacts,
        test_result_reference=test_result_reference,
        verification_result_reference=verification_result_reference,
        expected_inputs=expected_inputs,
    )
    return finalize_prepared_release_evidence(
        prepared,
        attestation,
        live_attestation=live_attestation,
    )


def verify_evidence_bundle(bundle: EvidenceBundle) -> None:
    """Re-verify an assembled evidence bundle end-to-end."""
    verify_manifest_digest(bundle.artifact_manifest, bundle.artifact_manifest_digest)
    verify_provenance(
        bundle.provenance,
        expected_image_digest=bundle.authoritative_image_digest,
        expected_artifact_manifest_digest=bundle.artifact_manifest_digest,
        require_live_attestation=(
            isinstance(bundle.provenance.get("attestation"), Mapping)
            and bundle.provenance["attestation"].get("schema_version")
            == "cold-storage-live-attestation-v1"
        ),
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
    "PreparedReleaseEvidence",
    "collect_release_candidate_evidence",
    "finalize_prepared_release_evidence",
    "prepare_pre_attestation_evidence",
    "verify_evidence_bundle",
    "verify_promotion_against_bundle",
]
