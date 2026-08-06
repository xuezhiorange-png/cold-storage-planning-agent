"""Final image digest unit tests (S2_GAP_02)."""

from __future__ import annotations

import pytest

from cold_storage.release.canonical_serialization import ReleaseEvidenceError
from cold_storage.release.digest_verifier import (
    authoritative_image_digest,
    is_mutable_tag,
    verify_registry_digest,
)
from cold_storage.release.provenance_schema import (
    RC_FINAL_IMAGE_DIGEST_MISSING,
    RC_REGISTRY_DIGEST_MISMATCH,
)

IMAGE = "sha256:" + "a" * 64
IMAGE_B = "sha256:" + "b" * 64


def test_mutable_tag_is_not_authoritative() -> None:
    assert is_mutable_tag("cold-storage-backend:latest") is True
    assert is_mutable_tag("cold-storage-backend:abc123") is True


def test_digest_reference_is_not_mutable() -> None:
    assert is_mutable_tag(f"cold-storage-backend@{IMAGE}") is False


def test_authoritative_digest_binds_to_oci_manifest() -> None:
    digest = authoritative_image_digest(
        local_oci_manifest_digest=IMAGE, registry_manifest_digest=IMAGE
    )
    assert digest == IMAGE
    assert digest.startswith("sha256:")


def test_authoritative_digest_rejects_missing() -> None:
    with pytest.raises(ReleaseEvidenceError) as exc:
        authoritative_image_digest(local_oci_manifest_digest=None, registry_manifest_digest=None)
    assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISSING


def test_authoritative_digest_rejects_registry_drift() -> None:
    with pytest.raises(ReleaseEvidenceError) as exc:
        authoritative_image_digest(
            local_oci_manifest_digest=IMAGE, registry_manifest_digest=IMAGE_B
        )
    assert exc.value.failure_code == RC_REGISTRY_DIGEST_MISMATCH


def test_registry_digest_verification_passes_when_equal() -> None:
    verify_registry_digest(local_oci_manifest_digest=IMAGE, registry_manifest_digest=IMAGE)


def test_registry_digest_verification_rejects_drift() -> None:
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_registry_digest(local_oci_manifest_digest=IMAGE, registry_manifest_digest=IMAGE_B)
    assert exc.value.failure_code == RC_REGISTRY_DIGEST_MISMATCH


def test_local_only_digest_is_authoritative_without_registry() -> None:
    """When no registry push occurs, the local OCI digest is authoritative."""
    assert (
        authoritative_image_digest(local_oci_manifest_digest=IMAGE, registry_manifest_digest=None)
        == IMAGE
    )


def test_tag_change_does_not_alter_frozen_digest_identity() -> None:
    """A mutable tag is never the authoritative identity (contract 7.3)."""
    tag = "cold-storage-backend:25a88f0"
    assert is_mutable_tag(tag) is True
    # The authoritative identity must be the digest, not the tag.
    assert (
        authoritative_image_digest(local_oci_manifest_digest=IMAGE, registry_manifest_digest=None)
        != tag
    )
