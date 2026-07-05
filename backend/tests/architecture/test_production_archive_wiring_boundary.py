"""Architecture boundary test: production archive wiring is centralized.

Verifies the round-9 invariant that ``SqlAlchemyProductionSchemeRunRepository``
can only be constructed **with** a ``build_archive_callable=`` argument
in the production code path.  The only authorized constructors are:

* ``bootstrap/production_composition.py`` — the single canonical
  composition entry point, which always passes a closure created by
  ``orchestration.infrastructure.archive_composition.make_production_archive_callable()``.
* ``orchestration/infrastructure/archive_composition.py`` — defines
  ``make_production_archive_callable`` but never constructs the
  repository itself, so it is excluded from the scan.

A repository constructed without ``build_archive_callable=`` bypasses
the production archive INSERT silently.  That regression would split
the production-mode ``scheme_runs`` row from the
``production_source_archives`` row, breaking the round-3 (P0-2) atomic
contract.

Detection
=========

We scan every Python file under ``backend/src/cold_storage/`` (the
production code tree) for source lines matching::

    SqlAlchemyProductionSchemeRunRepository(...)

A match is reported when the construction call does not pass the
``build_archive_callable=`` keyword argument.  We use a small AST
visitor because regex-on-source misses the difference between
positional and keyword arguments and cannot recover when the
constructor spans multiple lines.

Authorization
=============

The allow-list is intentionally narrow:

* ``cold_storage/bootstrap/production_composition.py`` — production
  composition root.  Construction here MUST pass the closure.

The deny-list (test files) is excluded from the scan entirely.

If a future change introduces a new production constructor for
``SqlAlchemyProductionSchemeRunRepository`` without
``build_archive_callable=`` (or that bypasses the composition root),
this test fails.  That is the intended behaviour.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"
PROD_TREE = BACKEND_SRC

# The single allowed production constructor.
ALLOWED_PRODUCTION_CONSTRUCTOR = BACKEND_SRC / "bootstrap" / "production_composition.py"

# Authoritative keyword that proves the archive wiring is in place.
ARCHIVE_CALLABLE_KW = "build_archive_callable"


def _iter_python_files(root: Path) -> list[Path]:
    """Return every ``.py`` file under *root*, excluding ``__pycache__``."""
    files: list[Path] = []
    for path in root.rglob("*.py"):
        parts = path.parts
        if any(part == "__pycache__" for part in parts):
            continue
        files.append(path)
    return files


def _find_repo_constructions(filepath: Path) -> list[tuple[int, str]]:
    """Return ``(line, call_repr)`` for every production repository construction.

    Only Call nodes whose function name is
    ``SqlAlchemyProductionSchemeRunRepository`` are reported.  Multi-line
    constructor calls are reported with their first-line number.
    """
    try:
        source = filepath.read_text()
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []
    results: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name):
            continue
        if func.id != "SqlAlchemyProductionSchemeRunRepository":
            continue
        # Inspect kwargs: report all such calls; the test below decides
        # whether each call passes build_archive_callable.
        kwargs = {kw.arg for kw in node.keywords if kw.arg is not None}
        if ARCHIVE_CALLABLE_KW in kwargs:
            continue  # compliant
        # Build a short call preview from line start to end of args.
        line = node.lineno
        end_line = getattr(node, "end_lineno", line) or line
        source_lines = source.splitlines()[line - 1 : end_line]
        preview = "\n".join(source_lines)
        results.append((line, preview.strip()[:200]))
    return results


class TestProductionArchiveWiringBoundary:
    """Every production repository call must wire the archive closure.

    Production ``SqlAlchemyProductionSchemeRunRepository(...)``
    calls (anywhere in the production tree) MUST pass the keyword
    argument ``build_archive_callable=``; otherwise they silently
    bypass the archive INSERT and regress the round-3 P0-2 atomic
    contract.
    """

    def test_production_constructors_pass_archive_callable(self) -> None:
        """Scan the production tree for naked constructor calls.

        For every production constructor of
        ``SqlAlchemyProductionSchemeRunRepository`` we require the
        keyword argument ``build_archive_callable=``.  Anything else
        bypasses the archive INSERT and regresses the production
        archive contract from round 3 (P0-2).
        """
        violations: list[str] = []
        for filepath in _iter_python_files(PROD_TREE):
            if filepath == ALLOWED_PRODUCTION_CONSTRUCTOR:
                continue
            for line, call_preview in _find_repo_constructions(filepath):
                relative = filepath.relative_to(BACKEND_SRC)
                violations.append(
                    f"  {relative}:{line}  construction has no "
                    f"{ARCHIVE_CALLABLE_KW} keyword:\n    {call_preview}"
                )

        assert not violations, (
            "Production code constructs SqlAlchemyProductionSchemeRunRepository "
            f"without {ARCHIVE_CALLABLE_KW}=; archive wiring is silently "
            "bypassed.  Route the construction through "
            "bootstrap.production_composition.compose_production_scheme_service.\n"
            + "\n".join(violations)
        )

    def test_bootstrap_composition_is_the_only_production_constructor(self) -> None:
        """Sanity check: the composition root is the canonical constructor."""
        assert ALLOWED_PRODUCTION_CONSTRUCTOR.exists(), (
            f"{ALLOWED_PRODUCTION_CONSTRUCTOR} must exist as the sole production-mode constructor."
        )
        # The composition root must itself wire the closure.
        constructors = _find_repo_constructions(ALLOWED_PRODUCTION_CONSTRUCTOR)
        assert constructors == [], (
            "bootstrap.production_composition must construct the repository via "
            f"a {ARCHIVE_CALLABLE_KW}= keyword; found naked construction."
        )
