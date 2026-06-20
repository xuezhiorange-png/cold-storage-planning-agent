"""Application settings — environment-driven configuration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Fields that should be masked in repr output
_SENSITIVE_FIELDS = {"postgres_password", "openai_api_key"}


class Settings(BaseSettings):
    app_env: str = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_backend: Literal["sqlite", "postgresql"] = "sqlite"
    database_url: str | None = None
    sqlite_path: str = "./cold_storage_dev.db"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "cold_storage"
    postgres_user: str = "cold_storage"
    postgres_password: str = ""

    redis_url: str = "redis://localhost:6379/0"
    storage_dir: str = "backend/storage"
    openai_api_key: str = ""

    @model_validator(mode="after")
    def _build_database_url(self) -> Settings:
        if self.database_url is not None:
            return self
        if self.database_backend == "sqlite":
            self.database_url = f"sqlite:///{self.sqlite_path}"
        else:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        return self

    def __repr_args__(self) -> Sequence[tuple[str, object]]:
        """Mask sensitive fields in repr output."""
        result = []
        for key, value in self.model_dump().items():
            if key in _SENSITIVE_FIELDS:
                result.append((key, "***" if value else ""))
            else:
                result.append((key, value))
        return result


def get_settings() -> Settings:
    return Settings()
