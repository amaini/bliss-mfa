import base64
import hashlib
import json
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from license_server.config import get_settings
from license_server.crypto import b64url, canonical_json
from license_server.db import Base, get_db
from license_server.models import License, LicenseStatus, LicenseType


@pytest.fixture
def api(tmp_path, monkeypatch):
    release_key = Ed25519PrivateKey.generate()
    keyfile = tmp_path / "release.key"
    keyfile.write_bytes(
        release_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin")
    monkeypatch.setenv("UPDATE_SIGNING_PRIVATE_KEY_FILE", str(keyfile))
    get_settings.cache_clear()
    from license_server.main import app

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    device = Ed25519PrivateKey.generate()
    with Session(engine) as db:
        db.add(
            License(
                id="fixture",
                customer_name="Test",
                license_type=LicenseType.online,
                status=LicenseStatus.active,
                max_rdp_users=1,
                installation_id="MFA-fixture",
                installation_public_key=b64url(
                    device.public_key().public_bytes(
                        serialization.Encoding.Raw, serialization.PublicFormat.Raw
                    )
                ),
            )
        )
        db.commit()

    def session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = session
    yield TestClient(app), device, release_key
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    engine.dispose()


ADMIN = {"X-Bliss-License-Admin": "test-admin"}
RELEASE = {
    "sequence": 1,
    "version": "0.2.0",
    "channel": "stable",
    "archive_url": "https://downloads.test/BlissMFA.zip",
    "sha256": "a" * 64,
    "size": 123,
    "provider_sha256": "b" * 64,
}


def query(client, device, current=0):
    nonce = client.post("/v1/challenges", json={"installation_id": "MFA-fixture"}).json()["nonce"]
    message = {
        "action": "update-check",
        "installation_id": "MFA-fixture",
        "nonce": nonce,
        "channel": "stable",
        "current_sequence": current,
    }
    payload = {k: v for k, v in message.items() if k != "action"}
    payload["signature"] = b64url(device.sign(canonical_json(message)))
    return payload


def test_publish_requires_admin_and_https(api):
    client, _, _ = api
    assert client.post("/v1/admin/updates/releases", json=RELEASE).status_code == 401
    assert (
        client.post(
            "/v1/admin/updates/releases",
            json={**RELEASE, "archive_url": "http://downloads.test/x"},
            headers=ADMIN,
        ).status_code
        == 422
    )
    assert client.post("/v1/admin/updates/releases", json=RELEASE, headers=ADMIN).status_code == 201
    assert (
        client.post(
            "/v1/admin/updates/releases", json={**RELEASE, "version": "0.3.0"}, headers=ADMIN
        ).status_code
        == 409
    )


def test_staged_release_then_backend_rollout_and_withdrawal(api):
    client, device, signer = api
    assert client.post("/v1/admin/updates/releases", json=RELEASE, headers=ADMIN).status_code == 201
    assert client.post("/v1/updates/check", json=query(client, device)).json() == {"update": None}
    assert (
        client.put(
            "/v1/admin/updates/releases/1/rollout",
            json={"enabled": True, "rollout_percent": 100},
            headers=ADMIN,
        ).status_code
        == 200
    )
    payload = query(client, device)
    envelope = client.post("/v1/updates/check", json=payload).json()["update"]
    decode = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    body = decode(envelope["payload"])
    signer.public_key().verify(decode(envelope["signature"]), body)
    descriptor = json.loads(body)
    assert descriptor["sha256"] == RELEASE["sha256"]
    assert datetime.fromisoformat(descriptor["expires_at"]) > datetime.now(UTC)
    assert client.post("/v1/updates/check", json=payload).status_code == 401  # challenge replay
    assert client.post("/v1/updates/check", json=query(client, device, 1)).json() == {
        "update": None
    }
    client.put(
        "/v1/admin/updates/releases/1/rollout",
        json={"enabled": False, "rollout_percent": 100},
        headers=ADMIN,
    )
    assert client.post("/v1/updates/check", json=query(client, device)).json() == {"update": None}


def test_forged_device_signature_is_rejected(api):
    client, device, _ = api
    payload = query(client, device)
    payload["current_sequence"] = 999
    assert client.post("/v1/updates/check", json=payload).status_code == 401


def test_stable_rollout_bucket(api):
    client, device, _ = api
    client.post("/v1/admin/updates/releases", json=RELEASE, headers=ADMIN)
    bucket = int.from_bytes(hashlib.sha256(b"MFA-fixture").digest()[:4], "big") % 100
    client.put(
        "/v1/admin/updates/releases/1/rollout",
        json={"enabled": True, "rollout_percent": bucket},
        headers=ADMIN,
    )
    assert client.post("/v1/updates/check", json=query(client, device)).json() == {"update": None}
    client.put(
        "/v1/admin/updates/releases/1/rollout",
        json={"enabled": True, "rollout_percent": bucket + 1},
        headers=ADMIN,
    )
    assert client.post("/v1/updates/check", json=query(client, device)).json()["update"] is not None
