from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env.

    All variables are prefixed DBDOCTOR_, e.g. DBDOCTOR_ENV=production.
    """

    model_config = SettingsConfigDict(env_prefix="DBDOCTOR_", env_file=".env", extra="ignore")

    app_name: str = "dbdoctor"
    env: str = "development"
    version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
