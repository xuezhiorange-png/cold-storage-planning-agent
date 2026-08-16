"""Architecture boundary tests for the reports module.

Enforces that:
- reports/ does not import from schemes.infrastructure or knowledge.infrastructure
- reports/infrastructure/real_data_provider.py does not import _session from any module
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

REPORTS_MODULE = (
    Path(__file__).resolve().parents[2] / "src" / "cold_storage" / "modules" / "reports"
)

REAL_DATA_PROVIDER = REPORTS_MODULE / "infrastructure" / "real_data_provider.py"


def _all_python_files(module_path: Path) -> list[Path]:
    """Return all .py files under module_path, excluding __pycache__."""
    return [p for p in module_path.rglob("*.py") if "__pycache__" not in p.parts]


def test_reports_do_not_import_schemes_infrastructure() -> None:
    """The reports module must not depend on schemes infrastructure internals.

    Reports should consume scheme data only through SchemeQueryPort.
    """
    forbidden = "cold_storage.modules.schemes.infrastructure"
    files = _all_python_files(REPORTS_MODULE)
    assert files, "No .py files found in reports module"

    violations: list[str] = []
    for path in files:
        content = path.read_text()
        if forbidden in content:
            violations.append(str(path.relative_to(REPORTS_MODULE)))

    assert not violations, f"Reports module imports from schemes.infrastructure: {violations}"


def test_reports_do_not_import_knowledge_infrastructure() -> None:
    """The reports module must not depend on knowledge infrastructure internals.

    Reports should consume knowledge data only through KnowledgeQueryPort.
    """
    forbidden = "cold_storage.modules.knowledge.infrastructure"
    files = _all_python_files(REPORTS_MODULE)
    assert files, "No .py files found in reports module"

    violations: list[str] = []
    for path in files:
        content = path.read_text()
        if forbidden in content:
            violations.append(str(path.relative_to(REPORTS_MODULE)))

    assert not violations, f"Reports module imports from knowledge.infrastructure: {violations}"


def test_real_data_provider_does_not_import_session() -> None:
    """RealReportDataProvider must not import _session from any module.

    Direct session access violates the architecture boundary. The provider
    should only use application-layer service ports.
    """
    assert REAL_DATA_PROVIDER.exists(), f"{REAL_DATA_PROVIDER} not found"

    content = REAL_DATA_PROVIDER.read_text()
    lines = content.splitlines()

    violations: list[str] = []
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if "import" in stripped and "_session" in stripped:
            violations.append(f"  line {i}: {stripped}")

    assert not violations, (
        "RealReportDataProvider imports _session (direct DB session access):\n"
        + "\n".join(violations)
    )


def test_reports_domain_has_no_infrastructure_imports() -> None:
    """The reports domain layer must not import from any infrastructure layer.

    Domain should be free of infrastructure concerns.
    """
    domain_path = REPORTS_MODULE / "domain"
    if not domain_path.exists():
        pytest.skip("reports/domain directory not found")

    forbidden_patterns = [
        "cold_storage.modules.schemes.infrastructure",
        "cold_storage.modules.knowledge.infrastructure",
        "cold_storage.modules.calculations.infrastructure",
        "cold_storage.modules.projects.infrastructure",
        "cold_storage.modules.planning_agent.infrastructure",
    ]

    files = _all_python_files(domain_path)
    violations: list[str] = []
    for path in files:
        content = path.read_text()
        for pattern in forbidden_patterns:
            if pattern in content:
                violations.append(f"  {path.relative_to(REPORTS_MODULE)} imports {pattern}")

    assert not violations, "Reports domain imports from infrastructure layers:\n" + "\n".join(
        violations
    )


def test_create_app_report_composition_uses_public_scheme_authority_query() -> None:
    """Exercise the real app factory's report service composition."""
    import cold_storage.modules.schemes.application.query as schemes_query
    from cold_storage.bootstrap.app import create_app
    from cold_storage.modules.reports.api.routes import _get_render_service, _get_service
    from cold_storage.modules.reports.application.service import _default_trusted_operator
    from cold_storage.modules.reports.infrastructure.orm import Base
    from cold_storage.modules.schemes.application.query import (
        SqlAlchemySchemeReviewAuthorityReader,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = create_app()
    factory = app.dependency_overrides[_get_service]
    render_factory = app.dependency_overrides[_get_render_service]

    with Session(engine) as session:
        service = factory(session)
        render_service = render_factory(session)

    provider = service._assembler._provider
    assert service._scheme_review_query is provider._scheme_query
    production_query_type = schemes_query._SCHEME_QUERY_SERVICE_IMPLEMENTATION
    assert isinstance(service._scheme_review_query, production_query_type)
    assert isinstance(
        service._scheme_review_query._review_authority_reader,
        SqlAlchemySchemeReviewAuthorityReader,
    )

    assert isinstance(render_service._scheme_review_query, production_query_type)
    assert isinstance(
        render_service._scheme_review_query._review_authority_reader,
        SqlAlchemySchemeReviewAuthorityReader,
    )
    assert render_service._trusted_operator is _default_trusted_operator
