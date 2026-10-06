# Reinstall and appliance identity recovery

The appliance identity is the `installation_id` plus the device Ed25519 key in
`C:\BlissMFA\bliss-mfa\.local\engine\license-state\`. The Bliss license is bound
to that identity. MFA users, OTP enrollment, the local owner, audit log, engine
secrets and certificate all live under `C:\BlissMFA\bliss-mfa\.local\`.

## Reinstall over retained data

Uninstalling removes the service, the credential provider and application
binaries. It deliberately keeps `C:\BlissMFA\bliss-mfa\.local`, backups and
pending-update recovery data.

To reinstall, run `Setup-BlissMFA.cmd` from a verified download. Do not delete
`C:\BlissMFA`. The installer:

1. Refuses to run while the service or credential provider is still installed.
2. Verifies the download SHA-256 and every file in the release manifest.
3. Extracts the release into `C:\BlissMFA\reinstall-staging` and runs
   `run-engine.py --inspect-retained` from it. No existing file has changed yet.
4. Stops with **"Retained appliance identity is lost. Nothing was changed."** if
   the appliance was activated but its identity files are missing or incomplete.
   It never creates a replacement identity over retained data.
5. Replaces application binaries only (`python`, `node`, `portal`, `php-runtime`,
   `multiotp-engine`, `installers`, application source). `bliss-mfa\.local`,
   `provider-backup` and `updates` are not modified.
6. Reuses the retained engine configuration, appliance configuration, identity,
   license lease, seat ledger, MFA users and enrollment.
7. Reinstalls the service and the credential provider with RDP enforcement
   **disabled**. After testing a fresh code, run `Enable-RdpProtection.cmd`.

The license does not need reactivation: the next heartbeat (shortly after
service start) refreshes the signed lease for the same identity.

## If the identity is genuinely lost

Typical causes: `C:\BlissMFA` was deleted, or only part of `license-state` was
restored. The license remains bound to the old identity, so a new installation
cannot activate with it ("License is already bound to another installation").

1. Prefer restoring the encrypted backup (see `engine-backup.py`) into a new
   directory and reinstalling over it. This preserves users and enrollment.
2. If no backup exists, contact Bliss support with the customer account email.
   Support verifies the account owner, then calls the admin-only
   `POST /v1/admin/licenses/{license_id}/force-release` endpoint. This unbinds
   the old identity and records `installation.force_released`.
3. The customer then installs fresh (empty `C:\BlissMFA`), generates a new
   activation code in the client portal (`/customer`, available for an active,
   unbound license), activates, and re-enrolls MFA users.

Self-service release from the customer portal is planned after the pilot.
Never edit `installation.json` or `device.key` by hand, and never copy a
license-state directory to a second machine: one license is bound to one
identity.

## What Bliss receives

Activation sends the activation code, `installation_id` and the device public
key. Heartbeats send the installation ID, protected-seat count, software
version, a hashed machine fingerprint and the local audit-chain head hash. No
usernames, OTP seeds, passwords or authentication traffic are sent.
