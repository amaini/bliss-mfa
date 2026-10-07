# Bliss MFA Windows installer — 0.2 preview

This package installs the Windows appliance, can repair its installed release, and can receive administrator-approved updates from the Bliss licensing backend. It is an acceptance-test preview until clean install, repair and update have passed on a disposable Windows target. Do not replace the website's customer download with this preview before that acceptance test.

## Install

Extract the complete ZIP. Run `Setup-BlissMFA.cmd` and approve Windows elevation. The default installation directory is `C:\BlissMFA`. Setup installs the engine service and the upstream credential provider with enforcement disabled, imports the private localhost certificate, and creates portal/update/repair shortcuts. Automatic update checks run as SYSTEM every six hours, beginning ten minutes after installation. Backend failures leave the installed version running.

To choose a different directory or disable automatic updates:

```powershell
.\Setup-BlissMFA.ps1 -Root 'C:\BlissMFA' -ManualUpdates
```

Create the local owner, activate the license and enroll an existing Windows account using the local portal at `https://localhost:19443`. Keep a tested recovery administrator available. RDP enforcement remains a separate explicit step:

```powershell
& 'C:\BlissMFA\bliss-mfa\scripts\Enable-RdpProtection.ps1' -ProtectedUser 'DisposableTestUser' -RecoveryConfirmed
```

This step consumes a fresh code through the installed native client and affects the machine's RDP authentication path. Never perform it on an active production account during acceptance testing. Enroll all intended RDP users before enabling enforcement. Console recovery and the recorded recovery-administrator exception must be tested.

## Repair and update

Use Start → Bliss MFA → Repair Bliss MFA to restore the exact installed payload from the local verified cache. Repair preserves enrollment secrets, license identity, certificates, local administrators, audit data and the credential provider's enforcement/recovery settings. Interrupted replacement transactions are recovered from a private journal on the next updater run. The upstream provider MSI restores provider files; it is not upgraded to a different provider version. Keep recovery access available during repair.

Use Start → Bliss MFA → Check for Bliss MFA updates for an immediate check and installation of a published release. `Setup-BlissMFA.ps1 -Action check` checks without applying. `-Action update` applies an approved release. `-Action repair` repairs. The protected control runtime under Program Files runs independently of the appliance Python runtime, so damaged appliance runtime files can be repaired.

Updates verify an Ed25519 signature against the installed public key, expiry, product, channel, increasing sequence, archive length and SHA-256, and every payload file. Downloads require HTTPS. Unlisted files, duplicate Windows paths, directory traversal, links, private-state entries, provider-version changes and downgrade attempts are rejected. Release publication does not run arbitrary backend commands on clients.

Before replacing files, updates stop only this installation's service and confirm its runtime processes are stopped. They preserve `.local` and snapshot it while stopped. If the replacement fails readiness, the old binaries and pre-update private state are restored and the old service is restarted. If rollback itself fails, the private transaction directory is retained for recovery. A failed first install keeps its payload and receipt so Repair can resume it.

Existing 0.1.1 installations do not have a managed update receipt; this installer refuses an implicit migration. A tested migration path is required before upgrading the existing website package in place.

## Backend publication

Deploy the new license-server source. Configure `UPDATE_SIGNING_PRIVATE_KEY_FILE` with the private Ed25519 key corresponding to the installer public key. Keep it only on the backend, never in a customer ZIP or the web directory. Provision the `windows_releases` table with the included migration module. Existing license signing keys remain separate.

Publish the appliance payload at an immutable HTTPS URL that serves the ZIP directly without redirects. Obtain its version, sequence, channel, SHA-256, length and provider hash from `release-metadata.json`. Using the existing `X-Bliss-License-Admin` header:

1. `POST /v1/admin/updates/releases` with those fields plus `archive_url` and optional `notes`. Publication is staged with rollout disabled.
2. `PUT /v1/admin/updates/releases/{sequence}/rollout` with `{"enabled":true,"rollout_percent":5}` to begin a stable installation-based pilot; increase to 100 after acceptance.
3. Set `enabled` to false to withdraw the release. This stops future offers; it does not downgrade already updated clients. Publish a higher sequence for a corrective release.

Registered clients authenticate update checks using their licensing device key and a one-use challenge. Update availability is independent of payment status. Offline customers may repair locally; automatic updates require backend reachability and a registered installation. Backend rollout is delivered on the next scheduled check, rather than maintaining a permanent inbound connection to customer computers.

The preview public key must match the backend configuration before updates can work. A key pair generated for local release testing is not a production deployment. No backend has been changed or release published by building this package.

## Build and validate

Build the portal with `next build` and `output: standalone`. Run `python windows_installer/build_release.py --help` for required runtime inputs, engine source, public key, version, sequence and output directory. The bundled engine client receives the same HTTP framing fix and TLS peer verification as the staged provider client. Runtime binaries come from the reviewed Windows prototype; the build records their hashes in `runtime-provenance.json`. A release manifest records source revision and whether the tree was dirty. Keep only public keys in payloads.

Unit and transaction checks:

```powershell
python -m pytest windows_installer/tests -q
# From apps/license-server with its test dependencies:
python -m pytest -q
```

On a disposable Windows machine, retain console recovery and validate clean install, owner setup, license activation, enrollment and native verification; repair deleted appliance/provider files; publish a pilot update; verify automatic and manual update, seed/license/audit preservation, withdrawal, corrupted/forged archive rejection and startup rollback; then test RDP positive and negative cases. Record Windows build, provider version, release sequence and results. File transaction tests do not establish real Windows service/provider behavior.
