# Alertable Failure Classes

## 10 Stable Failure Classes

| # | Class | Description |
|---|---|---|
| 1 | DATABASE_UNREACHABLE | Database connection failed |
| 2 | MIGRATION_HEAD_INVALID | Alembic migration head mismatch |
| 3 | REDIS_UNREACHABLE | Redis connection failed |
| 4 | ARTIFACT_STORAGE_AUTH_FAILED | Artifact storage authentication failed |
| 5 | OUTBOX_RETRY_EXHAUSTED | Outbox delivery retry limit reached |
| 6 | OUTBOX_POISON_MESSAGE | Outbox message cannot be delivered |
| 7 | READINESS_CHECK_TIMEOUT | Readiness probe timed out |
| 8 | STARTUP_LIVENESS_STALL | Startup liveness check stalled |
| 9 | STRICT_ENVIRONMENT_VIOLATION | Strict environment validation failed |
| 10 | SECRET_PRESENT_IN_REDACTED_OUTPUT | Secret leaked through redaction |

## Usage in Metrics

These classes are used as the `class` label in:
- `outbox_delivery_failures_total{queue, class}`
- `configuration_validation_failures_total{class}`

## Constraints

- No dynamic failure class labels permitted
- Enumeration is frozen at contract time
- Adding new classes requires a new governance round
