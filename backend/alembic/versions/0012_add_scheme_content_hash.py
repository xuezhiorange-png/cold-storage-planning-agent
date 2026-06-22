"""0012_add_scheme_content_hash

Adds content_hash column to scheme_runs for persisted provenance
and backfills all existing completed runs.

Previously the hash was only computed at query time, which could not
detect database-level tampering of scheme run data.

Revision ID: 0012_add_scheme_content_hash
Revises: 0011_fix_supersedes_fk
Create Date: 2026-06-22
"""

from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa

from alembic import op

revision = "0012_add_scheme_content_hash"
down_revision = "0011_fix_supersedes_fk"
branch_labels = None
depends_on = None


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


def upgrade() -> None:
    op.add_column(
        "scheme_runs",
        sa.Column("content_hash", sa.String(128), nullable=True),
    )

    # Backfill content_hash for all existing completed runs
    conn = op.get_bind()

    runs_result = conn.execute(
        sa.text(
            "SELECT id, recommended_scheme_code, generator_version "
            "FROM scheme_runs WHERE status = 'completed'"
        )
    )
    runs = runs_result.fetchall()

    for run_id, rec_code, gen_ver in runs:
        # Load candidates for this run
        cand_result = conn.execute(
            sa.text(
                "SELECT id, scheme_code, total_score, rank "
                "FROM scheme_candidates WHERE scheme_run_id = :run_id"
            ),
            {"run_id": run_id},
        )
        candidate_rows = cand_result.fetchall()
        candidates = [
            {
                # Use scheme_code as id for consistency with service.py
                "id": row[1],
                "scheme_code": row[1],
                "total_score": str(row[2]) if row[2] is not None else None,
                "rank": row[3],
            }
            for row in candidate_rows
        ]

        content_hash = _compute_run_hash(run_id, rec_code, gen_ver, candidates)
        conn.execute(
            sa.text("UPDATE scheme_runs SET content_hash = :hash WHERE id = :run_id"),
            {"hash": content_hash, "run_id": run_id},
        )


def downgrade() -> None:
    op.drop_column("scheme_runs", "content_hash")
