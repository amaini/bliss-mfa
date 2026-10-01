# Hosted licensing and paid-client onboarding

For the selected Contabo/CyberPanel VPS with Portainer inside LXD, use
`PORTAINER.md` and `portainer-stack.yaml`. That option uses CyberPanel HTTPS
instead of launching Caddy alongside the existing website. The compose/Caddy
instructions below are an alternative for a dedicated host.

The existing blissitek.ca WordPress/WooCommerce site provides the product tab.
The included WordPress plugin's `[bliss_mfa]` shortcode links to the separate
licensing/client portal at https://license.blissitek.ca/customer. Purchases use
the existing Stripe subscription flow; they do not create WooCommerce orders.

## Deployment inputs

Use a Linux VPS or Docker-capable host with Docker Compose and persistent storage.
The WordPress hosting plan alone may not support this Python service.
Cloudflare nameservers were observed for blissitek.ca on 30 September 2026; the
license.blissitek.ca A record was absent at that check. Configure the subdomain
to reach the selected host, with inbound TCP 80 and 443 available for Caddy TLS.

Keep `.local/hosted/server.env` and `.local/hosted/license-private.pem` private.
The signing private key must remain on Bliss infrastructure; the customer
installer contains only its public key. Preserve the private key across upgrades.
Mount the tested customer release from
`.local/deployment/bliss-mfa-windows-prototype.zip`. Its SHA-256 must match
`APPLIANCE_RELEASE_SHA256` in the private environment file. The compose file
mounts both the private signing key and the installer read-only.

Required settings:

- `ADMIN_API_KEY`: private central-administration key.
- `STRIPE_SECRET_KEY`: the chosen live key; price and webhook must use the same mode.
- `STRIPE_RDP_PRICE_ID`: recurring, licensed, per-unit protected-user Price ID.
- `STRIPE_WEBHOOK_SECRET`: signing secret for the actual deployed endpoint.
- `CUSTOMER_PORTAL_URL=https://license.blissitek.ca`.
- `RESEND_API_KEY`: sending-only permission is sufficient.
- `MAIL_FROM`: a sender allowed by the Resend key's verified domain.
- `APPLIANCE_RELEASE_SHA256`: digest of the customer download, not the inner archive.

From this directory, run `docker compose up --build -d`. The backend explicitly
initializes its schema before starting one application worker. Caddy terminates
public HTTPS; the Python service has no public host port. Persistent volumes hold
the licensing database and Caddy certificate state. Preserve and back up both
the licensing database and signing key. Docker deployment is prepared but has
not yet been executed on a real host.

## Stripe webhook

Create the endpoint in the same Stripe mode as the key and price:

`https://license.blissitek.ca/v1/webhooks/stripe`

Subscribe to checkout.session.completed, checkout.session.async_payment_succeeded,
checkout.session.expired, customer.subscription.created, customer.subscription.updated,
customer.subscription.deleted, customer.subscription.paused,
customer.subscription.resumed, invoice.paid, and invoice.payment_failed.
After creation, save that endpoint's `whsec_...` signing secret privately and
restart the backend to load it. A preexisting secret cannot be verified as belonging
to this endpoint until Stripe's signed delivery reaches the deployed service.

The backend verifies signatures, deduplicates events, and retrieves current Stripe
checkout/subscription state before issuing or changing licenses. The customer
return page also requests server-side reconciliation. A client redirect by itself
never grants a license. Actual live payment fulfillment remains untested: the
completed provider checks were read-only Stripe price access and a Resend send
to its test recipient.

## Customer journey

1. Register, verify email through Resend, and sign in.
2. Choose protected-user seats and complete Stripe Checkout.
3. Obtain the active paid license, download the hash-checked Windows prototype,
   and generate an installation activation code.
4. Extract the download and run Setup-BlissMFA.cmd. The installer configures its
   local service and HTTPS portal and stages the signed upstream provider with
   RDP enforcement disabled.
5. Create the local portal owner, activate the license, enroll an existing local
   Windows account, and verify its authenticator.
6. Run Enable-RdpProtection.cmd with tested recovery access available, verify
   through the native Windows client, and complete the portal's RDP checklist.

The current package was exercised with isolated state through all six processes
and the management portal. The installed VM passed service/transport and backup
restoration checks. The new clean-install wrapper still needs its own clean-VM
acceptance test; release signing and broader Windows compatibility remain future
work. Keep the download identified as a prototype.
