"""Migration 0039 upgrade/downgrade/upgrade cycle test.

Real Alembic + real PostgreSQL + real report_export_artifacts.
Verifies migration ``0039_widen_report_export_artifact_mime_type`` is
fully idempotent on PostgreSQL by running REAL Alembic subprocess
commands against a temporary PostgreSQL schema created for each test
and exercising the REAL production table ``report_export_artifacts``
with REAL parent FK rows (no probe tables, no FK disabling, no
mocking).

Brief §3: ``pytestmark = pytest.mark.postgresql`` (P1-2 fix — CI's
``pytest -m postgresql`` step must collect these tests).

Brief §4-§6: real Alembic upgrade/downgrade on real
``report_export_artifacts.mime_type`` — no probe tables, no raw
``ALTER COLUMN``-on-hand-crafted-table to simulate the migration.

Brief §8: each test creates its own temporary PostgreSQL schema
inside a temporary PostgreSQL database, the alembic version table
and all migration objects live in that schema (not the default
``public`` schema), and the entire database is dropped on teardown
without silent suppression.

Requires a running PostgreSQL instance (``DATABASE_URL`` env var).
Skipped if PostgreSQL is not available.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.postgresql


# ---------------------------------------------------------------------------
# Migration / revision constants
# ---------------------------------------------------------------------------

BACKEND_DIR = os.path.join(
    os.path.dirname(__file__),  # …/tests/integration
    "..",  # …/tests
    "..",  # …/backend
)

REVISION_HEAD = "0039_widen_report_export_artifact_mime_type"
REVISION_PARENT = "0038_phase4_slice1_coefficient_approval"
TBL_ARTIFACTS = "report_export_artifacts"
COL_MIME_TYPE = "mime_type"
ALEMBIC_VERSION_TABLE = "alembic_version"

# Standard DOCX MIME (the brief's actual production value).
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"  # 71 chars
MIME_PDF = "application/pdf"  # 15 chars
MIME_JSON = "application/json"  # 16 chars
# XLSX is 65 chars (not "short") — would itself trigger the preflight
# fail-closed path if inserted before a downgrade.

# Standard canonical locales enforced by the report_export_artifacts CHECK
# constraints introduced by migration 0019.
LOCALE_ZH = "zh-CN"
LOCALE_EN = "en-US"


# ---------------------------------------------------------------------------
# Session-scoped admin URL
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_admin_url() -> str:
    """Return the admin URL (the original DATABASE_URL) for creating per-test DBs."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping PostgreSQL migration tests")
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL is not postgresql — skipping")
    return url


# ---------------------------------------------------------------------------
# Alembic subprocess helper
# ---------------------------------------------------------------------------


def _run_alembic(
    args: list[str],
    *,
    test_url: str,
    schema: str,
    timeout: int = 240,
) -> subprocess.CompletedProcess:
    """Run alembic with the per-test schema pre-created and the search_path scoped.

    Required env contract (per PR67 P1-4 discovery):
    - ``DATABASE_BACKEND=postgresql`` is required so env.py's
      ``_build_database_url()`` doesn't default to SQLite.
    - ``DATABASE_URL`` must use the ``postgresql+psycopg2://`` driver.
    - The target ``schema`` must exist BEFORE this subprocess runs.
    - ``PGOPTIONS=-c search_path=<schema>`` so alembic creates the
      version table and all DDL in the per-test schema.
    """
    env = os.environ.copy()
    env["DATABASE_BACKEND"] = "postgresql"
    env["DATABASE_URL"] = test_url
    env["PYTHONPATH"] = "src"
    env["PGOPTIONS"] = f"-c search_path={schema}"
    return subprocess.run(
        ["uv", "run", "alembic"] + args,
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _admin_libpq_from_sa(url_sa: str) -> str:
    """Convert a ``postgresql+psycopg2://`` URL to a plain libpq URL (no driver suffix)."""
    parsed = urlparse(url_sa)
    scheme = parsed.scheme.replace("+psycopg2", "")
    pg_port = parsed.port or 5432
    db_part = parsed.path.lstrip("/") or "postgres"
    return f"{scheme}://{parsed.username}@{parsed.hostname}:{pg_port}/{db_part}"


# ---------------------------------------------------------------------------
# Per-test isolation: a fresh PostgreSQL DATABASE + SCHEMA
# ---------------------------------------------------------------------------


@pytest.fixture()
def pg_test_db(pg_admin_url: str) -> str:
    """Per-test: a fresh PostgreSQL DATABASE (isolation unit).

    Yields the test URL (``postgresql+psycopg2://.../<db>``). On
    teardown, terminate open backends then ``DROP DATABASE ... WITH
    (FORCE)`` (no silent suppression).
    """
    parsed = urlparse(pg_admin_url)
    pg_user = parsed.username
    pg_host = parsed.hostname
    pg_port = parsed.port or 5432
    test_db_name = f"mig0039_{uuid.uuid4().hex[:12]}"
    test_url = f"postgresql+psycopg2://{pg_user}@{pg_host}:{pg_port}/{test_db_name}"
    admin_url_libpq = _admin_libpq_from_sa(pg_admin_url)

    admin_eng = sa.create_engine(admin_url_libpq, isolation_level="AUTOCOMMIT")
    try:
        with admin_eng.begin() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{test_db_name}"'))
        yield test_url
    finally:
        cleanup_errors: list[BaseException] = []
        with admin_eng.begin() as conn:
            try:
                conn.execute(
                    sa.text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :db AND pid <> pg_backend_pid()"
                    ),
                    {"db": test_db_name},
                )
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(exc)
            try:
                conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'))
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(exc)
        admin_eng.dispose()
        if cleanup_errors:
            # Surface (not silently swallow) any cleanup failure.
            raise BaseExceptionGroup("p1-4 PG test DB cleanup failed", cleanup_errors)


@pytest.fixture()
def pg_test_schema(pg_test_db: str) -> str:
    """Per-test: a fresh PostgreSQL SCHEMA inside the test DB.

    Pre-creates the schema BEFORE alembic runs. Returns the schema
    name. Disposes the admin engine on teardown.
    """
    schema = f"tst_{uuid.uuid4().hex[:12]}"
    admin_url_libpq = _admin_libpq_from_sa(pg_test_db)
    admin_eng = sa.create_engine(admin_url_libpq, isolation_level="AUTOCOMMIT")
    try:
        with admin_eng.begin() as conn:
            conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        yield schema
    finally:
        admin_eng.dispose()


@pytest.fixture()
def pg_engine(pg_test_db: str, pg_test_schema: str):
    """Per-test: a real SQLAlchemy engine scoped to the per-test schema.

    Disposes the engine BEFORE the DATABASE teardown so we don't
    hold open backends when ``DROP DATABASE ... WITH (FORCE)`` runs.
    """
    eng = sa.create_engine(
        pg_test_db,
        connect_args={"options": f"-c search_path={pg_test_schema}"},
    )
    try:
        yield eng
    finally:
        eng.dispose()


# ---------------------------------------------------------------------------
# Real artifact + parent chain (no probe tables, no FK disabling)
# ---------------------------------------------------------------------------


def _insert_real_export_artifact(
    conn: sa.engine.Connection,
    *,
    mime_value: str,
    locale: str = LOCALE_ZH,
    template_locale: str = LOCALE_ZH,
) -> dict[str, str]:
    """Insert the full FK chain ending in a real ``report_export_artifacts`` row.

    Uses real production FKs and NOT NULL columns as they exist in
    the live schema. NO FK disabling, NO probe tables, NO mocking.
    Returns a dict of the generated primary keys for assertion.
    """
    now = "2026-07-19 00:00:00"
    p = {
        "project_id": str(uuid.uuid4()),
        "project_version_id": str(uuid.uuid4()),
        "report_template_id": str(uuid.uuid4()),
        "report_id": str(uuid.uuid4()),
        "report_revision_id": str(uuid.uuid4()),
        "artifact_id": str(uuid.uuid4()),
    }
    conn.execute(
        sa.text(
            "INSERT INTO projects (id, code, name, location, product_category, "
            "status, current_version_number, created_at, updated_at) VALUES "
            "(:id, :code, :name, :loc, :pc, :st, :cvn, :ca, :ua)"
        ),
        {
            "id": p["project_id"],
            "code": f"P-MIG-0039-{p['project_id'][:8]}",
            "name": "MIG-0039 test project",
            "loc": "test",
            "pc": "blueberry",
            "st": "active",
            "cvn": 1,
            "ca": now,
            "ua": now,
        },
    )
    conn.execute(
        sa.text(
            "INSERT INTO project_versions (id, project_id, version_number, "
            "change_summary, status, input_snapshot, created_at, created_by) "
            "VALUES (:id, :pid, :vn, :cs, :st, :ips, :ca, :cb)"
        ),
        {
            "id": p["project_version_id"],
            "pid": p["project_id"],
            "vn": 1,
            "cs": "init",
            "st": "approved",
            "ips": "{}",
            "ca": now,
            "cb": "tester",
        },
    )
    conn.execute(
        sa.text(
            "INSERT INTO report_templates (id, template_code, report_type, "
            "format, version, schema_version, locale, manifest_json, "
            "template_content_hash, created_by) VALUES (:id, :tc, :rt, "
            ":fmt, :ver, :sv, :loc, :mj, :tch, :cb)"
        ),
        {
            "id": p["report_template_id"],
            "tc": f"TC-MIG-0039-{p['report_template_id'][:8]}",
            "rt": "feasibility",
            "fmt": "docx",
            "ver": "1.0",
            "sv": "1.0",
            "loc": locale,
            "mj": "{}",
            "tch": "h" * 64,
            "cb": "tester",
        },
    )
    conn.execute(
        sa.text(
            "INSERT INTO reports (id, project_id, project_version_id, "
            "report_type, created_by) VALUES (:id, :pid, :pvid, :rt, :cb)"
        ),
        {
            "id": p["report_id"],
            "pid": p["project_id"],
            "pvid": p["project_version_id"],
            "rt": "feasibility",
            "cb": "tester",
        },
    )
    conn.execute(
        sa.text(
            "INSERT INTO report_revisions (id, report_id, revision_number, "
            "schema_version, content_json, canonical_content_json, "
            "content_hash, quality_status, quality_findings_json, "
            "generated_by) VALUES (:id, :rid, :rn, :sv, :cj, :ccj, "
            ":ch, :qs, :qfj, :gb)"
        ),
        {
            "id": p["report_revision_id"],
            "rid": p["report_id"],
            "rn": 1,
            "sv": "1.0",
            "cj": "{}",
            "ccj": "{}",
            "ch": "h" * 64,
            "qs": "ok",
            "qfj": "[]",
            "gb": "tester",
        },
    )
    conn.execute(
        sa.text("UPDATE reports SET approved_revision_id = :ar WHERE id = :id"),
        {"ar": p["report_revision_id"], "id": p["report_id"]},
    )
    conn.execute(
        sa.text(
            "INSERT INTO report_export_artifacts (id, report_id, "
            "report_revision_id, revision_number, format, template_id, "
            "template_version, schema_version, status, file_name, "
            "mime_type, source_content_hash, render_manifest_json, "
            "generated_by, locale, template_locale) VALUES "
            "(:id, :rid, :rrid, :rn, :fmt, :tid, :tv, :sv, :st, "
            ":fn, :mt, :sch, :rmj, :gb, :loc, :tl)"
        ),
        {
            "id": p["artifact_id"],
            "rid": p["report_id"],
            "rrid": p["report_revision_id"],
            "rn": 1,
            "fmt": "docx",
            "tid": p["report_template_id"],
            "tv": "1.0",
            "sv": "1.0",
            "st": "ready",
            "fn": "report.docx",
            "mt": mime_value,
            "sch": "h" * 64,
            "rmj": "{}",
            "gb": "tester",
            "loc": locale,
            "tl": template_locale,
        },
    )
    return p


# ---------------------------------------------------------------------------
# Column-type + FK reflection helpers (live, no mock)
# ---------------------------------------------------------------------------


def _get_column_max_length(engine: sa.Engine, table: str, column: str) -> int | None:
    """Return the live ``character_maximum_length`` for a column, or None."""
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).first()
    if row is None:
        return None
    return int(row[0]) if row[0] is not None else None


def _table_exists(engine: sa.Engine, table: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = :t LIMIT 1"),
            {"t": table},
        ).first()
    return row is not None


def _alembic_version(engine: sa.Engine) -> str | None:
    with engine.connect() as conn:
        return conn.execute(sa.text(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE}")).scalar()


# ---------------------------------------------------------------------------
# Tests — real table, real Alembic, no probe tables
# ---------------------------------------------------------------------------


class TestMimeTypeMigrationPostgreSQL:
    """Real-table evidence for migration 0039 on PostgreSQL."""

    # -- alembic head + 64/255 column width -------------------------------

    def test_upgrade_head_sets_mime_type_to_varchar_255(
        self, pg_engine, pg_test_db, pg_test_schema
    ) -> None:
        """After real ``alembic upgrade head``, the production column width is 255."""
        result = _run_alembic(["upgrade", "head"], test_url=pg_test_db, schema=pg_test_schema)
        assert result.returncode == 0, (
            f"alembic upgrade head failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert _table_exists(pg_engine, TBL_ARTIFACTS)
        assert _alembic_version(pg_engine) == REVISION_HEAD
        length = _get_column_max_length(pg_engine, TBL_ARTIFACTS, COL_MIME_TYPE)
        assert length == 255, f"Expected VARCHAR(255), got {length!r}"

    def test_parent_revision_keeps_mime_type_varchar_64(
        self, pg_engine, pg_test_db, pg_test_schema
    ) -> None:
        """At parent ``0038``, the production column is ``VARCHAR(64)`` (the pre-fix defect)."""
        result = _run_alembic(
            ["upgrade", REVISION_PARENT], test_url=pg_test_db, schema=pg_test_schema
        )
        assert result.returncode == 0, f"alembic upgrade to parent failed:\n{result.stderr}"
        length = _get_column_max_length(pg_engine, TBL_ARTIFACTS, COL_MIME_TYPE)
        assert length == 64, f"Expected VARCHAR(64) at parent, got {length!r}"

    # -- real DOCX round-trip on real report_export_artifacts -------------

    def test_real_docx_mime_round_trip_on_production_table(
        self, pg_engine, pg_test_db, pg_test_schema
    ) -> None:
        """The 71-char DOCX MIME persists byte-exact on the real production column."""
        result = _run_alembic(["upgrade", "head"], test_url=pg_test_db, schema=pg_test_schema)
        assert result.returncode == 0, f"upgrade head failed:\n{result.stderr}"

        assert len(MIME_DOCX) == 71

        with pg_engine.begin() as conn:
            p = _insert_real_export_artifact(conn, mime_value=MIME_DOCX)

        with pg_engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    f"SELECT {COL_MIME_TYPE}, length({COL_MIME_TYPE}) "
                    f"FROM {TBL_ARTIFACTS} WHERE id = :id"
                ),
                {"id": p["artifact_id"]},
            ).one()
        observed_value, observed_len = row[0], row[1]
        assert observed_value == MIME_DOCX, (
            f"DOCX MIME was truncated/rewritten: expected\n  {MIME_DOCX!r}\n "
            f" got\n  {observed_value!r}"
        )
        assert observed_len == 71, (
            f"DOCX MIME length must be 71 chars post-roundtrip, got {observed_len}"
        )

    # -- real alembic downgrade fail-closed on long data -----------------

    def test_real_alembic_downgrade_fails_closed_on_long_data(
        self, pg_engine, pg_test_db, pg_test_schema
    ) -> None:
        """Real ``alembic downgrade 0038`` aborts when a real long-MIME row exists.

        Brief §6.2: real alembic upgrade → real long-MIME insert
        (committed) → real alembic downgrade. Asserts:
        - downgrade exits non-zero
        - error contains the migration's preflight message + the
          real artifact id
        - alembic version stays at 0039
        - the long row is preserved with length 71
        - the production column is still VARCHAR(255)
        """
        result = _run_alembic(["upgrade", "head"], test_url=pg_test_db, schema=pg_test_schema)
        assert result.returncode == 0, f"upgrade head failed:\n{result.stderr}"

        with pg_engine.begin() as conn:
            p = _insert_real_export_artifact(conn, mime_value=MIME_DOCX)

        downgrade = _run_alembic(
            ["downgrade", REVISION_PARENT],
            test_url=pg_test_db,
            schema=pg_test_schema,
        )
        assert downgrade.returncode != 0, (
            f"alembic downgrade should have FAILED on long data, but it returned 0.\n"
            f"stdout: {downgrade.stdout}\nstderr: {downgrade.stderr}"
        )
        err_text = downgrade.stderr + downgrade.stdout
        for needle in (
            "Cannot downgrade report_export_artifacts.mime_type",
            "longer than 64",
            p["artifact_id"],
        ):
            assert needle in err_text, (
                f"Expected error text to contain {needle!r}, got:\n{err_text}"
            )

        assert _alembic_version(pg_engine) == REVISION_HEAD, (
            "Alembic version must remain at 0039 after a failed downgrade"
        )
        length = _get_column_max_length(pg_engine, TBL_ARTIFACTS, COL_MIME_TYPE)
        assert length == 255, (
            f"Production column width must remain 255 after failed downgrade, got {length!r}"
        )
        with pg_engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    f"SELECT {COL_MIME_TYPE}, length({COL_MIME_TYPE}) "
                    f"FROM {TBL_ARTIFACTS} WHERE id = :id"
                ),
                {"id": p["artifact_id"]},
            ).one()
        assert row[0] == MIME_DOCX, (
            f"Long row value must be unchanged after failed downgrade, got {row[0]!r}"
        )
        assert row[1] == 71

    # -- real clean downgrade / re-upgrade on short-MIME only ------------

    def test_real_clean_downgrade_then_reupgrade_preserves_short_rows(
        self, pg_engine, pg_test_db, pg_test_schema
    ) -> None:
        """Real clean downgrade 0039→0038 (with short MIMEs only) + re-upgrade."""
        assert (
            _run_alembic(["upgrade", "head"], test_url=pg_test_db, schema=pg_test_schema).returncode
            == 0
        )

        with pg_engine.begin() as conn:
            p_pdf = _insert_real_export_artifact(conn, mime_value=MIME_PDF)
            p_json = _insert_real_export_artifact(conn, mime_value=MIME_JSON)

        # Clean downgrade (no long data present)
        down = _run_alembic(
            ["downgrade", REVISION_PARENT],
            test_url=pg_test_db,
            schema=pg_test_schema,
        )
        assert down.returncode == 0, (
            f"Clean downgrade failed:\nstdout: {down.stdout}\nstderr: {down.stderr}"
        )
        assert _alembic_version(pg_engine) == REVISION_PARENT
        assert _get_column_max_length(pg_engine, TBL_ARTIFACTS, COL_MIME_TYPE) == 64

        # Rows preserved across the clean downgrade
        with pg_engine.connect() as conn:
            n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {TBL_ARTIFACTS}")).scalar()
            assert n == 2, f"Expected 2 artifacts preserved, got {n}"
            for pid, expected in (
                (p_pdf["artifact_id"], MIME_PDF),
                (p_json["artifact_id"], MIME_JSON),
            ):
                v = conn.execute(
                    sa.text(f"SELECT {COL_MIME_TYPE} FROM {TBL_ARTIFACTS} WHERE id = :id"),
                    {"id": pid},
                ).scalar()
                assert v == expected, f"Row {pid} changed: got {v!r}, expected {expected!r}"

        # Re-upgrade to head
        up = _run_alembic(["upgrade", "head"], test_url=pg_test_db, schema=pg_test_schema)
        assert up.returncode == 0, f"Re-upgrade failed:\n{up.stderr}"
        assert _alembic_version(pg_engine) == REVISION_HEAD
        assert _get_column_max_length(pg_engine, TBL_ARTIFACTS, COL_MIME_TYPE) == 255
        with pg_engine.connect() as conn:
            for pid, expected in (
                (p_pdf["artifact_id"], MIME_PDF),
                (p_json["artifact_id"], MIME_JSON),
            ):
                v = conn.execute(
                    sa.text(f"SELECT {COL_MIME_TYPE} FROM {TBL_ARTIFACTS} WHERE id = :id"),
                    {"id": pid},
                ).scalar()
                assert v == expected

    # -- schema isolation: alembic_version must be in the per-test schema

    def test_alembic_version_table_lives_in_per_test_schema(
        self, pg_engine, pg_test_db, pg_test_schema
    ) -> None:
        """The alembic_version table must be in the per-test schema, NOT public."""
        assert (
            _run_alembic(["upgrade", "head"], test_url=pg_test_db, schema=pg_test_schema).returncode
            == 0
        )
        with pg_engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT n.nspname FROM pg_class c "
                    "JOIN pg_namespace n ON c.relnamespace = n.oid "
                    "WHERE c.relname = :t AND c.relkind = 'r'"
                ),
                {"t": ALEMBIC_VERSION_TABLE},
            ).one_or_none()
        assert row is not None, "alembic_version table not found"
        assert row[0] == pg_test_schema, (
            f"alembic_version must live in {pg_test_schema!r}, found in {row[0]!r}"
        )

    # -- static guard: migration file must not silently truncate

    def test_migration_text_contains_no_silent_truncation(
        self, pg_engine, pg_test_db, pg_test_schema
    ) -> None:
        """The migration file must not contain LEFT/SUBSTR silent-truncation helpers."""
        migration_path = os.path.join(
            BACKEND_DIR,
            "alembic",
            "versions",
            f"{REVISION_HEAD}.py",
        )
        with open(migration_path, encoding="utf-8") as fh:
            content = fh.read()
        forbidden = (
            "LEFT(mime_type",
            "LEFT( mime_type",
            "SUBSTR(mime_type",
            "SUBSTR( mime_type",
            ".truncate(",
            "[:64]",
            "[: 64]",
            "[0:64]",
        )
        for pattern in forbidden:
            assert pattern not in content, (
                f"Migration 0039 must not use silent truncation; "
                f"found forbidden pattern {pattern!r}"
            )

    # -- module-level marker verification (P1-2 fix)

    def test_module_level_marker_is_postgresql(self) -> None:
        """The module declares ``pytestmark = pytest.mark.postgresql`` at the top level."""
        from tests.integration import test_migration_0039_mime_type_postgresql as mod

        # pytest >= 7: ``pytestmark`` is a MarkDecorator (single marker) or
        # a list of MarkDecorators. Both expose ``.name``.
        markers = mod.pytestmark
        if not isinstance(markers, list):
            markers = [markers]
        marker_names = {m.name for m in markers}
        assert "postgresql" in marker_names, f"Expected pytest.mark.postgresql, got {marker_names}"
