"""Source snapshot content/envelope DTOs — immutable, execution-bound.

``result_hash`` is the SHA-256 of the canonical JSON encoding of the
complete ``SourceSnapshotContentV1``, including provenance (see §13.5.7
of the approved design).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from cold_storage.modules.orchestration.domain.contracts import (
    validate_content_provenance_identity_consistency,
)


@dataclass(frozen=True, slots=True)
class SourceSnapshotProvenanceV1:
    """Execution-bound provenance frozen into the source snapshot content.

    ``upstream_calculation_ids`` is an exact-key mapping per stage:
        zone        → {}
        cooling_load→ {"zone": "<calculation_run_id>"}
        equipment   → {"cooling_load": "<calculation_run_id>"}
        power       → {"equipment": "<calculation_run_id>"}
        investment  → {"zone": "<...>", "power": "<...>"}

    All values are non-null canonical ID strings.  Zone uses an empty mapping.
    """

    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    orchestration_run_attempt_id: str
    upstream_calculation_ids: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        from cold_storage.modules.orchestration.domain.contracts import deep_freeze

        frozen = deep_freeze(self.upstream_calculation_ids)
        if frozen is not self.upstream_calculation_ids:
            object.__setattr__(self, "upstream_calculation_ids", frozen)

        # ── Validate identity IDs are non-null, non-empty, non-whitespace ──
        for field_name in (
            "execution_snapshot_id",
            "coefficient_context_id",
            "orchestration_identity_id",
            "orchestration_run_attempt_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(
                    f"SourceSnapshotProvenanceV1.{field_name} must be str, "
                    f"got {type(value).__name__}"
                )
            if not value.strip():
                raise ValueError(
                    f"SourceSnapshotProvenanceV1.{field_name} must not be empty or whitespace"
                )


@dataclass(frozen=True, slots=True)
class SourceSnapshotContentV1:
    """Complete hashed content for a single calculator stage.

    ``result_hash = SHA-256(canonical_json(self))``.
    The hash covers ALL fields in this DTO — metadata, payload, provenance,
    and ``requires_review``.

    Deep immutability: ``payload`` is deeply frozen on construction.
    External mutation of the original payload dict cannot affect this DTO.

    Provenance validation: ``upstream_calculation_ids`` are verified against
    the frozen key set for ``calculation_type``.  Content-level identity
    fields must match provenance identity fields exactly.
    """

    schema_version: str
    calculation_type: str
    calculator_name: str
    calculator_version: str
    project_id: str
    project_version_id: str
    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    orchestration_run_attempt_id: str
    input_hash: str
    requires_review: bool
    payload: Mapping[str, object]
    provenance: SourceSnapshotProvenanceV1

    def __post_init__(self) -> None:
        # ── Deep-freeze payload ─────────────────────────────────────────
        from cold_storage.modules.orchestration.domain.contracts import deep_freeze

        frozen_payload = deep_freeze(self.payload)
        if frozen_payload is not self.payload:
            object.__setattr__(self, "payload", frozen_payload)

        # Note: upstream provenance KEY set validation is performed by
        # SourceBindingVerifier._verify_upstream_provenance, not here.

        # ── Validate content/provenance identity consistency ─────────────
        validate_content_provenance_identity_consistency(
            calculation_type=self.calculation_type,
            execution_snapshot_id=self.execution_snapshot_id,
            coefficient_context_id=self.coefficient_context_id,
            orchestration_identity_id=self.orchestration_identity_id,
            orchestration_run_attempt_id=self.orchestration_run_attempt_id,
            provenance_execution_snapshot_id=self.provenance.execution_snapshot_id,
            provenance_coefficient_context_id=self.provenance.coefficient_context_id,
            provenance_orchestration_identity_id=self.provenance.orchestration_identity_id,
            provenance_orchestration_run_attempt_id=self.provenance.orchestration_run_attempt_id,
        )


@dataclass(frozen=True, slots=True)
class SourceSnapshotEnvelopeV1:
    """Envelope carrying result_hash outside the hashed content."""

    content: SourceSnapshotContentV1
    result_hash: str


# ── Shared builder ─────────────────────────────────────────────────────────


def build_source_snapshot_content_v1(
    *,
    schema_version: str,
    calculation_type: str,
    calculator_name: str,
    calculator_version: str,
    project_id: str,
    project_version_id: str,
    execution_snapshot_id: str,
    coefficient_context_id: str,
    orchestration_identity_id: str,
    orchestration_run_attempt_id: str,
    input_hash: str,
    requires_review: bool,
    payload: Mapping[str, object],
    upstream_calculation_ids: Mapping[str, str],
) -> SourceSnapshotContentV1:
    """Build a domain-layer ``SourceSnapshotContentV1`` from individual fields.

    This is the **single canonical builder** used by both the Transaction B
    executor and the SourceBinding verifiers to produce the hash contract.
    Using this function ensures that ``result_hash`` (SHA-256 of the
    canonical JSON of ``SourceSnapshotContentV1``) is computed identically
    everywhere.
    """
    provenance = SourceSnapshotProvenanceV1(
        execution_snapshot_id=execution_snapshot_id,
        coefficient_context_id=coefficient_context_id,
        orchestration_identity_id=orchestration_identity_id,
        orchestration_run_attempt_id=orchestration_run_attempt_id,
        upstream_calculation_ids=upstream_calculation_ids,
    )
    return SourceSnapshotContentV1(
        schema_version=schema_version,
        calculation_type=calculation_type,
        calculator_name=calculator_name,
        calculator_version=calculator_version,
        project_id=project_id,
        project_version_id=project_version_id,
        execution_snapshot_id=execution_snapshot_id,
        coefficient_context_id=coefficient_context_id,
        orchestration_identity_id=orchestration_identity_id,
        orchestration_run_attempt_id=orchestration_run_attempt_id,
        input_hash=input_hash,
        requires_review=requires_review,
        payload=payload,
        provenance=provenance,
    )
