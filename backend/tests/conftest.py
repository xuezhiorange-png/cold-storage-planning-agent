"""Shared test fixtures for the cold-storage-planning-agent test suite."""

from __future__ import annotations

import os

import pytest
from httpx import Client as TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.coefficients.infrastructure.database import (
    DatabaseCoefficientService,
)
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import Base


@pytest.fixture(autouse=True)
def _allow_insecure_actor():
    """Allow X-Actor header without proxy secret in all tests."""
    os.environ["PLANNING_AGENT_ALLOW_INSECURE_ACTOR"] = "true"
    yield
    os.environ.pop("PLANNING_AGENT_ALLOW_INSECURE_ACTOR", None)


@pytest.fixture()
def tmp_db_url(tmp_path):
    """Return a SQLite URL pointing at a temporary file."""
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture()
def tmp_engine(tmp_db_url):
    """Create a SQLAlchemy engine bound to the tmp DB and dispose on teardown."""
    engine = create_engine(
        tmp_db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def tmp_session_factory(tmp_engine):
    """Create a sessionmaker bound to the temporary engine."""
    return sessionmaker(bind=tmp_engine, expire_on_commit=False)


@pytest.fixture()
def tmp_project_service(tmp_engine):
    """Create a DatabaseProjectService using the temporary engine."""
    return DatabaseProjectService(tmp_engine)


@pytest.fixture()
def tmp_coefficient_service(tmp_engine):
    """Create a DatabaseCoefficientService using the temporary engine."""
    return DatabaseCoefficientService(tmp_engine)


@pytest.fixture()
def sample_app(tmp_project_service):
    """Create a FastAPI app with the project service dependency overridden."""
    from cold_storage.bootstrap.app import create_app

    app = create_app(project_service=tmp_project_service)
    return app


@pytest.fixture()
def sample_client(sample_app):
    """Create a httpx TestClient for the FastAPI app."""
    with TestClient(sample_app) as client:
        yield client


@pytest.fixture(autouse=True, scope="session")
def ensure_cjk_font():
    """Fail fast if the CJK font (fonts-wqy-zenhei) is not installed."""
    try:
        import fitz

        from cold_storage.modules.reports.renderers.pdf_renderer import (
            _get_cjk_font,
        )

        font = _get_cjk_font()
        doc = fitz.open()
        page = doc.new_page()
        tw = fitz.TextWriter(page.rect)
        tw.append((72, 72), "测试 Test", font=font, fontsize=12)
        tw.write_text(page)
        doc.close()
    except Exception as exc:
        pytest.fail(
            f"CJK font not available: {exc}. "
            "Install fonts-wqy-zenhei (apt-get install -y fonts-wqy-zenhei)."
        )
