"""P0-3 hex validation tests for the downgrade guard.

The migration 0034 downgrade guard calls ``_is_hex64`` on
production SchemeRun archive_hash values to verify a row's identity
before allowing the downgrade to proceed.  The previous
implementation used ``int(value, 16)`` which silently accepted
uppercase A-F.  P0-3 mandates strict lowercase 64-char hex.

These tests exercise the guard's hex validation across the 4
user-stated cases:

  1. uppercase 64 hex is REJECTED
  2. lowercase 64 hex is ALLOWED
  3. non-hex char (e.g. 'g') is REJECTED
  4. length != 64 (e.g. 63 or 65) is REJECTED

The exercise strategy: subprocess-isolated alembic upgrade/downgrade,
planting a row in the production_source_archives table with the
test's archive_hash value.  Each test has its own fresh DB so the
plumbing state is clean.

This file is SQLite-tagged (pytest.mark.sqlite).  A parallel
PostgreSQL version lives in
tests/integration/test_migration_0034_downgrade_guard_hex_postgresql.py
(test_migration_0034_downgrade_guard_hex_postgresql.py).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.sqlite


HEX_PATTERN_DOC = (
    "Exact 64 lowercase hex chars; uppercase, non-hex, or wrong-length values must be rejected."
)

_LOWER = "0123456789abcdef"
_UPPER = "0123456789ABCDEF"


def _run_alembic(db_path: str) -> None:
    """Run ``alembic upgrade head`` against db_path."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["SQLITE_PATH"] = db_path
    env["DATABASE_BACKEND"] = "sqlite"
    env.setdefault("COLD_STORAGE_TESTING", "1")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            "head",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(backend_dir),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade failed (exit={result.returncode}):\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )


def _write_archive_row_directly(
    conn: sqlite3.Connection,
    archive_hash: str,
) -> None:
    """Insert a synthetic production_source_archives row bypassing
    SQL CHECK on archive_hash via PRAGMA, so we can simulate legacy /
    buggy rows that the downgrade guard must catch.

    This stands in for a historically-written-but-now-invalid row.
    """
    cur = conn.cursor()
    # Disable CHECK so the SQL CHECK on archive_hash shape does
    # NOT reject the value before the Python guard has a chance
    # to test it.  This mirrors the "ignore_check_constraints"
    # pattern in test_unsupported_schema_version_raises.
    cur.execute("PRAGMA ignore_check_constraints=1")
    cur.execute(
        "INSERT INTO production_source_archives "
        "(id, scheme_run_id, source_binding_id, source_contract_version, "
        "archive_schema_version, archive_payload, archive_hash, "
        "combined_source_hash, weight_set_revision_id, "
        "weight_set_content_hash, binding_schema_version, "
        "execution_snapshot_id, coefficient_context_id, "
        "orchestration_identity_id, authoritative_attempt_id, "
        "orchestration_fingerprint, created_at, created_by, reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "archive-hex-test-001",
            "scheme-hex-test-001",
            "binding-hex-test-001",
            "SVC-1.0",
            "SchemeSourceArchiveV1",
            '{"schema":"SchemeSourceArchiveV1"}',
            archive_hash,
            "combined-hex-test",
            "rev-hex-test",
            "weight-hex-test",
            "BSV-1.0",
            "snap-hex-test",
            "ctx-hex-test",
            "ident-hex-test",
            "att-hex-test",
            "fp-hex-test",
            "2026-07-04 00:00:00.000",
            "seed",
            "completed",
        ),
    )
    conn.commit()
    cur.execute("PRAGMA ignore_check_constraints=0")


# Must import after pytestmark; noqa tacked onto the import line itself.
from tests.integration.test_migration_0034_downgrade_guard_sqlite import (  # noqa: E402
    _downgrade_one,
    _insert_full_chain,
    _insert_production_scheme_run,
    _upgrade_to_head,
)


def _seed_production_chain(db_path: str) -> str:
    """Build minimal production chain + plant a scheme_run.

    Returns the SchemeRun id.
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        ids = _insert_full_chain(cur)
        sid = _insert_production_scheme_run(
            conn,
            ids["pid"],
            ids["pvid"],
            source_binding_id=ids["src_bid"],
            combined_source_hash="combined-hex-test",
        )
        conn.commit()
    finally:
        conn.close()
    return sid


def _attempt_downgrade(db_path: str) -> subprocess.CompletedProcess:
    """Run ``alembic downgrade 0033_extend_outbox_envelope``."""
    return _downgrade_one(Path(db_path), "0033_extend_outbox_envelope")


def _fresh_db_with_archive(archive_hash: str) -> tuple[str, Path]:
    """Build a fresh SQLite DB to head, plant a production SchemeRun
    with the supplied archive_hash, and return (db_path, db_path_obj).
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    tmp.close()
    db_path = tmp.name
    _upgrade_to_head(Path(db_path))
    sid = _seed_production_chain(db_path)
    conn = sqlite3.connect(db_path)
    try:
        # Update the synthetic archive's scheme_run_id to match the
        # actually-inserted SchemeRun id from _insert_production_scheme_run.
        cur = conn.cursor()
        cur.execute(
            "UPDATE production_source_archives SET scheme_run_id = ?",
            (sid,),
        )
        conn.commit()
        # Re-plant the archive row using the supplied archive_hash.
        cur.execute("DELETE FROM production_source_archives")
        conn.commit()
    finally:
        conn.close()
    # Re-open and plant only the archive row.
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA ignore_check_constraints=1")
        cur.execute(
            "INSERT INTO production_source_archives "
            "(id, scheme_run_id, source_binding_id, source_contract_version, "
            "archive_schema_version, archive_payload, archive_hash, "
            "combined_source_hash, weight_set_revision_id, "
            "weight_set_content_hash, binding_schema_version, "
            "execution_snapshot_id, coefficient_context_id, "
            "orchestration_identity_id, authoritative_attempt_id, "
            "orchestration_fingerprint, created_at, created_by, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"archive-hex-test-{archive_hash[:6]}",
                sid,
                "binding-hex-test-001",
                "SVC-1.0",
                "SchemeSourceArchiveV1",
                '{"schema":"SchemeSourceArchiveV1"}',
                archive_hash,
                "combined-hex-test",
                "rev-hex-test",
                "weight-hex-test",
                "BSV-1.0",
                "snap-hex-test",
                "ctx-hex-test",
                "ident-hex-test",
                "att-hex-test",
                "fp-hex-test",
                "2026-07-04 00:00:00.000",
                "seed",
                "completed",
            ),
        )
        conn.commit()
        cur.execute("PRAGMA ignore_check_constraints=0")
    finally:
        conn.close()
    return db_path, Path(db_path)


# ── Acceptance: lowercase 64-char hex is ALLOWED ─────────────────────────


class TestHexStrictLowercase:
    """Strict lowercase hex contract."""

    def test_lowercase_64_hex_allows_downgrade(self) -> None:
        """Lowercase 64 hex ``{'0'..'9','a'..'f'}*64`` is allowed."""
        archive_hash = "a" * 64  # valid 64-char lowercase hex
        db_path, db_obj = _fresh_db_with_archive(archive_hash)

        r = _attempt_downgrade(db_path)

        try:
            assert r.returncode == 0, (
                f"downgrade should be allowed for lowercase 64 hex; "
                f"got exit={r.returncode} stderr={r.stderr!r}"
            )

            conn = sqlite3.connect(db_path)
            try:
                rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                assert rev == "0033_extend_outbox_envelope", f"version not rolled back: got {rev!r}"
            finally:
                conn.close()
        finally:
            db_obj.unlink(missing_ok=True)

    def test_uppercase_64_hex_blocks_downgrade(self) -> None:
        """Uppercase 64 hex MUST be REJECTED by the guard.

        A-F in the input MUST trigger the guard's "downgrade
        blocked" RuntimeError; a stale uppercase row in production
        would otherwise slip past the lenient ``int(value, 16)``
        check.
        """
        archive_hash = "A" * 64  # 64-char uppercase hex
        db_path, db_obj = _fresh_db_with_archive(archive_hash)

        r = _attempt_downgrade(db_path)

        try:
            assert r.returncode != 0, (
                "downgrade should be BLOCKED for uppercase 64 hex; "
                "the lenient int(x, 16) check previously let this slip"
            )
            assert "downgrade blocked" in r.stderr or "downgrade blocked" in r.stdout, (
                f"missing blocker message:\nstderr={r.stderr!r}\nstdout={r.stdout!r}"
            )

            # Verify the table is intact (downgrade did not drop it).
            conn = sqlite3.connect(db_path)
            try:
                exists = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE "
                    "type='table' AND name='production_source_archives'"
                ).fetchone()[0]
                assert exists == 1, (
                    "production_source_archives table missing after blocked downgrade"
                )
            finally:
                conn.close()
        finally:
            db_obj.unlink(missing_ok=True)

    def test_non_hex_char_blocks_downgrade(self) -> None:
        """Non-hex char (e.g. 'g') MUST trigger the guard."""
        # 'g' is NOT in [0-9a-fA-F] — the new strict set is
        # [0-9a-f].
        archive_hash = "g" + "a" * 63
        assert len(archive_hash) == 64
        db_path, db_obj = _fresh_db_with_archive(archive_hash)

        r = _attempt_downgrade(db_path)

        try:
            assert r.returncode != 0, (
                "downgrade should be BLOCKED for non-hex char in position 0 (char 'g')"
            )
            assert "downgrade blocked" in r.stderr or "downgrade blocked" in r.stdout, (
                f"missing blocker message:\nstderr={r.stderr!r}\nstdout={r.stdout!r}"
            )
        finally:
            db_obj.unlink(missing_ok=True)

    def test_length_63_blocks_downgrade(self) -> None:
        """Length 63 MUST trigger the guard."""
        archive_hash = "a" * 63  # one short
        db_path, db_obj = _fresh_db_with_archive(archive_hash)

        r = _attempt_downgrade(db_path)

        try:
            assert r.returncode != 0, "downgrade should be BLOCKED for length=63"
            assert "downgrade blocked" in r.stderr or "downgrade blocked" in r.stdout, (
                f"missing blocker message:\nstderr={r.stderr!r}"
            )
        finally:
            db_obj.unlink(missing_ok=True)

    def test_length_65_blocks_downgrade(self) -> None:
        """Length 65 MUST trigger the guard."""
        archive_hash = "a" * 65  # one long
        db_path, db_obj = _fresh_db_with_archive(archive_hash)

        r = _attempt_downgrade(db_path)

        try:
            assert r.returncode != 0, "downgrade should be BLOCKED for length=65"
            assert "downgrade blocked" in r.stderr or "downgrade blocked" in r.stdout, (
                f"missing blocker message:\nstderr={r.stderr!r}"
            )
        finally:
            db_obj.unlink(missing_ok=True)

    def test_mixed_case_blocks_downgrade(self) -> None:
        """Mixed-case (uppercase A-F mixed with lowercase) MUST trigger
        the guard.  Mixes are not allowed.
        """
        archive_hash = "a" * 30 + "A" * 4 + "a" * 30  # 64 chars, mixed
        assert len(archive_hash) == 64
        assert "A" in archive_hash
        db_path, db_obj = _fresh_db_with_archive(archive_hash)

        r = _attempt_downgrade(db_path)

        try:
            assert r.returncode != 0, (
                "downgrade should be BLOCKED for mixed-case (lenient int(x, 16) would accept this)"
            )
            assert "downgrade blocked" in r.stderr or "downgrade blocked" in r.stdout, (
                f"missing blocker message:\nstderr={r.stderr!r}"
            )
        finally:
            db_obj.unlink(missing_ok=True)

    def test_pure_zero_string_of_correct_length_allows_downgrade(self) -> None:
        """``'0' * 64`` is a valid lowercase 64-char hex string."""
        archive_hash = "0" * 64
        db_path, db_obj = _fresh_db_with_archive(archive_hash)

        r = _attempt_downgrade(db_path)

        try:
            assert r.returncode == 0, (
                f"downgrade should be allowed for '0'*64; "
                f"got exit={r.returncode} stderr={r.stderr!r}"
            )
        finally:
            db_obj.unlink(missing_ok=True)
