"""Application-level Unit of Work protocol for production scheme generation.

The ProductionSchemeUnitOfWork protocol defines the transaction boundary
for production scheme persistence.  The application service owns the
UoW lifecycle: create, enter, commit on success, exit (close session).

Infrastructure provides the concrete implementation.  The application
layer MUST NOT import SQLAlchemy.
"""

from __future__ import annotations

from typing import Any, Protocol


class ProductionSchemeUnitOfWork(Protocol):
    """Transaction boundary for production scheme persistence."""

    @property
    def session(self) -> Any:
        """Database session for the current transaction."""
        ...

    def __enter__(self) -> ProductionSchemeUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
