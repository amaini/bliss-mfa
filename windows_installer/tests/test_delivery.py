"""End-to-end registered device -> release backend -> client verifier."""

import importlib.util
import json
import sys
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

REPO = Path(__file__).parents[2]
sys.path.insert(0, str(REPO / "apps/license-server"))
spec = importlib.util.spec_from_file_location(
    "delivery_manager", REPO / "windows_installer/manager.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_registered_client_receives_only_approved_signed_update(tmp_path, monkeypatch):
    from license_server.config import get_settings
    from license_server.crypto import b64url
    from license_server.db import Base, get_db
    from license_server.models import License, LicenseStatus, LicenseType

    signing = Ed25519PrivateKey.generate()
    keyfile = tmp_path / "server.key"
    keyfile.write_bytes(
        signing.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    monkeypatch.setenv("ADMIN_API_KEY", "delivery-admin")
    monkeypatch.setenv("UPDATE_SIGNING_PRIVATE_KEY_FILE", str(keyfile))
    get_settings.cache_clear()
    from license_server.main import app

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    device = Ed25519PrivateKey.generate()
    device_id = "MFA-delivery"
    with Session(engine) as db:
        db.add(
            License(
                id="delivery",
                customer_name="Disposable",
                license_type=LicenseType.online,
                status=LicenseStatus.active,
                max_rdp_users=1,
                installation_id=device_id,
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
    backend = TestClient(app)
    state = tmp_path / "appliance/bliss-mfa/.local"
    updater, local_engine, license_state = (
        state / "updater",
        state / "engine",
        state / "license-state",
    )
    for folder in [updater, local_engine, license_state]:
        folder.mkdir(parents=True)
    (updater / "installation.json").write_text(
        json.dumps(
            {"updates_url": "https://backend.test", "sequence": 1, "channel": "preview"}
        )
    )
    (updater / "update-public.pem").write_bytes(
        signing.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    (local_engine / "appliance.json").write_text(
        json.dumps({"license_state_dir": str(license_state)})
    )
    (license_state / "installation.json").write_text(
        json.dumps({"installation_id": device_id})
    )
    (license_state / "device.key").write_text(
        b64url(
            device.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
        )
    )
    root = tmp_path / "appliance"

    def route(request):
        response = backend.request(
            request.method,
            request.url.path,
            content=request.content,
            headers={"content-type": "application/json"},
        )
        return httpx.Response(response.status_code, json=response.json())

    def transport():
        return httpx.Client(transport=httpx.MockTransport(route))

    try:
        admin = {"X-Bliss-License-Admin": "delivery-admin"}
        release = {
            "sequence": 2,
            "version": "0.2.0",
            "channel": "preview",
            "archive_url": "https://downloads.test/appliance.zip",
            "size": 100,
            "sha256": "a" * 64,
            "provider_sha256": m.PROVIDER_HASH,
        }
        assert (
            backend.post(
                "/v1/admin/updates/releases", headers=admin, json=release
            ).status_code
            == 201
        )
        assert m.check_backend(root, transport()) is None
        backend.put(
            "/v1/admin/updates/releases/2/rollout",
            headers=admin,
            json={"enabled": True, "rollout_percent": 100},
        )
        assert m.check_backend(root, transport())["sha256"] == release["sha256"]
        backend.put(
            "/v1/admin/updates/releases/2/rollout",
            headers=admin,
            json={"enabled": False, "rollout_percent": 100},
        )
        assert m.check_backend(root, transport()) is None
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()
