import pytest
from fastapi.testclient import TestClient

from adapter import main
from adapter.config import get_settings
from adapter.runner import CommandResult


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADAPTER_SHARED_TOKEN", "disposable-test-token")
    monkeypatch.setenv("ADAPTER_ENABLE_WRITES", "true")
    get_settings.cache_clear()
    calls = []
    state = {"kind": None}  # None = no user, "w" = without2FA, "t" = TOTP

    def run(*args):
        calls.append(args)
        op = args[0]
        if op == "-iswithout2fa":
            return CommandResult({None: 21, "w": 8, "t": 7}[state["kind"]], "", "")
        if op == "-create" and args[2] == "without2FA":
            if state["kind"]:
                return CommandResult(22, "", "")
            state["kind"] = "w"
            return CommandResult(11, "", "")
        if op == "-fastcreatenopin":
            if state["kind"]:
                return CommandResult(22, "", "")
            state["kind"] = "t"
            return CommandResult(11, "", "")
        if op == "-delete":
            existed = state["kind"] is not None
            state["kind"] = None
            return CommandResult(12 if existed else 21, "", "")
        return CommandResult(99, "", "")

    monkeypatch.setattr(main.runner, "run", run)
    with TestClient(main.app, headers={"authorization": "Bearer disposable-test-token"}) as c:
        yield c, calls, state
    get_settings.cache_clear()


def test_create_without2fa_record(client):
    c, calls, state = client
    r = c.post("/v1/users/Ekta/without2fa")
    assert r.json()["ok"] is True and state["kind"] == "w"
    assert ("-create", "Ekta", "without2FA", "", "", "6", "30") in calls


def test_create_without2fa_is_idempotent(client):
    c, _, state = client
    state["kind"] = "w"
    assert c.post("/v1/users/Ekta/without2fa").json()["ok"] is True


def test_without2fa_refused_for_totp_user(client):
    c, _, state = client
    state["kind"] = "t"
    assert c.post("/v1/users/Ekta/without2fa").json()["ok"] is False
    assert state["kind"] == "t"


def test_status_reports_kind(client):
    c, _, state = client
    assert c.get("/v1/users/Ekta/without2fa").json() == {"without2fa": False, "exists": False}
    state["kind"] = "w"
    assert c.get("/v1/users/Ekta/without2fa").json() == {"without2fa": True, "exists": True}
    state["kind"] = "t"
    assert c.get("/v1/users/Ekta/without2fa").json() == {"without2fa": False, "exists": True}


def test_enrolling_replaces_without2fa_record(client):
    c, _, state = client
    state["kind"] = "w"
    r = c.post("/v1/users", json={"username": "Ekta"})
    assert r.json()["ok"] is True and state["kind"] == "t"


def test_enrolling_does_not_delete_existing_totp(client):
    c, calls, state = client
    state["kind"] = "t"
    assert c.post("/v1/users", json={"username": "Ekta"}).json()["ok"] is False
    assert not any(call[0] == "-delete" for call in calls)


def test_invalid_username_refused(client):
    c, *_ = client
    assert c.post("/v1/users/-bad/without2fa").status_code == 422
