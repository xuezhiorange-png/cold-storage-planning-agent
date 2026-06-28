"""Orchestration module — formal calculation orchestration and persistence.

Scope:
- Immutable request/execution/source-snapshot DTOs (domain contracts).
- Five-stage calculator DAG definition.
- Execution-bound canonical hashing and source snapshot content/envelope contracts.
- ORM persistence skeleton for orchestration request, identity, attempt,
  calculation run, source binding, outbox, and related entities.
- Alembic migration extending existing CalculationRun, SchemeRun, and AuditEvent tables.

Implementation status:
- Phase 1 (this PR): domain contracts + persistence skeleton + constraints.
- Phase 2+: OrchestrationService, five-stage execution, SourceBinding assembly,
  SchemeService integration, outbox dispatcher.
- Task 11 Phase B remains BLOCKED.
"""
