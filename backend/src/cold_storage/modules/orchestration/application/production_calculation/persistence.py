"""Task 11B Phase 2 — future CalculationRun persistence port contract.

The orchestrator (Phase 3+) will compose the persistence port to
write ``CalculationRunRecord`` rows.  This module defines the
**interface only** — no production row is written by Phase 2
adapters.  A future implementation is responsible for satisfying
the contract on top of the production ORM (Task 11B Phase 3+).

The Phase 2 deliverables here are:

* the ``CalculationRunDraft`` value object built by the pure
  mapper from an :class:`AdapterResult`
* the ``CalculationRunPersistencePort`` protocol the future
  implementation must satisfy
* a stub ``InMemoryCalculationRunPersistencePort`` that captures
  drafts in a list — used by Phase 2 tests to verify the
  mapper/contract end-to-end without touching the production
  ORM
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterResult,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

# ── Draft value object ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CalculationRunDraft:
    """Pure value object representing a future ``CalculationRunRecord``.

    Built by the :func:`map_adapter_result_to_draft` helper from an
    :class:`AdapterResult`.  The persistence port implementation
    is responsible for turning this draft into a row — Phase 2
    does not write rows.
    """

    calculation_type: CalculationType
    calculator_name: str
    calculator_version: str
    payload: Mapping[str, Any]
    content_hash: str
    requires_review: bool
    actor: str
    correlation_id: str
    database_backend: str
    upstream_calculation_ids: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    blockers: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    provenance: Mapping[str, Any] = field(default_factory=dict)


# ── Persistence port ───────────────────────────────────────────────────────


class CalculationRunPersistencePort(Protocol):
    """Future persistence port for ``CalculationRunRecord`` writes.

    The interface is intentionally minimal — it accepts a single
    :class:`CalculationRunDraft` and returns a deterministic
    ``draft_id`` (a string the implementation mints).  The
    implementation MUST NOT commit, rollback, close, or create
    sessions — it operates inside the caller's transaction
    boundary.

    Phase 2 ships an in-memory test double only.  The
    SQLAlchemy-backed production implementation is reserved
    for a separately-authorised task.
    """

    def stage_draft(
        self,
        session: Any,
        /,
        *,
        draft: CalculationRunDraft,
    ) -> str:
        """Stage a draft for persistence and return its draft id."""
        ...


# ── In-memory test double ──────────────────────────────────────────────────


class InMemoryCalculationRunPersistencePort:
    """In-memory ``CalculationRunPersistencePort`` test double.

    Captures each staged draft in ``self.staged`` so Phase 2 tests
    can assert the contract end-to-end.  The double is the only
    persistence adapter Phase 2 ships — production wiring is
    reserved for Phase 3+.
    """

    def __init__(self) -> None:
        self.staged: list[CalculationRunDraft] = []

    def stage_draft(
        self,
        session: Any,
        /,
        *,
        draft: CalculationRunDraft,
    ) -> str:
        # The double is session-agnostic: the contract says the
        # implementation MUST NOT touch the session, so the
        # double accepts any value (including ``None``) without
        # using it.
        del session
        self.staged.append(draft)
        return f"draft-{len(self.staged)}"


# ── Pure mapper ────────────────────────────────────────────────────────────


def map_adapter_result_to_draft(
    *,
    adapter_result: AdapterResult,
    actor: str,
    correlation_id: str,
    database_backend: str,
    upstream_calculation_ids: Mapping[str, str] | None = None,
) -> CalculationRunDraft:
    """Map an :class:`AdapterResult` to a :class:`CalculationRunDraft`.

    The mapper is a pure function — no I/O, no session.  It
    carries the threaded identity fields
    (``actor``/``correlation_id``/``database_backend``) onto the
    draft so the future persistence port can stamp the row
    without re-deriving them.
    """
    warnings: tuple[Mapping[str, Any], ...] = tuple(
        {"code": w.code, "message": w.message, "details": dict(w.details)}
        for w in adapter_result.warnings
    )
    blockers: tuple[Mapping[str, Any], ...] = tuple(
        {
            "code": b.code,
            "message": b.message,
            "field": b.field_name,
            "details": dict(b.details),
        }
        for b in adapter_result.blockers
    )
    provenance: dict[str, Any] = {
        "formulas": [dict(f) for f in adapter_result.provenance.formulas],
        "coefficients": [dict(c) for c in adapter_result.provenance.coefficients],
        "source_references": [dict(s) for s in adapter_result.provenance.source_references],
        "assumptions": list(adapter_result.provenance.assumptions),
    }
    upstream = dict(upstream_calculation_ids) if upstream_calculation_ids else {}
    return CalculationRunDraft(
        calculation_type=adapter_result.calculation_type,
        calculator_name=adapter_result.calculator_name,
        calculator_version=adapter_result.calculator_version,
        payload=dict(adapter_result.payload),
        content_hash=adapter_result.content_hash,
        requires_review=adapter_result.requires_review,
        actor=actor,
        correlation_id=correlation_id,
        database_backend=database_backend,
        upstream_calculation_ids=upstream,
        warnings=warnings,
        blockers=blockers,
        provenance=provenance,
    )
