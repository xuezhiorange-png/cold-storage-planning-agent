"""Evaluation runner package (Task 11B Phase B Path A — Implementation Slice A1).

Path A adapter surface (A1-2a, ratified by Amendment 2 of
``docs/tasks/TASK-011B-path-a-design-ratification.md`` §13).

Public API re-exports:

* :func:`execute_scenario` — single-call entry point that wraps the
  production ``ProductionSchemeService.generate_production_scheme_run``
  call. Takes only FK references to pre-existing production rows
  plus the two mandatory Phase-1 input fields (a correlation marker
  and a database-backend marker — see the adapter module for the
  exact field names).

* :class:`AdapterResult` — read-only result dataclass.

* :class:`AdapterInputError` — raised when the input contract is
  violated.

See :mod:`cold_storage.evaluation.adapter` for the implementation and
the ownership boundary discussion.
"""

from __future__ import annotations

from cold_storage.evaluation.adapter import (
    AdapterInputError,
    AdapterResult,
    execute_scenario,
)

__all__ = [
    "AdapterInputError",
    "AdapterResult",
    "execute_scenario",
]
