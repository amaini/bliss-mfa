# Subscription lifecycle follow-up — 4 October 2026

Canceled paid customers can now subscribe again using their existing Stripe
customer and local appliance license. Checkout is offered only after completed
cancellation; active, overdue, unpaid, paused and trialing subscriptions remain
in their existing billing flow. A scheduled cancellation does not create a
second subscription. [Stripe documents that fully canceled subscriptions cannot
be restarted](https://docs.stripe.com/billing/subscriptions/cancel); the replacement
therefore uses a new Checkout subscription for the same customer.

Replacement fulfillment requires verified payment, the configured price and seat
count, the same Stripe customer and a confirmed canceled previous subscription.
It preserves license ID, device identity/key and enrollment. Repeated and late
old checkout/subscription events cannot rebind or expire the replacement.
Customer-row locking and a fresh binding read protect the replacement from an
old event that was already waiting when the new payment committed.

Billing reconciliation preserves administrator revocation, including on delayed
invoice/subscription events and manual refresh. Revoked trial and paid licenses
cannot start another checkout. The customer portal has a **Refresh subscription
status** action that retrieves current Stripe state to recover a missed webhook
without creating a purchase. It is authenticated and limited to the customer's
own subscription. Synchronous provider retrieval/database work runs in a worker
thread so an incoming webhook does not freeze the public portal event loop.

## Validation

- Licensing suite on SQLite: 51 passed, two PostgreSQL-only tests skipped.
- Licensing suite on real PostgreSQL 17.11: 53 passed, none skipped. Uses a fresh
  loopback-only cluster and a non-superuser application role. Includes concurrent
  old-event/replacement delivery, data transfer, migration and customer lifecycle.
- Responsiveness test: a deliberately waiting Stripe retrieval does not prevent
  `/health` from responding before the webhook finishes.
- Browser checks against the exact HTML with synthetic local API data: expired
  paid accounts see checkout and price; active accounts do not see duplicate
  checkout; suspended accounts see billing recovery and status refresh.
- Focused Ruff and whitespace checks pass. No live customer, charge, Checkout
  session or email was created for these checks.
- Local browser probe and disposable PostgreSQL processes were stopped; bootstrap
  password files removed. Isolated database evidence remains protected locally.

The latest PostgreSQL evidence is `.local/pg-pilot-c252be66/tests.log` in the
primary checkout. This validates source behavior against PostgreSQL with mocked
Stripe API objects. It does not prove Stripe test-mode/live delivery or current
production deployment. No central database schema change was required.

## Deployment and launch status

These changes affect the hosted licensing backend and its customer page. The
hosted server is not embedded in the Windows archives. The current Windows
0.1.2 archives were rebuilt after the full service lint cleanup; use the current
hashes in `pilot-release-0.1.2-validation.md`. Build the licensing image
from this updated source and preserve the deployed PostgreSQL volume and existing
licensing private key. Confirm cancellation/renewal/returning-customer behavior
with Stripe test-mode acceptance before public launch.

Exact-release Windows installation, native desktop MFA, upgrade/rollback, paid
download and activation, deployed backup preservation and signed feed remain
pending. VM WinRM still times out; RDP reachability alone is insufficient. The
user is restoring access and has been asked which existing hosted-server access
method to use. The goal remains incomplete until those checks pass.
