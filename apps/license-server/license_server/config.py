from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite+pysqlite:///./licenses.db"
    admin_api_key: str | None = None

    # PEM encoded Ed25519 private key. Generate once and keep only in Bliss infrastructure.
    signing_private_key_pem: str | None = None
    signing_private_key_file: str | None = None

    update_signing_private_key_file: str | None = None

    online_lease_days: int = 14
    online_grace_days: int = 30
    offline_default_days: int = 365

    stripe_secret_key: str | None = None
    stripe_return_url: str = "https://license.blissitek.ca/billing/return"


@lru_cache
def get_settings() -> Settings:
    return Settings()
