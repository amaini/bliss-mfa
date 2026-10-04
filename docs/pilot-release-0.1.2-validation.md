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
| Updater, backup, packaging and signing-key tests | 38 passed |
| Licensing agent | 10 passed |
| Engine adapter/native/proxy | 41 passed |
| Next.js portal production build and TypeScript | Passed, 15.5.27 |
| Real HTTP portal origin checks | 18/18 passed |
| Exact packaged local onboarding | 11/11 passed |
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

Current private staging directory: `.local/pilot-release-0.1.2-ci` in the primary checkout.
Built application source: `618e1c2d6bade38acde920a1255da00ff51c1370`.
All seven [GitHub Appliance CI jobs](https://github.com/amaini/bliss-mfa/actions/runs/37237072163) passed on this source commit.
The earlier `.local/pilot-release-0.1.2` candidate is retained privately and superseded.
These files are built and verified locally, not published customer downloads.

| Artifact | SHA256 |
|---|---|
| appliance-deployment-0.1.2.zip | b2f1767f2edb7a5c09d02c3eaac6262cc780b1850665756d7ce7e5014213d14a |
| bliss-mfa-windows-pilot-0.1.2.zip | 771f09e340e2c052b6d1bcbea8a5d73d05f8f1c5a71a587245f9722cb60d621c |
| bliss-mfa-update-0.1.2.zip | 6e10c494da8bf4b3fcab3a17ac29eb209fd62ead7c24d998f29ee6444c0dc518 |

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
- VM RDP port is reachable; WinRM times out. The user is restoring its existing
  remote command channel. Exact release clean installation, installed-service
  upgrade/rollback and Windows desktop OTP cases remain pending.
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
