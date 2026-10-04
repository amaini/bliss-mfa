import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_agent.config import get_settings
from license_agent.state import LicenseState, b64url, canonical_json


def licensed_state(tmp_path, monkeypatch, status="active", expired=False):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("BLISS_SIGNING_PUBLIC_KEY_PEM", key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
    get_settings.cache_clear()
    state = LicenseState(str(tmp_path))
    now = datetime.now(UTC)
    payload = {"installation_id": state.installation_id(), "license_id": "lic_concurrent",
               "license_type": "online", "state": status, "max_rdp_users": 3,
               "issued_at": (now - timedelta(days=2)).isoformat(),
               "lease_expires_at": (now + timedelta(days=-1 if expired else 1)).isoformat(),
               "grace_expires_at": (now + timedelta(days=20)).isoformat()}
    body = canonical_json(payload)
    state.save_lease(b64url(canonical_json({"payload": b64url(body), "signature": b64url(key.sign(body))})))
    return state


def test_parallel_reservations_cannot_exceed_limit(tmp_path, monkeypatch):
    state = licensed_state(tmp_path, monkeypatch)
    with ThreadPoolExecutor(max_workers=12) as workers:
        results = list(workers.map(lambda i: LicenseState(str(tmp_path)).reserve_seat(f"user{i}"), range(30)))
    assert sum(result["allowed"] for result in results) == 3
    assert state.seat_count() == 3


def test_parallel_releases_do_not_lose_updates(tmp_path, monkeypatch):
    state = licensed_state(tmp_path, monkeypatch)
    for i in range(3):
        state.reserve_seat(f"user{i}")
    with ThreadPoolExecutor(max_workers=3) as workers:
        list(workers.map(lambda i: LicenseState(str(tmp_path)).release_seat(f"user{i}"), range(3)))
    assert state.seat_count() == 0


def test_suspended_lease_does_not_become_grace_access(tmp_path, monkeypatch):
    state = licensed_state(tmp_path, monkeypatch, "suspended", expired=True)
    assert state.effective_status()["state"] == "suspended"
    assert state.reserve_seat("newuser")["allowed"] is False


def test_existing_reservation_cannot_bypass_restricted_license(tmp_path, monkeypatch):
    state = licensed_state(tmp_path, monkeypatch)
    assert state.reserve_seat("alice")["allowed"] is True
    state.clear_lease()
    assert state.reserve_seat("alice")["allowed"] is False


def test_legacy_seats_import_once_and_corruption_fails_closed(tmp_path, monkeypatch):
    state = licensed_state(tmp_path, monkeypatch)
    state.seat_state_path.write_text(json.dumps({"seats": [state.seat_id("alice")]}))
    assert state.has_seat("alice")
    state.release_seat("alice")
    assert not state.has_seat("alice")
    other = LicenseState(str(tmp_path / "corrupt"))
    other.seat_state_path.write_text("broken-json")
    with pytest.raises(ValueError):
        other.seat_count()
