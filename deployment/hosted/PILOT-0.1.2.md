# Windows paid pilot deployment handoff

The candidate is built from application commit
`aec259fbceaeea787e9aceca76e90fe1029536ad`. All seven Appliance CI jobs passed.
Current private files are in `.local/pilot-release-0.1.2-rc2` in the primary
checkout. They have not been published. Do not use the earlier candidate or the
historical v0.1.0 prototype hash in `INSTALLER.md` for this release.

| File | SHA256 |
|---|---|
| bliss-mfa-windows-pilot-0.1.2.zip | 57ede8cb2a2847b7dbe556f2d82c16da7dab5b99caa696ecaadd1c1b33a6cd9d |
| appliance-deployment-0.1.2.zip | d56758cbbbd7a096b85a91c414341eec235633c86b2074f3bcf322d4e73dbfc3 |
| bliss-mfa-update-0.1.2.zip | 77ae94db9db60e01b66825e2d15d895cadfd18892100be81a939b76fee34c314 |

## Prepare the hosted backend

Inspect the deployed database engine and schema before changing the stack. If
still using SQLite, follow `POSTGRESQL.md`, including the verified import guard.
If already using PostgreSQL, preserve the existing database volume, app/admin
password files, account rows, purchase ownership and licensing key. Take and
restore-test a consistent backup before replacing the backend. Do not rerun the
SQLite importer over existing PostgreSQL rows or remove its startup guard.

Build the licensing image from the current release branch on the Docker endpoint
managed by Portainer, retaining the previous image for recovery. Use the stack's
`bliss-license:postgres-v1` image name. The historical `:prototype` instructions
in `PORTAINER.md` describe the older SQLite deployment.

Create an empty `/opt/bliss-mfa/releases/updates` directory on that Docker
endpoint before applying `portainer-stack.yaml`. The stack mounts it read-only
at `/run/bliss-updates`; the application exposes it publicly at `/updates`.
Dedicated-host Compose instead uses `.local/deployment/public-updates`.
These directories must contain only signed public release assets. Never transfer
the update private key, server environment, licensing key, databases or backups
into either directory. An empty directory advertises no update.

## Publish after exact-release Windows acceptance

First complete clean installation, Windows MFA, installed upgrade/rollback and
backup recovery on the test target using the hashes above. Retain the evidence
in `docs/pilot-release-0.1.2-validation.md`.

Transfer the outer customer ZIP to `/opt/bliss-mfa/releases/windows.zip.new`
using the authorized private server connection. On the Docker endpoint:

```sh
set -eu
cd /opt/bliss-mfa/releases
echo '57ede8cb2a2847b7dbe556f2d82c16da7dab5b99caa696ecaadd1c1b33a6cd9d  windows.zip.new' | sha256sum --check
mv windows.zip.new windows.zip
```

Set `APPLIANCE_RELEASE_SHA256` to the outer ZIP digest above in the existing
private backend environment. Keep `APPLIANCE_RELEASE_FILE` at
`/run/bliss-release/windows.zip`. Recreate the backend container so its file bind
mount opens the new inode and its settings reload. Preserve database storage.

Upload `bliss-mfa-update-0.1.2.zip` and its `.signed.json` into the dedicated public
update directory as temporary files. Verify the ZIP digest, move it to the exact
immutable name `bliss-mfa-update-0.1.2.zip`, then atomically rename the signed JSON
to `stable.json`. Retain prior release ZIPs; do not replace an already published
version with different bytes. The signed download URL is
`https://license.blissitek.ca/updates/bliss-mfa-update-0.1.2.zip`.

## Confirm before taking customers

- Existing accounts can sign in and retain verified status, licenses and purchases.
- A real verification email reaches its inbox; the link works once.
- Confirm the existing paid purchase's signed Stripe delivery and installed
  activation without charging it again. Exercise failure scenarios in test mode.
- An authenticated paid/trial download has the outer ZIP hash above. Anonymous
  download metadata stays unauthorized.
- Fetch `stable.json` and the update ZIP through public HTTPS. Verify the
  signature with the installed pinned public key and the ZIP hash/size.
- Restart the backend and prove persistence; restore its backup into a separate
  database and compare account/license ownership. Do not test restoration over
  production data.

Public health and source CI alone do not prove any of these deployed results.
Server access is still required for hosted acceptance. VM remoting is restored;
installed upgrade, rollback and post-reboot service checks have passed. Fresh
installation and interactive Windows MFA acceptance remain pending.
