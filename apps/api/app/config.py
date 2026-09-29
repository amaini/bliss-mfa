from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "Bliss Secure MFA API"
    database_url: str = "sqlite+pysqlite:///./bliss_mfa.db"
    redis_url: str = "redis://localhost:6379/0"

    multiotp_mode: str = "mock"
    multiotp_base_url: str | None = None
    multiotp_adapter_url: str | None = None
    multiotp_adapter_token: str | None = None
    multiotp_api_username: str | None = None
    multiotp_api_password: str | None = None

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_starter: str | None = None
    stripe_price_business: str | None = None
    stripe_price_business_plus: str | None = None
    portal_base_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000"

    enrollment_ttl_minutes: int = Field(default=15, ge=5, le=120)
    bliss_bootstrap_api_key: str | None = None

    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_groups_claim: str = "groups"
    oidc_staff_admin_group: str = "bliss-mfa-super-admin"
    oidc_staff_technician_group: str = "bliss-mfa-technician"
    oidc_staff_billing_group: str = "bliss-mfa-billing"


@lru_cache
def get_settings() -> Settings:
    return Settings()
