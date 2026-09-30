import subprocess

import pytest
from fastapi.testclient import TestClient

from adapter import main
from adapter.config import get_settings
from adapter.runner import CommandResult, MultiOtpCliRunner


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADAPTER_SHARED_TOKEN", "disposable-test-token")
    monkeypatch.setenv("ADAPTER_ENABLE_WRITES", "true")
    get_settings.cache_clear()
    with TestClient(main.app, headers={"authorization": "Bearer disposable-test-token"}) as client:
        yield client
    get_settings.cache_clear()


@pytest.mark.parametrize("exception,expected", [
    (subprocess.TimeoutExpired(["engine", "submitted-secret"], 1), 504),
    (FileNotFoundError("private engine path"), 503),
])
def test_engine_transport_errors_are_controlled_and_private(client, monkeypatch, exception, expected):
    def failed(*args):
        raise exception
    monkeypatch.setattr(main.runner, "run", failed)
    result = client.post("/v1/users/alice/verify", json={"otp": "123456"})
    assert result.status_code == expected
    assert "submitted-secret" not in result.text
    assert "private engine path" not in result.text


def test_invalid_username_is_controlled_on_lifecycle_routes(client):
    result = client.post("/v1/users/-invalid/disable")
    assert result.status_code == 422


@pytest.mark.parametrize("path,code,expected", [
    ("verify", 0, True), ("verify", 11, False), ("verify", 19, False),
    ("verify", 26, False), ("disable", 11, True), ("disable", 19, False),
    ("enable", 11, True), ("lock", 11, True), ("lock", 19, False),
    ("unlock", 11, True), ("resync", 14, True),
])
def test_operation_codes_over_http(client, monkeypatch, path, code, expected):
    monkeypatch.setattr(main.runner, "run", lambda *args: CommandResult(code, "", ""))
    payload = {"otp": "123456"} if path == "verify" else (
        {"otp1": "123456", "otp2": "234567"} if path == "resync" else None
    )
    response = client.post("/v1/users/disposable/" + path, json=payload)
    assert response.status_code == 200
    assert response.json()["ok"] is expected


def test_list_and_provisioning_accept_engine_codes(client, monkeypatch):
    monkeypatch.setattr(main.runner, "run", lambda *args: CommandResult(
        19 if args[0] == "-userslist" else 17,
        "disposable\n" if args[0] == "-userslist" else "otpauth://totp/disposable?secret=TEST",
        "",
    ))
    assert client.get("/v1/users").json() == {"users": ["disposable"]}
    assert client.get("/v1/users/disposable/provisioning").status_code == 200


@pytest.mark.parametrize("code,expected", [(11, True), (22, False), (99, False)])
def test_create_rejects_engine_errors(client, monkeypatch, code, expected):
    monkeypatch.setattr(main.runner, "run", lambda *args: CommandResult(code, "", ""))
    assert client.post("/v1/users", json={"username": "disposable"}).json()["ok"] is expected


@pytest.mark.parametrize("code,expected", [(12, True), (21, True), (99, False)])
def test_deletion_is_idempotent(client, monkeypatch, code, expected):
    monkeypatch.setattr(main.runner, "run", lambda *args: CommandResult(code, "", ""))
    assert client.delete("/v1/users/disposable").json()["ok"] is expected


@pytest.mark.parametrize("removal", [19, 99, "timeout"])
def test_revoke_disables_before_removal(monkeypatch, removal):
    runner = MultiOtpCliRunner("unused-test-executable")
    calls = []

    def run(*args):
        calls.append(args)
        if args[0] == "-deactivate":
            return CommandResult(11, "", "")
        if removal == "timeout":
            raise subprocess.TimeoutExpired("unused-test-executable", 1)
        return CommandResult(removal, "", "")

    monkeypatch.setattr(runner, "run", run)
    result = runner.revoke_token("disposable")
    assert calls == [("-deactivate", "disposable"), ("-remove-token", "disposable")]
    assert result.authentication_disabled is True
    assert result.returncode == (99 if removal == "timeout" else removal)


def test_revoke_does_not_rotate_if_disabling_failed(monkeypatch):
    runner = MultiOtpCliRunner("unused-test-executable")
    calls = []
    monkeypatch.setattr(runner, "run", lambda *args: (calls.append(args) or CommandResult(99, "", "")))
    result = runner.revoke_token("disposable")
    assert calls == [("-deactivate", "disposable")]
    assert result.authentication_disabled is False
