# Windows pilot release candidate — 4 October 2026

Scope selected by the user: a small Windows paid pilot. Work builds on the
combined `release/client-updater-dashboard` branch and existing draft PR 6.
The release remains a prototype pending actual Windows installation and hosted
customer acceptance. Main and deployed customer artifacts were not replaced.

## Changes

- Appliance database schema version 1, serialized initialization and exact legacy
  schema adoption. Unexpected tables, column drift, missing uniqueness and newer
  versions fail startup rather than silently creating a replacement schema.
- Pending enrollments cannot become active through enable/disable commands.
  Locked users require unlock rather than enable.
- Packaging accepts external verified input paths and public keys, validates
  prerequisites before writing, refuses existing outputs and requires distinct
  Ed25519 license and update public keys.
- A separate update key was generated on this laptop with user authorization.
  Its directory and private file allow only the signing Windows account and
  SYSTEM. The private key is not in Git or customer artifacts. Retain a secure
  offline recovery copy before releasing to customers.
- Repeatable artifact verifier checks embedded installer hash, every appliance
  file hash, update signature/size/hash, pinned key, application contents and
  configured private values without printing those values.
- Packaged acceptance now waits for the appliance API, license agent and adapter,
  in addition to the static setup page, before owner bootstrap.
- CI now exercises packaging, key provisioning and backup tests on both Linux
  and Windows alongside updater tests.

## Verification on this laptop

| Check | Result |
|---|---|
| Appliance API, schema preservation and invalid state transitions | 34 passed |
| Licensing, customer, trial, payment and feed regression suite | 53 passed on real PostgreSQL; SQLite 51 passed and 2 PostgreSQL cases skipped |
| Updater, backup, packaging and signing-key tests | 40 passed in current CI; updater subset 27 passed locally |
| Licensing agent | 10 passed |
| Engine adapter/native/proxy | 41 passed |
| Next.js portal production build and TypeScript | Passed, 15.5.27 |
| Real HTTP portal origin checks | 18/18 passed |
| Previous candidate packaged local onboarding | 11/11 passed; repeat on RC2 during fresh installation |
| Prior packaged engine via native TLS/CGI | Fresh OTP passed; replay and incorrect OTP denied; repeat on current candidate during VM acceptance |
| Full service Ruff and whitespace checks | Passed |
| Artifact manifest, signature, keys and configured-secret verification | Passed, 4209 appliance files and 2084 update files |

The packaged onboarding used embedded runtimes and isolated ports/state. The
native CGI harness used controller Python dependencies with the package's
application, PHP and engine files. Neither check installed a credential provider
or changed Windows logon on this laptop. Owned test processes were stopped.

The first packaged onboarding attempt failed because the harness used static
page availability as readiness and reached the API before it was listening.
After checking backend readiness, a fresh extraction passed all eleven checks.
The first failed extraction is retained privately as evidence.

## Local candidate artifacts

Current private staging directory: `.local/pilot-release-0.1.2-rc2` in the primary checkout.
Built application source: `aec259fbceaeea787e9aceca76e90fe1029536ad`.
All seven [GitHub Appliance CI jobs](https://github.com/amaini/bliss-mfa/actions/runs/37256769971) passed on this source commit.
The earlier `.local/pilot-release-0.1.2` candidate is retained privately and superseded.
These files are built and verified locally, not published customer downloads.

| Artifact | SHA256 |
|---|---|
| appliance-deployment-0.1.2.zip | d56758cbbbd7a096b85a91c414341eec235633c86b2074f3bcf322d4e73dbfc3 |
| bliss-mfa-windows-pilot-0.1.2.zip | 57ede8cb2a2847b7dbe556f2d82c16da7dab5b99caa696ecaadd1c1b33a6cd9d |
| bliss-mfa-update-0.1.2.zip | 77ae94db9db60e01b66825e2d15d895cadfd18892100be81a939b76fee34c314 |

The detached signed feed is `bliss-mfa-update-0.1.2.signed.json` beside the ZIP.
Update public PEM SHA256:
`6d37a5b11ad0bb606d2c65ed10c98ea437b8e9503937a6a9382ce001ad153d42`.
Verification output is `verification.json`; packaged onboarding output is
`package-acceptance/verification-results.json`.

## Read-only public checks and remaining acceptance

- Hosted `/health` and `/customer`: HTTP 200.
- Anonymous installer metadata: HTTP 401 as expected.
- `/updates/stable.json`: HTTP 404; signed feed has not been deployed.
- Configured Stripe live price: active CAD 7.99 per user per month. Required
  webhook endpoint is enabled with checkout, subscription and invoice events.
  No charge, Checkout session or customer email was created by these checks.
- Restricted Stripe key can read the price/webhook list but `/v1/account` returns
  403. Resend's key is sending-only, so domain status could not be read; actual
  registration delivery remains an acceptance requirement.
- WinRM access restored. On Windows 10 Pro build 19045, RC2 passes all 15
  installed-service checks: exact hashes/signature, encrypted snapshot restore,
  0.1.1 to 0.1.2 upgrade, schema adoption, rollback, failed-readiness recovery,
  state preservation and pinned-key/version integration. After a real VM reboot,
  engine, adapter, appliance API, license agent and HTTPS portal all returned
  HTTP 200; BlissMFAEngine and WinRM are running with automatic startup.
  Fresh installation and interactive desktop/RDP OTP checks remain pending.
- Confirm real payment delivery, deployed PostgreSQL backup/account preservation,
  paid installer checksum/download and installed activation. Deploy the verified
  installer and public-only signed feed only after the VM release checks pass.

See `windows-paid-pilot.md` for the pilot journey, remaining acceptance and
operations requirements. These pending items prevent declaring the product
ready for paid customers.

The full lint cleanup preserves external-response error handling and declares FastAPI
dependency metadata safe in defaults. Current PostgreSQL evidence is
`.local/pg-pilot-c252be66/tests.log`, run with a non-superuser database role.
Subscription replacement preserves the installed license identity, rejects duplicate
active purchases and retains administrator revocation; see `subscription-lifecycle-validation.md`.

## Actual installed-service acceptance

Evidence: `.local/pilot-release-0.1.2-rc2/vm-installed-release.json` on the
controller and `C:\BlissMFA-TestRuns\pilot-aec259f\installed-release-results.json`
on the VM. The VM is left on 0.1.2 after successful upgrade/recovery checks.
The preexisting database contained one owner, one bootstrap seal and zero MFA
users: these checks preserve actual existing rows/configuration but do not prove
populated enrollment preservation. Add enrolled-user coverage in the next phase.

The first two rollback attempts were invalidated by the acceptance harness
leaving a SQLite inspection connection open. SQLite connection context managers
commit/roll back transactions but do not close the connection. Explicitly closing
both inspection connections allowed the full installed rollback and failure
recovery checks to pass. The bounded Windows PermissionError retry remains
covered by transient-lock and persistent-lock recovery tests; persistent errors
retain the journal and recovery snapshot. RC1 is retained as a superseded draft,
not evidence of a proven product rollback defect.
