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

    # persistence
    database_url: str = "sqlite:///./dbdoctor.db"  # compose overrides with postgres
    data_dir: str = "./data"  # snapshots + report bundles live here

    # auth
    jwt_secret: str = "dev-secret-change-me"  # MUST be overridden in production
    jwt_expiry_minutes: int = 60
    admin_emails: str = ""  # comma-separated; these accounts get review rights

    # pipeline
    max_upload_bytes: int = 50 * 1024 * 1024
    enable_pdf: bool = True
    enable_ai: bool = False  # off until pilots warrant the spend

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
