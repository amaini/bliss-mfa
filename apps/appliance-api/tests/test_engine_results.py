import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from appliance import main
from appliance.clients import AdapterOperationError, MultiOtpClient, operation_ok
from appliance.db import Base, get_db
from appliance.models import AdminRole, AuditEvent, MfaUser, UserStatus
from appliance.security import Principal, require_operator


def response(body):
    return httpx.Response(200, json=body, request=httpx.Request("POST", "http://isolated.invalid"))


def test_http_success_does_not_hide_failed_create(monkeypatch):
    client = MultiOtpClient()
    client.token = "test"
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response({"ok": False, "returncode": 22}))
    with pytest.raises(AdapterOperationError):
        client.create_user("disposable")


@pytest.mark.parametrize("body", [{"ok": "false"}, {"ok": 1}, {}, [], {"ok": None}])
def test_malformed_operation_result_fails_closed(body):
    with pytest.raises(RuntimeError):
        operation_ok(response(body))


@pytest.fixture
def isolated_api(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    principal = Principal(id="test-owner", email="owner@example.com", role=AdminRole.owner)
    main.app.dependency_overrides[get_db] = lambda: session
    main.app.dependency_overrides[require_operator] = lambda: principal

    class Seats:
        def __init__(self):
            self.released = []

        def reserve_seat(self, username):
            return {"allowed": True, "already_reserved": False}

        def release_seat(self, username):
            self.released.append(username)
            return 0

    seats = Seats()
    monkeypatch.setattr(main, "license_agent", lambda: seats)
    yield TestClient(main.app), session, seats
    main.app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def test_failed_create_has_no_row_and_releases_seat(isolated_api, monkeypatch):
    client, db, seats = isolated_api

    class FailedEngine:
        def create_user(self, username):
            raise AdapterOperationError()

    monkeypatch.setattr(main, "multiotp", FailedEngine)
    assert client.post("/v1/users", json={"username": "disposable"}).status_code == 502
    assert list(db.scalars(select(MfaUser))) == []
    assert seats.released == ["disposable"]
    assert db.scalar(select(AuditEvent)).success is False


def test_partial_revoke_records_revoked_and_releases_seat(isolated_api, monkeypatch):
    client, db, seats = isolated_api
    user = MfaUser(username="disposable", engine_username="disposable", status=UserStatus.active)
    db.add(user)
    db.commit()

    class FailedEngine:
        def command(self, *args):
            raise AdapterOperationError(authentication_disabled=True)

    monkeypatch.setattr(main, "multiotp", FailedEngine)
    assert client.post(f"/v1/users/{user.id}/revoke", json={"reason": "Test revoke"}).status_code == 409
    db.refresh(user)
    assert user.status == UserStatus.revoked
    assert seats.released == ["disposable"]
    event = db.scalar(select(AuditEvent))
    assert event.action == "mfa.user.revoked_failed" and event.success is False
    for operation in ["enable", "unlock", "disable"]:
        assert client.post(f"/v1/users/{user.id}/{operation}", json={"reason": "Test retry"}).status_code == 409


def test_successful_delete_removes_row_and_releases_seat(isolated_api, monkeypatch):
    client, db, seats = isolated_api
    user = MfaUser(username="disposable", engine_username="disposable", status=UserStatus.active)
    db.add(user)
    db.commit()
    user_id = user.id

    class Engine:
        def delete_user(self, username):
            return True

    monkeypatch.setattr(main, "multiotp", Engine)
    assert client.delete(f"/v1/users/{user_id}?reason=Test%20delete").status_code == 204
    assert db.get(MfaUser, user_id) is None
    assert seats.released == ["disposable"]


def test_lock_and_unlock_preserve_seat(isolated_api, monkeypatch):
    client, db, seats = isolated_api
    user = MfaUser(username="disposable", engine_username="disposable", status=UserStatus.active)
    db.add(user)
    db.commit()

    class Engine:
        def command(self, username, command):
            return True

    monkeypatch.setattr(main, "multiotp", Engine)
    assert client.post(f"/v1/users/{user.id}/lock", json={"reason": "Test lock"}).json()["status"] == "locked"
    assert client.post(f"/v1/users/{user.id}/unlock", json={"reason": "Test unlock"}).json()["status"] == "active"
    assert seats.released == []


@pytest.mark.parametrize("status", [UserStatus.pending, UserStatus.disabled, UserStatus.revoked])
def test_lock_rejects_ineligible_user_states(isolated_api, status):
    client, db, _ = isolated_api
    user = MfaUser(username="disposable", engine_username="disposable", status=status)
    db.add(user)
    db.commit()
    assert client.post(f"/v1/users/{user.id}/lock", json={"reason": "Test lock"}).status_code == 409
