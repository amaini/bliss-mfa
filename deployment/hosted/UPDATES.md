# Client application updates

Clients open **Start > Bliss MFA > Check for Bliss MFA updates**, accept Windows
administrator elevation, and type UPDATE after seeing the available version. The
website remains the place for purchasing and downloading the initial installer.
Existing installations need the updated installer integration provisioned once;
an existing 0.1.1 download does not acquire the shortcut by itself.

Updates are opt-in. Publishing a GitHub commit does not update client computers.
The updater fetches `https://license.blissitek.ca/updates/stable.json`, verifies an
Ed25519 signature using its pinned public key, downloads the signed HTTPS URL,
and verifies the exact ZIP size and SHA256 before touching the service.
Release versions must increase. Intermediate minimum versions are enforced.

## Signing and publishing

Use a **separate offline update signing key**, not the licensing signing key.
Keep the private key in private storage with a recovery copy. Put its public PEM
at `.local/deployment/update-public.pem` before building an appliance installer.
Only the public key ships. It is pinned in Program Files at installation; an
ordinary application update cannot replace that trust anchor.

Generate a key pair on your offline signing computer using OpenSSL:

```text
openssl genpkey -algorithm ED25519 -out update-private.pem
openssl pkey -in update-private.pem -pubout -out update-public.pem
```

Restrict the private key to the signing operator. Transfer only the public PEM
to the packaging computer. Never add either local key to a source commit.

Build and validate the complete appliance ZIP with `build-vm-package.py --appliance`
and the desired `--version`. Then build the application update:

```powershell
python scripts/publish-client-update.py --appliance .local/deployment/appliance-deployment.zip --output .local/deployment/bliss-mfa-update-0.1.2.zip --key PRIVATE_UPDATE_KEY_PATH --version 0.1.2 --minimum-version 0.1.1 --url https://license.blissitek.ca/updates/bliss-mfa-update-0.1.2.zip
```

The output `.signed.json` is the signed release manifest. Test the release on the
disposable Windows VM, including fresh, incorrect and empty OTP, before publishing.
Upload the immutable ZIP first. Atomically replace public `stable.json` with the
signed JSON only after the upload is complete. Retain earlier release ZIPs.

The Docker deployment agent must mount a dedicated **public-only** releases
directory read-only and set `APPLIANCE_UPDATE_DIRECTORY` to its container path,
for example `/releases/updates`. The licensing app exposes that directory at
`/updates`. Do not put server.env, private signing keys, customer databases, or
backups in this directory. No website-agent changes are required for this feed.

## Preservation, rollback and limits

This first update format replaces application files under `bliss-mfa` and the
built `portal`. It never replaces the Windows credential provider, service wrapper,
Python/Node/PHP runtimes or installed Python dependencies. Releases needing those
changes require a separately tested installer migration; do not publish them as
application-only updates. Keep code compatible with installed dependencies.
Obsolete files are retained; do not rely on deleting files in this format.

The updater stops BlissMFAEngine briefly, snapshots changed files and the entire
private `.local` state under the protected installation, then applies the release.
It runs the supervisor's complete startup checks, starts the service, and checks
health. Failure restores both old application files and private state, including
the database before migrations. Enrollment, keys, certificates and license are
never supplied by a release ZIP. Recovery console access must remain available
during the short maintenance window. No changes are made to RDP enforcement.

The transaction lives under `C:\BlissMFA\updates\pending`. Keep it private: it
contains enrollment and licensing state. It is replaced by the next update after
success. If Windows loses power mid-update, automatic service recovery may be
incomplete. Verify no updater process is running, remove the stale
`C:\BlissMFA\updates\update.lock` if present, then run elevated:

```powershell
& "$env:ProgramFiles\Bliss MFA\Update-BlissMFA.ps1" -Rollback
```

A pending journal blocks another update until recovery. If rollback fails, retain
the transaction and use the recovery administrator; do not delete the backup.
Update core/shortcut changes themselves currently require installer integration
again. The production feed and upgraded client installer must be deployed before
customers can use this capability.
