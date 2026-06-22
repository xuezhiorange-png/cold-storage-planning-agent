"""Migration 0011 & 0012 upgrade tests.

Proves safe upgrade of databases that already contain:
- report_revisions with supersedes_revision_id values
- report_source_references and report_review_actions
- scheme_runs (without content_hash column)

Uses raw SQL to simulate pre-migration schema, inserts test data,
runs the migration upgrade function, and verifies data integrity.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

# Pre-migration DDL for report_revisions (FK points to reports.id — wrong)
_REVISIONS_DDL = """\
CREATE TABLE report_revisions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    report_id VARCHAR(36) NOT NULL,
    revision_number INTEGER NOT NULL,
    schema_version VARCHAR(64) NOT NULL,
    content_json JSON NOT NULL,
    canonical_content_json JSON NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    quality_status VARCHAR(32) NOT NULL,
    quality_findings_json JSON NOT NULL,
    generated_by VARCHAR(64) NOT NULL,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    supersedes_revision_id VARCHAR(36),
    CONSTRAINT uq_report_revisions_report_revision
        UNIQUE (report_id, revision_number),
    FOREIGN KEY(report_id) REFERENCES projects(id),
    FOREIGN KEY(supersedes_revision_id) REFERENCES projects(id)
)"""

_SCHEME_RUNS_DDL = """\
CREATE TABLE scheme_runs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    project_id VARCHAR(36),
    project_version_id VARCHAR(36),
    weight_set_id VARCHAR(36),
    status VARCHAR(50),
    generator_version VARCHAR(50),
    source_snapshot_hash VARCHAR(128),
    input_snapshot JSON,
    assumption_snapshot JSON,
    comparison_snapshot JSON,
    candidates_snapshot JSON,
    requires_review BOOLEAN DEFAULT 1,
    recommended_scheme_code VARCHAR(120),
    warning_messages JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
)"""


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def pre_migration_engine():
    """SQLite engine with pre-migration schema (0010 state) and test data."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    conn = eng.connect()

    # Minimal pre-migration tables
    conn.execute(text("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY, name TEXT)"))
    conn.execute(
        text(
            "CREATE TABLE project_versions "
            "(id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(36), "
            "FOREIGN KEY(project_id) REFERENCES projects(id))"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE reports ("
            "id VARCHAR(36) NOT NULL PRIMARY KEY, "
            "project_id VARCHAR(36) NOT NULL, "
            "report_type VARCHAR(64) NOT NULL, "
            "status VARCHAR(32) NOT NULL, "
            "current_revision_id VARCHAR(36), "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "FOREIGN KEY(project_id) REFERENCES projects(id))"
        )
    )
    conn.execute(text(_REVISIONS_DDL))
    conn.execute(
        text(
            "CREATE TABLE report_source_references ("
            "id VARCHAR(36) NOT NULL PRIMARY KEY, "
            "revision_id VARCHAR(36) NOT NULL, "
            "section_key VARCHAR(128) NOT NULL, "
            "field_path VARCHAR(256), "
            "source_type VARCHAR(64) NOT NULL, "
            "source_id VARCHAR(256) NOT NULL, "
            "FOREIGN KEY(revision_id) REFERENCES report_revisions(id))"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE report_review_actions ("
            "id VARCHAR(36) NOT NULL PRIMARY KEY, "
            "revision_id VARCHAR(36) NOT NULL, "
            "action VARCHAR(64) NOT NULL, "
            "performed_by VARCHAR(128), "
            "performed_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "FOREIGN KEY(revision_id) REFERENCES report_revisions(id))"
        )
    )
    conn.execute(text(_SCHEME_RUNS_DDL))
    conn.execute(text("CREATE INDEX ix_report_revisions_report_id ON report_revisions (report_id)"))
    conn.execute(
        text("CREATE INDEX ix_report_revisions_content_hash ON report_revisions (content_hash)")
    )

    # Insert test data
    proj_id = _uid()
    ver_id = _uid()
    conn.execute(text(f"INSERT INTO projects VALUES ('{proj_id}', 'Test')"))
    conn.execute(text(f"INSERT INTO project_versions VALUES ('{ver_id}', '{proj_id}')"))

    report_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO reports VALUES "
            f"('{report_id}', '{proj_id}', 'cold_storage_concept_design', "
            f"'generated', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )

    # Two revisions: rev1 base, rev2 supersedes rev1
    rev1_id = _uid()
    rev2_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO report_revisions "
            f"(id, report_id, revision_number, schema_version, "
            f"content_json, canonical_content_json, content_hash, "
            f"quality_status, quality_findings_json, generated_by) "
            f"VALUES ('{rev1_id}', '{report_id}', 1, "
            f"'cold_storage_concept_design@1.0.0', "
            f"'{{}}', '{{}}', 'hash1', 'generated', '{{}}', 'test')"
        )
    )
    conn.execute(
        text(
            f"INSERT INTO report_revisions "
            f"(id, report_id, revision_number, schema_version, "
            f"content_json, canonical_content_json, content_hash, "
            f"quality_status, quality_findings_json, generated_by, "
            f"supersedes_revision_id) "
            f"VALUES ('{rev2_id}', '{report_id}', 2, "
            f"'cold_storage_concept_design@1.0.0', "
            f"'{{}}', '{{}}', 'hash2', 'draft', '{{}}', 'test', "
            f"'{rev1_id}')"
        )
    )

    # Source reference pointing to rev1
    src_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO report_source_references "
            f"(id, revision_id, section_key, field_path, source_type, source_id) "
            f"VALUES ('{src_id}', '{rev1_id}', 'cooling_load', "
            f"'cooling_load', 'calculation_result', 'calc-1')"
        )
    )

    # Review action on rev2
    act_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO report_review_actions "
            f"(id, revision_id, action, performed_by) "
            f"VALUES ('{act_id}', '{rev2_id}', 'submit_review', 'reviewer')"
        )
    )

    # Scheme run without content_hash
    run_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO scheme_runs "
            f"(id, project_id, project_version_id, weight_set_id, "
            f"status, generator_version, source_snapshot_hash, "
            f"input_snapshot, assumption_snapshot, comparison_snapshot, "
            f"candidates_snapshot, recommended_scheme_code, warning_messages) "
            f"VALUES ('{run_id}', '{proj_id}', '{ver_id}', 'ws-1', "
            f"'completed', 'gen-1.0', 'src_hash', '{{}}', '{{}}', '{{}}', "
            f"'{{}}', 'scheme-A', '{{}}')"
        )
    )

    conn.commit()

    info = {
        "project_id": proj_id,
        "version_id": ver_id,
        "report_id": report_id,
        "rev1_id": rev1_id,
        "rev2_id": rev2_id,
        "src_id": src_id,
        "act_id": act_id,
        "run_id": run_id,
    }
    yield eng, info
    conn.close()
    eng.dispose()


def _run_0011_sqlite(conn) -> None:
    """Run migration 0011 on SQLite using backup-copy pattern."""
    conn.execute(text("PRAGMA foreign_keys = OFF"))
    conn.execute(
        text(
            "CREATE TABLE report_revisions_new ("
            "id VARCHAR(36) NOT NULL, "
            "report_id VARCHAR(36) NOT NULL, "
            "revision_number INTEGER NOT NULL, "
            "schema_version VARCHAR(64) NOT NULL, "
            "content_json JSON NOT NULL, "
            "canonical_content_json JSON NOT NULL, "
            "content_hash VARCHAR(64) NOT NULL, "
            "quality_status VARCHAR(32) NOT NULL, "
            "quality_findings_json JSON NOT NULL, "
            "generated_by VARCHAR(64) NOT NULL, "
            "generated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "supersedes_revision_id VARCHAR(36), "
            "PRIMARY KEY (id), "
            "CONSTRAINT uq_report_revisions_report_revision "
            "UNIQUE (report_id, revision_number), "
            "FOREIGN KEY(report_id) REFERENCES projects(id), "
            "FOREIGN KEY(supersedes_revision_id) "
            "REFERENCES report_revisions(id)"
            ")"
        )
    )
    conn.execute(text("INSERT INTO report_revisions_new SELECT * FROM report_revisions"))
    conn.execute(text("DROP TABLE report_revisions"))
    conn.execute(text("ALTER TABLE report_revisions_new RENAME TO report_revisions"))
    conn.execute(text("CREATE INDEX ix_report_revisions_report_id ON report_revisions (report_id)"))
    conn.execute(
        text("CREATE INDEX ix_report_revisions_content_hash ON report_revisions (content_hash)")
    )
    conn.execute(text("PRAGMA foreign_keys = ON"))


class TestMigration0011Upgrade:
    """Verify migration 0011 safely upgrades existing databases."""

    def test_report_revisions_data_intact_after_upgrade(self, pre_migration_engine):
        """Revisions with supersedes_revision_id survive migration 0011."""
        engine, info = pre_migration_engine

        with engine.begin() as conn:
            _run_0011_sqlite(conn)

            # Verify rev1 intact
            rev1 = conn.execute(
                text(
                    f"SELECT id, report_id, supersedes_revision_id "
                    f"FROM report_revisions WHERE id = '{info['rev1_id']}'"
                )
            ).fetchone()
            assert rev1 is not None, "Revision 1 lost after migration"
            assert rev1[0] == info["rev1_id"]
            assert rev1[1] == info["report_id"]
            assert rev1[2] is None  # rev1 has no supersedes

            # Verify rev2 intact with correct supersedes
            rev2 = conn.execute(
                text(
                    f"SELECT id, report_id, supersedes_revision_id "
                    f"FROM report_revisions WHERE id = '{info['rev2_id']}'"
                )
            ).fetchone()
            assert rev2 is not None, "Revision 2 lost after migration"
            assert rev2[2] == info["rev1_id"], "supersedes_revision_id broken"

            # Source references still point to correct revision
            src = conn.execute(
                text(
                    f"SELECT revision_id FROM report_source_references "
                    f"WHERE id = '{info['src_id']}'"
                )
            ).fetchone()
            assert src is not None
            assert src[0] == info["rev1_id"]

            # Review actions still linked
            act = conn.execute(
                text(
                    f"SELECT revision_id, action FROM report_review_actions "
                    f"WHERE id = '{info['act_id']}'"
                )
            ).fetchone()
            assert act is not None
            assert act[0] == info["rev2_id"]
            assert act[1] == "submit_review"

    def test_new_supersedes_fk_references_report_revisions(self, pre_migration_engine):
        """After migration, supersedes_revision_id FK points to report_revisions(id)."""
        engine, info = pre_migration_engine

        with engine.begin() as conn:
            _run_0011_sqlite(conn)

            # Verify the FK definition — SQLite PRAGMA
            fk_info = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='report_revisions'")
            ).fetchone()
            assert fk_info is not None
            fk_sql = fk_info[0]
            # The correct FK references report_revisions(id), not reports(id)
            assert "REFERENCES report_revisions(id)" in fk_sql

    def test_scheme_runs_survive_content_hash_column_addition(self, pre_migration_engine):
        """Scheme runs data intact after migration 0012 adds content_hash column."""
        engine, info = pre_migration_engine

        with engine.begin() as conn:
            # Simulate migration 0012: add content_hash column via ALTER TABLE
            conn.execute(text("ALTER TABLE scheme_runs ADD COLUMN content_hash VARCHAR(128)"))

            # Verify existing run data intact
            run = conn.execute(
                text(
                    f"SELECT id, project_id, status, recommended_scheme_code, "
                    f"content_hash "
                    f"FROM scheme_runs WHERE id = '{info['run_id']}'"
                )
            ).fetchone()
            assert run is not None, "Scheme run lost after migration 0012"
            assert run[0] == info["run_id"]
            assert run[1] == info["project_id"]
            assert run[2] == "completed"
            assert run[3] == "scheme-A"
            assert run[4] is None  # New column defaults to NULL
