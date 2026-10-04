# Bliss Secure MFA

Bliss Secure MFA is an on-premise MFA appliance for Windows RDP and other
business access protected through multiOTP / FreeRADIUS.

The customer runs and manages the MFA control plane inside its own environment.
Bliss centrally provides licensing, billing, updates and support.

## Current product architecture

```text
CUSTOMER OFFICE
+-----------------------------------------------+
| Local portal                                  |
|   -> Appliance API                            |
|      -> License Agent                         |
|      -> multiOTP Adapter -> multiOTP/RADIUS   |
|                                               |
| MFA secrets, QR data, users and auth traffic  |
| remain local.                                 |
+----------------------+------------------------+
                       |
                       | licensing / billing only
                       v
              license.blissitek.ca
              +-------------------+
              | entitlement       |
              | installation bind |
              | signed leases     |
              | Stripe portal     |
              +-------------------+
```

## Licensing model

- One license is bound to one cryptographic installation identity.
- Normal online installations activate once and renew short-lived signed leases
  through challenge/response heartbeat.
- RDP licensing is per distinct protected RDP user, not per concurrent session.
- Seat limits are enforced by the local backend and license agent.
- Offline / air-gapped installations use annual prepaid signed licenses and a
  simple installation-code / activation-response flow.
- License expiry restricts commercial management operations but does not
  automatically disable already-working RDP authentication.
- A license must be released before normal transfer to another appliance.
- Bliss can force-release a failed installation from the central control plane.

## Repository layout

- `apps/appliance-api` — customer-local management API.
- `apps/appliance-portal` — customer-local management UI.
- `services/license-agent` — local device identity, lease validation and seat gate.
- `services/multiotp-adapter` — narrow allow-listed multiOTP integration.
- `apps/license-server` — Bliss central licensing and billing control plane.
- `website/managed-mfa` — product-page source.
- `apps/api` and `apps/portal` — earlier multi-tenant hosted-control-plane prototype;
  retained temporarily while the appliance migration is completed.

## Security principles

- multiOTP owns OTP secret material.
- Bliss licensing does not need usernames, OTP seeds, passwords or RADIUS traffic.
- The local portal never exposes arbitrary shell execution.
- Privileged local operations are role-gated and written to a hash-chained audit log.
- License leases are signed by Bliss and bound to a device-generated keypair.
- The Bliss signing private key never belongs on a customer appliance.
- Existing authentication is not intentionally shut down solely because a payment
  method expired.

## Status

The repository now contains the appliance/control-plane implementation
foundation. Production deployment still requires real multiOTP compatibility
testing, signing-key provisioning, TLS, database migrations, CI execution and
Stripe production configuration.

## Isolated Windows RADIUS testing

See [the disposable RADIUS harness](tools/windows-radius/README.md) for real loopback lifecycle checks using an extracted test kit, including support for paths containing spaces. These checks do not validate Windows login or RDP credential-provider integration.
