"""Orchestration Unit of Work — concrete SQLAlchemy implementation.

The application service owns the transaction lifecycle via the
UnitOfWork.  Repositories accept a session and NEVER commit, rollback,
close, or create sessions.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker


class SqlAlchemyOrchestrationUnitOfWork:
    """Transaction boundary owned by the application service."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def begin(self) -> None:
        """Begin a new transaction (no-op — session is transactional by default)."""
        pass

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()

    def close(self) -> None:
        """Close the session and release resources."""
        self.session.close()


class SqlAlchemyOrchestrationUnitOfWorkFactory:
    """Creates UnitOfWork instances from a session factory."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def __call__(self) -> Generator[SqlAlchemyOrchestrationUnitOfWork, None, None]:
        session = self._session_factory()
        uow = SqlAlchemyOrchestrationUnitOfWork(session)
        try:
            yield uow
        except Exception:
            uow.rollback()
            raise
        finally:
            uow.close()
