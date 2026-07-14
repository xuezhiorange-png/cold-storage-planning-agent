"""TASK-011C C-2 backend runners (TASK-011C C-2 runner authority).

This subpackage provides the C-2 backend composition for the
suite runner (:mod:`cold_storage.evaluation.evaluate`). Each
backend runner is a thin wrapper that:

* wires a SQLAlchemy session factory for the target backend
  (SQLite or PostgreSQL);
* identifies the backend identity (the canonical
  ``DatabaseBackend`` enum value);
* invokes :func:`evaluate_manifest` from the suite runner;
* cleans up any runner-owned backend resources on exit.

Backend runners MUST NOT duplicate the suite runner's
comparison / canonicalization / D10 / artifact logic. They
exist solely to wire the per-backend session lifecycle to
the single suite runner authority.

Public API:

* :mod:`.sqlite` — :func:`run_sqlite_suite`
* :mod:`.postgresql` — :func:`run_postgresql_suite`
* :mod:`._executor` — the per-scenario execution seam that
  the suite runner delegates to (overridable by tests / by
  the backend runners).
"""

from __future__ import annotations

__all__: list[str] = []
