# ADR-010 Project Versioning and Immutability

- Status: Accepted
- Date: 2026-06-20

## Context

The Cold Storage Planning Agent needs a stable, auditable way to manage project inputs, calculation results, and reports. Projects evolve through multiple planning iterations, and stakeholders must be able to trace which inputs produced which results. Approved versions must be immutable to ensure regulatory compliance and audit trails.

## Decision

### Domain Model Boundary

**Project** represents the long-term identity of a cold storage planning project. It holds stable metadata (name, code, location, product category) and references the current active version.

**ProjectVersion** represents a complete planning snapshot at a point in time. Each version contains:
- Input parameters (daily throughput, storage days, etc.)
- Calculation results (zone planning, investment estimation)
- Assumptions and coefficients used
- Status within the version lifecycle

The boundary is clear: Project is identity; ProjectVersion is state.

### Version State Machine

```
draft → generated → under_review → reviewed → approved → archived
draft → under_review ↺ (can return to draft from under_review or reviewed)
```

**Valid transitions:**
- draft → generated
- draft → under_review
- generated → under_review
- under_review → reviewed
- under_review → draft (with reason)
- reviewed → approved
- reviewed → draft (with reason)
- approved → archived

**Invalid transitions raise `InvalidVersionTransitionError`.**

### Immutability Rules

1. **Approved versions cannot be modified.** Input snapshots, calculation snapshots, and assumption snapshots are frozen.
2. **Archived versions cannot be modified.** All fields are read-only.
3. **To modify an approved version, create a new draft.** Use `create_version_from` to copy the approved version's data into a new draft.
4. **Return to draft requires a reason.** The reason is recorded in the audit event.
5. **Version numbers are unique per project.** Enforced by database unique constraint.

### Snapshot Strategy

Each version stores three snapshots as JSON:

```json
{
  "schema_version": "1.0",
  "captured_at": "2026-06-20T12:00:00Z",
  "data": { ... }
}
```

- `input_snapshot`: Design parameters (throughput, storage days, etc.)
- `calculation_snapshot`: Results from zone planning, investment estimation
- `assumption_snapshot`: Coefficients and assumptions used

Snapshots are serializable dictionaries. They never contain ORM objects.

### Current Version

`Project.current_version_number` tracks the active version. It can be updated via `set_current_version`. The current version is the default context for API operations.

### Concurrency Control

- Database unique constraint on (project_id, version_number)
- Application service checks version state before transitions
- Optimistic locking via state validation (not version column)

### Deletion Policy

- **ProjectVersion deletion is not allowed.** Versions are immutable records.
- **Draft versions may be deleted** if they have no dependent calculations. This is an explicit operation with audit logging.
- **Project deletion is not allowed** in V1. Soft-delete via status field if needed later.

### Audit Events

Every state transition emits an audit event:
- `project_created`
- `version_created`
- `inputs_updated`
- `submitted_for_review`
- `returned_to_draft`
- `review_completed`
- `version_approved`
- `version_archived`
- `current_version_changed`

## Consequences

### Positive
- Clear separation between identity (Project) and state (ProjectVersion)
- Full audit trail for regulatory compliance
- Immutable approved versions prevent accidental data corruption
- Version lineage via parent_version_id enables change tracking
- Snapshots preserve exact inputs/results for reproducibility

### Negative
- More complex state management (state machine logic)
- Additional database columns and migration complexity
- Need to handle concurrent version creation carefully

### Risks
- Performance impact of JSON snapshots for large calculation results
- Migration complexity for existing data (handled via Alembic)

## Alternatives Considered

1. **Single version with history table:** Simpler but loses snapshot isolation
2. **Event sourcing:** More flexible but over-engineered for V1
3. **File-based versioning:** Loses database query capabilities

## References

- ADR-007: Module Dependency Rules
- ADR-008: Runtime Database Modes
- ADR-009: Application Lifecycle and Dependency Injection
