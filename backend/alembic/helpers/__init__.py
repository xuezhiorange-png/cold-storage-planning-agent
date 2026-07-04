"""Helpers used by Alembic migrations.

This package is intentionally isolated from the application runtime code
so that historical migrations do not silently change behavior when the
production code evolves.  Each helper is version-suffixed (e.g. ``_v1``)
and must remain byte-identical across the lifetime of any migration
that imports it.

See ``frozen_outbox_envelope_v1`` for the canonical envelope hashing
algorithm used by migration 0033.
"""