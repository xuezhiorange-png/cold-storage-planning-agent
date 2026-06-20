from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"


def read_python_files(path: Path) -> list[Path]:
    return [item for item in path.rglob("*.py") if "__pycache__" not in item.parts]


def test_domain_has_no_framework_dependencies() -> None:
    forbidden = ("fastapi", "sqlalchemy", "redis", "openai")
    domain_files = [path for path in read_python_files(BACKEND_SRC) if "domain" in path.parts]

    assert domain_files
    for path in domain_files:
        content = path.read_text()
        has_forbidden_import = any(
            f"import {name}" in content or f"from {name}" in content for name in forbidden
        )
        assert not has_forbidden_import, path


def test_calculations_are_pure() -> None:
    forbidden = ("sqlalchemy", "redis", "requests", "httpx", "os.environ", "openai")
    calc_files = read_python_files(BACKEND_SRC / "modules" / "calculations")

    assert calc_files
    for path in calc_files:
        content = path.read_text()
        assert not any(term in content for term in forbidden), path


def test_agent_has_no_database_dependency() -> None:
    agent_files = read_python_files(BACKEND_SRC / "modules" / "planning_agent")

    assert agent_files
    for path in agent_files:
        content = path.read_text()
        assert "sqlalchemy" not in content
        assert "Session" not in content


def test_no_global_dumping_ground_modules() -> None:
    forbidden_names = {
        "utils.py",
        "helpers.py",
        "misc.py",
        "managers.py",
        "common_service.py",
        "base_manager.py",
        "service_v2.py",
        "temp.py",
    }

    found = {path.name for path in read_python_files(BACKEND_SRC)}

    assert forbidden_names.isdisjoint(found)
