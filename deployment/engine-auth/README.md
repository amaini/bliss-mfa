# Real engine prototype

Current priority: prove the local engine and Windows integration before connecting
public domains, delivery email, or real payments.

## Start from this Windows test kit

Run at the extracted kit root using the included Python environment:

```powershell
& .\work\venv\Scripts\python.exe .\work\bliss-mfa\scripts\run-engine.py
```

The private configuration has already been generated at
`work/bliss-mfa/.local/engine/config.json`. On a fresh kit initialize it once:

```powershell
& .\work\venv\Scripts\python.exe .\work\bliss-mfa\scripts\run-engine.py --initialize
```

Initialization refuses to overwrite existing secrets. The launcher uses the real
patched engine and production adapter runner, without the test fault-injection shim.
It starts an authenticated management adapter at `http://127.0.0.1:18090/docs`
and a native XML authentication endpoint at `https://127.0.0.1:18443/auth`.
State persists under `.local/engine/state`. Ctrl+C stops its owned processes.
Use `--check` to verify startup and immediately stop the components.

This foreground launcher and Python TLS proxy are prototype components. They are
not an installed Windows service or a production web server. No firewall,
registry, Windows account, credential provider, or trusted certificate store is
modified. Binding a LAN address and providing a certificate valid for that address
are explicit deployment tasks for the disposable VM stage.

## Manage engine users

Read the `adapter_token` from the private configuration locally and enter
`Bearer <adapter_token>` in the endpoint's `authorization` header field in Swagger.
Create a user through `POST /v1/users`, fetch its provisioning
URI, enroll in an authenticator, and verify a fresh OTP. Enable, disable, unlock,
resynchronize, revoke, and delete are allow-listed routes.

The adapter is a low-level privileged engine interface. Its token is intended for
the local appliance API/operator, not distribution to end users. Licensing, local
administrator roles, and audit belong to the appliance API, not this engine-only
launcher. The engine's stored key material and QR data must stay private.

## Windows provider protocol

The upstream multiOTP Windows provider uses a local multiOTP executable which
contacts a multiOTP server over its XML-over-HTTPS protocol. RADIUS remains a
separate interface for RADIUS consumers. Configure the provider against `/auth`,
using `native_shared_secret`, with offline token caching disabled for the initial
fail-closed prototype. The authentication-only router does not serve vendor web
administration pages.

The imported engine disabled TLS peer and hostname verification by default. This
branch enables both in the default XML transport context in all three shipped
engine implementations. The actual Windows provider must use this patched PHP
client and a trusted CA/certificate configuration before we claim equivalent TLS
behavior. An unmodified upstream installer has not been validated by these tests.
Do not silently disable certificate verification to complete setup.

Upstream provider reference:
https://github.com/multiOTP/multiOTPCredentialProvider

## Repeat the isolated checks

```powershell
& .\work\venv\Scripts\python.exe .\work\run_local_lifecycle.py
& .\work\venv\Scripts\python.exe .\work\run_radius_lifecycle.py
& .\work\venv\Scripts\python.exe .\work\run_engine_https.py
```

Expected totals: 95 lifecycle checks, 16 UDP PAP RADIUS checks, and 17 native HTTPS
checks. Reports are written under `outputs`; timestamped labs remain private
under `work`. These are independent engine/transport checks, not Windows logon
proof. RADIUS uses the bundled legacy FreeRADIUS executable only for compatibility
testing. Failed harness checks must cause a nonzero process exit.

## Pending Windows acceptance

Use a disposable VM with console access and a recovery checkpoint. Record its
Windows build, provider build, client PHP build, certificate trust, username
mapping, and configured logon/unlock paths. Prove actual RDP success with a correct
Windows password and fresh OTP. Deny wrong Windows password, wrong/empty OTP,
replay, disabled/locked/revoked/deleted identity, and engine outage. Reconnect,
unlock, and reboot must enforce the intended policy. Check local console recovery
before any provider installation. A RADIUS Access-Accept or XML code 0 is not
evidence of a Windows login.
