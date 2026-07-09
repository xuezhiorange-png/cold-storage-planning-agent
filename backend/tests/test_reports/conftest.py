"""Test-local synchronization helpers for report tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa

from cold_storage.modules.reports.domain.enums import ReportLocale
from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository

_FASTAPI_WAITER_CONVERGENCE_NODEID = (
    "tests/test_reports/test_waiter_concurrent.py::"
    "TestDefaultWaiterFastAPIConvergence::"
    "test_default_waiter_two_fastapi_requests_converge"
)


@pytest.fixture(autouse=True)
def _stabilize_fastapi_waiter_sqlite_visibility(
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    """Ensure seeded SQLite data is visible before the concurrent FastAPI test.

    The FastAPI waiter convergence test intentionally starts two request threads that
    each build a fresh SQLAlchemy session/SQLite connection.  On GitHub Actions the
    test can otherwise enter the barrier before a fresh reader connection reliably
    observes the report/revision/templates seeded by the fixture setup connection.
    That turns a legitimate idempotency convergence assertion into a pre-existing
    SQLite WAL visibility race where one request returns 404.

    Keep this barrier scoped to the one concurrent FastAPI node.  It does not skip
    or weaken the test; it only proves that a fresh request-side SQLite connection
    can already see the required setup rows before the two request threads race the
    idempotency path under test.
    """
    if request.node.nodeid != _FASTAPI_WAITER_CONVERGENCE_NODEID:
        yield
        return

    session_factory = request.getfixturevalue("session_factory")
    _client, report, revision = request.getfixturevalue("test_client")

    with session_factory() as session:
        repo = SQLReportRepository(session)

        assert repo.get_report(report.id) is not None
        assert repo.get_revision(report.id, revision.revision_number) is not None
        assert repo.list_templates(format="docx", locale=ReportLocale.ZH_CN)

        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            session.execute(sa.text("PRAGMA wal_checkpoint(FULL)")).all()

    yield
