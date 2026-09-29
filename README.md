# Bliss Secure MFA

Private management and billing platform for Bliss IT Solutions' managed multi-factor authentication service.

## Architecture

This repository contains the customer/admin portal, management API, multiOTP adapter, billing integration, and deployment assets for **Bliss Secure MFA**.

The authentication engine itself remains isolated in `amaini/multiotp_Bliss`.

```text
blissitek.ca/managed-mfa
        |
   Stripe Checkout
        |
        v
mfa.blissitek.ca
  Bliss MFA Portal
        |
        v
   Management API
        |
        +--> PostgreSQL (tenants, RBAC, billing, audit)
        |
        v
 multiOTP Adapter
        |
        v
   multiOTP / RADIUS
```

## Security principles

- multiOTP owns MFA secrets.
- The portal database must not persist TOTP seeds, QR provisioning secrets, or raw authenticator secrets.
- No arbitrary shell-command execution is exposed through the management API.
- Every privileged MFA lifecycle action is auditable.
- Tenant boundaries are enforced server-side.
- Stripe controls commercial entitlement, not authentication state directly.
- Payment failure must never immediately lock an organization out of MFA.

## Planned applications

- `apps/portal` — customer and technician web portal.
- `apps/api` — management API.
- `services/multiotp-adapter` — constrained integration with multiOTP.
- `deployment` — Docker and production deployment definitions.
- `docs` — architecture, security, integration, and roadmap documentation.

## Initial milestone

Phase 0 establishes:

1. Repository foundation.
2. Architecture and security model.
3. multiOTP API capability discovery.
4. Tenant/RBAC model.
5. Enrollment and recovery state machines.
6. Stripe subscription architecture.
7. Local Docker development baseline.

No production deployment or authentication-engine mutation is part of Phase 0.
