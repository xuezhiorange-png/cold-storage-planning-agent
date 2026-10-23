"""Shared baseline search for the P1-S3 and P1-S4 contract tests.

Register this module through pytest_plugins so both test modules use one
session FixtureDef/cache. Importing the fixture into each module would create
separate fixture definitions and repeat the expensive search.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from cold_storage.modules.layout.application.composition_placement import (
    enumerate_composition_placements,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context


@contextmanager
def _reject_database_access() -> Iterator[None]:
    """Reject new SQLAlchemy connections and SQL on already pooled connections."""

    def reject_database_access(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("COMPOSITION_TEST_DATABASE_ACCESS_FORBIDDEN")

    events = ("do_connect", "connect", "before_cursor_execute")
    for name in events:
        event.listen(Engine, name, reject_database_access)
    try:
        with ExitStack() as stack:
            for target in ("sqlite3.connect", "sqlite3.dbapi2.connect", "psycopg2.connect"):
                stack.enter_context(patch(target, side_effect=reject_database_access))
            yield
    finally:
        for name in events:
            event.remove(Engine, name, reject_database_access)


@pytest.fixture(scope="module")
def composition_no_database() -> Iterator[None]:
    """Opt in from composition modules only; remove listeners at module teardown."""
    with _reject_database_access():
        yield


@pytest.fixture(scope="session")
def xinzhao_placement() -> tuple[Any, Any, Any, Any]:
    """Share only baseline generation; determinism and validation replay anew."""
    # Session fixtures precede module guards, so protect baseline setup explicitly.
    with _reject_database_access():
        zone_plan, p1_handoff, site_geometry = _context()
        result = enumerate_composition_placements(zone_plan, p1_handoff, site_geometry)
    return zone_plan, p1_handoff, site_geometry, result
