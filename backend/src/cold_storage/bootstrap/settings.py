from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./cold_storage_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: str = "backend/storage"


def get_settings() -> Settings:
    return Settings()
