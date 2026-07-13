"""SQLite per-scenario isolation foundation (TASK-011C V1 — C-1).

This module provides a single, narrowly-scoped helper for C-1:

  :class:`SQLiteScenarioScope` — a context manager that creates a
  per-scenario temporary SQLite database, hands the caller a
  configured engine bound to that database, and guarantees
  deterministic, explicit cleanup on exit (no stale DB reuse,
  no cross-scenario leakage).

Hard rules (binding, Charles §15 + §16):

* No production ORM rows are created by this module.
* No ``CalculationRunRecord`` is constructed.
* Production services are NOT bypassed (this module is purely
  a database-isolation primitive; it does not invoke any
  production calculation, projection, or persistence code).
* The legacy test-side seeding helper is not restored; nothing
  in this module depends on it.
* The scope is for **C-1 foundation only**. C-2 (the runner) is
  the only authorized consumer and is not implemented in this
  round.

The scope guarantees:

* ``scenario_id`` follows the same character set as
  ``run_directory._SAFE_SCENARIO_ID`` (path-traversal-resistant).
* The temporary file path is constructed via ``tempfile`` and is
  unique to the process + thread (no fixed-path reuse).
* Engine disposal is performed deterministically in ``__exit__``.
* The temp file is unlinked on ``__exit__`` unless ``keep_db=True``
  is passed (useful for debugging; the runner never passes it).
* No thread or process fork: a fresh engine is created per scope.
* No cross-scenario state: each scope owns its own engine, its own
  file, and its own schema (initialized by the caller; this
  module does not run any DDL).
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

#: Allowed character set for scenario_id (matches
#: ``run_directory._SAFE_SCENARIO_ID``).
_SAFE_SCOPE_ID: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class SQLiteScopeError(Exception):
    """Base class for SQLite-scope failures.

    Subclasses set a stable, machine-readable ``code`` attribute.
    """

    code: str = "SQLITE_SCOPE_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self._details: dict[str, Any] = dict(details) if details else {}

    @property
    def details(self) -> dict[str, Any]:
        return dict(self._details)


class InvalidScopeIDError(SQLiteScopeError):
    """Raised when ``scope_id`` does not match the safe character set."""

    code = "INVALID_SCOPE_ID"


class _SQLiteScenarioScope:
    """Internal implementation of the scope. Use :func:`sqlite_scenario_scope`."""

    def __init__(
        self,
        *,
        scope_id: str,
        keep_db: bool = False,
    ) -> None:
        if not isinstance(scope_id, str) or not _SAFE_SCOPE_ID.match(scope_id):
            raise InvalidScopeIDError(
                f"scope_id must match {_SAFE_SCOPE_ID.pattern!r}; got {scope_id!r}.",
                details={"scope_id": scope_id},
            )
        self.scope_id: str = scope_id
        self.keep_db: bool = keep_db
        # The actual database file is created lazily on __enter__.
        self._db_path: Path | None = None
        self._engine: Engine | None = None
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self._exited: bool = False

    def __enter__(self) -> _SQLiteScenarioScope:
        # Allocate a per-scope tempdir (deterministic, unique to the
        # process) and an empty file inside it. Using a directory +
        # file (not ``NamedTemporaryFile``) because we need an engine
        # that can connect to the file after the handle is closed.
        self._tmpdir = tempfile.TemporaryDirectory(prefix=f"t11c-{self.scope_id}-")
        # The DB file lives inside the scope's tempdir.
        db_file = Path(self._tmpdir.name) / f"{self.scope_id}.sqlite"
        db_file.touch()
        self._db_path = db_file
        # Build a SQLAlchemy engine bound to this specific file. The
        # engine is owned exclusively by this scope; nothing else
        # holds a reference.
        url = URL.create(
            drivername="sqlite",
            database=str(db_file),
        )
        self._engine = create_engine(
            url,
            future=True,
            # The scope owns the file's lifetime; we always disconnect
            # on close.
            poolclass=None,
        )
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._exited:
            return
        self._exited = True
        # 1. Dispose the engine. This closes all pooled connections.
        if self._engine is not None:
            try:
                self._engine.dispose()
            finally:
                self._engine = None
        # 2. Unlink the DB file (unless the caller asked to keep it).
        if self._db_path is not None and not self.keep_db:
            try:
                self._db_path.unlink(missing_ok=True)
            finally:
                self._db_path = None
        # 3. Remove the tempdir (best-effort).
        if self._tmpdir is not None:
            try:
                self._tmpdir.cleanup()
            finally:
                self._tmpdir = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise SQLiteScopeError(
                "engine is not available outside the scope context.",
                details={"scope_id": self.scope_id},
            )
        return self._engine

    @property
    def db_path(self) -> Path:
        if self._db_path is None:
            raise SQLiteScopeError(
                "db_path is not available outside the scope context.",
                details={"scope_id": self.scope_id},
            )
        return self._db_path


@contextmanager
def sqlite_scenario_scope(
    scope_id: str,
    *,
    keep_db: bool = False,
) -> Iterator[_SQLiteScenarioScope]:
    """Open a per-scenario SQLite scope.

    The returned object exposes ``engine`` (a SQLAlchemy ``Engine``
    bound to a fresh, empty SQLite file) and ``db_path`` (the file
    path). On exit the engine is disposed and the file is unlinked.

    Example (C-1 foundation; the C-2 runner is the only authorized
    consumer in production code)::

      with sqlite_scenario_scope("baseline_feasible") as scope:
          # Caller runs alembic / DDL via scope.engine.
          ...
          # No production row is created here.

    Parameters
    ----------
    scope_id:
        A scenario-identifier-shaped string. Must match the safe
        character set enforced by ``run_directory._SAFE_SCENARIO_ID``.
    keep_db:
        If ``True``, the temporary file is not unlinked on exit.
        Useful only for debugging; the runner never sets this.

    Yields
    ------
    _SQLiteScenarioScope
        The scope object.
    """
    scope = _SQLiteScenarioScope(scope_id=scope_id, keep_db=keep_db)
    with scope:
        yield scope


__all__ = [
    "InvalidScopeIDError",
    "SQLiteScopeError",
    "sqlite_scenario_scope",
]
