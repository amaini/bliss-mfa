from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    adapter_mode: str = "cli"
    multiotp_executable: str = "/usr/local/bin/multiotp/multiotp.php"
    command_timeout_seconds: float = 15.0
    adapter_shared_token: str | None = None
    adapter_enable_writes: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
