"""Task 11B Phase 2 — DTOs for production calculation ports & adapters.

Every DTO is a frozen dataclass with explicit field types.  No ORM rows
are accepted as DTO inputs — all data passes through a typed boundary
that the production orchestrator (Phase 3+) will compose.

These DTOs are the only data structures adapters are allowed to
exchange.  Evaluation fixtures and raw ORM rows are explicitly banned.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from cold_storage.modules.orchestration.domain.contracts import CalculationType

# ── Approved project version read port ─────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ApprovedProjectVersionSnapshot:
    """Read model for an *approved* project version.

    The read port contract is responsible for guaranteeing that the
    version is in ``APPROVED`` status, that it is not archived, and
    that it belongs to the requested project.  Callers MUST NOT
    fabricate these fields — they are populated only by the
    implementation that talks to the production ORM.
    """

    project_id: str
    project_version_id: str
    version_number: int
    version_status: str  # always "APPROVED" when constructed by the port
    is_archived: bool  # always False when constructed by the port
    approved_at: datetime | None
    approved_by: str | None
    # The project-version-bound input snapshot used by Phase 3 to
    # derive calculator inputs.  Phase 2 passes it through but does
    # not interpret it — adapters are only allowed to read fields
    # they explicitly request.
    input_snapshot: dict[str, object] = field(default_factory=dict)
    schema_version: str = "v1"


# ── Calculator input projection ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CalculatorInputProjection:
    """Projected calculator input built from an approved project version.

    The projection DTO is the only input adapters accept.  Adapters
    MUST NOT read from the raw ``input_snapshot``; they MUST receive
    a fully-typed ``CalculatorInputProjection`` constructed by the
    projection helper.

    All ``Mapping`` values are defensively copied on construction
    so external mutation never affects a built projection.
    """

    calculation_type: CalculationType
    # The verbatim dict consumed by the underlying calculator function.
    # Callers MUST construct this from the approved project version
    # snapshot — evaluation fixtures are forbidden.
    raw_inputs: dict[str, object]
    # Identity fields threaded through to the future CalculationRunRecord.
    actor: str
    correlation_id: str
    database_backend: str
    # Optional upstream linkage (e.g. zone → cooling load) — empty
    # tuple for stage 1 (zone planning).
    upstream_calculation_ids: dict[str, str] = field(default_factory=dict)
    # Optional revision linkage so the future persistence layer can
    # stamp the draft with the right identity.
    calculator_name: str = ""
    calculator_version: str = ""


# ── Adapter result DTO ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AdapterWarning:
    """Typed warning surface propagated verbatim from the calculator.

    Adapters MUST pass warnings through unchanged.  They MUST NOT
    suppress, reclassify, or drop warnings — even if the calculator
    succeeded.
    """

    code: str
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterBlocker:
    """Typed blocker surface — calculator refused the input.

    A non-empty ``AdapterResult.blockers`` list is always a
    fail-closed outcome.  The orchestrator (Phase 3) MUST NOT
    continue to subsequent stages when blockers are present.
    """

    code: str
    message: str
    # ``field_name`` (not ``field``) avoids shadowing the
    # imported ``dataclasses.field`` helper.  With
    # ``from __future__ import annotations`` and a class-body
    # annotation named ``field: str``, mypy resolves
    # ``field(default_factory=...)`` to the annotation rather
    # than the module-level import.
    field_name: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterProvenance:
    """Provenance summary required for the future persistence layer.

    Carries the formula / coefficient references the calculator
    returned.  Adapters MUST propagate the upstream
    ``formula_references`` and ``source_references`` verbatim.
    """

    formulas: Sequence[dict[str, object]] = field(default_factory=tuple)
    coefficients: Sequence[dict[str, object]] = field(default_factory=tuple)
    source_references: Sequence[dict[str, object]] = field(default_factory=tuple)
    assumptions: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """Typed result returned by every calculation adapter.

    The shape is identical for all five calculation types; only the
    ``calculation_type`` discriminator and the ``payload`` content
    vary.  Adapters MUST:

    * populate ``content_hash`` from the canonicalised ``payload``
    * set ``requires_review`` from the calculator's verdict (no
      suppression)
    * propagate every warning / formula reference / coefficient
      reference without reclassification
    * never write to the database — that is the orchestrator's job
    """

    calculation_type: CalculationType
    payload: dict[str, object]
    content_hash: str
    requires_review: bool
    warnings: Sequence[AdapterWarning] = field(default_factory=tuple)
    blockers: Sequence[AdapterBlocker] = field(default_factory=tuple)
    provenance: AdapterProvenance = field(default_factory=AdapterProvenance)
    calculator_name: str = ""
    calculator_version: str = ""
    calculator_success: bool = True
