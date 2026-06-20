# ADR-008 Runtime Database Modes

- Status: Accepted
- Context: The project needs to support both lightweight SQLite development and PostgreSQL production integration.
- Decision:
  - SQLite is the default for local development and unit tests (`APP_ENV=development`, `DATABASE_BACKEND=sqlite`)
  - PostgreSQL is used for integration testing and production deployment
  - No silent fallback from PostgreSQL to SQLite — explicit error on connection failure
  - Both database paths must be maintained until explicit migration completion
  - `alembic.ini` no longer hardcodes a database URL; `env.py` reads from `Settings`
- Alternatives: Single database backend for all environments.
- Consequences: Both paths need CI coverage. PostgreSQL integration tests require Docker.
