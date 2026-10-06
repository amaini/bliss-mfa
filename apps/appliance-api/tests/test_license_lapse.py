"""A lapsed, cancelled or unreachable license restricts growth only; existing users stay usable."""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from appliance import main
from appliance.db import Base, get_db
from appliance.models import AdminRole, MfaUser, UserStatus
from appliance.security import Principal, require_operator

REASON = {"reason": "pilot lapse check"}


class LapsedAgent:
    """Mirrors the agent for a suspended/expired/restricted license."""

    def __init__(self, state):
        self.state = state
        self.released = []

    def reserve_seat(self, username):
        return {"allowed": False, "seat_count": 1, "max_rdp_users": 1,
                "reason": f"License state {self.state} does not allow a new RDP seat"}

    def release_seat(self, username):
        self.released.append(username)
        return 0


class UnreachableAgent:
    def reserve_seat(self, username):
        raise httpx.ConnectError("license agent down")

    def release_seat(self, username):
        raise httpx.ConnectError("license agent down")


class Engine:
    def __init__(self):
        self.commands = []

    def command(self, username, command):
        self.commands.append((username, command))
        return True

    def create_user(self, username):
        self.commands.append((username, "create"))
        return {"ok": True}


@pytest.fixture(params=["suspended", "expired", "restricted", "unreachable"])
def lapsed(request, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[require_operator] = lambda: Principal(
        id="owner", email="owner@example.com", role=AdminRole.owner)
    agent = UnreachableAgent() if request.param == "unreachable" else LapsedAgent(request.param)
    mfa = Engine()
    monkeypatch.setattr(main, "license_agent", lambda: agent)
    monkeypatch.setattr(main, "multiotp", lambda: mfa)
    yield TestClient(main.app), db, mfa
    main.app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def user(db, status):
    row = MfaUser(username="alice", engine_username="alice", status=status, protected_rdp=True)
    db.add(row)
    db.commit()
    return row


def test_locked_existing_user_can_still_be_unlocked(lapsed):
    client, db, mfa = lapsed
    row = user(db, UserStatus.locked)
    response = client.post(f"/v1/users/{row.id}/unlock", json=REASON)
    assert response.status_code == 200, response.text
    assert ("alice", "unlock") in mfa.commands


@pytest.mark.parametrize("action", ["lock", "disable"])
def test_existing_user_management_that_reduces_access_still_works(lapsed, action):
    client, db, _ = lapsed
    row = user(db, UserStatus.active)
    assert client.post(f"/v1/users/{row.id}/{action}", json=REASON).status_code == 200


def test_reenabling_a_disabled_user_needs_a_new_seat_and_is_blocked(lapsed):
    client, db, mfa = lapsed
    row = user(db, UserStatus.disabled)
    response = client.post(f"/v1/users/{row.id}/enable", json=REASON)
    assert response.status_code in (403, 503)
    assert ("alice", "enable") not in mfa.commands
    db.refresh(row)
    assert row.status == UserStatus.disabled


def test_new_protected_user_is_blocked(lapsed):
    client, db, mfa = lapsed
    response = client.post("/v1/users", json={"username": "newcomer"})
    assert response.status_code in (403, 503)
    assert list(db.scalars(select(MfaUser))) == []
    assert ("newcomer", "create") not in mfa.commands
