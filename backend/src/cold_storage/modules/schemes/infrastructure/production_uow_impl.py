"""SQLAlchemy implementation of ProductionSchemeUnitOfWork.

Manages the transaction boundary for production scheme persistence.
Application service creates this, calls commit/rollback, and exits.
Repository never commits.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session


class SqlAlchemyProductionSchemeUnitOfWork:
    """Concrete UoW using SQLAlchemy sessions.

    The application layer creates this via a factory, enters the context,
    performs operations, commits on success, and exits (which closes the
    session).  On exception the context manager rolls back automatically.
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyProductionSchemeUnitOfWork:
        self._session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        if self._session is not None:
            if exc is not None:
                self._session.rollback()
            self._session.close()

    @property
    def session(self) -> Session:
        assert self._session is not None, "UoW not entered"
        return self._session

    def commit(self) -> None:
        assert self._session is not None, "UoW not entered"
        self._session.commit()

    def rollback(self) -> None:
        assert self._session is not None, "UoW not entered"
        self._session.rollback()
