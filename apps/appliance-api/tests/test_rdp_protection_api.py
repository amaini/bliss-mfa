"""Dashboard-managed RDP protection API. Fakes only: no registry, engine or Windows account is touched."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from appliance import main
from appliance.db import Base, get_db
from appliance.models import AdminRole, LocalAdmin, MfaUser, UserStatus
from appliance.rdp_protection import ProviderRegistry
from appliance.security import Principal, current_principal, hash_password
from tests.test_coverage import FakeEngine
from tests.test_rdp_protection_registry import FakeBackend

ACCOUNTS = [{"username": "Abhishek", "display_name": None, "enabled": True},
            {"username": "Ekta", "display_name": None, "enabled": True},
            {"username": "JSmith", "display_name": "John", "enabled": True}]
GOOD = {"password": "owner-password-123", "username": "JSmith", "otp": "123456"}


class FakeAgent:
    def __init__(self):
        self.state = "active"

    def status(self):
        return {"state": self.state}

    def reserve_seat(self, username):
        return {"allowed": True}

    def release_seat(self, username):
        return 0


@pytest.fixture
def env(monkeypatch):
    engine_db = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine_db)
    db = Session(engine_db)
    owner = LocalAdmin(email="o@example.com", password_hash=hash_password("owner-password-123"), role=AdminRole.owner)
    db.add(owner)
    db.add(MfaUser(username="JSmith", engine_username="JSmith", status=UserStatus.active))
    db.commit()
    backend, engine, agent = FakeBackend(), FakeEngine(totp=["jsmith"]), FakeAgent()
    state = {"verify": True, "role": AdminRole.owner, "accounts": [dict(a) for a in ACCOUNTS]}
    monkeypatch.setattr(main, "provider_registry", lambda: ProviderRegistry(backend))
    monkeypatch.setattr(main, "multiotp", lambda: engine)
    monkeypatch.setattr(main, "license_agent", lambda: agent)
    monkeypatch.setattr(main, "read_local_windows_accounts", lambda: [dict(a) for a in state["accounts"]])
    monkeypatch.setattr(main, "native_verify", lambda u, o: state["verify"])
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[current_principal] = (
        lambda: Principal(id=owner.id, email=owner.email, role=state["role"]))
    yield TestClient(main.app), backend, engine, state, db, agent
    main.app.dependency_overrides.clear()
    db.close()


def test_enable_sets_values_and_covers_accounts(env):
    client, backend, engine, *_ = env
    r = client.post("/v1/rdp-protection/enable", json=GOOD)
    assert r.status_code == 200, r.text
    assert backend.values["cpus_logon"] == "1e" and backend.values["two_step_hide_otp"] == 1
    assert engine.kind["ekta"] == "w" and "abhishek" not in engine.kind
    status = client.get("/v1/rdp-protection").json()
    assert status["on"] is True and status["recovery_account"] == "Abhishek"
    assert status["protected"] == ["JSmith"] and status["password_only"] == ["Ekta"]


@pytest.mark.parametrize("change,code", [
    ({"password": "wrong-password-000"}, 401),
    ({"otp": "12345"}, 422),
    ({"username": "Ekta"}, 409),
    ({"username": "Abhishek"}, 409),
    ({"username": "ABHISHEK"}, 409),
])
def test_enable_refusals_change_nothing(env, change, code):
    client, backend, engine, *_ = env
    before = dict(backend.values)
    assert client.post("/v1/rdp-protection/enable", json={**GOOD, **change}).status_code == code
    assert backend.values == before and "ekta" not in engine.kind


def test_wrong_code_changes_nothing(env):
    client, backend, _, state, *_ = env
    state["verify"] = False
    before = dict(backend.values)
    assert client.post("/v1/rdp-protection/enable", json=GOOD).status_code == 400
    assert backend.values == before


def test_unlicensed_cannot_enable(env):
    client, backend, *_, agent = env
    agent.state = "expired"
    before = dict(backend.values)
    assert client.post("/v1/rdp-protection/enable", json=GOOD).status_code == 403
    assert backend.values == before


def test_enable_refused_when_accounts_cannot_be_listed(env, monkeypatch):
    client, backend, *_ = env

    def broken():
        raise main.HTTPException(502, "Could not read local Windows accounts")
    monkeypatch.setattr(main, "read_local_windows_accounts", broken)
    before = dict(backend.values)
    assert client.post("/v1/rdp-protection/enable", json=GOOD).status_code == 502
    assert backend.values == before


def test_disable_works_even_when_license_lapsed(env):
    client, backend, *_, agent = env
    client.post("/v1/rdp-protection/enable", json=GOOD)
    agent.state = "expired"
    assert client.post("/v1/rdp-protection/disable", json={"password": "owner-password-123"}).status_code == 200
    assert backend.values["cpus_logon"] == "3d"


def test_disable_needs_password(env):
    client, backend, *_ = env
    client.post("/v1/rdp-protection/enable", json=GOOD)
    assert client.post("/v1/rdp-protection/disable", json={"password": "wrong-password-000"}).status_code == 401
    assert backend.values["cpus_logon"] == "1e"


@pytest.mark.parametrize("role", [AdminRole.admin, AdminRole.operator, AdminRole.readonly])
def test_only_owner_can_change(env, role):
    client, _, _, state, *_ = env
    state["role"] = role
    assert client.post("/v1/rdp-protection/enable", json=GOOD).status_code == 403
    assert client.post("/v1/rdp-protection/disable", json={"password": "x"}).status_code == 403


@pytest.mark.parametrize("name", ["Abhishek", "ABHISHEK", "abhishek"])
def test_recovery_account_cannot_be_enrolled(env, monkeypatch, name):
    client, *_ = env
    monkeypatch.setattr(main.os, "name", "nt")
    monkeypatch.setattr(main.settings, "windows_account_validation", "auto")
    r = client.post("/v1/users", json={"username": name})
    assert r.status_code == 409 and "recovery account" in r.json()["detail"]


def test_delete_while_on_leaves_password_only_record(env):
    client, _, engine, _, db, _ = env
    client.post("/v1/rdp-protection/enable", json=GOOD)
    jsmith = db.scalar(select(MfaUser).where(MfaUser.username == "JSmith"))
    assert client.delete(f"/v1/users/{jsmith.id}", params={"reason": "test removal"}).status_code == 204
    assert engine.kind["jsmith"] == "w"


def test_enroll_while_on_replaces_password_only(env):
    client, _, engine, *_ = env
    client.post("/v1/rdp-protection/enable", json=GOOD)
    assert engine.kind["ekta"] == "w"
    r = client.post("/v1/users", json={"username": "Ekta"})
    assert r.status_code == 201, r.text
    assert engine.kind["ekta"] == "t"
    status = client.get("/v1/rdp-protection").json()
    assert "Ekta" in status["protected"]
