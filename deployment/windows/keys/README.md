# Public keys embedded in the Windows release

Only **public** keys belong here. Private signing keys stay on Bliss infrastructure
(licensing) and the offline signing computer (updates).

| File | Purpose | SHA-256 |
|---|---|---|
| `license-public.pem` | Verifies Bliss-signed license leases. Taken from the published `v0.1.0-windows-prototype` release (matches its manifest). | `6eaab9ec43df998cf1b19c696189c5598c285e32734129b7f92397327aad775b` |
| `update-public.pem` | Verifies signed application updates. **Not yet committed**: copy the production update public key from the signing computer. `scripts/build-release.py` refuses production builds unless its SHA-256 equals the pinned value. | `6d37a5b11ad0bb606d2c65ed10c98ea437b8e9503937a6a9382ce001ad153d42` (expected) |

Never generate a replacement update key to unblock a build: installed appliances pin the
key they shipped with, and a different key cannot update them.
