"""Source snapshot content/envelope DTOs — immutable, execution-bound.

``result_hash`` is the SHA-256 of the canonical JSON encoding of the
complete ``SourceSnapshotContentV1``, including provenance (see §13.5.7
of the approved design).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


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


@dataclass(frozen=True, slots=True)
class SourceSnapshotContentV1:
    """Complete hashed content for a single calculator stage.

    ``result_hash = SHA-256(canonical_json(self))``.
    The hash covers ALL fields in this DTO — metadata, payload, provenance,
    and ``requires_review``.
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


@dataclass(frozen=True, slots=True)
class SourceSnapshotEnvelopeV1:
    """Envelope carrying result_hash outside the hashed content."""

    content: SourceSnapshotContentV1
    result_hash: str
