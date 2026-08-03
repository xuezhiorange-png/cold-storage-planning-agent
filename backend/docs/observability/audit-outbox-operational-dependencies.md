# Audit & Outbox Operational Dependencies

## Outbox Metrics

| Metric | Labels | Threshold |
|---|---|---|
| outbox_backlog_total | queue | — |
| outbox_lag_seconds | queue | Alert at 300s |
| outbox_delivery_attempts_total | queue, attempt | — |
| outbox_delivery_failures_total | queue, class | — |
| outbox_poison_messages_total | queue | Alert at 0 (any) |
| outbox_retry_exhaustion_total | queue | Alert at 0 (any) |

## Audit Metrics

| Metric | Labels | Description |
|---|---|---|
| audit_chain_integrity_status | (none) | 1=valid, 0=invalid |
| audit_log_write_seconds | (none) | Write duration histogram |

## Constraints

- Outbox domain is NOT modified by observability
- Audit domain is NOT modified by observability
- No delivery guarantee changes
- No business event semantics changes
- No fake outbox queues
- Queue and capability must be explicitly registered
