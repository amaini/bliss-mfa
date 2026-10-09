# Dashboard-managed RDP protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Owners turn RDP MFA on/off from the local dashboard. Enrolled accounts get a second-step
code over RDP; every other enabled local account signs in over RDP with its password only. Local
sign-in is never affected.

**Architecture:**
- **Adapter:** the multiOTP adapter gains `without2FA` record operations.
- **Appliance API:**
  - a fixed-value provider-registry module, `rdp_protection.py`, which flushes after every write;
  - a native-client code verifier, `native_verify.py`;
  - a coverage reconciler, `coverage.py`;
  - three endpoints.
- **Portal:** an "RDP protection" card plus a post-enrollment prompt.
- **Runtime:** the supervisor passes the engine config and provider paths to the API.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest, `winreg` (Windows only, injectable),
Next.js 15 / React 19 / TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-08-dashboard-rdp-protection-design.md`

Repo root: `C:\Users\Abhishek\Documents\Apps\MultiOTP\bliss-mfa`. Branch: `design/dashboard-rdp-protection`.

Test commands:
- API: `apps/appliance-api/.venv/Scripts/python -m pytest apps/appliance-api/tests -q`
- Adapter: `services/multiotp-adapter/.venv/Scripts/python -m pytest services/multiotp-adapter/tests -q`
- Scripts: `.venv-scripts/Scripts/python -m pytest scripts/tests -q`
- Portal: `npm --prefix apps/appliance-portal run build`

## Global Constraints

- Protection ON writes exactly: `cpus_logon=1e`, `cpus_unlock=1e`, `cpus_credui=3d` (REG_SZ),
  `two_step_hide_otp=1`, `multiOTPWithout2FA=1` (REG_DWORD).
- Protection OFF writes `cpus_logon=3d`, `cpus_unlock=3d`, `cpus_credui=3d`.
- `two_step_send_password` is never written. `excluded_account` is never written.
- Provider key: `HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}`, 64-bit view, flushed after every write.
- No endpoint accepts a registry name or value from the client.
- Non-enrolled accounts get a multiOTP `without2FA` record and take **no** license seat.
- The excluded recovery account is never enrolled, never given a seat and never given a record.
- Disable is allowed for the owner regardless of license state.
- If the engine is down while ON, protected accounts fail closed (no fallback).
- Any failed enable/disable leaves the provider values exactly as before.
- Engine return codes (5.10.2.2):
  - create = 11, delete = 12 (21 = missing, which is fine);
  - `-iswithout2fa` = 8 (yes) / 7 (no);
  - native client success = 0.

## Review Focus

1. **Enrolling an account that already has a `without2FA` record.** It must become TOTP, not fail
   with "user exists". Test in Task 1.
2. **Re-enrolling after delete.** Delete while ON must leave a `without2FA` record, so the account can
   still RDP with a password. Test in Task 6.
3. **Local account names differing only in case** from MFA records, e.g. `Ekta` vs `ekta`. The
   reconciler must treat them as the same account. Test in Task 5.
4. **Registry read-back mismatch** after a partial write must restore the previous values. Test in Task 3.
5. **The recovery account in any letter case**, or prefixed `COMPUTER\name`, must be refused for
   enrollment. Test in Task 6.

---

### Task 1: Adapter `without2FA` operations

**Files:**
- Modify: `services/multiotp-adapter/adapter/runner.py` (add methods after `create_totp_user`)
- Modify: `services/multiotp-adapter/adapter/main.py` (SUCCESS_CODES, two routes, create replaces without2FA)
- Test: `services/multiotp-adapter/tests/test_without2fa.py`

**Interfaces:**
- Produces: `POST /v1/users/{username}/without2fa` → `CommandResponse` (ok when 11, or already without2FA);
  `GET /v1/users/{username}/without2fa` → `{"without2fa": bool, "exists": bool}`;
  `POST /v1/users` now deletes an existing without2FA record before creating TOTP.
- Runner: `create_without2fa_user(username) -> CommandResult`, `is_without2fa(username) -> CommandResult`.

- [ ] **Step 1: Write the failing tests**

```python
# services/multiotp-adapter/tests/test_without2fa.py
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
        op, user = args[0], args[-1]
        if op == "-iswithout2fa":
            return CommandResult({None: 21, "w": 8, "t": 7}[state["kind"]], "", "")
        if op == "-create" and args[2] == "without2FA":
            if state["kind"]:
                return CommandResult(22, "", "")  # exists
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
    assert state["kind"] == "t"  # an enrollment is never downgraded here


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
```

- [ ] **Step 2: Run to verify failure**

Run: `services/multiotp-adapter/.venv/Scripts/python -m pytest services/multiotp-adapter/tests/test_without2fa.py -q`
Expected: FAIL (404 on the new routes, and `test_enrolling_replaces_without2fa_record` fails).

- [ ] **Step 3: Implement the runner methods**

In `runner.py`, after `create_totp_user`:

```python
    def create_without2fa_user(self, username: str) -> CommandResult:
        return self.run("-create", validate_username(username), "without2FA", "", "", "6", "30")

    def is_without2fa(self, username: str) -> CommandResult:
        return self.run("-iswithout2fa", validate_username(username))
```

- [ ] **Step 4: Implement the routes**

In `main.py`, add `"without2fa": {11}` to `SUCCESS_CODES`. Replace `create_user` and add the routes:

```python
WITHOUT2FA, NOT_WITHOUT2FA, MISSING = 8, 7, 21


@app.post(
    "/v1/users",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def create_user(payload: UserCreate) -> CommandResponse:
    try:
        # Enrolling an account that signs in password-only replaces its without2FA record.
        if runner.is_without2fa(payload.username).returncode == WITHOUT2FA:
            removed = runner.delete_user(payload.username)
            if removed.returncode not in SUCCESS_CODES["delete"]:
                return command_response("delete", removed.returncode)
        result = runner.create_totp_user(payload.username)
    except AdapterInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return command_response("create", result.returncode)


@app.post(
    "/v1/users/{username}/without2fa",
    response_model=CommandResponse,
    dependencies=[Depends(require_internal_auth), Depends(require_writes_enabled)],
)
def create_without2fa(username: str) -> CommandResponse:
    kind = runner.is_without2fa(username).returncode
    if kind == WITHOUT2FA:
        return CommandResponse(ok=True, returncode=kind, authentication_disabled=False)
    if kind == NOT_WITHOUT2FA:  # an enrolled TOTP user is never downgraded here
        return CommandResponse(ok=False, returncode=kind, authentication_disabled=False)
    return command_response("without2fa", runner.create_without2fa_user(username).returncode)


@app.get("/v1/users/{username}/without2fa", dependencies=[Depends(require_internal_auth)])
def without2fa_status(username: str) -> dict[str, bool]:
    kind = runner.is_without2fa(username).returncode
    return {"without2fa": kind == WITHOUT2FA, "exists": kind in {WITHOUT2FA, NOT_WITHOUT2FA}}
```

`validate_username` raises `AdapterInputError` and the existing handler returns 422, so the new
routes need no try/except.

- [ ] **Step 5: Run the adapter suite**

Run: `services/multiotp-adapter/.venv/Scripts/python -m pytest services/multiotp-adapter/tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add services/multiotp-adapter
git commit -m "Adapter: without2FA records; enrolling replaces a without2FA record"
```

---

### Task 2: Appliance client methods for `without2FA`

**Files:**
- Modify: `apps/appliance-api/appliance/clients.py` (MultiOtpClient)
- Test: `apps/appliance-api/tests/test_clients_without2fa.py`

**Interfaces:**
- Produces: `MultiOtpClient.ensure_without2fa(username: str) -> bool`;
  `MultiOtpClient.without2fa_status(username: str) -> dict` (`{"without2fa": bool, "exists": bool}`).
- Consumes: the Task 1 routes.

- [ ] **Step 1: Failing test**

```python
# apps/appliance-api/tests/test_clients_without2fa.py
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
    return clients.MultiOtpClient()


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
```

- [ ] **Step 2: Run to verify it fails** (`AttributeError`).
- [ ] **Step 3: Implement** (in `MultiOtpClient`, after `delete_user`):

```python
    def ensure_without2fa(self, username: str) -> bool:
        response = httpx.post(
            f"{self.base_url}/v1/users/{quote(username, safe='')}/without2fa",
            headers=self._headers(), timeout=15,
        )
        return operation_ok(response)

    def without2fa_status(self, username: str) -> dict:
        response = httpx.get(
            f"{self.base_url}/v1/users/{quote(username, safe='')}/without2fa",
            headers=self._headers(), timeout=15,
        )
        response.raise_for_status()
        body = response.json()
        return {"without2fa": body["without2fa"] is True, "exists": body["exists"] is True}
```

- [ ] **Step 4: Run** `apps/appliance-api/.venv/Scripts/python -m pytest apps/appliance-api/tests/test_clients_without2fa.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "Appliance client: without2FA operations"` (`git add` the new test first).

---

### Task 3: Provider registry module

**Files:**
- Create: `apps/appliance-api/appliance/rdp_protection.py`
- Test: `apps/appliance-api/tests/test_rdp_protection_registry.py`

**Interfaces:**
- Produces:
  - `ProviderRegistry(backend=None)`;
  - `.read() -> dict[str, str | int | None]` (keys: the five managed names plus `excluded_account`);
  - `.is_on() -> bool`;
  - `.apply(on: bool) -> None` (writes, flushes, reads back; restores the previous values and raises `ProviderWriteError` on mismatch);
  - `.recovery_account() -> str | None` (the name after the last `\`).
- Backend protocol (injectable for tests): `get(name) -> value | None`, `set(name, value, kind: str)`,
  `delete(name)`, `flush()`. `kind` is `"sz"` or `"dword"`.
- `ON_VALUES`, `OFF_VALUES` constants.

- [ ] **Step 1: Failing tests**

```python
# apps/appliance-api/tests/test_rdp_protection_registry.py
import pytest

from appliance.rdp_protection import OFF_VALUES, ON_VALUES, ProviderRegistry, ProviderWriteError


class FakeBackend:
    def __init__(self, values=None, corrupt=None):
        self.values = dict(values or {"cpus_logon": "3d", "cpus_unlock": "3d", "cpus_credui": "3d",
                                      "excluded_account": r"UX8402ZE\Abhishek"})
        self.flushes = 0
        self.corrupt = corrupt  # name whose write silently fails once
        self.written = []

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value, kind):
        self.written.append(name)
        if name == self.corrupt:
            self.corrupt = None
            return
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)

    def flush(self):
        self.flushes += 1


def test_apply_on_writes_exact_values_and_flushes():
    backend = FakeBackend()
    ProviderRegistry(backend).apply(True)
    for name, (value, _) in ON_VALUES.items():
        assert backend.values[name] == value
    assert backend.flushes >= 1
    assert "two_step_send_password" not in backend.written
    assert "excluded_account" not in backend.written


def test_apply_off_sets_cpus_3d():
    backend = FakeBackend()
    registry = ProviderRegistry(backend)
    registry.apply(True)
    registry.apply(False)
    assert {n: backend.values[n] for n in OFF_VALUES} == {n: v for n, (v, _) in OFF_VALUES.items()}
    assert registry.is_on() is False


def test_readback_mismatch_restores_previous_values():
    backend = FakeBackend(corrupt="cpus_unlock")
    before = dict(backend.values)
    with pytest.raises(ProviderWriteError):
        ProviderRegistry(backend).apply(True)
    for name in ("cpus_logon", "cpus_unlock", "cpus_credui"):
        assert backend.values.get(name) == before.get(name)
    assert backend.values.get("two_step_hide_otp") is None


def test_is_on_requires_remote_only_values():
    assert ProviderRegistry(FakeBackend()).is_on() is False
    backend = FakeBackend()
    backend.values.update(cpus_logon="0e")  # local+remote is not a state Bliss sets
    assert ProviderRegistry(backend).is_on() is False


def test_recovery_account_name():
    assert ProviderRegistry(FakeBackend()).recovery_account() == "Abhishek"
    assert ProviderRegistry(FakeBackend({"excluded_account": None})).recovery_account() is None
```

- [ ] **Step 2: Run to verify failure** (ImportError).
- [ ] **Step 3: Implement**

```python
# apps/appliance-api/appliance/rdp_protection.py
"""Fixed-value control of the multiOTP Credential Provider for RDP-only protection.

Only the values below are ever written. Every write is flushed to disk (RegFlushKey) and read back,
so neither a partial write nor a power cut can silently leave a different sign-in policy.
"""
from __future__ import annotations

PROVIDER_KEY = r"CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}"
ON_VALUES = {
    "cpus_logon": ("1e", "sz"), "cpus_unlock": ("1e", "sz"), "cpus_credui": ("3d", "sz"),
    "two_step_hide_otp": (1, "dword"), "multiOTPWithout2FA": (1, "dword"),
}
OFF_VALUES = {"cpus_logon": ("3d", "sz"), "cpus_unlock": ("3d", "sz"), "cpus_credui": ("3d", "sz")}
MANAGED = tuple(ON_VALUES)


class ProviderWriteError(RuntimeError):
    pass


class WinregBackend:
    def __init__(self) -> None:
        import winreg
        self.winreg = winreg
        self.key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROVIDER_KEY, 0,
                                  winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)

    def get(self, name):
        try:
            return self.winreg.QueryValueEx(self.key, name)[0]
        except FileNotFoundError:
            return None

    def set(self, name, value, kind):
        kinds = {"sz": self.winreg.REG_SZ, "dword": self.winreg.REG_DWORD}
        self.winreg.SetValueEx(self.key, name, 0, kinds[kind], value)

    def delete(self, name):
        try:
            self.winreg.DeleteValue(self.key, name)
        except FileNotFoundError:
            pass

    def flush(self):
        self.winreg.FlushKey(self.key)


class ProviderRegistry:
    def __init__(self, backend=None) -> None:
        self.backend = backend or WinregBackend()

    def read(self) -> dict:
        return {name: self.backend.get(name) for name in (*MANAGED, "excluded_account")}

    def is_on(self) -> bool:
        values = self.read()
        return all(values[name] == value for name, (value, _) in ON_VALUES.items())

    def recovery_account(self) -> str | None:
        excluded = self.backend.get("excluded_account")
        return str(excluded).split("\\")[-1] if excluded else None

    def apply(self, on: bool) -> None:
        target = ON_VALUES if on else OFF_VALUES
        previous = {name: self.backend.get(name) for name in target}
        kinds = {name: kind for name, (_, kind) in target.items()}
        try:
            for name, (value, kind) in target.items():
                self.backend.set(name, value, kind)
            self.backend.flush()
            if any(self.backend.get(name) != value for name, (value, _) in target.items()):
                raise ProviderWriteError("Sign-in settings did not save as expected")
        except Exception:
            for name, value in previous.items():
                if value is None:
                    self.backend.delete(name)
                else:
                    self.backend.set(name, value, kinds[name])
            self.backend.flush()
            raise
```

The restore runs for any exception. `ProviderWriteError` is re-raised as is; other exceptions
propagate so the API can report them.

- [ ] **Step 4: Run** `apps/appliance-api/.venv/Scripts/python -m pytest apps/appliance-api/tests/test_rdp_protection_registry.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git add apps/appliance-api && git commit -m "Provider registry: fixed RDP-only values, flushed and read back"`

---

### Task 4: Native-client code verification

**Files:**
- Create: `apps/appliance-api/appliance/native_verify.py`
- Modify: `apps/appliance-api/appliance/config.py` (two settings)
- Test: `apps/appliance-api/tests/test_native_verify.py`

**Interfaces:**
- Produces: `native_verify(username: str, otp: str, *, run=subprocess.run) -> bool`; it raises
  `NativeVerifyUnavailable` when the config or the client is missing.
- Settings: `engine_config_file: str | None = None` (the engine `config.json`, providing `auth_port`
  and `native_shared_secret`); `provider_validation_dir: str | None = None`.
- The client path comes from the provider registry value `multiOTPPath` + `multiotp.exe`. Passing a
  `client` argument overrides it in tests.

- [ ] **Step 1: Failing tests**

```python
# apps/appliance-api/tests/test_native_verify.py
import json
import subprocess

import pytest

from appliance import native_verify as nv


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"auth_port": 18443, "native_shared_secret": "s3cret"}))
    monkeypatch.setattr(nv.settings, "engine_config_file", str(path))
    monkeypatch.setattr(nv.settings, "provider_validation_dir", str(tmp_path / "pv"))
    return tmp_path


def test_success_exit_zero_and_arguments(config):
    seen = {}

    def run(args, **kw):
        seen["args"] = args
        return subprocess.CompletedProcess(args, 0, "", "")
    assert nv.native_verify("Ekta", "123456", run=run, client="C:/m/multiotp.exe") is True
    a = seen["args"]
    assert a[0] == "C:/m/multiotp.exe" and a[1] == "-cp" and a[-2:] == ["Ekta", "123456"]
    assert "-server-url=https://127.0.0.1:18443/auth" in a and "-server-secret=s3cret" in a
    assert not any(x.endswith("\\") for x in a)  # trailing backslash corrupts multiotp.exe quoting


def test_failure_codes(config):
    for code in (21, 99):
        assert nv.native_verify("Ekta", "123456", client="c",
                                run=lambda a, **k: subprocess.CompletedProcess(a, code, "", "")) is False


def test_rejects_malformed_code_without_calling(config):
    called = []
    with pytest.raises(ValueError):
        nv.native_verify("Ekta", "12ab56", client="c", run=lambda *a, **k: called.append(1))
    assert not called


def test_unavailable_without_config(monkeypatch):
    monkeypatch.setattr(nv.settings, "engine_config_file", None)
    with pytest.raises(nv.NativeVerifyUnavailable):
        nv.native_verify("Ekta", "123456", client="c")
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** In `config.py`, add to `Settings`:

```python
    # Engine config.json (auth_port, native_shared_secret) and the provider validation directory,
    # used to verify a code through the installed Windows multiOTP client before enabling RDP MFA.
    engine_config_file: str | None = None
    provider_validation_dir: str | None = None
```

```python
# apps/appliance-api/appliance/native_verify.py
"""Verify a code through the installed Windows multiOTP client: the same path RDP sign-in uses."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .config import get_settings

settings = get_settings()


class NativeVerifyUnavailable(RuntimeError):
    pass


def provider_client() -> str:
    from .rdp_protection import ProviderRegistry
    base = ProviderRegistry().backend.get("multiOTPPath")
    if not base:
        raise NativeVerifyUnavailable("Windows multiOTP client is not installed")
    return str(Path(str(base)) / "multiotp.exe")


def native_verify(username: str, otp: str, *, run=subprocess.run, client: str | None = None) -> bool:
    if not re.fullmatch(r"\d{6}", otp):
        raise ValueError("Enter a six-digit code")
    if not settings.engine_config_file or not settings.provider_validation_dir:
        raise NativeVerifyUnavailable("Engine configuration is not available")
    config = json.loads(Path(settings.engine_config_file).read_text(encoding="utf-8-sig"))
    base = Path(settings.provider_validation_dir)
    base.mkdir(parents=True, exist_ok=True)
    args = [client or provider_client(), "-cp", f"-base-dir={str(base).rstrip(chr(92))}",
            "-server-cache-level=0", "-server-timeout=5",
            f"-server-url=https://127.0.0.1:{config['auth_port']}/auth",
            f"-server-secret={config['native_shared_secret']}", username, otp]
    result = run(args, capture_output=True, text=True, timeout=30, check=False)
    return result.returncode == 0
```

- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Verify codes through the installed Windows multiOTP client"` (add the files first).

---

### Task 5: Coverage reconciler

**Files:**
- Create: `apps/appliance-api/appliance/coverage.py`
- Test: `apps/appliance-api/tests/test_coverage.py`

**Interfaces:**
- Consumes: `MultiOtpClient.ensure_without2fa`, `.without2fa_status`, `.delete_user` (Task 2 and existing);
  the local account dicts from `main.read_local_windows_accounts()` (`username`, `display_name`, `enabled`).
- Produces: `reconcile(accounts: list[dict], mfa_users: list[MfaUser], engine, recovery: str | None) -> dict`.
  It returns `{"password_only": [names], "protected": [names], "errors": [names]}`. The rules, per
  enabled account:
  - the recovery account is skipped;
  - an active, pending, locked or disabled Bliss record is "protected" and its TOTP is left alone;
  - a revoked record, or none, means "password only": `ensure_without2fa`, and if that returns
    False because a stale TOTP exists and the Bliss record is revoked, delete the engine user, then
    `ensure_without2fa` again.

  Matching is case-insensitive. Disabled accounts get nothing. An exception on one account is
  recorded in `errors` and does not stop the others.

- [ ] **Step 1: Failing tests**

```python
# apps/appliance-api/tests/test_coverage.py
from appliance.coverage import reconcile
from appliance.models import MfaUser, UserStatus


class FakeEngine:
    def __init__(self, totp=(), fail=()):
        self.kind = {u.lower(): "t" for u in totp}
        self.fail = {f.lower() for f in fail}
        self.deleted = []

    def ensure_without2fa(self, username):
        if username.lower() in self.fail:
            raise RuntimeError("engine down")
        if self.kind.get(username.lower()) == "t":
            return False
        self.kind[username.lower()] = "w"
        return True

    def without2fa_status(self, username):
        k = self.kind.get(username.lower())
        return {"without2fa": k == "w", "exists": k is not None}

    def delete_user(self, username):
        self.deleted.append(username)
        self.kind.pop(username.lower(), None)
        return True


ACCOUNTS = [
    {"username": "Abhishek", "display_name": None, "enabled": True},
    {"username": "Ekta", "display_name": None, "enabled": True},
    {"username": "JSmith", "display_name": None, "enabled": True},
    {"username": "Pending", "display_name": None, "enabled": True},
    {"username": "Gone", "display_name": None, "enabled": True},
    {"username": "Guest", "display_name": None, "enabled": False},
]


def user(name, status):
    return MfaUser(username=name, engine_username=name, status=status)


def test_rows_of_the_coverage_table():
    engine = FakeEngine(totp=["jsmith", "pending", "gone"])
    users = [user("jsmith", UserStatus.active), user("Pending", UserStatus.pending), user("Gone", UserStatus.revoked)]
    result = reconcile(ACCOUNTS, users, engine, recovery="ABHISHEK")
    assert result["protected"] == ["JSmith", "Pending"]           # case-insensitive match
    assert sorted(result["password_only"]) == ["Ekta", "Gone"]
    assert engine.kind["ekta"] == "w" and engine.kind["gone"] == "w"
    assert engine.deleted == ["Gone"]                             # stale TOTP of a revoked record replaced
    assert "abhishek" not in engine.kind and "guest" not in engine.kind
    assert engine.kind["jsmith"] == "t"                           # enrollment never touched


def test_one_failure_does_not_stop_others():
    engine = FakeEngine(fail=["Ekta"])
    result = reconcile(ACCOUNTS[:3], [], engine, recovery="Abhishek")
    assert result["errors"] == ["Ekta"] and result["password_only"] == ["JSmith"]


def test_unexpected_totp_without_bliss_record_is_left_alone():
    engine = FakeEngine(totp=["ekta"])
    result = reconcile(ACCOUNTS[1:2], [], engine, recovery=None)
    assert result["errors"] == ["Ekta"] and engine.deleted == []
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement**

```python
# apps/appliance-api/appliance/coverage.py
"""Keep every enabled local account known to multiOTP while RDP protection is on.

Enrolled accounts keep their TOTP record. Every other enabled account gets a without2FA record
(password-only RDP, no license seat). Unknown accounts would otherwise be refused over RDP.
"""
from __future__ import annotations

from .models import UserStatus

PROTECTED = {UserStatus.active, UserStatus.pending, UserStatus.locked, UserStatus.disabled}


def reconcile(accounts, mfa_users, engine, recovery):
    records = {u.username.lower(): u for u in mfa_users}
    result = {"password_only": [], "protected": [], "errors": []}
    for account in accounts:
        name = account["username"]
        if not account["enabled"] or (recovery and name.lower() == recovery.lower()):
            continue
        record = records.get(name.lower())
        if record and record.status in PROTECTED:
            result["protected"].append(name)
            continue
        try:
            if not engine.ensure_without2fa(name):
                if not (record and record.status == UserStatus.revoked):
                    raise RuntimeError("TOTP record without a Bliss enrollment")
                engine.delete_user(name)
                if not engine.ensure_without2fa(name):
                    raise RuntimeError("Could not create password-only record")
            result["password_only"].append(name)
        except Exception:  # noqa: BLE001 - one account must not block the others
            result["errors"].append(name)
    return result
```

- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Coverage reconciler: password-only records for non-enrolled accounts"`

---

### Task 6: API endpoints, enrollment hooks and recovery-account guard

**Files:**
- Modify: `apps/appliance-api/appliance/main.py`
- Modify: `apps/appliance-api/appliance/schemas.py` (request model)
- Test: `apps/appliance-api/tests/test_rdp_protection_api.py`

**Interfaces:**
- Consumes: `ProviderRegistry` (Task 3), `native_verify`, `NativeVerifyUnavailable` (Task 4),
  `reconcile` (Task 5), `read_local_windows_accounts`, `find_mfa_user`, `verify_password`, `write_audit`.
- Produces:
  - `provider_registry()` factory in `main` (monkeypatchable);
  - `GET /v1/rdp-protection` (admin) → `{"on": bool, "recovery_account": str|None, "protected": [..], "password_only": [..], "disabled": [..]}`;
  - `POST /v1/rdp-protection/enable` (owner) with body `RdpProtectionEnable{password: str, username: str, otp: str}`;
  - `POST /v1/rdp-protection/disable` (owner) with body `RdpProtectionDisable{password: str}`.
- Behaviour changes:
  - `create_user` refuses the recovery account (409, "is the recovery account; it is always excluded from MFA and never uses a seat");
  - after `delete_user` / `revoke_user` / `verify_enrollment`, when protection is on, run `reconcile` (best effort; errors are logged in audit, not raised).

- [ ] **Step 1: Failing tests** (reuse the `env` fixture style from `tests/test_windows_accounts.py`;
  the principal is the owner; a real `LocalAdmin` row carries the password hash)

```python
# apps/appliance-api/tests/test_rdp_protection_api.py
import json
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from appliance import main
from appliance.db import Base, get_db
from appliance.models import AdminRole, LocalAdmin, MfaUser, UserStatus
from appliance.security import Principal, current_principal, hash_password
from tests.test_rdp_protection_registry import FakeBackend
from tests.test_coverage import FakeEngine
from appliance.rdp_protection import ProviderRegistry

ACCOUNTS = [{"username": "Abhishek", "display_name": None, "enabled": True},
            {"username": "Ekta", "display_name": None, "enabled": True},
            {"username": "JSmith", "display_name": "John", "enabled": True}]


@pytest.fixture
def env(monkeypatch):
    engine_db = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine_db)
    db = Session(engine_db)
    owner = LocalAdmin(email="o@example.com", password_hash=hash_password("owner-password-123"), role=AdminRole.owner)
    db.add(owner)
    db.add(MfaUser(username="JSmith", engine_username="JSmith", status=UserStatus.active))
    db.commit()
    backend, engine = FakeBackend(), FakeEngine(totp=["jsmith"])
    state = {"verify": True, "role": AdminRole.owner}
    monkeypatch.setattr(main, "provider_registry", lambda: ProviderRegistry(backend))
    monkeypatch.setattr(main, "multiotp", lambda: engine)
    monkeypatch.setattr(main, "read_local_windows_accounts", lambda: [dict(a) for a in ACCOUNTS])
    monkeypatch.setattr(main, "native_verify", lambda u, o: state["verify"])
    monkeypatch.setattr(main.license_agent(), "status", lambda: {"state": "active"}, raising=False)
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[current_principal] = lambda: Principal(id=owner.id, email=owner.email, role=state["role"])
    yield TestClient(main.app), backend, engine, state, db
    main.app.dependency_overrides.clear()
    db.close()


GOOD = {"password": "owner-password-123", "username": "JSmith", "otp": "123456"}


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
    ({"username": "Ekta"}, 409),        # not an enrolled, verified account
    ({"username": "Abhishek"}, 409),    # recovery account
])
def test_enable_refusals_change_nothing(env, change, code):
    client, backend, engine, *_ = env
    before = dict(backend.values)
    assert client.post("/v1/rdp-protection/enable", json={**GOOD, **change}).status_code == code
    assert backend.values == before and "ekta" not in engine.kind


def test_wrong_code_changes_nothing(env):
    client, backend, _, state, _ = env
    state["verify"] = False
    before = dict(backend.values)
    assert client.post("/v1/rdp-protection/enable", json=GOOD).status_code == 400
    assert backend.values == before


def test_enable_refused_when_accounts_cannot_be_listed(env, monkeypatch):
    client, backend, *_ = env
    def broken():
        raise main.HTTPException(502, "Could not read local Windows accounts")
    monkeypatch.setattr(main, "read_local_windows_accounts", broken)
    before = dict(backend.values)
    assert client.post("/v1/rdp-protection/enable", json=GOOD).status_code == 502
    assert backend.values == before


def test_disable_works_even_when_license_lapsed(env, monkeypatch):
    client, backend, *_ = env
    client.post("/v1/rdp-protection/enable", json=GOOD)
    monkeypatch.setattr(main, "license_agent", lambda: type("L", (), {"status": lambda self: {"state": "expired"}})())
    assert client.post("/v1/rdp-protection/disable", json={"password": "owner-password-123"}).status_code == 200
    assert backend.values["cpus_logon"] == "3d"


@pytest.mark.parametrize("role", [AdminRole.admin, AdminRole.operator, AdminRole.readonly])
def test_only_owner_can_change(env, role):
    client, _, _, state, _ = env
    state["role"] = role
    assert client.post("/v1/rdp-protection/enable", json=GOOD).status_code == 403
    assert client.post("/v1/rdp-protection/disable", json={"password": "x"}).status_code == 403


@pytest.mark.parametrize("name", ["Abhishek", "ABHISHEK", "abhishek"])
def test_recovery_account_cannot_be_enrolled(env, monkeypatch, name):
    client, *_ = env
    monkeypatch.setattr(main.os, "name", "nt")
    monkeypatch.setattr(main.settings, "windows_account_validation", "auto")
    monkeypatch.setattr(main.subprocess, "run", lambda a, **k: subprocess.CompletedProcess(a, 0, json.dumps(ACCOUNTS), ""))
    r = client.post("/v1/users", json={"username": name})
    assert r.status_code == 409 and "recovery account" in r.json()["detail"]


def test_delete_while_on_leaves_password_only_record(env):
    client, _, engine, _, db = env
    client.post("/v1/rdp-protection/enable", json=GOOD)
    jsmith = db.query(MfaUser).filter_by(username="JSmith").one()
    assert client.delete(f"/v1/users/{jsmith.id}", params={"reason": "test removal"}).status_code == 204
    assert engine.kind["jsmith"] == "w"
```

The license-agent and `delete_user` fakes may need extending to match the existing
`delete_user` code path, which calls `multiotp().delete_user` and the seat release. Use
`FakeEngine.delete_user` and a fake `license_agent` exposing `status`, `reserve_seat` and
`release_seat`, as in `test_windows_accounts.py`.

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** In `schemas.py`:

```python
class RdpProtectionEnable(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    username: str = Field(pattern=r"^[A-Za-z0-9_.@-]{1,100}$")
    otp: str = Field(pattern=r"^\d{6}$")


class RdpProtectionDisable(BaseModel):
    password: str = Field(min_length=1, max_length=256)
```

In `main.py` (imports: `from .rdp_protection import ProviderRegistry, ProviderWriteError`,
`from .native_verify import native_verify, NativeVerifyUnavailable`, `from .coverage import reconcile`,
`from .models import LocalAdmin`, `from .security import verify_password`, and the new schemas):

```python
def provider_registry() -> ProviderRegistry:
    return ProviderRegistry()


def owner_reauth(db: Session, principal: Principal, password: str) -> None:
    admin = db.get(LocalAdmin, principal.id)
    if not admin or not verify_password(admin.password_hash, password):
        raise HTTPException(401, "Password not accepted")


def coverage_now(db: Session, registry: ProviderRegistry) -> dict:
    return reconcile(read_local_windows_accounts(), list(db.scalars(select(MfaUser))),
                     multiotp(), registry.recovery_account())


def reconcile_if_on(db: Session, actor_id: str | None) -> None:
    try:
        registry = provider_registry()
        if registry.is_on():
            result = coverage_now(db, registry)
            if result["errors"]:
                write_audit(db, actor_id=actor_id, action="rdp.coverage.failed", subject_type="windows_account",
                            subject_id=None, reason=",".join(result["errors"]), success=False)
                db.commit()
    except Exception:  # noqa: BLE001 - coverage is retried by the periodic job
        pass


@app.get("/v1/rdp-protection")
def rdp_protection_status(_: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    registry = provider_registry()
    accounts = read_local_windows_accounts()
    recovery = registry.recovery_account()
    records = {u.username.lower(): u for u in db.scalars(select(MfaUser))}
    protected, password_only, disabled = [], [], []
    for a in accounts:
        name = a["username"]
        if recovery and name.lower() == recovery.lower():
            continue
        if not a["enabled"]:
            disabled.append(name)
        elif (r := records.get(name.lower())) and r.status != UserStatus.revoked:
            protected.append(name)
        else:
            password_only.append(name)
    return {"on": registry.is_on(), "recovery_account": recovery, "protected": protected,
            "password_only": password_only, "disabled": disabled}


@app.post("/v1/rdp-protection/enable")
def rdp_protection_enable(payload: RdpProtectionEnable, request: Request,
                          principal: Principal = Depends(require_owner), db: Session = Depends(get_db)) -> dict:
    owner_reauth(db, principal, payload.password)
    registry = provider_registry()
    recovery = registry.recovery_account()
    if recovery and payload.username.lower() == recovery.lower():
        raise HTTPException(409, "Choose an enrolled account other than the recovery account")
    user = find_mfa_user(db, payload.username)
    if not user or user.status != UserStatus.active:
        raise HTTPException(409, "Enroll and verify this account before turning on RDP protection")
    try:
        if license_agent().status().get("state") not in {"active", "offline_grace"}:
            raise HTTPException(403, "Activate your license before turning on RDP protection")
    except (httpx.HTTPError, RuntimeError):
        raise HTTPException(503, "License agent unavailable") from None
    try:
        if not native_verify(user.engine_username, payload.otp):
            raise HTTPException(400, "Code not accepted. Wait for the next code and try again.")
    except NativeVerifyUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    accounts = read_local_windows_accounts()  # raises 502/503 before anything changes
    result = reconcile(accounts, list(db.scalars(select(MfaUser))), multiotp(), recovery)
    if result["errors"]:
        raise HTTPException(502, "Could not prepare password-only access for: " + ", ".join(result["errors"]))
    try:
        registry.apply(True)
    except ProviderWriteError as exc:
        raise HTTPException(500, str(exc)) from None
    write_audit(db, actor_id=principal.id, action="rdp.protection.enabled", subject_type="mfa_user",
                subject_id=user.id, reason=f"password_only={len(result['password_only'])}",
                source_ip=request.client.host if request.client else None)
    db.commit()
    return {"on": True, **result}


@app.post("/v1/rdp-protection/disable")
def rdp_protection_disable(payload: RdpProtectionDisable, request: Request,
                           principal: Principal = Depends(require_owner), db: Session = Depends(get_db)) -> dict:
    owner_reauth(db, principal, payload.password)
    try:
        provider_registry().apply(False)
    except ProviderWriteError as exc:
        raise HTTPException(500, str(exc)) from None
    write_audit(db, actor_id=principal.id, action="rdp.protection.disabled", subject_type="provider",
                subject_id=None, source_ip=request.client.host if request.client else None)
    db.commit()
    return {"on": False}
```

In `validated_windows_username` (before the "disabled" check), add the recovery guard:

```python
    try:
        recovery = provider_registry().recovery_account()
    except OSError:
        recovery = None
    if recovery and match["username"].lower() == recovery.lower():
        raise HTTPException(409, f"'{match['username']}' is the recovery account; it is always excluded "
                                 "from MFA and never uses a seat")
```

Name the matched local-account variable as it's called in the existing function. Wrap
`provider_registry()` so that a host without the provider (tests, Linux) yields `None`; catching
`OSError` and `ImportError` covers both.

At the end of `verify_enrollment` (after commit), `delete_user` (after commit) and `revoke_user`
(after the `reason_command` result), call `reconcile_if_on(db, principal.id)`.

- [ ] **Step 4: Run the full API suite.**
  Run `apps/appliance-api/.venv/Scripts/python -m pytest apps/appliance-api/tests -q`. Expected: all pass.
  `conftest.py` sets validation "off". Make sure `provider_registry` is monkeypatched where the
  recovery guard runs (Windows dev host), or add to `conftest.py`:
  `monkeypatch.setattr(main, "provider_registry", lambda: ProviderRegistry(FakeBackend()))`.
- [ ] **Step 5: Lint.** Run `ruff check apps/appliance-api`.
- [ ] **Step 6: Commit** `git commit -m "RDP protection API: owner re-auth, native code check, coverage, recovery guard"`

---

### Task 7: Periodic coverage and runtime wiring

**Files:**
- Modify: `apps/appliance-api/appliance/main.py` (scheduler next to the heartbeat scheduler)
- Modify: `scripts/appliance-runtime.py` (`api_env`)
- Test: `apps/appliance-api/tests/test_rdp_protection_api.py` (add), `scripts/tests/test_retained_state.py` or new `scripts/tests/test_runtime_env.py`

**Interfaces:**
- Produces: `periodic_coverage() -> None`. It calls `reconcile_if_on` with a fresh session, every 600 s,
  started and stopped with the heartbeat scheduler, and is not started when `APP_ENV=test`.
- `api_env` gains `ENGINE_CONFIG_FILE=<engine config.json>` and `PROVIDER_VALIDATION_DIR=<root>/provider-validation`.

- [ ] **Step 1: Failing tests.**

```python
# appended to apps/appliance-api/tests/test_rdp_protection_api.py
def test_periodic_coverage_adds_new_account(env, monkeypatch):
    client, _, engine, _, db = env
    client.post("/v1/rdp-protection/enable", json=GOOD)
    monkeypatch.setattr(main, "read_local_windows_accounts",
                        lambda: [*ACCOUNTS, {"username": "NewHire", "display_name": None, "enabled": True}])
    monkeypatch.setattr(main, "SessionLocal", lambda: db, raising=False)
    main.periodic_coverage()
    assert engine.kind["newhire"] == "w"


def test_periodic_coverage_does_nothing_when_off(env, monkeypatch):
    _, _, engine, _, db = env
    monkeypatch.setattr(main, "SessionLocal", lambda: db, raising=False)
    main.periodic_coverage()
    assert "ekta" not in engine.kind
```

```python
# scripts/tests/test_runtime_env.py
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("appliance_runtime", SCRIPTS / "appliance-runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def test_api_env_has_engine_config_and_validation_dir(tmp_path):
    repo = tmp_path / "root" / "bliss-mfa"
    (tmp_path / "root/node").mkdir(parents=True)
    (tmp_path / "root/node/node.exe").write_bytes(b"")
    (tmp_path / "root/portal").mkdir()
    (tmp_path / "root/portal/server.js").write_text("")
    state = repo / ".local/engine"
    state.mkdir(parents=True)
    (state / "appliance.json").write_text(json.dumps({
        "database_file": str(state / "a.db"), "jwt_secret": "j", "setup_token": "s", "company_name": "c",
        "agent_port": 1, "agent_token": "a", "api_port": 2, "portal_port": 3, "tls_port": 4,
        "license_url": "https://x", "public_key_file": "k", "license_state_dir": str(state)}))
    engine_config = {"adapter_port": 5, "adapter_token": "t", "certificate_file": "c", "certificate_key_file": "k",
                     "config_file": str(state / "config.json")}
    procs = runtime.processes(repo, engine_config, state, "python")
    api = next(env for name, _, env, *_ in procs if name == "appliance-api")
    assert api["ENGINE_CONFIG_FILE"] == str(state / "config.json")
    assert api["PROVIDER_VALIDATION_DIR"] == str(tmp_path / "root/provider-validation")
```

Read `processes()` first. If `engine_config` doesn't carry its own path, pass
`state_parent / 'engine' / 'config.json'`; the engine config lives in the same `.local/engine`
directory as `appliance.json`. Adjust the expected path to match.

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.** In `appliance-runtime.py`'s `api_env = dict(...)`, add
  `ENGINE_CONFIG_FILE=str(state_parent / 'config.json')` (the directory holding appliance.json, i.e.
  `.local/engine`) and `PROVIDER_VALIDATION_DIR=str(repo.parent / 'provider-validation')`. In `main.py`:

```python
COVERAGE_INTERVAL_SECONDS = 600


def periodic_coverage() -> None:
    db = SessionLocal()
    try:
        reconcile_if_on(db, None)
    finally:
        db.close()
```

Register it in `start_heartbeat_scheduler` with the same scheduler mechanism the heartbeat uses
(read that function and mirror it: a daemon thread or timer re-arming every
`COVERAGE_INTERVAL_SECONDS`). Stop it in `stop_heartbeat_scheduler`. Import `SessionLocal` from
`.db` (check the existing name used by the heartbeat).

- [ ] **Step 4: Run** the API suite and `scripts/tests/test_runtime_env.py`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Periodic RDP coverage; pass engine config to the appliance API"`

---

### Task 8: Portal: RDP protection card and post-enrollment prompt

**Files:**
- Create: `apps/appliance-portal/components/RdpProtection.tsx`
- Modify: `apps/appliance-portal/components/UserConsole.tsx` (render the card on the Dashboard)
- Modify: `apps/appliance-portal/components/EnrollmentPanel.tsx` (after a successful verify, show
  "Protect RDP sign-in now?" when protection is off)
- Modify: `apps/appliance-portal/README.md` (one paragraph)

**Interfaces:**
- Consumes: `GET /v1/rdp-protection`, `POST /v1/rdp-protection/enable`, `POST /v1/rdp-protection/disable`,
  through the existing `api<T>(path, init)` helper used in `EnrollmentPanel.tsx` (the backend proxy adds `/v1`).
- Produces: `export function RdpProtection({ suggestedUser }: { suggestedUser?: string })`.

- [ ] **Step 1: Implement the component**

```tsx
// apps/appliance-portal/components/RdpProtection.tsx
"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Status = { on: boolean; recovery_account: string | null; protected: string[]; password_only: string[]; disabled: string[] };

export function RdpProtection({ suggestedUser }: { suggestedUser?: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState(suggestedUser ?? "");
  const [otp, setOtp] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api<Status>("/rdp-protection").then(setStatus).catch((e) => setMessage(String(e.message ?? e)));
  useEffect(() => { load(); }, []);
  useEffect(() => { if (suggestedUser) setUsername(suggestedUser); }, [suggestedUser]);

  async function submit() {
    setBusy(true); setMessage(null);
    try {
      if (status?.on) {
        await api("/rdp-protection/disable", { method: "POST", body: JSON.stringify({ password }) });
      } else {
        await api("/rdp-protection/enable", { method: "POST", body: JSON.stringify({ password, username, otp }) });
      }
      setOpen(false); setPassword(""); setOtp(""); await load();
    } catch (e: any) { setMessage(e?.message ?? "Request failed"); } finally { setBusy(false); }
  }

  if (!status) return message ? <p className="error">{message}</p> : null;
  return (
    <section className="card">
      <h2>RDP protection: {status.on ? "On" : "Off"}</h2>
      <p>Only Remote Desktop sign-in is protected. Signing in at the computer itself never asks for a code.</p>
      <p>Recovery account (never asked for a code): <strong>{status.recovery_account ?? "not set"}</strong></p>
      <p>Code required over RDP: {status.protected.join(", ") || "none"}</p>
      <p>Password only over RDP (not enrolled): {status.password_only.join(", ") || "none"}</p>
      {!open && <button onClick={() => setOpen(true)}>{status.on ? "Turn off RDP protection" : "Turn on RDP protection"}</button>}
      {open && (
        <div className="form">
          <label>Your portal password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {!status.on && <>
            <label>Enrolled Windows account<select value={username} onChange={(e) => setUsername(e.target.value)}>
              <option value="">Choose…</option>
              {status.protected.map((n) => <option key={n} value={n}>{n}</option>)}
            </select></label>
            <label>Fresh code for that account<input inputMode="numeric" maxLength={6} value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} /></label>
            <p>After this, enrolled accounts are asked for a code on a second screen when they connect over RDP. Other accounts keep signing in over RDP with their password.</p>
          </>}
          <button disabled={busy || !password || (!status.on && (!username || otp.length !== 6))} onClick={submit}>
            {status.on ? "Turn off" : "Turn on"}</button>
          <button onClick={() => { setOpen(false); setMessage(null); }}>Cancel</button>
        </div>
      )}
      {message && <p className="error">{message}</p>}
    </section>
  );
}
```

Match the import of `api` and the CSS class names to what `EnrollmentPanel.tsx` and
`WindowsAccounts.tsx` already use. Read them first and copy their exact helper import and
class conventions.

- [ ] **Step 2: Wire it in.**
  - **Dashboard:** in `UserConsole.tsx`, render `<RdpProtection />` above the "MFA accounts" section.
  - **Enrollment panel:** in `EnrollmentPanel.tsx`, after the successful-verify branch calls
    `onVerified(username)`, render `<RdpProtection suggestedUser={username} />`, so the owner can turn
    it on right away.
- [ ] **Step 3: Build.** Run `npm --prefix apps/appliance-portal run build`. Expected: success, no type errors.
- [ ] **Step 4: Browser check.** Use the demo backend (`tools/dev_windows_accounts_demo.py`): add fakes
  there for `provider_registry` (the `FakeBackend` from the tests) and `native_verify`
  (accepts `000000`). Then:
  1. enroll `demo.alice`;
  2. turn on protection (password, code `000000`);
  3. confirm the card shows On with alice protected and bob/carol password-only;
  4. turn it off.
- [ ] **Step 5: Commit** `git commit -m "Portal: RDP protection card and post-enrollment prompt"`

---

### Task 9: Docs and acceptance on real Windows

**Files:**
- Modify: `scripts/build-client-release.py` (README text: replace step 5 "Run Enable-RdpProtection.cmd" with the dashboard flow; keep the script as recovery)
- Modify: `docs/windows-paid-pilot.md` (RDP protection section)
- Create: `docs/rdp-protection-acceptance-2026-10.md` (results)

- [ ] **Step 1: Update texts.**
  - **README in `build-client-release.py`, step 5:** "In the portal, after verifying your first
    account, choose Turn on RDP protection, enter your portal password and a fresh code. Enrolled
    accounts are asked for a code over RDP; other accounts keep password-only RDP access. Console
    sign-in is never affected."
  - **Recovery text:** keep the existing `Enable-RdpProtection.ps1 -Disable` line.
- [ ] **Step 2: Run the script tests.** Run `.venv-scripts/Scripts/python -m pytest scripts/tests -q`. Expected: pass.
- [ ] **Step 3: Build a test release and install it on the VM.** Use `build-release.py --version 0.1.7`, the exe
  wrapper and the "fresh-install-0.1.6-exe" or "rdp-test-ready" checkpoint.
- [ ] **Step 4: Run the spec's acceptance list** and record results in `docs/rdp-protection-acceptance-2026-10.md`:
  1. an enrolled account over RDP gets a second-step code screen; correct/wrong/empty/reused codes;
  2. a password-only account over RDP gets no code screen;
  3. a newly created account is refused until reconciliation (≤10 min), then password-only;
  4. a non-excluded account signing in locally gets no code screen;
  5. the recovery account over RDP and locally gets no code screen;
  6. Turn off in the dashboard restores normal RDP;
  7. turn on, then `Stop-VM -TurnOff` after 1 minute: values are still `1e`/`1e`/`3d`/`1`/`1` after boot.
- [ ] **Step 5: Commit**

```bash
git add scripts/build-client-release.py docs
git commit -m "Docs: dashboard RDP protection; acceptance results"
```
