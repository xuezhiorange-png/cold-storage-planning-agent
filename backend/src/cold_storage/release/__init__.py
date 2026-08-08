"""TASK-012 V0.2 Slice 2 — release-candidate build & provenance evidence.

This package implements the five P0 gaps frozen in
``TASK-012-V0.2-SLICE2-RELEASE-CANDIDATE-BUILD-AND-PROVENANCE-EVIDENCE-GAP-CONTRACT-FREEZE-R1``:

* S2_GAP_01 — reproducible build evidence
* S2_GAP_02 — final image digest
* S2_GAP_03 — artifact manifest and digest
* S2_GAP_04 — release-candidate provenance
* S2_GAP_05 — environment promotion provenance

All verifiers adopt a unified fail-closed policy: missing, conflicting,
unverifiable, or partial evidence is rejected.  No secrets may appear in
any evidence field.
"""

from __future__ import annotations

from cold_storage.release.artifact_manifest import (
    ArtifactManifestError,
    build_manifest,
    compute_manifest_digest,
    verify_manifest_digest,
)
from cold_storage.release.canonical_serialization import (
    ReleaseEvidenceError,
    canonical_digest,
)
from cold_storage.release.digest_verifier import (
    ReproducibleBuildError,
    authoritative_image_digest,
    verify_reproducible_build,
)
from cold_storage.release.promotion_record import (
    PromotionError,
    verify_promotion,
)
from cold_storage.release.provenance_schema import (
    ALL_ERROR_CODES,
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    PROMOTION_RECORD_SCHEMA_VERSION,
    PROVENANCE_SCHEMA_VERSION,
)
from cold_storage.release.provenance_statement import (
    ProvenanceError,
    compute_provenance_digest,
    verify_provenance,
)

__all__ = [
    "ALL_ERROR_CODES",
    "ARTIFACT_MANIFEST_SCHEMA_VERSION",
    "ArtifactManifestError",
    "PROMOTION_RECORD_SCHEMA_VERSION",
    "PROVENANCE_SCHEMA_VERSION",
    "PromotionError",
    "ProvenanceError",
    "ReleaseEvidenceError",
    "ReproducibleBuildError",
    "authoritative_image_digest",
    "build_manifest",
    "canonical_digest",
    "compute_manifest_digest",
    "compute_provenance_digest",
    "verify_manifest_digest",
    "verify_promotion",
    "verify_provenance",
    "verify_reproducible_build",
]
