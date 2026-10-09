# Bliss MFA: what to fix before other installs (2026-10-08)

Scope: 0.1.6–0.1.8 installs on the Windows 10 Pro test VM (`WIN-10VM-ASUS`) and the owner's
Windows 11 Pro laptop (`UX8402ZE`, build 26300). Dashboard RDP protection is in 0.1.7+.

## Status

**Works (verified on the VM, 0.1.8, through the real API, engine and Windows multiOTP client):**
- **Accounts and enrollment.** The Windows Accounts list and Enroll MFA work. The recovery account is labelled
  and isn't offered for enrollment.
- **Turning protection on** from the dashboard checks the owner's password, the license, and a fresh
  code verified by the installed client. It then writes `cpus_logon=1e`, `cpus_unlock=1e`,
  `cpus_credui=3d`, `two_step_hide_otp=1` and `multiOTPWithout2FA=1`.
- **Password-only access.** Non-enrolled accounts get password-only records. The enrolled account
  keeps its code record, and the recovery account gets no record.
- **Turning protection off** restores `3d`.
- **Install, update and key:**
  - fresh install from `Setup-BlissMFA-0.1.6.exe`;
  - reinstall over retained data;
  - signed updates with the new key (0.1.5→0.1.6→0.1.7→0.1.8);
  - old-key installs refuse new-key updates.
- **Real RDP (spike, laptop):** a password-only account signs in with no code screen when the
  two-step settings are on. A wrong code is refused, and the recovery account is never asked locally or over RDP.

**Not yet verified on real RDP with the 0.1.8 dashboard flow:** an enrolled account getting the
second-step code screen, and a non-excluded user signing in at the console with no code.

## Fixed in this round (ship in the next release)

| Issue | Effect on an install | Fix |
|---|---|---|
| Portal pages cached for a year (`s-maxage=31536000`) through the HTTPS proxy, with a build ID that didn't change between builds | After an update the browser kept showing the **old dashboard**; the RDP protection card was missing on the laptop | Proxy sends `no-store` for everything except `/_next/static/`. Releases must build the portal (no `--skip-portal-build`) so the build ID is the commit |
| Next.js route cache (`portal/.next/server/route-cache/...`) kept the **previous version's pages** across application updates (same folder name every build) | Laptop served 0.1.6 pages after updating to 0.1.7/0.1.8 (no RDP protection card); VM served 0.1.7 pages on 0.1.8 and the Windows Accounts page crashed ("client-side exception") | 0.1.9: the supervisor deletes the route cache before starting the portal; the account list never crashes on an unknown state |
| No way to recover a forgotten portal owner password | The owner was locked out of the dashboard on the laptop (account and sign-in route verified working) | `scripts/reset-owner-password.py`: Windows-administrator-only reset of the owner's password (typed, never shown), re-enables the owner, audited. Add a Start-menu shortcut in the installer |
| Recovery account offered "Enroll MFA" and could take the only seat | Owner enrolled their own excluded account; no seat left for real users | API refuses it (409); list labels it "Recovery account · never asked for a code" |
| Customers had to run `Enable-RdpProtection.cmd` | Not possible for customers | Dashboard card with owner re-auth and a native-client code check |
| Enrolling right after verify reused the same code | "Code not accepted" on the first try | Form asks for the next code |
| Lost update signing key | No signed update could ever ship | Key rotated (`63983efc…`); backup script added |
| Single-file setup | Testers had to unzip and run a `.cmd` | `Setup-BlissMFA-<ver>.exe` (self-elevating, 64-bit relaunch, `/Q` silent works) |

## Must fix or decide before more installs

1. **Merge and CI.**
   - Merge `feature/windows-account-enrollment`, `chore/rotate-update-key` and
     `design/dashboard-rdp-protection` through PRs.
   - Releases 0.1.7/0.1.8 were built from local merge branches (`release/0.1.7-test`).
   - Rebuild the release from the merged branch with CI green.
2. **Back up the new update key.** Two offline copies (`scripts/backup-update-key.py`). Still a single copy.
3. **Durability after power loss.**
   - The VM lost its `BlissMFAEngine` service registration when the host cut power ~6 min after
     install. Not reproduced in isolation.
   - Add `RegFlushKey` after service install in `Install-EngineService.ps1`, and a post-install/boot
     check that the service exists.
   - The RDP protection settings already flush.
4. **Account names outside `[A-Za-z0-9_.@-]`** (e.g. with spaces) make Turn on fail with 502
   ("Could not prepare password-only access for: …"). Support or explicitly skip such names, with
   a warning that they will be refused over RDP.
5. **Real-RDP acceptance on 0.1.8:**
   - an enrolled account gets the second-step code screen;
   - correct/wrong/empty/reused codes;
   - a new account is password-only within 10 minutes;
   - console sign-in is unaffected for a non-excluded user;
   - Turn off restores normal RDP;
   - a hard power-off 1 minute after Turn on keeps the settings.
6. **Installer polish.**
   - Code-sign the exe and the PowerShell scripts (SmartScreen warns today).
   - Double-click elevation of the exe is untested on a desktop.
   - `Start-Setup.cmd` copies setup files to `%ProgramFiles%\Bliss MFA\Setup\<ver>`, and nothing
     removes old versions.
7. **Port confusion.** The portal's internal HTTP port `19043` is reachable on localhost. A browser
   that autocompletes `https://localhost:19043` shows `ERR_SSL_PROTOCOL_ERROR`. Bind the internal
   port to a random/ephemeral port or document `https://localhost:19443` only (shortcuts are correct).
8. **Windows 11 coverage.** The laptop (Windows 11 26300, an Insider-range build) installed and ran,
   but the RDP code path was only spike-tested there. Test a released Windows 11 build.
9. **Test VM hygiene.** Hyper-V stop action is `TurnOff`, so host shutdowns hard-kill the VM.
   Set it to `ShutDown` for test VMs.
10. **Update feed.** `/updates/stable.json` is not deployed. Publish only after items 1, 2 and 5.

## Install checklist for the next tester

1. Use Windows 10/11 **Pro** x64, signed in as the local administrator you keep for recovery (it is
   excluded from MFA automatically).
2. Run `Setup-BlissMFA-<ver>.exe` and accept elevation. Open the **Bliss MFA Portal** shortcut
   (`https://localhost:19443`).
3. Create the owner and activate the license.
4. **Windows Accounts → Enroll MFA** for a non-admin account, scan and verify.
5. In "Protect RDP sign-in now?", enter the owner password and the **next** code, then **Turn on**.
6. RDP in as the enrolled account (password, then code). Other accounts use their password only.
7. To recover: sign in at the console (never asks for a code) and use **Turn off**, or run
   `Enable-RdpProtection.ps1 -Disable` as admin.
