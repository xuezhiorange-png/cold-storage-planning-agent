"""Engine and session factory management — pure factory functions, no singletons."""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.settings import Settings


def create_engine_from_settings(settings: Settings) -> Engine:
    """Create a SQLAlchemy engine from Settings."""
    url = settings.database_url
    assert url is not None, "database_url must be set"
    connect_args: dict[str, object] = {}
    if settings.database_backend == "sqlite":
        connect_args["check_same_thread"] = False
    return create_engine(
        url,
        future=True,
        connect_args=connect_args,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Any]:
    """Create a session factory bound to the given engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def dispose_engine(engine: Engine) -> None:
    """Dispose of a SQLAlchemy engine."""
    engine.dispose()
