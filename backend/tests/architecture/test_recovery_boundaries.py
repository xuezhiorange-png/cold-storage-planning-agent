from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RECOVERY_ROOT = PROJECT_ROOT / "backend" / "src" / "cold_storage" / "recovery"


def _source(name: str) -> str:
    return (RECOVERY_ROOT / name).read_text(encoding="utf-8")


def test_recovery_package_exists_with_operator_surfaces() -> None:
    assert (RECOVERY_ROOT / "backup_bundle.py").is_file()
    assert (RECOVERY_ROOT / "restore_runner.py").is_file()
    assert (RECOVERY_ROOT / "verification.py").is_file()
    assert (RECOVERY_ROOT / "cli.py").is_file()
    cli = _source("cli.py")
    assert '"backup"' in cli
    assert '"restore-isolated"' in cli
    assert '"verify-restore"' in cli


def test_recovery_core_has_no_web_or_release_boundary_dependency() -> None:
    for path in RECOVERY_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [
            node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        names = []
        for node in imports:
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            else:
                names.append(node.module or "")
        assert not any(
            name.startswith(("fastapi", "uvicorn", "cold_storage.release")) for name in names
        )


def test_recovery_subprocess_boundary_is_explicit_and_non_shell() -> None:
    source = "\n".join(_source(name) for name in ("backup_bundle.py", "restore_runner.py"))
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "shell=False" in source
    assert "pg_dump" in source
    assert "pg_restore" in source


def test_recovery_does_not_upload_or_deploy() -> None:
    source = "\n".join(
        _source(name) for name in ("backup_bundle.py", "restore_runner.py", "cli.py")
    )
    for forbidden in ("upload-artifact", "github.token", "docker push", "cosign", "promotion"):
        assert forbidden not in source
