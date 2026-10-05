"""Environment-based application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Lenny Growth Assistant API"
    app_env: Literal["development", "test", "production"] = "development"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    database_url: SecretStr = SecretStr("")
    database_timeout_seconds: float = Field(default=5.0, gt=0, le=60)


@lru_cache
def get_settings() -> Settings:
    return Settings()
