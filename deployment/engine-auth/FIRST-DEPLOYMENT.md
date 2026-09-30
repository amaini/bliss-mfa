# First disposable-VM deployment

Target: `WIN-10VM-ASUS`, Windows 10 Pro x64 build 19045, Tailscale `100.83.112.5`.
Scope: engine and Windows RDP integration. Payment, email, public hosting,
appliance UI, and customer self-onboarding are later stages.

## Installed layout

- `C:\BlissMFA`: administrator/SYSTEM-only engine runtime and persistent state.
- `C:\BlissMFA\bliss-mfa\.local\engine\config.json`: private engine configuration.
- `C:\BlissMFA\Prototype-Enrollment.html`: private test-account enrollment page.
- `C:\Program Files\multiOTP`: signed upstream credential provider client 5.10.2.2.
- `C:\Windows\System32`: signed upstream provider and filter DLLs 5.10.2.2.
- Scheduled task `BlissMFA-PrototypeEngine`: SYSTEM, startup trigger, restart on
  process failure, no runtime limit. This is prototype supervision, not a
  production Windows service.

The task is allowed to start and continue on battery power. The default Task
Scheduler battery restriction initially prevented boot startup on this target;
the corrected settings were verified through a second reboot. WinRM starts
immediately rather than through delayed automatic startup, and Tailscale was
already configured for unattended operation.

The management adapter listens at `http://127.0.0.1:18090`; its routes require the
private adapter bearer token. The native client endpoint listens at
`https://127.0.0.1:18443/auth`. Both listeners stay on loopback.
The adapter Swagger UI is at `http://127.0.0.1:18090/docs` inside the VM.

The engine package contains Python 3.12.10's Windows embedded distribution,
portable PHP 8.3.35, pinned Python wheels, the patched engine, and its complete
contribution libraries. The installed provider contains its own PHP 8.5.4 runtime.
The engine uses Python's prototype TLS proxy and PHP's development server;
production runtime upgrades, service hosting, packaging, and release signing
remain required before client distribution.

## RDP policy and trust

`cpus_logon=1e` and `cpus_unlock=1e` enforce multiOTP for RDP. Local console sign-in
keeps its usual password path. `cpus_credui=3d` leaves administrative prompts on
their normal path. `WIN-10VM-ASUS\Abhishek` is the explicit recovery exception.
The test account `bliss_proto_test` is a standard user in Users and Remote Desktop
Users, not Administrators.

Offline OTP caching and Without2FA bypass are disabled. The provider's native
XML PHP client has TLS peer and hostname verification enabled. Its `php.ini`
pins the local engine certificate through `openssl.cafile`; the Windows machine
trust store was not changed. The original PHP and INI files are backed up under
`C:\BlissMFA\provider-backup`.

## Operator acceptance

As the existing administrator, open `C:\BlissMFA\Prototype-Enrollment.html` on
the VM. Scan its QR code, reveal the test Windows password, and connect through
RDP as `WIN-10VM-ASUS\bliss_proto_test`. The page contains private enrollment data;
do not include it or the private configuration in diagnostic uploads.

Verify real sign-in with a fresh OTP, rejection of bad/empty OTP, rejection of a
wrong Windows password, and replay denial. Wait for a fresh authenticator interval
after any accepted code. Reconnect and unlock also need interactive acceptance.
The automated client checks and Windows `LogonUser` password checks are independent
proofs; neither substitutes for an actual RDP credential-provider sign-in.

## Recovery and operation

Use the existing administrator exception or encrypted WinRM from controller
`100.68.167.45` to run `C:\BlissMFA\Recover-PrototypeProvider.ps1`. This sets all
three provider scenarios to `3d`, disabling enforcement while preserving the
engine and test identity. WinRM requires encrypted NTLM, Basic is disabled, and
its HTTP firewall rules are limited to the controller and target Tailscale IPs.

Start the engine with `Start-ScheduledTask -TaskName BlissMFA-PrototypeEngine`.
When stopping it, terminate the exact `run-engine.py` supervisor process tree
before ending the task; ending a scheduled task alone does not guarantee child
process cleanup. `scripts/Test-PrototypeRestart.ps1` implements the controlled
stop, outage check, and restart with recovery in `finally`.

Private diagnostic results live at `C:\BlissMFA\acceptance-results.json`,
`runtime-results.json`, `outage-results.json`, and `boot-results.json`.
Child logs live beside the engine state. Preserve `config.json`, the certificate
and key, and state together when backing up this prototype. Backup/restore has
not yet been exercised.

## Repeat packaging and installation

`scripts/build-vm-package.py` builds a secret-free archive with a SHA-256 file
manifest from the local test kit. Its docstring lists the required official
download artifacts and pinned wheels. It includes the engine's `contrib` directory;
the native health check loads the actual class and returns 503 if it cannot load.
The installer checks the manifest and publisher signatures before starting it.

On a clean disposable target, run these scripts in order through encrypted remoting:
`Install-PrototypeEngine.ps1`, `Install-PrototypeProvider.ps1`,
`Patch-PrototypeProviderTrust.ps1`, the installed-client acceptance script,
and `Setup-PrototypeTestAccount.ps1`. Installation deliberately refuses to
overwrite an existing engine or provider. The current scripts target this VM;
general client installation and upgrade/rollback workflows are future work.
