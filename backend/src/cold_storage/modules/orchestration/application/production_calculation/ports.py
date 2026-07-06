"""Task 11B Phase 2 — application port contracts.

This module defines the abstract ports the orchestrator (Phase 3+)
will compose.  No concrete adapter is bound here — implementations
live in submodules under
``orchestration.application.production_calculation.adapters``.

Every port is a ``Protocol`` with a typed return shape so callers
can verify at type-check time that the implementation satisfies the
contract.
"""

from __future__ import annotations

from typing import Any, Protocol

from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterResult,
    ApprovedProjectVersionSnapshot,
    CalculatorInputProjection,
)

# ── Approved project version read port ─────────────────────────────────────


class ApprovedProjectVersionReadPort(Protocol):
    """Read-only port that returns the approved project version snapshot.

    The port implementation is responsible for verifying that:

    * the version exists
    * the version is not archived
    * the version's status is ``APPROVED``
    * the version belongs to the requested project

    Implementations MUST return ``None`` (not raise) when the
    version is not found, is archived, or has the wrong status.
    The caller is responsible for mapping ``None`` to a
    :class:`MissingApprovedProjectVersionError`.  This separation
    keeps the port pure and lets the orchestrator apply the
    fail-closed mapping once for every adapter stage.
    """

    def load_approved_version(
        self,
        session: Any,
        /,
        *,
        project_id: str,
        project_version_id: str,
    ) -> ApprovedProjectVersionSnapshot | None:
        """Return the approved version snapshot, or ``None`` if unavailable."""
        ...


# ── Calculation adapter ports ──────────────────────────────────────────────


class ZonePlanningCalculationPort(Protocol):
    """Adapter port for the zone planning calculator."""

    def execute(
        self,
        projection: CalculatorInputProjection,
    ) -> AdapterResult:
        """Return the zone planning adapter result."""
        ...


class CoolingLoadCalculationPort(Protocol):
    """Adapter port for the cooling load calculator."""

    def execute(
        self,
        projection: CalculatorInputProjection,
    ) -> AdapterResult:
        """Return the cooling load adapter result."""
        ...


class EquipmentCapabilityCalculationPort(Protocol):
    """Adapter port for the equipment capability calculator."""

    def execute(
        self,
        projection: CalculatorInputProjection,
    ) -> AdapterResult:
        """Return the equipment capability adapter result."""
        ...


class InstalledPowerCalculationPort(Protocol):
    """Adapter port for the installed power calculator."""

    def execute(
        self,
        projection: CalculatorInputProjection,
    ) -> AdapterResult:
        """Return the installed power adapter result."""
        ...


class InvestmentCalculationPort(Protocol):
    """Adapter port for the investment estimator."""

    def execute(
        self,
        projection: CalculatorInputProjection,
    ) -> AdapterResult:
        """Return the investment adapter result."""
        ...
