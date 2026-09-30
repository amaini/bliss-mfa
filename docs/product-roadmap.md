# Product Roadmap

## Architecture decision

The hosted multi-tenant management plane has been superseded by an
appliance-first product. Customer MFA management and authentication stay inside
the customer environment. Bliss centrally owns licensing, billing, releases
and support.

The earlier `apps/api` / `apps/portal` implementation remains in the branch
temporarily as migration reference and is not the intended production topology.

## Phase A — Appliance core

Implemented foundation:
- local owner/admin/operator/readonly accounts
- local RDP-user lifecycle API
- local enrollment and OTP verification
- local enable/disable/unlock/revoke/resync/delete operations
- local dashboard and management portal
- local hash-chained audit log and integrity verification
- allow-listed multiOTP sidecar boundary

Still required before production:
- validate every multiOTP CLI return code on a disposable real instance
- finish and validate safe token/device replacement semantics
- production migrations and backup/restore
- TLS packaging for localhost/LAN management

## Phase B — Licensing

Implemented foundation:
- one license bound to one installation identity
- Ed25519 device identity
- Bliss-signed leases
- online activation
- challenge-response heartbeat
- per-protected-RDP-user seat limits
- offline grace/restricted states
- signed release / force-release flow for online installations
- offline annual activation request/response flow
- trusted-time persistence
- machine-fingerprint anomaly signal
- local audit-head heartbeat checkpoint
- Stripe Customer Portal session hook

Still required before production:
- provision production Bliss signing keys
- signing-key rotation procedure
- database migrations
- admin UI for Bliss licensing staff
- Stripe subscription/seat webhook mapping after final products/prices exist
- automated heartbeat scheduler/service supervision
- compiled/TPM-backed license-agent hardening

## Phase C — Distribution

- signed appliance releases
- versioned upgrade manifests
- rollback-safe updater
- Windows/Linux appliance installation packages as selected
- local-only and LAN-management deployment profiles
- recovery/backup documentation
- automated diagnostics bundle

## Phase D — Commercial launch

- final RDP-seat pricing
- online monthly subscription
- offline annual/prepaid pricing
- Stripe products and customer portal configuration
- website product page
- service agreement and responsibility boundaries
- pilot offices
- production security review and load/failure testing

## Phase E — MSP automation

- Zammad onboarding/support tickets
- n8n licensing and renewal alerts
- expired/offline heartbeat warnings
- version/compliance reporting
- deployment-health reporting without customer MFA secret data
