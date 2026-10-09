# Dashboard-managed RDP protection — design

Date: 2026-10-08 · Status: proposed (awaiting owner review) · Builds on `feature/windows-account-enrollment`

## Goal

Customers must be able to turn RDP MFA on and off from the local dashboard as part of
enrollment. They never run `Enable-RdpProtection.cmd` or any script. Local (console) sign-in
is never affected.

## Decisions (owner, 2026-10-08)

- Protection applies to **RDP only**; local sign-in, unlock at the console and admin (UAC)
  prompts are never protected.
- **Non-enrolled accounts keep signing in over RDP with their password only** and must not see
  a code prompt. Only enrolled accounts are asked for a code.
- The installing administrator remains the excluded recovery account.

## Evidence (spike, 2026-10-08)

multiOTP Credential Provider 5.10.2.2, native client path and real RDP on Windows 11 Pro 26300
(`UX8402ZE`) and the Windows 10 Pro test VM:

| Case | Result |
|---|---|
| Enrolled TOTP account: correct / wrong / empty code | allowed (0) / refused (99) / refused (99) |
| Account unknown to multiOTP | refused (21): unknown users are blocked |
| Account with a multiOTP `without2FA` record, empty code | allowed (0); any typed code refused (92) |
| RDP, `without2FA` account, default settings | code box shown; empty + Enter signs in; `123456` → "wrong one-time password" |
| RDP, `without2FA` account, `two_step_hide_otp=1` + `multiOTPWithout2FA=1` | password only, **no code screen** |
| Excluded recovery account, RDP and local | no code screen |

Provider value meanings (upstream README): `cpus_*` = `[0 both|1 remote|2 local|3 off][e only multiOTP|d others too]`;
`two_step_hide_otp` asks for the code in a second step; `multiOTPWithout2FA` disables the prompt
for `without2FA` users.

Still to verify before release (acceptance tests below): an enrolled, non-excluded account gets the
second-step code screen over RDP; a non-excluded user signing in locally sees no code screen.

## Behaviour

**Provider settings when protection is ON:** `cpus_logon=1e`, `cpus_unlock=1e`, `cpus_credui=3d`,
`two_step_hide_otp=1`, `multiOTPWithout2FA=1`, unchanged `excluded_account`. **OFF:** all three
`cpus_*` = `3d` (the two-step values may stay; they are inert while off).
`two_step_send_password` stays 0 (Windows passwords are never sent to the engine).

**Account coverage while ON** (every enabled local account must be known to multiOTP, or it is
blocked from RDP):

| Account | multiOTP record | Seat |
|---|---|---|
| Enrolled + verified | TOTP | 1 |
| Enrollment pending | TOTP (code required) | 1 |
| Not enrolled, enabled | `without2FA` (password only) | 0 |
| Excluded recovery account | none needed | 0 |
| Disabled Windows account | none | 0 |

Transitions: enroll → `without2FA` record replaced by TOTP; delete/revoke enrollment → back to
`without2FA`; new local account → `without2FA` added by reconciliation; account removed → record removed.

## Components

1. **Protection service (appliance API, runs under the existing LocalSystem service).**
   - New module `appliance/rdp_protection.py` owns provider registry reads/writes and flushes the
     key (`RegFlushKey`) after every write so a power cut cannot silently revert it.
   - Fixed value set only: no endpoint accepts registry names or values.
2. **Coverage reconciler.** Lists local accounts (existing `read_local_windows_accounts`),
   compares with Bliss records and multiOTP users, and creates or removes `without2FA` records
   through the existing multiOTP adapter. Runs on enable, after every enroll/delete/revoke,
   and every 10 minutes while ON. It never touches TOTP records and never deletes a user's
   enrollment.
3. **API endpoints** (owner/admin only, existing auth):
   - `GET /v1/rdp-protection`: state, provider values, recovery account, and accounts grouped as
     protected / password-only / disabled.
   - `POST /v1/rdp-protection/enable`: body: owner password re-entry, the enrolled account and a
     fresh code. Steps: re-authenticate the owner; check the license; verify the code through
     the installed native client (same call as today's script); reconcile coverage; write the
     provider settings; read back and flush; audit `rdp.protection.enabled`.
   - `POST /v1/rdp-protection/disable`: password re-entry, set `3d`, flush, audit
     `rdp.protection.disabled`.
   Any failure leaves protection exactly as before.
4. **Portal.**
   - The dashboard gets an "RDP protection" card: On/Off status, protected and password-only
     account lists, and the recovery account name.
   - After the first successful enrollment the panel offers "Protect RDP sign-in now?" with the
     re-auth + fresh-code form.
   - Turning protection off uses the same form.
5. **Guard rails.**
   - The excluded recovery account cannot be enrolled and never takes a seat.
   - Enable is refused if no non-excluded account is enrolled and verified.
   - Disable is always available to the owner, including when the license has lapsed.
6. **Kept for recovery only.** `Enable-RdpProtection.ps1 -Disable` (admin, offline) and console
   sign-in, which is never protected.

## Error handling

- Native verification fails: nothing changes; message "Code not accepted. Wait for the next code."
- Registry write or read-back mismatch: revert the values written in this request, then report.
- The reconciler cannot list accounts: enabling is refused. While ON, the failure is logged
  and retried; existing records are not removed.
- Engine unavailable while ON: RDP sign-in for protected accounts fails closed (as today). Console
  and the recovery account are unaffected.

## Testing

- **Unit tests** (fakes for registry, adapter, native client and license agent):
  - enable/disable success;
  - each failure leaves state unchanged;
  - authorization: readonly/operator 403, unauthenticated 401, wrong password 401;
  - the recovery account is refused enrollment;
  - reconciliation for every row of the coverage table;
  - registry writes limited to the fixed set and flushed.
- **Acceptance on the test VM, plus one Windows 11 machine:**
  - enrolled account over RDP: second-step code screen; correct/wrong/empty/reused codes;
  - a password-only account over RDP: no code screen;
  - an unknown (newly created, not yet reconciled) account: blocked until reconciliation, then
    password-only;
  - non-excluded account signing in locally: no code screen;
  - recovery account over RDP and locally: no code screen;
  - disable from the dashboard restores normal RDP;
  - enable, then a hard power-off one minute later: settings survive.

## Out of scope

Domain/AD accounts, per-user exemptions other than the single recovery account, protecting
local console sign-in, and SMS/email codes.
