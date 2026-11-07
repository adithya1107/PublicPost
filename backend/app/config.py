"""Application settings, read from environment variables and an optional backend/.env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_env: Literal["development", "production"] = "development"
    database_url: str = "sqlite:///./publicpost.db"
    # No default on purpose: the app refuses to start without a real secret.
    jwt_secret: str = Field(min_length=32)
    jwt_expire_days: int = Field(default=30, ge=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    ingestion_enabled: bool = True
    ingestion_interval_minutes: int = Field(default=20, ge=1)
    article_retention_days: int = Field(default=14, ge=1)
    rate_limits_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Hosting providers hand out postgres:// URLs; SQLAlchemy needs the driver named."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
