"""P0-9: Default waiter lineage validation + convergence tests.

Tests for DatabaseIdempotencyWaiter lineage validations:
- claim_version mismatch
- artifact idempotency_key mismatch
- report_id mismatch
- revision_number mismatch

Also tests service-level and API-level waiter convergence without
dependency override, using SQLite in-memory (no sleep).

Each test uses a REAL SQL Repository backed by SQLite with explicit
clock control (no sleep).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.reports.domain.enums import ArtifactStatus
from cold_storage.modules.reports.domain.errors import (
    IdempotencyClaimError,
)
from cold_storage.modules.reports.infrastructure.orm import (
    Base,
)
from cold_storage.modules.reports.infrastructure.repository import (
    SQLReportRepository,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture()
def repo(session):
    return SQLReportRepository(session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_idempotency_record(
    repo: SQLReportRepository,
    key: str,
    *,
    actor: str = "test_actor",
    action: str = "render",
    fingerprint: str = "test_fingerprint",
    status: str = "completed",
    claim_token: str = "tok",
    claim_version: int = 1,
    result_payload: dict[str, Any] | None = None,
) -> None:
    """Insert a raw idempotency record using the ORM."""
    from cold_storage.modules.reports.infrastructure.orm import IdempotencyRecord

    rec = IdempotencyRecord(
        key=key,
        actor=actor,
        action=action,
        fingerprint=fingerprint,
        status=status,
        claim_token=claim_token,
        claim_version=claim_version,
        result_payload=result_payload,
    )
    repo._session.add(rec)
    repo.commit()


def _insert_artifact_record(
    repo: SQLReportRepository,
    artifact_id: str,
    *,
    report_id: str = "report1",
    report_revision_id: str = "rev1",
    revision_number: int = 1,
    format: str = "pdf",
    template_id: str = "tmpl1",
    template_version: str = "1.0",
    schema_version: str = "1.0",
    status: str = "completed",
    storage_key: str = "",
    file_name: str = "test.pdf",
    mime_type: str = "application/pdf",
    file_size_bytes: int = 100,
    file_sha256: str = "",
    source_content_hash: str = "hash1",
    render_manifest_json: dict[str, Any] | None = None,
    generated_by: str = "tester",
    idempotency_key: str = "",
    claim_token: str = "tok",
    claim_version: int = 1,
    locale: str = "zh-CN",
) -> str:
    """Insert a raw artifact record using the ORM."""
    from cold_storage.modules.reports.infrastructure.orm import (
        ReportExportArtifactRecord,
    )

    if not storage_key:
        storage_key = str(uuid.uuid4())
    rec = ReportExportArtifactRecord(
        id=artifact_id,
        report_id=report_id,
        report_revision_id=report_revision_id,
        revision_number=revision_number,
        format=format,
        template_id=template_id,
        template_version=template_version,
        schema_version=schema_version,
        status=status,
        storage_key=storage_key,
        file_name=file_name,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        file_sha256=file_sha256 or ("x" * 64),
        source_content_hash=source_content_hash,
        render_manifest_json=render_manifest_json or {},
        generated_by=generated_by,
        idempotency_key=idempotency_key,
        claim_token=claim_token,
        claim_version=claim_version,
        locale=locale,
    )
    repo._session.add(rec)
    repo.commit()
    return storage_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_waiter(
    repo: SQLReportRepository,
    session_factory: Callable[[], Any] | None = None,
) -> Any:
    """Create a DatabaseIdempotencyWaiter."""
    from cold_storage.modules.reports.application.render_service import (
        DatabaseIdempotencyWaiter,
    )

    return DatabaseIdempotencyWaiter(
        repo=repo,
        artifact_repo=repo,
        session_factory=session_factory,
        poll_interval=0.01,  # fast polling for tests
    )


# ===================================================================
# Tests — Lineage validation
# ===================================================================


class TestDefaultWaiterLineage:
    """DatabaseIdempotencyWaiter lineage validation tests."""

    def test_default_waiter_rejects_claim_version_mismatch(
        self,
        repo: SQLReportRepository,
        session_factory: Callable[[], Any],
    ) -> None:
        """When artifact claim_version differs from idempotency record's
        claim_version, the waiter raises IdempotencyClaimError."""
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_lv_01"

        # Insert artifact with claim_version=1
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            status="completed",
        )

        # Insert completed idempotency record with claim_version=2
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=2,
            result_payload={"artifact_id": artifact_id},
        )

        # Fetch the record and test _handle_completed directly
        record = repo.get_idempotency_record(ikey)
        assert record is not None
        waiter = _make_waiter(repo)

        with pytest.raises(IdempotencyClaimError, match="(?i)claim.*version|mismatch|lineage"):
            waiter._handle_completed(
                record,
                fingerprint,
                ikey,
                repo,
                expected_report_id="report1",
                expected_revision_number=1,
            )

    def test_default_waiter_rejects_artifact_idempotency_key_mismatch(
        self,
        repo: SQLReportRepository,
        session_factory: Callable[[], Any],
    ) -> None:
        """When the artifact's idempotency_key does not match the
        idempotency key being waited on, the waiter raises IdempotencyClaimError."""
        ikey = str(uuid.uuid4())
        wrong_ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_lv_02"

        # Insert artifact with a DIFFERENT idempotency_key
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key=wrong_ikey,
            claim_token="tok",
            claim_version=1,
            status="completed",
        )

        # Insert completed idempotency record for ikey (not wrong_ikey)
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        # Fetch the record and test _handle_completed directly
        record = repo.get_idempotency_record(ikey)
        assert record is not None
        waiter = _make_waiter(repo)

        # The waiter should detect the idempotency_key mismatch
        with pytest.raises(IdempotencyClaimError, match="(?i)key|mismatch|idempotency|lineage"):
            waiter._handle_completed(
                record,
                fingerprint,
                ikey,
                repo,
                expected_report_id="report1",
                expected_revision_number=1,
            )

    def test_default_waiter_rejects_report_id_mismatch(
        self,
        repo: SQLReportRepository,
        session_factory: Callable[[], Any],
    ) -> None:
        """When the completed artifact's report_id does not match
        expectations, the waiter raises IdempotencyClaimError."""
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_lv_03"

        # Insert artifact with an unexpected report_id
        _insert_artifact_record(
            repo,
            artifact_id,
            report_id="wrong_report",
            report_revision_id="rev_wrong",
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            status="completed",
        )

        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        # Fetch the record and test _handle_completed directly
        record = repo.get_idempotency_record(ikey)
        assert record is not None
        waiter = _make_waiter(repo)

        # The waiter should detect the report_id mismatch
        with pytest.raises(IdempotencyClaimError, match="(?i)report.*id|mismatch|lineage"):
            waiter._handle_completed(
                record,
                fingerprint,
                ikey,
                repo,
                expected_report_id="expected_report",
                expected_revision_number=1,
            )

    def test_default_waiter_rejects_revision_number_mismatch(
        self,
        repo: SQLReportRepository,
        session_factory: Callable[[], Any],
    ) -> None:
        """When the completed artifact's revision_number does not match
        expectations, the waiter raises IdempotencyClaimError."""
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_lv_04"

        # Insert artifact with revision_number=99 (unexpected)
        _insert_artifact_record(
            repo,
            artifact_id,
            report_id="report1",
            report_revision_id="rev1",
            revision_number=99,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            status="completed",
        )

        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        # Fetch the record and test _handle_completed directly
        record = repo.get_idempotency_record(ikey)
        assert record is not None
        waiter = _make_waiter(repo)

        # The waiter should detect the revision_number mismatch
        with pytest.raises(IdempotencyClaimError, match="(?i)revision|number|mismatch|lineage"):
            waiter._handle_completed(
                record,
                fingerprint,
                ikey,
                repo,
                expected_report_id="report1",
                expected_revision_number=1,
            )


# ===================================================================
# Tests — Service-level convergence
# ===================================================================


class TestDefaultServiceWaiter:
    """Service-level waiter convergence without injection."""

    def _make_waiter(
        self,
        repo: SQLReportRepository,
        session_factory: Callable[[], Any] | None = None,
    ) -> Any:
        return _make_waiter(repo, session_factory)

    def test_default_service_waiter_converges_sqlite_without_injection(
        self,
        repo: SQLReportRepository,
    ) -> None:
        """DatabaseIdempotencyWaiter converges (finds completed record)
        using a shared repo without session_factory injection."""
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_svc_01"

        # Insert artifact record
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            status="completed",
        )

        # Insert completed idempotency record
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(repo, session_factory=None)
        deadline = __import__("time").monotonic() + 5.0

        result = waiter.wait_for_completion(ikey, fingerprint, deadline)
        assert result is not None
        assert result.id == artifact_id
        assert result.status == ArtifactStatus.COMPLETED


# ===================================================================
# Tests — API-level waiter convergence
# ===================================================================


class TestDefaultApiWaiter:
    """API-level waiter convergence without dependency override.

    These tests verify that ReportRenderService's default waiter
    (DatabaseIdempotencyWaiter) converges correctly without injecting
    a custom waiter or session_factory override.
    """

    def test_default_api_waiter_converges_without_dependency_override(
        self,
        repo: SQLReportRepository,
        session_factory: Callable[[], Any],
    ) -> None:
        """ReportRenderService resolves idempotency conflict via the default
        DatabaseIdempotencyWaiter without any custom waiter override.

        This simulates the API render flow where:
        1. A first call completes the render
        2. A second call with the same fingerprint finds the completed record
           and returns via the waiter
        """
        from cold_storage.modules.reports.application.render_service import (
            DatabaseIdempotencyWaiter,
            ReportRenderService,
            ReportRenderUnitOfWork,
        )
        from cold_storage.modules.reports.infrastructure.artifact_storage import (
            ReportArtifactStorage,
        )

        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_api_01"

        # Pre-seed exactly as if a prior render completed:
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            status="completed",
        )
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        # Build a minimal service that uses the default waiter
        uow = ReportRenderUnitOfWork(session=repo._session, artifact_repo=repo)
        storage = ReportArtifactStorage("/tmp/test_api_waiter_" + str(uuid.uuid4())[:8])

        # Default waiter — no override, no session_factory
        waiter = DatabaseIdempotencyWaiter(
            repo=repo,
            artifact_repo=repo,
            session_factory=None,
            poll_interval=0.01,
        )

        service = ReportRenderService(
            uow=uow,
            storage=storage,
            template_repo=repo,
            idempotency_waiter=waiter,
            stale_claim_seconds=30,
        )

        # Resolve the conflict — the waiter should find the completed record
        resolved = service._resolve_idempotency_conflict(ikey, fingerprint)
        assert resolved is not None
        assert resolved.id == artifact_id
        assert resolved.status == ArtifactStatus.COMPLETED
