from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite+pysqlite:///./licenses.db"
    database_password_file: str | None = None
    require_sqlite_import: bool = False
    admin_api_key: str | None = None

    # PEM encoded Ed25519 private key. Generate once and keep only in Bliss infrastructure.
    signing_private_key_pem: str | None = None
    signing_private_key_file: str | None = None

    online_lease_days: int = 14
    online_grace_days: int = 30
    offline_default_days: int = 365

    stripe_secret_key: str | None = None
    stripe_return_url: str = "https://license.blissitek.ca/billing/return"
    stripe_webhook_secret: str | None = None
    stripe_rdp_price_id: str | None = None
    customer_portal_url: str = "http://127.0.0.1:8080"
    customer_session_hours: int = 8
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    resend_api_key: str | None = None
    mail_from: str = "Bliss MFA <noreply@blissitek.ca>"
    development_mail_dir: str = ".local/mail"
    appliance_release_file: str | None = None
    appliance_release_sha256: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
