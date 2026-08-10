"""Release-candidate provenance statement (S2_GAP_04).

Implements the ``cold-storage-release-candidate-provenance-v1`` schema
frozen in Section 9 of the contract.  The provenance statement is a
machine-verifiable JSON document that binds the final image digest and
the artifact manifest digest to a build identity, and is protected
against tampering by an attestation binding (the contract-allowed
equivalent of a cryptographic signature for this scope).
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from cold_storage.release.canonical_serialization import (
    CanonicalSerializationError,
    ReleaseEvidenceError,
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    reject_secret_values,
)
from cold_storage.release.provenance_schema import (
    ALLOWED_WORKFLOW_REFS,
    EXPECTED_OIDC_ISSUER,
    EXPECTED_SOURCE_COMMIT_SHA,
    EXPECTED_SOURCE_REPOSITORY,
    EXPECTED_SOURCE_TREE_SHA,
    EXPECTED_WORKFLOW_IDENTITY,
    PROVENANCE_FIELD_ORDER,
    PROVENANCE_SCHEMA_VERSION,
    RC_PROVENANCE_REPO_MISMATCH,
    RC_PROVENANCE_SUBJECT_MISMATCH,
    RC_PROVENANCE_UNSIGNED,
    RC_PROVENANCE_WORKFLOW_MISMATCH,
)


class ProvenanceError(ReleaseEvidenceError):
    """Failure raised by provenance-statement operations."""


REQUIRED_PROVENANCE_FIELDS = (
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
    "attestation",
)

DIGEST_PATTERN = "sha256:"
LIVE_ATTESTATION_SCHEMA_VERSION = "cold-storage-live-attestation-v1"
LIVE_ATTESTATION_SUBJECT_SCHEMA = "cold-storage-release-evidence-attestation-subject-v1"
LIVE_ATTESTATION_MECHANISM = "write_once_integrity"
LIVE_ATTESTATION_FIELD_ORDER = (
    "schema_version",
    "task",
    "version",
    "slice",
    "mechanism",
    "subject_schema",
    "subject_digest_algorithm",
    "binding",
)
_LOWER_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(DIGEST_PATTERN)
        and len(value) == len(DIGEST_PATTERN) + 64
    )


def _ordered(fields: Mapping[str, Any]) -> OrderedDict[str, Any]:
    out: OrderedDict[str, Any] = OrderedDict()
    for key in PROVENANCE_FIELD_ORDER:
        if key in fields:
            out[key] = fields[key]
    return out


def verify_required_fields(fields: Mapping[str, Any]) -> None:
    for name in REQUIRED_PROVENANCE_FIELDS:
        if name not in fields or fields[name] in (None, ""):
            raise ProvenanceError(
                failure_code="RC_PROVENANCE_INCOMPLETE",
                detail=f"missing required provenance field: {name}",
            )


def build_provenance(fields: Mapping[str, Any]) -> OrderedDict[str, Any]:
    """Build an ordered, validated provenance statement dict.

    ``provenance_digest`` is excluded from the build-time presence check
    because it is computed *after* the statement is assembled.
    """
    if fields.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        raise ProvenanceError(
            failure_code="RC_PROVENANCE_SCHEMA_VERSION",
            detail="provenance schema_version mismatch",
        )
    # Structural presence checks (provenance_digest and
    # subject_artifact_manifest_digest are computed after assembly due to
    # the manifest↔provenance digest circularity).
    for name in REQUIRED_PROVENANCE_FIELDS:
        if name in ("provenance_digest", "subject_artifact_manifest_digest"):
            continue
        if name not in fields or fields[name] in (None, ""):
            raise ProvenanceError(
                failure_code="RC_PROVENANCE_INCOMPLETE",
                detail=f"missing required provenance field: {name}",
            )
    ordered = _ordered(fields)
    reject_secret_values(ordered)
    return ordered


def build_pre_attestation_provenance(fields: Mapping[str, Any]) -> OrderedDict[str, Any]:
    """Build the provenance input used before a live attestation exists.

    The pre-attestation document intentionally omits ``attestation``.  Its
    digest still uses the frozen provenance field order and the existing
    canonical serializer; the attestation and artifact-manifest subject
    fields are excluded by :func:`compute_provenance_digest`.
    """
    if fields.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        raise ProvenanceError(
            failure_code="RC_PROVENANCE_SCHEMA_VERSION",
            detail="provenance schema_version mismatch",
        )
    for name in REQUIRED_PROVENANCE_FIELDS:
        if name in ("attestation", "provenance_digest", "subject_artifact_manifest_digest"):
            continue
        if name not in fields or fields[name] in (None, ""):
            raise ProvenanceError(
                failure_code="RC_PROVENANCE_INCOMPLETE",
                detail=f"missing required provenance field: {name}",
            )
    ordered = _ordered(fields)
    reject_secret_values(ordered)
    return ordered


def compute_provenance_digest(provenance: Mapping[str, Any]) -> str:
    """Return ``sha256:<hex>`` of the canonical provenance bytes.

    The ``provenance_digest``, ``attestation``, and
    ``subject_artifact_manifest_digest`` fields are excluded from the
    digest input so the digest is stable and non-circular.  The
    subject-artifact binding is verified separately in
    :func:`verify_provenance` via cross-check against the expected
    artifact manifest digest.
    """
    stripped: OrderedDict[str, Any] = OrderedDict()
    for key, value in provenance.items():
        if key in ("provenance_digest", "attestation", "subject_artifact_manifest_digest"):
            continue
        stripped[key] = value
    return canonical_digest(stripped)


def compute_live_attestation_subject_digest(
    provenance_digest: str, artifact_manifest_digest: str
) -> str:
    """Compute the frozen composite P/M attestation subject digest."""
    if _LOWER_SHA256_RE.fullmatch(provenance_digest) is None:
        raise ProvenanceError(
            failure_code="ATTESTATION_BINDING_INVALID",
            detail="provenance digest is not a canonical SHA-256 digest",
        )
    if _LOWER_SHA256_RE.fullmatch(artifact_manifest_digest) is None:
        raise ProvenanceError(
            failure_code="ATTESTATION_BINDING_INVALID",
            detail="artifact manifest digest is not a canonical SHA-256 digest",
        )
    subject = OrderedDict(
        [
            ("schema_version", LIVE_ATTESTATION_SUBJECT_SCHEMA),
            ("provenance_digest", provenance_digest),
            ("artifact_manifest_digest", artifact_manifest_digest),
        ]
    )
    return canonical_digest(subject)


def verify_live_attestation(
    attestation: Mapping[str, Any],
    *,
    expected_provenance_digest: str,
    expected_artifact_manifest_digest: str,
) -> str:
    """Verify the exact Slice 2 live attestation schema and P/M/S binding."""
    if not isinstance(attestation, Mapping):
        raise ProvenanceError(
            failure_code="ATTESTATION_SCHEMA_INVALID",
            detail="live attestation must be an object",
        )
    for value in attestation.values():
        if isinstance(value, str) and any(
            marker in value for marker in ("TEST_ONLY", "SYNTHETIC_ONLY")
        ):
            raise ProvenanceError(
                failure_code="ATTESTATION_SYNTHETIC_REJECTED",
                detail="synthetic live attestation is not accepted",
            )
    if tuple(attestation.keys()) != LIVE_ATTESTATION_FIELD_ORDER:
        raise ProvenanceError(
            failure_code="ATTESTATION_SCHEMA_INVALID",
            detail="live attestation fields must exactly match the frozen schema",
        )
    expected_values: tuple[tuple[str, Any], ...] = (
        ("schema_version", LIVE_ATTESTATION_SCHEMA_VERSION),
        ("task", "TASK-012"),
        ("version", "V0.2"),
        ("slice", 2),
        ("mechanism", LIVE_ATTESTATION_MECHANISM),
        ("subject_schema", LIVE_ATTESTATION_SUBJECT_SCHEMA),
        ("subject_digest_algorithm", "sha256"),
    )
    for field, expected in expected_values:
        if attestation.get(field) != expected:
            raise ProvenanceError(
                failure_code=(
                    "ATTESTATION_MECHANISM_UNSUPPORTED"
                    if field == "mechanism"
                    else "ATTESTATION_SCHEMA_INVALID"
                ),
                detail=f"live attestation {field} mismatch",
            )
    binding = attestation.get("binding")
    if not isinstance(binding, str) or _LOWER_SHA256_RE.fullmatch(binding) is None:
        raise ProvenanceError(
            failure_code="ATTESTATION_BINDING_INVALID",
            detail="live attestation binding must be sha256:<64 lowercase hex>",
        )
    expected_binding = compute_live_attestation_subject_digest(
        expected_provenance_digest, expected_artifact_manifest_digest
    )
    if binding != expected_binding:
        raise ProvenanceError(
            failure_code="ATTESTATION_SUBJECT_MISMATCH",
            detail="live attestation binding does not match the recomputed P/M subject",
        )
    return binding


def serialize_provenance(provenance: Mapping[str, Any]) -> bytes:
    """Return the canonical byte sequence (including attestation)."""
    return canonical_bytes(provenance)


def load_provenance_from_text(raw: str) -> OrderedDict[str, Any]:
    """Parse a provenance text, rejecting duplicate keys."""
    try:
        data = load_json_strict(raw)
    except CanonicalSerializationError as exc:
        raise ProvenanceError(
            failure_code="RC_PROVENANCE_DUPLICATE_KEY"
            if exc.failure_code == "DUPLICATE_JSON_KEY"
            else "RC_PROVENANCE_MALFORMED",
            detail=exc.detail,
        ) from exc
    return _ordered(data)


def verify_provenance(
    provenance: Mapping[str, Any],
    *,
    expected_image_digest: str,
    expected_artifact_manifest_digest: str,
    require_live_attestation: bool = False,
) -> None:
    """Verify a provenance statement against the RC trust boundary.

    Raises :class:`ProvenanceError` with the matching ``RC_*`` code on
    any violation.  Unknown schema versions or unsigned provenance fail
    closed.
    """
    if provenance.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_UNSIGNED,
            detail="unknown provenance schema_version; fail closed",
        )

    # --- signing / equivalent tamper-evidence mechanism ---
    attestation = provenance.get("attestation")
    if not isinstance(attestation, Mapping):
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_UNSIGNED,
            detail="provenance lacks attestation binding",
        )
    mechanism = attestation.get("mechanism")
    binding = attestation.get("binding")
    issuer = attestation.get("issuer")
    if mechanism not in ("github_oidc", "cosign", "gpg", "write_once_integrity"):
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_UNSIGNED,
            detail=f"unsupported attestation mechanism: {mechanism!r}",
        )
    if not binding:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_UNSIGNED,
            detail="attestation binding missing",
        )
    if mechanism == "github_oidc" and issuer != EXPECTED_OIDC_ISSUER:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_UNSIGNED,
            detail=f"unexpected OIDC issuer: {issuer!r}",
        )

    if require_live_attestation:
        recomputed_provenance_digest = compute_provenance_digest(provenance)
        if provenance.get("provenance_digest") != recomputed_provenance_digest:
            raise ProvenanceError(
                failure_code="ATTESTATION_SUBJECT_MISMATCH",
                detail="provenance_digest does not match recomputed pre-attestation digest",
            )
        verify_live_attestation(
            attestation,
            expected_provenance_digest=recomputed_provenance_digest,
            expected_artifact_manifest_digest=expected_artifact_manifest_digest,
        )

    # --- repository / workflow / ref trust boundary ---
    if provenance.get("source_repository") != EXPECTED_SOURCE_REPOSITORY:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_REPO_MISMATCH,
            detail=f"source_repository mismatch: {provenance.get('source_repository')!r}",
        )
    workflow_identity = provenance.get("build_workflow_identity")
    if workflow_identity != EXPECTED_WORKFLOW_IDENTITY:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_WORKFLOW_MISMATCH,
            detail=f"build_workflow_identity mismatch: {workflow_identity!r}",
        )
    ref = provenance.get("build_workflow_ref")
    if ref not in ALLOWED_WORKFLOW_REFS:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_WORKFLOW_MISMATCH,
            detail=f"build_workflow_ref not allowed for RC: {ref!r}",
        )

    # --- subject digest cross-check ---
    subject_image = provenance.get("subject_final_image_digest")
    if subject_image != expected_image_digest:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_SUBJECT_MISMATCH,
            detail="subject_final_image_digest does not match authoritative image digest",
        )
    subject_artifact = provenance.get("subject_artifact_manifest_digest")
    if subject_artifact != expected_artifact_manifest_digest:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_SUBJECT_MISMATCH,
            detail="subject_artifact_manifest_digest does not match authoritative artifact digest",
        )

    # --- source commit / tree binding ---
    if provenance.get("source_commit_sha") != EXPECTED_SOURCE_COMMIT_SHA:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_SUBJECT_MISMATCH,
            detail="source_commit_sha does not match frozen RC commit",
        )
    if provenance.get("source_tree_sha") != EXPECTED_SOURCE_TREE_SHA:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_SUBJECT_MISMATCH,
            detail="source_tree_sha does not match frozen RC tree",
        )

    # --- reproducible build result ---
    if provenance.get("reproducible_build_result") != "PASS":
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_UNSIGNED,
            detail="reproducible_build_result is not PASS; provenance not acceptable",
        )

    # --- secret scan ---
    try:
        reject_secret_values(provenance)
    except CanonicalSerializationError as exc:
        raise ProvenanceError(
            failure_code=RC_PROVENANCE_SUBJECT_MISMATCH,
            detail=f"secret value detected: {exc.detail}",
        ) from exc


__all__ = [
    "LIVE_ATTESTATION_FIELD_ORDER",
    "LIVE_ATTESTATION_MECHANISM",
    "LIVE_ATTESTATION_SCHEMA_VERSION",
    "LIVE_ATTESTATION_SUBJECT_SCHEMA",
    "ProvenanceError",
    "REQUIRED_PROVENANCE_FIELDS",
    "build_provenance",
    "build_pre_attestation_provenance",
    "compute_live_attestation_subject_digest",
    "compute_provenance_digest",
    "load_provenance_from_text",
    "serialize_provenance",
    "verify_live_attestation",
    "verify_provenance",
]
