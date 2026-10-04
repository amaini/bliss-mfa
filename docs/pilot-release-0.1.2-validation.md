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
| Licensing, customer, trial, payment and feed regression suite | 38 passed, 1 optional PostgreSQL integration skipped |
| Updater, backup, packaging and signing-key tests | 38 passed |
| Licensing agent | 10 passed |
| Engine adapter/native/proxy | 41 passed |
| Next.js portal production build and TypeScript | Passed, 15.5.27 |
| Real HTTP portal origin checks | 18/18 passed |
| Exact packaged local onboarding | 11/11 passed |
| Exact packaged engine via native TLS/CGI | Fresh OTP passed; replay and incorrect OTP denied |
| Focused Ruff and whitespace checks | Passed |
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

Private staging directory: `.local/pilot-release-0.1.2` in the primary checkout.
These files are built and verified locally, not published customer downloads.

| Artifact | SHA256 |
|---|---|
| appliance-deployment-0.1.2.zip | cdc697236d72e4c99005c9fab5000beea5c550ae3dc67b2af7d6f41d5dc956ce |
| bliss-mfa-windows-pilot-0.1.2.zip | 56e2b5543196189f7a1b2c537e79d59a057e67f6cbbdf651872976a771643d1d |
| bliss-mfa-update-0.1.2.zip | 014b14d1b9840eba43db30031f301118a58b2c35d75296c5aaef3ddac3f467b6 |

The detached signed feed is `bliss-mfa-update-0.1.2.signed.json` beside the ZIP.
Update public PEM SHA256:
`6d37a5b11ad0bb606d2c65ed10c98ea437b8e9503937a6a9382ce001ad153d42`.
Verification output is `verification.json`; packaged onboarding output is
`package-acceptance-ready/verification-results.json`.

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
