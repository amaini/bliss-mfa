# Website-agent handoff

Publish the supplied `index.html` section as the Bliss MFA application page at
`https://blissitek.ca/bliss-mfa/`. Add “Bliss MFA” to the website navigation.
Use a full-width WordPress page and paste the section in a Custom HTML block,
or recreate its layout in the existing page builder. Keep the existing site's
header and footer. All CSS is scoped; no external fonts, scripts, images, secrets,
or plugin installation are required. Verify the existing `/contact/` route and
adjust that link if necessary. Use the current site logo in the normal header.
Suggested page title: “Bliss MFA for Windows & RDP | Bliss IT Solutions”.
Suggested meta description: “Configure Windows Remote Desktop MFA with a local
portal, authenticator enrollment, protected-user subscriptions, and guided setup.”

This page is ready to publish as a prototype preview. It intentionally uses
“Explore setup” instead of sending customers to an undeployed checkout. The
current Stripe subscription price is CAD 7.99 per protected user per month;
the website agent should reconfirm it before opening sales. No plan tiers,
setup charges, VPN support, or compatibility beyond the tested Windows target
are promised. Do not put Stripe/Resend credentials in WordPress or this page.

## Open client purchases after acceptance

Deploy the backend using `deployment/hosted/PORTAINER.md`. After HTTPS,
verification email, signed Stripe deliveries, paid downloads, activation, clean
Windows installation, and RDP acceptance pass:

1. Replace the hero “Explore setup” link with
   `https://license.blissitek.ca/customer`, labeled “Create your account”.
2. Replace the pricing “Purchases coming soon” badge with an account link to the
   same URL. Add “Client sign-in” in the site navigation to that URL.
3. Update the prototype availability copy to reflect the actual release status.
   Keep any remaining compatibility limitations visible.

Keep this route a product page. The account portal handles purchase, subscription,
download, and activation. It does not create WooCommerce orders.

## Review before publishing

Check desktop and mobile layouts, keyboard focus, FAQ expansion, anchor scrolling,
theme CSS interactions, and contact link. One page heading should remain: suppress
the theme's duplicate page title if necessary. For a standalone preview, open
`preview.html` locally; do not paste that outer HTML document into WordPress.
