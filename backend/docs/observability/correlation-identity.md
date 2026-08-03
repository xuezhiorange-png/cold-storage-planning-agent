# Correlation Identity

## Overview

Every request receives a unique correlation ID that propagates through
all log entries, metric labels (indirectly via capability_tags), and
audit trails.

## Propagation

1. Client sends `X-Request-ID` header (UUIDv4)
2. Middleware validates and reuses valid UUIDv4
3. Missing or invalid header generates new lowercase UUIDv4
4. `correlation_id` and `request_id` ContextVars set to same value
5. Response includes `X-Request-ID` header with final value
6. ContextVars reset after request completes

## Context Propagation

- Supports `asyncio.create_task()` propagation
- Sync and async handlers both work
- ContextVars are request-scoped, not persisted

## Constraints

- Correlation ID is never persisted to database
- Raw header values are never used as metric labels
- Maximum length: 36 characters (UUIDv4 format)
