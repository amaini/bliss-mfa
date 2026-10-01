# Prototype implementation status — 30 September 2026

The target is paid-client self-service purchase, installation, activation,
enrollment, and usable Windows/RDP MFA. The selected website is blissitek.ca
WordPress/WooCommerce; its application tab links to a separate licensing backend.
Email uses Resend. The user identified a Contabo Ubuntu 24.04 VPS with CyberPanel
and Portainer inside LXD. A WordPress-ready preview page and private-port Portainer
deployment handoff are prepared for the user's publishing agent. Deployment and
backend acceptance remain required before the public paid journey can run.

## Implemented and checked

- Actual RDP sign-in with the phone authenticator was confirmed by the user and
  Windows Security event 4624/type 10. Wrong Windows password rejection and
  reconnect were confirmed. The existing account and seed remain preserved.
- The VM now runs the native TLS/CGI gateway, adapter, license agent, appliance API,
  built Next.js portal, and HTTPS proxy under automatic BlissMFAEngine service
  supervision. The old scheduled task is disabled as a fallback. All six ports
  bind to loopback.
- Eight installed-service native-client checks passed after correcting framed
  HTTP body reads: fresh OTP acceptance, replay/incorrect OTP rejection, empty
  native request rejection, trusted TLS health, and hidden administration.
  Authentication took about 1.6 seconds; replay and incorrect-code rejection each
  took under a second. Tests used isolated identities and did not consume phone codes.
- The installed portal passed TLS, anonymous-access, foreign Host/Origin, and
  unactivated-license checks. Its private setup page is readable by Abhishek.
  The local portal certificate is trusted on this VM; its key remains private.
- The packaged appliance passed 11 setup checks: first owner, secure cookies,
  single-use bootstrap, login, onboarding, and unlicensed seat denial. A database
  primary-key seal prevents concurrent first-owner creation.
- An encrypted snapshot of the installed appliance restored into a new directory.
  All restored components passed readiness, and the original service restarted.
  Wrong passphrase, corruption, nested paths, and existing-destination protection
  also have passing checks.
- The customer download includes fixed-hash setup, embedded runtimes, pinned
  wheels, a built portal, signed upstream provider/runtime installers, service
  setup, backup tooling, and recovery-aware RDP activation. The provider starts
  with enforcement disabled; activation requires licensed enrollment and fresh
  verification through the installed native client.
- Paid-client downloads require an active owned license and matching release hash.
  Customer verification/reset, Stripe checkout, signed/deduplicated webhooks,
  reconciliation, activation, and billing are implemented. Production backend
  startup explicitly initializes the schema.
- Read-only live Stripe access verified CAD 7.99 per user per month. Resend accepted
  a configuration test to its test recipient. No customer email, purchase, or
  charge was created.
- WordPress product-tab plugin and Docker/Caddy deployment are prepared. Customers
  receive only the licensing public key; the private key stays on Bliss infrastructure.

## Validation in this pass

- Appliance API: 19 tests pass.
- Adapter/native/proxy: 41 tests pass.
- Central licensing/customer/mail/migration/download: 21 tests pass.
- Encrypted backup: 6 tests pass.
- Isolated real native TLS/CGI fresh/replay/incorrect OTP checks pass.
- Portal production build, PHP syntax, and PowerShell installer parsing pass.
- Packaged setup: 11 checks pass; installed VM portal: 5 checks pass.
- Installed VM native service: 8 checks pass; full snapshot restoration passes.

After a manual restart, boot time was verified as 2026-10-01T01:26:38Z.
BlissMFAEngine started automatically, all six loopback listeners returned, and
the five portal and eight native-client checks passed again. Earlier lifecycle,
RADIUS, SID, outage, and scheduled-task results remain in the first-deployment reports.

## Remaining acceptance and deployment

- Provide the backend host/access, configure license.blissitek.ca DNS, and deploy
  the backend and WordPress entry point.
- Create the actual live-mode Stripe webhook with this backend URL and matching
  secret. No matching live endpoint appeared in the read-only check. Complete a
  real payment-to-activation acceptance test after deployment.
- Complete human first-owner setup on the VM.
- Test the new clean-install wrapper on a clean Windows target. Existing provider
  installation and runtime upgrades were tested; the new wrapper has not received
  full clean-install acceptance.
- Complete actual RDP bad/empty OTP, replay, and unlock acceptance after the upgrade.
  Native-client checks are independent evidence. Wrong password/reconnect were confirmed.
- Add release signing, broader Windows compatibility, explicit appliance migrations,
  and cross-service operation/crash reconciliation. Seat transactions do not make
  engine, appliance, and agent writes one atomic operation.
- Legacy engine-only identities are preserved outside the new portal database.
  Importing those identities is separate migration work.

Keep the download identified as a prototype until these checks pass.
