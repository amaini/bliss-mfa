# Bliss Secure MFA Appliance API

This is the local single-customer management API installed inside each customer
environment.

It owns local administrator accounts, protected RDP user lifecycle, audit
history and the integration boundary to the local multiOTP adapter and license
agent.

The customer does not need direct multiOTP access. The API enforces licensed
RDP seat count before creating or re-enabling a protected user.

## Roles

- owner
- admin
- operator
- readonly

At least one owner remains required. Only the owner can release the appliance
license or create another owner.

## Authentication

The initial owner is created once with `SETUP_TOKEN`. Normal login uses local
credentials and short-lived JWT sessions. Production deployments must use a
random `JWT_SECRET` and TLS even when the portal is LAN-only.
