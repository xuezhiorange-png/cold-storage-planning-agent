"""Orchestration preflight ports.

Defines the application-level contracts for snapshot-schema and
coefficient-resolution validation.  Concrete implementations belong
in later sub-tasks (B/C); this phase uses test doubles to verify
error mapping.
"""

from __future__ import annotations

from typing import Protocol


class ExecutionSnapshotPreflightPort(Protocol):
    """Validate that the approved ProjectVersion can be captured as a valid
    execution snapshot candidate."""

    def validate_candidate(
        self,
        *,
        project_id: str,
        project_version_id: str,
        version_status: str,
    ) -> None:
        """Raise ``ExecutionSnapshotSchemaError`` when the snapshot schema
        is invalid or unsupported."""
        ...


class CoefficientResolutionPreflightPort(Protocol):
    """Validate that an approved coefficient context can be resolved
    for the given project/version."""

    def validate_resolution(
        self,
        *,
        project_id: str,
        project_version_id: str,
        coefficient_resolution_context: dict[str, object],
    ) -> None:
        """Raise ``CoefficientResolutionError``, ``CoefficientNotApprovedError``,
        or ``AmbiguousCoefficientError`` as appropriate."""
        ...
