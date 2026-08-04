# Metrics Catalog

## Metric Families

| # | Metric | Type | Labels | Description |
|---|---|---|---|---|
| 1 | process_uptime_seconds | Gauge | (none) | Process uptime |
| 2 | http_requests_total | Counter | method, path, status | HTTP request count |
| 3 | http_request_duration_seconds | Histogram | method, path, status | HTTP request duration |
| 4 | dependency_up | Gauge | dependency | Dependency health |
| 5 | outbox_backlog_total | Gauge | queue | Outbox backlog |
| 6 | outbox_lag_seconds | Gauge | queue | Outbox lag |
| 7 | outbox_delivery_attempts_total | Counter | queue, attempt | Delivery attempts |
| 8 | outbox_delivery_failures_total | Counter | queue, class | Delivery failures |
| 9 | outbox_poison_messages_total | Counter | queue | Poison messages |
| 10 | outbox_retry_exhaustion_total | Counter | queue | Retry exhaustion |
| 11 | configuration_validation_failures_total | Counter | class | Config failures |
| 12 | REDACTION_BYPASS_DETECTED | Counter | secret_type, emit_point | Redaction bypass |
| 13 | HIGH_CARDINALITY_LABEL_REJECTED | Counter | metric_name | Cardinality rejection |
| 14 | audit_chain_integrity_status | Gauge | (none) | Audit chain status |
| 15 | audit_log_write_seconds | Histogram | (none) | Audit write duration |
| 16 | agent_capability_status | Gauge | capability | Agent capability |

## Cardinality Bounds

| Label Domain | Cap |
|---|---|
| HTTP route templates | 10 |
| Dependencies | 8 |
| Outbox queues | 8 |
| HTTP methods | 5 (GET, POST, PUT, PATCH, DELETE) |
| HTTP statuses | 13 (200, 201, 204, 301, 302, 400, 401, 403, 404, 409, 422, 500, 503) |

## HTTP Logical Labelset Bounds

- Low (10 routes): 2 × 5 × 10 × 13 = 1,300
- High (20 routes): 2 × 5 × 20 × 13 = 2,600

## Histogram Buckets

`.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10` (seconds)

## Enforcement

Unregistered method, path, status, dependency, queue, failure class,
secret type, emit point, or capability values are REJECTED.
HIGH_CARDINALITY_LABEL_REJECTED is incremented with the metric name.
Raw values are never written to metric labels.
