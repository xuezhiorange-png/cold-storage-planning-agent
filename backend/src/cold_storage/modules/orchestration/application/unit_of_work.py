"""Orchestration Unit of Work protocol.

The application service owns the transaction lifecycle.
Repositories accept a session and NEVER commit, rollback, close,
or create sessions.

Implementation in later phases.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session


@runtime_checkable
class OrchestrationUnitOfWork(Protocol):
    """Transaction boundary owned by the application service."""

    session: Session

    def begin(self) -> None:
        """Begin a new transaction."""
        ...

    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    def rollback(self) -> None:
        """Rollback the current transaction."""
        ...

    def close(self) -> None:
        """Close the session and release resources."""
        ...
