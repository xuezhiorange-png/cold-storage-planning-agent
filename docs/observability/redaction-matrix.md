# Redaction Matrix

## Secret Types

| # | Secret Type | Pattern Examples |
|---|---|---|
| 1 | DATABASE_URL | `postgresql://user:pass@host/db` |
| 2 | REDIS_URL | `redis://:pass@host:6379` |
| 3 | OTHER_DSN | Any DSN with userinfo |
| 4 | PASSWORD | `password=secret` |
| 5 | TOKEN | `token=abc123` |
| 6 | API_KEY | `api_key=sk-...` |
| 7 | COOKIE | `Cookie: session=...` |
| 8 | AUTHORIZATION_HEADER | `Authorization: Bearer ...` |
| 9 | SECRET_ENVIRONMENT_VARIABLE | Any SECRET_* env var |
| 10 | SIGNED_URL | URLs with signature params |
| 11 | CREDENTIAL_BEARING_EXCEPTION | Exception messages with credentials |

## Emit Points

| Emit Point | Description |
|---|---|
| LOG | Structured log output |
| METRIC_LABEL | Prometheus metric label value |
| ERROR_RESPONSE | HTTP error response body |
| AUDIT_PAYLOAD | Audit event payload |
| EVIDENCE | Audit evidence artifact |

## Redaction Rules

1. All 11 secret types are covered by `redact_for_logging()`
2. Redaction failure is fail-closed: returns `***REDACTION_FAILED***`
3. Original sensitive values never enter logs, metric labels, error responses, audit payloads, or evidence
4. `REDACTION_BYPASS_DETECTED` uses only limited label enums (secret_type × emit_point)
5. No raw sensitive values in metric labels
