from functools import lru_cache

from .config import get_settings
from .multiotp import HttpMultiOtpAdapter, MockMultiOtpAdapter, MultiOtpAdapter


@lru_cache
def get_multiotp_adapter() -> MultiOtpAdapter:
    settings = get_settings()

    if settings.multiotp_mode == "mock":
        if settings.app_env == "production":
            raise RuntimeError("The mock multiOTP adapter is disabled in production")
        return MockMultiOtpAdapter()

    if settings.multiotp_mode == "http":
        if not settings.multiotp_adapter_url or not settings.multiotp_adapter_token:
            raise RuntimeError("The multiOTP sidecar URL/token are not configured")
        return HttpMultiOtpAdapter(
            settings.multiotp_adapter_url,
            settings.multiotp_adapter_token,
        )

    raise RuntimeError(f"Unsupported multiOTP adapter mode: {settings.multiotp_mode}")
