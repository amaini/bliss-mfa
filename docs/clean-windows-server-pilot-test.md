# Clean Windows Server pilot acceptance test

The product is **not pilot-ready** until every step below passes on a clean Windows
Server using only the Bliss download. Record evidence for each step in the results
table at the end. A failure is a release blocker unless explicitly waived.

## Ground rules

- Use a disposable VM snapshot. Never use a production or customer server.
- Do not make real Stripe charges. Use the **14-day trial** (no card) or Stripe
  **test mode** on a non-production backend. A live purchase needs written approval.
- Do not change production license-server state (suspend, revoke, force-release)
  without written approval. This plan has non-production alternatives for each case.
- Keep an independent recovery path open the whole time: the hypervisor console and
  a local administrator that is the provider's excluded recovery account.
- Record: VM edition/build, installer filename + SHA-256, `release.json` source
  commit, timestamps, and screenshots or command output per step.

## 0. Build under test

From CI (`windows-release` job artifact) or locally:

```sh
python scripts/fetch-build-inputs.py --output ../release-build/fetched --cache ../release-build/cache
python scripts/build-release.py --version 0.1.3 --inputs ../release-build/fetched --output ../release-build/rc-0.1.3
```

A production build requires `deployment/windows/keys/update-public.pem` (the pinned
production update key). Without it only a `-TEST` build is possible; a `-TEST` build
can exercise steps 1–20 and 22 but its update test (step 21) must use a test feed.

## Procedure

| # | Step | Expected result / evidence |
|---|---|---|
| 1 | Create a fresh **Windows Server 2022** (and, separately, 2019) VM, fully patched, joined to nothing. Take snapshot `clean`. | `winver` build recorded. |
| 2 | Confirm no developer tooling: `where node npm python py git` and Apps & Features. | All "not found"; no Node, npm, Python, Git, VC build tools. |
| 3 | In the hosted customer portal create a **dedicated test account** (`pilot-test+<date>@…`). | Registration accepted. |
| 4 | Verify the email from the Resend message. | Link verifies the account; sign-in works. |
| 5 | Start the **14-day trial** (no card) — or Stripe test mode on a non-production backend. | One seat, expiry 14 days out; repeat request keeps the original expiry. |
| 6 | Download the installer from the customer portal. | Download allowed only for the active licence. |
| 7 | `Get-FileHash .\bliss-mfa-windows-<v>.zip -Algorithm SHA256` | Equals the portal-displayed SHA-256 and `release.json` `installer.sha256`. Then flip one byte in a copy: the setup must refuse it ("Release archive hash mismatch"). |
| 8 | Extract; run `Setup-BlissMFA.cmd`; accept elevation. | Verifies appliance hash and every manifest file, installs VC++ (signature checked), service `BlissMFAEngine` (Automatic, Running), the stock SysCo provider with enforcement **disabled**, desktop/Start shortcuts, Installed-apps entry. Setup page opens. |
| 9 | Reboot if VC++ returned 3010. | Service returns automatically; `https://localhost:19443` loads. |
| 10 | Create the local owner on the private setup page; on **License**, generate an activation code in the customer portal and activate. | License state `active`, 1 seat; no reactivation prompt afterwards. |
| 11 | On **RDP Users** add one existing local (non-recovery) Windows account. | Seat 1/1 used. Adding a second protected user is **refused** (seat limit). |
| 12 | Scan the QR code with an authenticator app; verify a fresh code. | User becomes active. |
| 13 | Run `Enable-RdpProtection.cmd` (type the account, confirm recovery READY). From another machine RDP in: Windows password + fresh OTP. | Desktop session opens. Wrong password, wrong OTP, empty OTP and a replayed OTP are rejected. Note authentication time (target ≈ 1–2 s). |
| 14 | Reboot the server. | `BlissMFAEngine` starts automatically; portal loads. |
| 15 | Repeat the RDP login test (step 13 success + one rejection). | Same results. |
| 16 | **Licensing outage:** add an outbound Windows Firewall rule blocking `license.blissitek.ca` (or a `hosts` entry `0.0.0.0 license.blissitek.ca`). Restart the service. Wait for the startup heartbeat (≈60 s). | Portal License page still `active`; heartbeat reported unreachable; last lease retained. |
| 17 | With the outage still in place, RDP login with password + fresh OTP. | Login succeeds. Remove the block afterwards. |
| 18 | **Subscription lapse (non-production):** set the VM clock forward beyond lease + grace (≥ 31 days) with the license server blocked. Restart the service. *(With written approval only: suspend/cancel the test licence in production, or cancel a Stripe test-mode subscription on a non-production backend.)* | License page shows `restricted` (or `suspended`/`expired`). |
| 19 | RDP login as the existing protected user. | Login succeeds — lapse never disables existing authentication. |
| 20 | Management restrictions while lapsed: try adding a protected user; try re-enabling a disabled user; lock + unlock the existing user. | Add and re-enable are **refused** with a licence message; lock, unlock and disable still work. Restore the clock and network; the next heartbeat returns `active`. |
| 21 | **Software update:** run "Check for Bliss MFA updates" against a signed feed for a newer version (production feed for production builds; a test HTTPS feed signed with the matching test key for `-TEST` builds). | Signature verified, size/hash checked, service restarts, users/enrollment/licence retained, Installed-apps version updated; RDP login still works. |
| 22 | **Failed update rollback:** publish a signed update whose service fails readiness (e.g. a broken portal or engine file), install it. | Updater restores the previous application and private state automatically; service healthy on the old version; RDP login works. Then run the update shortcut with `-Rollback` after a manual interruption and confirm recovery. |
| 23 | **Component isolation:** stop the portal process (`node.exe` under `C:\BlissMFA`), then the license agent and appliance API processes, one at a time. | RDP login keeps working throughout; each component restarts automatically within ~60 s. |
| 24 | **Reinstall over retained data:** uninstall from Installed apps (type UNINSTALL), reboot, run `Setup-BlissMFA.cmd` again without deleting `C:\BlissMFA`. | Installer reports reinstall with the same `installation_id`; no reactivation needed; user and enrollment intact; protection starts disabled — re-run `Enable-RdpProtection.cmd`; RDP login with the **same** authenticator entry works. |
| 25 | **Lost identity guard:** on a copy of the snapshot, delete `license-state\installation.json`, uninstall, reinstall. | Setup stops with "Retained appliance identity is lost. Nothing was changed." |
| 26 | Uninstall and confirm Windows logon is back to stock behaviour. | Provider removed; console and RDP logon without OTP; subscription unchanged. |

## Results

| # | Pass/Fail | Evidence (file, screenshot, output) | Notes |
|---|---|---|---|
| 1–26 | | | |

Record the installer SHA-256 and source commit at the top of the results. The release
may be offered to pilot customers only when every row passes on Windows Server 2022
(and 2019 if supported) and the code-signing status has been accepted.
