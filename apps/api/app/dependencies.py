from functools import lru_cache

from .config import get_settings
from .multiotp import MockMultiOtpAdapter, MultiOtpAdapter


@lru_cache
def get_multiotp_adapter() -> MultiOtpAdapter:
    settings = get_settings()
    if settings.multiotp_mode == "mock" and settings.app_env != "production":
        return MockMultiOtpAdapter()

    raise RuntimeError(
        "A production multiOTP adapter has not been configured. "
        "The mock adapter is intentionally disabled in production."
    )
