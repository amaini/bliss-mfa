# Security Model

## Non-negotiable controls

- MFA seeds must remain owned by multiOTP.
- QR provisioning payloads must be short-lived and must not be logged.
- No TOTP seed, provisioning URI, PIN, recovery code, password, or Stripe secret may appear in application logs.
- All tenant-scoped reads and writes must enforce tenant membership server-side.
- Technician permissions must be explicit and auditable.
- The adapter must use an allow-list of operations. It must never accept a raw shell command from the portal or API.
- Destructive operations require a reason and generate immutable audit events.
- Customer payment state must not directly disable authentication.

## Roles

### Bliss Super Admin
Full tenant and platform administration.

### Bliss Technician
Operational MFA lifecycle actions based on granted permissions.

### Customer Administrator
Manages users/devices only inside their organization.

### End User
Limited self-service enrollment, device replacement, and recovery flows.

## Initial permissions

```text
organizations.read
organizations.manage
users.read
users.create
users.update
users.disable
users.delete
mfa.enroll
mfa.replace
mfa.revoke
mfa.unlock
mfa.resync
mfa.recovery
audit.read
billing.read
billing.manage
platform.admin
```

## Sensitive workflows

### Device replacement

1. Identity verification occurs outside or inside the workflow according to policy.
2. Existing device/token is revoked.
3. A single-use enrollment transaction is created.
4. Provisioning material is presented only to the intended user.
5. User proves possession by submitting a valid OTP.
6. Enrollment is marked complete.
7. Audit event records actor, tenant, subject, action, reason, source IP, and outcome.

## Billing safety

Allowed effects of payment problems:
- warn customer
- alert Bliss
- prevent plan expansion
- prevent new enrollments after policy-defined grace period

Disallowed automatic effect:
- immediate shutdown of existing MFA authentication
