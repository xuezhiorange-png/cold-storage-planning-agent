"""R13 source calibration remains a deterministic, read-only review adapter."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "src/cold_storage/modules/layout"


def test_domain_has_no_io_application_or_native_dependencies():
    tree = ast.parse((LAYOUT / "domain/physical_room_calibration.py").read_text())
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(
        any(
            x in m
            for x in (
                "application",
                "infrastructure",
                "ortools",
                "fastapi",
                "sqlalchemy",
                "requests",
                "pathlib",
            )
        )
        for m in modules
    )


def test_application_never_approves_persists_or_solves():
    tree = ast.parse((LAYOUT / "application/physical_room_calibration_review.py").read_text())
    calls = {
        n.func.id if isinstance(n.func, ast.Name) else n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
    }
    assert not calls & {
        "solve",
        "Solve",
        "approve",
        "claim",
        "commit",
        "write_text",
        "write_bytes",
        "execute",
        "open",
        "route_site_placement",
    }
    imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(
        any(x in m for x in ("infrastructure", "bootstrap", "ortools", "sqlalchemy", "requests"))
        for m in imports
    )


def test_no_production_registration_and_review_is_existing_type_only():
    src = ROOT / "src/cold_storage"
    files = list((src / "bootstrap").rglob("*.py")) + [
        p for p in src.rglob("*.py") if "/api/" in str(p) or "mcp" in p.name
    ]
    assert all("physical_room_calibration" not in p.read_text() for p in files)
    source = (LAYOUT / "application/physical_room_calibration_review.py").read_text()
    assert "ReviewedProjectDatum" in source
    tree = ast.parse(source)
    assert not any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "ReviewedProjectDatum"
        for n in ast.walk(tree)
    )
