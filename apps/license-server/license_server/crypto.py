from __future__ import annotations

import base64
import json
from pathlib import Path
from datetime import datetime
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import get_settings


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def get_signing_key() -> Ed25519PrivateKey:
    settings = get_settings()
    pem = settings.signing_private_key_pem
    if not pem and settings.signing_private_key_file:
        pem = Path(settings.signing_private_key_file).read_text()
    if not pem:
        raise RuntimeError("License signing key is not configured")
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("License signing key must be Ed25519")
    return key


def sign_payload(payload: dict[str, Any]) -> str:
    body = canonical_json(payload)
    signature = get_signing_key().sign(body)
    envelope = {
        "payload": b64url(body),
        "signature": b64url(signature),
    }
    return b64url(canonical_json(envelope))


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")
