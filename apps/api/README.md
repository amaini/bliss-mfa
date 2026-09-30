# Management API

Authoritative application layer for:

- authentication/session enforcement
- tenant boundaries
- RBAC
- MFA lifecycle workflows
- audit events
- subscription entitlement
- Stripe webhook processing

Planned stack: FastAPI/Python.

The API must never expose arbitrary multiOTP command execution.
