from __future__ import annotations

import base64
import json
import hashlib
import os
import platform
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .config import get_settings


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LicenseState:
    def __init__(self, state_dir: str | None = None) -> None:
        self.root = Path(state_dir or get_settings().state_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    @property
    def installation_path(self) -> Path:
        return self.root / "installation.json"

    @property
    def private_key_path(self) -> Path:
        return self.root / "device.key"

    @property
    def lease_path(self) -> Path:
        return self.root / "lease.token"

    @property
    def trusted_time_path(self) -> Path:
        return self.root / "trusted-time.json"

    @property
    def release_tombstone_path(self) -> Path:
        return self.root / "released.json"

    def installation_id(self) -> str:
        if self.installation_path.exists():
            return json.loads(self.installation_path.read_text())["installation_id"]

        installation_id = f"MFA-{uuid.uuid4()}"
        self._atomic_json(self.installation_path, {"installation_id": installation_id})
        return installation_id

    def device_key(self) -> Ed25519PrivateKey:
        if self.private_key_path.exists():
            raw = b64url_decode(self.private_key_path.read_text().strip())
            return Ed25519PrivateKey.from_private_bytes(raw)

        key = Ed25519PrivateKey.generate()
        raw = key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._atomic_text(self.private_key_path, b64url(raw))
        try:
            os.chmod(self.private_key_path, 0o600)
        except OSError:
            pass
        return key

    def public_key_b64(self) -> str:
        public = self.device_key().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return b64url(public)

    def sign(self, payload: dict[str, Any]) -> str:
        return b64url(self.device_key().sign(canonical_json(payload)))

    def machine_fingerprint(self) -> str:
        parts = [platform.node(), platform.system(), platform.machine()]
        machine_id = Path("/etc/machine-id")
        if machine_id.exists():
            try:
                parts.append(machine_id.read_text().strip())
            except OSError:
                pass
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def save_lease(self, token: str) -> None:
        # Verify before storing so a corrupt/forged response never becomes trusted local state.
        payload = self.verify_lease(token)
        if self.release_tombstone_path.exists():
            try:
                tombstone = json.loads(self.release_tombstone_path.read_text())
                if tombstone.get("license_id") == payload.get("license_id"):
                    raise ValueError("This installation has already released this license")
            except json.JSONDecodeError:
                raise ValueError("Local release state is invalid")
        self._atomic_text(self.lease_path, token)
        issued_at = parse_time(payload["issued_at"])
        self.update_trusted_time(issued_at)

    def load_lease(self) -> str | None:
        if not self.lease_path.exists():
            return None
        return self.lease_path.read_text().strip()

    def clear_lease(self) -> None:
        self.lease_path.unlink(missing_ok=True)

    def create_offline_release_code(self) -> str:
        token = self.load_lease()
        if not token:
            raise ValueError("No license is installed")
        payload = self.verify_lease(token)
        if payload.get("license_type") != "offline":
            raise ValueError("Installed license is not offline")
        message = {
            "v": 1,
            "action": "offline_release",
            "license_id": payload["license_id"],
            "installation_id": self.installation_id(),
            "nonce": b64url(os.urandom(24)),
        }
        envelope = {
            "message": message,
            "signature": self.sign(message),
        }
        code = b64url(canonical_json(envelope))
        self._atomic_json(
            self.release_tombstone_path,
            {
                "license_id": payload["license_id"],
                "released_at": utcnow().isoformat(),
            },
        )
        self.clear_lease()
        return code

    def verify_lease(self, token: str) -> dict[str, Any]:
        settings = get_settings()
        pem = settings.bliss_signing_public_key_pem
        if not pem and settings.bliss_signing_public_key_file:
            pem = Path(settings.bliss_signing_public_key_file).read_text()
        if not pem:
            raise RuntimeError("Bliss signing public key is not configured")

        outer = json.loads(b64url_decode(token))
        payload_bytes = b64url_decode(outer["payload"])
        signature = b64url_decode(outer["signature"])
        key = serialization.load_pem_public_key(pem.encode())
        if not isinstance(key, Ed25519PublicKey):
            raise RuntimeError("Bliss signing public key must be Ed25519")
        try:
            key.verify(signature, payload_bytes)
        except InvalidSignature as exc:
            raise ValueError("Invalid Bliss license signature") from exc

        payload = json.loads(payload_bytes)
        if payload.get("installation_id") != self.installation_id():
            raise ValueError("License belongs to a different installation")
        return payload

    def effective_status(self) -> dict[str, Any]:
        token = self.load_lease()
        if not token:
            return {
                "state": "unlicensed",
                "max_rdp_users": 0,
                "license_type": None,
                "license_id": None,
            }

        try:
            payload = self.verify_lease(token)
        except (ValueError, RuntimeError, KeyError, json.JSONDecodeError):
            return {
                "state": "invalid",
                "max_rdp_users": 0,
                "license_type": None,
                "license_id": None,
            }

        now = self.trusted_now()
        state = str(payload.get("state", "restricted"))
        lease_expires = parse_time(payload["lease_expires_at"])
        grace_raw = payload.get("grace_expires_at")
        grace_expires = parse_time(grace_raw) if grace_raw else None

        if state == "revoked":
            effective = "revoked"
        elif now <= lease_expires:
            effective = state
        elif grace_expires and now <= grace_expires:
            effective = "offline_grace"
        else:
            effective = "restricted"

        return {
            **payload,
            "state": effective,
            "trusted_now": now.isoformat(),
        }

    def update_trusted_time(self, server_time: datetime) -> None:
        current = self._read_trusted_time()
        value = max(current, server_time) if current else server_time
        self._atomic_json(self.trusted_time_path, {"trusted_time": value.isoformat()})

    def trusted_now(self) -> datetime:
        system_now = utcnow()
        trusted = self._read_trusted_time()
        # A rolled-back system clock cannot make a lease live longer than the most
        # recent signed server time already observed.
        return max(system_now, trusted) if trusted else system_now

    def _read_trusted_time(self) -> datetime | None:
        if not self.trusted_time_path.exists():
            return None
        try:
            value = json.loads(self.trusted_time_path.read_text())["trusted_time"]
            return parse_time(value)
        except (ValueError, KeyError, json.JSONDecodeError):
            return None

    def _atomic_text(self, path: Path, value: str) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(value)
        os.replace(temp, path)

    def _atomic_json(self, path: Path, value: dict[str, Any]) -> None:
        self._atomic_text(path, json.dumps(value, separators=(",", ":")))


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
