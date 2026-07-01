"""Architecture boundary tests for the schemes production layer.

Verifies that application-layer modules do not import from infrastructure
and that infrastructure modules do not import from application services.
Uses AST parsing for reliable import detection (catches inline imports
inside function bodies, not just top-level imports).
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"
SCHEMES_DIR = BACKEND_SRC / "modules" / "schemes"
APP_DIR = SCHEMES_DIR / "application"
INFRA_DIR = SCHEMES_DIR / "infrastructure"


def _get_imports(filepath: Path) -> list[tuple[int, str]]:
    """Parse a Python file and return all imported module names with line numbers.

    Returns list of (line_number, module_name) tuples.
    For ``from X.Y.Z import ...`` the module_name is ``X.Y.Z``.
    For ``import X.Y.Z`` the module_name is ``X.Y.Z``.
    Catches both top-level and inline (inside function body) imports.
    """
    source = filepath.read_text()
    tree = ast.parse(source, filename=str(filepath))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.lineno, node.module))
    return imports


def _imports_from(imports: list[tuple[int, str]], prefix: str) -> list[tuple[int, str]]:
    """Return imports whose module name starts with *prefix*."""
    return [(line, mod) for line, mod in imports if mod.startswith(prefix)]


def _imports_containing(imports: list[tuple[int, str]], fragment: str) -> list[tuple[int, str]]:
    """Return imports whose module name contains *fragment*."""
    return [(line, mod) for line, mod in imports if fragment in mod]


# ---------------------------------------------------------------------------
# 1) production_service must NOT import from orchestration.infrastructure
# ---------------------------------------------------------------------------


class TestProductionServiceBoundaries:
    """schemes.application.production_service architecture boundaries."""

    def test_no_orchestration_infrastructure_imports(self) -> None:
        """production_service must not import from orchestration.infrastructure.

        The production service operates in the application layer and must
        communicate with infrastructure only through ports/protocols.
        """
        filepath = APP_DIR / "production_service.py"
        assert filepath.exists(), f"{filepath} not found"
        imports = _get_imports(filepath)
        violations = _imports_from(imports, "cold_storage.modules.orchestration.infrastructure")
        assert not violations, (
            "production_service imports from orchestration.infrastructure:\n"
            + "\n".join(f"  line {line}: {mod}" for line, mod in violations)
        )


# ---------------------------------------------------------------------------
# 2) source_binding_verifier must NOT import from orchestration.infrastructure
# ---------------------------------------------------------------------------


class TestSourceBindingVerifierBoundaries:
    """schemes.application.source_binding_verifier architecture boundaries."""

    def test_no_orchestration_infrastructure_imports(self) -> None:
        """source_binding_verifier must not import from orchestration.infrastructure.

        The verifier is a pure application-layer adapter that operates on
        port snapshots, not ORM records.
        """
        filepath = APP_DIR / "source_binding_verifier.py"
        assert filepath.exists(), f"{filepath} not found"
        imports = _get_imports(filepath)
        violations = _imports_from(imports, "cold_storage.modules.orchestration.infrastructure")
        assert not violations, (
            "source_binding_verifier imports from orchestration.infrastructure:\n"
            + "\n".join(f"  line {line}: {mod}" for line, mod in violations)
        )


# ---------------------------------------------------------------------------
# 3) weight_revision_governance must NOT import from any infrastructure
# ---------------------------------------------------------------------------


class TestWeightRevisionGovernanceBoundaries:
    """schemes.application.weight_revision_governance architecture boundaries."""

    def test_no_infrastructure_imports(self) -> None:
        """weight_revision_governance must not import from any infrastructure.

        Weight revision governance is a pure validation/governance layer
        that must not depend on any infrastructure implementation.
        """
        filepath = APP_DIR / "weight_revision_governance.py"
        assert filepath.exists(), f"{filepath} not found"
        imports = _get_imports(filepath)
        violations = _imports_containing(imports, ".infrastructure")
        assert not violations, (
            "weight_revision_governance imports from infrastructure:\n"
            + "\n".join(f"  line {line}: {mod}" for line, mod in violations)
        )


# ---------------------------------------------------------------------------
# 4) source_domain_mapping must NOT import from any infrastructure
# ---------------------------------------------------------------------------


class TestSourceDomainMappingBoundaries:
    """schemes.application.source_domain_mapping architecture boundaries."""

    def test_no_infrastructure_imports(self) -> None:
        """source_domain_mapping must not import from any infrastructure.

        The source mapping layer transforms port snapshots into domain
        models and must not depend on infrastructure implementations.
        """
        filepath = APP_DIR / "source_domain_mapping.py"
        assert filepath.exists(), f"{filepath} not found"
        imports = _get_imports(filepath)
        violations = _imports_containing(imports, ".infrastructure")
        assert not violations, "source_domain_mapping imports from infrastructure:\n" + "\n".join(
            f"  line {line}: {mod}" for line, mod in violations
        )


# ---------------------------------------------------------------------------
# 5) production_ports must NOT import from any infrastructure
# ---------------------------------------------------------------------------


class TestProductionPortsBoundaries:
    """schemes.application.production_ports architecture boundaries."""

    def test_no_infrastructure_imports(self) -> None:
        """production_ports must not import from any infrastructure.

        Ports define the contract between application and infrastructure
        layers.  They must be free of infrastructure dependencies to
        prevent circular coupling.
        """
        filepath = APP_DIR / "production_ports.py"
        assert filepath.exists(), f"{filepath} not found"
        imports = _get_imports(filepath)
        violations = _imports_containing(imports, ".infrastructure")
        assert not violations, "production_ports imports from infrastructure:\n" + "\n".join(
            f"  line {line}: {mod}" for line, mod in violations
        )


# ---------------------------------------------------------------------------
# 6) All schemes.application production modules use only ports/protocols
#    for data access — no direct infrastructure imports
# ---------------------------------------------------------------------------

# The five production application modules defined in the production trust boundary.
_PRODUCTION_APP_MODULES = (
    "production_service.py",
    "source_binding_verifier.py",
    "weight_revision_governance.py",
    "source_domain_mapping.py",
    "production_ports.py",
)


class TestDataAccessPortsBoundary:
    """Verify production application modules access data via ports/protocols."""

    def test_no_infrastructure_imports_in_production_modules(self) -> None:
        """All production schemes.application modules must avoid infrastructure imports.

        Data access must flow through Protocol/ABC port interfaces defined
        in production_ports.py.  Infrastructure implementations provide the
        concrete adapters.
        """
        violations: list[str] = []
        for module_name in _PRODUCTION_APP_MODULES:
            filepath = APP_DIR / module_name
            if not filepath.exists():
                continue
            imports = _get_imports(filepath)
            for line, mod in imports:
                if ".infrastructure" in mod:
                    violations.append(f"  {module_name} line {line}: {mod}")

        assert not violations, (
            "schemes.application production modules import from infrastructure:\n"
            + "\n".join(violations)
        )

    def test_production_modules_only_use_standard_library(self) -> None:
        """Production application modules must not import third-party
        infrastructure libraries (SQLAlchemy, Redis, etc.).

        They may only import from:
        - standard library (hashlib, json, uuid, dataclasses, etc.)
        - typing / collections.abc
        - schemes.application.production_ports (port definitions)
        - schemes.domain (domain models and errors)
        - other schemes.application modules (sibling adapters)
        """
        forbidden_libraries = ("sqlalchemy", "redis", "fastapi", "requests", "httpx")
        violations: list[str] = []
        for module_name in _PRODUCTION_APP_MODULES:
            filepath = APP_DIR / module_name
            if not filepath.exists():
                continue
            imports = _get_imports(filepath)
            for line, mod in imports:
                for lib in forbidden_libraries:
                    if mod.startswith(lib):
                        violations.append(
                            f"  {module_name} line {line}: imports '{mod}' "
                            f"(forbidden library: {lib})"
                        )
                        break

        assert not violations, (
            "Production application modules import forbidden libraries:\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# 7) production_read_ports must NOT import from production_service
# ---------------------------------------------------------------------------


class TestProductionReadPortsBoundaries:
    """schemes.infrastructure.production_read_ports architecture boundaries."""

    def test_no_production_service_imports(self) -> None:
        """production_read_ports must not import from schemes.application.production_service.

        Infrastructure adapters implement application ports; they must not
        depend on application services (which would create a circular
        dependency).
        """
        filepath = INFRA_DIR / "production_read_ports.py"
        assert filepath.exists(), f"{filepath} not found"
        imports = _get_imports(filepath)
        violations = _imports_from(
            imports, "cold_storage.modules.schemes.application.production_service"
        )
        assert not violations, (
            "production_read_ports imports from "
            "schemes.application.production_service:\n"
            + "\n".join(f"  line {line}: {mod}" for line, mod in violations)
        )
