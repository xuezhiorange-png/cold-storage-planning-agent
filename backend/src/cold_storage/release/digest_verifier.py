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
args, platform, source commit, ``SOURCE_DATE_EPOCH``).
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
    "build_platform",
    "build_target",
)


class ReproducibleBuildError(ReleaseEvidenceError):
    """Failure raised by reproducible-build / digest verification."""


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
    out: OrderedDict[str, Any] = OrderedDict()
    for key in BUILD_INPUT_MANIFEST_FIELD_ORDER:
        if key in fields:
            out[key] = fields[key]
    # base_image_digest_set must be sorted for determinism.
    base_set = out.get("base_image_digest_set")
    if isinstance(base_set, list):
        out["base_image_digest_set"] = sorted(base_set)
    return out


def compute_build_input_manifest_digest(fields: Mapping[str, Any]) -> str:
    return canonical_digest(build_input_manifest(fields))


def verify_build_input_manifest(build_record: Mapping[str, Any]) -> None:
    """Verify a build record's declared ``build_input_manifest_digest``.

    Recomputes the canonical digest from the build inputs and rejects
    drift.  This closes the "undeclared dynamic input" gap.
    """
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


__all__ = [
    "BUILD_INPUT_MANIFEST_FIELD_ORDER",
    "ReproducibleBuildError",
    "authoritative_image_digest",
    "build_input_manifest",
    "compute_build_input_manifest_digest",
    "is_mutable_tag",
    "verify_build_input_manifest",
    "verify_registry_digest",
    "verify_reproducible_build",
]
