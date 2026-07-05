"""Real concurrent waiter tests — threading.Barrier based convergence.

Tests:
1. test_default_waiter_two_requests_converge_sqlite
   — File-backed SQLite, two threads with threading.Barrier(2), both call
     render() without explicit idempotency_waiter injection.
2. test_default_waiter_two_requests_converge_postgresql
   — Same pattern against PostgreSQL (skip if DATABASE_URL not set).
3. test_default_waiter_two_fastapi_requests_converge
   — TestClient + real FastAPI app, two concurrent httpx POST requests.
4. test_waiter_failure_matrix
   — Controlled waiter setup exercising all validation failures.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cold_storage.modules.reports.application.render_service import (
    DatabaseIdempotencyWaiter,
    ReportRenderService,
    ReportRenderUnitOfWork,
)
from cold_storage.modules.reports.domain.enums import (
    ArtifactStatus,
    ExportFormat,
    ReportLocale,
    ReportType,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.errors import (
    IdempotencyClaimError,
    IdempotencyPayloadConflictError,
)
from cold_storage.modules.reports.domain.models import Report
from cold_storage.modules.reports.infrastructure.artifact_storage import (
    ReportArtifactStorage,
)
from cold_storage.modules.reports.infrastructure.orm import Base
from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository

# ======================================================================
# Helpers — shared pipeline setup
# ======================================================================


class _MinimalDataProvider:
    """Minimal data provider for convergence tests."""

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return {"name": "Test", "location": "Test", "description": "Test"}

    def get_project_version(
        self, version_id: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        return {"id": version_id, "version_number": 1, "status": "active"}

    def get_calculation_results(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return []

    def get_scheme_results(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        return None

    def get_agent_sessions(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return []

    def get_knowledge_documents(self) -> list[dict[str, Any]]:
        return []


def _seed_active_template(repo: SQLReportRepository, fmt_str: str, locale_str: str) -> None:
    """Seed a single ACTIVE template for the given format and locale."""
    from dataclasses import replace

    from cold_storage.modules.reports.domain.models import ReportTemplate
    from cold_storage.modules.reports.infrastructure.template_seed import (
        _compute_content_hash,
        _load_manifest,
    )

    fmt = ExportFormat(fmt_str)
    manifest = _load_manifest(fmt, locale=locale_str, allow_legacy_fallback=True)
    if not manifest:
        return

    template_code = manifest.get("template_code", "cold_storage_concept_design")
    version = manifest.get("version", "1.0.0")
    report_type_str = manifest.get("report_type", "cold_storage_concept_design")
    schema_version = manifest.get("schema_version", f"{report_type_str}@{version}")
    content_hash = _compute_content_hash(manifest)
    report_type = ReportType(report_type_str)
    locale = ReportLocale(locale_str)

    template = ReportTemplate.create(
        template_code=template_code,
        report_type=report_type,
        format=fmt,
        version=version,
        schema_version=schema_version,
        locale=locale,
        manifest_json=manifest,
        template_content_hash=content_hash,
        created_by="system",
    )
    template = replace(template, status=TemplateStatus.ACTIVE)
    repo.save_template(template)


def _seed_both_locale_templates(repo: SQLReportRepository) -> None:
    """Create both zh-CN and en-US templates for DOCX, all ACTIVE."""
    for locale_str in ("zh-CN", "en-US"):
        _seed_active_template(repo, "docx", locale_str)
        _seed_active_template(repo, "pdf", locale_str)


def _full_setup(
    session_factory: Callable[[], Any],
    tmp_path: Path,
    subdir: str = "artifacts",
) -> tuple[Report, ReportArtifactStorage]:
    """Create a report with one revision and seeded templates.

    Returns (report, storage) for use by convergence tests.
    """
    session = session_factory()
    try:
        repo = SQLReportRepository(session)

        # Create report
        from cold_storage.modules.reports.application.assembler import ReportAssembler
        from cold_storage.modules.reports.application.service import ReportService

        provider = _MinimalDataProvider()
        assembler = ReportAssembler(provider)
        service = ReportService(repository=repo, assembler=assembler)

        report = Report.create(
            project_id="test-proj",
            project_version_id="test-ver",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            created_by="test-user",
        )
        repo.save_report(report)
        session.commit()

        revision = service.generate_revision(report.id, "test-user")
        assert revision is not None

        # Seed templates
        _seed_both_locale_templates(repo)

        session.commit()
    finally:
        session.close()

    storage_dir = tmp_path / subdir
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage = ReportArtifactStorage(str(storage_dir))

    return report, storage


# Grab Callable from typing
from collections.abc import Callable  # noqa: E402


def _run_concurrent_render(
    session_factory: Callable[[], Any],
    storage: ReportArtifactStorage,
    report_id: str,
    revision_number: int,
    fmt: str = "docx",
    locale: ReportLocale = ReportLocale.ZH_CN,
    actor: str = "test-user",
    idempotency_key: str | None = None,
) -> tuple[list[Any], list[Exception]]:
    """Run two concurrent render calls using threading.Barrier.

    Returns (results, errors).
    """
    barrier = threading.Barrier(2, timeout=30)
    results: list[Any] = [None, None]
    errors: list[Exception] = [None, None]
    lock = threading.Lock()

    def _render(idx: int) -> None:
        try:
            thread_session = session_factory()
            try:
                thread_repo = SQLReportRepository(thread_session)
                thread_uow = ReportRenderUnitOfWork(
                    thread_session,
                    report_repo=thread_repo,
                    artifact_repo=thread_repo,
                    session_factory=session_factory,
                )
                thread_svc = ReportRenderService(
                    uow=thread_uow,
                    storage=storage,
                    template_repo=thread_repo,
                )
                barrier.wait()
                artifact = thread_svc.render(
                    report_id=report_id,
                    revision_number=revision_number,
                    format=fmt,
                    template_version=None,
                    mode="draft",
                    actor=actor,
                    idempotency_key=idempotency_key,
                    locale=locale,
                )
                with lock:
                    results[idx] = artifact
            finally:
                thread_session.close()
        except Exception as e:
            with lock:
                errors[idx] = e

    t1 = threading.Thread(target=_render, args=(0,))
    t2 = threading.Thread(target=_render, args=(1,))
    t1.start()
    t2.start()
    t1.join(timeout=60)
    t2.join(timeout=60)

    return results, errors


def _find_idempotency_records(
    session_factory: Callable[[], Any], key: str, status: str | None = None
) -> list[dict[str, Any]]:
    """Find idempotency records by key."""
    from cold_storage.modules.reports.infrastructure.orm import IdempotencyRecord

    with session_factory() as sess:
        q = sa.select(IdempotencyRecord).where(IdempotencyRecord.key == key)
        if status:
            q = q.where(IdempotencyRecord.status == status)
        rows = sess.execute(q).scalars().all()
        result = []
        for r in rows:
            result.append(
                {
                    "key": r.key,
                    "status": r.status,
                    "claim_token": r.claim_token,
                    "claim_version": r.claim_version,
                    "result_payload": r.result_payload,
                    "fingerprint": r.fingerprint,
                }
            )
        return result


def _count_artifacts(
    session_factory: Callable[[], Any],
    report_id: str,
    status: str | None = None,
) -> int:
    """Count artifacts by report_id and optional status."""
    from cold_storage.modules.reports.infrastructure.orm import ReportExportArtifactRecord

    with session_factory() as sess:
        q = sa.select(sa.func.count(ReportExportArtifactRecord.id)).where(
            ReportExportArtifactRecord.report_id == report_id
        )
        if status:
            q = q.where(ReportExportArtifactRecord.status == status)
        return sess.execute(q).scalar() or 0


# ======================================================================
# 1. SQLite waiter convergence
# ======================================================================


class TestDefaultWaiterConcurrentSQLite:
    """File-backed SQLite convergence tests with two concurrent render calls."""

    @pytest.fixture()
    def db_path(self, tmp_path: Path) -> str:
        """File-backed SQLite database path."""
        return str(tmp_path / "concurrent_waiter.db")

    @pytest.fixture()
    def engine(self, db_path: str):
        """File-backed SQLite engine."""
        eng = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        # WAL mode enables concurrent reader + writer threads
        with eng.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(eng)
        yield eng
        eng.dispose()

    @pytest.fixture()
    def session_factory(self, engine):
        return sessionmaker(bind=engine, expire_on_commit=False)

    @pytest.fixture()
    def report_and_storage(
        self, session_factory, tmp_path: Path
    ) -> tuple[Report, ReportArtifactStorage]:
        return _full_setup(session_factory, tmp_path, subdir="concurrent_waiter_artifacts")

    def test_default_waiter_two_requests_converge_sqlite(
        self,
        session_factory,
        report_and_storage: tuple[Report, ReportArtifactStorage],
        tmp_path: Path,
    ) -> None:
        """Two concurrent render() calls with same params converge to one artifact.

        Uses threading.Barrier(2), independent sessions/repos per thread,
        no explicit idempotency_waiter injection (default DatabaseIdempotencyWaiter).
        """
        report, storage = report_and_storage
        ikey = f"converge-sqlite-{uuid.uuid4().hex}"

        results, errors = _run_concurrent_render(
            session_factory,
            storage,
            report.id,
            revision_number=1,
            idempotency_key=ikey,
        )

        # Both should succeed
        for i, err in enumerate(errors):
            assert err is None, f"Thread {i} raised: {err}"

        # Both return artifacts
        artifact1 = results[0]
        artifact2 = results[1]
        assert artifact1 is not None, "Thread 0 returned None"
        assert artifact2 is not None, "Thread 1 returned None"
        assert artifact1.status == ArtifactStatus.COMPLETED
        assert artifact2.status == ArtifactStatus.COMPLETED

        # Same artifact_id
        assert artifact1.id == artifact2.id, (
            f"Same idempotency key should return same artifact, "
            f"got {artifact1.id} vs {artifact2.id}"
        )

        # Same file_sha256
        assert artifact1.file_sha256 == artifact2.file_sha256, (
            f"Same idempotency key should return same sha256, "
            f"got {artifact1.file_sha256} vs {artifact2.file_sha256}"
        )

        # Only 1 COMPLETED artifact in DB
        completed_count = _count_artifacts(session_factory, report.id, status="completed")
        assert completed_count == 1, f"Expected exactly 1 COMPLETED artifact, got {completed_count}"

        # Only 1 completed idempotency record
        records = _find_idempotency_records(session_factory, ikey, status="completed")
        assert len(records) == 1, (
            f"Expected exactly 1 completed idempotency record, got {len(records)}"
        )

        # 0 RENDERING/FAILED artifacts
        rendering_count = _count_artifacts(session_factory, report.id, status="rendering")
        assert rendering_count == 0, f"Expected 0 RENDERING artifacts, got {rendering_count}"
        failed_count = _count_artifacts(session_factory, report.id, status="failed")
        assert failed_count == 0, f"Expected 0 FAILED artifacts, got {failed_count}"

        # 0 temp/orphan files in storage
        storage_dir = Path(storage._base_dir)
        temp_files = list(storage_dir.glob("*/temp*")) + list(storage_dir.glob("temp*"))
        assert len(temp_files) == 0, (
            f"Expected 0 temp files in storage, got {len(temp_files)}: {temp_files}"
        )

        # Storage directory only has the one artifact file
        artifact_dirs = [d for d in storage_dir.iterdir() if d.is_dir()]
        total_artifact_files = sum(len(list(d.iterdir())) for d in artifact_dirs)
        assert total_artifact_files >= 1, "Expected at least 1 artifact file in storage"
        # Check that there's exactly 1 artifact directory with files
        # (there could be sidecar .meta files as well)
        if artifact_dirs:
            first_dir = artifact_dirs[0]
            files_in_first = list(first_dir.iterdir())
            # Should have at least the main artifact file
            main_files = [f for f in files_in_first if not f.name.endswith(".meta")]
            assert len(main_files) == 1, (
                f"Expected exactly 1 main artifact file, got {len(main_files)}: {main_files}"
            )


# ======================================================================
# 2. PostgreSQL waiter convergence (skip if DATABASE_URL not set)
# ======================================================================


@pytest.mark.skipif(
    "os.environ.get('DATABASE_URL') is None",
    reason="DATABASE_URL not set — skipping PostgreSQL test",
)
class TestDefaultWaiterConcurrentPostgreSQL:
    """PostgreSQL convergence tests — requires DATABASE_URL env var."""

    @pytest.fixture()
    def pg_session_factory(self):
        """Create a temporary PostgreSQL schema for isolation."""
        from urllib.parse import urlparse

        pg_url = os.environ["DATABASE_URL"]
        urlparse(pg_url)
        schema = f"test_waiter_pg_{uuid.uuid4().hex[:8]}"

        # Create schema
        eng = sa.create_engine(pg_url, isolation_level="AUTOCOMMIT")
        with eng.connect() as conn:
            conn.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        eng.dispose()

        schema_engine = sa.create_engine(
            pg_url,
            connect_args={"options": f"-c search_path={schema}"},
        )
        Base.metadata.create_all(schema_engine)
        sf = sa.orm.sessionmaker(bind=schema_engine, expire_on_commit=False)

        yield sf

        schema_engine.dispose()
        # Cleanup
        cleanup_eng = sa.create_engine(pg_url, isolation_level="AUTOCOMMIT")
        with cleanup_eng.connect() as conn:
            conn.execute(sa.text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        cleanup_eng.dispose()

    @pytest.fixture()
    def report_and_storage(
        self, pg_session_factory, tmp_path: Path
    ) -> tuple[Report, ReportArtifactStorage]:
        return _full_setup(pg_session_factory, tmp_path, subdir="pg_waiter_artifacts")

    def test_default_waiter_two_requests_converge_postgresql(
        self,
        pg_session_factory,
        report_and_storage: tuple[Report, ReportArtifactStorage],
    ) -> None:
        """Two concurrent render() calls against PostgreSQL converge to one artifact."""
        report, storage = report_and_storage
        ikey = f"converge-pg-{uuid.uuid4().hex}"

        results, errors = _run_concurrent_render(
            pg_session_factory,
            storage,
            report.id,
            revision_number=1,
            idempotency_key=ikey,
        )

        for i, err in enumerate(errors):
            assert err is None, f"Thread {i} raised: {err}"

        artifact1 = results[0]
        artifact2 = results[1]
        assert artifact1 is not None
        assert artifact2 is not None
        assert artifact1.status == ArtifactStatus.COMPLETED
        assert artifact2.status == ArtifactStatus.COMPLETED
        assert artifact1.id == artifact2.id
        assert artifact1.file_sha256 == artifact2.file_sha256

        completed_count = _count_artifacts(pg_session_factory, report.id, status="completed")
        assert completed_count == 1

        records = _find_idempotency_records(pg_session_factory, ikey, status="completed")
        assert len(records) == 1

        rendering_count = _count_artifacts(pg_session_factory, report.id, status="rendering")
        assert rendering_count == 0
        failed_count = _count_artifacts(pg_session_factory, report.id, status="failed")
        assert failed_count == 0

        # 0 temp/orphan files in storage
        storage_dir = Path(storage._base_dir)
        temp_files = list(storage_dir.glob("*/temp*")) + list(storage_dir.glob("temp*"))
        assert len(temp_files) == 0


# ======================================================================
# 3. FastAPI endpoint convergence
# ======================================================================


@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="FastAPI waiter test uses local SQLite setup incompatible with PG CI",
)
class TestDefaultWaiterFastAPIConvergence:
    """TestClient with real FastAPI app, two concurrent POST requests."""

    @pytest.fixture()
    def db_path(self, tmp_path: Path) -> str:
        return str(tmp_path / "fastapi_waiter.db")

    @pytest.fixture()
    def engine(self, db_path: str):
        eng = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        # WAL mode enables concurrent reader + writer threads
        with eng.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(eng)
        yield eng
        eng.dispose()

    @pytest.fixture()
    def session_factory(self, engine):
        return sessionmaker(bind=engine, expire_on_commit=False)

    @pytest.fixture()
    def app_and_storage(self, session_factory, tmp_path: Path) -> tuple[Any, ReportArtifactStorage]:
        """Build a real FastAPI app with per-request session wiring."""
        from fastapi import FastAPI

        from cold_storage.modules.reports.api.routes import (
            _get_actor,
            _get_render_service,
            _get_service,
            reports_api_router,
        )

        # Full pipeline setup — create the report/revision/templates upfront
        session = session_factory()
        repo = SQLReportRepository(session)

        provider = _MinimalDataProvider()
        from cold_storage.modules.reports.application.assembler import ReportAssembler
        from cold_storage.modules.reports.application.service import ReportService

        assembler = ReportAssembler(provider)
        service = ReportService(repository=repo, assembler=assembler)

        report = Report.create(
            project_id="proj-fastapi-converge",
            project_version_id="ver-1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            created_by="test-user",
        )
        repo.save_report(report)
        session.commit()

        revision = service.generate_revision(report.id, "test-user")
        assert revision is not None

        _seed_both_locale_templates(repo)
        session.commit()

        storage_dir = tmp_path / "fastapi_artifacts"
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage = ReportArtifactStorage(str(storage_dir))

        # Build app with per-request render service
        app = FastAPI()
        app.include_router(reports_api_router)

        # Per-request service gets its own session
        def _get_report_service() -> ReportService:
            return service  # ReportService is read-only after setup

        def _get_render_svc() -> ReportRenderService:
            req_session = session_factory()
            req_repo = SQLReportRepository(req_session)
            req_uow = ReportRenderUnitOfWork(
                req_session,
                report_repo=req_repo,
                artifact_repo=req_repo,
                session_factory=session_factory,
            )
            return ReportRenderService(
                uow=req_uow,
                storage=storage,
                template_repo=req_repo,
            )

        app.dependency_overrides[_get_service] = _get_report_service
        app.dependency_overrides[_get_render_service] = _get_render_svc
        app.dependency_overrides[_get_actor] = lambda: "test-user"

        yield app, storage, report, revision

        session.close()

    @pytest.fixture()
    def test_client(self, app_and_storage):
        from fastapi.testclient import TestClient

        app, storage, report, revision = app_and_storage
        return TestClient(app), report, revision

    def test_default_waiter_two_fastapi_requests_converge(
        self,
        test_client,
    ) -> None:
        """Two concurrent POST requests with same params converge to same artifact_id."""
        from fastapi.testclient import TestClient

        client, report, revision = test_client
        app = client.app

        url = f"/api/v1/reports/{report.id}/revisions/{revision.revision_number}/render"

        body = {
            "format": "docx",
            "mode": "draft",
            "locale": "zh-CN",
            "idempotency_key": f"fastapi-converge-{uuid.uuid4().hex}",
        }

        barrier = threading.Barrier(2, timeout=30)
        responses: list[int | None] = [None, None]
        response_bodies: list[dict[str, Any] | None] = [None, None]
        errors: list[Exception | None] = [None, None]
        lock = threading.Lock()

        def _do_request(idx: int) -> None:
            try:
                tc = TestClient(app)
                barrier.wait()
                resp = tc.post(url, json=body)
                with lock:
                    responses[idx] = resp.status_code
                    response_bodies[idx] = resp.json()
            except Exception as e:
                with lock:
                    errors[idx] = e

        t1 = threading.Thread(target=_do_request, args=(0,))
        t2 = threading.Thread(target=_do_request, args=(1,))
        t1.start()
        t2.start()
        t1.join(timeout=60)
        t2.join(timeout=60)

        for i, err in enumerate(errors):
            assert err is None, f"Thread {i} raised: {err}"

        # Both should return 200
        for i, status in enumerate(responses):
            assert status == 200, f"Thread {i} returned status {status}, body: {response_bodies[i]}"

        # Both should return the same artifact_id
        body1 = response_bodies[0]
        body2 = response_bodies[1]
        assert body1 is not None
        assert body2 is not None
        assert body1["artifact_id"] == body2["artifact_id"], (
            f"Same params should return same artifact_id, "
            f"got {body1['artifact_id']} vs {body2['artifact_id']}"
        )

        # Both should have status 'completed'
        assert body1["status"] == "completed"
        assert body2["status"] == "completed"

        # Same file_sha256
        assert body1["file_sha256"] == body2["file_sha256"]


# ======================================================================
# 4. Waiter failure matrix
# ======================================================================


class TestWaiterFailureMatrix:
    """Controlled DatabaseIdempotencyWaiter tests exercising all validation paths."""

    @pytest.fixture()
    def engine(self, tmp_path: Path):
        db_path = tmp_path / "waiter_failure_matrix.db"
        eng = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        # WAL mode enables concurrent reader + writer threads
        with eng.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(eng)
        yield eng
        eng.dispose()

    @pytest.fixture()
    def session_factory(self, engine):
        return sessionmaker(bind=engine, expire_on_commit=False)

    def _make_waiter(
        self,
        session_factory,
        poll_interval: float = 0.01,
    ) -> DatabaseIdempotencyWaiter:
        return DatabaseIdempotencyWaiter(
            session_factory=session_factory,
            poll_interval=poll_interval,
        )

    def _insert_artifact_record(
        self,
        session_factory,
        artifact_id: str,
        *,
        report_id: str = "report1",
        revision_number: int = 1,
        status: str = "completed",
        idempotency_key: str = "",
        claim_token: str = "tok",
        claim_version: int = 1,
    ) -> None:
        """Insert a raw artifact record."""
        from cold_storage.modules.reports.infrastructure.orm import ReportExportArtifactRecord

        with session_factory() as sess:
            rec = ReportExportArtifactRecord(
                id=artifact_id,
                report_id=report_id,
                report_revision_id="rev1",
                revision_number=revision_number,
                format="pdf",
                template_id="tmpl1",
                template_version="1.0",
                schema_version="1.0",
                status=status,
                storage_key="sk_" + artifact_id,
                file_name="test.pdf",
                mime_type="application/pdf",
                file_size_bytes=100,
                file_sha256="x" * 64,
                source_content_hash="hash1",
                render_manifest_json={},
                generated_by="tester",
                idempotency_key=idempotency_key,
                claim_token=claim_token,
                claim_version=claim_version,
                locale="zh-CN",
            )
            sess.add(rec)
            sess.commit()

    def _insert_idempotency_record(
        self,
        session_factory,
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
        """Insert a raw idempotency record."""
        from cold_storage.modules.reports.infrastructure.orm import IdempotencyRecord

        with session_factory() as sess:
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
            sess.add(rec)
            sess.commit()

    # ------------------------------------------------------------------
    # Winner render failure
    # ------------------------------------------------------------------

    def test_waiter_winner_render_failure(
        self,
        session_factory,
    ) -> None:
        """When the winner's render fails, the waiter propagates the failure."""
        ikey = "failure-key-winner-fail"
        fingerprint = "fp-winner-fail"

        # Insert a FAILED idempotency record
        self._insert_idempotency_record(
            session_factory,
            ikey,
            fingerprint=fingerprint,
            status="failed",
            result_payload={
                "failure_code": "RenderError",
                "failure_message": "Simulated render failure",
            },
        )

        waiter = self._make_waiter(session_factory)
        deadline = time.monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError) as exc_info:
            waiter.wait_for_completion(ikey, fingerprint, deadline)
        assert exc_info.value.failure_code == "RenderError"

    # ------------------------------------------------------------------
    # Invalid result payload (no artifact_id)
    # ------------------------------------------------------------------

    def test_waiter_invalid_result_payload(
        self,
        session_factory,
    ) -> None:
        """When result_payload has no artifact_id, waiter raises IdempotencyClaimError."""
        ikey = "failure-key-no-artifact-id"
        fingerprint = "fp-no-artifact-id"

        self._insert_idempotency_record(
            session_factory,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            result_payload={"some_key": "some_value"},  # No artifact_id
        )

        waiter = self._make_waiter(session_factory)
        deadline = time.monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError) as exc_info:
            waiter.wait_for_completion(ikey, fingerprint, deadline)
        assert exc_info.value.failure_code == "MissingArtifactId"

    # ------------------------------------------------------------------
    # Missing completed artifact (artifact_id in payload but not in DB)
    # ------------------------------------------------------------------

    def test_waiter_missing_completed_artifact(
        self,
        session_factory,
    ) -> None:
        """When artifact_id in payload doesn't exist in DB, waiter raises."""
        ikey = "failure-key-missing-artifact"
        fingerprint = "fp-missing-artifact"

        self._insert_idempotency_record(
            session_factory,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            result_payload={"artifact_id": "nonexistent-artifact-id"},
        )

        waiter = self._make_waiter(session_factory)
        deadline = time.monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError) as exc_info:
            waiter.wait_for_completion(ikey, fingerprint, deadline)
        assert exc_info.value.failure_code == "ArtifactNotFound"

    # ------------------------------------------------------------------
    # claim_token mismatch
    # ------------------------------------------------------------------

    def test_waiter_claim_token_mismatch(
        self,
        session_factory,
    ) -> None:
        """When artifact claim_token != record claim_token, waiter raises."""
        ikey = "failure-key-claim-token"
        fingerprint = "fp-claim-token"
        artifact_id = "artifact-claim-token-mismatch"

        # Insert artifact with claim_token "tok_a"
        self._insert_artifact_record(
            session_factory,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok_a",
            claim_version=1,
        )

        # Insert idempotency record with DIFFERENT claim_token "tok_b"
        self._insert_idempotency_record(
            session_factory,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok_b",
            claim_version=2,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(session_factory)
        deadline = time.monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError) as exc_info:
            waiter.wait_for_completion(ikey, fingerprint, deadline)
        assert exc_info.value.failure_code == "ClaimMismatch"

    # ------------------------------------------------------------------
    # claim_version mismatch
    # ------------------------------------------------------------------

    def test_waiter_claim_version_mismatch(
        self,
        session_factory,
    ) -> None:
        """When artifact claim_version != record claim_version, waiter raises."""
        ikey = "failure-key-claim-version"
        fingerprint = "fp-claim-version"
        artifact_id = "artifact-claim-version-mismatch"

        # Insert artifact with claim_version=99
        self._insert_artifact_record(
            session_factory,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=99,
        )

        # Insert idempotency record with claim_version=5
        self._insert_idempotency_record(
            session_factory,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=5,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(session_factory)
        deadline = time.monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError) as exc_info:
            waiter.wait_for_completion(ikey, fingerprint, deadline)
        assert exc_info.value.failure_code == "ClaimVersionMismatch"

    # ------------------------------------------------------------------
    # artifact idempotency_key mismatch
    # ------------------------------------------------------------------

    def test_waiter_artifact_idempotency_key_mismatch(
        self,
        session_factory,
    ) -> None:
        """When artifact.idempotency_key != requested key, waiter raises."""
        ikey = "failure-key-idem-key"
        fingerprint = "fp-idem-key"
        artifact_id = "artifact-idem-key-mismatch"

        # Insert artifact with DIFFERENT idempotency_key
        self._insert_artifact_record(
            session_factory,
            artifact_id,
            idempotency_key="different_key",
            claim_token="tok",
            claim_version=1,
        )

        # Insert idempotency record with the requested key
        self._insert_idempotency_record(
            session_factory,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(session_factory)
        deadline = time.monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError) as exc_info:
            waiter.wait_for_completion(ikey, fingerprint, deadline)
        assert exc_info.value.failure_code == "IdempotencyKeyMismatch"

    # ------------------------------------------------------------------
    # report_id mismatch
    # ------------------------------------------------------------------

    def test_waiter_report_id_mismatch(
        self,
        session_factory,
    ) -> None:
        """When expected_report_id != artifact.report_id, waiter raises."""
        ikey = "failure-key-report-id"
        fingerprint = "fp-report-id"
        artifact_id = "artifact-report-id-mismatch"

        self._insert_artifact_record(
            session_factory,
            artifact_id,
            report_id="report_abc",
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
        )

        self._insert_idempotency_record(
            session_factory,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(session_factory)
        deadline = time.monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError) as exc_info:
            waiter.wait_for_completion(
                ikey,
                fingerprint,
                deadline,
                expected_report_id="different_report",
            )
        assert exc_info.value.failure_code == "ReportIdMismatch"

    # ------------------------------------------------------------------
    # revision_number mismatch
    # ------------------------------------------------------------------

    def test_waiter_revision_number_mismatch(
        self,
        session_factory,
    ) -> None:
        """When expected_revision_number != artifact.revision_number, waiter raises."""
        ikey = "failure-key-revision-number"
        fingerprint = "fp-revision-number"
        artifact_id = "artifact-revision-mismatch"

        self._insert_artifact_record(
            session_factory,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            revision_number=1,
        )

        self._insert_idempotency_record(
            session_factory,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(session_factory)
        deadline = time.monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError) as exc_info:
            waiter.wait_for_completion(
                ikey,
                fingerprint,
                deadline,
                expected_revision_number=99,
            )
        assert exc_info.value.failure_code == "RevisionNumberMismatch"

    # ------------------------------------------------------------------
    # Timeout
    # ------------------------------------------------------------------

    def test_waiter_timeout(
        self,
        session_factory,
    ) -> None:
        """When no idempotency record exists and deadline elapses, waiter times out."""
        waiter = self._make_waiter(session_factory, poll_interval=0.05)
        deadline = time.monotonic() + 0.3  # Short deadline

        with pytest.raises(IdempotencyClaimError) as exc_info:
            waiter.wait_for_completion(
                "nonexistent-key",
                expected_fingerprint="irrelevant",
                deadline=deadline,
            )
        assert exc_info.value.failure_code == "WaiterTimeout"

    # ------------------------------------------------------------------
    # Fingerprint mismatch (IdempotencyPayloadConflictError)
    # ------------------------------------------------------------------

    def test_waiter_fingerprint_mismatch(
        self,
        session_factory,
    ) -> None:
        """When record fingerprint != expected_fingerprint, waiter raises."""
        ikey = "failure-key-fingerprint"
        artifact_id = "artifact-fingerprint-mismatch"

        # Insert artifact
        self._insert_artifact_record(
            session_factory,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
        )

        # Insert idempotency record with fingerprint "actual-fp"
        self._insert_idempotency_record(
            session_factory,
            ikey,
            fingerprint="actual-fp",
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(session_factory)
        deadline = time.monotonic() + 5.0

        # Expect IdempotencyPayloadConflictError, not IdempotencyClaimError
        with pytest.raises(IdempotencyPayloadConflictError):
            waiter.wait_for_completion(
                ikey,
                expected_fingerprint="different-fp",
                deadline=deadline,
            )
