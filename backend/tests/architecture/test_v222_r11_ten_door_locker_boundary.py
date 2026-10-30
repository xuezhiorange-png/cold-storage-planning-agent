"""R14 remains a read-only adapter, never a production solver or Authority."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "src/cold_storage/modules/layout"


def test_new_domain_adapter_has_no_io_database_native_or_application_dependency():
    for p in (LAYOUT / "domain").glob("ten_door_locker*.py"):
        tree = ast.parse(p.read_text())
        names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any(
            any(
                x in m
                for x in (
                    "application",
                    "infrastructure",
                    "ortools",
                    "sqlalchemy",
                    "requests",
                    "pathlib",
                    "subprocess",
                    "fastapi",
                )
            )
            for m in names
        )


def test_application_is_read_only_and_uses_existing_project_datum():
    tree = ast.parse((LAYOUT / "application/ten_door_locker_review.py").read_text())
    calls = {
        n.func.id if isinstance(n.func, ast.Name) else n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
    }
    assert "ReviewedProjectDatum" in calls
    assert not calls & {
        "open",
        "write_text",
        "write_bytes",
        "approve",
        "claim",
        "solve",
        "Solve",
        "execute",
        "commit",
    }
    names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(
        any(x in m for x in ("infrastructure", "bootstrap", "ortools", "sqlalchemy")) for m in names
    )


def test_new_adapter_is_not_registered_in_production_or_mcp():
    src = ROOT / "src/cold_storage"
    files = [
        *(src / "bootstrap").rglob("*.py"),
        *[p for p in src.rglob("*.py") if "/api/" in str(p) or "mcp" in p.name],
    ]
    assert all("ten_door_locker" not in p.read_text() for p in files)
