"""Per-scenario temporary SQLite database lifecycle.

Each scenario gets its own isolated SQLite database to avoid cross-contamination.
The database is created in a temporary directory, populated via
``Base.metadata.create_all``, and disposed+deleted on exit via ``finally``.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.projects.infrastructure.orm import Base


class SqliteScope:
    """Context manager for a per-scenario temporary SQLite database.

    Usage::

        with SqliteScope() as scope:
            engine = scope.engine
            session_factory = scope.Session
            # … run scenario …
            scope.track_paths_for_cleanup(db_path)  # if created externally

    On exit the SQLite file is always deleted.
    """

    def __init__(self) -> None:
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self._db_path: Path | None = None
        self.engine: Any = None
        self.Session: Any = None
        self.db_url: str = ""

    def __enter__(self) -> SqliteScope:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="eval_sqlite_")
        self._db_path = Path(self._tmpdir.name) / "scenario.db"
        self.db_url = f"sqlite:///{self._db_path}"
        self.engine = create_engine(
            self.db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        return self

    def __exit__(self, *exc_args: Any) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        """Dispose engine and delete the SQLite file."""
        if self.engine is not None:
            with contextlib.suppress(Exception):
                self.engine.dispose()
            self.engine = None
        if self._tmpdir is not None:
            with contextlib.suppress(OSError):
                self._tmpdir.cleanup()
            self._tmpdir = None
        self._db_path = None

    @property
    def db_path(self) -> Path | None:
        return self._db_path

    @property
    def tmpdir(self) -> str | None:
        return self._tmpdir.name if self._tmpdir else None


def assert_temp_db_cleaned(scope: SqliteScope) -> None:
    """Verify that the temporary database file no longer exists."""
    if scope.db_path is not None and scope.db_path.exists():
        raise AssertionError(f"Temp database still exists: {scope.db_path}")
    if scope.tmpdir is not None and os.path.isdir(scope.tmpdir):
        raise AssertionError(f"Temp directory still exists: {scope.tmpdir}")
