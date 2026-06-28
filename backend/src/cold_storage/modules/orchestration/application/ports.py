"""Orchestration preflight ports.

Defines the application-level contracts for snapshot-schema and
coefficient-resolution validation.  Concrete implementations belong
in later sub-tasks (B/C); this phase uses test doubles to verify
error mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ResolvedCoefficientContextCandidate:
    """Resolved coefficient context returned by the resolution port.

    All fields are derived from the production coefficient catalog,
    never from caller self-attestation.
    """

    project_id: str
    project_version_id: str
    schema_version: str
    content: Mapping[str, object]
    content_hash: str
    approved_revision_ids: tuple[str, ...]


class CoefficientResolutionPreflightPort(Protocol):
    """Resolve an approved coefficient context for the given project/version.

    Returns a typed ``ResolvedCoefficientContextCandidate`` with verified
    approved revisions.  The caller must not forge ``source_type=approved``
    in the payload — that field comes from the catalog.
    """

    def resolve(
        self,
        *,
        project_id: str,
        project_version_id: str,
        coefficient_resolution_context: dict[str, object],
    ) -> ResolvedCoefficientContextCandidate:
        """Return a verified coefficient candidate.

        Raises ``CoefficientResolutionError``, ``CoefficientNotApprovedError``,
        or ``AmbiguousCoefficientError`` as appropriate.
        """
        ...
