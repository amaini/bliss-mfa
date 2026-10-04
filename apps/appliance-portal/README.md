# Local dashboard appearance

The local portal follows the supplied multiOTP Web Console layout: indigo top
navigation, a centered account table, an expandable disabled/revoked section,
enrollment actions and recent events. Dashboard and RDP Users share the same
account-management component. Get started, administrators, audit and licensing
remain available. The reference executable was inspected for templates/styles,
not installed or executed.

This is an adaptation to the existing Bliss API. It displays managed MFA records;
it does not claim to discover all Windows accounts, show Windows enablement, or
expose the reference executable's credential-provider settings. Such features
need corresponding backend support. Existing account lifecycle endpoints remain
in use, with inline confirmation and enrollment forms.

Build with the project's Next.js dependencies (`npm install`, `npm run build`).
For a standalone installation, package `.next/standalone` and copy `.next/static`
to its `.next/static` directory. Include this portal build in the appliance
installer or a tested signed application update. Updating WordPress or the
licensing Docker backend alone does not replace a client's installed dashboard.

Validation: production compilation/TypeScript and standalone startup passed.
Browser checks used isolated demo accounts, inspected desktop/mobile layouts,
opened the new-user form and verified recent-event rendering. They do not prove
actual Windows RDP sign-in or constitute an installed-client upgrade test.
