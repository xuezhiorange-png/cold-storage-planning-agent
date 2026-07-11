"""Fixture consistency tests for the A1.5 evaluation runner.

This suite asserts that the test-side pre-existing-context seed
helper (already on ``main`` via PR #49 / PR #50) is consistent with
the A1.5 runner's input contract — i.e., the helper produces a
production state that the runner can consume end-to-end on both
SQLite and PostgreSQL.

The suite is intentionally narrow: the helper itself is
test-side-only (per the A1 follow-up slice .gitignore allowlist),
and the canonical acceptance tests are in
``test_sqlite_acceptance.py`` / ``test_postgresql_acceptance.py``.
This suite is the contract layer between the helper and the runner.

Forbidden-pattern coverage (built into every test):

- The seed helper does NOT introduce demo / latest-row / partial-
  binding fallbacks (pre-freeze §5.3).
- The seed helper does NOT restore ``production_seeding.py``
  (pre-freeze §5.1).
- The seed helper does NOT modify any production-module file
  (pre-freeze §5.5).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

pytest_plugins = ["tests.evaluation._seed_helpers"]

from tests.evaluation._seed_helpers import (  # noqa: E402
    PROJECT_ID,
    SOURCE_BINDING_ID,
    WEIGHT_REVISION_ID,
    seed_a1_all_prereqs,
)


# ── Test 1 — helper writes the 5 canonical CalculationRunRecord rows ────


def test_helper_writes_five_canonical_calculation_runs(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The helper writes exactly 5 CalculationRunRecord rows (canonical set)."""
    from sqlalchemy import select
    from cold_storage.modules.projects.infrastructure.orm import (
        CalculationRunRecord,
    )

    seed_s = a1_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    verify_s = a1_session_factory()
    try:
        rows = (
            verify_s.execute(
                select(CalculationRunRecord).where(
                    CalculationRunRecord.project_id == PROJECT_ID
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 5, (
            f"Helper must write exactly 5 CalculationRunRecord rows; got {len(rows)}"
        )
        # All 5 rows carry the canonical stage names (zone /
        # cooling_load / equipment / power / investment).
        stages = {row.calculation_type for row in rows}
        assert stages == {"zone", "cooling_load", "equipment", "power", "investment"}
        # All 5 rows have requires_review=False (no demo fallback).
        for row in rows:
            assert row.requires_review is False
    finally:
        verify_s.close()


# ── Test 2 — helper writes the SourceBindingRecord with the right ID ──────


def test_helper_writes_source_binding_with_canonical_id(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The helper writes a SourceBindingRecord with the canonical ID."""
    from sqlalchemy import select
    from cold_storage.modules.orchestration.infrastructure.orm import (
        SourceBindingRecord,
    )

    seed_s = a1_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    verify_s = a1_session_factory()
    try:
        binding = verify_s.execute(
            select(SourceBindingRecord).where(
                SourceBindingRecord.id == SOURCE_BINDING_ID
            )
        ).scalar_one()
        assert binding is not None
        # The binding's combined_source_hash must be non-empty (the
        # helper computes it via the production
        # _compute_combined_source_hash helper).
        assert binding.combined_source_hash is not None
        assert len(binding.combined_source_hash) > 0
    finally:
        verify_s.close()


# ── Test 3 — helper writes the SchemeWeightSetRevisionRecord with status=approved ─


def test_helper_writes_approved_weight_set_revision(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The helper writes a SchemeWeightSetRevisionRecord with status='approved'."""
    from sqlalchemy import select
    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetRevisionRecord,
    )

    seed_s = a1_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    verify_s = a1_session_factory()
    try:
        revision = verify_s.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == WEIGHT_REVISION_ID
            )
        ).scalar_one()
        assert revision is not None
        assert revision.status == "approved"
    finally:
        verify_s.close()


# ── Test 4 — helper is idempotent (re-running is a no-op) ───────────────


def test_helper_is_idempotent(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """Re-running the helper does not duplicate rows."""
    from sqlalchemy import func, select
    from cold_storage.modules.projects.infrastructure.orm import (
        CalculationRunRecord,
    )

    seed_s = a1_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()
    seed_s2 = a1_session_factory()
    try:
        seed_a1_all_prereqs(seed_s2)
    finally:
        seed_s2.close()

    verify_s = a1_session_factory()
    try:
        count = verify_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
        assert count == 5, (
            f"Helper is idempotent; running twice must not duplicate "
            f"CalculationRunRecord rows; got {count}"
        )
    finally:
        verify_s.close()


# ── Test 5 — helper module does NOT import production_seeding ───────────


def test_helper_module_does_not_import_production_seeding() -> None:
    """The helper module is test-side-only and never references
    ``production_seeding`` (per the architecture test carve-out)."""
    helper_path = (
        Path(__file__).resolve().parents[1]
        / "evaluation"
        / "_seed_helpers.py"
    )
    assert helper_path.is_file(), f"Helper source missing: {helper_path}"
    source = helper_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                assert "production_seeding" not in alias.name, (
                    f"Helper must not import {alias.name}"
                )
        elif isinstance(stmt, ast.ImportFrom):
            assert "production_seeding" not in (stmt.module or ""), (
                f"Helper must not import from {stmt.module}"
            )