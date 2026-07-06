# Task 11B Phase 3 — SourceBinding + archive + SchemeService E2E

Status: **implementation in progress — Issue #35 still OPEN**

> **Phase 3 scope: SourceBinding + archive + SchemeService E2E only.**
> This phase does NOT authorize:
> - Closing Issue #35
> - approved non-demo coefficient governance
> - Task 11 Phase B / C / D
> - Task 12
> - Modifying PR #21 (still Draft / Open / Not merged / BLOCKED)

## 1. Goal

Phase 1 (PR #37) shipped the production schema and identity foundation.
Phase 2 (PR #38) shipped the production calculation ports & adapters.
Phase 3 closes the production loop: 5 calculator stages → 5
``CalculationRunRecord`` rows + 1 ``SourceBindingRecord`` row, consumed
by the production ``SchemeService`` end-to-end, with a verified
``SourceArchive`` payload.

Phase 3 proves the production path is wired through Phase 2's adapter
ports — not through golden fixtures, not through evaluation-owned
seeding, not through latest-row fallback.

## 2. Phase 3 deliverable list

### 2.1 Production code

1. ``Phase2AdapterCalculatorPort`` — concrete ``CalculatorPort`` Protocol
   implementation that drives Transaction B by routing each of the five
   stages through the corresponding Phase 2 adapter
   (``ZonePlanningAdapter`` → ``CoolingLoadAdapter`` →
   ``EquipmentCapabilityAdapter`` → ``InstalledPowerAdapter`` →
   ``InvestmentAdapter``).  Each stage consumes the upstream
   ``StagePersistedResult`` list and projects it into the
   ``CalculatorInputProjection`` for the next stage.
2. ``ProductionSourceBindingUseCase`` — application-level use case
   that:
   * loads the approved project version via
     ``ApprovedProjectVersionReadPort``;
   * builds a fresh orchestration attempt;
   * runs Transaction B end-to-end through
     ``OrchestrationService`` (which uses
     ``Phase2AdapterCalculatorPort``);
   * returns the verified ``SourceBindingRecord.id`` for downstream
     ``SchemeService`` consumption.
3. Minimum wiring touch in
   ``backend/src/cold_storage/bootstrap/production_composition.py``
   so the new port is available to the application service
   composition.  No new SQL, no schema changes.

### 2.2 Tests

* SQLite E2E:
  ``test_production_sourcebinding_e2e_sqlite.py`` — the use case runs
  end-to-end, produces exactly 5 ``CalculationRunRecord`` + 1
  ``SourceBindingRecord`` + 1 ``SchemeRunRecord`` + 1
  ``SourceArchiveRecord``; passes the existing
  ``SourceBindingVerifier`` re-verification.
* PostgreSQL E2E:
  ``test_production_sourcebinding_e2e_postgresql.py`` — same path on
  PG, with the same assertions.
* Fail-closed tests:
  * missing slot → ``SourceBindingVerificationError``
  * tampered ``combined_source_hash`` → fail closed
  * wrong project_id on binding → fail closed
  * wrong calculation_type on a slot → fail closed
  * attempt-status = PENDING (not COMPLETED) → fail closed
  * requires_review suppression attempt → fail closed
  * raw ORM fabrication of a ``CalculationRunRecord`` outside the
    transaction → fail closed
  * demo seed records entering the production path → fail closed
  * latest-row fallback attempt (manual binding pointing at the
    latest unverified row) → fail closed
* Rollback test: partial failure mid-pipeline leaves zero
  ``SourceBindingRecord`` and zero ``SchemeRunRecord``.
* Power authority test: SchemeRun ``installed_power`` comes from the
  power slot, not from a compressor power field on the equipment slot.
* Archive verification test: ``SourceArchiveRecord.payload_hash``
  recomputes from the archived payload; tampered archive fails closed
  on readback.
* Architecture boundary test:
  ``test_phase3_evaluation_does_not_import_production.py`` — the
  evaluation module must not import any new
  ``orchestration.application.source_binding_*`` /
  ``orchestration.application.production_source_binding`` /
  ``schemes.application.production_service`` symbols.

## 3. Non-deliverables (NOT in Phase 3)

* No changes to ``orchestration.infrastructure.orm`` schema.
* No new Alembic migrations.
* No changes to production calculator formulas, thresholds, weights,
  review rules.
* No new production coefficients or coefficient governance
  (Phase 3 uses the same demo coefficients Phase 2 used).
* No changes to evaluation manifest, expected outputs, or fixtures.
* No changes to PR #21.
* No Task 11 Phase B resumption test (that is the next phase, after
  Issue #35 acceptance criteria is fully satisfied).
* No Task 11 Phase C / D / E.
* No Task 12.

## 4. Stop conditions (per Charles's mandate)

Phase 3 implementation will halt and report if any of the following
is true:

* main HEAD does not match the expected baseline
  ``66593685a7950a1ccb881f265d3a8f60514aea51``.
* Issue #35 is closed or in a non-OPEN state.
* PR #21 is not Draft / Open / Not merged / BLOCKED.
* The PostgreSQL E2E test cannot run without skipping the
  production-critical assertions.
* Phase 3 requires modifying evaluation fixtures, expected outputs,
  or the evaluation manifest.
* Phase 3 requires changing production formulas, thresholds, weights,
  or review rules to make a test pass.
* ``SourceBinding`` cannot be assembled without a latest-row fallback.
* ``SchemeService`` cannot run without a demo record fallback.
* Any production calculator's ``requires_review`` is suppressed.

## 5. References

* PR #40 (Phase 2 closeout + governance deviation record):
  ``docs/tasks/TASK-011B-phase2-closeout.md``
* Phase 1 / Phase 2 design contract:
  ``docs/tasks/TASK-011B-production-calculation-orchestration-prerequisite.md``
* Phase 2 ports & adapters:
  ``backend/src/cold_storage/modules/orchestration/application/production_calculation/``
* Phase 1 schema / identity foundation:
  ``backend/src/cold_storage/modules/orchestration/infrastructure/orm.py``
* Production ``SchemeService`` (Phase 3 consumer):
  ``backend/src/cold_storage/modules/schemes/application/production_service.py``
* Source archive builder (Phase 3 path):
  ``backend/src/cold_storage/modules/orchestration/application/source_archive_builder.py``

## 6. Explicit non-authorization statement

This document does NOT authorize any of the following:

* Closing Issue #35.
* Modifying PR #21.
* Merging PR #21.
* Implementing approved non-demo coefficient governance.
* Starting Task 11 Phase B / C / D.
* Starting Task 12.
* Modifying production formulas, thresholds, weights, or review rules.
* Modifying evaluation manifest, expected outputs, or fixtures.
* Using latest-row fallback in any production path.
* Suppressing ``requires_review`` in any production path.
* Raw ORM fabrication of ``CalculationRunRecord`` outside the
  Transaction B boundary.

Any of the above requires a separate design, contract freeze, and
explicit authorization round.
