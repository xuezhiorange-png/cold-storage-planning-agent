"""Artifact manifest unit tests (S2_GAP_03)."""

from __future__ import annotations

from collections import OrderedDict

import pytest

from cold_storage.release.artifact_manifest import (
    ArtifactManifestError,
    build_manifest,
    compute_manifest_digest,
    load_manifest_from_path,
    load_manifest_from_text,
    serialize_manifest,
    verify_manifest_digest,
)
from cold_storage.release.canonical_serialization import ReleaseEvidenceError
from cold_storage.release.provenance_schema import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    RC_ARTIFACT_DIGEST_MISMATCH,
    RC_ARTIFACT_DUPLICATE_KEY,
    RC_ARTIFACT_MANIFEST_MISSING,
)

IMAGE = "sha256:" + "a" * 64
PROV = "sha256:" + "d" * 64


def _fields() -> OrderedDict:
    return OrderedDict(
        [
            ("schema_version", ARTIFACT_MANIFEST_SCHEMA_VERSION),
            ("rc_version", "v0.2.0"),
            ("source_commit_sha", "25a88f0b65fa7662310701563e306331034d6c34"),
            ("source_tree_sha", "274e84af01bd895a30571423283838017aacd45f"),
            ("dockerfile_digest", "sha256:" + "10" * 32),
            ("compose_file_digest", "sha256:" + "11" * 32),
            ("workflow_definition_digest", "sha256:" + "12" * 32),
            ("dependency_lockset_digest", "sha256:" + "1" * 64),
            ("migration_set_digest", "sha256:" + "13" * 32),
            ("final_image_digest", IMAGE),
            ("sbom_digest", ""),
            ("provenance_digest", PROV),
            ("test_result_reference", "https://github.com/test/run/1"),
            ("verification_result_reference", "https://github.com/test/run/2"),
            ("generator_tool", "cold-storage.release.evidence_collector:v0.2.0-slice2-r1"),
            (
                "artifacts",
                [{"relative_path": "backend/Dockerfile", "size_bytes": 100, "sha256": "x"}],
            ),
        ]
    )


def test_build_manifest_produces_ordered_dict() -> None:
    manifest = build_manifest(_fields())
    keys = list(manifest.keys())
    assert keys[0] == "schema_version"
    assert keys[-1] == "artifacts"


def test_manifest_digest_is_canonical_sha256() -> None:
    manifest = build_manifest(_fields())
    digest = compute_manifest_digest(manifest)
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_verify_manifest_digest_passes_when_correct() -> None:
    manifest = build_manifest(_fields())
    digest = compute_manifest_digest(manifest)
    verify_manifest_digest(manifest, digest)


def test_verify_manifest_digest_rejects_mismatch() -> None:
    manifest = build_manifest(_fields())
    with pytest.raises(ReleaseEvidenceError) as exc:
        verify_manifest_digest(manifest, "sha256:" + "0" * 64)
    assert exc.value.failure_code == RC_ARTIFACT_DIGEST_MISMATCH


def test_load_manifest_rejects_duplicate_keys() -> None:
    raw = '{"schema_version":"x","schema_version":"y"}'
    with pytest.raises(ReleaseEvidenceError) as exc:
        load_manifest_from_text(raw)
    assert exc.value.failure_code == RC_ARTIFACT_DUPLICATE_KEY


def test_load_manifest_missing_file() -> None:
    with pytest.raises(ReleaseEvidenceError) as exc:
        load_manifest_from_path("/nonexistent/manifest.json")
    assert exc.value.failure_code == RC_ARTIFACT_MANIFEST_MISSING


def test_manifest_rejects_absolute_artifact_path() -> None:
    fields = _fields()
    fields["artifacts"] = [{"relative_path": "/etc/passwd", "size_bytes": 1, "sha256": "x"}]
    with pytest.raises(ArtifactManifestError):
        build_manifest(fields)


def test_manifest_rejects_secret_value() -> None:
    fields = _fields()
    fields["test_result_reference"] = "https://github.com?password=secret"
    with pytest.raises(ArtifactManifestError):
        build_manifest(fields)


def test_manifest_serialization_is_deterministic() -> None:
    manifest = build_manifest(_fields())
    assert serialize_manifest(manifest) == serialize_manifest(manifest)
    assert serialize_manifest(manifest).endswith(b"\n")


def test_manifest_rejects_wrong_schema_version() -> None:
    fields = _fields()
    fields["schema_version"] = "wrong-version"
    with pytest.raises(ArtifactManifestError):
        build_manifest(fields)


def test_manifest_rejects_missing_required_field() -> None:
    fields = _fields()
    del fields["final_image_digest"]
    with pytest.raises(ArtifactManifestError):
        build_manifest(fields)


def test_manifest_digest_excludes_no_mutation_on_verify() -> None:
    """Verifying a manifest does not mutate it (canonical recompute)."""
    manifest = build_manifest(_fields())
    digest = compute_manifest_digest(manifest)
    verify_manifest_digest(manifest, digest)
    assert compute_manifest_digest(manifest) == digest
