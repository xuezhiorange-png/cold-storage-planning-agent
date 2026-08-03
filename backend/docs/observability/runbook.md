# Observability Runbook

## Metric Anomalies

### HIGH_CARDINALITY_LABEL_REJECTED

**Symptom**: `HIGH_CARDINALITY_LABEL_REJECTED` counter increasing
**Cause**: Unregistered route template, dependency, or queue value
**Action**: Register the value in the metrics registry before use

### REDACTION_BYPASS_DETECTED

**Symptom**: `REDACTION_BYPASS_DETECTED` counter increasing
**Cause**: Secret detected in log output after redaction attempt
**Action**: Investigate redaction failure; check emit_point and secret_type labels

### Outbox Lag > 300s

**Symptom**: `outbox_lag_seconds` exceeds 300s threshold
**Cause**: Outbox dispatcher stalled or database slow
**Action**: Check outbox dispatcher logs; verify database connectivity

### Outbox Poison Message

**Symptom**: `outbox_poison_messages_total` incrementing
**Cause**: Message cannot be delivered after max retries
**Action**: Inspect message payload; fix or discard poison message

### Outbox Retry Exhaustion

**Symptom**: `outbox_retry_exhaustion_total` incrementing
**Cause**: Delivery retries exhausted
**Action**: Check downstream service health; review retry configuration

### Dependency Down

**Symptom**: `dependency_up` = 0
**Cause**: Health probe timeout or failure
**Action**: Check dependency health endpoint; verify network connectivity

## Redaction Failure

**Symptom**: Log contains `***REDACTION_FAILED***`
**Cause**: Redaction function raised an exception
**Action**: Report as security incident; review redaction code

## Health Endpoint Issues

### /health/live returns non-200

**Cause**: Process or event loop issue
**Action**: Check process status; restart if needed

### /health/ready returns 503

**Cause**: Readiness probe failure
**Action**: Check individual probe outcomes in response body
