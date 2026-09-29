from __future__ import annotations

from urllib.parse import quote

import httpx

from .config import get_settings


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
        response.raise_for_status()

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
        response.raise_for_status()
        return bool(response.json()["ok"])

    def command(self, username: str, command: str, payload: dict | None = None) -> bool:
        response = httpx.post(
            f"{self.base_url}/v1/users/{quote(username, safe='')}/{command}",
            json=payload,
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return bool(response.json()["ok"])

    def delete_user(self, username: str) -> bool:
        response = httpx.delete(
            f"{self.base_url}/v1/users/{quote(username, safe='')}",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return bool(response.json()["ok"])


class LicenseAgentClient:
    def __init__(self) -> None:
        self.base_url = get_settings().license_agent_url.rstrip("/")

    def status(self) -> dict:
        response = httpx.get(f"{self.base_url}/v1/status", timeout=10)
        response.raise_for_status()
        return response.json()

    def authorize_seat(self, current: int, delta: int = 1) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/authorize/rdp-seat",
            json={"current_protected_rdp_users": current, "delta": delta},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def activate_online(self, code: str) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/activate/online",
            json={"activation_code": code},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def offline_request(self, code: str) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/offline/request",
            json={"activation_code": code},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def offline_apply(self, response_code: str) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/offline/apply",
            json={"activation_response": response_code},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def heartbeat(self, seats: int, audit_head_hash: str | None = None) -> dict:
        response = httpx.post(
            f"{self.base_url}/v1/heartbeat",
            json={"protected_rdp_users": seats, "audit_head_hash": audit_head_hash},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()



    def offline_release_code(self) -> str:
        response = httpx.post(f"{self.base_url}/v1/offline/release-code", timeout=10)
        response.raise_for_status()
        return str(response.json()["release_code"])

    def billing_portal(self) -> str:
        response = httpx.post(f"{self.base_url}/v1/billing/portal", timeout=20)
        response.raise_for_status()
        return str(response.json()["url"])

    def release(self) -> dict:
        response = httpx.post(f"{self.base_url}/v1/release", timeout=20)
        response.raise_for_status()
        return response.json()
