from __future__ import annotations

import re
import subprocess
from pathlib import Path
from dataclasses import dataclass

from .config import get_settings

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,255}$")
OTP_RE = re.compile(r"^[0-9]{4,16}$")


class AdapterInputError(ValueError):
    pass


class AdapterCommandError(RuntimeError):
    def __init__(self, message: str, *, returncode: int, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    authentication_disabled: bool = False


def validate_username(username: str) -> str:
    if not USERNAME_RE.fullmatch(username) or username.startswith("-"):
        raise AdapterInputError("Invalid username")
    return username


def validate_otp(otp: str) -> str:
    if not OTP_RE.fullmatch(otp):
        raise AdapterInputError("Invalid OTP format")
    return otp


class MultiOtpCliRunner:
    def __init__(self, executable: str | None = None) -> None:
        settings = get_settings()
        self.executable = executable or settings.multiotp_executable
        self.timeout = settings.command_timeout_seconds

    def run(self, *arguments: str) -> CommandResult:
        settings = get_settings()
        prefix = [self.executable]
        if settings.multiotp_php_executable:
            prefix = [settings.multiotp_php_executable]
            if settings.multiotp_php_extension_dir:
                prefix += ["-n", "-d", "extension_dir=" + settings.multiotp_php_extension_dir,
                           "-d", "extension=mbstring", "-d", "extension=openssl"]
            prefix.append(self.executable)
        if settings.multiotp_base_dir:
            prefix.append("-base-dir=" + Path(settings.multiotp_base_dir).resolve().as_posix() + "/")
        process = subprocess.run(
            [*prefix, *arguments],
            shell=False,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        return CommandResult(
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )

    def users_list(self) -> CommandResult:
        return self.run("-userslist")

    def user_info(self, username: str) -> CommandResult:
        return self.run("-user-info", validate_username(username))

    def create_totp_user(self, username: str) -> CommandResult:
        return self.run("-fastcreatenopin", validate_username(username))

    def provisioning_url(self, username: str) -> CommandResult:
        return self.run("-urllink", validate_username(username))

    def verify(self, username: str, otp: str) -> CommandResult:
        return self.run(validate_username(username), validate_otp(otp))

    def unlock(self, username: str) -> CommandResult:
        return self.run("-unlock", validate_username(username))

    def lock(self, username: str) -> CommandResult:
        return self.run("-lock", validate_username(username))

    def disable(self, username: str) -> CommandResult:
        return self.run("-deactivate", validate_username(username))

    def enable(self, username: str) -> CommandResult:
        return self.run("-activate", validate_username(username))

    def resync(self, username: str, otp1: str, otp2: str) -> CommandResult:
        return self.run(
            "-resync",
            validate_username(username),
            validate_otp(otp1),
            validate_otp(otp2),
        )

    def revoke_token(self, username: str) -> CommandResult:
        username = validate_username(username)
        disabled = self.disable(username)
        if disabled.returncode != 11:
            return disabled
        # Rotating a seed is not enough to revoke access. Keep the identity
        # disabled even if removal fails or times out after a partial mutation.
        try:
            removed = self.run("-remove-token", username)
        except (OSError, subprocess.TimeoutExpired):
            return CommandResult(99, "", "", authentication_disabled=True)
        return CommandResult(
            removed.returncode, removed.stdout, removed.stderr, authentication_disabled=True,
        )

    def delete_user(self, username: str) -> CommandResult:
        return self.run("-delete", validate_username(username))
