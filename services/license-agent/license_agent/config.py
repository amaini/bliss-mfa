from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    license_server_url: str = "https://license.blissitek.ca"
    state_dir: str = "/var/lib/bliss-mfa/license"
    bliss_signing_public_key_pem: str | None = None
    software_version: str = "0.1.0"
    heartbeat_timeout_seconds: int = 15

@lru_cache
def get_settings() -> Settings:
    return Settings()
