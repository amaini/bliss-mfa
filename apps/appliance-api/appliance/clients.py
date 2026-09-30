from __future__ import annotations

from urllib.parse import quote

import httpx

from .config import get_settings


class AdapterOperationError(RuntimeError):
    def __init__(self, *, authentication_disabled: bool = False) -> None:
        super().__init__("MFA engine rejected the operation")
        self.authentication_disabled = authentication_disabled


def operation_ok(response: httpx.Response) -> bool:
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("Invalid MFA engine response") from exc
    if not isinstance(body, dict) or type(body.get("ok")) is not bool:
        raise RuntimeError("Invalid MFA engine operation result")
    if not body["ok"] and body.get("authentication_disabled") is True:
        raise AdapterOperationError(authentication_disabled=True)
    return body["ok"]


class MultiOtpClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.multiotp_adapter_url.rstrip("/")
        self.token = settings.multiotp_adapter_token

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("multiOTP adapter token is not configured")
        return {"authorization": f"Bearer {self.token}"}

    def create_user(self, username: str) -> None:
        response = httpx.post(
            f"{self.base_url}/v1/users",
            json={"username": username},
            headers=self._headers(),
            timeout=15,
        )
        if not operation_ok(response):
            raise AdapterOperationError()

    def provisioning_uri(self, username: str) -> str:
        response = httpx.get(
            f"{self.base_url}/v1/users/{quote(username, safe='')}/provisioning",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return str(response.json()["provisioning_uri"])

    def verify(self, username: str, otp: str) -> bool:
        response = httpx.post(
            f"{self.base_url}/v1/users/{quote(username, safe='')}/verify",
            json={"otp": otp},
            headers=self._headers(),
            timeout=15,
        )
        return operation_ok(response)

    def command(self, username: str, command: str, payload: dict | None = None) -> bool:
        response = httpx.post(
            f"{self.base_url}/v1/users/{quote(username, safe='')}/{command}",
            json=payload,
            headers=self._headers(),
            timeout=15,
        )
        return operation_ok(response)

    def delete_user(self, username: str) -> bool:
        response = httpx.delete(
            f"{self.base_url}/v1/users/{quote(username, safe='')}",
            headers=self._headers(),
            timeout=15,
        )
        return operation_ok(response)


class LicenseAgentClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.license_agent_url.rstrip("/")
        self.token = settings.license_agent_token

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("License agent token is not configured")
        return {"authorization": f"Bearer {self.token}"}

    def status(self) -> dict:
        response = httpx.get(f"{self.base_url}/v1/status", headers=self._headers(), timeout=10)
        response.raise_for_status()
        return response.json()

    def authorize_seat(self, current: int, delta: int = 1) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/authorize/rdp-seat",
            json={"current_protected_rdp_users": current, "delta": delta},
            headers=self._headers(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def reserve_seat(self, username: str) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/seats/reserve",
            json={"username": username},
            headers=self._headers(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def release_seat(self, username: str) -> int:
        response = httpx.post(
            f"{self.base_url}/v1/seats/release",
            json={"username": username},
            headers=self._headers(),
            timeout=10,
        )
        response.raise_for_status()
        return int(response.json()["seat_count"])

    def activate_online(self, code: str) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/activate/online",
            json={"activation_code": code},
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def offline_request(self, code: str) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/offline/request",
            json={"activation_code": code},
            headers=self._headers(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def offline_apply(self, response_code: str) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/offline/apply",
            json={"activation_response": response_code},
            headers=self._headers(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def heartbeat(self, seats: int, audit_head_hash: str | None = None) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/heartbeat",
            json={"protected_rdp_users": seats, "audit_head_hash": audit_head_hash},
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()



    def offline_release_code(self) -> str:
        response = httpx.post(f"{self.base_url}/v1/offline/release-code", headers=self._headers(), timeout=10)
        response.raise_for_status()
        return str(response.json()["release_code"])

    def billing_portal(self) -> str:
        response = httpx.post(f"{self.base_url}/v1/billing/portal", headers=self._headers(), timeout=20)
        response.raise_for_status()
        return str(response.json()["url"])

    def release(self) -> dict:
        response = httpx.post(f"{self.base_url}/v1/release", headers=self._headers(), timeout=20)
        response.raise_for_status()
        return response.json()
