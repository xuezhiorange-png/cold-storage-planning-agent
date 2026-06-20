"""Tests for cold_storage.bootstrap.dependencies lifecycle management."""

from __future__ import annotations

import importlib

import pytest

from cold_storage.bootstrap.settings import Settings


class TestNoImportTimeSideEffects:
    """Importing dependencies.py must NOT create an engine at import time."""

    def test_import_does_not_create_engine(self, tmp_path):
        """After importing the module, no engine should exist yet."""
        # We verify by checking that singletons dict is empty
        from cold_storage.bootstrap import dependencies as deps

        # Force a fresh import
        importlib.reload(deps)
        assert deps._singletons == {}


class TestInitDependencies:
    """init_dependencies creates engine and services in the singleton store."""

    def test_init_creates_engine_and_services(self, tmp_path):
        from cold_storage.bootstrap import dependencies as deps

        # Ensure clean state
        deps._singletons.clear()

        url = f"sqlite:///{tmp_path / 'lifecycle_test.db'}"
        settings = Settings(database_url=url)

        deps.init_dependencies(settings)

        assert "engine" in deps._singletons
        assert "project_service" in deps._singletons
        assert "agent_service" in deps._singletons

        # Cleanup
        deps.shutdown_dependencies()


class TestShutdownDependencies:
    """shutdown_dependencies disposes the engine and clears singletons."""

    def test_shutdown_disposes_engine(self, tmp_path):
        from cold_storage.bootstrap import dependencies as deps

        deps._singletons.clear()

        url = f"sqlite:///{tmp_path / 'shutdown_test.db'}"
        settings = Settings(database_url=url)
        deps.init_dependencies(settings)

        deps.shutdown_dependencies()

        assert deps._singletons == {}


class TestGettersBeforeInit:
    """get_project_service and get_engine raise RuntimeError before init."""

    def test_get_project_service_raises_before_init(self):
        from cold_storage.bootstrap import dependencies as deps

        deps._singletons.clear()

        with pytest.raises(RuntimeError, match="Dependencies not initialized"):
            deps.get_project_service()

    def test_get_engine_raises_before_init(self):
        from cold_storage.bootstrap import dependencies as deps

        deps._singletons.clear()

        with pytest.raises(RuntimeError, match="Dependencies not initialized"):
            deps.get_engine()

    def test_get_agent_service_raises_before_init(self):
        from cold_storage.bootstrap import dependencies as deps

        deps._singletons.clear()

        with pytest.raises(RuntimeError, match="Dependencies not initialized"):
            deps.get_agent_service()
