import base64
import json
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_agent.config import get_settings
from license_agent.state import LicenseState, b64url, canonical_json


def make_lease(private_key, payload):
    body = canonical_json(payload)
    envelope = {
        "payload": b64url(body),
        "signature": b64url(private_key.sign(body)),
    }
    return b64url(canonical_json(envelope))


def test_signed_lease_is_bound_to_installation(tmp_path, monkeypatch):
    signing_key = Ed25519PrivateKey.generate()
    public_pem = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("BLISS_SIGNING_PUBLIC_KEY_PEM", public_pem)
    get_settings.cache_clear()

    state = LicenseState(str(tmp_path))
    now = datetime.now(timezone.utc)
    payload = {
        "v": 1,
        "license_id": "lic_test",
        "license_type": "online",
        "installation_id": state.installation_id(),
        "state": "active",
        "max_rdp_users": 25,
        "issued_at": now.isoformat(),
        "lease_expires_at": (now + timedelta(days=14)).isoformat(),
        "grace_expires_at": (now + timedelta(days=30)).isoformat(),
        "features": {"rdp_mfa": True},
    }
    token = make_lease(signing_key, payload)
    state.save_lease(token)

    status = state.effective_status()
    assert status["state"] == "active"
    assert status["max_rdp_users"] == 25


def test_tampered_lease_is_rejected(tmp_path, monkeypatch):
    signing_key = Ed25519PrivateKey.generate()
    public_pem = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("BLISS_SIGNING_PUBLIC_KEY_PEM", public_pem)
    get_settings.cache_clear()

    state = LicenseState(str(tmp_path))
    now = datetime.now(timezone.utc)
    payload = {
        "v": 1,
        "license_id": "lic_test",
        "license_type": "offline",
        "installation_id": state.installation_id(),
        "state": "active",
        "max_rdp_users": 10,
        "issued_at": now.isoformat(),
        "lease_expires_at": (now + timedelta(days=365)).isoformat(),
        "grace_expires_at": None,
        "features": {},
    }
    token = make_lease(signing_key, payload)

    outer = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    decoded = json.loads(base64.urlsafe_b64decode(outer["payload"] + "=" * (-len(outer["payload"]) % 4)))
    decoded["max_rdp_users"] = 999
    outer["payload"] = b64url(canonical_json(decoded))
    tampered = b64url(canonical_json(outer))

    try:
        state.save_lease(tampered)
        assert False, "tampered lease must fail"
    except ValueError:
        pass



def test_identity_bound_rdp_seat_enforcement(tmp_path, monkeypatch):
    signing_key = Ed25519PrivateKey.generate()
    public_pem = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("BLISS_SIGNING_PUBLIC_KEY_PEM", public_pem)
    get_settings.cache_clear()

    state = LicenseState(str(tmp_path))
    now = datetime.now(timezone.utc)
    payload = {
        "v": 1,
        "license_id": "lic_seats",
        "license_type": "online",
        "installation_id": state.installation_id(),
        "state": "active",
        "max_rdp_users": 2,
        "issued_at": now.isoformat(),
        "lease_expires_at": (now + timedelta(days=14)).isoformat(),
        "grace_expires_at": (now + timedelta(days=30)).isoformat(),
        "features": {"rdp_mfa": True},
    }
    state.save_lease(make_lease(signing_key, payload))

    assert state.reserve_seat("alice")["allowed"] is True
    duplicate = state.reserve_seat("ALICE")
    assert duplicate["allowed"] is True
    assert duplicate["already_reserved"] is True
    assert state.reserve_seat("bob")["allowed"] is True
    assert state.reserve_seat("charlie")["allowed"] is False
    assert state.seat_count() == 2

    assert state.release_seat("alice") == 1
    assert state.reserve_seat("charlie")["allowed"] is True
    assert state.seat_count() == 2


def test_restricted_license_cannot_reserve_new_seat(tmp_path, monkeypatch):
    signing_key = Ed25519PrivateKey.generate()
    public_pem = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("BLISS_SIGNING_PUBLIC_KEY_PEM", public_pem)
    get_settings.cache_clear()

    state = LicenseState(str(tmp_path))
    now = datetime.now(timezone.utc)
    payload = {
        "v": 1,
        "license_id": "lic_expired",
        "license_type": "offline",
        "installation_id": state.installation_id(),
        "state": "active",
        "max_rdp_users": 25,
        "issued_at": (now - timedelta(days=366)).isoformat(),
        "lease_expires_at": (now - timedelta(days=1)).isoformat(),
        "grace_expires_at": None,
        "features": {"rdp_mfa": True},
    }
    state.save_lease(make_lease(signing_key, payload))

    assert state.effective_status()["state"] == "restricted"
    denied = state.reserve_seat("newuser")
    assert denied["allowed"] is False
    assert "does not allow" in denied["reason"]
