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

    # billing (feature-flagged off for pilot customers, per plan)
    enable_payments: bool = False
    price_usd_cents: int = 19900  # Stripe: $199
    price_inr_paise: int = 999900  # Razorpay: ₹9,999 (GST-inclusive)
    gst_rate_pct: int = 18
    seller_gstin: str = ""  # founder's GSTIN, set in production .env
    seller_state_code: str = "36"  # Telangana; first two GSTIN digits
    invoice_prefix: str = "DBD"
    stripe_webhook_secret: str = ""
    razorpay_webhook_secret: str = ""

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
