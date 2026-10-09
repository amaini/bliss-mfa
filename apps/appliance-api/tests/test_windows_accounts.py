"""Windows Accounts page API and server-side validation of local Windows usernames.

Everything here uses fakes: no Windows account is read or changed, no multiOTP record is created
and no license seat is reserved for real.
"""
import json
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from appliance import main
from appliance.db import Base, get_db
from appliance.models import AdminRole, MfaUser, UserStatus
from appliance.security import Principal, current_principal

LOCAL_ACCOUNTS = [
    {"username": "Administrator", "display_name": None, "enabled": False},
    {"username": "JSmith", "display_name": "John Smith", "enabled": True},
    {"username": "frontdesk", "display_name": "Front Desk", "enabled": True},
    {"username": "olduser", "display_name": None, "enabled": False},
    {"username": "pending.user", "display_name": None, "enabled": True},
]


class FakeMultiOtp:
    def __init__(self):
        self.created: list[str] = []

    def create_user(self, username):
        self.created.append(username)

    def provisioning_uri(self, username):
        return f"otpauth://totp/Bliss:{username}?secret=TESTONLY"


class FakeLicenseAgent:
    def __init__(self):
        self.allowed = True
        self.reserved: list[str] = []

    def status(self):
        return {"state": "active"}

    def reserve_seat(self, username):
        if not self.allowed:
            return {"allowed": False, "reason": "Seat limit reached: 1 of 1 protected users in use"}
        self.reserved.append(username)
        return {"allowed": True}

    def release_seat(self, username):
        return 0


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    engine_fake, agent = FakeMultiOtp(), FakeLicenseAgent()
    monkeypatch.setattr(main, "multiotp", lambda: engine_fake)
    monkeypatch.setattr(main, "license_agent", lambda: agent)
    # Simulate the appliance host with the production default ("auto" = validate on Windows);
    # local accounts come from the faked PowerShell discovery.
    monkeypatch.setattr(main.os, "name", "nt")
    monkeypatch.setattr(main.settings, "windows_account_validation", "auto")
    calls = {"discovery": 0, "accounts": list(LOCAL_ACCOUNTS), "fail": False}

    def fake_run(args, **kwargs):
        calls["discovery"] += 1
        if calls["fail"]:
            return subprocess.CompletedProcess(args, 1, "", "Get-LocalUser failed")
        return subprocess.CompletedProcess(args, 0, json.dumps(calls["accounts"]), "")

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    principal = Principal(id="operator-test", email="op@example.com", role=AdminRole.operator)
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[current_principal] = lambda: principal
    yield TestClient(main.app), db, engine_fake, agent, calls
    main.app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def by_name(rows):
    return {row["username"]: row for row in rows}


# -- 1. Windows Accounts page: matching and honest status --------------------------------------
def test_accounts_are_matched_to_mfa_records_case_insensitively(env):
    client, db, *_ = env
    db.add_all([
        MfaUser(username="jsmith", engine_username="jsmith", status=UserStatus.active),
        MfaUser(username="pending.user", engine_username="pending.user", status=UserStatus.pending),
    ])
    db.commit()
    rows = by_name(client.get("/v1/windows-users").json())
    assert rows["JSmith"]["state"] == "enrolled"  # Windows "JSmith" matches MFA record "jsmith"
    assert rows["JSmith"]["mfa_status"] == "active"
    assert rows["pending.user"]["state"] == "pending"  # a record alone is not an enrollment
    assert rows["frontdesk"]["state"] == "not_enrolled"
    assert rows["frontdesk"]["mfa_status"] is None
    assert rows["olduser"]["state"] == "disabled_account"


def test_disabled_windows_account_is_reported_as_disabled_even_with_mfa_record(env):
    client, db, *_ = env
    db.add(MfaUser(username="olduser", engine_username="olduser", status=UserStatus.active))
    db.commit()
    row = by_name(client.get("/v1/windows-users").json())["olduser"]
    assert row["state"] == "disabled_account" and row["enabled"] is False and row["mfa_status"] == "active"


def test_inactive_mfa_records_are_not_reported_as_enrolled(env):
    client, db, *_ = env
    db.add(MfaUser(username="frontdesk", engine_username="frontdesk", status=UserStatus.revoked))
    db.commit()
    row = by_name(client.get("/v1/windows-users").json())["frontdesk"]
    assert row["state"] == "mfa_inactive" and row["mfa_status"] == "revoked"


def test_status_never_claims_protection(env):
    client, db, *_ = env
    db.add(MfaUser(username="jsmith", engine_username="jsmith", status=UserStatus.active))
    db.commit()
    body = json.dumps(client.get("/v1/windows-users").json()).lower()
    assert "protected" not in body and "protection" not in body


# -- 2. Enroll MFA from a Windows account ------------------------------------------------------
def test_enroll_uses_exact_windows_username_and_opens_enrollment(env):
    client, _db, engine_fake, agent, _ = env
    created = client.post("/v1/users", json={"username": "jsmith"})  # typed in a different case
    assert created.status_code == 201, created.text
    user = created.json()
    assert user["username"] == "JSmith" and user["status"] == "pending"
    assert engine_fake.created == ["JSmith"] and agent.reserved == ["JSmith"]
    enrollment = client.post(f"/v1/users/{user['id']}/enrollment")
    assert enrollment.status_code == 200
    assert enrollment.json()["provisioning_uri"].startswith("otpauth://")


@pytest.mark.parametrize("existing", ["JSmith", "jsmith", "JSMITH"])
def test_duplicate_enrollment_is_refused_case_insensitively(env, existing):
    client, db, engine_fake, agent, _ = env
    db.add(MfaUser(username=existing, engine_username=existing, status=UserStatus.pending))
    db.commit()
    response = client.post("/v1/users", json={"username": "JSmith"})
    assert response.status_code == 409
    assert "already" in response.json()["detail"].lower()
    assert engine_fake.created == [] and agent.reserved == []


def test_plan_limit_is_enforced_server_side(env):
    client, db, engine_fake, agent, _ = env
    agent.allowed = False
    response = client.post("/v1/users", json={"username": "frontdesk"})
    assert response.status_code == 403 and "Seat limit" in response.json()["detail"]
    assert engine_fake.created == []
    assert db.query(MfaUser).count() == 0


# -- 3. Server-side validation of manually entered names ------------------------------------
def test_nonexistent_local_account_is_refused_with_clear_message(env):
    client, db, engine_fake, agent, _ = env
    response = client.post("/v1/users", json={"username": "jsmiht"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "jsmiht" in detail and "local Windows account" in detail
    assert engine_fake.created == [] and agent.reserved == [] and db.query(MfaUser).count() == 0


def test_disabled_local_account_is_refused(env):
    client, _db, engine_fake, agent, _ = env
    response = client.post("/v1/users", json={"username": "olduser"})
    assert response.status_code == 409 and "disabled" in response.json()["detail"].lower()
    assert engine_fake.created == [] and agent.reserved == []


def test_validation_fails_closed_when_accounts_cannot_be_read(env):
    client, _db, engine_fake, agent, calls = env
    calls["fail"] = True
    response = client.post("/v1/users", json={"username": "frontdesk"})
    assert response.status_code == 503
    assert engine_fake.created == [] and agent.reserved == []


@pytest.mark.parametrize("bad", ["", "a b", "../x", "x;y", "name\twith\ttab", "x" * 101])
def test_invalid_usernames_are_rejected_before_any_lookup(env, bad):
    client, _db, engine_fake, _agent, calls = env
    response = client.post("/v1/users", json={"username": bad})
    assert response.status_code == 422
    assert calls["discovery"] == 0 and engine_fake.created == []


def test_non_windows_hosts_skip_local_account_validation(env, monkeypatch):
    """RADIUS-only/containers have no local Windows accounts; validation applies on the appliance host."""
    client, _db, engine_fake, _agent, calls = env
    monkeypatch.setattr(main.os, "name", "posix")
    assert client.post("/v1/users", json={"username": "radius.only"}).status_code == 201
    assert calls["discovery"] == 0 and engine_fake.created == ["radius.only"]


def test_windows_validation_can_be_required_explicitly(env, monkeypatch):
    client, *_ = env
    monkeypatch.setattr(main.os, "name", "posix")
    monkeypatch.setattr(main.settings, "windows_account_validation", "required")
    assert client.post("/v1/users", json={"username": "frontdesk"}).status_code == 503


# -- Authorization -------------------------------------------------------------------------
def test_readonly_admin_cannot_list_or_enroll(env):
    client, _db, engine_fake, _agent, calls = env
    main.app.dependency_overrides[current_principal] = lambda: Principal(
        id="ro", email="ro@example.com", role=AdminRole.readonly)
    assert client.get("/v1/windows-users").status_code == 403
    assert client.post("/v1/users", json={"username": "frontdesk"}).status_code == 403
    assert calls["discovery"] == 0 and engine_fake.created == []


def test_unauthenticated_requests_are_refused(env):
    client, *_ = env
    main.app.dependency_overrides.pop(current_principal)
    assert client.get("/v1/windows-users").status_code == 401
    assert client.post("/v1/users", json={"username": "frontdesk"}).status_code == 401
