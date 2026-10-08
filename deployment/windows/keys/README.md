# Public keys embedded in the Windows release

Only **public** keys belong here. Private signing keys stay on Bliss infrastructure
(licensing) and the offline signing computer (updates).

| File | Purpose | SHA-256 |
|---|---|---|
| `license-public.pem` | Verifies Bliss-signed license leases. Taken from the published `v0.1.0-windows-prototype` release (matches its manifest). | `6eaab9ec43df998cf1b19c696189c5598c285e32734129b7f92397327aad775b` |
| `update-public.pem` | Verifies signed application updates. Generated 2026-10-07 with `scripts/generate-update-keys.py` on the signing laptop (see the rotation section below). `scripts/build-release.py` refuses production builds unless its SHA-256 equals the pinned value. | `63983efc4773a356155f22c78fef67df768acc98f2d1af9eb15519a3777202cd` |

Never generate a replacement update key to unblock a build: installed appliances pin the
key they shipped with, and a different key cannot update them.

## Update key rotation, 2026-10-07

The private half of the previous update key (SHA-256
`6d37a5b11ad0bb606d2c65ed10c98ea437b8e9503937a6a9382ce001ad153d42`, pinned by the 0.1.2 pilot
RC and later test builds) could not be located, so no further update could ever be signed
for it. It was replaced before any customer installation was known to pin it: the public
update feed had not been deployed (`/updates/stable.json` returned 404).

Installations that pin the old key cannot receive signed updates. Migrate each one once,
deliberately, as an administrator: uninstall Bliss MFA (private data is retained), delete
`%ProgramFiles%\Bliss MFA\update-public.pem`, then run the new release's setup. Setup
reinstalls over the retained data and pins the new key. `Install-WindowsIntegration.ps1`
still refuses a silently changed key; deleting the old pin is the explicit migration step.

The new private key is in an access-restricted directory on the signing laptop (owner and
SYSTEM only). Keep at least two offline recovery copies before any customer release and
record their locations privately, outside Git.
