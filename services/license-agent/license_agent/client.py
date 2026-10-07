from __future__ import annotations

import httpx

from .config import get_settings
from .state import LicenseState, canonical_json


class LicenseServerClient:
    def __init__(self, state: LicenseState | None = None) -> None:
        self.settings = get_settings()
        self.state = state or LicenseState()

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.license_server_url.rstrip("/"),
            timeout=self.settings.heartbeat_timeout_seconds,
        )

    def activate_online(self, activation_code: str) -> dict:
        payload = {
            "activation_code": activation_code,
            "installation_id": self.state.installation_id(),
            "installation_public_key": self.state.public_key_b64(),
        }
        with self._client() as client:
            response = client.post("/v1/activate/online", json=payload)
            response.raise_for_status()
            data = response.json()
        self.state.save_lease(data["signed_lease"])
        return data

    def heartbeat(self, protected_rdp_users: int, audit_head_hash: str | None = None) -> dict:
        installation_id = self.state.installation_id()
        with self._client() as client:
            challenge = client.post(
                "/v1/challenges",
                json={"installation_id": installation_id},
            )
            challenge.raise_for_status()
            nonce = challenge.json()["nonce"]
            message = {
                "installation_id": installation_id,
                "nonce": nonce,
                "protected_rdp_users": protected_rdp_users,
                "software_version": self.settings.software_version,
                "machine_fingerprint": self.state.machine_fingerprint(),
                "audit_head_hash": audit_head_hash,
            }
            response = client.post(
                "/v1/heartbeat",
                json={
                    **message,
                    "signature": self.state.sign(message),
                },
            )
            response.raise_for_status()
            data = response.json()
        self.state.save_lease(data["signed_lease"])
        return data

    def release(self) -> dict:
        installation_id = self.state.installation_id()
        with self._client() as client:
            challenge = client.post(
                "/v1/challenges",
                json={"installation_id": installation_id},
            )
            challenge.raise_for_status()
            nonce = challenge.json()["nonce"]
            message = {
                "installation_id": installation_id,
                "nonce": nonce,
                "action": "release",
            }
            response = client.post(
                "/v1/release",
                json={
                    **message,
                    "signature": self.state.sign(message),
                },
            )
            response.raise_for_status()
            data = response.json()
        self.state.clear_lease()
        return data

    def billing_portal(self) -> str:
        with self._client() as client:
            installation_id = self.state.installation_id()
            challenge = client.post("/v1/challenges", json={"installation_id": installation_id})
            challenge.raise_for_status()
            message = {"installation_id": installation_id,
                       "nonce": challenge.json()["nonce"], "action": "billing"}
            response = client.post(
                "/v1/billing/portal",
                json={"installation_id": installation_id, "nonce": message["nonce"],
                      "signature": self.state.sign(message)},
            )
            response.raise_for_status()
            return str(response.json()["url"])

    def offline_installation_code(self, activation_code: str) -> str:
        request = {
            "v": 1,
            "activation_code": activation_code,
            "installation_id": self.state.installation_id(),
            "installation_public_key": self.state.public_key_b64(),
        }
        from .state import b64url
        return b64url(canonical_json(request))

    def apply_offline_response(self, activation_response: str) -> dict:
        self.state.save_lease(activation_response)
        return self.state.effective_status()
