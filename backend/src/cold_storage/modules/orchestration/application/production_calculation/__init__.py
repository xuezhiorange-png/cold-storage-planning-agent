"""Task 11B Phase 2 — production calculation ports & adapters.

This subpackage delivers the **application port contracts**, the
**adapter boundary wrappers** around existing production calculators,
and the **pure mapping helpers** that translate adapter output into
the future ``CalculationRunRecord`` draft.

It does NOT implement the full orchestrator.  The orchestrator (Phase 3+)
will compose the ports defined here.  No production row is written by
this subpackage — that is reserved for a separately-authorised task.

The Frozen Contract Authority SHA for this phase is
``ba4288ea1c6f258c8b0b9f487d071c8ffce0e4b2``.

Forbidden in this subpackage
----------------------------
* Imports from ``cold_storage.evaluation.*`` (no evaluation backdoor).
* Raw ORM inserts into ``calculation_runs`` / ``orchestration_run_attempts``
  / ``scheme_runs`` / ``source_archives`` / ``source_bindings``.
* Calls into ``SchemeService.run`` or any equivalent SchemeRun entrypoint.
* Modifications to calculator formula / threshold / weight / review rules.
* Suppression of ``requires_review=True`` outputs.
"""
