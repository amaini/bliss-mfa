# Prototype implementation status — 30 September 2026

## Current scope

The end goal remains self-service purchase, installation, activation, enrollment,
and usable Windows/RDP MFA. The user prioritized engine correctness and Windows
integration first; live domain, email, and payment wiring are deferred.

## Implemented in this development pass

- Local Git baselines for the imported Bliss and engine source trees.
- Real Windows PHP invocation in the adapter, preserving spaced paths and exit codes.
- Controlled adapter input, missing executable, and timeout responses without
  exposing submitted OTPs in errors.
- Transactional SQLite seat reservations/releases across simultaneous callers,
  with one-time legacy JSON import. Corrupt legacy state fails closed.
- Suspended/revoked licenses never turn into offline grace on lease expiration;
  an existing reservation cannot bypass restricted licensing.
- Signed challenge authorization for appliance billing access.
- Native authentication-only PHP router and isolated TLS transport verification.
- Default XML transport peer/hostname verification enabled in all three engine
  implementations. Trust must also be configured on the actual Windows client.
- Engine-only foreground launcher with private persistent state and local secrets.
- Portable RADIUS test paths and lifecycle harness updated for the seat ledger.
- Customer account/checkout foundation: verified-email registration, sign-in,
  password reset, customer-owned billing/license access, recurring per-seat
  checkout, signed webhooks, transactional event deduplication, current-subscription
  reconciliation, and one-time activation-code generation. Stripe calls are mocked
  in automated tests; no actual payment, email, or external deployment occurred.

## Validation

The first engine prototype is installed on the disposable Windows VM. Its signed
upstream credential provider uses a patched, certificate-verified native PHP
client. Twenty-four installed-client lifecycle checks pass, as do actual-default
client/SID, Windows password, controlled outage, and engine restart checks.
RDP-only enforcement and the non-admin test account are configured. Interactive
RDP acceptance is still pending. Automatic startup and authentication after reboot
pass after removing the scheduled task's default battery restriction. WinRM's
delayed startup was also disabled; its firewall retains the scoped Tailscale rule.
See `deployment/engine-auth/FIRST-DEPLOYMENT.md` for the installed layout and recovery.

- 95/95 live lifecycle checks passed through the real engine and four HTTP services.
- 16/16 loopback UDP PAP RADIUS checks passed after fixing spaced runtime paths.
- 17/17 native XML-over-HTTPS checks passed, including certificate trust rejection
  and same-code success with the trusted certificate.
- Unit tests and PHP regressions are tracked in the accompanying validation report.
- Engine launcher startup/readiness/shutdown check passed.

## Still required

Actual interactive Windows credential-provider/RDP proof, production service supervision,
cross-service operation journaling/crash reconciliation, appliance migrations,
backup/restore validation, client installation packaging and CA trust setup,
guided local onboarding, and release signing remain outstanding. Seat transactions
do not make engine/appliance/license writes one atomic transaction.

Customer purchase flow still requires real Stripe sandbox integration, SMTP
delivery, customer portal browser QA, production migrations, distributed rate
limits if scaled beyond one worker, pricing/tax decisions, and deployment. The
customer UI explicitly withholds unbuilt appliance downloads.

The existing hosted multi-tenant prototype remains a reference implementation.
The selected product architecture remains customer-local MFA with central
commercial licensing.
