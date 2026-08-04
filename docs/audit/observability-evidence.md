# Observability Evidence — TASK-012 Slice 4

## Execution Metadata

| Field | Value |
|---|---|
| ROUND | OBSERVABILITY_FINAL_TWO_FIXES |
| REPOSITORY | xuezhiorange-png/cold-storage-planning-agent |
| BRANCH | feat/task-012-observability |
| PR_NUMBER | 79 |
| PREVIOUS_HEAD | 7f701f0def9a6932fde05226a0a7e9d9551529e2 |
| FINAL_PR_HEAD | SEE_PR_EXACT_HEAD |
| FINAL_CI_RUN | SEE_PR_EXACT_HEAD_CHECKS |

## Fixes Applied

| Issue | Fix |
|---|---|
| F015: /metrics self-recording | Moved path=="/metrics" check to the very beginning of metrics recording logic, before any route template query or rejection counter. Both request_completed and request_failed paths excluded. |
| F015: Unresolved route rejection | Changed `elif route_template is not None:` to `else:` so unregistered/unresolved routes also increment HIGH_CARDINALITY_LABEL_REJECTED. |
| F016: Mapping key redaction | Added safe_key = _redact_log_value(k) for every Mapping key, with fail-closed fallback to REDACTION_FAILED. |

## Pre-Implementation Failing Tests

| Test Name | Failure Reason |
|---|---|
| test_metrics_endpoint_neither_records_nor_rejects_when_unregistered | /metrics registered as route, rejection counter incremented |
| test_unresolved_route_rejects_with_counter | No rejection counter for unresolved routes |
| test_mapping_key_with_secret_redacted | Mapping keys not redacted |
| test_mapping_key_with_token_redacted | Mapping keys not redacted |
| test_mapping_key_object_str_raises_fail_closed | No fail-closed for broken Mapping keys |

## Post-Implementation Gate Results

| Gate | Result |
|---|---|
| RUFF_FORMAT | PASS |
| RUFF_LINT | PASS |
| MYPY | PASS (268 files) |
| ALL_TESTS | PASS (70/70, 15.27s) |
| F015_METRICS_SELF_RECORDING | PASS (test_metrics_endpoint_neither_records_nor_rejects_when_unregistered) |
| F015_UNRESOLVED_ROUTE_REJECTION | PASS (test_unresolved_route_rejects_with_counter) |
| F016_MAPPING_KEY_SECRET | PASS (test_mapping_key_with_secret_redacted) |
| F016_MAPPING_KEY_TOKEN | PASS (test_mapping_key_with_token_redacted) |
| F016_MAPPING_KEY_FAIL_CLOSED | PASS (test_mapping_key_object_str_raises_fail_closed) |

## CI Status

CI status is tracked via PR exact HEAD checks. See PR #79 for current CI run.
