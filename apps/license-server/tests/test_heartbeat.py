"""Heartbeat: numeric usage visibility and tamper evidence without changing entitlement."""
import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from license_server import main
from license_server.config import get_settings
from license_server.crypto import canonical_json
from license_server.db import Base, get_db
from license_server.models import ActivationEvent, License

ADMIN = {"X-Bliss-License-Admin": "admin-test-key"}


def b64url(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


@pytest.fixture
def server(monkeypatch, database_engine):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN["X-Bliss-License-Admin"])
    monkeypatch.setenv("SIGNING_PRIVATE_KEY_PEM", Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
    get_settings.cache_clear()
    monkeypatch.setattr(main, "settings", get_settings())
    Base.metadata.create_all(database_engine)

    def database():
        with Session(database_engine, expire_on_commit=False) as db:
            yield db

    main.app.dependency_overrides[get_db] = database
    with TestClient(main.app) as client:
        yield client, database_engine
    main.app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def appliance(server):
    client, engine = server
    created = client.post("/v1/admin/licenses", headers=ADMIN, json={
        "customer_name": "Pilot Office", "license_type": "online", "max_rdp_users": 2}).json()
    key = Ed25519PrivateKey.generate()
    public = b64url(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    installation = "MFA-heartbeat-test"
    response = client.post("/v1/activate/online", json={
        "activation_code": created["activation_code"], "installation_id": installation,
        "installation_public_key": public})
    assert response.status_code == 200, response.text

    def heartbeat(seats, fingerprint="f" * 64):
        nonce = client.post("/v1/challenges", json={"installation_id": installation}).json()["nonce"]
        message = {"installation_id": installation, "nonce": nonce, "protected_rdp_users": seats,
                   "software_version": "0.1.3", "machine_fingerprint": fingerprint, "audit_head_hash": None}
        return client.post("/v1/heartbeat", json={**message, "signature": b64url(key.sign(canonical_json(message)))})

    def events():
        with Session(engine) as db:
            return [e.event_type for e in db.scalars(select(ActivationEvent).where(
                ActivationEvent.license_id == created["license_id"]))]

    def license():
        with Session(engine) as db:
            return db.get(License, created["license_id"])

    return heartbeat, events, license


def lease_payload(response):
    envelope = json.loads(base64.urlsafe_b64decode(response.json()["signed_lease"] + "=="))
    return json.loads(base64.urlsafe_b64decode(envelope["payload"] + "=="))


def test_heartbeat_records_reported_usage_and_version(appliance):
    heartbeat, _, license = appliance
    assert heartbeat(1).status_code == 200
    assert license().last_reported_seats == 1
    assert license().last_software_version == "0.1.3"


def test_overage_is_recorded_as_evidence_without_changing_entitlement(appliance):
    heartbeat, events, license = appliance
    response = heartbeat(5)
    assert response.status_code == 200
    assert "license.seat_overage_reported" in events()
    assert lease_payload(response)["max_rdp_users"] == 2
    assert lease_payload(response)["state"] == "active"
    assert license().last_reported_seats == 5


def test_changed_machine_fingerprint_is_logged_but_never_blocks_renewal(appliance):
    # Hostname changes (for example after container recreation) must not break licensing.
    heartbeat, events, _ = appliance
    assert heartbeat(1, fingerprint="a" * 64).status_code == 200
    assert heartbeat(1, fingerprint="b" * 64).status_code == 200
    assert "installation.fingerprint_changed" in events()
