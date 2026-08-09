"""Application settings. Secrets come from the environment, never from code."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="KAIROS_", extra="ignore")

    environment: str = "local"

    # DEC-03 is still open: these are placeholders, not derived numbers. BIZ-07's
    # unit-economics spreadsheet sets the real ones. Deliberately low so an
    # unattended loop stops early and cheaply rather than at a plausible-looking
    # figure nobody chose.
    budget_currency: str = "USD"
    daily_budget: str = "2.00"
    monthly_budget: str = "40.00"
    database_url: str = "postgresql+psycopg://kairos:kairos@localhost:5432/kairos"
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
