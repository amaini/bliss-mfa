# WordPress entry page

Upload the `bliss-mfa` plugin folder or its ZIP through WordPress Plugins.
Create an application page containing `[bliss_mfa]`, then add the page to the
website navigation. Set the HTTPS client portal URL under Settings → Bliss MFA
after the licensing backend is deployed.

This entry page links to the application's Stripe purchase and licensing flow.
It does not create a WooCommerce order or alter the existing store checkout.
MFA keys and Windows credentials never pass through WordPress. The application
backend must be hosted separately on a platform that runs its Python service;
the existing website's DNS can point a subdomain to that deployment.
