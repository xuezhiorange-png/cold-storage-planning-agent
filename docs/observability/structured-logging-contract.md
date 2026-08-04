# Structured Logging Contract

## Overview

All application logs are emitted as JSON Lines (one JSON object per line).

## Log Line Schema

```json
{
  "timestamp": "2025-01-15T10:30:00.000Z",
  "level": "INFO",
  "name": "cold_storage.bootstrap.app",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "capability_tags": ["http", "request"],
  "message": "Request completed",
  "extra_field": "value"
}
```

## Required Fields

| Field | Type | Description |
|---|---|---|
| timestamp | string | RFC 3339 UTC timestamp |
| level | string | Python logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| name | string | Logger name |
| correlation_id | string | UUIDv4 correlation ID |
| request_id | string | UUIDv4 request ID |
| capability_tags | list[str] | Capability tags for this log entry |
| message | string | Log message |

## Redaction

All log messages and extra fields are redacted before emission using the
configuration redaction authority. The following secret types are covered:

1. DATABASE_URL
2. REDIS_URL
3. OTHER_DSN
4. PASSWORD
5. TOKEN
6. API_KEY
7. COOKIE
8. AUTHORIZATION_HEADER
9. SECRET_ENVIRONMENT_VARIABLE
10. SIGNED_URL
11. CREDENTIAL_BEARING_EXCEPTION

Redaction failure is fail-closed: `***REDACTION_FAILED***` is returned.

## Retention

| Environment | Retention |
|---|---|
| Local | 30 days |
| CI | 90 days |
| Staging | 90 days |
| Production | 365 days |

## Handler Configuration

- `configure_logging()` installs exactly one JSON handler
- Multiple calls do not duplicate handlers
- Thread-safe via logging module internals
