# Rollback Guide

## Observability Rollback

### What CAN be rolled back

1. **Middleware removal**: Remove correlation_id and structured_logging middleware from app.py
2. **Metrics endpoint removal**: Remove GET /metrics route from app.py
3. **Dependency removal**: Remove prometheus-client from pyproject.toml

### What CANNOT be rolled back without impact

1. **Slice 1/2 functionality**: Observability does NOT depend on Slice 1/2 code
2. **Health endpoints**: /health/live and /health/ready are unchanged
3. **Business routes**: All business routes are unchanged

### Rollback Steps

1. Remove middleware imports from app.py
2. Remove middleware registration from app.py
3. Remove metrics endpoint from app.py
4. Remove prometheus-client from pyproject.toml
5. Run `uv sync` to update lockfile
6. Verify health endpoints still work

### Rollback Constraints

- Must NOT delete existing Slice 1/2 features
- Must NOT modify production_entrypoint.py
- Must NOT modify health endpoint semantics
- Must NOT modify database schema
