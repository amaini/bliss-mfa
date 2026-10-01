# Deploy the 14-day trial

Trial terms: one protected Windows/RDP account, no card required, no automatic
charge, one trial per verified customer account. The 14 days start when the
customer clicks the trial button. Repeated requests never extend the deadline.
Separate verified email accounts can obtain separate trials; this prototype
does not enforce one trial per company or person.

## Docker agent

1. Back up PostgreSQL with the existing backup procedure. Preserve signing keys,
   mail/payment secrets, the installer mount and its checksum.
2. Pull current GitHub main and rebuild the license-server image. Do not reuse
   the old image merely by restarting its container.
3. Run `python -m license_server.migrate` with the backend's existing database
   environment and secrets. This transaction adds `customer_trials` and moves
   schema version 1 to 2; existing customers, licenses and payments are unchanged.
   The normal container startup migration also performs this upgrade.
4. Recreate the backend using the rebuilt image. Check `/health`, `/customer`,
   and the existing installer integrity check.
5. Using a dedicated verified test account, start a trial through the customer
   portal. Verify one seat, an expiry 14 days later, installer access and an
   activation code. Repeating the trial request must retain the original expiry.
   Do not make a live Stripe charge solely to test the upgrade.

Signed trial leases and offline grace are capped at the trial deadline. Expiry
blocks new activation and downloads and restricts existing appliance entitlement.
It does not uninstall Windows software or remove recovery access. A verified
paid checkout upgrades the same license and device binding; the next appliance
heartbeat retrieves the paid entitlement without reenrollment.

No new Stripe webhook events or installer package are required. Trial creation
does not call Stripe or send a payment. Current appliances understand the normal
online lease deadlines. After the schema upgrade, rollback requires restoring
the database backup with its matching old application; do not edit the schema
version or drop the trial table to run old code against newly written data.

## Website agent

After the Docker agent confirms trial availability, publish the updated
`website/windows-mfa/index.html` section to WordPress. Its trial button links to
`https://license.blissitek.ca/customer`. Customers register, verify their email,
sign in, and start their trial there. Keep installer downloads behind the account
portal; do not expose the ZIP in WordPress. Display the one-user, no-card,
no-automatic-charge terms and the start-time rule.
