# Bliss Secure MFA Architecture

## Goal

Build a multi-tenant MSP management plane around multiOTP without turning the multiOTP codebase into the billing, customer, or technician portal.

## Trust boundaries

1. **Public website** — marketing and Stripe Checkout entry point.
2. **Portal** — authenticated customer/technician UI.
3. **Management API** — authorization, tenancy, audit, billing entitlement.
4. **multiOTP adapter** — narrow set of approved MFA lifecycle operations.
5. **multiOTP / RADIUS** — authentication engine and MFA secret owner.
6. **Stripe** — billing source of truth.

## High-level topology

```text
blissitek.ca/managed-mfa
          |
          v
   Stripe Checkout
          |
          v
   Stripe Webhooks ----------------------+
                                         |
                                         v
Internet ---> mfa.blissitek.ca ---> Management API ---> PostgreSQL
                                      |
                                      v
                                multiOTP Adapter
                                      |
                                      v
                                  multiOTP
                                      |
                                      v
                                  FreeRADIUS
                                      |
                               RDP / VPN / Apps
```

## Repository boundary

`amaini/multiotp_Bliss`
- multiOTP engine
- RADIUS integration
- minimal engine-level patches
- upstream tracking

`amaini/bliss-mfa`
- portal
- management API
- tenancy/RBAC
- billing
- audit
- multiOTP adapter
- deployment configuration

## Core rule

The Bliss API exposes business operations, never arbitrary multiOTP commands.

Examples:

- `create_user`
- `begin_totp_enrollment`
- `verify_enrollment`
- `replace_device`
- `revoke_device`
- `disable_user`
- `enable_user`
- `unlock_user`
- `generate_recovery_codes`
- `get_user_status`

## Data ownership

### multiOTP owns
- TOTP/HOTP seeds
- token state
- authentication counters
- OTP validation state
- RADIUS authentication data

### Bliss database owns
- organizations
- portal identities
- tenant membership
- RBAC
- device metadata
- enrollment workflow state
- audit events
- Stripe identifiers
- subscription entitlement
- commercial plan limits

The Bliss database must not persist raw MFA seed material.
