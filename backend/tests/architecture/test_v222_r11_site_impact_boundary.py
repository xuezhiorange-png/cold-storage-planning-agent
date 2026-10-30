"""Keep diagnostic overlay out of production authority, routing and persistence."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "src/cold_storage/modules/layout"


def test_site_impact_domain_has_no_application_infrastructure_dependencies():
    tree = ast.parse((LAYOUT / "domain/functional_site_impact.py").read_text())
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(
        any(w in m for w in ("application", "infrastructure", "sqlalchemy", "fastapi", "ortools"))
        for m in modules
    )


def test_review_does_not_call_solver_route_search_acceptance_or_persistence():
    tree = ast.parse((LAYOUT / "application/functional_site_impact_review.py").read_text())
    names = {
        n.func.id if isinstance(n.func, ast.Name) else n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
    }
    assert not names & {
        "solve",
        "Solve",
        "approve",
        "claim",
        "commit",
        "route_site_placement",
        "validate_generated_global_proposal",
        "write_text",
        "write_bytes",
        "execute",
        "post",
    }
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(
        any(w in m for w in ("infrastructure", "bootstrap", "ortools", "requests", "sqlalchemy"))
        for m in modules
    )


def test_no_production_mcp_or_bootstrap_registration():
    src = ROOT / "src/cold_storage"
    paths = list((src / "bootstrap").rglob("*.py"))
    paths += [p for p in src.rglob("*.py") if "mcp" in p.name or "/api/" in str(p)]
    assert all("functional_site_impact_review" not in p.read_text() for p in paths)
