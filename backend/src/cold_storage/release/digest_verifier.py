"""Reproducible build evidence and final image digest (S2_GAP_01, S2_GAP_02).

Implements the mechanical two-build comparison and the OCI image-digest
distinction (mutable tag vs. local manifest digest vs. registry digest
vs. authoritative digest) frozen in Sections 6 and 7 of the contract.

A *build record* is a plain dict with the keys:

* ``source_commit_sha``
* ``base_image_tag``
* ``base_image_digest``
* ``lockfile_digest``
* ``build_args``        (dict, compared by canonical JSON)
* ``build_platform``
* ``final_image_digest`` (``sha256:<hex>`` or ``None``/empty when missing)
* ``build_input_manifest_digest``

A *build input manifest* is an ordered dict whose canonical digest is
``build_input_manifest_digest``; it captures the frozen build inputs
(Dockerfile, Compose, workflow, locksets, base-image digests, build
args, OCI exporter policy, platform, source commit, ``SOURCE_DATE_EPOCH``).
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from cold_storage.release.canonical_serialization import (
    ReleaseEvidenceError,
    canonical_bytes,
    canonical_digest,
)
from cold_storage.release.provenance_schema import (
    EXPECTED_BUILD_PLATFORM,
    EXPECTED_DOCKER_TARGET_PLATFORM,
    RC_BASE_IMAGE_DIGEST_MISMATCH,
    RC_BUILD_ARG_MISMATCH,
    RC_FINAL_IMAGE_DIGEST_MISMATCH,
    RC_FINAL_IMAGE_DIGEST_MISSING,
    RC_LOCKFILE_DIGEST_MISMATCH,
    RC_REGISTRY_DIGEST_MISMATCH,
    RC_SOURCE_COMMIT_MISMATCH,
)

DIGEST_PREFIX = "sha256:"

BUILD_INPUT_MANIFEST_FIELD_ORDER: tuple[str, ...] = (
    "source_commit_sha",
    "source_date_epoch",
    "dockerfile_digest",
    "compose_file_digest",
    "workflow_definition_digest",
    "dependency_lockset_digest",
    "base_image_digest_set",
    "build_args",
    "oci_exporter",
    "docker_target_platform",
    "build_platform",
    "build_target",
)


class ReproducibleBuildError(ReleaseEvidenceError):
    """Failure raised by reproducible-build / digest verification."""


EXPECTED_OCI_EXPORTER_POLICY: dict[str, str] = {
    "type": "oci",
    "rewrite-timestamp": "true",
}


def normalize_oci_exporter_policy(value: Any) -> OrderedDict[str, str]:
    """Return the canonical shape of the observed OCI exporter policy.

    The policy is a build-input value, not a Dockerfile build argument.  A
    false rewrite setting remains representable so its manifest digest can be
    shown to differ, but it is rejected by the frozen-policy validator below.
    """
    if not isinstance(value, Mapping):
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="MISSING_OCI_EXPORTER_POLICY",
        )
    if set(value) != set(EXPECTED_OCI_EXPORTER_POLICY):
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="OCI_EXPORTER_POLICY_FIELDS_INVALID",
        )
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="OCI_EXPORTER_POLICY_TYPES_INVALID",
        )
    output_type = value["type"]
    rewrite_timestamp = value["rewrite-timestamp"]
    if output_type != "oci" or rewrite_timestamp not in {"true", "false"}:
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="OCI_EXPORTER_POLICY_VALUES_INVALID",
        )
    return OrderedDict(
        [
            ("type", output_type),
            ("rewrite-timestamp", rewrite_timestamp),
        ]
    )


def validate_oci_exporter_policy(value: Any) -> OrderedDict[str, str]:
    """Require the frozen OCI exporter policy for an executable build."""
    normalized = normalize_oci_exporter_policy(value)
    expected = OrderedDict(EXPECTED_OCI_EXPORTER_POLICY.items())
    if normalized != expected:
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="FALSE_OCI_REWRITE_TIMESTAMP_OR_EXPORTER_POLICY_DRIFT",
        )
    return normalized


def _present(value: Any) -> bool:
    return value not in (None, "")


def _canonical_args(args: Any) -> str:
    """Stable textual form of build args for equality comparison."""
    if isinstance(args, Mapping):
        ordered = OrderedDict((k, args[k]) for k in sorted(args))
        return canonical_bytes(ordered).decode("utf-8")
    return repr(args)


def build_input_manifest(fields: Mapping[str, Any]) -> OrderedDict[str, Any]:
    """Return an ordered build-input-manifest dict in canonical field order."""
    exporter_policy = normalize_oci_exporter_policy(fields.get("oci_exporter"))
    out: OrderedDict[str, Any] = OrderedDict()
    for key in BUILD_INPUT_MANIFEST_FIELD_ORDER:
        if key in fields:
            out[key] = fields[key]
    # base_image_digest_set must be sorted for determinism.
    base_set = out.get("base_image_digest_set")
    if isinstance(base_set, list):
        out["base_image_digest_set"] = sorted(base_set)
    out["oci_exporter"] = exporter_policy
    return out


def compute_build_input_manifest_digest(fields: Mapping[str, Any]) -> str:
    return canonical_digest(build_input_manifest(fields))


def verify_build_input_manifest(build_record: Mapping[str, Any]) -> None:
    """Verify a build record's declared ``build_input_manifest_digest``.

    Recomputes the canonical digest from the build inputs and rejects
    drift.  This closes the "undeclared dynamic input" gap.
    """
    validate_oci_exporter_policy(build_record.get("oci_exporter"))
    declared = build_record.get("build_input_manifest_digest")
    if not _present(declared):
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISSING,
            detail="build_input_manifest_digest missing",
        )
    recomputed = compute_build_input_manifest_digest(build_record)
    if declared != recomputed:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="build_input_manifest_digest drift",
        )


def verify_reproducible_build(
    build_a: Mapping[str, Any],
    build_b: Mapping[str, Any],
) -> str:
    """Verify two builds are reproducible and return the authoritative digest.

    Raises :class:`ReproducibleBuildError` with the matching ``RC_*`` code
    on the first violated condition, in the order frozen by the contract.

    The build input manifests of Build A and Build B are explicitly
    compared as part of the reproducibility verdict — not just the
    declared digest strings, but the recomputed canonical digests from
    the actual build inputs.
    """
    # 1. same source commit
    if build_a.get("source_commit_sha") != build_b.get("source_commit_sha"):
        raise ReproducibleBuildError(
            failure_code=RC_SOURCE_COMMIT_MISMATCH,
            detail="build A and B originate from different commits",
        )

    # 2. base image: same tag, same digest
    if build_a.get("base_image_tag") != build_b.get("base_image_tag"):
        raise ReproducibleBuildError(
            failure_code=RC_BASE_IMAGE_DIGEST_MISMATCH,
            detail="base image tag differs between builds",
        )
    if build_a.get("base_image_digest") != build_b.get("base_image_digest"):
        raise ReproducibleBuildError(
            failure_code=RC_BASE_IMAGE_DIGEST_MISMATCH,
            detail="base image digest differs between builds",
        )

    # 3. lockfile digest equality
    if build_a.get("lockfile_digest") != build_b.get("lockfile_digest"):
        raise ReproducibleBuildError(
            failure_code=RC_LOCKFILE_DIGEST_MISMATCH,
            detail="lockfile digest differs between builds",
        )

    # 4. build args equality
    if _canonical_args(build_a.get("build_args")) != _canonical_args(build_b.get("build_args")):
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="build args differ between builds",
        )

    # 4a. The exporter policy is a mandatory, digest-affecting producer input.
    policy_a = normalize_oci_exporter_policy(build_a.get("oci_exporter"))
    policy_b = normalize_oci_exporter_policy(build_b.get("oci_exporter"))
    if policy_a != policy_b:
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="A_B_EXPORTER_POLICY_DRIFT",
        )
    validate_oci_exporter_policy(policy_a)

    # 5. final image digest present
    digest_a = build_a.get("final_image_digest")
    digest_b = build_b.get("final_image_digest")
    if not _present(digest_a) or not _present(digest_b):
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISSING,
            detail="final image digest missing",
        )

    # 6. final image digest equality
    if digest_a != digest_b:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="build A and B produced different image digests",
        )

    # 7. platform must be the frozen value
    if (
        build_a.get("build_platform") != EXPECTED_BUILD_PLATFORM
        or build_b.get("build_platform") != EXPECTED_BUILD_PLATFORM
    ):
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="build platform is not ubuntu-latest",
        )

    # 8. Docker target platform is a separate frozen image-output input.
    docker_target_a = build_a.get("docker_target_platform")
    docker_target_b = build_b.get("docker_target_platform")
    if (
        docker_target_a != EXPECTED_DOCKER_TARGET_PLATFORM
        or docker_target_b != EXPECTED_DOCKER_TARGET_PLATFORM
    ):
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="Docker target platform is not the frozen linux/amd64 value",
        )
    if docker_target_a != docker_target_b:
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="Docker target platform differs between builds",
        )

    # 9. build input manifest comparison — Build A vs Build B
    # The build input manifest captures all deterministic build inputs
    # (Dockerfile, Compose, workflow, locksets, base-image digests,
    # build args, platform, source commit, SOURCE_DATE_EPOCH).  Two
    # builds claiming the same image digest MUST have identical build
    # input manifests.  We recompute the canonical digests from the
    # build inputs (not just comparing declared strings) so that a
    # mismatch in any deterministic input is detected.
    manifest_digest_a = build_a.get("build_input_manifest_digest")
    manifest_digest_b = build_b.get("build_input_manifest_digest")
    if not _present(manifest_digest_a) or not _present(manifest_digest_b):
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISSING,
            detail="build_input_manifest_digest missing from one or both builds",
        )
    # Recompute from actual build inputs to verify declared digest integrity
    verify_build_input_manifest(build_a)
    verify_build_input_manifest(build_b)
    # The two builds' input manifest digests must match
    if manifest_digest_a != manifest_digest_b:
        raise ReproducibleBuildError(
            failure_code=RC_BUILD_ARG_MISMATCH,
            detail="build A and B have different build input manifest digests",
        )

    return str(digest_a)


def authoritative_image_digest(
    *,
    local_oci_manifest_digest: str | None,
    registry_manifest_digest: str | None,
) -> str:
    """Return the authoritative final image digest.

    The authoritative digest is the OCI image manifest digest.  If both
    local and registry digests exist they MUST be equal.  If only a
    local digest exists (no registry push) it is authoritative.  A
    mutable tag is never authoritative.
    """
    local = local_oci_manifest_digest if _present(local_oci_manifest_digest) else None
    registry = registry_manifest_digest if _present(registry_manifest_digest) else None
    if local is None and registry is None:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISSING,
            detail="no image digest available (local or registry)",
        )
    if local is not None and registry is not None and local != registry:
        raise ReproducibleBuildError(
            failure_code=RC_REGISTRY_DIGEST_MISMATCH,
            detail="registry digest differs from local OCI digest",
        )
    return str(registry if registry is not None else local)


def verify_registry_digest(
    *,
    local_oci_manifest_digest: str,
    registry_manifest_digest: str,
) -> None:
    """Reject when the registry digest differs from the local OCI digest."""
    if local_oci_manifest_digest != registry_manifest_digest:
        raise ReproducibleBuildError(
            failure_code=RC_REGISTRY_DIGEST_MISMATCH,
            detail="registry digest differs from local OCI digest",
        )


def is_mutable_tag(reference: str) -> bool:
    """True when *reference* is a mutable tag (not an immutable digest).

    A bare ``sha256:<64-hex>`` digest and a ``name@sha256:<64-hex>``
    reference are both immutable; anything else (e.g. ``name:tag``) is a
    mutable tag.
    """
    bare = re.compile(r"^sha256:[0-9a-f]{64}$")
    if not isinstance(reference, str):
        return True
    if bare.match(reference):
        return False
    if "@" in reference:
        _, _, digest = reference.partition("@")
        return not bool(bare.match(digest))
    return True


def verify_declared_actual_digest_binding(
    *,
    declared_digest: str,
    actual_local_oci_digest: str,
    build_record: Mapping[str, Any],
) -> None:
    """Verify that a declared digest matches the actual local OCI digest.

    This establishes the machine-verifiable binding between the digest
    recorded in evidence and the actual OCI image manifest digest
    produced by the build.  The ``build_record`` must contain
    ``final_image_digest`` (the build's declared output) and
    ``build_input_manifest_digest`` for input integrity.

    Raises :class:`ReproducibleBuildError` with
    ``RC_FINAL_IMAGE_DIGEST_MISMATCH`` when the declared digest does
    not match the actual local OCI digest.
    """
    if not _present(declared_digest):
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISSING,
            detail="declared digest is missing",
        )
    if not _present(actual_local_oci_digest):
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISSING,
            detail="actual local OCI digest is missing",
        )
    if declared_digest != actual_local_oci_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="declared digest does not match actual local OCI digest",
        )
    # The build record's final_image_digest must also match
    recorded = build_record.get("final_image_digest")
    if _present(recorded) and recorded != actual_local_oci_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="build record final_image_digest does not match actual local OCI digest",
        )


def verify_digest_binding_chain(
    *,
    build_a_actual_digest: str,
    build_a_recorded_digest: str,
    build_b_actual_digest: str,
    build_b_recorded_digest: str,
    authoritative_rc_digest: str,
) -> None:
    """Verify the full digest binding chain across two builds and the RC.

    Establishes the machine-verifiable relationship:
    Build A actual local OCI digest ↔ Build A recorded digest ↔
    Build B actual local OCI digest ↔ Build B recorded digest ↔
    authoritative RC digest.

    Any mismatch in the chain raises :class:`ReproducibleBuildError`
    with ``RC_FINAL_IMAGE_DIGEST_MISMATCH``.
    """
    digests = [
        ("build_a_actual", build_a_actual_digest),
        ("build_a_recorded", build_a_recorded_digest),
        ("build_b_actual", build_b_actual_digest),
        ("build_b_recorded", build_b_recorded_digest),
        ("authoritative_rc", authoritative_rc_digest),
    ]
    for label, value in digests:
        if not _present(value):
            raise ReproducibleBuildError(
                failure_code=RC_FINAL_IMAGE_DIGEST_MISSING,
                detail=f"{label} digest is missing",
            )
    if build_a_actual_digest != build_a_recorded_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="Build A actual digest does not match Build A recorded digest",
        )
    if build_b_actual_digest != build_b_recorded_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="Build B actual digest does not match Build B recorded digest",
        )
    if build_a_actual_digest != build_b_actual_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="Build A and Build B actual digests differ",
        )
    if authoritative_rc_digest != build_a_actual_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="authoritative RC digest does not match Build A actual digest",
        )


def verify_provenance_subject_digest_binding(
    *,
    provenance_subject_digest: str,
    actual_image_digest: str,
) -> None:
    """Verify that the provenance subject digest matches the actual image digest.

    Raises :class:`ReproducibleBuildError` with
    ``RC_FINAL_IMAGE_DIGEST_MISMATCH`` when the provenance subject
    digest does not match the actual image digest.
    """
    if not _present(provenance_subject_digest):
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISSING,
            detail="provenance subject digest is missing",
        )
    if provenance_subject_digest != actual_image_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="provenance subject digest does not match actual image digest",
        )


def verify_promotion_digest_binding(
    *,
    promotion_digest: str,
    authoritative_rc_digest: str,
) -> None:
    """Verify that the promotion digest matches the authoritative RC digest.

    Raises :class:`ReproducibleBuildError` with
    ``RC_FINAL_IMAGE_DIGEST_MISMATCH`` when the promotion digest does
    not match the authoritative RC digest.
    """
    if not _present(promotion_digest):
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISSING,
            detail="promotion digest is missing",
        )
    if promotion_digest != authoritative_rc_digest:
        raise ReproducibleBuildError(
            failure_code=RC_FINAL_IMAGE_DIGEST_MISMATCH,
            detail="promotion digest does not match authoritative RC digest",
        )


__all__ = [
    "BUILD_INPUT_MANIFEST_FIELD_ORDER",
    "EXPECTED_OCI_EXPORTER_POLICY",
    "ReproducibleBuildError",
    "authoritative_image_digest",
    "build_input_manifest",
    "compute_build_input_manifest_digest",
    "is_mutable_tag",
    "normalize_oci_exporter_policy",
    "validate_oci_exporter_policy",
    "verify_build_input_manifest",
    "verify_declared_actual_digest_binding",
    "verify_digest_binding_chain",
    "verify_provenance_subject_digest_binding",
    "verify_promotion_digest_binding",
    "verify_registry_digest",
    "verify_reproducible_build",
]
