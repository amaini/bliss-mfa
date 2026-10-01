# First disposable-VM deployment

Target: `WIN-10VM-ASUS`, Windows 10 Pro x64 build 19045, Tailscale `100.83.112.5`.
Scope: engine, Windows RDP integration, and the local appliance portal. Public
hosting and the real paid-client journey remain pending. Updated 30 September 2026.

## Installed layout

- `C:\BlissMFA`: administrator/SYSTEM-only engine runtime and persistent state.
- `C:\BlissMFA\bliss-mfa\.local\engine\config.json`: private engine configuration.
- `C:\BlissMFA\Prototype-Enrollment.html`: private test-account enrollment page.
- `C:\Program Files\multiOTP`: signed upstream credential provider client 5.10.2.2.
- `C:\Windows\System32`: signed upstream provider and filter DLLs 5.10.2.2.
- Service `BlissMFAEngine`: SYSTEM, automatic startup, failure restart.
- Scheduled task `BlissMFA-PrototypeEngine`: disabled, retained as an old fallback.
- Private first-owner page: `C:\BlissMFA\bliss-mfa\.local\engine\Open-Appliance.html`.
- Local portal: `https://localhost:19443`, readable inside the VM.

After the manual reboot at 2026-10-01T01:26:38Z, the service started automatically
and all six loopback listeners returned. Five portal checks and eight installed
native-client checks passed again. WinRM and Tailscale allow unattended recovery.

The management adapter listens at `http://127.0.0.1:18090`; its routes require the
private adapter bearer token. The native client endpoint listens at
`https://127.0.0.1:18443/auth`. Both listeners stay on loopback.
The adapter Swagger UI is at `http://127.0.0.1:18090/docs` inside the VM.

The engine package contains Python 3.12.10's Windows embedded distribution,
portable PHP 8.3.35, pinned Python wheels, the patched engine, and its complete
contribution libraries. The installed provider contains its own PHP 8.5.4 runtime.
The engine uses a bounded native TLS gateway and PHP-CGI, supervised alongside
the adapter, appliance API, license agent, Next.js portal, and portal TLS proxy.
Client packaging is prepared; release signing and clean-install acceptance remain.

## RDP policy and trust

`cpus_logon=1e` and `cpus_unlock=1e` enforce multiOTP for RDP. Local console sign-in
keeps its usual password path. `cpus_credui=3d` leaves administrative prompts on
their normal path. `WIN-10VM-ASUS\Abhishek` is the explicit recovery exception.
The test account `bliss_proto_test` is a standard user in Users and Remote Desktop
Users, not Administrators.

Offline OTP caching and Without2FA bypass are disabled. The provider's native
XML PHP client has TLS peer and hostname verification enabled. Its `php.ini`
pins the local engine certificate through `openssl.cafile`. The local CA was
also imported into the Windows machine Root store for browser trust; its key
remains private. The original PHP and INI files are backed up under
`C:\BlissMFA\provider-backup`.

## Operator acceptance

Successful real RDP sign-in is confirmed: the user reported phone OTP acceptance,
and Windows Security event 4624 records a type-10 logon for `bliss_proto_test`
at `2026-09-30T22:11:08.7713890Z`. The user also confirmed wrong-password rejection and successful reconnect.
Interactive bad/empty OTP, replay, and unlock checks below remain pending.

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

Use `Start-Service BlissMFAEngine` and `Stop-Service BlissMFAEngine`. The supervisor
stops its owned child process trees. Do not start the old task alongside the service.

Private diagnostic results live at `C:\BlissMFA\acceptance-results.json`,
`runtime-results.json`, `outage-results.json`, and `boot-results.json`.
Child logs live beside the engine state. Preserve `config.json`, the certificate
and key, and state together when backing up this prototype. An encrypted snapshot
was restored into a new directory and all restored components passed readiness;
the original service then restarted. Current reports are `service-results.json`,
`appliance-results.json`, and `backup-restore-results.json` under `C:\BlissMFA`.

## Repeat packaging and installation

`scripts/build-vm-package.py` builds a secret-free archive with a SHA-256 file
manifest from the local test kit. Its docstring lists the required official
download artifacts and pinned wheels. It includes the engine's `contrib` directory;
the native health check loads the actual class and returns 503 if it cannot load.
The installer checks the manifest and publisher signatures before starting it.

`scripts/build-client-release.py` wraps the appliance archive in fixed-hash setup.
On a clean disposable target, run its `Setup.cmd` as instructed in the release
README. The provider starts with enforcement disabled. Create the owner, activate
a license, enroll a local Windows user, and use the recovery-aware RDP activation
wrapper with a fresh OTP before enforcement. Installation refuses an existing
engine destination. The new wrapper still needs full clean-install acceptance;
this VM exercised existing provider installation and runtime upgrades.
