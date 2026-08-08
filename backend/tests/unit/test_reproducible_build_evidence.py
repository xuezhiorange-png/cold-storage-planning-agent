"""Reproducible build evidence unit tests (S2_GAP_01)."""

from __future__ import annotations

from collections import OrderedDict

import pytest

from cold_storage.release.canonical_serialization import ReleaseEvidenceError
from cold_storage.release.digest_verifier import (
    ReproducibleBuildError,
    authoritative_image_digest,
    build_input_manifest,
    compute_build_input_manifest_digest,
    is_mutable_tag,
    verify_build_input_manifest,
    verify_registry_digest,
    verify_reproducible_build,
)
from cold_storage.release.provenance_schema import (
    RC_BASE_IMAGE_DIGEST_MISMATCH,
    RC_BUILD_ARG_MISMATCH,
    RC_FINAL_IMAGE_DIGEST_MISMATCH,
    RC_FINAL_IMAGE_DIGEST_MISSING,
    RC_LOCKFILE_DIGEST_MISMATCH,
    RC_REGISTRY_DIGEST_MISMATCH,
    RC_SOURCE_COMMIT_MISMATCH,
)

IMAGE = "sha256:" + "a" * 64
IMAGE_B = "sha256:" + "b" * 64
BASE = "sha256:" + "f" * 64
LOCK = "sha256:" + "1" * 64
COMMIT = "25a88f0b65fa7662310701563e306331034d6c34"


def _build(
    *,
    commit: str = COMMIT,
    base: str = BASE,
    lock: str = LOCK,
    digest: str = IMAGE,
    args: dict | None = None,
) -> OrderedDict:
    build_args = (
        args
        if args is not None
        else {
            "COLD_STORAGE_BUILD_COMMIT_SHA": commit,
            "COLD_STORAGE_BUILD_VERSION": "v0.2.0",
        }
    )
    rec = OrderedDict(
        [
            ("source_commit_sha", commit),
            ("base_image_tag", "python:3.12-slim"),
            ("base_image_digest", base),
            ("lockfile_digest", lock),
            ("build_args", build_args),
            ("build_platform", "ubuntu-latest"),
            ("final_image_digest", digest),
            ("build_input_manifest_digest", ""),
        ]
    )
    rec["build_input_manifest_digest"] = compute_build_input_manifest_digest(rec)
    return rec


def test_reproducible_build_pass_returns_authoritative_digest() -> None:
    a = _build()
    b = _build()
    # build_input_manifest_digest is a placeholder; verify_reproducible_build
    # does not re-check it, so equal builds pass.
    assert verify_reproducible_build(a, b) == IMAGE


def test_reproducible_build_rejects_different_commit() -> None:
    a = _build()
    b = _build(commit="0" * 40)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_reproducible_build(a, b)
    assert exc.value.failure_code == RC_SOURCE_COMMIT_MISMATCH


def test_reproducible_build_rejects_base_image_digest_drift() -> None:
    a = _build()
    b = _build(base="sha256:" + "9" * 64)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_reproducible_build(a, b)
    assert exc.value.failure_code == RC_BASE_IMAGE_DIGEST_MISMATCH


def test_reproducible_build_rejects_lockfile_digest_drift() -> None:
    a = _build()
    b = _build(lock="sha256:" + "8" * 64)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_reproducible_build(a, b)
    assert exc.value.failure_code == RC_LOCKFILE_DIGEST_MISMATCH


def test_reproducible_build_rejects_build_arg_mismatch() -> None:
    a = _build()
    b = _build(
        args={"COLD_STORAGE_BUILD_COMMIT_SHA": COMMIT, "COLD_STORAGE_BUILD_VERSION": "v0.2.1"}
    )
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_reproducible_build(a, b)
    assert exc.value.failure_code == RC_BUILD_ARG_MISMATCH


def test_reproducible_build_rejects_final_image_digest_mismatch() -> None:
    a = _build()
    b = _build(digest=IMAGE_B)
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_reproducible_build(a, b)
    assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISMATCH


def test_reproducible_build_rejects_missing_final_image_digest() -> None:
    a = _build()
    b = _build(digest="")
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_reproducible_build(a, b)
    assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISSING


def test_verify_registry_digest_rejects_mismatch() -> None:
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_registry_digest(local_oci_manifest_digest=IMAGE, registry_manifest_digest=IMAGE_B)
    assert exc.value.failure_code == RC_REGISTRY_DIGEST_MISMATCH


def test_authoritative_image_digest_local_only() -> None:
    assert (
        authoritative_image_digest(local_oci_manifest_digest=IMAGE, registry_manifest_digest=None)
        == IMAGE
    )


def test_authoritative_image_digest_local_equals_registry() -> None:
    assert (
        authoritative_image_digest(local_oci_manifest_digest=IMAGE, registry_manifest_digest=IMAGE)
        == IMAGE
    )


def test_authoritative_image_digest_rejects_drift() -> None:
    with pytest.raises(ReleaseEvidenceError) as exc:
        authoritative_image_digest(
            local_oci_manifest_digest=IMAGE, registry_manifest_digest=IMAGE_B
        )
    assert exc.value.failure_code == RC_REGISTRY_DIGEST_MISMATCH


def test_authoritative_image_digest_missing_raises() -> None:
    with pytest.raises(ReleaseEvidenceError) as exc:
        authoritative_image_digest(local_oci_manifest_digest=None, registry_manifest_digest=None)
    assert exc.value.failure_code == RC_FINAL_IMAGE_DIGEST_MISSING


def test_build_input_manifest_is_deterministic() -> None:
    fields = OrderedDict(
        [
            ("source_commit_sha", COMMIT),
            ("source_date_epoch", 123),
            ("dockerfile_digest", "sha256:" + "10" * 32),
            ("compose_file_digest", "sha256:" + "11" * 32),
            ("workflow_definition_digest", "sha256:" + "12" * 32),
            ("dependency_lockset_digest", LOCK),
            ("base_image_digest_set", ["sha256:z", "sha256:a"]),
            ("build_args", {"A": "1"}),
            ("build_platform", "ubuntu-latest"),
            ("build_target", "runtime"),
        ]
    )
    manifest = build_input_manifest(fields)
    # base_image_digest_set sorted
    assert manifest["base_image_digest_set"] == ["sha256:a", "sha256:z"]
    assert compute_build_input_manifest_digest(fields) == compute_build_input_manifest_digest(
        fields
    )


def test_is_mutable_tag() -> None:
    assert is_mutable_tag("cold-storage-backend:latest") is True
    assert is_mutable_tag("cold-storage-backend@sha256:" + "a" * 64) is False
    assert is_mutable_tag("sha256:" + "a" * 64) is False  # bare digest is immutable


def test_build_input_manifest_digest_drift_rejected() -> None:

    fields = OrderedDict(
        [
            ("source_commit_sha", COMMIT),
            ("source_date_epoch", 123),
            ("dockerfile_digest", "sha256:" + "10" * 32),
            ("compose_file_digest", "sha256:" + "11" * 32),
            ("workflow_definition_digest", "sha256:" + "12" * 32),
            ("dependency_lockset_digest", LOCK),
            ("base_image_digest_set", [BASE]),
            ("build_args", {"A": "1"}),
            ("build_platform", "ubuntu-latest"),
            ("build_target", "runtime"),
            ("build_input_manifest_digest", ""),
        ]
    )
    fields["build_input_manifest_digest"] = compute_build_input_manifest_digest(fields)
    verify_build_input_manifest(fields)
    # mutate a field -> drift
    fields["source_date_epoch"] = 999
    with pytest.raises(ReproducibleBuildError):
        verify_build_input_manifest(fields)
