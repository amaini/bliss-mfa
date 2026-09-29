from __future__ import annotations

import secrets

from .base import EngineUser, ProvisioningMaterial


class MockMultiOtpAdapter:
    """Development-only adapter.

    It deliberately stores no real MFA seed and must never be used as an
    authentication backend in production.
    """

    def __init__(self) -> None:
        self._users: dict[str, EngineUser] = {}

    def list_users(self) -> list[EngineUser]:
        return list(self._users.values())

    def get_user(self, username: str) -> EngineUser | None:
        return self._users.get(username)

    def create_totp_user(self, username: str, *, email: str | None = None) -> None:
        if username in self._users:
            raise ValueError("user already exists")
        self._users[username] = EngineUser(username=username)

    def begin_enrollment(self, username: str) -> ProvisioningMaterial:
        if username not in self._users:
            raise KeyError(username)
        nonce = secrets.token_urlsafe(24)
        return ProvisioningMaterial(provisioning_uri=f"otpauth://totp/mock:{username}?mock={nonce}")

    def verify_otp(self, username: str, otp: str) -> bool:
        if username not in self._users:
            return False
        return otp == "000000"

    def unlock_user(self, username: str) -> None:
        user = self._require(username)
        self._users[username] = EngineUser(username=user.username, active=user.active)

    def disable_user(self, username: str) -> None:
        user = self._require(username)
        self._users[username] = EngineUser(username=user.username, active=False)

    def enable_user(self, username: str) -> None:
        user = self._require(username)
        self._users[username] = EngineUser(username=user.username, active=True)

    def resync_user(self, username: str, otp1: str, otp2: str) -> bool:
        self._require(username)
        return otp1 != otp2 and otp1.isdigit() and otp2.isdigit()

    def revoke_token(self, username: str) -> None:
        self._require(username)

    def delete_user(self, username: str) -> None:
        self._require(username)
        del self._users[username]

    def _require(self, username: str) -> EngineUser:
        user = self._users.get(username)
        if user is None:
            raise KeyError(username)
        return user
