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

## Database upgrades

Startup initializes a clean database at schema version 1. An existing database
is adopted only if its tables, columns, column types, nullability, primary keys,
and required uniqueness constraints match the known appliance schema. Adoption
adds a version marker and preserves administrator credentials, bootstrap seal,
MFA users and audit history. Unknown or damaged schemas and future versions stop
API startup instead of silently creating replacement tables.

Use `python -m appliance.migrate` with the installed database configuration to
run this check separately. Stop the service and take an encrypted appliance
backup before upgrading. The signed application updater already snapshots the
private database before starting the new application and restores it on failed
startup. Future schema changes must introduce an explicit versioned migration;
changing model declarations alone is insufficient. This baseline version does
not import legacy identities held only in multiOTP engine state.
