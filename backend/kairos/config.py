"""Application settings. Secrets come from the environment, never from code."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="KAIROS_", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+psycopg://kairos:kairos@localhost:5432/kairos"
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
