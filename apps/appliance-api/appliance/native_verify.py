"""Verify a code through the installed Windows multiOTP client: the same path RDP sign-in uses."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .config import get_settings

settings = get_settings()


class NativeVerifyUnavailable(RuntimeError):
    pass


def provider_client() -> str:
    from .rdp_protection import ProviderRegistry
    try:
        base = ProviderRegistry().backend.get("multiOTPPath")
    except (OSError, ImportError) as exc:
        raise NativeVerifyUnavailable("Windows multiOTP client is not installed") from exc
    if not base:
        raise NativeVerifyUnavailable("Windows multiOTP client is not installed")
    return str(Path(str(base)) / "multiotp.exe")


def native_verify(username: str, otp: str, *, run=subprocess.run, client: str | None = None) -> bool:
    if not re.fullmatch(r"\d{6}", otp):
        raise ValueError("Enter a six-digit code")
    if not settings.engine_config_file or not settings.provider_validation_dir:
        raise NativeVerifyUnavailable("Engine configuration is not available")
    config = json.loads(Path(settings.engine_config_file).read_text(encoding="utf-8-sig"))
    base = Path(settings.provider_validation_dir)
    base.mkdir(parents=True, exist_ok=True)
    # No trailing backslash: multiotp.exe re-quotes arguments and \" would corrupt the path.
    args = [client or provider_client(), "-cp", "-base-dir=" + str(base).rstrip("\\/"),
            "-server-cache-level=0", "-server-timeout=5",
            f"-server-url=https://127.0.0.1:{config['auth_port']}/auth",
            f"-server-secret={config['native_shared_secret']}", username, otp]
    result = run(args, capture_output=True, text=True, timeout=30, check=False)
    return result.returncode == 0
