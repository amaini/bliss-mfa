from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EngineUser:
    username: str
    locked: bool = False
    delayed: bool = False
    active: bool = True


@dataclass(frozen=True)
class ProvisioningMaterial:
    # This object is intentionally ephemeral. Never persist or log these fields.
    provisioning_uri: str
    qr_svg: str | None = None


class MultiOtpAdapter(Protocol):
    def list_users(self) -> list[EngineUser]: ...

    def get_user(self, username: str) -> EngineUser | None: ...

    def create_totp_user(self, username: str, *, email: str | None = None) -> None: ...

    def begin_enrollment(self, username: str) -> ProvisioningMaterial: ...

    def verify_otp(self, username: str, otp: str) -> bool: ...

    def unlock_user(self, username: str) -> None: ...

    def disable_user(self, username: str) -> None: ...

    def enable_user(self, username: str) -> None: ...

    def resync_user(self, username: str, otp1: str, otp2: str) -> bool: ...

    def revoke_token(self, username: str) -> None: ...

    def delete_user(self, username: str) -> None: ...
