import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from license_agent import main
from license_agent.client import LicenseServerClient
from license_agent.config import get_settings
from license_agent.state import LicenseState, b64url, canonical_json

TOKEN = "agent-test-token"


@pytest.fixture
def agent(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("BLISS_SIGNING_PUBLIC_KEY_PEM", key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
    monkeypatch.setenv("AGENT_SHARED_TOKEN", TOKEN)
    # Nothing listens on the discard port: the Bliss licensing server is unreachable.
    monkeypatch.setenv("LICENSE_SERVER_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("HEARTBEAT_TIMEOUT_SECONDS", "2")
    get_settings.cache_clear()
    state = LicenseState(str(tmp_path))
    state.public_key_b64()  # activation creates the device identity before the first lease
    now = datetime.now(UTC)
    payload = {"installation_id": state.installation_id(), "license_id": "lic_outage",
               "license_type": "online", "state": "active", "max_rdp_users": 2,
               "issued_at": now.isoformat(),
               "lease_expires_at": (now + timedelta(days=14)).isoformat(),
               "grace_expires_at": (now + timedelta(days=30)).isoformat()}
    body = canonical_json(payload)
    state.save_lease(b64url(canonical_json({"payload": b64url(body), "signature": b64url(key.sign(body))})))
    monkeypatch.setattr(main, "state", state)
    monkeypatch.setattr(main, "client", LicenseServerClient(state))
    yield TestClient(main.app, headers={"Authorization": "Bearer " + TOKEN}), state, key
    get_settings.cache_clear()


def test_unreachable_licensing_server_keeps_last_valid_lease(agent):
    http, state, _ = agent
    lease = state.load_lease()
    response = http.post("/v1/heartbeat", json={"protected_rdp_users": 1})
    assert response.status_code == 200
    assert response.json()["heartbeat"] == "unreachable"
    assert response.json()["license"]["state"] == "active"
    assert state.load_lease() == lease
    assert http.get("/v1/status").json()["state"] == "active"


def test_unreachable_licensing_server_does_not_block_licensed_seat_decisions(agent):
    http, _, _ = agent
    http.post("/v1/heartbeat", json={"protected_rdp_users": 0})
    assert http.post("/v1/seats/reserve", json={"username": "alice"}).json()["allowed"] is True
    assert http.post("/v1/seats/reserve", json={"username": "bob"}).json()["allowed"] is True
    third = http.post("/v1/seats/reserve", json={"username": "carol"}).json()
    assert third["allowed"] is False and "limit" in third["reason"]
    assert json.dumps(third).find("alice") == -1


def capture_licensing_server(monkeypatch, state, key):
    """Answer challenge/heartbeat like Bliss and record exactly what the appliance sent."""
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append((request.url.path, request.content.decode(), body))
        if request.url.path == "/v1/challenges":
            return httpx.Response(200, json={"nonce": "n" * 32, "expires_at": "2099-01-01T00:00:00+00:00"})
        now = datetime.now(UTC)
        payload = canonical_json({"installation_id": state.installation_id(), "license_id": "lic_outage",
                                  "license_type": "online", "state": "active", "max_rdp_users": 2,
                                  "issued_at": now.isoformat(),
                                  "lease_expires_at": (now + timedelta(days=14)).isoformat(),
                                  "grace_expires_at": (now + timedelta(days=30)).isoformat()})
        lease = b64url(canonical_json({"payload": b64url(payload), "signature": b64url(key.sign(payload))}))
        return httpx.Response(200, json={"signed_lease": lease})

    reporter = LicenseServerClient(state)
    monkeypatch.setattr(reporter, "_client", lambda: httpx.Client(
        base_url="https://license.example", transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(main, "client", reporter)
    return sent


def reported(sent):
    return next(body for path, _, body in sent if path == "/v1/heartbeat")["protected_rdp_users"]


@pytest.mark.parametrize(("ledger", "appliance", "expected"), [(1, 3, 3), (2, 0, 2), (2, 2, 2)])
def test_heartbeat_reports_the_larger_protected_seat_usage(agent, monkeypatch, ledger, appliance, expected):
    http, state, key = agent
    for name in ("alice", "bob")[:ledger]:
        state.reserve_seat(name)
    sent = capture_licensing_server(monkeypatch, state, key)
    assert http.post("/v1/heartbeat", json={"protected_rdp_users": appliance}).status_code == 200
    assert reported(sent) == expected


def test_heartbeat_sends_only_numeric_usage_and_no_identities(agent, monkeypatch):
    http, state, key = agent
    state.reserve_seat("alice.secret-user")
    sent = capture_licensing_server(monkeypatch, state, key)
    http.post("/v1/heartbeat", json={"protected_rdp_users": 1, "audit_head_hash": "a" * 64})
    raw = next(text for path, text, _ in sent if path == "/v1/heartbeat")
    body = json.loads(raw)
    assert set(body) == {"installation_id", "nonce", "protected_rdp_users", "software_version",
                         "machine_fingerprint", "audit_head_hash", "signature"}
    assert isinstance(body["protected_rdp_users"], int)
    assert "alice" not in raw.lower()
    assert state.seat_id("alice.secret-user") not in raw


def test_appliance_reported_usage_does_not_change_local_entitlement(agent, monkeypatch):
    http, state, key = agent
    capture_licensing_server(monkeypatch, state, key)
    http.post("/v1/heartbeat", json={"protected_rdp_users": 99})
    assert http.post("/v1/seats/reserve", json={"username": "alice"}).json()["allowed"] is True
    assert http.post("/v1/seats/reserve", json={"username": "bob"}).json()["allowed"] is True
    assert http.post("/v1/seats/reserve", json={"username": "carol"}).json()["allowed"] is False
