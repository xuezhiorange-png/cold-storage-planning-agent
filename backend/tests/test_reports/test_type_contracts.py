"""AST-based type contract tests for the reports module (P0-9).

Scans production source files to enforce:
- No ``type: ignore`` comments in production code
- No bare ``Any`` in function parameter annotations (with exceptions)
"""
from __future__ import annotations

import ast
import pathlib

REPORTS_DIR = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "cold_storage"
    / "modules"
    / "reports"
)

PRODUCTION_FILES = [
    "application/render_service.py",
    "application/render_model_builder.py",
    "application/service.py",
    "api/routes.py",
    "infrastructure/repository.py",
    "infrastructure/template_seed.py",
    "domain/render_model.py",
    "domain/models.py",
    "domain/errors.py",
]

# Allowed exceptions: (file, function_name) pairs where bare Any is acceptable
ALLOWED_ANY_LOCATIONS: set[tuple[str, str]] = {
    # ORM JSON columns legitimately need Any
    ("infrastructure/orm.py", "_json_column"),
    # pydantic model_dump returns dict[str, Any]
    ("domain/render_model.py", "TemplateManifest"),
    # Dynamic JSON content — these helpers accept any JSON value
    ("application/render_model_builder.py", "_is_measured_value"),
    ("application/render_model_builder.py", "_build_citations_and_approval"),
    ("application/service.py", "_parse_dt"),
    ("application/service.py", "complete_idempotency_record"),
    ("infrastructure/repository.py", "_parse_dt"),
    ("infrastructure/repository.py", "complete_idempotency_record"),
    ("domain/render_model.py", "format_number"),
}

ALLOWED_TYPE_IGNORE: dict[str, str] = {
    # SQLAlchemy session.execute() returns Result, not CursorResult — rowcount attr
    "infrastructure/repository.py": "attr-defined",
}


def test_no_type_ignore_in_production() -> None:
    """No 'type: ignore' comments should appear in production files."""
    for fname in PRODUCTION_FILES:
        path = REPORTS_DIR / fname
        if not path.exists():
            continue
        source = path.read_text()
        if "type: ignore" in source:
            allowed_code = ALLOWED_TYPE_IGNORE.get(fname, "")
            # Check each type: ignore occurrence
            for i, line in enumerate(source.split("\n"), 1):
                if "type: ignore" in line:
                    if allowed_code and f"[{allowed_code}]" in line:
                        continue  # Allowed
                    assert False, f"Found 'type: ignore' in {fname}:{i}: {line.strip()}"


def test_no_bare_any_in_function_signatures() -> None:
    """Function parameters should not use bare ``Any`` type annotation."""
    for fname in PRODUCTION_FILES:
        path = REPORTS_DIR / fname
        if not path.exists():
            continue
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args:
                    if isinstance(arg.annotation, ast.Name) and arg.annotation.id == "Any":
                        loc = (fname, node.name)
                        if loc not in ALLOWED_ANY_LOCATIONS:
                            # Skip 'self' parameter
                            if arg.arg != "self":
                                assert False, (
                                    f"Bare Any in {fname}:{node.name}({arg.arg})"
                                )


def test_type_aliases_exist() -> None:
    """render_model.py should define JsonValue and JsonObject type aliases."""
    render_model_path = REPORTS_DIR / "domain" / "render_model.py"
    assert render_model_path.exists()
    source = render_model_path.read_text()
    assert "JsonValue" in source, "JsonValue type alias not found in render_model.py"
    assert "JsonObject" in source, "JsonObject type alias not found in render_model.py"
