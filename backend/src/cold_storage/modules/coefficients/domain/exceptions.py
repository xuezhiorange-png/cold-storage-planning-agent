"""Domain exceptions for the coefficient registry."""

from __future__ import annotations


class CoefficientDomainError(Exception):
    """Base exception for all coefficient domain errors."""


class CoefficientNotFoundError(CoefficientDomainError):
    """Raised when a coefficient definition or revision is not found."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"Coefficient not found: {identifier}")


class DuplicateCoefficientCodeError(CoefficientDomainError):
    """Raised when attempting to create a definition with a duplicate code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Coefficient code already exists: {code}")


class DuplicateRevisionNumberError(CoefficientDomainError):
    """Raised when a revision number already exists for a definition."""

    def __init__(self, definition_id: str, revision_number: int) -> None:
        self.definition_id = definition_id
        self.revision_number = revision_number
        super().__init__(
            f"Revision {revision_number} already exists for definition {definition_id}"
        )


class InvalidRevisionTransitionError(CoefficientDomainError):
    """Raised when an invalid revision state transition is attempted."""

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition from '{from_status}' to '{to_status}'")


class RevisionImmutabilityError(CoefficientDomainError):
    """Raised when attempting to modify a locked (approved/withdrawn) revision."""

    def __init__(self, revision_id: str, status: str, operation: str) -> None:
        self.revision_id = revision_id
        self.status = status
        self.operation = operation
        super().__init__(
            f"Cannot {operation} on revision {revision_id} with status '{status}'. "
            f"Approved/withdrawn revisions are immutable."
        )


class SupersedesCrossDefinitionError(CoefficientDomainError):
    """Raised when supersedes_revision_id crosses definition boundaries."""

    def __init__(self, supersedes_id: str, expected_def: str, actual_def: str) -> None:
        self.supersedes_id = supersedes_id
        self.expected_definition_id = expected_def
        self.actual_definition_id = actual_def
        super().__init__(
            f"Revision supersedes {supersedes_id} belongs to definition "
            f"{actual_def}, not {expected_def}"
        )
