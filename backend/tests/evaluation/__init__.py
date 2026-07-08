"""A1 evaluation tests package (Task 11B Path A — Implementation Slice A1).

The test package deliberately re-uses the A1 adapter's public surface
only:

* :mod:`tests.evaluation.test_path_a_adapter` — the A1 acceptance
  test suite. Enforces the A1-2a input contract and the ownership
  boundary invariants. Database-backed happy-path tests are
  deferred to a follow-up slice (see the "Note on
  database-backed happy-path tests" comment near the top of the
  test module) pending an architecture-test carve-out decision.

The empty package marker is required for pytest collection.
"""

from __future__ import annotations

__all__: list[str] = []
