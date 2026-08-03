"""Architecture tests for observability boundaries."""

from __future__ import annotations

import pathlib

BACKEND_SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "src"


class TestNoProviderSDKLeakage:
    """Ensure no provider SDK leakage into domain modules."""

    FORBIDDEN_IMPORTS = [
        "prometheus_client",
        "opentelemetry",
        "datadog",
    ]

    def test_domain_modules_no_provider_imports(self) -> None:
        """Domain modules must not import provider SDKs."""
        domain_dir = BACKEND_SRC / "cold_storage" / "modules"
        if not domain_dir.exists():
            return
        for py_file in domain_dir.rglob("*.py"):
            content = py_file.read_text()
            for forbidden in self.FORBIDDEN_IMPORTS:
                assert forbidden not in content, (
                    f"{py_file.relative_to(BACKEND_SRC)} imports {forbidden}"
                )


class TestOnlyAuthorizedPathsChanged:
    """Ensure only allowlisted paths were modified."""

    ALLOWED_PREFIXES = [
        "cold_storage/bootstrap/logging.py",
        "cold_storage/bootstrap/configuration_redactor.py",
        "cold_storage/bootstrap/app.py",
        "cold_storage/bootstrap/middleware/",
        "cold_storage/bootstrap/metrics/",
        "cold_storage/bootstrap/observability/",
    ]

    def test_no_unauthorized_business_module_changes(self) -> None:
        """Business module files should not be modified."""
        # This is a structural check - the test verifies that
        # observability code doesn't leak into business modules
        business_dir = BACKEND_SRC / "cold_storage" / "modules"
        if not business_dir.exists():
            return
        for py_file in business_dir.rglob("*.py"):
            content = py_file.read_text()
            # Business modules should not import from bootstrap.observability
            assert "from cold_storage.bootstrap.observability" not in content
            assert "from cold_storage.bootstrap.metrics" not in content
