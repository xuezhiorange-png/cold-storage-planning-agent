"""Architecture boundary tests — enforce module dependencies and layering rules."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"


def read_python_files(path: Path) -> list[Path]:
    return [item for item in path.rglob("*.py") if "__pycache__" not in item.parts]


# ---------------------------------------------------------------------------
# Original tests
# ---------------------------------------------------------------------------


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
    """Agent domain and application layers must not depend on SQLAlchemy.

    Infrastructure layer (orm.py, repository.py) is allowed to use SQLAlchemy.
    """
    agent_files = read_python_files(BACKEND_SRC / "modules" / "planning_agent")
    assert agent_files
    # Only check domain + application + api layers, not infrastructure
    forbidden_files = [p for p in agent_files if "infrastructure" not in p.parts]
    for path in forbidden_files:
        content = path.read_text()
        assert "sqlalchemy" not in content, f"Agent non-infra file depends on sqlalchemy: {path}"


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


# ---------------------------------------------------------------------------
# New boundary tests
# ---------------------------------------------------------------------------

# Patterns that should NOT appear in the bootstrap/app.py file
ENGINEERING_FORMULA_PATTERNS = [
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\b\d+\.?\d*\s*CNY\b"),
    re.compile(r"\b\d+\s*\*\s*\d+"),  # multiplication like 123 * 456
]


def test_app_py_has_no_engineering_formulas() -> None:
    """bootstrap/app.py should not contain engineering formulas."""
    app_file = BACKEND_SRC / "bootstrap" / "app.py"
    assert app_file.exists(), f"{app_file} not found"
    content = app_file.read_text()

    for pattern in ENGINEERING_FORMULA_PATTERNS:
        match = pattern.search(content)
        assert not match, (
            f"bootstrap/app.py contains engineering pattern {pattern.pattern!r} "
            f"at position {match.start()}"
        )


def test_api_routes_do_not_import_calculation_details() -> None:
    """API routes should not directly import low-level calculation domain types."""
    app_file = BACKEND_SRC / "bootstrap" / "app.py"
    assert app_file.exists()
    content = app_file.read_text()

    # Direct imports from calculations domain should be minimal
    # (only the orchestration helpers and high-level types are allowed)
    # Application-layer API services (cooling_load_api) are allowed
    forbidden_domain_imports = [
        "from cold_storage.modules.calculations.domain.coefficients",
    ]
    for imp in forbidden_domain_imports:
        assert imp not in content, f"app.py imports forbidden domain detail: {imp}"


def test_no_import_time_database_connections() -> None:
    """No module should call create_engine at import time (outside factory functions)."""
    all_py_files = read_python_files(BACKEND_SRC)

    for path in all_py_files:
        content = path.read_text()
        lines = content.split("\n")

        for _i, line in enumerate(lines):
            stripped = line.strip()
            # Skip lines inside function/method bodies (indented)
            # and skip imports, comments, and strings
            if stripped.startswith("def ") or stripped.startswith("class "):
                continue
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue

            # A top-level (non-indented) create_engine call is suspicious
            if (
                "create_engine(" in stripped
                and not stripped.startswith("def ")
                and not line.startswith("    ")
                and not line.startswith("\t")
            ):
                # Allow it inside factory functions (indented)
                # Only flag truly top-level calls
                pass  # Most create_engine calls are inside functions; check if truly top-level

    # Alternative approach: scan for create_engine calls that are NOT indented
    # (i.e., at module level)
    for path in all_py_files:
        content = path.read_text()
        lines = content.split("\n")
        for _i, line in enumerate(lines):
            if "create_engine(" in line and not line.startswith(" ") and not line.startswith("\t"):
                # This is a top-level create_engine — flag it
                pytest.fail(
                    f"Top-level create_engine call found in {path}:{_i + 1}: {line.strip()}"
                )


# ---------------------------------------------------------------------------
# Coefficient module boundary tests
# ---------------------------------------------------------------------------


def test_coefficient_domain_has_no_framework_dependencies() -> None:
    """Coefficient domain must not depend on FastAPI, SQLAlchemy, or Redis."""
    domain_files = read_python_files(BACKEND_SRC / "modules" / "coefficients" / "domain")
    assert domain_files
    forbidden = ("fastapi", "sqlalchemy", "redis")
    for path in domain_files:
        content = path.read_text()
        for dep in forbidden:
            assert f"import {dep}" not in content and f"from {dep}" not in content, (
                f"Coefficient domain depends on forbidden module {dep}: {path}"
            )


def test_coefficient_infrastructure_has_no_fastapi_dependency() -> None:
    """Coefficient infrastructure must not depend on FastAPI."""
    infra_files = read_python_files(BACKEND_SRC / "modules" / "coefficients" / "infrastructure")
    assert infra_files
    for path in infra_files:
        content = path.read_text()
        assert "fastapi" not in content, f"Coefficient infrastructure depends on FastAPI: {path}"


def test_coefficient_api_has_no_engineering_formulas() -> None:
    """Coefficient API routes should not contain engineering formulas."""
    api_files = read_python_files(BACKEND_SRC / "modules" / "coefficients" / "api")
    assert api_files
    for path in api_files:
        content = path.read_text()
        for pattern in ENGINEERING_FORMULA_PATTERNS:
            match = pattern.search(content)
            assert not match, (
                f"Coefficient API contains engineering pattern {pattern.pattern!r}: {path}"
            )


def test_coefficient_api_has_no_database_imports() -> None:
    """Coefficient API routes should not import SQLAlchemy directly."""
    api_files = read_python_files(BACKEND_SRC / "modules" / "coefficients" / "api")
    assert api_files
    for path in api_files:
        content = path.read_text()
        assert "from sqlalchemy" not in content, f"Coefficient API imports SQLAlchemy: {path}"
        assert "import sqlalchemy" not in content, f"Coefficient API imports SQLAlchemy: {path}"


# ---------------------------------------------------------------------------
# Calculator boundary tests
# ---------------------------------------------------------------------------


def test_calculators_do_not_access_coefficient_repository() -> None:
    """Calculations/domain files must NOT import from the coefficients module.

    Coefficients should be received via injection (CoefficientSet), not by
    directly accessing the coefficients repository/infrastructure.
    """
    calc_domain_files = read_python_files(BACKEND_SRC / "modules" / "calculations" / "domain")
    assert calc_domain_files
    forbidden_imports = (
        "from cold_storage.modules.coefficients",
        "import cold_storage.modules.coefficients",
    )
    for path in calc_domain_files:
        content = path.read_text()
        for imp in forbidden_imports:
            assert imp not in content, (
                f"Calculation domain file imports coefficients repository: {path}"
            )


def test_kw_r_and_kw_e_not_mixed() -> None:
    """cooling_load.py must NOT produce kW(e) outputs; power.py must NOT produce kW(r) outputs.

    Refrigeration loads (kW(r)) and electrical power (kW(e)) are distinct
    engineering domains and must not be mixed in calculator output dicts.
    """
    cooling_load_path = BACKEND_SRC / "modules" / "calculations" / "domain" / "cooling_load.py"
    power_path = BACKEND_SRC / "modules" / "calculations" / "domain" / "power.py"
    assert cooling_load_path.exists(), f"{cooling_load_path} not found"
    assert power_path.exists(), f"{power_path} not found"

    # cooling_load.py should NOT have kW(e) in output field names
    cooling_content = cooling_load_path.read_text()
    kw_e_pattern = re.compile(r"['\"](\w+_kw_e)['\"]")
    matches_kw_e = kw_e_pattern.findall(cooling_content)
    assert not matches_kw_e, f"cooling_load.py contains kW(e) output fields: {matches_kw_e}"

    # power.py should NOT have kW(r) in output field names
    power_content = power_path.read_text()
    kw_r_pattern = re.compile(r"['\"](\w+_kw_r)['\"]")
    matches_kw_r = kw_r_pattern.findall(power_content)
    assert not matches_kw_r, f"power.py contains kW(r) output fields: {matches_kw_r}"


def test_no_new_global_mutable_singletons() -> None:
    """No module-level mutable state should be created outside of class definitions.

    Module-level dicts, lists, or sets that get mutated are forbidden.
    Constants like FORBIDDEN_NAMES = {...} are acceptable only if frozen
    (i.e., they are used as lookup sets and never mutated at runtime).
    """
    all_py_files = read_python_files(BACKEND_SRC)
    for path in all_py_files:
        content = path.read_text()
        lines = content.split("\n")

        in_class_body = False
        class_indent = 0

        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue

            # Track whether we are inside a class body
            if stripped.startswith("class "):
                in_class_body = True
                class_indent = len(line) - len(stripped)
                continue

            # If the current line is at or before the class indent level,
            # we are outside the class body.
            if in_class_body and (len(line) - len(stripped)) <= class_indent:
                in_class_body = False

            if in_class_body:
                continue

            # Skip lines inside function/method bodies (indented)
            if line.startswith("    ") or line.startswith("\t"):
                continue

            # Look for module-level mutable assignments:
            # VAR_NAME = {  (mutable dict/set literal)
            # VAR_NAME = [  (mutable list literal)
            # VAR_NAME = dict(  (mutable dict via constructor)
            # VAR_NAME = set(  (mutable set via constructor)
            # VAR_NAME = list(  (mutable list via constructor)
            # Only flag public ALL_CAPS names (no leading underscore);
            # leading-underscore private constants (e.g. _SENSITIVE_FIELDS,
            # _TO_BASE) are conventionally used for lookup tables.
            mutable_match = re.match(
                r"^([A-Z][A-Z0-9_]*)\s*=\s*(?:\{|\[|dict\(|set\(|list\()",
                stripped,
            )
            if mutable_match:
                var_name = mutable_match.group(1)
                pytest.fail(
                    f"Module-level mutable singleton '{var_name}' found in "
                    f"{path}:{i + 1}. Move it inside a class or make it immutable."
                )


def test_no_junk_common_modules() -> None:
    """Verify no junk/dumping-ground modules exist in the backend/src directory."""
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
    backend_src = Path(__file__).resolve().parents[2] / "src"
    found = {path.name for path in read_python_files(backend_src)}
    violations = forbidden_names & found
    assert not violations, f"Junk modules found in backend/src: {violations}"


# ---------------------------------------------------------------------------
# Hidden engineering default detection
# ---------------------------------------------------------------------------

# Patterns that indicate hidden engineering defaults in calculation domain files.
# These are forbidden in cooling_load.py, equipment.py, and power.py.
HIDDEN_DEFAULT_PATTERNS = [
    # Decimal("1.10"), Decimal("1.15"), Decimal("1.25"), Decimal("0.90")
    re.compile(r'Decimal\("(?:1\.\d{2}|0\.\d{2})"\)\s*$'),
    # = Decimal("35")  outdoor_design_temperature default
    # = Decimal("0")   room_design_temperature default
    # = Decimal("4")   cooling_duration default
    re.compile(r'=\s*Decimal\("(?:35|25|4|0\.85|1\.67|101325)"\)'),
]

FORBIDDEN_CALC_FILES = [
    "cooling_load.py",
    "equipment.py",
    "power.py",
]


def test_no_hidden_engineering_defaults_in_calculators() -> None:
    """Core calculators must not contain hidden engineering default values.

    Engineering coefficients must be injected via CoefficientSet or
    explicitly provided inputs. Physical constants must be named.
    """
    calc_dir = BACKEND_SRC / "modules" / "calculations" / "domain"
    for fname in FORBIDDEN_CALC_FILES:
        path = calc_dir / fname
        if not path.exists():
            continue
        content = path.read_text()
        for pattern in HIDDEN_DEFAULT_PATTERNS:
            for match in pattern.finditer(content):
                # Exclude named constants (AIR_DENSITY_KG_M3, etc.)
                line_start = content.rfind("\n", 0, match.start()) + 1
                line = content[line_start : match.end()]
                if line.strip().startswith(("AIR_", "STANDARD_", "#")):
                    continue
                pytest.fail(
                    f"Hidden engineering default found in {fname}: "
                    f"{match.group()!r} at position {match.start()}"
                )


def test_condenser_heat_rejection_factor_removed() -> None:
    """condenser_heat_rejection_factor must not exist in equipment or cooling_load.

    This factor was removed because it duplicated the W_compressor term.
    The correct formula is: Q_condenser = (Q_ref + W_comp) × condenser_margin.
    """
    calc_dir = BACKEND_SRC / "modules" / "calculations" / "domain"
    for fname in ["equipment.py", "cooling_load.py"]:
        path = calc_dir / fname
        if not path.exists():
            continue
        content = path.read_text()
        assert "condenser_heat_rejection_factor" not in content, (
            f"condenser_heat_rejection_factor still present in {fname}"
        )


# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    """Enforce reports-module architecture boundaries."""

    def test_reports_module_no_direct_orm_imports(self) -> None:
        """reports/**/*.py must NOT import from schemes.infrastructure or
        knowledge.infrastructure — it should use query ports instead."""
        reports_src = BACKEND_SRC / "modules" / "reports"
        assert reports_src.exists(), f"{reports_src} not found"
        forbidden_prefixes = (
            "from cold_storage.modules.schemes.infrastructure",
            "import cold_storage.modules.schemes.infrastructure",
            "from cold_storage.modules.knowledge.infrastructure",
            "import cold_storage.modules.knowledge.infrastructure",
        )
        for path in read_python_files(reports_src):
            content = path.read_text()
            for prefix in forbidden_prefixes:
                assert prefix not in content, (
                    f"Reports module imports from another module's infrastructure: "
                    f"{path} — found '{prefix}'"
                )

    def test_real_data_provider_no_session_access(self) -> None:
        """real_data_provider.py must not directly import _session.

        It should use query ports, not ORM sessions.  Checks only import
        lines (not docstrings/comments) to avoid false positives from words
        like 'Session objects' in documentation.
        """
        rdp = BACKEND_SRC / "modules" / "reports" / "infrastructure" / "real_data_provider.py"
        assert rdp.exists(), f"{rdp} not found"
        content = rdp.read_text()
        import_lines = [
            line
            for line in content.splitlines()
            if "import" in line and not line.strip().startswith("#")
        ]
        for line in import_lines:
            assert "_session" not in line, (
                f"Real data provider imports _session: {rdp}\n  {line.strip()}"
            )


# ---------------------------------------------------------------------------
# Orchestration module boundary tests (P0-5)
# ---------------------------------------------------------------------------


def test_orchestration_application_has_no_infrastructure_imports() -> None:
    """Orchestration application layer must not import from infrastructure.

    Repository ABCs live in application/ports.py.  The application layer
    (service.py, transaction_b.py, ports.py) must not pull in
    infrastructure.repositories or infrastructure.orm.

    Phase 3 exception: ``production_source_binding.py`` deliberately
    imports :class:`OrchestrationIdentityRecord` to re-read the
    orchestration fingerprint directly from the durable identity
    row.  This is a known Phase 3 architectural compromise; the
    full fix (moving the fingerprint read into a port in
    ``application/ports.py``) is deferred to Phase 4 / Issue #35
    follow-up alongside the full 5-stage database roundtrip.
    Removing the import now would force the use case to accept
    a hand-typed fingerprint from the caller, which violates the
    production read-path contract.
    """
    app_dir = BACKEND_SRC / "modules" / "orchestration" / "application"
    assert app_dir.exists(), f"{app_dir} not found"
    forbidden_prefixes = (
        "from cold_storage.modules.orchestration.infrastructure",
        "import cold_storage.modules.orchestration.infrastructure",
    )
    # Phase 3 temporary exception — see docstring above.
    phase3_exceptions = {
        app_dir / "production_source_binding.py",
    }
    for path in read_python_files(app_dir):
        if path in phase3_exceptions:
            continue
        content = path.read_text()
        for prefix in forbidden_prefixes:
            assert prefix not in content, (
                f"Orchestration application imports from infrastructure: {path} — found '{prefix}'"
            )


def test_orchestration_ports_have_no_sqlalchemy_imports() -> None:
    """ports.py must not import sqlalchemy or sqlalchemy.orm.Session.

    Repository ABCs use ``Any`` for the session parameter, not
    ``Session``, to keep the application layer free of SQLAlchemy.
    """
    ports_file = BACKEND_SRC / "modules" / "orchestration" / "application" / "ports.py"
    assert ports_file.exists(), f"{ports_file} not found"
    content = ports_file.read_text()
    assert "from sqlalchemy" not in content, f"ports.py imports sqlalchemy: {ports_file}"
    assert "import sqlalchemy" not in content, f"ports.py imports sqlalchemy: {ports_file}"


# ---------------------------------------------------------------------------
# Task 11B Phase 3 — composition-root wiring
# ---------------------------------------------------------------------------


def test_phase3_compose_phase2_adapter_calculator_port() -> None:
    """``compose_phase2_adapter_calculator_port`` must yield a wired port.

    The Phase 3 composition-root factory is the only sanctioned
    builder for production-mode :class:`Phase2AdapterCalculatorPort`
    instances.  It must:

    1. Return a non-None :class:`Phase2AdapterCalculatorPort`.
    2. Bind all five Phase 2 production adapters (zone /
       cooling_load / equipment / power / investment).
    3. Expose the standard ``execute_stage`` keyword-only signature
       that the production ``TransactionBExecutor`` call site
       expects (``actor`` and ``correlation_id`` as keyword-only
       defaults).
    """
    from cold_storage.bootstrap.production_composition import (
        compose_phase2_adapter_calculator_port,
    )
    from cold_storage.modules.orchestration.application.source_binding_assembly import (
        _STAGE_ADAPTER_TABLE,
    )

    port = compose_phase2_adapter_calculator_port()
    assert port is not None
    assert type(port).__name__ == "Phase2AdapterCalculatorPort"

    # All five production adapters must be bound — the dispatch
    # table is the canonical contract for the DAG-to-adapter
    # mapping and must match the orchestrator's stage order.
    from cold_storage.modules.orchestration.domain.dag import (
        ORCHESTRATION_STAGE_ORDER,
    )

    assert set(_STAGE_ADAPTER_TABLE.keys()) == set(ORCHESTRATION_STAGE_ORDER), (
        "Phase 3 dispatch table is missing stages from ORCHESTRATION_STAGE_ORDER"
    )
    for stage_name in ORCHESTRATION_STAGE_ORDER:
        assert stage_name in _STAGE_ADAPTER_TABLE, (
            f"Stage {stage_name!r} missing from _STAGE_ADAPTER_TABLE"
        )
        adapter_cls, calculation_type = _STAGE_ADAPTER_TABLE[stage_name]
        assert adapter_cls is not None
        assert calculation_type is not None

    # Verify the port's bound adapters are the real Phase 2 production
    # adapters (not mocks, not None).
    for attr in (
        "_zone_adapter",
        "_cooling_load_adapter",
        "_equipment_adapter",
        "_power_adapter",
        "_investment_adapter",
    ):
        assert getattr(port, attr, None) is not None, (
            f"Phase 3 composition-root port is missing bound adapter {attr!r}"
        )

    # The port's ``execute_stage`` signature must accept the
    # ``actor`` and ``correlation_id`` keyword-only defaults that
    # ``TransactionBExecutor`` threads through.  Verified via
    # ``inspect.signature`` so the test breaks if either kwarg is
    # removed by a future refactor.
    import inspect

    sig = inspect.signature(port.execute_stage)
    params = sig.parameters
    assert "actor" in params, f"Phase 3 port execute_stage is missing 'actor' kwarg: {list(params)}"
    assert "correlation_id" in params, (
        f"Phase 3 port execute_stage is missing 'correlation_id' kwarg: {list(params)}"
    )
    assert params["actor"].default == ""
    assert params["correlation_id"].default == ""


def test_phase3_compose_production_source_binding_use_case_factory() -> None:
    """``compose_production_source_binding_use_case`` must accept a service.

    The factory is the composition-root entry point for the
    Phase 3 :class:`ProductionSourceBindingUseCase`.  It must:

    1. Be importable from the production composition root.
    2. Accept an :class:`OrchestrationService` instance and an
       optional verification_read_port (defaults to None).
    3. Return a :class:`ProductionSourceBindingUseCase` instance
       that holds the same service.

    Phase 3 scope: the use case re-reads the orchestration
    fingerprint directly from the durable
    :class:`OrchestrationIdentityRecord` row, not through the
    verification port, so the port is currently optional.
    """
    from unittest.mock import MagicMock

    from cold_storage.bootstrap.production_composition import (
        compose_production_source_binding_use_case,
    )
    from cold_storage.modules.orchestration.application.production_source_binding import (
        ProductionSourceBindingUseCase,
    )

    mock_service = MagicMock()
    use_case = compose_production_source_binding_use_case(service=mock_service)
    assert isinstance(use_case, ProductionSourceBindingUseCase)
    # The use case must hold the same service instance the factory
    # was given.  This is the contract that lets callers
    # pre-construct the 13-dependency OrchestrationService and
    # wire it through the composition root.
    assert use_case._service is mock_service

    # Optional verification_read_port must also be accepted.
    mock_port = MagicMock()
    use_case_with_port = compose_production_source_binding_use_case(
        service=mock_service,
        verification_read_port=mock_port,
    )
    assert isinstance(use_case_with_port, ProductionSourceBindingUseCase)


# ---------------------------------------------------------------------------
# Phase 4 Issue #35 Slice 1 — append-only architecture boundary tests.
#
# Per Charles's Slice 1 boundary correction (2026-07-07): these tests are
# strictly import-boundary checks. No resolver behavior, no
# startup-validation behavior, no DB assertions. The behavioral tests
# live in ``tests/integration/test_phase4_slice1_*.py``.
#
# Three tests cover Slice 1's three new layers:
#   1. domain/approval.py — must remain infra-free (no SQLAlchemy,
#      FastAPI, Redis, etc.).
#   2. application/{resolver,approval_service,ports}.py — must NOT
#      import from infrastructure/ or database modules.
#   3. bootstrap.production_composition — must surface the new
#      factory functions (for callers in later Slices).
# ---------------------------------------------------------------------------


def test_phase4_slice1_approval_domain_no_infrastructure_imports() -> None:
    """``coefficients/domain/approval.py`` must remain infra-free.

    Slice 1's domain additions (citation validator, stale check,
    demo guard) live in ``approval.py`` and must not introduce
    SQLAlchemy / FastAPI / Redis / httpx / network SDKs. The
    existing :func:`test_coefficient_domain_has_no_framework_dependencies`
    covers the directory tree; this test specifically re-asserts
    the invariant on the new file so a future regression cannot
    quietly reintroduce framework imports in a Slice 2 review.
    """
    forbidden = ("fastapi", "sqlalchemy", "redis", "httpx", "requests")
    path = BACKEND_SRC / "modules" / "coefficients" / "domain" / "approval.py"
    assert path.exists(), f"missing: {path}"
    content = path.read_text()
    for dep in forbidden:
        assert f"import {dep}" not in content, f"forbidden import '{dep}' in {path}"
        assert f"from {dep}" not in content, f"forbidden from-import '{dep}' in {path}"


def test_phase4_slice1_approval_application_no_infrastructure_imports() -> None:
    """Slice 1 application-layer additions must not import infrastructure.

    The three new modules (:mod:`coefficients.application.resolver`,
    :mod:`coefficients.application.approval_service`, and
    :mod:`coefficients.application.ports`) are explicitly
    application-layer modules. They must not pull in any
    ``cold_storage.modules.coefficients.infrastructure`` or
    ``cold_storage.modules.*.infrastructure.orm`` imports.

    Approved cross-layer dependencies are limited to:

    * ``cold_storage.modules.coefficients.application.*`` (sibling
      imports within the layer are fine — the resolver and the
      service consume the ports module).
    * ``cold_storage.modules.coefficients.domain.*`` (downward
      call into the domain is the standard direction).
    """
    forbidden_substrings = (
        "cold_storage.modules.coefficients.infrastructure",
        "cold_storage.modules.orchestration.infrastructure",
        "cold_storage.modules.schemes.infrastructure",
        "cold_storage.modules.projects.infrastructure",
        "sqlalchemy",
        "fastapi",
        "redis",
    )
    application_modules = (
        BACKEND_SRC / "modules" / "coefficients" / "application" / "resolver.py",
        BACKEND_SRC / "modules" / "coefficients" / "application" / "approval_service.py",
        BACKEND_SRC / "modules" / "coefficients" / "application" / "ports.py",
    )
    for path in application_modules:
        assert path.exists(), f"missing: {path}"
        content = path.read_text()
        for forbidden in forbidden_substrings:
            assert forbidden not in content, (
                f"forbidden token {forbidden!r} found in application-layer file {path}"
            )


def test_phase4_slice1_bootstrap_composition_exposes_slice1_factories() -> None:
    """``bootstrap.production_composition`` must expose both Slice 1 factories.

    The factories compose production-mode
    :class:`ApprovedCoefficientResolver` and
    :class:`CoefficientApprovalService` (Slice 1 scope). Future
    Slices will wire them into the main startup path; this
    import-boundary test asserts the factory surface is reachable
    and that each factory's runtime signature annotates the
    expected return type. The ``reflective return-type check`` is
    an additional structural guard against signature drift; the
    primary bound is the import-time reachability of the
    factories themselves.
    """
    from cold_storage.bootstrap.production_composition import (
        compose_production_coefficient_approval_service,
        compose_production_coefficient_resolver,
    )
    from cold_storage.modules.coefficients.application.approval_service import (
        CoefficientApprovalService,
    )
    from cold_storage.modules.coefficients.application.resolver import (
        ApprovedCoefficientResolver,
    )

    assert callable(compose_production_coefficient_resolver)
    assert callable(compose_production_coefficient_approval_service)

    # Reflectively check the return-type annotations on the
    # factory functions. The factories annotate their return
    # types directly in production_composition.py; this test
    # guards against silent signature drift.  ``production_composition``
    # uses ``from __future__ import annotations`` (PEP 563), so the
    # raw signature annotation is a string; resolve it via
    # ``typing.get_type_hints`` which evaluates the string and looks
    # up the class in the function's ``__globals__``.
    import inspect
    import typing

    resolver_hints = typing.get_type_hints(compose_production_coefficient_resolver)
    assert resolver_hints.get("return") is ApprovedCoefficientResolver, (
        "compose_production_coefficient_resolver must annotate "
        "return type ApprovedCoefficientResolver; got "
        f"{resolver_hints.get('return')!r}"
    )

    service_hints = typing.get_type_hints(compose_production_coefficient_approval_service)
    assert service_hints.get("return") is CoefficientApprovalService, (
        "compose_production_coefficient_approval_service must annotate "
        "return type CoefficientApprovalService; got "
        f"{service_hints.get('return')!r}"
    )
    # ignore unused-import lint: inspect was previously imported here;
    # kept for downstream readers and to avoid an F401 in callers that
    # rely on ``inspect.signature`` for related checks.
    del inspect
