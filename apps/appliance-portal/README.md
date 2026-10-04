# Bliss appliance portal

The portal uses the visual direction of the original multiOTP Web Console:
indigo top navigation, a light workspace, compact account tables and forms,
and QR enrollment. It is implemented in Next.js and uses the existing
authenticated appliance API through the server-side proxy.

## Development

Set `APPLIANCE_API_URL` to the appliance API origin (see `.env.example`), then:

```sh
npm install
npm run dev -- --hostname 127.0.0.1
```

Open `http://localhost:3000` for local development. The existing origin check
uses Next.js's request origin; with this development setup, mutation requests
from `http://127.0.0.1:3000` can be rejected. Do not disable the origin check.

Use `npm run build` to compile and check TypeScript before preparing a release.
The production portal requires a configured API, a real administrator session,
and TLS. The screenshots used for design review contain disposable UI fixture
data, not a connected Windows environment.

## Account controls

- Enrollment is available for pending users, with QR/manual setup and inline
  verification of the first code.
- Disabled and revoked MFA records appear in a collapsible section. Seat usage
  follows the backend's protected-user flag and pending/active/locked states.
- User operations require a reason and an explicit inline confirmation. Buttons
  pause during the request; operation failures refresh the account list because
  a partial revoke can still persist the safe revoked state.
- Revoked identities have no enable or unlock controls. They must be deleted
  and recreated before a new enrollment. The API remains the authority for
  role permissions, licensing, lifecycle state, and operation results.

Windows account discovery and credential-provider policy settings from the
older application are not implemented in this portal. Its account status is
MFA state, not a claim about the Windows account or actual RDP enforcement.
The redesign does not install the old executable or credential-provider MSI.
