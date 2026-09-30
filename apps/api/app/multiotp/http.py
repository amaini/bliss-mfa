from __future__ import annotations

from urllib.parse import quote

import httpx

from .base import EngineUser, ProvisioningMaterial


class HttpMultiOtpAdapter:
    def __init__(self, base_url: str, shared_token: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"authorization": f"Bearer {shared_token}"}
        self.timeout = timeout

    def _path_user(self, username: str) -> str:
        return quote(username, safe="")

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = httpx.request(
            method,
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def list_users(self) -> list[EngineUser]:
        response = self._request("GET", "/v1/users")
        return [EngineUser(username=name) for name in response.json()["users"]]

    def get_user(self, username: str) -> EngineUser | None:
        for user in self.list_users():
            if user.username == username:
                return user
        return None

    def create_totp_user(self, username: str, *, email: str | None = None) -> None:
        response = self._request("POST", "/v1/users", json={"username": username})
        if not response.json().get("ok"):
            raise ValueError("multiOTP user creation failed")

    def begin_enrollment(self, username: str) -> ProvisioningMaterial:
        user = self._path_user(username)
        response = self._request("GET", f"/v1/users/{user}/provisioning")
        return ProvisioningMaterial(provisioning_uri=response.json()["provisioning_uri"])

    def verify_otp(self, username: str, otp: str) -> bool:
        user = self._path_user(username)
        response = self._request("POST", f"/v1/users/{user}/verify", json={"otp": otp})
        return bool(response.json().get("ok"))

    def unlock_user(self, username: str) -> None:
        self._mutate(username, "unlock")

    def disable_user(self, username: str) -> None:
        self._mutate(username, "disable")

    def enable_user(self, username: str) -> None:
        self._mutate(username, "enable")

    def resync_user(self, username: str, otp1: str, otp2: str) -> bool:
        user = self._path_user(username)
        response = self._request(
            "POST",
            f"/v1/users/{user}/resync",
            json={"otp1": otp1, "otp2": otp2},
        )
        return bool(response.json().get("ok"))

    def revoke_token(self, username: str) -> None:
        self._mutate(username, "revoke")

    def delete_user(self, username: str) -> None:
        user = self._path_user(username)
        response = self._request("DELETE", f"/v1/users/{user}")
        if not response.json().get("ok"):
            raise RuntimeError("multiOTP user deletion failed")

    def _mutate(self, username: str, operation: str) -> None:
        user = self._path_user(username)
        response = self._request("POST", f"/v1/users/{user}/{operation}")
        if not response.json().get("ok"):
            raise RuntimeError(f"multiOTP operation failed: {operation}")
