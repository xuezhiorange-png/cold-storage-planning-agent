"""The new advisory module has no production execution or persistence route."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "src/cold_storage/modules/layout"


def test_advisory_domain_has_no_application_infrastructure_or_io_dependencies():
    path = MODULE / "domain/functional_sizing_advisory.py"
    tree = ast.parse(path.read_text())
    imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(
        any(
            v in name for v in [".application", ".infrastructure", "sqlalchemy", "fastapi", "redis"]
        )
        for name in imports
    )


def test_application_precheck_has_no_execution_network_or_persistence_calls():
    for name in ["functional_sizing_handoff.py", "functional_sizing_sources.py"]:
        tree = ast.parse((MODULE / "application" / name).read_text())
        calls = [
            n.func.attr
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        ]
        assert not set(calls) & {
            "solve",
            "Solve",
            "approve",
            "commit",
            "execute",
            "write_text",
            "write_bytes",
            "mkdir",
            "unlink",
            "send",
            "post",
        }
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(
            any(
                v in module
                for v in ["bootstrap", "database", "sqlalchemy", "httpx", "requests", "urllib"]
            )
            for module in imports
        )


def test_no_production_bootstrap_api_or_mcp_registration():
    src = ROOT / "src/cold_storage"
    paths = list((src / "bootstrap").rglob("*.py"))
    paths += [p for p in src.rglob("*.py") if "mcp" in p.name or "/api/" in str(p)]
    for p in paths:
        assert "functional_sizing_handoff" not in p.read_text(), str(p)


def test_source_reader_only_reads_known_paths():
    tree = ast.parse((MODULE / "infrastructure/functional_sizing_evidence.py").read_text())
    methods = {
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "read_bytes" in methods and "is_relative_to" in methods
    assert not methods & {"write_text", "write_bytes", "mkdir", "unlink", "open", "approve"}
