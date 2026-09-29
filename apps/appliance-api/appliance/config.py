from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite+pysqlite:///./appliance.db"
    jwt_secret: str = "change-me-development-only"
    jwt_minutes: int = 480
    setup_token: str | None = None
    company_name: str = "Bliss Secure MFA"
    multiotp_adapter_url: str = "http://multiotp-adapter:8090"
    multiotp_adapter_token: str | None = None
    license_agent_url: str = "http://license-agent:8091"
    local_portal_url: str = "http://127.0.0.1:9443"

@lru_cache
def get_settings() -> Settings:
    return Settings()
