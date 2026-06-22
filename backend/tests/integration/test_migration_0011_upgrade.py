"""Migration 0010 → 0011 → 0012 upgrade tests.

Proves safe upgrade of databases that already contain:
- report_revisions with supersedes_revision_id values
- report_source_references and report_review_actions
- scheme_runs with scheme_candidates (no content_hash column)

Uses the actual SQL operations from migration scripts to verify
data integrity through the full 0010 → 0011 → 0012 upgrade path.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Pre-migration DDL matching 0010 state
# ---------------------------------------------------------------------------

_PRE_MIGRATION_DDL = """
CREATE TABLE projects (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    code VARCHAR(120),
    name VARCHAR(200),
    location VARCHAR(500),
    product_category VARCHAR(100),
    status VARCHAR(50),
    current_version_number INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE project_versions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    version_number INTEGER NOT NULL,
    change_summary TEXT,
    status VARCHAR(50),
    created_by VARCHAR(128),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
CREATE TABLE reports (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    report_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    current_revision_id VARCHAR(36),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
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
);
CREATE INDEX ix_report_revisions_report_id ON report_revisions (report_id);
CREATE INDEX ix_report_revisions_content_hash ON report_revisions (content_hash);
CREATE TABLE report_source_references (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    revision_id VARCHAR(36) NOT NULL,
    section_key VARCHAR(128) NOT NULL,
    field_path VARCHAR(256),
    source_type VARCHAR(64) NOT NULL,
    source_id VARCHAR(256) NOT NULL,
    FOREIGN KEY(revision_id) REFERENCES report_revisions(id)
);
CREATE TABLE report_review_actions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    revision_id VARCHAR(36) NOT NULL,
    action VARCHAR(64) NOT NULL,
    performed_by VARCHAR(128),
    performed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(revision_id) REFERENCES report_revisions(id)
);
CREATE TABLE idempotency_records (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    idempotency_key VARCHAR(256) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL,
    result_json JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
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
);
CREATE TABLE scheme_candidates (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    scheme_run_id VARCHAR(36) NOT NULL,
    scheme_code VARCHAR(120) NOT NULL,
    profile_code VARCHAR(120),
    feasible BOOLEAN DEFAULT 1,
    rank INTEGER,
    total_score NUMERIC(12,3),
    score_breakdown_snapshot JSON,
    constraint_results JSON,
    result_snapshot JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(scheme_run_id) REFERENCES scheme_runs(id),
    CONSTRAINT uq_run_scheme UNIQUE (scheme_run_id, scheme_code)
);
"""


# ---------------------------------------------------------------------------
# Migration SQL — extracted from 0011 and 0012 upgrade() functions
# ---------------------------------------------------------------------------


def _apply_0011_sqlite(conn) -> None:
    """Apply migration 0011 on SQLite (backup-copy pattern from actual migration)."""
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


def _compute_run_hash(
    run_id: str,
    recommended_scheme_code: str | None,
    generator_version: str | None,
    candidates: list[dict[str, object]],
) -> str:
    """Compute content hash matching _run_content_hash in query.py."""
    payload: dict[str, object] = {
        "run_id": run_id,
        "recommended_scheme_code": recommended_scheme_code or "",
        "generator_version": generator_version or "",
    }
    if candidates:
        payload["candidates"] = [
            {
                "id": c.get("id", ""),
                "scheme_code": c.get("scheme_code", ""),
                "total_score": c.get("total_score"),
                "rank": c.get("rank"),
            }
            for c in sorted(candidates, key=lambda x: x.get("id", ""))
        ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _apply_0012(conn) -> None:
    """Apply migration 0012: add column + backfill (from actual migration)."""
    conn.execute(text("ALTER TABLE scheme_runs ADD COLUMN content_hash VARCHAR(128)"))

    runs_result = conn.execute(
        text(
            "SELECT id, recommended_scheme_code, generator_version "
            "FROM scheme_runs WHERE status = 'completed'"
        )
    )
    for run_id, rec_code, gen_ver in runs_result.fetchall():
        cand_result = conn.execute(
            text(
                "SELECT scheme_code, total_score, rank "
                "FROM scheme_candidates WHERE scheme_run_id = :run_id"
            ),
            {"run_id": run_id},
        )
        candidates = [
            {
                "id": row[0],
                "scheme_code": row[0],
                "total_score": str(row[1]) if row[1] is not None else None,
                "rank": row[2],
            }
            for row in cand_result.fetchall()
        ]
        content_hash = _compute_run_hash(run_id, rec_code, gen_ver, candidates)
        conn.execute(
            text("UPDATE scheme_runs SET content_hash = :hash WHERE id = :run_id"),
            {"hash": content_hash, "run_id": run_id},
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pre_migration_engine():
    """SQLite engine with 0010-state schema and test data."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    conn = eng.connect()
    conn.execute(text("PRAGMA foreign_keys = OFF"))

    for stmt in _PRE_MIGRATION_DDL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(text(stmt))

    proj_id = _uid()
    ver_id = _uid()
    conn.execute(text(f"INSERT INTO projects (id, name) VALUES ('{proj_id}', 'Test')"))
    conn.execute(
        text(
            f"INSERT INTO project_versions (id, project_id, version_number) "
            f"VALUES ('{ver_id}', '{proj_id}', 1)"
        )
    )

    report_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO reports (id, project_id, report_type, status, "
            f"created_at, updated_at) "
            f"VALUES ('{report_id}', '{proj_id}', "
            f"'cold_storage_concept_design', 'generated', "
            f"CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )

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

    src_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO report_source_references "
            f"(id, revision_id, section_key, field_path, source_type, "
            f"source_id) "
            f"VALUES ('{src_id}', '{rev1_id}', 'cooling_load', "
            f"'cooling_load', 'calculation_result', 'calc-1')"
        )
    )

    act_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO report_review_actions "
            f"(id, revision_id, action, performed_by) "
            f"VALUES ('{act_id}', '{rev2_id}', 'submit_review', 'reviewer')"
        )
    )

    run_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO scheme_runs "
            f"(id, project_id, project_version_id, weight_set_id, "
            f"status, generator_version, source_snapshot_hash, "
            f"input_snapshot, assumption_snapshot, comparison_snapshot, "
            f"candidates_snapshot, recommended_scheme_code, "
            f"warning_messages) "
            f"VALUES ('{run_id}', '{proj_id}', '{ver_id}', 'ws-1', "
            f"'completed', 'gen-1.0', 'src_hash', '{{}}', '{{}}', '{{}}', "
            f"'{{}}', 'scheme-A', '{{}}')"
        )
    )

    cand_id = _uid()
    conn.execute(
        text(
            f"INSERT INTO scheme_candidates "
            f"(id, scheme_run_id, scheme_code, profile_code, feasible, "
            f"rank, total_score, score_breakdown_snapshot, "
            f"constraint_results, result_snapshot) "
            f"VALUES ('{cand_id}', '{run_id}', 'scheme-A', 'balanced', 1, "
            f"1, 85.5, '{{}}', '{{}}', '{{}}')"
        )
    )

    conn.commit()
    conn.execute(text("PRAGMA foreign_keys = ON"))

    info = {
        "project_id": proj_id,
        "version_id": ver_id,
        "report_id": report_id,
        "rev1_id": rev1_id,
        "rev2_id": rev2_id,
        "src_id": src_id,
        "act_id": act_id,
        "run_id": run_id,
        "cand_id": cand_id,
    }
    yield eng, info
    conn.close()
    eng.dispose()


# ---------------------------------------------------------------------------
# Tests — migration 0011
# ---------------------------------------------------------------------------


class TestMigration0011Upgrade:
    """Verify migration 0011 safely upgrades existing databases."""

    def test_report_revisions_data_intact_after_upgrade(self, pre_migration_engine):
        """Revisions with supersedes_revision_id survive migration 0011."""
        engine, info = pre_migration_engine

        with engine.begin() as conn:
            _apply_0011_sqlite(conn)

        with engine.connect() as conn:
            rev1 = conn.execute(
                text(
                    f"SELECT id, report_id, supersedes_revision_id "
                    f"FROM report_revisions WHERE id = '{info['rev1_id']}'"
                )
            ).fetchone()
            assert rev1 is not None
            assert rev1[2] is None

            rev2 = conn.execute(
                text(
                    f"SELECT supersedes_revision_id "
                    f"FROM report_revisions WHERE id = '{info['rev2_id']}'"
                )
            ).fetchone()
            assert rev2[0] == info["rev1_id"]

            src = conn.execute(
                text(
                    f"SELECT revision_id FROM report_source_references "
                    f"WHERE id = '{info['src_id']}'"
                )
            ).fetchone()
            assert src[0] == info["rev1_id"]

            act = conn.execute(
                text(
                    f"SELECT revision_id, action FROM report_review_actions "
                    f"WHERE id = '{info['act_id']}'"
                )
            ).fetchone()
            assert act[0] == info["rev2_id"]

    def test_new_supersedes_fk_references_report_revisions(self, pre_migration_engine):
        """After migration, supersedes_revision_id FK references report_revisions(id)."""
        engine, info = pre_migration_engine

        with engine.begin() as conn:
            _apply_0011_sqlite(conn)

        with engine.connect() as conn:
            fk_info = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='report_revisions'")
            ).fetchone()
            assert fk_info is not None
            assert "REFERENCES report_revisions(id)" in fk_info[0]


# ---------------------------------------------------------------------------
# Tests — migration 0012
# ---------------------------------------------------------------------------


class TestMigration0012Upgrade:
    """Verify migration 0012 adds content_hash and backfills."""

    def _run_full_chain(self, engine):
        """Apply 0011 then 0012 using extracted migration SQL."""
        with engine.begin() as conn:
            _apply_0011_sqlite(conn)
            _apply_0012(conn)

    def test_scheme_runs_backfilled_after_upgrade(self, pre_migration_engine):
        """Migration 0012 backfills content_hash for existing completed runs."""
        engine, info = pre_migration_engine
        self._run_full_chain(engine)

        with engine.connect() as conn:
            run = conn.execute(
                text(
                    f"SELECT id, project_id, status, recommended_scheme_code, "
                    f"content_hash "
                    f"FROM scheme_runs WHERE id = '{info['run_id']}'"
                )
            ).fetchone()
            assert run is not None
            assert run[0] == info["run_id"]
            assert run[2] == "completed"
            assert run[3] == "scheme-A"
            assert run[4] is not None, "content_hash not backfilled"
            assert len(run[4]) == 64

    def test_backfilled_hash_matches_query_computation(self, pre_migration_engine):
        """Backfilled hash matches _run_content_hash with same inputs."""
        engine, info = pre_migration_engine
        self._run_full_chain(engine)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    f"SELECT content_hash, recommended_scheme_code, "
                    f"generator_version "
                    f"FROM scheme_runs WHERE id = '{info['run_id']}'"
                )
            ).fetchone()
            stored_hash = row[0]

            cand_row = conn.execute(
                text(
                    f"SELECT scheme_code, total_score, rank "
                    f"FROM scheme_candidates "
                    f"WHERE scheme_run_id = '{info['run_id']}'"
                )
            ).fetchone()

            from cold_storage.modules.schemes.application.query import (
                _run_content_hash,
            )

            class _FakeRun:
                id = info["run_id"]
                recommended_scheme_code = row[1]
                generator_version = row[2]

            expected = _run_content_hash(
                _FakeRun(),
                [
                    {
                        "id": cand_row[0],
                        "scheme_code": cand_row[0],
                        "total_score": str(cand_row[1]),
                        "rank": cand_row[2],
                    }
                ],
            )

            assert stored_hash == expected, f"Stored {stored_hash} != computed {expected}"
