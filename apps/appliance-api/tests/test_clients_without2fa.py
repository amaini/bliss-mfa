import httpx

from appliance import clients


def fake(monkeypatch, method, status, body):
    seen = {}

    def call(url, **kwargs):
        seen["url"] = url
        return httpx.Response(status, json=body, request=httpx.Request(method.upper(), url))
    monkeypatch.setattr(clients.httpx, method, call)
    return seen


def client(monkeypatch):
    monkeypatch.setenv("MULTIOTP_ADAPTER_URL", "http://adapter")
    monkeypatch.setenv("MULTIOTP_ADAPTER_TOKEN", "t")
    clients.get_settings.cache_clear()
    try:
        return clients.MultiOtpClient()
    finally:
        clients.get_settings.cache_clear()


def test_ensure_without2fa(monkeypatch):
    seen = fake(monkeypatch, "post", 200, {"ok": True, "returncode": 11, "authentication_disabled": False})
    assert client(monkeypatch).ensure_without2fa("Ekta") is True
    assert seen["url"] == "http://adapter/v1/users/Ekta/without2fa"


def test_ensure_without2fa_refused_for_totp(monkeypatch):
    fake(monkeypatch, "post", 200, {"ok": False, "returncode": 7, "authentication_disabled": False})
    assert client(monkeypatch).ensure_without2fa("Ekta") is False


def test_status(monkeypatch):
    fake(monkeypatch, "get", 200, {"without2fa": True, "exists": True})
    assert client(monkeypatch).without2fa_status("Ekta") == {"without2fa": True, "exists": True}
