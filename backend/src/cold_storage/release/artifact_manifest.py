"""Canonical artifact manifest (S2_GAP_03).

Implements the ``cold-storage-release-candidate-artifact-manifest-v1``
schema frozen in Section 8 of the contract.  The manifest is a
deterministic JSON document whose authoritative digest is
``sha256(canonical manifest bytes)``.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.release.canonical_serialization import (
    CanonicalSerializationError,
    ReleaseEvidenceError,
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    reject_absolute_paths,
    reject_secret_values,
)
from cold_storage.release.provenance_schema import (
    ARTIFACT_MANIFEST_FIELD_ORDER,
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    RC_ARTIFACT_DIGEST_MISMATCH,
    RC_ARTIFACT_DUPLICATE_KEY,
    RC_ARTIFACT_MANIFEST_MISSING,
)


class ArtifactManifestError(ReleaseEvidenceError):
    """Failure raised by artifact-manifest operations."""


def _ordered(fields: Mapping[str, Any]) -> OrderedDict[str, Any]:
    """Return a new ordered dict in the frozen schema field order.

    Unknown keys are dropped (strict mode: callers build from the frozen
    field set).  Missing required keys are left absent so that
    :func:`verify_required_fields` can flag them.
    """
    out: OrderedDict[str, Any] = OrderedDict()
    for key in ARTIFACT_MANIFEST_FIELD_ORDER:
        if key in fields:
            out[key] = fields[key]
    return out


REQUIRED_ARTIFACT_FIELDS = (
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
    "generator_tool",
    "artifacts",
)


def verify_required_fields(fields: Mapping[str, Any]) -> None:
    """Reject manifests missing any required field."""
    for name in REQUIRED_ARTIFACT_FIELDS:
        if name not in fields or fields[name] in (None, ""):
            raise ArtifactManifestError(
                failure_code=RC_ARTIFACT_DIGEST_MISMATCH,
                detail=f"missing required artifact-manifest field: {name}",
            )


def build_manifest(fields: Mapping[str, Any]) -> OrderedDict[str, Any]:
    """Build an ordered, validated manifest dict (without the digest field).

    ``provenance_digest`` and ``sbom_digest`` are optional; ``artifacts``
    is normalized to a list of objects each containing
    ``relative_path``, ``size_bytes``, ``sha256``.
    """
    verify_required_fields(fields)
    if fields.get("schema_version") != ARTIFACT_MANIFEST_SCHEMA_VERSION:
        raise ArtifactManifestError(
            failure_code=RC_ARTIFACT_DIGEST_MISMATCH,
            detail="artifact manifest schema_version mismatch",
        )
    artifacts = fields.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ArtifactManifestError(
            failure_code=RC_ARTIFACT_DIGEST_MISMATCH,
            detail="artifacts must be a list",
        )
    try:
        reject_absolute_paths(artifacts)
    except CanonicalSerializationError as exc:
        raise ArtifactManifestError(
            failure_code=RC_ARTIFACT_DIGEST_MISMATCH,
            detail=exc.detail,
        ) from exc
    ordered = _ordered(fields)
    try:
        reject_secret_values(ordered)
    except CanonicalSerializationError as exc:
        raise ArtifactManifestError(
            failure_code=RC_ARTIFACT_DIGEST_MISMATCH,
            detail=exc.detail,
        ) from exc
    return ordered


def serialize_manifest(manifest: Mapping[str, Any]) -> bytes:
    """Return the canonical byte sequence of a manifest."""
    return canonical_bytes(manifest)


def compute_manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Return ``sha256:<hex>`` of the canonical manifest bytes."""
    return canonical_digest(manifest)


def attach_digest(manifest: OrderedDict[str, Any]) -> OrderedDict[str, Any]:
    """Return a copy with ``provenance_digest`` is NOT set here — the
    artifact manifest digest is computed over the manifest *without* an
    embedded self-digest.  This helper exists for callers that want the
    canonical bytes excluding any self-reference; it returns the manifest
    unchanged (the digest is external).
    """
    return manifest


def load_manifest_from_text(raw: str) -> OrderedDict[str, Any]:
    """Parse a manifest text, rejecting duplicate keys.

    Duplicate keys raise :class:`ArtifactManifestError` with
    ``RC_ARTIFACT_DUPLICATE_KEY``.
    """
    try:
        data = load_json_strict(raw)
    except CanonicalSerializationError as exc:
        if exc.failure_code == "DUPLICATE_JSON_KEY":
            raise ArtifactManifestError(
                failure_code=RC_ARTIFACT_DUPLICATE_KEY,
                detail=exc.detail,
            ) from exc
        raise ArtifactManifestError(
            failure_code=RC_ARTIFACT_DIGEST_MISMATCH,
            detail=exc.detail,
        ) from exc
    return _ordered(data)


def load_manifest_from_path(path: str | Path) -> OrderedDict[str, Any]:
    """Load a manifest from a file path.

    A missing file raises :class:`ArtifactManifestError` with
    ``RC_ARTIFACT_MANIFEST_MISSING``.
    """
    p = Path(path)
    if not p.is_file():
        raise ArtifactManifestError(
            failure_code=RC_ARTIFACT_MANIFEST_MISSING,
            detail=f"artifact manifest not found: {p}",
        )
    raw = p.read_text(encoding="utf-8")
    return load_manifest_from_text(raw)


def verify_manifest_digest(manifest: Mapping[str, Any], expected_digest: str) -> None:
    """Verify that the canonical manifest digest equals *expected_digest*.

    Raises :class:`ArtifactManifestError` with ``RC_ARTIFACT_DIGEST_MISMATCH``
    on mismatch or when the manifest is structurally invalid.
    """
    try:
        verify_required_fields(manifest)
        reject_secret_values(manifest)
        artifacts = manifest.get("artifacts", [])
        if isinstance(artifacts, list):
            reject_absolute_paths(artifacts)
    except CanonicalSerializationError as exc:
        raise ArtifactManifestError(
            failure_code=RC_ARTIFACT_DIGEST_MISMATCH,
            detail=exc.detail,
        ) from exc
    actual = compute_manifest_digest(manifest)
    if actual != expected_digest:
        raise ArtifactManifestError(
            failure_code=RC_ARTIFACT_DIGEST_MISMATCH,
            detail=f"artifact manifest digest mismatch: expected {expected_digest} got {actual}",
        )


def verify_manifest_text(raw: str, expected_digest: str) -> None:
    """Parse + verify a manifest text in one step."""
    manifest = load_manifest_from_text(raw)
    verify_manifest_digest(manifest, expected_digest)


__all__ = [
    "ArtifactManifestError",
    "REQUIRED_ARTIFACT_FIELDS",
    "build_manifest",
    "compute_manifest_digest",
    "load_manifest_from_path",
    "load_manifest_from_text",
    "serialize_manifest",
    "verify_manifest_digest",
    "verify_manifest_text",
    "verify_required_fields",
]
