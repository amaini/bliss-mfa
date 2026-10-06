import json
from datetime import UTC, datetime, timedelta

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
    yield TestClient(main.app, headers={"Authorization": "Bearer " + TOKEN}), state
    get_settings.cache_clear()


def test_unreachable_licensing_server_keeps_last_valid_lease(agent):
    http, state = agent
    lease = state.load_lease()
    response = http.post("/v1/heartbeat", json={"protected_rdp_users": 1})
    assert response.status_code == 200
    assert response.json()["heartbeat"] == "unreachable"
    assert response.json()["license"]["state"] == "active"
    assert state.load_lease() == lease
    assert http.get("/v1/status").json()["state"] == "active"


def test_unreachable_licensing_server_does_not_block_licensed_seat_decisions(agent):
    http, _ = agent
    http.post("/v1/heartbeat", json={"protected_rdp_users": 0})
    assert http.post("/v1/seats/reserve", json={"username": "alice"}).json()["allowed"] is True
    assert http.post("/v1/seats/reserve", json={"username": "bob"}).json()["allowed"] is True
    third = http.post("/v1/seats/reserve", json={"username": "carol"}).json()
    assert third["allowed"] is False and "limit" in third["reason"]
    assert json.dumps(third).find("alice") == -1
