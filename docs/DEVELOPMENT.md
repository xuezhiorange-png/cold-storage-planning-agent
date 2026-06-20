# Development

## Local Setup

Use `uv` for backend Python 3.12 environments. The system Python on this workstation may be older than 3.12.

```bash
make install
make up
make migrate
make seed
make demo
```

## Quality Gates

Run before claiming a milestone complete:

```bash
make test
make lint
make typecheck
make architecture-test
```

## Module Boundaries

- API routes translate HTTP to application service calls.
- Application services coordinate domain objects and ports.
- Domain code owns business rules and must stay framework-free.
- Infrastructure code implements persistence, document parsing, model gateways, and file generation.

## Persistence

Project, version, input snapshot, calculation run, coefficient, and audit schemas are managed through Alembic. Run `make migrate` before starting the API locally.
